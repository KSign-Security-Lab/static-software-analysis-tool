from __future__ import annotations

from pathlib import Path

import pytest

from agent.rag import corpus

CWE_121 = """\
#include <string.h>

void copy_label_bad(const char *in) {
    char label[16];
    strcpy(label, in);
}
"""

CWE_121_FIXED = """\
#include <string.h>

void copy_label_fixed(const char *in) {
    char label[16];
    strncpy(label, in, sizeof(label) - 1);
    label[sizeof(label) - 1] = 0;
}
"""


def _tree(root: Path) -> Path:
    folder = root / "CWE-121_stack_based_buffer_overflow"
    folder.mkdir(parents=True)
    (folder / "copy_label_bad.c").write_text(CWE_121)
    (folder / "copy_label_fixed.c").write_text(CWE_121_FIXED)
    return root


def test_the_folder_names_the_weakness(tmp_path: Path) -> None:
    samples, skipped = corpus.read(_tree(tmp_path))
    assert {s.cwe for s in samples} == {"CWE-121"}
    assert skipped == 0


def test_the_filename_says_which_half_of_the_pair_it_is(tmp_path: Path) -> None:
    samples, _ = corpus.read(_tree(tmp_path))
    by_symbol = {s.symbol: s.variant for s in samples}
    assert by_symbol["copy_label_bad"] == corpus.VULNERABLE
    assert by_symbol["copy_label_fixed"] == corpus.FIXED


def test_an_unlabelled_sample_is_presumed_vulnerable() -> None:
    assert corpus.variant_of("example.c") == corpus.VULNERABLE


def test_a_folder_with_no_cwe_is_skipped_rather_than_fatal(tmp_path: Path) -> None:
    _tree(tmp_path)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "scratch.c").write_text("int main(void) { return 0; }\n")

    samples, skipped = corpus.read(tmp_path)
    assert skipped == 1
    assert all(s.cwe == "CWE-121" for s in samples)


def test_a_nested_folder_inherits_the_nearest_label(tmp_path: Path) -> None:
    assert corpus.cwe_of(tmp_path / "scraped" / "CWE-416_uaf" / "x.c", tmp_path) == "CWE-416"
    assert corpus.cwe_of(tmp_path / "misc" / "x.c", tmp_path) is None


def test_provenance_is_read_off_the_first_line() -> None:
    assert corpus.source_of("// source: CVE-2023-1 openssl@abc1234\nvoid f(void) {}") == (
        "CVE-2023-1 openssl@abc1234"
    )
    assert corpus.source_of("void f(void) {}") == ""


def test_only_functions_are_stored(tmp_path: Path) -> None:
    samples, _ = corpus.read(_tree(tmp_path))
    assert {s.symbol for s in samples} == {"copy_label_bad", "copy_label_fixed"}


@pytest.fixture()
def ingested(tmp_path: Path) -> Path:
    pytest.importorskip("fastembed", reason="needs the rag extra")
    root = _tree(tmp_path)
    corpus.ingest(root)
    return root


def test_re_ingesting_an_unchanged_corpus_does_no_work(ingested: Path, monkeypatch) -> None:
    def explode():
        raise AssertionError("the embedder was constructed for a corpus with nothing new")

    monkeypatch.setattr(corpus, "_embedder", explode)
    result = corpus.ingest(ingested)
    assert result["embedded"] == 0
    assert result["total"] == 2


def test_a_sample_deleted_from_disk_leaves_the_index(ingested: Path) -> None:
    (ingested / "CWE-121_stack_based_buffer_overflow" / "copy_label_fixed.c").unlink()
    result = corpus.ingest(ingested)
    assert result["removed"] == 1
    assert result["total"] == 1


def test_it_names_the_weakness() -> None:
    pytest.importorskip("fastembed", reason="needs the rag extra")
    root = Path(__file__).resolve().parents[3] / "corpus"
    if not root.is_dir():
        pytest.skip("the seed corpus is not checked out")
    corpus.ingest(root)

    probes = [
        ("CWE-78", 'void deploy(const char *tag) {\n    char line[200];\n    snprintf(line, sizeof(line), "docker push img:%s", tag);\n    system(line);\n}'),
        ("CWE-122", "char *clone_it(const char *s) {\n    char *p = malloc(strlen(s));\n    strcpy(p, s);\n    return p;\n}"),
        ("CWE-787", "void poke(int *arr, int i, int v) {\n    arr[i] = v;\n}"),
        ("CWE-134", "void say(const char *m) {\n    fprintf(stderr, m);\n}"),
        ("CWE-476", 'int sizeof_env(void) {\n    const char *p = getenv("PATH");\n    return (int)strlen(p);\n}'),
        ("CWE-190", "void *make(unsigned a, unsigned b) {\n    return malloc(a * b);\n}"),
        ("CWE-416", 'void done(struct conn *c) {\n    free(c);\n    printf("%d", c->fd);\n}'),
        ("CWE-22", 'FILE *grab(const char *f) {\n    char p[300];\n    snprintf(p, sizeof(p), "/data/%s", f);\n    return fopen(p, "r");\n}'),
    ]

    correct = [expected for expected, code in probes if corpus.search(code, limit=1)[0][1].cwe == expected]
    assert len(correct) >= 7, f"only {len(correct)}/{len(probes)} named the right CWE: {correct}"

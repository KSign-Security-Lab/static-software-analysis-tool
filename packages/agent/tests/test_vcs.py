"""Fetching a tree from a remote, and pushing a fix back.

`check_url` is the security boundary of the whole intake path: it is the only
thing standing between "paste a repository URL" and "make the server fetch
anything reachable from inside its network". It gets the most attention here.

Nothing in this file touches the network. Clones and pushes run against a bare
repository in `tmp_path`, with the URL check stubbed out where a local path
would obviously fail it -- so the plumbing is exercised for real while the
validation is tested on its own.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from agent.files import UploadRejected
from agent.vcs import (
    GitError,
    Origin,
    check_ref,
    check_url,
    clone,
    compare_url,
    label_for,
    open_pr,
    push,
    read_tree,
    redact,
)

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _run(*args: str, cwd: Path) -> None:
    subprocess.run(list(args), cwd=cwd, check=True, capture_output=True)  # noqa: S603 - fixed argv, no shell


# -- what the server is allowed to fetch --------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ssh://git@github.com/o/r.git",
        "git://github.com/o/r.git",
        "ext::sh -c 'curl evil'",
        "/etc/passwd",
        "git@github.com:o/r.git",
    ],
)
def test_only_http_urls_are_accepted(url: str) -> None:
    """Every one of these makes git do something other than fetch a repository.

    `file://` reads the server's disk, `ssh://` uses its keys, `ext::` hands git
    a command to run, and a bare path or scp-style address is not a URL at all.
    """
    with pytest.raises(UploadRejected):
        check_url(url)


def test_a_url_that_looks_like_an_option_is_refused() -> None:
    """git would read this as a flag, not an address."""
    with pytest.raises(UploadRejected):
        check_url("--upload-pack=touch /tmp/pwned")


def test_credentials_in_the_url_are_refused() -> None:
    """The URL is stored on the run as its origin, so a token in it would be
    persisted and shown back in the run list."""
    with pytest.raises(UploadRejected, match="인증"):
        check_url("https://user:token@github.com/o/r.git")


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "169.254.169.254", "10.0.0.1"])
def test_internal_addresses_are_refused_by_default(host: str) -> None:
    """Otherwise this endpoint is a port scanner for the network the API sits in,
    with the results readable in the run's file list."""
    with pytest.raises(UploadRejected, match="내부 주소|호스트를 찾을 수 없습니다"):
        check_url(f"https://{host}/o/r.git")


def test_the_private_range_can_be_opened_deliberately(monkeypatch: pytest.MonkeyPatch) -> None:
    """A lab running against a local Gitea sets this on purpose."""
    monkeypatch.setenv("AGENT_GIT_ALLOW_PRIVATE", "1")
    assert check_url("https://127.0.0.1/o/r.git") == "https://127.0.0.1/o/r.git"


def test_an_empty_or_overlong_url_is_refused() -> None:
    with pytest.raises(UploadRejected):
        check_url("   ")
    with pytest.raises(UploadRejected):
        check_url("https://example.com/" + "a" * 3000)


@pytest.mark.parametrize("ref", ["--force", "a..b", "a b", "--upload-pack=x", "/leading", ""])
def test_refs_that_are_not_names_are_refused(ref: str) -> None:
    if ref == "":
        assert check_ref(ref) is None
    else:
        with pytest.raises(UploadRejected):
            check_ref(ref)


def test_ordinary_refs_pass() -> None:
    assert check_ref("main") == "main"
    assert check_ref("release/1.2") == "release/1.2"
    assert check_ref(None) is None


# -- describing a remote ------------------------------------------------------


def test_the_label_is_what_somebody_would_recognise() -> None:
    assert label_for("https://github.com/o/myrepo.git", "main") == "myrepo@main"
    assert label_for("https://github.com/o/myrepo", None) == "myrepo"


def test_compare_urls_are_only_offered_for_hosts_we_know() -> None:
    """A guessed URL that 404s reads as the push having gone wrong."""
    assert compare_url("https://github.com/o/r.git", "fix") == "https://github.com/o/r/compare/fix?expand=1"
    assert compare_url("https://git.example.com/o/r.git", "fix") is None


def test_credentials_never_survive_a_message() -> None:
    """The one thing between a failed push and a token in the API log."""
    assert redact("fatal: https://x-access-token:ghp_secret@github.com/o/r.git not found") == (
        "fatal: https://***@github.com/o/r.git not found"
    )
    assert "ghp_secret" not in redact("remote: https://user:ghp_secret@example.com/x")


# -- reading a checkout -------------------------------------------------------


def test_read_tree_skips_the_git_directory_and_vendored_code(tmp_path: Path) -> None:
    """`.git` is most of the bytes of a shallow clone and none of the source."""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (tmp_path / "node_modules" / "dep").mkdir(parents=True)
    (tmp_path / "node_modules" / "dep" / "index.js").write_text("module.exports = 1\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")

    assert [each.path for each in read_tree(tmp_path).files] == ["src/app.c"]


def test_read_tree_ignores_symlinks(tmp_path: Path) -> None:
    """A repository can contain a link to anything the server can read."""
    (tmp_path / "real.c").write_text("int x;\n", encoding="utf-8")
    try:
        (tmp_path / "escape").symlink_to("/etc/passwd")
    except OSError:
        pytest.skip("this filesystem does not do symlinks")

    assert [each.path for each in read_tree(tmp_path).files] == ["real.c"]


def test_an_oversized_file_is_skipped_rather_than_refusing_the_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A checked-in generated artifact must not cost the reader the repository.

    Real projects carry them -- a 260 MB `pkix1.json` beside the C it came from --
    and the indexer skips anything over 1.5 MB anyway, so refusing the whole
    clone over one of them threw away every other file for nothing.
    """
    monkeypatch.setattr("agent.vcs.MAX_SINGLE_FILE_BYTES", 16)
    (tmp_path / "big.json").write_bytes(b"x" * 64)
    (tmp_path / "small.c").write_bytes(b"int x;")

    tree = read_tree(tmp_path)

    assert [each.path for each in tree.files] == ["small.c"]
    assert [(each.path, each.size, each.reason) for each in tree.skipped] == [("big.json", 64, "too_large")]


def test_a_repository_of_nothing_but_oversized_files_is_still_an_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Nothing was kept, so there is no tree to inspect -- and that is a different
    # thing from a clone that failed.
    monkeypatch.setattr("agent.vcs.MAX_SINGLE_FILE_BYTES", 16)
    (tmp_path / "big.json").write_bytes(b"x" * 64)

    with pytest.raises(UploadRejected, match="가져올 파일이 없습니다"):
        read_tree(tmp_path)


def test_the_total_cap_is_still_a_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The totals are the resource-exhaustion defence, and it stays a refusal.

    A thousand merely-large files each pass the per-file cap and still add up, so
    skipping cannot be the answer here the way it is for one absurd file.
    """
    monkeypatch.setattr("agent.vcs.MAX_UPLOAD_BYTES", 24)
    for name in ("a.c", "b.c", "c.c"):
        (tmp_path / name).write_bytes(b"x" * 16)

    with pytest.raises(UploadRejected, match="expands past"):
        read_tree(tmp_path)


def test_a_repository_with_nothing_in_it_is_an_answer(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    with pytest.raises(UploadRejected, match="가져올 파일이 없습니다"):
        read_tree(tmp_path)


# -- cloning ------------------------------------------------------------------


@pytest.fixture
def remote(tmp_path: Path) -> Path:
    """A real repository with one commit, to clone and push against."""
    work = tmp_path / "work"
    work.mkdir()
    (work / "app.c").write_text("void run(char *u) {\n    system(u);\n}\n", encoding="utf-8")
    _run("git", "init", "-q", "-b", "main", ".", cwd=work)
    _run("git", "config", "user.email", "t@t", cwd=work)
    _run("git", "config", "user.name", "t", cwd=work)
    _run("git", "add", "-A", cwd=work)
    _run("git", "commit", "-q", "-m", "first", cwd=work)

    bare = tmp_path / "remote.git"
    _run("git", "clone", "-q", "--bare", str(work), str(bare), cwd=tmp_path)
    return bare


@pytest.fixture
def local_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let a filesystem path through the URL check, for these tests only.

    The check is tested above on its own. Stubbing it here is what makes a real
    clone and a real push testable without a network or an http git server.
    """
    monkeypatch.setattr("agent.vcs.check_url", lambda url: url)
    monkeypatch.setattr("agent.vcs._authenticated", lambda url, token: url)


@needs_git
def test_clone_returns_the_tree_and_the_commit_it_is_at(tmp_path: Path, remote: Path, local_urls: None) -> None:
    """The commit is what makes a later push honest: the patch was computed
    against it, so applying it anywhere else applies it to other code."""
    cloned = clone(str(remote), "main", tmp_path / "out")

    assert cloned.ref == "main"
    assert len(cloned.commit) == 40
    assert [each.path for each in read_tree(cloned.root).files] == ["app.c"]


@needs_git
def test_cloning_a_branch_that_does_not_exist_is_the_remotes_answer(
    tmp_path: Path, remote: Path, local_urls: None
) -> None:
    with pytest.raises(GitError):
        clone(str(remote), "no-such-branch", tmp_path / "out")


# -- pushing ------------------------------------------------------------------


def _origin(url: str, commit: str) -> Origin:
    return Origin(kind="git", label="r@main", url=url, ref="main", commit=commit)


PATCH = """--- a/app.c
+++ b/app.c
@@ -1,3 +1,3 @@
 void run(char *u) {
-    system(u);
+    (void)u;
 }
"""


@needs_git
def test_push_applies_the_patch_and_creates_the_branch(tmp_path: Path, remote: Path, local_urls: None) -> None:
    cloned = clone(str(remote), "main", tmp_path / "out")

    pushed = push(_origin(str(remote), cloned.commit), PATCH, "ssat/fix", "token")

    assert pushed.branch == "ssat/fix"
    assert len(pushed.commit) == 40
    listed = subprocess.run(  # noqa: S603, S607 - fixed argv, no shell
        ["git", "branch", "--list", "ssat/fix"], cwd=remote, capture_output=True, text=True, check=True
    )
    assert "ssat/fix" in listed.stdout
    shown = subprocess.run(  # noqa: S603, S607 - fixed argv, no shell
        ["git", "show", "ssat/fix:app.c"], cwd=remote, capture_output=True, text=True, check=True
    )
    assert "(void)u;" in shown.stdout
    assert "system(u);" not in shown.stdout


@needs_git
def test_a_patch_that_does_not_apply_to_the_remote_is_refused_not_forced(
    tmp_path: Path, remote: Path, local_urls: None
) -> None:
    """The remote moved since the scan. The answer is to re-scan, not overwrite."""
    cloned = clone(str(remote), "main", tmp_path / "out")
    stale = PATCH.replace("system(u);", "nothing_like_this();")

    with pytest.raises(GitError, match="적용되지 않았습니다"):
        push(_origin(str(remote), cloned.commit), stale, "ssat/fix", "token")


def test_push_refuses_a_run_that_did_not_come_from_git() -> None:
    with pytest.raises(GitError, match="올릴 원격이 없습니다"):
        push(Origin(kind="zip", label="upload.zip"), PATCH, "ssat/fix", "token")


def test_push_refuses_an_empty_patch_a_bad_branch_and_a_missing_token() -> None:
    origin = _origin("https://github.com/o/r.git", "a" * 40)
    with pytest.raises(GitError, match="패치가 비어"):
        push(origin, "   ", "ssat/fix", "token")
    with pytest.raises(UploadRejected):
        push(origin, PATCH, "--force", "token")
    with pytest.raises(GitError, match="토큰"):
        push(origin, PATCH, "ssat/fix", "  ")


def test_pull_requests_are_only_attempted_where_we_know_the_api() -> None:
    """One forge on purpose. Elsewhere the caller still has a compare URL."""
    assert open_pr(Origin(kind="zip", label="x"), "b", "t", "title", "body") is None
    assert open_pr(_origin("https://git.example.com/o/r.git", "x"), "b", "t", "title", "body") is None

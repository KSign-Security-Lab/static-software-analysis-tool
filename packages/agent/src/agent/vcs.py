"""Getting a tree out of a git remote, and putting a fix back.

The other two intake paths hand us bytes a browser already had. This one makes
the *server* fetch a URL somebody typed, which is a different kind of thing: it
reaches out from inside the network the API runs in. So the validation here is
not about tidiness, it is the security boundary -- see `check_url`.

Cloning and pushing both shell out to `git` rather than linking a library. It is
the only implementation that is certain to agree with the `git apply` on the
reader's machine, and a patch that applies here and not there is worse than no
patch. Every call uses a fixed argv, never a shell.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import socket
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .files import (
    MAX_SINGLE_FILE_BYTES,
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_FILES,
    Skipped,
    Tree,
    Upload,
    UploadRejected,
    prepare,
    safe_name,
)
from .index import SKIP_DIRS

log = logging.getLogger(__name__)

__all__ = [
    "Origin",
    "Cloned",
    "Pushed",
    "GitError",
    "check_url",
    "clone",
    "read_tree",
    "push",
    "open_pr",
    "redact",
]

#: How long git gets. A clone that has not finished by now is not going to.
CLONE_TIMEOUT_SECONDS = 300
PUSH_TIMEOUT_SECONDS = 180

#: Set to allow cloning from loopback and private ranges.
#:
#: Off by default because the API has no authentication: without this, anybody
#: who can reach the web UI could use `POST /agent/runs/git` to probe the
#: network the server sits in and read the response back out of the file list.
#: A lab running against a local Gitea sets it deliberately.
ENV_ALLOW_PRIVATE = "AGENT_GIT_ALLOW_PRIVATE"

#: Only these. `ssh://` would use the server's keys, `file://` would read its
#: disk, and `ext::` hands git an arbitrary command to run.
ALLOWED_SCHEMES = frozenset({"http", "https"})

_BRANCH_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,200}$")


class GitError(RuntimeError):
    """git refused, or could not be reached. Message is already redacted."""


@dataclass(frozen=True)
class Origin:
    """Where a run's code came from.

    Stored on `run.meta["origin"]` for every intake path, not just git, so the
    run list can say what was scanned and the patch surface can tell whether
    pushing is even a possibility. `kind` is the discriminator; the git fields
    are None for an upload.
    """

    kind: str
    label: str
    url: str | None = None
    ref: str | None = None
    commit: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "kind": self.kind,
            "label": self.label,
            "url": self.url,
            "ref": self.ref,
            "commit": self.commit,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, str | None] | None) -> "Origin | None":
        if not raw or not raw.get("kind"):
            return None
        return cls(
            kind=str(raw["kind"]),
            label=str(raw.get("label") or ""),
            url=raw.get("url"),
            ref=raw.get("ref"),
            commit=raw.get("commit"),
        )


@dataclass(frozen=True)
class Cloned:
    """A checkout on disk, and the commit it is at."""

    root: Path
    commit: str
    ref: str | None


@dataclass(frozen=True)
class Pushed:
    """A branch that now exists on the remote."""

    branch: str
    commit: str
    compare_url: str | None = None
    pr_url: str | None = None


def redact(text: str) -> str:
    """Strip credentials out of anything on its way to a log or a response.

    git puts the whole remote URL in its error messages, and for a push that URL
    contains the caller's token. This is the only thing standing between "push
    failed" and a personal access token in the API log.
    """
    return re.sub(r"(https?://)[^/@\s]+@", r"\1***@", text)


def _env() -> dict[str, str]:
    """An environment git cannot block or leak in.

    `GIT_TERMINAL_PROMPT=0` and an askpass that answers nothing turn a private
    repo into a prompt failure instead of a request that hangs until it times
    out. The config vars stop the server's own git config -- credential helpers
    especially -- from applying to somebody else's URL.
    """
    env = dict(os.environ)
    env.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "/bin/true",
            "SSH_ASKPASS": "/bin/true",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GCM_INTERACTIVE": "never",
        }
    )
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return env


def _git(*args: str, cwd: Path | None = None, timeout: int) -> str:
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        env=_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        detail = redact((proc.stderr or proc.stdout or "").strip()) or f"git exited {proc.returncode}"
        raise GitError(detail)
    return proc.stdout


def check_url(raw: str) -> str:
    """The URL, if the server is allowed to fetch it. Raises `UploadRejected`.

    Three separate refusals, and each is a real attack rather than a tidiness
    rule:

    * a scheme other than http(s) makes git do something else entirely --
      `ext::` runs a command, `file://` reads the server's disk, `ssh://` uses
      the server's keys;
    * a leading `-` is read by git as an option, not a URL;
    * a host that resolves into loopback or a private range turns this endpoint
      into a port scanner for the network the API is deployed in, with the
      results readable in the run's file list.

    The host check resolves the name rather than pattern-matching it, because
    `internal.example.com` pointing at 127.0.0.1 is the interesting case and no
    amount of string matching finds it.
    """
    url = (raw or "").strip()
    if not url:
        raise UploadRejected("git 주소가 비어 있습니다")
    if url.startswith("-"):
        raise UploadRejected("git 주소가 옵션처럼 시작합니다")
    if len(url) > 2048:
        raise UploadRejected("git 주소가 너무 깁니다")

    parts = urlsplit(url)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UploadRejected(f"{parts.scheme or '알 수 없는'} 방식은 지원하지 않습니다. https 주소를 쓰십시오.")
    if not parts.hostname:
        raise UploadRejected("git 주소에 호스트가 없습니다")
    if parts.username or parts.password:
        # A token in the URL would be persisted on the run as its origin.
        raise UploadRejected("주소에 인증 정보를 넣지 마십시오. 공개 저장소만 가져올 수 있습니다.")

    if os.getenv(ENV_ALLOW_PRIVATE) == "1":
        return url

    try:
        resolved = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as err:
        raise UploadRejected(f"호스트를 찾을 수 없습니다: {parts.hostname}") from err

    for info in resolved:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global or address.is_private or address.is_loopback or address.is_link_local:
            raise UploadRejected(f"내부 주소는 가져올 수 없습니다: {parts.hostname}")
    return url


def check_ref(ref: str | None) -> str | None:
    """A branch or tag name git will take as a name and not as an option."""
    if ref is None or not ref.strip():
        return None
    name = ref.strip()
    if not _BRANCH_OK.match(name) or ".." in name:
        raise UploadRejected(f"브랜치 이름으로 쓸 수 없습니다: {name}")
    return name


def label_for(url: str, ref: str | None) -> str:
    """`myrepo@main`, for the run list. The path's last segment, no `.git`."""
    tail = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    name = tail[:-4] if tail.endswith(".git") else tail
    return f"{name or 'repo'}@{ref}" if ref else (name or "repo")


def clone(url: str, ref: str | None, into: Path) -> Cloned:
    """A shallow single-branch checkout of `url` at `ref`.

    `--depth 1` because the analysis reads the tree, never the history, and the
    difference on a real repository is seconds against minutes. It also caps
    what a hostile remote can make the server write, which `read_tree`'s caps
    then cap again.
    """
    checked = check_url(url)
    branch = check_ref(ref)

    args = ["clone", "--depth", "1", "--single-branch", "--no-tags"]
    if branch:
        args += ["--branch", branch]
    # `--` so a URL that still looks like an option cannot become one.
    args += ["--", checked, str(into)]

    try:
        _git(*args, timeout=CLONE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as err:
        raise GitError(f"저장소를 가져오는 데 {CLONE_TIMEOUT_SECONDS}초가 넘게 걸려 중단했습니다") from err

    commit = _git("rev-parse", "HEAD", cwd=into, timeout=30).strip()
    return Cloned(root=into, commit=commit, ref=branch)


def read_tree(root: Path) -> Tree:
    """Every file in a checkout, under the same rules as an uploaded zip.

    Same caps and the same name rules, deliberately: a repository is a tree
    somebody handed us and there is no reason it should be allowed to be bigger
    or stranger than an archive. `.git` goes first -- it is most of the bytes of
    a shallow clone and none of the source.

    A file over the per-file cap is skipped and reported rather than refusing the
    clone. Checked-in generated artifacts are ordinary in a real repository, and
    they are exactly the files the indexer would pass over anyway.
    """
    kept: list[Upload] = []
    skipped: list[Skipped] = []
    total = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        parts = relative.parts
        if any(part in SKIP_DIRS for part in parts[:-1]) or parts[0] in SKIP_DIRS:
            continue

        name = safe_name(relative.as_posix())
        if name is None:
            continue

        size = path.stat().st_size
        if size > MAX_SINGLE_FILE_BYTES:
            # Never read, so its bytes never count against the total.
            skipped.append(Skipped(path=name, size=size))
            continue
        total += size
        if total > MAX_UPLOAD_BYTES:
            raise UploadRejected(f"repository expands past {MAX_UPLOAD_BYTES} bytes")
        if len(kept) >= MAX_UPLOAD_FILES:
            raise UploadRejected(f"repository has more than {MAX_UPLOAD_FILES} files")

        kept.append(prepare(name, path.read_bytes()))

    if not kept:
        raise UploadRejected("저장소에 가져올 파일이 없습니다")
    return Tree(files=kept, skipped=skipped)


def _authenticated(url: str, token: str) -> str:
    """The remote URL with a token in it, for one push and nothing else.

    `x-access-token` is what GitHub expects and GitLab/Gitea accept as the user
    half of basic auth. The result is never stored and never logged -- `redact`
    covers the one place it could otherwise escape.
    """
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, f"x-access-token:{token}@{host}", parts.path, "", ""))


@dataclass
class _Committer:
    """Who the fix commit is by. Ours, and it says so."""

    name: str = "SSAT"
    email: str = "ssat@localhost"
    extra: list[str] = field(default_factory=list)


def push(origin: Origin, patch: str, branch: str, token: str, *, message: str | None = None) -> Pushed:
    """Apply `patch` on a fresh clone of `origin` and push it as `branch`.

    A fresh clone rather than the analysed tree, because the analysed tree is
    rows in a database with no history to commit against. Cloning at
    `origin.commit` is what makes the push honest: the patch was computed
    against that commit, so applying it anywhere else is applying it to code
    nobody looked at.

    Refuses rather than forcing. If the patch does not apply, the remote has
    moved on since the scan and the answer is to re-scan, not to overwrite.
    """
    if origin.kind != "git" or not origin.url:
        raise GitError("이 검사는 git 주소로 가져온 것이 아니어서 올릴 원격이 없습니다")
    if not patch.strip():
        raise GitError("올릴 패치가 비어 있습니다")
    name = check_ref(branch)
    if not name:
        raise GitError("브랜치 이름이 필요합니다")
    if not token.strip():
        raise GitError("토큰이 필요합니다")

    url = check_url(origin.url)
    with tempfile.TemporaryDirectory(prefix="ssat-push-") as tmp:
        root = Path(tmp) / "repo"
        # Full-depth is unnecessary, but the recorded commit has to be
        # reachable, and a shallow clone of the default branch may not contain
        # it. Fetching the one commit is the narrow version of that.
        _git("init", "-q", str(root), timeout=30)
        _git("remote", "add", "origin", url, cwd=root, timeout=30)
        try:
            _git("fetch", "--depth", "1", "origin", origin.commit or "HEAD", cwd=root, timeout=PUSH_TIMEOUT_SECONDS)
        except GitError as err:
            raise GitError(f"검사 당시의 커밋을 원격에서 찾지 못했습니다: {err}") from err
        _git("checkout", "-q", "-b", name, "FETCH_HEAD", cwd=root, timeout=60)

        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                ["git", "apply", "--index", "-"],
                cwd=str(root),
                env=_env(),
                input=patch,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except subprocess.TimeoutExpired as err:
            raise GitError("패치를 적용하는 데 시간이 너무 걸렸습니다") from err
        if proc.returncode != 0:
            raise GitError(f"패치가 원격 코드에 적용되지 않았습니다: {redact(proc.stderr.strip())}")

        who = _Committer()
        _git(
            "-c",
            f"user.name={who.name}",
            "-c",
            f"user.email={who.email}",
            "commit",
            "-q",
            "-m",
            message or "fix: SSAT 검사에서 확인된 취약점 수정",
            cwd=root,
            timeout=60,
        )
        commit = _git("rev-parse", "HEAD", cwd=root, timeout=30).strip()

        try:
            _git(
                "push", _authenticated(url, token), f"{name}:refs/heads/{name}", cwd=root, timeout=PUSH_TIMEOUT_SECONDS
            )
        except subprocess.TimeoutExpired as err:
            raise GitError("원격에 올리는 데 시간이 너무 걸렸습니다") from err

    return Pushed(branch=name, commit=commit, compare_url=compare_url(url, name))


def compare_url(url: str, branch: str) -> str | None:
    """Where to go to open a pull request by hand.

    Only for hosts whose compare path we actually know. A guessed URL that 404s
    is worse than no link, because it reads as the push having gone wrong.
    """
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    path = parts.path[:-4] if parts.path.endswith(".git") else parts.path
    path = path.rstrip("/")
    if host == "github.com":
        return f"https://github.com{path}/compare/{branch}?expand=1"
    if host == "gitlab.com":
        return f"https://gitlab.com{path}/-/merge_requests/new?merge_request[source_branch]={branch}"
    return None


def open_pr(origin: Origin, branch: str, token: str, title: str, body: str) -> str | None:
    """A pull request, on GitHub. None anywhere else.

    Deliberately one forge. Every other host has a different API, a different
    auth header and a different name for the thing, and a half-working
    abstraction over four of them would fail in a way nobody could read. Where
    this returns None the caller still has `compare_url`, which is a link a
    person can finish the job with.
    """
    if origin.kind != "git" or not origin.url:
        return None
    parts = urlsplit(origin.url)
    if (parts.hostname or "").lower() != "github.com":
        return None

    path = parts.path[:-4] if parts.path.endswith(".git") else parts.path
    owner_repo = path.strip("/")
    if owner_repo.count("/") != 1:
        return None

    import json
    import urllib.error
    import urllib.request

    base = origin.ref or "HEAD"
    payload = json.dumps({"title": title, "body": body, "head": branch, "base": base}).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310 - scheme is fixed https, host checked above
        f"https://api.github.com/repos/{owner_repo}/pulls",
        data=payload,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "ssat",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - as above
            return str(json.loads(response.read()).get("html_url") or "") or None
    except urllib.error.HTTPError as err:
        # Not fatal: the branch is pushed and the compare URL still works, so
        # this is a missing convenience rather than a failed operation.
        log.warning("could not open a pull request: %s", redact(str(err)))
        return None
    except (urllib.error.URLError, ValueError, OSError) as err:
        log.warning("could not open a pull request: %s", redact(str(err)))
        return None

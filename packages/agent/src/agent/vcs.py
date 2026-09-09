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
    too_big,
    Skipped,
    Tree,
    Upload,
    UploadRejected,
    is_binary,
    is_noise,
    is_source,
    prepare,
    safe_name,
)

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

CLONE_TIMEOUT_SECONDS = 300
PUSH_TIMEOUT_SECONDS = 180
ENV_ALLOW_PRIVATE = "AGENT_GIT_ALLOW_PRIVATE"
ALLOWED_SCHEMES = frozenset({"http", "https"})
_BRANCH_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,200}$")


class GitError(RuntimeError):
    pass


@dataclass(frozen=True)
class Origin:
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
    root: Path
    commit: str
    ref: str | None


@dataclass(frozen=True)
class Pushed:
    branch: str
    commit: str
    compare_url: str | None = None
    pr_url: str | None = None


def redact(text: str) -> str:
    return re.sub(r"(https?://)[^/@\s]+@", r"\1***@", text)


def _env() -> dict[str, str]:
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
    if ref is None or not ref.strip():
        return None
    name = ref.strip()
    if not _BRANCH_OK.match(name) or ".." in name:
        raise UploadRejected(f"브랜치 이름으로 쓸 수 없습니다: {name}")
    return name


def label_for(url: str, ref: str | None) -> str:
    tail = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    name = tail[:-4] if tail.endswith(".git") else tail
    return f"{name or 'repo'}@{ref}" if ref else (name or "repo")


def clone(url: str, ref: str | None, into: Path) -> Cloned:
    checked = check_url(url)
    branch = check_ref(ref)
    args = ["clone", "--depth", "1", "--single-branch", "--no-tags"]
    if branch:
        args += ["--branch", branch]
    args += ["--", checked, str(into)]

    try:
        _git(*args, timeout=CLONE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as err:
        raise GitError(f"저장소를 가져오는 데 {CLONE_TIMEOUT_SECONDS}초가 넘게 걸려 중단했습니다") from err

    commit = _git("rev-parse", "HEAD", cwd=into, timeout=30).strip()
    return Cloned(root=into, commit=commit, ref=branch)


def read_tree(root: Path) -> Tree:
    kept: list[Upload] = []
    skipped: list[Skipped] = []
    seen = 0
    total = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        name = safe_name(path.relative_to(root).as_posix())
        if name is None or is_noise(name):
            continue
        seen += 1
        if not is_source(name):
            continue
        if len(kept) >= MAX_UPLOAD_FILES:
            raise UploadRejected(f"소스 파일이 {MAX_UPLOAD_FILES}개를 넘습니다")

        size = path.stat().st_size
        if size > MAX_SINGLE_FILE_BYTES:
            skipped.append(Skipped(path=name, size=size))
            continue
        total += size
        if total > MAX_UPLOAD_BYTES:
            raise UploadRejected(too_big("저장소"))

        raw = path.read_bytes()
        if is_binary(raw):
            skipped.append(Skipped(path=name, size=size, reason="binary"))
            continue
        kept.append(prepare(name, raw))

    if not kept:
        raise UploadRejected(
            f"저장소에서 검사할 수 있는 소스를 찾지 못했습니다. 파일 {seen}개를 봤지만 "
            "C·C++·Java·Python·JS/TS·Go·Rust·C# 가운데 하나가 아니었습니다."
        )
    return Tree(files=kept, skipped=skipped, seen=seen)


def _authenticated(url: str, token: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, f"x-access-token:{token}@{host}", parts.path, "", ""))


@dataclass
class _Committer:
    name: str = "SSAT"
    email: str = "ssat@localhost"
    extra: list[str] = field(default_factory=list)


def push(origin: Origin, patch: str, branch: str, token: str, *, message: str | None = None) -> Pushed:
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
        log.warning("could not open a pull request: %s", redact(str(err)))
        return None
    except (urllib.error.URLError, ValueError, OSError) as err:
        log.warning("could not open a pull request: %s", redact(str(err)))
        return None

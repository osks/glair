from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def _git(*args: str, cwd: Path | None = None) -> str:
    r = subprocess.run(
        ("git", *args), cwd=cwd, capture_output=True, text=True, check=False,
    )
    if r.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def in_repo(cwd: Path | None = None) -> bool:
    r = subprocess.run(
        ("git", "rev-parse", "--show-toplevel"),
        cwd=cwd, capture_output=True, text=True,
    )
    return r.returncode == 0


def repo_root(cwd: Path | None = None) -> Path:
    return Path(_git("rev-parse", "--show-toplevel", cwd=cwd).strip())


def head_sha(cwd: Path | None = None) -> str:
    return _git("rev-parse", "HEAD", cwd=cwd).strip()


def current_branch(cwd: Path | None = None) -> str | None:
    """Return branch name, or None when HEAD is detached."""
    name = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd).strip()
    return None if name == "HEAD" else name


def porcelain_status(cwd: Path | None = None) -> list[str]:
    """Non-empty list means the working tree is dirty."""
    out = _git("status", "--porcelain", cwd=cwd)
    return [line for line in out.splitlines() if line]


def remote_url(name: str = "origin", cwd: Path | None = None) -> str | None:
    """Return the remote URL, or None if the remote doesn't exist."""
    try:
        return _git("remote", "get-url", name, cwd=cwd).strip() or None
    except GitError:
        return None

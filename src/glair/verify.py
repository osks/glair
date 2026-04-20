from __future__ import annotations

from pathlib import Path
from typing import Literal

import click

from glair import bundle as bundle_mod
from glair import gitstate

_BUNDLE_PREFIX = f"{bundle_mod.BUNDLE_ROOT}/"


def _porcelain_path(line: str) -> str:
    # "XY <path>" — we only need the path. Quoted/encoded paths (for
    # filenames with special chars) are handled well enough for v1 by
    # ignoring the quoting; verify is best-effort on exotic names.
    return line[3:].strip('"')


def _filter_bundle(dirty: list[str]) -> list[str]:
    return [l for l in dirty if not _porcelain_path(l).startswith(_BUNDLE_PREFIX)]

Status = Literal["ok", "warn", "fail"]
Check = tuple[str, Status, str]


def run(bundle_arg: str | None) -> int:
    """Run verify against the given (or auto-resolved) bundle.

    Prints a check table; returns the intended exit code (0 = all non-fail)."""
    b = bundle_mod.resolve_bundle(bundle_arg)
    meta = bundle_mod.load_meta(b)
    checks: list[Check] = []

    if not gitstate.in_repo():
        checks.append(("git repo", "fail", f"cwd is not a git repo ({Path.cwd()})"))
        _render(checks)
        return 1

    root = gitstate.repo_root()
    checks.append(("git repo", "ok", str(root)))

    try:
        head = gitstate.head_sha()
    except gitstate.GitError as e:
        checks.append(("head sha", "fail", str(e)))
        _render(checks)
        return 1

    want_head = meta["head_sha"]
    if head == want_head:
        checks.append(("head sha", "ok", f"{head[:12]} (matches meta.json)"))
    else:
        checks.append((
            "head sha", "fail",
            f"HEAD is {head[:12]}, bundle expects {want_head[:12]}",
        ))

    dirty = _filter_bundle(gitstate.porcelain_status())
    if not dirty:
        checks.append(("working tree clean", "ok", ""))
    else:
        first = dirty[0]
        more = f" (+{len(dirty)-1} more)" if len(dirty) > 1 else ""
        checks.append(("working tree clean", "fail", f"{first}{more}"))

    branch = gitstate.current_branch()
    want_branch = meta.get("source_branch")
    if branch is None:
        checks.append(("branch", "ok", "detached HEAD"))
    elif branch == want_branch:
        checks.append(("branch", "ok", branch))
    else:
        checks.append((
            "branch", "warn",
            f"{branch} (bundle source_branch is {want_branch})",
        ))

    _render(checks)
    return 1 if any(s == "fail" for _, s, _ in checks) else 0


def _render(checks: list[Check]) -> None:
    for name, status, detail in checks:
        mark = {"ok": "ok  ", "warn": "warn", "fail": "fail"}[status]
        line = f"{mark} {name:<20} {detail}" if detail else f"{mark} {name}"
        click.echo(line)

"""Fetch a merge request from GitLab and write a review bundle.

Network I/O lives in ``gitlab_client``. This module is mostly pure string
builders plus an orchestrator; the builders take plain dicts so tests can
drive them with fixtures.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from glair import bundle as bundle_mod


CLOSES_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)",
                       re.IGNORECASE)


@dataclass(frozen=True)
class MRPayload:
    """Everything we need from GitLab to write a bundle. Kept as plain
    attribute dicts so tests can construct one without hitting the API."""
    project: dict      # project attributes (path_with_namespace, id, …)
    mr: dict           # MR attributes (iid, title, diff_refs, …)
    changes: list[dict]         # `changes` array from /merge_requests/:iid/changes
    linked_issues: list[dict]   # each: iid, title, description, project_id, web_url


# --- builders ---------------------------------------------------------------

def build_meta(payload: MRPayload) -> dict:
    mr = payload.mr
    refs = mr.get("diff_refs") or {}
    return {
        "project_id": payload.project["id"],
        "project_path": payload.project["path_with_namespace"],
        "mr_iid": mr["iid"],
        "mr_id": mr["id"],
        "web_url": mr["web_url"],
        "title": mr["title"],
        "author": (mr.get("author") or {}).get("username"),
        "source_branch": mr["source_branch"],
        "target_branch": mr["target_branch"],
        "base_sha": refs.get("base_sha"),
        "start_sha": refs.get("start_sha"),
        "head_sha": refs.get("head_sha"),
        "created_at": mr.get("created_at"),
        "labels": mr.get("labels") or [],
        "milestone": (mr.get("milestone") or {}).get("title") if mr.get("milestone") else None,
        "draft": bool(mr.get("draft") or mr.get("work_in_progress")),
    }


def build_mr_md(payload: MRPayload) -> str:
    mr = payload.mr
    author = (mr.get("author") or {}).get("username", "?")
    labels = ", ".join(mr.get("labels") or []) or "—"
    closes = _parse_closes(mr.get("description") or "")
    closes_line = (
        "**Closes:** " + ", ".join(f"#{n}" for n in closes) + "\n"
        if closes else ""
    )
    draft_line = "**Draft:** yes\n" if mr.get("draft") or mr.get("work_in_progress") else ""
    lines = [
        f"# {mr['title']}",
        "",
        f"**Author:** @{author}",
        f"**Branch:** `{mr['source_branch']}` → `{mr['target_branch']}`",
        f"**Labels:** {labels}",
    ]
    if closes_line:
        lines.append(closes_line.rstrip())
    if draft_line:
        lines.append(draft_line.rstrip())
    lines.extend(["", "---", "", (mr.get("description") or "").rstrip(), ""])
    return "\n".join(lines)


def build_issue_md(issue: dict) -> str:
    return (
        f"# {issue['title']}\n"
        f"\n"
        f"**Issue:** #{issue['iid']} · {issue.get('web_url', '')}\n"
        f"\n"
        f"---\n"
        f"\n"
        f"{(issue.get('description') or '').rstrip()}\n"
    )


def build_changes_md(changes: list[dict]) -> str:
    lines = ["| path | status | + | - |", "|---|---|---|---|"]
    notes: list[str] = []
    for c in changes:
        path = c.get("new_path") or c.get("old_path") or "?"
        status = _status_for(c)
        added, deleted = _count_changes(c.get("diff") or "")
        if c.get("renamed_file"):
            notes.append(f"- `{path}` renamed from `{c['old_path']}`")
        lines.append(f"| `{path}` | {status} | +{added} | -{deleted} |")
    out = "\n".join(lines) + "\n"
    if notes:
        out += "\n" + "\n".join(notes) + "\n"
    return out


def split_diffs(changes: list[dict]) -> list[tuple[str, str]]:
    """Return (repo-relative path, diff text) for each file that has a diff.

    The path mirrors the repo layout under ``diffs/``. Deletions use
    ``old_path``; everything else uses ``new_path``.
    """
    out: list[tuple[str, str]] = []
    for c in changes:
        diff = c.get("diff") or ""
        if not diff:
            continue
        path = (
            c.get("old_path") if c.get("deleted_file") else c.get("new_path")
        ) or c.get("new_path") or c.get("old_path")
        if not path:
            continue
        out.append((path, diff))
    return out


def _status_for(c: dict) -> str:
    if c.get("new_file"):
        return "added"
    if c.get("deleted_file"):
        return "deleted"
    if c.get("renamed_file"):
        return "renamed"
    return "modified"


def _count_changes(diff_text: str) -> tuple[int, int]:
    added = deleted = 0
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            deleted += 1
    return added, deleted


def _parse_closes(description: str) -> list[int]:
    seen: dict[int, None] = {}
    for m in CLOSES_RE.finditer(description):
        seen.setdefault(int(m.group(1)), None)
    return list(seen)


# --- orchestration ----------------------------------------------------------

def write_bundle(payload: MRPayload, out_dir: Path) -> Path:
    """Write the bundle under ``out_dir``. Returns the bundle directory."""
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / bundle_mod.META_FILENAME).write_text(
        json.dumps(build_meta(payload), indent=2) + "\n"
    )
    (out_dir / "mr.md").write_text(build_mr_md(payload))
    (out_dir / "CHANGES.md").write_text(build_changes_md(payload.changes))

    if payload.linked_issues:
        issues_dir = out_dir / "issues"
        issues_dir.mkdir(exist_ok=True)
        for issue in payload.linked_issues:
            (issues_dir / f"{issue['iid']}.md").write_text(build_issue_md(issue))

    diffs_dir = out_dir / "diffs"
    for path, diff_text in split_diffs(payload.changes):
        target = diffs_dir / f"{path}.diff"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(diff_text if diff_text.endswith("\n") else diff_text + "\n")

    return out_dir


def default_out_dir(iid: int) -> Path:
    return Path(bundle_mod.BUNDLE_ROOT) / str(iid)

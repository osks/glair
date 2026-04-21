"""Parse and validate the agent's result directory.

Also used by ``glair post`` for schema-level validation before posting.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ALLOWED_VERDICTS = ("comment", "approve", "request_changes")
ALLOWED_SIDES = ("new", "old")


@dataclass(frozen=True)
class Comment:
    filename: str
    path: str
    body: str
    side: str = "new"
    line: int | None = None
    line_start: int | None = None
    line_end: int | None = None


@dataclass(frozen=True)
class Result:
    summary: str
    verdict: str
    comments: list[Comment]


class ResultError(ValueError):
    """Raised when result/ content is malformed."""


def load(bundle: Path) -> Result:
    """Parse and validate the bundle's ``result/`` directory.

    Raises ``ResultError`` with a concatenated error report on any failure.
    """
    result_dir = bundle / "result"
    errors: list[str] = []

    if not result_dir.is_dir():
        raise ResultError(f"no result/ directory at {result_dir}")

    summary_text = ""
    summary_path = result_dir / "summary.md"
    if not summary_path.is_file():
        errors.append("missing result/summary.md")
    else:
        summary_text = summary_path.read_text()
        if not summary_text.strip():
            errors.append("result/summary.md is empty")

    verdict = ""
    verdict_path = result_dir / "verdict"
    if not verdict_path.is_file():
        errors.append("missing result/verdict")
    else:
        verdict = verdict_path.read_text().strip()
        if verdict not in ALLOWED_VERDICTS:
            errors.append(
                f"result/verdict is {verdict!r}, expected one of {ALLOWED_VERDICTS}"
            )

    comments: list[Comment] = []
    comments_dir = result_dir / "comments"
    valid_paths = _changed_paths(bundle)
    if comments_dir.is_dir():
        for f in sorted(comments_dir.iterdir()):
            if not f.is_file() or not f.name.endswith(".md"):
                continue
            try:
                c = _parse_comment_file(f)
            except ValueError as e:
                errors.append(f"comments/{f.name}: {e}")
                continue
            if c.path not in valid_paths:
                errors.append(
                    f"comments/{f.name}: path {c.path!r} is not in the bundle's diffs"
                )
                continue
            comments.append(c)

    if errors:
        raise ResultError("\n".join(errors))

    return Result(summary=summary_text, verdict=verdict, comments=comments)


def _parse_comment_file(f: Path) -> Comment:
    raw = f.read_text()
    fm, body = _split_frontmatter(raw)
    return _build_comment(f.name, fm, body)


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing YAML frontmatter (expected leading `---`)")

    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        raise ValueError("unterminated frontmatter (no closing `---`)")

    fm: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError(f"malformed frontmatter line: {line!r}")
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()

    body = "\n".join(lines[end + 1 :]).strip()
    if not body:
        raise ValueError("comment body is empty")
    return fm, body


def _build_comment(filename: str, fm: dict[str, str], body: str) -> Comment:
    if "path" not in fm:
        raise ValueError("missing `path`")

    side = fm.get("side", "new")
    if side not in ALLOWED_SIDES:
        raise ValueError(f"`side` must be one of {ALLOWED_SIDES}, got {side!r}")

    has_line = "line" in fm
    has_range = "line_start" in fm or "line_end" in fm
    if has_line and has_range:
        raise ValueError("specify either `line` or `line_start`+`line_end`, not both")
    if not has_line and not has_range:
        raise ValueError("must specify `line` or `line_start`+`line_end`")

    line = line_start = line_end = None
    if has_line:
        line = _as_int(fm["line"], "line")
    else:
        if "line_start" not in fm or "line_end" not in fm:
            raise ValueError("range comment needs both `line_start` and `line_end`")
        line_start = _as_int(fm["line_start"], "line_start")
        line_end = _as_int(fm["line_end"], "line_end")
        if line_start > line_end:
            raise ValueError("`line_start` must be <= `line_end`")

    return Comment(
        filename=filename, path=fm["path"], body=body, side=side,
        line=line, line_start=line_start, line_end=line_end,
    )


def _as_int(v: str, name: str) -> int:
    try:
        return int(v)
    except ValueError:
        raise ValueError(f"`{name}` must be an integer, got {v!r}")


def _changed_paths(bundle: Path) -> set[str]:
    """Repo-relative paths with a diff in the bundle. Source of truth for
    which files the agent is allowed to comment on."""
    diffs = bundle / "diffs"
    if not diffs.is_dir():
        return set()
    paths: set[str] = set()
    for f in diffs.rglob("*.diff"):
        rel = str(f.relative_to(diffs))
        paths.add(rel.removesuffix(".diff"))
    return paths

"""Agent-runner orchestrator for `glair review`."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import click

from glair import bundle as bundle_mod
from glair import gitstate
from glair import result as result_mod
from glair import verify as verify_mod


INSTRUCTIONS_FILENAME = "INSTRUCTIONS.md"


def run(bundle_arg: str | None, agent_cmd: list[str]) -> int:
    """Run `verify`, write INSTRUCTIONS.md, spawn the agent, validate result/."""
    b = bundle_mod.resolve_bundle(bundle_arg)

    if verify_mod.run(str(b)) != 0:
        click.echo("verify failed — aborting review", err=True)
        return 1

    instructions = _instructions_text()
    (b / INSTRUCTIONS_FILENAME).write_text(instructions)

    repo_root = gitstate.repo_root()
    env = os.environ.copy()
    env["GLAIR_BUNDLE"] = str(b.resolve())

    click.echo(f"running agent: {' '.join(agent_cmd)}")
    try:
        proc = subprocess.Popen(
            agent_cmd,
            cwd=repo_root,
            env=env,
            stdin=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as e:
        click.echo(f"agent command not found: {e}", err=True)
        return 127

    try:
        proc.communicate(input=instructions)
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()
        return 130

    agent_rc = proc.returncode
    if agent_rc != 0:
        click.echo(f"agent exited with code {agent_rc}", err=True)
        return agent_rc

    try:
        result = result_mod.load(b)
    except result_mod.ResultError as e:
        click.echo("result/ is invalid:", err=True)
        for line in str(e).splitlines():
            click.echo(f"  {line}", err=True)
        return 1

    click.echo(
        f"review ok: verdict={result.verdict}, "
        f"{len(result.comments)} comment(s), summary at {b}/result/summary.md"
    )
    return 0


def _instructions_text() -> str:
    return _INSTRUCTIONS.lstrip()


_INSTRUCTIONS = """
You are reviewing a GitLab merge request. Everything you need is in the
directory at $GLAIR_BUNDLE. The repo is checked out at the MR's head
commit — read source directly from the working tree (the current
working directory), not from the bundle.

## Input

Start here:

- `$GLAIR_BUNDLE/mr.md`        — MR title, description, branches, links
- `$GLAIR_BUNDLE/CHANGES.md`   — index of changed files with +/- counts
- `$GLAIR_BUNDLE/issues/`      — linked issues (if any)
- `$GLAIR_BUNDLE/diffs/`       — per-file unified diffs (mirrors repo paths)

## Output

Write your review into `$GLAIR_BUNDLE/result/` using this layout:

    result/
      summary.md          # top-level MR note body (markdown)
      verdict             # single word: comment | approve | request_changes
      comments/
        001-<slug>.md
        002-<slug>.md
        ...

`summary.md` is posted as a general MR note. Each `comments/*.md` is
posted as a discussion on a specific line of the diff.

### Comment file format

YAML frontmatter followed by a markdown body.

Single-line comment:

    ---
    path: src/foo.py
    line: 42
    side: new
    ---
    Body markdown here. Can contain code fences, lists, etc.

Range comment (one thread covering multiple lines):

    ---
    path: src/foo.py
    line_start: 40
    line_end: 45
    side: new
    ---
    Body markdown.

### Rules

- `path` must be repo-relative and must appear in `CHANGES.md`.
- `side: new` — line number refers to the head (post-MR) version, for
  added or context lines.
- `side: old` — line number refers to the base version, for removed lines.
- Use `line` for single-line comments; use `line_start` + `line_end` for
  ranges. Not both.
- Use numbered filenames (`001-`, `002-`, …) so the order is stable.
- Anything you write outside `result/` is ignored.
- If `result/` exists from a previous run, overwrite or remove stale
  entries so what remains reflects this review.
"""

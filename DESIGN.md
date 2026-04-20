# glair — design

A CLI for running coding-agent code reviews on GitLab merge requests.

The CLI owns all GitLab API interaction (auth, fetching MR/issue/diff data,
posting comments back). The agent only reads a self-contained review bundle
from disk and writes its output to disk as files. This keeps the agent
agent-agnostic: any tool that can read files, edit files, and execute shell
commands can play the role.

The CLI runs inside the target repo, which must be checked out to the MR's
head commit. The agent reviews source from the working tree directly; the
bundle carries only the context that git does not (MR description, linked
issues, per-file diffs, SHAs, etc.).

## Pipeline

```
glair fetch <mr>           →  writes bundle to glair/<iid>/
glair verify [bundle]      →  pre-flight checks (repo state vs bundle)
glair review [bundle] -- <agent-cmd>
                           →  runs agent, validates result/
glair post   [bundle]      →  posts result/ back to the MR
```

Each step is independent and inspectable. You can hand-edit the bundle
between `fetch` and `review`, and hand-edit `result/` between `review`
and `post`.

## Commands

### `glair fetch <mr-ref> [--out DIR]`

Fetches MR data from GitLab and writes a bundle. Does **not** touch the
working tree.

`<mr-ref>` accepts:

- a full URL: `https://gitlab.example.com/group/proj/-/merge_requests/42`
- `<project-path>!<iid>`: `group/proj!42`
- bare `!<iid>`: `!42` — project inferred from `git remote get-url origin`

Default output path is `glair/<iid>/`.

Output: prints the bundle path and a one-line summary.

```
$ glair fetch !42
glair/42/  —  "Add retry logic to upload client"  (+128 −37, 6 files)
```

### `glair verify [BUNDLE]`

Local-only pre-flight. No GitLab calls.

Checks, in order:

1. CWD is a git repo.
2. `git rev-parse HEAD` equals `meta.json:head_sha`.
3. Working tree is clean (no staged, unstaged, or untracked files).
4. Current branch matches `meta.json:source_branch` (warning, not failure,
   if only the SHA matches — detached HEAD is fine).

Used standalone for debugging and run implicitly by `review` and `post`.

```
$ glair verify
ok   git repo              /home/me/proj
ok   head sha              a1b2c3d (matches meta.json)
fail working tree clean    modified: src/foo.py
```

Exit non-zero on any `fail`.

### `glair review [BUNDLE] -- <agent-cmd …>`

Runs the agent against the bundle.

1. Runs `verify`; aborts on failure.
2. Writes `INSTRUCTIONS.md` into the bundle — the agent's brief and the
   exact `result/` layout it must produce.
3. Spawns `<agent-cmd>` with:
   - `cwd` = repo root
   - env `GLAIR_BUNDLE` = absolute bundle path
   - `INSTRUCTIONS.md` piped to stdin (so `claude -p`, `aider`, etc.
     can consume it as the prompt directly)
4. On exit, validates `result/`:
   - `summary.md` exists and is non-empty
   - `verdict` is one of the allowed values
   - every `comments/*.md` has valid frontmatter and a body
   - frontmatter paths appear in the bundle's diffs
5. Exits non-zero on malformed output.

Example:

```
$ glair review -- claude -p
$ glair review -- aider --message-file -
$ glair review -- my-agent --stream
```

### `glair post [BUNDLE] [--dry-run] [--mode MODE] [--apply-verdict] [--lenient]`

Posts the result back to the MR.

1. Runs `verify` again — stale SHAs make line positions invalid.
2. For each comment, resolves `(path, line, side)` against the per-file
   diffs + SHAs in `meta.json` to produce a GitLab `position` object.
3. Posts the summary as a general MR note and each comment as a
   discussion (or draft note batch, depending on `--mode`).

Flags:

- `--dry-run` — print the exact API payloads; make no calls.
- `--mode discussions` (default) — one discussion thread per comment,
  posted immediately.
- `--mode draft` — create draft notes, publish as one atomic review.
- `--lenient` — comments that don't resolve to a diff line are demoted
  to bullets appended to `summary.md` (default is to error out).
- `--apply-verdict` — if `verdict` is `approve`, call the approve
  endpoint. Without this flag, verdict is advisory only.

## Bundle format

Written by `glair fetch`, read by the agent and later commands.

```
glair/<iid>/
  meta.json              # CLI-only metadata (SHAs, ids, urls)
  mr.md                  # human-readable MR description
  issues/<iid>.md        # one file per linked issue
  CHANGES.md             # index of changed files
  diffs/<path>.diff      # per-file unified diff, mirrors repo paths
  INSTRUCTIONS.md        # written by `glair review`
  result/                # written by the agent
```

### `meta.json`

The CLI's source of truth for anything the agent shouldn't touch.

```json
{
  "project_id": 123,
  "project_path": "group/proj",
  "mr_iid": 42,
  "mr_id": 98765,
  "web_url": "https://gitlab.example.com/group/proj/-/merge_requests/42",
  "title": "Add retry logic to upload client",
  "author": "alice",
  "source_branch": "alice/upload-retry",
  "target_branch": "main",
  "base_sha":  "e4e4e4e4…",
  "start_sha": "f1f1f1f1…",
  "head_sha":  "a1b2c3d4…",
  "created_at": "2026-04-18T10:12:00Z",
  "labels": ["backend", "reliability"]
}
```

`base_sha`, `start_sha`, `head_sha` are carried verbatim from GitLab's
MR payload; they are needed to build `position` objects when posting.

### `mr.md`

Plain markdown. Title as H1, then description, author, labels, linked-issue
references. Generated from the MR payload; no frontmatter.

```markdown
# Add retry logic to upload client

**Author:** @alice
**Branch:** `alice/upload-retry` → `main`
**Labels:** backend, reliability
**Closes:** #118, #124

---

Adds exponential-backoff retry to `UploadClient.put`. Caps at 5
attempts; jittered sleeps. See issue #118 for background.
```

### `issues/<iid>.md`

One file per linked issue. Same shape as `mr.md` — title as H1, then
description. Linked issues are discovered via `Closes #N` / `Related to #N`
markers in the MR description plus GitLab's own linked-issues endpoint.

### `CHANGES.md`

Human-readable index. The agent skims this first.

```markdown
| path                 | status    | +    | -    |
|----------------------|-----------|------|------|
| src/upload.py        | modified  | +48  | -12  |
| src/retry.py         | added     | +64  | 0    |
| src/old_retry.py     | deleted   | 0    | -27  |
| tests/test_upload.py | modified  | +16  | -2   |
| docs/logo.png        | binary    |      |      |
```

Rename rows include the old path in a footnote:

```markdown
| src/new/util.py      | renamed   | +3   | -1   |

[^rename-new-util]: renamed from `src/old/util.py`
```

Binary and truncated files are listed here but have no entry under `diffs/`.

### `diffs/<path>.diff`

Standard unified diff, one per changed file, mirroring repo paths
(`diffs/src/upload.py.diff`). No wrapping, no frontmatter — just the diff
as GitLab returns it.

Added files: trivial "new file" diff is still written.
Deleted files: the diff is still written; no source exists in the working
tree, which is expected.
Renamed files: written at the new path; the diff header carries the old
path.

### `INSTRUCTIONS.md`

Written by `glair review`. Tells the agent:

1. The repo is checked out at the MR's head commit; read source directly
   from disk.
2. Start from `$GLAIR_BUNDLE/CHANGES.md` and `mr.md`; consult `issues/`
   and `diffs/` as needed.
3. Write the review into `$GLAIR_BUNDLE/result/` per the layout below.
4. Address each comment by line number in the head (working-tree)
   version of the file.

## Result format

Written by the agent, consumed by `glair post`.

```
result/
  summary.md           # top-level MR note body (markdown)
  verdict              # single word: comment | approve | request_changes
  comments/
    001-src-upload-py-L42.md
    002-src-upload-py-L90-95.md
    003-src-retry-py-L10.md
```

### `summary.md`

Free-form markdown. Posted as a general MR note.

### `verdict`

A single word on one line:

- `comment` — informational review.
- `approve` — agent recommends approval. Only calls the approve endpoint
  if `glair post --apply-verdict` is passed.
- `request_changes` — GitLab has no native "request changes" state;
  surfaced in the summary as `**Verdict: request_changes**` and by
  leaving threads unresolved.

### `comments/NNN-<slug>.md`

One markdown file per comment. Filename is `<seq>-<path-slug>-L<line>.md`
for stable ordering and at-a-glance context. The canonical path is in the
frontmatter; the filename is advisory.

Single-line comment:

```markdown
---
path: src/upload.py
line: 42
side: new
---
`count` is user-controlled here — this can overflow when the request
body is larger than `MAX_BUF`. Bound it at the handler:

    if count > MAX_BUF:
        raise BadRequest(...)
```

Multi-line range:

```markdown
---
path: src/upload.py
line_start: 90
line_end: 95
side: new
---
This block duplicates `normalize_user` from `src/utils.py:88`. Consider
calling the existing helper instead of re-implementing.
```

Comment on a removed line:

```markdown
---
path: src/old_retry.py
line: 12
side: old
---
Worth keeping this backoff cap — the replacement in `src/retry.py` loses it.
```

Frontmatter schema:

| key          | type            | required         | notes                                   |
|--------------|-----------------|------------------|-----------------------------------------|
| `path`       | string          | yes              | repo-relative path                      |
| `side`       | `new` \| `old`  | yes              | defaults to `new` if omitted            |
| `line`       | int             | single-line only | line number in the head/base file       |
| `line_start` | int             | range only       | inclusive                               |
| `line_end`   | int             | range only       | inclusive                               |

Validation:

- Exactly one of `line` or (`line_start` + `line_end`) must be set.
- For `side: new`, the line must appear as an added or context line in
  `diffs/<path>.diff`.
- For `side: old`, the line must appear as a removed or context line.
- Paths must exist in `CHANGES.md` (no commenting on unchanged files
  in v1).

Out-of-diff comments are rejected by `glair post` unless `--lenient` is
set, in which case they are appended to the summary as bullets.

## End-to-end example

```
$ cd ~/projects/proj
$ git fetch origin
$ git checkout a1b2c3d4            # MR 42 head

$ glair fetch !42
glair/42/  —  "Add retry logic to upload client"  (+128 −37, 6 files)

$ ls glair/42
CHANGES.md  diffs/  issues/  meta.json  mr.md

$ $EDITOR glair/42/mr.md          # optional: trim noise, add scoping notes

$ glair verify
ok   git repo              /home/me/projects/proj
ok   head sha              a1b2c3d (matches meta.json)
ok   working tree clean
ok   branch                alice/upload-retry

$ glair review -- claude -p
…agent runs, writes glair/42/result/…

$ ls glair/42/result/comments
001-src-upload-py-L42.md
002-src-upload-py-L90-95.md
003-src-retry-py-L10.md

$ $EDITOR glair/42/result/comments/002-*.md   # optional: tweak wording

$ glair post --dry-run
would post 1 general note + 3 discussions on !42
  discussion  src/upload.py:42         (new)   "count is user-controlled…"
  discussion  src/upload.py:90-95      (new)   "This block duplicates…"
  discussion  src/retry.py:10          (new)   "Consider using a monotonic clock…"

$ glair post
posted 1 note + 3 discussions on !42
  https://gitlab.example.com/group/proj/-/merge_requests/42#note_556789
```

## Open questions

- **Auto-checkout.** Whether `glair fetch --checkout` (or a sibling
  `glair checkout`) should do the git fetch + checkout for the user,
  gated on a clean working tree and a safe-to-leave current branch.
  For v1: verify-only, human checks out.
- **Existing discussions.** Whether to include prior MR discussions in
  the bundle so the agent doesn't repeat feedback. Would add
  `discussions.md`.
- **Comments on unchanged files.** Out of scope for v1; would require
  including more than diffs in the bundle.
- **Auth.** Token discovery — env var, `glab` config file, or both.
- **One-shot `run`.** A `glair run <mr> -- <agent>` that chains
  fetch → verify → review → post. Deferred until the step commands feel
  right.

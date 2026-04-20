"""Thin ``python-gitlab`` wrapper. Exposes one call: fetch the MR and the
data needed to build a review bundle."""
from __future__ import annotations

import gitlab

from glair.config import GitLabAuth
from glair.fetch import MRPayload


def fetch_mr_payload(auth: GitLabAuth, project_path: str, iid: int) -> MRPayload:
    gl = gitlab.Gitlab(auth.url, private_token=auth.token)
    project = gl.projects.get(project_path)
    mr = project.mergerequests.get(iid)

    # `changes()` returns the MR dict including a `changes` list of per-file
    # entries with `diff`, `new_path`, `old_path`, `new_file`, etc.
    changes_resp = mr.changes()
    changes = changes_resp.get("changes") or []

    # `related_issues()` returns issues linked via `Closes #N` / related refs.
    related_raw = list(mr.related_issues())
    linked = [_issue_attrs(i) for i in related_raw]

    return MRPayload(
        project=dict(project.attributes),
        mr=dict(mr.attributes),
        changes=changes,
        linked_issues=linked,
    )


def _issue_attrs(obj) -> dict:
    # ``related_issues`` sometimes yields ProjectIssue objects (with
    # .attributes) and sometimes plain dicts depending on version.
    attrs = getattr(obj, "attributes", None)
    return dict(attrs) if attrs is not None else dict(obj)

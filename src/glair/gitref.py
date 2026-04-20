from __future__ import annotations

import re
from dataclasses import dataclass

from glair import gitstate


@dataclass(frozen=True)
class MRRef:
    url: str | None   # GitLab base URL, e.g. "https://gitlab.example.com"
    project: str      # path_with_namespace, e.g. "group/proj"
    iid: int


class RefError(ValueError):
    pass


_MR_URL_RE = re.compile(
    r"^(?P<base>https?://[^/]+)/(?P<project>.+?)/-/merge_requests/(?P<iid>\d+)/?$"
)
_PROJECT_BANG_RE = re.compile(r"^(?P<project>[^!]+)!(?P<iid>\d+)$")
_BANG_RE = re.compile(r"^!(?P<iid>\d+)$")

_SSH_REMOTE_RE = re.compile(r"^(?:ssh://)?git@(?P<host>[^:/]+)[:/](?P<path>.+?)(?:\.git)?$")
_HTTP_REMOTE_RE = re.compile(r"^(?P<scheme>https?)://(?:[^@/]+@)?(?P<host>[^/]+)/(?P<path>.+?)(?:\.git)?$")


def parse(ref: str, remote_url: str | None = None) -> MRRef:
    """Resolve an MR reference. When `ref` is `!<iid>`, `remote_url` is
    consulted to infer URL + project; otherwise it's ignored."""
    m = _MR_URL_RE.match(ref)
    if m:
        return MRRef(url=m["base"], project=m["project"], iid=int(m["iid"]))

    m = _PROJECT_BANG_RE.match(ref)
    if m:
        return MRRef(url=None, project=m["project"], iid=int(m["iid"]))

    m = _BANG_RE.match(ref)
    if m:
        if remote_url is None:
            raise RefError(
                f"`{ref}` requires a git remote to infer project; pass a full URL "
                f"or `<project>!<iid>` form instead"
            )
        base, project = parse_remote(remote_url)
        return MRRef(url=base, project=project, iid=int(m["iid"]))

    raise RefError(
        f"could not parse MR ref: {ref!r} (expected a URL, `<project>!<iid>`, or `!<iid>`)"
    )


def parse_remote(remote_url: str) -> tuple[str, str]:
    """Extract (base_url, project_path) from a git remote URL.

    Handles SSH (`git@host:path.git`, `ssh://git@host/path.git`) and
    HTTP(S) forms. SSH remotes are assumed to map to HTTPS for the API.
    """
    m = _HTTP_REMOTE_RE.match(remote_url)
    if m:
        return f"{m['scheme']}://{m['host']}", m["path"]
    m = _SSH_REMOTE_RE.match(remote_url)
    if m:
        return f"https://{m['host']}", m["path"]
    raise RefError(f"unrecognised remote URL: {remote_url!r}")


def resolve(ref: str) -> MRRef:
    """`parse` with the git `origin` remote as the fallback inference source."""
    return parse(ref, remote_url=gitstate.remote_url())

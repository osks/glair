from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class GitLabAuth:
    url: str
    token: str


class AuthError(RuntimeError):
    pass


def load_auth(url_override: str | None = None) -> GitLabAuth:
    """Resolve GitLab URL + token from env, allowing the URL to be overridden
    (e.g. by an MR URL or git remote)."""
    url = url_override or os.environ.get("GLAIR_GITLAB_URL")
    if not url:
        raise AuthError(
            "GitLab URL not known — pass a full MR URL, set GLAIR_GITLAB_URL, "
            "or run inside a repo with a GitLab remote"
        )
    token = os.environ.get("GLAIR_GITLAB_TOKEN")
    if not token:
        raise AuthError("GLAIR_GITLAB_TOKEN is not set")
    return GitLabAuth(url=url.rstrip("/"), token=token)

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

BUNDLE_ROOT = "glair"
META_FILENAME = "meta.json"


def resolve_bundle(explicit: str | None) -> Path:
    """Return the bundle directory, either the explicit arg or the unique
    ``glair/*`` subdir in the current directory."""
    if explicit is not None:
        p = Path(explicit)
        if not (p / META_FILENAME).is_file():
            raise click.ClickException(f"not a bundle: {p} (no {META_FILENAME})")
        return p

    root = Path(BUNDLE_ROOT)
    if not root.is_dir():
        raise click.ClickException(
            f"no {BUNDLE_ROOT}/ directory here — run `glair fetch <mr>` first "
            f"or pass a bundle path"
        )
    subs = [d for d in root.iterdir() if d.is_dir() and (d / META_FILENAME).is_file()]
    if not subs:
        raise click.ClickException(
            f"no bundles under {BUNDLE_ROOT}/ — run `glair fetch <mr>` first"
        )
    if len(subs) > 1:
        names = ", ".join(sorted(d.name for d in subs))
        raise click.ClickException(
            f"multiple bundles under {BUNDLE_ROOT}/ ({names}); pass one explicitly"
        )
    return subs[0]


def load_meta(bundle: Path) -> dict[str, Any]:
    return json.loads((bundle / META_FILENAME).read_text())

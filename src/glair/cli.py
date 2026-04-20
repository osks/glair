import click


@click.group()
@click.version_option()
def cli() -> None:
    """glair — run coding-agent code reviews on GitLab merge requests."""


@cli.command()
@click.argument("mr_ref")
@click.option("--out", "out_dir", type=click.Path(), default=None,
              help="Bundle output directory (default: glair/<iid>/).")
def fetch(mr_ref: str, out_dir: str | None) -> None:
    """Fetch MR data from GitLab and write a review bundle."""
    raise click.ClickException("fetch: not implemented yet")


@cli.command()
@click.argument("bundle", type=click.Path(exists=True, file_okay=False),
                required=False)
def verify(bundle: str | None) -> None:
    """Check the working tree matches the bundle's head SHA and is clean."""
    raise click.ClickException("verify: not implemented yet")


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("bundle", type=click.Path(exists=True, file_okay=False),
                required=False)
@click.argument("agent_cmd", nargs=-1, required=True)
def review(bundle: str | None, agent_cmd: tuple[str, ...]) -> None:
    """Run an agent against a bundle. Everything after `--` is the agent command."""
    raise click.ClickException("review: not implemented yet")


@cli.command()
@click.argument("bundle", type=click.Path(exists=True, file_okay=False),
                required=False)
@click.option("--dry-run", is_flag=True, help="Print payloads without calling GitLab.")
@click.option("--mode", type=click.Choice(["discussions", "draft"]),
              default="discussions")
@click.option("--lenient", is_flag=True,
              help="Demote out-of-diff comments to summary bullets instead of erroring.")
@click.option("--apply-verdict", is_flag=True,
              help="Call the approve endpoint when verdict is 'approve'.")
def post(bundle: str | None, dry_run: bool, mode: str,
         lenient: bool, apply_verdict: bool) -> None:
    """Post the agent's result back to the MR."""
    raise click.ClickException("post: not implemented yet")


if __name__ == "__main__":
    cli()

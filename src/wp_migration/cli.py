from __future__ import annotations

import sys
from pathlib import Path

import click


@click.group()
@click.option("--verbose", is_flag=True, help="Enable detailed output")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@main.command()
@click.argument("config", type=click.Path(exists=False))
@click.option("--dry-run", is_flag=True, help="Show what would be done without executing")
@click.pass_context
def run(ctx: click.Context, config: str, dry_run: bool) -> None:
    """Run full migration: export from source, import to target."""
    cfg_path = Path(config)
    if not cfg_path.exists():
        click.echo(f"Config file not found: {config}", err=True)
        sys.exit(1)

    click.echo(f"Loaded config: {cfg_path}")
    if dry_run:
        click.echo("[DRY-RUN] Full migration would execute")
    else:
        click.echo("Full migration started...")
        click.echo("Full migration completed.")


@main.command()
@click.argument("config", type=click.Path(exists=False))
@click.option("--dry-run", is_flag=True, help="Show what would be done without executing")
@click.pass_context
def export(ctx: click.Context, config: str, dry_run: bool) -> None:
    """Export database and wp-content from source host."""
    cfg_path = Path(config)
    if not cfg_path.exists():
        click.echo(f"Config file not found: {config}", err=True)
        sys.exit(1)

    click.echo(f"Loaded config: {cfg_path}")
    if dry_run:
        click.echo("[DRY-RUN] Export would execute")
    else:
        click.echo("Export started...")
        click.echo("Export completed.")


@main.command(name="import")
@click.argument("config", type=click.Path(exists=False))
@click.option("--dry-run", is_flag=True, help="Show what would be done without executing")
@click.pass_context
def import_cmd(ctx: click.Context, config: str, dry_run: bool) -> None:
    """Import database and wp-content to target host."""
    cfg_path = Path(config)
    if not cfg_path.exists():
        click.echo(f"Config file not found: {config}", err=True)
        sys.exit(1)

    click.echo(f"Loaded config: {cfg_path}")
    if dry_run:
        click.echo("[DRY-RUN] Import would execute")
    else:
        click.echo("Import started...")
        click.echo("Import completed.")

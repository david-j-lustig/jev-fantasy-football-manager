"""Command-line interface: ``jev-ff lineup|waivers|trade``."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import typer
from rich.console import Console
from rich.table import Table

from jev_ff.config import load_settings
from jev_ff.errors import JevFFError
from jev_ff.manager import FantasyManager
from jev_ff.models import LineupReport, TradeReport, WaiverReport

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Recommend Sleeper lineups, waivers, and trades.")
console = Console()
T = TypeVar("T")


def _build_manager(
    league_id: str | None,
    roster_id: int | None,
    username: str | None,
    config: Path | None,
    model: str | None,
) -> FantasyManager:
    settings = load_settings(
        league_id=league_id,
        roster_id=roster_id,
        username=username,
        model=model,
        config_path=config,
    )
    manager = FantasyManager.from_settings(settings)
    if not manager.jev_enabled:
        console.print(
            "[yellow]Jev disabled[/yellow] — set TYPESAFE_API_KEY for news/injury overlays. "
            "Projection-only recommendations still run."
        )
    return manager


def _run(action: Callable[[], T]) -> T:
    try:
        return action()
    except JevFFError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc


def _run_with_manager(
    league_id: str | None,
    roster_id: int | None,
    username: str | None,
    config: Path | None,
    model: str | None,
    action: Callable[[FantasyManager], T],
) -> T:
    manager = _run(lambda: _build_manager(league_id, roster_id, username, config, model))
    try:
        return _run(lambda: action(manager))
    finally:
        manager.close()


@app.callback()
def _root() -> None:
    """Recommend lineups, waivers, and trades for a Sleeper league."""


@app.command()
def lineup(
    league_id: str | None = typer.Option(None, "--league-id", help="Sleeper league id"),
    roster_id: int | None = typer.Option(None, "--roster-id", help="Your Sleeper roster id"),
    username: str | None = typer.Option(None, "--username", help="Sleeper username (if no roster id)"),
    week: int | None = typer.Option(None, "--week", help="NFL week (default: current)"),
    config: Path | None = typer.Option(None, "--config", help="Path to jev-ff.toml"),
    model: str | None = typer.Option(None, "--model", help="TypeSafe model id (default jev-latest)"),
) -> None:
    """Recommend a starting lineup for the week."""
    report = _run_with_manager(
        league_id, roster_id, username, config, model, lambda manager: manager.recommend_lineup(week)
    )
    _print_lineup(report)


@app.command()
def waivers(
    league_id: str | None = typer.Option(None, "--league-id"),
    roster_id: int | None = typer.Option(None, "--roster-id"),
    username: str | None = typer.Option(None, "--username"),
    week: int | None = typer.Option(None, "--week"),
    limit: int = typer.Option(10, "--limit", min=1, max=50),
    config: Path | None = typer.Option(None, "--config"),
    model: str | None = typer.Option(None, "--model"),
) -> None:
    """Rank waiver-wire adds for your roster."""
    report = _run_with_manager(
        league_id,
        roster_id,
        username,
        config,
        model,
        lambda manager: manager.find_waivers(week, limit=limit),
    )
    _print_waivers(report)


@app.command()
def trade(
    give: list[str] = typer.Option(..., "--give", help="Player to send (repeatable)"),
    get: list[str] = typer.Option(..., "--get", help="Player to receive (repeatable)"),
    league_id: str | None = typer.Option(None, "--league-id"),
    roster_id: int | None = typer.Option(None, "--roster-id"),
    username: str | None = typer.Option(None, "--username"),
    week: int | None = typer.Option(None, "--week"),
    opponent_roster_id: int | None = typer.Option(None, "--opponent-roster-id"),
    config: Path | None = typer.Option(None, "--config"),
    model: str | None = typer.Option(None, "--model"),
) -> None:
    """Evaluate a proposed give/get trade."""
    report = _run_with_manager(
        league_id,
        roster_id,
        username,
        config,
        model,
        lambda manager: manager.evaluate_trade(give, get, week=week, opponent_roster_id=opponent_roster_id),
    )
    _print_trade(report)


def _print_lineup(report: LineupReport) -> None:
    jev_tag = "  [cyan]Jev on[/cyan]" if report.jev_enabled else ""
    console.print(
        f"[bold]Week {report.week} lineup[/bold]  projected {report.projected_total:.1f}  "
        f"current {report.current_total:.1f}  delta {report.delta:+.1f}{jev_tag}"
    )
    table = Table(show_header=True, header_style="bold")
    table.add_column("Slot", style="cyan", width=12)
    table.add_column("Player")
    table.add_column("Pts", justify="right")
    table.add_column("Note")
    for row in report.starters:
        name = "—" if row.player is None else row.player.full_name
        note = row.reason
        if row.needs_review:
            note = (note + " · review").strip(" ·")
        table.add_row(row.slot, name, f"{row.projected_points:.1f}", note)
    console.print(table)
    if report.bench:
        bench = Table(title="Bench", show_header=True)
        bench.add_column("Player")
        bench.add_column("Pts", justify="right")
        bench.add_column("Note")
        for row in report.bench:
            name = row.player.full_name if row.player else "—"
            bench.add_row(name, f"{row.projected_points:.1f}", row.reason)
        console.print(bench)
    for note in report.notes:
        console.print(f"• {note}")


def _print_waivers(report: WaiverReport) -> None:
    drop = report.suggested_drop.full_name if report.suggested_drop else "—"
    console.print(f"[bold]Week {report.week} waivers[/bold]  suggested drop: {drop}")
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Player")
    table.add_column("Pos")
    table.add_column("Week", justify="right")
    table.add_column("VOR", justify="right")
    table.add_column("Trend", justify="right")
    table.add_column("FAAB")
    for index, row in enumerate(report.adds, start=1):
        table.add_row(
            str(index),
            row.player.full_name,
            "/".join(row.player.positions),
            f"{row.week_points:.1f}",
            f"{row.vor_week:+.1f}",
            str(row.trending_adds),
            row.faab_label,
        )
    console.print(table)
    for note in report.notes:
        console.print(f"• {note}")


def _print_trade(report: TradeReport) -> None:
    give_names = ", ".join(player.full_name for player in report.give.players) or "—"
    get_names = ", ".join(player.full_name for player in report.get.players) or "—"
    console.print(f"[bold]Trade[/bold]  give {give_names}  →  get {get_names}")
    console.print(f"ROS delta {report.ros_delta:+.1f}   week delta {report.week_delta:+.1f}   {report.fairness_label}")
    console.print(report.recommendation)
    if report.should_accept is not None:
        console.print(f"Should you accept? {report.should_accept:.2f}")
    if report.opponent_would_accept is not None:
        console.print(f"Would they accept? {report.opponent_would_accept:.2f}")
    for note in report.notes:
        console.print(f"• {note}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()

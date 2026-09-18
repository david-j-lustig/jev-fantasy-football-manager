"""Load a Sleeper league from the environment and print this week's lineup.

export JEV_FF_LEAGUE_ID=...
export JEV_FF_ROSTER_ID=1
export TYPESAFE_API_KEY=...   # optional; without it, projection-only mode

python examples/quickstart.py
"""

from jev_ff import FantasyManager


def main() -> None:
    manager = FantasyManager.from_env()
    report = manager.recommend_lineup()
    print(f"Week {report.week} projected {report.projected_total:.1f} (current {report.current_total:.1f})")
    for row in report.starters:
        name = "—" if row.player is None else row.player.full_name
        print(f"  {row.slot:12} {name:25} {row.projected_points:5.1f}  {row.reason}")
    if report.notes:
        print("Notes:")
        for note in report.notes:
            print(f"  - {note}")


if __name__ == "__main__":
    main()

# jev-fantasy-football-manager

Recommend Sleeper fantasy football lineups, waiver adds, and trades.

Scores your league with Sleeper’s own settings, then optionally asks [TypeSafe Jev](https://docs.typesafe.ai/api) about injuries, close start/sit calls, FAAB, and trade fairness. Recommend-only: it never sets a lineup or submits a claim.

[![CI](https://github.com/david-j-lustig/jev-fantasy-football-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/david-j-lustig/jev-fantasy-football-manager/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## Installation

```bash
pip install jev-fantasy-football-manager
```

Python 3.10+. From a clone: `pip install -e ".[dev]"`

## Quickstart

```python
from jev_ff import FantasyManager

with FantasyManager.from_env(league_id="123...", roster_id=1) as manager:
    report = manager.recommend_lineup()
    adds = manager.find_waivers(limit=10)
    verdict = manager.evaluate_trade(give=["CMC"], get=["Puka Nacua"])
```

```bash
jev-ff lineup  --league-id 123 --roster-id 1
jev-ff waivers --league-id 123 --roster-id 1
jev-ff trade   --league-id 123 --roster-id 1 --give CMC --get "Puka Nacua"
```

See [`examples/quickstart.py`](examples/quickstart.py). If `TYPESAFE_API_KEY` is unset, projection-only mode still runs.

## Configuration

```bash
export JEV_FF_LEAGUE_ID=your-sleeper-league-id
export JEV_FF_ROSTER_ID=1                 # or SLEEPER_USER=your_username
export TYPESAFE_API_KEY=...               # https://console.typesafe.ai/settings/keys
```

Or `jev-ff.toml` in the working directory ([example](examples/jev-ff.toml.example)):

```toml
league_id = "your-sleeper-league-id"
roster_id = 1
model = "jev-latest"
```

CLI flags override env, which overrides toml. Put `TYPESAFE_API_KEY` in the environment only — a key in toml is rejected. Sleeper’s official API needs no token.

The NFL player map is cached for 24 hours (`JEV_FF_CACHE_DIR` overrides the path). Don’t hammer `GET /v1/players/nfl`.

## Scoring

```text
sum(stat[k] * league.scoring_settings[k])
```

Sleeper’s pre-baked `pts_ppr` / `pts_std` fields are ignored, so half-PPR, TE premium, 6-point passing TDs, and IDP score correctly. Weekly and rest-of-season lines come from community projections on `api.sleeper.com`. You can supply your own `ProjectionsProvider` or `NewsProvider`.

Jev is optional. When a key is set, Python still owns lineup math; Jev only answers injury, start/sit, FAAB, and fairness questions.

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) · [Issues](https://github.com/david-j-lustig/jev-fantasy-football-manager/issues)

## License

[MIT](LICENSE)

## Disclaimer

Not affiliated with Sleeper or TypeSafe. Recommendations can be wrong; you still set the lineup in the Sleeper app. Sleeper’s API is free for non-commercial use — see [their docs](https://docs.sleeper.com/).

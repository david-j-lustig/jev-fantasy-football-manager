# jev-fantasy-football-manager

Recommend **Sleeper** fantasy football lineups, waiver adds, and trades. **Code calculates** (league scoring, roster slots, projections). **[TypeSafe Jev](https://docs.typesafe.ai/api) judges** the things projections miss: injury news, close start/sit calls, FAAB aggressiveness, and trade fairness.

v1 is **recommend-only**. It does not set your lineup or submit claims on Sleeper.

## Install

```bash
pip install jev-fantasy-football-manager
```

From a clone:

```bash
pip install -e .
```

Python 3.10+.

## Configure

```bash
export JEV_FF_LEAGUE_ID=your-sleeper-league-id
export JEV_FF_ROSTER_ID=1          # or SLEEPER_USER=your_username
export TYPESAFE_API_KEY=...        # from https://console.typesafe.ai/settings/keys
```

Optional `jev-ff.toml` in the working directory (see [`examples/jev-ff.toml.example`](examples/jev-ff.toml.example)):

```toml
league_id = "your-sleeper-league-id"
roster_id = 1
model = "jev-latest"
```

Do not commit API keys. Sleeper's official API is read-only and needs no token.

## Python

```python
from jev_ff import FantasyManager

manager = FantasyManager.from_env(league_id="123...", roster_id=1)

report = manager.recommend_lineup()          # current NFL week
adds = manager.find_waivers(limit=10)
verdict = manager.evaluate_trade(give=["CMC"], get=["Puka Nacua"])
```

Without `TYPESAFE_API_KEY`, lineup / waiver / trade still run on league-scored projections. Jev overlays are skipped.

## CLI

```bash
jev-ff lineup  --league-id 123 --roster-id 1
jev-ff waivers --league-id 123 --roster-id 1
jev-ff trade   --league-id 123 --roster-id 1 --give CMC --get "Puka Nacua"
```

## How scoring works

Points are always:

```text
sum(stat[k] * league.scoring_settings[k])
```

The package never uses Sleeper's generic `pts_ppr` / `pts_std` fields, so half-PPR, TE premium, 6-point passing TDs, and IDP leagues score correctly.

Weekly projections and season-long (ROS) lines come from Sleeper's community `api.sleeper.com` stats/projections endpoints. You can swap in your own `ProjectionsProvider` or `NewsProvider`.

The NFL player map is cached on disk for 24 hours (`JEV_FF_CACHE_DIR` overrides the location). Please do not hammer `GET /v1/players/nfl`.

## Architecture

```text
Sleeper league + projections  →  scoring engine  →  lineup / VOR / ROS math
                                      ↑
                         Jev (optional) injury, start/sit, FAAB, fairness
```

Jev is a System One model: you send compact JSON **state** and typed **questions** (`Noul`, `Choice`, `Score`) and get calibrated probabilities back. This library keeps control flow in Python and only asks Jev for judgments.

## Optional extras

```bash
pip install jev-fantasy-football-manager[ilp]
```

Installs PuLP for an ILP lineup solver. A backtracking solver is the default and is enough for typical roster sizes.

## Disclaimer

Not affiliated with Sleeper or TypeSafe. Recommendations can be wrong; you still set the lineup in the Sleeper app. Sleeper's API is free for non-commercial use — see [their docs](https://docs.sleeper.com/).

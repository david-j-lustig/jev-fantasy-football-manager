# Contributing

## Development

```bash
git clone https://github.com/david-j-lustig/jev-fantasy-football-manager.git
cd jev-fantasy-football-manager
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Checks

CI runs these on Python 3.10–3.13:

```bash
ruff check src tests examples
ruff format src tests examples
pytest
```

Keep PRs small. Add tests for scoring, lineup, waiver, or Jev changes. Mock HTTP with `httpx.MockTransport`; don’t hit live Sleeper in tests.

Open an issue first if the change is large or would write to Sleeper. In the PR, say why the change exists.

## Design

- Scoring, slots, byes, and rankings stay in Python.
- Jev questions should be narrow (`Noul` / `Choice` / `Score`) with compact state.
- Recommend only — no unofficial Sleeper writes (set lineup, claims, trades).
- API keys come from `TYPESAFE_API_KEY` only. Don’t put them in `jev-ff.toml`.

## Bugs and security

[Bug report](https://github.com/david-j-lustig/jev-fantasy-football-manager/issues/new?template=bug_report.yml) — include scoring format, the command, and `pip show jev-fantasy-football-manager`.

Security: [SECURITY.md](SECURITY.md).

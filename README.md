# ⚽ World Cup 2026 Tournament Simulator

Monte Carlo tournament simulator for the 2026 FIFA World Cup.

**Live demo:** (deploy on Streamlit Community Cloud)

## Features

- **Live results** from openfootball/worldcup.json
- **Polymarket odds** — match-level and tournament winner probabilities
- **Market-calibrated Elo** — inverts Polymarket tournament odds into Elo ratings via Bradley-Terry, preserving rank order and variance
- **Monte Carlo engine** — 10k+ full tournament simulations
- **Annex C** — all 495 third-place pairing combinations encoded
- **FIFA 2026 rules** — 7-step tiebreakers, third-place qualification, knockout bracket

## Pages

| Page | Description |
|------|-------------|
| **Standings & Results** | 12 group tables, match results, third-place ranking |
| **Knockout Bracket** | Live bracket projection with qualified teams |
| **Tournament Simulation** | Run Monte Carlo sims, win probabilities, team deep dives |
| **Odds Comparison** | Polymarket vs Elo vs simulated odds side-by-side |

## Quick Start

```bash
uv sync
uv run streamlit run src/worldcup_sim/streamlit_app.py --server.port 8501
```

Or with pip:

```bash
pip install -r requirements.txt
streamlit run src/worldcup_sim/streamlit_app.py
```

## Data Sources

| Source | Data |
|--------|------|
| [openfootball/worldcup.json](https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json) | Match fixtures + results |
| [Polymarket Gamma API](https://gamma-api.polymarket.com) | Match + tournament winner odds |
| eloratings.net | Pre-tournament Elo ratings (fallback) |

## Project Structure

```
src/worldcup_sim/
├── streamlit_app.py          # Entry point
├── data/
│   ├── models.py             # Pydantic models (Team, MatchResult, etc.)
│   ├── fetch.py              # Data fetchers (worldcup.json, Polymarket, Elo)
│   ├── calibrate.py          # Market-calibrated Elo from Polymarket odds
│   └── cache.py              # In-memory TTL cache
├── rules/
│   ├── group_stage.py        # Standings + 7-step tiebreakers
│   ├── third_place.py        # Third-place ranking
│   └── bracket.py            # Round-of-32 pairings + Annex C
├── sim/
│   ├── engine.py             # Monte Carlo tournament engine
│   ├── predictor.py          # Match outcome prediction
│   └── metrics.py            # Distribution aggregation
└── app/
    ├── state.py              # Session state
    ├── components/
    │   ├── bracket_viz.py    # SVG bracket renderer
    │   └── charts.py         # Win % bars, path distributions
    └── pages/
        ├── standings.py
        ├── bracket.py
        ├── simulation.py
        └── odds.py
data/
├── teams.json                # Team metadata (name, group, flag)
└── annex_c.json              # 495 × 8 third-place pairing matrix
```

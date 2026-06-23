# World Cup 2026 Simulator — Architecture & Plan

## 1. Scope

A Monte Carlo tournament simulator that:
- Pulls **live results** from openfootball/worldcup.json and/or web scrapes
- Pulls **live Elo ratings** for all 48 teams
- Pulls **live match odds** from Polymarket (Gamma API, no auth needed)
- Simulates the remainder of the tournament 10,000+ times
- Uses **Polymarket odds as default** for match predictions, **Elo as fallback** for unlisted matches
- Applies all **FIFA 2026 rules**: group tiebreakers (7-step chain), third-place ranking, 495 Annex C pairing combinations
- Exposes everything via **Streamlit** dashboard

---

## 2. Data Sources

| Source | Data | Access | Update |
|--------|------|--------|--------|
| openfootball/worldcup.json | Match fixtures + results with scores | `GET https://raw.githubusercontent.com/.../2026/worldcup.json` | ~daily (manual updates) |
| polymarket Gamma API | Match outcome probabilities | `GET https://gamma-api.polymarket.com/events?tag_id=1059&active=true` | real-time |
| eloratings.net | Team Elo ratings | Scrape/parse JS-loaded page | after each match |
| worldcupelo.com | Alternative Elo source | Web scrape | live |

**Elo → expected score formula:**
```
P(win) = 1 / (1 + 10^((elo_B - elo_A) / 400))
P(draw) = draw_factor (scaled by competition)
```

---

## 3. Project Structure (uv-managed)

```
worldcup-sim/
├── pyproject.toml              # uv + dependencies
├── ARCHITECTURE.md             # (this file)
├── src/
│   └── worldcup_sim/
│       ├── __init__.py
│       ├── config.py
│       │
│       ├── data/
│       │   ├── __init__.py
│       │   ├── models.py       # Pydantic models: Team, MatchResult, GroupStanding, BracketSlot
│       │   ├── fetch.py        # Data fetchers (worldcup.json, Polymarket, Elo)
│       │   └── cache.py        # Simple in-memory TTL cache
│       │
│       ├── rules/
│       │   ├── __init__.py
│       │   ├── group_stage.py   # Compute standings, apply 7-step tiebreakers
│       │   ├── third_place.py   # Rank 3rd-place teams, determine top 8
│       │   └── bracket.py       # Round-of-32 pairings (Annex C matrix), bracket traversal
│       │
│       ├── sim/
│       │   ├── __init__.py
│       │   ├── predictor.py     # Match outcome: Polymarket > Elo
│       │   ├── engine.py        # Monte Carlo engine (10k+ runs)
│       │   └── metrics.py       # Win %, SF%, QF%, etc. distributions
│       │
│       ├── app/
│       │   ├── __init__.py
│       │   ├── state.py         # Shared session state
│       │   ├── pages/
│       │   │   ├── standings.py     # Group standings + results
│       │   │   ├── bracket.py       # Live/current bracket
│       │   │   ├── simulation.py    # Run & explore simulations
│       │   │   └── odds.py          # Polymarket vs Elo comparison
│       │   └── components/
│       │       ├── bracket_viz.py   # SVG bracket renderer
│       │       └── charts.py        # Team win % bars, path distributions
│       │
│       └── streamlit_app.py     # Main entry point
│
└── data/                        # Scraped/cached data
    ├── teams.json               # Pre-built team metadata (name, flag, group)
    └── annex_c.json             # Encoded 495 × 8 pairing matrix
```

---

## 4. Data Models (core)

```python
class Team:
    name: str
    elo_rating: float
    group: str  # A-L
    flag_emoji: str

class MatchResult:
    team1: str
    team2: str
    score_ft: tuple[int, int] | None  # None = not yet played
    score_ht: tuple[int, int] | None
    group: str | None
    round: str  # "Matchday 1" | "Round of 32" | ...
    date: str
    polymarket_prob: float | None  # P(team1 wins in regulation)

class GroupStanding:
    team: str
    played: int
    wins: int
    draws: int
    losses: int
    gf: int
    ga: int
    gd: int
    points: int
    conduct_score: int  # Fair play tiebreaker
    fifa_rank: int      # Last-resort tiebreaker
    position: int       # Computed: 1st, 2nd, 3rd, 4th

class BracketSlot:
    round: str
    match_id: int
    team1: str | None
    team2: str | None
    winner: str | None
    source_match_1: int | None  # which match feeds into this
    source_match_2: int | None
```

---

## 5. Tournament Rules Implementation

### Group Stage
- **12 groups** (A–L), 4 teams each
- **Points**: Win=3, Draw=1, Loss=0
- **Tiebreakers** (7-step chain):
  1. Goal difference
  2. Goals scored
  3. Head-to-head points (among tied teams)
  4. Head-to-head goal difference
  5. Head-to-head goals scored
  6. Conduct score (fewer cards = higher)
  7. FIFA/Coca-Cola World Ranking

### Third-Place Qualification
- All 12 third-placed teams ranked on same 7-step chain
- Top 8 advance to Round of 32
- **Annex C matrix** — 495 possible combinations mapping which groups' third-placers go to which group winners

### Round of 32 — Fixed Match Structure (from FIFA regulations):

| Match | Pairing |
|-------|---------|
| 73 | RU A vs RU B |
| 74 | W E vs 3rd from {A,B,C,D,F} |
| 75 | W F vs RU C |
| 76 | W C vs RU F |
| 77 | W I vs 3rd from {C,D,F,G,H} |
| 78 | RU E vs RU I |
| 79 | W A vs 3rd from {C,E,F,H,I} |
| 80 | W L vs 3rd from {E,H,I,J,K} |
| 81 | W D vs 3rd from {B,E,F,I,J} |
| 82 | W G vs 3rd from {A,E,H,I,J} |
| 83 | RU K vs RU L |
| 84 | W H vs RU J |
| 85 | W B vs 3rd from {E,F,G,I,J} |
| 86 | W J vs RU H |
| 87 | W K vs 3rd from {D,E,I,J,L} |
| 88 | RU D vs RU G |

Which specific third-place team fills each slot depends on the Annex C combination.

### Knockout
- Extra time (30 min) then penalties if tied
- No golden goal / silver goal
- Third-place match played

---

## 6. Prediction Hierarchy

For each simulated match:

1. **Polymarket**: If market exists → use `outcomePrices` as base win/draw/lose probabilities
2. **Elo fallback**: `P(A win) = 1/(1+10^((eloB-eloA)/400))`, draw ~25% scaled
3. **Sampling**: Weighted random selection from {A win, Draw, B win}
4. **Draw resolution**: 50/50 penalty shootout (or Elo-based if detailed)

Polymarket prices give us the "wisdom of the crowd." Elo gives us a reasonable baseline for matches without markets (e.g., future group stage matches).

---

## 7. Streamlit App Layout

### Page 1: Standings & Results
- 12 group tables with current standings
- Match results list with scores
- Third-place ranking table
- Auto-refresh button

### Page 2: Bracket Viewer
- Currently set bracket (based on actual results)
- Fill in qualified teams, show next matchups
- SVG bracket visualization

### Page 3: Simulation
- Controls: N simulations (1k–100k), random seed
- Results:
  - Win probability bar chart for all 48 teams
  - Tournament path explorer (click a team → see most common opponents)
  - Stage-by-stage exit distribution (group, R32, R16, QF, SF, Final, Win)
  - Expected bracket (most common matchup at each slot)

### Page 4: Odds Comparison
- Polymarket vs Elo vs Simulated probabilities side-by-side
- Identify arbitrage/divergence opportunities

---

## 8. Implementation Plan (Ordered)

### Phase 1 — Data Layer (current focus)
1. Initialize project: `uv init`, set up pyproject.toml
2. Build Pydantic models (`models.py`)
3. Build `fetch.py` — worldcup.json parser, Polymarket Gamma API client, Elo scraper
4. Build `cache.py` with TTL

### Phase 2 — Rules Engine
5. Group stage computation + tiebreakers
6. Third-place ranking
7. Bracket pairing (Annex C table encoded)
8. Bracket traversal (winner propagation)

### Phase 3 — Simulation
9. Match predictor (Polymarket → Elo fallback)
10. Monte Carlo engine
11. Metrics aggregation

### Phase 4 — Streamlit UI
12. Main app shell + multi-page navigation
13. Standings page
14. Bracket visualization page
15. Simulation page (controls + charts)
16. Odds comparison page

### Phase 5 — Polish
17. Auto-refresh scheduling
18. Deployment (Streamlit Cloud or self-hosted)
19. Error handling for unavailable data sources

---

## 9. Dependencies

```
streamlit>=1.35
httpx>=0.27
pydantic>=2.0
plotly>=5.18
pandas>=2.0
numpy>=1.24
```

---

## 10. Questions / Decisions Needed

1. **Elo source**: Scrape eloratings.net (dynamic JS) vs worldcupelo.com (simpler) vs hardcoded initial ratings + update from results? I'd recommend footballratings.org or worldcupelo.com as they're more accessible.
2. **Data refresh**: Polling interval for Polymarket odds (30s?) and match results (5 min?).
3. **Polymarket tag_id** for World Cup matches — need to discover via Gamma API.
4. **Annex C encoding**: The matrix has 495 combos × 8 third-place slots. Would embed as a compact lookup table.
5. **Draw probability**: How to handle draws in simulation — Polymarket doesn't always have a "Draw" outcome for match markets.

"""Pre-computed match outcome table for vectorised Monte Carlo simulation.

Pre-samples all possible match outcomes (win/draw/lose) for every team pair
across all simulations. This eliminates per-match probability computation and
random sampling during the hot loop, making each simulation essentially just
routing logic.
"""

from __future__ import annotations

import json

import numpy as np

# Match outcome encoding (int8):
#   WIN_T1 = 0  → team1 wins in regulation
#   DRAW   = 1  → regulation draw (knockout: resolved by coin toss)
#   WIN_T2 = 2  → team2 wins in regulation
WIN_T1: int = 0
DRAW: int = 1
WIN_T2: int = 2


def get_team_order() -> list[str]:
    """Return all 48 team names in a stable order (group A–L)."""
    from importlib.resources import files
    data = json.loads(files("worldcup_sim.data").joinpath("teams.json").read_text())
    groups = data["groups"]
    teams: list[str] = []
    for grp in sorted(groups.keys()):
        teams.extend(groups[grp])
    return teams


def elo_diff_bucket(elo1: float, elo2: float) -> int:
    """Quantize an Elo difference to an integer bucket."""
    return int(round(elo1 - elo2))


def precompute_outcomes(
    team_elo: dict[str, float],
    num_simulations: int,
    seed: int = 42,
) -> np.ndarray:
    """Pre-compute match outcomes for all team pairs × simulations.

    Returns an int8 array of shape (N, N, S) where:
        N = number of teams (48)
        S = num_simulations
        result[i, j, k] = outcome for match team_i vs team_j in sim k

    The diagonal (i == j) is undefined (should never be used).

    Encoding:
        0 = team_i wins in regulation
        1 = regulation draw
        2 = team_j wins in regulation
    """
    teams = get_team_order()
    n = len(teams)
    rng = np.random.default_rng(seed)

    elo_vals = np.array([team_elo.get(t, 1500.0) for t in teams])
    outcomes = np.full((n, n, num_simulations), -1, dtype=np.int8)

    for i in range(n):
        for j in range(i + 1, n):
            elo1, elo2 = elo_vals[i], elo_vals[j]
            elo_diff = elo2 - elo1

            # Compute probabilities (same formula as predictor.py)
            expected = 1.0 / (1.0 + 10.0 ** (elo_diff / 400.0))
            abs_diff = abs(elo1 - elo2)
            draw_prob = 0.28 * max(0.1, 1.0 - abs_diff / 400.0)
            draw_prob = max(0.02, draw_prob)

            p_win1 = expected - 0.5 * draw_prob
            p_win2 = 1.0 - expected - 0.5 * draw_prob
            p_win1 = max(0.0, p_win1)
            p_win2 = max(0.0, p_win2)
            total = p_win1 + draw_prob + p_win2
            if total > 0:
                p_win1 /= total
                draw_prob /= total

            # Vectorised sampling for all S simulations
            r = rng.random(num_simulations)
            outcomes[i, j, :] = np.where(
                r < p_win1, WIN_T1,
                np.where(r < p_win1 + draw_prob, DRAW, WIN_T2),
            )
            outcomes[j, i, :] = np.where(
                r < p_win1, WIN_T2,
                np.where(r < p_win1 + draw_prob, DRAW, WIN_T1),
            )

    return outcomes


def build_team_index(team_elo: dict[str, float]) -> dict[str, int]:
    """Build a mapping from team name to index in the outcome table."""
    teams = get_team_order()
    return {t: i for i, t in enumerate(teams) if t in team_elo}


def get_outcome(
    outcomes: np.ndarray,
    team_idx: dict[str, int],
    t1: str,
    t2: str,
    sim_idx: int,
) -> int:
    """Look up the pre-sampled outcome for a match.

    Returns one of WIN_T1 (0), DRAW (1), WIN_T2 (2).
    """
    i = team_idx[t1]
    j = team_idx[t2]
    return int(outcomes[i, j, sim_idx])


def sample_goals(
    outcome: int,
    rng: np.random.Generator,
) -> tuple[int, int]:
    """Generate realistic goal counts given the match outcome.

    Args:
        outcome: WIN_T1, DRAW, or WIN_T2.
        rng: Random generator.

    Returns:
        (goals_team1, goals_team2).
    """
    if outcome == DRAW:
        g = min(rng.poisson(1.2), 4)
        return (g, g)

    # Winner scores between 1 and 5
    winner_goals = min(rng.poisson(1.5) + 1, 5)
    loser_goals = min(rng.poisson(1.0), 3)
    if loser_goals >= winner_goals:
        loser_goals = winner_goals - 1
    if loser_goals < 0:
        loser_goals = 0

    if outcome == WIN_T1:
        return (winner_goals, loser_goals)
    else:  # WIN_T2
        return (loser_goals, winner_goals)

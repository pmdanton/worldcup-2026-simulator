"""Match outcome prediction using Elo ratings and Polymarket odds."""

from __future__ import annotations

import numpy as np


def get_match_probabilities(
    team1: str,
    team2: str,
    team_elo: dict[str, float],
    match_date: str = "",
    polymarket_odds: dict[str, float] | None = None,
) -> tuple[float, float, float]:
    """Return win/draw/lose probabilities for team1.

    Priority:
        1. Polymarket odds if provided and valid.
        2. Elo-based formula.

    Args:
        team1: First team name.
        team2: Second team name.
        team_elo: Mapping of team name to Elo rating.
        match_date: Optional match date (used for Polymarket lookup upstream).
        polymarket_odds: Optional dict with "win", "draw", "lose" keys.

    Returns:
        Tuple of (p_win1, p_draw, p_win2) where values sum to ~1.
    """
    if polymarket_odds is not None:
        win = polymarket_odds.get("win", 0.0)
        draw = polymarket_odds.get("draw", 0.0)
        lose = polymarket_odds.get("lose", 0.0)
        total = win + draw + lose
        if total > 0:
            return (win / total, draw / total, lose / total)

    elo1 = team_elo.get(team1, 1500.0)
    elo2 = team_elo.get(team2, 1500.0)

    elo_diff = elo2 - elo1
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
        p_win2 /= total

    return (p_win1, draw_prob, p_win2)


def sample_match_outcome(
    p_win1: float,
    p_draw: float,
    p_win2: float,
    rng: np.random.Generator,
    resolve_draw_coin_toss: bool = False,
) -> tuple[str, tuple[int, int]]:
    """Sample a match outcome given win/draw/lose probabilities.

    Draws are resolved by a simulated penalty shootout (5 rounds, P(score)=0.75)
    by default. When *resolve_draw_coin_toss* is True, draws are decided by a
    fair coin toss instead (appropriate for knockout-stage simulation since
    penalties are essentially unpredictable).

    Generates realistic scores using a Poisson-ish distribution.

    Args:
        p_win1: Probability team1 wins in regulation.
        p_draw: Probability of a draw in regulation.
        p_win2: Probability team2 wins in regulation.
        rng: NumPy random generator.
        resolve_draw_coin_toss: If True, resolve draws with a fair coin toss
            instead of simulated penalty shootout.

    Returns:
        Tuple of ("1"|"2", (goals_team1, goals_team2)).
        "1" means team1 advances, "2" means team2 advances.
        The goals reflect the regulation score (may be a draw resolved by penalties).
    """
    total = p_win1 + p_draw + p_win2
    r = rng.random() * total

    if r < p_win1:
        outcome = "win1"
    elif r < p_win1 + p_draw:
        outcome = "draw"
    else:
        outcome = "win2"

    if outcome == "draw":
        goals = rng.poisson(1.2)
        goals = min(goals, 4)
        score = (goals, goals)

        if resolve_draw_coin_toss:
            winner_side = "1" if rng.random() < 0.5 else "2"
        else:
            p_pen = 0.75
            pen1 = rng.binomial(5, p_pen)
            pen2 = rng.binomial(5, p_pen)
            while pen1 == pen2:
                pen1 += rng.binomial(1, p_pen)
                pen2 += rng.binomial(1, p_pen)
            winner_side = "1" if pen1 > pen2 else "2"
        return (winner_side, score)

    if outcome == "win1":
        winner_goals = rng.poisson(1.5) + 1
        loser_goals = rng.poisson(1.0)
        winner_goals = min(winner_goals, 5)
        loser_goals = min(loser_goals, 4)
        if loser_goals >= winner_goals:
            loser_goals = winner_goals - 1
        if loser_goals < 0:
            loser_goals = 0
        return ("1", (winner_goals, loser_goals))
    else:
        winner_goals = rng.poisson(1.5) + 1
        loser_goals = rng.poisson(1.0)
        winner_goals = min(winner_goals, 5)
        loser_goals = min(loser_goals, 4)
        if loser_goals >= winner_goals:
            loser_goals = winner_goals - 1
        if loser_goals < 0:
            loser_goals = 0
        return ("2", (loser_goals, winner_goals))

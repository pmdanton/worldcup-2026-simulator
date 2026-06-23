"""Elo calibration from Polymarket tournament winner odds (Bradley-Terry).

Approach: treat Polymarket tournament-win probabilities as proportional to
10^(rating/400), the Bradley-Terry strength.  Invert to get market-implied
Elo ratings, then shift to preserve the Elo scale.

If the market says France is 19.8% to win the tournament and Spain is 13.9%,
the implied strength ratio is log10(0.198/0.139) * 400 ≈ 46 Elo points in
France's favour — very different from the stale pre-tournament gap where
Spain (2171) was 108 points ahead of France (2063).
"""

from __future__ import annotations

import numpy as np


def normalize_probabilities(
    raw_probs: dict[str, float],
    min_prob: float = 0.0001,
) -> dict[str, float]:
    """Normalize raw Polymarket win probabilities to sum to 1.

    Polymarket tournament winner markets are individual Yes/No binary markets.
    Their prices don't sum to 1 (overround).  This function:
    1. Filters out negligible probabilities (< min_prob)
    2. Normalizes the remainder to sum to 1

    Args:
        raw_probs: team_name → probability from Polymarket (raw, not normalized).
        min_prob: Minimum probability threshold. Teams below this are excluded.

    Returns:
        Normalized probabilities summing to 1.
    """
    filtered = {t: p for t, p in raw_probs.items() if p >= min_prob}
    total = sum(filtered.values())
    if total <= 0:
        return {}
    return {t: p / total for t, p in filtered.items()}


def compute_implied_elo(
    poly_winner_odds: dict[str, float],
    base_elo: dict[str, float],
    min_prob: float = 0.0001,
    scale_preserve: bool = True,
) -> dict[str, float]:
    """Compute market-implied Elo ratings from Polymarket tournament win odds.

    Uses a Bradley-Terry model: tournament win probability is proportional
    to 10^(rating/400).  Inverted:

        implied_rating_i = 400 * log10(p_i) + C

    where C is chosen so the average implied rating matches the average base
    Elo rating of the same teams (scale_preserve=True).

    Args:
        poly_winner_odds: team_name → Polymarket tournament win probability
            (as returned by fetch_polymarket_tournament_odds).
        base_elo: team_name → pre-tournament Elo rating (fallback for teams
            with no Polymarket odds).
        min_prob: Minimum probability threshold for inclusion in calibration.
        scale_preserve: If True, shift implied ratings to have the same mean
            as base_elo.  If False, use raw implied ratings (arbitrary scale).

    Returns:
        Dict mapping team_name → calibrated Elo rating.  Teams with no
        Polymarket data return their base_elo unchanged.
    """
    norm_probs = normalize_probabilities(poly_winner_odds, min_prob)

    if not norm_probs:
        return dict(base_elo)

    # Compute raw implied ratings: r_i_raw = 400 * log10(p_i)
    # Add a small epsilon to avoid log(0) for teams that somehow slipped through
    implied_raw: dict[str, float] = {}
    for team, p in norm_probs.items():
        safe_p = max(p, 1e-10)
        implied_raw[team] = 400.0 * np.log10(safe_p)

    if scale_preserve:
        # Compute mean of implied ratings for teams that have both implied and base elo
        common_teams = [t for t in implied_raw if t in base_elo]
        if common_teams:
            implied_mean = np.mean([implied_raw[t] for t in common_teams])
            base_mean = np.mean([base_elo[t] for t in common_teams])
            shift = base_mean - implied_mean
        else:
            shift = 0.0

        # Apply shift and blend
        result: dict[str, float] = {}
        for team, rating in base_elo.items():
            if team in implied_raw:
                result[team] = implied_raw[team] + shift
            else:
                result[team] = rating
    else:
        # No scale preservation: use raw implied + base elo as fallback
        result = dict(base_elo)
        for team, rating in implied_raw.items():
            result[team] = rating

    return result


def compute_implied_elo_robust(
    poly_winner_odds: dict[str, float],
    base_elo: dict[str, float],
    min_prob: float = 0.0001,
    blend_strength: float = 0.3,
) -> dict[str, float]:
    """Compute market-implied Elo with Bayesian shrinkage toward base Elo.

    For teams with thin Polymarket liquidity, pure implied Elo can be noisy.
    This version blends:

        final_rating = blend_strength * base_elo + (1 - blend_strength) * implied_elo

    but applied to implied Elo computed WITHOUT scale preservation, then the
    result is re-scaled.  More principled than the simple version when odds
    are noisy.

    Args:
        poly_winner_odds: team_name → Polymarket tournament win probability.
        base_elo: team_name → pre-tournament Elo rating.
        min_prob: Minimum probability threshold.
        blend_strength: Weight on base Elo (0 = pure market, 1 = pure base).

    Returns:
        Dict mapping team_name → blended Elo rating.
    """
    if blend_strength >= 1.0:
        return dict(base_elo)

    if blend_strength <= 0.0:
        return compute_implied_elo(poly_winner_odds, base_elo, min_prob, scale_preserve=False)

    # Get pure implied (unscaled)
    pure_implied = compute_implied_elo(poly_winner_odds, base_elo, min_prob, scale_preserve=False)

    # Blend in log-strength space
    blended_raw: dict[str, float] = {}
    for team, base_r in base_elo.items():
        if team in pure_implied:
            blended_raw[team] = blend_strength * base_r + (1 - blend_strength) * pure_implied[team]
        else:
            blended_raw[team] = base_r

    # Re-scale to match base_elo mean
    common = [t for t in blended_raw if t in base_elo]
    if common:
        blend_mean = np.mean([blended_raw[t] for t in common])
        base_mean = np.mean([base_elo[t] for t in common])
        shift = base_mean - blend_mean
        return {t: r + shift for t, r in blended_raw.items()}
    else:
        return dict(blended_raw)


def compute_implied_elo_variance_preserving(
    poly_winner_odds: dict[str, float],
    base_elo: dict[str, float],
    min_prob: float = 0.0001,
) -> dict[str, float]:
    """Compute market-implied Elo preserving both mean AND variance of base Elo.

    The pure Bradley-Terry inversion from tournament win odds amplifies small
    probability differences into huge rating gaps (because tournament win prob
    is a power function of pairwise strength).  This version normalises the
    implied ratings to have the same mean AND standard deviation as base_elo,
    preserving the market's rank ordering while keeping the Elo scale realistic
    for head-to-head predictions.

    Steps:
    1. Normalise Polymarket probabilities to sum to 1
    2. Compute raw Bradley-Terry ratings: r_i = 400 * log10(p_i)
    3. Standardise to z-scores
    4. Map to N(base_mean, base_std)

    Args:
        poly_winner_odds: team_name → Polymarket tournament win probability.
        base_elo: team_name → pre-tournament Elo rating.
        min_prob: Minimum probability threshold.

    Returns:
        Dict mapping team_name → variance-preserved calibrated Elo.
        Teams with no Polymarket data return base_elo unchanged.
    """
    norm_probs = normalize_probabilities(poly_winner_odds, min_prob)

    if not norm_probs:
        return dict(base_elo)

    # Raw Bradley-Terry implied ratings
    implied_raw: dict[str, float] = {}
    for team, p in norm_probs.items():
        safe_p = max(p, 1e-10)
        implied_raw[team] = 400.0 * np.log10(safe_p)

    # Compute base Elo distribution stats (only teams with market odds)
    common_teams = [t for t in implied_raw if t in base_elo]
    if not common_teams:
        return dict(base_elo)

    base_values = np.array([base_elo[t] for t in common_teams])
    implied_values = np.array([implied_raw[t] for t in common_teams])

    base_mean = float(np.mean(base_values))
    base_std = float(np.std(base_values, ddof=0))
    implied_mean = float(np.mean(implied_values))
    implied_std = float(np.std(implied_values, ddof=0))

    result: dict[str, float] = {}
    for team, base_r in base_elo.items():
        if team in implied_raw:
            # Standardise then map to base distribution
            if implied_std > 0:
                z = (implied_raw[team] - implied_mean) / implied_std
                result[team] = z * base_std + base_mean
            else:
                result[team] = base_mean
        else:
            result[team] = base_r

    return result

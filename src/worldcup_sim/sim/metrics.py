"""Tournament simulation metrics: bracket probabilities and team paths."""

from __future__ import annotations

from collections import Counter, defaultdict

from src.worldcup_sim.sim.engine import SimulationRun


def compute_bracket_probabilities(
    runs: list[SimulationRun],
    match_ids: list[int],
) -> dict[int, dict[str, float]]:
    """For each match slot, compute the probability of each team appearing.

    Args:
        runs: Completed simulation runs.
        match_ids: List of match IDs to analyze (e.g. [97, 98, 99, 100] for QF).

    Returns:
        Dict mapping match_id → dict of team → probability of appearing in
        that match (either as team1 or team2).
    """
    total = max(len(runs), 1)
    result: dict[int, dict[str, float]] = {}

    for mid in match_ids:
        counter: Counter[str] = Counter()
        for run in runs:
            km = run.played_knockout_matches.get(mid)
            if km is None:
                continue
            if km.team1:
                counter[str(km.team1)] += 1
            if km.team2:
                counter[str(km.team2)] += 1
        result[mid] = {team: count / total for team, count in counter.items()}

    return result


def find_team_path(team: str, run: SimulationRun) -> list[dict]:
    """Find the most common opponent path for a team through a simulation run.

    Returns a chronological list of dicts with keys: "match_id", "round",
    "opponent", "score", "result" (won/lost/draw_resolved).

    Args:
        team: The team name to trace.
        run: A single simulation run.

    Returns:
        Ordered list of matches the team participated in.
    """
    path: list[dict] = []

    for mid in sorted(run.played_knockout_matches.keys()):
        km = run.played_knockout_matches[mid]
        if team not in (str(km.team1), str(km.team2)):
            continue

        if team == str(km.team1):
            opponent = str(km.team2) if km.team2 else "Unknown"
        else:
            opponent = str(km.team1) if km.team1 else "Unknown"

        if km.winner == team:
            result = "won"
        elif km.winner is None:
            result = "draw_resolved"
        else:
            result = "lost"

        path.append({
            "match_id": mid,
            "round": km.round_name,
            "opponent": opponent,
            "score": km.score_ft,
            "result": result,
        })

    return path


def aggregate_simulations(runs: list[SimulationRun]) -> dict:
    """Aggregate multiple simulation runs into summary statistics.

    Returns a dict with:
        - "win_counts": dict of team → number of tournament wins
        - "final_counts": dict of team → number of final appearances
        - "semi_counts": dict of team → number of semi-final appearances
        - "total_runs": total number of simulation runs

    Args:
        runs: Completed simulation runs.

    Returns:
        Dict of aggregated statistics.
    """
    total = len(runs)
    win_counts: Counter[str] = Counter()
    final_counts: Counter[str] = Counter()
    semi_counts: Counter[str] = Counter()

    for run in runs:
        win_counts[run.winner] += 1
        final_counts[run.winner] += 1
        if run.runner_up:
            final_counts[run.runner_up] += 1
        for sf in run.semi_finalists:
            semi_counts[sf] += 1

    return {
        "win_counts": dict(win_counts),
        "final_counts": dict(final_counts),
        "semi_counts": dict(semi_counts),
        "total_runs": total,
    }

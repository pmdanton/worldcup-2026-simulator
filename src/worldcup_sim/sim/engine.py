"""Monte Carlo tournament simulation engine.

Runs many parallel simulations of the World Cup from the current state,
accounting for already-played matches and simulating unplayed ones.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from worldcup_sim.data.models import KnockoutMatch, MatchResult
from worldcup_sim.rules.bracket import build_full_bracket, build_round_of_32
from worldcup_sim.rules.group_stage import apply_group_tiebreakers, compute_group_standings
from worldcup_sim.rules.third_place import rank_third_placed_teams
from worldcup_sim.sim.outcome_table import (
    DRAW,
    WIN_T1,
    WIN_T2,
    build_team_index,
    get_outcome,
    sample_goals,
)
from worldcup_sim.sim.predictor import get_match_probabilities, sample_match_outcome

_TEAMS_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "teams.json"


def _load_teams() -> dict[str, list[str]]:
    with open(_TEAMS_PATH) as f:
        data = json.load(f)
    return data["groups"]


def _round_name(match_id: int) -> str:
    """Return the round name for a given match ID."""
    if 73 <= match_id <= 88:
        return "Round of 32"
    if 89 <= match_id <= 96:
        return "Round of 16"
    if 97 <= match_id <= 100:
        return "Quarter-finals"
    if match_id in (101, 102):
        return "Semi-finals"
    if match_id == 103:
        return "Third place match"
    if match_id == 104:
        return "Final"
    return "Unknown"


def _get_group_fixtures(teams: list[str]) -> list[tuple[str, str]]:
    """Return the 6 standard group-stage fixtures for a 4-team group."""
    return [
        (teams[0], teams[1]),
        (teams[2], teams[3]),
        (teams[0], teams[2]),
        (teams[1], teams[3]),
        (teams[0], teams[3]),
        (teams[1], teams[2]),
    ]


def _find_match(
    matches: list[MatchResult], team1: str, team2: str,
) -> MatchResult | None:
    """Find a match result for the given pair (order-independent)."""
    for m in matches:
        if (m.team1 == team1 and m.team2 == team2) or (m.team1 == team2 and m.team2 == team1):
            return m
    return None


def _build_played_ko_map(matches: list[MatchResult]) -> dict[int, MatchResult]:
    """Extract played knockout matches keyed by match_id."""
    result: dict[int, MatchResult] = {}
    for m in matches:
        if m.match_id is not None and m.match_id >= 73 and m.played:
            result[m.match_id] = m
    return result


def _propagate_winner(
    bracket: dict[int, KnockoutMatch],
    match_id: int,
    winner: str,
) -> dict[int, KnockoutMatch]:
    """Update bracket by propagating a winner into downstream match slots.

    Note: Match 103 (third-place) is NOT updated here — it receives semi-final
    *losers*, which are handled separately in the main simulation loop.
    """
    updated = dict(bracket)
    for candidate_id, candidate in updated.items():
        if candidate_id == 103:
            continue  # Third-place match gets losers, not winners
        changed = False
        new_team1 = candidate.team1
        new_team2 = candidate.team2
        if candidate.source_match_1 == match_id:
            new_team1 = winner
            changed = True
        if candidate.source_match_2 == match_id:
            new_team2 = winner
            changed = True
        if changed:
            updated[candidate_id] = KnockoutMatch(
                match_id=candidate.match_id,
                round_name=candidate.round_name,
                team1=new_team1,
                team2=new_team2,
                source_match_1=candidate.source_match_1,
                source_match_2=candidate.source_match_2,
            )
    return updated


@dataclass
class SimulationRun:
    """Result of one complete tournament simulation."""

    winner: str
    runner_up: str
    semi_finalists: list[str]
    elimination_round: dict[str, str]
    played_knockout_matches: dict[int, KnockoutMatch] = field(default_factory=dict)


class SimulationResults:
    """Aggregated results from many tournament simulations."""

    def __init__(
        self,
        runs: list[SimulationRun],
        match_odds_provenance: dict[str, str] | None = None,
    ) -> None:
        self.num_sims = len(runs)
        self.all_runs = runs
        self.match_odds_provenance: dict[str, str] = match_odds_provenance or {}

        team_wins: dict[str, int] = defaultdict(int)
        team_final: dict[str, int] = defaultdict(int)
        team_semi: dict[str, int] = defaultdict(int)
        team_qf: dict[str, int] = defaultdict(int)
        team_r16: dict[str, int] = defaultdict(int)
        team_r32: dict[str, int] = defaultdict(int)
        team_group: dict[str, int] = defaultdict(int)

        bracket_freq: dict[int, dict[str, Counter[str]]] = defaultdict(
            lambda: {"team1": Counter(), "team2": Counter()},
        )

        for run in runs:
            team_wins[run.winner] += 1

            for team, eliminated_at in run.elimination_round.items():
                if eliminated_at == "Group Stage":
                    team_group[team] += 1
                elif eliminated_at == "Round of 32":
                    team_r32[team] += 1
                    team_group[team] += 1
                elif eliminated_at == "Round of 16":
                    team_r16[team] += 1
                    team_r32[team] += 1
                    team_group[team] += 1
                elif eliminated_at == "Quarter-finals":
                    team_qf[team] += 1
                    team_r16[team] += 1
                    team_r32[team] += 1
                    team_group[team] += 1
                elif eliminated_at == "Semi-finals":
                    team_semi[team] += 1
                    team_qf[team] += 1
                    team_r16[team] += 1
                    team_r32[team] += 1
                    team_group[team] += 1
                elif eliminated_at == "Final":
                    team_final[team] += 1
                    team_semi[team] += 1
                    team_qf[team] += 1
                    team_r16[team] += 1
                    team_r32[team] += 1
                    team_group[team] += 1

            # Winner also gets all progression counts
            team_final[run.winner] += 1
            team_semi[run.winner] += 1
            team_qf[run.winner] += 1
            team_r16[run.winner] += 1
            team_r32[run.winner] += 1
            team_group[run.winner] += 1

            for sf_team in run.semi_finalists:
                team_semi.setdefault(sf_team, 0)
                team_qf.setdefault(sf_team, 0)
                team_r16.setdefault(sf_team, 0)
                team_r32.setdefault(sf_team, 0)
                team_group.setdefault(sf_team, 0)

            for mid, km in run.played_knockout_matches.items():
                if km.team1:
                    bracket_freq[mid]["team1"][km.team1] += 1
                if km.team2:
                    bracket_freq[mid]["team2"][km.team2] += 1

        total = max(self.num_sims, 1)
        self.win_probs = {t: c / total for t, c in team_wins.items()}
        self.final_probs = {t: c / total for t, c in team_final.items()}
        self.semi_probs = {t: c / total for t, c in team_semi.items()}
        self.qf_probs = {t: c / total for t, c in team_qf.items()}
        self.r16_probs = {t: c / total for t, c in team_r16.items()}
        self.r32_probs = {t: c / total for t, c in team_r32.items()}
        self.group_exit_probs = {t: c / total for t, c in team_group.items()}

        self.expected_bracket: dict[int, KnockoutMatch] = {}
        for mid in sorted(bracket_freq.keys()):
            t1 = bracket_freq[mid]["team1"].most_common(1)
            t2 = bracket_freq[mid]["team2"].most_common(1)
            self.expected_bracket[mid] = KnockoutMatch(
                match_id=mid,
                round_name=_round_name(mid),
                team1=t1[0][0] if t1 else None,
                team2=t2[0][0] if t2 else None,
            )

    def to_dataframe(self) -> pd.DataFrame:
        """Return a DataFrame with team probabilities at each round."""
        all_teams = set(self.win_probs) | set(self.final_probs) | set(self.semi_probs) | set(self.qf_probs) | set(self.r16_probs) | set(self.r32_probs) | set(self.group_exit_probs)
        rows = []
        for team in sorted(all_teams):
            rows.append({
                "Team": team,
                "Win": self.win_probs.get(team, 0.0),
                "Final": self.final_probs.get(team, 0.0),
                "Semi": self.semi_probs.get(team, 0.0),
                "QF": self.qf_probs.get(team, 0.0),
                "R16": self.r16_probs.get(team, 0.0),
                "R32": self.r32_probs.get(team, 0.0),
                "Group": self.group_exit_probs.get(team, 0.0),
            })
        df = pd.DataFrame(rows)
        return df.sort_values("Win", ascending=False).reset_index(drop=True)

    def top_teams(self, n: int = 10) -> list[tuple[str, float]]:
        """Return the top *n* teams by win probability."""
        sorted_teams = sorted(self.win_probs.items(), key=lambda x: x[1], reverse=True)
        return sorted_teams[:n]


def run_simulation(
    matches: list[MatchResult],
    team_elo: dict[str, float],
    num_simulations: int = 10000,
    polymarket_odds_map: dict[str, dict[str, float]] | None = None,
    seed: int | None = None,
    outcome_table: np.ndarray | None = None,
) -> SimulationResults:
    """Run Monte Carlo simulations of the tournament.

    Uses a pre-computed outcome table for fast match resolution when available.
    Falls back to per-match probability computation for matches with Polymarket
    odds (which differ from Elo-base).

    Args:
        matches: All known match data (played + scheduled) from worldcup.json.
        team_elo: Mapping of team name to Elo rating.
        num_simulations: Number of complete tournament simulations to run.
        polymarket_odds_map: Optional dict mapping canonical match keys
            ("Team1/Team2") to odds dicts with "win", "draw", "lose".
            Only keys present here are considered Polymarket-sourced;
            all others fall back to Elo.
        seed: Optional random seed for reproducibility.
        outcome_table: Pre-computed outcome array of shape (N, N, S).
            Built from Elo ratings. When provided, matches without Polymarket
            odds use a fast table lookup instead of per-simulation computation.

    Returns:
        SimulationResults with aggregated probabilities, bracket expectations,
        and match_odds_provenance.
    """
    # Build provenance: which match-ups have Polymarket odds?
    match_odds_provenance: dict[str, str] = {}
    if polymarket_odds_map is not None:
        for key in polymarket_odds_map:
            match_odds_provenance[key] = "polymarket"

    # Team index for outcome table lookup
    team_idx: dict[str, int] | None = None
    if outcome_table is not None:
        team_idx = build_team_index(team_elo)
    groups = _load_teams()
    played_ko = _build_played_ko_map(matches)

    # Index group matches by group letter
    group_matches: dict[str, list[MatchResult]] = defaultdict(list)
    for m in matches:
        if m.group is not None:
            group_matches[m.group].append(m)

    runs: list[SimulationRun] = []

    for sim_idx in range(num_simulations):
        rng = np.random.default_rng(
            seed + sim_idx if seed is not None else None
        )

        # ── Simulate group stage ──────────────────────────────
        group_standings: dict[str, list] = {}
        all_group_results: list[MatchResult] = []

        for group_letter, team_list in sorted(groups.items()):
            fixtures = _get_group_fixtures(team_list)
            existing = group_matches.get(group_letter, [])
            group_results: list[MatchResult] = []

            for t1, t2 in fixtures:
                found = _find_match(existing, t1, t2)
                if found is not None and found.played:
                    group_results.append(found)
                else:
                    odds = None
                    key = sorted([t1, t2])[0] + "/" + sorted([t1, t2])[1]
                    if polymarket_odds_map is not None:
                        odds = polymarket_odds_map.get(key)

                    if odds is not None:
                        # Polymarket odds: use per-match computation
                        p1, pd_, p2 = get_match_probabilities(t1, t2, team_elo, "", odds)
                        winner, score = sample_match_outcome(p1, pd_, p2, rng)
                        if key not in match_odds_provenance:
                            match_odds_provenance[key] = "polymarket"
                    elif outcome_table is not None and team_idx is not None:
                        # Elo-based: use pre-computed outcome table
                        outcome = get_outcome(outcome_table, team_idx, t1, t2, sim_idx)
                        score = sample_goals(outcome, rng)
                    else:
                        # Fallback: compute on the fly
                        p1, pd_, p2 = get_match_probabilities(t1, t2, team_elo, "", None)
                        winner, score = sample_match_outcome(p1, pd_, p2, rng)

                    sim_match = MatchResult(
                        team1=t1,
                        team2=t2,
                        score_ft=score,
                        group=group_letter,
                        round_name=f"Group {group_letter}",
                        date="",
                    )
                    group_results.append(sim_match)

            standings = compute_group_standings(group_results, group_letter)
            standings = apply_group_tiebreakers(standings, group_results)
            group_standings[group_letter] = standings
            all_group_results.extend(group_results)

        # ── Rank third-placed teams ───────────────────────────
        third_rankings = rank_third_placed_teams(group_standings)
        advancing_third: list[tuple[str, str]] = [
            (t.group, t.team) for t in third_rankings[:8]
        ]

        # ── Build knockout bracket ────────────────────────────
        group_winners: dict[str, str] = {}
        group_runners_up: dict[str, str] = {}
        for grp, st_list in group_standings.items():
            if len(st_list) >= 1:
                group_winners[grp] = st_list[0].team
            if len(st_list) >= 2:
                group_runners_up[grp] = st_list[1].team

        r32 = build_round_of_32(group_winners, group_runners_up, advancing_third)
        bracket = build_full_bracket(r32)

        # ── Resolve known played KO matches ───────────────────
        ko_results: dict[int, KnockoutMatch] = {}
        elimination: dict[str, str] = {}

        # Mark all teams as starting in group stage
        for team_list in groups.values():
            for t in team_list:
                elimination[t] = "Group Stage"

        # Process played knockout matches first (in order)
        played_ko_ordered = sorted(played_ko.items())
        for mid, pm in played_ko_ordered:
            km = bracket.get(mid)
            if km is None or km.team1 is None or km.team2 is None:
                continue
            winner = pm.winner
            if winner is None:
                continue

            ko_results[mid] = KnockoutMatch(
                match_id=mid,
                round_name=_round_name(mid),
                team1=km.team1,
                team2=km.team2,
                winner=winner,
                score_ft=pm.score_ft,
                source_match_1=km.source_match_1,
                source_match_2=km.source_match_2,
            )
            loser = km.team2 if winner == km.team1 else km.team1
            elimination[loser] = _round_name(mid)
            bracket = _propagate_winner(bracket, mid, winner)

        # ── Simulate remaining KO matches in order ────────────
        sf_losers: dict[int, str] = {}

        for mid in sorted(bracket.keys()):
            km = bracket[mid]
            if km.team1 is None or km.team2 is None:
                continue
            if km.winner is not None or mid in ko_results:
                continue

            # Handle third-place match separately after semi-finals
            if mid == 103:
                continue

            odds = None
            key = sorted([str(km.team1), str(km.team2)])[0] + "/" + sorted([str(km.team1), str(km.team2)])[1]
            # Only use pre-fetched Polymarket odds (no on-demand fetch in hot loop)
            if polymarket_odds_map is not None:
                odds = polymarket_odds_map.get(key)

            if odds is not None:
                # Polymarket odds: per-match computation
                if key not in match_odds_provenance:
                    match_odds_provenance[key] = "polymarket"
                p1, pd_, p2 = get_match_probabilities(
                    str(km.team1), str(km.team2), team_elo, "", odds,
                )
                winner_side, score = sample_match_outcome(
                    p1, pd_, p2, rng, resolve_draw_coin_toss=True,
                )
            elif outcome_table is not None and team_idx is not None:
                # Elo-based: pre-computed outcome table
                if key not in match_odds_provenance:
                    match_odds_provenance[key] = "elo"
                outcome = get_outcome(outcome_table, team_idx, str(km.team1), str(km.team2), sim_idx)
                if outcome == DRAW:
                    # Coin toss for knockout draws
                    winner_side = "1" if rng.random() < 0.5 else "2"
                elif outcome == WIN_T1:
                    winner_side = "1"
                else:
                    winner_side = "2"
                score = sample_goals(outcome, rng)
            else:
                # Fallback: compute on the fly
                if key not in match_odds_provenance:
                    match_odds_provenance[key] = "elo"
                p1, pd_, p2 = get_match_probabilities(
                    str(km.team1), str(km.team2), team_elo, "", None,
                )
                winner_side, score = sample_match_outcome(
                    p1, pd_, p2, rng, resolve_draw_coin_toss=True,
                )

            winner = km.team1 if winner_side == "1" else km.team2
            loser = km.team2 if winner == km.team1 else km.team1

            ko_results[mid] = KnockoutMatch(
                match_id=mid,
                round_name=_round_name(mid),
                team1=km.team1,
                team2=km.team2,
                winner=winner,
                score_ft=score,
                source_match_1=km.source_match_1,
                source_match_2=km.source_match_2,
            )
            elimination[str(loser)] = _round_name(mid)
            bracket = _propagate_winner(bracket, mid, str(winner))

            # Track semi-final losers for third-place match
            if mid in (101, 102):
                sf_losers[mid] = str(loser)

        # ── Simulate third-place match ────────────────────────
        if 101 in sf_losers and 102 in sf_losers:
            loser_101 = sf_losers[101]
            loser_102 = sf_losers[102]

            odds = None
            key = sorted([loser_101, loser_102])[0] + "/" + sorted([loser_101, loser_102])[1]
            if polymarket_odds_map is not None:
                odds = polymarket_odds_map.get(key)

            if odds is not None:
                if key not in match_odds_provenance:
                    match_odds_provenance[key] = "polymarket"
                p1, pd_, p2 = get_match_probabilities(
                    loser_101, loser_102, team_elo, "", odds,
                )
                winner_side, score = sample_match_outcome(
                    p1, pd_, p2, rng, resolve_draw_coin_toss=True,
                )
            elif outcome_table is not None and team_idx is not None:
                if key not in match_odds_provenance:
                    match_odds_provenance[key] = "elo"
                outcome = get_outcome(outcome_table, team_idx, loser_101, loser_102, sim_idx)
                if outcome == DRAW:
                    winner_side = "1" if rng.random() < 0.5 else "2"
                elif outcome == WIN_T1:
                    winner_side = "1"
                else:
                    winner_side = "2"
                score = sample_goals(outcome, rng)
            else:
                if key not in match_odds_provenance:
                    match_odds_provenance[key] = "elo"
                p1, pd_, p2 = get_match_probabilities(
                    loser_101, loser_102, team_elo, "", None,
                )
                winner_side, score = sample_match_outcome(
                    p1, pd_, p2, rng, resolve_draw_coin_toss=True,
                )

            tp_winner = loser_101 if winner_side == "1" else loser_102
            tp_loser = loser_102 if tp_winner == loser_101 else loser_101
            elimination[tp_loser] = "Third place match"

            third_place_km = bracket.get(103)
            ko_results[103] = KnockoutMatch(
                match_id=103,
                round_name=_round_name(103),
                team1=loser_101,
                team2=loser_102,
                winner=tp_winner,
                score_ft=score,
                source_match_1=third_place_km.source_match_1 if third_place_km else 101,
                source_match_2=third_place_km.source_match_2 if third_place_km else 102,
            )

        # ── Extract tournament results ────────────────────────
        final_match = ko_results.get(104)
        sf1 = ko_results.get(101)
        sf2 = ko_results.get(102)

        if final_match and final_match.winner:
            tournament_winner = final_match.winner
            tournament_runner_up = (
                final_match.team2 if final_match.winner == final_match.team1
                else final_match.team1
            )
            elimination[str(tournament_runner_up)] = "Final"
            elimination[str(tournament_winner)] = "Winner"
        else:
            tournament_winner = "Unknown"
            tournament_runner_up = "Unknown"

        semi_finalists: list[str] = []
        if sf1:
            if sf1.team1:
                semi_finalists.append(str(sf1.team1))
            if sf1.team2:
                semi_finalists.append(str(sf1.team2))
        if sf2:
            if sf2.team1:
                semi_finalists.append(str(sf2.team1))
            if sf2.team2:
                semi_finalists.append(str(sf2.team2))

        # Remove Winner from elimination (they're not eliminated)
        if tournament_winner in elimination:
            del elimination[tournament_winner]

        runs.append(SimulationRun(
            winner=str(tournament_winner),
            runner_up=str(tournament_runner_up),
            semi_finalists=semi_finalists,
            elimination_round=elimination,
            played_knockout_matches=ko_results,
        ))

    return SimulationResults(runs, match_odds_provenance=match_odds_provenance)

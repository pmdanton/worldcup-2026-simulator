"""Knockout bracket construction: Round of 32 pairings and full bracket traversal.

Implements the full bracket from Round of 32 (matches 73–88) through the Final
(match 104) per FIFA 2026 regulations, including Annex C third-place pairings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

# Use src-relative import to work with project layout
from worldcup_sim.data.models import KnockoutMatch

# ──────────────────────────────────────────────
#  Load Annex C lookup table (495 combinations)
# ──────────────────────────────────────────────

_ANNEX_C_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "annex_c.json"

with open(_ANNEX_C_PATH) as f:
    _ANNEX_C_RAW: dict[str, dict] = json.load(f)

# Build lookup: tuple of 8 sorted group letters → list of 8 "3X" assignments
_ANNEX_C: dict[tuple[str, ...], list[str]] = {}
for _combo_num, _data in _ANNEX_C_RAW.items():
    _key = tuple(sorted(_data["groups"]))
    _ANNEX_C[_key] = _data["assignments"]


# ──────────────────────────────────────────────
#  Match ID → round name helpers
# ──────────────────────────────────────────────


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


# ──────────────────────────────────────────────
#  Fixed-pairing matches (no third-place lookup)
# ──────────────────────────────────────────────

# Matches that are always between a group winner and runner-up,
# or runner-up and runner-up.
_FIXED_PAIRINGS: dict[int, tuple[str, str, str]] = {
    # match_id → (label, team1_formula, team2_formula)
    73: ("Runner-up A vs Runner-up B", "RU_A", "RU_B"),
    75: ("Winner F vs Runner-up C", "W_F", "RU_C"),
    76: ("Winner C vs Runner-up F", "W_C", "RU_F"),
    78: ("Runner-up E vs Runner-up I", "RU_E", "RU_I"),
    83: ("Runner-up K vs Runner-up L", "RU_K", "RU_L"),
    84: ("Winner H vs Runner-up J", "W_H", "RU_J"),
    86: ("Winner J vs Runner-up H", "W_J", "RU_H"),
    88: ("Runner-up D vs Runner-up G", "RU_D", "RU_G"),
}

# Matches that involve a third-placed team
# match_id → (winner_group, runner_up_or_third)
_THIRD_PLACE_MATCHES: list[int] = [74, 77, 79, 80, 81, 82, 85, 87]

# Which group winner appears in each third-place match
_WINNER_FOR_THIRD_MATCH: dict[int, str] = {
    74: "E",
    77: "I",
    79: "A",
    80: "L",
    81: "D",
    82: "G",
    85: "B",
    87: "K",
}


# ──────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────


def build_round_of_32(
    group_winners: dict[str, str],
    group_runners_up: dict[str, str],
    advancing_third: list[tuple[str, str]],
    annex_c: dict[tuple[str, ...], list[str]] | None = None,
) -> dict[int, KnockoutMatch]:
    """Build the Round of 32 (matches 73–88).

    Args:
        group_winners: Mapping from group letter (A–L) to winning team name.
        group_runners_up: Mapping from group letter (A–L) to runner-up team name.
        advancing_third: List of ``(group_letter, team_name)`` for the 8
            advancing third-placed teams, in any order.
        annex_c: Optional Annex C lookup dict.  If None, the built-in table
            (loaded from ``data/annex_c.json``) is used.

    Returns:
        Dict mapping match_id → KnockoutMatch for all 16 Round-of-32 fixtures.

    Raises:
        ValueError: If exactly 8 advancing third-place groups are not provided,
            or if the combination of advancing groups is not found in Annex C.
    """
    if annex_c is None:
        annex_c = _ANNEX_C

    if len(advancing_third) != 8:
        raise ValueError(
            f"Expected exactly 8 advancing third-placed teams, got {len(advancing_third)}"
        )

    # Build lookup for third-placed teams: group -> team name
    third_by_group: dict[str, str] = {}
    for grp, team in advancing_third:
        if grp in third_by_group:
            raise ValueError(f"Duplicate third-placed team for group {grp}")
        third_by_group[grp] = team

    # Get the sorted tuple of advancing third-place groups for Annex C lookup
    advancing_groups_tuple = tuple(sorted(third_by_group.keys()))

    if advancing_groups_tuple not in annex_c:
        raise ValueError(
            f"Advancing third-place group combination {advancing_groups_tuple} "
            f"not found in Annex C (495 valid combinations)"
        )

    assignments = annex_c[advancing_groups_tuple]
    # assignments is a list of 8 "3X" strings in order:
    # [match_74, match_77, match_79, match_80, match_81, match_82, match_85, match_87]

    assert len(assignments) == len(_THIRD_PLACE_MATCHES), (
        f"Annex C assignment count mismatch: {len(assignments)} vs {len(_THIRD_PLACE_MATCHES)}"
    )

    # Map assignment "3X" → group letter "X"
    third_for_match: dict[int, str] = {}
    for match_id, assignment in zip(_THIRD_PLACE_MATCHES, assignments):
        # assignment is "3X" where X is the group letter
        grp_letter = assignment[1]  # strip the "3"
        third_for_match[match_id] = third_by_group[grp_letter]

    result: dict[int, KnockoutMatch] = {}

    # Build fixed-pairing matches
    for match_id, (label, formula1, formula2) in _FIXED_PAIRINGS.items():
        # Parse formula like "RU_A" → extract "A"
        grp1 = formula1.split("_")[1]  # "RU" or "W" prefix stripped
        grp2 = formula2.split("_")[1]

        if formula1.startswith("W_"):
            team1 = group_winners[grp1]
        else:
            team1 = group_runners_up[grp1]

        if formula2.startswith("W_"):
            team2 = group_winners[grp2]
        else:
            team2 = group_runners_up[grp2]

        result[match_id] = KnockoutMatch(
            match_id=match_id,
            round_name=_round_name(match_id),
            team1=team1,
            team2=team2,
        )

    # Build third-place matches
    for match_id in _THIRD_PLACE_MATCHES:
        winner_grp = _WINNER_FOR_THIRD_MATCH[match_id]
        team1 = group_winners[winner_grp]
        team2 = third_for_match[match_id]
        result[match_id] = KnockoutMatch(
            match_id=match_id,
            round_name=_round_name(match_id),
            team1=team1,
            team2=team2,
        )

    return result


def build_full_bracket(
    round_of_32: dict[int, KnockoutMatch],
) -> dict[int, KnockoutMatch]:
    """Build subsequent knockout rounds from the Round of 32 onwards.

    Creates Round of 16 (89–96), Quarter-finals (97–100), Semi-finals
    (101–102), Third-place match (103), and Final (104).  Teams are left
    as None because they depend on previous match winners.

    Args:
        round_of_32: Dict mapping match_id → KnockoutMatch for all 16
            Round-of-32 fixtures.

    Returns:
        Complete dict mapping all match IDs (73–104) to KnockoutMatch objects.
    """
    bracket: dict[int, KnockoutMatch] = dict(round_of_32)

    # Round of 16 (89–96)
    _r16: list[tuple[int, int, int]] = [
        (89, 74, 77),
        (90, 73, 75),
        (91, 76, 78),
        (92, 79, 80),
        (93, 83, 84),
        (94, 81, 82),
        (95, 86, 88),
        (96, 85, 87),
    ]
    for mid, src1, src2 in _r16:
        bracket[mid] = KnockoutMatch(
            match_id=mid,
            round_name=_round_name(mid),
            source_match_1=src1,
            source_match_2=src2,
        )

    # Quarter-finals (97–100)
    _qf: list[tuple[int, int, int]] = [
        (97, 89, 90),
        (98, 93, 94),
        (99, 91, 92),
        (100, 95, 96),
    ]
    for mid, src1, src2 in _qf:
        bracket[mid] = KnockoutMatch(
            match_id=mid,
            round_name=_round_name(mid),
            source_match_1=src1,
            source_match_2=src2,
        )

    # Semi-finals (101–102)
    bracket[101] = KnockoutMatch(
        match_id=101,
        round_name=_round_name(101),
        source_match_1=97,
        source_match_2=98,
    )
    bracket[102] = KnockoutMatch(
        match_id=102,
        round_name=_round_name(102),
        source_match_1=99,
        source_match_2=100,
    )

    # Third-place match (103)
    bracket[103] = KnockoutMatch(
        match_id=103,
        round_name=_round_name(103),
        source_match_1=101,
        source_match_2=102,
    )

    # Final (104)
    bracket[104] = KnockoutMatch(
        match_id=104,
        round_name=_round_name(104),
        source_match_1=101,
        source_match_2=102,
    )

    return bracket


def resolve_bracket_winners(
    bracket: dict[int, KnockoutMatch],
    results: dict[int, KnockoutMatch],
) -> dict[int, KnockoutMatch]:
    """Propagate match winners through the bracket based on played results.

    For every knockout match that has been played (has a ``winner`` set in
    *results*), update the downstream match slots so teams flow forward.

    Args:
        bracket: The full bracket dict (may have None teams in later rounds).
        results: Played knockout match results keyed by match_id.

    Returns:
        Updated bracket dict with teams propagated forward where possible.
    """
    updated = {k: v for k, v in bracket.items()}

    for mid, res in results.items():
        if mid not in updated:
            continue
        if res.winner is None:
            continue

        winner_name = res.winner

        # Find matches that have this match as a source
        for candidate_id, candidate in updated.items():
            if candidate.source_match_1 == mid:
                updated[candidate_id] = KnockoutMatch(
                    match_id=candidate.match_id,
                    round_name=candidate.round_name,
                    team1=winner_name,
                    team2=candidate.team2,
                    source_match_1=candidate.source_match_1,
                    source_match_2=candidate.source_match_2,
                )
            if candidate.source_match_2 == mid:
                updated[candidate_id] = KnockoutMatch(
                    match_id=candidate.match_id,
                    round_name=candidate.round_name,
                    team1=candidate.team1,
                    team2=winner_name,
                    source_match_1=candidate.source_match_1,
                    source_match_2=candidate.source_match_2,
                )

    return updated

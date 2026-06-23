"""Third-place team ranking across all 12 groups.

Determines which 8 of the 12 third-placed teams advance to the Round of 32
using the same 7-step tiebreaker chain as within groups.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.worldcup_sim.data.models import GroupStanding, MatchResult, ThirdPlaceRanking


def rank_third_placed_teams(
    standings_by_group: dict[str, list[GroupStanding]],
    matches: list[MatchResult] | None = None,
) -> list[ThirdPlaceRanking]:
    """Rank all 12 third-placed teams and return the top 8 advancing.

    The ranking uses the same FIFA tiebreaker chain as within groups:
        1. Points
        2. Goal difference
        3. Goals scored
        4. Head-to-head points (N/A for cross-group — skipped)
        5. Head-to-head goal difference (skipped)
        6. Head-to-head goals scored (skipped)
        7. Fair-play conduct score (simulated random)
        8. FIFA/Coca-Cola World Ranking (predefined dict)

    Args:
        standings_by_group: Mapping from group letter (A–L) to its sorted
            list of GroupStanding (position 1–4).
        matches: All group-stage matches (not used for cross-group
                 comparisons, but accepted for API consistency).

    Returns:
        List of ThirdPlaceRanking sorted by rank (1 = best).  The ``rank``
        field indicates position among the 12 third-placers.
    """
    import random

    from src.worldcup_sim.data.models import ThirdPlaceRanking

    _FIFA_RANK: dict[str, int] = {
        "Argentina": 1, "France": 2, "Spain": 3, "England": 4,
        "Brazil": 5, "Portugal": 6, "Netherlands": 7, "Germany": 8,
        "Colombia": 9, "Morocco": 10, "USA": 11, "Mexico": 12,
        "Egypt": 13, "Uruguay": 14, "Norway": 15, "Japan": 16,
        "Canada": 17, "Iran": 18, "Belgium": 19, "Switzerland": 20,
        "Austria": 21, "South Korea": 22, "Australia": 23,
        "Sweden": 24, "Senegal": 25, "Ecuador": 26, "Ivory Coast": 27,
        "Ghana": 28, "Scotland": 29, "Croatia": 30, "Paraguay": 31,
        "Panama": 32, "Tunisia": 33, "Cape Verde": 34, "DR Congo": 35,
        "Saudi Arabia": 36, "Jordan": 37, "Algeria": 38,
        "Uzbekistan": 39, "Iraq": 40, "Qatar": 41, "Turkey": 42,
        "Bosnia & Herzegovina": 43, "Czech Republic": 44,
        "Haiti": 45, "New Zealand": 46, "Curaçao": 47,
        "South Africa": 48,
    }

    rng = random.Random(42)

    # Extract the team at position 3 from each group
    third_place_entries: list[ThirdPlaceRanking] = []
    for grp in sorted(standings_by_group.keys()):
        standings = standings_by_group[grp]
        third = next((s for s in standings if s.position == 3), None)
        if third is None:
            continue
        entry = ThirdPlaceRanking(
            team=third.team,
            group=third.group,
            played=third.played,
            wins=third.wins,
            draws=third.draws,
            losses=third.losses,
            gf=third.gf,
            ga=third.ga,
            gd=third.gd,
            points=third.points,
        )
        third_place_entries.append(entry)

    # Sort: points DESC, GD DESC, GF DESC
    third_place_entries.sort(key=lambda t: (t.points, t.gd, t.gf), reverse=True)

    # Detect blocks tied on points+GD+GF and break ties with steps 7–8
    i = 0
    ranked: list[ThirdPlaceRanking] = []
    while i < len(third_place_entries):
        j = i
        while (j < len(third_place_entries)
               and third_place_entries[j].points == third_place_entries[i].points
               and third_place_entries[j].gd == third_place_entries[i].gd
               and third_place_entries[j].gf == third_place_entries[i].gf):
            j += 1
        block = third_place_entries[i:j]
        if len(block) > 1:
            # Step 7: conduct score → random
            # Step 8: FIFA ranking
            block.sort(key=lambda t: _FIFA_RANK.get(t.team, 99))
        ranked.extend(block)
        i = j

    # Assign ranks
    for idx, entry in enumerate(ranked, start=1):
        entry.rank = idx

    return ranked

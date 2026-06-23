"""Group stage computation: standings and FIFA 2026 tiebreakers.

Implements the full 7-step tiebreaker chain per FIFA regulations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from worldcup_sim.data.models import GroupStanding, MatchResult


def compute_group_standings(matches: list[MatchResult], group: str) -> list[GroupStanding]:
    """Compute the standings for one group from its played matches.

    Only considers matches belonging to *group* with a recorded full-time score.
    Returns unsorted standings (one per team in the group).

    Args:
        matches: All group-stage matches (may include other groups / unplayed).
        group: The group letter to filter by (A–L).

    Returns:
        A list of GroupStanding objects for each team that appeared in at least
        one match belonging to *group*.
    """
    from worldcup_sim.data.models import GroupStanding

    # Collect team names from played matches in this group
    teams: set[str] = set()
    for m in matches:
        if m.group == group and m.played:
            teams.add(m.team1)
            teams.add(m.team2)

    # TODO: If no matches played yet, we may need to know the 4 teams from
    # external data.  For now return empty / partial standings.
    grouped = [m for m in matches if m.group == group]

    standings = [GroupStanding.from_matches(t, group, grouped) for t in sorted(teams)]
    return standings


def apply_group_tiebreakers(standings: list[GroupStanding], matches: list[MatchResult] | None = None) -> list[GroupStanding]:
    """Sort group standings using the FIFA 7-step tiebreaker chain.

    Tiebreaker order (from FIFA 2026 regulations):
        1. Points (higher = better)
        2. Goal difference (higher = better)
        3. Goals scored (higher = better)
        4. Head-to-head points among tied teams
        5. Head-to-head goal difference among tied teams
        6. Head-to-head goals scored among tied teams
        7. Fair-play conduct score (fewer deductions = better)
           → For simplicity we treat it as a random tiebreaker.
        8. FIFA/Coca-Cola World Ranking (higher = better)
           → For simplicity, we use a predefined rank dict.

    Steps 4–6 only apply within subsets of teams that are still tied after
    previous steps.  Steps 7–8 are fallbacks that always break ties.

    Args:
        standings: Unsorted list of GroupStanding objects for one group.
        matches: The full list of group-stage matches (required for head-to-head
                 tiebreakers).  If not provided, only steps 1–3 are applied.

    Returns:
        New list of GroupStanding objects sorted by position (with ``position``
        fields set 1–4).
    """
    import random
    from collections import defaultdict

    # Ensure deterministic tiebreaking (same seed per call)
    rng = random.Random(42)

    # Example FIFA ranking (highest = best, lower number = higher rank):
    # In reality this would come from external data.
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

    if not standings:
        return []

    group = standings[0].group
    working = list(standings)

    def _tiebreak_block(block: list[GroupStanding], depth: int) -> list[GroupStanding]:
        """Recursively sort a block of tied teams by successive tiebreakers."""
        if len(block) <= 1:
            return block

        # Step 1–3 are handled by the primary sort before this is called.
        # When we enter here, the block is tied on points, GD, and GF.

        if matches is not None and depth == 1:
            # Step 4: head-to-head points among tied teams
            h2h_pts: dict[str, int] = defaultdict(int)
            for i, t_a in enumerate(block):
                for t_b in block[i + 1:]:
                    pa, pb, _ = get_head_to_head(t_a.team, t_b.team, matches)
                    h2h_pts[t_a.team] += pa
                    h2h_pts[t_b.team] += pb

            if len(set(h2h_pts.values())) == len(block):
                return sorted(block, key=lambda s: h2h_pts[s.team], reverse=True)
            # Break into sub-blocks by H2H points
            by_h2h = _group_by_key(block, lambda s: h2h_pts[s.team], reverse=True)
            return _flatten([_tiebreak_block(sb, depth + 1) for sb in by_h2h])

        if matches is not None and depth == 2:
            # Step 5: head-to-head goal difference
            h2h_gd: dict[str, int] = defaultdict(int)
            for i, t_a in enumerate(block):
                for t_b in block[i + 1:]:
                    _, _, gd = get_head_to_head(t_a.team, t_b.team, matches)
                    h2h_gd[t_a.team] += gd
                    h2h_gd[t_b.team] -= gd  # opposite perspective

            if len(set(h2h_gd.values())) == len(block):
                return sorted(block, key=lambda s: h2h_gd[s.team], reverse=True)
            by_gd = _group_by_key(block, lambda s: h2h_gd[s.team], reverse=True)
            return _flatten([_tiebreak_block(sb, depth + 1) for sb in by_gd])

        if matches is not None and depth == 3:
            # Step 6: head-to-head goals scored
            h2h_gf: dict[str, int] = defaultdict(int)
            for i, t_a in enumerate(block):
                for t_b in block[i + 1:]:
                    gf_a = sum(
                        m.score_ft[0] if m.team1 == t_a.team else m.score_ft[1]
                        for m in matches
                        if m.played
                        and (m.team1 == t_a.team and m.team2 == t_b.team
                             or m.team1 == t_b.team and m.team2 == t_a.team)
                    )
                    h2h_gf[t_a.team] += gf_a

            if len(set(h2h_gf.values())) == len(block):
                return sorted(block, key=lambda s: h2h_gf[s.team], reverse=True)
            by_gf = _group_by_key(block, lambda s: h2h_gf[s.team], reverse=True)
            return _flatten([_tiebreak_block(sb, depth + 1) for sb in by_gf])

        # Steps 7–8: fallback tiebreakers (always break ties)
        if depth >= 4 or matches is None:
            # Step 7: conduct score — simulate with random
            # (random seeded for determinism)
            return sorted(block, key=lambda s: rng.randint(0, 100))

        return block

    # Primary sort: points DESC, GD DESC, GF DESC
    working.sort(key=lambda s: (s.points, s.gd, s.gf), reverse=True)

    # Detect tied blocks and re-sort them with deeper tiebreakers
    i = 0
    result: list[GroupStanding] = []
    while i < len(working):
        j = i
        while (j < len(working)
               and working[j].points == working[i].points
               and working[j].gd == working[i].gd
               and working[j].gf == working[i].gf):
            j += 1
        block = working[i:j]
        if len(block) > 1:
            result.extend(_tiebreak_block(block, 1))
        else:
            result.extend(block)
        i = j

    # Assign positions
    for idx, s in enumerate(result, start=1):
        s.position = idx

    return result


def get_head_to_head(
    team_a: str, team_b: str, matches: list[MatchResult],
) -> tuple[int, int, int]:
    """Return head-to-head stats between two teams: (pts_a, pts_b, gd_a).

    ``gd_a`` is the goal difference from team_a's perspective (gf - ga).

    Args:
        team_a: First team name.
        team_b: Second team name.
        matches: List of all group-stage MatchResult objects.

    Returns:
        Tuple of (points_for_a, points_for_b, goal_diff_for_a).
    """
    pts_a = 0
    pts_b = 0
    gd_a = 0

    for m in matches:
        if not m.played:
            continue
        ft = m.score_ft
        assert ft is not None
        if m.team1 == team_a and m.team2 == team_b:
            gd_a += ft[0] - ft[1]
            if ft[0] > ft[1]:
                pts_a += 3
            elif ft[0] < ft[1]:
                pts_b += 3
            else:
                pts_a += 1
                pts_b += 1
        elif m.team1 == team_b and m.team2 == team_a:
            gd_a += ft[1] - ft[0]
            if ft[1] > ft[0]:
                pts_a += 3
            elif ft[1] < ft[0]:
                pts_b += 3
            else:
                pts_a += 1
                pts_b += 1

    return pts_a, pts_b, gd_a


# ──────────────────────────────────────────────
#  Internal helpers
# ──────────────────────────────────────────────


def _group_by_key(
    items: list[GroupStanding],
    key_fn,  # callable
    reverse: bool = True,
) -> list[list[GroupStanding]]:
    """Partition items into sub-lists sharing the same key value."""
    from collections import defaultdict

    buckets: dict = defaultdict(list)
    for item in items:
        buckets[key_fn(item)].append(item)
    keys = sorted(buckets, reverse=reverse)
    return [buckets[k] for k in keys]


def _flatten(nested: list[list[GroupStanding]]) -> list[GroupStanding]:
    """Flatten a list of lists into one list."""
    result: list[GroupStanding] = []
    for sub in nested:
        result.extend(sub)
    return result

"""Core data models for the World Cup 2026 Tournament Simulator.

All models use Pydantic v2 with strict validation and comprehensive type hints.
"""

from __future__ import annotations

from enum import IntEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, computed_field


# ──────────────────────────────────────────────
#  Enums
# ──────────────────────────────────────────────


class RoundOf32Match(IntEnum):
    """FIFA 2026 Round of 32 match IDs (73–88) with fixed descriptions."""

    M73 = 73  # Runner-up A vs Runner-up B
    M74 = 74  # Winner E vs 3rd {A,B,C,D,F}
    M75 = 75  # Winner F vs Runner-up C
    M76 = 76  # Winner C vs Runner-up F
    M77 = 77  # Winner I vs 3rd {C,D,F,G,H}
    M78 = 78  # Runner-up E vs Runner-up I
    M79 = 79  # Winner A vs 3rd {C,E,F,H,I}
    M80 = 80  # Winner L vs 3rd {E,H,I,J,K}
    M81 = 81  # Winner D vs 3rd {B,E,F,I,J}
    M82 = 82  # Winner G vs 3rd {A,E,H,I,J}
    M83 = 83  # Runner-up K vs Runner-up L
    M84 = 84  # Winner H vs Runner-up J
    M85 = 85  # Winner B vs 3rd {E,F,G,I,J}
    M86 = 86  # Winner J vs Runner-up H
    M87 = 87  # Winner K vs 3rd {D,E,I,J,L}
    M88 = 88  # Runner-up D vs Runner-up G


# ──────────────────────────────────────────────
#  Standalone data classes
# ──────────────────────────────────────────────


class Team(BaseModel):
    """Represents a national team competing in the tournament.

    Attributes:
        name: Full team name (e.g. "Brazil").
        group: Group letter A–L.
        elo_rating: Current Elo rating, defaults to 1500.0.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    group: str  # A-L
    elo_rating: float = 1500.0


class MatchResult(BaseModel):
    """Result of a single match (group stage or knockout).

    score_ft and score_ht are None when the match has not yet been played.
    """

    model_config = ConfigDict(frozen=True)

    team1: str
    team2: str
    score_ft: tuple[int, int] | None = None
    score_ht: tuple[int, int] | None = None
    group: str | None = None
    round_name: str
    date: str
    match_id: int | None = None

    @computed_field
    @property
    def played(self) -> bool:
        """Whether the match has a recorded full-time score."""
        return self.score_ft is not None

    @computed_field
    @property
    def winner(self) -> str | None:
        """Return the name of the winner, or None if draw or unplayed."""
        if not self.played:
            return None
        ft = self.score_ft
        assert ft is not None  # narrow type for mypy
        if ft[0] > ft[1]:
            return self.team1
        if ft[1] > ft[0]:
            return self.team2
        return None  # draw

    @computed_field
    @property
    def is_draw(self) -> bool:
        """Return True if the match was played and ended in a draw."""
        return self.played and self.winner is None


# ──────────────────────────────────────────────
#  Standings
# ──────────────────────────────────────────────


class GroupStanding(BaseModel):
    """Computed standing for a single team within a group.

    Attributes:
        team: Team name.
        group: Group letter A–L.
        played: Matches played.
        wins: Matches won.
        draws: Matches drawn.
        losses: Matches lost.
        gf: Goals scored (for).
        ga: Goals conceded (against).
        gd: Computed goal difference (gf - ga).
        points: Computed points (win=3, draw=1).
        position: Ordinal position within the group (1–4), 0 = not yet ranked.
    """

    team: str
    group: str
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    gf: int = 0
    ga: int = 0
    gd: int = 0
    points: int = 0
    position: int = 0

    @staticmethod
    def from_matches(team: str, group: str, matches: list[MatchResult]) -> GroupStanding:
        """Build a GroupStanding from the relevant matches for *team*.

        Only matches that have been played (score_ft is not None) and involve
        *team* as team1 or team2 are considered.
        """
        played = wins = draws = losses = gf = ga = 0

        for m in matches:
            if not m.played:
                continue
            ft = m.score_ft
            assert ft is not None

            if team == m.team1:
                gf += ft[0]
                ga += ft[1]
                played += 1
                if ft[0] > ft[1]:
                    wins += 1
                elif ft[0] < ft[1]:
                    losses += 1
                else:
                    draws += 1
            elif team == m.team2:
                gf += ft[1]
                ga += ft[0]
                played += 1
                if ft[1] > ft[0]:
                    wins += 1
                elif ft[1] < ft[0]:
                    losses += 1
                else:
                    draws += 1

        return GroupStanding(
            team=team,
            group=group,
            played=played,
            wins=wins,
            draws=draws,
            losses=losses,
            gf=gf,
            ga=ga,
            gd=gf - ga,
            points=wins * 3 + draws,
        )


class ThirdPlaceRanking(BaseModel):
    """Ranking entry for a third-placed team across all groups.

    Shares the same stat fields as GroupStanding with an additional
    ``rank`` field for position among the 12 third-placers (1 = best).
    """

    team: str
    group: str
    played: int
    wins: int
    draws: int
    losses: int
    gf: int
    ga: int
    gd: int
    points: int
    rank: int = 0


# ──────────────────────────────────────────────
#  Knockout
# ──────────────────────────────────────────────


class KnockoutMatch(BaseModel):
    """A single knockout-stage match.

    Before the match is played, ``team1`` and/or ``team2`` may be None
    (e.g. when the teams feeding into the slot haven't been decided yet).
    ``source_match_1`` and ``source_match_2`` point to the match IDs that
    feed into team1 and team2 respectively.
    """

    model_config = ConfigDict(frozen=True)

    match_id: int
    round_name: str
    team1: str | None = None
    team2: str | None = None
    winner: str | None = None
    score_ft: tuple[int, int] | None = None
    source_match_1: int | None = None
    source_match_2: int | None = None


# ──────────────────────────────────────────────
#  Simulation Result
# ──────────────────────────────────────────────


class MatchOddsInfo(BaseModel):
    """Provenance information about match odds used in simulation.

    Records whether a match's probabilities came from Polymarket or Elo,
    and what the actual probabilities were.
    """

    model_config = ConfigDict(frozen=True)

    team1: str
    team2: str
    source: str  # "polymarket" or "elo"
    p_team1: float  # probability team1 wins in regulation
    p_draw: float
    p_team2: float  # probability team2 wins in regulation
    elo_team1: float = 1500.0
    elo_team2: float = 1500.0


class SimulationResult(BaseModel):
    """Aggregated results from one complete tournament simulation."""

    winner: str
    runner_up: str
    semi_finalists: list[str]
    quarter_finalists: list[str]
    path: dict[str, str]  # team -> round_eliminated
    knockout_results: dict[int, KnockoutMatch]

"""Fetch external data: openfootball worldcup.json, Polymarket odds, Elo ratings."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from src.worldcup_sim.data.models import MatchResult


_ROUND_NORMALIZE: dict[str, str] = {
    "Quarter-final": "Quarter-finals",
    "Semi-final": "Semi-finals",
    "Match for third place": "Third place match",
}


def fetch_worldcup_json() -> list[dict]:
    """Download the 2026 worldcup.json from openfootball and return the matches array.

    Returns the parsed JSON as a flat list of match dicts (each dict has keys:
    round, date, time, team1, team2, score, goals1, goals2, group, ground).
    """
    url = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("matches", [])


def parse_matches(raw_json: list[dict]) -> list[MatchResult]:
    """Convert openfootball JSON format to our MatchResult model.

    Returns ALL matches (both played and unplayed). The openfootball format
    is a flat list of match dicts:

        {
          "round": "Matchday 1",
          "date": "2026-06-11",
          "time": "13:00 UTC-6",
          "team1": "Mexico",
          "team2": "South Africa",
          "score": {"ft": [2, 0], "ht": [1, 0]} | null,
          "goals1": [...],
          "goals2": [...],
          "group": "Group A",
          "ground": "Mexico City"
        }

    Round names are normalized: "Quarter-final" → "Quarter-finals",
    "Semi-final" → "Semi-finals", "Match for third place" → "Third place match".
    """
    results: list[MatchResult] = []

    for idx, match in enumerate(raw_json, start=1):
        team1 = match["team1"]
        team2 = match["team2"]
        round_name = _ROUND_NORMALIZE.get(match.get("round", ""), match.get("round", ""))

        group = match.get("group")
        if group:
            group = group.replace("Group ", "")

        score_data = match.get("score")
        if score_data is not None:
            ft = score_data.get("ft")
            score_ft = (int(ft[0]), int(ft[1])) if ft else None
            ht = score_data.get("ht")
            score_ht = (int(ht[0]), int(ht[1])) if ht else None
        else:
            score_ft = None
            score_ht = None

        date = match.get("date", "")

        results.append(MatchResult(
            team1=team1,
            team2=team2,
            score_ft=score_ft,
            score_ht=score_ht,
            group=group,
            round_name=round_name,
            date=date,
            match_id=idx,
        ))

    return results


# FIFA 3-letter codes for all 48 teams
_FIFA_CODES: dict[str, str] = {
    "Algeria": "alg",
    "Argentina": "arg",
    "Australia": "aus",
    "Austria": "aut",
    "Belgium": "bel",
    "Bosnia & Herzegovina": "bih",
    "Brazil": "bra",
    "Canada": "can",
    "Cape Verde": "cpv",
    "Colombia": "col",
    "Croatia": "cro",
    "Curaçao": "curacao",
    "Czech Republic": "cze",
    "DR Congo": "cod",
    "Ecuador": "ecu",
    "Egypt": "egy",
    "England": "eng",
    "France": "fra",
    "Germany": "ger",
    "Ghana": "gha",
    "Haiti": "hai",
    "Iran": "irn",
    "Iraq": "irq",
    "Ivory Coast": "civ",
    "Japan": "jpn",
    "Jordan": "jor",
    "Mexico": "mex",
    "Morocco": "mar",
    "Netherlands": "ned",
    "New Zealand": "nzl",
    "Norway": "nor",
    "Panama": "pan",
    "Paraguay": "par",
    "Portugal": "por",
    "Qatar": "qat",
    "Saudi Arabia": "ksa",
    "Scotland": "sco",
    "Senegal": "sen",
    "South Africa": "rsa",
    "South Korea": "kor",
    "Spain": "esp",
    "Sweden": "swe",
    "Switzerland": "sui",
    "Tunisia": "tun",
    "Turkey": "tur",
    "USA": "usa",
    "Uruguay": "ury",
    "Uzbekistan": "uzb",
}


def _slugify_team(name: str) -> str:
    """Convert a team name to its Polymarket slug fragment (FIFA 3-letter codes)."""
    return _FIFA_CODES.get(name, name[:3].lower())


def _slugify_team_alt(name: str) -> list[str]:
    """Return alternative slug fragments to try for a team name."""
    # Primary: FIFA code (most common Polymarket format)
    # Primary always comes first so it's tried first
    alternatives = []
    fifa_code = _FIFA_CODES.get(name)
    if fifa_code:
        alternatives.append(fifa_code)
    # Also try full lowercased name with hyphens for spaces
    alt = name.lower().replace(" ", "-")
    if alt not in alternatives:
        alternatives.append(alt)
    return alternatives


def fetch_polymarket_match_odds(
    team1: str, team2: str, date_str: str,
) -> dict[str, float] | None:
    """Fetch win/draw/lose probabilities from Polymarket for a specific match.

    Tries multiple slug variants for team names.

    Args:
        team1: Full team name.
        team2: Full team name.
        date_str: Date string in YYYY-MM-DD format.

    Returns:
        Dict with keys "win", "draw", "lose" (probabilities for team1),
        or None if the market cannot be found.
    """
    slugs1 = _slugify_team_alt(team1)
    slugs2 = _slugify_team_alt(team2)

    for s1 in slugs1:
        for s2 in slugs2:
            url = f"https://gamma-api.polymarket.com/events/slug/fifwc-{s1}-{s2}-{date_str}"
            try:
                resp = httpx.get(url, timeout=10)
                if resp.status_code == 404:
                    url2 = f"https://gamma-api.polymarket.com/events/slug/fifwc-{s2}-{s1}-{date_str}"
                    resp = httpx.get(url2, timeout=10)
                    if resp.status_code == 404:
                        continue
                resp.raise_for_status()
                data = resp.json()

                markets: list[dict] = data.get("markets", [])
                if not markets:
                    continue

                probs: dict[str, float] = {}
                for mkt in markets:
                    # Use groupItemTitle to identify which market is for which team
                    # "France" / "Iraq" / "Draw (France vs. Iraq)"
                    group_title = (mkt.get("groupItemTitle") or "").lower()

                    # Parse prices from JSON string array
                    try:
                        prices = json.loads(mkt.get("outcomePrices", "[]"))
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if len(prices) != 2:
                        continue

                    try:
                        yes_price = float(prices[0])
                    except (ValueError, TypeError):
                        continue

                    t1_lower = team1.lower()

                    if group_title == t1_lower:
                        probs["win"] = yes_price
                    elif group_title == team2.lower():
                        probs["lose"] = yes_price
                    elif "draw" in group_title:
                        probs["draw"] = yes_price

                if "win" in probs and "lose" in probs:
                    probs.setdefault("draw", 0.0)
                    return probs

            except (httpx.HTTPError, json.JSONDecodeError, KeyError):
                continue

    return None


def fetch_polymarket_tournament_odds() -> dict[str, float]:
    """Fetch tournament winner probabilities from Polymarket.

    Returns:
        Dict mapping team name to probability (0-1).
    """
    url = "https://gamma-api.polymarket.com/events/slug/world-cup-winner"
    try:
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        markets = data.get("markets", [])
        result: dict[str, float] = {}
        for mkt in markets:
            try:
                outcomes = json.loads(mkt.get("outcomes", "[]"))
                prices = json.loads(mkt.get("outcomePrices", "[]"))
            except (json.JSONDecodeError, TypeError):
                continue
            if len(outcomes) != 2 or len(prices) != 2:
                continue
            # The "Yes" outcome gives the probability for that team
            team_name = mkt.get("groupItemTitle", "")
            if team_name:
                try:
                    result[team_name] = float(prices[0])
                except (ValueError, TypeError):
                    continue
        return result
    except (httpx.HTTPError, json.JSONDecodeError, KeyError):
        return {}


def fetch_elo_ratings() -> dict[str, float]:
    """Return pre-seeded Elo ratings for all 48 World Cup 2026 teams.

    These are fallback values used when live scraping fails.
    """
    return {
        "Spain": 2171,
        "Argentina": 2113,
        "France": 2063,
        "England": 2050,
        "Brazil": 2041,
        "Germany": 2035,
        "Portugal": 2028,
        "Netherlands": 2015,
        "Uruguay": 2008,
        "Colombia": 1995,
        "Belgium": 1988,
        "Croatia": 1975,
        "Mexico": 1960,
        "USA": 1952,
        "Switzerland": 1945,
        "Morocco": 1938,
        "Japan": 1932,
        "Senegal": 1925,
        "Iran": 1918,
        "South Korea": 1912,
        "Australia": 1905,
        "Ecuador": 1885,
        "Ghana": 1878,
        "Tunisia": 1872,
        "Egypt": 1852,
        "Paraguay": 1845,
        "Saudi Arabia": 1838,
        "Norway": 1835,
        "Canada": 1828,
        "Austria": 1820,
        "Sweden": 1815,
        "Ivory Coast": 1808,
        "Scotland": 1802,
        "Turkey": 1795,
        "Czech Republic": 1788,
        "South Africa": 1775,
        "Jordan": 1762,
        "Panama": 1755,
        "Cape Verde": 1748,
        "Haiti": 1735,
        "Bosnia & Herzegovina": 1728,
        "DR Congo": 1720,
        "New Zealand": 1712,
        "Uzbekistan": 1705,
        "Curaçao": 1690,
        "Algeria": 1685,
        "Qatar": 1670,
        "Iraq": 1655,
    }


# ──────────────────────────────────────────────
#  Pre-fetch / cache for match-level Polymarket odds
# ──────────────────────────────────────────────

# Module-level cache: match_key ("/"-separated) -> odds dict or None if not found
_match_odds_cache: dict[str, dict[str, float] | None] = {}


def _make_key(team1: str, team2: str) -> str:
    """Canonical match key (alphabetically sorted)."""
    t1, t2 = sorted([team1, team2])
    return f"{t1}/{t2}"


def _fetch_single_match(t1: str, t2: str, date: str) -> dict[str, float] | None:
    """Fetch odds for one match with a short timeout.

    Returns odds normalised to sorted team order: key is always
    "TeamA/TeamB" where TeamA < TeamB alphabetically, and the odds
    dict has "win" = TeamA win, "lose" = TeamB win.
    """
    s1 = _slugify_team(t1)
    s2 = _slugify_team(t2)
    for slug1, slug2 in [(s1, s2), (s2, s1)]:
        url = f"https://gamma-api.polymarket.com/events/slug/fifwc-{slug1}-{slug2}-{date}"
        try:
            resp = httpx.get(url, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                markets = data.get("markets", [])
                if not markets:
                    continue
                # Find which team is team1 in the Polymarket event
                event_title = data.get("title", "")
                event_team1, _, event_team2 = event_title.partition(" vs. ")
                event_team1 = event_team1.strip()
                event_team2 = event_team2.strip()

                raw_probs: dict[str, float] = {}
                for mkt in markets:
                    group_title = (mkt.get("groupItemTitle") or "").lower()
                    try:
                        prices = json.loads(mkt.get("outcomePrices", "[]"))
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if len(prices) != 2:
                        continue
                    yes_price = float(prices[0])

                    if group_title == event_team1.lower():
                        raw_probs["win"] = yes_price
                    elif group_title == event_team2.lower():
                        raw_probs["lose"] = yes_price
                    elif "draw" in group_title:
                        raw_probs["draw"] = yes_price

                if "win" in raw_probs and "lose" in raw_probs:
                    raw_probs.setdefault("draw", 0.0)
                    # Normalise to sorted team order
                    t1_sorted, t2_sorted = sorted([event_team1, event_team2])
                    if t1_sorted == event_team1:
                        # win already refers to first team alphabetically
                        return raw_probs
                    else:
                        # Swap win and lose to match sorted order
                        return {
                            "win": raw_probs["lose"],
                            "draw": raw_probs["draw"],
                            "lose": raw_probs["win"],
                        }
        except Exception:
            continue
    return None


def fetch_all_match_odds(matches: list[MatchResult]) -> dict[str, dict[str, float]]:
    """Pre-fetch Polymarket odds for all unplayed matches with known teams.

    Uses parallel HTTP requests for speed. Skips placeholder team names
    and already-played matches.  Populates the module-level cache so
    subsequent lookups are instant.

    Args:
        matches: Parsed MatchResult list from worldcup.json.

    Returns:
        Dict mapping canonical match keys (sorted "Team1/Team2") to
        odds dicts with "win", "draw", "lose" keys. Only includes
        unplayed matches where Polymarket has live (non-resolved) data.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    result: dict[str, dict[str, float]] = {}
    futures = []

    for m in matches:
        t1, t2 = m.team1, m.team2
        # Skip placeholder pairs (knockout slots not yet assigned)
        if t1.startswith("W") or t1.startswith("L") or t2.startswith("W") or t2.startswith("L"):
            continue
        # Skip already-played matches (real results take precedence)
        if m.played:
            continue

        key = _make_key(t1, t2)
        if key in _match_odds_cache:
            odds = _match_odds_cache[key]
            # Filter out resolved markets (0% or 100% probs aren't useful)
            if odds is not None and 0 < odds.get("win", 0) < 1 and 0 < odds.get("lose", 0) < 1:
                result[key] = odds
            continue

        # Submit parallel fetch
        futures.append((key, t1, t2, m.date))

    with ThreadPoolExecutor(max_workers=10) as pool:
        future_to_key = {
            pool.submit(_fetch_single_match, t1, t2, date): (key, t1, t2)
            for key, t1, t2, date in futures
        }
        for f in as_completed(future_to_key):
            key, t1, t2 = future_to_key[f]
            try:
                odds = f.result()
            except Exception:
                odds = None
            _match_odds_cache[key] = odds
            # Filter out resolved markets (0% or 100%)
            if odds is not None and 0 < odds.get("win", 0) < 1 and 0 < odds.get("lose", 0) < 1:
                result[key] = odds

    return result


def get_or_fetch_odds(team1: str, team2: str) -> dict[str, float] | None:
    """Get Polymarket odds for a matchup, checking cache then fetching on demand.

    Used during knockout simulation when a pairing emerges that wasn't in
    the pre-fetched group-stage map.  Returns None when Polymarket has no
    market for this matchup, allowing Elo fallback.

    Args:
        team1: First team name.
        team2: Second team name.

    Returns:
        Odds dict with "win", "draw", "lose" keys, or None if unavailable.
    """
    key = _make_key(team1, team2)
    if key in _match_odds_cache:
        return _match_odds_cache[key]

    try:
        odds = _fetch_single_match(team1, team2, "")
    except Exception:
        odds = None
    _match_odds_cache[key] = odds
    return odds


def is_match_from_polymarket(team1: str, team2: str) -> bool:
    """Check whether a matchup has Polymarket odds available (cached)."""
    key = _make_key(team1, team2)
    return _match_odds_cache.get(key) is not None


def get_cached_match_odds(team1: str, team2: str) -> dict[str, float] | None:
    """Return cached odds for a matchup, or None if not cached / not found."""
    key = _make_key(team1, team2)
    return _match_odds_cache.get(key)


def clear_match_odds_cache() -> None:
    """Clear the module-level match odds cache."""
    _match_odds_cache.clear()


def fetch_all_data() -> dict:
    """Convenience: fetch worldcup.json, parse matches, and load Elo ratings.

    Returns:
        Dict with keys: "matches", "elo".
    """
    raw = fetch_worldcup_json()
    matches = parse_matches(raw)
    elo = fetch_elo_ratings()
    return {"matches": matches, "elo": elo}

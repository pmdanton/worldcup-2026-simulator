"""Page 2: Knockout Bracket."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from worldcup_sim.app.components.bracket_viz import render_bracket
from worldcup_sim.app.state import get as get_state, set as set_state
from worldcup_sim.data.fetch import fetch_all_data
from worldcup_sim.data.models import GroupStanding, KnockoutMatch
from worldcup_sim.rules.bracket import build_full_bracket, build_round_of_32, resolve_bracket_winners
from worldcup_sim.rules.group_stage import apply_group_tiebreakers, compute_group_standings
from worldcup_sim.rules.third_place import rank_third_placed_teams


@st.cache_data(ttl=300)
def _fetch_data():
    return fetch_all_data()


@st.cache_data(ttl=3600)
def _load_teams() -> dict[str, list[str]]:
    from worldcup_sim.data._teams import GROUPS
    return GROUPS


def main():
    st.title("🏆 Knockout Bracket")

    with st.spinner("Loading data..."):
        try:
            data = _fetch_data()
            matches = data.get("matches", [])
            set_state("matches", matches)
            teams_by_group = _load_teams()
        except Exception as e:
            st.error(f"Failed to load data: {e}")
            return

    if not matches:
        st.warning("No match data available.")
        return

    groups = sorted(teams_by_group.keys())
    st.info("💡 Showing bracket **as if the group stage ended now** based on current results.")

    all_standings: dict[str, list[GroupStanding]] = {}
    for grp in groups:
        raw = compute_group_standings(matches, grp)
        group_team_names = set(teams_by_group[grp])
        existing_names = {s.team for s in raw}
        for tn in group_team_names - existing_names:
            raw.append(GroupStanding(team=tn, group=grp))
        sorted_s = apply_group_tiebreakers(raw, matches)
        all_standings[grp] = sorted_s

    group_winners: dict[str, str] = {}
    group_runners_up: dict[str, str] = {}
    for grp in groups:
        s = all_standings[grp]
        for entry in s:
            if entry.position == 1:
                group_winners[grp] = entry.team
            elif entry.position == 2:
                group_runners_up[grp] = entry.team

    third_rankings = rank_third_placed_teams(all_standings, matches)
    top_8_third = [(r.group, r.team) for r in third_rankings if r.rank <= 8]

    try:
        r32 = build_round_of_32(group_winners, group_runners_up, top_8_third)
        bracket = build_full_bracket(r32)

        ko_matches = [m for m in matches if m.match_id and m.match_id >= 73]
        if ko_matches:
            ko_results: dict[int, KnockoutMatch] = {}
            for m in ko_matches:
                if m.match_id and m.played:
                    ko_results[m.match_id] = KnockoutMatch(
                        match_id=m.match_id,
                        round_name=m.round_name,
                        team1=m.team1,
                        team2=m.team2,
                        winner=m.winner,
                        score_ft=m.score_ft,
                    )
            bracket = resolve_bracket_winners(bracket, ko_results)
    except ValueError as e:
        st.warning(f"Cannot build bracket yet: {e}")
        return

    bracket_data: dict[int, dict] = {}
    for mid, km in bracket.items():
        bracket_data[mid] = {
            "match_id": km.match_id,
            "round_name": km.round_name,
            "team1": km.team1,
            "team2": km.team2,
            "winner": km.winner,
            "score_ft": km.score_ft,
        }

    bracket_html = render_bracket(bracket_data)
    components.html(bracket_html, height=600, scrolling=True)

    st.subheader("Qualified Teams Summary")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Group Winners**")
        for grp in sorted(group_winners.keys()):
            st.write(f"*Group {grp}*: {group_winners[grp]}")
    with col2:
        st.markdown("**Runners-up**")
        for grp in sorted(group_runners_up.keys()):
            st.write(f"*Group {grp}*: {group_runners_up[grp]}")
    with col3:
        st.markdown("**Advancing 3rd Place**")
        for grp, team in top_8_third:
            st.write(f"*Group {grp}*: {team}")

    st.markdown("---")
    st.subheader("🔎 Team Zoom")

    all_team_names = sorted(t for teams in teams_by_group.values() for t in teams)
    zoom_team = st.selectbox("Select a team to inspect:", all_team_names, key="bracket_team_zoom")

    if zoom_team:
        team_group = None
        for grp, teams in teams_by_group.items():
            if zoom_team in teams:
                team_group = grp
                break

        team_elo = get_state("team_elo") or {}
        poly_odds = get_state("poly_winner_odds") or {}

        cz1, cz2, cz3 = st.columns(3)

        with cz1:
            st.markdown("**Group Standing**")
            if team_group:
                standings = all_standings.get(team_group, [])
                for s in standings:
                    if s.team == zoom_team:
                        pos_icon = {1: "🥇", 2: "🥈", 3: "🥉", 4: "❌"}
                        icon = pos_icon.get(s.position, "⚽")
                        st.write(f"{icon} Group {team_group} — **{s.position}{['th','st','nd','rd'][s.position if s.position <= 3 else 0]}**")
                        st.write(f"Points: {s.points} | GD: {s.gd:+d} | GF: {s.gf}")
                        advanced = (
                            s.position == 1
                            or s.position == 2
                            or (s.position == 3 and any(t == zoom_team for _, t in top_8_third))
                        )
                        if advanced:
                            st.success("✅ Qualified for knockout stage")
                        else:
                            st.error("❌ Eliminated")
                        break
                else:
                    st.info("No standing data available.")

        with cz2:
            st.markdown("**Ratings & Odds**")
            elo_val = team_elo.get(zoom_team)
            if elo_val is not None:
                st.metric("Elo Rating", f"{elo_val:.0f}")
            else:
                st.info("No Elo data")
            poly_val = poly_odds.get(zoom_team)
            if poly_val is not None:
                st.metric("Polymarket Win Odds", f"{poly_val * 100:.1f}%")
            else:
                st.info("No Polymarket odds")

        with cz3:
            st.markdown("**Bracket Path**")
            team_matches = []
            for mid in sorted(bracket.keys()):
                km = bracket[mid]
                if km.team1 == zoom_team or km.team2 == zoom_team:
                    opp = km.team2 if km.team1 == zoom_team else km.team1
                    team_matches.append((km.round_name, mid, opp))
            if team_matches:
                for round_name, mid, opp in team_matches:
                    st.write(f"*{round_name}*: vs {opp or 'TBD'} (M{mid})")
            else:
                st.info(f"{zoom_team} does not appear in any bracket slot.")

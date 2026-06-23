"""Page 1: Group Standings & Results."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from worldcup_sim.app.state import get, set
from worldcup_sim.data.fetch import fetch_all_data
from worldcup_sim.data.models import GroupStanding, Team
from worldcup_sim.rules.group_stage import apply_group_tiebreakers, compute_group_standings
from worldcup_sim.rules.third_place import rank_third_placed_teams


@st.cache_data(ttl=300)
def _fetch_data():
    return fetch_all_data()


@st.cache_data(ttl=3600)
def _load_teams() -> dict[str, list[str]]:
    from importlib.resources import files
    return json.loads(files("worldcup_sim.data").joinpath("teams.json").read_text())["groups"]


def _color_standings(val: pd.DataFrame) -> pd.DataFrame:
    n = len(val)
    styles = pd.DataFrame("", index=val.index, columns=val.columns)
    if n >= 1:
        styles.iloc[0] = "background-color: #1b4332"
    if n >= 2:
        styles.iloc[1] = "background-color: #1b4332"
    if n >= 3:
        styles.iloc[2] = "background-color: #3a3a1a"
    if n >= 4:
        styles.iloc[3] = "background-color: #4a1a1a"
    return styles


def main():
    st.title("⚽ Group Standings & Results")

    with st.spinner("Loading match data..."):
        try:
            data = _fetch_data()
            matches = data.get("matches", [])
            set("matches", matches)
        except Exception as e:
            st.error(f"Failed to load match data: {e}")
            return

    if not matches:
        st.warning("No match data available.")
        return

    teams_by_group = _load_teams()
    groups = sorted(teams_by_group.keys())

    st.subheader("Group Standings")

    all_standings: dict[str, list[GroupStanding]] = {}
    for grp in groups:
        raw = compute_group_standings(matches, grp)
        group_team_names = set(teams_by_group[grp])
        existing_names = {s.team for s in raw}
        for tn in group_team_names - existing_names:
            raw.append(GroupStanding(team=tn, group=grp))
        sorted_s = apply_group_tiebreakers(raw, matches)
        all_standings[grp] = sorted_s

    cols_per_row = 3
    groups_per_col = (len(groups) + cols_per_row - 1) // cols_per_row

    for row_idx in range(groups_per_col):
        cols = st.columns(cols_per_row)
        for col_idx in range(cols_per_row):
            group_idx = row_idx * cols_per_row + col_idx
            if group_idx >= len(groups):
                break
            grp = groups[group_idx]
            standings = all_standings[grp]
            with cols[col_idx]:
                with st.expander(f"**Group {grp}**", expanded=True):
                    data_rows = []
                    for s in standings:
                        data_rows.append({
                            "Pos": s.position,
                            "Team": s.team,
                            "Pld": s.played,
                            "W": s.wins,
                            "D": s.draws,
                            "L": s.losses,
                            "GF": s.gf,
                            "GA": s.ga,
                            "GD": s.gd,
                            "Pts": s.points,
                        })
                    if data_rows:
                        df = pd.DataFrame(data_rows)
                        styled = df.style.apply(_color_standings, axis=None)
                        st.dataframe(styled, use_container_width=True, hide_index=True)

    st.subheader("Third-Place Ranking")
    third_rankings = rank_third_placed_teams(all_standings, matches)
    if third_rankings:
        tp_data = []
        for r in third_rankings:
            tp_data.append({
                "Rank": r.rank,
                "Team": r.team,
                "Grp": r.group,
                "Pld": r.played,
                "W": r.wins,
                "D": r.draws,
                "L": r.losses,
                "GF": r.gf,
                "GA": r.ga,
                "GD": r.gd,
                "Pts": r.points,
                "Advances": "✅" if r.rank <= 8 else "❌",
            })
        tp_df = pd.DataFrame(tp_data)
        st.dataframe(tp_df, use_container_width=True, hide_index=True)

    st.subheader("Recent Results")
    played = [m for m in matches if m.played]
    played.sort(key=lambda m: m.date or "", reverse=True)

    if played:
        results_data = []
        for m in played[:10]:
            ft = m.score_ft
            results_data.append({
                "Date": m.date,
                "Group": m.group or "KO",
                "Home": m.team1,
                "Score": f"{ft[0]} - {ft[1]}" if ft else "vs",
                "Away": m.team2,
                "Round": m.round_name,
            })
        st.dataframe(pd.DataFrame(results_data), use_container_width=True, hide_index=True)
    else:
        st.info("No results yet.")

    st.subheader("Upcoming Fixtures")
    unplayed = [m for m in matches if not m.played]
    unplayed.sort(key=lambda m: m.date or "")

    if unplayed:
        upcoming_data = []
        for m in unplayed[:10]:
            upcoming_data.append({
                "Date": m.date,
                "Group": m.group or "KO",
                "Home": m.team1,
                "Away": m.team2,
                "Round": m.round_name,
            })
        st.dataframe(pd.DataFrame(upcoming_data), use_container_width=True, hide_index=True)
    else:
        st.info("No upcoming fixtures in data.")

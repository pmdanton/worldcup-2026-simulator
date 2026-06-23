"""Page 3: Tournament Simulation."""

from __future__ import annotations

from collections import Counter, defaultdict

import plotly.graph_objects as go
import streamlit as st
import pandas as pd

from worldcup_sim.app.components.charts import (
    stage_distribution_chart,
    team_path_chart,
    win_probability_chart,
)
from worldcup_sim.app.state import get as get_state, set as set_state
from worldcup_sim.data.fetch import (
    fetch_all_data,
    fetch_all_match_odds,
    fetch_elo_ratings,
    get_or_fetch_odds,
    is_match_from_polymarket,
)
from worldcup_sim.data.models import MatchOddsInfo
from worldcup_sim.sim.engine import run_simulation
from worldcup_sim.sim.predictor import get_match_probabilities


def main():
    st.title("🎲 Tournament Simulation")

    col1, col2, col3 = st.columns(3)
    with col1:
        num_sims = st.number_input("Simulations", min_value=100, max_value=100000, value=10000, step=1000)
    with col2:
        seed = st.number_input("Random Seed", min_value=0, max_value=999999, value=42, step=1)
    with col3:
        use_polymarket = st.checkbox("Use Polymarket odds", value=True)

    run_btn = st.button("▶ Run Simulation", type="primary", use_container_width=True)

    sim_results = get_state("sim_results")

    if run_btn:
        with st.spinner(f"Running {num_sims:,} simulations..."):
            try:
                data = fetch_all_data()
                matches = data.get("matches", [])
                set_state("matches", matches)
                elo = fetch_elo_ratings()
                set_state("team_elo", elo)

                # Pre-fetch Polymarket odds for all known match-ups
                poly_match_odds = None
                if use_polymarket:
                    with st.status("Fetching Polymarket odds...", expanded=False):
                        poly_match_odds = fetch_all_match_odds(matches)
                        set_state("poly_match_odds", poly_match_odds)
                        fetched = len(poly_match_odds)
                        st.write(f"Pre-fetched odds for {fetched} match-ups")

                results = run_simulation(
                    matches=matches,
                    team_elo=elo,
                    num_simulations=num_sims,
                    polymarket_odds_map=poly_match_odds if use_polymarket else None,
                    seed=seed,
                )
                set_state("sim_results", results)
                sim_results = results
                st.success(f"✅ Completed {num_sims:,} simulations!")
            except Exception as e:
                st.error(f"Simulation failed: {e}")
                return

    if sim_results is None:
        st.info("👆 Click **Run Simulation** to start a Monte Carlo tournament simulation.")
        return

    win_probs = sim_results.win_probs
    if not win_probs:
        st.warning("No simulation results to display.")
        return

    # 1. Win probability chart
    st.subheader("🏆 Win Probability — Top 20 Teams")
    fig = win_probability_chart(win_probs, top_n=20)
    st.plotly_chart(fig, use_container_width=True)

    # 2. Most likely champion card
    sorted_winners = sorted(win_probs.items(), key=lambda x: x[1], reverse=True)
    top_winner, top_win_prob = sorted_winners[0] if sorted_winners else ("N/A", 0)

    st.subheader("👑 Most Likely Champion")
    c1, c2 = st.columns([1, 3])
    with c1:
        st.metric("Champion", top_winner)
    with c2:
        st.metric("Win Probability", f"{top_win_prob * 100:.1f}%")

    # 3. Stage distribution table
    st.subheader("📊 Stage Distribution")
    df = sim_results.to_dataframe()
    display_cols = ["Team", "Win", "Final", "Semi", "QF", "R16", "R32", "Group"]
    display_df = df[display_cols].head(32).copy()
    for col in ["Win", "Final", "Semi", "QF", "R16", "R32", "Group"]:
        display_df[col] = (display_df[col] * 100).round(1).astype(str) + "%"
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # 4. Team deep dive
    st.markdown("---")
    st.subheader("🔎 Team Deep Dive")

    all_teams = sorted(win_probs.keys())
    zoom_team = st.selectbox("Select a team to zoom into:", all_teams, key="team_zoom_select", index=0)

    if zoom_team:
        col_left, col_right = st.columns(2)

        with col_left:
            st.metric("Tournament Win %", f"{sim_results.win_probs.get(zoom_team, 0)*100:.1f}%")
            st.metric("Final Appearance %", f"{sim_results.final_probs.get(zoom_team, 0)*100:.1f}%")
            st.metric("Semi-final %", f"{sim_results.semi_probs.get(zoom_team, 0)*100:.1f}%")
            st.metric("Group Exit %", f"{sim_results.group_exit_probs.get(zoom_team, 0)*100:.1f}%")

            stage_data = {
                zoom_team: {
                    "Group Stage": 1.0 - sim_results.r32_probs.get(zoom_team, 0),
                    "Round of 32": sim_results.r32_probs.get(zoom_team, 0) - sim_results.r16_probs.get(zoom_team, 0),
                    "Round of 16": sim_results.r16_probs.get(zoom_team, 0) - sim_results.qf_probs.get(zoom_team, 0),
                    "Quarter-finals": sim_results.qf_probs.get(zoom_team, 0) - sim_results.semi_probs.get(zoom_team, 0),
                    "Semi-finals": sim_results.semi_probs.get(zoom_team, 0) - sim_results.final_probs.get(zoom_team, 0),
                    "Runner-up": sim_results.final_probs.get(zoom_team, 0) - sim_results.win_probs.get(zoom_team, 0),
                    "Winner": sim_results.win_probs.get(zoom_team, 0),
                }
            }
            fig_zoom = team_path_chart(zoom_team, stage_data)
            if fig_zoom and len(fig_zoom.data) > 0:
                st.plotly_chart(fig_zoom, use_container_width=True)

        with col_right:
            st.subheader("💀 Who knocks them out?")
            eliminator_counts = Counter()
            for run in sim_results.all_runs:
                elim_round = run.elimination_round.get(zoom_team)
                if elim_round and elim_round not in ("Group Stage", "Winner"):
                    for mid, km in run.played_knockout_matches.items():
                        if km.winner and km.winner != zoom_team and (km.team1 == zoom_team or km.team2 == zoom_team):
                            eliminator_counts[km.winner] += 1
                            break
            if eliminator_counts:
                total = sum(eliminator_counts.values())
                elim_data = [(t, c / total) for t, c in eliminator_counts.most_common(8)]
                fig_elim = go.Figure(go.Bar(
                    x=[p * 100 for _, p in elim_data],
                    y=[t for t, _ in elim_data],
                    orientation="h",
                    marker_color="#e74c3c",
                    text=[f"{p * 100:.1f}%" for _, p in elim_data],
                    textposition="outside",
                ))
                fig_elim.update_layout(
                    height=250, margin=dict(l=0, r=0, t=0, b=0),
                    xaxis_title="Elimination probability",
                    yaxis=dict(autorange="reversed"),
                )
                st.plotly_chart(fig_elim, use_container_width=True, key="elim_chart")
            else:
                st.info("Not enough data to determine common eliminators.")

            st.subheader("📈 Stage Reach Probability")
            stages = [
                ("Round of 32", sim_results.r32_probs.get(zoom_team, 0)),
                ("Round of 16", sim_results.r16_probs.get(zoom_team, 0)),
                ("Quarter-finals", sim_results.qf_probs.get(zoom_team, 0)),
                ("Semi-finals", sim_results.semi_probs.get(zoom_team, 0)),
                ("Final", sim_results.final_probs.get(zoom_team, 0)),
                ("🏆 Champion", sim_results.win_probs.get(zoom_team, 0)),
            ]
            for stage_name, prob in stages:
                st.markdown(f"**{stage_name}**")
                st.progress(prob, text=f"{prob*100:.1f}%")

        st.markdown("---")
        st.subheader(f"🛣️ Most Common Opponents for {zoom_team}")

        round_opponents = defaultdict(Counter)
        for run in sim_results.all_runs:
            for mid, km in run.played_knockout_matches.items():
                if km.team1 == zoom_team or km.team2 == zoom_team:
                    opponent = km.team2 if km.team1 == zoom_team else km.team1
                    round_opponents[km.round_name][opponent] += 1

        if round_opponents:
            rows = []
            for round_name in ["Round of 32", "Round of 16", "Quarter-finals", "Semi-finals", "Final", "Third place match"]:
                if round_name in round_opponents:
                    counter = round_opponents[round_name]
                    total_opp = sum(counter.values())
                    top_3 = counter.most_common(3)
                    row = {
                        "Round": round_name,
                        "Most Common": f"{top_3[0][0]} ({top_3[0][1] / total_opp * 100:.0f}%)" if top_3 else "-",
                        "2nd": f"{top_3[1][0]} ({top_3[1][1] / total_opp * 100:.0f}%)" if len(top_3) > 1 else "-",
                        "3rd": f"{top_3[2][0]} ({top_3[2][1] / total_opp * 100:.0f}%)" if len(top_3) > 2 else "-",
                        "Total": total_opp,
                    }
                    rows.append(row)
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.info(f"{zoom_team} was eliminated in the group stage in most simulations.")
        else:
            st.info("No knockout opponents data available.")

        runs_won = sum(1 for r in sim_results.all_runs if r.winner == zoom_team)
        st.caption(f"🏆 Won the tournament in **{runs_won}** of {sim_results.num_sims} simulations ({runs_won / sim_results.num_sims * 100:.1f}%)")

    # 5. Match details query
    st.markdown("---")
    st.subheader("🔍 Match Details Query")
    st.caption("Look up a specific match-up to see odds source, probabilities, and simulation results.")

    match_query = st.text_input(
        "Enter a match (e.g. 'Germany vs France'):",
        placeholder="Team1 vs Team2",
        key="match_details_query",
    )

    if match_query and "vs" in match_query.lower():
        parts = match_query.split("vs", 1)
        t1 = parts[0].strip()
        t2 = parts[1].strip()

        if t1 and t2:
            elo = get_state("team_elo") or {}
            elo1 = elo.get(t1, 1500)
            elo2 = elo.get(t2, 1500)

            # Check odds source (use cached data, avoid API calls from UI)
            from worldcup_sim.data.fetch import get_cached_match_odds
            odds = get_cached_match_odds(t1, t2)
            if odds is None:
                # Per-match Polymarket odds typically don't exist for WC2026
                # so skip API call and go straight to Elo
                pass
            from_poly = odds is not None
            source = "Polymarket" if from_poly else "Elo"

            p_win1, p_draw, p_win2 = get_match_probabilities(t1, t2, elo, "", odds)

            c1, c2 = st.columns([1, 1])
            with c1:
                st.markdown(f"### {t1} vs {t2}")
                st.markdown(f"**Odds source:** {'📊 ' + source if from_poly else '📐 ' + source}")

                if from_poly:
                    st.markdown("✅ Using **Polymarket** market data")
                else:
                    st.markdown(f"ℹ️ Polymarket odds unavailable; using **Elo** formula")
                    st.markdown(f"Elo ratings: {t1} = **{elo1:.0f}**, {t2} = **{elo2:.0f}**")

            with c2:
                st.markdown("### Probabilities")
                st.markdown(f"- **{t1}** win: {p_win1 * 100:.1f}%")
                st.markdown(f"- **Draw**: {p_draw * 100:.1f}%")
                st.markdown(f"- **{t2}** win: {p_win2 * 100:.1f}%")

            st.markdown("---")
            st.markdown("### Simulation Stats")

            # Count match appearances in knockout simulations
            t1_wins_ko = 0
            t2_wins_ko = 0
            draw_count = 0
            matchup_sims = 0

            for run in sim_results.all_runs:
                for km in run.played_knockout_matches.values():
                    if (km.team1 == t1 and km.team2 == t2) or (km.team1 == t2 and km.team2 == t1):
                        matchup_sims += 1
                        if km.winner == t1:
                            t1_wins_ko += 1
                        elif km.winner == t2:
                            t2_wins_ko += 1
                        else:
                            draw_count += 1
                        break

            if matchup_sims > 0:
                ko_col1, ko_col2, ko_col3 = st.columns(3)
                with ko_col1:
                    st.metric(f"{t1} wins", f"{t1_wins_ko}", f"{t1_wins_ko / matchup_sims * 100:.1f}%")
                with ko_col2:
                    st.metric(f"{t2} wins", f"{t2_wins_ko}", f"{t2_wins_ko / matchup_sims * 100:.1f}%")
                with ko_col3:
                    st.metric("Sims with this fixture", f"{matchup_sims}")

                # Resolved by coin toss (draw)
                if draw_count > 0:
                    st.info(
                        f"⚠️ {draw_count} knockout match(es) went to penalties "
                        f"(resolved by coin toss — fair random choice)"
                    )
            else:
                st.info(
                    f"ℹ️ {t1} vs {t2} did not meet in the knockout stage in any of "
                    f"the {sim_results.num_sims:,} simulations."
                )

    # 6. Download CSV
    st.subheader("📥 Export Results")
    csv = df.to_csv(index=False)
    st.download_button(
        label="⬇ Download CSV",
        data=csv,
        file_name="worldcup_simulation_results.csv",
        mime="text/csv",
    )

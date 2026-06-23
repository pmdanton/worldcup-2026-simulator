"""Page 4: Odds Comparison — Polymarket vs Simulation."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from worldcup_sim.app.components.charts import odds_comparison_chart
from worldcup_sim.app.state import get as get_state, set as set_state
from worldcup_sim.data.fetch import (
    fetch_all_data,
    fetch_all_match_odds,
    fetch_elo_ratings,
    fetch_polymarket_tournament_odds,
)
from worldcup_sim.sim.engine import run_simulation


def main():
    st.title("📈 Odds Comparison")

    col1, col2 = st.columns(2)
    with col1:
        refresh_btn = st.button("🔄 Refresh Data", use_container_width=True)
    with col2:
        st.caption("Compares Polymarket odds vs two simulation variants")

    # Fetch Polymarket odds
    if refresh_btn or get_state("poly_winner_odds") is None:
        with st.spinner("Fetching Polymarket odds..."):
            try:
                odds = fetch_polymarket_tournament_odds()
                set_state("poly_winner_odds", odds)
                if odds:
                    st.success(f"Polymarket odds fetched! ({len(odds)} teams)")
                else:
                    st.warning("Polymarket returned no odds. Using Elo fallback.")
            except Exception as e:
                st.warning(f"Could not fetch Polymarket odds: {e}")
                odds = get_state("poly_winner_odds") or {}
    else:
        odds = get_state("poly_winner_odds") or {}

    # Run simulation (Poly+Elo)
    sim_results = get_state("sim_results")
    if refresh_btn or sim_results is None:
        with st.spinner("Running simulations (Poly+Elo)..."):
            try:
                data = fetch_all_data()
                matches = data.get("matches", [])
                elo = fetch_elo_ratings()
                poly_odds = fetch_all_match_odds(matches)
                set_state("poly_match_odds", poly_odds)
                results = run_simulation(
                    matches=matches,
                    team_elo=elo,
                    num_simulations=2000,
                    polymarket_odds_map=poly_odds,
                    seed=42,
                )
                set_state("sim_results", results)
                sim_results = results
            except Exception as e:
                st.error(f"Simulation failed: {e}")
                sim_results = None

    # Run Elo-only simulation (different seed for variance)
    elo_results = get_state("sim_results_elo")
    if refresh_btn or elo_results is None:
        with st.spinner("Running simulations (Elo only)..."):
            try:
                data = fetch_all_data()
                matches = data.get("matches", [])
                elo = fetch_elo_ratings()
                elo_results = run_simulation(
                    matches=matches,
                    team_elo=elo,
                    num_simulations=2000,
                    polymarket_odds_map=None,
                    seed=99,
                )
                set_state("sim_results_elo", elo_results)
            except Exception as e:
                st.error(f"Elo simulation failed: {e}")
                elo_results = None

    # Build comparison data
    st.subheader("Win Probability Comparison")

    all_teams: set[str] = set()
    if odds:
        all_teams |= set(odds.keys())
    if sim_results:
        all_teams |= set(sim_results.win_probs.keys())
    if elo_results:
        all_teams |= set(elo_results.win_probs.keys())

    if not all_teams:
        st.warning("No data to compare. Click Refresh to fetch data and run simulations.")
        return

    comp_rows = []
    for team in all_teams:
        p = odds.get(team, 0) * 100
        sp = sim_results.win_probs.get(team, 0) * 100 if sim_results else 0
        se = elo_results.win_probs.get(team, 0) * 100 if elo_results else 0
        diff = sp - p if p > 0 else 0
        comp_rows.append({
            "Team": team,
            "Polymarket %": f"{p:.1f}",
            "Sim (Poly+Elo) %": f"{sp:.1f}",
            "Sim (Elo) %": f"{se:.1f}",
            "Diff": f"{diff:+.1f}",
            "_p_raw": p,
            "_sp_raw": sp,
            "_se_raw": se,
            "_diff_raw": diff,
        })

    comp_rows.sort(key=lambda x: x["_sp_raw"], reverse=True)
    comp_df = pd.DataFrame(comp_rows)

    def _highlight_divergence(row):
        styles = [""] * len(row)
        if abs(row.get("_diff_raw", 0)) > 3:
            styles[4] = "background-color: #ffd700; color: #000; font-weight: 700"
        return styles

    display_cols = ["Team", "Polymarket %", "Sim (Poly+Elo) %", "Sim (Elo) %", "Diff"]
    styled = comp_df[display_cols].style.apply(_highlight_divergence, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True)
    st.caption("🟡 Yellow Diff cells indicate >3% divergence between Polymarket and simulation.")

    # Chart
    st.subheader("📊 Visual Comparison")
    chart_odds = {r["Team"]: r["_p_raw"] / 100 for r in comp_rows}
    chart_poly = {r["Team"]: r["_sp_raw"] / 100 for r in comp_rows}
    chart_elo = {r["Team"]: r["_se_raw"] / 100 for r in comp_rows}

    fig = odds_comparison_chart(chart_odds, chart_poly, chart_elo, top_n=15)
    st.plotly_chart(fig, use_container_width=True)

    # Key insights
    st.subheader("💡 Key Insights")
    big_divergence = [r for r in comp_rows if abs(r["_diff_raw"]) > 3]
    if big_divergence:
        for r in sorted(big_divergence, key=lambda x: abs(x["_diff_raw"]), reverse=True)[:5]:
            direction = "overvalued" if r["_diff_raw"] < 0 else "undervalued"
            st.markdown(f"- **{r['Team']}**: Market is **{direction}** by {abs(r['_diff_raw']):.1f}%")
    else:
        st.info("No significant divergences found (>3%).")

"""World Cup 2026 Tournament Simulator — Streamlit App Entry Point.

Phase 4: Multi-page dashboard with standings, bracket, simulation, and odds comparison.
"""

from __future__ import annotations

import streamlit as st

# Page config MUST be the first st command
st.set_page_config(
    page_title="World Cup 2026 Simulator",
    page_icon="⚽",
    layout="wide",
)

from src.worldcup_sim.app.state import get, init_state, set
from src.worldcup_sim.app.pages import bracket, odds, simulation, standings


def _apply_styling():
    st.markdown("""
    <style>
        /* Dark theme overrides */
        .match-card { background: #1a1a2e; border: 1px solid #333; border-radius: 8px; padding: 8px; margin: 4px 0; }
        .team-name { font-weight: 600; color: #e0e0e0; }
        .score { font-weight: 700; color: #ffd700; }
        .qualified { background: #1b4332 !important; }
        .eliminated { background: #4a1a1a !important; }
        .third-place { background: #3a3a1a !important; }

        /* Sidebar styling */
        [data-testid="stSidebar"] {
            background-color: #0d1117;
        }

        /* Data status indicators */
        .status-ok { color: #4ade80; }
        .status-stale { color: #fbbf24; }
        .status-error { color: #f87171; }

        /* Metric cards */
        [data-testid="stMetricValue"] {
            font-size: 1.5rem;
            font-weight: 700;
        }
    </style>
    """, unsafe_allow_html=True)


def _render_sidebar():
    """Render the sidebar with navigation and data status indicators."""
    with st.sidebar:
        st.markdown("# ⚽ WC 2026 Sim")
        st.markdown("---")

        page = st.radio(
            "Navigation",
            ["Standings & Results", "Knockout Bracket", "Tournament Simulation", "Odds Comparison"],
            index=0,
            label_visibility="collapsed",
        )

        st.markdown("---")

        # Data status indicators
        st.markdown("### Data Status")
        col1, col2 = st.columns(2)

        matches = get("matches")
        if matches is not None:
            played = sum(1 for m in matches if m.played)
            col1.metric("Matches", f"{played}/{len(matches)}")
        else:
            with col1:
                st.caption("Matches: not loaded")

        elo = get("team_elo")
        if elo is not None:
            col2.metric("Elo Ratings", f"{len(elo)} teams")
        else:
            with col2:
                st.caption("Elo: not loaded")

        sim = get("sim_results")
        if sim is not None:
            st.success(f"✅ Sims: {sim.num_sims:,} runs")
        else:
            st.info("No simulations")

        poly = get("poly_winner_odds")
        if poly is not None:
            st.success(f"✅ Polymarket: {len(poly)} markets")
        else:
            st.info("No odds data")

        st.markdown("---")

        # Auto-refresh toggle
        auto = st.toggle("Auto-refresh (30s)", value=get("auto_refresh") or False, key="auto_refresh_toggle")
        set("auto_refresh", auto)

        if auto:
            st.caption("🔄 Refreshing every 30 seconds")

    return page


def main():
    init_state()
    _apply_styling()
    page = _render_sidebar()

    # Auto-refresh
    if get("auto_refresh"):
        import time
        time.sleep(0.1)
        st.rerun()

    # Route to page
    if page == "Standings & Results":
        standings.main()
    elif page == "Knockout Bracket":
        bracket.main()
    elif page == "Tournament Simulation":
        simulation.main()
    elif page == "Odds Comparison":
        odds.main()


if __name__ == "__main__":
    main()

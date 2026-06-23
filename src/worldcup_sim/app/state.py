"""Shared Streamlit session state management."""

from __future__ import annotations

import streamlit as st


def init_state() -> None:
    """Initialize session state keys if not already present."""
    keys = [
        "matches", "team_elo", "sim_results", "sim_results_elo",
        "poly_winner_odds", "poly_match_odds", "auto_refresh",
    ]
    defaults = {
        "matches": None,
        "team_elo": None,
        "sim_results": None,
        "sim_results_elo": None,
        "poly_winner_odds": None,
        "poly_match_odds": None,
        "auto_refresh": False,
    }
    for k in keys:
        if k not in st.session_state:
            st.session_state[k] = defaults.get(k)


def get(key: str):
    """Get a value from session state."""
    return st.session_state.get(key)


def set(key: str, value) -> None:
    """Set a value in session state."""
    st.session_state[key] = value

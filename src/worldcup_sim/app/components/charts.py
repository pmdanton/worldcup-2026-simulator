"""Plotly chart functions for tournament visualization."""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd


def win_probability_chart(win_probs: dict[str, float], top_n: int = 20) -> go.Figure:
    """Horizontal bar chart of win probabilities for top N teams."""
    if not win_probs:
        return go.Figure()
    sorted_teams = sorted(win_probs.items(), key=lambda x: x[1], reverse=True)[:top_n]
    teams = [t for t, _ in sorted_teams]
    probs = [p * 100 for _, p in sorted_teams]

    fig = go.Figure(go.Bar(
        x=probs,
        y=teams,
        orientation="h",
        marker=dict(
            color=probs,
            colorscale="Viridis",
            showscale=False,
        ),
        text=[f"{p:.1f}%" for p in probs],
        textposition="outside",
    ))
    fig.update_layout(
        title="Tournament Win Probability",
        xaxis_title="Win Probability (%)",
        yaxis=dict(autorange="reversed"),
        height=max(400, top_n * 25),
        margin=dict(l=10, r=40, t=40, b=10),
    )
    return fig


def stage_distribution_chart(stage_probs: dict[str, dict[str, float]]) -> go.Figure:
    """Stacked horizontal bar chart showing stage exit distribution."""
    if not stage_probs:
        return go.Figure()

    stages = ["Group Stage", "Round of 32", "Round of 16", "Quarter-finals", "Semi-finals", "Fourth Place", "Runner-up", "Winner"]
    stage_colors = {
        "Group Stage": "#d32f2f",
        "Round of 32": "#f57c00",
        "Round of 16": "#fbc02d",
        "Quarter-finals": "#388e3c",
        "Semi-finals": "#1976d2",
        "Fourth Place": "#7b1fa2",
        "Runner-up": "#c0ca33",
        "Winner": "#ffd700",
    }

    data = []
    for team, stages_dict in stage_probs.items():
        row = {"Team": team}
        for s in stages:
            row[s] = stages_dict.get(s, 0) * 100
        data.append(row)

    df = pd.DataFrame(data)
    if df.empty:
        return go.Figure()

    # Sort by winner probability
    df = df.sort_values("Winner", ascending=False).head(30)

    fig = go.Figure()
    for stage in stages:
        if stage in df.columns and df[stage].sum() > 0:
            fig.add_trace(go.Bar(
                y=df["Team"],
                x=df[stage],
                name=stage,
                orientation="h",
                marker_color=stage_colors.get(stage, "#999"),
                text=[f"{v:.1f}%" if v > 1 else "" for v in df[stage]],
                textposition="inside",
            ))

    fig.update_layout(
        title="Stage Distribution by Team",
        barmode="stack",
        xaxis_title="Probability (%)",
        yaxis=dict(autorange="reversed"),
        height=max(500, len(df) * 22),
        margin=dict(l=10, r=40, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def odds_comparison_chart(
    polymarket: dict[str, float],
    sim_poly_elo: dict[str, float],
    sim_elo: dict[str, float],
    top_n: int = 15,
) -> go.Figure:
    """Grouped bar chart comparing Polymarket odds vs simulation probabilities."""
    all_teams = set(polymarket.keys()) | set(sim_poly_elo.keys()) | set(sim_elo.keys())
    if not all_teams:
        return go.Figure()

    data = []
    for team in all_teams:
        data.append({
            "Team": team,
            "Source": "Polymarket",
            "Probability": polymarket.get(team, 0) * 100,
        })
        data.append({
            "Team": team,
            "Source": "Sim (Poly+Elo)",
            "Probability": sim_poly_elo.get(team, 0) * 100,
        })
        data.append({
            "Team": team,
            "Source": "Sim (Elo only)",
            "Probability": sim_elo.get(team, 0) * 100,
        })

    df = pd.DataFrame(data)
    if df.empty:
        return go.Figure()

    # Show top N by max probability
    team_max = df.groupby("Team")["Probability"].max().sort_values(ascending=False).head(top_n)
    df = df[df["Team"].isin(team_max.index)]

    fig = px.bar(
        df,
        x="Team",
        y="Probability",
        color="Source",
        barmode="group",
        title="Odds Comparison: Polymarket vs Simulation",
        color_discrete_map={
            "Polymarket": "#1f77b4",
            "Sim (Poly+Elo)": "#ff7f0e",
            "Sim (Elo only)": "#2ca02c",
        },
    )
    fig.update_layout(
        xaxis_title="",
        yaxis_title="Win Probability (%)",
        height=500,
        margin=dict(l=10, r=40, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def team_path_chart(
    team: str,
    stage_probs: dict[str, dict[str, float]],
) -> go.Figure:
    """Pie/bar chart showing a single team's tournament path distribution."""
    if team not in stage_probs:
        return go.Figure()

    probs = stage_probs[team]
    stages = ["Group Stage", "Round of 32", "Round of 16", "Quarter-finals", "Semi-finals", "Fourth Place", "Runner-up", "Winner"]
    values = [probs.get(s, 0) * 100 for s in stages]
    labels = [s for s, v in zip(stages, values) if v > 0]
    values = [v for v in values if v > 0]

    if not labels:
        return go.Figure()

    colors = {
        "Group Stage": "#d32f2f", "Round of 32": "#f57c00",
        "Round of 16": "#fbc02d", "Quarter-finals": "#388e3c",
        "Semi-finals": "#1976d2", "Fourth Place": "#7b1fa2",
        "Runner-up": "#c0ca33", "Winner": "#ffd700",
    }

    fig = go.Figure(go.Bar(
        x=labels,
        y=values,
        marker_color=[colors.get(l, "#999") for l in labels],
        text=[f"{v:.1f}%" for v in values],
        textposition="outside",
    ))
    fig.update_layout(
        title=f"{team} — Tournament Path Probabilities",
        xaxis_title="",
        yaxis_title="Probability (%)",
        height=350,
        margin=dict(l=10, r=40, t=40, b=10),
    )
    return fig


def opponent_distribution_chart(team: str, opponents: list[dict]) -> go.Figure:
    """Grouped bar chart: most common opponents per knockout round.

    Args:
        team: The team to analyze.
        opponents: List of {round, opponent, prob} dicts.
    """
    df = pd.DataFrame(opponents)
    if df.empty:
        return go.Figure()
    fig = px.bar(
        df, x="round", y="prob", color="opponent", barmode="group",
        title=f"Most Common Opponents for {team}",
        labels={"round": "", "prob": "Probability", "opponent": ""},
    )
    fig.update_layout(
        height=400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_yaxes(tickformat=".0%")
    return fig


def team_stage_sankey(team: str, runs: list) -> go.Figure:
    """Sankey diagram showing a team's flow through the tournament.

    Args:
        team: The team to visualize.
        runs: List of SimulationRun objects with elimination_round and winner.
    """
    if not runs:
        return go.Figure()

    total = len(runs)
    cnt_r32 = cnt_r16 = cnt_qf = cnt_semi = cnt_final = cnt_win = 0

    for run in runs:
        elim = run.elimination_round.get(team)
        if elim is None:
            cnt_r32 += 1; cnt_r16 += 1; cnt_qf += 1; cnt_semi += 1; cnt_final += 1; cnt_win += 1
        elif elim == "Final":
            cnt_r32 += 1; cnt_r16 += 1; cnt_qf += 1; cnt_semi += 1; cnt_final += 1
        elif elim in ("Semi-finals", "Third place match"):
            cnt_r32 += 1; cnt_r16 += 1; cnt_qf += 1; cnt_semi += 1
        elif elim == "Quarter-finals":
            cnt_r32 += 1; cnt_r16 += 1; cnt_qf += 1
        elif elim == "Round of 16":
            cnt_r32 += 1; cnt_r16 += 1
        elif elim == "Round of 32":
            cnt_r32 += 1

    prob_r32 = cnt_r32 / total
    prob_r16 = cnt_r16 / total
    prob_qf = cnt_qf / total
    prob_semi = cnt_semi / total
    prob_final = cnt_final / total
    prob_win = cnt_win / total

    labels = [
        "Group Stage", "Round of 32", "Round of 16",
        "Quarter-finals", "Semi-finals", "Final",
        "Champion",
        "Elim (Group)", "Elim (R32)", "Elim (R16)",
        "Elim (QF)", "Elim (SF)", "Runner-up",
    ]

    # source, target, value
    links = [
        (0, 7, 1.0 - prob_r32),
        (0, 1, prob_r32),
        (1, 8, prob_r32 - prob_r16),
        (1, 2, prob_r16),
        (2, 9, prob_r16 - prob_qf),
        (2, 3, prob_qf),
        (3, 10, prob_qf - prob_semi),
        (3, 4, prob_semi),
        (4, 11, prob_semi - prob_final),
        (4, 5, prob_final),
        (5, 12, prob_final - prob_win),
        (5, 6, prob_win),
    ]

    source = [s for s, t, v in links if v > 0.001]
    target = [t for s, t, v in links if v > 0.001]
    values = [v * 100 for s, t, v in links if v > 0.001]

    node_colors = [
        "#d32f2f", "#f57c00", "#fbc02d", "#388e3c", "#1976d2",
        "#7b1fa2", "#ffd700",
        "#ffcdd2", "#ffe0b2", "#fff9c4", "#c8e6c9", "#bbdefb", "#e1bee7",
    ]

    fig = go.Figure(go.Sankey(
        node=dict(
            label=labels,
            color=node_colors,
            pad=15,
            thickness=20,
        ),
        link=dict(
            source=source,
            target=target,
            value=values,
        ),
    ))
    fig.update_layout(
        title=f"{team} — Tournament Flow",
        height=450,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    return fig


def key_matchups_chart(team: str, matchups: list[dict]) -> go.Figure:
    """Horizontal bar: teams most likely to knock this team out.

    Args:
        team: The team to analyze.
        matchups: List of {eliminator: str, prob: float} dicts.
    """
    df = pd.DataFrame(matchups)
    if df.empty:
        return go.Figure()
    fig = go.Figure(go.Bar(
        x=[p * 100 for p in df["prob"]],
        y=df["eliminator"],
        orientation="h",
        marker_color="#e74c3c",
        text=[f"{p * 100:.1f}%" for p in df["prob"]],
        textposition="outside",
    ))
    fig.update_layout(
        title=f"Who knocks {team} out?",
        xaxis_title="Elimination probability (%)",
        yaxis=dict(autorange="reversed"),
        height=300,
        margin=dict(l=0, r=40, t=40, b=0),
    )
    return fig


def group_position_chart(team: str, group_probs: dict[str, float]) -> go.Figure:
    """Donut chart: probability of finishing 1st/2nd/3rd/4th in group.

    Args:
        team: The team to analyze.
        group_probs: Dict mapping "1st"/"2nd"/"3rd"/"4th" to probability.
    """
    if not group_probs:
        return go.Figure()
    labels = list(group_probs.keys())
    values = [v * 100 for v in group_probs.values()]
    colors_map = {"1st": "#ffd700", "2nd": "#c0c0c0", "3rd": "#cd7f32", "4th": "#888888"}
    marker_colors = [colors_map.get(l, "#999") for l in labels]

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        marker_colors=marker_colors,
        hole=0.4,
        textinfo="label+percent",
    ))
    fig.update_layout(
        title=f"{team} — Group Finish",
        height=350,
    )
    return fig

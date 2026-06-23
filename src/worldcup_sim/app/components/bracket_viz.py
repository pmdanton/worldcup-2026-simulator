"""HTML bracket visualization component for the knockout stage."""

from __future__ import annotations


def render_bracket(matches: dict[int, dict]) -> str:
    """Render the knockout bracket as an HTML string for st.components.v1.html.

    Args:
        matches: Dict mapping match_id to match info with keys:
            match_id, round_name, team1, team2, winner, score_ft

    Returns:
        HTML string with inline CSS for bracket visualization.
    """
    if not matches:
        return "<p style='color:#888;text-align:center'>No bracket data available.</p>"

    # Group matches by round
    rounds_order = ["Round of 32", "Round of 16", "Quarter-finals", "Semi-finals", "Third place match", "Final"]
    by_round: dict[str, list[dict]] = {}
    for m in sorted(matches.values(), key=lambda x: x.get("match_id", 0)):
        rn = m.get("round_name", "Unknown")
        by_round.setdefault(rn, []).append(m)

    html = '<div class="bracket-container">'

    for round_name in rounds_order:
        if round_name not in by_round:
            continue
        round_matches = by_round[round_name]
        html += f'<div class="bracket-round"><h4>{round_name}</h4>'
        for m in round_matches:
            t1 = m.get("team1") or "TBD"
            t2 = m.get("team2") or "TBD"
            winner = m.get("winner")
            score = m.get("score_ft")

            score_str = ""
            if score:
                score_str = f'<span class="score">{score[0]} - {score[1]}</span>'

            t1_class = "qualified" if winner == t1 else ("eliminated" if winner and winner == t2 else "")
            t2_class = "qualified" if winner == t2 else ("eliminated" if winner and winner == t1 else "")

            html += f'''
            <div class="match-card">
                <div class="team-name {t1_class}">{_flag(t1)} {t1}</div>
                <div class="match-divider">vs {score_str}</div>
                <div class="team-name {t2_class}">{_flag(t2)} {t2}</div>
                <div class="match-id">M{m.get("match_id", "")}</div>
            </div>
            '''
        html += '</div>'

    html += '</div>'

    css = """
    <style>
    .bracket-container {
        display: flex;
        gap: 12px;
        overflow-x: auto;
        padding: 16px 0;
    }
    .bracket-round {
        background: #0d1117;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 12px;
        min-width: 180px;
        flex-shrink: 0;
    }
    .bracket-round h4 {
        margin: 0 0 12px 0;
        color: #58a6ff;
        font-size: 13px;
        text-align: center;
        border-bottom: 1px solid #30363d;
        padding-bottom: 8px;
    }
    .match-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 6px;
        padding: 8px;
        margin: 6px 0;
        font-size: 12px;
    }
    .team-name {
        padding: 3px 6px;
        border-radius: 3px;
        font-weight: 500;
        color: #c9d1d9;
    }
    .team-name.qualified {
        background: #1b4332 !important;
        color: #4ade80;
    }
    .team-name.eliminated {
        background: #4a1a1a !important;
        color: #f87171;
    }
    .match-divider {
        text-align: center;
        color: #8b949e;
        padding: 2px 0;
        font-size: 11px;
    }
    .score {
        font-weight: 700;
        color: #ffd700;
        font-size: 13px;
    }
    .match-id {
        text-align: right;
        color: #484f58;
        font-size: 10px;
        margin-top: 4px;
    }
    </style>
    """
    return css + html


def _flag(team_name: str) -> str:
    """Return a flag emoji for common teams."""
    flags = {
        "Argentina": "🇦🇷", "Brazil": "🇧🇷", "France": "🇫🇷", "Germany": "🇩🇪",
        "Spain": "🇪🇸", "England": "🏴", "Netherlands": "🇳🇱", "Portugal": "🇵🇹",
        "Italy": "🇮🇹", "Belgium": "🇧🇪", "Croatia": "🇭🇷", "Uruguay": "🇺🇾",
        "Morocco": "🇲🇦", "USA": "🇺🇸", "Mexico": "🇲🇽", "Japan": "🇯🇵",
        "South Korea": "🇰🇷", "Australia": "🇦🇺", "Canada": "🇨🇦",
        "Colombia": "🇨🇴", "Egypt": "🇪🇬", "Norway": "🇳🇴",
        "Switzerland": "🇨🇭", "Austria": "🇦🇹", "Sweden": "🇸🇪",
        "Senegal": "🇸🇳", "Ecuador": "🇪🇨", "Ghana": "🇬🇭",
        "Scotland": "🏴", "Paraguay": "🇵🇾", "Panama": "🇵🇦",
        "Tunisia": "🇹🇳", "Saudi Arabia": "🇸🇦", "Iran": "🇮🇷",
        "Ivory Coast": "🇨🇮", "Qatar": "🇶🇦", "Turkey": "🇹🇷",
        "Czech Republic": "🇨🇿", "South Africa": "🇿🇦",
        "Bosnia & Herzegovina": "🇧🇦", "Curaçao": "🇨🇼",
        "Haiti": "🇭🇹", "New Zealand": "🇳🇿", "Cape Verde": "🇨🇻",
        "DR Congo": "🇨🇩", "Uzbekistan": "🇺🇿", "Iraq": "🇮🇶",
        "Jordan": "🇯🇴", "Algeria": "🇩🇿",
    }
    return flags.get(team_name, "🏳️")

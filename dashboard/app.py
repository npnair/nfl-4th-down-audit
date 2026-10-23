"""4th Down Audit dashboard. Reads the dbt marts from Postgres."""

import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine

st.set_page_config(page_title="4th Down Audit", page_icon="🏈", layout="wide")

BLUE = "#2a78d6"     # categorical slot 1
ORANGE = "#eb6834"   # categorical slot 2
GRAY = "#8f8e8a"     # neutral
INK = "#52514e"      # secondary text
GRID = "rgba(127,127,127,0.18)"


# ---------- data ----------

def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        try:
            url = st.secrets["DATABASE_URL"]
        except Exception:
            url = None
    if not url:
        st.error("DATABASE_URL is not configured.")
        st.stop()
    # SQLAlchemy needs the explicit driver name.
    return url.replace("postgres://", "postgresql+psycopg2://", 1).replace(
        "postgresql://", "postgresql+psycopg2://", 1
    )


@st.cache_resource
def engine():
    return create_engine(database_url(), pool_pre_ping=True)


@st.cache_data(ttl=3600)
def query(sql: str, **params) -> pd.DataFrame:
    return pd.read_sql_query(sql, engine(), params=params or None)


def base_layout(fig, height=420, y_title=None, x_title=None, y_format=None):
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color=INK, size=13),
        hoverlabel=dict(font_size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    fig.update_xaxes(title=x_title, gridcolor=GRID, zeroline=False, showline=False)
    fig.update_yaxes(title=y_title, gridcolor=GRID, zeroline=False, tickformat=y_format)
    return fig


DECISION_LABELS = {"go": "Go for it", "field_goal": "Field goal", "punt": "Punt"}

status = query("select * from marts.mart_refresh_status").iloc[0]
league = query("select * from marts.mart_league_season order by season")
coach_season = query("select * from marts.mart_coach_season")
coach_career = query("select * from marts.mart_coach_career")

latest_season = int(status.latest_season)

# ---------- header ----------

st.title("4th Down Audit")
st.caption(
    "How much expected value NFL head coaches leave on the field with their 4th down decisions, 2010 to "
    f"{latest_season}. Data through week {int(status.latest_week)} of {latest_season}, "
    f"refreshed {pd.Timestamp(status.last_refreshed):%b %d, %Y}."
)

this = league[league.season == latest_season].iloc[0]
prior = league[league.season == latest_season - 1].iloc[0]
first = league.iloc[0]

c1, c2, c3 = st.columns(3)
c1.metric(
    f"Go rate when going is the better call ({latest_season})",
    f"{this.go_rate_when_should_go:.0%}",
    f"{(this.go_rate_when_should_go - first.go_rate_when_should_go) * 100:+.0f} pts since {int(first.season)}",
)
c2.metric(
    f"Expected points lost per team, per game ({latest_season})",
    f"{this.ep_lost_per_team_game:.2f}",
    f"{this.ep_lost_per_team_game - prior.ep_lost_per_team_game:+.2f} vs {latest_season - 1}",
    delta_color="inverse",
)
c3.metric(
    f"Graded 4th down decisions ({latest_season})",
    f"{int(this.decisions):,}",
)

tab_board, tab_scatter, tab_trend, tab_plays, tab_method = st.tabs(
    ["Coach leaderboard", "Aggression vs cost", "League trend", "Decision explorer", "Method"]
)

# ---------- leaderboard ----------

with tab_board:
    seasons = sorted(coach_season.season.unique(), reverse=True)
    f1, f2 = st.columns([1, 1])
    choice = f1.selectbox("Season", ["Career (2010 on)"] + [str(s) for s in seasons], index=1)
    if choice.startswith("Career"):
        min_games = f2.slider("Minimum games coached", 16, 150, 50, step=1)
        board = coach_career[coach_career.games >= min_games].copy()
        board["label"] = board.coach + " (" + board.first_season.astype(str) + "–" + board.last_season.astype(str) + ")"
    else:
        min_games = f2.slider("Minimum games coached", 1, 17, 5 if int(choice) == latest_season else 8)
        board = coach_season[(coach_season.season == int(choice)) & (coach_season.games >= min_games)].copy()
        board["label"] = board.coach + " (" + board.teams + ")"

    board = board.sort_values("ep_lost_vs_league", ascending=False)
    colors = [BLUE if v < 0 else ORANGE for v in board.ep_lost_vs_league]
    fig = go.Figure(
        go.Bar(
            x=board.ep_lost_vs_league,
            y=board.label,
            orientation="h",
            marker=dict(color=colors, cornerradius=4, line=dict(width=0)),
            customdata=board[["go_rate_when_should_go", "ep_lost_per_game", "games"]],
            hovertemplate=(
                "<b>%{y}</b><br>%{x:+.2f} expected points per game vs league<br>"
                "Lost %{customdata[1]:.2f} per game over %{customdata[2]} games<br>"
                "Went for it in %{customdata[0]:.0%} of should-go spots<extra></extra>"
            ),
        )
    )
    base_layout(fig, height=max(360, 22 * len(board) + 40), x_title="Expected points lost per game, relative to league average that season")
    fig.add_vline(x=0, line_color=GRAY, line_width=1)
    st.markdown(
        f"**<span style='color:{BLUE}'>■</span> Better than league average** &nbsp; "
        f"**<span style='color:{ORANGE}'>■</span> Worse than league average** &nbsp; "
        "Comparing to the same season's league average removes the effect of the whole league getting more aggressive over time.",
        unsafe_allow_html=True,
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Table view"):
        cols = {
            "label": "Coach",
            "games": "Games",
            "decisions": "Decisions",
            "go_rate_when_should_go": "Go rate when should go",
            "agreement_rate": "Agrees with model",
            "ep_lost_per_game": "EP lost per game",
            "ep_lost_vs_league": "vs league",
        }
        st.dataframe(
            board.sort_values("ep_lost_vs_league")[list(cols)].rename(columns=cols),
            hide_index=True,
            use_container_width=True,
            column_config={
                "Go rate when should go": st.column_config.NumberColumn(format="percent"),
                "Agrees with model": st.column_config.NumberColumn(format="percent"),
            },
        )

# ---------- scatter ----------

with tab_scatter:
    s1, s2 = st.columns([1, 1])
    season_pick = s1.selectbox("Season ", seasons, index=0)
    min_spots = s2.slider("Minimum should-go spots", 1, 40, 5 if season_pick == latest_season else 15)
    pts = coach_season[(coach_season.season == season_pick) & (coach_season.should_go_spots >= min_spots)]
    fig = go.Figure(
        go.Scatter(
            x=pts.go_rate_when_should_go,
            y=pts.ep_lost_per_game,
            mode="markers+text",
            text=pts.coach.str.split().str[-1],
            textposition="top center",
            textfont=dict(size=11, color=INK),
            marker=dict(size=11, color=BLUE, line=dict(width=2, color="white")),
            customdata=pts[["coach", "teams", "should_go_spots"]],
            hovertemplate=(
                "<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
                "Went for it in %{x:.0%} of %{customdata[2]} should-go spots<br>"
                "Lost %{y:.2f} expected points per game<extra></extra>"
            ),
        )
    )
    base_layout(
        fig,
        height=520,
        x_title="Went for it when going was the better call",
        y_title="Expected points lost per game",
        y_format=".1f",
    )
    fig.update_xaxes(tickformat=".0%")
    st.caption("Coaches toward the bottom right go for it when they should and lose the least. Hover for details.")
    st.plotly_chart(fig, use_container_width=True)

# ---------- league trend ----------

with tab_trend:
    st.subheader("Coaches are going for it more often")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=league.season, y=league.go_rate_when_clear_go, name="Clear go spots (go is better by 0.5+ EP)",
        mode="lines+markers", line=dict(color=BLUE, width=2), marker=dict(size=8),
        hovertemplate="%{x}: %{y:.0%}<extra>Clear go spots</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=league.season, y=league.go_rate_when_should_go, name="All should-go spots",
        mode="lines+markers", line=dict(color=ORANGE, width=2), marker=dict(size=8),
        hovertemplate="%{x}: %{y:.0%}<extra>All should-go spots</extra>",
    ))
    base_layout(fig, height=380, y_title="Share of spots where the team went for it", y_format=".0%")
    fig.update_layout(hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("...and leaving less on the field")
    fig = go.Figure(go.Bar(
        x=league.season, y=league.ep_lost_per_team_game,
        marker=dict(color=BLUE, cornerradius=4),
        hovertemplate="%{x}: %{y:.2f} expected points lost per team, per game<extra></extra>",
    ))
    base_layout(fig, height=320, y_title="Expected points lost per team, per game", y_format=".1f")
    st.plotly_chart(fig, use_container_width=True)
    if latest_season in league.season.values:
        st.caption(f"{latest_season} is a partial season.")

# ---------- play explorer ----------

with tab_plays:
    p1, p2, p3 = st.columns([1, 1.4, 1])
    season_p = p1.selectbox("Season  ", seasons, index=0)
    coaches = sorted(coach_season[coach_season.season == season_p].coach.unique())
    coach_p = p2.selectbox("Coach", coaches)
    only_misses = p3.toggle("Only decisions the model disagrees with", value=True)

    plays = query(
        """
        select week, defense as opponent, qtr, ydstogo, yardline_100, score_differential, decision, recommended,
               go_ep, fg_ep, punt_ep, ep_lost, conversion_rate, play_description
        from marts.fct_fourth_down_decisions
        where is_graded and season = %(season)s and offense_coach = %(coach)s
        order by ep_lost desc, week
        """,
        season=int(season_p),
        coach=coach_p,
    )
    if only_misses:
        plays = plays[plays.decision != plays.recommended]
    plays["situation"] = (
        "4th & " + plays.ydstogo.astype(str) + ", "
        + plays.yardline_100.map(lambda y: f"opp {y}" if y < 50 else ("midfield" if y == 50 else f"own {100 - y}"))
    )
    plays["decision"] = plays.decision.map(DECISION_LABELS)
    plays["recommended"] = plays.recommended.map(DECISION_LABELS)
    st.caption(f"{len(plays)} decisions. Sorted by expected points lost.")
    st.dataframe(
        plays[["week", "opponent", "qtr", "situation", "score_differential", "decision", "recommended",
               "ep_lost", "go_ep", "fg_ep", "punt_ep", "play_description"]].rename(columns={
            "week": "Week", "opponent": "Opp", "qtr": "Qtr", "situation": "Situation",
            "score_differential": "Score diff", "decision": "Chose", "recommended": "Model",
            "ep_lost": "EP lost", "go_ep": "Go EP", "fg_ep": "FG EP", "punt_ep": "Punt EP",
            "play_description": "Play",
        }),
        hide_index=True,
        use_container_width=True,
        height=520,
    )

# ---------- method ----------

with tab_method:
    st.markdown(
        """
### How a decision is graded

Every 4th down has three options. Each one is valued in **expected points (EP)**, the average number of
points a team scores from a given down, distance, and field position, using nflverse's EP values.

| Option | Value |
|---|---|
| **Go for it** | conversion rate × EP after a conversion + (1 − conversion rate) × EP after turning it over on downs |
| **Field goal** | make rate × (3 − EP the opponent gets from the kickoff) + miss rate × EP after a miss |
| **Punt** | average EP after real punts from that yard line (touchbacks, fair catches, returns, blocks) |

All rates are measured from **2010 onward** in this database:

* **Conversion rates** come from 3rd and 4th down runs and passes, split by distance, field zone, and era. Third
  downs are included because teams almost always go for it on 3rd down, which removes most of the selection bias in
  4th down attempts.
* **Field goal make rates** are split by era, since kickers have improved a lot (60 yard kicks went from about 36% to about 60%).
* Field goals are only considered from the opponent's 45 or closer, and punts only from the opponent's 30 or
  further back.

**EP lost** is the gap between the best option and the one the coach chose. It is zero when the coach made the best call.

### What is graded

Only competitive situations: win probability between 10% and 90%, and more than two minutes left in the half.
Expected points ignores the clock and the score, so late game and lopsided situations are left out rather than graded wrong.

### Known limits

* Expected points does not account for the score or time remaining inside the graded window.
* League average rates do not know about a specific team's offense, kicker, or weather.
* Fake punts and fake field goals count as going for it.

Data: [nflverse](https://github.com/nflverse) play by play. Pipeline: Python → Postgres → dbt → Streamlit,
refreshed weekly by GitHub Actions.
"""
    )

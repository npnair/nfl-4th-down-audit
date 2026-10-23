"""Load nflverse play-by-play data into Postgres (raw.pbp).

Each season is replaced as a unit (delete, then bulk COPY), so reruns are safe.

Usage:
    python ingest/load_pbp.py --current          # refresh the current season only (weekly job)
    python ingest/load_pbp.py --start 2010       # full backfill from 2010 through the current season
"""

import argparse
import io
import os
import sys
import time

import nflreadpy as nfl
import polars as pl
import psycopg2

# Only the columns the project uses. Keeps the database small enough for a free Postgres tier.
COLUMNS = {
    "game_id": "text",
    "play_id": "integer",
    "season": "integer",
    "week": "integer",
    "season_type": "text",
    "game_date": "date",
    "home_team": "text",
    "away_team": "text",
    "posteam": "text",
    "defteam": "text",
    "home_coach": "text",
    "away_coach": "text",
    "qtr": "integer",
    "game_seconds_remaining": "integer",
    "half_seconds_remaining": "integer",
    "down": "integer",
    "ydstogo": "integer",
    "yardline_100": "integer",
    "goal_to_go": "integer",
    "score_differential": "integer",
    "posteam_timeouts_remaining": "integer",
    "play_type": "text",
    "yards_gained": "integer",
    "first_down": "integer",
    "touchdown": "integer",
    "field_goal_result": "text",
    "kick_distance": "integer",
    "ep": "double precision",
    "epa": "double precision",
    "wp": "double precision",
    "vegas_wp": "double precision",
    "fourth_down_converted": "integer",
    "fourth_down_failed": "integer",
    "third_down_converted": "integer",
    "third_down_failed": "integer",
    "penalty": "integer",
    "success": "integer",
    "pass": "integer",
    "rush": "integer",
    "qb_kneel": "integer",
    "qb_spike": "integer",
    "two_point_attempt": "integer",
    "desc": "text",
}

TABLE = "raw.pbp"


def get_connection():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set.")
    return psycopg2.connect(url)


def ensure_table(conn):
    cols = ",\n    ".join(f'"{name}" {sqltype}' for name, sqltype in COLUMNS.items())
    with conn.cursor() as cur:
        cur.execute("create schema if not exists raw;")
        cur.execute(f"create table if not exists {TABLE} (\n    {cols}\n);")
        cur.execute(f"create index if not exists pbp_season_idx on {TABLE} (season);")
        cur.execute(
            """
            create table if not exists raw.load_log (
                season integer primary key,
                rows_loaded integer,
                max_week integer,
                loaded_at timestamptz default now()
            );
            """
        )
    conn.commit()


def fetch_season(season: int) -> pl.DataFrame:
    df = nfl.load_pbp([season]).select(list(COLUMNS))
    int_cols = [c for c, t in COLUMNS.items() if t == "integer"]
    # nflverse stores most numeric fields as floats; cast to ints for a cleaner schema.
    df = df.with_columns([pl.col(c).cast(pl.Int64, strict=False) for c in int_cols])
    # Play descriptions are the largest column and only the 4th down drilldown uses them.
    return df.with_columns(
        pl.when(pl.col("down") == 4).then(pl.col("desc")).otherwise(None).alias("desc")
    )


def load_season(conn, season: int) -> int:
    df = fetch_season(season)
    buf = io.StringIO()
    df.write_csv(buf, null_value="")
    buf.seek(0)
    col_list = ", ".join(f'"{c}"' for c in COLUMNS)
    with conn.cursor() as cur:
        cur.execute(f"delete from {TABLE} where season = %s;", (season,))
        cur.copy_expert(
            f"copy {TABLE} ({col_list}) from stdin with (format csv, header true, null '')",
            buf,
        )
        cur.execute(
            """
            insert into raw.load_log (season, rows_loaded, max_week, loaded_at)
            values (%s, %s, %s, now())
            on conflict (season) do update
              set rows_loaded = excluded.rows_loaded,
                  max_week = excluded.max_week,
                  loaded_at = excluded.loaded_at;
            """,
            (season, df.height, int(df["week"].max())),
        )
    conn.commit()
    return df.height


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--current", action="store_true", help="load only the current season")
    group.add_argument("--start", type=int, help="first season of a backfill (through the current season)")
    args = parser.parse_args()

    current = nfl.get_current_season()
    seasons = [current] if args.current else list(range(args.start, current + 1))

    conn = get_connection()
    ensure_table(conn)
    for season in seasons:
        t0 = time.time()
        rows = load_season(conn, season)
        print(f"{season}: {rows:,} plays loaded in {time.time() - t0:.1f}s")
    conn.close()


if __name__ == "__main__":
    main()

"""Load nflverse play-by-play data into the warehouse (raw.pbp).

Each season is replaced as a unit, so reruns are safe:
  * Postgres: delete the season, then bulk COPY it back in.
  * BigQuery: raw.pbp is partitioned by season, and each season is a load job that overwrites
    just its own partition (WRITE_TRUNCATE on raw.pbp$<season>). Load jobs are free and need no
    DML, so this also works in the BigQuery sandbox.

Usage:
    python ingest/load_pbp.py --current                          # refresh the current season (weekly job)
    python ingest/load_pbp.py --start 2010                       # full backfill through the current season
    python ingest/load_pbp.py --start 2010 --warehouse bigquery  # same, into BigQuery

The warehouse defaults to the WAREHOUSE environment variable, then to postgres.
Postgres reads DATABASE_URL. BigQuery reads GCP_PROJECT (and BQ_LOCATION, default US) and
authenticates with application default credentials.
"""

import argparse
import io
import os
import sys
import time
from datetime import datetime, timezone

import nflreadpy as nfl
import polars as pl

# Only the columns the project uses. Keeps the database small enough for a free tier.
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

POLARS_TYPES = {"text": pl.String, "integer": pl.Int64, "date": pl.Date, "double precision": pl.Float64}


def fetch_season(season: int) -> pl.DataFrame:
    df = nfl.load_pbp([season]).select(list(COLUMNS))
    # nflverse stores most numeric fields as floats and dates as text; give every column its real type
    # so Postgres and BigQuery end up with the same schema.
    df = df.with_columns(
        [
            pl.col(c).str.to_date() if t == "date" and df.schema[c] == pl.String
            else pl.col(c).cast(POLARS_TYPES[t], strict=False)
            for c, t in COLUMNS.items()
        ]
    )
    # Play descriptions are the largest column and only the 4th down drilldown uses them.
    return df.with_columns(
        pl.when(pl.col("down") == 4).then(pl.col("desc")).otherwise(None).alias("desc")
    )


class PostgresWriter:
    table = "raw.pbp"

    def __init__(self):
        import psycopg2

        url = os.environ.get("DATABASE_URL")
        if not url:
            sys.exit("DATABASE_URL is not set.")
        self.conn = psycopg2.connect(url)

    def ensure_tables(self):
        cols = ",\n    ".join(f'"{name}" {sqltype}' for name, sqltype in COLUMNS.items())
        with self.conn.cursor() as cur:
            cur.execute("create schema if not exists raw;")
            cur.execute(f"create table if not exists {self.table} (\n    {cols}\n);")
            cur.execute(f"create index if not exists pbp_season_idx on {self.table} (season);")
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
        self.conn.commit()

    def load_season(self, season: int, df: pl.DataFrame):
        buf = io.StringIO()
        df.write_csv(buf, null_value="")
        buf.seek(0)
        col_list = ", ".join(f'"{c}"' for c in COLUMNS)
        with self.conn.cursor() as cur:
            cur.execute(f"delete from {self.table} where season = %s;", (season,))
            cur.copy_expert(
                f"copy {self.table} ({col_list}) from stdin with (format csv, header true, null '')",
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
        self.conn.commit()

    def close(self):
        self.conn.close()


class BigQueryWriter:
    BQ_TYPES = {"text": "STRING", "integer": "INT64", "date": "DATE", "double precision": "FLOAT64"}
    # One partition per season. Integer range partitions cover start <= season < end.
    FIRST_SEASON, LAST_SEASON = 1999, 2100

    def __init__(self):
        from google.cloud import bigquery

        self.bq = bigquery
        project = os.environ.get("GCP_PROJECT")  # falls back to the credentials' project if unset
        self.location = os.environ.get("BQ_LOCATION", "US")
        self.client = bigquery.Client(project=project, location=self.location)
        self.dataset = f"{self.client.project}.raw"

    def _partitioned_table(self, name, schema):
        table = self.bq.Table(f"{self.dataset}.{name}", schema=schema)
        table.range_partitioning = self.bq.RangePartitioning(
            field="season",
            range_=self.bq.PartitionRange(start=self.FIRST_SEASON, end=self.LAST_SEASON, interval=1),
        )
        return self.client.create_table(table, exists_ok=True)

    def ensure_tables(self):
        dataset = self.bq.Dataset(self.dataset)
        dataset.location = self.location
        self.client.create_dataset(dataset, exists_ok=True)
        pbp_schema = [self.bq.SchemaField(c, self.BQ_TYPES[t]) for c, t in COLUMNS.items()]
        log_schema = [
            self.bq.SchemaField("season", "INT64"),
            self.bq.SchemaField("rows_loaded", "INT64"),
            self.bq.SchemaField("max_week", "INT64"),
            self.bq.SchemaField("loaded_at", "TIMESTAMP"),
        ]
        self._partitioned_table("pbp", pbp_schema)
        self._partitioned_table("load_log", log_schema)

    def _replace_partition(self, table: str, season: int, df: pl.DataFrame):
        # Parquet carries its own column types, which fetch_season already set to match the table.
        buf = io.BytesIO()
        df.write_parquet(buf)
        buf.seek(0)
        config = self.bq.LoadJobConfig(
            source_format=self.bq.SourceFormat.PARQUET,
            write_disposition=self.bq.WriteDisposition.WRITE_TRUNCATE,
        )
        # The $<season> decorator scopes WRITE_TRUNCATE to that one partition.
        job = self.client.load_table_from_file(buf, f"{self.dataset}.{table}${season}", job_config=config)
        job.result()

    def load_season(self, season: int, df: pl.DataFrame):
        self._replace_partition("pbp", season, df)
        log = pl.DataFrame(
            {
                "season": [season],
                "rows_loaded": [df.height],
                "max_week": [int(df["week"].max())],
                "loaded_at": [datetime.now(timezone.utc)],
            },
            schema={"season": pl.Int64, "rows_loaded": pl.Int64, "max_week": pl.Int64,
                    "loaded_at": pl.Datetime("us", "UTC")},
        )
        self._replace_partition("load_log", season, log)

    def close(self):
        self.client.close()


WRITERS = {"postgres": PostgresWriter, "bigquery": BigQueryWriter}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--current", action="store_true", help="load only the current season")
    group.add_argument("--start", type=int, help="first season of a backfill (through the current season)")
    parser.add_argument(
        "--warehouse",
        choices=sorted(WRITERS),
        default=os.environ.get("WAREHOUSE") or "postgres",
        help="where to load (default: $WAREHOUSE, else postgres)",
    )
    args = parser.parse_args()

    current = nfl.get_current_season()
    seasons = [current] if args.current else list(range(args.start, current + 1))

    writer = WRITERS[args.warehouse]()
    writer.ensure_tables()
    for season in seasons:
        t0 = time.time()
        df = fetch_season(season)
        writer.load_season(season, df)
        print(f"{season}: {df.height:,} plays loaded into {args.warehouse} in {time.time() - t0:.1f}s")
    writer.close()


if __name__ == "__main__":
    main()

# 4th Down Audit

How much expected value do NFL head coaches leave on the field with their 4th down decisions?

This project grades every 4th down since 2010 (about 65,000 decisions) by comparing what the coach did with the option that had the highest expected points. It refreshes automatically twice a week during the season, so the current year's leaderboard stays live.

**Live dashboard:** [nfl-4th-down-audit.streamlit.app](https://nfl-4th-down-audit.streamlit.app/)

## What it shows

* **Coach leaderboard:** expected points lost per game, compared with the league average that same season, for one season or a whole career.
* **Aggression vs cost:** how often each coach goes for it when going is the better call, against how much value they give up.
* **League trend:** coaches went for it in about 14% of "should go" spots in 2010 and about 37% in 2025, and the value left on the field fell by roughly 40% over the same period.
* **Decision explorer:** every graded 4th down for a coach and season, with the value of each option and the play description.

## Architecture

```mermaid
flowchart LR
    A[nflverse play by play] -->|Python ingest<br/>Parquet load jobs| B[(BigQuery<br/>raw.pbp<br/>partitioned by season)]
    B -->|dbt| C[staging]
    C -->|dbt| D[intermediate<br/>lookup tables]
    D -->|dbt| E[marts<br/>clustered fact table]
    E --> F[Streamlit dashboard]
    G[GitHub Actions<br/>Tue + Fri] -.-> A
```

| Layer | Tool | What it does |
|---|---|---|
| Ingest | Python (`nflreadpy`, `polars`, `google-cloud-bigquery`) | Loads each season from nflverse as Parquet into its own partition of `raw.pbp`, overwriting only that season. Reruns are safe. |
| Storage | Google BigQuery (PostgreSQL in Docker for local development) | About 790K plays from 2010 on, around 300 MB. |
| Transform | dbt (`dbt-bigquery`, `dbt-postgres`) | One project, two targets. Staging, five intermediate lookup tables, six marts, and 15 data tests. |
| Dashboard | Streamlit + Plotly | Reads only from the marts. Query results are cached for an hour. |
| Orchestration | GitHub Actions | Refreshes the current season and rebuilds the models every Tuesday and Friday. |

## BigQuery design

The pipeline started on Postgres and moved to BigQuery. The dbt project still runs on both, which is how the move was tested: every mart built on Postgres before and after the change was compared row for row and came out identical.

* **Partitioned raw table, no DML.** `raw.pbp` is integer range partitioned by `season`. Each refresh is a load job that writes to the `raw.pbp$2026` partition decorator with `WRITE_TRUNCATE`, which replaces that one season and leaves the others alone. Load jobs are free, idempotent, and need no `DELETE` or `MERGE`.
* **Staging as a table on BigQuery.** On Postgres, `stg_plays` is a view. On BigQuery a view is re-run by every model that reads it, so ten downstream models would each rescan the raw table. Materializing it as a table scans the raw data once per refresh.
* **Clustered fact table.** `fct_fourth_down_decisions` is clustered by `season` and `offense_coach`, the two filters the decision explorer uses, so those queries read only the blocks they need.
* **Cost guardrails.** The dbt profile sets `maximum_bytes_billed`, so a bad query fails instead of scanning more than 2 GB, and the dashboard caches each query for an hour.
* **Portable SQL.** Postgres-only syntax (`::` casts, `generate_series`, `FILTER`) became portable SQL or small macros in [`dbt/macros/cross_db.sql`](dbt/macros/cross_db.sql). One difference mattered for correctness: Postgres `GREATEST` skips nulls but BigQuery's returns null if any argument is null, which would have erased every 4th down where kicking is not an option. The `greatest_ignore_nulls` macro keeps the Postgres behavior on both.

**Cost.** A refresh processes roughly a gigabyte, so a season of twice weekly refreshes plus dashboard traffic stays far inside BigQuery's free monthly query allowance (1 TiB).

## How a decision is graded

Each 4th down has up to three options, all valued in **expected points (EP)**, using nflverse's EP values:

| Option | Expected points |
|---|---|
| Go for it | conversion rate × EP after converting + (1 − conversion rate) × EP after a turnover on downs |
| Field goal | make rate × (3 − EP the opponent gets from the kickoff) + miss rate × EP after a miss |
| Punt | average EP after real punts from that yard line |

All of the lookup tables are built in SQL from the data itself:

* `int_ep_curve`: EP of a fresh 1st down at every yard line, smoothed over five yards.
* `int_go_conversion_rates`: 3rd and 4th down conversion rates by distance, field zone, and era. Third downs are included because teams almost always go for it on 3rd down, which removes most of the selection bias in 4th down attempts.
* `int_go_success_value`: EP after a successful conversion.
* `int_fg_make_rates`: field goal make rate by distance and era (60 yard attempts went from about 36% in 2010 to 2014 to about 61% since 2024).
* `int_punt_values`: EP after punting from each yard line.

**EP lost** is the gap between the best option and the coach's choice. Only competitive situations are graded: win probability between 10% and 90% and more than two minutes left in the half, since expected points ignores the clock and score.

Career and season rankings use **EP lost per game relative to the league average that season**, so a coach from 2012 is not penalized for coaching before the league became more aggressive.

### Limits

* Expected points does not account for score or time inside the graded window.
* Rates are league averages and do not know about a specific offense, kicker, or weather.
* Fake punts and fake field goals count as going for it.

## Run it locally

Locally the whole stack runs on Postgres in Docker, with no cloud account needed.

```bash
docker compose up -d db
docker compose run --rm pipeline python ingest/load_pbp.py --start 2010
docker compose run --rm pipeline sh -c 'export $(python scripts/pg_env.py | xargs) && cd dbt && dbt build --profiles-dir .'
docker compose up dashboard        # http://localhost:8501
```

To run the pipeline against BigQuery from your machine instead:

```bash
gcloud auth application-default login
export WAREHOUSE=bigquery DBT_TARGET=bigquery GCP_PROJECT=your-project-id
python ingest/load_pbp.py --start 2010
cd dbt && dbt build --profiles-dir .
```

## Deploy (BigQuery)

1. **Create a Google Cloud project** and enable the BigQuery API. The BigQuery sandbox works for trying this out, but it deletes tables after 60 days, so for an always-on dashboard link a billing account (this project's usage stays inside the free tier) and set a budget alert.
2. **Create a service account** with the roles *BigQuery Data Editor* and *BigQuery Job User*, and download a JSON key.
3. **GitHub repo settings:**
   * Secret `GCP_SA_KEY`: the full JSON key.
   * Variables `WAREHOUSE` = `bigquery` and `GCP_PROJECT` = your project ID (optionally `BQ_LOCATION`, default `US`).
4. **Backfill:** run the **Weekly refresh** workflow manually with `backfill_start` set to `2010`.
5. **Streamlit Community Cloud:** add the key to the app's secrets as a table, and the dashboard switches to BigQuery automatically:

   ```toml
   [gcp_service_account]
   type = "service_account"
   project_id = "your-project-id"
   private_key_id = "..."
   private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
   client_email = "...@your-project-id.iam.gserviceaccount.com"
   client_id = "..."
   token_uri = "https://oauth2.googleapis.com/token"
   ```

The original Postgres deployment still works: leave `WAREHOUSE` unset (or `postgres`), set the `DATABASE_URL` secret to a Neon connection string, and give the Streamlit app the same `DATABASE_URL`.

## Project layout

```
ingest/load_pbp.py          nflverse loader (BigQuery or Postgres)
dbt/macros/cross_db.sql     helpers that render BigQuery or Postgres SQL
dbt/models/staging          cleaned plays with the offense's head coach
dbt/models/intermediate     expected points lookup tables
dbt/models/marts            decisions, coach season and career grades, league trend, team offense
dashboard/app.py            Streamlit app
.github/workflows           scheduled refresh
```

Data from [nflverse](https://github.com/nflverse).

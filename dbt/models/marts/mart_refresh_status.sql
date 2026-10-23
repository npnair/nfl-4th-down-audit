-- Shown on the dashboard so visitors can see how current the data is.
with load_log as (
    select * from {{ source('raw', 'load_log') }}
),

latest as (
    select max(season) as season from load_log
)

select
    max(l.season)                                                as latest_season,
    max(case when l.season = latest.season then l.max_week end)  as latest_week,
    max(l.loaded_at)                                             as last_refreshed
from load_log l
cross join latest

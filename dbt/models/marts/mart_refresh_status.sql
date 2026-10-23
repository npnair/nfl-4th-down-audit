-- Shown on the dashboard so visitors can see how current the data is.
select
    max(season)                                  as latest_season,
    max(max_week) filter (where season = (select max(season) from {{ source('raw', 'load_log') }})) as latest_week,
    max(loaded_at)                               as last_refreshed
from {{ source('raw', 'load_log') }}

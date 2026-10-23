-- Each coach should appear once per season. Written as a plain group by so it runs on any warehouse
-- (the old expression test concatenated an integer onto text, which BigQuery rejects).
select coach, season, count(*) as rows_found
from {{ ref('mart_coach_season') }}
group by coach, season
having count(*) > 1

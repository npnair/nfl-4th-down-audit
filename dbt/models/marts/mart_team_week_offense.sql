-- Weekly offensive efficiency for every team (EPA per play, success rate, pass rate).
select
    season,
    week,
    offense                                                        as team,
    max(offense_coach)                                             as coach,
    count(*)                                                       as plays,
    {{ round_to('avg(epa)', 3) }}                                  as epa_per_play,
    round(avg(case when is_success then 1.0 else 0 end), 3)        as success_rate,
    round(avg(case when is_pass then 1.0 else 0 end), 3)           as pass_rate
from {{ ref('stg_plays') }}
where (is_pass or is_rush)
  and epa is not null
group by season, week, offense

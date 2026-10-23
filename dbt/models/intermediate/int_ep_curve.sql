-- Expected points of a fresh first down at every yard line (1st and 10, or 1st and goal).
-- Smoothed over a five yard window. Used to value turnovers on downs, missed field goals,
-- and the kickoff that follows a score.
with first_downs as (
    select yardline_100, avg(ep) as ep, count(*) as n
    from {{ ref('stg_plays') }}
    where down = 1
      and (ydstogo = 10 or (is_goal_to_go and ydstogo = yardline_100))
      and half_seconds_remaining > {{ var('min_half_seconds') }}
      and ep is not null
    group by yardline_100
),

grid as (
    select generate_series(1, 99) as yardline_100
)

select
    g.yardline_100,
    sum(f.ep * f.n) / sum(f.n) as ep_first_down
from grid g
join first_downs f
  on f.yardline_100 between g.yardline_100 - 2 and g.yardline_100 + 2
group by g.yardline_100

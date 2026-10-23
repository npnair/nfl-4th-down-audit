-- Field goal make rate by line of scrimmage and era, smoothed over five yards.
-- Kick distance is the yard line plus 18 (10 yard end zone plus an 8 yard snap).
with attempts as (
    select
        era,
        yardline_100,
        sum(case when field_goal_result = 'made' then 1 else 0 end) as made,
        count(*) as attempts
    from {{ ref('stg_plays') }}
    where play_type = 'field_goal'
    group by 1, 2
),

grid as (
    select e.era, g.yardline_100
    from (select distinct era from attempts) e
    cross join generate_series(1, 50) as g(yardline_100)
)

select
    g.era,
    g.yardline_100,
    g.yardline_100 + 18 as kick_distance,
    sum(a.made)::numeric / sum(a.attempts) as make_rate,
    sum(a.attempts) as attempts
from grid g
join attempts a
  on a.era = g.era
 and a.yardline_100 between g.yardline_100 - 2 and g.yardline_100 + 2
group by 1, 2
having sum(a.attempts) >= 20

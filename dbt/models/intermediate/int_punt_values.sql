-- Expected points after punting from each yard line (negative: the opponent gets the ball).
-- Includes the real mix of touchbacks, fair catches, returns, and blocks. Smoothed over five yards.
with punts as (
    select yardline_100, avg(ep_after) as ep_after, count(*) as n
    from {{ ref('stg_plays') }}
    where play_type = 'punt'
      and ep_after is not null
      and not has_penalty
    group by 1
),

grid as (
    select yardline_100 from {{ int_series(1, 99, 'yardline_100') }}
)

select
    g.yardline_100,
    sum(p.ep_after * p.n) / sum(p.n) as punt_ep,
    sum(p.n) as punts
from grid g
join punts p
  on p.yardline_100 between g.yardline_100 - 2 and g.yardline_100 + 2
group by g.yardline_100
having sum(p.n) >= 20

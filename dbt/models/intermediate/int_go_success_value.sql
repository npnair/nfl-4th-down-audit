-- Expected points after a successful conversion, by distance needed and starting field position.
-- A touchdown is worth 7 minus the expected points the opponent gets back from the kickoff.
with kickoff as (
    select ep_first_down as kickoff_ep from {{ ref('int_ep_curve') }} where yardline_100 = 75
)

select
    {{ ydstogo_bucket('p.ydstogo') }}          as ydstogo_bucket,
    cast(least(ceil(p.yardline_100 / 5.0), 20) as {{ dbt.type_int() }}) as yardline_bucket,
    avg(case when p.is_touchdown then 7 - k.kickoff_ep else p.ep_after end) as success_ep,
    count(*) as conversions
from {{ ref('stg_plays') }} p
cross join kickoff k
where p.down in (3, 4)
  and p.play_type in ('run', 'pass')
  and p.is_converted
  and not p.has_penalty
  and p.ep_after is not null
  and p.half_seconds_remaining > {{ var('min_half_seconds') }}
group by 1, 2

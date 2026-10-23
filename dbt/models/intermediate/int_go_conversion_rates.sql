-- How often offenses convert on 3rd and 4th down, by distance, field zone, and era.
-- Third downs are included because almost every team goes for it on 3rd down, which removes
-- most of the selection bias in 4th down attempts.
select
    era,
    {{ ydstogo_bucket('ydstogo') }}  as ydstogo_bucket,
    {{ field_zone('yardline_100') }} as field_zone,
    avg(case when is_converted then 1.0 else 0.0 end) as conversion_rate,
    count(*) as attempts
from {{ ref('stg_plays') }}
where down in (3, 4)
  and play_type in ('run', 'pass')
  and not has_penalty
  and half_seconds_remaining > {{ var('min_half_seconds') }}
group by 1, 2, 3

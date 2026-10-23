-- One row per 4th down decision, with the expected points of each option and what the coach chose.
with plays as (
    select
        *,
        case
            when play_type in ('run', 'pass') then 'go'
            when play_type = 'field_goal' then 'field_goal'
            when play_type = 'punt' then 'punt'
        end as decision,
        {{ ydstogo_bucket('ydstogo') }}            as ydstogo_bucket,
        {{ field_zone('yardline_100') }}           as field_zone,
        least(ceil(yardline_100 / 5.0), 20)::int   as yardline_bucket,
        case when yardline_100 + 7 <= 20 then 80 else 100 - (yardline_100 + 7) end as fg_miss_opp_yardline
    from {{ ref('stg_plays') }}
    where down = 4
      and play_type in ('run', 'pass', 'field_goal', 'punt')
),

kickoff as (
    select ep_first_down as kickoff_ep from {{ ref('int_ep_curve') }} where yardline_100 = 75
),

success_fallback as (
    select ydstogo_bucket, sum(success_ep * conversions) / sum(conversions) as success_ep
    from {{ ref('int_go_success_value') }}
    group by 1
),

valued as (
    select
        p.*,
        cr.conversion_rate,
        fg.make_rate as fg_make_rate,
        cr.conversion_rate * coalesce(sv.success_ep, sf.success_ep)
            + (1 - cr.conversion_rate) * (-fail.ep_first_down)          as go_ep,
        case when p.yardline_100 <= {{ var('max_fg_yardline') }} then
            fg.make_rate * (3 - k.kickoff_ep)
            + (1 - fg.make_rate) * (-miss.ep_first_down)
        end                                                              as fg_ep,
        case when p.yardline_100 >= {{ var('min_punt_yardline') }} then pv.punt_ep end as punt_ep
    from plays p
    cross join kickoff k
    left join {{ ref('int_go_conversion_rates') }} cr
           on cr.era = p.era and cr.ydstogo_bucket = p.ydstogo_bucket and cr.field_zone = p.field_zone
    left join {{ ref('int_go_success_value') }} sv
           on sv.ydstogo_bucket = p.ydstogo_bucket and sv.yardline_bucket = p.yardline_bucket
    left join success_fallback sf
           on sf.ydstogo_bucket = p.ydstogo_bucket
    left join {{ ref('int_ep_curve') }} fail
           on fail.yardline_100 = 100 - p.yardline_100
    left join {{ ref('int_fg_make_rates') }} fg
           on fg.era = p.era and fg.yardline_100 = p.yardline_100
    left join {{ ref('int_ep_curve') }} miss
           on miss.yardline_100 = p.fg_miss_opp_yardline
    left join {{ ref('int_punt_values') }} pv
           on pv.yardline_100 = p.yardline_100
),

scored as (
    select
        *,
        greatest(go_ep, fg_ep, punt_ep) as best_ep,
        case decision
            when 'go' then go_ep
            when 'field_goal' then fg_ep
            when 'punt' then punt_ep
        end as chosen_ep
    from valued
)

select
    play_key,
    game_id,
    play_id,
    season,
    week,
    season_type,
    game_date,
    offense,
    defense,
    offense_coach,
    qtr,
    half_seconds_remaining,
    ydstogo,
    yardline_100,
    score_differential,
    wp,
    decision,
    case
        when best_ep = go_ep then 'go'
        when best_ep = fg_ep then 'field_goal'
        else 'punt'
    end                                                   as recommended,
    round(conversion_rate::numeric, 3)                    as conversion_rate,
    round(fg_make_rate::numeric, 3)                       as fg_make_rate,
    round(go_ep::numeric, 3)                              as go_ep,
    round(fg_ep::numeric, 3)                              as fg_ep,
    round(punt_ep::numeric, 3)                            as punt_ep,
    round(chosen_ep::numeric, 3)                          as chosen_ep,
    round((best_ep - chosen_ep)::numeric, 3)              as ep_lost,
    -- How much better going for it is than the best kick. Positive means "should go".
    round((go_ep - greatest(fg_ep, punt_ep))::numeric, 3) as go_advantage,
    round(ep_after::numeric, 3)                           as actual_ep_after,
    is_converted,
    play_description,
    wp between {{ var('min_wp') }} and {{ var('max_wp') }}
        and half_seconds_remaining > {{ var('min_half_seconds') }}
        and chosen_ep is not null                         as is_graded
from scored

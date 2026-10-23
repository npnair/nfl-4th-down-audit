-- Cleaned play-by-play: real snaps only, with the offense's head coach attached.
select
    game_id,
    play_id,
    game_id || '_' || cast(play_id as {{ dbt.type_string() }}) as play_key,
    season,
    week,
    season_type,
    game_date,
    {{ era('season') }}                        as era,
    posteam                                    as offense,
    defteam                                    as defense,
    case when posteam = home_team then home_coach else away_coach end as offense_coach,
    qtr,
    game_seconds_remaining,
    half_seconds_remaining,
    down,
    ydstogo,
    yardline_100,
    coalesce(goal_to_go, 0) = 1                as is_goal_to_go,
    score_differential,
    play_type,
    yards_gained,
    coalesce(touchdown, 0) = 1                 as is_touchdown,
    field_goal_result,
    ep,
    epa,
    ep + epa                                   as ep_after,
    wp,
    coalesce(third_down_converted, 0) = 1
        or coalesce(fourth_down_converted, 0) = 1 as is_converted,
    coalesce(penalty, 0) = 1                   as has_penalty,
    coalesce(success, 0) = 1                   as is_success,
    coalesce(pass, 0) = 1                      as is_pass,
    coalesce(rush, 0) = 1                      as is_rush,
    {{ adapter.quote('desc') }}                as play_description
from {{ source('raw', 'pbp') }}
where season_type in ('REG', 'POST')
  and posteam is not null
  and play_type is not null
  and coalesce(two_point_attempt, 0) = 0
  and coalesce(qb_kneel, 0) = 0
  and coalesce(qb_spike, 0) = 0

-- 4th down report card for each head coach and season (graded situations only).
with graded as (
    select * from {{ ref('fct_fourth_down_decisions') }} where is_graded
),

games as (
    select offense_coach, season, count(distinct game_id) as games
    from {{ ref('stg_plays') }}
    group by 1, 2
)

select
    g.offense_coach                                                          as coach,
    g.season,
    string_agg(distinct g.offense, '/')                                      as teams,
    gm.games,
    count(*)                                                                 as decisions,
    round(avg(case when g.decision = 'go' then 1.0 else 0 end), 3)           as go_rate,
    count(*) filter (where g.go_advantage > 0)                               as should_go_spots,
    round(avg(case when g.decision = 'go' then 1.0 else 0 end)
          filter (where g.go_advantage > 0), 3)                              as go_rate_when_should_go,
    count(*) filter (where g.go_advantage >= {{ var('clear_go_threshold') }})                              as clear_go_spots,
    round(avg(case when g.decision = 'go' then 1.0 else 0 end)
          filter (where g.go_advantage >= {{ var('clear_go_threshold') }}), 3)                             as go_rate_when_clear_go,
    round(avg(case when g.decision = g.recommended then 1.0 else 0 end), 3)  as agreement_rate,
    round(sum(g.ep_lost), 2)                                                 as ep_lost,
    round(sum(g.ep_lost) / nullif(gm.games, 0), 3)                           as ep_lost_per_game,
    -- Era adjustment: compare each coach with the league average that same season.
    round(sum(g.ep_lost) / nullif(gm.games, 0) - max(lg.ep_lost_per_team_game), 3) as ep_lost_vs_league,
    round(sum(g.ep_lost) filter (where g.decision <> 'go' and g.recommended = 'go'), 2) as ep_lost_too_timid,
    round(sum(g.ep_lost) filter (where g.decision = 'go' and g.recommended <> 'go'), 2) as ep_lost_too_aggressive
from graded g
left join games gm
  on gm.offense_coach = g.offense_coach and gm.season = g.season
left join {{ ref('mart_league_season') }} lg
  on lg.season = g.season
group by g.offense_coach, g.season, gm.games

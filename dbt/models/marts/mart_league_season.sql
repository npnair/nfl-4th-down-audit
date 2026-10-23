-- League wide trend: are coaches getting more aggressive, and how much is still left on the field?
with graded as (
    select
        *,
        case when decision = 'go' then 1.0 else 0 end as went_for_it,
        game_id || offense                            as team_game
    from {{ ref('fct_fourth_down_decisions') }}
    where is_graded
)

select
    season,
    count(*)                                                                   as decisions,
    round(avg(went_for_it), 3)                                                 as go_rate,
    round(avg(case when go_advantage > 0 then went_for_it end), 3)             as go_rate_when_should_go,
    round(avg(case when go_advantage >= {{ var('clear_go_threshold') }} then went_for_it end), 3) as go_rate_when_clear_go,
    round(avg(case when decision = recommended then 1.0 else 0 end), 3)        as agreement_rate,
    count(distinct team_game)                                                  as team_games,
    round(sum(ep_lost) / count(distinct team_game), 3)                         as ep_lost_per_team_game
from graded
group by season

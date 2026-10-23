-- Career 4th down grades for every head coach since 2010.
select
    coach,
    min(season)                                                    as first_season,
    max(season)                                                    as last_season,
    count(*)                                                       as seasons,
    sum(games)                                                     as games,
    sum(decisions)                                                 as decisions,
    round(sum(go_rate * decisions) / sum(decisions), 3)            as go_rate,
    sum(should_go_spots)                                           as should_go_spots,
    round(sum(go_rate_when_should_go * should_go_spots)
          / nullif(sum(should_go_spots), 0), 3)                    as go_rate_when_should_go,
    round(sum(agreement_rate * decisions) / sum(decisions), 3)     as agreement_rate,
    round(sum(ep_lost), 1)                                         as ep_lost,
    round(sum(ep_lost) / nullif(sum(games), 0), 3)                 as ep_lost_per_game,
    round(sum(ep_lost_vs_league * games) / nullif(sum(games), 0), 3) as ep_lost_vs_league
from {{ ref('mart_coach_season') }}
group by coach

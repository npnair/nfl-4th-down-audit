-- The chosen option can never beat the best option.
select play_key, ep_lost
from {{ ref('fct_fourth_down_decisions') }}
where ep_lost < 0

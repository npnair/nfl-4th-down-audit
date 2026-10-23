{% macro ydstogo_bucket(col) -%}
    case
        when {{ col }} <= 5 then {{ col }}::text
        when {{ col }} <= 7 then '6-7'
        when {{ col }} <= 10 then '8-10'
        else '11+'
    end
{%- endmacro %}

{% macro field_zone(col) -%}
    case
        when {{ col }} <= 10 then 'inside_10'
        when {{ col }} <= 40 then 'opp_11_40'
        else 'beyond_40'
    end
{%- endmacro %}

{% macro era(col) -%}
    case
        when {{ col }} <= 2014 then '2010-2014'
        when {{ col }} <= 2019 then '2015-2019'
        when {{ col }} <= 2023 then '2020-2023'
        else '2024+'
    end
{%- endmacro %}

-- Small helpers so the same models run on Postgres (local Docker) and BigQuery (production).
-- Each macro renders the native syntax for whichever warehouse dbt is targeting.

-- A column of consecutive integers, for building yard line grids.
-- Use in a from or join clause: `from {{ int_series(1, 99, 'yardline_100') }}`.
{% macro int_series(start, stop, alias) -%}
    {%- if target.type == 'bigquery' -%}
        unnest(generate_array({{ start }}, {{ stop }})) as {{ alias }}
    {%- else -%}
        generate_series({{ start }}, {{ stop }}) as {{ alias }}
    {%- endif -%}
{%- endmacro %}


-- Largest non-null value. Postgres GREATEST skips nulls, but BigQuery GREATEST returns null
-- if any argument is null, which would wipe out every 4th down where a kick is not an option.
{% macro greatest_ignore_nulls() -%}
    {%- if target.type == 'bigquery' -%}
        (select max(v) from unnest([{{ varargs | join(', ') }}]) as v)
    {%- else -%}
        greatest({{ varargs | join(', ') }})
    {%- endif -%}
{%- endmacro %}


-- Exact decimal division and rounding. Postgres needs numeric for round(x, n);
-- BigQuery rounds FLOAT64 directly, which keeps dashboard columns as plain floats.
{% macro as_decimal(expr) -%}
    {%- if target.type == 'bigquery' -%}
        cast({{ expr }} as float64)
    {%- else -%}
        ({{ expr }})::numeric
    {%- endif -%}
{%- endmacro %}

{% macro round_to(expr, digits) -%}
    round({{ as_decimal(expr) }}, {{ digits }})
{%- endmacro %}

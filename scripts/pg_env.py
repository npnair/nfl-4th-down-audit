"""Print PG* environment variables parsed from DATABASE_URL (dbt reads these).

GitHub Actions:  python scripts/pg_env.py >> "$GITHUB_ENV"
Local shell:     export $(python scripts/pg_env.py | xargs)
"""
import os
import sys
from urllib.parse import parse_qs, unquote, urlparse

url = os.environ.get("DATABASE_URL")
if not url:
    sys.exit("DATABASE_URL is not set.")
u = urlparse(url)
print(f"PGHOST={u.hostname}")
print(f"PGPORT={u.port or 5432}")
print(f"PGUSER={unquote(u.username or '')}")
print(f"PGPASSWORD={unquote(u.password or '')}")
print(f"PGDATABASE={u.path.lstrip('/')}")
print(f"PGSSLMODE={parse_qs(u.query).get('sslmode', ['prefer'])[0]}")

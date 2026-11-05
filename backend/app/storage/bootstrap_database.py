"""Controlled deployment job only; never imported from application startup."""

import os
import sys

from sqlalchemy import text

from app.database import engine


def main():
    password = os.environ["APP_DATABASE_PASSWORD"]
    with engine.begin() as connection:
        # Fixed role identity; quote the secret with the PostgreSQL driver, never a shell.
        from psycopg import sql

        cursor = connection.connection.cursor()
        exists = cursor.execute("SELECT 1 FROM pg_roles WHERE rolname='llm_harness_app'").fetchone()
        if not exists:
            cursor.execute("CREATE ROLE llm_harness_app LOGIN")
        cursor.execute(
            sql.SQL("ALTER ROLE llm_harness_app PASSWORD {}").format(sql.Literal(password))
        )
        connection.execute(text("GRANT CONNECT ON DATABASE llm_harness TO llm_harness_app"))
        connection.execute(text("GRANT USAGE ON SCHEMA public TO llm_harness_app"))
        if "--grant" in sys.argv:
            connection.execute(
                text("GRANT SELECT,INSERT,UPDATE ON ALL TABLES IN SCHEMA public TO llm_harness_app")
            )
            connection.execute(
                text("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO llm_harness_app")
            )


if __name__ == "__main__":
    main()

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine


def apply_powerbi_views(engine: Engine, project_root: Path) -> bool:
    """Install the Power BI views when the active database is PostgreSQL."""
    if engine.dialect.name != "postgresql":
        return False
    path = Path(project_root) / "database" / "002_powerbi_views.sql"
    sql = path.read_text(encoding="utf-8")
    with engine.begin() as connection:
        for statement in sql.split(";"):
            statement = statement.strip()
            if statement:
                connection.exec_driver_sql(statement)
    return True

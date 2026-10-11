import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", BASE_DIR / "dashboard.db"))
FLAGS_DIR = BASE_DIR.parent / "flags"


def migrate_team_table(connection):
    """Add registration fields while preserving existing teams and references."""
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(teams)")
    }
    if "members" not in columns:
        connection.execute("ALTER TABLE teams ADD COLUMN members TEXT")
        columns.add("members")
    if "university" not in columns:
        connection.execute("ALTER TABLE teams ADD COLUMN university TEXT")
        columns.add("university")

    table_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("teams",),
    ).fetchone()
    table_sql = table_row["sql"].upper(
    ) if table_row and table_row["sql"] else ""
    if "CREATED_AT" not in columns or "DEFAULT CURRENT_TIMESTAMP" not in table_sql:
        connection.execute(
            """
            CREATE TABLE teams_migrated (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                members TEXT,
                university TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        if "created_at" in columns:
            connection.execute(
                """
                INSERT INTO teams_migrated
                    (id, username, password_hash, score, members, university, created_at)
                SELECT id, username, password_hash, score, members, university,
                    COALESCE(created_at, CURRENT_TIMESTAMP)
                FROM teams
                """
            )
        else:
            connection.execute(
                """
                INSERT INTO teams_migrated
                    (id, username, password_hash, score, members, university, created_at)
                SELECT id, username, password_hash, score, members, university, CURRENT_TIMESTAMP
                FROM teams
                """
            )
        connection.execute("DROP TABLE teams")
        connection.execute("ALTER TABLE teams_migrated RENAME TO teams")

    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS teams_username_nocase "
        "ON teams(username COLLATE NOCASE)"
    )


def seed_database():
    """Create the control database and load flags from the repository files."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    flag_values = []
    for stage_id in range(1, 7):
        flag_file = FLAGS_DIR / f"stage{stage_id}.txt"
        flag_value = flag_file.read_text(encoding="utf-8").strip()
        if not flag_value:
            raise ValueError(f"Flag file is empty: {flag_file}")
        if not (flag_value.startswith("LB{") and flag_value.endswith("}")):
            raise ValueError(
                f"Flag must use the LB{{...}} format: {flag_file}")
        flag_values.append((stage_id, flag_value))

    username = os.getenv("TEAM_USERNAME", "redteam")
    password_hash = generate_password_hash(
        os.getenv("TEAM_PASSWORD", "audit2026"))
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("BEGIN")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                members TEXT,
                university TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS flags (
                stage_id INTEGER PRIMARY KEY,
                flag_value TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS solves (
                team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                stage_id INTEGER NOT NULL REFERENCES flags(stage_id) ON DELETE CASCADE,
                solved_at TEXT NOT NULL,
                PRIMARY KEY (team_id, stage_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS revealed_hints (
                team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                stage_id INTEGER NOT NULL REFERENCES flags(stage_id) ON DELETE CASCADE,
                hint_no INTEGER NOT NULL CHECK (hint_no IN (1, 2)),
                PRIMARY KEY (team_id, stage_id, hint_no)
            )
            """
        )
        migrate_team_table(connection)
        connection.executemany(
            "INSERT INTO flags (stage_id, flag_value) VALUES (?, ?) "
            "ON CONFLICT(stage_id) DO UPDATE SET flag_value = excluded.flag_value",
            flag_values,
        )
        existing_team = connection.execute(
            "SELECT id FROM teams WHERE username = ? COLLATE NOCASE",
            (username,),
        ).fetchone()
        if existing_team:
            connection.execute(
                "UPDATE teams SET password_hash = ? WHERE id = ?",
                (password_hash, existing_team["id"]),
            )
        else:
            connection.execute(
                "INSERT INTO teams (username, password_hash) VALUES (?, ?)",
                (username, password_hash),
            )
        connection.commit()
        connection.execute("PRAGMA foreign_keys = ON")


if __name__ == "__main__":
    seed_database()

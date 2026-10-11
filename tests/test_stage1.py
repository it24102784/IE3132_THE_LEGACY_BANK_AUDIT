import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dashboard.app as dashboard_app


class Stage1FlagTests(unittest.TestCase):
    def test_requires_full_flag_wrapper(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "dashboard.db"
            with patch.object(dashboard_app, "DATABASE_PATH", database_path):
                with sqlite3.connect(database_path) as connection:
                    connection.execute(
                        "CREATE TABLE flags (stage_id INTEGER PRIMARY KEY, flag_value TEXT NOT NULL)"
                    )
                    connection.execute(
                        "CREATE TABLE solves (team_id INTEGER, stage_id INTEGER, solved_at TEXT, "
                        "PRIMARY KEY (team_id, stage_id))"
                    )
                    connection.execute(
                        "CREATE TABLE teams (id INTEGER PRIMARY KEY, score INTEGER)"
                    )
                    connection.execute(
                        "INSERT INTO flags VALUES (1, ?)",
                        ("LB{f0rg0tt3n_s3rv3r_f0und}",),
                    )
                    connection.execute("INSERT INTO teams VALUES (1, 0)")
                connection.close()

                self.assertEqual(
                    dashboard_app.check_and_record_flag(
                        1, 1, "LB{f0rg0tt3n_s3rv3r_f0und}"
                    ),
                    (True, True),
                )
                self.assertEqual(
                    dashboard_app.check_and_record_flag(
                        1, 1, "f0rg0tt3n_s3rv3r_f0und"
                    ),
                    (False, False),
                )
                self.assertEqual(
                    dashboard_app.check_and_record_flag(
                        1, 1, "f0rg0tt3n_s3rv3r_wrong"
                    ),
                    (False, False),
                )

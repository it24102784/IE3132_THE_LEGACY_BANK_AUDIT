import sqlite3
import tempfile
import unittest
import re
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import dashboard.app as dashboard_app


class DashboardWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(
            self.temporary_directory.name) / "dashboard.db"
        self.database_patch = patch.object(
            dashboard_app, "DATABASE_PATH", self.database_path
        )
        self.database_patch.start()
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute(
                "CREATE TABLE teams (id INTEGER PRIMARY KEY, username TEXT, "
                "password_hash TEXT, score INTEGER NOT NULL DEFAULT 0)"
            )
            connection.execute(
                "CREATE TABLE flags (stage_id INTEGER PRIMARY KEY, flag_value TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE solves (team_id INTEGER NOT NULL, stage_id INTEGER NOT NULL, "
                "solved_at TEXT NOT NULL, PRIMARY KEY (team_id, stage_id))"
            )
            connection.execute(
                "CREATE TABLE revealed_hints (team_id INTEGER NOT NULL, stage_id INTEGER NOT NULL, "
                "hint_no INTEGER NOT NULL, PRIMARY KEY (team_id, stage_id, hint_no))"
            )
            connection.executemany(
                "INSERT INTO teams VALUES (?, ?, ?, ?)",
                [(1, "alpha", "hash", 0), (2, "bravo", "hash", 0)],
            )
            connection.executemany(
                "INSERT INTO flags VALUES (?, ?)",
                [(stage_id, f"LB{{stage_{stage_id}_flag}}")
                 for stage_id in range(1, 7)],
            )
        self.client = self.make_team_client(1)

    def tearDown(self):
        self.database_patch.stop()
        self.temporary_directory.cleanup()

    @staticmethod
    def make_team_client(team_id):
        client = dashboard_app.app.test_client()
        with client.session_transaction() as session:
            session["team_id"] = team_id
        return client

    def get_team_score(self, team_id):
        with closing(sqlite3.connect(self.database_path)) as connection:
            return connection.execute(
                "SELECT score FROM teams WHERE id = ?", (team_id,)
            ).fetchone()[0]

    def test_stages_unlock_in_order_and_award_points_once(self):
        response = self.client.get("/stage/2")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/stages")

        wrong_response = self.client.post(
            "/submit/1", data={"flag": "LB{wrong_flag}"}
        )
        self.assertEqual(wrong_response.location, "/stage/1")
        self.assertEqual(self.get_team_score(1), 0)

        correct_response = self.client.post(
            "/submit/1", data={"flag": "LB{stage_1_flag}"}
        )
        self.assertEqual(correct_response.location, "/stage/2")
        self.assertEqual(self.get_team_score(1), 100)

        self.client.post("/submit/1", data={"flag": "LB{stage_1_flag}"})
        self.assertEqual(self.get_team_score(1), 100)
        self.assertEqual(self.client.get("/stage/2").status_code, 200)

    def test_dashboard_session_cookie_is_app_specific(self):
        self.assertEqual(
            dashboard_app.app.config["SESSION_COOKIE_NAME"],
            "dashboard_session",
        )

    def test_dashboard_lists_all_unlocked_stages_and_advances_after_solve(self):
        first_dashboard = self.client.get("/stages")
        self.assertIn(b"The Forgotten Server", first_dashboard.data)
        self.assertNotIn(b"The Legacy Employee Portal", first_dashboard.data)
        self.assertNotIn(b"The Encoded Credentials", first_dashboard.data)

        self.client.post("/submit/1", data={"flag": "LB{stage_1_flag}"})
        next_dashboard = self.client.get("/stages")
        self.assertIn(b"The Forgotten Server", next_dashboard.data)
        self.assertIn(b"The Legacy Employee Portal", next_dashboard.data)
        self.assertNotIn(b"The Encoded Credentials", next_dashboard.data)
        self.assertIn(b"Solved &#10003;", next_dashboard.data)

        locked_stage = self.client.get("/stage/3")
        self.assertEqual(locked_stage.status_code, 302)
        self.assertEqual(locked_stage.location, "/stages")
        redirected = self.client.get("/stage/3", follow_redirects=True)
        self.assertIn(b"Complete the previous stage first.", redirected.data)

    def test_solved_stage_keeps_briefing_and_hints_without_submission_form(self):
        self.client.post("/submit/1", data={"flag": "LB{stage_1_flag}"})
        self.client.post("/hint/1/1")

        solved_stage = self.client.get("/stage/1")
        self.assertEqual(solved_stage.status_code, 200)
        self.assertIn(b"Solved", solved_stage.data)
        self.assertIn(b"Briefing", solved_stage.data)
        self.assertIn(b"Hint 1:", solved_stage.data)
        self.assertNotIn(b"Flag submission", solved_stage.data)
        self.assertNotIn(b'name="flag"', solved_stage.data)

    def test_all_solved_stages_remain_visible_with_audit_complete_state(self):
        for stage_id in range(1, 7):
            if stage_id == 4:
                with self.client.session_transaction() as session:
                    session["stage4_gate"] = True
            response = self.client.post(
                f"/submit/{stage_id}", data={"flag": f"LB{{stage_{stage_id}_flag}}"}
            )
            self.assertEqual(response.status_code, 302)

        completed_dashboard = self.client.get("/stages")
        self.assertEqual(completed_dashboard.data.count(b"Solved &#10003;"), 6)
        self.assertIn(b"Audit complete", completed_dashboard.data)

    def test_how_to_play_instructions_are_stage_one_only(self):
        stage_one = self.client.get("/stage/1")
        self.assertEqual(stage_one.status_code, 200)
        rendered_stage_one = re.sub(r"\s+", " ", stage_one.data.decode())
        for instruction in (
            "docker compose exec kali_player bash",
            "find which machines are alive on it",
            "find out which ports are open",
            "inspect the full HTTP response",
            "come back here and submit it below",
        ):
            self.assertIn(instruction, rendered_stage_one)

        self.client.post("/submit/1", data={"flag": "LB{stage_1_flag}"})
        stage_two = self.client.get("/stage/2")
        self.assertEqual(stage_two.status_code, 200)
        self.assertNotIn(b"How to play", stage_two.data)

    def test_stage_five_explains_ssh_and_cron_clue_path(self):
        for stage_id in range(1, 5):
            if stage_id == 4:
                with self.client.session_transaction() as session:
                    session["stage4_gate"] = True
            self.client.post(
                f"/submit/{stage_id}", data={"flag": f"LB{{stage_{stage_id}_flag}}"}
            )

        response = self.client.get("/stage/5")
        self.assertEqual(response.status_code, 200)
        rendered_stage_five = re.sub(r"\s+", " ", response.data.decode())
        for instruction in (
            "ssh vaultadmin@10.10.10.10",
            "How to approach it",
            "whoami",
            "id",
            "/etc/crontab",
            "/etc/cron.d",
            "crontab -l",
            "&lt;script-path-from-job&gt;",
            "directory containing the script",
            "unlock Stage 6",
        ):
            self.assertIn(instruction, rendered_stage_five)
        for answer_path in (
            "/etc/cron.d/legacy-maintenance",
            "/opt/legacy/maintenance.sh",
            "/opt/legacy/scheduler_audit.txt",
        ):
            self.assertNotIn(answer_path, rendered_stage_five)

    def test_stage_six_shows_capstone_content_without_stage_five_guidance(self):
        for stage_id in range(1, 6):
            if stage_id == 4:
                with self.client.session_transaction() as session:
                    session["stage4_gate"] = True
            self.client.post(
                f"/submit/{stage_id}", data={"flag": f"LB{{stage_{stage_id}_flag}}"}
            )

        self.client.post("/hint/6/1")
        self.client.post("/hint/6/2")
        response = self.client.get("/stage/6")
        self.assertEqual(response.status_code, 200)
        rendered_stage_six = response.data.decode()
        for content in (
            "The Root Scheduler",
            "Hard",
            "250 points",
            "Review Stage 5",
            "Escalation strategy",
            "execute commands as root and read /root/flag.txt",
            "stage-six-guide-title",
            "harmless test",
            "job's next run",
            "Who executes this scheduled task, and what does it run?",
            "Check write permissions on everything the task touches.",
        ):
            self.assertIn(content, rendered_stage_six)
        for stage_five_detail in (
            "Starting position",
            "How to approach it",
        ):
            self.assertNotIn(stage_five_detail, rendered_stage_six)

    def test_team_solves_hints_and_scores_are_isolated(self):
        self.client.post("/submit/1", data={"flag": "LB{stage_1_flag}"})
        self.client.post("/hint/2/1")
        self.assertEqual(self.get_team_score(1), 98)
        self.assertEqual(self.client.get("/stage/2").status_code, 200)

        other_team = self.make_team_client(2)
        blocked = other_team.get("/stage/2")
        self.assertEqual(blocked.status_code, 302)
        self.assertEqual(blocked.location, "/stages")
        self.assertEqual(self.get_team_score(2), 0)

        own_stage = other_team.get("/stage/1")
        self.assertEqual(own_stage.status_code, 200)
        self.assertNotIn(b"A network you've never seen", own_stage.data)

    def test_hint_cost_is_deducted_once_and_scoreboard_has_no_flags(self):
        first_hint = self.client.post("/hint/1/1")
        self.assertEqual(first_hint.location, "/stage/1")
        self.assertEqual(self.get_team_score(1), -2)
        self.client.post("/hint/1/1")
        self.assertEqual(self.get_team_score(1), -2)

        scoreboard = dashboard_app.app.test_client().get("/scoreboard")
        self.assertEqual(scoreboard.status_code, 200)
        self.assertIn(b"alpha", scoreboard.data)
        self.assertIn(b"bravo", scoreboard.data)
        self.assertNotIn(b"LB{", scoreboard.data)


if __name__ == "__main__":
    unittest.main()

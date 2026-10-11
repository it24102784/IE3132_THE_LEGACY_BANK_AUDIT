import os
import json
import re
import secrets
import sqlite3
import subprocess
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_NAME="dashboard_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", BASE_DIR / "dashboard.db"))
CHALLENGE_VALUE = secrets.randbelow(90000) + 10000
EMPLOYEE_ID = 1007
LEGACY_PIN = 7391

STAGES = [
    {"id": 1, "title": "The Forgotten Server",
        "domain": "Networking/Reconnaissance", "difficulty": "Easy", "points": 100,
        "briefing": "During the cloud migration, Legacy Bank's IT team believed their old staging server was decommissioned. It wasn't. Scope: 10.10.10.0/24. Objective: find what's still running out there, and look closely at what it reveals. Submit any flag you find in LB{...} format."},
    {"id": 2, "title": "The Legacy Employee Portal",
        "domain": "Web Security", "difficulty": "Easy", "points": 100,
        "briefing": "The forgotten server hosts the bank's old employee login portal. The developers never sanitized user input. Scope: the portal URL you found in Stage 1. Objective: bypass the login and retrieve the flag from the authenticated dashboard."},
    {"id": 3, "title": "The Encoded Credentials",
        "domain": "Cryptography", "difficulty": "Moderate", "points": 150,
        "briefing": "Inside the portal you found a config file with 'protected' admin credentials. The developers used encoding and a classical cipher instead of proper hashing. Objective: reverse both layers and recover the credential — it doubles as this stage's flag."},
    {"id": 4, "title": "The Broken Second Factor",
        "domain": "Authentication", "difficulty": "Moderate", "points": 150,
        "briefing": "The recovered credential alone isn't enough — SSH needs the legacy two-factor response. The old 2FA computes its answer from a predictable formula, not a secure token. Objective: combine the employee ID, legacy PIN, and the displayed challenge value to compute the correct response."},
    {"id": 5, "title": "Inside the Legacy Server", "domain": "Linux/System Security",
        "difficulty": "Moderate-Hard", "points": 200,
        "briefing": "Connect to the legacy server over SSH as a low-privilege user. Enumerate scheduled tasks and their permissions to locate the misconfigured root cron job and recover the clue it guards."},
    {"id": 6, "title": "The Root Scheduler", "domain": "Linux/Privilege Escalation",
        "difficulty": "Hard", "points": 250,
        "briefing": "A maintenance script runs as root on a schedule — and it's insecurely configured. Objective: exploit it to execute commands as root and read /root/flag.txt. This is the capstone: it builds on everything you found in Stage 5."},
]

HINTS = {
    1: [("A network you've never seen before — what tool tells you who's alive on it?", 2), ("Found the web server? Web pages have more than just what the browser shows you.", 3)],
    2: [("The login query might trust user input too much.", 2), ("Try classic authentication bypass payloads.", 3)],
    3: [("That's not encryption, it's just an encoding scheme.", 2), ("Look for a key hint in the portal's page source or comments.", 3)],
    4: [("The formula uses values you already have.", 2), ("Try combining ID and PIN with the challenge value using simple arithmetic.", 3)],
    5: [("Check what's running on a schedule.", 2), ("Look at permissions on files a root job touches.", 3)],
    6: [("Who executes this scheduled task, and what does it run?", 3), ("Check write permissions on everything the task touches.", 4)],
}

UNIVERSITY_OPTIONS = {
    "Government / State": [
        "Bhiksu University of Sri Lanka",
        "Buddhist and Pali University of Sri Lanka",
        "Eastern University, Sri Lanka",
        "Gampaha Wickramarachchi University of Indigenous Medicine",
        "General Sir John Kotelawala Defence University",
        "National Institute of Business Management",
        "Ocean University of Sri Lanka",
        "Open University of Sri Lanka",
        "Rajarata University of Sri Lanka",
        "Sabaragamuwa University of Sri Lanka",
        "South Eastern University of Sri Lanka",
        "University of Colombo",
        "University of Jaffna",
        "University of Kelaniya",
        "University of Moratuwa",
        "University of Peradeniya",
        "University of Ruhuna",
        "University of Sri Jayewardenepura",
        "University of the Visual and Performing Arts",
        "University of Vavuniya",
        "University of Vocational Technology",
        "Uva Wellassa University of Sri Lanka",
        "Wayamba University of Sri Lanka",
    ],
    "Private / Non-State": [
        "ACBT (Australian College of Business and Technology)",
        "ANC Education",
        "APIIT Sri Lanka",
        "Aquinas College of Higher Studies",
        "BCAS Campus",
        "Business Management School (BMS)",
        "Ceylon Open Campus",
        "CINEC Campus",
        "Colombo School of Business and Management",
        "ESOFT Metro Campus",
        "Horizon Campus",
        "ICBT Campus",
        "Informatics Institute of Technology (IIT)",
        "International Institute of Health Sciences (IIHS)",
        "KIU (Kaatsu International University)",
        "Lyceum Campus",
        "National School of Business Management (NSBM Green University)",
        "Royal Institute of Colombo (RIC)",
        "Saegis Campus",
        "Sri Lanka Institute of Information Technology (SLIIT)",
        "Sri Lanka Technological Campus (SLTC Research University)",
        "Universal College Lanka",
    ],
}
VALID_UNIVERSITIES = {
    university
    for options in UNIVERSITY_OPTIONS.values()
    for university in options
} | {"Other / not listed"}


@contextmanager
def get_db():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "team_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


@app.context_processor
def inject_current_team():
    """Make the session's team name available to the shared navbar."""
    team_id = session.get("team_id")
    if team_id is None:
        return {"current_team": None}
    with get_db() as connection:
        current_team = connection.execute(
            "SELECT id, username FROM teams WHERE id = ?", (team_id,)
        ).fetchone()
    return {"current_team": current_team}


def award_solve(connection, team_id, stage_id):
    """Record a solve once and add its configured stage points."""
    result = connection.execute(
        "INSERT OR IGNORE INTO solves (team_id, stage_id, solved_at) "
        "VALUES (?, ?, CURRENT_TIMESTAMP)",
        (team_id, stage_id),
    )
    if not result.rowcount:
        return False

    points = next(stage["points"]
                  for stage in STAGES if stage["id"] == stage_id)
    connection.execute(
        "UPDATE teams SET score = score + ? WHERE id = ?", (points, team_id))
    return True


def check_and_record_flag(team_id, stage_id, submitted_flag):
    """Validate a flag against SQLite without returning the stored value."""
    with get_db() as connection:
        row = connection.execute(
            "SELECT flag_value FROM flags WHERE stage_id = ?", (stage_id,)
        ).fetchone()
        if not row:
            return False, False
        expected_flag = row["flag_value"].strip()
        submitted_flag = submitted_flag.strip()
        if submitted_flag != expected_flag:
            return False, False
        return True, award_solve(connection, team_id, stage_id)


def team_has_unlocked_stage(connection, team_id, stage_id):
    if stage_id == 1:
        return True
    return connection.execute(
        "SELECT 1 FROM solves WHERE team_id = ? AND stage_id = ?",
        (team_id, stage_id - 1),
    ).fetchone() is not None


def stage_submission_redirect(stage_id):
    next_stage_id = stage_id + 1
    if next_stage_id <= len(STAGES):
        return redirect(url_for("stage_detail", stage_id=next_stage_id))
    return redirect(url_for("stages"))


@app.route("/health")
def health_check():
    """Expose a lightweight health response for the container check."""
    return {"status": "healthy", "service": "dashboard"}, 200


@app.route("/")
def index():
    """Send authenticated teams to their dashboard and others to login."""
    endpoint = "stages" if "team_id" in session else "login"
    return redirect(url_for(endpoint))


@app.route("/login", methods=["GET", "POST"])
def login():
    """Authenticate a registered team without disclosing account existence."""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with get_db() as connection:
            team = connection.execute(
                "SELECT id, password_hash FROM teams "
                "WHERE username = ? COLLATE NOCASE",
                (username,),
            ).fetchone()
        if team and check_password_hash(team["password_hash"], password):
            session.clear()
            session["team_id"] = team["id"]
            return redirect(url_for("stages"))
        return render_template("error.html", message="Invalid team name or password."), 401
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Validate and create a team account with hashed credentials and members."""
    if session.get("team_id") is not None:
        return redirect(url_for("stages"))
    if request.method == "GET":
        return render_template(
            "register.html",
            errors=[],
            form_data={},
            university_options=UNIVERSITY_OPTIONS,
        )

    team_name = request.form.get("team_name", "").strip()
    university = request.form.get("university", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")
    member_values = {
        f"member{number}": request.form.get(f"member{number}", "").strip()
        for number in range(1, 5)
    }
    form_data = {"team_name": team_name,
                 "university": university, **member_values}
    errors = []

    if not team_name:
        errors.append("Team name is required.")
    elif not 3 <= len(team_name) <= 20:
        errors.append("Team name must be 3 to 20 characters long.")
    elif re.fullmatch(r"[A-Za-z0-9_-]+", team_name) is None:
        errors.append(
            "Team name may contain only letters, numbers, underscores, and hyphens.")

    if not password:
        errors.append("Password is required.")
    elif len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    if password != confirm_password:
        errors.append("Passwords do not match.")
    if not member_values["member1"]:
        errors.append("Member 1 name is required.")
    if university not in VALID_UNIVERSITIES:
        errors.append("Select a university from the list.")

    if team_name and re.fullmatch(r"[A-Za-z0-9_-]{3,20}", team_name):
        with get_db() as connection:
            duplicate = connection.execute(
                "SELECT 1 FROM teams WHERE username = ? COLLATE NOCASE",
                (team_name,),
            ).fetchone()
        if duplicate:
            errors.append("That team name is taken, choose another.")

    if errors:
        return render_template(
            "register.html",
            errors=errors,
            form_data=form_data,
            university_options=UNIVERSITY_OPTIONS,
        ), 400

    members = json.dumps(
        [member_values[f"member{number}"] for number in range(1, 5)],
        ensure_ascii=False,
    )
    try:
        with get_db() as connection:
            connection.execute(
                "INSERT INTO teams (username, password_hash, score, members, university) "
                "VALUES (?, ?, 0, ?, ?)",
                (team_name, generate_password_hash(password), members, university),
            )
    except sqlite3.IntegrityError:
        return render_template(
            "register.html",
            errors=["That team name is taken, choose another."],
            form_data=form_data,
            university_options=UNIVERSITY_OPTIONS,
        ), 400
    except sqlite3.Error:
        return render_template(
            "error.html", message="Registration could not be completed. Please try again later."
        ), 500

    flash("registration successful, please log in", "success")
    return redirect(url_for("login"))


@app.route("/logout")
def logout():
    """Clear the team session."""
    session.clear()
    return redirect(url_for("login"))


@app.route("/stages")
@login_required
def stages():
    """Show all stages with access determined by this team's solves."""
    with get_db() as connection:
        team = connection.execute(
            "SELECT username, score FROM teams WHERE id = ?", (
                session["team_id"],)
        ).fetchone()
        if not team:
            session.clear()
            return redirect(url_for("login"))
        solved = {
            row["stage_id"]
            for row in connection.execute(
                "SELECT stage_id FROM solves WHERE team_id = ?", (
                    session["team_id"],)
            )
        }
    stage_data = []
    for stage in STAGES:
        stage_data.append({
            **stage,
            "solved": stage["id"] in solved,
            "unlocked": stage["id"] == 1 or stage["id"] - 1 in solved,
        })
    return render_template("stages.html", stages=stage_data, team=team)


@app.route("/scoreboard")
def scoreboard():
    """Show team totals without exposing challenge flag data."""
    with get_db() as connection:
        teams = connection.execute(
            "SELECT username, score FROM teams ORDER BY score DESC, username COLLATE NOCASE"
        ).fetchall()
    return render_template("scoreboard.html", teams=teams)


@app.route("/stage/<int:stage_id>")
@login_required
def stage_detail(stage_id):
    """Show a stage briefing only after the previous stage is solved."""
    if stage_id not in range(1, len(STAGES) + 1):
        return render_template("error.html", message="That stage does not exist."), 404
    with get_db() as connection:
        if not team_has_unlocked_stage(connection, session["team_id"], stage_id):
            flash("Complete the previous stage first.", "warning")
            return redirect(url_for("stages"))
        team = connection.execute(
            "SELECT username, score FROM teams WHERE id = ?", (
                session["team_id"],)
        ).fetchone()
        if not team:
            session.clear()
            return redirect(url_for("login"))
        solved = connection.execute(
            "SELECT 1 FROM solves WHERE team_id = ? AND stage_id = ?",
            (session["team_id"], stage_id),
        ).fetchone() is not None
        revealed = {
            row["hint_no"]
            for row in connection.execute(
                "SELECT hint_no FROM revealed_hints WHERE team_id = ? AND stage_id = ?",
                (session["team_id"], stage_id),
            )
        }
    stage = next(item for item in STAGES if item["id"] == stage_id)
    hints = [
        {"number": number, "text": text, "cost": cost,
            "revealed": number in revealed}
        for number, (text, cost) in enumerate(HINTS[stage_id], start=1)
    ]
    return render_template(
        "stage.html", stage=stage, hints=hints, solved=solved,
        team=team, stage4_gate=session.get("stage4_gate", False),
    )


@app.route("/submit/<int:stage_id>", methods=["POST"])
@login_required
def submit(stage_id):
    """Validate a submitted stage flag and award points only for a new solve."""
    if stage_id not in range(1, 7):
        return render_template("error.html", message="That stage does not exist."), 404
    with get_db() as connection:
        if not team_has_unlocked_stage(connection, session["team_id"], stage_id):
            flash("Complete the previous stage first.", "warning")
            return redirect(url_for("stages"))
    if stage_id == 4 and not session.get("stage4_gate"):
        flash("Complete the second-factor gate before submitting Stage 4.", "warning")
        return redirect(url_for("twofa"))

    correct, newly_solved = check_and_record_flag(
        session["team_id"], stage_id, request.form.get("flag", "")
    )
    if not correct:
        flash("Incorrect flag, try again.", "danger")
        return redirect(url_for("stage_detail", stage_id=stage_id))
    elif newly_solved:
        flash(
            f"Correct flag. Stage {stage_id} complete; {STAGES[stage_id - 1]['points']} points awarded.", "success")
        return stage_submission_redirect(stage_id)
    else:
        flash("This stage is already solved; no additional points were awarded.", "info")
    return stage_submission_redirect(stage_id)


@app.route("/hint/<int:stage_id>/<int:n>", methods=["POST"])
@login_required
def reveal_hint(stage_id, n):
    """Reveal a progressive hint and deduct its points at most once."""
    if stage_id not in HINTS or n not in (1, 2):
        return render_template("error.html", message="That hint does not exist."), 404
    with get_db() as connection:
        if not team_has_unlocked_stage(connection, session["team_id"], stage_id):
            flash("Complete the previous stage first.", "warning")
            return redirect(url_for("stages"))

    hint_text, cost = HINTS[stage_id][n - 1]
    with get_db() as connection:
        result = connection.execute(
            "INSERT OR IGNORE INTO revealed_hints (team_id, stage_id, hint_no) VALUES (?, ?, ?)",
            (session["team_id"], stage_id, n),
        )
        if result.rowcount:
            connection.execute(
                "UPDATE teams SET score = score - ? WHERE id = ?", (cost, session["team_id"]))
    flash(f"Hint {n}: {hint_text} ({cost} points deducted once)", "info")
    return redirect(url_for("stage_detail", stage_id=stage_id))


@app.route("/twofa", methods=["GET", "POST"])
@login_required
def twofa():
    """Validate Stage 4's second factor without solving the stage itself."""
    with get_db() as connection:
        if not team_has_unlocked_stage(connection, session["team_id"], 4):
            flash("Complete the previous stage first.", "warning")
            return redirect(url_for("stages"))
    if request.method == "POST":
        response = request.form.get("response", "").strip()
        expected = f"{(EMPLOYEE_ID * 7 + LEGACY_PIN * 3 + CHALLENGE_VALUE) % 100000:05d}"
        if not secrets.compare_digest(response, expected):
            flash("Incorrect response, try again.", "danger")
            return redirect(url_for("twofa"))
        session["stage4_gate"] = True
        flash("Second factor accepted. Submit the Stage 4 flag to complete the stage.", "success")
        return redirect(url_for("stage_detail", stage_id=4))

    return render_template(
        "twofa.html",
        employee_id=EMPLOYEE_ID,
        legacy_pin=LEGACY_PIN,
        challenge_value=CHALLENGE_VALUE,
        gate_passed=session.get("stage4_gate", False),
    )


@app.route("/reset", methods=["POST"])
@login_required
def reset_targets():
    """Best-effort restart of challenge containers for the operator/team."""
    commands = [
        ["docker", "compose", "restart", "web", "linuxsrv"],
        ["docker", "compose", "restart", "web_challenge", "linux_challenge"],
    ]
    for command in commands:
        try:
            subprocess.run(command, cwd=BASE_DIR.parent,
                           check=True, capture_output=True, text=True)
            flash("Challenge targets restarted.", "success")
            break
        except (OSError, subprocess.CalledProcessError):
            continue
    else:
        flash("Automatic reset failed. Run `docker compose restart web_challenge linux_challenge` from the project directory.", "warning")
    return redirect(url_for("stages"))


if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "80"))
    app.run(host="0.0.0.0", port=port)

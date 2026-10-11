import base64
import os
import random
import sqlite3
import tempfile

from flask import Flask, Response, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default_web_secret_key')
app.config['SESSION_COOKIE_NAME'] = 'portal_session'


def get_flag(stage):
    # Single source of truth: flags/stageN.txt (mounted at /app/flags/ in Docker)
    candidates = [
        f'/app/flags/stage{stage}.txt',
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     '..', 'flags', f'stage{stage}.txt'),
    ]
    for path in candidates:
        try:
            if os.path.exists(path):
                with open(path) as f:
                    return f.read().strip()
        except OSError:
            continue
    return 'LB{flag_not_configured}'


STAGE1_FLAG = get_flag(1)
STAGE2_FLAG = get_flag(2)
STAGE3_FLAG = get_flag(3)
STAGE4_FLAG = get_flag(4)

# Vigenere key protecting the Stage 3 config file (hinted in the portal page source)
STAGE3_KEY = 'LEGACYBANK'

# Stage 4: legacy 2FA challenge value, re-randomized on every (re)start
STAGE4_CHALLENGE = random.randint(1000, 9999)


def compute_2fa_response(emp_id, pin, challenge):
    # The legacy 2FA "formula": simple, deterministic arithmetic
    return f"{(int(emp_id) + int(pin) + int(challenge)) % 10000:04d}"


# Worked examples from the legacy documentation (fixed samples; the live
# challenge above is randomized, but the same rule always applies)
TWOFA_EXAMPLES = [
    (1001, 4821, 1111, compute_2fa_response(1001, 4821, 1111)),
    (1001, 4821, 9999, compute_2fa_response(1001, 4821, 9999)),
]


@app.after_request
def expose_stage1_flag(response):
    # Stage 1: the flag leaks in a response header
    response.headers['X-Legacy-Staging'] = STAGE1_FLAG
    return response


# ---------------------------------------------------------------------------
# Stage 2: The Legacy Employee Portal (SQL injection)
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(tempfile.gettempdir(), 'legacy_portal.db')


def init_db():
    # Fresh database on every (re)start, per the design doc
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, role TEXT, employee_id TEXT, pin TEXT)')
    conn.execute(
        "INSERT INTO users (username, password, role, employee_id, pin) VALUES ('admin', 'Sup3rS3cret2019!', 'administrator', '1001', '4821')")
    conn.execute(
        "INSERT INTO users (username, password, role, employee_id, pin) VALUES ('jdoe', 'Welcome123', 'employee', '1002', '7304')")
    conn.commit()
    conn.close()


init_db()


def vigenere_encrypt(plaintext, key):
    # Classical Vigenere, CyberChef-compatible: letters shift, everything else untouched
    key = key.upper()
    out = []
    ki = 0
    for ch in plaintext:
        if 'A' <= ch <= 'Z' or 'a' <= ch <= 'z':
            base = ord('A') if ch.isupper() else ord('a')
            shift = ord(key[ki % len(key)]) - ord('A')
            out.append(chr((ord(ch) - base + shift) % 26 + base))
            ki += 1
        else:
            out.append(ch)
    return ''.join(out)


def build_stage3_config():
    # Stage 3 setup: Base64( Vigenere( stage3_flag ) ), generated at runtime
    cipher = vigenere_encrypt(STAGE3_FLAG, STAGE3_KEY)
    b64 = base64.b64encode(cipher.encode()).decode()
    return (
        '# Legacy Bank - vault backup config (auto-generated 2019-03-14)\n'
        '# INTERNAL ONLY - do not share\n'
        'vault_admin_user = vaultadmin\n'
        f'vault_admin_cred = {b64}\n'
        '# credentials are protected, safe to keep here\n'
    )


def login_page(error=''):
    return render_template('login.html', error=error)


@app.route('/portal', methods=['GET', 'POST'])
def portal_login():
    error = ''
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        # INTENTIONALLY VULNERABLE (Stage 2): user input goes straight into the SQL query
        query = "SELECT * FROM users WHERE username = '%s' AND password = '%s'" % (
            username, password)
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        try:
            cur.execute(query)
            row = cur.fetchone()
        except sqlite3.Error:
            row = None
        conn.close()
        if row:
            session['portal_user'] = row[1]
            session['portal_role'] = row[3]
            session['portal_emp_id'] = row[4]
            session['portal_pin'] = row[5]
            return redirect(url_for('portal_dashboard'))
        error = 'Invalid username or password.'
    return login_page(error)


@app.route('/portal/dashboard')
def portal_dashboard():
    user = session.get('portal_user')
    if not user:
        return redirect(url_for('portal_login'))
    return render_template(
        'portal.html',
        user=user,
        role=session.get('portal_role', ''),
        employee_id=session.get('portal_emp_id', ''),
        pin=session.get('portal_pin', ''),
        stage2_flag=STAGE2_FLAG,
        authenticated=True,
    )


@app.route('/portal/legacy-config.bak')
def portal_config():
    # Stage 3 lives inside the Stage 2 portal: config file is only reachable after login
    if not session.get('portal_user'):
        return redirect(url_for('portal_login'))
    return Response(
        build_stage3_config(),
        mimetype='text/plain',
        headers={'Content-Disposition': 'attachment; filename=legacy-config.bak'},
    )


@app.route('/portal/logout')
def portal_logout():
    session.clear()
    return redirect(url_for('portal_login'))


# ---------------------------------------------------------------------------
# Stage 4: The Broken Second Factor (weak 2FA logic gate)
# ---------------------------------------------------------------------------
@app.route('/2fa', methods=['GET', 'POST'])
def twofa_gate():
    # Stage 4 lives behind the portal login: no bypass, no 2FA page
    user = session.get('portal_user')
    if not user:
        return redirect(url_for('portal_login'))
    emp_id = session.get('portal_emp_id', '')
    pin = session.get('portal_pin', '')
    error = ''
    if request.method == 'POST':
        given = request.form.get('response', '').strip()
        expected = compute_2fa_response(emp_id, pin, STAGE4_CHALLENGE)
        if given == expected:
            return render_template(
                'twofa_success.html',
                user=user,
                stage4_flag=STAGE4_FLAG,
                authenticated=True,
            )
        error = 'Incorrect response. Study the worked examples and try again.'
    return render_template(
        '2fa.html',
        employee_id=emp_id,
        challenge=STAGE4_CHALLENGE,
        examples=TWOFA_EXAMPLES,
        error=error,
        authenticated=True,
    )


# ---------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/health')
def health_check():
    return {'status': 'healthy', 'service': 'web_challenge'}, 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('WEB_PORT', 80)))

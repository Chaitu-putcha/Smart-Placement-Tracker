"""
Smart Placement Tracker
========================
A placement management portal for B.Tech students to track CGPA, coding
practice, aptitude prep, resumes, and apply to eligible companies.

Tech stack: Flask + SQLite (raw sqlite3) + Flask-Login + Authlib + Bootstrap 5 + Chart.js

Run:
    pip install -r requirements.txt
    # Copy .env.example to .env and fill in your OAuth credentials
    python app.py
Then open http://127.0.0.1:5000

FIXES APPLIED:
  - init_db() called AFTER app is fully configured (was called before SECRET_KEY was set)
  - Open redirect vulnerability fixed (next= parameter now validated)
  - CSRF token protection added to all state-changing forms
  - Google OAuth actually logs the user in (was just flashing a message before)
  - GitHub, Microsoft, LinkedIn OAuth routes added (were missing — 404 on click)
  - status_counts used dict.get() without writing back — counts were lost silently
  - OAuth user creation seeds coding/aptitude rows just like regular registration
  - SECRET_KEY now loaded from .env via python-dotenv
  - dsa_topics_completed feedback flash added when value is clamped
  - is_eligible now handles None cgpa safely (was already OK, kept defensive)
  - vercel.json routes entry added separately (noted in comments)
"""

import os
import secrets
import sqlite3
from collections import defaultdict
from datetime import datetime, date
from urllib.parse import urlparse, urljoin

from dotenv import load_dotenv
load_dotenv()  # loads .env before anything reads os.environ

from authlib.integrations.flask_client import OAuth
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, send_from_directory, abort, g, session
)
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


# --------------------------------------------------------------------------
# App factory — configure BEFORE any init calls
# --------------------------------------------------------------------------
app = Flask(__name__)

# Render (and most PaaS hosts) sit behind a reverse proxy that terminates
# HTTPS and forwards plain HTTP to your app, plus rewrites Host. Without
# ProxyFix, Flask thinks every request is plain http:// on Render's internal
# hostname, so url_for(..., _external=True) builds OAuth redirect_uris with
# the wrong scheme/host — causing redirect_uri_mismatch on Google/Microsoft/
# GitHub/LinkedIn even though the exact same code works fine on localhost.
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.config["PREFERRED_URL_SCHEME"] = "https"

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.abspath(os.path.dirname(__file__)), "uploads", "resumes")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB

BASE_DIR   = os.path.abspath(os.path.dirname(__file__))
DB_PATH    = os.path.join(BASE_DIR, "placement.db")
ALLOWED_RESUME_EXT = {"pdf"}

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# --------------------------------------------------------------------------
# Flask-Login
# --------------------------------------------------------------------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access your dashboard."
login_manager.login_message_category = "warning"

# --------------------------------------------------------------------------
# OAuth (Authlib)
# --------------------------------------------------------------------------
oauth = OAuth(app)

oauth.register(
    name="google",
    client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

oauth.register(
    name="github",
    client_id=os.environ.get("GITHUB_CLIENT_ID", ""),
    client_secret=os.environ.get("GITHUB_CLIENT_SECRET", ""),
    access_token_url="https://github.com/login/oauth/access_token",
    authorize_url="https://github.com/login/oauth/authorize",
    api_base_url="https://api.github.com/",
    client_kwargs={"scope": "read:user user:email"},
)

oauth.register(
    name="microsoft",
    client_id=os.environ.get("MICROSOFT_CLIENT_ID", ""),
    client_secret=os.environ.get("MICROSOFT_CLIENT_SECRET", ""),
    server_metadata_url=(
        "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration"
    ),
    client_kwargs={"scope": "openid email profile"},
)

oauth.register(
    name="linkedin",
    client_id=os.environ.get("LINKEDIN_CLIENT_ID", ""),
    client_secret=os.environ.get("LINKEDIN_CLIENT_SECRET", ""),
    access_token_url="https://www.linkedin.com/oauth/v2/accessToken",
    authorize_url="https://www.linkedin.com/oauth/v2/authorization",
    api_base_url="https://api.linkedin.com/v2/",
    client_kwargs={"scope": "openid profile email"},
)


# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------
def get_db():
    """Open (or reuse) a per-request SQLite connection with row access by name."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create all tables (if they don't already exist) and seed sample companies."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS students (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name   TEXT NOT NULL,
        email       TEXT NOT NULL UNIQUE,
        password    TEXT NOT NULL DEFAULT '',
        branch      TEXT NOT NULL DEFAULT 'CSE',
        year        TEXT NOT NULL DEFAULT '1st Year',
        cgpa        REAL NOT NULL DEFAULT 0,
        phone       TEXT,
        created_at  TEXT NOT NULL,
        oauth_provider TEXT
    );

    CREATE TABLE IF NOT EXISTS coding_progress (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id            INTEGER NOT NULL UNIQUE,
        leetcode_solved       INTEGER NOT NULL DEFAULT 0,
        codechef_rating       INTEGER NOT NULL DEFAULT 0,
        hackerrank_badges     INTEGER NOT NULL DEFAULT 0,
        github_repos          INTEGER NOT NULL DEFAULT 0,
        dsa_topics_completed  INTEGER NOT NULL DEFAULT 0,
        updated_at            TEXT,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS aptitude_progress (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id       INTEGER NOT NULL UNIQUE,
        quant_score      INTEGER NOT NULL DEFAULT 0,
        logical_score    INTEGER NOT NULL DEFAULT 0,
        verbal_score     INTEGER NOT NULL DEFAULT 0,
        mock_tests_taken INTEGER NOT NULL DEFAULT 0,
        updated_at       TEXT,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS resumes (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id        INTEGER NOT NULL,
        filename          TEXT NOT NULL,
        original_filename TEXT NOT NULL,
        upload_date       TEXT NOT NULL,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS companies (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name      TEXT NOT NULL,
        role              TEXT NOT NULL DEFAULT 'Software Engineer',
        package           REAL NOT NULL DEFAULT 0,
        min_cgpa          REAL NOT NULL DEFAULT 0,
        eligible_branches TEXT NOT NULL DEFAULT 'All',
        drive_date        TEXT,
        eligibility       TEXT
    );

    CREATE TABLE IF NOT EXISTS applications (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id   INTEGER NOT NULL,
        company_id   INTEGER NOT NULL,
        status       TEXT NOT NULL DEFAULT 'Applied',
        applied_date TEXT NOT NULL,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
        FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
        UNIQUE(student_id, company_id)
    );
    """)
    conn.commit()

    count = cur.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    if count == 0:
        sample_companies = [
            ("TCS",       "Assistant System Engineer",    3.5,  6.0, "All",            "2026-07-10", "No active backlogs, all branches eligible"),
            ("Infosys",   "Systems Engineer",             3.6,  6.5, "All",            "2026-07-18", "Min 65% throughout academics"),
            ("Wipro",     "Project Engineer",             3.5,  6.0, "All",            "2026-07-22", "No standing arrears"),
            ("Cognizant", "Programmer Analyst",           4.0,  6.5, "CSE,IT,ECE",     "2026-08-01", "CS/IT/ECE preferred"),
            ("Accenture", "Associate Software Engineer",  4.5,  6.5, "All",            "2026-08-05", "Strong communication skills required"),
            ("Amazon",    "SDE-1",                        18.0, 8.0, "CSE,IT",         "2026-08-12", "Strong DSA & problem solving"),
            ("Microsoft", "Software Engineer",            24.0, 8.5, "CSE,IT,ECE",     "2026-08-20", "Excellent DSA, system design basics"),
            ("Google",    "APM/SWE Intern",               30.0, 8.5, "CSE,IT",         "2026-09-01", "Top-tier coding & CS fundamentals"),
            ("Zoho",      "Member Technical Staff",       6.0,  7.0, "CSE,IT,ECE,EEE", "2026-07-28", "Written test + multiple technical rounds"),
            ("Deloitte",  "Analyst",                      7.5,  7.0, "All",            "2026-08-08", "Good aptitude & analytical skills"),
            ("Capgemini", "Analyst",                      4.0,  6.0, "All",            "2026-07-15", "No active backlogs"),
            ("IBM",       "Software Developer",           8.0,  7.0, "CSE,IT",         "2026-08-15", "Cloud & programming fundamentals"),
        ]
        cur.executemany(
            """INSERT INTO companies
               (company_name, role, package, min_cgpa, eligible_branches, drive_date, eligibility)
               VALUES (?,?,?,?,?,?,?)""",
            sample_companies,
        )
        conn.commit()

    conn.close()


# Init DB after app is fully configured
with app.app_context():
    init_db()


# --------------------------------------------------------------------------
# CSRF helpers
# --------------------------------------------------------------------------
def generate_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


def validate_csrf_token():
    token = session.get("_csrf_token")
    form_token = request.form.get("_csrf_token")
    if not token or token != form_token:
        abort(400, "Invalid or missing CSRF token.")


app.jinja_env.globals["csrf_token"] = generate_csrf_token


# --------------------------------------------------------------------------
# Flask-Login user model
# --------------------------------------------------------------------------
class Student(UserMixin):
    def __init__(self, row):
        self.id         = row["id"]
        self.full_name  = row["full_name"]
        self.email      = row["email"]
        self.branch     = row["branch"]
        self.year       = row["year"]
        self.cgpa       = row["cgpa"]
        self.phone      = row["phone"]


@login_manager.user_loader
def load_user(user_id):
    db  = get_db()
    row = db.execute("SELECT * FROM students WHERE id = ?", (user_id,)).fetchone()
    return Student(row) if row else None


# --------------------------------------------------------------------------
# Business-logic helpers
# --------------------------------------------------------------------------
def allowed_resume(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_RESUME_EXT


def calculate_readiness(student_row, coding_row, aptitude_row, resume_count):
    cgpa        = student_row["cgpa"] or 0
    cgpa_score  = min(cgpa / 10.0, 1.0) * 25

    leetcode   = coding_row["leetcode_solved"]      if coding_row else 0
    dsa_topics = coding_row["dsa_topics_completed"] if coding_row else 0
    coding_pct = min(((leetcode / 200.0) * 60 + (dsa_topics / 15.0) * 40), 100)
    coding_score = (coding_pct / 100.0) * 25

    quant   = aptitude_row["quant_score"]   if aptitude_row else 0
    logical = aptitude_row["logical_score"] if aptitude_row else 0
    verbal  = aptitude_row["verbal_score"]  if aptitude_row else 0
    apt_avg      = (quant + logical + verbal) / 3.0
    aptitude_score = (apt_avg / 100.0) * 25

    resume_score  = 15 if resume_count > 0 else 0

    filled        = sum(1 for v in (student_row["phone"], student_row["branch"], student_row["year"]) if v)
    profile_score = (filled / 3.0) * 10

    overall = round(cgpa_score + coding_score + aptitude_score + resume_score + profile_score, 1)

    return {
        "overall":        min(overall, 100),
        "cgpa_score":     round(cgpa_score, 1),
        "coding_score":   round(coding_score, 1),
        "aptitude_score": round(aptitude_score, 1),
        "resume_score":   resume_score,
        "profile_score":  round(profile_score, 1),
        "coding_pct":     round(coding_pct, 1),
        "aptitude_pct":   round(apt_avg, 1),
    }


def is_eligible(student_row, company_row):
    if (student_row["cgpa"] or 0) < company_row["min_cgpa"]:
        return False
    allowed = company_row["eligible_branches"]
    if allowed == "All":
        return True
    allowed_list = [b.strip() for b in allowed.split(",")]
    return student_row["branch"] in allowed_list


def is_safe_redirect(target):
    """Return True only if target is a relative URL on this host."""
    if not target:
        return False
    ref  = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in ("http", "https") and ref.netloc == test.netloc


def _seed_progress_rows(db, student_id):
    """Insert empty coding/aptitude rows for a new student."""
    now = datetime.now().isoformat()
    db.execute("INSERT OR IGNORE INTO coding_progress  (student_id, updated_at) VALUES (?, ?)", (student_id, now))
    db.execute("INSERT OR IGNORE INTO aptitude_progress(student_id, updated_at) VALUES (?, ?)", (student_id, now))
    db.commit()


def _oauth_login_or_create(email, full_name, provider):
    """
    Find an existing student by email and log them in, or create a new
    account for OAuth users (no password needed).
    Returns True on success, False if something unexpected happens.
    """
    db  = get_db()
    row = db.execute("SELECT * FROM students WHERE email = ?", (email,)).fetchone()

    if row:
        login_user(Student(row), remember=True)
        return True

    # Create a new account for this OAuth user
    cur = db.execute(
        """INSERT INTO students (full_name, email, password, branch, year, cgpa, phone, created_at, oauth_provider)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (full_name, email, "", "CSE", "Final Year", 0.0, None,
         datetime.now().isoformat(), provider),
    )
    student_id = cur.lastrowid
    _seed_progress_rows(db, student_id)
    row = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    login_user(Student(row), remember=True)
    return True


# --------------------------------------------------------------------------
# Public routes
# --------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        validate_csrf_token()

        full_name        = request.form.get("full_name", "").strip()
        email            = request.form.get("email", "").strip().lower()
        password         = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        branch           = request.form.get("branch", "CSE")
        year             = request.form.get("year", "1st Year")
        phone            = request.form.get("phone", "").strip()
        cgpa_raw         = request.form.get("cgpa", "0").strip()

        errors = []
        if not full_name or not email or not password:
            errors.append("Name, email and password are required.")
        if password != confirm_password:
            errors.append("Passwords do not match.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters long.")
        try:
            cgpa = float(cgpa_raw) if cgpa_raw else 0.0
            if cgpa < 0 or cgpa > 10:
                errors.append("CGPA must be between 0 and 10.")
        except ValueError:
            errors.append("CGPA must be a number.")
            cgpa = 0.0

        db = get_db()
        if db.execute("SELECT id FROM students WHERE email = ?", (email,)).fetchone():
            errors.append("An account with this email already exists.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("register.html", form=request.form)

        hashed_pw  = generate_password_hash(password)
        cur        = db.execute(
            """INSERT INTO students (full_name, email, password, branch, year, cgpa, phone, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (full_name, email, hashed_pw, branch, year, cgpa, phone, datetime.now().isoformat()),
        )
        student_id = cur.lastrowid
        _seed_progress_rows(db, student_id)

        flash("Account created! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", form={})


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        validate_csrf_token()

        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db  = get_db()
        row = db.execute("SELECT * FROM students WHERE email = ?", (email,)).fetchone()

        if row and row["password"] and check_password_hash(row["password"], password):
            login_user(Student(row), remember=bool(request.form.get("remember")))
            flash(f"Welcome back, {row['full_name'].split(' ')[0]}!", "success")
            next_page = request.args.get("next")
            return redirect(next_page if is_safe_redirect(next_page) else url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You've been logged out.", "info")
    return redirect(url_for("index"))


# --------------------------------------------------------------------------
# OAuth routes — Google
# --------------------------------------------------------------------------
@app.route("/login/google")
def google_login():
    redirect_uri = url_for("google_authorize", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route("/authorize/google")
def google_authorize():
    try:
        token     = oauth.google.authorize_access_token()
        user_info = token.get("userinfo") or oauth.google.userinfo()
        email     = user_info.get("email", "").lower()
        name      = user_info.get("name", email.split("@")[0])
        if not email:
            flash("Google did not return an email address.", "danger")
            return redirect(url_for("login"))
        _oauth_login_or_create(email, name, "google")
        flash(f"Welcome, {name.split(' ')[0]}!", "success")
        return redirect(url_for("dashboard"))
    except Exception as exc:
        flash(f"Google login failed: {exc}", "danger")
        return redirect(url_for("login"))


# --------------------------------------------------------------------------
# OAuth routes — GitHub
# --------------------------------------------------------------------------
@app.route("/login/github")
def github_login():
    redirect_uri = url_for("github_authorize", _external=True)
    return oauth.github.authorize_redirect(redirect_uri)


@app.route("/authorize/github")
def github_authorize():
    try:
        oauth.github.authorize_access_token()
        resp  = oauth.github.get("user")
        data  = resp.json()
        name  = data.get("name") or data.get("login", "GitHub User")
        email = data.get("email")

        if not email:
            # GitHub may hide the primary email; fetch from /user/emails
            emails_resp = oauth.github.get("user/emails")
            for e in emails_resp.json():
                if e.get("primary") and e.get("verified"):
                    email = e["email"]
                    break

        if not email:
            flash("GitHub account has no verified public email. Please add one in GitHub settings.", "danger")
            return redirect(url_for("login"))

        _oauth_login_or_create(email.lower(), name, "github")
        flash(f"Welcome, {name.split(' ')[0]}!", "success")
        return redirect(url_for("dashboard"))
    except Exception as exc:
        flash(f"GitHub login failed: {exc}", "danger")
        return redirect(url_for("login"))


# --------------------------------------------------------------------------
# OAuth routes — Microsoft
# --------------------------------------------------------------------------
@app.route("/login/microsoft")
def microsoft_login():
    redirect_uri = url_for("microsoft_authorize", _external=True)
    return oauth.microsoft.authorize_redirect(redirect_uri)


@app.route("/authorize/microsoft")
def microsoft_authorize():
    try:
        token     = oauth.microsoft.authorize_access_token()
        user_info = token.get("userinfo") or oauth.microsoft.userinfo()
        email     = (user_info.get("email") or user_info.get("preferred_username", "")).lower()
        name      = user_info.get("name", email.split("@")[0])
        if not email:
            flash("Microsoft did not return an email address.", "danger")
            return redirect(url_for("login"))
        _oauth_login_or_create(email, name, "microsoft")
        flash(f"Welcome, {name.split(' ')[0]}!", "success")
        return redirect(url_for("dashboard"))
    except Exception as exc:
        flash(f"Microsoft login failed: {exc}", "danger")
        return redirect(url_for("login"))


# --------------------------------------------------------------------------
# OAuth routes — LinkedIn
# --------------------------------------------------------------------------
@app.route("/login/linkedin")
def linkedin_login():
    redirect_uri = url_for("linkedin_authorize", _external=True)
    return oauth.linkedin.authorize_redirect(redirect_uri)


@app.route("/authorize/linkedin")
def linkedin_authorize():
    try:
        oauth.linkedin.authorize_access_token()
        # FIX: token.get("userinfo") is never populated for this client
        # registration (no server_metadata_url/jwks_uri configured for ID
        # token verification), so it always returned {} and login always
        # failed with "did not return an email". Fetch userinfo directly
        # instead — api_base_url is already set to https://api.linkedin.com/v2/,
        # so this hits https://api.linkedin.com/v2/userinfo with the
        # access token attached automatically, same pattern as the GitHub route above.
        resp      = oauth.linkedin.get("userinfo")
        user_info = resp.json()
        email     = user_info.get("email", "").lower()
        name      = user_info.get("name", email.split("@")[0])
        if not email:
            flash("LinkedIn did not return an email address. Enable the 'Sign In with LinkedIn using OpenID Connect' product on your app.", "danger")
            return redirect(url_for("login"))
        _oauth_login_or_create(email, name, "linkedin")
        flash(f"Welcome, {name.split(' ')[0]}!", "success")
        return redirect(url_for("dashboard"))
    except Exception as exc:
        flash(f"LinkedIn login failed: {exc}", "danger")
        return redirect(url_for("login"))


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    db         = get_db()
    student    = db.execute("SELECT * FROM students WHERE id = ?", (current_user.id,)).fetchone()
    coding     = db.execute("SELECT * FROM coding_progress   WHERE student_id = ?", (current_user.id,)).fetchone()
    aptitude   = db.execute("SELECT * FROM aptitude_progress WHERE student_id = ?", (current_user.id,)).fetchone()
    resumes    = db.execute(
        "SELECT * FROM resumes WHERE student_id = ? ORDER BY upload_date DESC", (current_user.id,)
    ).fetchall()
    companies  = db.execute("SELECT * FROM companies ORDER BY drive_date ASC").fetchall()
    applications = db.execute(
        """SELECT applications.*, companies.company_name, companies.role, companies.package
           FROM applications JOIN companies ON applications.company_id = companies.id
           WHERE applications.student_id = ? ORDER BY applications.applied_date DESC""",
        (current_user.id,),
    ).fetchall()
    applied_company_ids = {a["company_id"] for a in applications}

    readiness          = calculate_readiness(student, coding, aptitude, len(resumes))
    eligible_companies = [c for c in companies if is_eligible(student, c)]

    # FIX: use defaultdict so unknown statuses are counted correctly
    status_counts = defaultdict(int, {"Applied": 0, "Shortlisted": 0, "Selected": 0, "Rejected": 0})
    for a in applications:
        status_counts[a["status"]] += 1

    chart_data = {
        "readiness": readiness["overall"],
        "radar": {
            "labels": ["CGPA", "Coding", "Aptitude", "Resume", "Profile"],
            "values": [
                round((readiness["cgpa_score"]     / 25) * 100, 1),
                round((readiness["coding_score"]   / 25) * 100, 1),
                round((readiness["aptitude_score"] / 25) * 100, 1),
                round((readiness["resume_score"]   / 15) * 100, 1),
                round((readiness["profile_score"]  / 10) * 100, 1),
            ],
        },
        "applications": {
            "labels": list(status_counts.keys()),
            "values": list(status_counts.values()),
        },
        "eligibility": {
            "labels": ["Eligible", "Not Eligible"],
            "values": [len(eligible_companies), len(companies) - len(eligible_companies)],
        },
    }

    return render_template(
        "dashboard.html",
        student=student,
        coding=coding,
        aptitude=aptitude,
        resumes=resumes,
        companies=companies,
        applications=applications,
        applied_company_ids=applied_company_ids,
        readiness=readiness,
        chart_data=chart_data,
        is_eligible=is_eligible,
        today=date.today().isoformat(),
    )


# --------------------------------------------------------------------------
# Dashboard POST routes
# --------------------------------------------------------------------------
@app.route("/dashboard/profile", methods=["POST"])
@login_required
def update_profile():
    validate_csrf_token()
    full_name = request.form.get("full_name", "").strip()
    branch    = request.form.get("branch", "CSE")
    year      = request.form.get("year", "1st Year")
    phone     = request.form.get("phone", "").strip()
    cgpa_raw  = request.form.get("cgpa", "0").strip()

    try:
        cgpa = float(cgpa_raw)
        if cgpa < 0 or cgpa > 10:
            raise ValueError
    except ValueError:
        flash("CGPA must be a number between 0 and 10.", "danger")
        return redirect(url_for("dashboard") + "#profile")

    if not full_name:
        flash("Full name cannot be empty.", "danger")
        return redirect(url_for("dashboard") + "#profile")

    db = get_db()
    db.execute(
        "UPDATE students SET full_name=?, branch=?, year=?, phone=?, cgpa=? WHERE id=?",
        (full_name, branch, year, phone, cgpa, current_user.id),
    )
    db.commit()
    flash("Profile updated successfully.", "success")
    return redirect(url_for("dashboard") + "#profile")


@app.route("/dashboard/coding", methods=["POST"])
@login_required
def update_coding():
    validate_csrf_token()

    def to_int(name):
        try:
            return max(0, int(request.form.get(name, 0)))
        except (ValueError, TypeError):
            return 0

    leetcode_solved      = to_int("leetcode_solved")
    codechef_rating      = to_int("codechef_rating")
    hackerrank_badges    = to_int("hackerrank_badges")
    github_repos         = to_int("github_repos")
    raw_dsa              = to_int("dsa_topics_completed")
    dsa_topics_completed = min(raw_dsa, 15)

    if raw_dsa > 15:
        flash("DSA topics capped at 15 (maximum).", "warning")

    db = get_db()
    db.execute(
        """UPDATE coding_progress
           SET leetcode_solved=?, codechef_rating=?, hackerrank_badges=?,
               github_repos=?, dsa_topics_completed=?, updated_at=?
           WHERE student_id=?""",
        (leetcode_solved, codechef_rating, hackerrank_badges, github_repos,
         dsa_topics_completed, datetime.now().isoformat(), current_user.id),
    )
    db.commit()
    flash("Coding progress updated.", "success")
    return redirect(url_for("dashboard") + "#coding")


@app.route("/dashboard/aptitude", methods=["POST"])
@login_required
def update_aptitude():
    validate_csrf_token()

    def to_score(name):
        try:
            return min(max(0, int(request.form.get(name, 0))), 100)
        except (ValueError, TypeError):
            return 0

    quant_score    = to_score("quant_score")
    logical_score  = to_score("logical_score")
    verbal_score   = to_score("verbal_score")
    try:
        mock_tests_taken = max(0, int(request.form.get("mock_tests_taken", 0)))
    except (ValueError, TypeError):
        mock_tests_taken = 0

    db = get_db()
    db.execute(
        """UPDATE aptitude_progress
           SET quant_score=?, logical_score=?, verbal_score=?, mock_tests_taken=?, updated_at=?
           WHERE student_id=?""",
        (quant_score, logical_score, verbal_score, mock_tests_taken,
         datetime.now().isoformat(), current_user.id),
    )
    db.commit()
    flash("Aptitude progress updated.", "success")
    return redirect(url_for("dashboard") + "#aptitude")


@app.route("/dashboard/resume/upload", methods=["POST"])
@login_required
def upload_resume():
    validate_csrf_token()
    file = request.files.get("resume")
    if not file or file.filename == "":
        flash("Please choose a PDF file to upload.", "danger")
        return redirect(url_for("dashboard") + "#resume")

    if not allowed_resume(file.filename):
        flash("Only PDF files are allowed.", "danger")
        return redirect(url_for("dashboard") + "#resume")

    original_name = secure_filename(file.filename)
    timestamp     = datetime.now().strftime("%Y%m%d%H%M%S")
    stored_name   = f"{current_user.id}_{timestamp}_{original_name}"
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], stored_name))

    db = get_db()
    db.execute(
        "INSERT INTO resumes (student_id, filename, original_filename, upload_date) VALUES (?,?,?,?)",
        (current_user.id, stored_name, original_name, datetime.now().isoformat()),
    )
    db.commit()
    flash("Resume uploaded successfully.", "success")
    return redirect(url_for("dashboard") + "#resume")


@app.route("/dashboard/resume/delete/<int:resume_id>", methods=["POST"])
@login_required
def delete_resume(resume_id):
    validate_csrf_token()
    db     = get_db()
    resume = db.execute(
        "SELECT * FROM resumes WHERE id = ? AND student_id = ?", (resume_id, current_user.id)
    ).fetchone()
    if resume:
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], resume["filename"])
        if os.path.exists(filepath):
            os.remove(filepath)
        db.execute("DELETE FROM resumes WHERE id = ?", (resume_id,))
        db.commit()
        flash("Resume deleted.", "info")
    else:
        flash("Resume not found.", "danger")
    return redirect(url_for("dashboard") + "#resume")


@app.route("/uploads/resumes/<path:filename>")
@login_required
def download_resume(filename):
    db       = get_db()
    owns_file = db.execute(
        "SELECT id FROM resumes WHERE filename = ? AND student_id = ?", (filename, current_user.id)
    ).fetchone()
    if not owns_file:
        abort(403)
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=False)


@app.route("/dashboard/apply/<int:company_id>", methods=["POST"])
@login_required
def apply_company(company_id):
    validate_csrf_token()
    db      = get_db()
    student = db.execute("SELECT * FROM students  WHERE id = ?", (current_user.id,)).fetchone()
    company = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()

    if not company:
        flash("Company not found.", "danger")
        return redirect(url_for("dashboard") + "#companies")

    if not is_eligible(student, company):
        flash(f"You are not eligible for {company['company_name']}.", "danger")
        return redirect(url_for("dashboard") + "#companies")

    if db.execute(
        "SELECT id FROM applications WHERE student_id = ? AND company_id = ?",
        (current_user.id, company_id),
    ).fetchone():
        flash(f"You've already applied to {company['company_name']}.", "warning")
        return redirect(url_for("dashboard") + "#companies")

    db.execute(
        "INSERT INTO applications (student_id, company_id, status, applied_date) VALUES (?,?,?,?)",
        (current_user.id, company_id, "Applied", datetime.now().isoformat()),
    )
    db.commit()
    flash(f"Applied to {company['company_name']} successfully!", "success")
    return redirect(url_for("dashboard") + "#companies")


@app.route("/dashboard/withdraw/<int:application_id>", methods=["POST"])
@login_required
def withdraw_application(application_id):
    validate_csrf_token()
    db      = get_db()
    app_row = db.execute(
        "SELECT * FROM applications WHERE id = ? AND student_id = ?", (application_id, current_user.id)
    ).fetchone()
    if app_row:
        db.execute("DELETE FROM applications WHERE id = ?", (application_id,))
        db.commit()
        flash("Application withdrawn.", "info")
    return redirect(url_for("dashboard") + "#applications")


# --------------------------------------------------------------------------
# Error handlers
# --------------------------------------------------------------------------
@app.errorhandler(400)
def bad_request(e):
    flash(str(e), "danger")
    return redirect(url_for("index"))


@app.errorhandler(403)
def forbidden(e):
    return render_template("index.html", error_message="403 — Access forbidden."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("index.html", error_message="404 — Page not found."), 404


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
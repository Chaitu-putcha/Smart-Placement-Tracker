"""
Smart Placement Tracker
========================
A placement management portal for B.Tech students to track CGPA, coding
practice, aptitude prep, resumes, and apply to eligible companies.

Tech stack: Flask + SQLite (raw sqlite3) + Flask-Login + Jinja2 + Bootstrap 5 + Chart.js

Run:
    pip install -r requirements.txt
    python app.py
Then open http://127.0.0.1:5000
"""

import os
import sqlite3
from datetime import datetime, date
from authlib.integrations.flask_client import OAuth
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, send_from_directory, abort, g
)
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "placement.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads", "resumes")
ALLOWED_RESUME_EXT = {"pdf"}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB resume upload cap

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-key-change-this-in-production"  # change before deploying
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
# Google OAuth
oauth = OAuth(app)

oauth.register(
    name='google',
    client_id='YOUR_GOOGLE_CLIENT_ID',
    client_secret='YOUR_GOOGLE_CLIENT_SECRET',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access your dashboard."
login_manager.login_message_category = "warning"


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
        password    TEXT NOT NULL,
        branch      TEXT NOT NULL DEFAULT 'CSE',
        year        TEXT NOT NULL DEFAULT '1st Year',
        cgpa        REAL NOT NULL DEFAULT 0,
        phone       TEXT,
        created_at  TEXT NOT NULL
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

    # Seed companies only if table is empty, so re-running the app never duplicates data
    count = cur.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    if count == 0:
        sample_companies = [
            ("TCS",          "Assistant System Engineer", 3.5,  6.0, "All",            "2026-07-10", "No active backlogs, all branches eligible"),
            ("Infosys",      "Systems Engineer",           3.6,  6.5, "All",            "2026-07-18", "Min 65% throughout academics"),
            ("Wipro",        "Project Engineer",           3.5,  6.0, "All",            "2026-07-22", "No standing arrears"),
            ("Cognizant",    "Programmer Analyst",         4.0,  6.5, "CSE,IT,ECE",     "2026-08-01", "CS/IT/ECE preferred"),
            ("Accenture",    "Associate Software Engineer",4.5,  6.5, "All",            "2026-08-05", "Strong communication skills required"),
            ("Amazon",       "SDE-1",                      18.0, 8.0, "CSE,IT",         "2026-08-12", "Strong DSA & problem solving"),
            ("Microsoft",    "Software Engineer",          24.0, 8.5, "CSE,IT,ECE",     "2026-08-20", "Excellent DSA, system design basics"),
            ("Google",       "APM/SWE Intern",             30.0, 8.5, "CSE,IT",         "2026-09-01", "Top-tier coding & CS fundamentals"),
            ("Zoho",         "Member Technical Staff",     6.0,  7.0, "CSE,IT,ECE,EEE", "2026-07-28", "Written test + multiple technical rounds"),
            ("Deloitte",     "Analyst",                    7.5,  7.0, "All",            "2026-08-08", "Good aptitude & analytical skills"),
            ("Capgemini",    "Analyst",                    4.0,  6.0, "All",            "2026-07-15", "No active backlogs"),
            ("IBM",          "Software Developer",         8.0,  7.0, "CSE,IT",         "2026-08-15", "Cloud & programming fundamentals"),
        ]
        cur.executemany(
            """INSERT INTO companies
               (company_name, role, package, min_cgpa, eligible_branches, drive_date, eligibility)
               VALUES (?,?,?,?,?,?,?)""",
            sample_companies,
        )
        conn.commit()

    conn.close()


# --------------------------------------------------------------------------
# Flask-Login user model
# --------------------------------------------------------------------------
class Student(UserMixin):
    """Thin wrapper around a `students` row so Flask-Login can track sessions."""

    def __init__(self, row):
        self.id = row["id"]
        self.full_name = row["full_name"]
        self.email = row["email"]
        self.branch = row["branch"]
        self.year = row["year"]
        self.cgpa = row["cgpa"]
        self.phone = row["phone"]


@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    row = db.execute("SELECT * FROM students WHERE id = ?", (user_id,)).fetchone()
    return Student(row) if row else None


# --------------------------------------------------------------------------
# Business-logic helpers
# --------------------------------------------------------------------------
def allowed_resume(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_RESUME_EXT


def calculate_readiness(student_row, coding_row, aptitude_row, resume_count):
    """
    Returns a dict with an overall placement-readiness percentage (0-100)
    and the weighted breakdown that makes it up:
        CGPA 25%  |  Coding 25%  |  Aptitude 25%  |  Resume 15%  |  Profile 10%
    """
    cgpa = student_row["cgpa"] or 0
    cgpa_score = min(cgpa / 10.0, 1.0) * 25

    leetcode = coding_row["leetcode_solved"] if coding_row else 0
    dsa_topics = coding_row["dsa_topics_completed"] if coding_row else 0
    coding_pct = min(((leetcode / 200.0) * 60 + (dsa_topics / 15.0) * 40), 100)
    coding_score = (coding_pct / 100.0) * 25

    quant = aptitude_row["quant_score"] if aptitude_row else 0
    logical = aptitude_row["logical_score"] if aptitude_row else 0
    verbal = aptitude_row["verbal_score"] if aptitude_row else 0
    apt_avg = (quant + logical + verbal) / 3.0
    aptitude_score = (apt_avg / 100.0) * 25

    resume_score = 15 if resume_count > 0 else 0

    filled = sum(1 for v in (student_row["phone"], student_row["branch"], student_row["year"]) if v)
    profile_score = (filled / 3.0) * 10

    overall = round(cgpa_score + coding_score + aptitude_score + resume_score + profile_score, 1)

    return {
        "overall": min(overall, 100),
        "cgpa_score": round(cgpa_score, 1),
        "coding_score": round(coding_score, 1),
        "aptitude_score": round(aptitude_score, 1),
        "resume_score": resume_score,
        "profile_score": round(profile_score, 1),
        "coding_pct": round(coding_pct, 1),
        "aptitude_pct": round(apt_avg, 1),
    }


def is_eligible(student_row, company_row):
    """A student is eligible if CGPA clears the bar and the branch is allowed."""
    if (student_row["cgpa"] or 0) < company_row["min_cgpa"]:
        return False
    allowed = company_row["eligible_branches"]
    if allowed == "All":
        return True
    allowed_list = [b.strip() for b in allowed.split(",")]
    return student_row["branch"] in allowed_list


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
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        branch = request.form.get("branch", "CSE")
        year = request.form.get("year", "1st Year")
        phone = request.form.get("phone", "").strip()
        cgpa_raw = request.form.get("cgpa", "0").strip()

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
        existing = db.execute("SELECT id FROM students WHERE email = ?", (email,)).fetchone()
        if existing:
            errors.append("An account with this email already exists.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("register.html", form=request.form)

        hashed_pw = generate_password_hash(password)
        cur = db.execute(
            """INSERT INTO students (full_name, email, password, branch, year, cgpa, phone, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (full_name, email, hashed_pw, branch, year, cgpa, phone, datetime.now().isoformat()),
        )
        student_id = cur.lastrowid
        # Seed empty progress rows so later dashboard reads/upserts are simple
        db.execute("INSERT INTO coding_progress (student_id, updated_at) VALUES (?, ?)",
                   (student_id, datetime.now().isoformat()))
        db.execute("INSERT INTO aptitude_progress (student_id, updated_at) VALUES (?, ?)",
                   (student_id, datetime.now().isoformat()))
        db.commit()

        flash("Account created successfully! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", form={})

@app.route('/login/google')
def google_login():
    redirect_uri = url_for('google_authorize', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route('/authorize/google')
def google_authorize():
    token = oauth.google.authorize_access_token()
    user_info = token.get('userinfo')

    flash(f"Welcome {user_info['name']}", "success")

    return redirect(url_for('dashboard'))
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = get_db()
        row = db.execute("SELECT * FROM students WHERE email = ?", (email,)).fetchone()

        if row and check_password_hash(row["password"], password):
            login_user(Student(row), remember=bool(request.form.get("remember")))
            flash(f"Welcome back, {row['full_name'].split(' ')[0]}!", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    student = db.execute("SELECT * FROM students WHERE id = ?", (current_user.id,)).fetchone()
    coding = db.execute("SELECT * FROM coding_progress WHERE student_id = ?", (current_user.id,)).fetchone()
    aptitude = db.execute("SELECT * FROM aptitude_progress WHERE student_id = ?", (current_user.id,)).fetchone()
    resumes = db.execute(
        "SELECT * FROM resumes WHERE student_id = ? ORDER BY upload_date DESC", (current_user.id,)
    ).fetchall()
    companies = db.execute("SELECT * FROM companies ORDER BY drive_date ASC").fetchall()
    applications = db.execute(
        """SELECT applications.*, companies.company_name, companies.role, companies.package
           FROM applications JOIN companies ON applications.company_id = companies.id
           WHERE applications.student_id = ? ORDER BY applications.applied_date DESC""",
        (current_user.id,),
    ).fetchall()
    applied_company_ids = {a["company_id"] for a in applications}

    readiness = calculate_readiness(student, coding, aptitude, len(resumes))

    eligible_companies = [c for c in companies if is_eligible(student, c)]

    status_counts = {"Applied": 0, "Shortlisted": 0, "Selected": 0, "Rejected": 0}
    for a in applications:
        status_counts[a["status"]] = status_counts.get(a["status"], 0) + 1

    chart_data = {
        "readiness": readiness["overall"],
        "radar": {
            "labels": ["CGPA", "Coding", "Aptitude", "Resume", "Profile"],
            "values": [
                round((readiness["cgpa_score"] / 25) * 100, 1),
                round((readiness["coding_score"] / 25) * 100, 1),
                round((readiness["aptitude_score"] / 25) * 100, 1),
                round((readiness["resume_score"] / 15) * 100, 1),
                round((readiness["profile_score"] / 10) * 100, 1),
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


@app.route("/dashboard/profile", methods=["POST"])
@login_required
def update_profile():
    full_name = request.form.get("full_name", "").strip()
    branch = request.form.get("branch", "CSE")
    year = request.form.get("year", "1st Year")
    phone = request.form.get("phone", "").strip()
    cgpa_raw = request.form.get("cgpa", "0").strip()

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
    def to_int(name):
        try:
            return max(0, int(request.form.get(name, 0)))
        except (ValueError, TypeError):
            return 0

    leetcode_solved = to_int("leetcode_solved")
    codechef_rating = to_int("codechef_rating")
    hackerrank_badges = to_int("hackerrank_badges")
    github_repos = to_int("github_repos")
    dsa_topics_completed = min(to_int("dsa_topics_completed"), 15)

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
    def to_score(name):
        try:
            return min(max(0, int(request.form.get(name, 0))), 100)
        except (ValueError, TypeError):
            return 0

    quant_score = to_score("quant_score")
    logical_score = to_score("logical_score")
    verbal_score = to_score("verbal_score")
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
    file = request.files.get("resume")
    if not file or file.filename == "":
        flash("Please choose a PDF file to upload.", "danger")
        return redirect(url_for("dashboard") + "#resume")

    if not allowed_resume(file.filename):
        flash("Only PDF files are allowed.", "danger")
        return redirect(url_for("dashboard") + "#resume")

    original_name = secure_filename(file.filename)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    stored_name = f"{current_user.id}_{timestamp}_{original_name}"
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
    db = get_db()
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
    db = get_db()
    owns_file = db.execute(
        "SELECT id FROM resumes WHERE filename = ? AND student_id = ?", (filename, current_user.id)
    ).fetchone()
    if not owns_file:
        abort(403)
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=False)


@app.route("/dashboard/apply/<int:company_id>", methods=["POST"])
@login_required
def apply_company(company_id):
    db = get_db()
    student = db.execute("SELECT * FROM students WHERE id = ?", (current_user.id,)).fetchone()
    company = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()

    if not company:
        flash("Company not found.", "danger")
        return redirect(url_for("dashboard") + "#companies")

    if not is_eligible(student, company):
        flash(f"You are not eligible for {company['company_name']}.", "danger")
        return redirect(url_for("dashboard") + "#companies")

    already_applied = db.execute(
        "SELECT id FROM applications WHERE student_id = ? AND company_id = ?",
        (current_user.id, company_id),
    ).fetchone()
    if already_applied:
        flash(f"You have already applied to {company['company_name']}.", "warning")
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
    db = get_db()
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
@app.errorhandler(403)
def forbidden(e):
    return render_template("index.html", error_message="403 - Access forbidden."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("index.html", error_message="404 - Page not found."), 404


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)

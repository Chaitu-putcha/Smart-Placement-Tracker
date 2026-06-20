# 🎯 Smart Placement Tracker

A full-stack placement management portal for B.Tech students — track CGPA, coding/aptitude prep, resumes, and apply to eligible companies, with a live readiness score and analytics dashboard.

**Stack:** Flask · SQLite · Flask-Login · Bootstrap 5 · Chart.js · Vanilla JS

---

## ✨ Features

- Landing page, registration, login/logout (hashed passwords via Werkzeug)
- Dashboard with 8 sections: Overview, Profile, Coding Tracker, Aptitude Tracker, Resume, Companies, Applications, Analytics
- **Placement Readiness %** — live score computed from CGPA, coding progress, aptitude scores, resume status, and profile completeness
- **Company Eligibility Checker** — auto-flags which companies you qualify for based on CGPA + branch
- Resume upload (PDF, 5MB limit) with ownership-protected download/delete
- Apply / withdraw from company drives, with duplicate-application protection
- Search + "eligible only" filter for companies (instant, client-side)
- Analytics: skill radar chart, eligibility doughnut chart, application status bar chart (Chart.js)
- Dark mode toggle (persisted via localStorage, no flash-of-wrong-theme)
- Fully responsive (mobile, tablet, desktop)

---

## 📁 Project Structure

```
SmartPlacementTracker/
│
├── app.py                  # Flask backend (routes, auth, DB logic)
├── placement.db             # SQLite DB — auto-created on first run
├── requirements.txt
│
├── templates/
│   ├── index.html            # Landing page
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html        # Main dashboard (all 8 tabs)
│   ├── _navbar.html          # Shared navbar partial
│   ├── _flashes.html         # Shared flash-message partial
│   └── _theme_init.html      # Dark-mode init script partial
│
├── static/
│   ├── css/style.css
│   ├── js/
│   │   ├── theme.js           # Dark mode toggle
│   │   └── dashboard.js       # Tabs, charts, filters, upload UI
│   └── images/
│
└── uploads/
    └── resumes/              # Uploaded PDF resumes land here
```

---

## 🚀 Setup Instructions

### 1. Prerequisites
- Python 3.9+ installed

### 2. Get the project
Unzip the project folder and open a terminal inside it.

### 3. Create a virtual environment (recommended)
```bash
python -m venv venv

# Activate it:
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
```

### 4. Install dependencies
```bash
pip install -r requirements.txt
```

### 5. Run the app
```bash
python app.py
```
The first run automatically creates `placement.db`, all 6 tables, and seeds 12 sample companies (TCS, Infosys, Amazon, Microsoft, Google, etc.).

### 6. Open in browser
```
http://127.0.0.1:5000
```

### 7. Try it out
1. Click **Register** → create a student account.
2. Log in → you'll land on the **Dashboard**.
3. Update your **Coding** and **Aptitude** progress, set your CGPA in **Profile**.
4. Watch the **Readiness Ring** on Overview update live.
5. Go to **Companies** → search/filter → **Apply** to any company you're eligible for.
6. Check **Analytics** for your skill radar and application charts.
7. Try the 🌙 **dark mode** toggle in the navbar.

---

## ⚙️ Configuration Notes

- **Secret key:** `app.py` uses a placeholder `SECRET_KEY`. Before deploying anywhere public, change it to a long random string (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`).
- **Database resets:** Delete `placement.db` and restart the app to get a fresh seeded database.
- **Resume limit:** PDFs only, max 5MB (configurable in `app.py` via `MAX_CONTENT_LENGTH`).
- **Debug mode:** `app.run(debug=True)` is fine for development/demo. Turn it off (`debug=False`) before any real deployment.

---

## 🧮 How Readiness % Is Calculated

| Component | Weight | Basis |
|---|---|---|
| CGPA | 25% | `cgpa / 10` |
| Coding | 25% | LeetCode solved (60%) + DSA topics completed (40%) |
| Aptitude | 25% | Average of Quant, Logical, Verbal scores |
| Resume | 15% | Full credit if at least one resume is uploaded |
| Profile completeness | 10% | Phone, branch, and year filled in |

---

## 🗄️ Database Schema

- **students** — id, full_name, email, password (hashed), branch, year, cgpa, phone, created_at
- **coding_progress** — student_id, leetcode_solved, codechef_rating, hackerrank_badges, github_repos, dsa_topics_completed
- **aptitude_progress** — student_id, quant_score, logical_score, verbal_score, mock_tests_taken
- **resumes** — student_id, filename, original_filename, upload_date
- **companies** — company_name, role, package, min_cgpa, eligible_branches, drive_date, eligibility
- **applications** — student_id, company_id, status, applied_date

---

## 🛠️ Built With

Flask 3 · Flask-Login · Werkzeug · SQLite3 (raw, no ORM) · Bootstrap 5.3 · Bootstrap Icons · Chart.js 4 · Google Fonts (Sora, Inter, JetBrains Mono)

---

## 📌 Ideal Use Case

Built as a portfolio-ready, resume-worthy project for Final Year B.Tech CSE students — demonstrating full-stack development, authentication, file handling, data visualization, and clean UI/UX in a single cohesive application.

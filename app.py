# app.py
import json
import uuid
from pathlib import Path
from datetime import datetime, date, timedelta
import streamlit as st
import sqlite3
from passlib.hash import bcrypt
import secrets as pysecrets
import requests
from urllib.parse import urlencode
import speech_recognition as sr  # optional; requires PyAudio
import matplotlib.pyplot as plt
import pandas as pd
import base64
import random

# ---------------------- Config ----------------------
st.set_page_config(
    page_title="Simple To-Do App",
    page_icon="✅",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ---------------------- Paths & DB ----------------------
DATA_PATH = Path(__file__).parent / "data" / "todos.json"
DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(__file__).parent / "data" / "app.db"

USE_DB = True

# ---------------------- DB helpers ----------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            password_hash TEXT,
            provider TEXT NOT NULL DEFAULT 'local',
            points INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            last_complete_date TEXT,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            desc TEXT,
            due TEXT,
            priority TEXT,
            category TEXT,
            done INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------------- Styling ----------------------
st.markdown("""
    <style>
    header {visibility:hidden;}
    footer {visibility:hidden;}
    .glass { background: rgba(255,255,255,0.85); border-radius: 12px; padding: 14px; box-shadow: 0 6px 24px rgba(16,24,40,0.06); }
    </style>
""", unsafe_allow_html=True)

# ---------------------- Utilities ----------------------
def safe_rerun():
    try:
        st.experimental_rerun()
    except Exception:
        pass

# ---------------------- Mock extras ----------------------
def random_quote():
    quotes = [
        "The only way to do great work is to love what you do. - Steve Jobs",
        "Productivity is never an accident. It is always the result of a commitment to excellence.",
        "Your time is limited, so don't waste it living someone else's life. - Steve Jobs",
    ]
    return random.choice(quotes)

def fake_weather():
    return random.choice(["☀️ Sunny, 25°C","🌧️ Rainy, 22°C","🌤️ Partly Cloudy, 24°C"]) 

# ---------------------- Auth / User helpers ----------------------

def get_user_by_email(email: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def create_user(name: str, email: str, password: str | None, provider: str = "local"):
    conn = get_conn()
    cur = conn.cursor()
    pwhash = bcrypt.hash(password) if password else None
    cur.execute(
        "INSERT INTO users (email, name, password_hash, provider, created_at) VALUES (?, ?, ?, ?, ?)",
        (email.lower().strip(), name.strip(), pwhash, provider, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return user_id


def login_local(email: str, password: str):
    user = get_user_by_email(email)
    if not user:
        return None, "No account found for that email."
    if user["provider"] != "local":
        return None, "This email is registered via Google. Use 'Continue with Google'."
    if not bcrypt.verify(password, user["password_hash"]):
        return None, "Incorrect password."
    return user, None

# ---------------------- Data layer ----------------------

def load_tasks():
    if USE_DB and st.session_state.get("user"):
        uid = st.session_state["user"]["id"]
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM tasks WHERE user_id = ? ORDER BY created_at ASC", (uid,))
        rows = cur.fetchall()
        conn.close()
        tasks = []
        for r in rows:
            d = dict(r)
            d["done"] = bool(d["done"])
            tasks.append(d)
        return tasks
    # fallback JSON
    if DATA_PATH.exists():
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_tasks_json(tasks):
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)

# ---------------------- Task operations ----------------------

def add_task(title, desc, due, priority, category):
    if priority in (None, "Auto"):
        priority = suggest_priority_by_due(due)
    task_id = str(uuid.uuid4())
    if USE_DB and st.session_state.get("user"):
        uid = st.session_state["user"]["id"]
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tasks (id, user_id, title, desc, due, priority, category, done, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id, uid, title.strip(), desc.strip(),
                due.isoformat() if isinstance(due, (date, datetime)) else None,
                priority, category, 0, datetime.now().isoformat(timespec="seconds")
            )
        )
        conn.commit()
        conn.close()
        return {"id": task_id}
    # json fallback
    tasks = load_tasks()
    new_task = {
        "id": task_id,
        "title": title.strip(),
        "desc": desc.strip(),
        "due": due.isoformat() if isinstance(due, (date, datetime)) else None,
        "priority": priority,
        "category": category,
        "done": False,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "completed_at": None
    }
    tasks.append(new_task)
    save_tasks_json(tasks)
    return new_task


def update_task(task_id, **updates):
    if USE_DB and st.session_state.get("user"):
        uid = st.session_state["user"]["id"]
        if "done" in updates:
            updates["done"] = 1 if bool(updates["done"]) else 0
            if updates["done"] == 1:
                updates["completed_at"] = datetime.now().isoformat(timespec="seconds")
        sets = ", ".join([f"{k} = ?" for k in updates.keys()])
        vals = list(updates.values()) + [task_id, uid]
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(f"UPDATE tasks SET {sets} WHERE id = ? AND user_id = ?", vals)
        conn.commit()
        # gamify when completed
        if "done" in updates and updates["done"] == 1:
            cur.execute("SELECT points, streak, last_complete_date FROM users WHERE id = ?", (uid,))
            row = cur.fetchone()
            points = row["points"] if row else 0
            streak = row["streak"] if row else 0
            last = row["last_complete_date"] if row else None
            today_str = date.today().isoformat()
            last_date = None
            if last:
                try:
                    last_date = datetime.fromisoformat(last).date()
                except Exception:
                    last_date = None
            cur.execute("SELECT priority FROM tasks WHERE id = ? AND user_id = ?", (task_id, uid))
            pr = cur.fetchone()
            prio = pr["priority"] if pr else "Medium"
            bonus = {"High":5,"Medium":2,"Low":0}.get(prio,0)
            points += 10 + bonus
            if last_date == date.today() - timedelta(days=1):
                streak = (streak or 0) + 1
            elif last_date == date.today():
                pass
            else:
                streak = 1
            cur.execute("UPDATE users SET points = ?, streak = ?, last_complete_date = ? WHERE id = ?",
                        (points, streak, today_str, uid))
            conn.commit()
        conn.close()
        return
    # json fallback
    tasks = load_tasks()
    for t in tasks:
        if t["id"] == task_id:
            prev_done = t.get("done", False)
            t.update(**updates)
            if updates.get("done") and not prev_done:
                t["completed_at"] = datetime.now().isoformat(timespec="seconds")
    save_tasks_json(tasks)


def delete_task(task_id):
    if USE_DB and st.session_state.get("user"):
        uid = st.session_state["user"]["id"]
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, uid))
        conn.commit()
        conn.close()
        return
    tasks = load_tasks()
    tasks = [t for t in tasks if t["id"] != task_id]
    save_tasks_json(tasks)

# ---------------------- Helpers ----------------------

def suggest_priority_by_due(due):
    if not due:
        return "Low"
    today = date.today()
    if isinstance(due, str):
        try:
            due_dt = datetime.fromisoformat(due).date()
        except Exception:
            return "Low"
    elif isinstance(due, datetime):
        due_dt = due.date()
    elif isinstance(due, date):
        due_dt = due
    else:
        return "Low"
    delta = (due_dt - today).days
    if delta <= 0:
        return "High"
    if delta <= 3:
        return "Medium"
    return "Low"

def priority_badge(p):
    mapping = {"High": "🔴 High", "Medium": "🟠 Medium", "Low": "🟢 Low"}
    return mapping.get(p, p)

def status_badge(done):
    return "✅ Done" if done else "🕒 Pending"

def category_badge(c):
    mapping = {"Work": "💼 Work", "Personal": "🏠 Personal", "Shopping": "🛒 Shopping", "Other": "📌 Other"}
    return mapping.get(c, c)

# ---------------------- Voice capture (optional) ----------------------

def parse_voice_text_for_task(text: str):
    txt = text.strip()
    txt_low = txt.lower()
    suggested_priority = None
    due = None
    if "high priority" in txt_low or "urgent" in txt_low:
        suggested_priority = "High"
    elif "low priority" in txt_low or "low" in txt_low:
        suggested_priority = "Low"
    if "tomorrow" in txt_low:
        due = date.today() + timedelta(days=1)
        title = txt.replace("tomorrow", "").strip()
        return title or txt, due, suggested_priority
    import re
    m = re.search(r"in (\d+) days?", txt_low)
    if m:
        n = int(m.group(1))
        due = date.today() + timedelta(days=n)
        title = re.sub(r"in \d+ days?", "", txt, flags=re.I).strip()
        return title or txt, due, suggested_priority
    return txt, None, suggested_priority


def capture_voice_input():
    try:
        r = sr.Recognizer()
        with sr.Microphone() as source:
            st.info("Listening... speak now (5 sec max).")
            audio = r.listen(source, phrase_time_limit=5)
        try:
            text = r.recognize_google(audio)
            st.success("Recognized: " + text)
            return text
        except sr.UnknownValueError:
            st.error("Could not understand audio")
        except sr.RequestError as e:
            st.error("Speech service error: " + str(e))
    except Exception as e:
        st.error(f"Microphone access error: {e}")
    return None

# ---------------------- Analytics ----------------------

def compute_analytics(tasks):
    if not tasks:
        return {"weekly": {}, "categories": {}, "avg_completion_hours": None}
    df = pd.DataFrame(tasks)
    if "completed_at" in df.columns:
        df["completed_at"] = pd.to_datetime(df["completed_at"], errors="coerce")
    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    comp = df.dropna(subset=["completed_at"]) if "completed_at" in df.columns else pd.DataFrame()
    if comp.empty:
        weekly = {}
    else:
        comp["week"] = comp["completed_at"].dt.strftime("%Y-W%V")
        weekly = comp.groupby("week").size().to_dict()
    categories = df["category"].fillna("Other").value_counts().to_dict() if "category" in df.columns else {}
    avg_hours = None
    if not comp.empty:
        diffs = (comp["completed_at"] - comp["created_at"]).dt.total_seconds() / 3600.0
        avg_hours = float(diffs.mean())
    return {"weekly": weekly, "categories": categories, "avg_completion_hours": avg_hours}

# ---------------------- Google Sheets helpers (kept simple) ----------------------

def gspread_available():
    try:
        _ = st.secrets["gspread"]
        return "service_account_json" in st.secrets["gspread"] and "sheet_name" in st.secrets["gspread"]
    except Exception:
        return False

# ---------------------- UI: Authentication ----------------------

def render_auth():
    st.markdown('<div class="glass">', unsafe_allow_html=True)
    st.title("🔐 Sign in to To-Do")
    tabs = st.tabs(["Login", "Sign up"])
    with tabs[0]:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in")
        if submitted:
            user, err = login_local(email, password)
            if err:
                st.error(err)
            else:
                st.session_state["user"] = {"id": user["id"], "email": user["email"], "name": user["name"], "provider": user["provider"]}
                st.success(f"Welcome back, {user['name']}!")
                safe_rerun()
    with tabs[1]:
        with st.form("signup_form"):
            name = st.text_input("Name")
            email = st.text_input("Email")
            pw1 = st.text_input("Password", type="password")
            pw2 = st.text_input("Confirm Password", type="password")
            submitted = st.form_submit_button("Create account")
        if submitted:
            if not name.strip() or not email.strip() or not pw1.strip():
                st.warning("Please fill all fields.")
            elif pw1 != pw2:
                st.warning("Passwords do not match.")
            elif get_user_by_email(email):
                st.error("An account with that email already exists.")
            else:
                _ = create_user(name=name, email=email, password=pw1, provider="local")
                st.success("Account created! You can log in now.")
    st.markdown('</div>', unsafe_allow_html=True)

# If not authenticated -> show auth and stop
if "user" not in st.session_state:
    render_auth()
    st.stop()

# ---------------------- Top Navigation ----------------------
cols = st.columns([1,6,1])
with cols[0]:
    st.image("https://api.iconify.design/mdi/check-circle-outline.svg?color=%232E86AB", width=36)
with cols[1]:
    st.markdown(f"<div style='display:flex;align-items:center;gap:12px;'>"
                f"<h2 style='margin:0'>✅ Simple To-Do</h2>"
                f"<div style='color:#666;margin-left:8px;'>Smart • Voice • Analytics • Sync</div>"
                f"</div>", unsafe_allow_html=True)
    page = st.radio("", ["Tasks","Create Task","Analytics","Settings"], horizontal=True, key="top_page")
with cols[2]:
    st.markdown(f"<div style='text-align:right'>👋 <b>{st.session_state['user']['name']}</b><br/>{st.session_state['user']['email']}</div>", unsafe_allow_html=True)
    if st.button("Logout"):
        for k in ("user", "oauth_state"):
            if k in st.session_state:
                del st.session_state[k]
        safe_rerun()

# ---------------------- Page: Tasks ----------------------
if page == "Tasks":
    st.markdown('<div class="glass" style="margin-bottom:12px;">', unsafe_allow_html=True)
    st.header("📋 Your Tasks")
    st.write("View and manage your tasks. Use the 'Create Task' page to add new ones.")
    st.markdown('</div>', unsafe_allow_html=True)

    tasks = load_tasks()
    done_count = sum(1 for t in tasks if t.get("done")) if tasks else 0
    if tasks:
        st.progress(done_count / len(tasks))
        st.caption(f"{done_count}/{len(tasks)} tasks completed")
    # filters
    q = st.text_input("Search", placeholder="Search title/description...", key="tasks_search")
    status_filter = st.selectbox("Status", ["All","Pending","Done"], key="tasks_status")
    priority_filter = st.selectbox("Priority", ["All","High","Medium","Low"], key="tasks_prio")
    category_filter = st.selectbox("Category", ["All","Work","Personal","Shopping","Other"], key="tasks_cat")

    def task_matches(t):
        if q:
            ql = q.lower()
            if ql not in (t.get("title","") or "").lower() and ql not in (t.get("desc","") or "").lower():
                return False
        if status_filter != "All":
            want_done = (status_filter == "Done")
            if t.get("done") != want_done:
                return False
        if priority_filter != "All" and (t.get("priority") or "") != priority_filter:
            return False
        if category_filter != "All" and (t.get("category") or "Other") != category_filter:
            return False
        return True

    filtered = [t for t in tasks if task_matches(t)]
    st.markdown(f"**{len(filtered)}** task(s) shown")

    if not filtered:
        st.info("No tasks match your filters yet. Add one from the Create Task page!")
    else:
        for t in filtered:
            st.markdown('<div class="glass" style="padding:10px; margin-bottom:8px;">', unsafe_allow_html=True)
            cols = st.columns([0.06, 1.6, 0.9, 0.8, 0.8, 0.6, 0.6])
            with cols[0]:
                toggled = st.checkbox("", value=t.get("done", False), key=f"done_{t['id']}")
                if toggled != t.get("done", False):
                    update_task(t["id"], done=toggled)
                    if toggled:
                        st.success("Nice! + points earned 🎉")
                    safe_rerun()
            with cols[1]:
                st.subheader(t.get("title","(untitled)"))
                st.caption(t.get("desc") or "—")
            with cols[2]:
                due_fmt = "—"
                if t.get("due"):
                    try:
                        due_dt = datetime.fromisoformat(t["due"]).date()
                        due_fmt = due_dt.strftime("%b %d, %Y")
                    except Exception:
                        due_fmt = t["due"]
                st.write(f"📅 **{due_fmt}**")
            with cols[3]:
                st.write(priority_badge(t.get("priority","Medium")))
            with cols[4]:
                st.write(category_badge(t.get("category","Other")))
            with cols[5]:
                st.write(status_badge(t.get("done", False)))
            with cols[6]:
                if st.button("✏️ Edit", key=f"edit_{t['id']}"):
                    with st.form(f"edit_form_{t['id']}"):
                        new_title = st.text_input("Title", value=t.get("title",""))
                        new_desc = st.text_area("Description", value=t.get("desc") or "")
                        current_due = None
                        if t.get("due"):
                            try:
                                current_due = datetime.fromisoformat(t["due"]).date()
                            except Exception:
                                current_due = date.today()
                        no_due = st.checkbox("No due date", value=(current_due is None))
                        new_due = None if no_due else st.date_input("Due date", value=current_due or date.today())
                        new_priority = st.selectbox("Priority", ["High","Medium","Low"], index=["High","Medium","Low"].index(t.get("priority","Medium")))
                        new_category = st.selectbox("Category", ["Work","Personal","Shopping","Other"], index=["Work","Personal","Shopping","Other"].index(t.get("category","Other")))
                        save = st.form_submit_button("Save changes")
                    if save:
                        update_task(t["id"],
                                    title=new_title.strip(),
                                    desc=new_desc.strip(),
                                    due=new_due.isoformat() if isinstance(new_due, date) else None,
                                    priority=new_priority,
                                    category=new_category)
                        st.success("Task updated!")
                        safe_rerun()
            if st.button("🗑️ Delete", key=f"del_{t['id']}"):
                delete_task(t["id"])
                st.warning("Task deleted")
                safe_rerun()
            st.markdown('</div>', unsafe_allow_html=True)

# ---------------------- Page: Create Task ----------------------
elif page == "Create Task":
    st.markdown('<div class="glass" style="margin-bottom:12px;">', unsafe_allow_html=True)
    st.header("➕ Create a Task")
    st.write("Add new tasks, use voice capture or fill the form below.")
    st.markdown('</div>', unsafe_allow_html=True)

    # voice capture quick block
    if st.button("Start voice capture (experimental)"):
        text = capture_voice_input()
        if text:
            title, due_s, prio_s = parse_voice_text_for_task(text)
            st.session_state["_voice_parsed"] = {"title": title, "due": due_s.isoformat() if due_s else None, "priority": prio_s}
            st.success("Parsed voice into draft. Fill details and submit.")

    if "_voice_parsed" in st.session_state:
        vp = st.session_state["_voice_parsed"]
        st.info(f"Draft from voice: {vp.get('title')}")

    with st.form("create_task_form", clear_on_submit=True):
        title = st.text_input("Title", value=(st.session_state.get("_voice_parsed",{}) or {}).get("title", ""))
        desc = st.text_area("Description", value="")
        no_due = st.checkbox("No due date", value=True)
        due_widget = None if no_due else st.date_input("Due date", value=date.today())
        priority_options = ["Auto", "High", "Medium", "Low"]
        priority_sel = st.selectbox("Priority", priority_options, index=0)
        priority = None if priority_sel == "Auto" else priority_sel
        category = st.selectbox("Category", ["Work","Personal","Shopping","Health","Other"], index=0)
        submitted = st.form_submit_button("Add Task")
    if submitted:
        if not title.strip():
            st.warning("Please enter a title")
        else:
            add_task(title, desc, None if no_due else due_widget, priority, category)
            st.success("Task added ✅")
            if "_voice_parsed" in st.session_state:
                del st.session_state["_voice_parsed"]
            safe_rerun()

# ---------------------- Page: Analytics ----------------------
elif page == "Analytics":
    st.header("📊 Analytics Dashboard")
    analytics_tasks = load_tasks()
    analytics = compute_analytics(analytics_tasks)
    if analytics["weekly"]:
        weeks = sorted(analytics["weekly"].items())
        labels = [w for w,_ in weeks]
        values = [v for _,v in weeks]
        fig, ax = plt.subplots(figsize=(6,2.5))
        ax.bar(labels, values)
        ax.set_title("Tasks completed per week")
        ax.set_ylabel("Completed")
        ax.tick_params(axis='x', rotation=45)
        st.pyplot(fig)
    else:
        st.info("No completed tasks yet to show weekly chart.")
    if analytics["categories"]:
        cat_labels = list(analytics["categories"].keys())
        cat_vals = list(analytics["categories"].values())
        fig2, ax2 = plt.subplots(figsize=(4,3))
        ax2.pie(cat_vals, labels=cat_labels, autopct='%1.1f%%', startangle=140)
        ax2.axis('equal')
        st.pyplot(fig2)
    else:
        st.info("No category data yet.")
    if analytics["avg_completion_hours"] is not None:
        st.metric("Average completion time (hours)", f"{analytics['avg_completion_hours']:.2f}")
    else:
        st.info("Average completion time not available (no completed tasks).")
    # CSV export
    if analytics_tasks:
        df = pd.DataFrame(analytics_tasks)
        csv = df.to_csv(index=False)
        st.download_button(label="⬇️ Download tasks CSV", data=csv, file_name="tasks_export.csv", mime="text/csv")

# ---------------------- Page: Settings ----------------------
# ---------------------- Page: Settings ----------------------
elif page == "Settings":
    st.header("⚙️ Settings & Sync")
    st.write("Manage sync, export data, and view gamification stats.")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT points, streak FROM users WHERE id = ?", (st.session_state["user"]["id"],))
    row = cur.fetchone()
    conn.close()
    points = row["points"] if row else 0
    streak = row["streak"] if row else 0
    st.metric("⭐ Points", points)
    st.metric("🔥 Streak (days)", streak)

    # ✅ Add this block to compute completed tasks
    tasks = load_tasks()
    done_count = sum(1 for t in tasks if t.get("done")) if tasks else 0

    st.subheader("Google Sheets Sync")
    if gspread_available():
        if st.button("Upload tasks to Google Sheets"):
            st.info("Uploading... (see console if long)")
            try:
                from types import SimpleNamespace
                st.success("Upload routine not implemented in this simplified release. Add your gspread logic.")
            except Exception:
                st.error("Failed to upload: gspread logic missing.")
    else:
        st.info("Add gspread credentials to .streamlit/secrets.toml to enable sync.")

    st.subheader("Export / Backup")
    st.download_button(
        label="⬇️ Export Tasks as JSON",
        data=json.dumps(tasks, indent=2),
        file_name="tasks.json",
        mime="application/json"
    )

    st.subheader("Motivation & Extras")
    st.info(random_quote())
    st.write("🌦️ Today's Weather — ", fake_weather())

    st.subheader("Badges")
    badges = []
    if points >= 100:
        badges.append("🏅 Productivity Master (100+ pts)")
    if streak >= 7:
        badges.append("🔥 7-day streak")
    if done_count >= 50:
        badges.append("🎯 Closer to target (50+ tasks completed)")
    if not badges:
        badges.append("🙂 Keep going — complete tasks to earn badges!")
    for b in badges:
        st.write("- " + b)
    
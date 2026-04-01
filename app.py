import json
import logging
import os
import sqlite3
from datetime import date, timedelta, datetime
from functools import wraps

from flask import Flask, g, redirect, render_template, request, session
from google import genai
from werkzeug.routing import BaseConverter
from werkzeug.security import check_password_hash, generate_password_hash


class IntegerConverter(BaseConverter):
    def __init__(self, map, *args, **kwargs):
        super().__init__(map)
        self.regex = r"-?\d+"


DATABASE = os.environ.get("DATABASE_PATH", "database.db")


def get_required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def create_genai_client():
    api_key = os.environ.get("GOOGLE_GENAI_API_KEY")
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


client = create_genai_client()

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
app.secret_key = get_required_env("FLASK_SECRET_KEY")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_SECURE_COOKIES", "true").lower() == "true",
)
app.jinja_env.add_extension("jinja2.ext.do")
app.url_map.converters["int"] = IntegerConverter


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv


def execute_db(query, args=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(query, args)
    conn.commit()
    cur.close()


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function


@app.route("/")
@login_required
def sigma():
    return redirect("/0")


@app.route("/<int:extra>")
@login_required
def index(extra):
    extra = int(extra)
    today = date.today() + timedelta(weeks=extra)
    monday = today - timedelta(days=today.weekday())
    week_dates = [monday + timedelta(days=i) for i in range(7)]
    user = query_db("SELECT * FROM users WHERE id = ?", (session["user_id"],), one=True)
    stored_periods = query_db("SELECT * FROM periods WHERE owner_id = ?", (session["user_id"],))
    generated_periods = []

    def add_period_if_in_week(period_id, start, end, name, color, repeat_start, repeat_end):
        if (
            monday <= start.date() < monday + timedelta(weeks=1)
            and (not repeat_start or repeat_start <= start.date())
            and (not repeat_end or repeat_end >= start.date())
        ):
            generated_periods.append(
                {
                    "id": period_id,
                    "period_name": name,
                    "start_time": start.strftime("%Y-%m-%d %H:%M"),
                    "end_time": end.strftime("%Y-%m-%d %H:%M"),
                    "color": color,
                }
            )

    for period in stored_periods:
        period_id = period["id"]
        color = period["color"]
        start_dt = datetime.strptime(period["start_time"], "%Y-%m-%dT%H:%M")
        end_dt = datetime.strptime(period["end_time"], "%Y-%m-%dT%H:%M")
        repeat = period["repeat"]
        repeat_start_dt = (
            datetime.strptime(period["repeat_start"], "%Y-%m-%dT%H:%M")
            if period["repeat_start"]
            else None
        )
        repeat_end_dt = (
            datetime.strptime(period["repeat_end"], "%Y-%m-%dT%H:%M")
            if period["repeat_end"]
            else None
        )

        add_period_if_in_week(
            period_id,
            start_dt,
            end_dt,
            period["period_name"],
            color,
            repeat_start_dt,
            repeat_end_dt,
        )

        if repeat == "daily":
            original_start_time = start_dt.time()
            original_end_time = end_dt.time()
            for day_offset in range(7):
                repeat_day = (
                    monday + timedelta(days=day_offset)
                    if monday + timedelta(days=day_offset) > start_dt.date()
                    else start_dt.date()
                )
                new_start = datetime.combine(repeat_day, original_start_time)
                new_end = datetime.combine(repeat_day, original_end_time)
                add_period_if_in_week(
                    period_id,
                    new_start,
                    new_end,
                    period["period_name"],
                    color,
                    repeat_start_dt,
                    repeat_end_dt,
                )

        elif repeat == "weekly":
            original_weekday = start_dt.weekday()
            current_monday_weekday = monday.weekday()
            days_difference = original_weekday - current_monday_weekday

            if days_difference >= 0:
                repeat_start_date = monday + timedelta(days=days_difference)
                repeat_time_start = start_dt.time()
                new_start = datetime.combine(repeat_start_date, repeat_time_start)

                repeat_end_date = monday + timedelta(days=days_difference)
                repeat_time_end = end_dt.time()
                new_end = datetime.combine(repeat_end_date, repeat_time_end)

                if monday <= new_start.date() < monday + timedelta(days=7):
                    add_period_if_in_week(
                        period_id,
                        new_start,
                        new_end,
                        period["period_name"],
                        color,
                        repeat_start_dt,
                        repeat_end_dt,
                    )

    schedule = {day.strftime("%Y-%m-%d"): {} for day in week_dates}
    for period in generated_periods:
        start_dt = datetime.strptime(period["start_time"], "%Y-%m-%d %H:%M")
        end_dt = datetime.strptime(period["end_time"], "%Y-%m-%d %H:%M")
        day_str = start_dt.strftime("%Y-%m-%d")
        time_str = start_dt.strftime("%H:%M")

        start_minute = start_dt.hour * 60 + start_dt.minute
        end_minute = end_dt.hour * 60 + end_dt.minute
        duration_minutes = end_minute - start_minute
        rowspan = (duration_minutes / 5) if duration_minutes >= 0 else 1

        if day_str not in schedule:
            schedule[day_str] = {}

        schedule[day_str][time_str] = {
            "id": period["id"],
            "name": period["period_name"],
            "end_time": period["end_time"].split(" ")[1],
            "rowspan": int(rowspan),
            "color": period["color"],
        }

    return render_template(
        "john.html",
        user=user["name"],
        week_dates=week_dates,
        schedule=schedule,
        extra=extra,
    )


@app.route("/period/<int:period_id>", methods=["GET", "POST"])
@login_required
def edit_period(period_id):
    period = query_db(
        "SELECT * FROM periods WHERE id = ? AND owner_id = ?",
        (period_id, session["user_id"]),
        one=True,
    )
    error = ""

    if period is None:
        return redirect("/")

    courses = query_db("SELECT id, name FROM courses WHERE owner_id = ?", (session["user_id"],))
    assignments = query_db(
        "SELECT id, name FROM assignments WHERE owner_id = ?",
        (session["user_id"],),
    )

    if request.method == "POST":
        period_name = request.form["period_name"]
        start_time_str = request.form["start_time"]
        end_time_str = request.form["end_time"]
        repeat = request.form.get("repeat_type", "none")
        movable = "1" if request.form.get("is_movable") else "0"
        parent = request.form.get("parent")
        color = request.form.get("color_selector")
        repeat_start = request.form.get("repeat_start")
        repeat_end = request.form.get("repeat_end")

        try:
            start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M")
            end_time = datetime.strptime(end_time_str, "%Y-%m-%dT%H:%M")
            if start_time >= end_time:
                error = "Start time must be before end time."
                return render_template(
                    "edit_period.html",
                    period=period,
                    error=error,
                    courses=courses,
                    assignments=assignments,
                )
            elif repeat != "none":
                if datetime.strptime(repeat_start, "%Y-%m-%dT%H:%M") >= datetime.strptime(
                    repeat_end, "%Y-%m-%dT%H:%M"
                ):
                    error = "Repeat start must be before repeat end."
                    return render_template(
                        "edit_period.html",
                        period=period,
                        error=error,
                        courses=courses,
                        assignments=assignments,
                    )
        except ValueError:
            error = "Invalid date/time format."
            return render_template(
                "edit_period.html",
                period=period,
                error=error,
                courses=courses,
                assignments=assignments,
            )

        execute_db(
            """
            UPDATE periods
            SET period_name = ?, start_time = ?, end_time = ?, parent = ?, repeat = ?,
                is_movable = ?, color = ?, repeat_start = ?, repeat_end = ?
            WHERE id = ? AND owner_id = ?
            """,
            (
                period_name,
                start_time_str,
                end_time_str,
                parent,
                repeat,
                movable,
                color,
                repeat_start,
                repeat_end,
                period_id,
                session["user_id"],
            ),
        )
        return redirect("/")

    user = query_db("SELECT * FROM users WHERE id = ?", (session["user_id"],), one=True)["name"]
    return render_template(
        "edit_period.html",
        period=period,
        error=error,
        courses=courses,
        assignments=assignments,
        user=user,
    )


@app.route("/courses")
@login_required
def view_courses():
    courses = query_db("SELECT id, name FROM courses WHERE owner_id = ?", (session["user_id"],))
    user = query_db("SELECT * FROM users WHERE id = ?", (session["user_id"],), one=True)["name"]
    return render_template("view_courses.html", courses=courses, user=user)


@app.route("/assignment/<int:assignment_id>", methods=["GET", "POST"])
@login_required
def view_assignment(assignment_id):
    assignment = query_db(
        "SELECT * FROM assignments WHERE id = ? AND owner_id = ?",
        (assignment_id, session["user_id"]),
        one=True,
    )

    if not assignment:
        return "Assignment not found or unauthorized", 404

    error = None
    periods = query_db(
        "SELECT id, period_name, start_time, end_time FROM periods WHERE parent = ? AND owner_id = ?",
        (f"a{assignment_id}", session["user_id"]),
    )

    if request.method == "POST":
        name = request.form.get("name")
        due_date = request.form.get("due_date")
        progress = request.form.get("progress")
        weight = request.form.get("weight")
        notes = request.form.get("notes")
        parent = request.form.get("parent")
        color = request.form.get("color_selector")
        expected_time = request.form.get("expected_time")
        reset = request.form.get("reset")
        reset_time = request.form.get("reset_time")

        if not name or not due_date or not progress:
            error = "Name, due date, and progress are required."
        else:
            for period in periods:
                execute_db(
                    "UPDATE periods SET color = ? WHERE id = ? AND owner_id = ?",
                    (color, period["id"], session["user_id"]),
                )

            execute_db(
                """
                UPDATE assignments
                SET name = ?, due_date = ?, progress = ?, weight = ?, notes = ?, parent = ?,
                    color = ?, expected_time = ?, reset = ?, reset_time = ?
                WHERE id = ? AND owner_id = ?
                """,
                (
                    name,
                    due_date,
                    progress,
                    weight,
                    notes,
                    parent,
                    color,
                    expected_time,
                    reset,
                    reset_time,
                    assignment_id,
                    session["user_id"],
                ),
            )

            return redirect("/assignments")

    courses = query_db("SELECT id, name FROM courses WHERE owner_id = ?", (session["user_id"],))
    user = query_db("SELECT * FROM users WHERE id = ?", (session["user_id"],), one=True)["name"]

    better_periods = []
    for period in periods:
        entry = {"id": period["id"], "period_name": period["period_name"]}
        entry["start_time"] = datetime.strftime(
            datetime.strptime(period["start_time"], "%Y-%m-%dT%H:%M"),
            "%m-%d %H:%M",
        )
        entry["end_time"] = datetime.strftime(
            datetime.strptime(period["end_time"], "%Y-%m-%dT%H:%M"),
            "%H:%M",
        )
        better_periods.append(entry)

    return render_template(
        "view_assignment.html",
        assignment=assignment,
        courses=courses,
        periods=better_periods,
        error=error,
        user=user,
    )


@app.route("/assignments")
@login_required
def assignments():
    user_id = session["user_id"]

    incomplete_assignments = query_db(
        """
        SELECT id, name, due_date, progress FROM assignments
        WHERE owner_id = ? AND progress < 100
        ORDER BY due_date ASC
        """,
        (user_id,),
    )

    complete_assignments = query_db(
        """
        SELECT id, name, due_date, progress FROM assignments
        WHERE owner_id = ? AND progress = 100
        ORDER BY due_date DESC
        """,
        (user_id,),
    )
    user = query_db("SELECT * FROM users WHERE id = ?", (session["user_id"],), one=True)["name"]

    return render_template(
        "assignments.html",
        incomplete_assignments=incomplete_assignments,
        complete_assignments=complete_assignments,
        user=user,
    )


@app.route("/assignment/add", methods=["GET", "POST"])
@login_required
def add_assignment():
    defaults = {}
    courses = query_db("SELECT id, name FROM courses WHERE owner_id = ?", (session["user_id"],))
    user = query_db("SELECT * FROM users WHERE id = ?", (session["user_id"],), one=True)["name"]

    if request.method == "POST":
        name = request.form.get("name")
        due_date = request.form.get("due_date")
        progress = request.form.get("progress")
        parent = request.form.get("parent")
        weight = request.form.get("weight")
        notes = request.form.get("notes")
        color = request.form.get("color_selector")
        expected_time = request.form.get("expected_time")
        reset = request.form.get("reset")
        reset_time = request.form.get("reset_time")

        if parent:
            course = query_db(
                "SELECT color FROM courses WHERE id = ? AND owner_id = ?",
                (parent, session["user_id"]),
                one=True,
            )
            if course:
                color = course["color"]

        if not name or not due_date or not progress:
            return render_template(
                "add_assignment.html",
                error="Please fill out all required fields.",
                courses=courses,
                user=user,
                defaults=defaults,
            )

        try:
            progress_val = float(progress)
            if not (0 <= progress_val <= 100):
                raise ValueError
        except ValueError:
            return render_template(
                "add_assignment.html",
                error="Progress must be a number between 0 and 100.",
                courses=courses,
                user=user,
                defaults=defaults,
            )

        execute_db(
            """
            INSERT INTO assignments
            (name, due_date, progress, parent, weight, notes, color, reset, reset_time, expected_time, owner_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                due_date,
                progress,
                parent or None,
                weight,
                notes,
                color,
                reset,
                reset_time,
                expected_time,
                session["user_id"],
            ),
        )
        return redirect("/assignments")

    return render_template("add_assignment.html", courses=courses, user=user, defaults=defaults)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    username = (request.form.get("username") or "").lower()
    password = request.form.get("password")
    confirm = request.form.get("confirmation")
    name = request.form.get("name")

    if not username or not password or password != confirm or not name:
        return render_template(
            "register.html",
            error="Please fill all fields and ensure passwords match.",
        )

    try:
        execute_db(
            """
            INSERT INTO users (username, hash, name, regimen_short, regimen_long)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username, generate_password_hash(password), name, "average", "average"),
        )
        return redirect("/login")
    except sqlite3.IntegrityError:
        return render_template("register.html", error="Username already exists.")


@app.route("/login", methods=["GET", "POST"])
def login():
    session.clear()

    if request.method == "POST":
        username = (request.form.get("username") or "").lower()
        password = request.form.get("password")

        if not username:
            return render_template("login.html", error="Must provide username.")
        if not password:
            return render_template("login.html", error="Must provide password.")

        row = query_db("SELECT * FROM users WHERE username = ?", (username,), one=True)

        if row is None or not check_password_hash(row["hash"], password):
            return render_template("login.html", error="Invalid username or password.")

        session["user_id"] = row["id"]
        return redirect("/")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    user_id = session["user_id"]
    user = query_db("SELECT * FROM users WHERE id = ?", (user_id,), one=True)

    if request.method == "POST":
        name = request.form.get("name")
        username = (request.form.get("username") or "").lower()
        password = request.form.get("password")
        confirm = request.form.get("confirmation")

        if not name or not username:
            return render_template("account.html", user=user, error="Please fill all required fields.")

        try:
            execute_db(
                "UPDATE users SET name = ?, username = ? WHERE id = ?",
                (name, username, user_id),
            )
            if password:
                if password == confirm:
                    new_hash = generate_password_hash(password)
                    execute_db("UPDATE users SET hash = ? WHERE id = ?", (new_hash, user_id))
                else:
                    return render_template("account.html", user=user, error="New passwords do not match.")
            return redirect("/account")
        except sqlite3.IntegrityError:
            return render_template("account.html", user=user, error="Username already exists.")

    return render_template("account.html", user=user, usert=user["name"])


@app.route("/course/add", methods=["GET", "POST"])
@login_required
def add_course():
    error = None

    if request.method == "POST":
        course_name = request.form["course_name"]
        color = request.form.get("color_selector")

        execute_db(
            "INSERT INTO courses (owner_id, name, color) VALUES (?, ?, ?)",
            (session["user_id"], course_name, color),
        )
        return redirect("/courses")

    user = query_db("SELECT * FROM users WHERE id = ?", (session["user_id"],), one=True)["name"]
    return render_template("add_course.html", error=error, user=user)


@app.route("/course/<int:course_id>", methods=["GET", "POST"])
@login_required
def view_course(course_id):
    course = query_db(
        "SELECT * FROM courses WHERE id = ? AND owner_id = ?",
        (course_id, session["user_id"]),
        one=True,
    )

    assignments = query_db(
        """
        SELECT id, name, due_date, progress
        FROM assignments
        WHERE parent = ? AND owner_id = ?
        ORDER BY DATETIME(due_date) ASC
        """,
        (course_id, session["user_id"]),
    )

    periods = query_db(
        """
        SELECT id, period_name, start_time, end_time
        FROM periods
        WHERE parent = ? AND owner_id = ?
        """,
        (f"c{course_id}", session["user_id"]),
    )

    assignments_b = []
    remaining_assignments = []
    for assignment in assignments:
        periods += query_db(
            """
            SELECT id, period_name, start_time, end_time
            FROM periods
            WHERE parent = ? AND owner_id = ?
            """,
            (f"a{assignment['id']}", session["user_id"]),
        )
        if assignment["progress"] in (100, 100.0):
            assignments_b.insert(0, assignment)
        else:
            remaining_assignments.append(assignment)

    error = None
    user = query_db("SELECT * FROM users WHERE id = ?", (session["user_id"],), one=True)["name"]

    if request.method == "POST":
        name = request.form.get("name")
        color = request.form.get("color_selector")
        if not name:
            error = "Name is required."
        else:
            execute_db(
                "UPDATE courses SET name = ?, color = ? WHERE id = ? AND owner_id = ?",
                (name, color, course_id, session["user_id"]),
            )

            for period in periods:
                execute_db(
                    "UPDATE periods SET color = ? WHERE id = ? AND owner_id = ?",
                    (color, period["id"], session["user_id"]),
                )

            for assignment in remaining_assignments:
                execute_db(
                    "UPDATE assignments SET color = ? WHERE id = ? AND owner_id = ?",
                    (color, assignment["id"], session["user_id"]),
                )

            return redirect("/courses")

    better_periods = []
    all_assignments = remaining_assignments + assignments_b

    for period in periods:
        entry = {"id": period["id"], "period_name": period["period_name"]}
        entry["start_time"] = datetime.strftime(
            datetime.strptime(period["start_time"], "%Y-%m-%dT%H:%M"),
            "%m-%d %H:%M",
        )
        entry["end_time"] = datetime.strftime(
            datetime.strptime(period["end_time"], "%Y-%m-%dT%H:%M"),
            "%H:%M",
        )
        better_periods.append(entry)

    better_assignments = []
    for assignment in all_assignments:
        entry = {
            "id": assignment["id"],
            "name": assignment["name"],
            "progress": assignment["progress"],
        }
        entry["due_date"] = datetime.strftime(
            datetime.strptime(assignment["due_date"], "%Y-%m-%dT%H:%M"),
            "%m-%d %H:%M",
        )
        better_assignments.append(entry)

    return render_template(
        "view_course.html",
        course=course,
        assignments=better_assignments,
        periods=better_periods,
        error=error,
        user=user,
    )


@app.route("/period/add", methods=["GET", "POST"])
@login_required
def add_period():
    now = datetime.now()
    default_start_time = now.strftime("%Y-%m-%dT%H:00")
    default_end_time = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:00")
    error = None

    courses = query_db("SELECT id, name FROM courses WHERE owner_id = ?", (session["user_id"],))
    assignments = query_db(
        "SELECT id, name FROM assignments WHERE owner_id = ?",
        (session["user_id"],),
    )

    if request.method == "POST":
        period_name = request.form["period_name"]
        start_time_str = request.form["start_time"]
        end_time_str = request.form["end_time"]
        repeat = request.form.get("repeat_type", "none")
        movable = True if request.form.get("is_movable") else False
        parent = request.form.get("parent")
        color = request.form.get("color_selector")
        repeat_start = request.form.get("repeat_start")
        repeat_end = request.form.get("repeat_end")

        if parent:
            if parent[0] == "a":
                assignment = query_db(
                    "SELECT color FROM assignments WHERE id = ? AND owner_id = ?",
                    (parent[1:], session["user_id"]),
                    one=True,
                )
                if assignment:
                    color = assignment["color"]
            elif parent[0] == "c":
                course = query_db(
                    "SELECT color FROM courses WHERE id = ? AND owner_id = ?",
                    (parent[1:], session["user_id"]),
                    one=True,
                )
                if course:
                    color = course["color"]

        try:
            datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M")
            datetime.strptime(end_time_str, "%Y-%m-%dT%H:%M")
            if datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M") >= datetime.strptime(
                end_time_str, "%Y-%m-%dT%H:%M"
            ):
                error = "Start time must be before end time."
            elif repeat != "none":
                if datetime.strptime(repeat_start, "%Y-%m-%dT%H:%M") >= datetime.strptime(
                    repeat_end, "%Y-%m-%dT%H:%M"
                ):
                    error = "Repeat start must be before repeat end."
        except ValueError:
            error = "Invalid date/time format."

        if error:
            return render_template(
                "add_period.html",
                default_start_time=default_start_time,
                default_end_time=default_end_time,
                error=error,
                courses=courses,
                assignments=assignments,
            )

        execute_db(
            """
            INSERT INTO periods
            (owner_id, period_name, start_time, end_time, parent, repeat, is_movable, color, repeat_start, repeat_end)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                period_name,
                start_time_str,
                end_time_str,
                parent,
                repeat,
                movable,
                color,
                repeat_start,
                repeat_end,
            ),
        )
        return redirect("/")

    user = query_db("SELECT * FROM users WHERE id = ?", (session["user_id"],), one=True)["name"]
    return render_template(
        "add_period.html",
        default_start_time=default_start_time,
        default_end_time=default_end_time,
        error=error,
        courses=courses,
        assignments=assignments,
        user=user,
    )


@app.route("/period/delete/<int:period_id>")
@login_required
def delete_period(period_id):
    execute_db("DELETE FROM periods WHERE id = ? AND owner_id = ?", (period_id, session["user_id"]))
    return redirect("/")


@app.route("/course/delete/<int:course_id>")
@login_required
def delete_course(course_id):
    execute_db("DELETE FROM courses WHERE id = ? AND owner_id = ?", (course_id, session["user_id"]))
    return redirect("/")


@app.route("/assignment/delete/<int:assignment_id>")
@login_required
def delete_assignment(assignment_id):
    execute_db(
        "DELETE FROM assignments WHERE id = ? AND owner_id = ?",
        (assignment_id, session["user_id"]),
    )
    return redirect("/")


@app.route("/ai/settings", methods=["GET", "POST"])
@login_required
def ai_settings():
    user = query_db("SELECT * FROM users WHERE id = ?", (session["user_id"],), one=True)
    usert = user["name"]
    user_id = session["user_id"]

    if request.method == "POST":
        regimen_short = request.form.get("regimen_short")
        regimen_long = request.form.get("regimen_long")
        break_duration = request.form.get("break_duration")
        max_session_length = request.form.get("max_session_length")
        ai_notes = request.form.get("notes")
        ai_notes = user["ai_notes"] if ai_notes == "" else ai_notes

        execute_db(
            """
            UPDATE users
            SET ai_notes = ?, regimen_short = ?, regimen_long = ?, break_duration = ?, max_session_length = ?
            WHERE id = ?
            """,
            (ai_notes, regimen_short, regimen_long, break_duration, max_session_length, user_id),
        )

        user = query_db("SELECT * FROM users WHERE id = ?", (session["user_id"],), one=True)

    return render_template("ai_settings.html", usert=usert, user=user)


@app.route("/ai/arrange/<int:extra>", methods=["GET", "POST"])
@login_required
def ai_rearrange(extra):
    if client is None:
        return "AI integration is not configured.", 503

    extra = int(extra)
    user = query_db("SELECT * FROM users WHERE id = ?", (session["user_id"],), one=True)
    user_id = session["user_id"]
    all_periods = query_db("SELECT * FROM periods WHERE owner_id = ?", (session["user_id"],))

    if request.method == "GET":
        today = date.today()
        target_dates = [today + timedelta(days=i) for i in range(int(extra))]
        regimen_long = user["regimen_long"]
        regimen_short = user["regimen_short"]

        def occurs_on(period, d: date):
            start_dt = datetime.strptime(period["start_time"], "%Y-%m-%dT%H:%M")
            start_date = start_dt.date()
            repeat = (period["repeat"] or "").lower()

            if start_date == d:
                return True
            if repeat == "daily" and start_date <= d:
                return True
            if repeat == "weekly" and start_date <= d:
                return d.weekday() == start_date.weekday()
            return False

        schedule = {d.strftime("%Y-%m-%d"): [] for d in target_dates}
        for p in all_periods:
            for d in target_dates:
                if occurs_on(p, d):
                    start_dt = datetime.strptime(p["start_time"], "%Y-%m-%dT%H:%M")
                    end_dt = datetime.strptime(p["end_time"], "%Y-%m-%dT%H:%M")
                    if p["repeat"] and start_dt.date() != d:
                        new_start = datetime.combine(d, start_dt.time())
                        new_end = datetime.combine(d, end_dt.time())
                    else:
                        new_start = start_dt
                        new_end = end_dt

                    schedule[d.strftime("%Y-%m-%d")].append(
                        {
                            "id": p["id"],
                            "name": p["period_name"],
                            "start_time": new_start.isoformat(timespec="minutes"),
                            "end_time": new_end.isoformat(timespec="minutes"),
                            "repeat": p["repeat"] or "",
                            "is_movable": p["is_movable"],
                            "parent": p["parent"],
                            "color": p["color"],
                        }
                    )

        regimen_map = {"Very low": 1, "low": extra, "average": 7, "high": 14, "very high": 30}
        regimen_long_val = regimen_map.get(regimen_long, 7)
        due_end = today + timedelta(days=regimen_long_val - 1)

        assignments = query_db(
            """
            SELECT * FROM assignments
            WHERE owner_id = ?
              AND progress < 100.0
              AND DATETIME(due_date) <= DATETIME(?)
            ORDER BY DATETIME(due_date) ASC
            """,
            (user_id, due_end),
        )

        assignments_by_date = {}
        for a in assignments:
            due_str = a["due_date"][0:10]
            assignments_by_date.setdefault(due_str, []).append(
                {
                    "id": a["id"],
                    "name": a["name"],
                    "due_date": a["due_date"],
                    "progress": a["progress"],
                    "expected_time": a["expected_time"],
                    "color": a["color"],
                    "weight": a["weight"],
                    "notes": a["notes"],
                    "reset": a["reset"],
                    "reset_time": a["reset_time"],
                }
            )

        schedule_description = ""
        for day_str, periods in schedule.items():
            schedule_description += f"Schedule for {day_str}:\n"
            for p in periods:
                schedule_description += (
                    f"- {p['name']} from {p['start_time']} to {p['end_time']} "
                    f"(Movable: {p['is_movable']}, Parent: {p['parent']}, Color: {p['color']}, "
                    f"ID: {p['id']}, Repeat: {p['repeat']})\n"
                )
            schedule_description += "\n"

        assignment_description = ""
        for due_str, assigns in assignments_by_date.items():
            assignment_description += f"Assignments due on {due_str}:\n"
            for a in assigns:
                assignment_description += (
                    f"- {a['name']} ID: {a['id']} "
                    f"(Due: {a['due_date']}, Progress: {a['progress']:.1f}%, "
                    f"Total Expected time: {a['expected_time']} hours, "
                    f"Priority: {a['weight']}, Color: {a['color']}, "
                    f"Progress reset: {a['reset']}, Initial reset: {a['reset_time']})\n"
                )
            assignment_description += "\n"

        preferences_description = (
            f"User ID: {user['id']}, "
            f"Short term work intensity: {regimen_short}, "
            f"Long term work intensity: {regimen_long}, "
            f"Break duration: {user['break_duration']}, "
            f"Max session length: {user['max_session_length']}, "
            f"Notes to AI: {user['ai_notes']}."
        )

        llm_prompt = (
            f"You are an intelligent schedule assistant. Your goal is to rearrange the schedule optimally "
            f"from {target_dates[0]} to {target_dates[-1]}. "
            f"Here is the user's schedule and preferences.\n\n"
            f"{schedule_description}\n"
            f"{assignment_description}\n"
            "You may:\n"
            "- Reorder existing tasks.\n"
            "- Add new periods if needed (e.g., breaks, planning sessions, assignment work).\n"
            f"- Honor user preferences: {preferences_description}\n"
            "Do not move or delete any period with Movable as 0.\n\n"
            "When moving a period with repeats, keep the old period, and create a new period without repeats at the new time. "
            "When deleting a period, add a 'd' before the ID, with the same ID number and details. "
            "When creating or updating a period for an assignment, set its parent field to 'a{assignment_id}' and use the assignment's color.\n\n"
            "Return the updated schedule as JSON with entries: id (None if a new period), owner_id (integer), "
            "period_name, start_time (%Y-%m-%dT%H:%M), end_time (%Y-%m-%dT%H:%M), parent, repeat, "
            "is_movable ('0' or '1'), color.\n"
            "Include all given periods in the JSON, including unchanged and deleted ones.\n"
            "IMPORTANT: Only respond with JSON period entries."
        )

        ai_response = client.models.generate_content(
            model=os.environ.get("GOOGLE_GENAI_MODEL", "gemini-2.5-flash"),
            contents=llm_prompt,
        ).text

        cleaned = ai_response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned.removeprefix("```json").removesuffix("```").strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```").removesuffix("```").strip()

        response = json.loads(cleaned)

    else:
        return redirect("/")

    def sametime(a, b):
        a_dt = datetime.strptime(a, "%Y-%m-%dT%H:%M")
        b_dt = datetime.strptime(b, "%Y-%m-%dT%H:%M")
        return (a_dt - b_dt).total_seconds() == 0

    for period in response:
        if period["id"] is None:
            execute_db(
                """
                INSERT INTO periods (owner_id, period_name, start_time, end_time, repeat, is_movable, parent, color)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    period["period_name"],
                    period["start_time"],
                    period["end_time"],
                    period["repeat"],
                    period["is_movable"],
                    period["parent"],
                    period["color"],
                ),
            )
            continue

        if isinstance(period["id"], str):
            period_id = int(str(period["id"])[1:])
            execute_db("DELETE FROM periods WHERE id = ? AND owner_id = ?", (period_id, user_id))
            continue

        old_period = query_db(
            "SELECT * FROM periods WHERE id = ? AND owner_id = ?",
            (period["id"], session["user_id"]),
            one=True,
        )
        if not old_period:
            continue

        if sametime(period["start_time"], old_period["start_time"]) and sametime(
            period["end_time"], old_period["end_time"]
        ):
            continue

        if (
            len(period.items() & dict(old_period).items()) >= 6
            and str(old_period["is_movable"]) == "1"
            and old_period["repeat"] == "none"
        ):
            execute_db(
                "UPDATE periods SET start_time = ?, end_time = ? WHERE id = ? AND owner_id = ?",
                (period["start_time"], period["end_time"], period["id"], user_id),
            )

    return redirect("/")


if __name__ == "__main__":
    app.run(debug=False)
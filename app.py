import os
from datetime import date, datetime
from functools import wraps

import mysql.connector
from mysql.connector import Error
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret-key")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "root"),
    "database": os.getenv("DB_NAME", "leave_management"),
}

LEAVE_TYPES = ["Casual Leave", "Sick Leave", "Earned Leave"]

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def login_required(role=None):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in first.", "warning")
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("You are not authorized to view that page.", "danger")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapped
    return decorator

def fetch_one(query, params=()):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute(query, params)
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def fetch_all(query, params=()):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "employee")
        if not name or not email or len(password) < 6:
            flash("Enter your name, a valid email and a password of at least 6 characters.", "danger")
            return render_template("register.html")
        if role not in ("employee", "manager"):
            flash("Invalid role.", "danger")
            return render_template("register.html")
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (%s,%s,%s,%s)",
                (name, email, generate_password_hash(password), role)
            )
            user_id = cur.lastrowid
            if role == "employee":
                cur.executemany(
                    "INSERT INTO leave_balances (user_id, leave_type, balance) VALUES (%s,%s,%s)",
                    [(user_id, kind, amount) for kind, amount in [
                        ("Casual Leave", 12), ("Sick Leave", 10), ("Earned Leave", 15)
                    ]]
                )
            conn.commit()
            cur.close()
            conn.close()
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))
        except Error as exc:
            if "conn" in locals() and conn.is_connected():
                conn.rollback()
                conn.close()
            flash("Could not register. The email may already be registered. " + str(exc), "danger")
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = fetch_one("SELECT * FROM users WHERE email=%s", (email,))
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session.update(user_id=user["id"], name=user["name"], role=user["role"])
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required()
def dashboard():
    if session["role"] == "manager":
        requests_list = fetch_all("""
            SELECT l.*, u.name AS employee_name, u.email
            FROM leave_requests l JOIN users u ON l.user_id=u.id
            ORDER BY l.created_at DESC
        """)
        return render_template("manager_dashboard.html", requests=requests_list)
    balances = fetch_all(
        "SELECT leave_type, balance FROM leave_balances WHERE user_id=%s ORDER BY leave_type",
        (session["user_id"],)
    )
    requests_list = fetch_all(
        "SELECT * FROM leave_requests WHERE user_id=%s ORDER BY created_at DESC",
        (session["user_id"],)
    )
    return render_template("employee_dashboard.html", balances=balances, requests=requests_list)

@app.route("/apply", methods=["GET", "POST"])
@login_required("employee")
def apply_leave():
    balances = fetch_all(
        "SELECT leave_type, balance FROM leave_balances WHERE user_id=%s",
        (session["user_id"],)
    )
    balance_map = {b["leave_type"]: b["balance"] for b in balances}
    if request.method == "POST":
        leave_type = request.form.get("leave_type")
        start_raw = request.form.get("start_date")
        end_raw = request.form.get("end_date")
        reason = request.form.get("reason", "").strip()
        try:
            start = datetime.strptime(start_raw, "%Y-%m-%d").date()
            end = datetime.strptime(end_raw, "%Y-%m-%d").date()
            days = (end - start).days + 1
            if leave_type not in LEAVE_TYPES:
                raise ValueError("Choose a valid leave type.")
            if start < date.today():
                raise ValueError("Start date cannot be in the past.")
            if end < start:
                raise ValueError("End date cannot be before start date.")
            if not reason:
                raise ValueError("Please enter a reason.")
            if days > balance_map.get(leave_type, 0):
                raise ValueError("Insufficient leave balance. Your request was not submitted.")
            conn = get_db()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO leave_requests
                (user_id, leave_type, start_date, end_date, days, reason, status)
                VALUES (%s,%s,%s,%s,%s,%s,'Pending')
            """, (session["user_id"], leave_type, start, end, days, reason))
            conn.commit()
            cur.close()
            conn.close()
            flash("Leave application submitted to your manager.", "success")
            return redirect(url_for("dashboard"))
        except ValueError as exc:
            flash(str(exc), "danger")
        except Error as exc:
            flash("Database error: " + str(exc), "danger")
    return render_template("apply_leave.html", balances=balance_map, today=date.today().isoformat())

@app.route("/manager/action/<int:request_id>", methods=["POST"])
@login_required("manager")
def manager_action(request_id):
    action = request.form.get("action")
    if action not in ("Approved", "Rejected"):
        flash("Invalid action.", "danger")
        return redirect(url_for("dashboard"))
    conn = get_db()
    try:
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM leave_requests WHERE id=%s FOR UPDATE", (request_id,))
        leave = cur.fetchone()
        if not leave or leave["status"] != "Pending":
            raise ValueError("This request is not available for review.")
        if action == "Approved":
            cur.execute("""
                SELECT balance FROM leave_balances
                WHERE user_id=%s AND leave_type=%s FOR UPDATE
            """, (leave["user_id"], leave["leave_type"]))
            balance_row = cur.fetchone()
            if not balance_row or balance_row["balance"] < leave["days"]:
                raise ValueError("Employee no longer has sufficient balance.")
            cur.execute("""
                UPDATE leave_balances SET balance=balance-%s
                WHERE user_id=%s AND leave_type=%s
            """, (leave["days"], leave["user_id"], leave["leave_type"]))
        cur.execute(
            "UPDATE leave_requests SET status=%s, reviewed_at=NOW() WHERE id=%s",
            (action, request_id)
        )
        conn.commit()
        flash("Leave request " + action.lower() + ".", "success")
    except (Error, ValueError) as exc:
        conn.rollback()
        flash(str(exc), "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("dashboard"))

@app.route("/cancel/<int:request_id>", methods=["POST"])
@login_required("employee")
def cancel_leave(request_id):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cur.execute(
            "SELECT * FROM leave_requests WHERE id=%s AND user_id=%s FOR UPDATE",
            (request_id, session["user_id"])
        )
        leave = cur.fetchone()
        if not leave or leave["status"] not in ("Pending", "Approved"):
            raise ValueError("This request cannot be cancelled.")
        if leave["status"] == "Approved":
            cur.execute("""
                UPDATE leave_balances SET balance=balance+%s
                WHERE user_id=%s AND leave_type=%s
            """, (leave["days"], session["user_id"], leave["leave_type"]))
        cur.execute(
            "UPDATE leave_requests SET status='Cancelled', reviewed_at=NOW() WHERE id=%s",
            (request_id,)
        )
        conn.commit()
        flash("Leave request cancelled.", "success")
    except (Error, ValueError) as exc:
        conn.rollback()
        flash(str(exc), "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("dashboard"))
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        user = fetch_one(
            "SELECT * FROM users WHERE email=%s",
            (email,)
        )

        if user:
            serializer = URLSafeTimedSerializer(app.secret_key)

            token = serializer.dumps(
                email,
                salt="password-reset"
            )

            reset_link = url_for(
                "reset_password",
                token=token,
                _external=True
            )

            print("PASSWORD RESET LINK:", reset_link)

        flash(
            "If the email is registered, a reset link has been generated.",
            "success"
        )

    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    serializer = URLSafeTimedSerializer(app.secret_key)

    try:
        email = serializer.loads(
            token,
            salt="password-reset",
            max_age=1800
        )
    except Exception:
        flash("Reset link is invalid or expired.", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        password = request.form.get("password", "")

        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "danger")
            return render_template("reset_password.html")

        conn = get_db()
        cur = conn.cursor()

        try:
            cur.execute(
                "UPDATE users SET password_hash=%s WHERE email=%s",
                (generate_password_hash(password), email)
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()

        flash("Password changed successfully. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html")



if __name__ == "__main__":
    app.run(debug=True)

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from datetime import date
import sqlite3
import calendar

app = Flask(__name__)
app.secret_key = "yourSuperSecretKey123"

DB_PATH = "booking.db"

# ---------------- 教練設定 ----------------
coaches = [
    {"id": 1, "name": "A教練"},
    {"id": 2, "name": "B教練"},
    {"id": 3, "name": "C教練"},
]

# 教練顏色
coach_colors = {
    "A教練": "#4A90E2",
    "B教練": "#7ED321",
    "C教練": "#D0021B",
}

# 課程類別
course_types = [
    "初階訓練",
    "核心改善",
    "姿勢評估",
    "肌力訓練",
    "伸展放鬆",
    "私人教練課程",
    "其他",
]

# ---------------- 資料庫 ----------------
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    # 預約紀錄表
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coach TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            note TEXT,
            client_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT,
            gender TEXT,
            birthday TEXT NOT NULL,
            line_id TEXT,
            course_type TEXT NOT NULL
        )
        """
    )

    # 會員資料表：以 (name, birthday) 為唯一識別
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            birthday TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            gender TEXT,
            line_id TEXT,
            UNIQUE(name, birthday)
        )
        """
    )

    conn.commit()
    conn.close()

init_db()

# ---------------- 前台首頁 ----------------
@app.route("/")
def index():
    today = date.today().isoformat()
    last_booking = session.pop("last_booking", None)

    return render_template(
        "index.html",
        coaches=coaches,
        today=today,
        course_types=course_types,
        last_booking=last_booking
    )

# ---------------- 可預約時段 API ----------------
@app.route("/available_times")
def available_times():
    coach_id = request.args.get("coach_id")
    the_date = request.args.get("date")

    # 09:00 ~ 20:30，每 30 分
    all_times = []
    for h in range(9, 21):
        all_times.append(f"{h}:00")
        all_times.append(f"{h}:30")

    if not coach_id or not the_date:
        return jsonify(all_times)

    coach = next((c for c in coaches if str(c["id"]) == str(coach_id)), None)
    if not coach:
        return jsonify(all_times)

    coach_name = coach["name"]

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT time FROM bookings WHERE coach = ? AND date = ?",
        (coach_name, the_date),
    )
    rows = cur.fetchall()
    conn.close()

    reserved_times = [r["time"] for r in rows]
    reserved_minutes = []
    for t in reserved_times:
        h, m = t.split(":")
        reserved_minutes.append(int(h) * 60 + int(m))

    available = []
    for t in all_times:
        h, m = t.split(":")
        minutes = int(h) * 60 + int(m)

        # 至少間隔一小時
        conflict = False
        for r in reserved_minutes:
            if abs(minutes - r) < 60:
                conflict = True
                break

        if not conflict:
            available.append(t)

    return jsonify(available)

# ---------------- 預約提交 ----------------
@app.route("/book", methods=["POST"])
def book():
    coach_id    = request.form.get("coach_id")
    the_date    = request.form.get("date")
    hour        = request.form.get("hour")
    minute      = request.form.get("minute")
    note        = request.form.get("note", "").strip()

    client_name = request.form.get("client_name", "").strip()
    phone       = request.form.get("phone", "").strip()
    email       = request.form.get("email", "").strip()
    gender      = request.form.get("gender", "").strip()
    birthday    = request.form.get("birthday", "").strip()
    line_id     = request.form.get("line_id", "").strip()
    course_type = request.form.get("course_type", "").strip()

    # 必填欄位檢查（生日也必填）
    if not all([coach_id, the_date, hour, minute, client_name, phone, course_type, birthday]):
        flash("請確認教練、日期、時間、姓名、電話、生日與課程類別都有填寫！", "error")
        return redirect(url_for("index"))

    the_time = f"{hour}:{minute}"

    coach = next((c for c in coaches if str(c["id"]) == str(coach_id)), None)
    if not coach:
        flash("教練不存在，請重新選擇。", "error")
        return redirect(url_for("index"))

    coach_name = coach["name"]
    new_minutes = int(hour) * 60 + int(minute)

    conn = get_db_connection()
    cur = conn.cursor()

    # 檢查是否有太接近的預約
    cur.execute(
        "SELECT time FROM bookings WHERE coach = ? AND date = ?",
        (coach_name, the_date),
    )
    rows = cur.fetchall()
    for r in rows:
        h, m = r["time"].split(":")
        old_minutes = int(h) * 60 + int(m)
        if abs(new_minutes - old_minutes) < 60:
            flash("該時段已被預約或與其他預約時間過近，請重新選擇。", "error")
            conn.close()
            return redirect(url_for("index"))

    # 寫入 bookings
    cur.execute(
        """
        INSERT INTO bookings
            (coach, date, time, note,
             client_name, phone, email, gender, birthday, line_id, course_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            coach_name, the_date, the_time, note,
            client_name, phone, email, gender, birthday, line_id, course_type
        ),
    )

    # 更新 / 建立會員資料（以姓名 + 生日為 key）
    cur.execute(
        """
        INSERT INTO members (name, birthday, phone, email, gender, line_id)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(name, birthday) DO UPDATE SET
            phone  = excluded.phone,
            email  = excluded.email,
            gender = excluded.gender,
            line_id= excluded.line_id
        """,
        (client_name, birthday, phone, email, gender, line_id),
    )

    conn.commit()
    conn.close()

    # 存到 session 給首頁彈窗用
    session["last_booking"] = {
        "client_name": client_name,
        "coach": coach_name,
        "date": the_date,
        "time": the_time,
        "course_type": course_type,
        "note": note,
    }

    return redirect(url_for("index"))

# ---------------- 後台預約列表 ----------------
@app.route("/admin")
def admin():
    coach_filter  = request.args.get("coach") or "all"
    date_filter   = request.args.get("date") or ""
    course_filter = request.args.get("course_type") or "all"
    name_filter   = request.args.get("client_name") or ""

    conn = get_db_connection()
    cur = conn.cursor()

    query = "SELECT * FROM bookings WHERE 1=1"
    params = []

    if coach_filter != "all":
        query += " AND coach = ?"
        params.append(coach_filter)
    if date_filter:
        query += " AND date = ?"
        params.append(date_filter)
    if course_filter != "all":
        query += " AND course_type = ?"
        params.append(course_filter)
    if name_filter:
        query += " AND client_name LIKE ?"
        params.append(f"%{name_filter}%")

    query += " ORDER BY date, time"
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    coach_names = [c["name"] for c in coaches]

    return render_template(
        "admin.html",
        bookings=rows,
        coach_names=coach_names,
        course_types=course_types,
        coach_filter=coach_filter,
        date_filter=date_filter,
        course_filter=course_filter,
        name_filter=name_filter,
    )

@app.route("/admin/delete/<int:booking_id>", methods=["POST"])
def delete_booking(booking_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()
    flash("已刪除該筆預約。", "success")
    return redirect(url_for("admin"))

# ---------------- 小型會員系統：查詢（姓名 + 生日） ----------------
@app.route("/history", methods=["GET", "POST"])
def history():
    name = ""
    birthday = ""
    records = []
    member_info = None

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        birthday = request.form.get("birthday", "").strip()

        conn = get_db_connection()
        cur = conn.cursor()

        # 會員主資料
        cur.execute("""
            SELECT *
            FROM members
            WHERE name = ? AND birthday = ?
        """, (name, birthday))
        member_info = cur.fetchone()

        # 預約紀錄
        cur.execute("""
            SELECT *
            FROM bookings
            WHERE client_name = ? AND birthday = ?
            ORDER BY date DESC, time DESC
        """, (name, birthday))
        records = cur.fetchall()

        conn.close()

    return render_template(
        "history.html",
        name=name,
        birthday=birthday,
        records=records,
        member_info=member_info
    )

# ---------------- 會員列表 ----------------
@app.route("/members")
def members():
    keyword = request.args.get("keyword", "").strip()

    conn = get_db_connection()
    cur = conn.cursor()

    if keyword:
        cur.execute("""
            SELECT *
            FROM members
            WHERE name LIKE ?
            ORDER BY name, birthday
        """, (f"%{keyword}%",))
    else:
        cur.execute("""
            SELECT *
            FROM members
            ORDER BY name, birthday
        """)
    rows = cur.fetchall()
    conn.close()

    return render_template("members.html", members=rows, keyword=keyword)

# ---------------- 會員編輯 ----------------
@app.route("/member/edit/<int:member_id>", methods=["GET", "POST"])
def edit_member(member_id):
    conn = get_db_connection()
    cur = conn.cursor()

    # 先抓原本資料
    cur.execute("SELECT * FROM members WHERE id = ?", (member_id,))
    member = cur.fetchone()

    if not member:
        conn.close()
        flash("找不到該會員。", "error")
        return redirect(url_for("members"))

    old_name = member["name"]
    old_birthday = member["birthday"]

    if request.method == "POST":
        new_name     = request.form.get("name", "").strip()
        new_birthday = request.form.get("birthday", "").strip()
        phone        = request.form.get("phone", "").strip()
        email        = request.form.get("email", "").strip()
        gender       = request.form.get("gender", "").strip()
        line_id      = request.form.get("line_id", "").strip()

        if not new_name or not new_birthday:
            flash("姓名與生日為必填。", "error")
            conn.close()
            return redirect(url_for("edit_member", member_id=member_id))

        # 更新 members
        try:
            cur.execute("""
                UPDATE members
                SET name = ?, birthday = ?, phone = ?, email = ?, gender = ?, line_id = ?
                WHERE id = ?
            """, (new_name, new_birthday, phone, email, gender, line_id, member_id))
        except sqlite3.IntegrityError:
            # 如果新的姓名+生日已存在於其他會員，會觸發 UNIQUE 錯誤
            flash("已有相同姓名與生日的會員，請確認是否重複。", "error")
            conn.close()
            return redirect(url_for("edit_member", member_id=member_id))

        # 同步更新 bookings 中的姓名 / 生日（以及聯絡資料）
        cur.execute("""
            UPDATE bookings
            SET client_name = ?, birthday = ?, phone = ?, email = ?, gender = ?, line_id = ?
            WHERE client_name = ? AND birthday = ?
        """, (new_name, new_birthday, phone, email, gender, line_id, old_name, old_birthday))

        conn.commit()
        conn.close()

        flash("會員資料已更新。", "success")
        return redirect(url_for("members"))

    conn.close()
    return render_template("member_edit.html", member=member)

# ---------------- 月排程 ----------------
@app.route("/admin/calendar")
def admin_calendar():
    today = date.today()
    year = request.args.get("year", type=int) or today.year
    month = request.args.get("month", type=int) or today.month

    first_day = date(year, month, 1)
    last = calendar.monthrange(year, month)[1]
    last_day = date(year, month, last)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT coach, date, time, client_name, course_type
        FROM bookings
        WHERE date BETWEEN ? AND ?
    """, (first_day.isoformat(), last_day.isoformat()))
    rows = cur.fetchall()
    conn.close()

    events_by_date = {}
    for r in rows:
        d = r["date"]
        if d not in events_by_date:
            events_by_date[d] = []
        events_by_date[d].append({
            "coach": r["coach"],
            "time": r["time"],
            "client_name": r["client_name"],
            "course_type": r["course_type"],
        })
        # 依時間排序
        events_by_date[d].sort(
            key=lambda x: int(x["time"].split(":")[0]) * 60 + int(x["time"].split(":")[1])
        )

    cal = calendar.Calendar(firstweekday=0)
    month_weeks = cal.monthdayscalendar(year, month)

    prev_year, prev_month = (year, month - 1) if month > 1 else (year - 1, 12)
    next_year, next_month = (year, month + 1) if month < 12 else (year + 1, 1)

    return render_template(
        "calendar.html",
        year=year,
        month=month,
        month_weeks=month_weeks,
        events_by_date=events_by_date,
        coach_colors=coach_colors,
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
    )

# ---------------- 日排程 ----------------
@app.route("/admin/day")
def admin_day():
    date_str = request.args.get("date") or date.today().isoformat()
    coach_name = request.args.get("coach") or coaches[0]["name"]

    coach_names = [c["name"] for c in coaches]

    time_slots = []
    for h in range(9, 21):
        time_slots.append(f"{h}:00")
        time_slots.append(f"{h}:30")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT time, client_name, course_type
        FROM bookings
        WHERE coach = ? AND date = ?
        ORDER BY time
    """, (coach_name, date_str))
    rows = cur.fetchall()
    conn.close()

    bookings_by_time = {
        r["time"]: {
            "client_name": r["client_name"],
            "course_type": r["course_type"],
        }
        for r in rows
    }

    color = coach_colors.get(coach_name, "#D5C79A")

    return render_template(
        "day.html",
        date_str=date_str,
        coach_name=coach_name,
        coach_names=coach_names,
        time_slots=time_slots,
        bookings_by_time=bookings_by_time,
        coach_color=color,
    )
# ---------------- 會員資料（History頁面直接修改） ----------------
@app.route("/history/update", methods=["POST"])
def history_update():
    old_name = request.form.get("old_name", "").strip()
    old_birthday = request.form.get("old_birthday", "").strip()

    new_name = request.form.get("name", "").strip()
    new_birthday = request.form.get("birthday", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    gender = request.form.get("gender", "").strip()
    line_id = request.form.get("line_id", "").strip()

    if not new_name or not new_birthday:
        flash("姓名與生日為必填。", "error")
        return redirect(url_for("history"))

    conn = get_db_connection()
    cur = conn.cursor()

    # 先確認會員是否存在
    cur.execute("""
        SELECT id FROM members WHERE name = ? AND birthday = ?
    """, (old_name, old_birthday))
    member = cur.fetchone()

    if not member:
        conn.close()
        flash("找不到會員資料。", "error")
        return redirect(url_for("history"))

    member_id = member["id"]

    # 更新 members 資料
    try:
        cur.execute("""
            UPDATE members
            SET name = ?, birthday = ?, phone = ?, email = ?, gender = ?, line_id = ?
            WHERE id = ?
        """, (new_name, new_birthday, phone, email, gender, line_id, member_id))
    except sqlite3.IntegrityError:
        conn.close()
        flash("已有相同姓名＋生日的會員，請確認是否重複。", "error")
        return redirect(url_for("history"))

    # 更新 bookings 中的資料（保持一致性）
    cur.execute("""
        UPDATE bookings
        SET client_name = ?, birthday = ?, phone = ?, email = ?, gender = ?, line_id = ?
        WHERE client_name = ? AND birthday = ?
    """, (new_name, new_birthday, phone, email, gender, line_id, old_name, old_birthday))

    conn.commit()
    conn.close()

    flash("會員資料更新成功！", "success")
    return redirect(url_for("history"))

if __name__ == "__main__":
    app.run(debug=True)

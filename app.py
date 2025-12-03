import os
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, jsonify, session
)
from datetime import date
import calendar
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = "yourSuperSecretKey123"

# ---------------- 資料庫設定（PostgreSQL） ----------------
# Render 環境變數裡已經設定 DATABASE_URL
db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise RuntimeError("DATABASE_URL 未設定，請在 Render Environment 加上。")

# 有些環境會用 postgres://，SQLAlchemy 建議用 postgresql://
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ---------------- 教練設定 ----------------
coaches = [
    {"id": 1, "name": "A教練"},
    {"id": 2, "name": "B教練"},
    {"id": 3, "name": "C教練"},
]

coach_colors = {
    "A教練": "#4A90E2",
    "B教練": "#7ED321",
    "C教練": "#D0021B",
}

course_types = [
    "初階訓練",
    "核心改善",
    "姿勢評估",
    "肌力訓練",
    "伸展放鬆",
    "私人教練課程",
    "其他",
]

# ---------------- SQLAlchemy 模型 ----------------
class Member(db.Model):
    __tablename__ = "members"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    birthday = db.Column(db.String(10), nullable=False)  # YYYY-MM-DD
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))
    gender = db.Column(db.String(20))
    line_id = db.Column(db.String(80))

    __table_args__ = (
        db.UniqueConstraint("name", "birthday", name="uq_member_name_birthday"),
    )


class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    coach = db.Column(db.String(50), nullable=False)
    date = db.Column(db.String(10), nullable=False)      # YYYY-MM-DD
    time = db.Column(db.String(5), nullable=False)       # HH:MM
    note = db.Column(db.Text)

    client_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120))
    gender = db.Column(db.String(20))
    birthday = db.Column(db.String(10), nullable=False)
    line_id = db.Column(db.String(80))
    course_type = db.Column(db.String(50), nullable=False)


# ---------------- 建立資料表 ----------------
with app.app_context():
    db.create_all()

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

    bookings = (
        Booking.query
        .filter_by(coach=coach_name, date=the_date)
        .all()
    )

    reserved_times = [b.time for b in bookings]
    reserved_minutes = []
    for t in reserved_times:
        h, m = t.split(":")
        reserved_minutes.append(int(h) * 60 + int(m))

    available = []
    for t in all_times:
        h, m = t.split(":")
        minutes = int(h) * 60 + int(m)

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

    # 檢查是否與其他預約太接近
    existing = Booking.query.filter_by(coach=coach_name, date=the_date).all()
    for b in existing:
        h, m = b.time.split(":")
        old_minutes = int(h) * 60 + int(m)
        if abs(new_minutes - old_minutes) < 60:
            flash("該時段已被預約或與其他預約時間過近，請重新選擇。", "error")
            return redirect(url_for("index"))

    # 寫入 bookings
    new_booking = Booking(
        coach=coach_name,
        date=the_date,
        time=the_time,
        note=note,
        client_name=client_name,
        phone=phone,
        email=email,
        gender=gender,
        birthday=birthday,
        line_id=line_id,
        course_type=course_type
    )
    db.session.add(new_booking)

    # 更新 / 建立會員資料（以姓名 + 生日為 key）
    member = Member.query.filter_by(name=client_name, birthday=birthday).first()
    if member is None:
        member = Member(
            name=client_name,
            birthday=birthday,
            phone=phone,
            email=email,
            gender=gender,
            line_id=line_id
        )
        db.session.add(member)
    else:
        member.phone = phone
        member.email = email
        member.gender = gender
        member.line_id = line_id

    db.session.commit()

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

    query = Booking.query

    if coach_filter != "all":
        query = query.filter(Booking.coach == coach_filter)
    if date_filter:
        query = query.filter(Booking.date == date_filter)
    if course_filter != "all":
        query = query.filter(Booking.course_type == course_filter)
    if name_filter:
        query = query.filter(Booking.client_name.contains(name_filter))

    rows = query.order_by(Booking.date, Booking.time).all()

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
    b = Booking.query.get(booking_id)
    if b:
        db.session.delete(b)
        db.session.commit()
        flash("已刪除該筆預約。", "success")
    else:
        flash("找不到該筆預約。", "error")
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

        member_info = Member.query.filter_by(name=name, birthday=birthday).first()

        records = (
            Booking.query
            .filter_by(client_name=name, birthday=birthday)
            .order_by(Booking.date.desc(), Booking.time.desc())
            .all()
        )

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

    if keyword:
        rows = (
            Member.query
            .filter(Member.name.contains(keyword))
            .order_by(Member.name, Member.birthday)
            .all()
        )
    else:
        rows = Member.query.order_by(Member.name, Member.birthday).all()

    return render_template("members.html", members=rows, keyword=keyword)

# ---------------- 會員編輯 ----------------
@app.route("/member/edit/<int:member_id>", methods=["GET", "POST"])
def edit_member(member_id):
    member = Member.query.get(member_id)
    if not member:
        flash("找不到該會員。", "error")
        return redirect(url_for("members"))

    old_name = member.name
    old_birthday = member.birthday

    if request.method == "POST":
        new_name     = request.form.get("name", "").strip()
        new_birthday = request.form.get("birthday", "").strip()
        phone        = request.form.get("phone", "").strip()
        email        = request.form.get("email", "").strip()
        gender       = request.form.get("gender", "").strip()
        line_id      = request.form.get("line_id", "").strip()

        if not new_name or not new_birthday:
            flash("姓名與生日為必填。", "error")
            return redirect(url_for("edit_member", member_id=member_id))

        # 檢查是否跟其他會員衝突
        other = (
            Member.query
            .filter(Member.id != member_id,
                    Member.name == new_name,
                    Member.birthday == new_birthday)
            .first()
        )
        if other:
            flash("已有相同姓名與生日的會員，請確認是否重複。", "error")
            return redirect(url_for("edit_member", member_id=member_id))

        member.name = new_name
        member.birthday = new_birthday
        member.phone = phone
        member.email = email
        member.gender = gender
        member.line_id = line_id

        # 同步更新 bookings
        bookings = Booking.query.filter_by(
            client_name=old_name,
            birthday=old_birthday
        ).all()
        for b in bookings:
            b.client_name = new_name
            b.birthday = new_birthday
            b.phone = phone
            b.email = email
            b.gender = gender
            b.line_id = line_id

        db.session.commit()
        flash("會員資料已更新。", "success")
        return redirect(url_for("members"))

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

    rows = (
        Booking.query
        .filter(Booking.date >= first_day.isoformat(),
                Booking.date <= last_day.isoformat())
        .all()
    )

    events_by_date = {}
    for r in rows:
        d = r.date
        if d not in events_by_date:
            events_by_date[d] = []
        events_by_date[d].append({
            "coach": r.coach,
            "time": r.time,
            "client_name": r.client_name,
            "course_type": r.course_type,
        })
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

# 讓 /calendar 自動導向到 /admin/calendar（好記一點）
@app.route("/calendar")
def calendar_redirect():
    return redirect(url_for("admin_calendar"))

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

    rows = (
        Booking.query
        .filter_by(coach=coach_name, date=date_str)
        .order_by(Booking.time)
        .all()
    )

    bookings_by_time = {
        r.time: {
            "client_name": r.client_name,
            "course_type": r.course_type,
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

# ---------------- History 頁面直接修改會員資料 ----------------
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

    member = Member.query.filter_by(name=old_name, birthday=old_birthday).first()
    if not member:
        flash("找不到會員資料。", "error")
        return redirect(url_for("history"))

    # 檢查是否與其他會員衝突
    other = (
        Member.query
        .filter(Member.id != member.id,
                Member.name == new_name,
                Member.birthday == new_birthday)
        .first()
    )
    if other:
        flash("已有相同姓名＋生日的會員，請確認是否重複。", "error")
        return redirect(url_for("history"))

    member.name = new_name
    member.birthday = new_birthday
    member.phone = phone
    member.email = email
    member.gender = gender
    member.line_id = line_id

    bookings = Booking.query.filter_by(
        client_name=old_name,
        birthday=old_birthday
    ).all()
    for b in bookings:
        b.client_name = new_name
        b.birthday = new_birthday
        b.phone = phone
        b.email = email
        b.gender = gender
        b.line_id = line_id

    db.session.commit()

    flash("會員資料更新成功！", "success")
    return redirect(url_for("history"))


if __name__ == "__main__":
    # 本機測試用，Render 仍然會用 gunicorn app:app 啟動
    app.run(debug=True)

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from flask_socketio import SocketIO, emit
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import random
import os
from dotenv import load_dotenv
import pytz
import csv
import io
import json

# ==========================================================
# LOAD ENV
# ==========================================================

load_dotenv()

# ==========================================================
# APP CONFIGURATION
# ==========================================================

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "super-secret-key")

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///acid_amp.db"
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300
}

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading"
)

TIMEZONE = "Asia/Kolkata"

# ==========================================================
# DATABASE MODELS
# ==========================================================

class User(db.Model):

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(100), nullable=False, unique=True)

    email = db.Column(db.String(150), nullable=False, unique=True, index=True)

    password_hash = db.Column(db.String(200), nullable=False)

    role = db.Column(db.String(20), default="user")

    created_at = db.Column(db.DateTime)

    is_active = db.Column(db.Boolean, default=True)


class ContactMessage(db.Model):

    __tablename__ = "contacts"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(150), nullable=False)

    email = db.Column(db.String(150), nullable=False)

    subject = db.Column(db.String(200))

    message = db.Column(db.Text, nullable=False)

    status = db.Column(db.String(20), default="unread")

    created_at = db.Column(db.DateTime)


class SensorData(db.Model):

    __tablename__ = "sensor_data"

    id = db.Column(db.Integer, primary_key=True)

    voltage = db.Column(db.Float)

    current = db.Column(db.Float)

    ph = db.Column(db.Float)

    iron = db.Column(db.Float)

    copper = db.Column(db.Float)

    biofilm_status = db.Column(db.String(50))

    power = db.Column(db.Float)

    timestamp = db.Column(db.DateTime, index=True)

# ==========================================================
# TIMEZONE HELPERS
# ==========================================================

def get_local_time():

    utc_now = datetime.utcnow().replace(tzinfo=pytz.UTC)

    return utc_now.astimezone(pytz.timezone(TIMEZONE))


def format_local_time(dt):

    if not dt:
        return "N/A"

    if isinstance(dt, str):
        return dt

    return dt.astimezone(
        pytz.timezone(TIMEZONE)
    ).strftime("%Y-%m-%d %H:%M:%S")

# ==========================================================
# DATABASE INITIALIZATION
# ==========================================================

def init_db():

    with app.app_context():

        db.create_all()

        admin = User.query.filter_by(
            email="admin@acidtoamp.com"
        ).first()

        if not admin:

            admin = User(
                username="admin",
                email="admin@acidtoamp.com",
                password_hash=generate_password_hash("admin2026"),
                role="admin",
                created_at=get_local_time()
            )

            db.session.add(admin)
            db.session.commit()

            print("✅ Admin Created")
            print("admin@acidtoamp.com / admin2026")

# ==========================================================
# USER CRUD
# ==========================================================

def create_user(username, email, password, role="user"):

    if User.query.filter_by(email=email).first():
        return None

    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        role=role,
        created_at=get_local_time()
    )

    db.session.add(user)
    db.session.commit()

    return str(user.id)


def get_user_by_email(email):

    user = User.query.filter_by(email=email).first()

    if user:

        return {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "password_hash": user.password_hash,
            "role": user.role
        }

    return None


def get_all_users():

    users = User.query.order_by(
        User.created_at.desc()
    ).all()

    return [
        {
            "_id": str(u.id),
            "username": u.username,
            "email": u.email,
            "role": u.role,
            "created_at_formatted": format_local_time(u.created_at)
        }
        for u in users
    ]


def update_user(user_id, updates):

    user = User.query.get(int(user_id))

    if not user:
        return False

    for key, value in updates.items():

        if key == "password" and value:
            user.password_hash = generate_password_hash(value)

        elif key != "password_hash":
            setattr(user, key, value)

    db.session.commit()

    return True


def delete_user(user_id):

    user = User.query.get(int(user_id))

    if not user:
        return False

    db.session.delete(user)

    db.session.commit()

    return True


def check_password(user_dict, password):

    return check_password_hash(
        user_dict["password_hash"],
        password
    )

# ==========================================================
# MESSAGE CRUD
# ==========================================================

def add_message(name, email, subject, message):

    msg = ContactMessage(
        name=name,
        email=email,
        subject=subject,
        message=message,
        created_at=get_local_time()
    )

    db.session.add(msg)
    db.session.commit()

    return str(msg.id)


def get_all_messages():

    msgs = ContactMessage.query.order_by(
        ContactMessage.created_at.desc()
    ).all()

    return [
        {
            "_id": str(m.id),
            "name": m.name,
            "email": m.email,
            "subject": m.subject,
            "message": m.message,
            "status": m.status,
            "timestamp_formatted": format_local_time(m.created_at)
        }
        for m in msgs
    ]


def mark_as_read(message_id):

    msg = ContactMessage.query.get(int(message_id))

    if not msg:
        return False

    msg.status = "read"

    db.session.commit()

    return True


def delete_message(message_id):

    msg = ContactMessage.query.get(int(message_id))

    if not msg:
        return False

    db.session.delete(msg)

    db.session.commit()

    return True

# ==========================================================
# SENSOR CRUD
# ==========================================================

def add_reading(voltage, current, ph, iron, copper, biofilm_status):

    data = SensorData(
        voltage=voltage,
        current=current,
        ph=ph,
        iron=iron,
        copper=copper,
        biofilm_status=biofilm_status,
        power=round(voltage * current * 1000, 2),
        timestamp=get_local_time()
    )

    db.session.add(data)
    db.session.commit()


def get_recent_data(limit=100):

    data = SensorData.query.order_by(
        SensorData.timestamp.desc()
    ).limit(limit).all()

    return [
        {
            "_id": str(d.id),
            "voltage": d.voltage,
            "current": d.current,
            "ph": d.ph,
            "iron": d.iron,
            "copper": d.copper,
            "biofilm_status": d.biofilm_status,
            "power": d.power,
            "timestamp": format_local_time(d.timestamp)
        }
        for d in data
    ]


def clear_all_data():

    count = SensorData.query.count()

    SensorData.query.delete()

    db.session.commit()

    return count

# ==========================================================
# EXPORT FUNCTIONS
# ==========================================================

def export_csv(data):

    output = io.StringIO()

    writer = csv.DictWriter(
        output,
        fieldnames=data[0].keys()
    )

    writer.writeheader()

    writer.writerows(data)

    return output.getvalue()


# ==========================================================
# DECORATORS
# ==========================================================

def login_required(f):

    @wraps(f)
    def decorated(*args, **kwargs):

        if "user_id" not in session:

            flash("Please login first", "warning")

            return redirect(url_for("login"))

        return f(*args, **kwargs)

    return decorated


def admin_required(f):

    @wraps(f)
    def decorated(*args, **kwargs):

        if "user_id" not in session or session.get("role") != "admin":

            flash("Admin access required", "danger")

            return redirect(url_for("login"))

        return f(*args, **kwargs)

    return decorated

# ==========================================================
# ROUTES
# ==========================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email")

        password = request.form.get("password")

        user = get_user_by_email(email)

        if user and check_password(user, password):

            session["user_id"] = user["id"]

            session["username"] = user["username"]

            session["role"] = user["role"]

            flash("Login Successful", "success")

            return redirect(url_for("index"))

        flash("Invalid Credentials", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():

    session.clear()

    flash("Logged out successfully")

    return redirect(url_for("index"))

# ==========================================================
# ADMIN PANEL
# ==========================================================

@app.route("/admin")
@admin_required
def admin_panel():

    users = get_all_users()

    messages = get_all_messages()

    stats = {
        "users": User.query.count(),
        "readings": SensorData.query.count(),
        "messages": ContactMessage.query.count()
    }

    return render_template(
        "admin.html",
        users=users,
        messages=messages,
        stats=stats
    )

# ==========================================================
# SOCKET SENSOR SIMULATION
# ==========================================================

def background_sensor_task():

    while True:

        voltage = round(random.uniform(0.45, 0.55), 3)

        current = round(random.uniform(1.9, 2.4), 2)

        ph = round(random.uniform(4.9, 5.5), 2)

        iron = round(random.uniform(22, 38), 1)

        copper = round(random.uniform(8, 16), 1)

        biofilm = random.choice(["Active", "Growing", "Stable", "Peak"])

        add_reading(voltage, current, ph, iron, copper, biofilm)

        socketio.emit("sensor_update", {
            "voltage": voltage,
            "current": current,
            "ph": ph,
            "iron": iron,
            "copper": copper,
            "biofilm": biofilm,
            "power": round(voltage * current * 1000, 2),
            "timestamp": format_local_time(get_local_time())
        })

        socketio.sleep(10)

# ==========================================================
# INITIALIZATION
# ==========================================================

def init_app():

    init_db()

    socketio.start_background_task(
        background_sensor_task
    )

    print("🚀 Acid-to-Amp System Ready")


init_app()

# ==========================================================
# MAIN
# ==========================================================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False
    )

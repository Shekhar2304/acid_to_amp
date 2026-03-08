from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from flask_socketio import SocketIO, emit
from flask_bcrypt import Bcrypt
from functools import wraps
from datetime import datetime
import random
import os
import pytz
import csv
import io
import json

from config import Config
from models import db, User, SensorData, ContactMessage

from dashboard import dashboard_bp

# =========================================================
# APP INITIALIZATION
# =========================================================

app = Flask(__name__)
app.config.from_object(Config)

bcrypt = Bcrypt(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize SQLAlchemy
db.init_app(app)

# Register dashboard blueprint
app.register_blueprint(dashboard_bp)

# =========================================================
# CREATE TABLES
# =========================================================

with app.app_context():
    db.create_all()

# =========================================================
# TIMEZONE SETTINGS
# =========================================================

TIMEZONE = 'Asia/Kolkata'

def get_local_time():
    utc_now = datetime.utcnow()
    local_tz = pytz.timezone(TIMEZONE)
    return utc_now.replace(tzinfo=pytz.UTC).astimezone(local_tz)

def format_local_time(dt):
    if dt is None:
        return 'N/A'
    if isinstance(dt, str):
        return dt
    local_tz = pytz.timezone(TIMEZONE)
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    local_dt = dt.astimezone(local_tz)
    return local_dt.strftime('%Y-%m-%d %H:%M:%S')

# =========================================================
# DECORATORS
# =========================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# =========================================================
# PUBLIC ROUTES
# =========================================================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/technology')
def technology():
    return render_template('technology.html')


@app.route('/privacy')
def privacy():
    return render_template('legal/privacy.html')


@app.route('/terms')
def terms():
    return render_template('legal/terms.html')

# =========================================================
# AUTH ROUTES
# =========================================================

@app.route('/login', methods=['GET','POST'])
def login():

    if request.method == 'POST':

        email = request.form['email']
        password = request.form['password']

        user = User.get_user_by_email(email)

        if user and User.check_password(user, password):

            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']

            flash(f"Welcome back {user['username']}", "success")
            return redirect(url_for('dashboard.dashboard'))

        flash("Invalid credentials", "danger")

    return render_template('login.html')


@app.route('/register', methods=['GET','POST'])
def register():

    if request.method == 'POST':

        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        existing = User.get_user_by_email(email)

        if existing:
            flash("Email already exists", "danger")
            return render_template('register.html')

        User.create_user(username,email,password)

        flash("Registration successful", "success")
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():

    session.clear()
    flash("Logged out successfully","info")
    return redirect(url_for('index'))

# =========================================================
# CONTACT
# =========================================================

@app.route('/contact', methods=['GET','POST'])
def contact():

    if request.method == 'POST':

        name = request.form.get('name')
        email = request.form.get('email')
        subject = request.form.get('subject')
        message = request.form.get('message')

        if not name or not email or not message:
            flash("Please fill required fields","danger")
            return redirect(url_for('contact'))

        ContactMessage.add_message(name,email,subject,message)

        flash("Message sent successfully","success")
        return redirect(url_for('contact'))

    return render_template('contact.html')

# =========================================================
# ADMIN PANEL
# =========================================================

@app.route('/admin')
@admin_required
def admin_panel():

    users = User.get_all_users()
    messages = ContactMessage.get_all_messages()

    stats = {
        "users": User.query.count(),
        "readings": SensorData.query.count(),
        "messages": ContactMessage.query.count(),
        "unread_messages": ContactMessage.query.filter_by(status='unread').count(),
        "active_sessions": random.randint(8,15),
        "online_now": random.randint(3,8)
    }

    return render_template("admin.html", users=users, messages=messages, stats=stats)


@app.route('/admin/clear_data', methods=['POST'])
@admin_required
def clear_data():

    deleted = SensorData.clear_all_data()

    return jsonify({
        "success":True,
        "cleared":deleted
    })
# =========================================================
# ADMIN USER CRUD
# =========================================================

@app.route('/admin/users')
@admin_required
def admin_users():
    users = User.get_all_users()
    return jsonify(users)


@app.route('/admin/create_user', methods=['POST'])
@admin_required
def admin_create_user():

    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password', 'temp123')
    role = request.form.get('role', 'user')

    existing = User.get_user_by_email(email)

    if existing:
        return jsonify({"success": False, "error": "Email already exists"}), 400

    user_id = User.create_user(username, email, password, role)

    return jsonify({
        "success": True,
        "user_id": user_id
    })


@app.route('/admin/update_user/<user_id>', methods=['POST'])
@admin_required
def admin_update_user(user_id):

    updates = {
        "username": request.form.get("username"),
        "email": request.form.get("email"),
        "role": request.form.get("role")
    }

    success = User.update_user(user_id, updates)

    return jsonify({"success": success})


@app.route('/admin/delete_user/<user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):

    if str(session["user_id"]) == user_id:
        return jsonify({"error": "Cannot delete yourself"}), 400

    success = User.delete_user(user_id)

    return jsonify({"success": success})
# =========================================================
# ADMIN MESSAGE CRUD
# =========================================================

@app.route('/admin/message_read/<message_id>', methods=['POST'])
@admin_required
def message_read(message_id):

    success = ContactMessage.mark_as_read(message_id)

    return jsonify({"success": success})


@app.route('/admin/delete_message/<message_id>', methods=['POST'])
@admin_required
def delete_message(message_id):

    success = ContactMessage.delete_message(message_id)

    return jsonify({"success": success})


@app.route('/admin/messages/mark_all_read', methods=['POST'])
@admin_required
def mark_all_messages_read():

    count = ContactMessage.mark_all_read()

    return jsonify({
        "success": True,
        "count": count
    })
# =========================================================
# API ENDPOINTS
# =========================================================

@app.route('/api/recent-data')
@login_required
def recent_data():

    data = SensorData.get_recent_data(100)

    return jsonify(data)


@app.route('/api/live-stats')
@login_required
def live_stats():

    data = SensorData.get_recent_data(1)

    if data:
        return jsonify(data[0])

    return jsonify({})

# =========================================================
# EXPORT SYSTEM
# =========================================================

@app.route('/admin/export_report')
@admin_required
def export_report():

    export_format = request.args.get("format","csv")

    data = SensorData.get_data_for_export(10000)

    timestamp = get_local_time().strftime('%Y%m%d_%H%M%S')

    if export_format == "csv":
        return export_csv(data,timestamp)

    if export_format == "json":
        return export_json(data,timestamp)

    if export_format == "excel":
        return export_excel(data,timestamp)


def export_csv(data,timestamp):

    output = io.StringIO()

    writer = csv.DictWriter(output, fieldnames=data[0].keys())

    writer.writeheader()
    writer.writerows(data)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition":f"attachment; filename=sensor_export_{timestamp}.csv"
        }
    )


def export_json(data,timestamp):

    return Response(
        json.dumps(data,indent=2),
        mimetype="application/json",
        headers={
            "Content-Disposition":f"attachment; filename=sensor_export_{timestamp}.json"
        }
    )


def export_excel(data,timestamp):

    import pandas as pd
    from io import BytesIO

    df = pd.DataFrame(data)

    output = BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer,index=False)

    return Response(
        output.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition":f"attachment; filename=sensor_export_{timestamp}.xlsx"
        }
    )

# =========================================================
# SOCKET.IO
# =========================================================

@socketio.on("connect")
def handle_connect():
    emit("status",{"message":"Connected to Acid-to-Amp"})


@socketio.on("disconnect")
def handle_disconnect():
    print("Client disconnected")

# =========================================================
# BACKGROUND SENSOR SIMULATION
# =========================================================

def background_sensor_task():

    while True:

        voltage = round(random.uniform(0.45,0.55),3)
        current = round(random.uniform(1.9,2.4),2)
        ph = round(random.uniform(4.9,5.5),2)
        iron = round(random.uniform(22,38),1)
        copper = round(random.uniform(8,16),1)

        biofilm = random.choice(["Active","Growing","Stable","Peak"])

        SensorData.add_reading(voltage,current,ph,iron,copper,biofilm)

        socketio.emit("sensor_update",{
            "voltage":voltage,
            "current":current,
            "ph":ph,
            "iron":iron,
            "copper":copper,
            "biofilm":biofilm,
            "power":round(voltage*current*1000,2),
            "timestamp":format_local_time(get_local_time())
        })

        socketio.sleep(10)

# =========================================================
# AUTO CREATE ADMIN
# =========================================================

with app.app_context():

    admin = User.get_user_by_email("admin@acidtoamp.com")

    if not admin:
        User.create_user(
            "admin",
            "admin@acidtoamp.com",
            "admin2026",
            "admin"
        )

        print("Default admin created")

# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    socketio.start_background_task(background_sensor_task)

    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=True
    )

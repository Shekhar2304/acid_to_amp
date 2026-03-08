from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from flask_socketio import SocketIO, emit
from flask_bcrypt import Bcrypt
from functools import wraps
from datetime import datetime
import random
import os
from dotenv import load_dotenv
import pytz
import csv
import io
import json
import pandas as pd

from models import db, User, SensorData, ContactMessage
from dashboard import dashboard_bp

load_dotenv()

TIMEZONE = 'Asia/Kolkata'

app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "acid_to_amp_secret")

app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///acid_to_amp.db"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

bcrypt = Bcrypt(app)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

app.register_blueprint(dashboard_bp)


# =============================================================================
# TIME HELPERS
# =============================================================================

def get_local_time():
    utc_now = datetime.utcnow()
    local_tz = pytz.timezone(TIMEZONE)
    local_time = utc_now.replace(tzinfo=pytz.UTC).astimezone(local_tz)
    return local_time


def format_local_time(dt):

    if dt is None:
        return "N/A"

    local_tz = pytz.timezone(TIMEZONE)

    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)

    local_dt = dt.astimezone(local_tz)

    return local_dt.strftime('%Y-%m-%d %H:%M:%S')


# =============================================================================
# DECORATORS
# =============================================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):

        if 'user_id' not in session:
            flash("Please login first", "warning")
            return redirect(url_for('login'))

        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):

        if session.get('role') != 'admin':
            flash("Admin access required", "danger")
            return redirect(url_for('login'))

        return f(*args, **kwargs)

    return decorated_function


# =============================================================================
# PUBLIC ROUTES
# =============================================================================

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


# =============================================================================
# AUTH
# =============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        email = request.form['email']

        password = request.form['password']

        user = User.get_user_by_email(email)

        if user and User.check_password(user, password):

            session['user_id'] = user['_id']

            session['username'] = user['username']

            session['role'] = user['role']

            flash("Login successful", "success")

            return redirect(url_for('dashboard.dashboard'))

        flash("Invalid credentials", "danger")

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        username = request.form['username']

        email = request.form['email']

        password = request.form['password']

        if User.get_user_by_email(email):

            flash("Email already registered", "danger")

            return redirect(url_for('register'))

        User.create_user(username, email, password)

        flash("Registration successful", "success")

        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():

    session.clear()

    flash("Logged out", "info")

    return redirect(url_for('index'))


# =============================================================================
# CONTACT
# =============================================================================

@app.route('/contact', methods=['GET', 'POST'])
def contact():

    if request.method == 'POST':

        name = request.form.get('name')

        email = request.form.get('email')

        subject = request.form.get('subject')

        message = request.form.get('message')

        ContactMessage.add_message(name, email, subject, message)

        flash("Message sent successfully", "success")

        return redirect(url_for('contact'))

    return render_template('contact.html')


# =============================================================================
# ADMIN PANEL
# =============================================================================

@app.route('/admin')
@admin_required
def admin_panel():

    users = User.get_all_users()

    messages = ContactMessage.get_all_messages()

    stats = {
        "users": len(users),
        "messages": len(messages),
        "readings": len(SensorData.get_recent_data(10000))
    }

    return render_template("admin.html", users=users, messages=messages, stats=stats)


@app.route('/admin/delete_user/<user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):

    User.delete_user(user_id)

    return jsonify({"success": True})


@app.route('/admin/message_read/<message_id>', methods=['POST'])
@admin_required
def mark_read(message_id):

    ContactMessage.mark_as_read(message_id)

    return jsonify({"success": True})


@app.route('/admin/delete_message/<message_id>', methods=['DELETE'])
@admin_required
def delete_message(message_id):

    ContactMessage.delete_message(message_id)

    return jsonify({"success": True})


# =============================================================================
# API
# =============================================================================

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


# =============================================================================
# EXPORT
# =============================================================================

@app.route('/admin/export_report')
@admin_required
def export_report():

    export_format = request.args.get('format', 'csv')

    data = SensorData.get_data_for_export(10000)

    timestamp = get_local_time().strftime("%Y%m%d_%H%M%S")

    if export_format == "csv":

        output = io.StringIO()

        writer = csv.DictWriter(output, fieldnames=data[0].keys())

        writer.writeheader()

        writer.writerows(data)

        return Response(

            output.getvalue(),

            mimetype="text/csv",

            headers={
                "Content-Disposition": f"attachment;filename=sensor_export_{timestamp}.csv"
            }

        )

    elif export_format == "json":

        return Response(

            json.dumps(data, indent=2),

            mimetype="application/json",

            headers={
                "Content-Disposition": f"attachment;filename=sensor_export_{timestamp}.json"
            }

        )

    elif export_format == "excel":

        df = pd.DataFrame(data)

        output = io.BytesIO()

        with pd.ExcelWriter(output, engine='openpyxl') as writer:

            df.to_excel(writer, index=False)

        return Response(

            output.getvalue(),

            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",

            headers={
                "Content-Disposition": f"attachment;filename=sensor_export_{timestamp}.xlsx"
            }

        )


# =============================================================================
# SOCKET EVENTS
# =============================================================================

@socketio.on('connect')
def handle_connect():

    print("Client connected")

    emit("status", {"message": "Connected to Acid-to-Amp"})


@socketio.on('disconnect')
def handle_disconnect():

    print("Client disconnected")


# =============================================================================
# SENSOR SIMULATION
# =============================================================================

def background_sensor_task():

    while True:

        voltage = round(random.uniform(0.45, 0.55), 3)

        current = round(random.uniform(1.9, 2.4), 2)

        ph = round(random.uniform(4.9, 5.5), 2)

        iron = round(random.uniform(22, 38), 1)

        copper = round(random.uniform(8, 16), 1)

        biofilm = random.choice(['Active', 'Growing', 'Stable', 'Peak'])

        SensorData.add_reading(voltage, current, ph, iron, copper, biofilm)

        socketio.emit("sensor_update", {

            "voltage": voltage,
            "current": current,
            "ph": ph,
            "iron": iron,
            "copper": copper,
            "biofilm": biofilm,
            "timestamp": format_local_time(get_local_time())

        })

        socketio.sleep(10)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":

    with app.app_context():

        db.create_all()

        admin = User.get_user_by_email("admin@acidtoamp.com")

        if not admin:
            User.create_user("admin", "admin@acidtoamp.com", "admin2026", "admin")

    socketio.start_background_task(background_sensor_task)

    socketio.run(app, host="0.0.0.0", port=5000, debug=True)


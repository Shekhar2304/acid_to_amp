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

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'your-super-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or 'sqlite:///acid_amp.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

TIMEZONE = 'Asia/Kolkata'

# =============================================================================
# TIMEZONE FUNCTIONS
# =============================================================================
def get_local_time():
    utc_now = datetime.utcnow()
    local_tz = pytz.timezone(TIMEZONE)
    return utc_now.replace(tzinfo=pytz.UTC).astimezone(local_tz)

def format_local_time(dt):
    if dt is None or isinstance(dt, str):
        return str(dt) if dt else 'N/A'
    local_tz = pytz.timezone(TIMEZONE)
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(local_tz).strftime('%Y-%m-%d %H:%M:%S')

# =============================================================================
# DATABASE MODELS WITH FULL CRUD
# =============================================================================
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    email = db.Column(db.String(150), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='user')
    created_at = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)

class ContactMessage(db.Model):
    __tablename__ = 'contacts'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=False)
    subject = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='unread')
    created_at = db.Column(db.DateTime)

class SensorData(db.Model):
    __tablename__ = 'sensor_data'
    id = db.Column(db.Integer, primary_key=True)
    voltage = db.Column(db.Float, nullable=False)
    current = db.Column(db.Float, nullable=False)
    ph = db.Column(db.Float, nullable=False)
    iron = db.Column(db.Float, nullable=False)
    copper = db.Column(db.Float, nullable=False)
    biofilm_status = db.Column(db.String(50), nullable=False)
    power = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, index=True)

# =============================================================================
# USER CRUD OPERATIONS
# =============================================================================
def create_user(username, email, password, role='user'):
    try:
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
    except Exception as e:
        db.session.rollback()
        print(f"Create user error: {e}")
        return None

def get_user_by_email(email):
    try:
        user = User.query.filter_by(email=email).first()
        if user:
            return {
                'id': str(user.id),
                'username': user.username,
                'email': user.email,
                'password_hash': user.password_hash,
                'role': user.role,
                'created_at': user.created_at
            }
        return None
    except:
        return None

def get_all_users():
    try:
        users = User.query.order_by(User.created_at.desc()).all()
        return [{
            '_id': str(u.id),
            'username': u.username,
            'email': u.email,
            'role': u.role,
            'created_at_formatted': format_local_time(u.created_at),
            'is_active': u.is_active
        } for u in users]
    except:
        return []

def update_user(user_id, updates):
    try:
        user = User.query.get(int(user_id))
        if user:
            for key, value in updates.items():
                if key == 'password' and value:
                    user.password_hash = generate_password_hash(value)
                elif key != 'password_hash':
                    setattr(user, key, value)
            db.session.commit()
            return True
        return False
    except:
        db.session.rollback()
        return False

def delete_user(user_id):
    try:
        user = User.query.get(int(user_id))
        if user:
            db.session.delete(user)
            db.session.commit()
            return True
        return False
    except:
        db.session.rollback()
        return False

def check_password(user_dict, password):
    try:
        return check_password_hash(user_dict['password_hash'], password)
    except:
        return False

# =============================================================================
# CONTACT MESSAGE CRUD
# =============================================================================
def add_message(name, email, subject, message):
    try:
        msg = ContactMessage(
            name=name, email=email, subject=subject, 
            message=message, created_at=get_local_time()
        )
        db.session.add(msg)
        db.session.commit()
        return str(msg.id)
    except:
        db.session.rollback()
        return None

def get_all_messages():
    try:
        msgs = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
        return [{
            '_id': str(m.id), 'name': m.name, 'email': m.email,
            'subject': m.subject, 'message': m.message,
            'status': m.status, 'timestamp_formatted': format_local_time(m.created_at)
        } for m in msgs]
    except:
        return []

def mark_as_read(message_id):
    try:
        msg = ContactMessage.query.get(int(message_id))
        if msg:
            msg.status = 'read'
            db.session.commit()
            return True
        return False
    except:
        db.session.rollback()
        return False

def delete_message(message_id):
    try:
        msg = ContactMessage.query.get(int(message_id))
        if msg:
            db.session.delete(msg)
            db.session.commit()
            return True
        return False
    except:
        db.session.rollback()
        return False

# =============================================================================
# SENSOR DATA CRUD
# =============================================================================
def add_reading(voltage, current, ph, iron, copper, biofilm_status):
    try:
        power = round(voltage * current * 1000, 2)
        data = SensorData(
            voltage=voltage, current=current, ph=ph,
            iron=iron, copper=copper, biofilm_status=biofilm_status,
            power=power, timestamp=get_local_time()
        )
        db.session.add(data)
        db.session.commit()
        return str(data.id)
    except:
        db.session.rollback()
        return None

def get_recent_data(limit=100):
    try:
        data = SensorData.query.order_by(SensorData.timestamp.desc()).limit(limit).all()
        return [{
            '_id': str(d.id), 'voltage': float(d.voltage), 'current': float(d.current),
            'ph': float(d.ph), 'iron': float(d.iron), 'copper': float(d.copper),
            'biofilm_status': d.biofilm_status, 'power': float(d.power) if d.power else 0,
            'timestamp': format_local_time(d.timestamp)
        } for d in data]
    except:
        return []

def get_data_for_export(limit=10000):
    try:
        data = SensorData.query.order_by(SensorData.timestamp.desc()).limit(limit).all()
        return [{
            'Timestamp': format_local_time(d.timestamp),
            'Voltage (V)': float(d.voltage),
            'Current (mA)': float(d.current),
            'pH': float(d.ph),
            'Iron (mg/L)': float(d.iron),
            'Copper (mg/L)': float(d.copper),
            'Biofilm': d.biofilm_status,
            'Power (mW)': float(d.power) if d.power else 0
        } for d in data]
    except:
        return []

def clear_all_data():
    try:
        count = SensorData.query.count()
        SensorData.query.delete()
        db.session.commit()
        return count
    except:
        db.session.rollback()
        return 0

# =============================================================================
# DECORATORS
# =============================================================================
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

# =============================================================================
# ROUTES - PUBLIC
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
# AUTH ROUTES
# =============================================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '')
        password = request.form.get('password', '')
        user = get_user_by_email(email)
        
        if user and check_password(user, password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash(f"Welcome back {user['username']}", "success")
            return redirect(url_for('index'))  # Fixed dashboard redirect
        flash("Invalid credentials", "danger")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '')
        email = request.form.get('email', '')
        password = request.form.get('password', '')
        
        existing = get_user_by_email(email)
        if existing:
            flash("Email already exists", "danger")
            return render_template('register.html')
        
        if create_user(username, email, password):
            flash("Registration successful", "success")
            return redirect(url_for('login'))
        flash("Registration failed", "danger")
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully", "info")
    return redirect(url_for('index'))

# =============================================================================
# CONTACT ROUTES
# =============================================================================
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name', '')
        email = request.form.get('email', '')
        subject = request.form.get('subject', '')
        message = request.form.get('message', '')
        
        if name and email and message:
            add_message(name, email, subject, message)
            flash("Message sent successfully", "success")
        else:
            flash("Please fill required fields", "danger")
        return redirect(url_for('contact'))
    return render_template('contact.html')

# =============================================================================
# ADMIN PANEL - FULL CRUD
# =============================================================================
@app.route('/admin')
@admin_required
def admin_panel():
    users = get_all_users()
    messages = get_all_messages()
    
    stats = {
        "users": User.query.count(),
        "readings": SensorData.query.count(),
        "messages": ContactMessage.query.count(),
        "unread_messages": ContactMessage.query.filter_by(status='unread').count(),
        "active_sessions": random.randint(8,15),
        "online_now": random.randint(3,8)
    }
    return render_template("admin.html", users=users, messages=messages, stats=stats)

# User CRUD API
@app.route('/admin/users', methods=['GET'])
@admin_required
def admin_users():
    return jsonify(get_all_users())

@app.route('/admin/create_user', methods=['POST'])
@admin_required
def admin_create_user():
    username = request.form.get('username', '')
    email = request.form.get('email', '')
    password = request.form.get('password', 'temp123')
    role = request.form.get('role', 'user')
    
    if get_user_by_email(email):
        return jsonify({'success': False, 'error': 'Email exists'}), 400
    
    user_id = create_user(username, email, password, role)
    return jsonify({'success': bool(user_id), 'user_id': user_id})

@app.route('/admin/update_user/<user_id>', methods=['POST'])
@admin_required
def admin_update_user(user_id):
    updates = {
        'username': request.form.get('username', ''),
        'email': request.form.get('email', ''),
        'role': request.form.get('role', ''),
        'password': request.form.get('password', '')
    }
    success = update_user(user_id, updates)
    return jsonify({'success': success})

@app.route('/admin/delete_user/<user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    if session['user_id'] == user_id:
        return jsonify({'error': 'Cannot delete yourself'}), 400
    success = delete_user(user_id)
    return jsonify({'success': success})

# Message CRUD API
@app.route('/admin/messages', methods=['GET'])
@admin_required
def admin_messages():
    return jsonify(get_all_messages())

@app.route('/admin/message_read/<message_id>', methods=['POST'])
@admin_required
def admin_message_read(message_id):
    return jsonify({'success': mark_as_read(message_id)})

@app.route('/admin/delete_message/<message_id>', methods=['POST'])
@admin_required
def admin_delete_message(message_id):
    return jsonify({'success': delete_message(message_id)})

@app.route('/admin/mark_all_read', methods=['POST'])
@admin_required
def admin_mark_all_read():
    ContactMessage.query.filter_by(status='unread').update({'status': 'read'})
    db.session.commit()
    return jsonify({'success': True})

# Sensor Data API
@app.route('/admin/clear_data', methods=['POST'])
@admin_required
def clear_data():
    deleted = clear_all_data()
    return jsonify({"success": True, "cleared": deleted})

# =============================================================================
# API ENDPOINTS
# =============================================================================
@app.route('/api/recent-data')
@login_required
def recent_data():
    return jsonify(get_recent_data(100))

@app.route('/api/live-stats')
@login_required
def live_stats():
    data = get_recent_data(1)
    return jsonify(data[0] if data else {})

# =============================================================================
# EXPORT SYSTEM
# =============================================================================
@app.route('/admin/export_report')
@admin_required
def export_report():
    export_format = request.args.get("format", "csv")
    data = get_data_for_export(10000)
    timestamp = get_local_time().strftime('%Y%m%d_%H%M%S')
    
    if export_format == "csv":
        return export_csv(data, timestamp)
    elif export_format == "json":
        return export_json(data, timestamp)
    return jsonify({'error': 'Unsupported format'}), 400

def export_csv(data, timestamp):
    output = io.StringIO()
    if data:
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    else:
        output.write('No data available')
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=sensor_export_{timestamp}.csv"}
    )

def export_json(data, timestamp):
    return Response(
        json.dumps(data, indent=2, default=str),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename=sensor_export_{timestamp}.json"}
    )

# =============================================================================
# SOCKET.IO
# =============================================================================
@socketio.on("connect")
def handle_connect():
    emit("status", {"message": "Connected to Acid-to-Amp"})

@socketio.on("disconnect")
def handle_disconnect():
    print("Client disconnected")

# =============================================================================
# BACKGROUND TASK
# =============================================================================
def background_sensor_task():
    while True:
        try:
            voltage = round(random.uniform(0.45, 0.55), 3)
            current = round(random.uniform(1.9, 2.4), 2)
            ph = round(random.uniform(4.9, 5.5), 2)
            iron = round(random.uniform(22, 38), 1)
            copper = round(random.uniform(8, 16), 1)
            biofilm = random.choice(["Active", "Growing", "Stable", "Peak"])
            
            add_reading(voltage, current, ph, iron, copper, biofilm)
            
            socketio.emit("sensor_update", {
                "voltage": voltage, "current": current, "ph": ph,
                "iron": iron, "copper": copper, "biofilm": biofilm,
                "power": round(voltage * current * 1000, 2),
                "timestamp": format_local_time(get_local_time())
            })
            socketio.sleep(10)
        except:
            socketio.sleep(10)

# =============================================================================
# INITIALIZATION
# =============================================================================
@app.before_first_request
def create_tables_and_admin():
    db.create_all()
    if not get_user_by_email("admin@acidtoamp.com"):
        create_user("admin", "admin@acidtoamp.com", "admin2026", "admin")
        print("✅ Default admin created: admin@acidtoamp.com / admin2026")

# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    socketio.start_background_task(background_sensor_task)
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=False)

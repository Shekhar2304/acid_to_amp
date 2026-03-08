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
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', logger=False, engineio_logger=False)

TIMEZONE = 'Asia/Kolkata'

# =============================================================================
# MODELS (Self-contained - NO external imports)
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
    voltage = db.Column(db.Float)
    current = db.Column(db.Float)
    ph = db.Column(db.Float)
    iron = db.Column(db.Float)
    copper = db.Column(db.Float)
    biofilm_status = db.Column(db.String(50))
    power = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, index=True)

# =============================================================================
# TIMEZONE HELPERS
# =============================================================================
def get_local_time():
    utc_now = datetime.utcnow().replace(tzinfo=pytz.UTC)
    return utc_now.astimezone(pytz.timezone(TIMEZONE))

def format_local_time(dt):
    if not dt:
        return 'N/A'
    if isinstance(dt, str):
        return dt
    return dt.astimezone(pytz.timezone(TIMEZONE)).strftime('%Y-%m-%d %H:%M:%S')

# =============================================================================
# CRUD FUNCTIONS
# =============================================================================
def init_db():
    """GUNICORN-SAFE DATABASE INITIALIZATION"""
    with app.app_context():
        db.create_all()
        
        # Create admin user
        admin = User.query.filter_by(email='admin@acidtoamp.com').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@acidtoamp.com',
                password_hash=generate_password_hash('admin2026'),
                role='admin',
                created_at=get_local_time()
            )
            db.session.add(admin)
            db.session.commit()
            print("✅ Admin created: admin@acidtoamp.com / admin2026")

# User CRUD
def create_user(username, email, password, role='user'):
    try:
        if User.query.filter_by(email=email).first():
            return None
        user = User(
            username=username, email=email,
            password_hash=generate_password_hash(password),
            role=role, created_at=get_local_time()
        )
        db.session.add(user)
        db.session.commit()
        return str(user.id)
    except:
        db.session.rollback()
        return None

def get_user_by_email(email):
    user = User.query.filter_by(email=email).first()
    if user:
        return {
            'id': str(user.id), 'username': user.username,
            'email': user.email, 'password_hash': user.password_hash,
            'role': user.role
        }
    return None

def get_all_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return [{
        '_id': str(u.id), 'username': u.username, 'email': u.email,
        'role': u.role, 'created_at_formatted': format_local_time(u.created_at)
    } for u in users]

def update_user(user_id, updates):
    user = User.query.get(int(user_id))
    if not user:
        return False
    for key, value in updates.items():
        if key == 'password' and value:
            user.password_hash = generate_password_hash(value)
        elif key != 'password_hash':
            setattr(user, key, value)
    try:
        db.session.commit()
        return True
    except:
        db.session.rollback()
        return False

def delete_user(user_id):
    user = User.query.get(int(user_id))
    if not user:
        return False
    try:
        db.session.delete(user)
        db.session.commit()
        return True
    except:
        db.session.rollback()
        return False

def check_password(user_dict, password):
    return check_password_hash(user_dict['password_hash'], password)

# Message CRUD
def add_message(name, email, subject, message):
    msg = ContactMessage(
        name=name, email=email, subject=subject,
        message=message, created_at=get_local_time()
    )
    try:
        db.session.add(msg)
        db.session.commit()
        return str(msg.id)
    except:
        db.session.rollback()
        return None

def get_all_messages():
    msgs = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
    return [{
        '_id': str(m.id), 'name': m.name, 'email': m.email,
        'subject': m.subject, 'message': m.message[:100] + '...',
        'status': m.status, 'timestamp_formatted': format_local_time(m.created_at)
    } for m in msgs]

def mark_as_read(message_id):
    msg = ContactMessage.query.get(int(message_id))
    if msg:
        msg.status = 'read'
        db.session.commit()
        return True
    return False

def delete_message(message_id):
    msg = ContactMessage.query.get(int(message_id))
    if msg:
        db.session.delete(msg)
        db.session.commit()
        return True
    return False

# Sensor CRUD
def add_reading(voltage, current, ph, iron, copper, biofilm_status):
    data = SensorData(
        voltage=voltage, current=current, ph=ph,
        iron=iron, copper=copper, biofilm_status=biofilm_status,
        power=round(voltage * current * 1000, 2),
        timestamp=get_local_time()
    )
    try:
        db.session.add(data)
        db.session.commit()
        return True
    except:
        db.session.rollback()
        return False

def get_recent_data(limit=100):
    data = SensorData.query.order_by(SensorData.timestamp.desc()).limit(limit).all()
    return [{
        '_id': str(d.id), 'voltage': float(d.voltage or 0),
        'current': float(d.current or 0), 'ph': float(d.ph or 0),
        'iron': float(d.iron or 0), 'copper': float(d.copper or 0),
        'biofilm_status': d.biofilm_status or 'Unknown',
        'power': float(d.power or 0), 'timestamp': format_local_time(d.timestamp)
    } for d in data]

def get_data_for_export(limit=10000):
    data = SensorData.query.order_by(SensorData.timestamp.desc()).limit(limit).all()
    return [{
        'Timestamp': format_local_time(d.timestamp),
        'Voltage (V)': float(d.voltage or 0),
        'Current (mA)': float(d.current or 0),
        'pH': float(d.ph or 0),
        'Iron (mg/L)': float(d.iron or 0),
        'Copper (mg/L)': float(d.copper or 0),
        'Biofilm': d.biofilm_status or 'Unknown',
        'Power (mW)': float(d.power or 0)
    } for d in data]

def clear_all_data():
    count = SensorData.query.count()
    SensorData.query.delete()
    db.session.commit()
    return count

# =============================================================================
# DECORATORS
# =============================================================================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# =============================================================================
# ROUTES
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
            return redirect(url_for('index'))
        flash("Invalid credentials", "danger")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '')
        email = request.form.get('email', '')
        password = request.form.get('password', '')
        user_id = create_user(username, email, password)
        if user_id:
            flash("Registration successful", "success")
            return redirect(url_for('login'))
        flash("Registration failed - email may exist", "danger")
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully", "info")
    return redirect(url_for('index'))

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

# Admin CRUD APIs
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
    user_id = create_user(username, email, password, role)
    return jsonify({'success': bool(user_id), 'user_id': user_id})

@app.route('/admin/update_user/<user_id>', methods=['POST'])
@admin_required
def admin_update_user(user_id):
    updates = {
        'username': request.form.get('username', ''),
        'email': request.form.get('email', ''),
        'role': request.form.get('role', '')
    }
    return jsonify({'success': update_user(user_id, updates)})

@app.route('/admin/delete_user/<user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    if session['user_id'] == user_id:
        return jsonify({'error': 'Cannot delete yourself'}), 400
    return jsonify({'success': delete_user(user_id)})

@app.route('/admin/clear_data', methods=['POST'])
@admin_required
def admin_clear_data():
    deleted = clear_all_data()
    return jsonify({"success": True, "cleared": deleted})

@app.route('/api/recent-data')
@login_required
def api_recent_data():
    return jsonify(get_recent_data(100))

@app.route('/admin/export_report')
@admin_required
def admin_export_report():
    data = get_data_for_export(10000)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
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

# SocketIO
@socketio.on("connect")
def handle_connect():
    emit("status", {"message": "Connected to Acid-to-Amp"})

# Background task
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
# GUNICORN PRODUCTION INITIALIZATION
# =============================================================================
def init_app():
    """Call this ONCE at startup for Gunicorn"""
    init_db()
    socketio.start_background_task(background_sensor_task)
    print("🚀 Acid-to-Amp Production Ready!")
    print("👤 Admin: admin@acidtoamp.com / admin2026")
    print(f"🌐 Running on port {os.environ.get('PORT', 5000)}")

# Call initialization
init_app()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=False)

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from flask_socketio import SocketIO
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

# Initialize extensions SAFELY
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', logger=False, engineio_logger=False)

TIMEZONE = 'Asia/Kolkata'

# =============================================================================
# SAFE MODEL DEFINITIONS
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
# SAFE MODEL METHODS
# =============================================================================
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
    return dt.astimezone(local_tz).strftime('%Y-%m-%d %H:%M:%S')

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
    except:
        db.session.rollback()
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
                'role': user.role
            }
        return None
    except:
        return None

def get_all_users():
    try:
        users = User.query.order_by(User.created_at.desc()).all()
        result = []
        for u in users:
            result.append({
                '_id': str(u.id),
                'username': u.username,
                'email': u.email,
                'role': u.role,
                'created_at_formatted': format_local_time(u.created_at)
            })
        return result
    except:
        return []

def update_user(user_id, updates):
    try:
        user = User.query.get(int(user_id))
        if user:
            for key, value in updates.items():
                if key != 'password_hash':
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

def add_contact_message(name, email, subject, message):
    try:
        msg = ContactMessage(
            name=name,
            email=email,
            subject=subject,
            message=message,
            created_at=get_local_time()
        )
        db.session.add(msg)
        db.session.commit()
        return msg.id
    except:
        db.session.rollback()
        return None

def get_all_messages():
    try:
        msgs = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
        result = []
        for m in msgs:
            result.append({
                '_id': str(m.id),
                'name': m.name,
                'email': m.email,
                'subject': m.subject,
                'message': m.message,
                'status': m.status,
                'timestamp_formatted': format_local_time(m.created_at)
            })
        return result
    except:
        return []

def mark_message_read(message_id):
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

def add_sensor_reading(voltage, current, ph, iron, copper, biofilm_status):
    try:
        power = round(voltage * current * 1000, 2)
        data = SensorData(
            voltage=voltage,
            current=current,
            ph=ph,
            iron=iron,
            copper=copper,
            biofilm_status=biofilm_status,
            power=power,
            timestamp=get_local_time()
        )
        db.session.add(data)
        db.session.commit()
        return data.id
    except:
        db.session.rollback()
        return None

def get_recent_sensor_data(limit=100):
    try:
        data = SensorData.query.order_by(SensorData.timestamp.desc()).limit(limit).all()
        result = []
        for item in data:
            result.append({
                '_id': str(item.id),
                'voltage': float(item.voltage),
                'current': float(item.current),
                'ph': float(item.ph),
                'iron': float(item.iron),
                'copper': float(item.copper),
                'biofilm_status': item.biofilm_status,
                'power': float(item.power) if item.power else 0,
                'timestamp': format_local_time(item.timestamp)
            })
        return result
    except:
        return []

def get_sensor_data_export(limit=10000):
    try:
        data = SensorData.query.order_by(SensorData.timestamp.desc()).limit(limit).all()
        result = []
        for item in data:
            result.append({
                'Timestamp': format_local_time(item.timestamp),
                'Voltage (V)': float(item.voltage),
                'Current (mA)': float(item.current),
                'pH': float(item.ph),
                'Iron (mg/L)': float(item.iron),
                'Copper (mg/L)': float(item.copper),
                'Biofilm': item.biofilm_status,
                'Power (mW)': float(item.power) if item.power else 0
            })
        return result
    except:
        return []

def clear_all_sensor_data():
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
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Admin access required', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# =============================================================================
# ROUTES
# =============================================================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/privacy')
def privacy():
    return render_template('legal/privacy.html')

@app.route('/terms')
def terms():
    return render_template('legal/terms.html')

@app.route('/technology')
def technology():
    return render_template('technology.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name', '')
        email = request.form.get('email', '')
        subject = request.form.get('subject', '')
        message = request.form.get('message', '')
        
        if name and email and message:
            add_contact_message(name, email, subject, message)
            flash('Your message has been sent. Thank you!', 'success')
        else:
            flash('Please fill in all required fields.', 'danger')
        return redirect(url_for('contact'))
    
    return render_template('contact.html')

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
            flash(f'Welcome back, {user["username"]}!', 'success')
            return redirect(url_for('index'))
        flash('Invalid credentials', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '')
        email = request.form.get('email', '')
        password = request.form.get('password', '')
        
        if get_user_by_email(email):
            flash('Email already registered', 'danger')
        else:
            create_user(username, email, password)
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'info')
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
def admin_panel():
    if session.get('role') != 'admin':
        flash('Admin access required', 'danger')
        return redirect(url_for('login'))
    
    users = get_all_users()
    messages = get_all_messages()
    
    stats = {
        'users': User.query.count(),
        'readings': SensorData.query.count(),
        'messages': ContactMessage.query.count(),
        'unread_messages': ContactMessage.query.filter_by(status='unread').count(),
        'active_sessions': random.randint(8, 15),
        'online_now': random.randint(3, 8)
    }
    return render_template('admin.html', users=users, messages=messages, stats=stats)

@app.route('/admin/users')
@login_required
def admin_users():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Admin required'}), 403
    return jsonify(get_all_users())

@app.route('/admin/create_user', methods=['POST'])
@login_required
def admin_create_user():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Admin required'}), 403
    
    username = request.form.get('username', '')
    email = request.form.get('email', '')
    password = request.form.get('password', 'temp123')
    role = request.form.get('role', 'user')
    
    if get_user_by_email(email):
        return jsonify({'success': False, 'error': 'Email already exists'}), 400
    
    user_id = create_user(username, email, password, role)
    return jsonify({'success': True, 'user_id': user_id})

@app.route('/admin/clear_data', methods=['POST'])
@login_required
def admin_clear_data():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Admin required'}), 403
    deleted = clear_all_sensor_data()
    return jsonify({'success': True, 'cleared': deleted})

@app.route('/api/recent-data')
@login_required
def api_recent_data():
    return jsonify(get_recent_sensor_data(100))

@app.route('/admin/export_report')
@login_required
def admin_export_report():
    if session.get('role') != 'admin':
        return {"error": "Admin required"}, 403
    
    export_format = request.args.get('format', 'csv').lower()
    sensor_data = get_sensor_data_export(10000)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if export_format == 'csv':
        output = io.StringIO()
        if sensor_data:
            fieldnames = sensor_data[0].keys()
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(sensor_data)
        else:
            output.write('Message,No data available')
        
        filename = f"sensor_export_{timestamp}.csv"
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    
    return {"error": "Unsupported format"}, 400

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return "Page not found", 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return "Internal server error", 500

# =============================================================================
# MAIN - RAILWAY READY
# =============================================================================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Create admin user
        if not get_user_by_email('admin@acidtoamp.com'):
            create_user('admin', 'admin@acidtoamp.com', 'admin2026', 'admin')
            print("✅ Admin created: admin@acidtoamp.com / admin2026")
    
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Starting on port {port}")
    socketio.run(app, debug=False, host='0.0.0.0', port=port)

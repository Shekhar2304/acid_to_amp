from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from flask_socketio import SocketIO, emit
from flask_bcrypt import Bcrypt
import sqlite3
from functools import wraps
from datetime import datetime, timedelta
import random
import os
from dotenv import load_dotenv
import pytz
import csv
import io
import json
import pandas as pd
import shutil

# Import dashboard blueprint SAFELY
try:
    from dashboard import dashboard_bp
    HAS_DASHBOARD = True
except ImportError:
    HAS_DASHBOARD = False
    print("⚠️ Dashboard blueprint not found - continuing without it")

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'your-super-secret-key-change-in-production'

# SQLite configuration
DATABASE = os.environ.get('DATABASE_PATH', 'acid_amp.db')
app.config['DATABASE'] = DATABASE

# Set your timezone
TIMEZONE = 'Asia/Kolkata'

bcrypt = Bcrypt(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# =============================================================================
# DATABASE HELPER FUNCTIONS
# =============================================================================

def get_db_connection():
    """Get SQLite database connection with foreign keys enabled"""
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

def init_db():
    """Initialize database with all required tables"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    # Create sensor_data table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voltage REAL NOT NULL,
            current REAL NOT NULL,
            ph REAL NOT NULL,
            iron REAL NOT NULL,
            copper REAL NOT NULL,
            biofilm_status TEXT NOT NULL,
            power REAL NOT NULL,
            timestamp TEXT NOT NULL
        )
    ''')
    
    # Create contacts table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            subject TEXT,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'unread',
            created_at TEXT NOT NULL
        )
    ''')
    
    # Indexes for performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sensor_timestamp ON sensor_data(timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_contacts_status ON contacts(status)')
    
    conn.commit()
    conn.close()
    print("✅ Database tables initialized")

# =============================================================================
# TIMEZONE HELPER FUNCTIONS
# =============================================================================

def get_local_time():
    """Get current time in local timezone"""
    utc_now = datetime.utcnow()
    local_tz = pytz.timezone(TIMEZONE)
    local_time = utc_now.replace(tzinfo=pytz.UTC).astimezone(local_tz)
    return local_time

def format_local_time(dt):
    """Format datetime to local timezone string"""
    if dt is None:
        return 'N/A'
    if isinstance(dt, str):
        return dt
    local_tz = pytz.timezone(TIMEZONE)
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    local_dt = dt.astimezone(local_tz)
    return local_dt.strftime('%Y-%m-%d %H:%M:%S')

# =============================================================================
# MODELS (SQLite versions)
# =============================================================================

class User:
    @staticmethod
    def create_user(username, email, password, role='user'):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, role, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (username, email, password_hash, role, get_local_time()))
            conn.commit()
            return str(cursor.lastrowid)
        finally:
            conn.close()
    
    @staticmethod
    def get_user_by_email(email):
        conn = get_db_connection()
        try:
            user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
            if user:
                user_dict = dict(user)
                user_dict['id'] = str(user_dict['id'])
                return user_dict
            return None
        finally:
            conn.close()
    
    @staticmethod
    def get_all_users():
        conn = get_db_connection()
        try:
            users = conn.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
            users_list = []
            for user in users:
                user_dict = dict(user)
                user_dict['_id'] = str(user_dict.pop('id'))
                if user_dict.get('created_at'):
                    user_dict['created_at_formatted'] = format_local_time(user_dict['created_at'])
                users_list.append(user_dict)
            return users_list
        finally:
            conn.close()
    
    @staticmethod
    def update_user(user_id, updates):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
            values = list(updates.values()) + [user_id]
            cursor.execute(f'UPDATE users SET {set_clause} WHERE id = ?', values)
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    @staticmethod
    def delete_user(user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    @staticmethod
    def check_password(user, password):
        return bcrypt.check_password_hash(user['password_hash'], password)

class SensorData:
    @staticmethod
    def add_reading(voltage, current, ph, iron, copper, biofilm_status):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            power = round(voltage * current * 1000, 2)
            cursor.execute('''
                INSERT INTO sensor_data (voltage, current, ph, iron, copper, biofilm_status, power, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (voltage, current, ph, iron, copper, biofilm_status, power, get_local_time()))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()
    
    @staticmethod
    def get_recent_data(limit=100):
        conn = get_db_connection()
        try:
            data = conn.execute('SELECT * FROM sensor_data ORDER BY timestamp DESC LIMIT ?', (limit,)).fetchall()
            data_list = []
            for item in data:
                item_dict = dict(item)
                item_dict['_id'] = str(item_dict.pop('id'))
                if item_dict.get('timestamp'):
                    item_dict['timestamp'] = format_local_time(item_dict['timestamp'])
                data_list.append(item_dict)
            return data_list
        finally:
            conn.close()
    
    @staticmethod
    def get_data_for_export(limit=10000):
        conn = get_db_connection()
        try:
            data = conn.execute('SELECT * FROM sensor_data ORDER BY timestamp DESC LIMIT ?', (limit,)).fetchall()
            formatted_data = []
            for item in data:
                item_dict = dict(item)
                formatted_data.append({
                    'Timestamp': format_local_time(item_dict.get('timestamp')),
                    'Voltage (V)': item_dict.get('voltage', 0),
                    'Current (mA)': item_dict.get('current', 0),
                    'pH': item_dict.get('ph', 0),
                    'Iron (mg/L)': item_dict.get('iron', 0),
                    'Copper (mg/L)': item_dict.get('copper', 0),
                    'Biofilm': item_dict.get('biofilm_status', 'Unknown'),
                    'Power (mW)': item_dict.get('power', 0)
                })
            return formatted_data
        finally:
            conn.close()
    
    @staticmethod
    def clear_all_data():
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM sensor_data')
            count = cursor.rowcount
            conn.commit()
            return count
        finally:
            conn.close()

class ContactMessage:
    @staticmethod
    def add_message(name, email, subject, message):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO contacts (name, email, subject, message, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (name, email, subject, message, get_local_time()))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()
    
    @staticmethod
    def get_all_messages():
        conn = get_db_connection()
        try:
            messages = conn.execute('SELECT * FROM contacts ORDER BY created_at DESC').fetchall()
            messages_list = []
            for msg in messages:
                msg_dict = dict(msg)
                msg_dict['_id'] = str(msg_dict.pop('id'))
                if msg_dict.get('created_at'):
                    msg_dict['created_at_formatted'] = format_local_time(msg_dict['created_at'])
                messages_list.append(msg_dict)
            return messages_list
        finally:
            conn.close()
    
    @staticmethod
    def mark_as_read(message_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE contacts SET status = "read" WHERE id = ?', (message_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    @staticmethod
    def delete_message(message_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM contacts WHERE id = ?', (message_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    @staticmethod
    def mark_all_read():
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE contacts SET status = "read" WHERE status = "unread"')
            count = cursor.rowcount
            conn.commit()
            return count
        finally:
            conn.close()

# =============================================================================
# CRITICAL: INITIALIZE DATABASE ON EVERY STARTUP (Render/Gunicorn fix)
# =============================================================================
print("🚀 Initializing Acid-to-Amp Bioelectric System...")
init_db()

# Auto-create admin user
admin = User.get_user_by_email('admin@acidtoamp.com')
if not admin:
    User.create_user('admin', 'admin@acidtoamp.com', 'admin2026', 'admin')
    print("✅ Admin created: admin@acidtoamp.com / admin2026")

# Safely register dashboard blueprint
if HAS_DASHBOARD:
    app.register_blueprint(dashboard_bp)
    print("✅ Dashboard blueprint registered")

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
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        
        user = User.get_user_by_email(session.get('email', ''))
        if not user or user.get('role') != 'admin':
            flash('Admin access required', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# =============================================================================
# ROUTES - PUBLIC
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
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        
        if not all([name, email, message]):
            flash('Please fill in all required fields.', 'danger')
            return render_template('contact.html')
        
        ContactMessage.add_message(name, email, subject, message)
        flash('Your message has been sent. Thank you!', 'success')
        return render_template('contact.html')
    
    return render_template('contact.html')

@app.route('/debug/time-diagnostic')
def time_diagnostic():
    import time
    system_time = datetime.now()
    utc_time = datetime.utcnow()
    india_tz = pytz.timezone('Asia/Kolkata')
    india_time = datetime.now(india_tz)
    
    return jsonify({
        'system_time': system_time.strftime('%Y-%m-%d %H:%M:%S'),
        'utc_time': utc_time.strftime('%Y-%m-%d %H:%M:%S'),
        'india_time': india_time.strftime('%Y-%m-%d %H:%M:%S'),
        'timezone_setting': TIMEZONE
    })

# =============================================================================
# ROUTES - AUTH
# =============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        user = User.get_user_by_email(email)
        if user and User.check_password(user, password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['email'] = user['email']
            flash(f'Welcome back, {user["username"]}!', 'success')
            
            # Redirect to dashboard if exists, otherwise admin
            if HAS_DASHBOARD:
                return redirect(url_for('dashboard.dashboard'))
            return redirect(url_for('admin_panel'))
        flash('Invalid credentials', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        if not all([username, email, password]):
            flash('Please fill all fields.', 'danger')
            return render_template('register.html')
        
        existing = User.get_user_by_email(email)
        if existing:
            flash('Email already registered', 'danger')
            return render_template('register.html')
        
        User.create_user(username, email, password)
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('Logged out successfully', 'info')
    return redirect(url_for('index'))

# =============================================================================
# API ENDPOINTS
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
    return jsonify(data[0] if data else {})

# =============================================================================
# ROUTES - ADMIN PANEL
# =============================================================================

@app.route('/admin')
@admin_required
def admin_panel():
    users = User.get_all_users()
    messages = ContactMessage.get_all_messages()
    
    conn = get_db_connection()
    try:
        stats = {
            'users': conn.execute('SELECT COUNT(*) FROM users').fetchone()[0],
            'readings': conn.execute('SELECT COUNT(*) FROM sensor_data').fetchone()[0],
            'messages': conn.execute('SELECT COUNT(*) FROM contacts').fetchone()[0],
            'unread_messages': conn.execute('SELECT COUNT(*) FROM contacts WHERE status = "unread"').fetchone()[0],
            'active_sessions': random.randint(8, 15),
            'online_now': random.randint(3, 8)
        }
    finally:
        conn.close()
    
    return render_template('admin.html', users=users, messages=messages, stats=stats)

@app.route('/admin/users')
@admin_required
def admin_users():
    return jsonify(User.get_all_users())

@app.route('/admin/create_user', methods=['POST'])
@admin_required
def create_user():
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', 'temp123')
    role = request.form.get('role', 'user')
    
    if not username or not email:
        return jsonify({'success': False, 'error': 'Username and email required'}), 400
    
    existing = User.get_user_by_email(email)
    if existing:
        return jsonify({'success': False, 'error': 'Email already exists'}), 400
    
    try:
        user_id = User.create_user(username, email, password, role)
        return jsonify({'success': True, 'user_id': user_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/update_user/<user_id>', methods=['POST'])
@admin_required
def update_user(user_id):
    updates = {
        'username': request.form.get('username', ''),
        'email': request.form.get('email', ''),
        'role': request.form.get('role', 'user')
    }
    success = User.update_user(user_id, updates)
    return jsonify({'success': success})

@app.route('/admin/delete_user/<user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    if str(session['user_id']) == user_id:
        return jsonify({'error': 'Cannot delete yourself'}), 400
    success = User.delete_user(user_id)
    return jsonify({'success': success})

@app.route('/admin/clear_data', methods=['POST'])
@admin_required
def clear_data():
    deleted = SensorData.clear_all_data()
    return jsonify({'success': True, 'cleared': deleted})

@app.route('/admin/stats')
@admin_required
def admin_stats():
    conn = get_db_connection()
    try:
        stats = {
            'users': conn.execute('SELECT COUNT(*) FROM users').fetchone()[0],
            'readings': conn.execute('SELECT COUNT(*) FROM sensor_data').fetchone()[0],
            'active_sessions': random.randint(8, 15),
            'online_now': random.randint(3, 8)
        }
    finally:
        conn.close()
    return jsonify(stats)

# =============================================================================
# CONTACT ADMIN ROUTES
# =============================================================================

@app.route('/admin/message_read/<int:message_id>', methods=['POST'])
@admin_required
def message_read(message_id):
    success = ContactMessage.mark_as_read(message_id)
    return jsonify({'success': success})

@app.route('/admin/delete_message/<int:message_id>', methods=['DELETE'])
@admin_required
def delete_message(message_id):
    success = ContactMessage.delete_message(message_id)
    return jsonify({'success': success})

@app.route('/admin/messages/mark_all_read', methods=['POST'])
@admin_required
def mark_all_messages_read():
    count = ContactMessage.mark_all_read()
    return jsonify({'success': True, 'count': count})

# =============================================================================
# EXPORT FUNCTIONALITY
# =============================================================================

@app.route('/admin/export_report')
@admin_required
def export_report():
    try:
        export_format = request.args.get('format', 'csv').lower()
        sensor_data = SensorData.get_data_for_export(10000)
        timestamp = get_local_time().strftime('%Y%m%d_%H%M%S')
        
        if export_format == 'csv':
            return export_as_csv(sensor_data, timestamp)
        elif export_format == 'excel':
            return export_as_excel(sensor_data, timestamp)
        elif export_format == 'json':
            return export_as_json(sensor_data, timestamp)
        else:
            return {"error": "Invalid format"}, 400
    except Exception as e:
        print(f"Export error: {str(e)}")
        return {"error": str(e)}, 500

def export_as_csv(data, timestamp):
    try:
        if not data:
            data = [{'Message': 'No data available'}]
        
        output = io.StringIO()
        fieldnames = data[0].keys()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
        
        filename = f"sensor_export_{timestamp}.csv"
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    except Exception as e:
        return {"error": str(e)}, 500

def export_as_excel(data, timestamp):
    try:
        if not data:
            data = [{'Message': 'No data available'}]
        
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Sensor Data', index=False)
        output.seek(0)
        
        filename = f"sensor_export_{timestamp}.xlsx"
        return Response(
            output.getvalue(),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    except Exception as e:
        return {"error": "Excel export failed"}, 500

def export_as_json(data, timestamp):
    try:
        if not data:
            data = [{'Message': 'No data available'}]
        
        filename = f"sensor_export_{timestamp}.json"
        return Response(
            json.dumps(data, indent=2, default=str),
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/admin/export_options')
@admin_required
def export_options():
    return render_template('export_options.html')

# =============================================================================
# SOCKET.IO
# =============================================================================

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('status', {'message': 'Connected to Acid-to-Amp'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

# =============================================================================
# BACKGROUND TASK
# =============================================================================

def background_sensor_task():
    """Simulate sensor readings and broadcast via socket.io"""
    while True:
        try:
            voltage = round(random.uniform(0.45, 0.55), 3)
            current = round(random.uniform(1.9, 2.4), 2)
            ph = round(random.uniform(4.9, 5.5), 2)
            iron = round(random.uniform(22, 38), 1)
            copper = round(random.uniform(8, 16), 1)
            biofilm = random.choice(['Active', 'Growing', 'Stable', 'Peak'])
            
            SensorData.add_reading(voltage, current, ph, iron, copper, biofilm)
            
            socketio.emit('sensor_update', {
                'voltage': voltage,
                'current': current,
                'ph': ph,
                'iron': iron,
                'copper': copper,
                'biofilm': biofilm,
                'power': round(voltage * current * 1000, 2),
                'timestamp': format_local_time(get_local_time())
            })
            socketio.sleep(10)
        except Exception as e:
            print(f"Background task error: {e}")
            socketio.sleep(10)

# =============================================================================
# DEBUG ENDPOINTS
# =============================================================================

@app.route('/debug/endpoints')
def debug_endpoints():
    endpoints = []
    for rule in app.url_map.iter_rules():
        endpoints.append({
            'endpoint': rule.endpoint,
            'url': str(rule)
        })
    return jsonify(endpoints)

# =============================================================================
# MAIN (Local development only)
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 ACID-TO-AMP BIOELECTRIC SYSTEM (Production Ready)")
    print("=" * 60)
    print(f"📍 Timezone: {TIMEZONE}")
    print(f"🕐 Local time: {format_local_time(get_local_time())}")
    print(f"📊 Database: {app.config['DATABASE']}")
    print(f"🌐 Development server: http://localhost:5000")
    print(f"👤 Admin login: admin@acidtoamp.com / admin2026")
    print("=" * 60)
    
    socketio.start_background_task(target=background_sensor_task)
    socketio.run(app, debug=True, host='0.0.0.0', port=8080, allow_unsafe_werkzeug=True)

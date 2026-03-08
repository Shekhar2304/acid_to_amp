from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from flask_socketio import SocketIO, emit
from flask_bcrypt import Bcrypt
import sqlite3
from functools import wraps
from datetime import datetime, timedelta
import random
 
from dotenv import load_dotenv
import pytz
import csv
import io
import json
import pandas as pd
import logging
import os
os.environ['PANDAS_BUILD_STRATEGY'] = 'minimal'


# CRITICAL: Load env FIRST
load_dotenv()

# Configure logging for Railway
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'your-super-secret-key-change-in-production'
app.config['DEBUG'] = False  # Production ready

# RAILWAY: Dynamic PORT binding
PORT = int(os.environ.get('PORT', 8080))
HOST = os.environ.get('HOST', '0.0.0.0')

# SQLite configuration (Railway-safe path)
DATABASE = os.environ.get('DATABASE_PATH', '/app/acid_amp.db')  # Persistent volume
app.config['DATABASE'] = DATABASE

TIMEZONE = 'Asia/Kolkata'
bcrypt = Bcrypt(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', logger=True, engineio_logger=True)

# =============================================================================
# FIXED: GUNICORN-SAFE DATABASE CONNECTIONS
# =============================================================================

def get_app_context_db():
    """Gunicorn-safe DB connection using app context"""
    if not hasattr(g, 'db_conn'):
        g.db_conn = sqlite3.connect(app.config['DATABASE'], check_same_thread=False)
        g.db_conn.row_factory = sqlite3.Row
        g.db_conn.execute('PRAGMA foreign_keys = ON')
        g.db_conn.execute('PRAGMA journal_mode=WAL')  # Better concurrency
    return g.db_conn

# Global for thread-local storage
from flask import g

def get_db_connection():
    """Thread-safe DB connection"""
    if not hasattr(g, 'db_conn'):
        conn = sqlite3.connect(app.config['DATABASE'], check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute('PRAGMA journal_mode=WAL')
        g.db_conn = conn
    return g.db_conn

@app.teardown_appcontext
def close_db_connection(exception):
    """Clean up DB connections"""
    if hasattr(g, 'db_conn'):
        g.db_conn.close()
        delattr(g, 'db_conn')

def init_db():
    """Initialize database - idempotent"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
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
    
    # Performance indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sensor_timestamp ON sensor_data(timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_contacts_status ON contacts(status)')
    
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized")

# Initialize ON STARTUP
with app.app_context():
    init_db()

# =============================================================================
# TIMEZONE HELPERS (UNCHANGED)
# =============================================================================
def get_local_time():
    utc_now = datetime.utcnow()
    local_tz = pytz.timezone(TIMEZONE)
    return utc_now.replace(tzinfo=pytz.UTC).astimezone(local_tz)

def format_local_time(dt):
    if dt is None or isinstance(dt, str):
        return dt or 'N/A'
    local_tz = pytz.timezone(TIMEZONE)
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(local_tz).strftime('%Y-%m-%d %H:%M:%S')

# =============================================================================
# FIXED MODELS (Gunicorn-safe)
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
    def check_password(user, password):
        return bcrypt.check_password_hash(user['password_hash'], password)

# FIXED SensorData with proper connection cleanup
class SensorData:
    @staticmethod
    def get_data_for_export(limit=10000):
        """FIXED: Export function - no more SQLAlchemy errors"""
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

# =============================================================================
# DECORATORS (UNCHANGED)
# =============================================================================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = User.get_user_by_email(session.get('email', ''))
        if not user or user.get('role') != 'admin':
            flash('Admin access required', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# =============================================================================
# ROUTES (RAILWAY READY)
# =============================================================================
@app.route('/')
def index():
    return render_template('index.html')

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
            return redirect(url_for('admin_panel'))
        flash('Invalid credentials', 'danger')
    return render_template('login.html')

@app.route('/admin')
@login_required
def admin_panel():
    return render_template('admin.html')

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "db": os.path.exists(app.config['DATABASE'])})

# =============================================================================
# FIXED EXPORT ROUTES - NO MORE ERRORS
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
            return jsonify({"error": "Invalid format"}), 400
    except Exception as e:
        logger.error(f"Export error: {str(e)}")
        return jsonify({"error": str(e)}), 500

def export_as_csv(data, timestamp):
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
        logger.error(f"Excel export error: {e}")
        return jsonify({"error": "Excel export failed"}), 500

def export_as_json(data, timestamp):
    if not data:
        data = [{'Message': 'No data available'}]
    
    filename = f"sensor_export_{timestamp}.json"
    return Response(
        json.dumps(data, indent=2, default=str),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

# Static files for Railway
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

# =============================================================================
# MAIN - Railway Production Ready
# =============================================================================
if __name__ == '__main__':
    # Auto-create admin
    admin = User.get_user_by_email('admin@acidtoamp.com')
    if not admin:
        User.create_user('admin', 'admin@acidtoamp.com', 'admin2026', 'admin')
        logger.info("✅ Admin created: admin@acidtoamp.com / admin2026")
    
    logger.info(f"🚀 Starting on {HOST}:{PORT}")
    socketio.run(app, host=HOST, port=PORT, debug=False)

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from flask_socketio import SocketIO, emit
from flask_bcrypt import Bcrypt
from models import db, User, SensorData, ContactMessage
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

# Import dashboard blueprint (if exists)
try:
    from dashboard import dashboard_bp
    HAS_DASHBOARD = True
except ImportError:
    HAS_DASHBOARD = False

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'your-super-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or 'sqlite:///acid_amp.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
bcrypt = Bcrypt(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
db.init_app(app)

# Register dashboard blueprint if available
if HAS_DASHBOARD:
    app.register_blueprint(dashboard_bp)

TIMEZONE = 'Asia/Kolkata'

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
        name = request.form.get('name')
        email = request.form.get('email')
        subject = request.form.get('subject')
        message = request.form.get('message')
        
        if not name or not email or not message:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('contact'))
        
        ContactMessage.add_message(name, email, subject, message)
        flash('Your message has been sent. Thank you!', 'success')
        return redirect(url_for('contact'))
    
    return render_template('contact.html')

@app.route('/debug/time-diagnostic')
def time_diagnostic():
    """Comprehensive time diagnostic"""
    import time
    
    system_time = datetime.now()
    utc_time = datetime.utcnow()
    india_tz = pytz.timezone('Asia/Kolkata')
    india_time = datetime.now(india_tz)
    is_dst = time.localtime().tm_isdst
    tz_env = os.environ.get('TZ', 'Not set')
    
    return jsonify({
        'system_time': system_time.strftime('%Y-%m-%d %H:%M:%S'),
        'utc_time': utc_time.strftime('%Y-%m-%d %H:%M:%S'),
        'india_time': india_time.strftime('%Y-%m-%d %H:%M:%S'),
        'server_timezone': time.tzname,
        'is_dst': is_dst,
        'tz_environment': tz_env,
        'timezone_setting': TIMEZONE
    })

# =============================================================================
# ROUTES - AUTH
# =============================================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.get_user_by_email(email)
        
        if user and User.check_password(user, password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash(f'Welcome back, {user["username"]}!', 'success')
            if HAS_DASHBOARD:
                return redirect(url_for('dashboard.dashboard'))
            return redirect(url_for('index'))
        flash('Invalid credentials', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
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
    if data:
        return jsonify(data[0])
    return jsonify({})

# =============================================================================
# ROUTES - ADMIN PANEL
# =============================================================================
@app.route('/admin')
@admin_required
def admin_panel():
    users = User.get_all_users()
    messages = ContactMessage.get_all_messages()
    
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
@admin_required
def admin_users():
    users = User.get_all_users()
    return jsonify(users)

@app.route('/admin/create_user', methods=['POST'])
@admin_required
def create_user():
    username = request.form['username']
    email = request.form['email']
    password = request.form.get('password', 'temp123')
    role = request.form.get('role', 'user')
    
    existing = User.get_user_by_email(email)
    if existing:
        return jsonify({'success': False, 'error': 'Email already exists'}), 400
    
    try:
        user_id = User.create_user(username, email, password, role)
        return jsonify({'success': True, 'user_id': user_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/admin/update_user/<user_id>', methods=['POST'])
@admin_required
def update_user(user_id):
    updates = {
        'username': request.form['username'],
        'email': request.form['email'],
        'role': request.form['role']
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
    stats = {
        'users': User.query.count(),
        'readings': SensorData.query.count(),
        'active_sessions': random.randint(8, 15),
        'online_now': random.randint(3, 8)
    }
    return jsonify(stats)

# Admin message endpoints
@app.route('/admin/message_read/<message_id>', methods=['POST'])
@admin_required
def message_read(message_id):
    success = ContactMessage.mark_as_read(message_id)
    return jsonify({'success': success})

@app.route('/admin/delete_message/<message_id>', methods=['POST'])
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
    """Export sensor data in multiple formats"""
    try:
        export_format = request.args.get('format', 'csv').lower()
        sensor_data = SensorData.get_data_for_export(10000)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
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
    """Export data as CSV file"""
    try:
        if not data:
            data = [{'Message': 'No data available'}]
        
        output = io.StringIO()
        if data:
            fieldnames = data[0].keys()
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        
        filename = f"sensor_export_{timestamp}.csv"
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename={filename}',
                'Content-Type': 'text/csv; charset=utf-8'
            }
        )
    except Exception as e:
        print(f"CSV export error: {str(e)}")
        return {"error": str(e)}, 500

def export_as_excel(data, timestamp):
    """Export data as Excel file"""
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
            headers={
                'Content-Disposition': f'attachment; filename={filename}',
                'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            }
        )
    except ImportError:
        return {"error": "Excel export requires pandas and openpyxl"}, 500
    except Exception as e:
        print(f"Excel export error: {str(e)}")
        return {"error": str(e)}, 500

def export_as_json(data, timestamp):
    """Export data as JSON file"""
    try:
        if not data:
            data = [{'Message': 'No data available'}]
        
        filename = f"sensor_export_{timestamp}.json"
        return Response(
            json.dumps(data, indent=2, default=str),
            mimetype='application/json',
            headers={
                'Content-Disposition': f'attachment; filename={filename}',
                'Content-Type': 'application/json; charset=utf-8'
            }
        )
    except Exception as e:
        print(f"JSON export error: {str(e)}")
        return {"error": str(e)}, 500

@app.route('/admin/export_options')
@admin_required
def export_options():
    """Show export options page"""
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
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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
# RAILWAY PRODUCTION READY MAIN
# =============================================================================
if __name__ == '__main__':
    # Create tables and setup admin user
    with app.app_context():
        db.create_all()
        
        # Auto-create admin if not exists
        admin = User.get_user_by_email('admin@acidtoamp.com')
        if not admin:
            User.create_user('admin', 'admin@acidtoamp.com', 'admin2026', 'admin')
            print(f"✅ Admin created: admin@acidtoamp.com / admin2026")
    
    print("=" * 60)
    print("🔋 ACID-TO-AMP BIOELECTRIC SYSTEM - RAILWAY READY")
    print("=" * 60)
    print(f"🌐 Timezone: {TIMEZONE}")
    print(f"🕐 Local time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"💾 Database: {app.config['SQLALCHEMY_DATABASE_URI']}")
    print(f"🌐 PORT: {os.environ.get('PORT', 5000)}")
    print(f"👤 Admin login: admin@acidtoamp.com / admin2026")
    print("=" * 60)
    
    # 🚀 RAILWAY COMPATIBLE: Uses $PORT (defaults to 8080 on Railway)
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    socketio.start_background_task(target=background_sensor_task)
    socketio.run(
        app, 
        debug=debug, 
        host='0.0.0.0', 
        port=port,
        allow_unsafe_werkzeug=False
    )

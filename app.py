from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from flask_socketio import SocketIO, emit
from flask_bcrypt import Bcrypt
import pymongo
from bson import ObjectId
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
from models import User, SensorData, ContactMessage

# Import dashboard blueprint
from dashboard import dashboard_bp

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'your-super-secret-key-change-in-production'
app.config['MONGO_URI'] = os.environ.get('MONGO_URI') or 'mongodb://localhost:27017/acid_amp'

# Set your timezone
TIMEZONE = 'Asia/Kolkata'  # For India

bcrypt = Bcrypt(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

client = pymongo.MongoClient(app.config['MONGO_URI'])
db = client.get_database()
app.db = db

# Register dashboard blueprint
app.register_blueprint(dashboard_bp)

@app.route('/privacy')
def privacy():
    return render_template('legal/privacy.html')

@app.route('/terms')
def terms():
    return render_template('legal/terms.html')

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
# MODELS
# =============================================================================

class User:
    @staticmethod
    def create_user(username, email, password, role='user'):
        user_data = {
            'username': username,
            'email': email,
            'password_hash': bcrypt.generate_password_hash(password).decode('utf-8'),
            'role': role,
            'created_at': get_local_time(),
            'is_active': True
        }
        result = db.users.insert_one(user_data)
        return str(result.inserted_id)
    
    @staticmethod
    def get_user_by_email(email):
        user = db.users.find_one({'email': email})
        if user:
            user['_id'] = str(user['_id'])
        return user
    
    @staticmethod
    def get_all_users():
        users = list(db.users.find())
        for user in users:
            user['_id'] = str(user['_id'])
            if user.get('created_at'):
                user['created_at_formatted'] = format_local_time(user['created_at'])
        return users
    
    @staticmethod
    def update_user(user_id, updates):
        result = db.users.update_one({'_id': ObjectId(user_id)}, {'$set': updates})
        return result.modified_count > 0
    
    @staticmethod
    def delete_user(user_id):
        result = db.users.delete_one({'_id': ObjectId(user_id)})
        return result.deleted_count > 0
    
    @staticmethod
    def check_password(user, password):
        return bcrypt.check_password_hash(user['password_hash'], password)

class SensorData:
    @staticmethod
    def add_reading(voltage, current, ph, iron, copper, biofilm_status):
        data = {
            'voltage': voltage,
            'current': current,
            'ph': ph,
            'iron': iron,
            'copper': copper,
            'biofilm_status': biofilm_status,
            'power': round(voltage * current * 1000, 2),
            'timestamp': get_local_time()
        }
        db.sensor_data.insert_one(data)
        return data
    
    @staticmethod
    def get_recent_data(limit=100):
        data = list(db.sensor_data.find().sort('timestamp', -1).limit(limit))
        for item in data:
            item['_id'] = str(item['_id'])
            if item.get('timestamp'):
                item['timestamp'] = format_local_time(item['timestamp'])
        return data
    
    @staticmethod
    def get_data_for_export(limit=10000):
        """Get data formatted for export"""
        data = list(db.sensor_data.find().sort('timestamp', -1).limit(limit))
        formatted_data = []
        for item in data:
            formatted_data.append({
                'Timestamp': format_local_time(item.get('timestamp')),
                'Voltage (V)': item.get('voltage', 0),
                'Current (mA)': item.get('current', 0),
                'pH': item.get('ph', 0),
                'Iron (mg/L)': item.get('iron', 0),
                'Copper (mg/L)': item.get('copper', 0),
                'Biofilm': item.get('biofilm_status', 'Unknown'),
                'Power (mW)': item.get('power', 0)
            })
        return formatted_data
    
    @staticmethod
    def clear_all_data():
        result = db.sensor_data.delete_many({})
        return result.deleted_count

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
            return redirect(url_for('login'))  # Redirect to login, not dashboard
        return f(*args, **kwargs)
    return decorated_function

# =============================================================================
# ROUTES - PUBLIC
# =============================================================================

@app.route('/')
def index():
    return render_template('index.html')
@app.route('/debug/time-diagnostic')
def time_diagnostic():
    """Comprehensive time diagnostic"""
    import pytz
    from datetime import datetime
    import os
    import time
    
    # System time
    system_time = datetime.now()
    
    # UTC time
    utc_time = datetime.utcnow()
    
    # India time
    india_tz = pytz.timezone('Asia/Kolkata')
    india_time = datetime.now(india_tz)
    
    # Server timezone info
    is_dst = time.localtime().tm_isdst
    
    # Get environment info
    tz_env = os.environ.get('TZ', 'Not set')
    
    # Sample from database if available
    db_sample = None
    try:
        sample = list(db.sensor_data.find().sort('timestamp', -1).limit(1))
        if sample:
            ts = sample[0].get('timestamp')
            db_sample = {
                'raw_timestamp': str(ts),
                'type': str(type(ts)),
                'formatted_utc': ts.strftime('%Y-%m-%d %H:%M:%S') if ts else None,
            }
            # Try to convert to India time
            if ts:
                if ts.tzinfo is None:
                    ts_utc = pytz.UTC.localize(ts)
                else:
                    ts_utc = ts
                ts_india = ts_utc.astimezone(india_tz)
                db_sample['formatted_india'] = ts_india.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        db_sample = {'error': str(e)}
    
    return jsonify({
        'system_time': system_time.strftime('%Y-%m-%d %H:%M:%S'),
        'utc_time': utc_time.strftime('%Y-%m-%d %H:%M:%S'),
        'india_time': india_time.strftime('%Y-%m-%d %H:%M:%S'),
        'server_timezone': time.tzname,
        'is_dst': is_dst,
        'tz_environment': tz_env,
        'database_sample': db_sample,
        'timezone_setting': TIMEZONE
    })
# =============================================================================
# ROUTES - AUTH
# =============================================================================
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
            session['user_id'] = user['_id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash(f'Welcome back, {user["username"]}!', 'success')
            return redirect(url_for('dashboard.dashboard'))  # FIXED: changed from 'dashboard_bp.dashboard' to 'dashboard.dashboard'
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
#technology
@app.route('/technology')
def technology():
    return render_template('technology.html')
# In app.py, modify admin_panel route to include messages
@app.route('/admin')
@admin_required
def admin_panel():
    users = User.get_all_users()
    messages = ContactMessage.get_all_messages()
    stats = {
        'users': db.users.count_documents({}),
        'readings': db.sensor_data.count_documents({}),
        'messages': db.contacts.count_documents({}),
        'unread_messages': db.contacts.count_documents({'status': 'unread'}),
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

@app.route('/admin/update_user/<user_id>', methods=['PUT'])
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
        'users': db.users.count_documents({}),
        'readings': db.sensor_data.count_documents({}),
        'active_sessions': random.randint(8, 15),
        'online_now': random.randint(3, 8)
    }
    return jsonify(stats)
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
        import pandas as pd
        from io import BytesIO
        
        if not data:
            data = [{'Message': 'No data available'}]
        
        df = pd.DataFrame(data)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Sensor Data', index=False)
        
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
        return {"error": "Excel export requires pandas and openpyxl. Install with: pip install pandas openpyxl"}, 500
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

# =============================================================================
# SOCKET.IO
# =============================================================================
#contact 
# app.py – add these routes (somewhere before the main block)

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
        
        # Save to database
        ContactMessage.add_message(name, email, subject, message)
        
        # Optional: send email notification to admin
        # You can use Flask-Mail here if configured
        
        flash('Your message has been sent. Thank you!', 'success')
        return redirect(url_for('contact'))
    
    return render_template('contact.html')

# Admin endpoints for messages (used by admin panel)
@app.route('/admin/message_read/<message_id>', methods=['POST'])
@admin_required
def message_read(message_id):
    success = ContactMessage.mark_as_read(message_id)
    return jsonify({'success': success})

@app.route('/admin/delete_message/<message_id>', methods=['DELETE'])
@admin_required
def delete_message(message_id):
    success = ContactMessage.delete_message(message_id)
    return jsonify({'success': success})

@app.route('/admin/messages/mark_all_read', methods=['POST'])
@admin_required
def mark_all_messages_read():
    count = ContactMessage.mark_all_read()
    return jsonify({'success': True, 'count': count})
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
# EXPORT OPTIONS PAGE
# =============================================================================

@app.route('/admin/export_options')
@admin_required
def export_options():
    """Show export options page"""
    return render_template('export_options.html')

# =============================================================================
# DATABASE INDEX SETUP
# =============================================================================

def setup_database_indexes():
    """Safely set up database indexes"""
    print("\n🔧 Setting up database indexes...")
    
    try:
        # Check if email index exists
        existing_indexes = list(db.users.list_indexes())
        email_index_exists = False
        
        for index in existing_indexes:
            if index['name'] == 'email_1':
                email_index_exists = True
                if index.get('unique'):
                    print("✅ Unique email index already exists")
                else:
                    db.users.drop_index('email_1')
                    print("✅ Dropped non-unique email index")
                    db.users.create_index('email', unique=True)
                    print("✅ Created unique email index")
                break
        
        if not email_index_exists:
            db.users.create_index('email', unique=True)
            print("✅ Created unique email index")
        
        # Create timestamp index for sensor_data
        db.sensor_data.create_index('timestamp')
        print("✅ Created timestamp index for sensor_data")
        
    except Exception as e:
        print(f"⚠️ Index setup warning: {e}")

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
# MAIN
# =============================================================================

if __name__ == '__main__':
    # Setup database indexes
    setup_database_indexes()
    
    # Auto-create admin if not exists
    admin = User.get_user_by_email('admin@acidtoamp.com')
    if not admin:
        User.create_user('admin', 'admin@acidtoamp.com', 'admin2026', 'admin')
        print(f"✅ Admin created: admin@acidtoamp.com / admin2026")
    
    print("=" * 50)
    print("🚀 Acid-to-Amp Bioelectric System")
    print("=" * 50)
    print(f"📍 Timezone: {TIMEZONE}")
    print(f"🕐 Local time: {format_local_time(get_local_time())}")
    print(f"📊 Database: {app.config['MONGO_URI']}")
    print(f"🌐 Server: http://localhost:5000")
    print(f"👤 Admin login: admin@acidtoamp.com / admin2026")
    print("=" * 50)
    
    socketio.start_background_task(target=background_sensor_task)
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
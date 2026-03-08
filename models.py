from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pytz

# Create SQLAlchemy instance (app.py will call db.init_app(app))
db = SQLAlchemy()

# =============================================================================
# TIMEZONE SETTINGS (Exactly matches app.py)
# =============================================================================
TIMEZONE = 'Asia/Kolkata'

def get_local_time():
    """Get current time in local timezone (matches app.py)"""
    utc_now = datetime.utcnow()
    local_tz = pytz.timezone(TIMEZONE)
    local_time = utc_now.replace(tzinfo=pytz.UTC).astimezone(local_tz)
    return local_time

def format_local_time(dt):
    """Format datetime to local timezone string (matches app.py)"""
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
# USER MODEL (100% app.py compatible)
# =============================================================================
class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    email = db.Column(db.String(150), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='user')
    created_at = db.Column(db.DateTime, default=get_local_time)
    is_active = db.Column(db.Boolean, default=True)

    @staticmethod
    def create_user(username, email, password, role='user'):
        """Create new user - returns user ID (matches app.py signature)"""
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role=role,
            created_at=get_local_time()
        )
        db.session.add(user)
        db.session.commit()
        return str(user.id)  # app.py expects string ID

    @staticmethod
    def get_user_by_email(email):
        """Get user by email - MongoDB-style dict (matches app.py)"""
        user = User.query.filter_by(email=email).first()
        if user:
            return {
                'id': str(user.id),  # app.py expects string
                'username': user.username,
                'email': user.email,
                'password_hash': user.password_hash,
                'role': user.role,
                'created_at': user.created_at
            }
        return None

    @staticmethod
    def get_all_users():
        """Get all users with formatted timestamps (matches app.py)"""
        users = User.query.order_by(User.created_at.desc()).all()
        result = []
        for u in users:
            result.append({
                '_id': str(u.id),  # app.py expects _id as string
                'username': u.username,
                'email': u.email,
                'role': u.role,
                'created_at_formatted': format_local_time(u.created_at)
            })
        return result

    @staticmethod
    def update_user(user_id, updates):
        """Update user by ID (matches app.py signature)"""
        user = User.query.get(int(user_id))
        if not user:
            return False
        for key, value in updates.items():
            if key != 'password_hash':  # Security
                setattr(user, key, value)
        db.session.commit()
        return True

    @staticmethod
    def delete_user(user_id):
        """Delete user by ID (matches app.py)"""
        user = User.query.get(int(user_id))
        if not user:
            return False
        db.session.delete(user)
        db.session.commit()
        return True

    @staticmethod
    def check_password(user_dict, password):
        """Check password against hash (matches app.py)"""
        return check_password_hash(user_dict['password_hash'], password)

# =============================================================================
# CONTACT MESSAGE MODEL (100% app.py compatible)
# =============================================================================
class ContactMessage(db.Model):
    __tablename__ = 'contacts'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=False)
    subject = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='unread')
    created_at = db.Column(db.DateTime, default=get_local_time)

    @staticmethod
    def add_message(name, email, subject, message):
        """Add contact message (matches app.py signature exactly)"""
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

    @staticmethod
    def get_all_messages():
        """Get all messages with formatted timestamps (matches app.py)"""
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

    @staticmethod
    def mark_as_read(message_id):
        """Mark message as read (matches app.py)"""
        msg = ContactMessage.query.get(int(message_id))
        if not msg:
            return False
        msg.status = 'read'
        db.session.commit()
        return True

    @staticmethod
    def delete_message(message_id):
        """Delete message (matches app.py)"""
        msg = ContactMessage.query.get(int(message_id))
        if not msg:
            return False
        db.session.delete(msg)
        db.session.commit()
        return True

    @staticmethod
    def mark_all_read():
        """Mark all unread as read (matches app.py)"""
        count = ContactMessage.query.filter_by(status='unread').update({'status': 'read'})
        db.session.commit()
        return count

# =============================================================================
# SENSOR DATA MODEL (100% app.py compatible)
# =============================================================================
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
    timestamp = db.Column(db.DateTime, default=get_local_time, index=True)

    @staticmethod
    def add_reading(voltage, current, ph, iron, copper, biofilm_status):
        """Add sensor reading (matches app.py exactly)"""
        power = round(voltage * current * 1000, 2)  # mW
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

    @staticmethod
    def get_recent_data(limit=100):
        """Get recent data (matches app.py exactly)"""
        data = SensorData.query.order_by(SensorData.timestamp.desc()).limit(limit).all()
        result = []
        for item in data:
            result.append({
                '_id': str(item.id),
                'voltage': item.voltage,
                'current': item.current,
                'ph': item.ph,
                'iron': item.iron,
                'copper': item.copper,
                'biofilm_status': item.biofilm_status,
                'power': item.power,
                'timestamp': format_local_time(item.timestamp)
            })
        return result

    @staticmethod
    def get_data_for_export(limit=10000):
        """Export formatted data (matches app.py)"""
        data = SensorData.query.order_by(SensorData.timestamp.desc()).limit(limit).all()
        result = []
        for item in data:
            result.append({
                'Timestamp': format_local_time(item.timestamp),
                'Voltage (V)': item.voltage,
                'Current (mA)': item.current,
                'pH': item.ph,
                'Iron (mg/L)': item.iron,
                'Copper (mg/L)': item.copper,
                'Biofilm': item.biofilm_status,
                'Power (mW)': item.power
            })
        return result

    @staticmethod
    def clear_all_data():
        """Clear all data (matches app.py return format)"""
        count = SensorData.query.count()
        SensorData.query.delete()
        db.session.commit()
        return count

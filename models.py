from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pytz

db = SQLAlchemy()

# =============================================================================
# TIMEZONE SETTINGS
# =============================================================================

TIMEZONE = 'Asia/Kolkata'

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
# USER MODEL
# =============================================================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='user')
    created_at = db.Column(db.DateTime, default=get_local_time)
    is_active = db.Column(db.Boolean, default=True)

    @staticmethod
    def create_user(username, email, password, role='user'):
        """Create new user - returns user ID"""
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role=role,
            created_at=get_local_time()
        )
        db.session.add(user)
        db.session.commit()
        return user.id

    @staticmethod
    def get_user_by_email(email):
        """Get user by email with MongoDB-style response"""
        user = User.query.filter_by(email=email).first()
        if user:
            return {
                "_id": user.id,
                "username": user.username,
                "email": user.email,
                "password_hash": user.password_hash,
                "role": user.role,
                "created_at": user.created_at,
                "created_at_formatted": format_local_time(user.created_at),
                "is_active": user.is_active
            }
        return None

    @staticmethod
    def get_all_users():
        """Get all users with formatted timestamps"""
        users = User.query.order_by(User.created_at.desc()).all()
        result = []
        for u in users:
            result.append({
                "_id": u.id,
                "username": u.username,
                "email": u.email,
                "role": u.role,
                "created_at": u.created_at,
                "created_at_formatted": format_local_time(u.created_at),
                "is_active": u.is_active
            })
        return result

    @staticmethod
    def update_user(user_id, updates):
        """Update user by ID"""
        user = User.query.get(user_id)
        if not user:
            return False
        for key, value in updates.items():
            if key != 'password_hash':  # Don't allow direct password hash update
                setattr(user, key, value)
        db.session.commit()
        return True

    @staticmethod
    def delete_user(user_id):
        """Delete user by ID"""
        user = User.query.get(user_id)
        if not user:
            return False
        db.session.delete(user)
        db.session.commit()
        return True

    @staticmethod
    def check_password(user_dict, password):
        """Check password against hash in user dict"""
        return check_password_hash(user_dict['password_hash'], password)

# =============================================================================
# CONTACT MESSAGE MODEL
# =============================================================================

class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=False)
    subject = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="unread")
    timestamp = db.Column(db.DateTime, default=get_local_time)

    @staticmethod
    def add_message(name, email, subject, message):
        """Add new contact message"""
        msg = ContactMessage(
            name=name,
            email=email,
            subject=subject,
            message=message,
            timestamp=get_local_time()
        )
        db.session.add(msg)
        db.session.commit()
        return msg.id

    @staticmethod
    def get_all_messages():
        """Get all messages with formatted timestamps"""
        msgs = ContactMessage.query.order_by(ContactMessage.timestamp.desc()).all()
        result = []
        for m in msgs:
            result.append({
                "_id": m.id,
                "name": m.name,
                "email": m.email,
                "subject": m.subject,
                "message": m.message,
                "status": m.status,
                "timestamp": m.timestamp,
                "timestamp_formatted": format_local_time(m.timestamp)
            })
        return result

    @staticmethod
    def mark_as_read(message_id):
        """Mark message as read"""
        msg = ContactMessage.query.get(message_id)
        if not msg:
            return False
        msg.status = "read"
        db.session.commit()
        return True

    @staticmethod
    def delete_message(message_id):
        """Delete message"""
        msg = ContactMessage.query.get(message_id)
        if not msg:
            return False
        db.session.delete(msg)
        db.session.commit()
        return True

    @staticmethod
    def mark_all_read():
        """Mark all unread messages as read"""
        unread_count = ContactMessage.query.filter_by(status="unread").update({"status": "read"})
        db.session.commit()
        return unread_count

# =============================================================================
# SENSOR DATA MODEL
# =============================================================================

class SensorData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    voltage = db.Column(db.Float, nullable=False)
    current = db.Column(db.Float, nullable=False)
    ph = db.Column(db.Float, nullable=False)  # Changed from ph_before for app.py compatibility
    iron = db.Column(db.Float, nullable=False)  # Changed from iron_before
    copper = db.Column(db.Float, nullable=False)  # Changed from copper_before
    biofilm_status = db.Column(db.String(50), nullable=False)
    power = db.Column(db.Float)  # Added power field
    timestamp = db.Column(db.DateTime, default=get_local_time, index=True)

    @staticmethod
    def add_reading(voltage, current, ph, iron, copper, biofilm_status):
        """Add new sensor reading with calculated power"""
        power = round(voltage * current * 1000, 2)  # mW calculation
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
        return data

    @staticmethod
    def get_recent_data(limit=100):
        """Get recent sensor data with formatted timestamps"""
        data = SensorData.query.order_by(SensorData.timestamp.desc()).limit(limit).all()
        result = []
        for item in data:
            result.append({
                "_id": item.id,
                "voltage": item.voltage,
                "current": item.current,
                "ph": item.ph,  # Matches app.py expectation
                "iron": item.iron,
                "copper": item.copper,
                "biofilm_status": item.biofilm_status,
                "power": item.power,
                "timestamp": format_local_time(item.timestamp)
            })
        return result

    @staticmethod
    def get_data_for_export(limit=10000):
        """Get data formatted for CSV/Excel/JSON export"""
        data = SensorData.query.order_by(SensorData.timestamp.desc()).limit(limit).all()
        formatted_data = []
        for item in data:
            formatted_data.append({
                "Timestamp": format_local_time(item.timestamp),
                "Voltage (V)": item.voltage,
                "Current (mA)": item.current,
                "pH": item.ph,
                "Iron (mg/L)": item.iron,
                "Copper (mg/L)": item.copper,
                "Biofilm": item.biofilm_status,
                "Power (mW)": item.power
            })
        return formatted_data

    @staticmethod
    def clear_all_data():
        """Clear all sensor data"""
        count = SensorData.query.count()
        SensorData.query.delete()
        db.session.commit()
        return count

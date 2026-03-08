
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
    utc_now = datetime.utcnow()
    local_tz = pytz.timezone(TIMEZONE)
    local_time = utc_now.replace(tzinfo=pytz.UTC).astimezone(local_tz)
    return local_time


def format_local_time(dt):
    if dt is None:
        return 'N/A'

    if isinstance(dt, str):
        return dt

    local_tz = pytz.timezone(TIMEZONE)

    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)

    local_dt = dt.astimezone(local_tz)

    return local_dt.strftime('%Y-%m-%d %H:%M:%S')


def get_india_time():
    india_tz = pytz.timezone('Asia/Kolkata')

    utc_now = datetime.utcnow()
    utc_now = pytz.UTC.localize(utc_now)

    india_time = utc_now.astimezone(india_tz)

    return india_time


def format_india_time(dt):

    if dt is None:
        return 'N/A'

    if isinstance(dt, str):
        return dt

    india_tz = pytz.timezone('Asia/Kolkata')

    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)

    india_dt = dt.astimezone(india_tz)

    return india_dt.strftime('%Y-%m-%d %H:%M:%S')


# =============================================================================
# USER MODEL
# =============================================================================

class User(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(100), nullable=False)

    email = db.Column(db.String(150), unique=True, nullable=False)

    password_hash = db.Column(db.String(200), nullable=False)

    role = db.Column(db.String(20), default='user')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    is_active = db.Column(db.Boolean, default=True)

    # ----------------------

    @staticmethod
    def create_user(username, email, password, role='user'):

        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role=role
        )

        db.session.add(user)

        db.session.commit()

        return user.id

    # ----------------------

    @staticmethod
    def get_user_by_email(email):

        user = User.query.filter_by(email=email).first()

        if user:

            user_dict = {
                "_id": user.id,
                "username": user.username,
                "email": user.email,
                "password_hash": user.password_hash,
                "role": user.role,
                "created_at": user.created_at,
                "created_at_formatted": format_india_time(user.created_at)
            }

            return user_dict

        return None

    # ----------------------

    @staticmethod
    def get_all_users():

        users = User.query.all()

        result = []

        for u in users:

            result.append({
                "_id": u.id,
                "username": u.username,
                "email": u.email,
                "role": u.role,
                "created_at": u.created_at,
                "created_at_formatted": format_india_time(u.created_at)
            })

        return result

    # ----------------------

    @staticmethod
    def update_user(user_id, updates):

        user = User.query.get(user_id)

        if not user:
            return False

        for key, value in updates.items():
            setattr(user, key, value)

        db.session.commit()

        return True

    # ----------------------

    @staticmethod
    def delete_user(user_id):

        user = User.query.get(user_id)

        if not user:
            return False

        db.session.delete(user)

        db.session.commit()

        return True

    # ----------------------

    @staticmethod
    def check_password(user, password):

        return check_password_hash(user['password_hash'], password)


# =============================================================================
# CONTACT MESSAGE MODEL
# =============================================================================

class ContactMessage(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(150))

    email = db.Column(db.String(150))

    subject = db.Column(db.String(200))

    message = db.Column(db.Text)

    status = db.Column(db.String(20), default="unread")

    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    # ----------------------

    @staticmethod
    def add_message(name, email, subject, message):

        msg = ContactMessage(
            name=name,
            email=email,
            subject=subject,
            message=message
        )

        db.session.add(msg)

        db.session.commit()

        return msg.id

    # ----------------------

    @staticmethod
    def get_all_messages():

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
                "timestamp": format_local_time(m.timestamp)
            })

        return result

    # ----------------------

    @staticmethod
    def mark_as_read(message_id):

        msg = ContactMessage.query.get(message_id)

        if not msg:
            return False

        msg.status = "read"

        db.session.commit()

        return True

    # ----------------------

    @staticmethod
    def delete_message(message_id):

        msg = ContactMessage.query.get(message_id)

        if not msg:
            return False

        db.session.delete(msg)

        db.session.commit()

        return True

    # ----------------------

    @staticmethod
    def mark_all_read():

        msgs = ContactMessage.query.filter_by(status="unread").all()

        for m in msgs:
            m.status = "read"

        db.session.commit()

        return len(msgs)


# =============================================================================
# SENSOR DATA MODEL
# =============================================================================

class SensorData(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    voltage = db.Column(db.Float)

    current = db.Column(db.Float)

    ph_before = db.Column(db.Float)

    iron_before = db.Column(db.Float)

    copper_before = db.Column(db.Float)

    biofilm_status = db.Column(db.String(50))

    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    # ----------------------

    @staticmethod
    def add_reading(voltage, current, ph, iron, copper, biofilm_status):

        data = SensorData(
            voltage=voltage,
            current=current,
            ph_before=ph,
            iron_before=iron,
            copper_before=copper,
            biofilm_status=biofilm_status
        )

        db.session.add(data)

        db.session.commit()

        return data

    # ----------------------

    @staticmethod
    def get_recent_data(limit=50):

        data = SensorData.query.order_by(SensorData.timestamp.desc()).limit(limit).all()

        result = []

        for item in data:

            result.append({
                "_id": item.id,
                "voltage": item.voltage,
                "current": item.current,
                "ph_before": item.ph_before,
                "iron_before": item.iron_before,
                "copper_before": item.copper_before,
                "biofilm_status": item.biofilm_status,
                "timestamp": format_india_time(item.timestamp)
            })

        return result

    # ----------------------

    @staticmethod
    def get_data_for_export(limit=10000):

        data = SensorData.query.order_by(SensorData.timestamp.desc()).limit(limit).all()

        formatted_data = []

        for item in data:

            formatted_data.append({
                "Timestamp": format_india_time(item.timestamp),
                "Voltage (V)": item.voltage,
                "Current (mA)": item.current,
                "pH": item.ph_before,
                "Iron (mg/L)": item.iron_before,
                "Copper (mg/L)": item.copper_before,
                "Biofilm": item.biofilm_status
            })

        return formatted_data

    # ----------------------

    @staticmethod
    def clear_all_data():

        deleted = SensorData.query.delete()

        db.session.commit()

        return deleted

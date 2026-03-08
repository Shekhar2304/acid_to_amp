from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pytz

db = SQLAlchemy()

TIMEZONE = "Asia/Kolkata"

# =========================================================
# TIME FUNCTIONS
# =========================================================

def get_local_time():
    utc_now = datetime.utcnow().replace(tzinfo=pytz.UTC)
    return utc_now.astimezone(pytz.timezone(TIMEZONE))


def format_local_time(dt):

    if not dt:
        return "N/A"

    if isinstance(dt, str):
        return dt

    return dt.astimezone(
        pytz.timezone(TIMEZONE)
    ).strftime("%Y-%m-%d %H:%M:%S")


# =========================================================
# USER MODEL
# =========================================================

class User(db.Model):

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(100), unique=True, nullable=False)

    email = db.Column(db.String(150), unique=True, nullable=False)

    password_hash = db.Column(db.String(200), nullable=False)

    role = db.Column(db.String(20), default="user")

    created_at = db.Column(db.DateTime, default=get_local_time)

    is_active = db.Column(db.Boolean, default=True)

    # CREATE
    @staticmethod
    def create_user(username,email,password,role="user"):

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

    # READ
    @staticmethod
    def get_user_by_email(email):

        user = User.query.filter_by(email=email).first()

        if user:

            return {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "password_hash": user.password_hash,
                "role": user.role
            }

        return None


    @staticmethod
    def get_all_users():

        users = User.query.order_by(User.created_at.desc()).all()

        result = []

        for u in users:

            result.append({
                "_id": str(u.id),
                "username": u.username,
                "email": u.email,
                "role": u.role,
                "created_at_formatted": format_local_time(u.created_at)
            })

        return result


    # UPDATE
    @staticmethod
    def update_user(user_id, updates):

        user = User.query.get(int(user_id))

        if not user:
            return False

        for key,value in updates.items():

            if key == "password":
                user.password_hash = generate_password_hash(value)

            elif key != "password_hash":
                setattr(user,key,value)

        db.session.commit()

        return True


    # DELETE
    @staticmethod
    def delete_user(user_id):

        user = User.query.get(int(user_id))

        if not user:
            return False

        db.session.delete(user)

        db.session.commit()

        return True


    @staticmethod
    def check_password(user_dict,password):

        return check_password_hash(
            user_dict["password_hash"],
            password
        )


# =========================================================
# CONTACT MESSAGE MODEL
# =========================================================

class ContactMessage(db.Model):

    __tablename__ = "contacts"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(150), nullable=False)

    email = db.Column(db.String(150), nullable=False)

    subject = db.Column(db.String(200))

    message = db.Column(db.Text, nullable=False)

    status = db.Column(db.String(20), default="unread")

    created_at = db.Column(db.DateTime, default=get_local_time)

    # CREATE
    @staticmethod
    def add_message(name,email,subject,message):

        msg = ContactMessage(
            name=name,
            email=email,
            subject=subject,
            message=message,
            created_at=get_local_time()
        )

        db.session.add(msg)
        db.session.commit()

        return str(msg.id)

    # READ
    @staticmethod
    def get_all_messages():

        msgs = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()

        result = []

        for m in msgs:

            result.append({
                "_id": str(m.id),
                "name": m.name,
                "email": m.email,
                "subject": m.subject,
                "message": m.message,
                "status": m.status,
                "timestamp_formatted": format_local_time(m.created_at)
            })

        return result


# =========================================================
# SENSOR DATA MODEL
# =========================================================

class SensorData(db.Model):

    __tablename__ = "sensor_data"

    id = db.Column(db.Integer, primary_key=True)

    voltage = db.Column(db.Float)

    current = db.Column(db.Float)

    ph = db.Column(db.Float)

    iron = db.Column(db.Float)

    copper = db.Column(db.Float)

    biofilm_status = db.Column(db.String(50))

    power = db.Column(db.Float)

    timestamp = db.Column(db.DateTime, default=get_local_time)

    # CREATE
    @staticmethod
    def add_reading(voltage,current,ph,iron,copper,biofilm_status):

        data = SensorData(
            voltage=voltage,
            current=current,
            ph=ph,
            iron=iron,
            copper=copper,
            biofilm_status=biofilm_status,
            power=round(voltage * current * 1000,2),
            timestamp=get_local_time()
        )

        db.session.add(data)
        db.session.commit()

    # READ
    @staticmethod
    def get_recent_data(limit=100):

        data = SensorData.query.order_by(
            SensorData.timestamp.desc()
        ).limit(limit).all()

        result=[]

        for d in data:

            result.append({
                "_id":str(d.id),
                "voltage":d.voltage,
                "current":d.current,
                "ph":d.ph,
                "iron":d.iron,
                "copper":d.copper,
                "biofilm_status":d.biofilm_status,
                "power":d.power,
                "timestamp":format_local_time(d.timestamp)
            })

        return result


    @staticmethod
    def get_data_for_export(limit=10000):

        data = SensorData.query.order_by(
            SensorData.timestamp.desc()
        ).limit(limit).all()

        result=[]

        for d in data:

            result.append({
                "Timestamp":format_local_time(d.timestamp),
                "Voltage (V)":d.voltage,
                "Current (mA)":d.current,
                "pH":d.ph,
                "Iron (mg/L)":d.iron,
                "Copper (mg/L)":d.copper,
                "Biofilm":d.biofilm_status,
                "Power (mW)":d.power
            })

        return result


    # DELETE
    @staticmethod
    def clear_all_data():

        count = SensorData.query.count()

        SensorData.query.delete()

        db.session.commit()

        return count

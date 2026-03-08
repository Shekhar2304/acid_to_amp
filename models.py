from flask import current_app
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from bson import ObjectId
import pytz
import time

# Set your timezone to Jharkhand/Ranchi (Asia/Kolkata)
TIMEZONE = 'Asia/Kolkata'
# Timezone settings
TIMEZONE = 'Asia/Kolkata'  # or your local timezone

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
def get_india_time():
    """Get current time in India timezone (Asia/Kolkata)"""
    india_tz = pytz.timezone('Asia/Kolkata')
    # Get current time in UTC and convert to India
    utc_now = datetime.utcnow()
    utc_now = pytz.UTC.localize(utc_now)
    india_time = utc_now.astimezone(india_tz)
    return india_time

def format_india_time(dt):
    """Convert any datetime to India timezone string"""
    if dt is None:
        return 'N/A'
    if isinstance(dt, str):
        return dt
    
    india_tz = pytz.timezone('Asia/Kolkata')
    
    # If datetime is naive (no timezone), assume it's UTC
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    
    # Convert to India timezone
    india_dt = dt.astimezone(india_tz)
    return india_dt.strftime('%Y-%m-%d %H:%M:%S')

def get_current_india_time_str():
    """Get current India time as formatted string"""
    return format_india_time(get_india_time())

class User:
    @staticmethod
    def create_user(username, email, password):
        user_data = {
            'username': username,
            'email': email,
            'password_hash': generate_password_hash(password),
            'role': 'user',
            'created_at': datetime.utcnow(),  # Store in UTC
            'is_active': True
        }
        result = current_app.db.users.insert_one(user_data)
        return str(result.inserted_id)
    
    @staticmethod
    def get_user_by_email(email):
        user = current_app.db.users.find_one({'email': email})
        if user:
            user['_id'] = str(user['_id'])
            # Format created_at for display in India time
            if user.get('created_at'):
                user['created_at_formatted'] = format_india_time(user['created_at'])
        return user
    
    @staticmethod
    def check_password(user, password):
        return check_password_hash(user['password_hash'], password)
# models.py (add this class)

class ContactMessage:
    @staticmethod
    def add_message(name, email, subject, message):
        data = {
            'name': name,
            'email': email,
            'subject': subject,
            'message': message,
            'timestamp': get_local_time(),
            'status': 'unread'
        }
        result = current_app.db.contacts.insert_one(data)
        return str(result.inserted_id)

    @staticmethod
    def get_all_messages():
        msgs = list(current_app.db.contacts.find().sort('timestamp', -1))
        for msg in msgs:
            msg['_id'] = str(msg['_id'])
            if msg.get('timestamp'):
                msg['timestamp_formatted'] = format_local_time(msg['timestamp'])
        return msgs

    @staticmethod
    def mark_as_read(message_id):
        result = current_app.db.contacts.update_one(
            {'_id': ObjectId(message_id)},
            {'$set': {'status': 'read'}}
        )
        return result.modified_count > 0

    @staticmethod
    def delete_message(message_id):
        result = current_app.db.contacts.delete_one({'_id': ObjectId(message_id)})
        return result.deleted_count > 0

    @staticmethod
    def mark_all_read():
        result = current_app.db.contacts.update_many(
            {'status': 'unread'},
            {'$set': {'status': 'read'}}
        )
        return result.modified_count
class SensorData:
    @staticmethod
    def add_reading(voltage, current, ph, iron, copper, biofilm_status):
        data = {
            'voltage': voltage,
            'current': current,
            'ph_before': ph,
            'iron_before': iron,
            'copper_before': copper,
            'biofilm_status': biofilm_status,
            'timestamp': datetime.utcnow()  # Store in UTC
        }
        current_app.db.sensor_data.insert_one(data)
        return data
    
    @staticmethod
    def get_recent_data(limit=50):
        """Get recent data with timestamps converted to India time"""
        data = list(current_app.db.sensor_data.find().sort('timestamp', -1).limit(limit))
        for item in data:
            item['_id'] = str(item['_id'])
            # Convert timestamp to India time for display
            if item.get('timestamp'):
                # Store both UTC and formatted India time
                item['timestamp_utc'] = item['timestamp'].strftime('%Y-%m-%d %H:%M:%S') if item['timestamp'] else None
                item['timestamp'] = format_india_time(item['timestamp'])
        return data
    
    @staticmethod
    def get_data_for_export(limit=10000):
        """Get data formatted for export with India timestamps"""
        data = list(current_app.db.sensor_data.find().sort('timestamp', -1).limit(limit))
        formatted_data = []
        for item in data:
            formatted_data.append({
                'Timestamp': format_india_time(item.get('timestamp')),
                'Voltage (V)': item.get('voltage', 0),
                'Current (mA)': item.get('current', 0),
                'pH': item.get('ph_before', 0),
                'Iron (mg/L)': item.get('iron_before', 0),
                'Copper (mg/L)': item.get('copper_before', 0),
                'Biofilm': item.get('biofilm_status', 'Unknown')
            })
        return formatted_data
    
    @staticmethod
    def clear_all_data():
        result = current_app.db.sensor_data.delete_many({})
        return result.deleted_count
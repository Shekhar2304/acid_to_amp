# dashboard.py
from flask import Blueprint, render_template, session, redirect, url_for, jsonify, request, Response
from functools import wraps
from models import SensorData
import csv
import io
import json
from datetime import datetime
import pytz

dashboard_bp = Blueprint('dashboard', __name__)

# Timezone settings
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

# Login decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@dashboard_bp.route('/charts')
@login_required
def charts():
    return render_template('charts.html')

@dashboard_bp.route('/impact')
@login_required
def impact():
    return render_template('impact.html')

@dashboard_bp.route('/system')
@login_required
def system():
    return render_template('system.html')

# API endpoint for dashboard data
@dashboard_bp.route('/api/dashboard-data')
@login_required
def dashboard_data():
    recent_data = SensorData.get_recent_data(20)
    return jsonify(recent_data)

# API endpoint for live stats
@dashboard_bp.route('/api/live-stats')
@login_required
def live_stats():
    data = SensorData.get_recent_data(1)
    if data:
        return jsonify(data[0])
    return jsonify({})

# =============================================================================
# EXPORT FUNCTIONALITY FOR DASHBOARD
# =============================================================================

@dashboard_bp.route('/export_report')
@login_required
def export_report():
    """Export sensor data in multiple formats from dashboard"""
    try:
        export_format = request.args.get('format', 'csv').lower()
        print(f"Export requested: {export_format}")  # Debug log
        
        # Get data for export
        sensor_data = SensorData.get_data_for_export(10000)
        
        if not sensor_data:
            # Return a message if no data
            sensor_data = [{'Message': 'No data available for export'}]
        
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
        print(f"Dashboard export error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}, 500

def export_as_csv(data, timestamp):
    """Export data as CSV file"""
    try:
        output = io.StringIO()
        if data and len(data) > 0:
            fieldnames = data[0].keys()
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        
        filename = f"sensor_export_{timestamp}.csv"
        
        # Create response with proper headers
        response = Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename={filename}',
                'Content-Type': 'text/csv; charset=utf-8'
            }
        )
        return response
    except Exception as e:
        print(f"CSV export error: {str(e)}")
        return {"error": str(e)}, 500

def export_as_excel(data, timestamp):
    """Export data as Excel file"""
    try:
        import pandas as pd
        from io import BytesIO
        
        df = pd.DataFrame(data)
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Sensor Data', index=False)
        
        output.seek(0)
        filename = f"sensor_export_{timestamp}.xlsx"
        
        response = Response(
            output.getvalue(),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={
                'Content-Disposition': f'attachment; filename={filename}',
                'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            }
        )
        return response
    except ImportError:
        return {"error": "Excel export requires pandas and openpyxl"}, 500
    except Exception as e:
        print(f"Excel export error: {str(e)}")
        return {"error": str(e)}, 500

def export_as_json(data, timestamp):
    """Export data as JSON file"""
    try:
        filename = f"sensor_export_{timestamp}.json"
        
        # Convert datetime objects to strings
        def json_serial(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")
        
        response = Response(
            json.dumps(data, indent=2, default=json_serial),
            mimetype='application/json',
            headers={
                'Content-Disposition': f'attachment; filename={filename}',
                'Content-Type': 'application/json; charset=utf-8'
            }
        )
        return response
    except Exception as e:
        print(f"JSON export error: {str(e)}")
        return {"error": str(e)}, 500

def register_dashboard_routes(app):
    app.register_blueprint(dashboard_bp, url_prefix='/')
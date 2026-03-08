# Utility functions for the application
from datetime import datetime
import json

def format_timestamp(ts):
    """Format MongoDB timestamp for display"""
    if isinstance(ts, str):
        return datetime.fromisoformat(ts.replace('Z', '+00:00'))
    return ts

def generate_demo_data():
    """Generate sample sensor data for demo"""
    import random
    return {
        'voltage': round(random.uniform(0.3, 0.8), 2),
        'current': round(random.uniform(1.5, 3.0), 2),
        'ph': round(random.uniform(4.5, 6.0), 2),
        'iron': round(random.uniform(20, 40), 1),
        'copper': round(random.uniform(5, 15), 1),
        'biofilm': random.choice(['Active', 'Growing', 'Stable'])
    }

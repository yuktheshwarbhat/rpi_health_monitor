from flask import Flask, render_template, jsonify
import psutil
import subprocess
import sqlite3
import time
import os
from datetime import datetime

app = Flask(__name__)

# --- DATABASE SETUP (from Feature 1) ---
DB_NAME = 'history.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS temps 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  timestamp REAL, 
                  temperature REAL)''')
    conn.commit()
    conn.close()

init_db()

# --- GLOBAL VARIABLES FOR NETWORK SPEED CALCULATION ---
# We store the previous network counters to calculate speed
_last_net_io = None
_last_net_time = None

# --- HELPER FUNCTIONS ---

def get_cpu_temp():
    """Reads CPU temperature using Pi hardware commands, with fallback."""
    try:
        result = subprocess.run(['vcgencmd', 'measure_temp'], 
                                capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            return float(result.stdout.replace("temp=", "").replace("'C\n", ""))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    try:
        temps = psutil.sensors_temperatures()
        if 'cpu_thermal' in temps:
            return temps['cpu_thermal'][0].current
        elif 'coretemp' in temps:
            return temps['coretemp'][0].current
    except Exception:
        pass
        
    return 45.0

def get_top_processes(limit=8):
    """
    Returns the top processes sorted by CPU usage, then RAM.
    This is like a mini 'htop' for the web dashboard.
    """
    processes = []
    
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'status']):
        try:
            pinfo = proc.info
            
            # Calculate RAM in MB
            ram_mb = pinfo['memory_info'].rss / (1024 * 1024)
            
            processes.append({
                'pid': pinfo['pid'],
                'name': pinfo['name'][:20],  # Truncate long names
                'cpu_percent': pinfo['cpu_percent'] or 0.0,
                'ram_mb': round(ram_mb, 1),
                'status': pinfo['status']
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # Process may have died between listing and reading
            continue
    
    # Sort by CPU usage (descending), then by RAM (descending)
    processes.sort(key=lambda x: (x['cpu_percent'], x['ram_mb']), reverse=True)
    
    return processes[:limit]

def get_network_speed():
    """
    Calculates real-time upload/download speed by comparing
    network counters between API calls.
    """
    global _last_net_io, _last_net_time
    
    current_io = psutil.net_io_counters()
    current_time = time.time()
    
    upload_speed = 0.0
    download_speed = 0.0
    
    if _last_net_io is not None and _last_net_time is not None:
        time_delta = current_time - _last_net_time
        
        if time_delta > 0:
            # Calculate bytes transferred since last call
            upload_delta = current_io.bytes_sent - _last_net_io.bytes_sent
            download_delta = current_io.bytes_recv - _last_net_io.bytes_recv
            
            # Convert to KB/s or MB/s
            upload_speed = upload_delta / time_delta
            download_speed = download_delta / time_delta
    
    # Update stored values for next call
    _last_net_io = current_io
    _last_net_time = current_time
    
    return {
        'upload_speed': format_bytes(upload_speed),
        'download_speed': format_bytes(download_speed),
        'total_upload': format_bytes(current_io.bytes_sent),
        'total_download': format_bytes(current_io.bytes_recv)
    }

def format_bytes(bytes_per_sec):
    """Converts bytes to human-readable format (KB/s, MB/s)."""
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.0f} B/s"
    elif bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.1f} KB/s"
    else:
        return f"{bytes_per_sec / (1024 * 1024):.2f} MB/s"

def get_uptime():
    """Returns how long the system has been running."""
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime_seconds = time.time() - psutil.boot_time()
    
    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    
    return {
        'boot_time': boot_time.strftime('%Y-%m-%d %H:%M:%S'),
        'uptime_string': f"{days}d {hours}h {minutes}m",
        'uptime_seconds': int(uptime_seconds)
    }

def get_disk_usage():
    """Returns disk usage for the root filesystem."""
    disk = psutil.disk_usage('/')
    return {
        'total': format_bytes_static(disk.total),
        'used': format_bytes_static(disk.used),
        'free': format_bytes_static(disk.free),
        'percent': disk.percent
    }

def format_bytes_static(bytes_value):
    """Converts bytes to human-readable format (for static values)."""
    if bytes_value < 1024:
        return f"{bytes_value} B"
    elif bytes_value < 1024 ** 2:
        return f"{bytes_value / 1024:.1f} KB"
    elif bytes_value < 1024 ** 3:
        return f"{bytes_value / (1024 ** 2):.1f} MB"
    else:
        return f"{bytes_value / (1024 ** 3):.2f} GB"

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stats')
def stats():
    # 1. Get current temperature
    current_temp = get_cpu_temp()
    current_time = time.time()
    
    # 2. Save to Database (Feature 1)
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO temps (timestamp, temperature) VALUES (?, ?)", 
              (current_time, current_temp))
    c.execute("DELETE FROM temps WHERE id NOT IN (SELECT id FROM temps ORDER BY id DESC LIMIT 60)")
    conn.commit()
    
    # 3. Fetch history for the graph (Feature 1)
    c.execute("SELECT timestamp, temperature FROM temps ORDER BY id ASC")
    history_data = [{"time": row[0], "temp": row[1]} for row in c.fetchall()]
    conn.close()
    
    # 4. Get system stats (Feature 2 - NEW)
    cpu_usage = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    
    # 5. Build the response
    return jsonify({
        # Feature 1 data
        "cpu_temp": current_temp,
        "cpu_usage": cpu_usage,
        "history": history_data,
        
        # Feature 2 data - NEW
        "memory": {
            "total": format_bytes_static(memory.total),
            "used": format_bytes_static(memory.used),
            "available": format_bytes_static(memory.available),
            "percent": memory.percent
        },
        "top_processes": get_top_processes(limit=8),
        "network": get_network_speed(),
        "uptime": get_uptime(),
        "disk": get_disk_usage()
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
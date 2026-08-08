from flask import Flask, render_template, jsonify
import psutil
import subprocess
import sqlite3
import time
import os

app = Flask(__name__)

# --- DATABASE SETUP ---
DB_NAME = 'history.db'

def init_db():
    """Creates the database table if it doesn't exist."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS temps 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  timestamp REAL, 
                  temperature REAL)''')
    conn.commit()
    conn.close()

# Initialize DB when the app starts
init_db()

# --- HELPER FUNCTIONS ---
def get_cpu_temp():
    """Reads CPU temperature using Pi hardware commands, with a fallback for PC testing."""
    try:
        # Try Raspberry Pi specific command
        result = subprocess.run(['vcgencmd', 'measure_temp'], capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            return float(result.stdout.replace("temp=", "").replace("'C\n", ""))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    # Fallback for standard Linux/PC testing
    try:
        temps = psutil.sensors_temperatures()
        if 'cpu_thermal' in temps:
            return temps['cpu_thermal'][0].current
        elif 'coretemp' in temps:
            return temps['coretemp'][0].current
    except Exception:
        pass
        
    return 45.0 # Dummy data if no sensors are found

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stats')
def stats():
    # 1. Get current temperature
    current_temp = get_cpu_temp()
    current_time = time.time()
    
    # 2. Save to Database
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO temps (timestamp, temperature) VALUES (?, ?)", (current_time, current_temp))
    
    # 3. Clean up old data (Keep only the last 60 records to keep the graph clean and DB small)
    c.execute("DELETE FROM temps WHERE id NOT IN (SELECT id FROM temps ORDER BY id DESC LIMIT 60)")
    conn.commit()
    
    # 4. Fetch history for the graph
    c.execute("SELECT timestamp, temperature FROM temps ORDER BY id ASC")
    history_data = [{"time": row[0], "temp": row[1]} for row in c.fetchall()]
    conn.close()
    
    # 5. Get basic system stats (CPU usage)
    cpu_usage = psutil.cpu_percent(interval=0.1)

    # 6. Return everything as JSON
    return jsonify({
        "cpu_temp": current_temp,
        "cpu_usage": cpu_usage,
        "history": history_data
    })

if __name__ == '__main__':
    # Run on port 8080, accessible from your mobile phone/laptop
    app.run(host='0.0.0.0', port=8080, debug=True)
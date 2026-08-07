from flask import Flask, jsonify, render_template
import psutil
import subprocess
import time
import os
import socket

app = Flask(__name__)

# Prime CPU percent so later interval=None calls have a baseline
psutil.cpu_percent(interval=None, percpu=True)

_net_state = {
    "counters": None,
    "time": None,
}


def run_vcgencmd(*args):
    """
    Run a vcgencmd command and return stdout.
    Returns None if vcgencmd is unavailable or fails.
    """
    try:
        result = subprocess.run(
            ["vcgencmd", *args],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    return None


def get_temp():
    """
    Get CPU temperature in Celsius.
    Uses vcgencmd first, falls back to thermal_zone0.
    """
    out = run_vcgencmd("measure_temp")

    if out and "temp=" in out:
        try:
            return float(out.replace("temp=", "").replace("'C", "").strip())
        except Exception:
            pass

    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return None


def get_clock(name):
    """
    Get clock speed in MHz.
    Example names: arm, core
    """
    out = run_vcgencmd("measure_clock", name)

    if out and "=" in out:
        try:
            hz = float(out.split("=")[1])
            return hz / 1_000_000
        except Exception:
            return None

    return None


def get_mem_split(part):
    """
    Get CPU/GPU memory split.
    part can be arm or gpu.
    """
    out = run_vcgencmd("get_mem", part)

    if out and "=" in out:
        return out.split("=")[1]

    return None


def get_throttled():
    """
    Decode vcgencmd get_throttled.
    """
    out = run_vcgencmd("get_throttled")

    if not out or "=" not in out:
        return {
            "raw": "unknown",
            "ok": False,
            "issues": ["vcgencmd unavailable"],
        }

    raw = out.split("=")[1].strip()

    try:
        val = int(raw, 16)
    except Exception:
        return {
            "raw": raw,
            "ok": False,
            "issues": ["parse error"],
        }

    if val == 0:
        return {
            "raw": raw,
            "ok": True,
            "issues": [],
        }

    issues = []

    bits = [
        (0, "Undervoltage"),
        (1, "ARM frequency capped"),
        (2, "Currently throttled"),
        (3, "Soft temperature limit"),
        (16, "Undervoltage occurred"),
        (17, "ARM frequency capped occurred"),
        (18, "Throttling occurred"),
        (19, "Soft temperature limit occurred"),
    ]

    for bit, name in bits:
        if val & (1 << bit):
            issues.append(name)

    return {
        "raw": raw,
        "ok": False,
        "issues": issues,
    }


def get_network():
    """
    Get network usage and approximate RX/TX rates.
    """
    counters = psutil.net_io_counters()
    now = time.time()

    rx_rate = 0.0
    tx_rate = 0.0

    if _net_state["counters"] and _net_state["time"]:
        dt = now - _net_state["time"]

        if dt > 0:
            rx_rate = max(
                0.0,
                (counters.bytes_recv - _net_state["counters"].bytes_recv) / dt,
            )
            tx_rate = max(
                0.0,
                (counters.bytes_sent - _net_state["counters"].bytes_sent) / dt,
            )

    _net_state["counters"] = counters
    _net_state["time"] = now

    return {
        "rx_rate": rx_rate,
        "tx_rate": tx_rate,
        "rx_total": counters.bytes_recv,
        "tx_total": counters.bytes_sent,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/stats")
def api_stats():
    temp = get_temp()

    per_cpu = psutil.cpu_percent(interval=None, percpu=True)
    cpu = sum(per_cpu) / len(per_cpu) if per_cpu else 0.0

    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    load = list(os.getloadavg())
    uptime = int(time.time() - psutil.boot_time())

    return jsonify(
        {
            "hostname": socket.gethostname(),
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "temp": temp,
            "cpu": cpu,
            "cpu_per_core": per_cpu,
            "memory": {
                "total": mem.total,
                "used": mem.used,
                "available": mem.available,
                "percent": mem.percent,
            },
            "swap": {
                "total": swap.total,
                "used": swap.used,
                "percent": swap.percent,
            },
            "disk": {
                "total": disk.total,
                "used": disk.used,
                "free": disk.free,
                "percent": disk.percent,
            },
            "load": load,
            "uptime": uptime,
            "clocks": {
                "arm": get_clock("arm"),
                "core": get_clock("core"),
            },
            "memory_split": {
                "arm": get_mem_split("arm"),
                "gpu": get_mem_split("gpu"),
            },
            "throttling": get_throttled(),
            "network": get_network(),
        }
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8080,
        debug=False,
        threaded=True,
    )
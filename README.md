# 🌡️ Raspberry Pi CPU Temperature Dashboard

A real-time web-based dashboard for monitoring Raspberry Pi CPU temperature with a beautiful speedometer-style gauge.

![Dashboard Preview](preview.png)

## ✨ Features

- 🎯 **Real-time Monitoring** - Updates every 2 seconds
- 🎨 **Beautiful UI** - Speedometer-style gauge with color zones
- 📊 **Temperature Status** - Normal (Green), Warm (Orange), Hot (Red)
- 🌐 **Network Access** - Accessible from any device on your network
- 📱 **Responsive Design** - Works on mobile and desktop
- ⚡ **Lightweight** - Built with Flask, no heavy dependencies

## 📋 Requirements

- Raspberry Pi (any model with Linux)
- Python 3.6+
- Flask

## 🚀 Installation

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/rpi-temp-dashboard.git
cd rpi-temp-dashboard

# 2. Install dependencies
pip3 install flask

# 3. Create templates folder
mkdir -p templates

# 4. Move index.html to templates
mv index.html templates/

# 5. Run the application
python3 app.py

# 6. Open in browser
# http://<your-pi-ip>:5000

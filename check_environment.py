#!/usr/bin/env python3
"""
Simple script to check if running on VPS or localhost
"""
import socket
import requests
import platform
import os

def check_environment():
    print("🔍 ENVIRONMENT CHECK")
    print("=" * 40)
    
    # 1. Check hostname
    hostname = socket.gethostname()
    print(f"🖥️  Hostname: {hostname}")
    
    # 2. Check local IP
    local_ip = socket.gethostbyname(hostname)
    print(f"🌐 Local IP: {local_ip}")
    
    # 3. Check public IP
    try:
        public_ip = requests.get('https://api.ipify.org', timeout=5).text
        print(f"🌍 Public IP: {public_ip}")
    except:
        print("🌍 Public IP: Unable to fetch")
    
    # 4. Check platform info
    print(f"💻 OS: {platform.system()} {platform.release()}")
    print(f"🏗️  Architecture: {platform.machine()}")
    
    # 5. Simple detection
    print("\n🎯 DETECTION:")
    if local_ip.startswith('127.') or hostname.lower() in ['localhost', 'desktop', 'laptop']:
        print("📍 Running on: LOCALHOST")
    elif 'vps' in hostname.lower() or 'server' in hostname.lower():
        print("📍 Running on: VPS (likely)")
    else:
        print("📍 Running on: REMOTE SERVER (likely VPS)")
    
    # 6. Check if common VPS indicators
    vps_indicators = []
    if os.path.exists('/etc/cloud'):
        vps_indicators.append("Cloud instance detected")
    if 'ec2' in hostname.lower():
        vps_indicators.append("AWS EC2 detected")
    if 'vultr' in hostname.lower():
        vps_indicators.append("Vultr VPS detected")
    if 'digitalocean' in hostname.lower():
        vps_indicators.append("DigitalOcean detected")
    
    if vps_indicators:
        print("🔍 VPS Indicators:")
        for indicator in vps_indicators:
            print(f"   • {indicator}")

if __name__ == "__main__":
    check_environment()
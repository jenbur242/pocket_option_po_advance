#!/usr/bin/env python3
"""Quick environment checks"""

# Method 1: Check IP
import socket
hostname = socket.gethostname()
local_ip = socket.gethostbyname(hostname)
print(f"Hostname: {hostname}")
print(f"Local IP: {local_ip}")

# Method 2: Check if localhost
is_localhost = local_ip.startswith('127.') or hostname.lower() == 'localhost'
print(f"Is Localhost: {is_localhost}")

# Method 3: Simple detection
if is_localhost:
    print("✅ Running on LOCALHOST")
else:
    print("✅ Running on VPS/REMOTE SERVER")
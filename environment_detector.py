#!/usr/bin/env python3
"""
Environment detector - add this to your existing code
"""
import socket

def detect_environment():
    """Simple function to detect if running on VPS or localhost"""
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    
    # Simple detection logic
    if local_ip.startswith('127.') or hostname.lower() in ['localhost', 'desktop']:
        return "LOCALHOST"
    else:
        return "VPS/REMOTE"

# Usage example:
if __name__ == "__main__":
    env = detect_environment()
    print(f"🌍 Environment: {env}")
    
    # You can use this in your code like:
    if env == "LOCALHOST":
        print("📍 Running locally - development mode")
    else:
        print("📍 Running on VPS - production mode")
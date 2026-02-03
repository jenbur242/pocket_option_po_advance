#!/usr/bin/env python3
"""
Update all status display lines in app.py to show clean format
"""

def update_status_displays():
    """Update all status display lines to clean format"""
    
    # Read the file
    with open('app.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace all occurrences of the verbose status display
    old_pattern1 = 'print(f"\\rCurrent: {current_time_str} | Signal: {signal_time_str} ({signal[\'asset\']} {signal[\'direction\'].upper()})", end="", flush=True)'
    new_pattern1 = '''# Show clean status line: date | current time | signal time | time remaining
                    current_date = current_time.strftime('%Y-%m-%d')
                    current_time_hms = current_time.strftime('%H:%M:%S')
                    signal_time_hms = signal['signal_datetime'].strftime('%H:%M:%S')
                    time_remaining = format_time_remaining(current_time, signal['signal_datetime'])
                    
                    print(f"\\r{current_date} | {current_time_hms} | {signal_time_hms} | {time_remaining} | {signal['asset']} {signal['direction'].upper()}", end="", flush=True)'''
    
    # Replace the pattern
    content = content.replace(old_pattern1, new_pattern1)
    
    # Also update the "No signals available" display
    old_pattern2 = 'print(f"\\rCurrent: {current_time_str} | No signals available", end="", flush=True)'
    new_pattern2 = '''current_date = current_time.strftime('%Y-%m-%d')
                    current_time_hms = current_time.strftime('%H:%M:%S')
                    print(f"\\r{current_date} | {current_time_hms} | No signals available", end="", flush=True)'''
    
    content = content.replace(old_pattern2, new_pattern2)
    
    # Write the updated content back
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Updated all status display lines in app.py")
    print("📊 New format: date | current_time | signal_time | time_remaining | asset direction")

if __name__ == "__main__":
    update_status_displays()
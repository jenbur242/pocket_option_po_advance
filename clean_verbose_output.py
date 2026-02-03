#!/usr/bin/env python3
"""
Remove verbose output from app.py to make it cleaner
"""

def clean_verbose_output():
    """Remove verbose scanning and signal overview output"""
    
    # Read the file
    with open('app.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Remove the verbose scanning messages
    content = content.replace('print(f"\\n📊 SCANNING CSV FOR SIGNALS...")', '# Scanning for signals...')
    content = content.replace('print(f"\\n📊 SCANNING CSV FOR SIGNALS ON {target_date}...")', '# Scanning for signals on target date...')
    
    # Remove the verbose signal overview display
    patterns_to_remove = [
        'if initial_signals:\n                print(f"✅ Found {len(initial_signals)} signals in CSV:")\n                for sig in initial_signals[:3]:  # Show first 3\n                    print(f"   🎯 {sig[\'asset\']} {sig[\'direction\'].upper()} at {sig[\'signal_time\']}")\n                if len(initial_signals) > 3:\n                    print(f"   ... and {len(initial_signals) - 3} more signals")',
        'if initial_signals:\n                print(f"✅ Found {len(initial_signals)} signals for {target_date}:")\n                for sig in initial_signals[:3]:  # Show first 3\n                    print(f"   🎯 {sig[\'asset\']} {sig[\'direction\'].upper()} at {sig[\'signal_time\']}")\n                if len(initial_signals) > 3:\n                    print(f"   ... and {len(initial_signals) - 3} more signals")'
    ]
    
    for pattern in patterns_to_remove:
        content = content.replace(pattern, '# Signal overview removed for cleaner output')
    
    # Also remove the verbose "Found X signals" messages in get_signals_from_csv
    content = content.replace('print(f"📅 Filtering signals for current date: {filter_date_str}")', '# Filtering signals...')
    content = content.replace('print(f"📅 Filtering signals for specific date: {filter_date_str}")', '# Filtering signals...')
    content = content.replace('print(f"📊 Found {len(signals)} total signals, {upcoming_count} upcoming for today")', '# Found signals')
    content = content.replace('print(f"📊 Found {len(signals)} signals for {filter_date_str}")', '# Found signals')
    
    # Write the updated content back
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Cleaned verbose output from app.py")
    print("📊 Removed scanning messages and signal overviews")
    print("🎯 Status display now shows clean single-line format")

if __name__ == "__main__":
    clean_verbose_output()
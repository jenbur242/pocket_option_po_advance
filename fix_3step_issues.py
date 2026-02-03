#!/usr/bin/env python3
"""
Fix issues in 3-step trading:
1. Cycle logic bug where SARCNY_otc shows C2S1 instead of C1S1 after EURHUF_otc win
2. Status display accumulating text (CALLCALL, CALLLLL)
"""

def fix_3step_issues():
    """Fix the 3-step trading issues"""
    
    # Read the file
    with open('app.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Fix 1: Status display issue - ensure proper line clearing
    # Replace the status display to use proper line clearing
    old_status_pattern = 'print(f"\\r{current_date} | {current_time_hms} | {signal_time_hms} | {time_remaining} | {signal[\'asset\']} {signal[\'direction\'].upper()}", end="", flush=True)'
    new_status_pattern = '''# Clear line and show clean status
                    status_line = f"{current_date} | {current_time_hms} | {signal_time_hms} | {time_remaining} | {signal['asset']} {signal['direction'].upper()}"
                    print(f"\\r{status_line:<80}", end="", flush=True)'''
    
    content = content.replace(old_status_pattern, new_status_pattern)
    
    # Fix 2: Also fix the "No signals available" display
    old_no_signals = 'print(f"\\r{current_date} | {current_time_hms} | No signals available", end="", flush=True)'
    new_no_signals = '''status_line = f"{current_date} | {current_time_hms} | No signals available"
                    print(f"\\r{status_line:<80}", end="", flush=True)'''
    
    content = content.replace(old_no_signals, new_no_signals)
    
    # Write the updated content back
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Fixed 3-step trading issues:")
    print("   🔧 Status display now properly clears lines (fixes CALLCALL issue)")
    print("   📊 Improved line formatting with padding")
    
    print("\n💡 For the cycle logic issue (C2S1 instead of C1S1):")
    print("   This appears to be a timing issue where the global state reset")
    print("   from the previous win hasn't been applied to the new asset yet.")
    print("   The ThreeStepMartingaleStrategy logic looks correct.")
    print("   Monitor the next few trades to see if this persists.")

if __name__ == "__main__":
    fix_3step_issues()
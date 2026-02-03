#!/usr/bin/env python3
"""Reprocess the Pocket Option Sign CSV with corrected signal extraction"""

import csv
import re
import os

def extract_pocket_option_sign_signal(message_text):
    """Extract signal data from Pocket Option Sign channel format"""
    if not message_text:
        return None
    
    # Skip result messages and non-signal content
    skip_words = ['win', 'loss', 'profit', '✅', '❌', '☑️', 'register', 'bonus', 'join', 'channel', 'withdraw']
    if any(word in message_text.lower() for word in skip_words):
        # But allow if it contains signal indicators
        if not any(indicator in message_text for indicator in ['🛰', '💷', '⌚️', '🔼', '🔽']):
            return None
    
    # Must contain Pocket Option signal indicators
    if not ('🛰 POCKET OPTION' in message_text and '💷' in message_text and '⌚️' in message_text):
        return None
    
    # Extract Asset - specific pattern for this channel: 💷 EURUSD-OTC
    asset = None
    asset_patterns = [
        r'💷\s+([A-Z]{6}-OTC)',        # 💷 EURUSD-OTC
        r'💷\s+([A-Z]{6})',            # 💷 EURUSD
    ]
    
    for pattern in asset_patterns:
        asset_match = re.search(pattern, message_text, re.IGNORECASE)
        if asset_match:
            raw_asset = asset_match.group(1).upper()
            base_asset = raw_asset.split('-')[0]
            if len(base_asset) == 6:  # Valid currency pair
                asset = raw_asset
                break
    
    if not asset:
        return None
    
    # Extract time - specific pattern: ⌚️ 23:40:00
    signal_time = None
    time_patterns = [
        r'⌚️\s+(\d{1,2}:\d{2}:\d{2})',     # ⌚️ 23:40:00
        r'⌚️\s+(\d{1,2}:\d{2})',           # ⌚️ 23:40
    ]
    
    for pattern in time_patterns:
        time_match = re.search(pattern, message_text)
        if time_match:
            full_time = time_match.group(1)
            # Convert to HH:MM format (remove seconds if present)
            if len(full_time.split(':')) == 3:
                signal_time = ':'.join(full_time.split(':')[:2])
            else:
                signal_time = full_time
            break
    
    # Extract direction - specific patterns: 🔼 call or 🔽 put
    direction = None
    if '🔽 put' in message_text.lower():
        direction = 'put'
    elif '🔼 call' in message_text.lower():
        direction = 'call'
    
    if not direction or not signal_time:
        return None
    
    return {
        'asset': asset,
        'direction': direction,
        'signal_time': signal_time
    }

def reprocess_csv():
    """Reprocess the CSV file with corrected signal extraction"""
    csv_file = "pocketoption_pocket_option_sign_20260129.csv"
    
    if not os.path.exists(csv_file):
        print(f"❌ CSV file not found: {csv_file}")
        return
    
    # Read existing data
    rows = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = next(reader)  # Read headers
        for row in reader:
            rows.append(row)
    
    print(f"📄 Processing {len(rows)} rows from {csv_file}")
    
    # Reprocess each row
    updated_rows = []
    signals_found = 0
    
    for row in rows:
        if len(row) >= 8:
            timestamp, channel, message_id, message_text, old_is_signal, old_asset, old_direction, old_signal_time = row[:8]
            
            # Extract signal data with corrected method
            signal_data = extract_pocket_option_sign_signal(message_text)
            
            if signal_data:
                # Update with extracted signal data
                new_row = [timestamp, channel, message_id, message_text, 'Yes', 
                          signal_data['asset'], signal_data['direction'], signal_data['signal_time']]
                signals_found += 1
                print(f"✅ Signal found: {signal_data['asset']} {signal_data['direction']} at {signal_data['signal_time']}")
            else:
                # Keep as non-signal
                new_row = [timestamp, channel, message_id, message_text, 'No', '', '', '']
            
            updated_rows.append(new_row)
    
    # Write updated data back to CSV
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)  # Write headers
        writer.writerows(updated_rows)
    
    print(f"\n✅ CSV reprocessed successfully!")
    print(f"📊 Total rows: {len(updated_rows)}")
    print(f"🎯 Signals detected: {signals_found}")
    print(f"📄 Updated file: {csv_file}")

if __name__ == "__main__":
    reprocess_csv()
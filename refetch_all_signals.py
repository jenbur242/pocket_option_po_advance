#!/usr/bin/env python3
"""
Refetch ALL signals from PO ADVANCE BOT channel and save to CSV
This will clear the CSV and fetch everything fresh from Telegram
"""
import asyncio
import os
import csv
import re
from datetime import datetime
from dotenv import load_dotenv
from telethon import TelegramClient

# Load environment variables
load_dotenv()

def extract_po_advance_signal(message_text):
    """Extract signal data from PO ADVANCE BOT message"""
    if not message_text:
        return None
    
    # Skip obvious non-signal messages
    skip_phrases = ['generating', 'please wait', 'loading', 'updating', 'maintenance', 'resultado', 'result', 'win', 'loss', 'profit']
    if any(phrase in message_text.lower() for phrase in skip_phrases):
        return None
    
    try:
        # Pattern: POCKET PRO AI BOT format
        if "POCKET PRO AI" in message_text or "POCKET PRO AI BOT" in message_text:
            # Extract asset/pair
            asset_match = re.search(r'💹\s*Pair\s*│\s*([^\s\n]+)', message_text)
            asset = asset_match.group(1).strip() if asset_match else None
            
            # Extract entry time
            time_match = re.search(r'⏰\s*Entry Time\s*│\s*(\d{1,2}:\d{2})', message_text)
            signal_time = time_match.group(1) if time_match else None
            
            # Extract direction
            direction = None
            if 'PUT ➥ DOWN' in message_text or '⬇️' in message_text:
                direction = 'put'
            elif 'CALL ➥ UP' in message_text or '⬆️' in message_text:
                direction = 'call'
            
            if asset and direction and signal_time:
                return {
                    'asset': asset,
                    'direction': direction,
                    'signal_time': signal_time
                }
        
        return None
        
    except Exception as e:
        print(f"   ⚠️ Signal extraction error: {e}")
        return None

async def refetch_all_signals():
    """Refetch all signals from channel and save to CSV"""
    
    # Telegram config
    api_id = os.getenv('TELEGRAM_API_ID')
    api_hash = os.getenv('TELEGRAM_API_HASH')
    phone = os.getenv('TELEGRAM_PHONE')
    
    # Channel
    channel_link = 'https://t.me/+teILb87erlthODll'  # PO ADVANCE BOT
    csv_file = 'pocketoption_po_advance_bot.csv'
    
    print("🔄 REFETCHING ALL SIGNALS FROM PO ADVANCE BOT")
    print("=" * 60)
    print(f"📅 Target Date: {datetime.now().strftime('%Y-%m-%d')} (today, local time)")
    print(f"📄 CSV File: {csv_file}")
    print("=" * 60)
    
    # Create client - reuse existing session
    session_name = 'monitor_session_1771849245'  # Reuse existing session
    client = TelegramClient(session_name, api_id, api_hash)
    
    try:
        print(f"🔌 Connecting using existing session: {session_name}")
        await client.start(phone=phone)
        print("✅ Connected to Telegram (reused session)")
        
        # Get channel entity
        print(f"📡 Connecting to channel...")
        try:
            entity = await client.get_entity(channel_link)
        except:
            invite_hash = channel_link.split('+')[-1]
            result = await client.join_chat(invite_hash)
            entity = result.chats[0]
        
        print(f"✅ Connected to: {entity.title}")
        
        # Fetch ALL messages
        print(f"\n📥 Fetching all messages...")
        messages = await client.get_messages(entity, limit=None)
        print(f"✅ Fetched {len(messages)} total messages")
        
        # Filter to today (local time)
        current_date = datetime.now().strftime('%Y-%m-%d')
        today_messages = []
        
        for msg in messages:
            if msg.date:
                msg_date_local = msg.date.astimezone().strftime('%Y-%m-%d')
                if msg_date_local == current_date:
                    today_messages.append(msg)
        
        print(f"✅ Found {len(today_messages)} messages from today ({current_date})")
        
        # Clear CSV and write headers
        headers = ['date', 'timestamp', 'channel', 'message_id', 'message_text', 
                   'is_signal', 'asset', 'direction', 'signal_time']
        
        print(f"\n📝 Writing to CSV: {csv_file}")
        print(f"🗑️ Clearing old data...")
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)  # Quote all fields
            writer.writerow(headers)
        
        print(f"✅ CSV cleared and headers written")
        
        # Process and save all messages (oldest first)
        print(f"\n📊 Processing {len(today_messages)} messages...")
        print("=" * 60)
        
        signals_found = 0
        messages_saved = 0
        
        for i, msg in enumerate(reversed(today_messages), 1):
            if msg.text:
                # Extract signal data
                signal_data = extract_po_advance_signal(msg.text)
                
                # Prepare row data
                msg_time_local = msg.date.astimezone()
                date = msg_time_local.strftime('%Y-%m-%d')
                timestamp = msg_time_local.strftime('%Y-%m-%d %H:%M:%S')
                channel_name = 'po advance bot'
                message_id = msg.id
                
                # Clean message text - remove newlines, tabs, and extra spaces
                message_text = msg.text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
                # Remove multiple spaces
                message_text = ' '.join(message_text.split())
                # Limit length to avoid CSV issues
                if len(message_text) > 500:
                    message_text = message_text[:500] + '...'
                
                if signal_data:
                    is_signal = 'Yes'
                    asset = signal_data['asset']
                    direction = signal_data['direction']
                    signal_time = signal_data['signal_time']
                    signals_found += 1
                    
                    print(f"{i}. 🎯 SIGNAL: {asset} {direction.upper()} at {signal_time} (ID: {message_id})")
                else:
                    is_signal = 'No'
                    asset = ''
                    direction = ''
                    signal_time = ''
                    
                    # Show non-signal messages briefly
                    if i <= 5 or '12:04' in message_text or 'GBPUSD' in message_text.upper():
                        preview = message_text[:80]
                        print(f"{i}. 📝 Message: {preview}... (ID: {message_id})")
                
                # Write to CSV with proper quoting
                row = [date, timestamp, channel_name, message_id, message_text,
                       is_signal, asset, direction, signal_time]
                
                with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f, quoting=csv.QUOTE_ALL)  # Quote all fields
                    writer.writerow(row)
                
                messages_saved += 1
            else:
                # Media message
                msg_time_local = msg.date.astimezone()
                date = msg_time_local.strftime('%Y-%m-%d')
                timestamp = msg_time_local.strftime('%Y-%m-%d %H:%M:%S')
                
                row = [date, timestamp, 'po advance bot', msg.id, '[MEDIA]',
                       'No', '', '', '']
                
                with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f, quoting=csv.QUOTE_ALL)  # Quote all fields
                    writer.writerow(row)
                
                messages_saved += 1
        
        print("=" * 60)
        print(f"\n✅ REFETCH COMPLETED")
        print(f"📊 Summary:")
        print(f"   📅 Date: {current_date}")
        print(f"   📨 Total messages: {len(today_messages)}")
        print(f"   💾 Messages saved: {messages_saved}")
        print(f"   🎯 Signals found: {signals_found}")
        print(f"   📄 CSV file: {csv_file}")
        
        # Check for 12:04 signal specifically
        print(f"\n🔍 Checking for 12:04 GBPUSD signal...")
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            gbpusd_1204 = [row for row in reader if '12:04' in row['signal_time'] and 'GBPUSD' in row['asset'].upper()]
            
            if gbpusd_1204:
                print(f"✅ Found {len(gbpusd_1204)} GBPUSD 12:04 signal(s):")
                for row in gbpusd_1204:
                    print(f"   📊 {row['asset']} {row['direction'].upper()} at {row['signal_time']} (Message ID: {row['message_id']})")
            else:
                print(f"❌ No GBPUSD 12:04 signal found in CSV")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await client.disconnect()
        print("\n👋 Disconnected from Telegram")

if __name__ == '__main__':
    asyncio.run(refetch_all_signals())

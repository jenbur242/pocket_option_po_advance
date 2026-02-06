#!/usr/bin/env python3
"""
Simple Monitor - Fetch messages from Telegram channels and save to CSV
Updated with improved LC Trader pattern recognition
"""
import asyncio
import logging
import os
import re
import csv
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telethon import TelegramClient

# Load environment variables
load_dotenv()

# Disable telethon logging
logging.basicConfig(level=logging.CRITICAL)

class SimpleMonitor:
    def __init__(self):
        # Telegram config
        self.api_id = os.getenv('TELEGRAM_API_ID')
        self.api_hash = os.getenv('TELEGRAM_API_HASH')
        self.phone = os.getenv('TELEGRAM_PHONE')
        
        # Initialize clients
        self.telegram_client = None
        
        # Channels to monitor
        self.channels = [
            #  {
            #      'id': 'https://t.me/+bZ0mJA0qQX02NDIx',
            #      'name': 'james martin vip channel m1',
            #      'entity': None,
            #      'last_msg_id': None
            #  },
            # {
            #     'id': 'https://t.me/+teILb87erlthODll',  # Correct PO ADVANCE BOT invite link
            #     'name': 'po advance bot',
            #     'entity': None,
            #     'last_msg_id': None
            # },
            # {
            #     'id': 'https://t.me/luctrader09',
            #     'name': 'lc trader',
            #     'entity': None,
            #     'last_msg_id': None
            # },

            #  {
            #     'id': 'https://t.me/pocketoption0o',
            #      'name': 'logic 5 cycle',
            #      'entity': None,
            #      'last_msg_id': None
            #  },
            #  {
            #     'id': 'https://t.me/pocket_optionsign',
            #     'name': 'pocket option sign',
            #     'entity': None,
            #     'last_msg_id': None
            #  },
            #  {
            #     'id': 'https://t.me/pocketoptionai',  # NEW CHANNEL
            #      'name': 'pocket pro ai',
            #      'entity': None,
            #      'last_msg_id': None
            #  },
            # {
            #    'id': 'https://t.me/+Wc1-m-ShMdRkOTg1',  # NEW CHANNEL
            #     'name': 'Trade x po',
            #     'entity': None,
            #     'last_msg_id': None
            # }
             {
                'id': 'https://t.me/+3FlQlhKisy5kOTcx',  # NEW CHANNEL
                 'name': 'James martin free channel',
                 'entity': None,
                 'last_msg_id': None
             }
        ]
        
        # CSV file setup - separate file for each channel with date column
        self.csv_files = {}
        self.current_date = None  # Track current date for automatic detection
        
        # Initialize CSV files for each channel - FIXED FILENAMES (no dates)
        channel_csv_mapping = {
            'james martin vip channel m1': 'pocketoption_james_martin_vip_channel_m1.csv',
            'lc trader': 'pocketoption_lc_trader.csv',
            'po advance bot': 'pocketoption_po_advance_bot.csv',
            'logic 5 cycle': 'pocketoption_logic_5_cycle.csv',
            'pocket option sign': 'pocketoption_pocket_option_sign.csv',
            'pocket pro ai': 'pocketoption_pocket_pro_ai.csv',
            'trade x po': 'pocketoption_new_channel_7.csv',  # lowercase key to match channel_name.lower()
            'new channel': 'pocketoption_new_channel.csv'  # New channel mapping
        }
        
        # Set fixed CSV filenames for each channel
        for channel in self.channels:
            channel_name = channel['name'].lower()
            if channel_name in channel_csv_mapping:
                self.csv_files[channel['name']] = channel_csv_mapping[channel_name]
            else:
                # Fallback for any other channels
                safe_name = re.sub(r'[^\w\s-]', '', channel['name']).strip()
                safe_name = re.sub(r'[-\s]+', '_', safe_name).lower()
                csv_filename = f"pocketoption_{safe_name}.csv"
                self.csv_files[channel['name']] = csv_filename
        
        # Fix any existing CSV files that don't have headers
        self.fix_existing_csv_files()
        
        # Initialize CSV files with headers
        self.ensure_csv_headers()
        
        # Set initial date
        self.current_date = datetime.now().strftime('%Y-%m-%d')
        
        # Clean old data on startup
        print(f"\n🧹 STARTUP: Cleaning old data from CSV files...")
        print(f"   Current Date: {self.current_date}")
        self.clean_old_data_on_startup()
        
        self.current_channel = 0
        self.running = False
        
        # Session statistics
        self.session_start = datetime.now()
        self.signals_detected = 0
        self.messages_processed = 0
        self.last_status_time = None
    
    async def cleanup_all_sessions(self):
        """Clean all previous session files on startup"""
        try:
            import glob
            import time
            
            # Find all session files
            session_patterns = [
                'monitor_session*.session*',
                'signal_session*.session*',
                '*.session',
                '*.session-journal',
                '*.session-wal'
            ]
            
            all_session_files = []
            for pattern in session_patterns:
                all_session_files.extend(glob.glob(pattern))
            
            if all_session_files:
                print(f"🗑️ Found {len(all_session_files)} session files to clean:")
                for file in all_session_files:
                    print(f"   📄 {file}")
                
                # Force cleanup with retries
                cleaned_count = 0
                for session_file in all_session_files:
                    if os.path.exists(session_file):
                        for attempt in range(3):
                            try:
                                os.remove(session_file)
                                print(f"   ✅ Cleaned: {session_file}")
                                cleaned_count += 1
                                break
                            except PermissionError:
                                if attempt < 2:
                                    print(f"   ⏳ Retrying {session_file}... (attempt {attempt + 1}/3)")
                                    time.sleep(0.5)
                                else:
                                    print(f"   ⚠️ Could not remove {session_file}: File locked")
                            except Exception as e:
                                print(f"   ❌ Error removing {session_file}: {e}")
                                break
                
                print(f"✅ Session cleanup completed: {cleaned_count}/{len(all_session_files)} files cleaned")
            else:
                print("✅ No previous session files found")
                
        except Exception as cleanup_error:
            print(f"⚠️ Session cleanup error: {cleanup_error}")
    
    def fix_existing_csv_files(self):
        """Fix any existing CSV files that don't have proper headers"""
        import glob
        
        # Find all CSV files matching various patterns
        csv_patterns = [
            "pocketoption_*.csv",
            "*pocketoption*.csv", 
            "test_pocketoption*.csv"
        ]
        
        existing_csv_files = []
        for pattern in csv_patterns:
            existing_csv_files.extend(glob.glob(pattern))
        
        # Remove duplicates
        existing_csv_files = list(set(existing_csv_files))
        
        headers = [
            'date', 'timestamp', 'channel', 'message_id', 'message_text', 
            'is_signal', 'asset', 'direction', 'signal_time'
        ]
        
        for csv_file in existing_csv_files:
            try:
                # Check if file has headers
                needs_headers = False
                existing_data = ""
                
                if os.path.exists(csv_file):
                    with open(csv_file, 'r', newline='', encoding='utf-8') as f:
                        first_line = f.readline().strip()
                        
                        # Check if first line contains headers
                        if not first_line or first_line.startswith('2026-') or 'timestamp' not in first_line:
                            needs_headers = True
                            # Read all existing data
                            f.seek(0)
                            existing_data = f.read().strip()
                            print(f"🔧 Found CSV file without headers: {csv_file}")
                
                # Add headers if needed
                if needs_headers:
                    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow(headers)
                        
                        # Add existing data if any
                        if existing_data:
                            f.write('\n' + existing_data)
                    
                    print(f"✅ Added headers to: {csv_file}")
                else:
                    print(f"✅ Headers already present in: {csv_file}")
                    
            except Exception as e:
                print(f"⚠️ Error fixing CSV file {csv_file}: {e}")
    
    def clean_old_data_on_startup(self):
        """Clean all old date data from CSV files on startup, keeping only current date"""
        headers = [
            'date', 'timestamp', 'channel', 'message_id', 'message_text', 
            'is_signal', 'asset', 'direction', 'signal_time'
        ]
        
        print("-" * 60)
        
        for channel_name, csv_file in self.csv_files.items():
            try:
                if not os.path.exists(csv_file):
                    print(f"   ℹ️ {csv_file}: File doesn't exist yet")
                    continue
                
                # Read all data from CSV
                rows_to_keep = []
                old_rows_count = 0
                total_rows = 0
                old_dates = set()
                
                with open(csv_file, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    
                    # Read header
                    header_row = next(reader, None)
                    
                    # Process data rows
                    for row in reader:
                        total_rows += 1
                        if len(row) >= 1:  # Check if row has date column
                            row_date = row[0]
                            if row_date == self.current_date:
                                # Keep only current date rows
                                rows_to_keep.append(row)
                            else:
                                # Count old date rows
                                old_rows_count += 1
                                old_dates.add(row_date)
                
                # Rewrite CSV file with headers and only current date data
                with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)  # Write headers
                    writer.writerows(rows_to_keep)  # Write current date data only
                
                if old_rows_count > 0:
                    print(f"   🗑️ {csv_file}:")
                    print(f"      Old dates found: {', '.join(sorted(old_dates))}")
                    print(f"      Deleted: {old_rows_count} old rows")
                    print(f"      Kept: {len(rows_to_keep)} current date rows ({self.current_date})")
                elif total_rows > 0:
                    print(f"   ✅ {csv_file}: All {len(rows_to_keep)} rows are current date ({self.current_date})")
                else:
                    print(f"   ℹ️ {csv_file}: Empty file")
                    
            except Exception as e:
                print(f"   ⚠️ Error cleaning {csv_file}: {e}")
        
        print("-" * 60)
        print(f"✅ Startup cleanup completed - All CSV files now contain only {self.current_date} data\n")
    
    def clean_previous_date_data(self, old_date):
        """Clean all rows with previous date from CSV files and keep only current date data with headers"""
        headers = [
            'date', 'timestamp', 'channel', 'message_id', 'message_text', 
            'is_signal', 'asset', 'direction', 'signal_time'
        ]
        
        print(f"\n🧹 CLEANING PREVIOUS DATE DATA:")
        print(f"   Old Date: {old_date}")
        print(f"   New Date: {self.current_date}")
        print("-" * 60)
        
        for channel_name, csv_file in self.csv_files.items():
            try:
                if not os.path.exists(csv_file):
                    print(f"   ℹ️ {csv_file}: File doesn't exist yet")
                    continue
                
                # Read all data from CSV
                rows_to_keep = []
                previous_date_rows_count = 0
                total_rows = 0
                
                with open(csv_file, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    
                    # Read header
                    header_row = next(reader, None)
                    
                    # Process data rows
                    for row in reader:
                        total_rows += 1
                        if len(row) >= 1:  # Check if row has date column
                            row_date = row[0]
                            if row_date == self.current_date:
                                # Keep only current date rows
                                rows_to_keep.append(row)
                            else:
                                # Count all non-current date rows for reporting
                                previous_date_rows_count += 1
                
                # Rewrite CSV file with headers and only current date data
                with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)  # Write headers
                    writer.writerows(rows_to_keep)  # Write current date data only
                
                if previous_date_rows_count > 0:
                    print(f"   🗑️ {csv_file}:")
                    print(f"      Deleted: {previous_date_rows_count} old rows")
                    print(f"      Kept: {len(rows_to_keep)} current date rows")
                elif total_rows > 0:
                    print(f"   ✅ {csv_file}: All {len(rows_to_keep)} rows are current date")
                else:
                    print(f"   ℹ️ {csv_file}: Empty file")
                    
            except Exception as e:
                print(f"   ⚠️ Error cleaning {csv_file}: {e}")
        
        print("-" * 60)
        print(f"✅ Date cleanup completed - All CSV files now contain only {self.current_date} data")
        print()
    
    def check_date_change(self):
        """Check if date has changed and CLEAR ALL DATA to start fresh with new date"""
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        if self.current_date != current_date:
            old_date = self.current_date
            self.current_date = current_date
            
            if old_date:
                print(f"\n{'='*60}")
                print(f"📅 DATE CHANGED: {old_date} → {current_date}")
                print(f"{'='*60}")
                print(f"🗑️ CLEARING ALL OLD DATA - Starting fresh with {current_date}")
                self.clear_all_csv_data()
                print(f"✅ All CSV files cleared and ready for {current_date} data")
                print(f"✅ Only NEW messages from {current_date} will be saved")
                print(f"{'='*60}\n")
            
            return True  # Date changed
        return False  # No date change
    
    def clear_all_csv_data(self):
        """Clear all data from CSV files, keeping only headers"""
        headers = [
            'date', 'timestamp', 'channel', 'message_id', 'message_text', 
            'is_signal', 'asset', 'direction', 'signal_time'
        ]
        
        for channel_name, csv_file in self.csv_files.items():
            try:
                if not os.path.exists(csv_file):
                    continue
                
                # Count rows before clearing
                row_count = 0
                with open(csv_file, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    next(reader, None)  # Skip header
                    row_count = sum(1 for row in reader)
                
                # Rewrite with only headers
                with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                
                if row_count > 0:
                    print(f"   🗑️ {csv_file}: Deleted {row_count} rows")
                else:
                    print(f"   ✅ {csv_file}: Already empty")
                    
            except Exception as e:
                print(f"   ⚠️ Error clearing {csv_file}: {e}")
    
    def ensure_csv_headers(self):
        """Ensure CSV files exist with proper headers for each channel"""
        headers = [
            'date', 'timestamp', 'channel', 'message_id', 'message_text', 
            'is_signal', 'asset', 'direction', 'signal_time'
        ]
        
        for channel_name, csv_file in self.csv_files.items():
            # Check if file exists and has headers
            file_needs_headers = False
            
            if not os.path.exists(csv_file):
                # File doesn't exist, create with headers
                file_needs_headers = True
                print(f"📄 Creating new CSV file for {channel_name}: {csv_file}")
            else:
                # File exists, check if it has headers
                try:
                    with open(csv_file, 'r', newline='', encoding='utf-8') as f:
                        first_line = f.readline().strip()
                        # Check if first line contains headers (not timestamp format)
                        if not first_line or first_line.startswith('2026-') or not 'timestamp' in first_line:
                            file_needs_headers = True
                            print(f"📄 Existing CSV file missing headers for {channel_name}: {csv_file}")
                            
                            # Backup existing data
                            f.seek(0)
                            existing_data = f.read()
                            
                            # Rewrite file with headers + existing data
                            with open(csv_file, 'w', newline='', encoding='utf-8') as write_f:
                                writer = csv.writer(write_f)
                                writer.writerow(headers)
                                # Add existing data if any
                                if existing_data.strip():
                                    write_f.write(existing_data)
                            print(f"✅ Added headers to existing CSV file: {csv_file}")
                        else:
                            print(f"📄 Using existing CSV file with headers for {channel_name}: {csv_file}")
                except Exception as e:
                    print(f"⚠️ Error checking CSV headers for {csv_file}: {e}")
                    file_needs_headers = True
            
            # Create new file with headers if needed
            if file_needs_headers and not os.path.exists(csv_file):
                with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                print(f"✅ Created CSV file with headers for {channel_name}: {csv_file}")
    
    async def fetch_last_message_pattern(self, channel):
        """Fetch the last 10 messages from TODAY ONLY to learn pattern and save all to CSV"""
        if not channel['entity']:
            return None
        
        try:
            # Get the last 50 messages to find today's messages
            messages = await self.telegram_client.get_messages(channel['entity'], limit=50)
            
            if not messages:
                print(f"   📭 No messages found in {channel['name']}")
                return None
            
            # Filter messages to only TODAY
            current_date = datetime.now().strftime('%Y-%m-%d')
            today_messages = []
            
            for msg in messages:
                if msg.date:
                    msg_date = msg.date.strftime('%Y-%m-%d')
                    if msg_date == current_date:
                        today_messages.append(msg)
            
            if not today_messages:
                print(f"   📭 No messages from TODAY ({current_date}) found in {channel['name']}")
                return None
            
            # Limit to last 10 messages from today
            today_messages = today_messages[:10]
            
            print(f"\n🔍 ANALYZING & SAVING LAST {len(today_messages)} MESSAGES FROM TODAY ({current_date}) for {channel['name']}:")
            print("-" * 60)
            
            patterns_found = []
            messages_saved = 0
            
            # Process messages in reverse order (oldest first) for better CSV chronology
            for i, msg in enumerate(reversed(today_messages)):
                if msg.text:
                    print(f"📨 Message {i+1} (ID: {msg.id}):")
                    print(f"   📝 Text: {msg.text[:200]}...")
                    
                    # Analyze for signal patterns
                    signal_data = self.extract_signal_data(msg.text, channel['name'])
                    
                    # Save ALL messages to CSV (both signals and regular messages)
                    saved = self.save_to_csv(channel, msg, signal_data)
                    
                    if signal_data:
                        print(f"   🎯 SIGNAL DETECTED:")
                        print(f"      💰 Asset: {signal_data['asset']}")
                        print(f"      📊 Direction: {signal_data['direction']}")
                        print(f"      ⏰ Time: {signal_data['signal_time'] or 'Not specified'}")
                        print(f"      💾 Saved to CSV: {'✅' if saved else '❌'}")
                        patterns_found.append(signal_data)
                        if saved:
                            messages_saved += 1
                    else:
                        # Check for other patterns
                        text_lower = msg.text.lower()
                        if any(word in text_lower for word in ['win', 'result', '✅']):
                            print(f"   📊 RESULT MESSAGE detected")
                        elif any(word in text_lower for word in ['register', 'bonus', 'join']):
                            print(f"   📢 PROMOTIONAL MESSAGE detected")
                        else:
                            print(f"   📝 REGULAR MESSAGE")
                        
                        print(f"      💾 Saved to CSV: {'✅' if saved else '❌'}")
                        if saved:
                            messages_saved += 1
                    
                    print()
            
            print(f"📊 SUMMARY for {channel['name']}:")
            print(f"   📅 Date: {current_date} (TODAY ONLY)")
            print(f"   🎯 Signals found: {len(patterns_found)}")
            print(f"   💾 Messages saved to CSV: {messages_saved}")
            if patterns_found:
                print(f"   📄 CSV file: {self.csv_files.get(channel['name'], 'Unknown')}")
            
            print("-" * 60)
            return patterns_found
            
        except Exception as e:
            print(f"❌ Error fetching patterns from {channel['name']}: {e}")
            return None
    
    async def list_available_channels(self):
        """List all available channels in dialogs to help find the correct one"""
        print("🔍 SCANNING YOUR TELEGRAM DIALOGS...")
        print("=" * 60)
        
        try:
            channel_count = 0
            async for dialog in self.telegram_client.iter_dialogs():
                if hasattr(dialog.entity, 'title'):  # It's a channel/group
                    channel_count += 1
                    entity_type = "Channel" if hasattr(dialog.entity, 'broadcast') and dialog.entity.broadcast else "Group"
                    print(f"📺 {entity_type}: '{dialog.entity.title}' (ID: {dialog.entity.id})")
                    
                    # Highlight potential PO ADVANCE BOT matches
                    title_upper = dialog.entity.title.upper()
                    if any(keyword in title_upper for keyword in ['PO ADVANCE', 'POCKET PRO', 'POCKET OPTION']):
                        print(f"   🎯 POTENTIAL MATCH for PO ADVANCE BOT!")
            
            print("=" * 60)
            print(f"📊 Found {channel_count} channels/groups in your dialogs")
            print("💡 Look for channels containing 'PO ADVANCE', 'POCKET PRO', or 'POCKET OPTION'")
            
        except Exception as e:
            print(f"❌ Error listing channels: {e}")

    async def initialize(self):
        """Initialize clients with session reuse and authentication"""
        try:
            # ALWAYS clean all previous sessions on startup
            print("🧹 Cleaning all previous sessions...")
            await self.cleanup_all_sessions()
            
            # Check for existing instances
            import psutil
            current_pid = os.getpid()
            python_processes = []
            
            try:
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    if proc.info['name'] and 'python' in proc.info['name'].lower():
                        if proc.info['cmdline'] and any('simple_monitor.py' in str(cmd) for cmd in proc.info['cmdline']):
                            if proc.info['pid'] != current_pid:
                                python_processes.append(proc.info['pid'])
                
                if python_processes:
                    print(f"⚠️ Found {len(python_processes)} other monitor instances running")
                    print(f"💡 PIDs: {python_processes}")
                    print(f"🔧 To avoid conflicts, consider stopping other instances")
            except Exception as proc_check_error:
                print(f"⚠️ Could not check for other instances: {proc_check_error}")
            
            print("🔌 Initializing fresh Telegram connection...")
            
            # Use unique session name with timestamp to avoid conflicts
            import time
            session_name = f'monitor_session_{int(time.time())}'
            
            # Create Telegram client with unique session name
            self.telegram_client = TelegramClient(session_name, self.api_id, self.api_hash)
            
            # Check if session exists
            print("📱 Creating fresh Telegram session...")
            
            # Always create new session (no reuse)
            try:
                await self.telegram_client.start(phone=self.phone)
                
                # Test connection
                me = await self.telegram_client.get_me()
                print(f"✅ Connected as: {me.first_name} ({me.phone})")
                
            except Exception as auth_error:
                print(f"⚠️ Authentication required: {auth_error}")
                print("🔄 Starting fresh authentication...")
                
                # Start fresh authentication
                await self.authenticate_new_session()
                
                # Test new connection
                me = await self.telegram_client.get_me()
                print(f"✅ Fresh session created - Logged in as: {me.first_name} ({me.phone})")
            
            # Get entities for all channels and analyze patterns
            print("📡 Connecting to channels and analyzing patterns...")
            for channel in self.channels:
                try:
                    # Handle different channel ID formats
                    if isinstance(channel['id'], str) and ('joinchat' in channel['id'] or '+' in channel['id']):
                        # Handle invite link
                        if '+' in channel['id']:
                            invite_hash = channel['id'].split('+')[-1]
                        else:
                            invite_hash = channel['id'].split('/')[-1]
                        
                        # Join channel using invite link
                        try:
                            result = await self.telegram_client.join_chat(invite_hash)
                            entity = result.chats[0]
                        except Exception as join_error:
                            print(f"⚠️ Could not join channel: {join_error}")
                            # Try to get entity directly
                            entity = await self.telegram_client.get_entity(channel['id'])
                    elif isinstance(channel['id'], str) and channel['id'] == 'PO ADVANCE BOT':
                        # Handle PO ADVANCE BOT by searching in dialogs
                        print(f"🔍 Searching for PO ADVANCE BOT in dialogs...")
                        entity = None
                        async for dialog in self.telegram_client.iter_dialogs():
                            dialog_title = getattr(dialog.entity, 'title', '')
                            # Search for various possible titles
                            if (dialog_title == 'PO ADVANCE BOT' or 
                                'POCKET PRO AI' in dialog_title or
                                'PO ADVANCE' in dialog_title.upper() or
                                'POCKET OPTION' in dialog_title.upper()):
                                entity = dialog.entity
                                print(f"✅ Found PO ADVANCE BOT in dialogs: '{dialog_title}' (ID: {entity.id})")
                                break
                        
                        if not entity:
                            print(f"❌ PO ADVANCE BOT not found in dialogs")
                            print(f"💡 Let me show you all available channels...")
                            await self.list_available_channels()
                            print(f"💡 Please join the PO ADVANCE BOT channel manually, then restart the monitor")
                            continue
                    else:
                        # Handle direct channel ID (numeric)
                        try:
                            entity = await self.telegram_client.get_entity(channel['id'])
                        except Exception as direct_error:
                            print(f"⚠️ Direct ID failed for {channel['name']}: {direct_error}")
                            continue
                    
                    channel['entity'] = entity
                    
                    # Get the latest message ID to start from
                    messages = await self.telegram_client.get_messages(entity, limit=1)
                    if messages:
                        channel['last_msg_id'] = messages[0].id
                    
                    channel_title = getattr(entity, 'title', channel['name'])
                    print(f"✅ {channel['name']}: Connected to '{channel_title}'")
                    
                    # Analyze message patterns from this channel (last 10 messages)
                    await self.fetch_last_message_pattern(channel)
                    
                except Exception as e:
                    print(f"❌ {channel['name']}: Failed to connect - {e}")
            
            return True
            
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False
    
    async def authenticate_new_session(self):
        """Handle new session authentication with OTP and password"""
        try:
            print(f"📱 Sending OTP to {self.phone}...")
            
            # Start authentication process (without password_callback)
            await self.telegram_client.start(
                phone=self.phone,
                code_callback=self.get_otp_code
            )
            
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            raise e
    
    def get_otp_code(self):
        """Get OTP code from user input"""
        print("\n📨 OTP code has been sent to your phone")
        print("💡 Check your Telegram app for the verification code")
        
        while True:
            try:
                code = input("🔢 Enter the OTP code: ").strip()
                if code and len(code) >= 5:
                    return code
                else:
                    print("❌ Invalid code. Please enter the 5-digit code from Telegram")
            except KeyboardInterrupt:
                print("\n🛑 Authentication cancelled")
                raise
            except Exception as e:
                print(f"❌ Error reading code: {e}")
    
    async def handle_2fa_if_needed(self):
        """Handle 2FA password if required"""
        try:
            # Check if 2FA is enabled
            if await self.telegram_client.is_user_authorized():
                return True
            
            print("\n🔐 Two-factor authentication required")
            print("💡 Enter your 2FA password (cloud password)")
            
            while True:
                try:
                    import getpass
                    password = getpass.getpass("🔑 Enter your 2FA password: ").strip()
                    if password:
                        await self.telegram_client.sign_in(password=password)
                        return True
                    else:
                        print("❌ Password cannot be empty")
                except KeyboardInterrupt:
                    print("\n🛑 Authentication cancelled")
                    raise
                except Exception as e:
                    print(f"❌ 2FA failed: {e}")
                    return False
        except Exception as e:
            print(f"❌ 2FA error: {e}")
            return False
    
    def convert_otc_asset_name(self, asset: str) -> str:
        """
        Convert Logic 5 Cycle asset names from USDBDT-OTCp format to USDBDT_otc format
        Input: USDBDT-OTCp, USDPKR-OTCp, EURJPY-OTC, etc.
        Output: USDBDT_otc, USDPKR_otc, EURJPY, etc.
        """
        if not asset:
            return asset
            
        asset = asset.strip()
        
        # If asset has -OTC or -OTCp suffix, remove it and decide format
        if asset.endswith('-OTC') or asset.endswith('-OTCp'):
            base_asset = asset.split('-')[0]  # Get USDBDT from USDBDT-OTCp
            
            # Major pairs that should use regular format (no _otc)
            MAJOR_PAIRS = {
                'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'USDCAD', 'AUDUSD',
                'EURJPY', 'EURGBP', 'GBPJPY', 'AUDJPY', 'NZDUSD'
            }
            
            if base_asset in MAJOR_PAIRS:
                return base_asset  # Return EURJPY (regular format)
            else:
                return f"{base_asset}_otc"  # Return USDBDT_otc (OTC format)
        else:
            # Asset without -OTC suffix, use as-is
            return asset

    def extract_signal_data(self, message_text, channel_name):
        """Extract signal data from message based on channel type"""
        if not message_text:
            return None
        
        # Logic 5 Cycle channel pattern (new format)
        if 'logic 5 cycle' in channel_name.lower():
            return self.extract_logic_5_cycle_signal(message_text)
        
        # Pocket Option Sign channel pattern (new format)
        if 'pocket option sign' in channel_name.lower():
            return self.extract_pocket_option_sign_signal(message_text)
        
        # Pocket Pro AI channel pattern (new format) - COMMENTED OUT
        # if 'pocket pro ai' in channel_name.lower():
        #     return self.extract_pocket_pro_ai_signal(message_text)
        
        # PO ADVANCE BOT channel pattern
        if 'po advance bot' in channel_name.lower():
            return self.extract_po_advance_signal(message_text)
        
        # LC Trader channel pattern
        if 'lc trader' in channel_name.lower():
            return self.extract_lc_trader_signal(message_text)
        
        # Trade x po channel pattern (new channel 7)
        if 'trade x po' in channel_name.lower():
            return self.extract_trade_x_po_signal(message_text)
        
        # James Martin VIP channel pattern (original)
        return self.extract_james_martin_signal(message_text)
    
    def extract_logic_5_cycle_signal(self, message_text):
        """Extract signal data from Logic 5 Cycle channel format"""
        if not message_text:
            return None
        
        # Skip result messages
        if any(word in message_text.lower() for word in ['profit', 'loss', '✅', '☑️']):
            return None
        
        # Must contain signal indicators
        if not ('📊' in message_text and ('🟢 CALL UP' in message_text or '🔴 PUT DOWN' in message_text)):
            return None
        
        try:
            # Extract asset - format: 📊 USDBDT-OTCp ⏰
            asset_match = re.search(r'📊\s+([A-Z]{6}-OTC[p]?)', message_text)
            if not asset_match:
                return None
            
            asset = asset_match.group(1)
            
            # Convert asset name from USDBDT-OTCp to USDBDT_otc format
            converted_asset = self.convert_otc_asset_name(asset)
            
            # Extract time - format: ⏰ 20:37
            time_match = re.search(r'⏰\s+(\d{1,2}:\d{2})', message_text)
            signal_time = time_match.group(1) if time_match else None
            
            # Extract direction
            direction = None
            if '🟢 CALL UP' in message_text or '⬆️' in message_text:
                direction = 'call'
            elif '🔴 PUT DOWN' in message_text or '⬇️' in message_text:
                direction = 'put'
            
            if converted_asset and direction and signal_time:
                return {
                    'asset': converted_asset,
                    'direction': direction,
                    'signal_time': signal_time
                }
            
            return None
            
        except Exception as e:
            print(f"   ⚠️ Logic 5 Cycle signal extraction error: {e}")
            return None
    
    def extract_pocket_pro_ai_signal(self, message_text):
        """Extract signal data from Pocket Pro AI channel format"""
        if not message_text:
            return None
        
        # Skip result messages
        if any(word in message_text.lower() for word in ['profit', 'loss', '✅', '☑️', 'win', 'result']):
            return None
        
        # Must contain signal indicators - similar to PO ADVANCE BOT format
        if not any(indicator in message_text.upper() for indicator in ['CALL', 'PUT', 'UP', 'DOWN', '⬆️', '⬇️', '🔼', '🔽']):
            return None
        
        try:
            # Multiple signal detection patterns for Pocket Pro AI
            
            # Pattern 1: POCKET PRO AI format (similar to PO ADVANCE BOT)
            if "POCKET PRO AI" in message_text:
                # Extract asset/pair - EXACT format as shown in message
                asset_match = re.search(r'💹\s*Pair\s*│\s*([^\s\n]+)', message_text)
                asset = asset_match.group(1).strip() if asset_match else None
                
                # Extract entry time - look for format: ⏰ Entry Time │ 17:03
                time_match = re.search(r'⏰\s*Entry Time\s*│\s*(\d{1,2}:\d{2})', message_text)
                signal_time = time_match.group(1) if time_match else None
                
                # Extract direction - look for PUT ➥ DOWN or CALL ➥ UP
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
            
            # Pattern 2: Simple format with asset and direction
            # Look for currency pairs (6 letters) followed by direction
            asset_patterns = [
                r'([A-Z]{6}(?:-OTC[p]?)?)\s*[-:]\s*(CALL|PUT)',  # EURUSD - CALL
                r'([A-Z]{6}(?:-OTC[p]?)?)\s*(CALL|PUT)',        # EURUSD CALL
                r'💰\s*([A-Z]{6}(?:-OTC[p]?)?)\s*(CALL|PUT)',   # 💰 EURUSD CALL
                r'📊\s*([A-Z]{6}(?:-OTC[p]?)?)\s*(CALL|PUT)',   # 📊 EURUSD CALL
            ]
            
            for pattern in asset_patterns:
                match = re.search(pattern, message_text, re.IGNORECASE)
                if match:
                    asset = match.group(1).upper()
                    direction = match.group(2).lower()
                    
                    # Extract time if available
                    time_patterns = [
                        r'(\d{1,2}:\d{2})',  # Any time format
                        r'⏰\s*(\d{1,2}:\d{2})',
                        r'Time:\s*(\d{1,2}:\d{2})',
                    ]
                    
                    signal_time = None
                    for time_pattern in time_patterns:
                        time_match = re.search(time_pattern, message_text)
                        if time_match:
                            signal_time = time_match.group(1)
                            break
                    
                    return {
                        'asset': asset,
                        'direction': direction,
                        'signal_time': signal_time or 'Not specified'
                    }
            
            # Pattern 3: Look for direction indicators with any asset
            if any(indicator in message_text.upper() for indicator in ['CALL', 'PUT', 'UP', 'DOWN', '⬆️', '⬇️', '🔼', '🔽']):
                # Try to find any currency pair
                asset_match = re.search(r'([A-Z]{6}(?:-OTC[p]?)?)', message_text)
                if asset_match:
                    asset = asset_match.group(1).upper()
                    
                    # Determine direction
                    direction = None
                    if any(word in message_text.upper() for word in ['CALL', 'UP', '⬆️', '🔼']):
                        direction = 'call'
                    elif any(word in message_text.upper() for word in ['PUT', 'DOWN', '⬇️', '🔽']):
                        direction = 'put'
                    
                    if direction:
                        # Extract time if available
                        time_match = re.search(r'(\d{1,2}:\d{2})', message_text)
                        signal_time = time_match.group(1) if time_match else 'Not specified'
                        
                        return {
                            'asset': asset,
                            'direction': direction,
                            'signal_time': signal_time
                        }
            
            return None
            
        except Exception as e:
            print(f"   ⚠️ Pocket Pro AI signal extraction error: {e}")
            return None
    
    def extract_po_advance_signal(self, message_text):
        """Extract signal data from PO ADVANCE BOT - Enhanced detection for multiple formats"""
        if not message_text:
            return None
        
        # Skip obvious non-signal messages
        skip_phrases = ['generating', 'please wait', 'loading', 'updating', 'maintenance']
        if any(phrase in message_text.lower() for phrase in skip_phrases):
            return None
        
        try:
            # Multiple signal detection patterns
            
            # Pattern 1: POCKET PRO AI format
            if "POCKET PRO AI" in message_text:
                # Extract asset/pair - EXACT format as shown in message
                asset_match = re.search(r'💹\s*Pair\s*│\s*([^\s\n]+)', message_text)
                asset = asset_match.group(1).strip() if asset_match else None
                
                # Extract entry time - look for format: ⏰ Entry Time │ 17:03
                time_match = re.search(r'⏰\s*Entry Time\s*│\s*(\d{1,2}:\d{2})', message_text)
                signal_time = time_match.group(1) if time_match else None
                
                # Extract direction - look for PUT ➥ DOWN or CALL ➥ UP
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
            
            # Pattern 2: Simple format with asset and direction
            # Look for currency pairs (6 letters) followed by direction
            asset_patterns = [
                r'([A-Z]{6}(?:_otc)?)\s*[-:]\s*(CALL|PUT)',  # EURUSD - CALL
                r'([A-Z]{6}(?:_otc)?)\s*(CALL|PUT)',        # EURUSD CALL
                r'💰\s*([A-Z]{6}(?:_otc)?)\s*(CALL|PUT)',   # 💰 EURUSD CALL
                r'📊\s*([A-Z]{6}(?:_otc)?)\s*(CALL|PUT)',   # 📊 EURUSD CALL
            ]
            
            for pattern in asset_patterns:
                match = re.search(pattern, message_text, re.IGNORECASE)
                if match:
                    asset = match.group(1).upper()
                    direction = match.group(2).lower()
                    
                    # Extract time if available
                    time_patterns = [
                        r'(\d{1,2}:\d{2})',  # Any time format
                        r'⏰\s*(\d{1,2}:\d{2})',
                        r'Time:\s*(\d{1,2}:\d{2})',
                    ]
                    
                    signal_time = None
                    for time_pattern in time_patterns:
                        time_match = re.search(time_pattern, message_text)
                        if time_match:
                            signal_time = time_match.group(1)
                            break
                    
                    return {
                        'asset': asset,
                        'direction': direction,
                        'signal_time': signal_time or 'Not specified'
                    }
            
            # Pattern 3: Look for direction indicators with any asset
            if any(indicator in message_text.upper() for indicator in ['CALL', 'PUT', 'UP', 'DOWN', '⬆️', '⬇️', '🔼', '🔽']):
                # Try to find any currency pair
                asset_match = re.search(r'([A-Z]{6}(?:_otc|_OTC)?)', message_text)
                if asset_match:
                    asset = asset_match.group(1).upper()
                    
                    # Determine direction
                    direction = None
                    if any(word in message_text.upper() for word in ['CALL', 'UP', '⬆️', '🔼']):
                        direction = 'call'
                    elif any(word in message_text.upper() for word in ['PUT', 'DOWN', '⬇️', '🔽']):
                        direction = 'put'
                    
                    if direction:
                        # Extract time if available
                        time_match = re.search(r'(\d{1,2}:\d{2})', message_text)
                        signal_time = time_match.group(1) if time_match else 'Not specified'
                        
                        return {
                            'asset': asset,
                            'direction': direction,
                            'signal_time': signal_time
                        }
            
            return None
            
        except Exception as e:
            print(f"   ⚠️ Signal extraction error: {e}")
            return None
    
    def extract_lc_trader_signal(self, message_text):
        """Extract signal data from LC Trader message format"""
        # Check for LC Trader signal pattern: "OPPORTUNITY FOUND"
        if "OPPORTUNITY FOUND" not in message_text:
            return None
        
        # Pattern: ASSET_otc—TIME: DIRECTION
        # Example: CHFJPY_otc—05:00: PUT 🔴
        signal_pattern = r'([A-Z]{6})_otc—(\d{2}:\d{2}):\s*(PUT|CALL)'
        
        match = re.search(signal_pattern, message_text, re.IGNORECASE)
        if not match:
            return None
        
        asset = match.group(1).upper() + "_otc"  # CHFJPY_otc
        signal_time = match.group(2)  # 05:00
        direction = match.group(3).lower()  # put or call
        
        return {
            'asset': asset,
            'direction': direction,
            'signal_time': signal_time
        }
    
    def extract_james_martin_signal(self, message_text):
        """Extract signal data from James Martin VIP channel format"""
        # Skip obvious non-signal messages
        skip_words = ['win', 'loss', '💔', '✅', 'register', 'code', 'bonus', 'join', 'channel', 'withdraw', 'verify', 'account']
        if any(skip_word in message_text.lower() for skip_word in skip_words):
            # But allow if it has VIP SIGNAL
            if 'VIP SIGNAL' not in message_text:
                return None
        
        # Must have VIP SIGNAL or signal indicators
        if not any(indicator in message_text for indicator in ['VIP SIGNAL', '💳', '🔥', '⌛', 'CALL', 'PUT']):
            return None
        
        # Extract Asset - use EXACT name from message without any modifications
        asset = None
        
        # Pattern to match asset names in various formats - capture EXACTLY as written
        asset_patterns = [
            r'\*\*([A-Z]{6}(?:-OTC[p]?)?)\*\*',     # **EURJPY** or **EURJPY-OTC** or **EURJPY-OTCp**
            r'💳\s*([A-Z]{6}(?:-OTC[p]?)?)',        # 💳 EURJPY or 💳 EURJPY-OTC
            r'📊\s*([A-Z]{6}(?:-OTC[p]?)?)',        # 📊 EURJPY or 📊 EURJPY-OTC
            r'([A-Z]{6}(?:-OTC[p]?)?)\s*-\s*(CALL|PUT)', # EURJPY - PUT or EURJPY-OTC - PUT
        ]
        
        # Find the first matching asset pattern
        for pattern in asset_patterns:
            asset_match = re.search(pattern, message_text, re.IGNORECASE)
            if asset_match:
                raw_asset = asset_match.group(1).upper()
                # Ensure the base asset is 6 characters (valid currency pair)
                base_asset = raw_asset.split('-')[0]  # Get part before -OTC
                if len(base_asset) == 6:
                    # Convert -OTC to _otc format for James Martin signals
                    if raw_asset.endswith('-OTC') or raw_asset.endswith('-OTCP'):
                        asset = base_asset + '_otc'  # Convert EURJPY-OTC to EURJPY_otc
                    else:
                        asset = raw_asset  # Use as-is if no -OTC suffix
                    break
        
        if not asset:
            return None
        
        # Extract time
        signal_time = None
        time_patterns = [
            r'PUT\s*🟥\s*-\s*(\d{1,2}:\d{2})',  # PUT 🟥 - 00:37
            r'CALL\s*🟩\s*-\s*(\d{1,2}:\d{2})', # CALL 🟩 - 00:37
            r'-\s*(\d{1,2}:\d{2})\s*•',         # - 21:32 •
            r'⌛\s*(\d{1,2}:\d{2}:\d{2})',      # ⌛ 12:25:00
            r'⌛\s*(\d{1,2}:\d{2})',           # ⌛ 12:25
            r'⏰\s*(\d{1,2}:\d{2})',           # ⏰ 12:25
            r'-\s*(\d{1,2}:\d{2})$',           # - 21:32 at end
            r'(\d{1,2}:\d{2})\s*•',            # 21:32 •
        ]
        
        for pattern in time_patterns:
            time_match = re.search(pattern, message_text)
            if time_match:
                signal_time = time_match.group(1)
                break
        
        # Extract direction
        direction = None
        if '🔽' in message_text or 'PUT' in message_text.upper() or 'DOWN' in message_text.upper() or '🟥' in message_text:
            direction = 'put'
        elif '🔼' in message_text or 'CALL' in message_text.upper() or 'UP' in message_text.upper() or '🟩' in message_text:
            direction = 'call'
        
        if not direction:
            return None
        
        return {
            'asset': asset,
            'direction': direction,
            'signal_time': signal_time
        }
    
    def extract_pocket_option_sign_signal(self, message_text):
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
    
    def extract_trade_x_po_signal(self, message_text):
        """Extract signal data from Trade x po channel format (new channel 7)"""
        if not message_text:
            return None
        
        # Skip result messages and non-signal content
        skip_words = ['win', 'loss', 'profit', '✅', '❌', '☑️', 'register', 'bonus', 'join', 'channel', 'withdraw', 'result update', 'report', 'accuracy']
        if any(word in message_text.lower() for word in skip_words):
            # But allow if it contains signal indicators
            if not any(indicator in message_text for indicator in ['CALL', 'PUT', '🔼', '🔽', '⬆️', '⬇️', 'BUY', 'SELL', 'Entry:']):
                return None
        
        try:
            # Pattern 1: Trade x po specific format
            # **🌟** **AUDUSD - OTC**  **⏳**** Expiry: 1 Minutes** **🔜**** Entry:** 15:37  🟥 **Direction: **SELL 📈
            # Also handles: **🌟** AUDUSD** - OTC**  (variation with different asterisks)
            if '**🌟**' in message_text and 'Entry:' in message_text and 'Direction:' in message_text:
                # Extract asset - handle multiple formats:
                # Format 1: **AUDUSD - OTC**
                # Format 2: AUDUSD** - OTC**
                asset_patterns = [
                    r'\*\*([A-Z]{6})\s*-\s*OTC\*\*',      # **AUDUSD - OTC**
                    r'([A-Z]{6})\*\*\s*-\s*OTC\*\*',      # AUDUSD** - OTC**
                ]
                
                asset = None
                for asset_pattern in asset_patterns:
                    asset_match = re.search(asset_pattern, message_text)
                    if asset_match:
                        base_asset = asset_match.group(1)
                        asset = f"{base_asset}_otc"  # Convert to AUDUSD_otc format
                        break
                
                if asset:
                    # Extract time - format: Entry:** 15:37
                    time_match = re.search(r'Entry:\*\*\s*(\d{1,2}:\d{2})', message_text)
                    signal_time = time_match.group(1) if time_match else None
                    
                    # Extract direction - format: **Direction: **SELL or **Direction: **BUY
                    direction = None
                    if 'Direction: **SELL' in message_text or '🟥' in message_text:
                        direction = 'put'
                    elif 'Direction: **BUY' in message_text or '🟩' in message_text:
                        direction = 'call'
                    
                    if direction and signal_time:
                        return {
                            'asset': asset,
                            'direction': direction,
                            'signal_time': signal_time
                        }
            
            # Pattern 2: Generic signal detection patterns for other formats
            # Since we don't know all possible formats, use flexible patterns
            
            # Look for currency pairs with direction
            asset_patterns = [
                r'([A-Z]{6}(?:_otc|_OTC|-OTC[p]?)?)\s*[-:]\s*(CALL|PUT)',  # EURUSD - CALL
                r'([A-Z]{6}(?:_otc|_OTC|-OTC[p]?)?)\s*(CALL|PUT)',        # EURUSD CALL
                r'💰\s*([A-Z]{6}(?:_otc|_OTC|-OTC[p]?)?)\s*(CALL|PUT)',   # 💰 EURUSD CALL
                r'📊\s*([A-Z]{6}(?:_otc|_OTC|-OTC[p]?)?)\s*(CALL|PUT)',   # 📊 EURUSD CALL
            ]
            
            for pattern in asset_patterns:
                match = re.search(pattern, message_text, re.IGNORECASE)
                if match:
                    asset = match.group(1).upper()
                    direction = match.group(2).lower()
                    
                    # Extract time if available
                    time_patterns = [
                        r'(\d{1,2}:\d{2}:\d{2})',  # HH:MM:SS format
                        r'(\d{1,2}:\d{2})',        # HH:MM format
                        r'⏰\s*(\d{1,2}:\d{2})',   # ⏰ HH:MM
                        r'Time:\s*(\d{1,2}:\d{2})', # Time: HH:MM
                    ]
                    
                    signal_time = None
                    for time_pattern in time_patterns:
                        time_match = re.search(time_pattern, message_text)
                        if time_match:
                            full_time = time_match.group(1)
                            # Convert to HH:MM format (remove seconds if present)
                            if len(full_time.split(':')) == 3:
                                signal_time = ':'.join(full_time.split(':')[:2])
                            else:
                                signal_time = full_time
                            break
                    
                    return {
                        'asset': asset,
                        'direction': direction,
                        'signal_time': signal_time or 'Not specified'
                    }
            
            # Pattern 3: Look for direction indicators with any asset
            if any(indicator in message_text.upper() for indicator in ['CALL', 'PUT', 'UP', 'DOWN', '⬆️', '⬇️', '🔼', '🔽']):
                # Try to find any currency pair
                asset_match = re.search(r'([A-Z]{6}(?:_otc|_OTC|-OTC[p]?)?)', message_text)
                if asset_match:
                    asset = asset_match.group(1).upper()
                    
                    # Determine direction
                    direction = None
                    if any(word in message_text.upper() for word in ['CALL', 'UP', '⬆️', '🔼']):
                        direction = 'call'
                    elif any(word in message_text.upper() for word in ['PUT', 'DOWN', '⬇️', '🔽']):
                        direction = 'put'
                    
                    if direction:
                        # Extract time if available
                        time_match = re.search(r'(\d{1,2}:\d{2})', message_text)
                        signal_time = time_match.group(1) if time_match else 'Not specified'
                        
                        return {
                            'asset': asset,
                            'direction': direction,
                            'signal_time': signal_time
                        }
            
            return None
            
        except Exception as e:
            print(f"   ⚠️ Trade x po signal extraction error: {e}")
            return None
    
    def save_to_csv(self, channel, message, signal_data=None):
        """Save message to channel-specific CSV file with current date column"""
        try:
            # Check for date change before saving
            self.check_date_change()
            
            # Get the CSV file for this channel
            csv_file = self.csv_files.get(channel['name'])
            if not csv_file:
                print(f"❌ No CSV file found for channel: {channel['name']}")
                return False
            
            with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Prepare row data with current date column
                current_datetime = datetime.now()
                date = self.current_date  # Use tracked current date
                timestamp = current_datetime.strftime('%Y-%m-%d %H:%M:%S')  # Full timestamp
                channel_name = channel['name']
                message_id = message.id
                message_text = message.text.replace('\n', ' ').replace('\r', ' ') if message.text else ''
                
                if signal_data:
                    is_signal = 'Yes'
                    asset = signal_data['asset']
                    direction = signal_data['direction']
                    signal_time = signal_data['signal_time'] or ''
                    
                    # Debug logging for signal data
                    print(f"   💾 Saving signal to {csv_file}: {signal_data['asset']} (EXACT) {signal_data['direction']} at {signal_data['signal_time']} [Date: {date}]")
                else:
                    is_signal = 'No'
                    asset = ''
                    direction = ''
                    signal_time = ''
                
                row = [date, timestamp, channel_name, message_id, message_text, 
                       is_signal, asset, direction, signal_time]
                
                writer.writerow(row)
                return True
                
        except Exception as e:
            print(f"         ❌ CSV save error: {e}")
            return False
    
    async def check_channel(self, channel):
        """Check one channel for new messages - ONLY from current date"""
        if not channel['entity']:
            return
        
        try:
            # Get latest messages (check more messages for better detection)
            messages = await self.telegram_client.get_messages(channel['entity'], limit=10)
            
            new_messages_found = False
            
            # Get current date for filtering
            current_date = datetime.now().strftime('%Y-%m-%d')
            
            for msg in messages:
                # Skip if we've already seen this message
                if channel['last_msg_id'] and msg.id <= channel['last_msg_id']:
                    continue
                
                # FILTER: Only process messages from TODAY
                if msg.date:
                    msg_date = msg.date.strftime('%Y-%m-%d')
                    if msg_date != current_date:
                        # Skip messages not from today
                        continue
                
                new_messages_found = True
                self.messages_processed += 1
                
                # Update last seen message ID
                if not channel['last_msg_id'] or msg.id > channel['last_msg_id']:
                    channel['last_msg_id'] = msg.id
                
                if msg.text:
                    # Show message in real-time format
                    time_str = datetime.now().strftime('%H:%M:%S')
                    message_preview = msg.text.replace('\n', ' ')[:150]
                    print(f"\n🔔 [{time_str}] NEW MESSAGE from {channel['name']}:")
                    print(f"   📝 {message_preview}")
                    
                    # Check if it's a signal with detailed analysis (pass channel name)
                    signal_data = self.extract_signal_data(msg.text, channel['name'])
                    
                    # Save to CSV
                    saved = self.save_to_csv(channel, msg, signal_data)
                    
                    if signal_data:
                        self.signals_detected += 1
                        # Show detailed signal info
                        save_status = "✅ SAVED TO CSV" if saved else "❌ SAVE FAILED"
                        print(f"   🎯 TRADING SIGNAL DETECTED:")
                        print(f"      💰 Asset: {signal_data['asset']}")
                        print(f"      📊 Direction: {signal_data['direction'].upper()}")
                        print(f"      ⏰ Time: {signal_data['signal_time'] or 'Not specified'}")
                        print(f"      💾 Status: {save_status}")
                        print(f"      📊 Session Signals: {self.signals_detected}")
                        print(f"   🚨 READY FOR TRADING!")
                    else:
                        # Check if it's a result message
                        if any(word in msg.text.lower() for word in ['win', 'result', '✅', 'confirmed', 'victory', 'gain']):
                            save_status = "📊 RESULT SAVED" if saved else "❌ SAVE FAILED"
                            print(f"   📊 RESULT MESSAGE: {save_status}")
                        else:
                            save_status = "📝 MESSAGE SAVED" if saved else "❌ SAVE FAILED"
                            print(f"   📝 Status: {save_status}")
                    
                    # Show which CSV file was used
                    csv_file = self.csv_files.get(channel['name'], 'Unknown')
                    print(f"   📄 CSV: {csv_file}")
                    print("-" * 60)
                else:
                    # Media message
                    saved = self.save_to_csv(channel, msg, None)
                    time_str = datetime.now().strftime('%H:%M:%S')
                    print(f"\n🔔 [{time_str}] NEW MEDIA MESSAGE from {channel['name']}")
                    save_status = "📷 MEDIA SAVED" if saved else "❌ SAVE FAILED"
                    print(f"   📷 Status: {save_status}")
                    csv_file = self.csv_files.get(channel['name'], 'Unknown')
                    print(f"   📄 CSV: {csv_file}")
                    print("-" * 60)
            
            # No need for individual channel status - handled in main loop
            
        except Exception as e:
            error_msg = str(e).lower()
            time_str = datetime.now().strftime('%H:%M:%S')
            
            # Handle specific database errors
            if 'readonly database' in error_msg or 'database is locked' in error_msg:
                print(f"🔄 [{time_str}] Database issue detected - recreating session...")
                # Try to recreate the session
                try:
                    await self.telegram_client.disconnect()
                    await asyncio.sleep(2)
                    
                    # Clean session files with improved error handling
                    import glob
                    session_patterns = ['monitor_session*.session*', 'signal_session*.session*']
                    session_files = []
                    
                    for pattern in session_patterns:
                        session_files.extend(glob.glob(pattern))
                    
                    for session_file in session_files:
                        if os.path.exists(session_file):
                            try:
                                # First try to disconnect any existing connections
                                if hasattr(self, 'telegram_client') and self.telegram_client:
                                    try:
                                        await self.telegram_client.disconnect()
                                    except:
                                        pass
                                
                                # Force close and remove with retries
                                import time
                                for attempt in range(3):
                                    try:
                                        os.remove(session_file)
                                        print(f"🧹 Cleaned: {session_file}")
                                        break
                                    except PermissionError:
                                        if attempt < 2:
                                            print(f"⏳ Retrying {session_file} cleanup... (attempt {attempt + 1}/3)")
                                            time.sleep(1)
                                        else:
                                            print(f"⚠️ Could not remove {session_file}: File locked by another process")
                                    except Exception as e:
                                        print(f"⚠️ Cleanup error for {session_file}: {e}")
                                        break
                            except Exception as cleanup_error:
                                print(f"⚠️ Session cleanup failed for {session_file}: {cleanup_error}")
                    
                    # Create new client with unique session name
                    import time
                    new_session_name = f'monitor_session_{int(time.time())}'
                    self.telegram_client = TelegramClient(new_session_name, self.api_id, self.api_hash)
                    await self.authenticate_new_session()
                    
                    # Reconnect to channels
                    await self.reconnect_channels()
                    print(f"✅ [{time_str}] Session recreated successfully")
                    
                except Exception as reconnect_error:
                    print(f"❌ [{time_str}] Failed to recreate session: {reconnect_error}")
            else:
                print(f"❌ [{time_str}] Error checking {channel['name']}: {e}")
    
    async def reconnect_channels(self):
        """Reconnect to all channels after session recreation"""
        print("📡 Reconnecting to channels...")
        for channel in self.channels:
            try:
                # Handle different channel ID formats
                if isinstance(channel['id'], str) and ('joinchat' in channel['id'] or '+' in channel['id']):
                    # Handle invite link
                    if '+' in channel['id']:
                        invite_hash = channel['id'].split('+')[-1]
                    else:
                        invite_hash = channel['id'].split('/')[-1]
                    
                    # Join channel using invite link
                    try:
                        result = await self.telegram_client.join_chat(invite_hash)
                        entity = result.chats[0]
                    except Exception as join_error:
                        print(f"⚠️ Could not join channel: {join_error}")
                        # Try to get entity directly
                        entity = await self.telegram_client.get_entity(channel['id'])
                elif isinstance(channel['id'], str) and channel['id'] == 'PO ADVANCE BOT':
                    # Handle PO ADVANCE BOT by searching in dialogs
                    print(f"🔍 Searching for PO ADVANCE BOT in dialogs...")
                    entity = None
                    async for dialog in self.telegram_client.iter_dialogs():
                        dialog_title = getattr(dialog.entity, 'title', '')
                        # Search for various possible titles
                        if (dialog_title == 'PO ADVANCE BOT' or 
                            'POCKET PRO AI' in dialog_title or
                            'PO ADVANCE' in dialog_title.upper() or
                            'POCKET OPTION' in dialog_title.upper()):
                            entity = dialog.entity
                            print(f"✅ Found PO ADVANCE BOT in dialogs: '{dialog_title}' (ID: {entity.id})")
                            break
                    
                    if not entity:
                        print(f"❌ PO ADVANCE BOT not found in dialogs")
                        print(f"💡 Please join the channel manually first, then restart the monitor")
                        continue
                else:
                    # Handle direct channel ID (numeric)
                    try:
                        entity = await self.telegram_client.get_entity(channel['id'])
                    except Exception as direct_error:
                        print(f"⚠️ Direct ID failed for {channel['name']}: {direct_error}")
                        continue
                
                channel['entity'] = entity
                
                # Get the latest message ID to start from
                messages = await self.telegram_client.get_messages(entity, limit=1)
                if messages:
                    channel['last_msg_id'] = messages[0].id
                
                channel_title = getattr(entity, 'title', channel['name'])
                print(f"✅ {channel['name']}: Reconnected to '{channel_title}'")
                
            except Exception as e:
                print(f"❌ {channel['name']}: Failed to reconnect - {e}")
    
    async def start_monitoring(self):
        """Start real-time signal monitoring - ONLY TODAY'S MESSAGES"""
        print("🚀 REAL-TIME SIGNAL MONITOR STARTING...")
        print(f"📄 CSV Files: Separate file for each channel with date column")
        for channel_name, csv_file in self.csv_files.items():
            print(f"   📊 {channel_name}: {csv_file}")
        print("📡 Channels:")
        for channel in self.channels:
            if isinstance(channel['id'], str):
                print(f"   📺 {channel['name']}: {channel['id']}")
            else:
                print(f"   📺 {channel['name']}: ID {channel['id']}")
        print("⚡ Monitoring: ALL channels every 2 seconds (parallel)")
        print("🎯 Detection: Trading signals + Results")
        print("📊 Format: [time] NEW MESSAGE details")
        print("🚀 Real-time: Instant notifications for new signals")
        print("📡 Method: Parallel channel checking for faster detection")
        print("🚨 Alerts: Real-time signal notifications")
        print(f"📅 Current Date: {self.current_date}")
        print(f"🔍 Filter: ONLY messages from TODAY ({self.current_date}) will be saved")
        print(f"🗑️ Auto-cleanup: When date changes, ALL old data is deleted")
        print("-" * 60)
        
        # Initialize with authentication handling
        try:
            if not await self.initialize():
                print("❌ Failed to initialize - exiting")
                return
        except KeyboardInterrupt:
            print("\n🛑 Setup cancelled by user")
            return
        except Exception as e:
            print(f"❌ Setup failed: {e}")
            return
        
        print("✅ MONITORING ACTIVE - Watching for signals...")
        print("🔔 New messages will appear below:")
        print("=" * 60)
        
        self.running = True
        
        try:
            while self.running:
                # Check for date change at the beginning of each loop
                self.check_date_change()
                
                # Check ALL channels in parallel every 2 seconds
                check_tasks = []
                for channel in self.channels:
                    if channel['entity']:  # Only check connected channels
                        task = asyncio.create_task(self.check_channel(channel))
                        check_tasks.append(task)
                
                # Wait for all channel checks to complete
                if check_tasks:
                    results = await asyncio.gather(*check_tasks, return_exceptions=True)
                    
                    # Check if any new messages were found
                    new_messages_found = any(not isinstance(r, Exception) for r in results)
                    
                    # Show status only if no new messages (to avoid spam)
                    if not new_messages_found:
                        current_time = datetime.now()
                        if self.last_status_time is None or (current_time - self.last_status_time).seconds >= 10:
                            time_str = current_time.strftime('%H:%M:%S')
                            active_channels = len([c for c in self.channels if c['entity']])
                            print(f"🔍 [{time_str}] Monitoring {active_channels} channels - No new messages")
                            self.last_status_time = current_time
                
                # Wait 2 seconds before next check cycle
                await asyncio.sleep(2)
                
        except KeyboardInterrupt:
            print("\n🛑 MONITOR STOPPED BY USER")
            
            # Show session summary
            session_duration = datetime.now() - self.session_start
            duration_minutes = int(session_duration.total_seconds() / 60)
            duration_seconds = int(session_duration.total_seconds() % 60)
            
            print("\n📊 SESSION SUMMARY:")
            print(f"   ⏰ Duration: {duration_minutes}m {duration_seconds}s")
            print(f"   📨 Messages Processed: {self.messages_processed}")
            print(f"   🎯 Signals Detected: {self.signals_detected}")
            print(f"   � Final Date: {self.current_date}")
            print(f"   �📄 CSV Files:")
            for channel_name, csv_file in self.csv_files.items():
                print(f"      📊 {channel_name}: {csv_file}")
            print("📊 Session completed successfully")
        except Exception as e:
            print(f"\n❌ Monitor error: {e}")
            print("🔄 Restarting in 5 seconds...")
            await asyncio.sleep(5)
        finally:
            self.running = False
            if self.telegram_client:
                try:
                    await self.telegram_client.disconnect()
                    print("🔌 Disconnected from Telegram")
                except:
                    pass

async def main():
    print("🚀 SIMPLE MONITOR STARTING...")
    print("=" * 50)
    print("🧹 Auto-cleanup: All previous sessions will be cleaned")
    print("🔄 Fresh start: New session will be created")
    print("📡 Multi-channel: Monitoring all configured channels")
    print("=" * 50)
    
    monitor = SimpleMonitor()
    await monitor.start_monitoring()

if __name__ == "__main__":
    asyncio.run(main())
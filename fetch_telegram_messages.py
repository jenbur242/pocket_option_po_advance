#!/usr/bin/env python3
"""
Fetch Last 10 Messages from Telegram Channel
Channel ID: -3254300055 (from URL: https://web.telegram.org/k/#-3254300055)
"""
import asyncio
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from telethon import TelegramClient

# Load environment variables
load_dotenv()

# Disable telethon logging
logging.basicConfig(level=logging.CRITICAL)

class TelegramMessageFetcher:
    def __init__(self):
        # Telegram config
        self.api_id = os.getenv('TELEGRAM_API_ID')
        self.api_hash = os.getenv('TELEGRAM_API_HASH')
        self.phone = os.getenv('TELEGRAM_PHONE')
        
        # Target channel ID from URL (corrected)
        self.channel_id = 3254300055  # Positive ID for the channel
        
        # Initialize client
        self.telegram_client = None
    
    async def initialize(self):
        """Initialize Telegram client"""
        try:
            print("🔌 Initializing Telegram connection...")
            
            # Create Telegram client (reuse existing session if available)
            self.telegram_client = TelegramClient('fetch_session', self.api_id, self.api_hash)
            
            # Check if session exists
            session_exists = os.path.exists('fetch_session.session')
            
            if session_exists:
                print("📱 Using existing session...")
                try:
                    await self.telegram_client.start(phone=self.phone)
                    
                    # Test if session is still valid
                    me = await self.telegram_client.get_me()
                    print(f"✅ Session valid - Logged in as: {me.first_name} ({me.phone})")
                    
                except Exception as session_error:
                    print(f"⚠️ Existing session invalid: {session_error}")
                    print("🔄 Creating new session...")
                    
                    # Clean invalid session files
                    session_files = ['fetch_session.session', 'fetch_session.session-journal', 'fetch_session.session-wal']
                    for session_file in session_files:
                        if os.path.exists(session_file):
                            try:
                                os.remove(session_file)
                                print(f"🧹 Cleaned: {session_file}")
                            except Exception as e:
                                print(f"⚠️ Could not remove {session_file}: {e}")
                    
                    # Recreate client and authenticate
                    self.telegram_client = TelegramClient('fetch_session', self.api_id, self.api_hash)
                    await self.authenticate_new_session()
                    
                    # Test new connection
                    me = await self.telegram_client.get_me()
                    print(f"✅ New session created - Logged in as: {me.first_name} ({me.phone})")
            else:
                print("📱 No existing session found - Creating new session...")
                await self.authenticate_new_session()
                
                # Test connection
                me = await self.telegram_client.get_me()
                print(f"✅ New session created - Logged in as: {me.first_name} ({me.phone})")
            
            return True
            
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False
    
    async def authenticate_new_session(self):
        """Handle new session authentication with OTP"""
        try:
            print(f"📱 Sending OTP to {self.phone}...")
            
            # Start authentication process
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
    
    async def fetch_channel_info(self):
        """Get channel information"""
        try:
            print(f"📡 Connecting to channel ID: {self.channel_id}")
            
            # Try different methods to get the channel
            entity = None
            
            # Method 1: Try direct ID
            try:
                entity = await self.telegram_client.get_entity(self.channel_id)
            except Exception as e1:
                print(f"⚠️ Direct ID failed: {e1}")
                
                # Method 2: Try as PeerChannel
                try:
                    from telethon.tl.types import PeerChannel
                    peer = PeerChannel(abs(self.channel_id))
                    entity = await self.telegram_client.get_entity(peer)
                except Exception as e2:
                    print(f"⚠️ PeerChannel failed: {e2}")
                    
                    # Method 3: Try to find in dialogs
                    try:
                        print("🔍 Searching in dialogs...")
                        async for dialog in self.telegram_client.iter_dialogs():
                            if dialog.entity.id == self.channel_id or dialog.entity.id == abs(self.channel_id):
                                entity = dialog.entity
                                print(f"✅ Found in dialogs: {dialog.title}")
                                break
                        
                        if not entity:
                            print("❌ Channel not found in dialogs")
                            print("💡 Available channels:")
                            count = 0
                            async for dialog in self.telegram_client.iter_dialogs():
                                if hasattr(dialog.entity, 'broadcast') or 'channel' in str(type(dialog.entity)).lower():
                                    print(f"   📺 {dialog.title} (ID: {dialog.entity.id})")
                                    count += 1
                                    if count >= 10:  # Limit to first 10
                                        break
                            return None
                            
                    except Exception as e3:
                        print(f"⚠️ Dialog search failed: {e3}")
                        return None
            
            if entity:
                print(f"✅ Channel found:")
                print(f"   📛 Title: {getattr(entity, 'title', 'Unknown')}")
                print(f"   👥 Type: {'Channel' if hasattr(entity, 'broadcast') and entity.broadcast else 'Group'}")
                print(f"   🆔 ID: {entity.id}")
                if hasattr(entity, 'username') and entity.username:
                    print(f"   🔗 Username: @{entity.username}")
                if hasattr(entity, 'participants_count') and entity.participants_count:
                    print(f"   👥 Members: {entity.participants_count:,}")
            
            return entity
            
        except Exception as e:
            print(f"❌ Error getting channel info: {e}")
            return None
    
    async def fetch_last_messages(self, limit=10):
        """Fetch last N messages from the channel"""
        try:
            # Get channel entity
            entity = await self.fetch_channel_info()
            if not entity:
                return []
            
            print(f"\n📥 Fetching last {limit} messages...")
            print("=" * 80)
            
            # Get messages
            messages = await self.telegram_client.get_messages(entity, limit=limit)
            
            if not messages:
                print("📭 No messages found")
                return []
            
            print(f"✅ Found {len(messages)} messages:")
            print("-" * 80)
            
            for i, msg in enumerate(messages, 1):
                # Message header
                msg_time = msg.date.strftime('%Y-%m-%d %H:%M:%S') if msg.date else 'Unknown time'
                print(f"\n📨 MESSAGE {i} (ID: {msg.id})")
                print(f"   ⏰ Time: {msg_time}")
                print(f"   👤 From: {msg.sender_id or 'Channel'}")
                
                # Message content
                if msg.text:
                    # Clean text for display
                    text = msg.text.replace('\n', ' ').strip()
                    if len(text) > 200:
                        text = text[:200] + "..."
                    print(f"   📝 Text: {text}")
                    
                    # Check if it looks like a trading signal
                    if self.is_trading_signal(msg.text):
                        signal_data = self.extract_signal_data(msg.text)
                        if signal_data:
                            print(f"   🎯 TRADING SIGNAL DETECTED:")
                            print(f"      💰 Asset: {signal_data.get('asset', 'Unknown')}")
                            print(f"      📊 Direction: {signal_data.get('direction', 'Unknown').upper()}")
                            print(f"      ⏰ Time: {signal_data.get('signal_time', 'Not specified')}")
                        else:
                            print(f"   🎯 SIGNAL-LIKE MESSAGE (parsing failed)")
                    elif any(word in msg.text.lower() for word in ['win', 'loss', 'result', '✅', '❌']):
                        print(f"   📊 RESULT MESSAGE")
                    elif any(word in msg.text.lower() for word in ['register', 'bonus', 'join', 'click']):
                        print(f"   📢 PROMOTIONAL MESSAGE")
                    else:
                        print(f"   📝 REGULAR MESSAGE")
                        
                elif msg.media:
                    print(f"   📷 Media message (photo/video/document)")
                else:
                    print(f"   📝 Empty message")
                
                # Show full text for signals
                if msg.text and self.is_trading_signal(msg.text):
                    print(f"   📄 FULL TEXT:")
                    for line in msg.text.split('\n'):
                        if line.strip():
                            print(f"      {line.strip()}")
                
                print("-" * 80)
            
            return messages
            
        except Exception as e:
            print(f"❌ Error fetching messages: {e}")
            return []
    
    def is_trading_signal(self, text):
        """Check if message looks like a trading signal"""
        if not text:
            return False
        
        signal_indicators = [
            'VIP SIGNAL', 'SIGNAL', 'CALL', 'PUT', 'OPPORTUNITY FOUND',
            '🚥', '💳', '🔥', '⌛', '🟩', '🟥'
        ]
        
        return any(indicator in text.upper() for indicator in signal_indicators)
    
    def extract_signal_data(self, message_text):
        """Extract basic signal data from message"""
        if not message_text:
            return None
        
        try:
            import re
            
            # Extract asset
            asset = None
            asset_patterns = [
                r'\*\*([A-Z]{6}(?:-OTC[p]?)?)\*\*',     # **EURJPY** or **EURJPY-OTC**
                r'([A-Z]{6}(?:-OTC[p]?)?)\s*-\s*(CALL|PUT)', # EURJPY - PUT
                r'([A-Z]{6})_otc—',  # For LC Trader format
            ]
            
            for pattern in asset_patterns:
                match = re.search(pattern, message_text, re.IGNORECASE)
                if match:
                    asset = match.group(1).upper()
                    break
            
            # Extract direction
            direction = None
            if '🔽' in message_text or 'PUT' in message_text.upper() or '🟥' in message_text:
                direction = 'put'
            elif '🔼' in message_text or 'CALL' in message_text.upper() or '🟩' in message_text:
                direction = 'call'
            
            # Extract time
            signal_time = None
            time_patterns = [
                r'PUT\s*🟥\s*-\s*(\d{1,2}:\d{2})',  # PUT 🟥 - 00:37
                r'CALL\s*🟩\s*-\s*(\d{1,2}:\d{2})', # CALL 🟩 - 00:37
                r'-\s*(\d{1,2}:\d{2})\s*•',         # - 21:32 •
                r'(\d{1,2}:\d{2}):\s*(PUT|CALL)',   # 05:00: PUT
            ]
            
            for pattern in time_patterns:
                match = re.search(pattern, message_text)
                if match:
                    signal_time = match.group(1)
                    break
            
            if asset and direction:
                return {
                    'asset': asset,
                    'direction': direction,
                    'signal_time': signal_time
                }
            
            return None
            
        except Exception as e:
            print(f"⚠️ Signal extraction error: {e}")
            return None
    
    async def run(self):
        """Main execution function"""
        try:
            print("🚀 TELEGRAM MESSAGE FETCHER")
            print(f"📡 Target Channel ID: {self.channel_id}")
            print(f"🔗 URL: https://web.telegram.org/k/#{self.channel_id}")
            print("=" * 80)
            
            # Initialize connection
            if not await self.initialize():
                print("❌ Failed to initialize - exiting")
                return
            
            # Fetch messages
            messages = await self.fetch_last_messages(10)
            
            if messages:
                print(f"\n✅ Successfully fetched {len(messages)} messages")
                
                # Count signal messages
                signal_count = sum(1 for msg in messages if msg.text and self.is_trading_signal(msg.text))
                print(f"🎯 Trading signals found: {signal_count}")
                print(f"📝 Regular messages: {len(messages) - signal_count}")
            else:
                print("❌ No messages retrieved")
            
        except KeyboardInterrupt:
            print("\n🛑 Fetch cancelled by user")
        except Exception as e:
            print(f"❌ Fetch error: {e}")
        finally:
            if self.telegram_client:
                try:
                    await self.telegram_client.disconnect()
                    print("\n🔌 Disconnected from Telegram")
                except:
                    pass

async def main():
    fetcher = TelegramMessageFetcher()
    await fetcher.run()

if __name__ == "__main__":
    asyncio.run(main())
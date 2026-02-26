#!/usr/bin/env python3
"""
Test script to fetch missing signals from Telegram channel
This will check if the 12:04 GBPUSD_otc signal exists in the channel
"""
import asyncio
import os
import re
from datetime import datetime
from dotenv import load_dotenv
from telethon import TelegramClient

# Load environment variables
load_dotenv()

async def test_fetch_messages():
    """Fetch all messages from today and check for 12:04 signal"""
    
    # Telegram config
    api_id = os.getenv('TELEGRAM_API_ID')
    api_hash = os.getenv('TELEGRAM_API_HASH')
    phone = os.getenv('TELEGRAM_PHONE')
    
    # Channel invite link
    channel_link = 'https://t.me/+teILb87erlthODll'  # PO ADVANCE BOT
    
    print("🔍 TESTING MESSAGE FETCH FROM TELEGRAM")
    print("=" * 60)
    print(f"📅 Target Date: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"🎯 Looking for: 12:04 GBPUSD_otc PUT signal")
    print("=" * 60)
    
    # Create client
    client = TelegramClient('test_fetch_session', api_id, api_hash)
    
    try:
        await client.start(phone=phone)
        print("✅ Connected to Telegram")
        
        # Get channel entity
        print(f"📡 Connecting to channel...")
        invite_hash = channel_link.split('+')[-1]
        
        try:
            # Try to get entity directly first
            entity = await client.get_entity(channel_link)
        except:
            # If that fails, try joining
            result = await client.join_chat(invite_hash)
            entity = result.chats[0]
        
        print(f"✅ Connected to: {entity.title}")
        
        # Fetch ALL messages
        print(f"\n📥 Fetching all messages from channel...")
        messages = await client.get_messages(entity, limit=None)
        
        print(f"✅ Fetched {len(messages)} total messages")
        
        # Filter to today only
        current_date = datetime.now().strftime('%Y-%m-%d')
        today_messages = []
        
        for msg in messages:
            if msg.date:
                msg_date = msg.date.strftime('%Y-%m-%d')
                if msg_date == current_date:
                    today_messages.append(msg)
        
        print(f"✅ Found {len(today_messages)} messages from today ({current_date})")
        
        # Show ALL messages from today
        print(f"\n📋 ALL MESSAGES FROM TODAY:")
        print("=" * 60)
        
        for i, msg in enumerate(reversed(today_messages), 1):  # Reverse to show oldest first
            if msg.text:
                msg_time = msg.date.strftime('%H:%M:%S')
                print(f"\n{i}. Message ID: {msg.id} | Time: {msg_time}")
                print(f"   {msg.text[:250]}")
                
                # Highlight if it contains signal keywords
                if any(word in msg.text.upper() for word in ['CALL', 'PUT', 'ENTRY TIME', 'PAIR']):
                    print(f"   🎯 POTENTIAL SIGNAL")
                if 'GBPUSD' in msg.text.upper():
                    print(f"   💰 CONTAINS GBPUSD")
                if '12:04' in msg.text:
                    print(f"   ⏰ CONTAINS 12:04")
                
                print("-" * 60)
            else:
                msg_time = msg.date.strftime('%H:%M:%S')
                print(f"\n{i}. Message ID: {msg.id} | Time: {msg_time}")
                print(f"   📷 MEDIA MESSAGE (no text)")
                print("-" * 60)
        
        # Look for 12:04 signal
        print(f"\n🔍 SEARCHING FOR 12:04 SIGNAL...")
        print("=" * 60)
        
        found_1204_signal = False
        messages_around_1204 = []
        gbpusd_messages = []
        
        for msg in today_messages:
            if msg.text:
                msg_time = msg.date.strftime('%H:%M')
                
                # Check if message is around 11:58-12:10 timeframe (wider range)
                if msg_time >= '11:58' and msg_time <= '12:10':
                    messages_around_1204.append({
                        'id': msg.id,
                        'time': msg.date.strftime('%H:%M:%S'),
                        'text': msg.text[:200]
                    })
                
                # Also collect any GBPUSD mentions
                if 'GBPUSD' in msg.text.upper():
                    gbpusd_messages.append({
                        'id': msg.id,
                        'time': msg.date.strftime('%H:%M:%S'),
                        'text': msg.text[:300]
                    })
                    
                    # Check if this is the 12:04 signal
                    if '12:04' in msg.text and 'GBPUSD' in msg.text.upper():
                        found_1204_signal = True
                        print(f"✅ FOUND 12:04 SIGNAL!")
                        print(f"   Message ID: {msg.id}")
                        print(f"   Posted at: {msg.date.strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"   Content preview:")
                        print(f"   {msg.text[:300]}")
                        print()
                        
                        # Extract signal data
                        asset_match = re.search(r'💹\s*Pair\s*│\s*([^\s\n]+)', msg.text)
                        time_match = re.search(r'⏰\s*Entry Time\s*│\s*(\d{1,2}:\d{2})', msg.text)
                        
                        if asset_match and time_match:
                            print(f"   📊 Parsed Signal:")
                            print(f"      Asset: {asset_match.group(1)}")
                            print(f"      Entry Time: {time_match.group(1)}")
                            
                            if 'PUT ➥ DOWN' in msg.text or '⬇️' in msg.text:
                                print(f"      Direction: PUT")
                            elif 'CALL ➥ UP' in msg.text or '⬆️' in msg.text:
                                print(f"      Direction: CALL")
        
        if not found_1204_signal:
            print(f"❌ 12:04 GBPUSD_otc signal NOT FOUND in channel")
            
            print(f"\n📋 All GBPUSD mentions today:")
            print("=" * 60)
            if gbpusd_messages:
                for i, msg_info in enumerate(gbpusd_messages, 1):
                    print(f"\n{i}. Message ID: {msg_info['id']}")
                    print(f"   Time: {msg_info['time']}")
                    print(f"   Text: {msg_info['text']}")
                    print("-" * 60)
            else:
                print("   No GBPUSD messages found today")
            
            print(f"\n📋 Messages found between 11:58-12:10:")
            print("=" * 60)
            
            if messages_around_1204:
                for i, msg_info in enumerate(messages_around_1204, 1):
                    print(f"\n{i}. Message ID: {msg_info['id']}")
                    print(f"   Time: {msg_info['time']}")
                    print(f"   Text: {msg_info['text']}")
                    print("-" * 60)
            else:
                print("   No messages found in this timeframe")
        
        print("\n" + "=" * 60)
        print("✅ TEST COMPLETED")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await client.disconnect()
        print("👋 Disconnected from Telegram")

if __name__ == '__main__':
    asyncio.run(test_fetch_messages())

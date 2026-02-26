#!/usr/bin/env python3
"""
Test the fixed scraper to verify it captures all messages including the 12:04 signal
"""
import asyncio
import sys

# Import the SimpleMonitor class
from simple_monitor import SimpleMonitor

async def test_scraper():
    """Test the scraper with the fix"""
    print("🧪 TESTING FIXED SCRAPER")
    print("=" * 60)
    print("This will:")
    print("1. Connect to PO ADVANCE BOT channel")
    print("2. Fetch ALL messages from today")
    print("3. Save them to CSV")
    print("4. Verify the 12:04 GBPUSD_otc signal is captured")
    print("=" * 60)
    
    monitor = SimpleMonitor()
    
    try:
        # Initialize
        print("\n📡 Initializing...")
        await monitor.initialize()
        
        # Fetch messages for each channel
        for channel in monitor.channels:
            if channel['entity']:
                print(f"\n📥 Fetching messages from {channel['name']}...")
                await monitor.fetch_last_message_pattern(channel)
        
        print("\n✅ TEST COMPLETED")
        print("=" * 60)
        print("📄 Check the CSV file: pocketoption_po_advance_bot.csv")
        print("🔍 Look for message ID 3679 with GBPUSD_otc CALL at 12:04")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if monitor.telegram_client:
            await monitor.telegram_client.disconnect()
            print("👋 Disconnected")

if __name__ == '__main__':
    asyncio.run(test_scraper())

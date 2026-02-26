#!/usr/bin/env python3
"""
Test script to check if payout data is being received from PocketOption API
"""
import os
import asyncio
from dotenv import load_dotenv
from pocketoptionapi_async import AsyncPocketOptionClient

# Load environment variables
load_dotenv()

async def test_payout_data():
    """Test if payout data is received"""
    ssid = os.getenv('SSID')
    
    if not ssid:
        print("❌ No SSID found in .env file")
        return
    
    print("🔌 Connecting to PocketOption...")
    print(f"🔑 SSID: {ssid[:50]}...")
    
    # Track payout updates
    payout_count = 0
    payout_data = {}
    
    def on_json_data(data):
        """Handle JSON data messages that contain asset information"""
        nonlocal payout_count, payout_data
        
        try:
            # Check if this is asset data (list of lists with asset info)
            if isinstance(data, list) and len(data) > 0:
                for asset_info in data:
                    if isinstance(asset_info, list) and len(asset_info) > 5:
                        # Asset data format: [id, symbol, name, type, ?, payout, ...]
                        # Index 5 is the payout percentage
                        asset_id = asset_info[0]
                        asset_symbol = asset_info[1]
                        asset_name = asset_info[2]
                        asset_type = asset_info[3]
                        payout = asset_info[5]
                        
                        # Store payout data
                        payout_data[asset_symbol] = payout
                        payout_count += 1
                        
                        # Print first 20 updates
                        if payout_count <= 20:
                            print(f"💹 Payout #{payout_count}: {asset_symbol} = {payout}%")
        except Exception as e:
            pass  # Ignore parsing errors for non-asset messages
    
    try:
        # Create client with logging enabled
        client = AsyncPocketOptionClient(
            ssid=ssid,
            is_demo=True,
            persistent_connection=False,
            auto_reconnect=False,
            enable_logging=False  # Disable logging for cleaner output
        )
        
        # Register JSON data handler to capture asset information
        client._websocket.add_event_handler("json_data", on_json_data)
        
        # Connect
        print("⏳ Connecting...")
        await asyncio.wait_for(client.connect(), timeout=15.0)
        
        # Get balance to confirm connection
        balance = await asyncio.wait_for(client.get_balance(), timeout=10.0)
        print(f"✅ Connected! DEMO Account")
        print(f"💰 Balance: ${balance.balance:.2f}")
        
        # Wait for payout data
        print(f"\n⏳ Waiting 3 seconds for payout data...")
        await asyncio.sleep(3.0)
        
        # Show results
        print(f"\n📊 PAYOUT DATA SUMMARY:")
        print(f"   Total payout updates received: {payout_count}")
        print(f"   Unique assets with payout data: {len(payout_data)}")
        
        if payout_data:
            print(f"\n💹 Sample payout data (first 30 assets):")
            for i, (asset, payout) in enumerate(sorted(payout_data.items())[:30]):
                print(f"   {i+1}. {asset}: {payout}%")
            
            if len(payout_data) > 30:
                print(f"   ... and {len(payout_data) - 30} more assets")
            
            # Test specific assets from CSV
            print(f"\n🔍 Testing specific assets:")
            test_assets = ['EURUSD_otc', 'EURUSD', 'GBPUSD_otc', 'GBPUSD', 'USDJPY', 'USDEGP_otc', 'USDEGP']
            for asset in test_assets:
                # Try different variations
                variations = [
                    asset,
                    asset.upper(),
                    asset.upper().replace('_OTC', ''),
                    asset.lower(),
                    asset.replace('_otc', ''),
                    f"#{asset}",
                    f"#{asset.upper()}",
                ]
                
                found = False
                for var in variations:
                    if var in payout_data:
                        print(f"   ✅ {asset} found as '{var}': {payout_data[var]}%")
                        found = True
                        break
                
                if not found:
                    print(f"   ❌ {asset} not found in payout data")
            
            # Search for assets containing "USDEGP"
            print(f"\n🔍 Searching for assets containing 'USDEGP':")
            matching_assets = [k for k in payout_data.keys() if 'USDEGP' in k.upper()]
            if matching_assets:
                for asset in matching_assets:
                    print(f"   Found: {asset} = {payout_data[asset]}%")
            else:
                print(f"   No assets found containing 'USDEGP'")
        else:
            print(f"\n❌ No payout data received!")
            print(f"   This could mean:")
            print(f"   1. Payout messages are not being sent by the server")
            print(f"   2. The message handler is not working correctly")
            print(f"   3. The connection is not fully established")
        
        # Disconnect
        await client.disconnect()
        print(f"\n🔌 Disconnected")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_payout_data())

#!/usr/bin/env python3
"""
Test script to verify SSID format works with pocketoptionapi_async
"""

import asyncio
import sys
import os
import json

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pocketoptionapi_async.client import AsyncPocketOptionClient

async def test_ssid_connection():
    """Test SSID connection with proper format validation"""
    
    # Your complete SSID to test
    test_ssid = r'42["auth",{"session":"a:4:{s:10:\"session_id\";s:32:\"bd9508d693a16b8d4c8eb403c4e8b36b\";s:10:\"ip_address\";s:14:\"172.86.107.247\";s:10:\"user_agent\";s:111:\"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36\";s:13:\"last_activity\";i:1770133418;}4e4efa81293f4504f4a787696793527e","isDemo":0,"uid":116040367,"platform":2,"isFastHistory":true,"isOptimized":true}]'
    
    print("🧪 TESTING POCKETOPTION SSID CONNECTION")
    print("=" * 60)
    print(f"📋 SSID Length: {len(test_ssid)} characters")
    print(f"📋 SSID Preview: {test_ssid[:80]}...")
    print("=" * 60)
    
    # Step 1: Validate SSID format
    print("\n🔍 STEP 1: Validating SSID Format")
    try:
        if not test_ssid.startswith('42["auth",'):
            print("❌ SSID doesn't start with correct prefix")
            return
        
        # Extract JSON part
        json_start = test_ssid.find("{")
        json_end = test_ssid.rfind("}") + 1
        
        if json_start == -1 or json_end <= json_start:
            print("❌ No valid JSON found in SSID")
            return
            
        json_part = test_ssid[json_start:json_end]
        print(f"📋 JSON Part: {json_part[:100]}...")
        
        # Parse JSON
        data = json.loads(json_part)
        print("✅ JSON parsing successful!")
        print(f"📊 Session: {data.get('session', 'N/A')[:50]}...")
        print(f"📊 isDemo: {data.get('isDemo')}")
        print(f"📊 UID: {data.get('uid')}")
        print(f"📊 Platform: {data.get('platform')}")
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing failed: {e}")
        return
    except Exception as e:
        print(f"❌ SSID validation failed: {e}")
        return
    
    # Step 2: Create client
    print("\n🔧 STEP 2: Creating PocketOption Client")
    try:
        client = AsyncPocketOptionClient(
            ssid=test_ssid,
            is_demo=False,  # Real account (isDemo=0)
            persistent_connection=False,
            enable_logging=True
        )
        
        print("✅ Client created successfully!")
        print(f"📊 Extracted Session ID: {client.session_id[:30]}...")
        print(f"📊 Client UID: {client.uid}")
        print(f"📊 Client Platform: {client.platform}")
        print(f"📊 Client Is Demo: {client.is_demo}")
        
    except Exception as e:
        print(f"❌ Client creation failed: {e}")
        return
    
    # Step 3: Test connection
    print("\n🔌 STEP 3: Testing Connection")
    try:
        print("⏳ Connecting to PocketOption...")
        await client.connect()
        
        if client.is_connected:
            print("✅ CONNECTION SUCCESSFUL!")
            print("🎉 Your SSID format is working correctly!")
            
            # Test basic functionality
            print("\n💰 STEP 4: Testing Basic Functionality")
            try:
                balance = await client.get_balance()
                print(f"✅ Account Balance: ${balance:.2f}")
            except Exception as e:
                print(f"⚠️ Could not get balance: {e}")
                
            try:
                assets = await client.get_all_asset()
                if assets:
                    print(f"✅ Available Assets: {len(assets)} found")
                    # Show first 5 assets
                    for i, asset in enumerate(list(assets.keys())[:5]):
                        print(f"   {i+1}. {asset}")
                else:
                    print("⚠️ No assets found")
            except Exception as e:
                print(f"⚠️ Could not get assets: {e}")
            
        else:
            print("❌ CONNECTION FAILED!")
            print("🔍 Client created but connection was not established")
            
    except Exception as e:
        print(f"❌ CONNECTION ERROR: {e}")
        print("🔍 This could be due to:")
        print("   - Invalid session (expired)")
        print("   - Network issues")
        print("   - PocketOption server issues")
        
    finally:
        # Step 5: Cleanup
        print("\n🧹 STEP 5: Cleanup")
        try:
            if 'client' in locals() and hasattr(client, 'is_connected') and client.is_connected:
                await client.disconnect()
                print("✅ Disconnected successfully")
            else:
                print("ℹ️ No active connection to disconnect")
        except Exception as e:
            print(f"⚠️ Disconnect error: {e}")

if __name__ == "__main__":
    print("🚀 Starting SSID Connection Test...")
    asyncio.run(test_ssid_connection())
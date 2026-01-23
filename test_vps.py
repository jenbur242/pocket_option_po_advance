#!/usr/bin/env python3
"""Test script for VPS"""
try:
    import aiohttp
    print("SUCCESS: aiohttp imported successfully")
except ImportError as e:
    print(f"ERROR: aiohttp import failed: {e}")

try:
    import pandas
    print("SUCCESS: pandas imported successfully")
except ImportError as e:
    print(f"ERROR: pandas import failed: {e}")

try:
    import asyncio
    print("SUCCESS: asyncio imported successfully")
except ImportError as e:
    print(f"ERROR: asyncio import failed: {e}")

try:
    from pocketoptionapi_async import AsyncPocketOptionClient
    print("SUCCESS: PocketOption API imported successfully")
except ImportError as e:
    print(f"ERROR: PocketOption API import failed: {e}")

print("All tests completed!")
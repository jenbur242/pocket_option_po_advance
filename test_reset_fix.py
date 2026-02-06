#!/usr/bin/env python3
"""
Test script to verify the TwoCycleThreeStepMartingaleStrategy reset fix
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import the strategy class from app.py
from app import TwoCycleThreeStepMartingaleStrategy

def test_reset_logic():
    """Test the reset logic to ensure it works correctly"""
    print("🧪 Testing TwoCycleThreeStepMartingaleStrategy Reset Logic")
    print("=" * 60)
    
    # Create strategy with $10 base amount
    strategy = TwoCycleThreeStepMartingaleStrategy(base_amount=10.0, multiplier=2.5)
    
    print("\n📊 Initial State:")
    strategy.show_global_status()
    
    # Test Case 1: EUR/GBP loses 3 times
    print("\n🔴 Test Case 1: EUR/GBP loses C1S1, C1S2, C1S3")
    
    # EUR/GBP C1S1 LOSS
    amount1 = strategy.get_current_amount("EURUSD")
    print(f"EURUSD C1S1: ${amount1:.2f}")
    result1 = strategy.record_result(False, "EURUSD", amount1)
    print(f"Result: {result1}")
    
    # EUR/GBP C1S2 LOSS  
    amount2 = strategy.get_current_amount("EURUSD")
    print(f"EURUSD C1S2: ${amount2:.2f}")
    result2 = strategy.record_result(False, "EURUSD", amount2)
    print(f"Result: {result2}")
    
    # EUR/GBP C1S3 LOSS
    amount3 = strategy.get_current_amount("EURUSD")
    print(f"EURUSD C1S3: ${amount3:.2f}")
    result3 = strategy.record_result(False, "EURUSD", amount3)
    print(f"Result: {result3}")
    
    print("\n📊 After EUR/GBP losses:")
    strategy.show_global_status()
    
    # Test Case 2: EUR/JPY starts at C2S1 and WINS
    print("\n🟢 Test Case 2: EUR/JPY starts at C2S1 and WINS")
    
    amount4 = strategy.get_current_amount("EURJPY")
    print(f"EURJPY C2S1: ${amount4:.2f}")
    result4 = strategy.record_result(True, "EURJPY", amount4)  # WIN!
    print(f"Result: {result4}")
    
    print("\n📊 After EUR/JPY WIN:")
    strategy.show_global_status()
    
    # Test Case 3: Next EUR/JPY signal should be C1S1 ($10)
    print("\n🔍 Test Case 3: Next EUR/JPY signal should be C1S1 ($10)")
    
    amount5 = strategy.get_current_amount("EURJPY")
    print(f"EURJPY next trade: ${amount5:.2f}")
    
    if amount5 == 10.0:
        print("✅ RESET WORKING CORRECTLY! Next trade is $10 (C1S1)")
    else:
        print(f"❌ RESET FAILED! Expected $10, got ${amount5:.2f}")
        
    # Test Case 4: New asset should also start at C1S1
    print("\n🔍 Test Case 4: New asset should start at C1S1 ($10)")
    
    amount6 = strategy.get_current_amount("GBPUSD")
    print(f"GBPUSD (new asset): ${amount6:.2f}")
    
    if amount6 == 10.0:
        print("✅ NEW ASSET WORKING CORRECTLY! Starts at $10 (C1S1)")
    else:
        print(f"❌ NEW ASSET FAILED! Expected $10, got ${amount6:.2f}")

if __name__ == "__main__":
    test_reset_logic()
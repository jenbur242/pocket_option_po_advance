#!/usr/bin/env python3
"""Complete test of Option 3: Cross-Asset 3-Cycle 2-Step Martingale Strategy"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import TwoStepMartingaleStrategy

def test_complete_option3():
    """Test the complete Option 3 implementation"""
    print("🧪 TESTING COMPLETE OPTION 3 IMPLEMENTATION")
    print("=" * 60)
    
    strategy = TwoStepMartingaleStrategy(1.0, 2.5)
    
    print("\n📋 TEST SCENARIO: Multiple assets with cross-asset cycle progression")
    print("=" * 60)
    
    # Test data: asset, won/lost results for each step
    test_sequence = [
        # Asset 1: EURJPY - C1S1 LOSS, C1S2 LOSS → advances global to C2S1
        ("EURJPY", [False, False]),
        
        # Asset 2: GBPUSD - starts at C2S1, C2S1 LOSS, C2S2 LOSS → advances global to C3S1  
        ("GBPUSD", [False, False]),
        
        # Asset 3: USDJPY - starts at C3S1, C3S1 WIN → resets global to C1S1
        ("USDJPY", [True]),
        
        # Asset 4: AUDCAD - starts at C1S1 (after WIN), C1S1 LOSS, C1S2 WIN → resets global to C1S1
        ("AUDCAD", [False, True]),
        
        # Asset 5: NZDUSD - starts at C1S1, C1S1 WIN → stays at C1S1
        ("NZDUSD", [True]),
    ]
    
    for asset_num, (asset, results) in enumerate(test_sequence, 1):
        print(f"\n{asset_num}️⃣ ASSET: {asset}")
        print("-" * 30)
        
        # Show global state before this asset
        strategy.show_global_status()
        
        # Show asset status
        print(f"   Asset Status: {strategy.get_status(asset)}")
        
        # Process each step for this asset
        for step_num, won in enumerate(results, 1):
            current_cycle = strategy.get_asset_cycle(asset)
            current_step = strategy.get_asset_step(asset)
            amount = strategy.get_current_amount(asset)
            
            print(f"\n   Step {step_num}: C{current_cycle}S{current_step} - ${amount:.2f}")
            
            # Record the result
            result = strategy.record_result(won, asset, amount)
            
            result_text = "WIN ✅" if won else "LOSS ❌"
            print(f"   Result: {result_text}")
            print(f"   Action: {result['action']}")
            
            # If won or asset completed, break out of steps loop
            if won or result['action'] in ['asset_completed', 'reset', 'reset_after_max_loss']:
                break
        
        print(f"\n   Final Status: {strategy.get_status(asset)}")
    
    print(f"\n🏁 FINAL GLOBAL STATE:")
    strategy.show_global_status()
    
    print(f"\n✅ COMPLETE OPTION 3 TEST FINISHED!")
    
    # Verify expected final state
    expected_global_cycle = 1
    expected_global_step = 1
    
    if strategy.global_cycle == expected_global_cycle and strategy.global_step == expected_global_step:
        print(f"✅ PASS: Global state is C{strategy.global_cycle}S{strategy.global_step} as expected")
    else:
        print(f"❌ FAIL: Expected C{expected_global_cycle}S{expected_global_step}, got C{strategy.global_cycle}S{strategy.global_step}")
    
    print(f"\n📊 SUMMARY OF CROSS-ASSET PROGRESSION:")
    print(f"   • EURJPY: C1S1 LOSS → C1S2 LOSS → Global advances to C2S1")
    print(f"   • GBPUSD: C2S1 LOSS → C2S2 LOSS → Global advances to C3S1")
    print(f"   • USDJPY: C3S1 WIN → Global resets to C1S1")
    print(f"   • AUDCAD: C1S1 LOSS → C1S2 WIN → Global stays at C1S1")
    print(f"   • NZDUSD: C1S1 WIN → Global stays at C1S1")

if __name__ == "__main__":
    test_complete_option3()
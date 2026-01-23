#!/usr/bin/env python3
"""Test the Cross-Asset 3-Cycle 2-Step Martingale Strategy"""

from typing import Dict, Any, List

class TwoStepMartingaleStrategy:
    """3-Cycle 2-Step Martingale: Cycle progression across different assets"""
    
    def __init__(self, base_amount: float, multiplier: float = 2.5):
        self.base_amount = base_amount
        self.multiplier = multiplier
        self.max_cycles = 3
        self.max_steps_per_cycle = 2
        
        # Global cycle state - applies to ALL assets
        self.global_cycle = 1
        self.global_step = 1
        
        # Track each asset separately with cycle and step info
        self.asset_strategies = {}  # {asset: {'cycle': 1, 'step': 1, 'amounts': []}}
        
        print(f"🎯 Cross-Asset 3-Cycle 2-Step Martingale Strategy")
        print(f"   Base Amount: ${base_amount}")
        print(f"   Multiplier: {multiplier}")
        print(f"   Logic: LOSS at Step 2 → Next asset starts at next cycle")
    
    def get_current_amount(self, asset: str) -> float:
        """Get current trade amount for specific asset based on cycle and step"""
        if asset not in self.asset_strategies:
            # New asset starts at current global cycle and step
            self.asset_strategies[asset] = {
                'cycle': self.global_cycle, 
                'step': self.global_step, 
                'amounts': []
            }
        
        strategy = self.asset_strategies[asset]
        cycle = strategy['cycle']
        step = strategy['step']
        
        # Calculate amount based on cycle and step
        if cycle == 1:
            if step == 1:
                return self.base_amount  # C1S1: $1
            else:  # step == 2
                return self.base_amount * self.multiplier  # C1S2: $1 × 2.5 = $2.5
        elif cycle == 2:
            c1s2_amount = self.base_amount * self.multiplier  # $2.5
            if step == 1:
                return c1s2_amount * self.multiplier  # C2S1: $2.5 × 2.5 = $6.25
            else:  # step == 2
                return c1s2_amount * self.multiplier * self.multiplier  # C2S2: $6.25 × 2.5 = $15.625
        elif cycle == 3:
            c2s2_amount = self.base_amount * (self.multiplier ** 4)  # $15.625
            if step == 1:
                return c2s2_amount * self.multiplier  # C3S1: $15.625 × 2.5 = $39.06
            else:  # step == 2
                c3s1_amount = c2s2_amount * self.multiplier  # $39.06
                return c3s1_amount * self.multiplier  # C3S2: $39.06 × 2.5 = $97.66
        else:
            return self.base_amount
    
    def record_result(self, won: bool, asset: str, trade_amount: float) -> Dict[str, Any]:
        """Record trade result and return next action with cross-asset cycle progression"""
        if asset not in self.asset_strategies:
            self.asset_strategies[asset] = {
                'cycle': self.global_cycle, 
                'step': self.global_step, 
                'amounts': []
            }
        
        strategy = self.asset_strategies[asset]
        cycle = strategy['cycle']
        step = strategy['step']
        
        if won:
            print(f"✅ {asset} WIN at C{cycle}S{step}! Resetting global state to C1S1")
            # WIN resets GLOBAL state to C1S1 - all future assets start at C1S1
            self.global_cycle = 1
            self.global_step = 1
            return {'action': 'reset', 'asset': asset}
        else:
            print(f"❌ {asset} LOSS at C{cycle}S{step}!")
            
            if step < self.max_steps_per_cycle:
                # Move to next step in same cycle (same asset)
                strategy['step'] += 1
                print(f"🔄 Moving to C{cycle}S{strategy['step']} for {asset}")
                return {'action': 'continue', 'asset': asset}
            else:
                # Step 2 of current cycle lost - advance GLOBAL cycle for NEXT assets
                if cycle < self.max_cycles:
                    # Advance global cycle for next assets
                    self.global_cycle = cycle + 1
                    self.global_step = 1
                    print(f"🔄 {asset} C{cycle}S2 LOST! Next assets will start at C{self.global_cycle}S1")
                    return {'action': 'asset_completed', 'asset': asset}
                else:
                    # All 3 cycles completed - reset global state to C1S1
                    print(f"🔄 {asset} C3S2 LOST! All cycles completed - resetting global state to C1S1")
                    self.global_cycle = 1
                    self.global_step = 1
                    return {'action': 'reset_after_max_loss', 'asset': asset}
    
    def get_status(self, asset: str) -> str:
        """Get current strategy status for specific asset"""
        if asset not in self.asset_strategies:
            return f"{asset}: C{self.global_cycle}S{self.global_step} (${self.get_current_amount(asset):.2f}) [NEW]"
        
        strategy = self.asset_strategies[asset]
        cycle = strategy['cycle']
        step = strategy['step']
        current_amount = self.get_current_amount(asset)
        return f"{asset}: C{cycle}S{step} (${current_amount:.2f})"
    
    def show_global_status(self):
        """Show global cycle state"""
        print(f"🌍 Global Cycle State: C{self.global_cycle}S{self.global_step} (new assets start here)")

# Test the cross-asset cycle progression
print("Testing Cross-Asset 3-Cycle 2-Step Martingale Strategy:")
print("=" * 70)

strategy = TwoStepMartingaleStrategy(1.0, 2.5)

print("\n📋 SCENARIO: Testing cross-asset cycle progression")
print("=" * 50)

# Asset 1: EURJPY - starts at C1S1
print(f"\n1️⃣ EURJPY Signal:")
strategy.show_global_status()
print(f"   {strategy.get_status('EURJPY')}")
amount1 = strategy.get_current_amount('EURJPY')
print(f"   Trade Amount: ${amount1:.2f}")

# EURJPY C1S1 LOSS
result1 = strategy.record_result(False, 'EURJPY', amount1)
print(f"   Result: {result1['action']}")

# EURJPY C1S2
print(f"\n   EURJPY C1S2:")
print(f"   {strategy.get_status('EURJPY')}")
amount2 = strategy.get_current_amount('EURJPY')
print(f"   Trade Amount: ${amount2:.2f}")

# EURJPY C1S2 LOSS - this should advance global cycle to C2S1
result2 = strategy.record_result(False, 'EURJPY', amount2)
print(f"   Result: {result2['action']}")

print(f"\n2️⃣ GBPUSD Signal (NEW ASSET):")
strategy.show_global_status()
print(f"   {strategy.get_status('GBPUSD')}")
amount3 = strategy.get_current_amount('GBPUSD')
print(f"   Trade Amount: ${amount3:.2f} (should be C2S1 amount)")

# GBPUSD C2S1 LOSS
result3 = strategy.record_result(False, 'GBPUSD', amount3)
print(f"   Result: {result3['action']}")

# GBPUSD C2S2
print(f"\n   GBPUSD C2S2:")
print(f"   {strategy.get_status('GBPUSD')}")
amount4 = strategy.get_current_amount('GBPUSD')
print(f"   Trade Amount: ${amount4:.2f}")

# GBPUSD C2S2 LOSS - this should advance global cycle to C3S1
result4 = strategy.record_result(False, 'GBPUSD', amount4)
print(f"   Result: {result4['action']}")

print(f"\n3️⃣ USDJPY Signal (NEW ASSET):")
strategy.show_global_status()
print(f"   {strategy.get_status('USDJPY')}")
amount5 = strategy.get_current_amount('USDJPY')
print(f"   Trade Amount: ${amount5:.2f} (should be C3S1 amount)")

# USDJPY C3S1 WIN - this should reset global cycle to C1S1
result5 = strategy.record_result(True, 'USDJPY', amount5)
print(f"   Result: {result5['action']}")

print(f"\n4️⃣ AUDCAD Signal (NEW ASSET AFTER WIN):")
strategy.show_global_status()
print(f"   {strategy.get_status('AUDCAD')}")
amount6 = strategy.get_current_amount('AUDCAD')
print(f"   Trade Amount: ${amount6:.2f} (should be C1S1 amount after WIN)")

print("\n✅ Cross-Asset Cycle Progression Test Complete!")
print("\n📋 SUMMARY:")
print("   • EURJPY: C1S1 LOSS → C1S2 LOSS → Global advances to C2S1")
print("   • GBPUSD: Starts at C2S1 → C2S1 LOSS → C2S2 LOSS → Global advances to C3S1")
print("   • USDJPY: Starts at C3S1 → C3S1 WIN → Global resets to C1S1")
print("   • AUDCAD: Starts at C1S1 (fresh start after WIN)")
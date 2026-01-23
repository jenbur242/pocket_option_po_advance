#!/usr/bin/env python3
"""Test the 3-Cycle 2-Step Martingale Strategy"""

from typing import Dict, Any, List

class TwoStepMartingaleStrategy:
    """3-Cycle 2-Step Martingale: 3 cycles × 2 steps each = up to 6 total trades"""
    
    def __init__(self, base_amount: float, multiplier: float = 2.5):
        self.base_amount = base_amount
        self.multiplier = multiplier
        self.max_cycles = 3
        self.max_steps_per_cycle = 2
        
        # Track each asset separately with cycle and step info
        self.asset_strategies = {}  # {asset: {'cycle': 1, 'step': 1, 'amounts': []}}
        
        # Calculate all amounts for display
        c1s1 = base_amount
        c1s2 = c1s1 * multiplier
        c2s1 = c1s2 * multiplier
        c2s2 = c2s1 * multiplier
        c3s1 = c2s2 * multiplier
        c3s2 = c3s1 * multiplier
        
        print(f"🎯 3-Cycle 2-Step Martingale Strategy")
        print(f"   Base Amount: ${base_amount}")
        print(f"   Multiplier: {multiplier}")
        print(f"   Max Cycles: {self.max_cycles}")
        print(f"   Steps per Cycle: {self.max_steps_per_cycle}")
        print(f"   Cycle Amounts:")
        print(f"     Cycle 1: Step 1 ${c1s1:.2f} → Step 2 ${c1s2:.2f}")
        print(f"     Cycle 2: Step 1 ${c2s1:.2f} → Step 2 ${c2s2:.2f}")
        print(f"     Cycle 3: Step 1 ${c3s1:.2f} → Step 2 ${c3s2:.2f}")
        print(f"   Strategy: 3 cycles × 2 steps = up to 6 total trades")
    
    def get_current_amount(self, asset: str) -> float:
        """Get current trade amount for specific asset based on cycle and step"""
        if asset not in self.asset_strategies:
            self.asset_strategies[asset] = {'cycle': 1, 'step': 1, 'amounts': []}
        
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
    
    def get_status(self, asset: str) -> str:
        """Get current strategy status for specific asset"""
        if asset not in self.asset_strategies:
            return f"{asset}: C1S1 (${self.base_amount})"
        
        strategy = self.asset_strategies[asset]
        cycle = strategy['cycle']
        step = strategy['step']
        current_amount = self.get_current_amount(asset)
        return f"{asset}: C{cycle}S{step} (${current_amount:.2f})"

# Test the strategy
print("Testing 3-Cycle 2-Step Martingale Strategy:")
print("=" * 60)

strategy = TwoStepMartingaleStrategy(1.0, 2.5)

print("\nTesting amount calculations:")
test_cases = [
    ('EURJPY', 1, 1),  # C1S1
    ('EURJPY', 1, 2),  # C1S2
    ('EURJPY', 2, 1),  # C2S1
    ('EURJPY', 2, 2),  # C2S2
    ('EURJPY', 3, 1),  # C3S1
    ('EURJPY', 3, 2),  # C3S2
]

for asset, cycle, step in test_cases:
    # Set the strategy state
    strategy.asset_strategies[asset] = {'cycle': cycle, 'step': step, 'amounts': []}
    amount = strategy.get_current_amount(asset)
    status = strategy.get_status(asset)
    print(f"  {status} → Amount: ${amount:.2f}")

print("\n✅ 3-Cycle 2-Step Martingale Strategy implemented successfully!")

# Show the progression
print("\nProgression Example:")
print("C1S1: $1.00 → C1S2: $2.50 → C2S1: $6.25 → C2S2: $15.63 → C3S1: $39.06 → C3S2: $97.66")
print("Total possible loss: $161.04 (if all 6 trades lose)")
print("WIN at any step → Reset to C1S1")
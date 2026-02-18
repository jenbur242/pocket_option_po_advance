#!/usr/bin/env python3
"""
PocketOption Precise Timing Trader
Places trades with configurable offset from signal time
Trade timing is controlled by trade_config.txt file
Example: Signal at 00:38:00, offset=3s → Execute at 00:37:57

NEW FEATURES:
- Date-specific trading: Run continuously for signals on any specific date
- Enhanced CSV file handling: Supports both current date and date matching
- Flexible channel support: Works with all 5 channels (James Martin, LC Trader, PO ADVANCE BOT, Logic 5 Cycle, Pocket Option Sign)
- Current date focus: Prioritizes today's signals but supports historical/future date trading
- Regular channel runs: Automatically updates CSV files and runs channel code regularly
"""
import os
import json
import time
import asyncio
import logging
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Tuple
from dotenv import load_dotenv

# Import PocketOption API
from pocketoptionapi_async import AsyncPocketOptionClient
from pocketoptionapi_async.models import OrderDirection, OrderStatus

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global timezone setting - will be configured by user input
USER_TIMEZONE = None

def set_user_timezone(timezone_offset: float):
    """Set user timezone from offset (e.g., 6.0 for UTC+6, -5.0 for UTC-5)"""
    global USER_TIMEZONE
    hours = int(timezone_offset)
    minutes = int((abs(timezone_offset) - abs(hours)) * 60)
    USER_TIMEZONE = timezone(timedelta(hours=hours, minutes=minutes))
    print(f"✅ Timezone set to UTC{timezone_offset:+.1f}")

def get_user_time() -> datetime:
    """Get current time in user's configured timezone"""
    if USER_TIMEZONE is None:
        raise Exception("Timezone not configured. Please set timezone first.")
    return datetime.now(USER_TIMEZONE)

def format_time_hmsms(dt: datetime) -> str:
    """Format datetime as h:m:s:ms (hours:minutes:seconds:milliseconds)"""
    return dt.strftime('%H:%M:%S') + f":{dt.microsecond // 1000:03d}"

def get_user_time_str() -> str:
    """Get current user timezone time as formatted string h:m:s:ms"""
    return format_time_hmsms(get_user_time())

def format_time_remaining(current_time: datetime, signal_time: datetime) -> str:
    """Format time remaining until signal execution"""
    time_diff = signal_time - current_time
    total_seconds = int(time_diff.total_seconds())
    
    if total_seconds <= 0:
        return "NOW"
    
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

def get_timezone_name() -> str:
    """Get timezone name for display"""
    if USER_TIMEZONE is None:
        return "Not Set"
    offset = USER_TIMEZONE.utcoffset(get_user_time()).total_seconds() / 3600
    return f"UTC{offset:+.1f}"

class MultiAssetMartingaleStrategy:
    """Multi-asset martingale strategy with immediate step progression"""
    
    def __init__(self, base_amount: float, multiplier: float = 2.5):
        self.base_amount = base_amount
        self.multiplier = multiplier
        self.max_steps = 3
        
        # Track each asset separately
        self.asset_strategies = {}  # {asset: {'step': 1, 'amounts': []}}
        
        # Calculate step amounts for display
        step1 = base_amount
        step2 = step1 * multiplier
        step3 = step2 * multiplier
        
        print(f"🎯 Multi-Asset Martingale Strategy")
        print(f"   Base Amount: ${base_amount}")
        print(f"   Multiplier: {multiplier}")
        print(f"   Max Steps: {self.max_steps}")
        print(f"   Step Amounts:")
        print(f"     Step 1: ${step1:.2f} (Base)")
        print(f"     Step 2: ${step2:.2f} (${step1:.2f} × {multiplier})")
        print(f"     Step 3: ${step3:.2f} (${step2:.2f} × {multiplier})")
        print(f"   Strategy: Immediate step progression + parallel assets")
    
    def get_asset_step(self, asset: str) -> int:
        """Get current step for specific asset"""
        if asset not in self.asset_strategies:
            self.asset_strategies[asset] = {'step': 1, 'amounts': []}
        return self.asset_strategies[asset]['step']
    
    def get_current_amount(self, asset: str) -> float:
        """Get current trade amount for specific asset based on its step"""
        if asset not in self.asset_strategies:
            self.asset_strategies[asset] = {'step': 1, 'amounts': []}
        
        strategy = self.asset_strategies[asset]
        step = strategy['step']
        amounts = strategy['amounts']
        
        if step == 1:
            return self.base_amount
        elif step == 2:
            # Step 2 = Step 1 amount × multiplier
            if len(amounts) > 0:
                return amounts[0] * self.multiplier
            else:
                return self.base_amount * self.multiplier
        elif step == 3:
            # Step 3 = Step 2 amount × multiplier
            if len(amounts) > 1:
                return amounts[1] * self.multiplier
            else:
                # If no Step 2 amount recorded, calculate: (Step 1 × multiplier) × multiplier
                step2_amount = self.base_amount * self.multiplier
                return step2_amount * self.multiplier
        else:
            return self.base_amount
    
    def record_result(self, won: bool, asset: str, trade_amount: float) -> Dict[str, Any]:
        """Record trade result and return next action"""
        if asset not in self.asset_strategies:
            self.asset_strategies[asset] = {'step': 1, 'amounts': []}
        
        strategy = self.asset_strategies[asset]
        
        # Record amount used
        if len(strategy['amounts']) < strategy['step']:
            strategy['amounts'].append(trade_amount)
        
        if won:
            print(f"✅ {asset} WIN at Step {strategy['step']}! Resetting to Step 1")
            strategy['step'] = 1
            strategy['amounts'] = []
            return {'action': 'reset', 'asset': asset, 'next_step': 1}
        else:
            print(f"❌ {asset} LOSS at Step {strategy['step']}! Moving to Step {strategy['step'] + 1}")
            strategy['step'] += 1
            
            if strategy['step'] > self.max_steps:
                print(f"🚨 {asset} - All {self.max_steps} steps lost! Resetting to Step 1")
                strategy['step'] = 1
                strategy['amounts'] = []
                return {'action': 'reset_after_max_loss', 'asset': asset, 'next_step': 1}
            else:
                return {'action': 'continue', 'asset': asset, 'next_step': strategy['step']}
    
    def get_status(self, asset: str) -> str:
        """Get current strategy status for specific asset"""
        if asset not in self.asset_strategies:
            return f"{asset}: Step 1/3 (${self.base_amount})"
        
        strategy = self.asset_strategies[asset]
        current_amount = self.get_current_amount(asset)
        return f"{asset}: Step {strategy['step']}/3 (${current_amount})"
    
    def get_all_active_assets(self) -> List[str]:
        """Get all assets currently being tracked"""
        return list(self.asset_strategies.keys())
    
    def should_prioritize_existing_sequences(self) -> bool:
        """Check if any asset is in the middle of a martingale sequence (Step 2 or 3)"""
        for asset, strategy in self.asset_strategies.items():
            if strategy['step'] > 1:  # Asset is at Step 2 or 3
                return True
        return False
    
    def show_strategy_status(self):
        """Show current status of all assets"""
        if not self.asset_strategies:
            print("📊 No active asset strategies")
            return
            
        print("📊 Current Asset Strategy Status:")
        for asset, strategy in self.asset_strategies.items():
            step = strategy['step']
            amounts = strategy['amounts']
            current_amount = self.get_current_amount(asset)
            
            if step == 1:
                status = "✅ Ready for new signal"
            else:
                status = f"🔄 In martingale sequence"
                
            print(f"   {asset}: Step {step}/3 (${current_amount:.2f}) - {status}")
    
    def get_assets_in_sequence(self) -> List[str]:
        """Get assets that are currently in martingale sequence (Step 2 or 3)"""
        assets_in_sequence = []
        for asset, strategy in self.asset_strategies.items():
            if strategy['step'] > 1:
                assets_in_sequence.append(asset)
        return assets_in_sequence
    
    def get_assets_at_step1(self) -> List[str]:
        """Get assets that are at Step 1 (ready for new signals)"""
        assets_at_step1 = []
        for asset, strategy in self.asset_strategies.items():
            if strategy['step'] == 1:
                assets_at_step1.append(asset)
        return assets_at_step1

class TwoCycleTwoStepMartingaleStrategy:
    """2-Cycle 2-Step Martingale: Cycle progression across different assets"""
    
    def __init__(self, base_amount: float, multiplier: float = 2.5):
        self.base_amount = base_amount
        self.multiplier = multiplier
        self.max_cycles = 2
        self.max_steps_per_cycle = 2
        
        # Global cycle state - applies to ALL assets
        self.global_cycle = 1
        self.global_step = 1
        
        # Track each asset separately with cycle and step info
        self.asset_strategies = {}  # {asset: {'cycle': 1, 'step': 1, 'amounts': []}}
        
        # Calculate all amounts for display
        c1s1 = base_amount                                    # $1.00
        c1s2 = base_amount * multiplier                       # $2.50
        c2s1 = base_amount * (multiplier ** 2)               # $6.25
        c2s2 = base_amount * (multiplier ** 3)               # $15.625
        
        print(f"🎯 2-Cycle 2-Step Martingale Strategy (Cross-Asset Progression)")
        print(f"   Base Amount: ${base_amount}")
        print(f"   Multiplier: {multiplier}")
        print(f"   Max Cycles: {self.max_cycles}")
        print(f"   Steps per Cycle: {self.max_steps_per_cycle}")
        print(f"   Cycle Amounts:")
        print(f"     Cycle 1: Step 1 ${c1s1:.2f} → Step 2 ${c1s2:.2f}")
        print(f"     Cycle 2: Step 1 ${c2s1:.2f} → Step 2 ${c2s2:.2f}")
        print(f"   Strategy: Cycle progression across different assets")
        print(f"   Logic: LOSS at Step 2 → Next asset starts at next cycle")
    
    def get_asset_step(self, asset: str) -> int:
        """Get current step for specific asset - uses global cycle state for new assets"""
        if asset not in self.asset_strategies:
            # New asset starts at current global cycle and step
            self.asset_strategies[asset] = {
                'cycle': self.global_cycle, 
                'step': self.global_step, 
                'amounts': []
            }
        return self.asset_strategies[asset]['step']
    
    def get_asset_cycle(self, asset: str) -> int:
        """Get current cycle for specific asset - uses global cycle state for new assets"""
        if asset not in self.asset_strategies:
            # New asset starts at current global cycle and step
            print(f"🔍 DEBUG: New asset {asset} starting at global C{self.global_cycle}S{self.global_step}")
            self.asset_strategies[asset] = {
                'cycle': self.global_cycle, 
                'step': self.global_step, 
                'amounts': []
            }
        else:
            print(f"🔍 DEBUG: Existing asset {asset} at C{self.asset_strategies[asset]['cycle']}S{self.asset_strategies[asset]['step']} (global: C{self.global_cycle}S{self.global_step})")
        return self.asset_strategies[asset]['cycle']
    
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
                return self.base_amount  # C1S1: $1.00
            else:  # step == 2
                return self.base_amount * self.multiplier  # C1S2: $1.00 × 2.5 = $2.50
        elif cycle == 2:
            # C2S1 = C1S2 × multiplier = $2.50 × 2.5 = $6.25
            # C2S2 = C2S1 × multiplier = $6.25 × 2.5 = $15.625
            if step == 1:
                return self.base_amount * (self.multiplier ** 2)  # C2S1: $1 × 2.5² = $6.25
            else:  # step == 2
                return self.base_amount * (self.multiplier ** 3)  # C2S2: $1 × 2.5³ = $15.625
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
        
        # Record amount used
        strategy['amounts'].append(trade_amount)
        
        if won:
            print(f"✅ {asset} WIN at C{cycle}S{step}! Resetting global state to C1S1")
            print(f"🔍 DEBUG: Before reset - Global: C{self.global_cycle}S{self.global_step}")
            # WIN resets GLOBAL state to C1S1 - all future assets start at C1S1
            self.global_cycle = 1
            self.global_step = 1
            print(f"🔍 DEBUG: After reset - Global: C{self.global_cycle}S{self.global_step}")
            # Reset this asset's strategy
            strategy['cycle'] = 1
            strategy['step'] = 1
            strategy['amounts'] = []
            return {'action': 'reset', 'asset': asset, 'next_cycle': 1, 'next_step': 1}
        else:
            print(f"❌ {asset} LOSS at C{cycle}S{step}!")
            
            if step < self.max_steps_per_cycle:
                # Move to next step in same cycle (same asset)
                strategy['step'] += 1
                print(f"🔄 Moving to C{cycle}S{strategy['step']} for {asset}")
                return {'action': 'continue', 'asset': asset, 'next_cycle': cycle, 'next_step': strategy['step']}
            else:
                # Step 2 of current cycle lost - advance GLOBAL cycle for NEXT assets
                if cycle < self.max_cycles:
                    # Advance global cycle for next assets
                    self.global_cycle = cycle + 1
                    self.global_step = 1
                    print(f"🔄 {asset} C{cycle}S2 LOST! Next assets will start at C{self.global_cycle}S1")
                    
                    # Mark this asset as completed (no more trades for this asset)
                    strategy['cycle'] = cycle + 1  # For status display
                    strategy['step'] = 1
                    strategy['amounts'] = []
                    return {'action': 'asset_completed', 'asset': asset, 'next_cycle': self.global_cycle, 'next_step': 1}
                else:
                    # All 2 cycles completed - reset global state to C1S1
                    print(f"🔄 {asset} C2S2 LOST! All cycles completed - resetting global state to C1S1")
                    self.global_cycle = 1
                    self.global_step = 1
                    
                    # Reset this asset's strategy
                    strategy['cycle'] = 1
                    strategy['step'] = 1
                    strategy['amounts'] = []
                    return {'action': 'reset_after_max_loss', 'asset': asset, 'next_cycle': 1, 'next_step': 1}
    
    def get_status(self, asset: str) -> str:
        """Get current strategy status for specific asset"""
        if asset not in self.asset_strategies:
            return f"{asset}: C{self.global_cycle}S{self.global_step} (${self.get_current_amount(asset):.2f}) [NEW]"
        
        strategy = self.asset_strategies[asset]
        cycle = strategy['cycle']
        step = strategy['step']
        current_amount = self.get_current_amount(asset)
        return f"{asset}: C{cycle}S{step} (${current_amount:.2f})"
    
    def get_all_active_assets(self) -> List[str]:
        """Get all assets currently being tracked"""
        return list(self.asset_strategies.keys())
    
    def should_prioritize_existing_sequences(self) -> bool:
        """Check if any asset is in the middle of a cycle sequence"""
        for asset, strategy in self.asset_strategies.items():
            if strategy['cycle'] > 1 or strategy['step'] > 1:
                return True
        return False
    
    def show_global_status(self):
        """Show global cycle state"""
        print(f"🌍 Global Cycle State: C{self.global_cycle}S{self.global_step} (new assets start here)")
    
    def show_strategy_status(self):
        """Show current status of all assets and global cycle state"""
        print("📊 Current Strategy Status:")
        print(f"   🌍 Global Cycle State: C{self.global_cycle}S{self.global_step} (new assets start here)")
        
        if not self.asset_strategies:
            print("   📊 No active assets")
            return
            
        print("   📊 Asset Status:")
        for asset, strategy in self.asset_strategies.items():
            cycle = strategy['cycle']
            step = strategy['step']
            current_amount = self.get_current_amount(asset)
            
            if cycle == 1 and step == 1:
                status = "✅ Ready for new signal"
            else:
                status = f"🔄 In cycle sequence"
                
            print(f"      {asset}: C{cycle}S{step} (${current_amount:.2f}) - {status}")
    
    def get_assets_in_sequence(self) -> List[str]:
        """Get assets that are currently in cycle sequence"""
        assets_in_sequence = []
        for asset, strategy in self.asset_strategies.items():
            if strategy['cycle'] > 1 or strategy['step'] > 1:
                assets_in_sequence.append(asset)
        return assets_in_sequence
    
    def get_assets_at_step1(self) -> List[str]:
        """Get assets that are at C1S1 (ready for new signals)"""
        assets_at_step1 = []
        for asset, strategy in self.asset_strategies.items():
            if strategy['cycle'] == 1 and strategy['step'] == 1:
                assets_at_step1.append(asset)
        return assets_at_step1

class TwoCycleThreeStepMartingaleStrategy:
    """2-Cycle 3-Step Martingale: 2 cycles with 3 steps, step 4 initial amount is sum of first 3 steps"""
    
    def __init__(self, base_amount: float, multiplier: float = 2.5):
        self.base_amount = base_amount
        self.multiplier = multiplier
        self.max_cycles = 2
        self.max_steps_per_cycle = 3
        self.max_steps = 6  # Total max steps (2 cycles × 3 steps)
        
        # Global cycle state - applies to ALL assets
        self.global_cycle = 1
        self.global_step = 1
        
        # Track each asset separately with cycle and step info
        self.asset_strategies = {}  # {asset: {'cycle': 1, 'step': 1, 'amounts': []}}
        
        # Calculate all amounts for display
        c1s1 = base_amount                                    # $1.00
        c1s2 = base_amount * multiplier                       # $2.50
        c1s3 = base_amount * (multiplier ** 2)               # $6.25
        # Step 4 (C2S1) = sum of first 3 steps
        c2s1 = c1s1 + c1s2 + c1s3                           # $1.00 + $2.50 + $6.25 = $9.75
        c2s2 = c2s1 * multiplier                            # $9.75 × 2.5 = $24.375
        c2s3 = c2s2 * multiplier                            # $24.375 × 2.5 = $60.9375
        
        print(f"🎯 2-Cycle 3-Step Martingale Strategy (Cross-Asset Progression)")
        print(f"   Base Amount: ${base_amount}")
        print(f"   Multiplier: {multiplier}")
        print(f"   Max Cycles: {self.max_cycles}")
        print(f"   Steps per Cycle: {self.max_steps_per_cycle}")
        print(f"   Cycle Amounts:")
        print(f"     Cycle 1: Step 1 ${c1s1:.2f} → Step 2 ${c1s2:.2f} → Step 3 ${c1s3:.2f}")
        print(f"     Cycle 2: Step 1 ${c2s1:.2f} → Step 2 ${c2s2:.2f} → Step 3 ${c2s3:.2f}")
        print(f"   Special Logic: Step 4 (C2S1) = Sum of first 3 steps (${c2s1:.2f})")
        print(f"   Strategy: Cycle progression across different assets")
        print(f"   Logic: LOSS at Step 3 → Next asset starts at next cycle")
        print(f"   🔍 DEBUG MODE: Enhanced logging enabled for win reset tracking")
    
    def get_asset_step(self, asset: str) -> int:
        """Get current step for specific asset - uses global cycle state for new assets"""
        if asset not in self.asset_strategies:
            # New asset starts at current global cycle and step
            self.asset_strategies[asset] = {
                'cycle': self.global_cycle, 
                'step': self.global_step, 
                'amounts': []
            }
        return self.asset_strategies[asset]['step']
    
    def get_asset_cycle(self, asset: str) -> int:
        """Get current cycle for specific asset - uses global cycle state for new assets"""
        if asset not in self.asset_strategies:
            # New asset starts at current global cycle and step
            print(f"🔍 DEBUG: New asset {asset} starting at global C{self.global_cycle}S{self.global_step}")
            self.asset_strategies[asset] = {
                'cycle': self.global_cycle, 
                'step': self.global_step, 
                'amounts': []
            }
        else:
            print(f"🔍 DEBUG: Existing asset {asset} at C{self.asset_strategies[asset]['cycle']}S{self.asset_strategies[asset]['step']} (global: C{self.global_cycle}S{self.global_step})")
        return self.asset_strategies[asset]['cycle']
    
    def get_current_amount(self, asset: str) -> float:
        """Get current trade amount for specific asset based on cycle and step"""
        if asset not in self.asset_strategies:
            # New asset starts at current global cycle and step
            print(f"🔍 DEBUG get_current_amount: Creating new asset {asset} at global C{self.global_cycle}S{self.global_step}")
            self.asset_strategies[asset] = {
                'cycle': self.global_cycle, 
                'step': self.global_step, 
                'amounts': []
            }
        
        strategy = self.asset_strategies[asset]
        cycle = strategy['cycle']
        step = strategy['step']
        
        print(f"🔍 DEBUG get_current_amount: {asset} at C{cycle}S{step} (global: C{self.global_cycle}S{self.global_step})")
        
        # Calculate amount based on cycle and step
        if cycle == 1:
            if step == 1:
                amount = self.base_amount  # C1S1: $1.00
            elif step == 2:
                amount = self.base_amount * self.multiplier  # C1S2: $1.00 × 2.5 = $2.50
            else:  # step == 3
                amount = self.base_amount * (self.multiplier ** 2)  # C1S3: $1.00 × 2.5² = $6.25
        elif cycle == 2:
            # Special logic: C2S1 = sum of first 3 steps
            c1s1 = self.base_amount
            c1s2 = self.base_amount * self.multiplier
            c1s3 = self.base_amount * (self.multiplier ** 2)
            c2s1 = c1s1 + c1s2 + c1s3  # Sum of first 3 steps
            
            if step == 1:
                amount = c2s1  # C2S1: sum of first 3 steps
            elif step == 2:
                amount = c2s1 * self.multiplier  # C2S2: C2S1 × multiplier
            else:  # step == 3
                amount = c2s1 * (self.multiplier ** 2)  # C2S3: C2S1 × multiplier²
        else:
            amount = self.base_amount
            
        print(f"🔍 DEBUG get_current_amount: {asset} C{cycle}S{step} → ${amount:.2f}")
        return amount
    
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
        
        # Record amount used
        strategy['amounts'].append(trade_amount)
        
        if won:
            print(f"✅ {asset} WIN at C{cycle}S{step}! Resetting global state to C1S1")
            print(f"🔍 DEBUG WIN: Before reset - Global: C{self.global_cycle}S{self.global_step}, Asset: C{cycle}S{step}")
            print(f"🔍 DEBUG WIN: All tracked assets before reset: {list(self.asset_strategies.keys())}")
            # WIN resets GLOBAL state to C1S1 - all future assets start at C1S1
            self.global_cycle = 1
            self.global_step = 1
            print(f"🔍 DEBUG WIN: After reset - Global: C{self.global_cycle}S{self.global_step}")
            
            # CRITICAL FIX: Clear ALL assets so they start fresh at C1S1
            # This prevents old asset states from being reused
            print(f"🔍 DEBUG WIN: Clearing all {len(self.asset_strategies)} tracked assets")
            self.asset_strategies.clear()
            
            print(f"🔍 DEBUG WIN: All assets cleared - next signals will start at C1S1")
            return {'action': 'reset', 'asset': asset, 'next_cycle': 1, 'next_step': 1}
        else:
            print(f"❌ {asset} LOSS at C{cycle}S{step}!")
            
            if step < self.max_steps_per_cycle:
                # Move to next step in same cycle (same asset)
                strategy['step'] += 1
                print(f"🔄 Moving to C{cycle}S{strategy['step']} for {asset}")
                return {'action': 'continue', 'asset': asset, 'next_cycle': cycle, 'next_step': strategy['step']}
            else:
                # Step 3 of current cycle lost - advance GLOBAL cycle for NEXT assets
                if cycle < self.max_cycles:
                    # Advance global cycle for next assets
                    self.global_cycle = cycle + 1
                    self.global_step = 1
                    print(f"🔄 {asset} C{cycle}S3 LOST! Next assets will start at C{self.global_cycle}S1")
                    
                    # Mark this asset as completed (no more trades for this asset)
                    strategy['cycle'] = cycle + 1  # For status display
                    strategy['step'] = 1
                    strategy['amounts'] = []
                    return {'action': 'asset_completed', 'asset': asset, 'next_cycle': self.global_cycle, 'next_step': 1}
                else:
                    # All 2 cycles completed - reset global state to C1S1
                    print(f"🔄 {asset} C2S3 LOST! All cycles completed - resetting global state to C1S1")
                    self.global_cycle = 1
                    self.global_step = 1
                    
                    # CRITICAL FIX: Clear ALL assets so they start fresh at C1S1
                    print(f"🔍 DEBUG: Clearing all {len(self.asset_strategies)} tracked assets after max loss")
                    self.asset_strategies.clear()
                    
                    print(f"🔍 DEBUG: All assets cleared - next signals will start at C1S1")
                    return {'action': 'reset_after_max_loss', 'asset': asset, 'next_cycle': 1, 'next_step': 1}
    
    def get_status(self, asset: str) -> str:
        """Get current strategy status for specific asset"""
        if asset not in self.asset_strategies:
            return f"{asset}: C{self.global_cycle}S{self.global_step} (${self.get_current_amount(asset):.2f}) [NEW]"
        
        strategy = self.asset_strategies[asset]
        cycle = strategy['cycle']
        step = strategy['step']
        current_amount = self.get_current_amount(asset)
        return f"{asset}: C{cycle}S{step} (${current_amount:.2f})"
    
    def get_all_active_assets(self) -> List[str]:
        """Get all assets currently being tracked"""
        return list(self.asset_strategies.keys())
    
    def should_prioritize_existing_sequences(self) -> bool:
        """Check if any asset is in the middle of a cycle sequence"""
        for asset, strategy in self.asset_strategies.items():
            if strategy['cycle'] > 1 or strategy['step'] > 1:
                return True
        return False
    
    def show_global_status(self):
        """Show global cycle state"""
        print(f"🌍 Global Cycle State: C{self.global_cycle}S{self.global_step} (new assets start here)")
    
    def show_strategy_status(self):
        """Show current status of all assets and global cycle state"""
        print("📊 Current Strategy Status:")
        print(f"   🌍 Global Cycle State: C{self.global_cycle}S{self.global_step} (new assets start here)")
        
        if not self.asset_strategies:
            print("   📊 No active assets")
            return
            
        print("   📊 Asset Status:")
        for asset, strategy in self.asset_strategies.items():
            cycle = strategy['cycle']
            step = strategy['step']
            current_amount = self.get_current_amount(asset)
            
            if cycle == 1 and step == 1:
                status = "✅ Ready for new signal"
            else:
                status = f"🔄 In cycle sequence"
                
            print(f"      {asset}: C{cycle}S{step} (${current_amount:.2f}) - {status}")
    
    def get_assets_in_sequence(self) -> List[str]:
        """Get assets that are currently in cycle sequence"""
        assets_in_sequence = []
        for asset, strategy in self.asset_strategies.items():
            if strategy['cycle'] > 1 or strategy['step'] > 1:
                assets_in_sequence.append(asset)
        return assets_in_sequence
    
    def get_assets_at_step1(self) -> List[str]:
        """Get assets that are at C1S1 (ready for new signals)"""
        assets_at_step1 = []
        for asset, strategy in self.asset_strategies.items():
            if strategy['cycle'] == 1 and strategy['step'] == 1:
                assets_at_step1.append(asset)
        return assets_at_step1

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
        
        # Calculate all amounts for display - CORRECTED
        c1s1 = base_amount                                    # $1.00
        c1s2 = base_amount * multiplier                       # $2.50
        c2s1 = base_amount * (multiplier ** 2)               # $6.25
        c2s2 = base_amount * (multiplier ** 3)               # $15.625
        c3s1 = base_amount * (multiplier ** 4)               # $39.0625
        c3s2 = base_amount * (multiplier ** 5)               # $97.65625
        
        print(f"🎯 3-Cycle 2-Step Martingale Strategy (Cross-Asset Progression)")
        print(f"   Base Amount: ${base_amount}")
        print(f"   Multiplier: {multiplier}")
        print(f"   Max Cycles: {self.max_cycles}")
        print(f"   Steps per Cycle: {self.max_steps_per_cycle}")
        print(f"   Cycle Amounts:")
        print(f"     Cycle 1: Step 1 ${c1s1:.2f} → Step 2 ${c1s2:.2f}")
        print(f"     Cycle 2: Step 1 ${c2s1:.2f} → Step 2 ${c2s2:.2f}")
        print(f"     Cycle 3: Step 1 ${c3s1:.2f} → Step 2 ${c3s2:.2f}")
        print(f"   Strategy: Cycle progression across different assets")
        print(f"   Logic: LOSS at Step 2 → Next asset starts at next cycle")
    
    def get_asset_step(self, asset: str) -> int:
        """Get current step for specific asset - uses global cycle state for new assets"""
        if asset not in self.asset_strategies:
            # New asset starts at current global cycle and step
            self.asset_strategies[asset] = {
                'cycle': self.global_cycle, 
                'step': self.global_step, 
                'amounts': []
            }
        return self.asset_strategies[asset]['step']
    
    def get_asset_cycle(self, asset: str) -> int:
        """Get current cycle for specific asset - uses global cycle state for new assets"""
        if asset not in self.asset_strategies:
            # New asset starts at current global cycle and step
            print(f"🔍 DEBUG: New asset {asset} starting at global C{self.global_cycle}S{self.global_step}")
            self.asset_strategies[asset] = {
                'cycle': self.global_cycle, 
                'step': self.global_step, 
                'amounts': []
            }
        else:
            print(f"🔍 DEBUG: Existing asset {asset} at C{self.asset_strategies[asset]['cycle']}S{self.asset_strategies[asset]['step']} (global: C{self.global_cycle}S{self.global_step})")
        return self.asset_strategies[asset]['cycle']
    
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
        amounts = strategy['amounts']
        
        # Calculate amount based on cycle and step - CORRECTED LOGIC
        if cycle == 1:
            if step == 1:
                return self.base_amount  # C1S1: $1.00
            else:  # step == 2
                return self.base_amount * self.multiplier  # C1S2: $1.00 × 2.5 = $2.50
        elif cycle == 2:
            # C2S1 = C1S2 × multiplier = $2.50 × 2.5 = $6.25
            # C2S2 = C2S1 × multiplier = $6.25 × 2.5 = $15.625
            if step == 1:
                return self.base_amount * (self.multiplier ** 2)  # C2S1: $1 × 2.5² = $6.25
            else:  # step == 2
                return self.base_amount * (self.multiplier ** 3)  # C2S2: $1 × 2.5³ = $15.625
        elif cycle == 3:
            # C3S1 = C2S2 × multiplier = $15.625 × 2.5 = $39.0625
            # C3S2 = C3S1 × multiplier = $39.0625 × 2.5 = $97.65625
            if step == 1:
                return self.base_amount * (self.multiplier ** 4)  # C3S1: $1 × 2.5⁴ = $39.0625
            else:  # step == 2
                return self.base_amount * (self.multiplier ** 5)  # C3S2: $1 × 2.5⁵ = $97.65625
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
        
        # Record amount used
        strategy['amounts'].append(trade_amount)
        
        if won:
            print(f"✅ {asset} WIN at C{cycle}S{step}! Resetting global state to C1S1")
            print(f"🔍 DEBUG: Before reset - Global: C{self.global_cycle}S{self.global_step}")
            # WIN resets GLOBAL state to C1S1 - all future assets start at C1S1
            self.global_cycle = 1
            self.global_step = 1
            print(f"🔍 DEBUG: After reset - Global: C{self.global_cycle}S{self.global_step}")
            # Reset this asset's strategy
            strategy['cycle'] = 1
            strategy['step'] = 1
            strategy['amounts'] = []
            return {'action': 'reset', 'asset': asset, 'next_cycle': 1, 'next_step': 1}
        else:
            print(f"❌ {asset} LOSS at C{cycle}S{step}!")
            
            if step < self.max_steps_per_cycle:
                # Move to next step in same cycle (same asset)
                strategy['step'] += 1
                print(f"🔄 Moving to C{cycle}S{strategy['step']} for {asset}")
                return {'action': 'continue', 'asset': asset, 'next_cycle': cycle, 'next_step': strategy['step']}
            else:
                # Step 2 of current cycle lost - advance GLOBAL cycle for NEXT assets
                if cycle < self.max_cycles:
                    # Advance global cycle for next assets
                    self.global_cycle = cycle + 1
                    self.global_step = 1
                    print(f"🔄 {asset} C{cycle}S2 LOST! Next assets will start at C{self.global_cycle}S1")
                    
                    # Mark this asset as completed (no more trades for this asset)
                    strategy['cycle'] = cycle + 1  # For status display
                    strategy['step'] = 1
                    strategy['amounts'] = []
                    return {'action': 'asset_completed', 'asset': asset, 'next_cycle': self.global_cycle, 'next_step': 1}
                else:
                    # All 3 cycles completed - reset global state to C1S1
                    print(f"🔄 {asset} C3S2 LOST! All cycles completed - resetting global state to C1S1")
                    self.global_cycle = 1
                    self.global_step = 1
                    
                    # Reset this asset's strategy
                    strategy['cycle'] = 1
                    strategy['step'] = 1
                    strategy['amounts'] = []
                    return {'action': 'reset_after_max_loss', 'asset': asset, 'next_cycle': 1, 'next_step': 1}
    
    def get_status(self, asset: str) -> str:
        """Get current strategy status for specific asset"""
        if asset not in self.asset_strategies:
            return f"{asset}: C{self.global_cycle}S{self.global_step} (${self.get_current_amount(asset):.2f}) [NEW]"
        
        strategy = self.asset_strategies[asset]
        cycle = strategy['cycle']
        step = strategy['step']
        current_amount = self.get_current_amount(asset)
        return f"{asset}: C{cycle}S{step} (${current_amount:.2f})"
    
    def get_all_active_assets(self) -> List[str]:
        """Get all assets currently being tracked"""
        return list(self.asset_strategies.keys())
    
    def should_prioritize_existing_sequences(self) -> bool:
        """Check if any asset is in the middle of a cycle sequence"""
        for asset, strategy in self.asset_strategies.items():
            if strategy['cycle'] > 1 or strategy['step'] > 1:
                return True
        return False
    
    def show_global_status(self):
        """Show global cycle state"""
        print(f"🌍 Global Cycle State: C{self.global_cycle}S{self.global_step} (new assets start here)")
    
    def show_strategy_status(self):
        """Show current status of all assets and global cycle state"""
        print("📊 Current Strategy Status:")
        print(f"   🌍 Global Cycle State: C{self.global_cycle}S{self.global_step} (new assets start here)")
        
        if not self.asset_strategies:
            print("   📊 No active assets")
            return
            
        print("   📊 Asset Status:")
        for asset, strategy in self.asset_strategies.items():
            cycle = strategy['cycle']
            step = strategy['step']
            current_amount = self.get_current_amount(asset)
            
            if cycle == 1 and step == 1:
                status = "✅ Ready for new signal"
            else:
                status = f"🔄 In cycle sequence"
                
            print(f"      {asset}: C{cycle}S{step} (${current_amount:.2f}) - {status}")
    
    def get_assets_in_sequence(self) -> List[str]:
        """Get assets that are currently in cycle sequence"""
        assets_in_sequence = []
        for asset, strategy in self.asset_strategies.items():
            if strategy['cycle'] > 1 or strategy['step'] > 1:
                assets_in_sequence.append(asset)
        return assets_in_sequence
    
    def get_assets_at_step1(self) -> List[str]:
        """Get assets that are at C1S1 (ready for new signals)"""
        assets_at_step1 = []
        for asset, strategy in self.asset_strategies.items():
            if strategy['cycle'] == 1 and strategy['step'] == 1:
                assets_at_step1.append(asset)
        return assets_at_step1

class FourCycleMartingaleStrategy:
    """4-Cycle 2-Step Martingale: Extended cycle progression across different assets"""
    
    def __init__(self, base_amount: float, multiplier: float = 2.5):
        self.base_amount = base_amount
        self.multiplier = multiplier
        self.max_cycles = 4  # Extended to 4 cycles
        self.max_steps_per_cycle = 2
        
        # Global cycle state - applies to ALL assets
        self.global_cycle = 1
        self.global_step = 1
        
        # Track each asset separately with cycle and step info
        self.asset_strategies = {}  # {asset: {'cycle': 1, 'step': 1, 'amounts': []}}
        
        # Calculate all amounts for display - CORRECTED with 4 cycles
        c1s1 = base_amount                                    # $1.00
        c1s2 = base_amount * multiplier                       # $2.50
        c2s1 = base_amount * (multiplier ** 2)               # $6.25
        c2s2 = base_amount * (multiplier ** 3)               # $15.625
        c3s1 = base_amount * (multiplier ** 4)               # $39.0625
        c3s2 = base_amount * (multiplier ** 5)               # $97.65625
        c4s1 = base_amount * (multiplier ** 6)               # $244.140625
        c4s2 = base_amount * (multiplier ** 7)               # $610.35156
        
        print(f"🎯 4-Cycle 2-Step Martingale Strategy (Cross-Asset Progression)")
        print(f"   Base Amount: ${base_amount}")
        print(f"   Multiplier: {multiplier}")
        print(f"   Max Cycles: {self.max_cycles}")
        print(f"   Steps per Cycle: {self.max_steps_per_cycle}")
        print(f"   Cycle Amounts:")
        print(f"     Cycle 1: Step 1 ${c1s1:.2f} → Step 2 ${c1s2:.2f}")
        print(f"     Cycle 2: Step 1 ${c2s1:.2f} → Step 2 ${c2s2:.2f}")
        print(f"     Cycle 3: Step 1 ${c3s1:.2f} → Step 2 ${c3s2:.2f}")
        print(f"     Cycle 4: Step 1 ${c4s1:.2f} → Step 2 ${c4s2:.2f}")
        print(f"   Strategy: Cycle progression across different assets")
        print(f"   Logic: LOSS at Step 2 → Next asset starts at next cycle")
    
    def get_asset_step(self, asset: str) -> int:
        """Get current step for specific asset - uses global cycle state for new assets"""
        if asset not in self.asset_strategies:
            # New asset starts at current global cycle and step
            self.asset_strategies[asset] = {
                'cycle': self.global_cycle, 
                'step': self.global_step, 
                'amounts': []
            }
        return self.asset_strategies[asset]['step']
    
    def get_asset_cycle(self, asset: str) -> int:
        """Get current cycle for specific asset - uses global cycle state for new assets"""
        if asset not in self.asset_strategies:
            # New asset starts at current global cycle and step
            print(f"🔍 DEBUG: New asset {asset} starting at global C{self.global_cycle}S{self.global_step}")
            self.asset_strategies[asset] = {
                'cycle': self.global_cycle, 
                'step': self.global_step, 
                'amounts': []
            }
        else:
            print(f"🔍 DEBUG: Existing asset {asset} at C{self.asset_strategies[asset]['cycle']}S{self.asset_strategies[asset]['step']} (global: C{self.global_cycle}S{self.global_step})")
        return self.asset_strategies[asset]['cycle']
    
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
        amounts = strategy['amounts']
        
        # Calculate amount based on cycle and step - CORRECTED LOGIC with 4 cycles
        if cycle == 1:
            if step == 1:
                return self.base_amount  # C1S1: $1.00
            else:  # step == 2
                return self.base_amount * self.multiplier  # C1S2: $1.00 × 2.5 = $2.50
        elif cycle == 2:
            # C2S1 = C1S2 × multiplier = $2.50 × 2.5 = $6.25
            # C2S2 = C2S1 × multiplier = $6.25 × 2.5 = $15.625
            if step == 1:
                return self.base_amount * (self.multiplier ** 2)  # C2S1: $1 × 2.5² = $6.25
            else:  # step == 2
                return self.base_amount * (self.multiplier ** 3)  # C2S2: $1 × 2.5³ = $15.625
        elif cycle == 3:
            # C3S1 = C2S2 × multiplier = $15.625 × 2.5 = $39.0625
            # C3S2 = C3S1 × multiplier = $39.0625 × 2.5 = $97.65625
            if step == 1:
                return self.base_amount * (self.multiplier ** 4)  # C3S1: $1 × 2.5⁴ = $39.0625
            else:  # step == 2
                return self.base_amount * (self.multiplier ** 5)  # C3S2: $1 × 2.5⁵ = $97.65625
        elif cycle == 4:
            # C4S1 = C3S2 × multiplier = $97.65625 × 2.5 = $244.140625
            # C4S2 = C4S1 × multiplier = $244.140625 × 2.5 = $610.35156
            if step == 1:
                return self.base_amount * (self.multiplier ** 6)  # C4S1: $1 × 2.5⁶ = $244.140625
            else:  # step == 2
                return self.base_amount * (self.multiplier ** 7)  # C4S2: $1 × 2.5⁷ = $610.35156
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
        
        # Record amount used
        strategy['amounts'].append(trade_amount)
        
        if won:
            print(f"✅ {asset} WIN at C{cycle}S{step}! Resetting global state to C1S1")
            print(f"🔍 DEBUG: Before reset - Global: C{self.global_cycle}S{self.global_step}")
            # WIN resets GLOBAL state to C1S1 - all future assets start at C1S1
            self.global_cycle = 1
            self.global_step = 1
            print(f"🔍 DEBUG: After reset - Global: C{self.global_cycle}S{self.global_step}")
            # Reset this asset's strategy
            strategy['cycle'] = 1
            strategy['step'] = 1
            strategy['amounts'] = []
            return {'action': 'reset', 'asset': asset, 'next_cycle': 1, 'next_step': 1}
        else:
            print(f"❌ {asset} LOSS at C{cycle}S{step}!")
            
            if step < self.max_steps_per_cycle:
                # Move to next step in same cycle (same asset)
                strategy['step'] += 1
                print(f"🔄 Moving to C{cycle}S{strategy['step']} for {asset}")
                return {'action': 'continue', 'asset': asset, 'next_cycle': cycle, 'next_step': strategy['step']}
            else:
                # Step 2 of current cycle lost - advance GLOBAL cycle for NEXT assets
                if cycle < self.max_cycles:
                    # Advance global cycle for next assets
                    self.global_cycle = cycle + 1
                    self.global_step = 1
                    print(f"🔄 {asset} C{cycle}S2 LOST! Next assets will start at C{self.global_cycle}S1")
                    
                    # Mark this asset as completed (no more trades for this asset)
                    strategy['cycle'] = cycle + 1  # For status display
                    strategy['step'] = 1
                    strategy['amounts'] = []
                    return {'action': 'asset_completed', 'asset': asset, 'next_cycle': self.global_cycle, 'next_step': 1}
                else:
                    # All 4 cycles completed - reset global state to C1S1
                    print(f"🔄 {asset} C4S2 LOST! All cycles completed - resetting global state to C1S1")
                    self.global_cycle = 1
                    self.global_step = 1
                    
                    # Reset this asset's strategy
                    strategy['cycle'] = 1
                    strategy['step'] = 1
                    strategy['amounts'] = []
                    return {'action': 'reset_after_max_loss', 'asset': asset, 'next_cycle': 1, 'next_step': 1}
    
    def get_status(self, asset: str) -> str:
        """Get current strategy status for specific asset"""
        if asset not in self.asset_strategies:
            return f"{asset}: C{self.global_cycle}S{self.global_step} (${self.get_current_amount(asset):.2f}) [NEW]"
        
        strategy = self.asset_strategies[asset]
        cycle = strategy['cycle']
        step = strategy['step']
        current_amount = self.get_current_amount(asset)
        return f"{asset}: C{cycle}S{step} (${current_amount:.2f})"
    
    def get_all_active_assets(self) -> List[str]:
        """Get all assets currently being tracked"""
        return list(self.asset_strategies.keys())
    
    def should_prioritize_existing_sequences(self) -> bool:
        """Check if any asset is in the middle of a cycle sequence"""
        for asset, strategy in self.asset_strategies.items():
            if strategy['cycle'] > 1 or strategy['step'] > 1:
                return True
        return False
    
    def show_global_status(self):
        """Show global cycle state"""
        print(f"🌍 Global Cycle State: C{self.global_cycle}S{self.global_step} (new assets start here)")
    
    def show_strategy_status(self):
        """Show current status of all assets and global cycle state"""
        print("📊 Current Strategy Status:")
        print(f"   🌍 Global Cycle State: C{self.global_cycle}S{self.global_step} (new assets start here)")
        
        if not self.asset_strategies:
            print("   📊 No active assets")
            return
            
        print("   📊 Asset Status:")
        for asset, strategy in self.asset_strategies.items():
            cycle = strategy['cycle']
            step = strategy['step']
            current_amount = self.get_current_amount(asset)
            
            if cycle == 1 and step == 1:
                status = "✅ Ready for new signal"
            else:
                status = f"🔄 In cycle sequence"
                
            print(f"      {asset}: C{cycle}S{step} (${current_amount:.2f}) - {status}")
    
    def get_assets_in_sequence(self) -> List[str]:
        """Get assets that are currently in cycle sequence"""
        assets_in_sequence = []
        for asset, strategy in self.asset_strategies.items():
            if strategy['cycle'] > 1 or strategy['step'] > 1:
                assets_in_sequence.append(asset)
        return assets_in_sequence
    
    def get_assets_at_step1(self) -> List[str]:
        """Get assets that are at C1S1 (ready for new signals)"""
        assets_at_step1 = []
        for asset, strategy in self.asset_strategies.items():
            if strategy['cycle'] == 1 and strategy['step'] == 1:
                assets_at_step1.append(asset)
        return assets_at_step1

class FiveCycleMartingaleStrategy:
    """5-Cycle 2-Step Martingale: Extended cycle progression across different assets"""
    
    def __init__(self, base_amount: float, multiplier: float = 2.5):
        self.base_amount = base_amount
        self.multiplier = multiplier
        self.max_cycles = 5  # Extended to 5 cycles
        self.max_steps_per_cycle = 2
        
        # Global cycle state - applies to ALL assets
        self.global_cycle = 1
        self.global_step = 1
        
        # Track each asset separately with cycle and step info
        self.asset_strategies = {}  # {asset: {'cycle': 1, 'step': 1, 'amounts': []}}
        
        # Calculate all amounts for display - CORRECTED with 5 cycles
        c1s1 = base_amount                                    # $1.00
        c1s2 = base_amount * multiplier                       # $2.50
        c2s1 = base_amount * (multiplier ** 2)               # $6.25
        c2s2 = base_amount * (multiplier ** 3)               # $15.625
        c3s1 = base_amount * (multiplier ** 4)               # $39.0625
        c3s2 = base_amount * (multiplier ** 5)               # $97.65625
        c4s1 = base_amount * (multiplier ** 6)               # $244.140625
        c4s2 = base_amount * (multiplier ** 7)               # $610.35156
        c5s1 = base_amount * (multiplier ** 8)               # $1525.87891
        c5s2 = base_amount * (multiplier ** 9)               # $3814.69727
        
        print(f"🎯 5-Cycle 2-Step Martingale Strategy (Cross-Asset Progression)")
        print(f"   Base Amount: ${base_amount}")
        print(f"   Multiplier: {multiplier}")
        print(f"   Max Cycles: {self.max_cycles}")
        print(f"   Steps per Cycle: {self.max_steps_per_cycle}")
        print(f"   Cycle Amounts:")
        print(f"     Cycle 1: Step 1 ${c1s1:.2f} → Step 2 ${c1s2:.2f}")
        print(f"     Cycle 2: Step 1 ${c2s1:.2f} → Step 2 ${c2s2:.2f}")
        print(f"     Cycle 3: Step 1 ${c3s1:.2f} → Step 2 ${c3s2:.2f}")
        print(f"     Cycle 4: Step 1 ${c4s1:.2f} → Step 2 ${c4s2:.2f}")
        print(f"     Cycle 5: Step 1 ${c5s1:.2f} → Step 2 ${c5s2:.2f}")
        print(f"   Strategy: Cycle progression across different assets")
        print(f"   Logic: LOSS at Step 2 → Next asset starts at next cycle")
    
    def get_asset_step(self, asset: str) -> int:
        """Get current step for specific asset - uses global cycle state for new assets"""
        if asset not in self.asset_strategies:
            # New asset starts at current global cycle and step
            self.asset_strategies[asset] = {
                'cycle': self.global_cycle, 
                'step': self.global_step, 
                'amounts': []
            }
        return self.asset_strategies[asset]['step']
    
    def get_asset_cycle(self, asset: str) -> int:
        """Get current cycle for specific asset - uses global cycle state for new assets"""
        if asset not in self.asset_strategies:
            # New asset starts at current global cycle and step
            print(f"🔍 DEBUG: New asset {asset} starting at global C{self.global_cycle}S{self.global_step}")
            self.asset_strategies[asset] = {
                'cycle': self.global_cycle, 
                'step': self.global_step, 
                'amounts': []
            }
        else:
            print(f"🔍 DEBUG: Existing asset {asset} at C{self.asset_strategies[asset]['cycle']}S{self.asset_strategies[asset]['step']} (global: C{self.global_cycle}S{self.global_step})")
        return self.asset_strategies[asset]['cycle']
    
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
        amounts = strategy['amounts']
        
        # Calculate amount based on cycle and step - CORRECTED LOGIC with 5 cycles
        if cycle == 1:
            if step == 1:
                return self.base_amount  # C1S1: $1.00
            else:  # step == 2
                return self.base_amount * self.multiplier  # C1S2: $1.00 × 2.5 = $2.50
        elif cycle == 2:
            # C2S1 = C1S2 × multiplier = $2.50 × 2.5 = $6.25
            # C2S2 = C2S1 × multiplier = $6.25 × 2.5 = $15.625
            if step == 1:
                return self.base_amount * (self.multiplier ** 2)  # C2S1: $1 × 2.5² = $6.25
            else:  # step == 2
                return self.base_amount * (self.multiplier ** 3)  # C2S2: $1 × 2.5³ = $15.625
        elif cycle == 3:
            # C3S1 = C2S2 × multiplier = $15.625 × 2.5 = $39.0625
            # C3S2 = C3S1 × multiplier = $39.0625 × 2.5 = $97.65625
            if step == 1:
                return self.base_amount * (self.multiplier ** 4)  # C3S1: $1 × 2.5⁴ = $39.0625
            else:  # step == 2
                return self.base_amount * (self.multiplier ** 5)  # C3S2: $1 × 2.5⁵ = $97.65625
        elif cycle == 4:
            # C4S1 = C3S2 × multiplier = $97.65625 × 2.5 = $244.140625
            # C4S2 = C4S1 × multiplier = $244.140625 × 2.5 = $610.35156
            if step == 1:
                return self.base_amount * (self.multiplier ** 6)  # C4S1: $1 × 2.5⁶ = $244.140625
            else:  # step == 2
                return self.base_amount * (self.multiplier ** 7)  # C4S2: $1 × 2.5⁷ = $610.35156
        elif cycle == 5:
            # C5S1 = C4S2 × multiplier = $610.35156 × 2.5 = $1525.87891
            # C5S2 = C5S1 × multiplier = $1525.87891 × 2.5 = $3814.69727
            if step == 1:
                return self.base_amount * (self.multiplier ** 8)  # C5S1: $1 × 2.5⁸ = $1525.87891
            else:  # step == 2
                return self.base_amount * (self.multiplier ** 9)  # C5S2: $1 × 2.5⁹ = $3814.69727
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
        
        # Record amount used
        strategy['amounts'].append(trade_amount)
        
        if won:
            print(f"✅ {asset} WIN at C{cycle}S{step}! Resetting global state to C1S1")
            print(f"🔍 DEBUG: Before reset - Global: C{self.global_cycle}S{self.global_step}")
            # WIN resets GLOBAL state to C1S1 - all future assets start at C1S1
            self.global_cycle = 1
            self.global_step = 1
            print(f"🔍 DEBUG: After reset - Global: C{self.global_cycle}S{self.global_step}")
            # Reset this asset's strategy
            strategy['cycle'] = 1
            strategy['step'] = 1
            strategy['amounts'] = []
            return {'action': 'reset', 'asset': asset, 'next_cycle': 1, 'next_step': 1}
        else:
            print(f"❌ {asset} LOSS at C{cycle}S{step}!")
            
            if step < self.max_steps_per_cycle:
                # Move to next step in same cycle (same asset)
                strategy['step'] += 1
                print(f"🔄 Moving to C{cycle}S{strategy['step']} for {asset}")
                return {'action': 'continue', 'asset': asset, 'next_cycle': cycle, 'next_step': strategy['step']}
            else:
                # Step 2 of current cycle lost - advance GLOBAL cycle for NEXT assets
                if cycle < self.max_cycles:
                    # Advance global cycle for next assets
                    self.global_cycle = cycle + 1
                    self.global_step = 1
                    print(f"🔄 {asset} C{cycle}S2 LOST! Next assets will start at C{self.global_cycle}S1")
                    
                    # Mark this asset as completed (no more trades for this asset)
                    strategy['cycle'] = cycle + 1  # For status display
                    strategy['step'] = 1
                    strategy['amounts'] = []
                    return {'action': 'asset_completed', 'asset': asset, 'next_cycle': self.global_cycle, 'next_step': 1}
                else:
                    # All 5 cycles completed - reset global state to C1S1
                    print(f"🔄 {asset} C5S2 LOST! All cycles completed - resetting global state to C1S1")
                    self.global_cycle = 1
                    self.global_step = 1
                    
                    # Reset this asset's strategy
                    strategy['cycle'] = 1
                    strategy['step'] = 1
                    strategy['amounts'] = []
                    return {'action': 'reset_after_max_loss', 'asset': asset, 'next_cycle': 1, 'next_step': 1}
    
    def get_status(self, asset: str) -> str:
        """Get current strategy status for specific asset"""
        if asset not in self.asset_strategies:
            return f"{asset}: C{self.global_cycle}S{self.global_step} (${self.get_current_amount(asset):.2f}) [NEW]"
        
        strategy = self.asset_strategies[asset]
        cycle = strategy['cycle']
        step = strategy['step']
        current_amount = self.get_current_amount(asset)
        return f"{asset}: C{cycle}S{step} (${current_amount:.2f})"
    
    def get_all_active_assets(self) -> List[str]:
        """Get all assets currently being tracked"""
        return list(self.asset_strategies.keys())
    
    def should_prioritize_existing_sequences(self) -> bool:
        """Check if any asset is in the middle of a cycle sequence"""
        for asset, strategy in self.asset_strategies.items():
            if strategy['cycle'] > 1 or strategy['step'] > 1:
                return True
        return False
    
    def show_global_status(self):
        """Show global cycle state"""
        print(f"🌍 Global Cycle State: C{self.global_cycle}S{self.global_step} (new assets start here)")
    
    def show_strategy_status(self):
        """Show current status of all assets and global cycle state"""
        print("📊 Current Strategy Status:")
        print(f"   🌍 Global Cycle State: C{self.global_cycle}S{self.global_step} (new assets start here)")
        
        if not self.asset_strategies:
            print("   📊 No active assets")
            return
            
        print("   📊 Asset Status:")
        for asset, strategy in self.asset_strategies.items():
            cycle = strategy['cycle']
            step = strategy['step']
            current_amount = self.get_current_amount(asset)
            
            if cycle == 1 and step == 1:
                status = "✅ Ready for new signal"
            else:
                status = f"🔄 In cycle sequence"
                
            print(f"      {asset}: C{cycle}S{step} (${current_amount:.2f}) - {status}")
    
    def get_assets_in_sequence(self) -> List[str]:
        """Get assets that are currently in cycle sequence"""
        assets_in_sequence = []
        for asset, strategy in self.asset_strategies.items():
            if strategy['cycle'] > 1 or strategy['step'] > 1:
                assets_in_sequence.append(asset)
        return assets_in_sequence
    
    def get_assets_at_step1(self) -> List[str]:
        """Get assets that are at C1S1 (ready for new signals)"""
        assets_at_step1 = []
        for asset, strategy in self.asset_strategies.items():
            if strategy['cycle'] == 1 and strategy['step'] == 1:
                assets_at_step1.append(asset)
        return assets_at_step1

class ThreeStepMartingaleStrategy:
    """3-Cycle 3-Step Martingale: Extended step progression across different assets"""
    
    def __init__(self, base_amount: float, multiplier: float = 2.5):
        self.base_amount = base_amount
        self.multiplier = multiplier
        self.max_cycles = 3
        self.max_steps_per_cycle = 3  # 3 steps per cycle
        
        # Global cycle state - applies to ALL assets
        self.global_cycle = 1
        self.global_step = 1
        
        # Track each asset separately with cycle and step info
        self.asset_strategies = {}  # {asset: {'cycle': 1, 'step': 1, 'amounts': []}}
        
        # Calculate all amounts for display - 3 cycles × 3 steps
        c1s1 = base_amount                                    # $1.00
        c1s2 = base_amount * multiplier                       # $2.50
        c1s3 = base_amount * (multiplier ** 2)               # $6.25
        c2s1 = base_amount * (multiplier ** 3)               # $15.625
        c2s2 = base_amount * (multiplier ** 4)               # $39.0625
        c2s3 = base_amount * (multiplier ** 5)               # $97.65625
        c3s1 = base_amount * (multiplier ** 6)               # $244.140625
        c3s2 = base_amount * (multiplier ** 7)               # $610.35156
        c3s3 = base_amount * (multiplier ** 8)               # $1525.87891
        
        print(f"🎯 3-Cycle 3-Step Martingale Strategy (Cross-Asset Progression)")
        print(f"   Base Amount: ${base_amount}")
        print(f"   Multiplier: {multiplier}")
        print(f"   Max Cycles: {self.max_cycles}")
        print(f"   Steps per Cycle: {self.max_steps_per_cycle}")
        print(f"   Cycle Amounts:")
        print(f"     Cycle 1: Step 1 ${c1s1:.2f} → Step 2 ${c1s2:.2f} → Step 3 ${c1s3:.2f}")
        print(f"     Cycle 2: Step 1 ${c2s1:.2f} → Step 2 ${c2s2:.2f} → Step 3 ${c2s3:.2f}")
        print(f"     Cycle 3: Step 1 ${c3s1:.2f} → Step 2 ${c3s2:.2f} → Step 3 ${c3s3:.2f}")
        print(f"   Strategy: Cycle progression across different assets")
        print(f"   Logic: LOSS at Step 3 → Next asset starts at next cycle")
    
    def get_asset_step(self, asset: str) -> int:
        """Get current step for specific asset - uses global cycle state for new assets"""
        if asset not in self.asset_strategies:
            # New asset starts at current global cycle and step
            self.asset_strategies[asset] = {
                'cycle': self.global_cycle, 
                'step': self.global_step, 
                'amounts': []
            }
        return self.asset_strategies[asset]['step']
    
    def get_asset_cycle(self, asset: str) -> int:
        """Get current cycle for specific asset - uses global cycle state for new assets"""
        if asset not in self.asset_strategies:
            # New asset starts at current global cycle and step
            print(f"🔍 DEBUG: New asset {asset} starting at global C{self.global_cycle}S{self.global_step}")
            self.asset_strategies[asset] = {
                'cycle': self.global_cycle, 
                'step': self.global_step, 
                'amounts': []
            }
        else:
            print(f"🔍 DEBUG: Existing asset {asset} at C{self.asset_strategies[asset]['cycle']}S{self.asset_strategies[asset]['step']} (global: C{self.global_cycle}S{self.global_step})")
        return self.asset_strategies[asset]['cycle']
    
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
        
        # Calculate amount based on cycle and step - 3 cycles × 3 steps
        if cycle == 1:
            if step == 1:
                return self.base_amount  # C1S1: $1.00
            elif step == 2:
                return self.base_amount * self.multiplier  # C1S2: $1.00 × 2.5 = $2.50
            else:  # step == 3
                return self.base_amount * (self.multiplier ** 2)  # C1S3: $1.00 × 2.5² = $6.25
        elif cycle == 2:
            if step == 1:
                return self.base_amount * (self.multiplier ** 3)  # C2S1: $1 × 2.5³ = $15.625
            elif step == 2:
                return self.base_amount * (self.multiplier ** 4)  # C2S2: $1 × 2.5⁴ = $39.0625
            else:  # step == 3
                return self.base_amount * (self.multiplier ** 5)  # C2S3: $1 × 2.5⁵ = $97.65625
        elif cycle == 3:
            if step == 1:
                return self.base_amount * (self.multiplier ** 6)  # C3S1: $1 × 2.5⁶ = $244.140625
            elif step == 2:
                return self.base_amount * (self.multiplier ** 7)  # C3S2: $1 × 2.5⁷ = $610.35156
            else:  # step == 3
                return self.base_amount * (self.multiplier ** 8)  # C3S3: $1 × 2.5⁸ = $1525.87891
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
        
        # Record amount used
        strategy['amounts'].append(trade_amount)
        
        if won:
            print(f"✅ {asset} WIN at C{cycle}S{step}! Resetting global state to C1S1")
            print(f"🔍 DEBUG: Before reset - Global: C{self.global_cycle}S{self.global_step}")
            # WIN resets GLOBAL state to C1S1 - all future assets start at C1S1
            self.global_cycle = 1
            self.global_step = 1
            print(f"🔍 DEBUG: After reset - Global: C{self.global_cycle}S{self.global_step}")
            # Reset this asset's strategy
            strategy['cycle'] = 1
            strategy['step'] = 1
            strategy['amounts'] = []
            return {'action': 'reset', 'asset': asset, 'next_cycle': 1, 'next_step': 1}
        else:
            print(f"❌ {asset} LOSS at C{cycle}S{step}!")
            
            if step < self.max_steps_per_cycle:
                # Move to next step in same cycle (same asset)
                strategy['step'] += 1
                print(f"🔄 Moving to C{cycle}S{strategy['step']} for {asset}")
                return {'action': 'continue', 'asset': asset, 'next_cycle': cycle, 'next_step': strategy['step']}
            else:
                # Step 3 of current cycle lost - advance GLOBAL cycle for NEXT assets
                if cycle < self.max_cycles:
                    # Advance global cycle for next assets
                    self.global_cycle = cycle + 1
                    self.global_step = 1
                    print(f"🔄 {asset} C{cycle}S3 LOST! Next assets will start at C{self.global_cycle}S1")
                    
                    # Mark this asset as completed (no more trades for this asset)
                    strategy['cycle'] = cycle + 1  # For status display
                    strategy['step'] = 1
                    strategy['amounts'] = []
                    return {'action': 'asset_completed', 'asset': asset, 'next_cycle': self.global_cycle, 'next_step': 1}
                else:
                    # All 3 cycles completed - reset global state to C1S1
                    print(f"🔄 {asset} C3S3 LOST! All cycles completed - resetting global state to C1S1")
                    self.global_cycle = 1
                    self.global_step = 1
                    
                    # Reset this asset's strategy
                    strategy['cycle'] = 1
                    strategy['step'] = 1
                    strategy['amounts'] = []
                    return {'action': 'reset_after_max_loss', 'asset': asset, 'next_cycle': 1, 'next_step': 1}
    
    def get_status(self, asset: str) -> str:
        """Get current strategy status for specific asset"""
        if asset not in self.asset_strategies:
            return f"{asset}: C{self.global_cycle}S{self.global_step} (${self.get_current_amount(asset):.2f}) [NEW]"
        
        strategy = self.asset_strategies[asset]
        cycle = strategy['cycle']
        step = strategy['step']
        current_amount = self.get_current_amount(asset)
        return f"{asset}: C{cycle}S{step} (${current_amount:.2f})"
    
    def get_all_active_assets(self) -> List[str]:
        """Get all assets currently being tracked"""
        return list(self.asset_strategies.keys())
    
    def should_prioritize_existing_sequences(self) -> bool:
        """Check if any asset is in the middle of a cycle sequence"""
        for asset, strategy in self.asset_strategies.items():
            if strategy['cycle'] > 1 or strategy['step'] > 1:
                return True
        return False
    
    def show_global_status(self):
        """Show global cycle state"""
        print(f"🌍 Global Cycle State: C{self.global_cycle}S{self.global_step} (new assets start here)")
    
    def show_strategy_status(self):
        """Show current status of all assets and global cycle state"""
        print("📊 Current Strategy Status:")
        print(f"   🌍 Global Cycle State: C{self.global_cycle}S{self.global_step} (new assets start here)")
        
        if not self.asset_strategies:
            print("   📊 No active assets")
            return
            
        print("   📊 Asset Status:")
        for asset, strategy in self.asset_strategies.items():
            cycle = strategy['cycle']
            step = strategy['step']
            current_amount = self.get_current_amount(asset)
            
            if cycle == 1 and step == 1:
                status = "✅ Ready for new signal"
            else:
                status = f"🔄 In cycle sequence"
                
            print(f"      {asset}: C{cycle}S{step} (${current_amount:.2f}) - {status}")
    
    def get_assets_in_sequence(self) -> List[str]:
        """Get assets that are currently in cycle sequence"""
        assets_in_sequence = []
        for asset, strategy in self.asset_strategies.items():
            if strategy['cycle'] > 1 or strategy['step'] > 1:
                assets_in_sequence.append(asset)
        return assets_in_sequence
    
    def get_assets_at_step1(self) -> List[str]:
        """Get assets that are at C1S1 (ready for new signals)"""
        assets_at_step1 = []
        for asset, strategy in self.asset_strategies.items():
            if strategy['cycle'] == 1 and strategy['step'] == 1:
                assets_at_step1.append(asset)
        return assets_at_step1

class MultiAssetPreciseTrader:
    """Multi-asset trader with immediate step progression and stop loss/take profit"""
    
    def __init__(self, stop_loss: float = None, take_profit: float = None):
        self.ssid = os.getenv('SSID')
        self.client = None
        
        # Stop Loss and Take Profit settings
        self.stop_loss = stop_loss  # Maximum loss in dollars before stopping
        self.take_profit = take_profit  # Target profit in dollars before stopping
        self.session_profit = 0.0  # Track session profit/loss
        
        # Load trade timing offset from config file
        self.trade_offset_seconds = 0  # Always execute exactly at signal time
        
        # Channel selection and trade duration settings (simplified)
        self.active_channel = None  # Will be set by user
        self.james_martin_free_duration = 300  # 5:00 for James Martin Free Channel
        
        # Use date-based CSV filename - support new channel only
        # Will be auto-updated to find latest available CSV
        self.james_martin_free_csv = None
        self.current_csv_date = None
        self._update_csv_filenames(show_info=True)
        
        self.trade_history = []
        self.pending_immediate_trades = []  # Queue for immediate next step trades
        self.executed_signals = set()  # Track executed signal combinations to prevent duplicates
        
        # API health tracking
        self.api_failures = 0
        self.max_api_failures = 3  # System will fail after 3 consecutive failures
        self.last_successful_api_call = get_user_time()
        
        # Available assets - VERIFIED WORKING (75/78 assets tested and confirmed)
        # Updated: 2026-01-15 - Bulk tested with 96.2% success rate
        self.WORKING_ASSETS = {
            # Major pairs (direct format) - All verified working
            'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'USDCAD', 'AUDUSD',
            # Cross pairs (direct format) - All verified working
            'AUDCAD', 'AUDCHF', 'AUDJPY', 'CADCHF', 'CADJPY', 'CHFJPY',
            'EURAUD', 'EURCAD', 'EURCHF', 'EURGBP', 'EURJPY',
            'GBPAUD', 'GBPCAD', 'GBPCHF', 'GBPJPY',
            # OTC pairs - All verified working
            'AEDCNY', 'AUDNZD', 'BHDCNY', 'CHFNOK', 'EURHUF', 'EURNZD', 'EURTRY',
            'JODCNY', 'KESUSD', 'LBPUSD', 'MADUSD', 'NGNUSD', 'NZDJPY', 'NZDUSD',
            'OMRCNY', 'QARCNY', 'SARCNY', 'TNDUSD', 'UAHUSD',
            'USDARS', 'USDBDT', 'USDBRL', 'USDCLP', 'USDCNH', 'USDCOP',
            'USDDZD', 'USDEGP', 'USDIDR', 'USDINR', 'USDMXN', 'USDMYR',
            'USDPHP', 'USDPKR', 'USDRUB', 'USDSGD', 'USDTHB', 'ZARUSD'
        }
        
        # Assets that don't work (only 3 out of 78)
        self.UNSUPPORTED_ASSETS = {
            'EURRUB',    # Russian Ruble - sanctioned/restricted
            'YERUSD',    # Yemeni Rial - extremely low liquidity
            'USDVND'     # Vietnamese Dong - limited availability
        }
        
        print(f"📊 James Martin Free Channel CSV: {self.james_martin_free_csv}")
        print(f"⏰ Trade Duration: James Martin Free Channel (5:00)")
        print(f"🎯 Active Channel: {self.active_channel or 'Not selected'}")
        print(f"⏱️  Execution: Exactly at signal time + 10ms")
        
        # Display stop loss and take profit settings
        if self.stop_loss is not None:
            print(f"🛑 Stop Loss: ${self.stop_loss:.2f}")
        else:
            print(f"🛑 Stop Loss: Disabled")
            
        if self.take_profit is not None:
            print(f"🎯 Take Profit: ${self.take_profit:.2f}")
        else:
            print(f"🎯 Take Profit: Disabled")
    
    
    def _update_csv_filenames(self, show_info: bool = False):
        """Set fixed CSV filenames for the new channel (no date-based naming)"""
        # Use FIXED CSV filename that matches simple_monitor.py exactly
        self.james_martin_free_csv = "pocketoption_james_martin_free_channel.csv"
        
        # Only show detailed info when requested (during initialization)
        if show_info:
            # Show only the selected channel's CSV file, not all channels
            if self.active_channel:
                # Get the selected channel's CSV file and details
                if self.active_channel == "james_martin_free":
                    selected_csv = self.james_martin_free_csv
                    selected_name = "James Martin Free Channel"
                else:
                    selected_csv = None
                    selected_name = "Unknown"
                
                if selected_csv:
                    print(f"📊 Using CSV file for selected channel:")
                    if os.path.exists(selected_csv):
                        # Get file size and modification time
                        file_size = os.path.getsize(selected_csv)
                        mod_time = datetime.fromtimestamp(os.path.getmtime(selected_csv)).strftime('%Y-%m-%d %H:%M:%S')
                        print(f"   ✅ {selected_name}: {selected_csv} ({file_size} bytes, modified: {mod_time})")
                    else:
                        print(f"   ❌ {selected_name}: {selected_csv} (file not found)")
            else:
                print(f"📊 No channel selected - CSV files available but not loaded")
        
        # Set current date for tracking (but don't use in filenames)
        self.current_csv_date = datetime.now().strftime('%Y-%m-%d')
    
    def _validate_duration(self, duration: int, channel: str = None) -> int:
        """Simple duration validation - return as-is"""
        return duration
    
    def get_channel_duration(self, channel: str) -> int:
        """Get duration in seconds for specific channel"""
        if channel == "james_martin_free":
            return self.james_martin_free_duration
        else:
            return 300  # Default fallback (5:00)
    
    def should_use_api(self, asset: str) -> bool:
        """Check if API is available and connected"""
        if not self.client:
            raise Exception("API client not connected - fix connection")
            
        if not self.ssid:
            raise Exception("SSID not available - get fresh SSID")
        
        return True
    
    def record_api_success(self):
        """Record successful API call"""
        self.api_failures = 0
        self.last_successful_api_call = get_user_time()
    
    def record_api_failure(self):
        """Record API failure with improved handling"""
        self.api_failures += 1
        print(f"⚠️ API failure recorded ({self.api_failures}/{self.max_api_failures})")
        
        if self.api_failures >= self.max_api_failures:
            print(f"❌ API health degraded ({self.api_failures} failures)")
            print(f"🔄 Continuing with reduced API calls and longer timeouts")
            # Don't stop the system, just reduce API aggressiveness
    
    def update_session_profit(self, profit: float):
        """Update session profit and check stop loss/take profit conditions"""
        self.session_profit += profit
        
        # Display current session status
        if profit > 0:
            print(f"💰 Session P&L: ${self.session_profit:+.2f} (+${profit:.2f})")
        else:
            print(f"💰 Session P&L: ${self.session_profit:+.2f} (${profit:+.2f})")
    
    def should_stop_trading(self) -> Tuple[bool, str]:
        """Check if trading should stop due to stop loss or take profit"""
        # Check stop loss
        if self.stop_loss is not None and self.session_profit <= -self.stop_loss:
            return True, f"🛑 STOP LOSS REACHED: ${self.session_profit:+.2f} (limit: -${self.stop_loss:.2f})"
        
        # Check take profit
        if self.take_profit is not None and self.session_profit >= self.take_profit:
            return True, f"🎯 TAKE PROFIT REACHED: ${self.session_profit:+.2f} (target: +${self.take_profit:.2f})"
        
        return False, ""
    
    def get_session_status(self) -> str:
        """Get current session status with stop loss/take profit info"""
        status = f"Session P&L: ${self.session_profit:+.2f}"
        
        if self.stop_loss is not None:
            remaining_loss = self.stop_loss + self.session_profit
            status += f" | Stop Loss: ${remaining_loss:.2f} remaining"
        
        if self.take_profit is not None:
            remaining_profit = self.take_profit - self.session_profit
            status += f" | Take Profit: ${remaining_profit:.2f} to go"
        
        return status
    
    async def connect(self, is_demo: bool = True) -> bool:
        """Connect to PocketOption"""
        try:
            print("🔌 Connecting to PocketOption...")
            
            if self.ssid:
                print(f"🔑 Using SSID: {self.ssid[:50]}...")
                
                self.client = AsyncPocketOptionClient(
                    ssid=self.ssid,
                    is_demo=is_demo,
                    persistent_connection=False,
                    auto_reconnect=False,
                    enable_logging=False
                )
                
                try:
                    await asyncio.wait_for(self.client.connect(), timeout=15.0)
                    balance = await asyncio.wait_for(self.client.get_balance(), timeout=10.0)
                    
                    print(f"✅ Connected! {'DEMO' if is_demo else 'REAL'} Account")
                    print(f"💰 Balance: ${balance.balance:.2f}")
                    return True
                    
                except Exception as conn_error:
                    print(f"❌ Connection failed: {conn_error}")
                    self.client = None
                    raise Exception(f"Connection failed: {conn_error}")
            else:
                print(f"❌ No SSID provided")
                raise Exception("No SSID provided")
            
        except Exception as e:
            print(f"❌ Connection error: {e}")
            self.client = None
            raise Exception(f"Connection error: {e}")
    
    def get_signals_from_csv(self, target_date: str = None) -> List[Dict[str, Any]]:
        """Get trading signals from selected channel CSV file with date filtering and current time focus"""
        try:
            # Update CSV filenames in case date has changed
            self._update_csv_filenames()
            
            # Determine which CSV file to use based on active channel
            if self.active_channel == "james_martin_free":
                csv_file = self.james_martin_free_csv
                trade_duration = self.james_martin_free_duration
                channel_name = "James Martin Free Channel"
            else:
                return []
            
            if not os.path.exists(csv_file):
                return []
            
            df = pd.read_csv(csv_file, on_bad_lines='skip')
            
            if 'is_signal' in df.columns:
                signals_df = df[df['is_signal'] == 'Yes'].copy()
            else:
                signals_df = df.copy()
            
            if signals_df.empty:
                return []
            
            # Get current time for filtering
            current_time = get_user_time()
            current_date_str = current_time.strftime('%Y-%m-%d')
            
            # Use current date for signal filtering
            filter_date_str = current_date_str
            
            signals = []
            
            for _, row in signals_df.iterrows():
                try:
                    asset = str(row.get('asset', '')).strip()
                    direction = str(row.get('direction', '')).strip().lower()
                    signal_time_str = str(row.get('signal_time', '')).strip()
                    
                    if not asset or not direction or not signal_time_str or signal_time_str == 'nan':
                        continue
                    
                    # Use EXACT asset name from CSV - no modifications
                    trading_asset = asset
                    
                    if direction not in ['call', 'put']:
                        continue
                    
                    # Parse signal time
                    try:
                        if signal_time_str.count(':') == 2:
                            signal_time = datetime.strptime(signal_time_str, '%H:%M:%S')
                        elif signal_time_str.count(':') == 1:
                            signal_time = datetime.strptime(signal_time_str, '%H:%M')
                        elif '.' in signal_time_str:
                            signal_time = datetime.strptime(signal_time_str.replace('.', ':'), '%H:%M')
                        else:
                            # If signal_time is invalid, skip this signal
                            print(f"⚠️ Invalid signal time format: {signal_time_str} for {asset}")
                            continue
                        
                        # Create signal datetime for the target date
                        signal_date = datetime.strptime(filter_date_str, '%Y-%m-%d').date()
                        signal_datetime = datetime.combine(signal_date, datetime.min.time().replace(
                            hour=signal_time.hour,
                            minute=signal_time.minute,
                            second=signal_time.second if signal_time_str.count(':') == 2 else 0
                        ))
                        
                        # Convert to user timezone
                        if USER_TIMEZONE:
                            signal_datetime = signal_datetime.replace(tzinfo=USER_TIMEZONE)
                        
                        # Only include upcoming signals (future or current time)
                        time_until_signal = (signal_datetime - current_time).total_seconds()
                        if time_until_signal < -60:  # Signal was more than 1 minute ago - skip it
                            continue
                        
                        # Execute exactly at signal time (no offset)
                        trade_datetime = signal_datetime
                        
                        # Use channel-specific duration
                        duration_seconds = trade_duration
                        
                        close_datetime = trade_datetime + timedelta(seconds=duration_seconds)
                        
                    except ValueError as e:
                        print(f"⚠️ Signal time parsing error for {asset}: {signal_time_str} - {e}")
                        continue
                    
                    signal = {
                        'asset': trading_asset,
                        'direction': direction,
                        'signal_time': signal_time_str,
                        'signal_datetime': signal_datetime,
                        'trade_datetime': trade_datetime,  # exactly at signal time
                        'close_datetime': close_datetime,  # channel-specific duration
                        'timestamp': get_user_time().isoformat(),
                        'message_text': str(row.get('message_text', ''))[:100],
                        'channel': self.active_channel,
                        'duration': duration_seconds,  # Channel-specific duration
                        'date_filter': filter_date_str
                    }
                    
                    # Add all valid signals (will be filtered by readiness in main loop)
                    signals.append(signal)
                    
                except Exception:
                    continue
            
            # Sort by trade execution time
            signals.sort(key=lambda x: x['trade_datetime'])
            
            # Remove duplicate signals (same asset+direction+time) to prevent multiple executions
            unique_signals = []
            seen_combinations = set()
            for signal in signals:
                signal_key = f"{signal['asset']}_{signal['direction']}_{signal['signal_datetime'].strftime('%H:%M:%S')}"
                if signal_key not in seen_combinations:
                    unique_signals.append(signal)
                    seen_combinations.add(signal_key)
            
            # Return unique signals only
            return unique_signals
            
        except Exception as e:
            logger.error(f"Error reading CSV: {e}")
            return []
    
    def _map_asset_name(self, csv_asset: str) -> str:
        """
        Convert exact asset names from CSV to PocketOption API format.
        Input: EURJPY, EURJPY-OTC, AUDCAD-OTC, AUDCAD_otc, etc.
        Output: EURJPY, EURJPY, AUDCAD_otc, AUDCAD_otc, etc.
        """
        asset = csv_asset.strip()
        
        # If asset already has _otc suffix (from PO ADVANCE BOT), use as-is
        if asset.endswith('_otc'):
            return asset  # Return AUDCAD_otc as-is
        
        # If asset has -OTC or -OTCp suffix, remove it and decide format
        if asset.endswith('-OTC') or asset.endswith('-OTCp'):
            base_asset = asset.split('-')[0]  # Get EURJPY from EURJPY-OTC
            
            # Major pairs that should use regular format (no _otc)
            MAJOR_PAIRS = {
                'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'USDCAD', 'AUDUSD',
                'EURJPY', 'EURGBP', 'GBPJPY', 'AUDJPY', 'NZDUSD'
            }
            
            if base_asset in MAJOR_PAIRS:
                return base_asset  # Return EURJPY (regular format)
            else:
                return f"{base_asset}_otc"  # Return AUDCAD_otc (OTC format)
        else:
            # Asset without -OTC suffix, use as-is
            return asset
    
    async def execute_single_4cycle_trade(self, asset: str, direction: str, base_amount: float, strategy: 'FourCycleMartingaleStrategy', channel: str = None) -> Tuple[bool, float, str]:
        """Execute a single trade in the 4-cycle 2-step sequence and return next action"""
        current_cycle = strategy.get_asset_cycle(asset)
        current_step = strategy.get_asset_step(asset)
        step_amount = strategy.get_current_amount(asset)
        
        print(f"📊 C{current_cycle}S{current_step}: {asset} {direction.upper()} ${step_amount}")
        print(f"⏱️  Trade execution at: {get_user_time_str()}")
        
        try:
            # Execute trade based on step
            if current_step == 1:
                # For Step 1, use precise timing with channel-specific duration
                duration_seconds = self.get_channel_duration(channel or self.active_channel)
                won, profit = await self.execute_precise_trade({
                    'asset': asset,
                    'direction': direction,
                    'trade_datetime': get_user_time(),
                    'signal_datetime': get_user_time(),
                    'close_datetime': get_user_time() + timedelta(seconds=duration_seconds),
                    'channel': channel or self.active_channel,
                    'duration': duration_seconds
                }, step_amount)
            else:
                # For Step 2, execute immediately
                won, profit = await self.execute_immediate_trade(asset, direction, step_amount, channel or self.active_channel)
            
            # Record result and get next action
            next_action = strategy.record_result(won, asset, step_amount)
            
            if won:
                print(f"✅ {asset} WIN at C{current_cycle}S{current_step}! Profit: ${profit:+.2f}")
                return True, profit, 'completed'
            else:
                print(f"❌ {asset} LOSS at C{current_cycle}S{current_step}! Loss: ${profit:+.2f}")
                
                if next_action['action'] == 'continue':
                    # Move to next step in same cycle (same asset)
                    print(f"🔄 Moving to C{current_cycle}S{next_action['next_step']} for {asset}")
                    return False, profit, 'continue'
                elif next_action['action'] == 'asset_completed':
                    # Asset completed - no more trades for this asset
                    print(f"🔄 {asset} completed - cycle advanced for next assets")
                    return False, profit, 'completed'
                elif next_action['action'] in ['reset', 'reset_after_max_loss']:
                    # Strategy reset
                    print(f"🔄 {asset} - Strategy reset for next signal")
                    return False, profit, 'completed'
                else:
                    print(f"🚨 {asset} - Unexpected action: {next_action['action']}")
                    return False, profit, 'completed'
                    
        except Exception as e:
            print(f"❌ C{current_cycle}S{current_step} error for {asset}: {e}")
            # Record as loss
            strategy.record_result(False, asset, step_amount)
            return False, -step_amount, 'error'

    async def execute_single_5cycle_trade(self, asset: str, direction: str, base_amount: float, strategy: 'FiveCycleMartingaleStrategy', channel: str = None) -> Tuple[bool, float, str]:
        """Execute a single trade in the 5-cycle 2-step sequence and return next action"""
        current_cycle = strategy.get_asset_cycle(asset)
        current_step = strategy.get_asset_step(asset)
        step_amount = strategy.get_current_amount(asset)
        
        print(f"📊 C{current_cycle}S{current_step}: {asset} {direction.upper()} ${step_amount}")
        print(f"⏱️  Trade execution at: {get_user_time_str()}")
        
        try:
            # Execute trade based on step
            if current_step == 1:
                # For Step 1, use precise timing with channel-specific duration
                duration_seconds = self.get_channel_duration(channel or self.active_channel)
                won, profit = await self.execute_precise_trade({
                    'asset': asset,
                    'direction': direction,
                    'trade_datetime': get_user_time(),
                    'signal_datetime': get_user_time(),
                    'close_datetime': get_user_time() + timedelta(seconds=duration_seconds),
                    'channel': channel or self.active_channel,
                    'duration': duration_seconds
                }, step_amount)
            else:
                # For Step 2, execute immediately
                won, profit = await self.execute_immediate_trade(asset, direction, step_amount, channel or self.active_channel)
            
            # Record result and get next action
            next_action = strategy.record_result(won, asset, step_amount)
            
            if won:
                print(f"✅ {asset} WIN at C{current_cycle}S{current_step}! Profit: ${profit:+.2f}")
                return True, profit, 'completed'
            else:
                print(f"❌ {asset} LOSS at C{current_cycle}S{current_step}! Loss: ${profit:+.2f}")
                
                if next_action['action'] == 'continue':
                    # Move to next step in same cycle (same asset)
                    print(f"🔄 Moving to C{current_cycle}S{next_action['next_step']} for {asset}")
                    return False, profit, 'continue'
                elif next_action['action'] == 'asset_completed':
                    # Asset completed - no more trades for this asset
                    print(f"🔄 {asset} completed - cycle advanced for next assets")
                    return False, profit, 'completed'
                elif next_action['action'] in ['reset', 'reset_after_max_loss']:
                    # Strategy reset
                    print(f"🔄 {asset} - Strategy reset for next signal")
                    return False, profit, 'completed'
                else:
                    print(f"🚨 {asset} - Unexpected action: {next_action['action']}")
                    return False, profit, 'completed'
                    
        except Exception as e:
            print(f"❌ C{current_cycle}S{current_step} error for {asset}: {e}")
            # Record as loss
            strategy.record_result(False, asset, step_amount)
            return False, -step_amount, 'error'

    async def execute_single_2step_trade(self, asset: str, direction: str, base_amount: float, strategy: 'TwoStepMartingaleStrategy', channel: str = None) -> Tuple[bool, float, str]:
        """Execute a single trade in the 2-step sequence and return next action"""
        current_cycle = strategy.get_asset_cycle(asset)
        current_step = strategy.get_asset_step(asset)
        step_amount = strategy.get_current_amount(asset)
        
        print(f"📊 C{current_cycle}S{current_step}: {asset} {direction.upper()} ${step_amount}")
        print(f"⏱️  Trade execution at: {get_user_time_str()}")
        
        try:
            # Execute trade based on step
            if current_step == 1:
                # For Step 1, use precise timing
                won, profit = await self.execute_precise_trade({
                    'asset': asset,
                    'direction': direction,
                    'trade_datetime': get_user_time(),
                    'signal_datetime': get_user_time(),
                    'close_datetime': get_user_time() + timedelta(seconds=60),
                    'channel': channel or self.active_channel,
                    'duration': 60
                }, step_amount)
            else:
                # For Step 2, execute immediately
                won, profit = await self.execute_immediate_trade(asset, direction, step_amount, channel or self.active_channel)
            
            # Record result and get next action
            next_action = strategy.record_result(won, asset, step_amount)
            
            if won:
                print(f"✅ {asset} WIN at C{current_cycle}S{current_step}! Profit: ${profit:+.2f}")
                return True, profit, 'completed'
            else:
                print(f"❌ {asset} LOSS at C{current_cycle}S{current_step}! Loss: ${profit:+.2f}")
                
                if next_action['action'] == 'continue':
                    # Move to next step in same cycle (same asset)
                    print(f"🔄 Moving to C{current_cycle}S{next_action['next_step']} for {asset}")
                    return False, profit, 'continue'
                elif next_action['action'] == 'asset_completed':
                    # Asset completed - no more trades for this asset
                    print(f"🔄 {asset} completed - cycle advanced for next assets")
                    return False, profit, 'completed'
                elif next_action['action'] in ['reset', 'reset_after_max_loss']:
                    # Strategy reset
                    print(f"🔄 {asset} - Strategy reset for next signal")
                    return False, profit, 'completed'
                else:
                    print(f"🚨 {asset} - Unexpected action: {next_action['action']}")
                    return False, profit, 'completed'
                    
        except Exception as e:
            print(f"❌ C{current_cycle}S{current_step} error for {asset}: {e}")
            # Record as loss
            strategy.record_result(False, asset, step_amount)
            return False, -step_amount, 'error'
    
    async def execute_single_3step_trade(self, asset: str, direction: str, base_amount: float, strategy: 'ThreeStepMartingaleStrategy', channel: str = None) -> Tuple[bool, float, str]:
        """Execute a single trade in the 3-step sequence and return next action"""
        current_cycle = strategy.get_asset_cycle(asset)
        current_step = strategy.get_asset_step(asset)
        step_amount = strategy.get_current_amount(asset)
        
        print(f"📊 C{current_cycle}S{current_step}: {asset} {direction.upper()} ${step_amount}")
        print(f"⏱️  Trade execution at: {get_user_time_str()}")
        
        try:
            # Execute trade based on step
            if current_step == 1:
                # For Step 1, use precise timing
                won, profit = await self.execute_precise_trade({
                    'asset': asset,
                    'direction': direction,
                    'trade_datetime': get_user_time(),
                    'signal_datetime': get_user_time(),
                    'close_datetime': get_user_time() + timedelta(seconds=60),
                    'channel': channel or self.active_channel,
                    'duration': 60
                }, step_amount)
            else:
                # For Step 2 and 3, execute immediately
                won, profit = await self.execute_immediate_trade(asset, direction, step_amount, channel or self.active_channel)
            
            # Record result and get next action
            next_action = strategy.record_result(won, asset, step_amount)
            
            if won:
                print(f"✅ {asset} WIN at C{current_cycle}S{current_step}! Profit: ${profit:+.2f}")
                return True, profit, 'completed'
            else:
                print(f"❌ {asset} LOSS at C{current_cycle}S{current_step}! Loss: ${profit:+.2f}")
                
                if next_action['action'] == 'continue':
                    # Move to next step in same cycle (same asset)
                    print(f"🔄 Moving to C{current_cycle}S{next_action['next_step']} for {asset}")
                    return False, profit, 'continue'
                elif next_action['action'] == 'asset_completed':
                    # Asset completed - no more trades for this asset
                    print(f"🔄 {asset} completed - cycle advanced for next assets")
                    return False, profit, 'completed'
                elif next_action['action'] in ['reset', 'reset_after_max_loss']:
                    # Strategy reset
                    print(f"🔄 {asset} - Strategy reset for next signal")
                    return False, profit, 'completed'
                else:
                    print(f"🚨 {asset} - Unexpected action: {next_action['action']}")
                    return False, profit, 'completed'
                    
        except Exception as e:
            print(f"❌ C{current_cycle}S{current_step} error for {asset}: {e}")
            # Record as loss
            strategy.record_result(False, asset, step_amount)
            return False, -step_amount, 'error'

    async def execute_single_2cycle_2step_trade(self, asset: str, direction: str, base_amount: float, strategy: 'TwoCycleTwoStepMartingaleStrategy', channel: str = None) -> Tuple[bool, float, str]:
        """Execute a single trade in the 2-cycle 2-step sequence and return next action"""
        current_cycle = strategy.get_asset_cycle(asset)
        current_step = strategy.get_asset_step(asset)
        step_amount = strategy.get_current_amount(asset)
        
        print(f"📊 C{current_cycle}S{current_step}: {asset} {direction.upper()} ${step_amount}")
        print(f"⏱️  Trade execution at: {get_user_time_str()}")
        
        try:
            # Execute trade based on step
            if current_step == 1:
                # For Step 1, use precise timing
                won, profit = await self.execute_precise_trade({
                    'asset': asset,
                    'direction': direction,
                    'trade_datetime': get_user_time(),
                    'signal_datetime': get_user_time(),
                    'close_datetime': get_user_time() + timedelta(seconds=60),
                    'channel': channel or self.active_channel,
                    'duration': 60
                }, step_amount)
            else:
                # For Step 2, execute immediately
                won, profit = await self.execute_immediate_trade(asset, direction, step_amount, channel or self.active_channel)
            
            # Record result and get next action
            next_action = strategy.record_result(won, asset, step_amount)
            
            if won:
                print(f"✅ {asset} WIN at C{current_cycle}S{current_step}! Profit: ${profit:+.2f}")
                return True, profit, 'completed'
            else:
                print(f"❌ {asset} LOSS at C{current_cycle}S{current_step}! Loss: ${profit:+.2f}")
                
                if next_action['action'] == 'continue':
                    # Move to next step in same cycle (same asset)
                    print(f"🔄 Moving to C{current_cycle}S{next_action['next_step']} for {asset}")
                    return False, profit, 'continue'
                elif next_action['action'] == 'asset_completed':
                    # Asset completed - no more trades for this asset
                    print(f"🔄 {asset} completed - cycle advanced for next assets")
                    return False, profit, 'completed'
                elif next_action['action'] in ['reset', 'reset_after_max_loss']:
                    # Strategy reset
                    print(f"🔄 {asset} - Strategy reset for next signal")
                    return False, profit, 'completed'
                else:
                    print(f"🚨 {asset} - Unexpected action: {next_action['action']}")
                    return False, profit, 'completed'
                    
        except Exception as e:
            print(f"❌ C{current_cycle}S{current_step} error for {asset}: {e}")
            # Record as loss
            strategy.record_result(False, asset, step_amount)
            return False, -step_amount, 'error'

    async def execute_single_2cycle_3step_trade(self, asset: str, direction: str, base_amount: float, strategy: 'TwoCycleThreeStepMartingaleStrategy', channel: str = None) -> Tuple[bool, float, str]:
        """Execute a single trade in the 2-cycle 3-step sequence and return next action"""
        current_cycle = strategy.get_asset_cycle(asset)
        current_step = strategy.get_asset_step(asset)
        step_amount = strategy.get_current_amount(asset)
        
        print(f"📊 C{current_cycle}S{current_step}: {asset} {direction.upper()} ${step_amount}")
        print(f"⏱️  Trade execution at: {get_user_time_str()}")
        
        # Special display for Step 4 (C2S1) which uses sum of first 3 steps
        if current_cycle == 2 and current_step == 1:
            c1s1 = base_amount
            c1s2 = base_amount * strategy.multiplier
            c1s3 = base_amount * (strategy.multiplier ** 2)
            sum_first_3 = c1s1 + c1s2 + c1s3
            print(f"🔢 Step 4 Logic: ${c1s1:.2f} + ${c1s2:.2f} + ${c1s3:.2f} = ${sum_first_3:.2f}")
        
        try:
            # Execute trade based on step
            if current_step == 1:
                # For Step 1, use precise timing
                won, profit = await self.execute_precise_trade({
                    'asset': asset,
                    'direction': direction,
                    'trade_datetime': get_user_time(),
                    'signal_datetime': get_user_time(),
                    'close_datetime': get_user_time() + timedelta(seconds=60),
                    'channel': channel or self.active_channel,
                    'duration': 60
                }, step_amount)
            else:
                # For Step 2 and 3, execute immediately
                won, profit = await self.execute_immediate_trade(asset, direction, step_amount, channel or self.active_channel)
            
            # Record result and get next action
            next_action = strategy.record_result(won, asset, step_amount)
            
            if won:
                print(f"✅ {asset} WIN at C{current_cycle}S{current_step}! Profit: ${profit:+.2f}")
                return True, profit, 'completed'
            else:
                print(f"❌ {asset} LOSS at C{current_cycle}S{current_step}! Loss: ${profit:+.2f}")
                
                if next_action['action'] == 'continue':
                    # Move to next step in same cycle (same asset)
                    print(f"🔄 Moving to C{current_cycle}S{next_action['next_step']} for {asset}")
                    return False, profit, 'continue'
                elif next_action['action'] == 'asset_completed':
                    # Asset completed - no more trades for this asset
                    print(f"🔄 {asset} completed - cycle advanced for next assets")
                    return False, profit, 'completed'
                elif next_action['action'] in ['reset', 'reset_after_max_loss']:
                    # Strategy reset
                    print(f"🔄 {asset} - Strategy reset for next signal")
                    return False, profit, 'completed'
                else:
                    print(f"🚨 {asset} - Unexpected action: {next_action['action']}")
                    return False, profit, 'completed'
                    
        except Exception as e:
            print(f"❌ C{current_cycle}S{current_step} error for {asset}: {e}")
            # Record as loss
            strategy.record_result(False, asset, step_amount)
            return False, -step_amount, 'error'

    async def execute_complete_martingale_sequence(self, asset: str, direction: str, amount: float, strategy, channel: str = None) -> Tuple[bool, float]:
        """Execute complete martingale sequence for an asset - wait for each step result before proceeding"""
        total_profit = 0.0
        current_step = strategy.get_asset_step(asset)
        
        print(f"🎯 Starting martingale sequence for {asset} {direction.upper()} - Step {current_step}")
        
        while current_step <= strategy.max_steps:
            step_amount = strategy.get_current_amount(asset)
            
            print(f"📊 Step {current_step}: {asset} {direction.upper()} ${step_amount}")
            
            try:
                # Execute trade and WAIT for complete result
                if current_step == 1:
                    # For Step 1, use the signal's scheduled time (if available) or execute immediately
                    duration_seconds = self.get_channel_duration(channel or self.active_channel)
                    won, profit = await self.execute_precise_trade({
                        'asset': asset,
                        'direction': direction,
                        'trade_datetime': get_user_time(),
                        'signal_datetime': get_user_time(),
                        'close_datetime': get_user_time() + timedelta(seconds=duration_seconds),
                        'channel': channel or self.active_channel,
                        'duration': duration_seconds
                    }, step_amount)
                else:
                    # For Steps 2 and 3, execute immediately with channel-specific duration
                    won, profit = await self.execute_immediate_trade(asset, direction, step_amount, channel or self.active_channel)
                
                total_profit += profit
                
                # Record result and get next action
                next_action = strategy.record_result(won, asset, step_amount)
                
                if won:
                    print(f"✅ {asset} WIN at Step {current_step}! Total profit: ${total_profit:+.2f}")
                    return True, total_profit
                else:
                    print(f"❌ {asset} LOSS at Step {current_step}! Loss: ${profit:+.2f}")
                    
                    if next_action['action'] == 'continue':
                        current_step = next_action['next_step']
                        print(f"🔄 Moving to Step {current_step} for {asset}")
                        
                        # Use consistent timing between steps for both channels
                        await asyncio.sleep(0.01)  # 10ms delay for all channels
                        print(f"⏳ 10ms delay before Step {current_step}")
                    elif next_action['action'] == 'reset_after_max_loss':
                        # All 3 steps lost - reset to Step 1 for next signal
                        print(f"🔄 {asset} - All 3 steps lost! Reset to Step 1 for next signal")
                        return False, total_profit
                    else:
                        # Should not reach here, but handle gracefully
                        print(f"🚨 {asset} - Unexpected action: {next_action['action']}")
                        return False, total_profit
                        
            except Exception as e:
                print(f"❌ Step {current_step} error for {asset}: {e}")
                # Record as loss and continue to next step if possible
                next_action = strategy.record_result(False, asset, step_amount)
                total_profit -= step_amount  # Assume full loss
                
                if next_action['action'] == 'continue':
                    current_step = next_action['next_step']
                    print(f"🔄 Error recovery - Moving to Step {current_step} for {asset}")
                    
                    # Use consistent timing after error for both channels
                    await asyncio.sleep(0.01)  # 10ms wait after error for all channels
                elif next_action['action'] == 'reset_after_max_loss':
                    # All 3 steps lost due to errors - reset to Step 1 for next signal
                    print(f"🔄 {asset} - All 3 steps failed due to errors! Reset to Step 1 for next signal")
                    return False, total_profit
                else:
                    print(f"🚨 {asset} - Sequence failed after error! Total loss: ${total_profit:+.2f}")
                    return False, total_profit
        
        # Should not reach here, but handle gracefully
        print(f"🚨 {asset} - Sequence completed without resolution! Total: ${total_profit:+.2f}")
        return False, total_profit
    
    async def execute_immediate_trade(self, asset: str, direction: str, amount: float, channel: str = None) -> Tuple[bool, float]:
        """Execute immediate trade (for steps 2 and 3) with channel-specific duration"""
        try:
            execution_time = get_user_time()
            
            # Use channel-specific duration
            dynamic_duration = self.get_channel_duration(channel or self.active_channel)
            target_close_time = execution_time + timedelta(seconds=dynamic_duration)
            
            # Determine channel name for display
            if channel == "james_martin_free":
                channel_name = "James Martin Free"
            else:
                # Use active channel if not specified
                if self.active_channel == "james_martin_free":
                    channel_name = "James Martin Free"
                else:
                    channel_name = "Default"
            
            print(f"⚡ IMMEDIATE ({channel_name}): {asset} {direction.upper()} ${amount} (60s)")
            print(f"⏱️  Executing at: {get_user_time_str()}")
            print(f"⏰ Close at: {format_time_hmsms(target_close_time)} (60s later)")
            
            if not self.should_use_api(asset):
                print(f"❌ API not available for {asset}")
                raise Exception(f"API not available for {asset}")
            
            try:
                asset_name = self._map_asset_name(asset)
                order_direction = OrderDirection.CALL if direction.lower() == 'call' else OrderDirection.PUT
                
                order_result = await self.client.place_order(
                    asset=asset_name,
                    direction=order_direction,
                    amount=amount,
                    duration=dynamic_duration
                )
                
                if order_result and order_result.status in [OrderStatus.ACTIVE, OrderStatus.PENDING]:
                    print(f"✅ Immediate trade placed - ID: {order_result.order_id}")
                    self.record_api_success()
                    
                    # Improved result checking with appropriate timeout based on duration
                    try:
                        # Use appropriate timeout based on trade duration, but consistent check intervals
                        if dynamic_duration >= 300:  # LC Trader (5:00) and James Martin (5:00)
                            max_wait = min(330.0, dynamic_duration + 30.0)  # Max 330 seconds for 5:00 trades
                        else:  # PO ADVANCE BOT and others (1:00)
                            max_wait = min(80.0, dynamic_duration + 20.0)  # Max 80 seconds for 1:00 trades
                        
                        # Use consistent check interval for both channels
                        check_interval = 0.01  # 10ms check interval for both channels
                        
                        print(f"⏳ Monitoring immediate result (max {max_wait:.0f}s, check every 10ms)...")
                        
                        start_time = get_user_time()
                        win_result = None
                        
                        # Use consistent polling intervals for both channels
                        while (get_user_time() - start_time).total_seconds() < max_wait:
                            try:
                                win_result = await asyncio.wait_for(
                                    self.client.check_win(order_result.order_id, max_wait_time=5.0),
                                    timeout=5.0
                                )
                                
                                if win_result and win_result.get('completed', False):
                                    break
                                
                                elapsed = (get_user_time() - start_time).total_seconds()
                                remaining = max_wait - elapsed
                                if remaining > check_interval:
                                    await asyncio.sleep(check_interval)
                                else:
                                    break
                                    
                            except asyncio.TimeoutError:
                                elapsed = (get_user_time() - start_time).total_seconds()
                                remaining = max_wait - elapsed
                                if remaining > check_interval:
                                    await asyncio.sleep(check_interval)
                                else:
                                    break
                            except Exception as check_error:
                                print(f"⚠️ Check error: {check_error}")
                                await asyncio.sleep(check_interval)
                        
                        if win_result and win_result.get('completed', False):
                            result_type = win_result.get('result', 'unknown')
                            won = result_type == 'win'
                            profit = win_result.get('profit', amount * 0.8 if won else -amount)
                            print(f"✅ IMMEDIATE {'WIN' if won else 'LOSS'}: ${profit:+.2f}")
                            self.record_api_success()
                            return won, profit
                        else:
                            elapsed = (get_user_time() - start_time).total_seconds()
                            print(f"⚠️ Immediate trade timeout after {elapsed:.0f}s - assuming loss")
                            # Don't fail the system, just assume loss and continue
                            return False, -amount
                            
                    except Exception as e:
                        print(f"⚠️ Immediate trade result error: {e} - assuming loss")
                        # Don't fail the system, just assume loss and continue
                        return False, -amount
                else:
                    print(f"❌ Immediate trade failed")
                    self.record_api_failure()
                    raise Exception("Immediate trade failed")
                    
            except Exception as api_error:
                error_msg = str(api_error).lower()
                if 'incorrectopentime' in error_msg or 'market' in error_msg or 'closed' in error_msg:
                    raise Exception(f"Market closed for {asset} - trade during market hours")
                else:
                    print(f"❌ Immediate API Error: {api_error}")
                    self.record_api_failure()
                    raise Exception(f"Immediate API Error: {api_error}")
            
        except Exception as e:
            print(f"❌ Immediate trade error: {e}")
            raise Exception(f"Immediate trade failed: {e}")
    
    async def execute_precise_trade(self, signal: Dict, amount: float) -> Tuple[bool, float]:
        """Execute trade with precise UTC+6 timing - wait for exact signal time and execute within 10ms"""
        try:
            asset = signal['asset']
            direction = signal['direction']
            signal_time = signal['signal_datetime']
            channel = signal.get('channel', self.active_channel)
            
            # Get channel-specific duration
            if channel == "james_martin_free":
                dynamic_duration = self.james_martin_free_duration
                channel_name = "James Martin Free"
            else:
                dynamic_duration = signal.get('duration', 300)  # Use signal duration or default to 5:00
                channel_name = "Default"
            
            duration_display = f"{dynamic_duration}s" if dynamic_duration < 60 else f"{dynamic_duration//60}:{dynamic_duration%60:02d}"
            
            print(f"🚀 PRECISE TIMING ({channel_name}): {asset} {direction.upper()} ${amount} ({duration_display})")
            print(f"   Signal Time: {format_time_hmsms(signal_time)}")
            print(f"   Current Time: {get_user_time_str()}")
            
            # Wait for EXACT signal time match (at :00 seconds)
            target_signal_time = signal_time.replace(second=0, microsecond=0)  # Exact :00 seconds
            print(f"🎯 Waiting for EXACT time: {format_time_hmsms(target_signal_time)}")
            
            # Precision timing loop - wait for exact second match
            while True:
                current_time = get_user_time()
                current_hms = current_time.strftime('%H:%M:%S')
                target_hms = target_signal_time.strftime('%H:%M:%S')
                
                if current_hms == target_hms:
                    # EXACT TIME MATCH! Wait 10ms then execute
                    await asyncio.sleep(0.01)  # Wait 10ms
                    execution_time = get_user_time()
                    print(f"✅ EXACT TIME MATCH! Executing at {format_time_hmsms(execution_time)} (10ms after match)")
                    break
                else:
                    # Calculate time until target
                    time_diff = (target_signal_time - current_time).total_seconds()
                    if time_diff < 0:
                        # Signal time has passed
                        print(f"❌ Signal time {target_hms} has passed (current: {current_hms})")
                        raise Exception(f"Signal time {target_hms} has passed")
                    elif time_diff > 60:
                        # More than 1 minute away - sleep longer
                        await asyncio.sleep(1.0)
                    elif time_diff > 1:
                        # More than 1 second away - sleep 100ms
                        await asyncio.sleep(0.1)
                    else:
                        # Less than 1 second away - high precision timing
                        await asyncio.sleep(0.001)  # 1ms precision
            
            # Calculate target close time using channel-specific duration
            target_close_time = execution_time + timedelta(seconds=dynamic_duration)
            
            # Use channel-specific duration (not signal duration)
            trade_duration = dynamic_duration
            
            print(f"🎯 EXECUTING: {asset} {direction.upper()} ${amount}")
            print(f"⏰ TIMING: Execute {format_time_hmsms(execution_time)} → Close {format_time_hmsms(target_close_time)}")
            duration_minutes = trade_duration // 60
            duration_seconds = trade_duration % 60
            if duration_minutes > 0:
                print(f"📊 Duration: {trade_duration} seconds ({duration_minutes}:{duration_seconds:02d})")
            else:
                print(f"📊 Duration: {trade_duration} seconds (0:{duration_seconds:02d})")
            
            if not self.should_use_api(asset):
                print(f"❌ API not available for {asset}")
                raise Exception(f"API not available for {asset}")
            
            try:
                # Real API execution with optimized asset format selection
                asset_name = self._map_asset_name(asset)
                order_direction = OrderDirection.CALL if direction.lower() == 'call' else OrderDirection.PUT
                
                print(f"🔄 Using API format: {asset_name}")
                order_result = await self.client.place_order(
                    asset=asset_name,
                    direction=order_direction,
                    amount=amount,
                    duration=trade_duration
                )
                
                if order_result and order_result.status in [OrderStatus.ACTIVE, OrderStatus.PENDING]:
                    print(f"✅ Trade placed - ID: {order_result.order_id}")
                    print(f"⏳ Monitoring result...")
                    self.record_api_success()
                    
                    # Monitor trade result with appropriate timeout based on duration
                    try:
                        # Use appropriate timeout based on trade duration, but consistent check intervals
                        if trade_duration >= 300:  # LC Trader (5:00) and James Martin (5:00)
                            max_wait = min(330.0, trade_duration + 30.0)  # Max 330 seconds for 5:00 trades
                        else:  # PO ADVANCE BOT and others (1:00)
                            max_wait = min(80.0, trade_duration + 20.0)  # Max 80 seconds for 1:00 trades
                        
                        # Use consistent check interval for both channels
                        check_interval = 0.01  # 10ms check interval for both channels
                        
                        print(f"⏳ Monitoring result (max {max_wait:.0f}s, check every 10ms)...")
                        
                        start_time = get_user_time()
                        win_result = None
                        
                        while (get_user_time() - start_time).total_seconds() < max_wait:
                            try:
                                win_result = await asyncio.wait_for(
                                    self.client.check_win(order_result.order_id, max_wait_time=5.0),
                                    timeout=5.0
                                )
                                
                                if win_result and win_result.get('completed', False):
                                    break
                                
                                elapsed = (get_user_time() - start_time).total_seconds()
                                remaining = max_wait - elapsed
                                if remaining > check_interval:
                                    await asyncio.sleep(check_interval)
                                else:
                                    break
                                    
                            except asyncio.TimeoutError:
                                elapsed = (get_user_time() - start_time).total_seconds()
                                remaining = max_wait - elapsed
                                if remaining > check_interval:
                                    await asyncio.sleep(check_interval)
                                else:
                                    break
                            except Exception as check_error:
                                print(f"⚠️ Check error: {check_error}")
                                await asyncio.sleep(check_interval)
                        
                        # Process result
                        if win_result and win_result.get('completed', False):
                            result_type = win_result.get('result', 'unknown')
                            profit_amount = win_result.get('profit', 0)
                            
                            if result_type == 'win':
                                won = True
                                profit = profit_amount if profit_amount > 0 else amount * 0.8
                                print(f"🎉 WIN! Profit: ${profit:.2f}")
                            elif result_type == 'loss':
                                won = False
                                profit = profit_amount if profit_amount < 0 else -amount
                                print(f"💔 LOSS! Loss: ${abs(profit):.2f}")
                            else:
                                won = False
                                profit = 0.0 if result_type == 'draw' else -amount
                                print(f"🤝 {result_type.upper()}!")
                            
                            self.record_api_success()
                        else:
                            elapsed = (get_user_time() - start_time).total_seconds()
                            print(f"❌ Result timeout after {elapsed:.0f}s - API connection failed")
                            self.record_api_failure()
                            raise Exception(f"API result timeout after {elapsed:.0f}s")
                            
                    except Exception as result_error:
                        print(f"❌ Result error: {result_error}")
                        self.record_api_failure()
                        raise Exception(f"API result error: {result_error}")
                else:
                    print(f"❌ Trade failed - status: {order_result.status if order_result else 'None'}")
                    self.record_api_failure()
                    raise Exception(f"Trade placement failed")
                    
            except Exception as api_error:
                error_msg = str(api_error).lower()
                if 'incorrectopentime' in error_msg or 'market' in error_msg or 'closed' in error_msg:
                    raise Exception(f"Market closed for {asset} - trade during market hours")
                else:
                    print(f"❌ API Error: {api_error}")
                    self.record_api_failure()
                    raise Exception("API failed")
            
            # Calculate actual close time for record (same as target close time)
            actual_close_time = target_close_time
            
            # Record trade
            result_status = 'win' if won else ('draw' if profit == 0 else 'loss')
            trade_record = {
                'asset': asset,
                'direction': direction,
                'amount': amount,
                'result': result_status,
                'profit_loss': profit,
                'execution_time': execution_time.isoformat(),
                'signal_time': signal_time.isoformat(),
                'close_time': actual_close_time.isoformat(),
                'target_close_time': target_close_time.isoformat(),
                'duration_seconds': trade_duration,
                'timing_strategy': 'precise_user_timezone_10ms_window',
                'mode': 'real'
            }
            self.trade_history.append(trade_record)
            
            return won, profit
            
        except Exception as e:
            print(f"❌ Trade execution error: {e}")
            return False, -amount
    
    async def execute_martingale_sequence(self, asset: str, direction: str, base_amount: float, strategy, channel: str = None) -> Tuple[bool, float]:
        """Execute complete martingale sequence for an asset"""
        total_profit = 0.0
        
        # Get max steps based on strategy type
        if hasattr(strategy, 'max_steps'):
            max_steps = strategy.max_steps
        else:
            max_steps = 6  # Default fallback
        
        step_count = 0  # Track actual steps executed
        
        while step_count < max_steps:
            # Get current step and amount from strategy (this will reflect any resets)
            current_step = strategy.get_asset_step(asset)
            current_cycle = strategy.get_asset_cycle(asset)
            step_amount = strategy.get_current_amount(asset)
            
            print(f"🔍 DEBUG: {asset} executing C{current_cycle}S{current_step} with ${step_amount:.2f}")
            
            try:
                # Execute trade based on step
                if current_step == 1 and step_count == 0:
                    # For first Step 1, use precise timing
                    won, profit = await self.execute_precise_trade({
                        'asset': asset,
                        'direction': direction,
                        'trade_datetime': get_user_time(),
                        'signal_datetime': get_user_time(),
                        'close_datetime': get_user_time() + timedelta(seconds=60),
                        'channel': channel or self.active_channel,
                        'duration': 60
                    }, step_amount)
                else:
                    # For all other steps, execute immediately
                    won, profit = await self.execute_immediate_trade(asset, direction, step_amount, channel or self.active_channel)
                
                total_profit += profit
                step_count += 1
                
                # Record result and get next action
                next_action = strategy.record_result(won, asset, step_amount)
                
                print(f"🔍 DEBUG: {asset} result: {'WIN' if won else 'LOSS'}, action: {next_action['action']}")
                
                if won:
                    print(f"✅ {asset} WIN! Strategy reset. Sequence complete.")
                    return True, total_profit
                else:
                    if next_action['action'] == 'continue':
                        print(f"🔄 {asset} continuing to next step...")
                        await asyncio.sleep(0.01)  # 10ms delay between steps
                        continue
                    elif next_action['action'] in ['reset', 'reset_after_max_loss', 'asset_completed']:
                        print(f"🔄 {asset} sequence complete: {next_action['action']}")
                        return False, total_profit
                    else:
                        print(f"🔄 {asset} unknown action: {next_action['action']}")
                        return False, total_profit
                        
            except Exception as e:
                print(f"❌ Step {current_step} error for {asset}: {e}")
                next_action = strategy.record_result(False, asset, step_amount)
                total_profit -= step_amount
                step_count += 1
                
                if next_action['action'] == 'continue':
                    await asyncio.sleep(0.01)
                    continue
                elif next_action['action'] in ['reset', 'reset_after_max_loss', 'asset_completed']:
                    return False, total_profit
                else:
                    return False, total_profit
        
        print(f"🔄 {asset} reached max steps ({max_steps})")
        return False, total_profit

    async def start_simple_trading(self, base_amount: float, multiplier: float = 2.5, is_demo: bool = True):
        """Start simple trading with minimal output - one line status only"""
        strategy = MultiAssetMartingaleStrategy(base_amount, multiplier)
        session_trades = 0
        
        try:
            while True:
                # Check stop loss and take profit conditions
                should_stop, stop_reason = self.should_stop_trading()
                if should_stop:
                    print(f"\n{stop_reason}")
                    break
                
                # Get signals for scheduled trades
                signals = self.get_signals_from_csv()
                
                if not signals:
                    # Show minimal status line
                    current_time_str = get_user_time_str()
                    print(f"\r⏰ Current: {current_time_str} | No signals | Scanning...", end="", flush=True)
                    await asyncio.sleep(1)
                    continue
                
                # Find next upcoming signal and ready signals
                current_time = get_user_time()
                ready_signals = []
                next_signal = None
                
                for signal in signals:
                    current_hms = current_time.strftime('%H:%M:%S')
                    signal_hms = signal['signal_datetime'].strftime('%H:%M:%S')
                    
                    # Check for EXACT time match (current time = signal time)
                    if current_hms == signal_hms:
                        ready_signals.append(signal)
                    else:
                        # Calculate time until signal
                        time_until_signal = (signal['signal_datetime'] - current_time).total_seconds()
                        if time_until_signal > 0 and next_signal is None:
                            next_signal = signal
                
                # Show clean status line
                current_time_str = get_user_time_str()
                if next_signal:
                    next_time = next_signal['signal_datetime'].strftime('%H:%M:00')
                    time_until = (next_signal['signal_datetime'] - current_time).total_seconds()
                    wait_min = int(time_until // 60)
                    wait_sec = int(time_until % 60)
                    
                    if ready_signals:
                        if len(ready_signals) == 1:
                            executing_signal = ready_signals[0]
                            print(f"\r⏰ Current: {current_time_str} | EXECUTING: {executing_signal['asset']} {executing_signal['direction'].upper()} | Next: {next_time}", end="", flush=True)
                        else:
                            assets_list = [f"{s['asset']} {s['direction'].upper()}" for s in ready_signals]
                            print(f"\r⏰ Current: {current_time_str} | EXECUTING {len(ready_signals)} ASSETS: {', '.join(assets_list[:2])}{'...' if len(assets_list) > 2 else ''} | Next: {next_time}", end="", flush=True)
                    else:
                        print(f"\r⏰ Current: {current_time_str} | Next: {next_time} in {wait_min}m{wait_sec}s", end="", flush=True)
                else:
                    if ready_signals:
                        if len(ready_signals) == 1:
                            executing_signal = ready_signals[0]
                            print(f"\r⏰ Current: {current_time_str} | EXECUTING: {executing_signal['asset']} {executing_signal['direction'].upper()}", end="", flush=True)
                        else:
                            print(f"\r⏰ Current: {current_time_str} | EXECUTING {len(ready_signals)} ASSETS SIMULTANEOUSLY", end="", flush=True)
                    else:
                        print(f"\r⏰ Current: {current_time_str} | No upcoming signals", end="", flush=True)
                
                if not ready_signals:
                    await asyncio.sleep(1)
                    continue
                
                # Process ready signals - handle multiple assets at same time
                if ready_signals:
                    if len(ready_signals) == 1:
                        # Single signal - execute normally
                        signal = ready_signals[0]
                        asset = signal['asset']
                        direction = signal['direction']
                        current_step = strategy.get_asset_step(asset)
                        
                        print(f"\n🚀 EXECUTING: {asset} {direction.upper()} - Step {current_step}")
                        
                        try:
                            final_won, total_profit = await self.execute_martingale_sequence(
                                asset, direction, base_amount, strategy, self.active_channel
                            )
                            
                            self.update_session_profit(total_profit)
                            session_trades += 1
                            
                            if final_won:
                                print(f"✅ {asset} WIN! Profit: ${total_profit:+.2f}")
                            else:
                                print(f"❌ {asset} LOSS! Loss: ${total_profit:+.2f}")
                            
                        except Exception as sequence_error:
                            print(f"❌ Error for {asset}: {sequence_error}")
                            strategy.asset_strategies[asset] = {'step': 1, 'amounts': []}
                    
                    else:
                        # Multiple signals at same time - execute concurrently
                        print(f"\n🚀 EXECUTING {len(ready_signals)} ASSETS SIMULTANEOUSLY:")
                        
                        # Create concurrent tasks for all ready signals
                        tasks = []
                        for signal in ready_signals:
                            asset = signal['asset']
                            direction = signal['direction']
                            current_step = strategy.get_asset_step(asset)
                            
                            print(f"   📊 {asset} {direction.upper()} - Step {current_step}")
                            
                            # Create async task for each asset
                            task = asyncio.create_task(
                                self.execute_martingale_sequence(
                                    asset, direction, base_amount, strategy, self.active_channel
                                )
                            )
                            tasks.append((task, asset, direction))
                        
                        # Wait for all tasks to complete
                        results = await asyncio.gather(*[task for task, _, _ in tasks], return_exceptions=True)
                        
                        # Process results
                        for i, result in enumerate(results):
                            _, asset, direction = tasks[i]
                            
                            if isinstance(result, Exception):
                                print(f"❌ {asset} Error: {result}")
                                strategy.asset_strategies[asset] = {'step': 1, 'amounts': []}
                                continue
                            
                            final_won, total_profit = result
                            self.update_session_profit(total_profit)
                            session_trades += 1
                            
                            if final_won:
                                print(f"✅ {asset} WIN! Profit: ${total_profit:+.2f}")
                            else:
                                print(f"❌ {asset} LOSS! Loss: ${total_profit:+.2f}")
                    
                    # Check stop conditions after processing all signals
                    should_stop, stop_reason = self.should_stop_trading()
                    if should_stop:
                        print(f"\n{stop_reason}")
                        return
                
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            print(f"\n🛑 TRADING STOPPED BY USER")
        except Exception as e:
            print(f"❌ Trading error: {e}")

    async def start_precise_trading(self, base_amount: float, multiplier: float = 2.5, is_demo: bool = True):
        """Start precise timing trading with SEQUENTIAL martingale progression and stop loss/take profit"""
        print(f"\n🚀 SEQUENTIAL MARTINGALE TRADING STARTED")
        print("=" * 60)
        print(f"💰 Base Amount: ${base_amount}")
        print(f"📈 Multiplier: {multiplier}")
        print(f"🔄 Sequential System: All steps executed immediately with channel-specific durations")
        print(f"⏳ Step Timing: Step 1 → Wait for result → Step 2 (10ms) → Step 3 (10ms)")
        print(f"🎯 Unified Delays: 10ms between steps for both channels")
        print(f"✅ WIN at any step → Reset to Step 1 for next signal")
        print(f"❌ LOSS → Continue to next step (10ms delay)")
        print(f"🔄 All 3 steps lost → Reset to Step 1 for next signal")
        print(f"🔧 API Health: Consistent timing, channel-specific durations")
        
        # Display stop loss and take profit info
        if self.stop_loss is not None or self.take_profit is not None:
            print(f"💡 Risk Management:")
            if self.stop_loss is not None:
                print(f"   🛑 Stop Loss: ${self.stop_loss:.2f}")
            if self.take_profit is not None:
                print(f"   🎯 Take Profit: ${self.take_profit:.2f}")
        
        print("Press Ctrl+C to stop")
        print("=" * 60)
        
        strategy = MultiAssetMartingaleStrategy(base_amount, multiplier)
        session_trades = 0
        
        try:
            # Show initial signal overview
            # Scanning for signals...
            initial_signals = self.get_signals_from_csv()
            if initial_signals:
                print(f"✅ Found {len(initial_signals)} signals in CSV:")
                current_time = get_user_time()
                for i, signal in enumerate(initial_signals[:5]):  # Show first 5
                    time_until = (signal['trade_datetime'] - current_time).total_seconds()
                    wait_minutes = int(time_until // 60)
                    wait_seconds = int(time_until % 60)
                    status = "Ready!" if time_until <= 5 else f"in {wait_minutes}m {wait_seconds}s"
                    print(f"   {i+1}. {signal['asset']} {signal['direction'].upper()} at {signal['signal_time']} ({status})")
                if len(initial_signals) > 5:
                    print(f"   ... and {len(initial_signals) - 5} more signals")
            else:
                print(f"❌ No signals found in CSV - add signals to the selected channel CSV file")
            print("=" * 60)
            
            while True:
                # Display current time
                current_time = get_user_time()
                current_time_str = current_time.strftime('%H:%M:%S')
                
                # Check stop loss and take profit conditions
                should_stop, stop_reason = self.should_stop_trading()
                if should_stop:
                    print(f"\n{stop_reason}")
                    print(f"🏁 Trading session ended")
                    break
                
                # Process any pending immediate trades first
                if self.pending_immediate_trades:
                    print(f"\n⚡ PROCESSING {len(self.pending_immediate_trades)} IMMEDIATE TRADES")
                    
                    immediate_tasks = []
                    for immediate_trade in self.pending_immediate_trades:
                        asset = immediate_trade['asset']
                        direction = immediate_trade['direction']
                        amount = immediate_trade['amount']
                        step = immediate_trade['step']
                        
                        print(f"⚡ IMMEDIATE Step {step}: {asset} {direction.upper()} ${amount}")
                        
                        # Execute immediate trade
                        task = asyncio.create_task(
                            self.execute_immediate_trade(asset, direction, amount)
                        )
                        immediate_tasks.append((task, asset, direction, amount, step))
                    
                    # Clear pending trades
                    self.pending_immediate_trades.clear()
                    
                    # Wait for all immediate trades to complete
                    if immediate_tasks:
                        results = await asyncio.gather(*[task for task, _, _, _, _ in immediate_tasks], return_exceptions=True)
                        
                        # Process immediate trade results
                        for i, result in enumerate(results):
                            if isinstance(result, Exception):
                                print(f"❌ Immediate trade {i+1} failed: {result}")
                                continue
                            
                            won, profit = result
                            _, asset, direction, amount, step = immediate_tasks[i]
                            
                            # Update session profit using class method
                            self.update_session_profit(profit)
                            session_trades += 1
                            
                            # Update strategy for immediate trade result
                            next_action = strategy.record_result(won, asset, amount)
                            
                            if next_action['action'] == 'continue':
                                # Need another immediate trade (step 3 after step 2 loss)
                                next_step = next_action['next_step']
                                next_amount = strategy.get_current_amount(asset)
                                
                                print(f"⚡ QUEUEING Step {next_step}: {asset} {direction.upper()} ${next_amount}")
                                self.pending_immediate_trades.append({
                                    'asset': asset,
                                    'direction': direction,
                                    'amount': next_amount,
                                    'step': next_step
                                })
                            elif next_action['action'] in ['reset', 'reset_after_max_loss']:
                                print(f"🔄 {asset} strategy reset - ready for new signals")
                        
                        # Show session stats after immediate trades
                        wins = len([t for t in self.trade_history if t['result'] == 'win'])
                        losses = len([t for t in self.trade_history if t['result'] == 'loss'])
                        
                        print(f"📊 {self.get_session_status()} | Trades: {session_trades}")
                        print(f"🏆 Results: {wins}W/{losses}L")
                        
                        # Check stop conditions after immediate trades
                        should_stop, stop_reason = self.should_stop_trading()
                        if should_stop:
                            print(f"\n{stop_reason}")
                            print(f"🏁 Trading session ended")
                            break
                
                # Get signals for scheduled trades
                signals = self.get_signals_from_csv()
                
                if not signals and not self.pending_immediate_trades:
                    # Show current time and status
                    current_time_display = get_user_time_str()
                    if hasattr(self, 'api_failures') and self.api_failures > 0:
                        health_status = f"API Health: {self.api_failures}/{self.max_api_failures} failures"
                        print(f"\n🔄 [{current_time_display}] No signals ready - {health_status}")
                    else:
                        print(f"\n🔄 [{current_time_display}] No signals ready - scanning for upcoming trades...")
                    await asyncio.sleep(1)  # Check every 1 seconds for upcoming signals
                    continue
                
                # Show upcoming signals info with precise time matching
                if signals:
                    current_time = get_user_time()
                    current_time_str = get_user_time_str()
                    ready_signals = []
                    future_signals = []
                    
                    print(f"⏰ CURRENT TIME (UTC+6): {current_time_str}")
                    
                    for signal in signals:
                        current_time_hms = current_time.strftime('%H:%M:%S')
                        signal_time_hms = signal['signal_datetime'].strftime('%H:%M:%S')
                        
                        # Check for EXACT time match (current time = signal time)
                        if current_time_hms == signal_time_hms:
                            print(f"🎯 EXACT TIME MATCH: {signal['asset']} {signal['direction'].upper()}")
                            print(f"   Current: {current_time_hms} = Signal: {signal_time_hms} ✅")
                            ready_signals.append(signal)
                        else:
                            # Calculate time difference
                            time_until_signal = (signal['signal_datetime'] - current_time).total_seconds()
                            if time_until_signal > 0:
                                future_signals.append((signal, time_until_signal))
                            else:
                                # Signal time has passed
                                print(f"⏰ MISSED: {signal['asset']} {signal['direction'].upper()} at {signal_time_hms}")
                                continue
                    
                    if future_signals:
                        print(f"📅 UPCOMING SIGNALS:")
                        for signal, wait_time in sorted(future_signals, key=lambda x: x[1])[:5]:  # Show next 5
                            wait_minutes = int(wait_time // 60)
                            wait_seconds = int(wait_time % 60)
                            signal_time_display = signal['signal_time'] if 'signal_time' in signal else signal['signal_datetime'].strftime('%H:%M')
                            print(f"   {signal['asset']} {signal['direction'].upper()} at {signal_time_display} (in {wait_minutes}m {wait_seconds}s)")
                    
                    if not ready_signals:
                        if future_signals:
                            next_signal, next_wait = min(future_signals, key=lambda x: x[1])
                            wait_minutes = int(next_wait // 60)
                            wait_seconds = int(next_wait % 60)
                            print(f"⏰ Next signal: {next_signal['asset']} {next_signal['direction'].upper()} in {wait_minutes}m {wait_seconds}s")
                        await asyncio.sleep(1)  # Wait 1 seconds and check again
                        continue
                    
                    # Process only ready signals
                    signals = ready_signals
                
                # PRIORITY SYSTEM: Complete existing martingale sequences first
                if signals:
                    # Check if any assets are in the middle of sequences (Step 2 or 3)
                    assets_in_sequence = strategy.get_assets_in_sequence()
                    
                    if assets_in_sequence:
                        print(f"\n🎯 PRIORITY: Completing existing sequences first")
                        print(f"📊 Assets in sequence: {', '.join(assets_in_sequence)}")
                        
                        # Filter signals to only process assets that are in sequence
                        priority_signals = []
                        blocked_signals = []
                        
                        for signal in signals:
                            if signal['asset'] in assets_in_sequence:
                                priority_signals.append(signal)
                            else:
                                blocked_signals.append(signal)
                        
                        if blocked_signals:
                            blocked_assets = [s['asset'] for s in blocked_signals]
                            print(f"⏸️  Blocking new assets: {', '.join(blocked_assets)} (waiting for sequences to complete)")
                        
                        # Process only priority signals (assets in sequence)
                        signals_to_process = priority_signals
                    else:
                        print(f"\n📊 PROCESSING {len(signals)} NEW SIGNALS (No active sequences):")
                        # No assets in sequence, process all signals
                        signals_to_process = signals
                    
                    if signals_to_process:
                        print("=" * 50)
                        
                        # Create tasks for selected signals - but execute martingale sequences sequentially
                        for signal in signals_to_process:
                            asset = signal['asset']
                            direction = signal['direction']
                            
                            # Each asset gets its own independent step progression
                            current_step = strategy.get_asset_step(asset)
                            
                            print(f"📊 {asset} {direction.upper()} - {strategy.get_status(asset)}")
                            print(f"⏰ Signal: {signal['signal_time']} | Trade: {signal['trade_datetime'].strftime('%H:%M:%S')}")
                            
                            # Execute complete martingale sequence for this asset
                            try:
                                print(f"🚀 EXECUTING MARTINGALE SEQUENCE FOR {asset}")
                                
                                # Execute the complete sequence and wait for final result
                                final_won, total_profit = await self.execute_martingale_sequence(
                                    asset, direction, base_amount, strategy, self.active_channel
                                )
                                
                                # Update session profit using class method
                                self.update_session_profit(total_profit)
                                session_trades += 1  # Count as one sequence
                                
                                if final_won:
                                    print(f"🎉 {asset} SEQUENCE WIN! Total profit: ${total_profit:+.2f}")
                                else:
                                    print(f"💔 {asset} SEQUENCE LOSS! Total loss: ${total_profit:+.2f}")
                                
                            except Exception as sequence_error:
                                print(f"❌ Martingale sequence error for {asset}: {sequence_error}")
                                # Reset the asset strategy on error
                                strategy.asset_strategies[asset] = {'step': 1, 'amounts': []}
                            
                            # Show session stats after each sequence
                            wins = len([t for t in self.trade_history if t['result'] == 'win'])
                            losses = len([t for t in self.trade_history if t['result'] == 'loss'])
                            
                            print(f"\n📊 TRADING SESSION:")
                            print(f"   💰 {self.get_session_status()}")
                            print(f"   📈 Total Trades: {session_trades}")
                            print(f"   🏆 Results: {wins}W/{losses}L")
                            
                            # Check stop conditions after each sequence
                            should_stop, stop_reason = self.should_stop_trading()
                            if should_stop:
                                print(f"\n{stop_reason}")
                                print(f"🏁 Trading session ended")
                                return  # Exit the trading method
                            
                            # Show current status of all active assets
                            active_assets = strategy.get_all_active_assets()
                            if active_assets:
                                print(f"   📊 Asset Status:")
                                for asset_name in active_assets:
                                    status = strategy.get_status(asset_name)
                                    step = strategy.get_asset_step(asset_name)
                                    if step > 1:
                                        print(f"      🎯 {status} (IN SEQUENCE)")
                                    else:
                                        print(f"      ✅ {status} (READY)")
                
                await asyncio.sleep(1)  # 1s check interval
                
        except KeyboardInterrupt:
            print(f"\n🛑 TRADING STOPPED BY USER")
        except Exception as e:
            print(f"❌ Trading error: {e}")
        
        # Final stats
        total_trades = len(self.trade_history)
        total_wins = len([t for t in self.trade_history if t['result'] == 'win'])
        total_losses = len([t for t in self.trade_history if t['result'] == 'loss'])
        total_profit = sum([t['profit_loss'] for t in self.trade_history])
        
        print(f"\n📊 FINAL STATISTICS:")
        print(f"   💰 {self.get_session_status()}")
        print(f"   📈 Session Trades: {session_trades}")
        print(f"   🏆 Results: {total_wins}W/{total_losses}L")
        print(f"   💵 Total P&L: ${total_profit:.2f}")
        print(f"   🎯 Assets Tracked: {len(strategy.get_all_active_assets())}")
        
        # Show final stop loss/take profit status
        if self.stop_loss is not None or self.take_profit is not None:
            print(f"\n🎯 RISK MANAGEMENT SUMMARY:")
            if self.stop_loss is not None:
                if self.session_profit <= -self.stop_loss:
                    print(f"   🛑 Stop Loss TRIGGERED: ${self.session_profit:+.2f} (limit: -${self.stop_loss:.2f})")
                else:
                    remaining_loss = self.stop_loss + self.session_profit
                    print(f"   🛑 Stop Loss: ${remaining_loss:.2f} remaining")
            
            if self.take_profit is not None:
                if self.session_profit >= self.take_profit:
                    print(f"   🎯 Take Profit ACHIEVED: ${self.session_profit:+.2f} (target: +${self.take_profit:.2f})")
                else:
                    remaining_profit = self.take_profit - self.session_profit
                    print(f"   🎯 Take Profit: ${remaining_profit:.2f} to go")

    async def start_single_trade_mode(self, base_amount: float, is_demo: bool = True):
        """Start single trade mode - one trade per signal, no martingale"""
        print(f"\n🚀 SINGLE TRADE MODE STARTED")
        print("=" * 60)
        print(f"💰 Trade Amount: ${base_amount}")
        print(f"🎯 Strategy: One trade per signal")
        print(f"📊 No step progression")
        print(f"✅ WIN or LOSS → Move to next signal")
        
        # Display stop loss and take profit info
        if self.stop_loss is not None or self.take_profit is not None:
            print(f"💡 Risk Management:")
            if self.stop_loss is not None:
                print(f"   🛑 Stop Loss: ${self.stop_loss:.2f}")
            if self.take_profit is not None:
                print(f"   🎯 Take Profit: ${self.take_profit:.2f}")
        
        print("Press Ctrl+C to stop")
        print("=" * 60)
        
        session_trades = 0
        processed_signals = set()  # Track processed signals to avoid duplicates
        
        try:
            # Show initial signal overview
            # Scanning for signals...
            initial_signals = self.get_signals_from_csv()
            if initial_signals:
                print(f"✅ Found {len(initial_signals)} signals in CSV:")
                current_time = get_user_time()
                for i, signal in enumerate(initial_signals[:5]):  # Show first 5
                    time_until = (signal['trade_datetime'] - current_time).total_seconds()
                    wait_minutes = int(time_until // 60)
                    wait_seconds = int(time_until % 60)
                    status = "Ready!" if time_until <= 5 else f"in {wait_minutes}m {wait_seconds}s"
                    print(f"   {i+1}. {signal['asset']} {signal['direction'].upper()} at {signal['signal_time']} ({status})")
                if len(initial_signals) > 5:
                    print(f"   ... and {len(initial_signals) - 5} more signals")
            else:
                print(f"❌ No signals found in CSV - add signals to the selected channel CSV file")
            print("=" * 60)
            
            while True:
                # Display current time
                current_time = get_user_time()
                current_time_str = current_time.strftime('%H:%M:%S')
                
                # Check stop loss and take profit conditions
                should_stop, stop_reason = self.should_stop_trading()
                if should_stop:
                    print(f"\n{stop_reason}")
                    print(f"🏁 Trading session ended")
                    break
                
                # Get signals
                signals = self.get_signals_from_csv()
                
                if not signals:
                    # Show current time and status
                    current_time_display = get_user_time().strftime('%H:%M:%S')
                    print(f"\n🔄 [{current_time_display}] No signals ready - scanning for upcoming trades...")
                    await asyncio.sleep(1)  # Check every 1 seconds
                    continue
                
                # Show upcoming signals info with precise time matching
                if signals:
                    current_time = get_user_time()
                    current_time_str = current_time.strftime('%H:%M:%S')
                    ready_signals = []
                    future_signals = []
                    
                    print(f"⏰ CURRENT TIME: {current_time_str}")
                    
                    for signal in signals:
                        # Create unique signal ID
                        signal_id = f"{signal['asset']}_{signal['direction']}_{signal['signal_time']}"
                        
                        # Skip if already processed
                        if signal_id in processed_signals:
                            continue
                        
                        current_time_hms = current_time.strftime('%H:%M:%S')
                        signal_time_hms = signal['signal_datetime'].strftime('%H:%M:%S')
                        
                        # Check for EXACT time match
                        if current_time_hms == signal_time_hms:
                            print(f"🎯 EXACT TIME MATCH: {signal['asset']} {signal['direction'].upper()}")
                            print(f"   Current: {current_time_hms} = Signal: {signal_time_hms} ✅")
                            ready_signals.append(signal)
                        else:
                            # Calculate time difference
                            time_until_signal = (signal['signal_datetime'] - current_time).total_seconds()
                            if time_until_signal > 0:
                                future_signals.append((signal, time_until_signal))
                    
                    if future_signals:
                        print(f"📅 UPCOMING SIGNALS:")
                        for signal, wait_time in sorted(future_signals, key=lambda x: x[1])[:5]:
                            wait_minutes = int(wait_time // 60)
                            wait_seconds = int(wait_time % 60)
                            signal_time_display = signal['signal_time'] if 'signal_time' in signal else signal['signal_datetime'].strftime('%H:%M')
                            print(f"   {signal['asset']} {signal['direction'].upper()} at {signal_time_display} (in {wait_minutes}m {wait_seconds}s)")
                    
                    if not ready_signals:
                        if future_signals:
                            next_signal, next_wait = min(future_signals, key=lambda x: x[1])
                            wait_minutes = int(next_wait // 60)
                            wait_seconds = int(next_wait % 60)
                            print(f"⏰ Next signal: {next_signal['asset']} {next_signal['direction'].upper()} in {wait_minutes}m {wait_seconds}s")
                        await asyncio.sleep(1)
                        continue
                    
                    # Process ready signals
                    signals = ready_signals
                
                # Process signals
                if signals:
                    print(f"\n📊 PROCESSING {len(signals)} SIGNALS:")
                    print("=" * 50)
                    
                    for signal in signals:
                        asset = signal['asset']
                        direction = signal['direction']
                        
                        # Create unique signal ID
                        signal_id = f"{asset}_{direction}_{signal['signal_time']}"
                        
                        # Mark as processed
                        processed_signals.add(signal_id)
                        
                        print(f"📊 {asset} {direction.upper()} - Single Trade")
                        print(f"⏰ Signal: {signal['signal_time']} | Trade: {signal['trade_datetime'].strftime('%H:%M:%S')}")
                        
                        # Execute single trade
                        try:
                            print(f"🚀 EXECUTING SINGLE TRADE: {asset} {direction.upper()} ${base_amount:.2f}")
                            
                            # Execute the trade
                            won, profit = await self.execute_single_trade(
                                asset, direction, base_amount, self.active_channel
                            )
                            
                            # Update session profit
                            self.update_session_profit(profit)
                            session_trades += 1
                            
                            if won:
                                print(f"🎉 {asset} WIN! Profit: ${profit:+.2f}")
                            else:
                                print(f"💔 {asset} LOSS! Loss: ${profit:+.2f}")
                            
                        except Exception as trade_error:
                            print(f"❌ Trade error for {asset}: {trade_error}")
                        
                        # Show session stats
                        wins = len([t for t in self.trade_history if t['result'] == 'win'])
                        losses = len([t for t in self.trade_history if t['result'] == 'loss'])
                        
                        print(f"\n📊 TRADING SESSION:")
                        print(f"   💰 {self.get_session_status()}")
                        print(f"   📈 Total Trades: {session_trades}")
                        print(f"   🏆 Results: {wins}W/{losses}L")
                        
                        # Check stop conditions
                        should_stop, stop_reason = self.should_stop_trading()
                        if should_stop:
                            print(f"\n{stop_reason}")
                            print(f"🏁 Trading session ended")
                            return
                
                await asyncio.sleep(1)  # 1s check interval
                
        except KeyboardInterrupt:
            print(f"\n🛑 TRADING STOPPED BY USER")
        except Exception as e:
            print(f"❌ Trading error: {e}")
        
        # Final stats
        total_trades = len(self.trade_history)
        total_wins = len([t for t in self.trade_history if t['result'] == 'win'])
        total_losses = len([t for t in self.trade_history if t['result'] == 'loss'])
        total_profit = sum([t['profit_loss'] for t in self.trade_history])
        
        print(f"\n📊 FINAL STATISTICS:")
        print(f"   💰 {self.get_session_status()}")
        print(f"   📈 Total Trades: {session_trades}")
        print(f"   🏆 Results: {total_wins}W/{total_losses}L")
        print(f"   💵 Total P&L: ${total_profit:.2f}")
        
        # Show final stop loss/take profit status
        if self.stop_loss is not None or self.take_profit is not None:
            print(f"\n🎯 RISK MANAGEMENT SUMMARY:")
            if self.stop_loss is not None:
                if self.session_profit <= -self.stop_loss:
                    print(f"   🛑 Stop Loss TRIGGERED: ${self.session_profit:+.2f} (limit: -${self.stop_loss:.2f})")
                else:
                    remaining_loss = self.stop_loss + self.session_profit
                    print(f"   🛑 Stop Loss: ${remaining_loss:.2f} remaining")
            
            if self.take_profit is not None:
                if self.session_profit >= self.take_profit:
                    print(f"   🎯 Take Profit ACHIEVED: ${self.session_profit:+.2f} (target: +${self.take_profit:.2f})")
                else:
                    remaining_profit = self.take_profit - self.session_profit
                    print(f"   🎯 Take Profit: ${remaining_profit:.2f} to go")

    async def start_option2_trading(self, base_amount: float, multiplier: float = 2.5, is_demo: bool = True):
        """Start Option 2: 3-Cycle Progressive Martingale trading with GLOBAL cycle progression"""
        print(f"\n🚀 OPTION 2: 3-CYCLE PROGRESSIVE MARTINGALE STARTED")
        print("=" * 60)
        print(f"💰 Base Amount: ${base_amount}")
        print(f"📈 Multiplier: {multiplier}")
        print(f"🔄 GLOBAL CYCLE SYSTEM:")
        print(f"   • Cycle 1: All assets start with Step 1, 2, 3")
        print(f"   • If Cycle 1 all steps lost → ALL new assets move to Cycle 2")
        print(f"   • Cycle 2: All assets start with Cycle 2 amounts")
        print(f"   • If Cycle 2 all steps lost → ALL new assets move to Cycle 3")
        print(f"   • Cycle 3: All assets use Cycle 3 amounts (capped)")
        print(f"✅ WIN at any step → Reset GLOBAL cycle to Cycle 1")
        print(f"❌ LOSS → Continue to next step in current cycle")
        
        # Display stop loss and take profit info
        if self.stop_loss is not None or self.take_profit is not None:
            print(f"💡 Risk Management:")
            if self.stop_loss is not None:
                print(f"   🛑 Stop Loss: ${self.stop_loss:.2f}")
            if self.take_profit is not None:
                print(f"   🎯 Take Profit: ${self.take_profit:.2f}")
        
        print("Press Ctrl+C to stop")
        print("=" * 60)
        
        # GLOBAL cycle tracker (applies to ALL assets)
        global_cycle_tracker = {
            'current_cycle': 1,  # Global cycle: 1, 2, or 3
            'cycle_1_last_amount': base_amount * (multiplier ** 2),
            'config': {'base_amount': base_amount, 'multiplier': multiplier}
        }
        
        # Per-asset step tracker (each asset has its own step within the global cycle)
        asset_step_trackers = {}  # {asset: {'current_step': 1}}
        
        session_trades = 0
        
        try:
            # Show initial signal overview
            # Scanning for signals...
            initial_signals = self.get_signals_from_csv()
            if initial_signals:
                print(f"✅ Found {len(initial_signals)} signals in CSV:")
                current_time = get_user_time()
                for i, signal in enumerate(initial_signals[:5]):
                    time_until = (signal['trade_datetime'] - current_time).total_seconds()
                    wait_minutes = int(time_until // 60)
                    wait_seconds = int(time_until % 60)
                    status = "Ready!" if time_until <= 5 else f"in {wait_minutes}m {wait_seconds}s"
                    print(f"   {i+1}. {signal['asset']} {signal['direction'].upper()} at {signal['signal_time']} ({status})")
                if len(initial_signals) > 5:
                    print(f"   ... and {len(initial_signals) - 5} more signals")
            else:
                print(f"❌ No signals found in CSV")
            print("=" * 60)
            
            while True:
                # Check stop loss and take profit conditions
                should_stop, stop_reason = self.should_stop_trading()
                if should_stop:
                    print(f"\n{stop_reason}")
                    print(f"🏁 Trading session ended")
                    break
                
                # Get signals
                signals = self.get_signals_from_csv()
                
                if not signals:
                    current_time_display = get_user_time().strftime('%H:%M:%S')
                    print(f"\n🔄 [{current_time_display}] No signals ready - scanning...")
                    await asyncio.sleep(1)
                    continue
                
                # Check for exact time match
                current_time = get_user_time()
                current_time_str = current_time.strftime('%H:%M:%S')
                ready_signals = []
                
                print(f"⏰ CURRENT TIME: {current_time_str}")
                
                for signal in signals:
                    signal_time_hms = signal['signal_datetime'].strftime('%H:%M:%S')
                    if current_time_str == signal_time_hms:
                        print(f"🎯 EXACT TIME MATCH: {signal['asset']} {signal['direction'].upper()}")
                        ready_signals.append(signal)
                
                if not ready_signals:
                    await asyncio.sleep(1)
                    continue
                
                # Process ready signals
                current_global_cycle = global_cycle_tracker['current_cycle']
                print(f"\n📊 PROCESSING {len(ready_signals)} SIGNALS (GLOBAL CYCLE {current_global_cycle}):")
                print("=" * 50)
                
                for signal in ready_signals:
                    asset = signal['asset']
                    direction = signal['direction']
                    
                    # Initialize step tracker for this asset if not exists
                    if asset not in asset_step_trackers:
                        asset_step_trackers[asset] = {'current_step': 1}
                    
                    asset_tracker = asset_step_trackers[asset]
                    current_step = asset_tracker['current_step']
                    
                    print(f"📊 {asset} {direction.upper()} - Global Cycle {current_global_cycle}, Step {current_step}")
                    print(f"⏰ Signal: {signal['signal_time']}")
                    
                    # Execute sequence for this asset using global cycle
                    try:
                        print(f"🚀 EXECUTING OPTION 2: {asset} (Global C{current_global_cycle})")
                        
                        # Execute the sequence
                        final_won, total_profit = await self.execute_option2_global_sequence(
                            asset, direction, global_cycle_tracker, asset_tracker, self.active_channel
                        )
                        
                        # Update session profit
                        self.update_session_profit(total_profit)
                        session_trades += 1
                        
                        if final_won:
                            print(f"🎉 {asset} WIN! Profit: ${total_profit:+.2f}")
                            print(f"🔄 GLOBAL RESET: All assets return to Cycle 1")
                            # Reset global cycle to 1
                            global_cycle_tracker['current_cycle'] = 1
                            # Reset all asset steps
                            for a in asset_step_trackers:
                                asset_step_trackers[a]['current_step'] = 1
                        else:
                            print(f"💔 {asset} SEQUENCE COMPLETE! P&L: ${total_profit:+.2f}")
                            # Check if we need to advance global cycle
                            if asset_tracker['current_step'] > 3:
                                # This asset completed all 3 steps - advance global cycle
                                if current_global_cycle < 3:
                                    global_cycle_tracker['current_cycle'] += 1
                                    print(f"🔄 GLOBAL CYCLE ADVANCED: Cycle {current_global_cycle} → Cycle {global_cycle_tracker['current_cycle']}")
                                    print(f"   All upcoming assets will start at Cycle {global_cycle_tracker['current_cycle']}")
                                    # Reset all asset steps for new cycle
                                    for a in asset_step_trackers:
                                        asset_step_trackers[a]['current_step'] = 1
                        
                    except Exception as sequence_error:
                        print(f"❌ Sequence error for {asset}: {sequence_error}")
                    
                    # Show session stats
                    wins = len([t for t in self.trade_history if t['result'] == 'win'])
                    losses = len([t for t in self.trade_history if t['result'] == 'loss'])
                    
                    print(f"\n📊 TRADING SESSION:")
                    print(f"   💰 {self.get_session_status()}")
                    print(f"   🌍 Global Cycle: {global_cycle_tracker['current_cycle']}")
                    print(f"   📈 Total Sequences: {session_trades}")
                    print(f"   🏆 Results: {wins}W/{losses}L")
                    
                    # Check stop conditions
                    should_stop, stop_reason = self.should_stop_trading()
                    if should_stop:
                        print(f"\n{stop_reason}")
                        print(f"🏁 Trading session ended")
                        return
                
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            print(f"\n🛑 TRADING STOPPED BY USER")
        except Exception as e:
            print(f"❌ Trading error: {e}")
        
        # Final stats
        total_wins = len([t for t in self.trade_history if t['result'] == 'win'])
        total_losses = len([t for t in self.trade_history if t['result'] == 'loss'])
        total_profit = sum([t['profit_loss'] for t in self.trade_history])
        
        print(f"\n📊 FINAL STATISTICS:")
        print(f"   💰 {self.get_session_status()}")
        print(f"   🌍 Final Global Cycle: {global_cycle_tracker['current_cycle']}")
        print(f"   📈 Total Sequences: {session_trades}")
        print(f"   🏆 Results: {total_wins}W/{total_losses}L")
        print(f"   💵 Total P&L: ${total_profit:.2f}")

    async def execute_option2_global_sequence(self, asset: str, direction: str, global_tracker: Dict[str, Any], 
                                             asset_tracker: Dict[str, Any], channel: str) -> Tuple[bool, float]:
        """Execute Option 2 sequence with GLOBAL cycle system"""
        current_global_cycle = global_tracker['current_cycle']
        current_step = asset_tracker['current_step']
        config = global_tracker['config']
        total_profit = 0.0
        
        print(f"🔄 Starting sequence: Global Cycle {current_global_cycle}, Step {current_step}")
        
        # Execute steps within current global cycle
        while current_step <= 3:
            # Calculate amount based on GLOBAL cycle and current step
            if current_global_cycle == 1:
                # Cycle 1: Normal 3-step martingale
                amount = config['base_amount'] * (config['multiplier'] ** (current_step - 1))
            elif current_global_cycle == 2:
                # Cycle 2: Continues from Cycle 1's last amount
                cycle_1_last = global_tracker['cycle_1_last_amount']
                cycle_2_step1 = cycle_1_last * config['multiplier']
                amount = cycle_2_step1 * (config['multiplier'] ** (current_step - 1))
            else:  # Cycle 3
                # Cycle 3: Same amounts as Cycle 2 (capped risk)
                cycle_1_last = global_tracker['cycle_1_last_amount']
                cycle_2_step1 = cycle_1_last * config['multiplier']
                amount = cycle_2_step1 * (config['multiplier'] ** (current_step - 1))
            
            print(f"🔄 Global C{current_global_cycle}S{current_step}: ${amount:.2f} | {asset} {direction.upper()}")
            
            try:
                # Execute trade using the same method as Option 1
                won, profit = await self.execute_immediate_trade(asset, direction, amount, channel)
                total_profit += profit
                
                if won:
                    print(f"🎉 WIN Global C{current_global_cycle}S{current_step}!")
                    # WIN resets everything globally
                    return True, total_profit
                else:
                    print(f"💔 LOSS Global C{current_global_cycle}S{current_step}")
                    
                    # Move to next step
                    if current_step < 3:
                        current_step += 1
                        asset_tracker['current_step'] = current_step
                        await asyncio.sleep(0.01)  # 10ms delay
                        continue
                    else:
                        # Completed all 3 steps in this global cycle
                        asset_tracker['current_step'] = 4  # Mark as completed
                        print(f"🔄 Completed all 3 steps in Global Cycle {current_global_cycle}")
                        
                        # Store Cycle 1 last amount if we're in Cycle 1
                        if current_global_cycle == 1:
                            global_tracker['cycle_1_last_amount'] = amount
                        
                        return False, total_profit
            
            except Exception as e:
                print(f"❌ Trade error Global C{current_global_cycle}S{current_step}: {e}")
                # Record as loss and continue
                total_profit -= amount
                
                # Move to next step
                if current_step < 3:
                    current_step += 1
                    asset_tracker['current_step'] = current_step
                    await asyncio.sleep(0.01)
                    continue
                else:
                    # Completed all steps (with errors)
                    asset_tracker['current_step'] = 4
                    if current_global_cycle == 1:
                        global_tracker['cycle_1_last_amount'] = amount
                    return False, total_profit
        
        return False, total_profit
        """Execute Option 2: 3-Cycle Progressive Martingale sequence"""
        current_cycle = tracker['current_cycle']
        current_step = tracker['current_step']
        config = tracker['config']
        total_profit = 0.0
        
        print(f"🔄 Starting Option 2 sequence: C{current_cycle}S{current_step}")
        
        # Continue until WIN or max cycles/steps reached
        while current_cycle <= 3:
            while current_step <= 3:
                # Calculate amount based on cycle and step
                if current_cycle == 1:
                    amount = config['base_amount'] * (config['multiplier'] ** (current_step - 1))
                elif current_cycle == 2:
                    cycle_1_last = tracker['cycle_1_last_amount']
                    cycle_2_step1 = cycle_1_last * config['multiplier']
                    amount = cycle_2_step1 * (config['multiplier'] ** (current_step - 1))
                else:  # Cycle 3
                    cycle_1_last = tracker['cycle_1_last_amount']
                    cycle_2_step1 = cycle_1_last * config['multiplier']
                    amount = cycle_2_step1 * (config['multiplier'] ** (current_step - 1))
                
                print(f"🔄 C{current_cycle}S{current_step}: ${amount:.2f} | {asset} {direction.upper()}")
                
                # Execute trade
                won, profit = await self.execute_single_trade(asset, direction, amount, channel)
                total_profit += profit
                
                if won:
                    print(f"🎉 WIN C{current_cycle}S{current_step}! → Reset to C1S1")
                    # Reset to Cycle 1, Step 1
                    tracker['current_cycle'] = 1
                    tracker['current_step'] = 1
                    tracker['cycle_1_last_amount'] = config['base_amount'] * (config['multiplier'] ** 2)
                    return True, total_profit
                else:
                    print(f"💔 LOSS C{current_cycle}S{current_step}")
                    
                    # Move to next step
                    if current_step < 3:
                        current_step += 1
                        tracker['current_step'] = current_step
                        # Small delay before next step
                        await asyncio.sleep(0.01)
                        continue
                    else:
                        # Completed all steps in cycle
                        if current_cycle == 1:
                            # Store Cycle 1 last amount and move to Cycle 2
                            tracker['cycle_1_last_amount'] = amount
                            tracker['current_cycle'] = 2
                            tracker['current_step'] = 1
                            print(f"🔄 Moving to Cycle 2, Step 1")
                            break
                        elif current_cycle == 2:
                            # Move to Cycle 3
                            tracker['current_cycle'] = 3
                            tracker['current_step'] = 1
                            print(f"🔄 Moving to Cycle 3, Step 1")
                            break
                        else:
                            # Cycle 3 complete - stay in C3S1
                            tracker['current_step'] = 1
                            print(f"🔄 Cycle 3 complete - Staying in C3S1")
                            return False, total_profit
            
            # Move to next cycle
            current_cycle = tracker['current_cycle']
            current_step = tracker['current_step']
        
        return False, total_profit

    async def start_4cycle_trading(self, base_amount: float, multiplier: float = 2.5, is_demo: bool = True):
        """Start 4-Cycle 2-Step Martingale trading: 4 cycles × 2 steps = up to 8 trades"""
        print(f"\n🚀 4-CYCLE 2-STEP MARTINGALE TRADING STARTED")
        print("=" * 60)
        print(f"💰 Base Amount: ${base_amount}")
        print(f"📈 Multiplier: {multiplier}")
        print(f"🔄 Cross-Asset 2-Step System: Extended to 4 cycles")
        print(f"⏳ Logic: Wait for exact signal time → Execute → Cross-asset progression")
        print(f"📅 Date Focus: TODAY ONLY ({get_user_time().strftime('%Y-%m-%d')}) - no future dates")
        print(f"⏰ Timing: Check every 1 second for signal matches")
        print(f"✅ WIN at any step → All assets reset to C1S1")
        print(f"❌ LOSS at Step 1 → Move to Step 2 (same asset, 10ms delay)")
        print(f"❌ LOSS at Step 2 → Next asset starts at next cycle")
        print(f"🔄 Example: EURJPY loses C1S2 → GBPUSD starts at C2S1")
        print(f"🔧 API Health: Consistent timing, channel-specific durations")
        print(f"🆕 Extended: 4 cycles for more recovery opportunities")
        
        # Display stop loss and take profit info
        if self.stop_loss is not None or self.take_profit is not None:
            print(f"💡 Risk Management:")
            if self.stop_loss is not None:
                print(f"   🛑 Stop Loss: ${self.stop_loss:.2f}")
            if self.take_profit is not None:
                print(f"   🎯 Take Profit: ${self.take_profit:.2f}")
        
        print("Press Ctrl+C to stop")
        print("=" * 60)
        
        strategy = FourCycleMartingaleStrategy(base_amount, multiplier)
        session_trades = 0
        processed_signals = set()  # Track processed signals to prevent infinite loops
        
        try:
            # Show initial signal overview
            # Scanning for signals...
            initial_signals = self.get_signals_from_csv()
            if initial_signals:
                print(f"✅ Found {len(initial_signals)} signals in CSV:")
                current_time = get_user_time()
                for i, signal in enumerate(initial_signals[:5]):  # Show first 5
                    time_until = (signal['trade_datetime'] - current_time).total_seconds()
                    wait_minutes = int(time_until // 60)
                    wait_seconds = int(time_until % 60)
                    status = "Ready!" if time_until <= 5 else f"in {wait_minutes}m {wait_seconds}s"
                    print(f"   {i+1}. {signal['asset']} {signal['direction'].upper()} at {signal['signal_time']} ({status})")
                if len(initial_signals) > 5:
                    print(f"   ... and {len(initial_signals) - 5} more signals")
            else:
                print(f"❌ No signals found in CSV - add signals to the selected channel CSV file")
            print("=" * 60)
            
            while True:
                # Get current time
                current_time = get_user_time()
                current_time_str = current_time.strftime('%H:%M:%S')
                
                # Check for stop loss or take profit
                should_stop, stop_reason = self.should_stop_trading()
                if should_stop:
                    print(f"\n{stop_reason}")
                    print("🛑 Trading stopped due to risk management limits")
                    break
                
                # Get fresh signals from CSV
                signals = self.get_signals_from_csv()
                
                if not signals:
                    current_date = current_time.strftime('%Y-%m-%d')
                    current_time_hms = current_time.strftime('%H:%M:%S')
                    status_line = f"{current_date} | {current_time_hms} | No signals available"
                    print(f"\r{status_line:<80}", end="", flush=True)
                    await asyncio.sleep(0.01)  # Check every 10ms
                    continue
                
                # Find next signal
                for signal in signals:
                    signal_time_str = signal['signal_datetime'].strftime('%H:%M:%S')
                    signal_key = f"{signal['asset']}_{signal['direction']}_{signal_time_str}"
                    
                    # Skip if already processed
                    if signal_key in processed_signals:
                        continue
                    
                    # Show current time and signal time
                    # Show clean status line: date | current time | signal time | time remaining
                    current_date = current_time.strftime('%Y-%m-%d')
                    current_time_hms = current_time.strftime('%H:%M:%S')
                    signal_time_hms = signal['signal_datetime'].strftime('%H:%M:%S')
                    time_remaining = format_time_remaining(current_time, signal['signal_datetime'])
                    
                    # Clear line and show clean status
                    status_line = f"{current_date} | {current_time_hms} | {signal_time_hms} | {time_remaining} | {signal['asset']} {signal['direction'].upper()}"
                    print(f"\r{status_line:<80}", end="", flush=True)
                    
                    # Execute when times match exactly
                    if current_time_str == signal_time_str:
                        print(f"\n🎯 EXECUTING: {signal['asset']} {signal['direction'].upper()} at {signal_time_str}")
                        
                        # Mark signal as processed
                        processed_signals.add(signal_key)
                        
                        # Execute trade using 4-cycle strategy
                        try:
                            won, profit, action = await self.execute_single_4cycle_trade(
                                signal['asset'], signal['direction'], base_amount, strategy, signal.get('channel')
                            )
                            
                            # Update session profit
                            self.update_session_profit(profit)
                            session_trades += 1
                            
                            # Show result
                            result_emoji = "✅" if won else "❌"
                            print(f"{result_emoji} {signal['asset']} {'WIN' if won else 'LOSS'} - ${profit:+.2f}")
                            
                            # Handle the action result
                            if action == 'continue':
                                # Need to execute next step immediately
                                print(f"⚡ CONTINUING TO NEXT STEP for {signal['asset']}")
                                await asyncio.sleep(0.01)  # 10ms delay
                                
                                # Execute Step 2 immediately
                                try:
                                    won2, profit2, action2 = await self.execute_single_4cycle_trade(
                                        signal['asset'], signal['direction'], base_amount, strategy, signal.get('channel')
                                    )
                                    
                                    # Update session profit
                                    self.update_session_profit(profit2)
                                    session_trades += 1
                                    
                                    # Show result
                                    result_emoji2 = "✅" if won2 else "❌"
                                    print(f"{result_emoji2} {signal['asset']} Step 2 {'WIN' if won2 else 'LOSS'} - ${profit2:+.2f}")
                                    
                                except Exception as step2_error:
                                    print(f"❌ Step 2 error for {signal['asset']}: {step2_error}")
                            
                            # Show session stats
                            print(f"📊 Session: {self.get_session_status()} | Trades: {session_trades}")
                            
                            # Check stop conditions after trade
                            should_stop, stop_reason = self.should_stop_trading()
                            if should_stop:
                                print(f"\n{stop_reason}")
                                print("🛑 Trading stopped due to risk management limits")
                                return
                            
                        except Exception as trade_error:
                            print(f"❌ Trade error for {signal['asset']}: {trade_error}")
                        
                        break  # Exit signal loop after processing one signal
                
                await asyncio.sleep(0.01)  # Check every 10ms for precise timing
                
                # Clean up old processed signals every minute to prevent memory buildup
                if len(processed_signals) > 100:
                    processed_signals.clear()
                    print(f"\n🧹 Cleaned processed signals cache")
                
        except KeyboardInterrupt:
            print(f"\n🛑 TRADING STOPPED BY USER")
        except Exception as e:
            print(f"❌ Trading error: {e}")
        
        # Final stats
        total_trades = len(self.trade_history)
        total_wins = len([t for t in self.trade_history if t['result'] == 'win'])
        total_losses = len([t for t in self.trade_history if t['result'] == 'loss'])
        
        print(f"\n📊 FINAL STATISTICS:")
        print(f"   💰 {self.get_session_status()}")
        print(f"   📈 Session Trades: {session_trades}")
        print(f"   🏆 Results: {total_wins}W/{total_losses}L")
        print(f"   🎯 Assets Tracked: {len(strategy.get_all_active_assets())}")

    async def start_5cycle_trading(self, base_amount: float, multiplier: float = 2.5, is_demo: bool = True):
        """Start 5-Cycle 2-Step Martingale trading: 5 cycles × 2 steps = up to 10 trades"""
        print(f"\n🚀 5-CYCLE 2-STEP MARTINGALE TRADING STARTED")
        print("=" * 60)
        print(f"💰 Base Amount: ${base_amount}")
        print(f"📈 Multiplier: {multiplier}")
        print(f"🔄 Cross-Asset 2-Step System: Precise timing with 1-second checks")
        print(f"⏳ Logic: Wait for exact signal time → Execute → Cross-asset progression")
        print(f"📅 Date Focus: TODAY ONLY ({get_user_time().strftime('%Y-%m-%d')}) - no future dates")
        print(f"⏰ Timing: Check every 1 second for signal matches")
        print(f"✅ WIN at any step → All assets reset to C1S1")
        print(f"❌ LOSS at Step 1 → Move to Step 2 (same asset, 10ms delay)")
        print(f"❌ LOSS at Step 2 → Next asset starts at next cycle")
        print(f"🔄 Example: EURJPY loses C1S2 → GBPUSD starts at C2S1")
        print(f"🔧 API Health: Consistent timing, channel-specific durations")
        print(f"🎯 Extended to 5 cycles for maximum recovery opportunities")
        
        # Display stop loss and take profit info
        if self.stop_loss is not None or self.take_profit is not None:
            print(f"💡 Risk Management:")
            if self.stop_loss is not None:
                print(f"   🛑 Stop Loss: ${self.stop_loss:.2f}")
            if self.take_profit is not None:
                print(f"   🎯 Take Profit: ${self.take_profit:.2f}")
        
        print("Press Ctrl+C to stop")
        print("=" * 60)
        
        strategy = FiveCycleMartingaleStrategy(base_amount, multiplier)
        session_trades = 0
        processed_signals = set()  # Track processed signals to prevent infinite loops
        
        try:
            # Show initial signal overview
            # Scanning for signals...
            initial_signals = self.get_signals_from_csv()
            if initial_signals:
                print(f"✅ Found {len(initial_signals)} signals in CSV:")
                current_time = get_user_time()
                for i, signal in enumerate(initial_signals[:5]):  # Show first 5
                    time_until = (signal['trade_datetime'] - current_time).total_seconds()
                    wait_minutes = int(time_until // 60)
                    wait_seconds = int(time_until % 60)
                    status = "Ready!" if time_until <= 5 else f"in {wait_minutes}m {wait_seconds}s"
                    print(f"   {i+1}. {signal['asset']} {signal['direction'].upper()} at {signal['signal_time']} ({status})")
                if len(initial_signals) > 5:
                    print(f"   ... and {len(initial_signals) - 5} more signals")
            else:
                print(f"❌ No signals found in CSV - add signals to the selected channel CSV file")
            print("=" * 60)
            
            while True:
                # Get current time
                current_time = get_user_time()
                current_time_str = current_time.strftime('%H:%M:%S')
                
                # Check for stop loss or take profit
                should_stop, stop_reason = self.should_stop_trading()
                if should_stop:
                    print(f"\n{stop_reason}")
                    print("🛑 Trading stopped due to risk management limits")
                    break
                
                # Get fresh signals from CSV
                signals = self.get_signals_from_csv()
                
                if not signals:
                    current_date = current_time.strftime('%Y-%m-%d')
                    current_time_hms = current_time.strftime('%H:%M:%S')
                    status_line = f"{current_date} | {current_time_hms} | No signals available"
                    print(f"\r{status_line:<80}", end="", flush=True)
                    await asyncio.sleep(0.01)  # Check every 10ms
                    continue
                
                # Find next signal
                for signal in signals:
                    signal_time_str = signal['signal_datetime'].strftime('%H:%M:%S')
                    signal_key = f"{signal['asset']}_{signal['direction']}_{signal_time_str}"
                    
                    # Skip if already processed
                    if signal_key in processed_signals:
                        continue
                    
                    # Show current time and signal time
                    # Show clean status line: date | current time | signal time | time remaining
                    current_date = current_time.strftime('%Y-%m-%d')
                    current_time_hms = current_time.strftime('%H:%M:%S')
                    signal_time_hms = signal['signal_datetime'].strftime('%H:%M:%S')
                    time_remaining = format_time_remaining(current_time, signal['signal_datetime'])
                    
                    # Clear line and show clean status
                    status_line = f"{current_date} | {current_time_hms} | {signal_time_hms} | {time_remaining} | {signal['asset']} {signal['direction'].upper()}"
                    print(f"\r{status_line:<80}", end="", flush=True)
                    
                    # Execute when times match exactly
                    if current_time_str == signal_time_str:
                        print(f"\n🎯 EXECUTING: {signal['asset']} {signal['direction'].upper()} at {signal_time_str}")
                        
                        # Mark signal as processed
                        processed_signals.add(signal_key)
                        
                        # Execute trade using 5-cycle strategy
                        try:
                            won, profit, action = await self.execute_single_5cycle_trade(
                                signal['asset'], signal['direction'], base_amount, strategy, signal.get('channel')
                            )
                            
                            # Update session profit
                            self.update_session_profit(profit)
                            session_trades += 1
                            
                            # Show result
                            result_emoji = "✅" if won else "❌"
                            print(f"{result_emoji} {signal['asset']} {'WIN' if won else 'LOSS'} - ${profit:+.2f}")
                            
                            # Handle the action result
                            if action == 'continue':
                                # Need to execute next step immediately
                                print(f"⚡ CONTINUING TO NEXT STEP for {signal['asset']}")
                                await asyncio.sleep(0.01)  # 10ms delay
                                
                                # Execute Step 2 immediately
                                try:
                                    won2, profit2, action2 = await self.execute_single_5cycle_trade(
                                        signal['asset'], signal['direction'], base_amount, strategy, signal.get('channel')
                                    )
                                    
                                    # Update session profit
                                    self.update_session_profit(profit2)
                                    session_trades += 1
                                    
                                    # Show result
                                    result_emoji2 = "✅" if won2 else "❌"
                                    print(f"{result_emoji2} {signal['asset']} Step 2 {'WIN' if won2 else 'LOSS'} - ${profit2:+.2f}")
                                    
                                except Exception as step2_error:
                                    print(f"❌ Step 2 error for {signal['asset']}: {step2_error}")
                            
                            # Show session stats
                            print(f"📊 Session: {self.get_session_status()} | Trades: {session_trades}")
                            
                            # Check stop conditions after trade
                            should_stop, stop_reason = self.should_stop_trading()
                            if should_stop:
                                print(f"\n{stop_reason}")
                                print("🛑 Trading stopped due to risk management limits")
                                return
                            
                        except Exception as trade_error:
                            print(f"❌ Trade error for {signal['asset']}: {trade_error}")
                        
                        break  # Exit signal loop after processing one signal
                
                await asyncio.sleep(0.01)  # Check every 10ms for precise timing
                
                # Clean up old processed signals every minute to prevent memory buildup
                if len(processed_signals) > 100:
                    processed_signals.clear()
                    print(f"\n🧹 Cleaned processed signals cache")
                
        except KeyboardInterrupt:
            print(f"\n🛑 TRADING STOPPED BY USER")
        except Exception as e:
            print(f"❌ Trading error: {e}")
        
        # Final stats
        total_trades = len(self.trade_history)
        total_wins = len([t for t in self.trade_history if t['result'] == 'win'])
        total_losses = len([t for t in self.trade_history if t['result'] == 'loss'])
        
        print(f"\n📊 FINAL STATISTICS:")
        print(f"   💰 {self.get_session_status()}")
        print(f"   📈 Session Trades: {session_trades}")
        print(f"   🏆 Results: {total_wins}W/{total_losses}L")
        print(f"   🎯 Assets Tracked: {len(strategy.get_all_active_assets())}")

    async def start_2step_trading(self, base_amount: float, multiplier: float = 2.5, is_demo: bool = True):
        """Start 3-Cycle 2-Step Martingale trading: 3 cycles × 2 steps = up to 6 trades"""
        print(f"\n🚀 3-CYCLE 2-STEP MARTINGALE TRADING STARTED")
        print("=" * 60)
        print(f"💰 Base Amount: ${base_amount}")
        print(f"📈 Multiplier: {multiplier}")
        print(f"🔄 Cross-Asset 2-Step System: Precise timing with 1-second checks")
        print(f"⏳ Logic: Wait for exact signal time → Execute → Cross-asset progression")
        print(f"📅 Date Focus: TODAY ONLY ({get_user_time().strftime('%Y-%m-%d')}) - no future dates")
        print(f"⏰ Timing: Check every 1 second for signal matches")
        print(f"✅ WIN at any step → All assets reset to C1S1")
        print(f"❌ LOSS at Step 1 → Move to Step 2 (same asset, 10ms delay)")
        print(f"❌ LOSS at Step 2 → Next asset starts at next cycle")
        print(f"🔄 Example: EURJPY loses C1S2 → GBPUSD starts at C2S1")
        print(f"🔧 API Health: Consistent timing, channel-specific durations")
        
        # Display stop loss and take profit info
        if self.stop_loss is not None or self.take_profit is not None:
            print(f"💡 Risk Management:")
            if self.stop_loss is not None:
                print(f"   🛑 Stop Loss: ${self.stop_loss:.2f}")
            if self.take_profit is not None:
                print(f"   🎯 Take Profit: ${self.take_profit:.2f}")
        
        print("Press Ctrl+C to stop")
        print("=" * 60)
        
        strategy = TwoStepMartingaleStrategy(base_amount, multiplier)
        session_trades = 0
        
        try:
            # Show initial signal overview
            # Scanning for signals...
            initial_signals = self.get_signals_from_csv()
            if initial_signals:
                print(f"✅ Found {len(initial_signals)} signals in CSV:")
                current_time = get_user_time()
                for i, signal in enumerate(initial_signals[:5]):  # Show first 5
                    time_until = (signal['trade_datetime'] - current_time).total_seconds()
                    wait_minutes = int(time_until // 60)
                    wait_seconds = int(time_until % 60)
                    status = "Ready!" if time_until <= 5 else f"in {wait_minutes}m {wait_seconds}s"
                    print(f"   {i+1}. {signal['asset']} {signal['direction'].upper()} at {signal['signal_time']} ({status})")
                if len(initial_signals) > 5:
                    print(f"   ... and {len(initial_signals) - 5} more signals")
            else:
                print(f"❌ No signals found in CSV - add signals to the selected channel CSV file")
            print("=" * 60)
            
            while True:
                # Get current time
                current_time = get_user_time()
                current_time_str = current_time.strftime('%H:%M:%S')
                
                # Check for stop loss or take profit
                should_stop, stop_reason = self.should_stop_trading()
                if should_stop:
                    print(f"\n{stop_reason}")
                    print("🛑 Trading stopped due to risk management limits")
                    break
                
                # Get fresh signals from CSV
                signals = self.get_signals_from_csv()
                
                if not signals:
                    current_date = current_time.strftime('%Y-%m-%d')
                    current_time_hms = current_time.strftime('%H:%M:%S')
                    status_line = f"{current_date} | {current_time_hms} | No signals available"
                    print(f"\r{status_line:<80}", end="", flush=True)
                    await asyncio.sleep(0.01)  # Check every 10ms
                    continue
                
                # Find next signal
                for signal in signals:
                    signal_time_str = signal['signal_datetime'].strftime('%H:%M:%S')
                    
                    # Show current time and signal time
                    # Show clean status line: date | current time | signal time | time remaining
                    current_date = current_time.strftime('%Y-%m-%d')
                    current_time_hms = current_time.strftime('%H:%M:%S')
                    signal_time_hms = signal['signal_datetime'].strftime('%H:%M:%S')
                    time_remaining = format_time_remaining(current_time, signal['signal_datetime'])
                    
                    # Clear line and show clean status
                    status_line = f"{current_date} | {current_time_hms} | {signal_time_hms} | {time_remaining} | {signal['asset']} {signal['direction'].upper()}"
                    print(f"\r{status_line:<80}", end="", flush=True)
                    
                    # Execute when times match exactly
                    if current_time_str == signal_time_str:
                        print(f"\n🎯 EXECUTING: {signal['asset']} {signal['direction'].upper()} at {signal_time_str}")
                        
                        # Execute trade
                        try:
                            won, profit, action = await self.execute_single_2step_trade(
                                signal['asset'], signal['direction'], base_amount, strategy, signal.get('channel')
                            )
                            
                            # Update session profit
                            self.update_session_profit(profit)
                            session_trades += 1
                            
                            # Show result
                            result_emoji = "✅" if won else "❌"
                            print(f"{result_emoji} {signal['asset']} {'WIN' if won else 'LOSS'} - ${profit:+.2f}")
                            
                            # Handle the action result
                            if action == 'continue':
                                # Need to execute next step immediately
                                print(f"⚡ CONTINUING TO NEXT STEP for {signal['asset']}")
                                await asyncio.sleep(0.01)  # 10ms delay
                                
                                # Execute next step immediately
                                try:
                                    won2, profit2, action2 = await self.execute_single_2step_trade(
                                        signal['asset'], signal['direction'], base_amount, strategy, signal.get('channel')
                                    )
                                    
                                    # Update session profit for step 2
                                    self.update_session_profit(profit2)
                                    session_trades += 1
                                    
                                    # Show step 2 result
                                    result_emoji2 = "✅" if won2 else "❌"
                                    print(f"{result_emoji2} {signal['asset']} STEP 2 {'WIN' if won2 else 'LOSS'} - ${profit2:+.2f}")
                                    
                                except Exception as e2:
                                    print(f"❌ Step 2 Error: {e2}")
                            
                        except Exception as e:
                            print(f"❌ Error: {e}")
                        
                        break
                    
                    break  # Show only first signal
                
                await asyncio.sleep(0.01)  # Check every 10ms
                
        except KeyboardInterrupt:
            print(f"\n\n🛑 3-CYCLE 2-STEP MARTINGALE TRADING STOPPED")
            print("=" * 60)
            print(f"📊 SESSION SUMMARY:")
            print(f"   🎯 Total Signals Processed: {session_trades}")
            print(f"   💰 Final P&L: ${self.session_profit:+.2f}")
            
            # Show final strategy status
            strategy.show_strategy_status()
            
            print("=" * 60)
            print("👋 Thank you for using the 3-Cycle 2-Step Martingale Trader!")

    async def start_3step_trading(self, base_amount: float, multiplier: float = 2.5, is_demo: bool = True):
        """Start 3-Cycle 3-Step Martingale trading: 3 cycles × 3 steps = up to 9 trades"""
        print(f"\n🚀 3-CYCLE 3-STEP MARTINGALE TRADING STARTED")
        print("=" * 60)
        print(f"💰 Base Amount: ${base_amount}")
        print(f"📈 Multiplier: {multiplier}")
        print(f"🔄 Cross-Asset 3-Step System: Precise timing with 1-second checks")
        print(f"⏳ Logic: Wait for exact signal time → Execute → Cross-asset progression")
        print(f"📅 Date Focus: TODAY ONLY ({get_user_time().strftime('%Y-%m-%d')}) - no future dates")
        print(f"⏰ Timing: Check every 1 second for signal matches")
        print(f"✅ WIN at any step → All assets reset to C1S1")
        print(f"❌ LOSS at Step 1 → Move to Step 2 (same asset, 10ms delay)")
        print(f"❌ LOSS at Step 2 → Move to Step 3 (same asset, 10ms delay)")
        print(f"❌ LOSS at Step 3 → Next asset starts at next cycle")
        print(f"🔄 Example: EURJPY loses C1S3 → GBPUSD starts at C2S1")
        print(f"🔧 API Health: Consistent timing, channel-specific durations")
        
        # Display stop loss and take profit info
        if self.stop_loss is not None or self.take_profit is not None:
            print(f"💡 Risk Management:")
            if self.stop_loss is not None:
                print(f"   🛑 Stop Loss: ${self.stop_loss:.2f}")
            if self.take_profit is not None:
                print(f"   🎯 Take Profit: ${self.take_profit:.2f}")
        
        print("Press Ctrl+C to stop")
        print("=" * 60)
        
        strategy = ThreeStepMartingaleStrategy(base_amount, multiplier)
        session_trades = 0
        
        try:
            # Show initial signal overview
            # Scanning for signals...
            initial_signals = self.get_signals_from_csv()
            if initial_signals:
                print(f"✅ Found {len(initial_signals)} signals in CSV:")
                current_time = get_user_time()
                for i, signal in enumerate(initial_signals[:5]):  # Show first 5
                    time_until = (signal['trade_datetime'] - current_time).total_seconds()
                    wait_minutes = int(time_until // 60)
                    wait_seconds = int(time_until % 60)
                    status = "Ready!" if time_until <= 5 else f"in {wait_minutes}m {wait_seconds}s"
                    print(f"   {i+1}. {signal['asset']} {signal['direction'].upper()} at {signal['signal_time']} ({status})")
                if len(initial_signals) > 5:
                    print(f"   ... and {len(initial_signals) - 5} more signals")
            else:
                print(f"❌ No signals found in CSV - add signals to the selected channel CSV file")
            print("=" * 60)
            
            while True:
                # Get current time
                current_time = get_user_time()
                current_time_str = current_time.strftime('%H:%M:%S')
                
                # Check for stop loss or take profit
                should_stop, stop_reason = self.should_stop_trading()
                if should_stop:
                    print(f"\n{stop_reason}")
                    print("🛑 Trading stopped due to risk management limits")
                    break
                
                # Get fresh signals from CSV
                signals = self.get_signals_from_csv()
                
                if not signals:
                    current_date = current_time.strftime('%Y-%m-%d')
                    current_time_hms = current_time.strftime('%H:%M:%S')
                    status_line = f"{current_date} | {current_time_hms} | No signals available"
                    print(f"\r{status_line:<80}", end="", flush=True)
                    await asyncio.sleep(0.01)  # Check every 10ms
                    continue
                
                # Find next signal
                for signal in signals:
                    signal_time_str = signal['signal_datetime'].strftime('%H:%M:%S')
                    
                    # Show current time and signal time
                    # Show clean status line: date | current time | signal time | time remaining
                    current_date = current_time.strftime('%Y-%m-%d')
                    current_time_hms = current_time.strftime('%H:%M:%S')
                    signal_time_hms = signal['signal_datetime'].strftime('%H:%M:%S')
                    time_remaining = format_time_remaining(current_time, signal['signal_datetime'])
                    
                    # Clear line and show clean status
                    status_line = f"{current_date} | {current_time_hms} | {signal_time_hms} | {time_remaining} | {signal['asset']} {signal['direction'].upper()}"
                    print(f"\r{status_line:<80}", end="", flush=True)
                    
                    # Execute when times match exactly
                    if current_time_str == signal_time_str:
                        print(f"\n🎯 EXECUTING: {signal['asset']} {signal['direction'].upper()} at {signal_time_str}")
                        
                        # Execute trade
                        try:
                            won, profit, action = await self.execute_single_3step_trade(
                                signal['asset'], signal['direction'], base_amount, strategy, signal.get('channel')
                            )
                            
                            # Update session profit
                            self.update_session_profit(profit)
                            session_trades += 1
                            
                            # Show result
                            result_emoji = "✅" if won else "❌"
                            print(f"{result_emoji} {signal['asset']} {'WIN' if won else 'LOSS'} - ${profit:+.2f}")
                            
                            # Handle the action result
                            if action == 'continue':
                                # Need to execute next step immediately
                                print(f"⚡ CONTINUING TO NEXT STEP for {signal['asset']}")
                                await asyncio.sleep(0.01)  # 10ms delay
                                
                                # Execute next step immediately
                                try:
                                    won2, profit2, action2 = await self.execute_single_3step_trade(
                                        signal['asset'], signal['direction'], base_amount, strategy, signal.get('channel')
                                    )
                                    
                                    # Update session profit for step 2
                                    self.update_session_profit(profit2)
                                    session_trades += 1
                                    
                                    # Show step 2 result
                                    result_emoji2 = "✅" if won2 else "❌"
                                    print(f"{result_emoji2} {signal['asset']} STEP 2 {'WIN' if won2 else 'LOSS'} - ${profit2:+.2f}")
                                    
                                    # Handle step 2 action result
                                    if action2 == 'continue':
                                        # Need to execute step 3 immediately
                                        print(f"⚡ CONTINUING TO STEP 3 for {signal['asset']}")
                                        await asyncio.sleep(0.01)  # 10ms delay
                                        
                                        # Execute step 3 immediately
                                        try:
                                            won3, profit3, action3 = await self.execute_single_3step_trade(
                                                signal['asset'], signal['direction'], base_amount, strategy, signal.get('channel')
                                            )
                                            
                                            # Update session profit for step 3
                                            self.update_session_profit(profit3)
                                            session_trades += 1
                                            
                                            # Show step 3 result
                                            result_emoji3 = "✅" if won3 else "❌"
                                            print(f"{result_emoji3} {signal['asset']} STEP 3 {'WIN' if won3 else 'LOSS'} - ${profit3:+.2f}")
                                            
                                        except Exception as e3:
                                            print(f"❌ Step 3 Error: {e3}")
                                    
                                except Exception as e2:
                                    print(f"❌ Step 2 Error: {e2}")
                            
                        except Exception as e:
                            print(f"❌ Error: {e}")
                        
                        break
                    
                    break  # Show only first signal
                
                await asyncio.sleep(0.01)  # Check every 10ms
                
        except KeyboardInterrupt:
            print(f"\n\n🛑 3-CYCLE 3-STEP MARTINGALE TRADING STOPPED")
            print("=" * 60)
            print(f"📊 SESSION SUMMARY:")
            print(f"   🎯 Total Signals Processed: {session_trades}")
            print(f"   💰 Final P&L: ${self.session_profit:+.2f}")
            
            # Show final strategy status
            strategy.show_strategy_status()
            
            print("=" * 60)
            print("👋 Thank you for using the 3-Cycle 3-Step Martingale Trader!")

    async def start_2cycle_2step_trading(self, base_amount: float, multiplier: float = 2.5, is_demo: bool = True):
        """Start 2-Cycle 2-Step Martingale trading: 2 cycles × 2 steps = up to 4 trades"""
        print(f"\n🚀 2-CYCLE 2-STEP MARTINGALE TRADING STARTED")
        print("=" * 60)
        print(f"💰 Base Amount: ${base_amount}")
        print(f"📈 Multiplier: {multiplier}")
        print(f"🔄 Cross-Asset 2-Step System: Precise timing with 1-second checks")
        print(f"⏳ Logic: Wait for exact signal time → Execute → Cross-asset progression")
        print(f"📅 Date Focus: TODAY ONLY ({get_user_time().strftime('%Y-%m-%d')}) - no future dates")
        print(f"⏰ Timing: Check every 1 second for signal matches")
        print(f"✅ WIN at any step → All assets reset to C1S1")
        print(f"❌ LOSS at Step 1 → Move to Step 2 (same asset, 10ms delay)")
        print(f"❌ LOSS at Step 2 → Next asset starts at next cycle")
        print(f"🔄 Example: EURJPY loses C1S2 → GBPUSD starts at C2S1")
        print(f"🔧 API Health: Consistent timing, channel-specific durations")
        
        # Display stop loss and take profit info
        if self.stop_loss is not None or self.take_profit is not None:
            print(f"💡 Risk Management:")
            if self.stop_loss is not None:
                print(f"   🛑 Stop Loss: ${self.stop_loss:.2f}")
            if self.take_profit is not None:
                print(f"   🎯 Take Profit: ${self.take_profit:.2f}")
        
        print("Press Ctrl+C to stop")
        print("=" * 60)
        
        strategy = TwoCycleTwoStepMartingaleStrategy(base_amount, multiplier)
        session_trades = 0
        
        try:
            # Show initial signal overview
            initial_signals = self.get_signals_from_csv()
            if initial_signals:
                print(f"✅ Found {len(initial_signals)} signals in CSV:")
                current_time = get_user_time()
                for i, signal in enumerate(initial_signals[:5]):  # Show first 5
                    time_until = (signal['trade_datetime'] - current_time).total_seconds()
                    wait_minutes = int(time_until // 60)
                    wait_seconds = int(time_until % 60)
                    status = "Ready!" if time_until <= 5 else f"in {wait_minutes}m {wait_seconds}s"
                    print(f"   {i+1}. {signal['asset']} {signal['direction'].upper()} at {signal['signal_time']} ({status})")
                if len(initial_signals) > 5:
                    print(f"   ... and {len(initial_signals) - 5} more signals")
            else:
                print(f"❌ No signals found in CSV - add signals to the selected channel CSV file")
            print("=" * 60)
            
            while True:
                # Get current time
                current_time = get_user_time()
                current_time_str = current_time.strftime('%H:%M:%S')
                
                # Check for stop loss or take profit
                should_stop, stop_reason = self.should_stop_trading()
                if should_stop:
                    print(f"\n{stop_reason}")
                    print("🛑 Trading stopped due to risk management limits")
                    break
                
                # Get fresh signals from CSV
                signals = self.get_signals_from_csv()
                
                if not signals:
                    current_date = current_time.strftime('%Y-%m-%d')
                    current_time_hms = current_time.strftime('%H:%M:%S')
                    status_line = f"{current_date} | {current_time_hms} | No signals available"
                    print(f"\r{status_line:<80}", end="", flush=True)
                    await asyncio.sleep(0.01)  # Check every 10ms
                    continue
                
                # Find next signal
                for signal in signals:
                    signal_time_str = signal['signal_datetime'].strftime('%H:%M:%S')
                    
                    # Show current time and signal time
                    current_date = current_time.strftime('%Y-%m-%d')
                    current_time_hms = current_time.strftime('%H:%M:%S')
                    signal_time_hms = signal['signal_datetime'].strftime('%H:%M:%S')
                    time_remaining = format_time_remaining(current_time, signal['signal_datetime'])
                    
                    # Clear line and show clean status
                    status_line = f"{current_date} | {current_time_hms} | {signal_time_hms} | {time_remaining} | {signal['asset']} {signal['direction'].upper()}"
                    print(f"\r{status_line:<80}", end="", flush=True)
                    
                    # Execute when times match exactly
                    if current_time_str == signal_time_str:
                        print(f"\n🎯 EXECUTING: {signal['asset']} {signal['direction'].upper()} at {signal_time_str}")
                        
                        # Execute trade using 2-cycle 2-step strategy
                        try:
                            won, profit, action = await self.execute_single_2cycle_2step_trade(
                                signal['asset'], signal['direction'], base_amount, strategy, signal.get('channel')
                            )
                            
                            # Update session profit
                            self.update_session_profit(profit)
                            session_trades += 1
                            
                            # Show result
                            result_emoji = "✅" if won else "❌"
                            print(f"{result_emoji} {signal['asset']} {'WIN' if won else 'LOSS'} - ${profit:+.2f}")
                            
                            # Handle the action result
                            if action == 'continue':
                                # Need to execute next step immediately
                                print(f"⚡ CONTINUING TO NEXT STEP for {signal['asset']}")
                                await asyncio.sleep(0.01)  # 10ms delay
                                
                                # Execute next step immediately
                                try:
                                    won2, profit2, action2 = await self.execute_single_2cycle_2step_trade(
                                        signal['asset'], signal['direction'], base_amount, strategy, signal.get('channel')
                                    )
                                    
                                    # Update session profit for step 2
                                    self.update_session_profit(profit2)
                                    session_trades += 1
                                    
                                    # Show step 2 result
                                    result_emoji2 = "✅" if won2 else "❌"
                                    print(f"{result_emoji2} {signal['asset']} STEP 2 {'WIN' if won2 else 'LOSS'} - ${profit2:+.2f}")
                                    
                                except Exception as e2:
                                    print(f"❌ Step 2 Error: {e2}")
                            
                        except Exception as e:
                            print(f"❌ Error: {e}")
                        
                        break
                    
                    break  # Show only first signal
                
                await asyncio.sleep(0.01)  # Check every 10ms
                
        except KeyboardInterrupt:
            print(f"\n\n🛑 2-CYCLE 2-STEP MARTINGALE TRADING STOPPED")
            print("=" * 60)
            print(f"📊 SESSION SUMMARY:")
            print(f"   🎯 Total Signals Processed: {session_trades}")
            print(f"   💰 Final P&L: ${self.session_profit:+.2f}")
            
            # Show final strategy status
            strategy.show_strategy_status()
            
            print("=" * 60)
            print("👋 Thank you for using the 2-Cycle 2-Step Martingale Trader!")

    async def start_2cycle_3step_trading(self, base_amount: float, multiplier: float = 2.5, is_demo: bool = True):
        """Start 2-Cycle 3-Step Martingale trading: 2 cycles × 3 steps = up to 6 trades (Step 4 = sum of first 3)"""
        print(f"\n🚀 2-CYCLE 3-STEP MARTINGALE TRADING STARTED")
        print("=" * 60)
        print(f"💰 Base Amount: ${base_amount}")
        print(f"📈 Multiplier: {multiplier}")
        print(f"🔄 Cross-Asset 3-Step System: Precise timing with 1-second checks")
        print(f"⏳ Logic: Wait for exact signal time → Execute → Cross-asset progression")
        print(f"📅 Date Focus: TODAY ONLY ({get_user_time().strftime('%Y-%m-%d')}) - no future dates")
        print(f"⏰ Timing: Check every 1 second for signal matches")
        print(f"✅ WIN at any step → All assets reset to C1S1")
        print(f"❌ LOSS at Step 1 → Move to Step 2 (same asset, 10ms delay)")
        print(f"❌ LOSS at Step 2 → Move to Step 3 (same asset, 10ms delay)")
        print(f"❌ LOSS at Step 3 → Next asset starts at next cycle")
        print(f"🔄 Example: EURJPY loses C1S3 → GBPUSD starts at C2S1")
        print(f"🔧 Special Logic: Step 4 (C2S1) = Sum of first 3 steps")
        
        # Display stop loss and take profit info
        if self.stop_loss is not None or self.take_profit is not None:
            print(f"💡 Risk Management:")
            if self.stop_loss is not None:
                print(f"   🛑 Stop Loss: ${self.stop_loss:.2f}")
            if self.take_profit is not None:
                print(f"   🎯 Take Profit: ${self.take_profit:.2f}")
        
        print("Press Ctrl+C to stop")
        print("=" * 60)
        
        strategy = TwoCycleThreeStepMartingaleStrategy(base_amount, multiplier)
        session_trades = 0
        
        try:
            # Show initial signal overview
            initial_signals = self.get_signals_from_csv()
            if initial_signals:
                print(f"✅ Found {len(initial_signals)} signals in CSV:")
                current_time = get_user_time()
                for i, signal in enumerate(initial_signals[:5]):  # Show first 5
                    time_until = (signal['trade_datetime'] - current_time).total_seconds()
                    wait_minutes = int(time_until // 60)
                    wait_seconds = int(time_until % 60)
                    status = "Ready!" if time_until <= 5 else f"in {wait_minutes}m {wait_seconds}s"
                    print(f"   {i+1}. {signal['asset']} {signal['direction'].upper()} at {signal['signal_time']} ({status})")
                if len(initial_signals) > 5:
                    print(f"   ... and {len(initial_signals) - 5} more signals")
            else:
                print(f"❌ No signals found in CSV - add signals to the selected channel CSV file")
            print("=" * 60)
            
            while True:
                # Get current time
                current_time = get_user_time()
                current_time_str = current_time.strftime('%H:%M:%S')
                
                # Check for stop loss or take profit
                should_stop, stop_reason = self.should_stop_trading()
                if should_stop:
                    print(f"\n{stop_reason}")
                    print("🛑 Trading stopped due to risk management limits")
                    break
                
                # Get fresh signals from CSV
                signals = self.get_signals_from_csv()
                
                if not signals:
                    current_date = current_time.strftime('%Y-%m-%d')
                    current_time_hms = current_time.strftime('%H:%M:%S')
                    status_line = f"{current_date} | {current_time_hms} | No signals available"
                    print(f"\r{status_line:<80}", end="", flush=True)
                    await asyncio.sleep(0.01)  # Check every 10ms
                    continue
                
                # Find next signal
                for signal in signals:
                    signal_time_str = signal['signal_datetime'].strftime('%H:%M:%S')
                    
                    # Show current time and signal time
                    current_date = current_time.strftime('%Y-%m-%d')
                    current_time_hms = current_time.strftime('%H:%M:%S')
                    signal_time_hms = signal['signal_datetime'].strftime('%H:%M:%S')
                    time_remaining = format_time_remaining(current_time, signal['signal_datetime'])
                    
                    # Clear line and show clean status
                    status_line = f"{current_date} | {current_time_hms} | {signal_time_hms} | {time_remaining} | {signal['asset']} {signal['direction'].upper()}"
                    print(f"\r{status_line:<80}", end="", flush=True)
                    
                    # Execute when times match exactly
                    if current_time_str == signal_time_str:
                        print(f"\n🎯 EXECUTING: {signal['asset']} {signal['direction'].upper()} at {signal_time_str}")
                        
                        # Execute trade using 2-cycle 3-step strategy
                        try:
                            won, profit, action = await self.execute_single_2cycle_3step_trade(
                                signal['asset'], signal['direction'], base_amount, strategy, signal.get('channel')
                            )
                            
                            # Update session profit
                            self.update_session_profit(profit)
                            session_trades += 1
                            
                            # Show result
                            result_emoji = "✅" if won else "❌"
                            print(f"{result_emoji} {signal['asset']} {'WIN' if won else 'LOSS'} - ${profit:+.2f}")
                            
                            # Handle the action result for 3-step progression
                            if action == 'continue':
                                # Need to execute next step immediately
                                current_step = strategy.get_asset_step(signal['asset'])
                                print(f"⚡ CONTINUING TO STEP {current_step} for {signal['asset']}")
                                await asyncio.sleep(0.01)  # 10ms delay
                                
                                # Execute next step immediately
                                try:
                                    won2, profit2, action2 = await self.execute_single_2cycle_3step_trade(
                                        signal['asset'], signal['direction'], base_amount, strategy, signal.get('channel')
                                    )
                                    
                                    # Update session profit
                                    self.update_session_profit(profit2)
                                    session_trades += 1
                                    
                                    # Show result
                                    result_emoji2 = "✅" if won2 else "❌"
                                    current_step2 = strategy.get_asset_step(signal['asset']) - 1  # Previous step
                                    print(f"{result_emoji2} {signal['asset']} STEP {current_step2} {'WIN' if won2 else 'LOSS'} - ${profit2:+.2f}")
                                    
                                    # Check if we need to continue to step 3
                                    if action2 == 'continue':
                                        print(f"⚡ CONTINUING TO STEP 3 for {signal['asset']}")
                                        await asyncio.sleep(0.01)  # 10ms delay
                                        
                                        try:
                                            won3, profit3, action3 = await self.execute_single_2cycle_3step_trade(
                                                signal['asset'], signal['direction'], base_amount, strategy, signal.get('channel')
                                            )
                                            
                                            # Update session profit
                                            self.update_session_profit(profit3)
                                            session_trades += 1
                                            
                                            # Show result
                                            result_emoji3 = "✅" if won3 else "❌"
                                            print(f"{result_emoji3} {signal['asset']} STEP 3 {'WIN' if won3 else 'LOSS'} - ${profit3:+.2f}")
                                            
                                        except Exception as e3:
                                            print(f"❌ Step 3 Error: {e3}")
                                    
                                except Exception as e2:
                                    print(f"❌ Step 2 Error: {e2}")
                            
                        except Exception as e:
                            print(f"❌ Error: {e}")
                        
                        break
                    
                    break  # Show only first signal
                
                await asyncio.sleep(0.01)  # Check every 10ms
                
        except KeyboardInterrupt:
            print(f"\n\n🛑 2-CYCLE 3-STEP MARTINGALE TRADING STOPPED")
            print("=" * 60)
            print(f"📊 SESSION SUMMARY:")
            print(f"   🎯 Total Signals Processed: {session_trades}")
            print(f"   💰 Final P&L: ${self.session_profit:+.2f}")
            
            # Show final strategy status
            strategy.show_strategy_status()
            
            print("=" * 60)
            print("👋 Thank you for using the 2-Cycle 3-Step Martingale Trader!")

    async def start_date_specific_trading(self, target_date: str, base_amount: float, strategy_type: str = "3step", multiplier: float = 2.5, is_demo: bool = True):
        """Start trading for a specific date continuously"""
        print(f"\n🚀 DATE-SPECIFIC TRADING STARTED")
        print("=" * 60)
        print(f"📅 Target Date: {target_date}")
        print(f"💰 Base Amount: ${base_amount}")
        print(f"📈 Strategy: {strategy_type}")
        print(f"🔄 Multiplier: {multiplier}")
        print(f"🎯 Channel: {self.active_channel}")
        print(f"⏰ Running continuously for signals on {target_date}")
        
        # Display stop loss and take profit info
        if self.stop_loss is not None or self.take_profit is not None:
            print(f"💡 Risk Management:")
            if self.stop_loss is not None:
                print(f"   🛑 Stop Loss: ${self.stop_loss:.2f}")
            if self.take_profit is not None:
                print(f"   🎯 Take Profit: ${self.take_profit:.2f}")
        
        print("Press Ctrl+C to stop")
        print("=" * 60)
        
        # Initialize strategy based on type
        if strategy_type == "2step":
            strategy = TwoStepMartingaleStrategy(base_amount, multiplier)
        elif strategy_type == "3step":
            strategy = ThreeStepMartingaleStrategy(base_amount, multiplier)
        elif strategy_type == "4cycle":
            strategy = FourCycleMartingaleStrategy(base_amount, multiplier)
        elif strategy_type == "5cycle":
            strategy = FiveCycleMartingaleStrategy(base_amount, multiplier)
        else:
            strategy = MultiAssetMartingaleStrategy(base_amount, multiplier)
        
        session_trades = 0
        processed_signals = set()  # Track processed signals to avoid duplicates
        
        try:
            # Show initial signal overview for the target date
            # Scanning for signals on target date...
            initial_signals = self.get_signals_from_csv(target_date)
            if initial_signals:
                print(f"✅ Found {len(initial_signals)} signals for {target_date}:")
                for i, signal in enumerate(initial_signals[:10]):  # Show first 10
                    print(f"   {i+1}. {signal['asset']} {signal['direction'].upper()} at {signal['signal_time']}")
                if len(initial_signals) > 10:
                    print(f"   ... and {len(initial_signals) - 10} more signals")
            else:
                print(f"❌ No signals found for {target_date} - check CSV file")
            print("=" * 60)
            
            while True:
                # Check stop loss and take profit conditions
                should_stop, stop_reason = self.should_stop_trading()
                if should_stop:
                    print(f"\n{stop_reason}")
                    print(f"🏁 Trading session ended")
                    break
                
                # Get signals for the target date
                signals = self.get_signals_from_csv(target_date)
                
                if not signals:
                    current_time_display = get_user_time().strftime('%H:%M:%S')
                    print(f"\n🔄 [{current_time_display}] No signals available for {target_date} - waiting...")
                    await asyncio.sleep(5)  # Check every 5 seconds for date-specific trading
                    continue
                
                # Check for exact time match with signals from target date
                current_time = get_user_time()
                current_time_str = current_time.strftime('%H:%M:%S')
                ready_signals = []
                
                print(f"⏰ CURRENT TIME: {current_time_str} | TARGET DATE: {target_date}")
                
                for signal in signals:
                    # Create unique signal ID
                    signal_id = f"{signal['asset']}_{signal['direction']}_{signal['signal_time']}_{target_date}"
                    
                    # Skip if already processed
                    if signal_id in processed_signals:
                        continue
                    
                    signal_time_hms = signal['signal_datetime'].strftime('%H:%M:%S')
                    
                    # Check for EXACT time match
                    if current_time_str == signal_time_hms:
                        print(f"🎯 EXACT TIME MATCH: {signal['asset']} {signal['direction'].upper()} at {signal_time_hms}")
                        ready_signals.append(signal)
                        processed_signals.add(signal_id)
                
                if not ready_signals:
                    # Show next upcoming signal
                    future_signals = []
                    for signal in signals:
                        signal_id = f"{signal['asset']}_{signal['direction']}_{signal['signal_time']}_{target_date}"
                        if signal_id not in processed_signals:
                            # Calculate time until signal (using current date but signal time)
                            signal_today = current_time.replace(
                                hour=signal['signal_datetime'].hour,
                                minute=signal['signal_datetime'].minute,
                                second=signal['signal_datetime'].second
                            )
                            time_until = (signal_today - current_time).total_seconds()
                            if time_until > 0:
                                future_signals.append((signal, time_until))
                    
                    if future_signals:
                        next_signal, next_wait = min(future_signals, key=lambda x: x[1])
                        wait_minutes = int(next_wait // 60)
                        wait_seconds = int(next_wait % 60)
                        print(f"⏰ Next signal: {next_signal['asset']} {next_signal['direction'].upper()} at {next_signal['signal_time']} (in {wait_minutes}m {wait_seconds}s)")
                    
                    await asyncio.sleep(1)  # Check every second
                    continue
                
                # Process ready signals
                if ready_signals:
                    print(f"\n📊 PROCESSING {len(ready_signals)} SIGNALS FOR {target_date}:")
                    print("=" * 50)
                    
                    for signal in ready_signals:
                        asset = signal['asset']
                        direction = signal['direction']
                        
                        print(f"📊 {asset} {direction.upper()} - {strategy.get_status(asset) if hasattr(strategy, 'get_status') else 'Ready'}")
                        print(f"⏰ Signal: {signal['signal_time']} | Date: {target_date}")
                        
                        # Execute trade based on strategy type
                        try:
                            if strategy_type in ["2step", "3step", "4cycle", "5cycle"]:
                                # Execute single trade in sequence
                                if strategy_type == "2step":
                                    won, profit, action = await self.execute_single_2step_trade(
                                        asset, direction, base_amount, strategy, signal.get('channel')
                                    )
                                elif strategy_type == "3step":
                                    won, profit, action = await self.execute_single_3step_trade(
                                        asset, direction, base_amount, strategy, signal.get('channel')
                                    )
                                elif strategy_type == "4cycle":
                                    won, profit, action = await self.execute_single_4cycle_trade(
                                        asset, direction, base_amount, strategy, signal.get('channel')
                                    )
                                elif strategy_type == "5cycle":
                                    won, profit, action = await self.execute_single_5cycle_trade(
                                        asset, direction, base_amount, strategy, signal.get('channel')
                                    )
                                
                                # Update session profit
                                self.update_session_profit(profit)
                                session_trades += 1
                                
                                # Show result
                                result_emoji = "✅" if won else "❌"
                                print(f"{result_emoji} {asset} {'WIN' if won else 'LOSS'} - ${profit:+.2f}")
                                
                                # Handle continuation if needed
                                if action == 'continue':
                                    print(f"⚡ CONTINUING TO NEXT STEP for {asset}")
                                    await asyncio.sleep(0.01)  # 10ms delay
                                    
                                    # Execute next step immediately
                                    try:
                                        if strategy_type == "2step":
                                            won2, profit2, action2 = await self.execute_single_2step_trade(
                                                asset, direction, base_amount, strategy, signal.get('channel')
                                            )
                                        elif strategy_type == "3step":
                                            won2, profit2, action2 = await self.execute_single_3step_trade(
                                                asset, direction, base_amount, strategy, signal.get('channel')
                                            )
                                        elif strategy_type == "4cycle":
                                            won2, profit2, action2 = await self.execute_single_4cycle_trade(
                                                asset, direction, base_amount, strategy, signal.get('channel')
                                            )
                                        elif strategy_type == "5cycle":
                                            won2, profit2, action2 = await self.execute_single_5cycle_trade(
                                                asset, direction, base_amount, strategy, signal.get('channel')
                                            )
                                        
                                        # Update session profit for next step
                                        self.update_session_profit(profit2)
                                        session_trades += 1
                                        
                                        # Show next step result
                                        result_emoji2 = "✅" if won2 else "❌"
                                        print(f"{result_emoji2} {asset} NEXT STEP {'WIN' if won2 else 'LOSS'} - ${profit2:+.2f}")
                                        
                                        # Handle further continuation for 3-step
                                        if strategy_type == "3step" and action2 == 'continue':
                                            print(f"⚡ CONTINUING TO STEP 3 for {asset}")
                                            await asyncio.sleep(0.01)  # 10ms delay
                                            
                                            won3, profit3, action3 = await self.execute_single_3step_trade(
                                                asset, direction, base_amount, strategy, signal.get('channel')
                                            )
                                            
                                            self.update_session_profit(profit3)
                                            session_trades += 1
                                            
                                            result_emoji3 = "✅" if won3 else "❌"
                                            print(f"{result_emoji3} {asset} STEP 3 {'WIN' if won3 else 'LOSS'} - ${profit3:+.2f}")
                                        
                                    except Exception as next_step_error:
                                        print(f"❌ Next step error: {next_step_error}")
                            else:
                                # Execute complete martingale sequence
                                final_won, total_profit = await self.execute_complete_martingale_sequence(
                                    asset, direction, base_amount, strategy, signal.get('channel')
                                )
                                
                                # Update session profit
                                self.update_session_profit(total_profit)
                                session_trades += 1
                                
                                if final_won:
                                    print(f"🎉 {asset} SEQUENCE WIN! Profit: ${total_profit:+.2f}")
                                else:
                                    print(f"💔 {asset} SEQUENCE LOSS! Loss: ${total_profit:+.2f}")
                            
                        except Exception as trade_error:
                            print(f"❌ Trade error for {asset}: {trade_error}")
                        
                        # Show session stats
                        wins = len([t for t in self.trade_history if t['result'] == 'win'])
                        losses = len([t for t in self.trade_history if t['result'] == 'loss'])
                        
                        print(f"\n📊 TRADING SESSION:")
                        print(f"   💰 {self.get_session_status()}")
                        print(f"   📈 Total Trades: {session_trades}")
                        print(f"   🏆 Results: {wins}W/{losses}L")
                        print(f"   📅 Target Date: {target_date}")
                        
                        # Check stop conditions
                        should_stop, stop_reason = self.should_stop_trading()
                        if should_stop:
                            print(f"\n{stop_reason}")
                            print(f"🏁 Trading session ended")
                            return
                
                await asyncio.sleep(1)  # Check every second
                
        except KeyboardInterrupt:
            print(f"\n🛑 DATE-SPECIFIC TRADING STOPPED")
        except Exception as e:
            print(f"❌ Trading error: {e}")
        
        # Final stats
        total_trades = len(self.trade_history)
        total_wins = len([t for t in self.trade_history if t['result'] == 'win'])
        total_losses = len([t for t in self.trade_history if t['result'] == 'loss'])
        
        print(f"\n📊 FINAL STATISTICS:")
        print(f"   💰 {self.get_session_status()}")
        print(f"   📈 Session Trades: {session_trades}")
        print(f"   🏆 Results: {total_wins}W/{total_losses}L")
        print(f"   📅 Target Date: {target_date}")
        
        # Show final stop loss/take profit status
        if self.stop_loss is not None or self.take_profit is not None:
            print(f"\n🎯 RISK MANAGEMENT SUMMARY:")
            if self.stop_loss is not None:
                if self.session_profit <= -self.stop_loss:
                    print(f"   🛑 Stop Loss TRIGGERED: ${self.session_profit:+.2f} (limit: -${self.stop_loss:.2f})")
                else:
                    remaining_loss = self.stop_loss + self.session_profit
                    print(f"   🛑 Stop Loss: ${remaining_loss:.2f} remaining")
            
            if self.take_profit is not None:
                if self.session_profit >= self.take_profit:
                    print(f"   🎯 Take Profit ACHIEVED: ${self.session_profit:+.2f} (target: +${self.take_profit:.2f})")
                else:
                    remaining_profit = self.take_profit - self.session_profit
                    print(f"   🎯 Take Profit: ${remaining_profit:.2f} to go")

def get_timezone_from_user() -> float:
    """Get timezone offset from user input"""
    print("🌍 TIMEZONE CONFIGURATION")
    print("=" * 30)
    print("Enter your timezone offset from UTC:")
    print("Examples:")
    print("  UTC+6 (Bangladesh): 6.0")
    print("  UTC+5:30 (India): 5.5") 
    print("  UTC-5 (EST): -5.0")
    print("  UTC+0 (GMT): 0.0")
    print("  UTC+8 (China): 8.0")
    print()
    
    while True:
        try:
            timezone_input = input("Enter timezone offset (e.g., 6.0 for UTC+6): ").strip()
            timezone_offset = float(timezone_input)
            
            if -12.0 <= timezone_offset <= 14.0:
                return timezone_offset
            else:
                print("❌ Invalid timezone offset. Please enter a value between -12.0 and +14.0")
        except ValueError:
            print("❌ Invalid input. Please enter a number (e.g., 6.0)")
        except KeyboardInterrupt:
            print("\n👋 Timezone configuration cancelled!")
            exit(0)

async def main():
    """Main application with timezone configuration and trading strategy options"""
    print("=" * 80)
    print("🚀 POCKETOPTION PRECISE TIMING TRADER")
    print("=" * 80)
    
    # Get timezone from user first
    timezone_offset = get_timezone_from_user()
    set_user_timezone(timezone_offset)
    
    print(f"\n⏰ Current time in {get_timezone_name()}: {get_user_time_str()}")
    print("=" * 80)
    print("📊 Choose your trading strategy:")
    print("=" * 80)
    
    while True:
        print("\n📋 TRADING STRATEGY MENU:")
        print("=" * 40)
        print("1️⃣  Option 1: 2-Cycle 3-Step Martingale")
        print("    • 2 cycles × 3 steps = up to 6 trades")
        print("    • Step 4 (C2S1) = sum of first 3 steps")
        print("    • LOSS at final step → Next ASSET starts at next cycle")
        print("    • WIN at any step → All assets reset to Cycle 1")
        print("    • Cross-asset cycle progression")
        print()
        print("0️⃣  Exit")
        print("=" * 40)
        
        try:
            strategy_choice = input("\n🎯 Select strategy (1 or 0 to exit): ").strip()
            
            if strategy_choice == '0':
                print("\n👋 Goodbye!")
                break
            
            if strategy_choice != '1':
                print("❌ Please enter 1 or 0")
                continue
            
            # Option 1: 2-Cycle 3-Step Martingale (formerly 3d)
            print("\n✅ Selected: Option 1 - 2-Cycle 3-Step Martingale")
            use_date_specific = False
            use_option2 = False
            use_option3 = False
            use_option3b = False
            use_option3c = False
            use_option3d = True
            use_option4 = False
            use_option5 = False
            
            print("\n📋 TRADING SETUP:")
            print("=" * 40)
            
            # Get channel selection
            print("1. Channel Selection:")
            print("   Available channels:")
            print("   1) James Martin Free Channel (5:00 trades)")
            
            while True:
                try:
                    channel_choice = input("   Select channel (1): ").strip()
                    if channel_choice == '1':
                        active_channel = "james_martin_free"
                        channel_display = "James Martin Free Channel (5:00 trades)"
                        break
                    else:
                        print("   ❌ Please enter 1")
                except ValueError:
                    print("   ❌ Please enter 1")
            
            print(f"   ✅ Selected: {channel_display}")
            
            # Get account type
            print("\n2. Account Type:")
            account_choice = input("   Use DEMO account? (Y/n): ").lower().strip()
            is_demo = account_choice != 'n'
            print(f"   ✅ {'DEMO' if is_demo else 'REAL'} account selected")
            
            # Get base amount
            print("\n3. Base Amount:")
            while True:
                try:
                    base_amount = float(input("   Enter base amount ($): $"))
                    if base_amount <= 0:
                        print("   ❌ Amount must be positive")
                        continue
                    print(f"   ✅ Base amount: ${base_amount}")
                    break
                except ValueError:
                    print("   ❌ Please enter a valid number")
            
            # Get multiplier
            print("\n4. Multiplier:")
            while True:
                try:
                    multiplier_input = input("   Enter multiplier (default 2.5): ").strip()
                    if not multiplier_input:
                        multiplier = 2.5
                    else:
                        multiplier = float(multiplier_input)
                    
                    if multiplier <= 1:
                        print("   ❌ Multiplier must be greater than 1")
                        continue
                    print(f"   ✅ Multiplier: {multiplier}")
                    break
                except ValueError:
                    print("   ❌ Please enter a valid number")
            
            # Get stop loss
            print(f"\n5. Stop Loss (Risk Management):")
            while True:
                try:
                    stop_loss_input = input("   Enter stop loss in $ (0 to disable): $").strip()
                    if not stop_loss_input or stop_loss_input == '0':
                        stop_loss = None
                        print("   ✅ Stop Loss: Disabled")
                    else:
                        stop_loss = float(stop_loss_input)
                        if stop_loss <= 0:
                            print("   ❌ Stop loss must be positive or 0 to disable")
                            continue
                        print(f"   ✅ Stop Loss: ${stop_loss:.2f}")
                    break
                except ValueError:
                    print("   ❌ Please enter a valid number")
            
            # Get take profit
            print(f"\n6. Take Profit (Risk Management):")
            while True:
                try:
                    take_profit_input = input("   Enter take profit in $ (0 to disable): $").strip()
                    if not take_profit_input or take_profit_input == '0':
                        take_profit = None
                        print("   ✅ Take Profit: Disabled")
                    else:
                        take_profit = float(take_profit_input)
                        if take_profit <= 0:
                            print("   ❌ Take profit must be positive or 0 to disable")
                            continue
                        print(f"   ✅ Take Profit: ${take_profit:.2f}")
                    break
                except ValueError:
                    print("   ❌ Please enter a valid number")
            
            # Show timing info with user's timezone
            print(f"\n⏰ TIMING CONFIGURATION:")
            print(f"   Timezone: {get_timezone_name()}")
            print(f"   Current Time: {get_user_time_str()}")
            print(f"   Precision: Millisecond-level timing")
            print(f"   Execution Window: Within 10ms of signal time")
            
            # Show timing example based on selected channel
            print(f"\n⏰ TIMING EXAMPLE ({channel_display}):")
            example_signal = "00:38:00"
            
            if active_channel == "james_martin_free":
                duration_text = "5:00 duration"
            else:
                duration_text = "5:00 duration"
            
            print(f"   Signal Time: {example_signal}:000 (exact second)")
            print(f"   Execute: Within 0-10ms of {example_signal}:000")
            print(f"   Duration: {duration_text}")
            
            
            # Show strategy preview - Option 1: 2-Cycle 3-Step Martingale (formerly 3d)
            c1s1 = base_amount
            c1s2 = c1s1 * multiplier
            c1s3 = c1s2 * multiplier
            # Step 4 (C2S1) = sum of first 3 steps
            c2s1 = c1s1 + c1s2 + c1s3
            c2s2 = c2s1 * multiplier
            c2s3 = c2s2 * multiplier
            
            print(f"\n📊 STRATEGY PREVIEW (2-Cycle 3-Step Cross-Asset Martingale - {channel_display}):")
            print(f"   Cycle 1: Step 1 ${c1s1:.2f} → Step 2 ${c1s2:.2f} → Step 3 ${c1s3:.2f}")
            print(f"   Cycle 2: Step 1 ${c2s1:.2f} → Step 2 ${c2s2:.2f} → Step 3 ${c2s3:.2f}")
            print(f"   Special Logic: Step 4 (C2S1) = Sum of first 3 steps (${c2s1:.2f})")
            print(f"   Trade Duration: {duration_text}")
            print(f"\n🔄 Cross-Asset Cycle Logic:")
            print(f"   • WIN at any step → All assets reset to C1S1")
            print(f"   • LOSS at Step 1 → Move to Step 2 (same asset)")
            print(f"   • LOSS at Step 2 → Move to Step 3 (same asset)")
            print(f"   • LOSS at Step 3 → NEXT asset starts at next cycle")
            print(f"   • Example: EURJPY loses C1S3 → GBPUSD starts at C2S1")
            
            # Show risk management summary
            if stop_loss is not None or take_profit is not None:
                print(f"\n🛡️ RISK MANAGEMENT:")
                if stop_loss is not None:
                    print(f"   🛑 Stop Loss: ${stop_loss:.2f} (trading stops if loss reaches this)")
                if take_profit is not None:
                    print(f"   🎯 Take Profit: ${take_profit:.2f} (trading stops if profit reaches this)")
            
            # Confirm start
            print(f"\n🚀 Ready to start trading!")
            start = input("Start trading? (Y/n): ").lower().strip()
            if start == 'n':
                continue
            
            # Initialize trader with stop loss, take profit, and active channel
            trader = MultiAssetPreciseTrader(stop_loss=stop_loss, take_profit=take_profit)
            trader.active_channel = active_channel  # Set the selected channel
            
            # Connect
            if not await trader.connect(is_demo):
                print("❌ Failed to connect")
                continue
            
            try:
                # Start trading with Option 1: 2-Cycle 3-Step Martingale (formerly 3d)
                await trader.start_2cycle_3step_trading(base_amount, multiplier, is_demo)
            finally:
                # Disconnect
                if trader.client:
                    await trader.client.disconnect()
                    print("🔌 Disconnected from PocketOption")
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            continue
        
        # Ask if want to restart
        restart = input("\nStart another trading session? (Y/n): ").lower().strip()
        if restart == 'n':
            break
    
    print("\n👋 Thank you for using PocketOption Automated Trader!")

if __name__ == "__main__":
    asyncio.run(main())s
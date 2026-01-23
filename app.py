#!/usr/bin/env python3
"""
PocketOption Precise Timing Trader
Places trades with configurable offset from signal time
Trade timing is controlled by trade_config.txt file
Example: Signal at 00:38:00, offset=3s → Execute at 00:37:57
"""
import os
import json
import time
import asyncio
import logging
import pandas as pd
from datetime import datetime, timedelta
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
        
        # Calculate all amounts for display
        c1s1 = base_amount
        c1s2 = c1s1 * multiplier
        c2s1 = c1s2 * multiplier
        c2s2 = c2s1 * multiplier
        c3s1 = c2s2 * multiplier
        c3s2 = c3s1 * multiplier
        
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
            self.asset_strategies[asset] = {
                'cycle': self.global_cycle, 
                'step': self.global_step, 
                'amounts': []
            }
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
        
        # Record amount used
        strategy['amounts'].append(trade_amount)
        
        if won:
            print(f"✅ {asset} WIN at C{cycle}S{step}! Resetting global state to C1S1")
            # WIN resets GLOBAL state to C1S1 - all future assets start at C1S1
            self.global_cycle = 1
            self.global_step = 1
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
        self.trade_offset_seconds = self._load_trade_offset()
        
        # Use date-based CSV filename - support all channels
        # Will be auto-updated to find latest available CSV
        self.james_martin_csv = None
        self.lc_trader_csv = None
        self.po_advance_bot_csv = None
        self.current_csv_date = None
        self._update_csv_filenames()
        
        # Channel selection and trade duration settings
        self.active_channel = None  # Will be set by user
        self.james_martin_duration = 60  # 60 seconds (1:00) for James Martin
        self.lc_trader_duration = 300   # 5:00 (300 seconds) for LC Trader
        self.po_advance_bot_duration = 60  # 60 seconds (1:00) for PO ADVANCE BOT
        
        self.trade_history = []
        self.pending_immediate_trades = []  # Queue for immediate next step trades
        
        # API health tracking
        self.api_failures = 0
        self.max_api_failures = 3  # System will fail after 3 consecutive failures
        self.last_successful_api_call = datetime.now()
        
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
        
        print(f"📊 James Martin CSV: {self.james_martin_csv}")
        print(f"📊 LC Trader CSV: {self.lc_trader_csv}")
        print(f"📊 PO ADVANCE BOT CSV: {self.po_advance_bot_csv}")
        print(f"⏰ Trade Durations: James Martin (1:00) | LC Trader (5:00) | PO ADVANCE BOT (1:00)")
        print(f"🎯 Active Channel: {self.active_channel or 'Not selected'}")
        print(f"⏱️  Trade Offset: {self.trade_offset_seconds}s before signal time")
        
        # Display stop loss and take profit settings
        if self.stop_loss is not None:
            print(f"🛑 Stop Loss: ${self.stop_loss:.2f}")
        else:
            print(f"🛑 Stop Loss: Disabled")
            
        if self.take_profit is not None:
            print(f"🎯 Take Profit: ${self.take_profit:.2f}")
        else:
            print(f"🎯 Take Profit: Disabled")
    
    def _load_trade_offset(self) -> int:
        """Load trade timing offset from config file"""
        config_file = "trade_config.txt"
        default_offset = 0  # Default: Execute exactly at signal time (no offset)
        
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        # Skip comments and empty lines
                        if line.startswith('#') or not line:
                            continue
                        # Look for TRADE_OFFSET_SECONDS setting
                        if line.startswith('TRADE_OFFSET_SECONDS='):
                            offset_str = line.split('=')[1].strip()
                            offset = int(offset_str)
                            print(f"✅ Loaded trade offset from config: {offset}s before signal")
                            return offset
                
                print(f"⚠️ TRADE_OFFSET_SECONDS not found in config, using default: {default_offset}s")
                return default_offset
            else:
                print(f"⚠️ Config file not found, using default offset: {default_offset}s")
                return default_offset
                
        except Exception as e:
            print(f"⚠️ Error loading config: {e}, using default offset: {default_offset}s")
            return default_offset
    
    def _update_csv_filenames(self):
        """Automatically find and use TODAY'S CSV files for each channel - no future dates"""
        import glob
        
        today = datetime.now().strftime('%Y%m%d')
        print(f"📅 Focusing on TODAY'S date: {today}")
        
        # Check if we need to update (date changed or first run)
        if self.current_csv_date == today and self.james_martin_csv and self.lc_trader_csv and self.po_advance_bot_csv:
            return  # Already up to date
        
        old_date = self.current_csv_date
        self.current_csv_date = today
        
        # Find James Martin CSV files - ONLY TODAY'S DATE
        today_james = f"pocketoption_james_martin_vip_channel_m1_{today}.csv"
        if os.path.exists(today_james):
            self.james_martin_csv = today_james
            print(f"✅ Using TODAY'S James Martin CSV: {today_james}")
        else:
            # Fallback to latest available, but prefer today
            james_pattern = "pocketoption_james_martin_vip_channel_m1_*.csv"
            james_files = glob.glob(james_pattern)
            if james_files:
                james_files.sort(reverse=True)
                self.james_martin_csv = james_files[0]
                print(f"⚠️ Today's James Martin CSV not found, using: {james_files[0]}")
            else:
                self.james_martin_csv = today_james
                print(f"📄 Will create James Martin CSV: {today_james}")
        
        # Find LC Trader CSV files - ONLY TODAY'S DATE
        today_lc = f"pocketoption_lc_trader_{today}.csv"
        if os.path.exists(today_lc):
            self.lc_trader_csv = today_lc
            print(f"✅ Using TODAY'S LC Trader CSV: {today_lc}")
        else:
            # Fallback to latest available, but prefer today
            lc_pattern = "pocketoption_lc_trader_*.csv"
            lc_files = glob.glob(lc_pattern)
            if lc_files:
                lc_files.sort(reverse=True)
                self.lc_trader_csv = lc_files[0]
                print(f"⚠️ Today's LC Trader CSV not found, using: {lc_files[0]}")
            else:
                self.lc_trader_csv = today_lc
                print(f"📄 Will create LC Trader CSV: {today_lc}")
        
        # Find PO ADVANCE BOT CSV files - ONLY TODAY'S DATE
        today_po_advance = f"pocketoption_po_advance_bot_{today}.csv"
        if os.path.exists(today_po_advance):
            self.po_advance_bot_csv = today_po_advance
            print(f"✅ Using TODAY'S PO ADVANCE BOT CSV: {today_po_advance}")
        else:
            # Fallback to latest available, but prefer today
            po_advance_pattern = "pocketoption_po_advance_bot_*.csv"
            po_advance_files = glob.glob(po_advance_pattern)
            if po_advance_files:
                po_advance_files.sort(reverse=True)
                self.po_advance_bot_csv = po_advance_files[0]
                print(f"⚠️ Today's PO ADVANCE BOT CSV not found, using: {po_advance_files[0]}")
            else:
                self.po_advance_bot_csv = today_po_advance
                print(f"📄 Will create PO ADVANCE BOT CSV: {today_po_advance}")
        
        # Log the update
        if old_date and old_date != today:
            print(f"\n📅 DATE CHANGED: {old_date} → {today}")
            print(f"📄 CSV FILES UPDATED:")
            print(f"   📊 James Martin: {self.james_martin_csv}")
            print(f"   📊 LC Trader: {self.lc_trader_csv}")
            print(f"   📊 PO ADVANCE BOT: {self.po_advance_bot_csv}")
            print("-" * 60)
        elif not old_date:
            # First run
            print(f"📄 CSV FILES DETECTED:")
            print(f"   📊 James Martin: {self.james_martin_csv}")
            print(f"   📊 LC Trader: {self.lc_trader_csv}")
            print(f"   📊 PO ADVANCE BOT: {self.po_advance_bot_csv}")
    
    def _validate_duration(self, duration: int, channel: str = None) -> int:
        """Ensure duration matches channel requirements"""
        if channel == "james_martin":
            if duration != 60:
                print(f"⚠️ James Martin duration {duration}s adjusted to 60s (1:00)")
                return 60
            return duration
        elif channel == "lc_trader":
            if duration != 300:
                print(f"⚠️ LC Trader duration {duration}s adjusted to 5:00 (300s)")
                return 300
            return duration
        elif channel == "po_advance_bot":
            if duration != 60:
                print(f"⚠️ PO ADVANCE BOT duration {duration}s adjusted to 60s (1:00)")
                return 60
            return duration
        else:
            # Default behavior for backward compatibility
            if duration != 60:
                print(f"⚠️ Duration {duration}s adjusted to 60s (1:00)")
                return 60
            return duration
    
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
        self.last_successful_api_call = datetime.now()
    
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
    
    def get_signals_from_csv(self) -> List[Dict[str, Any]]:
        """Get trading signals from selected channel CSV file"""
        try:
            # Update CSV filenames in case date has changed
            self._update_csv_filenames()
            
            # Determine which CSV file to use based on active channel
            if self.active_channel == "james_martin":
                csv_file = self.james_martin_csv
                trade_duration = self.james_martin_duration
                channel_name = "James Martin VIP"
            elif self.active_channel == "lc_trader":
                csv_file = self.lc_trader_csv
                trade_duration = self.lc_trader_duration
                channel_name = "LC Trader"
            elif self.active_channel == "po_advance_bot":
                csv_file = self.po_advance_bot_csv
                trade_duration = self.po_advance_bot_duration
                channel_name = "PO ADVANCE BOT"
            else:
                print(f"❌ No active channel selected")
                return []
            
            if not os.path.exists(csv_file):
                print(f"❌ CSV file not found: {csv_file}")
                return []
            
            print(f"📊 Reading signals from {channel_name} ({csv_file})")
            
            df = pd.read_csv(csv_file, on_bad_lines='skip')
            
            if 'is_signal' in df.columns:
                signals_df = df[df['is_signal'] == 'Yes'].copy()
            else:
                signals_df = df.copy()
            
            if signals_df.empty:
                return []
            
            signals = []
            current_time = datetime.now()
            
            for _, row in signals_df.iterrows():
                try:
                    asset = str(row.get('asset', '')).strip()
                    direction = str(row.get('direction', '')).strip().lower()
                    signal_time_str = str(row.get('signal_time', '')).strip()
                    
                    if not asset or not direction or not signal_time_str or signal_time_str == 'nan':
                        continue
                    
                    # Use EXACT asset name from CSV - no modifications
                    trading_asset = asset
                    
                    # Extract base asset for logging purposes only
                    if trading_asset.endswith('_otc'):
                        base_asset = trading_asset[:-4]  # Remove _otc for logging
                        asset_type = "OTC"
                    else:
                        base_asset = trading_asset
                        asset_type = "Regular"
                    
                    # Log asset status using base asset
                    if base_asset in getattr(self, 'WORKING_ASSETS', set()):
                        print(f"✅ Supported {asset_type} asset: {asset}")
                    elif base_asset in getattr(self, 'UNSUPPORTED_ASSETS', set()):
                        print(f"❌ Unsupported {asset_type} asset: {asset} - skipping")
                        continue  # Skip unsupported assets
                    else:
                        print(f"❓ Unknown {asset_type} asset: {asset} - will test API formats")
                    
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
                            continue
                        
                        # Set to today's date ONLY - no future dates
                        signal_datetime = current_time.replace(
                            hour=signal_time.hour,
                            minute=signal_time.minute,
                            second=signal_time.second if signal_time_str.count(':') == 2 else 0,
                            microsecond=0
                        )
                        
                        # Skip signals that have passed today - focus only on current date
                        if signal_datetime <= current_time:
                            # Check if signal is from today but already passed
                            time_passed = (current_time - signal_datetime).total_seconds()
                            if time_passed > 300:  # More than 5 minutes ago
                                print(f"⏰ SKIPPING old signal: {asset} {direction} at {signal_time_str} (passed {time_passed/60:.1f}m ago)")
                                continue
                            else:
                                # Recent signal (within 5 minutes) - might still be valid
                                print(f"⚠️ Recent signal: {asset} {direction} at {signal_time_str} (passed {time_passed:.0f}s ago)")
                        
                        # Ensure signal is for TODAY only
                        today_date = current_time.date()
                        signal_date = signal_datetime.date()
                        if signal_date != today_date:
                            print(f"⏰ SKIPPING non-today signal: {asset} {direction} at {signal_time_str} (date: {signal_date})")
                            continue
                        
                        # Calculate trade execution time with offset from config
                        # Positive offset = execute BEFORE signal time
                        # Example: signal at 10:30:00, offset=3 → trade at 10:29:57
                        trade_datetime = signal_datetime - timedelta(seconds=self.trade_offset_seconds)
                        
                        # Skip past trades (more than 2 minutes ago)
                        time_diff = (trade_datetime - current_time).total_seconds()
                        if time_diff < -120:
                            print(f"⏰ SKIPPING old signal: {asset} {direction} at {signal_time_str} (too old)")
                            continue
                        
                        # Allow future trades (remove the 1-minute limit for Step 1)
                        # Step 1 should wait for the actual signal time
                        
                    except ValueError:
                        continue
                    
                    signal = {
                        'asset': trading_asset,
                        'direction': direction,
                        'signal_time': signal_time_str,
                        'signal_datetime': signal_datetime,
                        'trade_datetime': trade_datetime,  # exactly at signal time
                        'close_datetime': trade_datetime + timedelta(seconds=trade_duration),  # Channel-specific duration
                        'timestamp': datetime.now().isoformat(),
                        'message_text': str(row.get('message_text', ''))[:100],
                        'channel': self.active_channel,
                        'duration': trade_duration
                    }
                    
                    # Debug timing
                    current_time_for_debug = datetime.now()
                    time_until_trade = (trade_datetime - current_time_for_debug).total_seconds()
                    
                    duration_display = f"{trade_duration}s" if trade_duration < 60 else f"{trade_duration//60}:{trade_duration%60:02d}"
                    
                    # Calculate offset display
                    if self.trade_offset_seconds > 0:
                        offset_display = f"{self.trade_offset_seconds}s before signal"
                    elif self.trade_offset_seconds < 0:
                        offset_display = f"{abs(self.trade_offset_seconds)}s after signal"
                    else:
                        offset_display = "exactly at signal"
                    
                    print(f"🔍 Signal parsed: {trading_asset} {direction} at {signal_time_str} ({channel_name})")
                    print(f"   Signal time: {signal_datetime.strftime('%H:%M:%S')}")
                    print(f"   Trade time:  {trade_datetime.strftime('%H:%M:%S')} ({offset_display})")
                    print(f"   Duration:    {duration_display}")
                    
                    if time_until_trade > 0:
                        if time_until_trade < 60:  # Less than 1 minute
                            print(f"   ⏰ Wait time: {time_until_trade:.1f}s")
                        else:
                            wait_minutes = int(time_until_trade // 60)
                            wait_seconds = time_until_trade % 60
                            print(f"   ⏰ Wait time: {wait_minutes}m {wait_seconds:.1f}s")
                    else:
                        print(f"   ✅ Ready to execute!")
                    
                    # Add all valid signals (will be filtered by readiness in main loop)
                    signals.append(signal)
                    
                except Exception:
                    continue
            
            # Sort by trade execution time
            signals.sort(key=lambda x: x['trade_datetime'])
            return signals
            
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
        if asset.endswith('-OTC') or asset.endswith('-OTCP'):
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
    
    async def execute_single_2step_trade(self, asset: str, direction: str, base_amount: float, strategy: 'TwoStepMartingaleStrategy', channel: str = None) -> Tuple[bool, float, str]:
        """Execute a single trade in the 2-step sequence and return next action"""
        current_cycle = strategy.get_asset_cycle(asset)
        current_step = strategy.get_asset_step(asset)
        step_amount = strategy.get_current_amount(asset)
        
        print(f"📊 C{current_cycle}S{current_step}: {asset} {direction.upper()} ${step_amount}")
        print(f"⏱️  Trade execution at: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
        
        try:
            # Execute trade based on step
            if current_step == 1:
                # For Step 1, use precise timing
                won, profit = await self.execute_precise_trade({
                    'asset': asset,
                    'direction': direction,
                    'trade_datetime': datetime.now(),
                    'signal_datetime': datetime.now(),
                    'close_datetime': datetime.now() + timedelta(seconds=300 if channel == "lc_trader" else (60 if channel in ["james_martin", "po_advance_bot"] else 60)),
                    'channel': channel or self.active_channel,
                    'duration': 300 if channel == "lc_trader" else (60 if channel in ["james_martin", "po_advance_bot"] else 60)
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
    
    async def execute_immediate_trade(self, asset: str, direction: str, amount: float, channel: str = None) -> Tuple[bool, float]:
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
                    won, profit = await self.execute_precise_trade({
                        'asset': asset,
                        'direction': direction,
                        'trade_datetime': datetime.now(),
                        'signal_datetime': datetime.now(),
                        'close_datetime': datetime.now() + timedelta(seconds=300 if channel == "lc_trader" else (60 if channel in ["james_martin", "po_advance_bot"] else 60)),
                        'channel': channel or self.active_channel,
                        'duration': 300 if channel == "lc_trader" else (60 if channel in ["james_martin", "po_advance_bot"] else 60)
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
        """Execute immediate trade (for steps 2 and 3) with channel-specific timing"""
        try:
            # Determine duration based on channel
            if channel == "james_martin":
                dynamic_duration = self.james_martin_duration
                channel_name = "James Martin"
            elif channel == "lc_trader":
                dynamic_duration = self.lc_trader_duration
                channel_name = "LC Trader"
            elif channel == "po_advance_bot":
                dynamic_duration = self.po_advance_bot_duration
                channel_name = "PO ADVANCE BOT"
            else:
                # Use active channel if not specified
                if self.active_channel == "james_martin":
                    dynamic_duration = self.james_martin_duration
                    channel_name = "James Martin"
                elif self.active_channel == "lc_trader":
                    dynamic_duration = self.lc_trader_duration
                    channel_name = "LC Trader"
                elif self.active_channel == "po_advance_bot":
                    dynamic_duration = self.po_advance_bot_duration
                    channel_name = "PO ADVANCE BOT"
                else:
                    dynamic_duration = 60  # Default to 1:00
                    channel_name = "Default"
            
            duration_display = f"{dynamic_duration}s" if dynamic_duration < 60 else f"{dynamic_duration//60}:{dynamic_duration%60:02d}"
            
            print(f"⚡ IMMEDIATE ({channel_name}): {asset} {direction.upper()} ${amount} ({duration_display})")
            print(f"⏱️  Executing at: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
            
            execution_time = datetime.now()
            
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
                        if dynamic_duration >= 300:  # LC Trader (5:00)
                            max_wait = min(330.0, dynamic_duration + 30.0)  # Max 330 seconds for 5:00 trades
                        else:  # James Martin (1:00)
                            max_wait = min(80.0, dynamic_duration + 20.0)  # Max 80 seconds for 1:00 trades
                        
                        # Use consistent check interval for both channels
                        check_interval = 0.01  # 10ms check interval for both channels
                        
                        print(f"⏳ Monitoring immediate result (max {max_wait:.0f}s, check every 10ms)...")
                        
                        start_time = datetime.now()
                        win_result = None
                        
                        # Use consistent polling intervals for both channels
                        while (datetime.now() - start_time).total_seconds() < max_wait:
                            try:
                                win_result = await asyncio.wait_for(
                                    self.client.check_win(order_result.order_id, max_wait_time=5.0),
                                    timeout=5.0
                                )
                                
                                if win_result and win_result.get('completed', False):
                                    break
                                
                                elapsed = (datetime.now() - start_time).total_seconds()
                                remaining = max_wait - elapsed
                                if remaining > check_interval:
                                    await asyncio.sleep(check_interval)
                                else:
                                    break
                                    
                            except asyncio.TimeoutError:
                                elapsed = (datetime.now() - start_time).total_seconds()
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
                            elapsed = (datetime.now() - start_time).total_seconds()
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
        """Execute trade immediately when time matches exactly with channel-specific duration"""
        try:
            asset = signal['asset']
            direction = signal['direction']
            signal_time = signal['signal_datetime']
            channel = signal.get('channel', self.active_channel)
            
            # Get channel-specific duration
            if channel == "james_martin":
                dynamic_duration = self.james_martin_duration
                channel_name = "James Martin"
            elif channel == "lc_trader":
                dynamic_duration = self.lc_trader_duration
                channel_name = "LC Trader"
            elif channel == "po_advance_bot":
                dynamic_duration = self.po_advance_bot_duration
                channel_name = "PO ADVANCE BOT"
            else:
                dynamic_duration = signal.get('duration', 60)  # Use signal duration or default to 1:00
                channel_name = "Default"
            
            execution_time = datetime.now()
            execution_time_str = execution_time.strftime('%H:%M:%S')
            signal_time_str = signal_time.strftime('%H:%M:%S')
            
            duration_display = f"{dynamic_duration}s" if dynamic_duration < 60 else f"{dynamic_duration//60}:{dynamic_duration%60:02d}"
            
            print(f"🚀 EXECUTING NOW ({channel_name}): {asset} {direction.upper()} ${amount} ({duration_display})")
            print(f"   Execution Time: {execution_time_str}")
            print(f"   Signal Time:    {signal_time_str}")
            
            # Calculate target close time - based on channel duration
            target_close_time = execution_time + timedelta(seconds=dynamic_duration)
            
            # Calculate EXACT duration to hit target close time
            actual_close_time = execution_time + timedelta(seconds=dynamic_duration)
            
            print(f"🎯 EXECUTING: {asset} {direction.upper()} ${amount}")
            print(f"⏰ TIMING: Trade {execution_time.strftime('%H:%M:%S.%f')[:12]} → Signal {signal_time.strftime('%H:%M:%S')} → Close {actual_close_time.strftime('%H:%M:%S')}")
            print(f"📊 Duration: {duration_display} (target: {target_close_time.strftime('%H:%M:%S')})")
            
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
                    duration=dynamic_duration
                )
                
                if order_result and order_result.status in [OrderStatus.ACTIVE, OrderStatus.PENDING]:
                    print(f"✅ Trade placed - ID: {order_result.order_id}")
                    print(f"⏳ Monitoring result...")
                    self.record_api_success()
                    
                    # Monitor trade result with appropriate timeout based on duration
                    try:
                        # Use appropriate timeout based on trade duration, but consistent check intervals
                        if dynamic_duration >= 300:  # LC Trader (5:00)
                            max_wait = min(330.0, dynamic_duration + 30.0)  # Max 330 seconds for 5:00 trades
                        else:  # James Martin (1:00)
                            max_wait = min(80.0, dynamic_duration + 20.0)  # Max 80 seconds for 1:00 trades
                        
                        # Use consistent check interval for both channels
                        check_interval = 0.01  # 10ms check interval for both channels
                        
                        print(f"⏳ Monitoring result (max {max_wait:.0f}s, check every 10ms)...")
                        
                        start_time = datetime.now()
                        win_result = None
                        
                        while (datetime.now() - start_time).total_seconds() < max_wait:
                            try:
                                win_result = await asyncio.wait_for(
                                    self.client.check_win(order_result.order_id, max_wait_time=5.0),
                                    timeout=5.0
                                )
                                
                                if win_result and win_result.get('completed', False):
                                    break
                                
                                elapsed = (datetime.now() - start_time).total_seconds()
                                remaining = max_wait - elapsed
                                if remaining > check_interval:
                                    await asyncio.sleep(check_interval)
                                else:
                                    break
                                    
                            except asyncio.TimeoutError:
                                elapsed = (datetime.now() - start_time).total_seconds()
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
                            elapsed = (datetime.now() - start_time).total_seconds()
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
                'duration_seconds': dynamic_duration,
                'timing_strategy': 'dynamic_duration_00_close',
                'mode': 'real'
            }
            self.trade_history.append(trade_record)
            
            return won, profit
            
        except Exception as e:
            print(f"❌ Trade execution error: {e}")
            return False, -amount
    
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
            print(f"\n📊 SCANNING CSV FOR SIGNALS...")
            initial_signals = self.get_signals_from_csv()
            if initial_signals:
                print(f"✅ Found {len(initial_signals)} signals in CSV:")
                current_time = datetime.now()
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
                current_time = datetime.now()
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
                    current_time_display = datetime.now().strftime('%H:%M:%S')
                    if hasattr(self, 'api_failures') and self.api_failures > 0:
                        health_status = f"API Health: {self.api_failures}/{self.max_api_failures} failures"
                        print(f"\n🔄 [{current_time_display}] No signals ready - {health_status}")
                    else:
                        print(f"\n🔄 [{current_time_display}] No signals ready - scanning for upcoming trades...")
                    await asyncio.sleep(1)  # Check every 1 seconds for upcoming signals
                    continue
                
                # Show upcoming signals info with precise time matching
                if signals:
                    current_time = datetime.now()
                    current_time_str = current_time.strftime('%H:%M:%S')
                    ready_signals = []
                    future_signals = []
                    
                    print(f"⏰ CURRENT TIME: {current_time_str}")
                    
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
            print(f"\n📊 SCANNING CSV FOR SIGNALS...")
            initial_signals = self.get_signals_from_csv()
            if initial_signals:
                print(f"✅ Found {len(initial_signals)} signals in CSV:")
                current_time = datetime.now()
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
                current_time = datetime.now()
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
                    current_time_display = datetime.now().strftime('%H:%M:%S')
                    print(f"\n🔄 [{current_time_display}] No signals ready - scanning for upcoming trades...")
                    await asyncio.sleep(1)  # Check every 1 seconds
                    continue
                
                # Show upcoming signals info with precise time matching
                if signals:
                    current_time = datetime.now()
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
            print(f"\n📊 SCANNING CSV FOR SIGNALS...")
            initial_signals = self.get_signals_from_csv()
            if initial_signals:
                print(f"✅ Found {len(initial_signals)} signals in CSV:")
                current_time = datetime.now()
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
                    current_time_display = datetime.now().strftime('%H:%M:%S')
                    print(f"\n🔄 [{current_time_display}] No signals ready - scanning...")
                    await asyncio.sleep(1)
                    continue
                
                # Check for exact time match
                current_time = datetime.now()
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

    async def start_2step_trading(self, base_amount: float, multiplier: float = 2.5, is_demo: bool = True):
        """Start 3-Cycle 2-Step Martingale trading: 3 cycles × 2 steps = up to 6 trades"""
        print(f"\n🚀 3-CYCLE 2-STEP MARTINGALE TRADING STARTED")
        print("=" * 60)
        print(f"💰 Base Amount: ${base_amount}")
        print(f"📈 Multiplier: {multiplier}")
        print(f"🔄 Cross-Asset 2-Step System: Precise timing with 1-second checks")
        print(f"⏳ Logic: Wait for exact signal time → Execute → Cross-asset progression")
        print(f"📅 Date Focus: TODAY ONLY ({datetime.now().strftime('%Y-%m-%d')}) - no future dates")
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
            print(f"\n📊 SCANNING CSV FOR SIGNALS...")
            initial_signals = self.get_signals_from_csv()
            if initial_signals:
                print(f"✅ Found {len(initial_signals)} signals in CSV:")
                current_time = datetime.now()
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
                current_time = datetime.now()
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
                    print(f"\rCurrent: {current_time_str} | No signals available", end="", flush=True)
                    await asyncio.sleep(0.01)  # Check every 10ms
                    continue
                
                # Find next signal
                for signal in signals:
                    signal_time_str = signal['signal_datetime'].strftime('%H:%M:%S')
                    
                    # Show current time and signal time
                    print(f"\rCurrent: {current_time_str} | Signal: {signal_time_str} ({signal['asset']} {signal['direction'].upper()})", end="", flush=True)
                    
                    # Execute when times match exactly
                    if current_time_str == signal_time_str:
                        print(f"\n🎯 EXECUTING: {signal['asset']} {signal['direction'].upper()} at {signal_time_str}")
                        
                        # Execute trade
                        try:
                            won, profit, action = await self.execute_single_2step_trade(
                                signal['asset'], signal['direction'], base_amount, strategy, signal.get('channel')
                            )
                            
                            # Show result
                            result_emoji = "✅" if won else "❌"
                            print(f"{result_emoji} {signal['asset']} {'WIN' if won else 'LOSS'} - ${profit:+.2f}")
                            
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

async def main():
    """Main application with trading strategy options"""
    print("=" * 80)
    print("🚀 POCKETOPTION AUTOMATED TRADER")
    print("=" * 80)
    print("📊 Choose your trading strategy:")
    print("=" * 80)
    
    while True:
        print("\n📋 TRADING STRATEGY MENU:")
        print("=" * 40)
        print("1️⃣  Option 1: 3-Step Martingale")
        print("    • Step 1, 2, 3 progression")
        print("    • WIN at any step → Reset to Step 1")
        print("    • LOSS → Continue to next step")
        print("    • All 3 steps lost → Reset to Step 1")
        print()
        print("2️⃣  Option 2: 3-Cycle Progressive Martingale")
        print("    • 3 cycles × 3 steps each = up to 9 total trades")
        print("    • Cycle 1: 3-step martingale")
        print("    • Cycle 2: Continues from Cycle 1's last amount")
        print("    • Cycle 3: Same amounts as Cycle 2 (capped risk)")
        print()
        print("3️⃣  Option 3: 3-Cycle 2-Step Martingale (Cross-Asset)")
        print("    • 3 cycles × 2 steps each = up to 6 total trades")
        print("    • Cycle 1: 2-step martingale (Step 1, Step 2)")
        print("    • LOSS at Step 2 → Next ASSET starts at next cycle")
        print("    • WIN at any step → All assets reset to Cycle 1")
        print("    • Cross-asset cycle progression")
        print()
        print("0️⃣  Exit")
        print("=" * 40)
        
        try:
            strategy_choice = input("\n🎯 Select strategy (1, 2, 3, or 0 to exit): ").strip()
            
            if strategy_choice == '0':
                print("\n👋 Goodbye!")
                break
            
            if strategy_choice not in ['1', '2', '3']:
                print("❌ Please enter 1, 2, 3, or 0")
                continue
            
            # Show selected strategy
            if strategy_choice == '1':
                print("\n✅ Selected: Option 1 - 3-Step Martingale")
                use_option2 = False
                use_option3 = False
            elif strategy_choice == '2':
                print("\n✅ Selected: Option 2 - 3-Cycle Progressive Martingale")
                use_option2 = True
                use_option3 = False
            else:  # strategy_choice == '3'
                print("\n✅ Selected: Option 3 - 3-Cycle 2-Step Martingale")
                use_option2 = False
                use_option3 = True
            
            print("\n📋 TRADING SETUP:")
            print("=" * 40)
            
            # Get channel selection
            print("1. Channel Selection:")
            print("   Available channels:")
            print("   1) James Martin VIP (1:00 trades)")
            print("   2) LC Trader (5:00 trades)")
            print("   3) PO ADVANCE BOT (1:00 trades)")
            
            while True:
                try:
                    channel_choice = input("   Select channel (1, 2, or 3): ").strip()
                    if channel_choice == '1':
                        active_channel = "james_martin"
                        channel_display = "James Martin VIP (1:00 trades)"
                        break
                    elif channel_choice == '2':
                        active_channel = "lc_trader"
                        channel_display = "LC Trader (5:00 trades)"
                        break
                    elif channel_choice == '3':
                        active_channel = "po_advance_bot"
                        channel_display = "PO ADVANCE BOT (1:00 trades)"
                        break
                    else:
                        print("   ❌ Please enter 1, 2, or 3")
                except ValueError:
                    print("   ❌ Please enter 1, 2, or 3")
            
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
            
            # Load trade offset early (before creating trader object)
            def load_trade_offset() -> int:
                """Load trade timing offset from config file"""
                config_file = "trade_config.txt"
                default_offset = 0  # Execute exactly at signal time
                try:
                    if os.path.exists(config_file):
                        with open(config_file, 'r') as f:
                            for line in f:
                                line = line.strip()
                                if line.startswith('#') or not line:
                                    continue
                                if line.startswith('TRADE_OFFSET_SECONDS='):
                                    offset_str = line.split('=')[1].strip()
                                    return int(offset_str)
                    return default_offset
                except:
                    return default_offset
            
            trade_offset_seconds = load_trade_offset()
            
            # Show timing example based on selected channel
            print(f"\n⏰ TIMING EXAMPLE ({channel_display}):")
            example_signal = "00:38:00"
            
            # Calculate example trade time with offset
            if trade_offset_seconds > 0:
                example_trade_time = datetime.strptime(example_signal, '%H:%M:%S') - timedelta(seconds=trade_offset_seconds)
                example_trade = example_trade_time.strftime('%H:%M:%S')
                offset_text = f"{trade_offset_seconds}s before signal"
            elif trade_offset_seconds < 0:
                example_trade_time = datetime.strptime(example_signal, '%H:%M:%S') + timedelta(seconds=abs(trade_offset_seconds))
                example_trade = example_trade_time.strftime('%H:%M:%S')
                offset_text = f"{abs(trade_offset_seconds)}s after signal"
            else:
                example_trade = example_signal
                offset_text = "exactly at signal"
            
            if active_channel == "james_martin":
                example_close_time = datetime.strptime(example_trade, '%H:%M:%S') + timedelta(seconds=60)
                example_close = example_close_time.strftime('%H:%M:%S')
                duration_text = "1:00 duration"
            else:  # lc_trader
                example_close_time = datetime.strptime(example_trade, '%H:%M:%S') + timedelta(seconds=300)
                example_close = example_close_time.strftime('%H:%M:%S')
                duration_text = "5:00 duration"
            
            print(f"   Signal Time: {example_signal}")
            print(f"   Trade Time:  {example_trade} ({offset_text})")
            print(f"   Close Time:  {example_close} ({duration_text})")
            
            # Show strategy preview
            if use_option3:
                # Option 3: 3-Cycle 2-Step Martingale (Cross-Asset)
                c1s1 = base_amount
                c1s2 = c1s1 * multiplier
                c2s1 = c1s2 * multiplier
                c2s2 = c2s1 * multiplier
                c3s1 = c2s2 * multiplier
                c3s2 = c3s1 * multiplier
                
                print(f"\n📊 STRATEGY PREVIEW (3-Cycle 2-Step Cross-Asset Martingale - {channel_display}):")
                print(f"   Cycle 1: Step 1 ${c1s1:.2f} → Step 2 ${c1s2:.2f}")
                print(f"   Cycle 2: Step 1 ${c2s1:.2f} → Step 2 ${c2s2:.2f}")
                print(f"   Cycle 3: Step 1 ${c3s1:.2f} → Step 2 ${c3s2:.2f}")
                print(f"   Trade Duration: {duration_text}")
                print(f"\n🔄 Cross-Asset Cycle Logic:")
                print(f"   • WIN at any step → All assets reset to C1S1")
                print(f"   • LOSS at Step 1 → Move to Step 2 (same asset)")
                print(f"   • LOSS at Step 2 → NEXT asset starts at next cycle")
                print(f"   • Example: EURJPY loses C1S2 → GBPUSD starts at C2S1")
            elif use_option2:
                # Option 2: 3-Cycle Progressive Martingale
                step1_amount = base_amount
                step2_amount = step1_amount * multiplier
                step3_amount = step2_amount * multiplier
                cycle1_last = step3_amount
                cycle2_step1 = cycle1_last * multiplier
                cycle2_step2 = cycle2_step1 * multiplier
                cycle2_step3 = cycle2_step2 * multiplier
                
                print(f"\n📊 STRATEGY PREVIEW (3-Cycle Progressive Martingale - {channel_display}):")
                print(f"   Cycle 1:")
                print(f"     Step 1: ${step1_amount:.2f} (Base)")
                print(f"     Step 2: ${step2_amount:.2f}")
                print(f"     Step 3: ${step3_amount:.2f}")
                print(f"   Cycle 2 (Continues from Cycle 1):")
                print(f"     Step 1: ${cycle2_step1:.2f}")
                print(f"     Step 2: ${cycle2_step2:.2f}")
                print(f"     Step 3: ${cycle2_step3:.2f}")
                print(f"   Cycle 3: Same as Cycle 2 (Capped Risk)")
                print(f"   Trade Duration: {duration_text}")
                print(f"\n🔄 Progressive Martingale Logic:")
                print(f"   • WIN at any step → Reset to Cycle 1, Step 1")
                print(f"   • LOSS → Continue to next step")
                print(f"   • Cycle 2 continues from Cycle 1's last amount")
                print(f"   • Cycle 3 uses same amounts as Cycle 2")
            else:
                # Option 1: 3-Step Martingale
                step1_amount = base_amount
                step2_amount = step1_amount * multiplier
                step3_amount = step2_amount * multiplier
                print(f"\n📊 STRATEGY PREVIEW (3-Step Martingale - {channel_display}):")
                print(f"   Step 1: ${step1_amount:.2f} (Base)")
                print(f"   Step 2: ${step2_amount:.2f} (${step1_amount:.2f} × {multiplier})")
                print(f"   Step 3: ${step3_amount:.2f} (${step2_amount:.2f} × {multiplier})")
                print(f"   Total Risk: ${step1_amount + step2_amount + step3_amount:.2f}")
                print(f"   Trade Duration: {duration_text}")
                print(f"\n🔄 Martingale Logic:")
                print(f"   • WIN at any step → Reset to Step 1")
                print(f"   • LOSS → Continue to next step")
                print(f"   • All 3 steps lost → Reset to Step 1")
            
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
                # Start trading based on strategy
                if use_option3:
                    # Option 3: 2-Step Martingale
                    await trader.start_2step_trading(base_amount, multiplier, is_demo)
                elif use_option2:
                    # Option 2: 3-Cycle Progressive Martingale
                    await trader.start_option2_trading(base_amount, multiplier, is_demo)
                else:
                    # Option 1: 3-Step Martingale
                    await trader.start_precise_trading(base_amount, multiplier, is_demo)
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
    asyncio.run(main())
#!/usr/bin/env python3
"""
PocketOption Precise Timing Trader
Places trades 19 seconds before signal time and closes after exactly 59 seconds
Example: Signal at 00:38:00 → Trade at 00:37:41 → Close at 00:38:40 (59s duration)
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

class MultiAssetPreciseTrader:
    """Multi-asset trader with immediate step progression"""
    
    def __init__(self):
        self.ssid = os.getenv('SSID')
        self.client = None
        
        # Use available CSV files
        # Check which CSV files exist and use the appropriate one
        available_csvs = [
            "pocketoption_lc_trader_20260113.csv",
            "pocketoption_james_martin_vip_channel_m1_20260113.csv"
        ]
        
        # Use the first available CSV file
        self.csv_file = None
        for csv_file in available_csvs:
            if os.path.exists(csv_file):
                self.csv_file = csv_file
                break
        
        if not self.csv_file:
            # Fallback to date-based filename
            today = datetime.now().strftime('%Y%m%d')
            self.csv_file = f"pocketoption_messages_{today}.csv"
        
        self.trade_history = []
        self.pending_immediate_trades = []  # Queue for immediate next step trades
        
        # API health tracking
        self.api_failures = 0
        self.max_api_failures = 3  # System will fail after 3 consecutive failures
        self.last_successful_api_call = datetime.now()
        
        # Available assets - based on PocketOption API library constants
        self.WORKING_ASSETS = {
            # Major pairs (direct format) - Forex only for trading signals
            'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'USDCAD', 'AUDUSD', 'NZDUSD',
            # Cross pairs (require _otc suffix)
            'AUDCAD', 'AUDCHF', 'AUDJPY', 'AUDNZD', 'CADCHF', 'CADJPY', 'CHFJPY', 
            'CHFNOK', 'EURCHF', 'EURGBP', 'EURHUF', 'EURJPY', 'EURNZD', 'EURRUB', 
            'GBPAUD', 'GBPJPY', 'NZDJPY', 'USDRUB'
        }
        
        # Assets that don't work with the API (confirmed not in API library)
        self.UNSUPPORTED_ASSETS = {
            'BRLUSD', 'USDBRL', 'USDCOP', 'NZDCAD', 'USDPKR', 'USDBDT', 'USDEGP'
        }
        
        print(f"📊 Using CSV file: {self.csv_file}")
    
    def _validate_duration(self, duration: int) -> int:
        """Ensure duration is exactly 59 seconds"""
        if duration != 59:
            print(f"⚠️ Duration {duration}s adjusted to 59s")
            return 59
        else:
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
        """Get trading signals from CSV file"""
        try:
            if not os.path.exists(self.csv_file):
                print(f"❌ CSV file not found: {self.csv_file}")
                return []
            
            df = pd.read_csv(self.csv_file, on_bad_lines='skip')
            
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
                    
                    # Normalize asset format: uppercase base, lowercase _otc suffix
                    if asset.lower().endswith('_otc'):
                        base_asset = asset[:-4].upper()
                        trading_asset = f"{base_asset}_otc"
                    else:
                        trading_asset = asset.upper()
                    
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
                        print(f"❌ Unsupported {asset_type} asset: {asset} - not supported")
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
                        
                        # Set to today's date
                        signal_datetime = current_time.replace(
                            hour=signal_time.hour,
                            minute=signal_time.minute,
                            second=signal_time.second if signal_time_str.count(':') == 2 else 0,
                            microsecond=0
                        )
                        
                        # If signal time has passed today, set it for tomorrow
                        if signal_datetime <= current_time:
                            signal_datetime = signal_datetime + timedelta(days=1)
                        
                        # Calculate trade execution time (19 seconds before signal time)
                        trade_datetime = signal_datetime - timedelta(seconds=19)
                        
                        # Skip past trades (more than 2 minutes ago)
                        time_diff = (trade_datetime - current_time).total_seconds()
                        if time_diff < -120:
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
                        'trade_datetime': trade_datetime,  # 19 seconds before signal
                        'close_datetime': trade_datetime + timedelta(seconds=59),  # 59 seconds after trade
                        'timestamp': datetime.now().isoformat(),
                        'message_text': str(row.get('message_text', ''))[:100]
                    }
                    
                    # Debug timing
                    current_time_for_debug = datetime.now()
                    time_until_trade = (trade_datetime - current_time_for_debug).total_seconds()
                    
                    print(f"🔍 Signal parsed: {trading_asset} {direction} at {signal_time_str}")
                    print(f"   Signal time: {signal_datetime.strftime('%H:%M:%S')}")
                    print(f"   Trade time:  {trade_datetime.strftime('%H:%M:%S')} (19s before signal)")
                    
                    if time_until_trade > 0:
                        wait_minutes = int(time_until_trade // 60)
                        wait_seconds = int(time_until_trade % 60)
                        print(f"   ⏰ Wait time: {wait_minutes}m {wait_seconds}s")
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
        """Map CSV asset names to API format based on comprehensive testing"""
        # Handle new _otc format from improved CSV parsing
        if csv_asset.endswith('_otc'):
            base_asset = csv_asset[:-4]  # Remove _otc suffix
            # For _otc assets, always return with _otc suffix (they're cross pairs)
            return csv_asset  # Keep as GBPUSD_otc
        elif csv_asset.endswith('-OTCp'):
            base_asset = csv_asset[:-5]
            return f"{base_asset}_otc"  # Convert to _otc format
        elif csv_asset.endswith('-OTC'):
            base_asset = csv_asset[:-4]
            return f"{base_asset}_otc"  # Convert to _otc format
        else:
            base_asset = csv_asset
        
        # Based on PocketOption API library constants:
        
        # Major pairs that work with direct format
        major_pairs = {'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'USDCAD', 'AUDUSD', 'NZDUSD'}
        
        # Cross pairs that ONLY work with _otc suffix
        cross_pairs_otc = {
            'AUDCAD', 'AUDCHF', 'AUDJPY', 'AUDNZD', 'CADCHF', 'CADJPY', 'CHFJPY', 
            'CHFNOK', 'EURCHF', 'EURGBP', 'EURHUF', 'EURJPY', 'EURNZD', 'EURRUB', 
            'GBPAUD', 'GBPJPY', 'NZDJPY', 'USDRUB'
        }
        
        if base_asset in major_pairs:
            # Major pairs work with direct format
            return base_asset
        elif base_asset in cross_pairs_otc:
            # Cross pairs ONLY work with _otc suffix
            return f"{base_asset}_otc"
        else:
            # Unknown/exotic pairs - return as is (will likely fail)
            return base_asset
    
    async def execute_martingale_sequence(self, asset: str, direction: str, base_amount: float, strategy: 'MultiAssetMartingaleStrategy') -> Tuple[bool, float]:
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
                    # Use regular precise trade for Step 1 (scheduled)
                    won, profit = await self.execute_precise_trade({
                        'asset': asset,
                        'direction': direction,
                        'trade_datetime': datetime.now(),
                        'signal_datetime': datetime.now() + timedelta(seconds=5),
                        'close_datetime': datetime.now() + timedelta(seconds=59)
                    }, step_amount)
                else:
                    # Use immediate trade for Steps 2 and 3
                    won, profit = await self.execute_immediate_trade(asset, direction, step_amount)
                
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
                        
                        # Wait a bit before next step to avoid API overload
                        await asyncio.sleep(0.5)
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
                    await asyncio.sleep(0.5)  # Wait after error
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
    
    async def execute_immediate_trade(self, asset: str, direction: str, amount: float) -> Tuple[bool, float]:
        """Execute immediate trade (for next step after loss) with improved timeout handling"""
        try:
            print(f"⚡ IMMEDIATE: {asset} {direction.upper()} ${amount}")
            
            execution_time = datetime.now()
            # For immediate trades, use exactly 59 seconds duration
            dynamic_duration = 59
            
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
                    
                    # Improved result checking with longer timeout for immediate trades
                    try:
                        # Use appropriate timeout for 59s trades (duration + small buffer)
                        max_wait = min(70.0, dynamic_duration + 10.0)  # Max 70 seconds for 59s trades
                        print(f"⏳ Monitoring immediate result (max {max_wait:.0f}s)...")
                        
                        start_time = datetime.now()
                        win_result = None
                        
                        # Use longer polling intervals to reduce API stress
                        while (datetime.now() - start_time).total_seconds() < max_wait:
                            try:
                                win_result = await asyncio.wait_for(
                                    self.client.check_win(order_result.order_id, max_wait_time=10.0),
                                    timeout=10.0
                                )
                                
                                if win_result and win_result.get('completed', False):
                                    break
                                
                                elapsed = (datetime.now() - start_time).total_seconds()
                                remaining = max_wait - elapsed
                                if remaining > 5:
                                    print(f"⏳ Trade active, checking again in 5s (remaining: {remaining:.0f}s)")
                                    await asyncio.sleep(0.5)  # Reduce API calls
                                else:
                                    break
                                    
                            except asyncio.TimeoutError:
                                elapsed = (datetime.now() - start_time).total_seconds()
                                remaining = max_wait - elapsed
                                if remaining > 3:
                                    await asyncio.sleep(0.3)
                                else:
                                    break
                            except Exception as check_error:
                                print(f"⚠️ Check error: {check_error}")
                                await asyncio.sleep(0.2)
                        
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
        """Execute trade with precise timing"""
        try:
            asset = signal['asset']
            direction = signal['direction']
            trade_time = signal['trade_datetime']
            signal_time = signal['signal_datetime']
            
            current_time = datetime.now()
            
            # Wait until EXACT trade execution time
            wait_seconds = (trade_time - current_time).total_seconds()
            
            # If wait time is more than 1 minute, skip this signal
            if wait_seconds > 59:
                print(f"⏰ Signal too far: {wait_seconds:.0f}s (>{59}s) - SKIPPING")
                return False, 0  # Skip this trade
            
            if wait_seconds > 0:
                print(f"⏰ Waiting {wait_seconds:.0f}s until trade time: {trade_time.strftime('%H:%M:%S')}")
                print(f"📝 {asset} {direction.upper()} → Execute 19s before signal")
                
                # Wait with high precision for exact timing
                while wait_seconds > 1:
                    if wait_seconds > 10:
                        await asyncio.sleep(0.5)  # Fast updates every 0.5s
                        current_time = datetime.now()
                        wait_seconds = (trade_time - current_time).total_seconds()
                        if wait_seconds > 10:
                            print(f"⏰ {wait_seconds:.0f}s until EXACT trade execution")
                    else:
                        await asyncio.sleep(max(0.001, wait_seconds - 0.1))
                        break
                
                # Final precision timing - execute within 10ms of target time
                while True:
                    current_time = datetime.now()
                    remaining = (trade_time - current_time).total_seconds()
                    if remaining <= 0.01:  # Execute within 10ms
                        break
                    await asyncio.sleep(0.001)  # 1ms precision
            
            execution_time = datetime.now()
            
            # Calculate target close time - EXACTLY 59 seconds later
            signal_minute = signal_time.minute
            signal_hour = signal_time.hour
            
            # Target close time is exactly 59 seconds after trade execution
            target_close_time = execution_time + timedelta(seconds=59)
            
            # Calculate EXACT duration to hit target close time
            dynamic_duration = 59  # Always use exactly 59 seconds
            
            # Ensure duration is exactly 59 seconds
            actual_close_time = execution_time + timedelta(seconds=59)
            
            print(f"🎯 EXECUTING: {asset} {direction.upper()} ${amount}")
            print(f"⏰ TIMING: Trade {execution_time.strftime('%H:%M:%S.%f')[:12]} → Signal {signal_time.strftime('%H:%M:%S')} → Close {actual_close_time.strftime('%H:%M:%S')}")
            print(f"📊 EXACT Duration: {dynamic_duration}s (target: {target_close_time.strftime('%H:%M:%S')})")
            
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
                    
                    # Monitor trade result with appropriate timeout for 59s trades
                    try:
                        max_wait = min(70.0, dynamic_duration + 10.0)  # Max 70 seconds for 59s trades
                        print(f"⏳ Monitoring result (max {max_wait:.0f}s)...")
                        
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
                                if remaining > 2:
                                    print(f"⏳ Trade active, checking again in 0.2s (remaining: {remaining:.0f}s)")
                                    await asyncio.sleep(0.2)
                                else:
                                    break
                                    
                            except asyncio.TimeoutError:
                                elapsed = (datetime.now() - start_time).total_seconds()
                                remaining = max_wait - elapsed
                                if remaining > 2:
                                    print(f"⏳ Checking result... ({elapsed:.0f}s elapsed)")
                                    await asyncio.sleep(0.1)
                                else:
                                    break
                            except Exception as check_error:
                                print(f"⚠️ Check error: {check_error}")
                                await asyncio.sleep(0.1)
                        
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
        """Start precise timing trading with SEQUENTIAL martingale progression"""
        print(f"\n🚀 SEQUENTIAL MARTINGALE TRADING STARTED")
        print("=" * 60)
        print(f"💰 Base Amount: ${base_amount}")
        print(f"📈 Multiplier: {multiplier}")
        print(f"🔄 Sequential System: Wait for each step result before next step")
        print(f"⏳ Step Timing: Step 1 → Wait for result → Step 2 → Wait → Step 3")
        print(f"✅ WIN at any step → Reset to Step 1 for next signal")
        print(f"❌ LOSS → Continue to next step (martingale)")
        print(f"🔄 All 3 steps lost → Reset to Step 1 for next signal")
        print(f"🔧 API Health: Improved timeout handling and error recovery")
        print("Press Ctrl+C to stop")
        print("=" * 60)
        
        strategy = MultiAssetMartingaleStrategy(base_amount, multiplier)
        session_profit = 0.0
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
                print(f"❌ No signals found in CSV - add signals to {self.csv_file}")
            print("=" * 60)
            
            while True:
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
                            
                            session_profit += profit
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
                        
                        print(f"📊 Session: ${session_profit:+.2f} | Trades: {session_trades}")
                        print(f"🏆 Results: {wins}W/{losses}L")
                
                # Get signals for scheduled trades
                signals = self.get_signals_from_csv()
                
                if not signals and not self.pending_immediate_trades:
                    # Show API health status periodically
                    if hasattr(self, 'api_failures') and self.api_failures > 0:
                        health_status = f"API Health: {self.api_failures}/{self.max_api_failures} failures"
                        print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] No signals ready - {health_status}")
                    else:
                        print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] No signals ready - checking again in 1 second...")
                    await asyncio.sleep(0.1)  # Check every 0.1 seconds for upcoming signals
                    continue
                
                # Show upcoming signals info
                if signals:
                    current_time = datetime.now()
                    ready_signals = []
                    future_signals = []
                    
                    for signal in signals:
                        time_until_trade = (signal['trade_datetime'] - current_time).total_seconds()
                        if time_until_trade <= 5:  # Ready to execute (within 5 seconds)
                            ready_signals.append(signal)
                        else:  # Future signal
                            future_signals.append((signal, time_until_trade))
                    
                    if future_signals:
                        print(f"\n📅 UPCOMING SIGNALS:")
                        for signal, wait_time in sorted(future_signals, key=lambda x: x[1])[:3]:  # Show next 3
                            wait_minutes = int(wait_time // 60)
                            wait_seconds = int(wait_time % 60)
                            print(f"   {signal['asset']} {signal['direction'].upper()} at {signal['signal_time']} (in {wait_minutes}m {wait_seconds}s)")
                    
                    if not ready_signals:
                        if future_signals:
                            next_signal, next_wait = min(future_signals, key=lambda x: x[1])
                            wait_minutes = int(next_wait // 60)
                            wait_seconds = int(next_wait % 60)
                            print(f"⏰ Next signal: {next_signal['asset']} {next_signal['direction'].upper()} in {wait_minutes}m {wait_seconds}s")
                        await asyncio.sleep(0.1)  # Wait 0.1 second and check again
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
                                    asset, direction, base_amount, strategy
                                )
                                
                                session_profit += total_profit
                                session_trades += 1  # Count as one sequence
                                
                                if final_won:
                                    print(f"🎉 {asset} SEQUENCE WIN! Total profit: ${total_profit:+.2f}")
                                else:
                                    print(f"💔 {asset} SEQUENCE LOSS! Total loss: ${total_profit:+.2f}")
                                
                            except Exception as sequence_error:
                                print(f"❌ Martingale sequence error for {asset}: {sequence_error}")
                                # Reset the asset strategy on error
                                strategy.asset_strategies[asset] = {'step': 1, 'amounts': []}
                            
                            # Show session stats after all signals processed
                            wins = len([t for t in self.trade_history if t['result'] == 'win'])
                            losses = len([t for t in self.trade_history if t['result'] == 'loss'])
                            
                            print(f"\n📊 PRIORITY TRADING SESSION:")
                            print(f"   💰 Session P&L: ${session_profit:+.2f}")
                            print(f"   📈 Total Trades: {session_trades}")
                            print(f"   🏆 Results: {wins}W/{losses}L")
                            
                            # Show current status of all active assets
                            active_assets = strategy.get_all_active_assets()
                            if active_assets:
                                print(f"   📊 Asset Status:")
                                for asset in active_assets:
                                    status = strategy.get_status(asset)
                                    step = strategy.get_asset_step(asset)
                                    if step > 1:
                                        print(f"      🎯 {status} (IN SEQUENCE)")
                                    else:
                                        print(f"      ✅ {status} (READY)")
                
                await asyncio.sleep(0.05)  # 50ms check interval
                
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
        print(f"   💰 Session P&L: ${session_profit:.2f}")
        print(f"   📈 Session Trades: {session_trades}")
        print(f"   🏆 Results: {total_wins}W/{total_losses}L")
        print(f"   💵 Total P&L: ${total_profit:.2f}")
        print(f"   🎯 Assets Tracked: {len(strategy.get_all_active_assets())}")

async def main():
    """Main application with SEQUENTIAL martingale progression"""
    print("=" * 80)
    print("🚀 POCKETOPTION SEQUENTIAL MARTINGALE TRADER")
    print("=" * 80)
    print("🔄 SEQUENTIAL PROGRESSION: Wait for each step result before next step")
    print("⏰ Scheduled trades: 19 seconds before signal time")
    print("🎯 Trades close exactly 59 seconds after execution")
    print("📝 Example: Step 1 → Wait for result → Step 2 → Wait → Step 3")
    print("✅ WIN at any step → Reset to Step 1 for next signal")
    print("❌ LOSS → Continue to next step (martingale)")
    print("🔄 All 3 steps lost → Reset to Step 1 for next signal")
    print("🔧 Improved: Better timeout handling and error recovery")
    print("=" * 80)
    
    while True:
        print("\n📋 PRECISE TIMING SETUP:")
        print("=" * 40)
        
        try:
            # Get account type
            print("1. Account Type:")
            account_choice = input("   Use DEMO account? (Y/n): ").lower().strip()
            is_demo = account_choice != 'n'
            print(f"   ✅ {'DEMO' if is_demo else 'REAL'} account selected")
            
            # Get base amount
            print("\n2. Base Amount:")
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
            print("\n3. Multiplier:")
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
            
            # Show timing example
            print(f"\n⏰ TIMING EXAMPLE:")
            example_signal = "00:38:00"
            example_trade = "00:37:41"
            example_close = "00:38:41"
            print(f"   Signal Time: {example_signal}")
            print(f"   Trade Time:  {example_trade} (19s before)")
            print(f"   Close Time:  {example_close} (59s duration)")
            
            # Show strategy preview
            step1_amount = base_amount
            step2_amount = step1_amount * multiplier
            step3_amount = step2_amount * multiplier
            print(f"\n📊 STRATEGY PREVIEW (3-Step Martingale):")
            print(f"   Step 1: ${step1_amount:.2f} (Base)")
            print(f"   Step 2: ${step2_amount:.2f} (${step1_amount:.2f} × {multiplier})")
            print(f"   Step 3: ${step3_amount:.2f} (${step2_amount:.2f} × {multiplier})")
            print(f"   Total Risk: ${step1_amount + step2_amount + step3_amount:.2f}")
            
            # Confirm start
            print(f"\n🚀 Ready to start precise timing trading!")
            start = input("Start trading? (Y/n): ").lower().strip()
            if start == 'n':
                continue
            
            # Initialize trader
            trader = MultiAssetPreciseTrader()
            
            # Connect
            if not await trader.connect(is_demo):
                print("❌ Failed to connect")
                continue
            
            try:
                # Start precise timing trading
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
    
    print("\n👋 Thank you for using PocketOption Precise Timing Trader!")

if __name__ == "__main__":
    asyncio.run(main())
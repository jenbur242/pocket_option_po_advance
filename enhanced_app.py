#!/usr/bin/env python3
"""
Enhanced PocketOption Trader with Signal Queue Management
Handles multiple upcoming signals with proper queue management and execution timing
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

# Import existing components
from app import (
    MultiAssetPreciseTrader, 
    MultiAssetMartingaleStrategy,
    TwoStepMartingaleStrategy,
    FourCycleMartingaleStrategy,
    set_user_timezone,
    get_user_time,
    get_user_time_str,
    format_time_hmsms
)

# Import new signal queue manager
from signal_queue_manager import SignalQueueManager, QueuedSignal, SignalStatus

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EnhancedMultiAssetTrader(MultiAssetPreciseTrader):
    """
    Enhanced trader with signal queue management
    Features:
    - Automatic signal queue management from CSV
    - Multiple upcoming signals handling
    - Concurrent execution of simultaneous signals
    - Real-time queue monitoring
    - Automatic signal expiry handling
    """
    
    def __init__(self, base_amount: float, multiplier: float = 2.5, 
                 stop_loss: float = None, take_profit: float = None):
        super().__init__(base_amount, multiplier, stop_loss, take_profit)
        
        # Initialize signal queue manager
        self.signal_queue = SignalQueueManager(expiry_seconds=30)
        
        # Queue management settings
        self.queue_refresh_interval = 5  # Refresh queue every 5 seconds
        self.last_queue_refresh = None
        self.auto_queue_management = True
        
        # Enhanced statistics
        self.session_stats = {
            'signals_queued': 0,
            'signals_executed': 0,
            'signals_expired': 0,
            'concurrent_executions': 0,
            'queue_refreshes': 0
        }
        
        print(f"🚀 Enhanced Multi-Asset Trader Initialized")
        print(f"📊 Signal Queue: Automatic management enabled")
        print(f"⏰ Queue refresh: Every {self.queue_refresh_interval} seconds")
        print(f"⏳ Signal expiry: {self.signal_queue.expiry_seconds} seconds")
    
    def refresh_signal_queue(self) -> Tuple[int, int]:
        """
        Refresh signal queue from CSV files
        Returns (new_signals_added, duplicates_skipped)
        """
        try:
            # Get fresh signals from CSV
            signals = self.get_signals_from_csv()
            
            if not signals:
                return 0, 0
            
            # Add signals to queue
            added, duplicates = self.signal_queue.add_signals_batch(signals)
            
            # Update statistics
            self.session_stats['signals_queued'] += added
            self.session_stats['queue_refreshes'] += 1
            self.last_queue_refresh = get_user_time()
            
            if added > 0:
                logger.info(f"Queue refreshed: {added} new signals added, {duplicates} duplicates skipped")
            
            return added, duplicates
            
        except Exception as e:
            logger.error(f"Error refreshing signal queue: {e}")
            return 0, 0
    
    def should_refresh_queue(self) -> bool:
        """Check if queue should be refreshed"""
        if not self.auto_queue_management:
            return False
        
        if self.last_queue_refresh is None:
            return True
        
        time_since_refresh = (get_user_time() - self.last_queue_refresh).total_seconds()
        return time_since_refresh >= self.queue_refresh_interval
    
    async def process_signal(self, queued_signal: QueuedSignal) -> Dict[str, Any]:
        """
        Process a single queued signal
        Returns execution result
        """
        asset = queued_signal.asset
        direction = queued_signal.direction
        
        try:
            # Execute the trade using existing precise trade logic
            won, profit = await self.execute_precise_trade({
                'asset': asset,
                'direction': direction,
                'trade_datetime': queued_signal.trade_datetime,
                'signal_datetime': queued_signal.signal_datetime,
                'close_datetime': queued_signal.close_datetime,
                'channel': queued_signal.channel,
                'duration': queued_signal.duration,
                'signal_time': queued_signal.signal_time,
                'message_text': queued_signal.message_text
            }, self.base_amount)
            
            # Update session profit
            self.update_session_profit(profit)
            
            result = {
                'won': won,
                'profit': profit,
                'asset': asset,
                'direction': direction,
                'signal_time': queued_signal.signal_time,
                'executed_at': get_user_time().isoformat()
            }
            
            # Update statistics
            self.session_stats['signals_executed'] += 1
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing signal {queued_signal.signal_id}: {e}")
            return {
                'error': str(e),
                'asset': asset,
                'direction': direction,
                'signal_time': queued_signal.signal_time
            }
    
    async def start_enhanced_trading(self, strategy_type: str = "martingale"):
        """
        Start enhanced trading with signal queue management
        
        Args:
            strategy_type: "martingale", "single", "2step", "4cycle"
        """
        print(f"\n🚀 ENHANCED TRADING STARTED")
        print("=" * 60)
        print(f"💰 Base Amount: ${self.base_amount}")
        print(f"📈 Strategy: {strategy_type.upper()}")
        print(f"🎯 Queue Management: Automatic")
        print(f"⏰ Real-time Processing: Multiple signals supported")
        
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
        if strategy_type == "martingale":
            strategy = MultiAssetMartingaleStrategy(self.base_amount, self.multiplier)
        elif strategy_type == "2step":
            strategy = TwoStepMartingaleStrategy(self.base_amount, self.multiplier)
        elif strategy_type == "4cycle":
            strategy = FourCycleMartingaleStrategy(self.base_amount, self.multiplier)
        else:
            strategy = None  # Single trade mode
        
        session_trades = 0
        
        try:
            # Initial queue population
            print(f"\n📊 INITIALIZING SIGNAL QUEUE...")
            added, duplicates = self.refresh_signal_queue()
            if added > 0:
                print(f"✅ Loaded {added} signals into queue")
                self.signal_queue.print_queue_summary(get_user_time())
            else:
                print(f"❌ No signals found in CSV - add signals to continue")
            print("=" * 60)
            
            while True:
                current_time = get_user_time()
                
                # Check stop loss and take profit conditions
                should_stop, stop_reason = self.should_stop_trading()
                if should_stop:
                    print(f"\n{stop_reason}")
                    print(f"🏁 Trading session ended")
                    break
                
                # Refresh queue if needed
                if self.should_refresh_queue():
                    added, duplicates = self.refresh_signal_queue()
                    if added > 0:
                        print(f"\n🔄 Queue refreshed: {added} new signals added")
                
                # Clean up expired signals
                expired_count = self.signal_queue.cleanup_expired_signals(current_time)
                if expired_count > 0:
                    self.session_stats['signals_expired'] += expired_count
                    print(f"⏰ Cleaned {expired_count} expired signals")
                
                # Get queue status for display
                status_display = self.signal_queue.get_status_display(current_time)
                current_time_str = get_user_time_str()
                
                # Process ready signals
                if strategy_type == "single":
                    # Single trade mode
                    results = await self.signal_queue.process_ready_signals(
                        current_time, 
                        self.process_signal
                    )
                else:
                    # Martingale strategy modes
                    results = await self.signal_queue.process_ready_signals(
                        current_time,
                        lambda signal: self.process_signal_with_strategy(signal, strategy)
                    )
                
                # Display results
                if results:
                    print(f"\n🚀 EXECUTED {len(results)} SIGNALS:")
                    for queued_signal, result in results:
                        if 'error' in result:
                            print(f"❌ {result['asset']} {result['direction'].upper()}: {result['error']}")
                        else:
                            session_trades += 1
                            if result['won']:
                                print(f"✅ {result['asset']} {result['direction'].upper()} WIN: ${result['profit']:+.2f}")
                            else:
                                print(f"❌ {result['asset']} {result['direction'].upper()} LOSS: ${result['profit']:+.2f}")
                    
                    # Show session stats
                    print(f"\n📊 SESSION STATUS:")
                    print(f"   💰 {self.get_session_status()}")
                    print(f"   📈 Trades: {session_trades}")
                    print(f"   🎯 Queue: {self.session_stats['signals_queued']} queued, {self.session_stats['signals_executed']} executed")
                    
                    # Check stop conditions after processing
                    should_stop, stop_reason = self.should_stop_trading()
                    if should_stop:
                        print(f"\n{stop_reason}")
                        break
                else:
                    # Show status line
                    print(f"\r⏰ {current_time_str} | {status_display}", end="", flush=True)
                
                # Wait before next check
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            print(f"\n🛑 TRADING STOPPED BY USER")
        except Exception as e:
            print(f"❌ Trading error: {e}")
            logger.error(f"Trading error: {e}")
        
        # Final statistics
        self.print_final_statistics(session_trades)
    
    async def process_signal_with_strategy(self, queued_signal: QueuedSignal, strategy) -> Dict[str, Any]:
        """Process signal with martingale strategy"""
        asset = queued_signal.asset
        direction = queued_signal.direction
        
        try:
            # Execute martingale sequence for this asset
            final_won, total_profit = await self.execute_martingale_sequence(
                asset, direction, self.base_amount, strategy, queued_signal.channel
            )
            
            # Update session profit
            self.update_session_profit(total_profit)
            
            result = {
                'won': final_won,
                'profit': total_profit,
                'asset': asset,
                'direction': direction,
                'signal_time': queued_signal.signal_time,
                'executed_at': get_user_time().isoformat(),
                'strategy_type': 'martingale_sequence'
            }
            
            self.session_stats['signals_executed'] += 1
            return result
            
        except Exception as e:
            logger.error(f"Error processing signal with strategy {queued_signal.signal_id}: {e}")
            return {
                'error': str(e),
                'asset': asset,
                'direction': direction,
                'signal_time': queued_signal.signal_time
            }
    
    def print_final_statistics(self, session_trades: int):
        """Print comprehensive final statistics"""
        total_trades = len(self.trade_history)
        total_wins = len([t for t in self.trade_history if t['result'] == 'win'])
        total_losses = len([t for t in self.trade_history if t['result'] == 'loss'])
        total_profit = sum([t['profit_loss'] for t in self.trade_history])
        
        print(f"\n📊 FINAL STATISTICS:")
        print(f"   💰 {self.get_session_status()}")
        print(f"   📈 Session Trades: {session_trades}")
        print(f"   🏆 Results: {total_wins}W/{total_losses}L")
        print(f"   💵 Total P&L: ${total_profit:.2f}")
        
        # Queue statistics
        print(f"\n🎯 QUEUE STATISTICS:")
        print(f"   📊 Signals queued: {self.session_stats['signals_queued']}")
        print(f"   ✅ Signals executed: {self.session_stats['signals_executed']}")
        print(f"   ⏰ Signals expired: {self.session_stats['signals_expired']}")
        print(f"   🔄 Queue refreshes: {self.session_stats['queue_refreshes']}")
        print(f"   🚀 Max concurrent: {self.signal_queue.stats['concurrent_executions']}")
        
        # Final queue status
        current_time = get_user_time()
        queue_status = self.signal_queue.get_queue_status(current_time)
        print(f"   📋 Final queue: {queue_status['pending_count']} pending, {queue_status['completed_count']} completed")

async def main():
    """Main function to run enhanced trading"""
    print("🚀 ENHANCED POCKETOPTION TRADER")
    print("=" * 50)
    print("Features:")
    print("• Automatic signal queue management")
    print("• Multiple upcoming signals handling") 
    print("• Concurrent execution support")
    print("• Real-time queue monitoring")
    print("• Automatic signal expiry handling")
    print("=" * 50)
    
    # Configuration
    base_amount = 1.0
    multiplier = 2.5
    stop_loss = None  # Set to dollar amount if desired
    take_profit = None  # Set to dollar amount if desired
    
    # Set timezone (adjust as needed)
    set_user_timezone(6.0)  # UTC+6
    
    # Initialize enhanced trader
    trader = EnhancedMultiAssetTrader(
        base_amount=base_amount,
        multiplier=multiplier,
        stop_loss=stop_loss,
        take_profit=take_profit
    )
    
    # Set active channel (adjust as needed)
    trader.active_channel = "trade_x_po"  # or "james_martin", "lc_trader", etc.
    
    try:
        # Connect to PocketOption
        await trader.connect(is_demo=True)
        
        # Start enhanced trading
        # Options: "martingale", "single", "2step", "4cycle"
        await trader.start_enhanced_trading(strategy_type="martingale")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if trader.client:
            await trader.client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
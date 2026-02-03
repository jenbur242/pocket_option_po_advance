#!/usr/bin/env python3
"""
Signal Queue Manager - Enhanced signal processing with proper queue management
Handles multiple upcoming signals and executes them at the correct time
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
import heapq
from enum import Enum

logger = logging.getLogger(__name__)

class SignalStatus(Enum):
    PENDING = "pending"
    READY = "ready"
    EXECUTING = "executing"
    COMPLETED = "completed"
    EXPIRED = "expired"

@dataclass
class QueuedSignal:
    """Represents a signal in the queue with execution timing"""
    signal_id: str
    asset: str
    direction: str
    signal_time: str
    signal_datetime: datetime
    trade_datetime: datetime
    close_datetime: datetime
    channel: str
    duration: int
    message_text: str = ""
    status: SignalStatus = SignalStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    executed_at: Optional[datetime] = None
    
    def __lt__(self, other):
        """For heapq ordering by trade_datetime"""
        return self.trade_datetime < other.trade_datetime
    
    def is_ready(self, current_time: datetime) -> bool:
        """Check if signal is ready for execution (exact time match)"""
        current_hms = current_time.strftime('%H:%M:%S')
        signal_hms = self.trade_datetime.strftime('%H:%M:%S')
        return current_hms == signal_hms
    
    def is_expired(self, current_time: datetime, expiry_seconds: int = 30) -> bool:
        """Check if signal has expired (missed execution window)"""
        time_passed = (current_time - self.trade_datetime).total_seconds()
        return time_passed > expiry_seconds
    
    def time_until_execution(self, current_time: datetime) -> float:
        """Get seconds until execution time"""
        return (self.trade_datetime - current_time).total_seconds()

class SignalQueueManager:
    """
    Enhanced signal queue manager that handles multiple upcoming signals
    Features:
    - Priority queue for time-ordered signal execution
    - Automatic signal expiry handling
    - Duplicate signal detection
    - Concurrent execution of simultaneous signals
    - Real-time status monitoring
    """
    
    def __init__(self, expiry_seconds: int = 30):
        self.signal_queue: List[QueuedSignal] = []  # Priority queue (heapq)
        self.active_signals: Dict[str, QueuedSignal] = {}  # Currently executing signals
        self.completed_signals: Dict[str, QueuedSignal] = {}  # Completed signals
        self.expiry_seconds = expiry_seconds
        self.running = False
        
        # Statistics
        self.stats = {
            'total_queued': 0,
            'total_executed': 0,
            'total_expired': 0,
            'total_completed': 0,
            'concurrent_executions': 0
        }
    
    def create_signal_id(self, asset: str, direction: str, signal_time: str) -> str:
        """Create unique signal ID to prevent duplicates"""
        return f"{asset}_{direction}_{signal_time}"
    
    def add_signal(self, signal_data: Dict[str, Any]) -> bool:
        """
        Add a new signal to the queue
        Returns True if added, False if duplicate
        """
        signal_id = self.create_signal_id(
            signal_data['asset'],
            signal_data['direction'], 
            signal_data['signal_time']
        )
        
        # Check for duplicates
        if (signal_id in self.active_signals or 
            signal_id in self.completed_signals or
            any(s.signal_id == signal_id for s in self.signal_queue)):
            return False
        
        # Create queued signal
        queued_signal = QueuedSignal(
            signal_id=signal_id,
            asset=signal_data['asset'],
            direction=signal_data['direction'],
            signal_time=signal_data['signal_time'],
            signal_datetime=signal_data['signal_datetime'],
            trade_datetime=signal_data['trade_datetime'],
            close_datetime=signal_data['close_datetime'],
            channel=signal_data.get('channel', 'unknown'),
            duration=signal_data.get('duration', 60),
            message_text=signal_data.get('message_text', '')
        )
        
        # Add to priority queue
        heapq.heappush(self.signal_queue, queued_signal)
        self.stats['total_queued'] += 1
        
        return True
    
    def add_signals_batch(self, signals_list: List[Dict[str, Any]]) -> Tuple[int, int]:
        """
        Add multiple signals to queue
        Returns (added_count, duplicate_count)
        """
        added = 0
        duplicates = 0
        
        for signal_data in signals_list:
            if self.add_signal(signal_data):
                added += 1
            else:
                duplicates += 1
        
        return added, duplicates
    
    def get_ready_signals(self, current_time: datetime) -> List[QueuedSignal]:
        """Get all signals ready for execution at current time"""
        ready_signals = []
        
        # Check signals in queue for readiness
        while self.signal_queue:
            # Peek at the earliest signal
            earliest_signal = self.signal_queue[0]
            
            if earliest_signal.is_expired(current_time, self.expiry_seconds):
                # Remove expired signal
                expired_signal = heapq.heappop(self.signal_queue)
                expired_signal.status = SignalStatus.EXPIRED
                self.stats['total_expired'] += 1
                logger.warning(f"Signal expired: {expired_signal.signal_id}")
                continue
            
            if earliest_signal.is_ready(current_time):
                # Signal is ready for execution
                ready_signal = heapq.heappop(self.signal_queue)
                ready_signal.status = SignalStatus.READY
                ready_signals.append(ready_signal)
            else:
                # No more ready signals (queue is time-ordered)
                break
        
        return ready_signals
    
    def get_upcoming_signals(self, current_time: datetime, limit: int = 10) -> List[Tuple[QueuedSignal, float]]:
        """Get upcoming signals with time until execution"""
        upcoming = []
        
        for signal in sorted(self.signal_queue):
            if len(upcoming) >= limit:
                break
                
            if not signal.is_expired(current_time, self.expiry_seconds):
                time_until = signal.time_until_execution(current_time)
                if time_until > 0:
                    upcoming.append((signal, time_until))
        
        return upcoming
    
    def mark_signal_executing(self, signal: QueuedSignal) -> None:
        """Mark signal as currently executing"""
        signal.status = SignalStatus.EXECUTING
        signal.executed_at = datetime.now()
        self.active_signals[signal.signal_id] = signal
        self.stats['total_executed'] += 1
    
    def mark_signal_completed(self, signal_id: str, result: Dict[str, Any]) -> None:
        """Mark signal as completed with result"""
        if signal_id in self.active_signals:
            signal = self.active_signals.pop(signal_id)
            signal.status = SignalStatus.COMPLETED
            self.completed_signals[signal_id] = signal
            self.stats['total_completed'] += 1
    
    def get_queue_status(self, current_time: datetime) -> Dict[str, Any]:
        """Get comprehensive queue status"""
        # Clean expired signals first
        self.cleanup_expired_signals(current_time)
        
        ready_count = len([s for s in self.signal_queue if s.is_ready(current_time)])
        pending_count = len(self.signal_queue) - ready_count
        
        next_signal = None
        next_time_until = None
        
        if self.signal_queue:
            next_signal = min(self.signal_queue, key=lambda s: s.trade_datetime)
            next_time_until = next_signal.time_until_execution(current_time)
        
        return {
            'queue_size': len(self.signal_queue),
            'ready_count': ready_count,
            'pending_count': pending_count,
            'active_count': len(self.active_signals),
            'completed_count': len(self.completed_signals),
            'next_signal': {
                'asset': next_signal.asset if next_signal else None,
                'direction': next_signal.direction if next_signal else None,
                'time_until': next_time_until,
                'signal_time': next_signal.signal_time if next_signal else None
            } if next_signal else None,
            'stats': self.stats.copy()
        }
    
    def cleanup_expired_signals(self, current_time: datetime) -> int:
        """Remove expired signals from queue"""
        expired_count = 0
        new_queue = []
        
        for signal in self.signal_queue:
            if signal.is_expired(current_time, self.expiry_seconds):
                signal.status = SignalStatus.EXPIRED
                expired_count += 1
                self.stats['total_expired'] += 1
            else:
                new_queue.append(signal)
        
        self.signal_queue = new_queue
        heapq.heapify(self.signal_queue)
        
        return expired_count
    
    def clear_old_completed_signals(self, hours_old: int = 24) -> int:
        """Clear completed signals older than specified hours"""
        cutoff_time = datetime.now() - timedelta(hours=hours_old)
        old_signals = []
        
        for signal_id, signal in list(self.completed_signals.items()):
            if signal.executed_at and signal.executed_at < cutoff_time:
                old_signals.append(signal_id)
        
        for signal_id in old_signals:
            del self.completed_signals[signal_id]
        
        return len(old_signals)
    
    def get_status_display(self, current_time: datetime) -> str:
        """Get formatted status display string"""
        status = self.get_queue_status(current_time)
        
        if status['ready_count'] > 0:
            return f"🚀 {status['ready_count']} READY | {status['pending_count']} pending | {status['active_count']} executing"
        elif status['next_signal']:
            next_sig = status['next_signal']
            time_until = next_sig['time_until']
            if time_until > 0:
                minutes = int(time_until // 60)
                seconds = int(time_until % 60)
                return f"⏰ Next: {next_sig['asset']} {next_sig['direction'].upper()} in {minutes}m{seconds}s | {status['pending_count']} queued"
            else:
                return f"⏰ Next: {next_sig['asset']} {next_sig['direction'].upper()} NOW | {status['pending_count']} queued"
        else:
            return f"📭 Queue empty | {status['completed_count']} completed today"
    
    async def process_ready_signals(self, current_time: datetime, signal_processor) -> List[Tuple[QueuedSignal, Any]]:
        """
        Process all ready signals using the provided signal processor
        Returns list of (signal, result) tuples
        """
        ready_signals = self.get_ready_signals(current_time)
        
        if not ready_signals:
            return []
        
        # Mark all signals as executing
        for signal in ready_signals:
            self.mark_signal_executing(signal)
        
        # Update concurrent execution stats
        self.stats['concurrent_executions'] = max(
            self.stats['concurrent_executions'], 
            len(ready_signals)
        )
        
        # Process signals concurrently if multiple, sequentially if single
        results = []
        
        if len(ready_signals) == 1:
            # Single signal - process normally
            signal = ready_signals[0]
            try:
                result = await signal_processor(signal)
                results.append((signal, result))
                self.mark_signal_completed(signal.signal_id, {'result': result})
            except Exception as e:
                logger.error(f"Error processing signal {signal.signal_id}: {e}")
                results.append((signal, {'error': str(e)}))
                self.mark_signal_completed(signal.signal_id, {'error': str(e)})
        else:
            # Multiple signals - process concurrently
            tasks = []
            for signal in ready_signals:
                task = asyncio.create_task(signal_processor(signal))
                tasks.append((signal, task))
            
            # Wait for all tasks to complete
            for signal, task in tasks:
                try:
                    result = await task
                    results.append((signal, result))
                    self.mark_signal_completed(signal.signal_id, {'result': result})
                except Exception as e:
                    logger.error(f"Error processing signal {signal.signal_id}: {e}")
                    results.append((signal, {'error': str(e)}))
                    self.mark_signal_completed(signal.signal_id, {'error': str(e)})
        
        return results
    
    def print_queue_summary(self, current_time: datetime) -> None:
        """Print detailed queue summary"""
        status = self.get_queue_status(current_time)
        
        print(f"\n📊 SIGNAL QUEUE STATUS:")
        print(f"   🎯 Ready for execution: {status['ready_count']}")
        print(f"   ⏳ Pending in queue: {status['pending_count']}")
        print(f"   🔄 Currently executing: {status['active_count']}")
        print(f"   ✅ Completed today: {status['completed_count']}")
        
        if status['next_signal']:
            next_sig = status['next_signal']
            time_until = next_sig['time_until']
            if time_until and time_until > 0:
                minutes = int(time_until // 60)
                seconds = int(time_until % 60)
                print(f"   ⏰ Next signal: {next_sig['asset']} {next_sig['direction'].upper()} at {next_sig['signal_time']} (in {minutes}m{seconds}s)")
            else:
                print(f"   ⏰ Next signal: {next_sig['asset']} {next_sig['direction'].upper()} at {next_sig['signal_time']} (NOW)")
        
        # Show upcoming signals
        upcoming = self.get_upcoming_signals(current_time, 5)
        if upcoming:
            print(f"   📅 Upcoming signals:")
            for i, (signal, time_until) in enumerate(upcoming[:3]):
                minutes = int(time_until // 60)
                seconds = int(time_until % 60)
                print(f"      {i+1}. {signal.asset} {signal.direction.upper()} at {signal.signal_time} (in {minutes}m{seconds}s)")
            if len(upcoming) > 3:
                print(f"      ... and {len(upcoming) - 3} more")
        
        # Show statistics
        stats = status['stats']
        print(f"   📈 Statistics:")
        print(f"      Total queued: {stats['total_queued']}")
        print(f"      Total executed: {stats['total_executed']}")
        print(f"      Total expired: {stats['total_expired']}")
        print(f"      Max concurrent: {stats['concurrent_executions']}")
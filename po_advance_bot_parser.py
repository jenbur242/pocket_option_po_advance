#!/usr/bin/env python3
"""
PO ADVANCE BOT Signal Parser
Specialized parser for the PO ADVANCE BOT channel format
"""
import re
from datetime import datetime

def parse_po_advance_signal(message_text):
    """Parse PO ADVANCE BOT signal format"""
    if not message_text:
        return None
    
    # Check if it's a signal message
    if 'POCKET PRO AI' not in message_text or 'Pair' not in message_text:
        return None
    
    try:
        # Extract asset/pair
        asset_match = re.search(r'💹 Pair\s*│\s*([A-Z_]+)', message_text)
        asset = asset_match.group(1) if asset_match else None
        
        # Extract entry time
        time_match = re.search(r'⏰ Entry Time\s*│\s*(\d{1,2}:\d{2})', message_text)
        entry_time = time_match.group(1) if time_match else None
        
        # Extract direction
        direction = None
        if 'PUT ➥ DOWN' in message_text or '⬇️' in message_text:
            direction = 'PUT'
        elif 'CALL ➥ UP' in message_text or '⬆️' in message_text:
            direction = 'CALL'
        
        # Extract strategy
        strategy_match = re.search(r'∯ Strategy\s*│\s*([^∯]+)', message_text)
        strategy = strategy_match.group(1).strip() if strategy_match else None
        
        if asset and direction and entry_time:
            return {
                'asset': asset,
                'direction': direction,
                'entry_time': entry_time,
                'strategy': strategy,
                'broker': 'Pocket Option',
                'confidence': 'HIGH' if 'HIGH CONFIDENCE' in message_text else 'NORMAL'
            }
        
        return None
        
    except Exception as e:
        print(f"⚠️ Parse error: {e}")
        return None

def parse_po_advance_result(message_text):
    """Parse PO ADVANCE BOT result format"""
    if not message_text:
        return None
    
    # Check if it's a result message
    if 'RESULTADO FINAL' not in message_text:
        return None
    
    try:
        # Extract result type
        result_type = None
        if 'VICTORY CONFIRMED' in message_text:
            result_type = 'WIN'
        elif 'LOSS CONFIRMED' in message_text:
            result_type = 'LOSS'
        
        # Extract asset/pair
        pair_match = re.search(r'💎 Pair\s*→\s*([A-Z_]+)', message_text)
        asset = pair_match.group(1) if pair_match else None
        
        # Extract time
        time_match = re.search(r'⏳ Time\s*→\s*(\d{1,2}:\d{2})', message_text)
        time = time_match.group(1) if time_match else None
        
        # Extract winrate
        winrate_match = re.search(r'🎯 WINRATE\s*:\s*([\d.]+)%', message_text)
        winrate = float(winrate_match.group(1)) if winrate_match else None
        
        # Extract profit/loss counts
        profit_match = re.search(r'✨ PROFIT\s*:\s*(\d+)', message_text)
        loss_match = re.search(r'⚡ LOSS\s*:\s*(\d+)', message_text)
        
        profit_count = int(profit_match.group(1)) if profit_match else None
        loss_count = int(loss_match.group(1)) if loss_match else None
        
        if asset and result_type and time:
            return {
                'asset': asset,
                'result': result_type,
                'time': time,
                'winrate': winrate,
                'profit_count': profit_count,
                'loss_count': loss_count
            }
        
        return None
        
    except Exception as e:
        print(f"⚠️ Result parse error: {e}")
        return None

# Test with the actual messages from the channel
test_messages = [
    # Signal message
    """⁠
`𓂀𓂀𓂀 POCKET PRO AI  𓂀𓂀𓂀
🏦 Broker        │ Pocket Option
💹 Pair          │ AUDCAD_otc
⏰ Entry Time    │ 17:03 (Server Time)
🎯 Direction     │ PUT ➥ DOWN ⬇️⬇️⬇️
∯ Strategy       │ NXP Elite Protocol ∯
⚠️  Rule         │ SKIP if payout; 80%
🔥 HIGH CONFIDENCE SIGNAL 🔥
Execute with confidence!`""",
    
    # Result message
    """✦✦✦ RESULTADO FINAL ✦✦✦
VICTORY CONFIRMED ✅
💎 Pair      → QARCNY_otc
⏳ Time      → 16:53
👑 Outcome   → PROFIT SECURED 💰🔥
▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃
✨ PROFIT    : 8
⚡ LOSS      : 2
🎯 WINRATE   : 80.0% 🔥
▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃"""
]

print("🤖 PO ADVANCE BOT SIGNAL PARSER TEST")
print("=" * 50)

for i, message in enumerate(test_messages, 1):
    print(f"\nTest {i}:")
    print(f"Message: {message[:100]}...")
    
    # Try parsing as signal
    signal = parse_po_advance_signal(message)
    if signal:
        print("🎯 SIGNAL DETECTED:")
        for key, value in signal.items():
            print(f"   {key}: {value}")
    
    # Try parsing as result
    result = parse_po_advance_result(message)
    if result:
        print("📊 RESULT DETECTED:")
        for key, value in result.items():
            print(f"   {key}: {value}")
    
    if not signal and not result:
        print("❌ No signal or result detected")
#!/usr/bin/env python3
"""
Debug the cycle logic issue in 3-step trading
"""

def add_debug_logging():
    """Add debug logging to track cycle state changes"""
    
    # Read the file
    with open('app.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add debug logging to get_asset_cycle method
    old_get_cycle = '''    def get_asset_cycle(self, asset: str) -> int:
        """Get current cycle for specific asset - uses global cycle state for new assets"""
        if asset not in self.asset_strategies:
            # New asset starts at current global cycle and step
            self.asset_strategies[asset] = {
                'cycle': self.global_cycle, 
                'step': self.global_step, 
                'amounts': []
            }
        return self.asset_strategies[asset]['cycle']'''
    
    new_get_cycle = '''    def get_asset_cycle(self, asset: str) -> int:
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
        return self.asset_strategies[asset]['cycle']'''
    
    content = content.replace(old_get_cycle, new_get_cycle)
    
    # Add debug logging to record_result method
    old_record_win = '''            print(f"✅ {asset} WIN at C{cycle}S{step}! Resetting global state to C1S1")
            # WIN resets GLOBAL state to C1S1 - all future assets start at C1S1
            self.global_cycle = 1
            self.global_step = 1'''
    
    new_record_win = '''            print(f"✅ {asset} WIN at C{cycle}S{step}! Resetting global state to C1S1")
            print(f"🔍 DEBUG: Before reset - Global: C{self.global_cycle}S{self.global_step}")
            # WIN resets GLOBAL state to C1S1 - all future assets start at C1S1
            self.global_cycle = 1
            self.global_step = 1
            print(f"🔍 DEBUG: After reset - Global: C{self.global_cycle}S{self.global_step}")'''
    
    content = content.replace(old_record_win, new_record_win)
    
    # Write the updated content back
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Added debug logging to track cycle state changes")
    print("📊 Debug messages will show:")
    print("   🔍 When new assets are created and their starting cycle")
    print("   🔍 When existing assets are accessed and their current state")
    print("   🔍 Global state before and after wins")
    print("\n💡 Run the trading app and watch for DEBUG messages to identify the issue")

if __name__ == "__main__":
    add_debug_logging()
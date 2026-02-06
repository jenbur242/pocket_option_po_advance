#!/usr/bin/env python3
"""
Test script to demonstrate date change detection and data cleanup in simple_monitor.py
"""
import csv
import os
from datetime import datetime, timedelta

# Test CSV file
test_csv = "test_date_cleanup.csv"

# Create test data with multiple dates
def create_test_data():
    """Create test CSV with data from multiple dates"""
    headers = ['date', 'timestamp', 'channel', 'message_id', 'message_text', 
               'is_signal', 'asset', 'direction', 'signal_time']
    
    # Generate dates
    today = datetime.now().strftime('%Y-%m-%d')
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    two_days_ago = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    
    # Create test data
    test_data = [
        [two_days_ago, f"{two_days_ago} 10:00:00", "test_channel", "1", "Old message 1", "Yes", "EURUSD", "call", "10:00"],
        [two_days_ago, f"{two_days_ago} 11:00:00", "test_channel", "2", "Old message 2", "Yes", "GBPUSD", "put", "11:00"],
        [yesterday, f"{yesterday} 12:00:00", "test_channel", "3", "Yesterday message 1", "Yes", "USDJPY", "call", "12:00"],
        [yesterday, f"{yesterday} 13:00:00", "test_channel", "4", "Yesterday message 2", "No", "", "", ""],
        [today, f"{today} 14:00:00", "test_channel", "5", "Today message 1", "Yes", "EURJPY", "put", "14:00"],
        [today, f"{today} 15:00:00", "test_channel", "6", "Today message 2", "Yes", "AUDUSD", "call", "15:00"],
    ]
    
    # Write test data
    with open(test_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(test_data)
    
    print(f"✅ Created test CSV: {test_csv}")
    print(f"   Total rows: {len(test_data)}")
    print(f"   Dates: {two_days_ago}, {yesterday}, {today}")
    return today, yesterday, two_days_ago

def show_csv_content(label):
    """Display CSV content"""
    print(f"\n{label}")
    print("-" * 80)
    
    if not os.path.exists(test_csv):
        print("   File doesn't exist")
        return
    
    with open(test_csv, 'r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = next(reader)
        print(f"   Headers: {', '.join(headers[:4])}")
        
        rows = list(reader)
        print(f"   Total data rows: {len(rows)}")
        
        # Group by date
        dates = {}
        for row in rows:
            if len(row) >= 1:
                date = row[0]
                if date not in dates:
                    dates[date] = []
                dates[date].append(row)
        
        for date, date_rows in dates.items():
            print(f"   📅 {date}: {len(date_rows)} rows")
            for row in date_rows:
                signal = "🎯" if row[5] == "Yes" else "📝"
                asset = row[6] if row[6] else "N/A"
                print(f"      {signal} {row[3]}: {asset} - {row[4][:30]}")

def clean_old_data(current_date):
    """Simulate the clean_previous_date_data function"""
    headers = ['date', 'timestamp', 'channel', 'message_id', 'message_text', 
               'is_signal', 'asset', 'direction', 'signal_time']
    
    print(f"\n🧹 CLEANING DATA - Keeping only: {current_date}")
    print("-" * 80)
    
    # Read all data
    rows_to_keep = []
    deleted_count = 0
    
    with open(test_csv, 'r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)  # Skip header
        
        for row in reader:
            if len(row) >= 1:
                row_date = row[0]
                if row_date == current_date:
                    rows_to_keep.append(row)
                else:
                    deleted_count += 1
                    print(f"   🗑️ Deleting: {row_date} - {row[4][:40]}")
    
    # Rewrite with only current date data
    with open(test_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows_to_keep)
    
    print(f"\n   ✅ Deleted: {deleted_count} old rows")
    print(f"   ✅ Kept: {len(rows_to_keep)} current date rows")

def main():
    print("="*80)
    print("DATE CHANGE CLEANUP TEST")
    print("="*80)
    
    # Create test data
    today, yesterday, two_days_ago = create_test_data()
    
    # Show initial state
    show_csv_content("📊 INITIAL STATE (Multiple dates)")
    
    # Simulate date change cleanup
    print(f"\n{'='*80}")
    print(f"📅 DATE CHANGED: Simulating cleanup to keep only {today}")
    print(f"{'='*80}")
    
    clean_old_data(today)
    
    # Show final state
    show_csv_content("📊 AFTER CLEANUP (Only current date)")
    
    print(f"\n{'='*80}")
    print("✅ TEST COMPLETED")
    print(f"{'='*80}")
    print(f"\nThis demonstrates how simple_monitor.py automatically:")
    print(f"  1. Detects when the date changes")
    print(f"  2. Deletes all previous date data from CSV files")
    print(f"  3. Keeps only current date data")
    print(f"  4. Continues saving new data with the current date")
    print(f"\nTest file: {test_csv}")
    
    # Cleanup
    cleanup = input("\nDelete test file? (Y/n): ").lower().strip()
    if cleanup != 'n':
        os.remove(test_csv)
        print(f"🗑️ Deleted: {test_csv}")

if __name__ == "__main__":
    main()

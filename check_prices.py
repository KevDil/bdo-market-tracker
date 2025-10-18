"""
Price Validation Script - Check all transactions for plausibility
Usage: python check_prices.py
"""
from database import get_connection
from utils import check_price_plausibility

def check_all_prices():
    """Check all transactions in database for price plausibility."""
    conn = get_connection()
    c = conn.cursor()
    
    # Get all transactions with prices
    c.execute('''
        SELECT id, item_name, quantity, price, transaction_type, timestamp 
        FROM transactions 
        WHERE price > 0 
        ORDER BY timestamp DESC
    ''')
    
    rows = c.fetchall()
    print(f"\n{'='*80}")
    print(f"Checking {len(rows)} transactions for price plausibility...")
    print(f"{'='*80}\n")
    
    suspicious = []
    total = 0
    
    for row in rows:
        tx_id, item_name, quantity, price, tx_type, timestamp = row
        total += 1
        
        try:
            result = check_price_plausibility(item_name, quantity, price, tx_side=tx_type)
            
            if not result['plausible']:
                unit_price = result['unit_price']
                reason = result.get('reason', 'unknown')
                expected_min = result.get('expected_min')
                expected_max = result.get('expected_max')
                
                suspicious.append({
                    'id': tx_id,
                    'item': item_name,
                    'qty': quantity,
                    'price': price,
                    'unit': unit_price,
                    'type': tx_type,
                    'timestamp': timestamp,
                    'reason': reason,
                    'expected_min': expected_min,
                    'expected_max': expected_max
                })
                
                print(f"⚠️  SUSPICIOUS PRICE DETECTED:")
                print(f"   ID:        {tx_id}")
                print(f"   Item:      {item_name}")
                print(f"   Quantity:  {quantity}")
                print(f"   Price:     {price:,} ({unit_price:,.0f} per unit)")
                print(f"   Type:      {tx_type}")
                print(f"   Timestamp: {timestamp}")
                print(f"   Reason:    {reason}")
                if expected_min:
                    print(f"   Expected:  {expected_min:,} - {expected_max:,}")
                print()
        
        except Exception as e:
            # API check failed or no market data available
            pass
    
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    print(f"Total transactions checked: {total}")
    print(f"Suspicious prices found:    {len(suspicious)}")
    print(f"{'='*80}\n")
    
    if suspicious:
        print("⚠️  ACTION REQUIRED:")
        print("The following transactions have suspicious prices and may need correction:\n")
        
        for s in suspicious:
            deviation = ""
            if s['reason'] == 'too_low' and s['expected_min']:
                pct = (s['price'] / s['expected_min']) * 100
                deviation = f"({pct:.1f}% of expected minimum)"
            elif s['reason'] == 'too_high' and s['expected_max']:
                pct = (s['price'] / s['expected_max']) * 100
                deviation = f"({pct:.1f}% of expected maximum)"
            
            print(f"   [{s['id']}] {s['item']} x{s['qty']} @ {s['price']:,} - {s['reason']} {deviation}")
        
        print("\nTo fix a price manually, use:")
        print("   python fix_price.py")
        print("   OR edit the database directly using SQL UPDATE statement")
    else:
        print("✅ All prices look plausible! No corrections needed.")
    
    print()

if __name__ == "__main__":
    check_all_prices()

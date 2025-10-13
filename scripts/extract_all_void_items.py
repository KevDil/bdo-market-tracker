#!/usr/bin/env python3
import json
import sys
from pathlib import Path

# Path to market.json
market_json_path = Path(__file__).parent.parent / "config" / "market.json"

print(f"Loading {market_json_path}...")

try:
    with open(market_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    print("✅ Loaded market.json")
    print(f"Type: {type(data)}")
    print(f"Top-level keys: {list(data.keys())}")
    
    # Access items dict
    if 'items' in data:
        items = data['items']
        print(f"Total items: {len(items)}")
        
        # Search for void-related items
        void_items = []
        for item_id, item_data in items.items():
            if 'name' in item_data and 'void' in item_data['name'].lower():
                void_items.append((item_id, item_data))
        
        print(f"\n🔍 Found {len(void_items)} Void-related items:")
        for item_id, item_data in void_items:
            print(f"\n  Item ID: {item_id}")
            print(f"  Name: {item_data['name']}")
            price = item_data.get('price')
            stock = item_data.get('stock')
            grade = item_data.get('grade')
            main_cat = item_data.get('main_category')
            sub_cat = item_data.get('sub_category')
            
            if price is not None:
                print(f"  Price: {price:,}")
            if stock is not None:
                print(f"  Stock: {stock}")
            if grade is not None:
                print(f"  Grade: {grade}")
            if main_cat is not None and sub_cat is not None:
                print(f"  Category: {main_cat}/{sub_cat}")
    else:
        print("❌ No 'items' key found in market.json")

except FileNotFoundError:
    print(f"❌ File not found: {market_json_path}")
    sys.exit(1)
except json.JSONDecodeError as e:
    print(f"❌ JSON decode error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)

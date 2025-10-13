#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Extract Gem of Void and Crystal of Void entries from market.json"""

import json
import sys

def extract_void_items():
    """Parse market.json and extract all void-related items"""
    
    try:
        # Load market.json
        with open('c:/Users/kdill/Desktop/market_tracker/config/market.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"✅ Loaded market.json")
        print(f"Type: {type(data)}")
        
        # Check structure
        if isinstance(data, dict):
            print(f"Total entries: {len(data)}")
            
            # Find all void-related items
            void_items = []
            for item_id, item_data in data.items():
                if isinstance(item_data, dict) and 'name' in item_data:
                    name = item_data.get('name', '')
                    if 'Void' in name or 'void' in name:
                        # Extract price and stock from first sub_item
                        sub_items = item_data.get('sub_items', [])
                        price = sub_items[0].get('price') if sub_items else None
                        stock = sub_items[0].get('stock') if sub_items else None
                        
                        void_items.append({
                            'id': item_id,
                            'name': name,
                            'backup_name': item_data.get('backup_name', ''),
                            'price': price,
                            'stock': stock,
                            'grade': item_data.get('grade'),
                            'main_category': item_data.get('main_category'),
                            'sub_category': item_data.get('sub_category')
                        })
            
            # Display results
            print(f"\n🔍 Found {len(void_items)} Void-related items:\n")
            
            for item in void_items:
                print(f"ID: {item['id']}")
                print(f"  Name: {item['name']}")
                print(f"  Price: {item['price']:,} Silver" if item['price'] else "  Price: N/A")
                print(f"  Stock: {item['stock']}" if item['stock'] is not None else "  Stock: N/A")
                print(f"  Grade: {item['grade']} (0=white, 1=green, 2=blue, 3=yellow, 4=orange)")
                print(f"  Category: {item['main_category']}/{item['sub_category']}")
                print()
            
            # Check if "Gem of Void" is present
            gem_of_void = [item for item in void_items if item['name'] == 'Gem of Void']
            if gem_of_void:
                print("\n✅ 'Gem of Void' IS in market.json!")
                print(f"   ID: {gem_of_void[0]['id']}")
                print(f"   Current Price: {gem_of_void[0]['price']:,} Silver")
                print(f"   Stock: {gem_of_void[0]['stock']} units")
            else:
                print("\n❌ 'Gem of Void' NOT FOUND in market.json")
                
        else:
            print(f"❌ Unexpected data structure: {type(data)}")
            print(f"First few items: {str(data)[:500]}")
            
    except FileNotFoundError:
        print("❌ market.json not found!")
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    extract_void_items()

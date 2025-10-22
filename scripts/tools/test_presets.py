"""
Test script for Item Presets functionality
Tests CRUD operations and data retrieval
"""

from database import (
    get_all_presets,
    get_preset_by_name,
    save_preset,
    delete_preset,
)

def test_presets():
    print("=" * 60)
    print("Testing Item Presets Functionality")
    print("=" * 60)
    
    # Test 1: Get all presets
    print("\n1. Getting all presets...")
    presets = get_all_presets()
    print(f"   Found {len(presets)} preset(s)")
    for preset in presets:
        print(f"   - {preset['name']}: {len(preset['items'])} items")
    
    # Test 2: Get specific preset
    print("\n2. Getting 'Harmony Draught' preset...")
    harmony = get_preset_by_name("Harmony Draught")
    if harmony:
        print(f"   ✓ Found preset with {len(harmony['items'])} items")
        print(f"   Sample items: {', '.join(harmony['items'][:5])}...")
    else:
        print("   ✗ Preset not found")
    
    # Test 3: Create a test preset
    print("\n3. Creating test preset...")
    test_items = [
        "Black Stone Powder",
        "Pure Powder Reagent",
        "Clear Liquid Reagent",
        "Purified Water"
    ]
    success = save_preset("Test Materials", test_items)
    if success:
        print(f"   ✓ Created 'Test Materials' with {len(test_items)} items")
    else:
        print("   ✗ Failed to create preset")
    
    # Test 4: Verify creation
    print("\n4. Verifying test preset...")
    test_preset = get_preset_by_name("Test Materials")
    if test_preset:
        print(f"   ✓ Test preset exists with {len(test_preset['items'])} items")
        print(f"   Items: {', '.join(test_preset['items'])}")
    else:
        print("   ✗ Test preset not found")
    
    # Test 5: Update preset
    print("\n5. Updating test preset...")
    updated_items = test_items + ["Monk's Branch", "Silver Azalea"]
    success = save_preset("Test Materials", updated_items)
    if success:
        print(f"   ✓ Updated preset to {len(updated_items)} items")
        test_preset = get_preset_by_name("Test Materials")
        print(f"   Verified: {len(test_preset['items'])} items in DB")
    else:
        print("   ✗ Failed to update preset")
    
    # Test 6: Delete test preset
    print("\n6. Cleaning up test preset...")
    success = delete_preset("Test Materials")
    if success:
        print("   ✓ Test preset deleted")
    else:
        print("   ✗ Failed to delete test preset")
    
    # Test 7: Verify deletion
    print("\n7. Verifying deletion...")
    test_preset = get_preset_by_name("Test Materials")
    if test_preset is None:
        print("   ✓ Test preset successfully removed")
    else:
        print("   ✗ Test preset still exists")
    
    # Final summary
    print("\n" + "=" * 60)
    print("Final State:")
    presets = get_all_presets()
    print(f"Total presets: {len(presets)}")
    for preset in presets:
        print(f"  - {preset['name']}: {len(preset['items'])} items")
    print("=" * 60)

if __name__ == "__main__":
    test_presets()

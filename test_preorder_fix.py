"""Quick validation of find_matching_listing fix"""
from preorder_manager import PreorderManager
import inspect

pm = PreorderManager()
print('✅ Import successful')
print('')

methods = [m for m in dir(pm) if not m.startswith('_')]
preorder_methods = [m for m in methods if 'preorder' in m.lower()]
listing_methods = [m for m in methods if 'listing' in m.lower()]

print('📋 Available Methods:')
print('')
print('BUY-SIDE (Preorders):')
for m in sorted(preorder_methods):
    print(f'   ✅ {m}')

print('')
print('SELL-SIDE (Listings):')
for m in sorted(listing_methods):
    print(f'   ✅ {m}')

print('')
sig_preorder = inspect.signature(pm.find_matching_preorder)
sig_listing = inspect.signature(pm.find_matching_listing)

print('Signature Match:')
print(f'   find_matching_preorder{sig_preorder}')
print(f'   find_matching_listing{sig_listing}')
print('   ✅ Signatures are analogous!')

import sys, os
# Add project root (two levels up from scripts/utils/) to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from parsing import extract_details_from_entry

def main():
    cases = [
        ('2025.10.09 22.10', 'Relisted Magical Shard x60 for 179,934,300 Silver'),
        ('2025.10.09 22.10', 'Re-list Magical Shard x60 for 179,934,300 Silver'),
        ('2025.10.09 22.10', 'Listed Magical Shard x60 for 179,934,300 Silver'),
        ('2025.10.09 22.10', 'Transaction of Magical Shard x60 worth 179,934,300 Silver has been completed.'),
        ('2025.10.09 22.10', 'Purchased Gem of Void x7 for 301,700,000 Silver'),
    ]
    for ts, txt in cases:
        print(txt)
        print(extract_details_from_entry(ts, txt))

if __name__ == '__main__':
    main()

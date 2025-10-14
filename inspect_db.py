import sqlite3

conn = sqlite3.connect('bdo_tracker.db')
c = conn.cursor()

# List all tables
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()

print("Tables in bdo_tracker.db:")
for table in tables:
    print(f"  - {table[0]}")

# Get schema for each table
for table in tables:
    table_name = table[0]
    print(f"\n{'='*80}")
    print(f"Schema for {table_name}:")
    print('='*80)
    c.execute(f"PRAGMA table_info({table_name})")
    for col in c.fetchall():
        print(f"  {col[1]:20} {col[2]:15} {'NOT NULL' if col[3] else ''}")
    
    # Show sample data
    print(f"\nSample data from {table_name} (last 5 rows):")
    try:
        c.execute(f"SELECT * FROM {table_name} ORDER BY rowid DESC LIMIT 5")
        rows = c.fetchall()
        if rows:
            # Get column names
            c.execute(f"PRAGMA table_info({table_name})")
            cols = [col[1] for col in c.fetchall()]
            print(f"  Columns: {', '.join(cols)}")
            for row in rows:
                print(f"  {row}")
        else:
            print("  (empty)")
    except Exception as e:
        print(f"  Error: {e}")

conn.close()

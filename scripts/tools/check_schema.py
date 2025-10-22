import sqlite3

conn = sqlite3.connect('bdo_tracker.db')
c = conn.cursor()

print("=" * 80)
print("DATABASE SCHEMA:")
print("=" * 80)

c.execute("PRAGMA table_info(transactions)")
columns = c.fetchall()

print("\nColumns in 'transactions' table:")
for col in columns:
    cid, name, type_, notnull, default, pk = col
    nullable = "NOT NULL" if notnull else "NULL"
    pk_marker = "PRIMARY KEY" if pk else ""
    default_val = f"DEFAULT {default}" if default else ""
    print(f"  {name:20} {type_:15} {nullable:10} {default_val:20} {pk_marker}")

# Check if content_hash column exists
has_content_hash = any(col[1] == 'content_hash' for col in columns)
print(f"\n✓ content_hash column exists: {has_content_hash}")

if not has_content_hash:
    print("\n⚠️ PROBLEM: content_hash column is missing!")
    print("   The dedupe logic expects this column but it doesn't exist in the database.")
    print("   Solution: Run a migration to add the column.")

conn.close()

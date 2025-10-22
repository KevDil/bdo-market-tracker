"""
Benchmark: Parsing & Database Performance
Tests parsing cache, item-name cache, and DB batch-insert optimizations.
"""

import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from parsing import split_text_into_log_entries, extract_details_from_entry
from market_json_manager import correct_item_name
from database import get_connection, get_cursor
import datetime


# Test data: Realistic OCR text from BDO market
TEST_TEXTS = [
    # Scenario 1: Single transaction (repeated)
    """10:23
Transaction of Sharp Black Crystal Shard x513 worth 4,688,420 Silver
Orders 1 Orders Completed 0 Collect Re-list""",
    
    # Scenario 2: Multiple transactions
    """14:45
Purchased Caphras Stone x100 for 2,450,000 Silver
Purchased Pure Powder of Darkness x50 for 1,225,000 Silver
Listed Black Magic Crystal - Precision x1 for 850,000 Silver""",
    
    # Scenario 3: Complex with relists
    """16:30
Transaction of Magical Shard x1 worth 425,000 Silver
Re-listed Monk's Branch x3 for 1,500,000 Silver
Withdrew order of Ancient Magic Crystal - Carmae x1 for 125,000,000 Silver""",
    
    # Scenario 4: Sold items
    """18:15
Sold Black Distortion Earring x1 for 95,000,000 Silver
Sold Caphras Stone x25 for 612,500 Silver""",
]

# Test items for item-name correction (with typos)
TEST_ITEMS = [
    "Sharp Black Crystal Shard",
    "Sharp Black Crysta1 Shard",  # OCR error: 1 instead of l
    "Caphras Stone",
    "Caphras St0ne",  # OCR error: 0 instead of o
    "Pure Powder of Darkness",
    "Pure Powder of Darknes",  # Missing s
    "Black Magic Crystal - Precision",
    "Black Magic Crysta1 - Precision",
    "Magical Shard",
    "Magica1 Shard",
]


def benchmark_parsing(iterations: int = 100):
    """Benchmark parsing performance (BEFORE optimization)"""
    print("=" * 80)
    print("📝 PARSING BENCHMARK (split_text_into_log_entries)")
    print("=" * 80)
    
    times = []
    for i in range(iterations):
        # Use different text each iteration to avoid unintended caching
        text = TEST_TEXTS[i % len(TEST_TEXTS)]
        
        start = time.perf_counter()
        entries = split_text_into_log_entries(text)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    
    avg = sum(times) / len(times)
    p50 = sorted(times)[len(times) // 2]
    p95 = sorted(times)[int(len(times) * 0.95)]
    
    print(f"Iterations: {iterations}")
    print(f"Average: {avg:.3f}ms")
    print(f"p50: {p50:.3f}ms")
    print(f"p95: {p95:.3f}ms")
    print()
    return avg


def benchmark_item_correction(iterations: int = 1000):
    """Benchmark item-name correction (RapidFuzz)"""
    print("=" * 80)
    print("🔧 ITEM-NAME CORRECTION BENCHMARK (correct_item_name)")
    print("=" * 80)
    
    times = []
    for i in range(iterations):
        item = TEST_ITEMS[i % len(TEST_ITEMS)]
        
        start = time.perf_counter()
        corrected, is_valid = correct_item_name(item)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    
    avg = sum(times) / len(times)
    p50 = sorted(times)[len(times) // 2]
    p95 = sorted(times)[int(len(times) * 0.95)]
    
    print(f"Iterations: {iterations}")
    print(f"Average: {avg:.3f}ms")
    print(f"p50: {p50:.3f}ms")
    print(f"p95: {p95:.3f}ms")
    print()
    return avg


def benchmark_db_single_inserts(iterations: int = 50):
    """Benchmark single DB inserts (BEFORE batch optimization)"""
    print("=" * 80)
    print("💾 DATABASE SINGLE-INSERT BENCHMARK (current implementation)")
    print("=" * 80)
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Create temp table for testing
    cur.execute("DROP TABLE IF EXISTS test_transactions")
    cur.execute("""
        CREATE TABLE test_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT,
            quantity INTEGER,
            price REAL,
            transaction_type TEXT,
            timestamp DATETIME,
            tx_case TEXT,
            occurrence_index INTEGER DEFAULT 0,
            content_hash TEXT
        )
    """)
    conn.commit()
    
    times = []
    for i in range(iterations):
        start = time.perf_counter()
        
        # Simulate single transaction insert
        cur.execute("""
            INSERT OR IGNORE INTO test_transactions 
            (item_name, quantity, price, transaction_type, timestamp, tx_case, occurrence_index, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f"Test Item {i}",
            10,
            100000,
            "buy",
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "buy_collect",
            0,
            f"hash_{i}"
        ))
        conn.commit()
        
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    
    avg = sum(times) / len(times)
    p50 = sorted(times)[len(times) // 2]
    p95 = sorted(times)[int(len(times) * 0.95)]
    
    print(f"Iterations: {iterations}")
    print(f"Average: {avg:.3f}ms per insert")
    print(f"p50: {p50:.3f}ms")
    print(f"p95: {p95:.3f}ms")
    print()
    
    # Cleanup
    cur.execute("DROP TABLE test_transactions")
    conn.commit()
    
    return avg


def benchmark_db_batch_inserts(iterations: int = 50):
    """Benchmark batch DB inserts (AFTER optimization)"""
    print("=" * 80)
    print("⚡ DATABASE BATCH-INSERT BENCHMARK (optimized)")
    print("=" * 80)
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Create temp table for testing
    cur.execute("DROP TABLE IF EXISTS test_transactions_batch")
    cur.execute("""
        CREATE TABLE test_transactions_batch (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT,
            quantity INTEGER,
            price REAL,
            transaction_type TEXT,
            timestamp DATETIME,
            tx_case TEXT,
            occurrence_index INTEGER DEFAULT 0,
            content_hash TEXT
        )
    """)
    conn.commit()
    
    # Test with batches of 5 items (realistic scenario)
    batch_sizes = [1, 5, 10]
    results = {}
    
    for batch_size in batch_sizes:
        times = []
        for i in range(iterations // batch_size):
            # Prepare batch
            batch = [
                (
                    f"Test Item {i * batch_size + j}",
                    10,
                    100000,
                    "buy",
                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "buy_collect",
                    0,
                    f"hash_{i * batch_size + j}"
                )
                for j in range(batch_size)
            ]
            
            start = time.perf_counter()
            cur.executemany("""
                INSERT OR IGNORE INTO test_transactions_batch 
                (item_name, quantity, price, transaction_type, timestamp, tx_case, occurrence_index, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, batch)
            conn.commit()
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed / batch_size)  # Per-item time
        
        avg = sum(times) / len(times)
        results[batch_size] = avg
        print(f"Batch size {batch_size}: {avg:.3f}ms per item")
    
    print()
    
    # Cleanup
    cur.execute("DROP TABLE test_transactions_batch")
    conn.commit()
    
    return results


def main():
    print("\n" + "=" * 80)
    print("🚀 BDO Market Tracker - Parsing & Database Performance Benchmark")
    print("=" * 80)
    print()
    
    # Baseline measurements
    parsing_avg = benchmark_parsing(iterations=100)
    item_correction_avg = benchmark_item_correction(iterations=1000)
    db_single_avg = benchmark_db_single_inserts(iterations=50)
    db_batch_results = benchmark_db_batch_inserts(iterations=50)
    
    # Summary
    print("=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print()
    print(f"Parsing (split_text_into_log_entries): {parsing_avg:.3f}ms")
    print(f"Item-Name Correction (correct_item_name): {item_correction_avg:.3f}ms")
    print(f"Database Single-Insert: {db_single_avg:.3f}ms per transaction")
    print()
    print("Database Batch-Insert (per item):")
    for batch_size, avg in db_batch_results.items():
        speedup = db_single_avg / avg
        print(f"  Batch size {batch_size}: {avg:.3f}ms ({speedup:.1f}x faster)")
    print()
    
    # Optimization potential
    print("=" * 80)
    print("💡 OPTIMIZATION POTENTIAL")
    print("=" * 80)
    print()
    print("1. Parsing Cache:")
    print(f"   - Current: {parsing_avg:.3f}ms per parse")
    print(f"   - With cache (90% hit rate): ~{parsing_avg * 0.1:.3f}ms avg")
    print(f"   - Speedup: ~{10:.1f}x on repeated text")
    print()
    print("2. Item-Name Cache:")
    print(f"   - Current: {item_correction_avg:.3f}ms per correction")
    print(f"   - With LRU cache (80% hit rate): ~{item_correction_avg * 0.2:.3f}ms avg")
    print(f"   - Speedup: ~{5:.1f}x on repeated items")
    print()
    print("3. Database Batch-Insert:")
    if 5 in db_batch_results:
        batch_5_speedup = db_single_avg / db_batch_results[5]
        print(f"   - Current (single): {db_single_avg:.3f}ms per item")
        print(f"   - Batch size 5: {db_batch_results[5]:.3f}ms per item")
        print(f"   - Speedup: {batch_5_speedup:.1f}x on multi-item scans")
    print()


if __name__ == "__main__":
    main()

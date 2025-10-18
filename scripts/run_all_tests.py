"""
Basic Test Runner - Führt alle Test-Skripte in scripts/ aus

Quick Win: Einfacher Test-Runner ohne externe Dependencies
Gibt Übersicht über erfolgreiche/fehlgeschlagene Tests
"""

import subprocess
import sys
import os
import time
from pathlib import Path

# Fix Unicode encoding on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def run_all_tests():
    """Führe alle test_*.py Skripte aus und sammle Ergebnisse"""
    
    # Finde alle Test-Skripte
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    unit_dir = project_root / "tests" / "unit"

    test_files = []
    if unit_dir.exists():
        test_files.extend(sorted(str(path.relative_to(project_root)) for path in unit_dir.glob("test_*.py")))

    if not test_files:
        print("❌ Keine Test-Dateien gefunden!")
        return 1
    
    if not test_files:
        print("❌ Keine Test-Dateien gefunden!")
        return 1
    
    print(f"🧪 Gefunden: {len(test_files)} Test-Skripte\n")
    print("=" * 80)
    
    results = []
    total_time = 0
    
    for test_file in test_files:
        test_path = project_root / test_file
        test_name = Path(test_file).stem
        
        print(f"\n▶️  Führe aus: {test_name}")
        print("-" * 80)
        
        start_time = time.time()
        
        try:
            # Führe Test aus und capture Output
            # Fix Unicode encoding on Windows
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            
            result = subprocess.run(
                [sys.executable, str(test_path)],
                cwd=project_root,  # Run from project root
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=30,  # 30 Sekunden Timeout pro Test
                env=env
            )
            
            elapsed = time.time() - start_time
            total_time += elapsed
            
            # Prüfe Exit-Code
            if result.returncode == 0:
                status = "✅ PASS"
                color = "\033[92m"  # Green
            else:
                status = "❌ FAIL"
                color = "\033[91m"  # Red
            
            reset_color = "\033[0m"
            
            # Zeige Output (letzte 20 Zeilen bei langen Outputs)
            output_lines = result.stdout.split('\n')
            if len(output_lines) > 20:
                print('\n'.join(output_lines[-20:]))
            else:
                print(result.stdout)
            
            if result.stderr:
                print("STDERR:", result.stderr)
            
            print(f"\n{color}{status}{reset_color} - {test_name} ({elapsed:.2f}s)")
            
            results.append({
                'name': test_name,
                'status': 'PASS' if result.returncode == 0 else 'FAIL',
                'time': elapsed,
                'returncode': result.returncode
            })
            
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            total_time += elapsed
            print(f"\n⏱️  TIMEOUT - {test_name} ({elapsed:.2f}s)")
            results.append({
                'name': test_name,
                'status': 'TIMEOUT',
                'time': elapsed,
                'returncode': -1
            })
        except Exception as e:
            elapsed = time.time() - start_time
            total_time += elapsed
            print(f"\n💥 ERROR - {test_name}: {e}")
            results.append({
                'name': test_name,
                'status': 'ERROR',
                'time': elapsed,
                'returncode': -1
            })
    
    # Zusammenfassung
    print("\n" + "=" * 80)
    print("📊 ZUSAMMENFASSUNG")
    print("=" * 80)
    
    passed = sum(1 for r in results if r['status'] == 'PASS')
    failed = sum(1 for r in results if r['status'] == 'FAIL')
    timeout = sum(1 for r in results if r['status'] == 'TIMEOUT')
    errors = sum(1 for r in results if r['status'] == 'ERROR')
    
    print(f"\n✅ Passed:  {passed}/{len(results)}")
    print(f"❌ Failed:  {failed}/{len(results)}")
    if timeout > 0:
        print(f"⏱️  Timeout: {timeout}/{len(results)}")
    if errors > 0:
        print(f"💥 Errors:  {errors}/{len(results)}")
    
    print(f"\n⏱️  Gesamtzeit: {total_time:.2f}s")
    
    # Detaillierte Ergebnisse
    if failed > 0 or timeout > 0 or errors > 0:
        print("\n" + "-" * 80)
        print("Fehlgeschlagene Tests:")
        print("-" * 80)
        for r in results:
            if r['status'] != 'PASS':
                print(f"  {r['status']:8} {r['name']} ({r['time']:.2f}s)")
    
    print("\n" + "=" * 80)
    
    # Return exit code basierend auf Ergebnissen
    if passed == len(results):
        print("🎉 Alle Tests erfolgreich!")
        return 0
    else:
        print(f"⚠️  {failed + timeout + errors} Test(s) fehlgeschlagen!")
        return 1

if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)

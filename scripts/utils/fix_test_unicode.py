"""
Automatischer Unicode-Fix für alle Test-Dateien

Fügt 'from test_utils import fix_windows_unicode' zu allen test_*.py hinzu
"""

import os
import re
from pathlib import Path

def fix_test_file(filepath):
    """Füge Unicode-Fix zu einer Test-Datei hinzu"""
    
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Check ob fix bereits vorhanden
    if 'test_utils' in content or 'fix_windows_unicode' in content:
        return False, "Already fixed"
    
    # Finde die erste import-Zeile nach dem docstring
    lines = content.split('\n')
    insert_pos = None
    in_docstring = False
    docstring_char = None
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Track docstrings
        if stripped.startswith('"""') or stripped.startswith("'''"):
            if not in_docstring:
                in_docstring = True
                docstring_char = stripped[:3]
            elif stripped.endswith(docstring_char):
                in_docstring = False
                continue
        
        # Nach docstring suchen wir erste import-Zeile
        if not in_docstring and (stripped.startswith('import ') or stripped.startswith('from ')):
            # Füge nach diesem import ein
            insert_pos = i + 1
            break
    
    if insert_pos is None:
        return False, "No import found"
    
    # Füge Unicode-Fix ein
    fix_lines = [
        "",
        "# Fix Unicode encoding on Windows",
        "try:",
        "    from test_utils import fix_windows_unicode",
        "    fix_windows_unicode()",
        "except ImportError:",
        "    pass  # test_utils.py not found",
        ""
    ]
    
    new_lines = lines[:insert_pos] + fix_lines + lines[insert_pos:]
    new_content = '\n'.join(new_lines)
    
    # Schreibe zurück
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    return True, "Fixed"

def main():
    script_dir = Path(__file__).parent
    test_files = sorted(script_dir.glob('test_*.py'))
    
    print("🔧 Automatischer Unicode-Fix für Test-Dateien")
    print("=" * 80)
    
    fixed_count = 0
    skipped_count = 0
    
    for test_file in test_files:
        if test_file.name == 'test_utils.py':
            continue
        
        success, message = fix_test_file(test_file)
        
        if success:
            print(f"✅ {test_file.name}: {message}")
            fixed_count += 1
        else:
            print(f"⏭️  {test_file.name}: {message}")
            skipped_count += 1
    
    print("=" * 80)
    print(f"📊 Zusammenfassung:")
    print(f"   Fixed: {fixed_count}")
    print(f"   Skipped: {skipped_count}")
    print(f"   Total: {len(list(test_files)) - 1}")  # -1 for test_utils.py

if __name__ == '__main__':
    main()

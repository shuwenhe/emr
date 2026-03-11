#!/usr/bin/env python3
"""
验证报告生成所需的所有依赖。
"""

def test_imports():
    """Test critical imports for report generation."""
    tests_passed = 0
    tests_failed = 0
    
    imports_to_test = [
        ("docx", "Document from docx"),
        ("matplotlib", "matplotlib for visualization"),
        ("matplotlib.font_manager", "font_manager for CJK fonts"),
        ("PIL", "PIL for image processing"),
        ("numpy", "numpy for numerical operations"),
        ("pathlib", "pathlib for path handling"),
    ]
    
    for module_name, description in imports_to_test:
        try:
            __import__(module_name)
            print(f"✓ {module_name:30} - {description}")
            tests_passed += 1
        except ImportError as e:
            print(f"✗ {module_name:30} - {description}")
            print(f"  Error: {e}")
            tests_failed += 1
    
    # Test specific report modules
    print("\n--- Report Module Imports ---")
    
    try:
        from reports import generate_docx_report, generate_template_report
        print(f"✓ reports - Report generation functions imported")
        tests_passed += 1
    except ImportError as e:
        print(f"✗ reports - Error: {e}")
        tests_failed += 1
    
    # Test config
    try:
        from backend.ingestion.app.config import REPORTS_DIR, DATA_DIR
        print(f"✓ Config - REPORTS_DIR={REPORTS_DIR}, DATA_DIR={DATA_DIR}")
        print(f"  REPORTS_DIR exists: {REPORTS_DIR.exists()}")
        print(f"  REPORTS_DIR is_dir: {REPORTS_DIR.is_dir()}")
        tests_passed += 1
    except Exception as e:
        print(f"✗ Config - Error: {e}")
        tests_failed += 1
    
    print(f"\n--- Summary ---")
    print(f"Passed: {tests_passed}")
    print(f"Failed: {tests_failed}")
    
    return tests_failed == 0


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/home/shuwen/emr/backend")
    sys.path.insert(0, "/home/shuwen/emr/ingestion")
    
    success = test_imports()
    sys.exit(0 if success else 1)

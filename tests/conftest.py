"""
Pytest configuration for test suite.

Adds project root to sys.path to enable 'src.' imports.
"""

import sys
from pathlib import Path

# Add project root to Python path so 'src.module' imports work
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

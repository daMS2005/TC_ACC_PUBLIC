"""Put the repository root on the import path.

Without this, the included tests only run from the repository root, and only
if a copy of the package happens to be installed in the environment. Both are
traps for anyone cloning this to read it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

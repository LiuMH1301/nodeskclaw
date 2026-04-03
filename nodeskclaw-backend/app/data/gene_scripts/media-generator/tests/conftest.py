"""Fix sys.path so tests can import from lib/ and providers/ without package install."""

import sys
from pathlib import Path

# Add gene_scripts/media-generator to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

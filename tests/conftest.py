import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['INTERNAL_API_TOKEN'] = 'test-internal-token-' + 'x' * 40
os.environ['SEMANTIC_SIMILARITY_ENABLED'] = 'false'

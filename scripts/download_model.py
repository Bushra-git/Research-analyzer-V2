"""Explicit setup step; serving a manuscript never downloads model files."""
import json
import os
from pathlib import Path
from huggingface_hub import HfApi, snapshot_download

MODEL = 'sentence-transformers/all-MiniLM-L6-v2'
root = Path(__file__).resolve().parents[1]
manifest_path = root / 'models' / 'manifest.json'
revision = os.getenv('EMBEDDING_MODEL_REVISION')
if not revision and manifest_path.exists():
    revision = json.loads(manifest_path.read_text())['revision']
if not revision:
    revision = HfApi().model_info(MODEL).sha
destination = root / 'models' / 'all-MiniLM-L6-v2'
snapshot_download(MODEL, revision=revision, local_dir=destination,
    allow_patterns=['*.json', '*.txt', 'README.md', 'LICENSE*', 'model.safetensors', '1_Pooling/*'],
    ignore_patterns=['onnx/*', 'openvino/*', '*.bin', '*.h5', '*.ot'])
manifest_path.write_text(json.dumps({'model': MODEL, 'revision': revision, 'format': 'safetensors'}, indent=2) + '\n')
print(f'Installed {MODEL} at revision {revision}')

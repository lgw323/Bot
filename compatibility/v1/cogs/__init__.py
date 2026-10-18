"""Hash-checked historical comparison code; never a production extension set."""

from hashlib import sha256
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_MANIFEST = _ROOT / "oracles-manifest.json"
if sha256(_MANIFEST.read_bytes()).hexdigest() != "afdb96f5d4674ea6b4052b51a787a42bb0e3de8d9511552a3f74a200d1969e76":
    raise ImportError("Frozen V1 oracle manifest changed; review its provenance before use")
for _entry in json.loads(_MANIFEST.read_text(encoding="utf-8"))["oracles"]:
    if sha256((_ROOT / _entry["reference_path"]).read_bytes()).hexdigest() != _entry["reference_sha256"]:
        raise ImportError("Frozen V1 comparison reference changed; review its provenance before use")

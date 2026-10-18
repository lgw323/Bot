"""Verify the frozen V1 database oracle before allowing its import."""

from hashlib import sha256
from pathlib import Path


_DATABASE_SHA256 = "2862326053920ef379e72ceca7e65cba6f032f04e8285f4221d8101898c179b1"
if sha256(Path(__file__).with_name("database_manager.py").read_bytes()).hexdigest() != _DATABASE_SHA256:
    raise ImportError("Frozen V1 database reference changed; review its provenance before use")

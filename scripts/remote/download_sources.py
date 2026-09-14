"""Download only the five preregistered order files; verify before rename."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

manifest, out = json.loads(Path(sys.argv[1]).read_text()), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
for symbol, entry in manifest["files"].items():
    started = time.monotonic()
    target = out / entry["filename"]
    temporary = target.with_suffix(".download")
    if not target.exists():
        subprocess.run(["curl", "--fail", "--location", "--retry", "3", "--max-time", "1800", "--output", str(temporary), entry["url"]], check=True)
        candidate = temporary
    else:
        candidate = target
    sha = hashlib.sha256()
    with candidate.open("rb") as f:
        for block in iter(lambda: f.read(8*1024*1024), b""):
            sha.update(block)
    if sha.hexdigest() != entry["sha256"] or candidate.stat().st_size != entry["bytes"]:
        raise ValueError(f"official source mismatch: {symbol}")
    if candidate != target:
        candidate.replace(target)
    print(json.dumps({"symbol": symbol, "sha256": sha.hexdigest(), "bytes": target.stat().st_size, "seconds": time.monotonic()-started}), flush=True)

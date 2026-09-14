from __future__ import annotations

import re
import subprocess
from pathlib import Path

FORBIDDEN_BASENAMES = {
    "host_inventory.json",
    "resource_metrics.csv",
    "performance_receipts.json",
    "resume_receipts.json",
    "cache_transfer_metrics.csv",
}

FORBIDDEN_PATTERNS = {
    "GPU UUID": re.compile(r"GPU-[0-9a-fA-F]{8,}(?:-[0-9a-fA-F]{4,})+"),
    "serialized hostname field": re.compile(r"[\"']hostname[\"']\s*[:=]", re.IGNORECASE),
    "raw CPU inventory": re.compile(r"(?m)^CPU\(s\):\s+\d+"),
    "raw CPU model inventory": re.compile(r"(?m)^Model name:\s+.+"),
    "raw GPU inventory header": re.compile(r"memory\.total\s*\[MiB\]", re.IGNORECASE),
    "scheduler job receipt": re.compile(r"[\"']?(?:slurm_)?job(?:_id)?[\"']?\s*[:=]\s*\d+", re.IGNORECASE),
    "absolute Linux home path": re.compile(r"/home/[A-Za-z0-9._-]+/"),
    "absolute macOS home path": re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    "embedded SSH target": re.compile(r"\bssh\s+[A-Za-z0-9._-]+@[A-Za-z0-9._-]+", re.IGNORECASE),
}

SKIP_TEXT_SCAN = {
    "scripts/check_public_privacy.py",
    "CONTRIBUTING.md",
    "docs/NEXT_RESEARCH_ROADMAP.md",
}


def tracked_files() -> list[Path]:
    output = subprocess.check_output(["git", "ls-files", "-z"])
    return [Path(p.decode()) for p in output.split(b"\0") if p]


def main() -> None:
    failures: list[str] = []
    for path in tracked_files():
        if path.name in FORBIDDEN_BASENAMES:
            failures.append(f"forbidden public artifact: {path}")
            continue
        if str(path) in SKIP_TEXT_SCAN or not path.is_file():
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\0" in raw or len(raw) > 2_000_000:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in FORBIDDEN_PATTERNS.items():
            if pattern.search(text):
                failures.append(f"{label}: {path}")
    if failures:
        raise SystemExit("Public-repo privacy check failed:\n- " + "\n- ".join(sorted(set(failures))))
    print("Public-repo privacy check passed.")


if __name__ == "__main__":
    main()

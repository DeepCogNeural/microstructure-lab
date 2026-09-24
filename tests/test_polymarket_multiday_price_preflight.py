"""Synthetic checks for the manifest-only budget gate."""
import importlib.util
import io
import json
import zipfile
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "scripts/polymarket_multiday_price_preflight.py"
SPEC = importlib.util.spec_from_file_location("multiday_preflight", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def source_zip(lines):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(MODULE.MANIFEST_MEMBER, "\n".join(lines) + "\n")
    return buffer.getvalue()


def test_budget_counts_every_fixed_day_and_never_emits_url():
    secret = "https://example.invalid/signed-secret"
    data = source_zip([
        f"{MODULE.MAX_COMPRESSED_BYTES}\traw/2026-07-27/0000.jsonl.zst\t{secret}",
        f"1\traw/2026-08-02/2300.jsonl.zst\t{secret}",
        f"999\traw/2026-08-03/0000.jsonl.zst\t{secret}",
    ])
    result = MODULE.aggregate(data)
    assert result["status"] == "ACCESS_OR_BUDGET_BLOCKED"
    assert result["window_source_bytes"] == MODULE.MAX_COMPRESSED_BYTES + 1
    assert result["window_source_objects"] == 2
    assert secret not in json.dumps(result)


def test_duplicate_manifest_path_fails_closed():
    row = "1\traw/2026-07-27/0000.jsonl.zst\thttps://example.invalid"
    try:
        MODULE.aggregate(source_zip([row, row]))
    except ValueError as exc:
        assert "duplicate path" in str(exc)
    else:
        raise AssertionError("duplicate path accepted")

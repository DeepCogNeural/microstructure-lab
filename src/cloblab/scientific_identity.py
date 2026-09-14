"""Scientific identity independent of runtime placement and telemetry."""
from cloblab.scale_common import digest

SCIENTIFIC_SECTIONS = ("dataset", "features", "evaluation", "models", "negative_controls", "execution_labels", "robustness")
EXECUTION_FIELDS = frozenset({"device", "n_jobs", "threads", "workers", "worker_count", "host", "hostname", "scheduler", "paths", "path", "cache_path", "output_path", "runtime_limits", "max_hours", "telemetry", "publication", "privacy", "environment"})


def scientific_config(config):
    def clean(value):
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items() if key not in EXECUTION_FIELDS}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value
    return {key: clean(config[key]) for key in SCIENTIFIC_SECTIONS if key in config}


def scientific_cache(manifest):
    """Bind input contents, excluding cache placement, timings and old config IDs."""
    return {"sources": {symbol: entry.get("sha256") for symbol, entry in sorted(manifest.get("sources", {}).items())},
            "partitions": sorted([{key: p[key] for key in ("symbol", "day", "features_sha256", "snapshots_sha256") if key in p}
                                  for p in manifest["partitions"]], key=lambda p: (p["symbol"], p["day"]))}


def scientific_task_id(config, task, manifest):
    identity = {key: task[key] for key in ("symbol", "month", "horizon", "model", "control_seed")}
    return digest({"identity_version": 2, "science": scientific_config(config), "input": scientific_cache(manifest), "task": identity})

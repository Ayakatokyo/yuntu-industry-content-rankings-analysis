"""Load and validate the project-scoped Yuntu hot-material rule."""

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOT_MATERIAL_CONFIG_PATH = PROJECT_ROOT / "config" / "hot-material-rules.json"
CONFIG_SCHEMA_VERSION = 1
ALLOWED_METRICS = {"exposure_interval_min"}
ALLOWED_COMPARISONS = {"gte"}


class HotMaterialConfigError(ValueError):
    """Raised when the hot-material configuration is missing or invalid."""


def load_hot_material_rule(path=None):
    config_path = Path(path) if path is not None else DEFAULT_HOT_MATERIAL_CONFIG_PATH
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HotMaterialConfigError(
            f"unable to read hot-material config {config_path}: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise HotMaterialConfigError("hot-material config must be an object")
    if set(payload) != {"schemaVersion", "hotMaterialRule"}:
        raise HotMaterialConfigError(
            "hot-material config must contain only schemaVersion and hotMaterialRule"
        )
    if payload["schemaVersion"] != CONFIG_SCHEMA_VERSION:
        raise HotMaterialConfigError(
            f"unsupported hot-material config schemaVersion: {payload['schemaVersion']}"
        )

    rule = payload["hotMaterialRule"]
    if not isinstance(rule, dict):
        raise HotMaterialConfigError("hotMaterialRule must be an object")
    if set(rule) != {"metric", "comparison", "threshold"}:
        raise HotMaterialConfigError(
            "hotMaterialRule must contain only metric, comparison, and threshold"
        )
    if rule["metric"] not in ALLOWED_METRICS:
        raise HotMaterialConfigError(
            f"unsupported hot-material metric: {rule['metric']}"
        )
    if rule["comparison"] not in ALLOWED_COMPARISONS:
        raise HotMaterialConfigError(
            f"unsupported hot-material comparison: {rule['comparison']}"
        )
    threshold = rule["threshold"]
    if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold <= 0:
        raise HotMaterialConfigError("hot-material threshold must be a positive integer")

    return {
        "metric": rule["metric"],
        "comparison": rule["comparison"],
        "threshold": threshold,
    }

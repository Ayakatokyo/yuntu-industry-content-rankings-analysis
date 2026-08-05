"""Persistent run-state helpers for the Yuntu RPA workflow."""

import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid


class YuntuRunStateError(RuntimeError):
    """Raised when run state or a registered artifact is invalid."""


def parameter_fingerprint(filters):
    """Return the stable SHA-256 identity for a filter mapping."""
    encoded = json.dumps(filters, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def new_run_summary(root, filters):
    """Create the initial state for a single collection run."""
    del root
    filters_snapshot = json.loads(
        json.dumps(filters, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    return {
        "schemaVersion": 1,
        "runId": uuid.uuid4().hex,
        "parameterFingerprint": parameter_fingerprint(filters_snapshot),
        "filters": filters_snapshot,
        "status": "collecting",
        "artifacts": {},
        "nextAction": {"command": "fetch", "allowsRpa": True},
    }


def sha256_file(path):
    """Calculate a SHA-256 checksum without loading the entire file into memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as artifact_file:
        for block in iter(lambda: artifact_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _root_contained_file(root, path):
    root_path = Path(root).resolve()
    artifact_path = Path(path).resolve()
    if not artifact_path.is_file() or artifact_path.stat().st_size == 0:
        raise YuntuRunStateError("artifact must be a nonempty file")
    try:
        relative_path = artifact_path.relative_to(root_path)
    except ValueError as exc:
        raise YuntuRunStateError("artifact must be within the run root") from exc
    return artifact_path, relative_path


def register_artifact(summary, root, key, path, source):
    """Record an immutable identity for a file produced within the run root."""
    if not isinstance(key, str) or not key:
        raise YuntuRunStateError("artifact key must be nonempty")
    if not isinstance(source, str) or not source:
        raise YuntuRunStateError("artifact source must be nonempty")
    artifact_path, relative_path = _root_contained_file(root, path)
    artifacts = summary.get("artifacts")
    if not isinstance(artifacts, dict):
        raise YuntuRunStateError("run summary artifacts must be an object")
    artifacts[key] = {
        "path": relative_path.as_posix(),
        "source": source,
        "sizeBytes": artifact_path.stat().st_size,
        "sha256": sha256_file(artifact_path),
        "parseStatus": "pending",
    }
    return artifacts[key]


def save_run_state(summary, path):
    """Atomically persist a run summary as UTF-8 JSON."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".tmp", dir=target.parent, delete=False
    ) as staging_file:
        staging_path = Path(staging_file.name)
        try:
            json.dump(summary, staging_file, ensure_ascii=False, indent=2)
            staging_file.write("\n")
            staging_file.flush()
            os.fsync(staging_file.fileno())
        except Exception:
            staging_path.unlink(missing_ok=True)
            raise
    try:
        os.replace(staging_path, target)
    except Exception:
        staging_path.unlink(missing_ok=True)
        raise
    return target


def load_run_state(path):
    """Load a persisted run summary and reject malformed JSON state."""
    source = Path(path)
    try:
        with source.open(encoding="utf-8") as state_file:
            summary = json.load(state_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise YuntuRunStateError(f"unable to load run state {source}: {exc}") from exc
    if not isinstance(summary, dict):
        raise YuntuRunStateError("run state must be a JSON object")
    return summary


def validate_artifact(summary, root, key):
    """Verify that a registered artifact remains rooted, nonempty, and unchanged."""
    artifacts = summary.get("artifacts")
    artifact = artifacts.get(key) if isinstance(artifacts, dict) else None
    if not isinstance(artifact, dict):
        raise YuntuRunStateError(f"artifact {key!r} is not registered")
    relative_path = artifact.get("path")
    if not isinstance(relative_path, str) or not relative_path:
        raise YuntuRunStateError(f"artifact {key!r} has an invalid path")
    artifact_path, _ = _root_contained_file(root, Path(root) / relative_path)
    if artifact.get("sizeBytes") != artifact_path.stat().st_size:
        raise YuntuRunStateError(f"artifact {key!r} size does not match run state")
    if artifact.get("sha256") != sha256_file(artifact_path):
        raise YuntuRunStateError(f"artifact {key!r} checksum does not match run state")
    return Path(root) / relative_path

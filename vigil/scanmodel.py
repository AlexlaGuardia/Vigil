"""Registration-time scanner for serialized model configs (Keras `.keras` / HDF5 `.h5`).

Companion to `scantools` (which walks MCP tool definitions). Same lesson, one layer up:
**walk the WHOLE serialized structure, flag dangerous nodes wherever they sit — never a
flat top-level pass keyed on a single class name.**

Motivation (FINDING-M1, 2026-07-24). The reference OSS model scanner `modelscan` 0.8.8
reduces all Keras/H5/SavedModel arbitrary-code detection to one flat, top-level test::

    layers = model_config["config"]["layers"]          # TOP LEVEL ONLY
    [ l for l in layers if l.get("class_name") == "Lambda" ]   # ONE operator name

Two structural blind spots follow, both confirmed empirically against the shipped version:
  - a `Lambda` nested one level deep (a Sequential/Functional inside a Functional — ordinary
    Keras) is never descended into, so it scans CLEAN;
  - any *other* code-reaching operator (`TFSMLayer`, a custom registered callable) has
    `class_name != "Lambda"` and is therefore never considered.

Vigil closes both by construction: `_iter_layers` recurses the ENTIRE config tree, and the
danger test keys on a set of code-reaching operators PLUS the presence of an embedded
serialized callable (which is class-name-agnostic — the real ACE carrier). This is the
allowlist-the-safe / enumerate-the-structure discipline, not a denylist of one name.
"""

from __future__ import annotations

import json
import zipfile

from vigil.scantools import Flag, ScanResult


# Operators whose deserialization reaches code execution on model load. HIGH.
# This is a curated set, extended as the ecosystem grows — NOT the whole of danger.
# The serialized-function check below is what makes coverage class-name-agnostic.
_DANGEROUS_OPS: dict[str, str] = {
    "Lambda": "Lambda layers deserialize and call an arbitrary Python function on load "
              "(the canonical Keras RCE primitive; blocked only by safe_mode=True).",
    "TFSMLayer": "TFSMLayer loads and executes an attacker-referenced TensorFlow "
                 "SavedModel on load (CVE-2026-1462 class).",
}

# Standard first-party namespaces. A layer registered outside these is a custom object
# whose deserialization can import an arbitrary module — worth a review flag (LOW).
_TRUSTED_MODULE_PREFIXES = ("keras", "tensorflow", "tf_keras", "tf.")


def _iter_layers(obj, path=""):
    """Yield (field_path, node) for EVERY dict carrying a "class_name" — at ANY depth.

    modelscan iterates only `config.layers` at the top level; a nested submodel hides a
    layer from it. This walk descends into every dict/list, so a Lambda buried inside a
    nested Functional/Sequential (or any wrapper) is enumerated like any other."""
    if isinstance(obj, dict):
        if isinstance(obj.get("class_name"), str):
            yield path, obj
        for k, v in obj.items():
            yield from _iter_layers(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _iter_layers(v, f"{path}[{i}]")


def _has_serialized_function(layer_config: dict) -> bool:
    """True if a layer config embeds a serialized Python callable (the actual code carrier).

    Keras serializes a Lambda's function (and custom activations) as either a marshalled
    `{"class_name": "__lambda__", "config": {"code": ...}}` blob or a `"function"` /
    `"activation"` object holding a `code`/`module`+`class_name` pointer. Catching this
    makes detection independent of the LAYER's own class_name — a renamed or custom
    Lambda-equivalent still trips it."""
    if not isinstance(layer_config, dict):
        return False
    for key in ("function", "activation"):
        v = layer_config.get(key)
        if isinstance(v, dict):
            cn = v.get("class_name")
            if cn == "__lambda__" or "code" in v or "code" in v.get("config", {}):
                return True
    return False


def scan_model_config(config: dict, name: str = "<model>") -> ScanResult:
    """Scan a parsed Keras model config for code-reaching operators at any nesting depth."""
    flags: list[Flag] = []
    score = 0

    for path, node in _iter_layers(config):
        cn = node.get("class_name")
        node_cfg = node.get("config", {}) if isinstance(node.get("config"), dict) else {}
        layer_name = node_cfg.get("name", cn)

        if cn in _DANGEROUS_OPS:
            score += 3
            flags.append(Flag(
                "dangerous_operator", f"{path}.class_name",
                _DANGEROUS_OPS[cn],
                f"{cn} ({layer_name})"))
        elif _has_serialized_function(node_cfg):
            # A non-listed operator that still carries a serialized callable payload.
            score += 3
            flags.append(Flag(
                "serialized_function", f"{path}.config",
                "layer embeds a serialized Python callable (code executes on "
                "deserialization) despite a non-standard operator name",
                f"{cn} ({layer_name})"))
        else:
            # Custom object registered outside the first-party namespaces: its
            # deserialization can import an arbitrary module. Review-worthy (LOW).
            module = node.get("module") or node.get("registered_name") or ""
            if isinstance(module, str) and module and not module.startswith(_TRUSTED_MODULE_PREFIXES):
                score += 1
                flags.append(Flag(
                    "custom_object_import", f"{path}.module",
                    "layer resolves a custom object from a non-first-party module; "
                    "deserialization imports an attacker-named module",
                    f"{cn} <- {module}"))

    has_exec = any(f.signal in ("dangerous_operator", "serialized_function") for f in flags)
    if has_exec:
        sev = "high"
    elif score >= 1:
        sev = "low"
    else:
        sev = "none"
    return ScanResult(name, score, sev, flags)


# --- file extractors (lazy deps; only imported when a real file is scanned) ---------------

def extract_keras_config(path: str) -> dict:
    """Pull the architecture config dict from a `.keras` archive (its `config.json`)."""
    with zipfile.ZipFile(path, "r") as zf:
        with zf.open("config.json") as fh:
            return json.load(fh)


def extract_h5_config(path: str) -> dict:
    """Pull the architecture config from an HDF5 `.h5` file's `model_config` attribute."""
    import h5py  # optional dep; only needed for .h5 inputs

    with h5py.File(path, "r") as f:
        raw = f.attrs.get("model_config")
        if raw is None:
            return {}
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)


def scan_model_file(path: str) -> ScanResult:
    """Scan a `.keras` or `.h5` model file on disk."""
    lower = path.lower()
    if lower.endswith(".keras"):
        config = extract_keras_config(path)
    elif lower.endswith((".h5", ".hdf5")):
        config = extract_h5_config(path)
    else:
        raise ValueError(f"unsupported model file (want .keras/.h5/.hdf5): {path}")
    return scan_model_config(config, name=path.rsplit("/", 1)[-1])

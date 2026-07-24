"""Tests for the model-config scanner (vigil/scanmodel.py) — FINDING-M1.

The regression that matters: Vigil flags HIGH exactly the configs that the shipped
modelscan 0.8.8 reports clean (nested Lambda + non-Lambda TFSMLayer), while its flat
top-level `class_name == "Lambda"` scan misses them. The `control` case (top-level
Lambda) is where the two scanners agree — it proves detection is live, not that Vigil
merely flags everything."""

from vigil.scanmodel import scan_model_config, _has_serialized_function


def _lambda_layer(name="evil"):
    return {
        "class_name": "Lambda",
        "config": {"name": name,
                   "function": {"class_name": "__lambda__",
                                "config": {"code": "<b64 os.system payload>"}}},
    }


def _dense(name="dense"):
    return {"class_name": "Dense", "config": {"name": name, "units": 64,
                                              "activation": "relu"}}


# --- the three M1 files ------------------------------------------------------------------

def test_toplevel_lambda_high():
    """Control: modelscan catches this too. Vigil must also flag it (detection is live)."""
    cfg = {"class_name": "Sequential",
           "config": {"name": "top", "layers": [_dense("in"), _lambda_layer("top_lambda")]}}
    r = scan_model_config(cfg)
    assert r.severity == "high"
    assert any(f.signal == "dangerous_operator" for f in r.flags)


def test_nested_lambda_high_where_modelscan_misses():
    """BYPASS-A: Lambda nested one level deep. modelscan 0.8.8 -> 'No issues found'.
    Vigil recurses the full tree -> HIGH."""
    cfg = {"class_name": "Functional",
           "config": {"name": "outer", "layers": [
               _dense("in"),
               {"class_name": "Functional",
                "config": {"name": "inner_submodel",
                           "layers": [_dense("in2"), _lambda_layer("nested_lambda")]}},
           ]}}
    r = scan_model_config(cfg)
    assert r.severity == "high"
    hit = [f for f in r.flags if f.signal == "dangerous_operator"]
    assert hit and "nested_lambda" in hit[0].excerpt


def test_nonlambda_tfsmlayer_high_where_modelscan_misses():
    """BYPASS-B: TFSMLayer (class_name != 'Lambda'). modelscan -> 'No issues found'.
    Vigil keys on a set of code-reaching ops, not one name -> HIGH."""
    cfg = {"class_name": "Functional",
           "config": {"name": "top", "layers": [
               _dense("in"),
               {"class_name": "TFSMLayer",
                "config": {"name": "evil_tfsm", "filepath": "./attacker_saved_model",
                           "call_endpoint": "serving_default"}},
           ]}}
    r = scan_model_config(cfg)
    assert r.severity == "high"
    assert any("TFSMLayer" in f.excerpt for f in r.flags)


# --- clean + edge cases ------------------------------------------------------------------

def test_clean_model_none():
    cfg = {"class_name": "Sequential",
           "config": {"name": "clean", "layers": [_dense("d1"), _dense("d2")]}}
    r = scan_model_config(cfg)
    assert r.severity == "none"
    assert r.flags == []


def test_deeply_nested_lambda_still_caught():
    """Three levels deep — the walk has no depth limit."""
    inner = {"class_name": "Sequential",
             "config": {"name": "L3", "layers": [_lambda_layer("deep")]}}
    mid = {"class_name": "Functional", "config": {"name": "L2", "layers": [inner]}}
    cfg = {"class_name": "Functional", "config": {"name": "L1", "layers": [_dense("in"), mid]}}
    r = scan_model_config(cfg)
    assert r.severity == "high"


def test_serialized_function_under_renamed_class():
    """A custom-named layer carrying a serialized callable — class-name-agnostic catch."""
    cfg = {"class_name": "Functional",
           "config": {"name": "top", "layers": [
               {"class_name": "TotallyBenignLayer",
                "config": {"name": "sneaky",
                           "function": {"class_name": "__lambda__",
                                        "config": {"code": "<payload>"}}}},
           ]}}
    r = scan_model_config(cfg)
    assert r.severity == "high"
    assert any(f.signal == "serialized_function" for f in r.flags)


def test_custom_module_import_is_low():
    cfg = {"class_name": "Functional",
           "config": {"name": "top", "layers": [
               {"class_name": "MyLayer", "module": "attacker_pkg.evil",
                "config": {"name": "x"}},
           ]}}
    r = scan_model_config(cfg)
    assert r.severity == "low"
    assert any(f.signal == "custom_object_import" for f in r.flags)


def test_first_party_custom_module_not_flagged():
    cfg = {"class_name": "Functional",
           "config": {"name": "top", "layers": [
               {"class_name": "Dense", "module": "keras.layers", "config": {"name": "x"}},
           ]}}
    r = scan_model_config(cfg)
    assert r.severity == "none"


def test_has_serialized_function_helper():
    assert _has_serialized_function({"function": {"class_name": "__lambda__", "config": {}}})
    assert _has_serialized_function({"activation": {"code": "x"}})
    assert not _has_serialized_function({"units": 64, "activation": "relu"})

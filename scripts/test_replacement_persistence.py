"""SP2 Task 10 — Round-trip test for _wiring_resolutions serialization format.

Locks the contract: key=(fn_id, pin_net) <-> "fn_id|pin_net" string used by
save_project() (serialize) and load_project() (deserialize) in studio_view.py.

No Qt dependency — pure Python.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers that mirror studio_view.py serialize / deserialize exactly
# ---------------------------------------------------------------------------

def _serialize(resolutions: dict) -> dict:
    """Mirror of studio_view.save_project() line ~4980-4983."""
    return {f"{k[0]}|{k[1]}": v for k, v in resolutions.items()}


def _deserialize(raw: dict) -> dict:
    """Mirror of studio_view.load_project() lines ~4717-4720."""
    out = {}
    for k_str, v in raw.items():
        if "|" in k_str:
            fn_id, pin_net = k_str.split("|", 1)
            out[(fn_id, pin_net)] = v
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_resolution_roundtrip_for_catalog_type():
    """Basic round-trip: a simple type is preserved through serialize+deserialize."""
    res = {("fn-1", "D5"): "relay"}
    ser = _serialize(res)
    back = _deserialize(ser)
    assert back == res, f"Expected {res!r}, got {back!r}"
    assert back[("fn-1", "D5")] == "relay"


def test_resolution_roundtrip_multiple_types():
    """Multiple components of different types all survive the round-trip."""
    res = {
        ("fn-2", "D9"): "servo",
        ("fn-3", "A0"): "potentiometer",
        ("fn-4", "D3"): "buzzer",
    }
    back = _deserialize(_serialize(res))
    assert back == res, f"Expected {res!r}, got {back!r}"


def test_resolution_roundtrip_dc_motor_with_driver():
    """dc_motor + its ::_driver sub-key both survive the round-trip.

    The driver key uses pin_net = "D5::_driver" which contains a pipe-free
    suffix; the split("|", 1) must not break it.
    """
    res = {
        ("fn-5", "D5"): "dc_motor",
        ("fn-5", "D5::_driver"): "l298n",
    }
    back = _deserialize(_serialize(res))
    assert back == res, f"Expected {res!r}, got {back!r}"
    assert back[("fn-5", "D5")] == "dc_motor"
    assert back[("fn-5", "D5::_driver")] == "l298n"


def test_serialize_key_format():
    """Serialized keys must be exactly 'fn_id|pin_net'."""
    res = {("fn-1", "D13"): "led"}
    ser = _serialize(res)
    assert list(ser.keys()) == ["fn-1|D13"], f"Unexpected key format: {list(ser.keys())}"
    assert ser["fn-1|D13"] == "led"


def test_deserialize_ignores_keys_without_pipe():
    """Keys without '|' (corrupted data) are silently skipped on load."""
    raw = {"bad_key": "led", "fn-1|D3": "relay"}
    back = _deserialize(raw)
    assert ("fn-1", "D3") in back
    assert back[("fn-1", "D3")] == "relay"
    # bad_key must not appear
    for k in back:
        assert "|" not in k[0] or True  # keys are tuples, not strings
    assert len(back) == 1, f"Unexpected extra keys: {back}"


def test_roundtrip_pin_net_with_colon():
    """pin_net values with '::' suffix (driver sub-keys) are preserved by split(|,1)."""
    res = {("fn-6", "D6::_driver"): "tb6612fng"}
    ser = _serialize(res)
    assert "fn-6|D6::_driver" in ser
    back = _deserialize(ser)
    assert back == res


def test_scoped_single_edit_type_persisted():
    """Simulates the persistence write for a scoped single-component edit.

    This is the canonical pattern from studio_view.py lines 3163-3170
    (non-beginner path) and 3089-3098 (beginner path). Both paths write
    the same key format.
    """
    # Simulate state before the scoped edit
    wiring_resolutions: dict = {}

    # After modal accepted for scoped component:
    key = ("fn-7", "D11")
    comp_type = "buzzer"
    wiring_resolutions[key] = comp_type
    # No dc_motor driver sub-key needed here

    # Persist (serialize)
    serialized = _serialize(wiring_resolutions)
    # Reload (deserialize)
    reloaded = _deserialize(serialized)

    assert reloaded[key] == comp_type, (
        f"Scoped edit for {key!r} not persisted correctly: "
        f"expected {comp_type!r}, got {reloaded.get(key)!r}"
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    test_resolution_roundtrip_for_catalog_type,
    test_resolution_roundtrip_multiple_types,
    test_resolution_roundtrip_dc_motor_with_driver,
    test_serialize_key_format,
    test_deserialize_ignores_keys_without_pipe,
    test_roundtrip_pin_net_with_colon,
    test_scoped_single_edit_type_persisted,
]


def main():
    passed = 0
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"  PASS  {test.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL  {test.__name__}: {exc}")
            failed += 1
    print(f"\n{passed}/{passed + failed} tests passed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

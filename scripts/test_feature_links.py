"""feature_links: providers / deps / closure / constrained reorder (pure, no Qt)."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.generation.feature_model import Feature, FeatureFunction
from ui.generation.feature_links import (
    providers, feature_deps, dependency_closure, reorder_with_constraints,
)


def _feat(fid, *, glob=(), setup=(), loop=(), funcs=()):
    return Feature(
        id=fid, prompt=fid,
        global_lines=list(glob), setup_lines=list(setup),
        loop_lines=list(loop),
        functions=[FeatureFunction(name=n, code=c) for n, c in funcs],
    )


def test_providers_extracts_globals_defines_functions():
    f = _feat("f1",
              glob=["const int PIN_LED = 13;", "#define SEUIL 200"],
              funcs=[("readDistance", "long readDistance() {\n  return 0;\n}")])
    p = providers(f)
    assert "PIN_LED" in p, p
    assert "SEUIL" in p, p
    assert "readDistance" in p, p


def test_short_names_ignored():
    f = _feat("f1", glob=["int i = 0;", "int ok = 1;"])
    p = providers(f)
    assert "i" not in p, p
    assert "ok" not in p, p       # len < 3 filtered (noise)


def test_deps_on_shared_global():
    a = _feat("A", glob=["const int PIN_LED = 13;"],
              setup=["pinMode(PIN_LED, OUTPUT);"])
    b = _feat("B", loop=["digitalWrite(PIN_LED, HIGH);"])
    deps = feature_deps([a, b])
    assert deps["B"] == {"A"}, deps
    assert deps["A"] == set(), deps    # no self-dependency


def test_deps_on_function_call():
    a = _feat("A", funcs=[("readDistance", "long readDistance() { return 1; }")])
    b = _feat("B", loop=["long d = readDistance();"])
    deps = feature_deps([a, b])
    assert deps["B"] == {"A"}, deps


def test_redeclared_name_first_provider_wins():
    # B redeclares PIN_LED: assemble dedup keeps A's line (first emitter),
    # so B actually consumes A's declaration -> B depends on A.
    a = _feat("A", glob=["const int PIN_LED = 13;"])
    b = _feat("B", glob=["const int PIN_LED = 5;"],
              loop=["digitalWrite(PIN_LED, HIGH);"])
    c = _feat("C", glob=["const int PIN_UNIQUE = 7;"],
              loop=["digitalWrite(PIN_UNIQUE, LOW);"])
    deps = feature_deps([a, b, c])
    assert deps["B"] == {"A"}, deps
    assert deps["C"] == set(), deps    # unique name -> no dep


def test_closure_is_transitive():
    a = _feat("A", glob=["const int PIN_X = 1;"])
    b = _feat("B", glob=["int etatX = 0;"], loop=["etatX = digitalRead(PIN_X);"])
    c = _feat("C", loop=["if (etatX) {}"])
    deps = feature_deps([a, b, c])
    assert dependency_closure("C", deps) == {"A", "B"}, deps
    assert dependency_closure("B", deps) == {"A"}, deps
    assert dependency_closure("A", deps) == set(), deps


def test_reorder_legal_move_unchanged():
    deps = {"A": set(), "B": {"A"}, "X": set()}
    # X moved to front: no constraint involved -> exact requested order.
    assert reorder_with_constraints(["A", "B", "X"], "X", 0, deps) == ["X", "A", "B"]


def test_reorder_consumer_before_provider_pulls_provider():
    deps = {"A": set(), "B": {"A"}, "X": set()}
    # B dropped at index 0 (before its provider A) -> A slides just above B.
    assert reorder_with_constraints(["A", "B", "X"], "B", 0, deps) == ["A", "B", "X"]


def test_reorder_provider_after_consumer_pushes_consumer():
    deps = {"A": set(), "B": {"A"}, "X": set()}
    # A moved to the end -> its consumer B slides just below it.
    assert reorder_with_constraints(["A", "B", "X"], "A", 2, deps) == ["X", "A", "B"]


def test_reorder_preserves_block_internal_order():
    # C -> B -> A chain; move C to front: whole chain re-stacks above C,
    # keeping A before B before C.
    deps = {"A": set(), "B": {"A"}, "C": {"B"}, "X": set(), "Y": set()}
    out = reorder_with_constraints(["X", "A", "B", "Y", "C"], "C", 0, deps)
    assert out.index("A") < out.index("B") < out.index("C"), out
    # C requested at 0: the block lands at the front, X/Y keep relative order.
    assert out == ["A", "B", "C", "X", "Y"], out


def test_reorder_cycle_does_not_hang():
    deps = {"A": {"B"}, "B": {"A"}}
    out = reorder_with_constraints(["A", "B"], "B", 0, deps)
    assert sorted(out) == ["A", "B"], out   # returns SOMETHING sane


TESTS = [
    test_providers_extracts_globals_defines_functions,
    test_short_names_ignored,
    test_deps_on_shared_global,
    test_deps_on_function_call,
    test_redeclared_name_first_provider_wins,
    test_closure_is_transitive,
    test_reorder_legal_move_unchanged,
    test_reorder_consumer_before_provider_pulls_provider,
    test_reorder_provider_after_consumer_pushes_consumer,
    test_reorder_preserves_block_internal_order,
    test_reorder_cycle_does_not_hang,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t(); passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)

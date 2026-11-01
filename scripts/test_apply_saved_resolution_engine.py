import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules.setdefault("ui", ui_pkg)

from ui.wiring.netlist import Component, Pin, Netlist
from ui.wiring.ambiguity_dialog import apply_saved_resolution


def test_apply_saved_resolution_uses_engine_for_catalog_type():
    # 'relay' has no dedicated transform but is a single_output catalogue entry.
    led = Component(ref="D1", type="led",
                    pins=[Pin("A", "D7"), Pin("K", "GND")],
                    attributes={"category": "single_output",
                                "signature_detected": False})
    nl = Netlist(board_id="", components=[led])
    apply_saved_resolution(led, "relay", netlist=nl)
    assert led.type == "relay"
    # Signal preserved via the engine. Since TODO #41 part 2 the relay carries
    # its REAL pinout (VCC / GND / IN) instead of a 2-pin approximation, so the
    # signal lands on IN -- assert that, not a pin POSITION, which is what made
    # this test brittle in the first place.
    assert led.pin("IN") is not None, [p.name for p in led.pins]
    assert led.pin("IN").net == "D7"


def test_apply_saved_resolution_keeps_historical_transform():
    # a historical type (buzzer) must continue to go through its transform,
    # NOT through the generic engine: we just verify it stays functional.
    led = Component(ref="D1", type="led",
                    pins=[Pin("A", "D7"), Pin("K", "GND")],
                    attributes={"category": "single_output",
                                "signature_detected": False})
    nl = Netlist(board_id="", components=[led])
    apply_saved_resolution(led, "buzzer", netlist=nl)
    assert led.type == "buzzer"


def test_routing_unifies_via_apply_saved_resolution():
    # Verify that apply_saved_resolution routes arbitrary catalogue types
    # (e.g. relay) via the SP1 engine (replace_component), not _to_led_red.
    # This contract is what apply_choices must delegate (SP2 Task 5).
    from ui.wiring.ambiguity_dialog import _DEFAULT_TRANSFORMS
    assert "relay" not in _DEFAULT_TRANSFORMS
    led = Component(ref="D1", type="led",
                    pins=[Pin("A", "D7"), Pin("K", "GND")],
                    attributes={"category": "single_output",
                                "signature_detected": False})
    nl = Netlist(board_id="", components=[led])
    apply_saved_resolution(led, "relay", netlist=nl)
    # Same reason as above: the relay's real pinout puts the signal on IN, so
    # assert the net survives rather than the position it survives at.
    assert led.type == "relay"
    assert led.pin("IN") is not None and led.pin("IN").net == "D7"


def test_une_fiche_declaree_retire_la_resistance_serie_orpheline():
    """Requalifier une LED vers une fiche declaree laissait sa resistance
    serie derriere elle, branchee sur du vide (#70, 2026-08-27).

    `_drop_orphan_companions` existe pour ca et les quatre transformations
    historiques l'appellent (`_to_buzzer`, `_to_servo`, `_to_module_generic`,
    `_to_dc_motor`) ; le chemin catalogue, lui, retire ses freres inferes dans
    `replace_component`. Seul `_apply_declared` ne faisait ni l'un ni l'autre :
    `apply_saved_resolution` lui rend la main et RETOURNE aussitot.

    ⚠️ Le decor vient de `analyze_netlist`, pas d'un netlist fabrique a la
    main : la resistance serie n'existe que parce que l'inference tourne. Un
    test qui la poserait lui-meme prouverait moins -- c'est precisement ce
    raccourci qui a laisse vivre 17 jours le defaut voisin de ce ticket.
    """
    import ui.declared_components as dc
    from ui.declared_components import DeclaredComponent, DeclaredPin
    from ui.wiring.layout.pipeline import analyze_netlist

    dc.set_registry([DeclaredComponent(
        id="mon-capteur", name="Mon capteur", headers=("libinconnue.h",),
        pins=(DeclaredPin("VCC", "vcc", "5V"), DeclaredPin("GND", "gnd", "GND"),
              DeclaredPin("SIG", "signal", "D7")),
        lib="", keywords=("Mon capteur",))])
    try:
        nl = analyze_netlist("void setup(){ pinMode(7, OUTPUT); }\n"
                             "void loop(){ digitalWrite(7, HIGH); }\n",
                             "arduino_uno_r3", prompt="")
        led = next(c for c in nl.components if c.type == "led")
        assert any(c.type == "resistor" for c in nl.components), \
            "decor invalide : l'inference n'a pas pose de resistance serie"
        apply_saved_resolution(led, "custom:mon-capteur", netlist=nl)
        assert led.type == "custom:mon-capteur"
        restes = [(c.ref, [(p.name, p.net) for p in c.pins])
                  for c in nl.components if c.type == "resistor"]
        assert not restes, f"resistance serie orpheline laissee derriere : {restes}"
        assert not [w for w in nl.warnings if w.code == "led_series_resistor"], \
            "l'avertissement de la R serie survit a la disparition de la R"
    finally:
        dc.set_registry([])


TESTS = [
    test_apply_saved_resolution_uses_engine_for_catalog_type,
    test_apply_saved_resolution_keeps_historical_transform,
    test_routing_unifies_via_apply_saved_resolution,
    # #70 (2026-08-27) : le chemin `custom:` ne nettoyait pas.
    test_une_fiche_declaree_retire_la_resistance_serie_orpheline,
]


def main():
    passed = 0
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  OK  {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL  {t.__name__}: {exc}")
            failed += 1
    total = passed + failed
    print(f"\n{passed}/{total} OK")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

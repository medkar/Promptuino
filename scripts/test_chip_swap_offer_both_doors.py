"""QA AC1 (2026-08-31) : l'offre de regeneration apres swap de puce doit
partir des DEUX portes du schema.

Le defaut : `_resolve_wiring_netlist_tracked` ne suivait que l'edition SCOPEE
(engrenage), au motif que « la modale non scopee ne voit que les composants
low » — un invariant vrai a l'ecriture (SP2) et rendu FAUX par le #81
(« Modifier les composants » ouvre TOUT le schema via `collect_all_editable`,
puces signature comprises). Consequence : un swap ecran -> LED valide par ce
bouton n'offrait jamais la regeneration, en silence — le code gardait la lib
de l'ecran sans que rien ne le dise.

NB : UN seul StudioView par process (meme contrainte que
`test_scoped_edit_persistence`) ; les deux portes sont donc deux tests sur la
meme instance, avec remise a zero entre les deux.
"""
from __future__ import annotations
import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication  # noqa: E402
_APP = QApplication.instance() or QApplication([])

import ui.declared_components as declared_components  # noqa: E402
declared_components.set_registry([])

CODE = """#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>
#define DHTPIN 2
#define DHTTYPE DHT11
Adafruit_SSD1306 display(128, 64, &Wire, -1);
DHT dht(DHTPIN, DHTTYPE);
void setup() { dht.begin(); display.begin(SSD1306_SWITCHCAPVCC, 0x3C); }
void loop() { float t = dht.readTemperature(); display.print(t); display.display(); }
"""
BOARD = "arduino_uno_r3"
PROMPT = "affiche la temperature d'un capteur DHT11 sur un ecran OLED SSD1306"

_SV = None
_OLED_REF = None


def _studio():
    global _SV, _OLED_REF
    if _SV is None:
        from ui.studio_view import StudioView
        from ui.generation.feature_model import Feature
        from ui.wiring.layout import pipeline as _v2
        _SV = StudioView()
        _SV._features = [Feature(id="fn-1", prompt=PROMPT)]
        nl0 = _v2.analyze_netlist(CODE, BOARD)
        oled = next(c for c in nl0.components if c.type == "oled_ssd1306")
        assert oled.attributes.get("signature_detected"), oled.attributes
        _OLED_REF = oled.ref
        _SV._nl0 = nl0
    return _SV


def _drive(sv, scoped_to_ref):
    """Une resolution avec la modale detournee (choix : LED pour l'ecran).
    Rend la liste des couples passes a `_confirm_regen_after_swap`."""
    from ui.wiring import ambiguity_dialog as ad
    sv._open_wiring_dialog = types.SimpleNamespace(_netlist=sv._nl0)
    sv._pending_regen_swap = None
    sv._wiring_resolutions = {}
    calls: list[tuple[str, str]] = []
    oled_ref = _OLED_REF

    def fake_exec(self):
        self._chosen_type[oled_ref] = "led"
        return self.DialogCode.Accepted

    orig_exec = ad.AmbiguityDialog.exec
    orig_confirm = sv._confirm_regen_after_swap
    ad.AmbiguityDialog.exec = fake_exec
    sv._confirm_regen_after_swap = (
        lambda old, new: calls.append((old, new)) or False)
    try:
        nl = sv._resolve_wiring_netlist_tracked(
            CODE, BOARD, PROMPT, "", {}, force_remodal=True,
            scoped_to_ref=scoped_to_ref)
    finally:
        ad.AmbiguityDialog.exec = orig_exec
        sv._confirm_regen_after_swap = orig_confirm
    assert nl is not None, "modale annulee a tort"
    swapped = next(c for c in nl.components if c.ref == oled_ref)
    assert swapped.type == "led", swapped.type
    return calls


def test_the_gear_door_offers_the_regeneration():
    sv = _studio()
    calls = _drive(sv, scoped_to_ref=_OLED_REF)
    assert calls == [("oled_ssd1306", "led")], calls


def test_the_edit_all_door_offers_it_too():
    """La porte « Modifier les composants » (non scopee) — le trou du #81."""
    sv = _studio()
    calls = _drive(sv, scoped_to_ref=None)
    assert calls == [("oled_ssd1306", "led")], calls


def test_an_unchanged_signature_component_asks_nothing():
    """Valider sans rien changer ne doit pas poser la question (le DHT11 et
    l'ecran gardent leur type -> aucun couple, aucune popup)."""
    from ui.wiring import ambiguity_dialog as ad
    sv = _studio()
    sv._open_wiring_dialog = types.SimpleNamespace(_netlist=sv._nl0)
    sv._pending_regen_swap = None
    sv._wiring_resolutions = {}
    calls: list[tuple[str, str]] = []

    def fake_exec(self):
        return self.DialogCode.Accepted

    orig_exec = ad.AmbiguityDialog.exec
    orig_confirm = sv._confirm_regen_after_swap
    ad.AmbiguityDialog.exec = fake_exec
    sv._confirm_regen_after_swap = (
        lambda old, new: calls.append((old, new)) or False)
    try:
        sv._resolve_wiring_netlist_tracked(
            CODE, BOARD, PROMPT, "", {}, force_remodal=True)
    finally:
        ad.AmbiguityDialog.exec = orig_exec
        sv._confirm_regen_after_swap = orig_confirm
    assert calls == [], calls


# ── QA AC1, second aller-retour : le schema APRES la regeneration ────────
# Le code regenere garde souvent le #include de l'ecran ORPHELIN ; le
# detecteur (header-based) recreait la boite, et la resolution « led » du
# swap s'y reappliquait. Pire : la cle ecrite pour l'ecran etait ('', '5V')
# (pins[0] d'un composant I2C = VCC), et TOUT composant alimente la
# matchait — le DHT11 devenait une LED avec la pull-up de son ancien role.

REGEN_CODE = """#include <DHT.h>
#include <Wire.h>
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#define DHTPIN 2
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);
void setup() { Serial.begin(9600); dht.begin(); }
void loop() { float t = dht.readTemperature(); Serial.print(t); }
"""


def test_the_swap_key_is_a_signal_never_a_power_rail():
    from ui.wiring.ambiguity_dialog import _arduino_signal_pin
    from ui.wiring.layout import pipeline as _v2
    nl = _v2.analyze_netlist(CODE, BOARD)
    oled = next(c for c in nl.components if c.type == "oled_ssd1306")
    net = _arduino_signal_pin(oled, nl)
    assert net not in ("5V", "3V3", "GND", "VIN"), net
    assert net and (net.startswith("A") or net.startswith("D")), net


def test_a_pot_pin_named_A_on_the_rail_is_not_the_signal():
    """Deuxieme porte de la meme pathologie (QA AC2, 2026-08-31) : la broche
    « A » d'un POTENTIOMETRE est sa patte 5V (« A » = premiere patte, pas
    anode). `pin("A")` gagnait sans regarder le net -> titre de modale
    « Broche 5V » et cle de resolution ('', '5V'), que tout composant
    alimente matche."""
    from ui.wiring.markers import extract_netlist
    from ui.wiring.ambiguity_dialog import _arduino_signal_pin
    code = ("#define POT_PIN 3\n"
            "void setup() { pinMode(POT_PIN, INPUT); }\n"
            "void loop() { int v = analogRead(POT_PIN); }\n")
    nl = extract_netlist(code, BOARD)
    pot = next(c for c in nl.components if c.type == "potentiometer")
    # Preconception du piege : la broche « A » du pot EST sur le rail.
    assert pot.pin("A") is not None and pot.pin("A").net == "5V", pot.pins
    assert _arduino_signal_pin(pot, nl) == "A3", _arduino_signal_pin(pot, nl)


def test_a_banned_orphan_include_does_not_rebuild_the_box():
    from ui.wiring.markers import extract_netlist
    # Sans suppression : l'include orphelin suffit a faire naitre l'ecran
    # (caracterisation du fantome).
    types0 = [c.type for c in extract_netlist(REGEN_CODE, BOARD).components]
    assert "oled_ssd1306" in types0, types0
    # Avec l'en-tete supprime (lib bannie) : plus de boite.
    nl = extract_netlist(
        REGEN_CODE, BOARD,
        suppressed_headers=frozenset({"Adafruit_SSD1306.h"}))
    types1 = [c.type for c in nl.components]
    assert "oled_ssd1306" not in types1, types1
    assert "dht11" in types1, types1


def test_after_the_regen_the_schema_heals():
    """Bout en bout : swap ecran -> LED, bans poses (regen acceptee), puis
    reouverture sur le code regenere aux includes orphelins. Attendu : le
    DHT11 est toujours un DHT11 (la cle du swap ne matche plus tout ce qui
    touche 5V) et l'ecran remplace n'existe plus (ni oled, ni led fantome).
    Avant les correctifs, ce scenario rendait DEUX LEDs — dont une a la
    place du DHT, heritee via la cle ('', '5V')."""
    sv = _studio()
    _drive(sv, scoped_to_ref=_OLED_REF)      # ecrit la resolution du swap
    assert all(k[1] != "5V" for k in sv._wiring_resolutions), \
        sv._wiring_resolutions
    sv._features[0].banned_lib_ids = ["adafruit-ssd1306"]
    try:
        nl = sv._resolve_wiring_netlist(REGEN_CODE, BOARD, PROMPT, "", {})
        types = [c.type for c in (nl.components if nl else [])]
        assert "dht11" in types, types
        assert "oled_ssd1306" not in types, types
        assert "led" not in types, types
    finally:
        sv._features[0].banned_lib_ids = []
        sv._wiring_resolutions = {}


def test_a_stepdir_driver_swap_asks_nothing():
    """Exemption #84, rattrapee en QA AD1 (2026-08-31) : la generalisation
    << deux portes >> voyait a4988 -> drv8825 comme un swap de puce ordinaire
    et posait la popup << le code decrit encore un a4988 >> -- FAUSSE, le
    code AccelStepper est agnostique au driver. Un swap entre drivers
    step/dir ne demande RIEN, quelle que soit la porte."""
    from ui.wiring.netlist import Component, Netlist, Pin
    sv = _studio()

    def _drv(t):
        return Component(ref="U9", type=t,
                         pins=[Pin("STEP", "D3"), Pin("DIR", "D4")],
                         attributes={"signature_detected": True})
    nl_before = Netlist(board_id=BOARD, components=[_drv("a4988")])
    nl_after = Netlist(board_id=BOARD, components=[_drv("drv8825")])
    sv._open_wiring_dialog = types.SimpleNamespace(_netlist=nl_before)
    sv._pending_regen_swap = None
    calls: list[tuple[str, str]] = []
    orig_confirm = sv._confirm_regen_after_swap
    sv._confirm_regen_after_swap = (
        lambda o, n: calls.append((o, n)) or False)
    sv._resolve_wiring_netlist = lambda *a, **k: nl_after
    try:
        sv._resolve_wiring_netlist_tracked(
            CODE, BOARD, PROMPT, "", {}, force_remodal=True,
            scoped_to_ref="U9")
    finally:
        sv._confirm_regen_after_swap = orig_confirm
        del sv._resolve_wiring_netlist   # retire l'ombre d'instance
    # Temoin que le test PEUT echouer : la cible de regen existe bien pour
    # cette paire -- seule l'exemption la neutralise.
    from ui.studio_view import _chip_swap_regen_target
    assert _chip_swap_regen_target("a4988", "drv8825") == "drv8825"
    assert calls == [], calls


TESTS = [
    test_the_gear_door_offers_the_regeneration,
    test_the_edit_all_door_offers_it_too,
    test_an_unchanged_signature_component_asks_nothing,
    test_the_swap_key_is_a_signal_never_a_power_rail,
    test_a_pot_pin_named_A_on_the_rail_is_not_the_signal,
    test_a_banned_orphan_include_does_not_rebuild_the_box,
    test_after_the_regen_the_schema_heals,
    test_a_stepdir_driver_swap_asks_nothing,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()

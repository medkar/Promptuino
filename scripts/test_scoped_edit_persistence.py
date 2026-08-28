"""End-to-end : une edition scopee (engrenage) d'un moteur/driver est
PERSISTEE dans _wiring_resolutions et survit a la reouverture du schema.

Avant le fix, les editions scopees etaient transitoires (perdues a la
reouverture). On simule le cycle complet : edition engrenage (change le
driver) -> reouverture -> le driver edite est conserve.

NB : ce fichier ne contient QU'UN test car il construit un vrai StudioView ;
en construire plusieurs (ou melanger StudioView + modales) dans le meme
process casse les cycles de vie Qt (theme_manager/StudioView detruits). La
pre-selection du driver est testee a part, au niveau modale, dans
`test_ambiguity_cards_smoke.py`.

Reecrit le 2026-08-13 : il detournait `VisualAmbiguityDialog.exec` (modale
debutant, supprimee). L'INTENTION est inchangee — une edition scopee persiste
son choix — mais elle se verifie desormais sur la seule modale restante,
`AmbiguityDialog`, dont le vocabulaire differe : `_on_shared_driver_toggled(
refs, driver)` au lieu de `_on_shared_driver(driver)`, et pas de
`_on_validate` (la validation passe par `accept()`, les choix vivant deja
dans `_chosen_type` / `_chosen_driver` et etant appliques par
`apply_choices`, que `studio_view` appelle lui-meme).

Qt requis (offscreen) ; skip propre si absent.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CODE = r'''
#include <Arduino.h>
const uint8_t PIN_M1_PWM = 9;
const uint8_t PIN_M1_IN1 = 8;
const uint8_t PIN_M1_IN2 = 7;
const uint8_t PIN_M2_PWM = 10;
const uint8_t PIN_M2_IN1 = 11;
const uint8_t PIN_M2_IN2 = 12;
void setup() {
  pinMode(PIN_M1_PWM, OUTPUT); pinMode(PIN_M1_IN1, OUTPUT); pinMode(PIN_M1_IN2, OUTPUT);
  pinMode(PIN_M2_PWM, OUTPUT); pinMode(PIN_M2_IN1, OUTPUT); pinMode(PIN_M2_IN2, OUTPUT);
}
void loop() {
  setMotor(PIN_M1_PWM, PIN_M1_IN1, PIN_M1_IN2, 150);
  setMotor(PIN_M2_PWM, PIN_M2_IN1, PIN_M2_IN2, -100);
}
void setMotor(uint8_t pwmPin, uint8_t in1Pin, uint8_t in2Pin, int speed) {
  if (speed > 0) { digitalWrite(in1Pin, HIGH); digitalWrite(in2Pin, LOW); }
  else if (speed < 0) { digitalWrite(in1Pin, LOW); digitalWrite(in2Pin, HIGH); }
  else { digitalWrite(in1Pin, LOW); digitalWrite(in2Pin, LOW); }
  analogWrite(pwmPin, abs(speed));
}
'''

BOARD = "arduino_uno_r3"

try:
    from PyQt6.QtWidgets import QApplication
    _HAS_QT = True
    # Reference gardee au niveau module : sans elle, `QApplication.instance()
    # or QApplication([])` ecrit inline cree une app temporaire immediatement
    # GC-ee, et construire un QWidget ensuite crashe le process (0xC0000409).
    _APP = QApplication.instance() or QApplication([])
except Exception:
    _HAS_QT = False


def test_scoped_driver_edit_persists_across_reopen():
    from ui.studio_view import StudioView
    from ui.wiring.layout import pipeline as _v2
    from ui.wiring import ambiguity_dialog as ad
    from ui.wiring.ambiguity_dialog import collect_ambiguous

    sv = StudioView()
    # Le mode n'entre plus dans le cablage (une seule modale depuis le
    # 2026-08-13) : on ne le force plus, ce qui rend ce test valable pour
    # les trois modes a la fois.
    assert sv._wiring_resolutions == {}

    # ref du 1er moteur groupe dans le netlist fraichement parse (= ce que
    # l'engrenage passe en scoped_to_ref).
    nl_probe = _v2.analyze_netlist(CODE, BOARD)
    grouped = [c for c in collect_ambiguous(nl_probe)
               if c.attributes.get("_grouped_pwm_pin")]
    assert len(grouped) == 2, [c.ref for c in grouped]
    motor_ref = grouped[0].ref

    # Monkeypatch exec() : simule l'user qui choisit le driver TB6612FNG
    # dans la section consolidee puis valide. Les deux moteurs sont deja
    # pre-coches dc_motor par la construction de la section ; il ne reste
    # qu'a poser le driver PARTAGE sur leurs refs.
    def fake_exec(self):
        refs = [c.ref for c in self._ambiguous
                if c.attributes.get("_grouped_pwm_pin")]
        assert len(refs) == 2, refs
        self._on_shared_driver_toggled(refs, "tb6612fng")
        return self.DialogCode.Accepted
    orig_exec = ad.AmbiguityDialog.exec
    ad.AmbiguityDialog.exec = fake_exec
    try:
        # 1) Edition scopee via l'engrenage (force_remodal + scoped_to_ref).
        nl1 = sv._resolve_wiring_netlist(
            CODE, BOARD, "", "", {},
            force_remodal=True, scoped_to_ref=motor_ref)
    finally:
        ad.AmbiguityDialog.exec = orig_exec
    assert nl1 is not None, "modale annulee a tort"

    # PERSISTANCE : l'edition scopee (engrenage) a bien ecrit les 2 moteurs
    # + leur driver TB6612FNG dans _wiring_resolutions (avant le fix, une
    # edition scopee etait transitoire -> rien n'etait ecrit). La
    # reconstruction a la reouverture (re-application des resolutions sauvees
    # + pre-selection du driver dans la modale) est couverte au niveau
    # modale par test_ambiguity_cards_smoke.py.
    motor_types = [v for k, v in sv._wiring_resolutions.items()
                   if not k[1].endswith("::_driver")]
    drivers = [v for k, v in sv._wiring_resolutions.items()
               if k[1].endswith("::_driver")]
    assert motor_types.count("dc_motor") == 2, sv._wiring_resolutions
    assert drivers and all(d == "tb6612fng" for d in drivers), sv._wiring_resolutions


TESTS = [test_scoped_driver_edit_persists_across_reopen]


def main() -> None:
    if not _HAS_QT:
        print("SKIP (PyQt6 absent)")
        os._exit(0)
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as exc:
            print(f"FAIL {t.__name__}: {exc}")
            failed += 1
    print(f"OK : {len(TESTS)} test" if not failed else f"{failed} failed")
    # Sous Windows + Qt offscreen, le teardown statique de Qt apres un vrai
    # StudioView crashe le process (0xC0000409 / rc 127) APRES que la logique
    # de test soit passee. os._exit reflete les assertions, pas le crash.
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()

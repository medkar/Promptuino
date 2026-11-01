import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.wiring.netlist import Component, Pin
from ui.wiring.replacement_ui import build_replacement_choices


def _comp(type_id):
    return Component(ref="U1", type=type_id, fn_id="fn-1",
                     pins=[Pin("VCC", "5V"), Pin("GND", "GND"),
                           Pin("SDA", "A4"), Pin("SCL", "A5")])


def test_screen_only_proposes_screens():
    # type WIRING reel d'un ecran detecte (cf. markers._add("oled_ssd1306", ...)).
    ids = [t for t, _ in build_replacement_choices(_comp("oled_ssd1306"))]
    # Que des ecrans (famille 'ecran'), pas les autres peripheriques I2C.
    assert ids[0] == "oled_ssd1306"
    assert "sh1106" in ids
    # Un capteur I2C hors famille ecran ne doit PAS apparaitre.
    assert "bme280" not in ids and "adafruit-bme280" not in ids, ids


def test_generic_output_keeps_electrical_category():
    # Une LED (pas de famille fonctionnelle) garde la categorie electrique.
    led = Component(ref="D1", type="led", fn_id="fn-1", pins=[Pin("A", "D3")])
    ids = [t for t, _ in build_replacement_choices(led)]
    assert "led" in ids
    assert any(x in ids for x in ("buzzer", "relay", "neopixel")), ids


def test_order_is_deterministic_across_hash_seeds():
    # Revue 2026-07-29 #3 : functions_of_component renvoie un set — itere tel
    # quel, l'ordre des candidats changeait a chaque lancement (PYTHONHASHSEED).
    # On verifie l'ordre d'un composant MULTI-familles (bme280 = temperature +
    # pression + humidite) dans des sous-processus a seeds differents.
    import os
    import subprocess
    snippet = (
        "import sys; sys.path.insert(0, r'%s');"
        "from ui.wiring.netlist import Component, Pin;"
        "from ui.wiring.replacement_ui import build_replacement_choices;"
        "c = Component(ref='U1', type='bme280', fn_id='fn-1',"
        "              pins=[Pin('VCC','5V'), Pin('GND','GND'),"
        "                    Pin('SDA','A4'), Pin('SCL','A5')]);"
        "print([t for t, _ in build_replacement_choices(c)])"
    ) % str(Path(__file__).resolve().parents[1])
    outs = []
    for seed in ("1", "2", "42"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        r = subprocess.run([sys.executable, "-c", snippet],
                           capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
        outs.append(r.stdout.strip())
    assert outs[0] == outs[1] == outs[2], outs


TESTS = [test_screen_only_proposes_screens,
         test_generic_output_keeps_electrical_category,
         test_order_is_deterministic_across_hash_seeds]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

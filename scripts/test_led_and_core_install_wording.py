"""Deux textes que lit un debutant (2026-11-07).

1. Instructions d'une LED : « anode → D7 » puis « resistance entre D7 et A »,
   lu a la lettre, branche la LED directement sur D7 et rend la resistance
   inutile. L'anode doit nommer la resistance.
2. Premier televersement : l'installation du coeur Arduino versait des
   dizaines de barres de progression collees dans le journal.
"""
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LED = ("void setup(){ pinMode(7, OUTPUT); }\n"
       "void loop(){ digitalWrite(7, HIGH); delay(500); digitalWrite(7, LOW); delay(500); }\n")


def _steps(lang):
    from ui.wiring.layout.pipeline import analyze_netlist
    from ui.wiring.instructions import render_instructions
    nl = analyze_netlist(LED, "arduino_uno_r3", prompt="LED sur D7")
    md = render_instructions(nl, lang=lang)
    return [l for l in md.splitlines() if l[:2] in ("1.", "2.")]


def test_the_led_anode_goes_to_the_resistor_in_every_language():
    mots = {"fr": "résistance R1", "en": "resistor R1",
            "es": "resistencia R1", "it": "resistenza R1"}
    for lang, mot in mots.items():
        led = next(l for l in _steps(lang) if "D1" in l and ("anode" in l or "nodo" in l))
        assert mot in led and "D7" in led, (lang, led)
        assert "→ **D7**" not in led, (lang, led)


def test_the_resistor_step_still_spans_d7_and_the_led():
    r = next(l for l in _steps("fr") if "R1" in l and "220" in l)
    assert "D7" in r and "LED D1" in r, r


SORTIE = ("Downloading packages...\r\n"
          "arduino:avr-gcc@7.3.0 0 B / 50.09 MiB 0.00%\r"
          "arduino:avr-gcc@7.3.0 12.79 MiB / 50.09 MiB 25.54% 00m02s\r"
          "arduino:avr-gcc@7.3.0 downloaded\n"
          "arduino:avrdude@8.0.0 1.80 MiB / 1.80 MiB 100.00%\r\n"
          "Installing arduino:avr-gcc@7.3.0...\n"
          "Configuring tool.\n"
          "arduino:avr-gcc@7.3.0 installed\n"
          "Installing platform arduino:avr@1.8.8...\n"
          "Configuring platform.\n"
          "Platform arduino:avr@1.8.8 installed\n"
          "Platform arduino:avr@1.8.8 installed\n")


def test_a_successful_core_install_is_summarized():
    from ui.arduino_cli import summarize_core_install
    out = summarize_core_install(SORTIE)
    assert out.splitlines() == ["arduino:avr-gcc@7.3.0 installed",
                                "Platform arduino:avr@1.8.8 installed"], out
    assert "%" not in out and "MiB" not in out


def test_a_failed_install_still_shows_everything():
    src = (ROOT / "ui" / "arduino_cli.py").read_text(encoding="utf-8")
    assert "install_out if not ok" in src


TESTS = [test_the_led_anode_goes_to_the_resistor_in_every_language,
         test_the_resistor_step_still_spans_d7_and_the_led,
         test_a_successful_core_install_is_summarized,
         test_a_failed_install_still_shows_everything]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t(); print("PASS", t.__name__)
        except Exception as e:  # noqa: BLE001
            failed += 1; print("FAIL", t.__name__, repr(e)[:300])
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} OK")
    raise SystemExit(1 if failed else 0)

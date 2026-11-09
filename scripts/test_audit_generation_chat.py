"""Audit 2026-11-06, lot « generation + chat » : un test par constat corrige.

Run : python scripts/test_audit_generation_chat.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.generation.assembler import assemble, clean_feature_contributions
from ui.generation.feature_model import Feature, declared_name
from ui.generation.gen_prompts import build_context_summary
from ui.generation.pin_reassign import reassign_conflicting_pins
from ui.generation.splicer import splice_add, splice_replace
from ui.chat.chat_heuristics import is_off_scope

_ALIVE: list = []


# ── 1. Nouvelle conversation pendant un streaming ────────────────

def test_reset_during_stream_leaves_the_chat_usable():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    _ALIVE.append(app)
    from ui.chat.chat_controller import ChatController
    from ui.chat.chat_message import ChatMessage
    from ui.chat.chat_view import ChatView, _StreamWorker

    class _B:
        name = "Mock"

        def chat_stream(self, system, messages):
            yield "x"

        def chat(self, system, messages):
            return "x"

        def cancel(self):
            pass

    ctrl = ChatController(backend=_B(), user_mode="beginner")
    v = ChatView(ctrl)
    _ALIVE.append(v)
    ctrl.commit_streamed_turn("q1", "a1")
    v._rebuild_conversation()
    # Etat d'un stream en cours : indicateur, bulle, worker (non demarre).
    v._show_typing_indicator()
    v._streaming_bubble = ChatMessage(role="assistant", text="par",
                                      dark_theme=True)
    v._conv_lay.insertWidget(v._conv_lay.count() - 1, v._streaming_bubble)
    v._worker = _StreamWorker(ctrl.backend, "s", [], parent=v)
    v._set_streaming_ui(True)
    v._abort_stream()
    v._rebuild_conversation()
    assert v._worker is None
    assert v._streaming_bubble is None
    assert v._typing_indicator is None
    assert v._input.isEnabled(), "saisie restee grisee"
    # Les chemins qui plantaient ne levent plus.
    v._on_chunk("suite")
    v._on_stream_done("")
    v._on_stop_clicked()


# ── 4/5. Pas de second worker ────────────────────────────────────

def test_no_second_stream_while_one_runs():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    _ALIVE.append(app)
    from ui.chat.chat_controller import ChatController
    from ui.chat.chat_view import ChatView, _StreamWorker

    class _B:
        name = "Mock"

        def chat_stream(self, system, messages):
            yield "x"

        def chat(self, system, messages):
            return "x"

        def cancel(self):
            pass

    ctrl = ChatController(backend=_B(), user_mode="beginner")
    v = ChatView(ctrl)
    _ALIVE.append(v)
    started = []
    v._start_stream = lambda d: started.append(d)   # type: ignore
    w = _StreamWorker(ctrl.backend, "s", [], parent=v)
    v._worker = w
    v._answer_anyway("Comment faire clignoter une LED ?")
    assert started == [], "_answer_anyway a lance un 2e flux"
    v._input.setPlainText("une autre question")
    v._on_send_clicked()
    assert started == [], "_on_send_clicked a lance un 2e flux"
    assert v._input.toPlainText() == "une autre question"
    # Changer de modele / langue en plein stream ne rouvre pas la saisie.
    v._set_streaming_ui(True)
    v.set_backend(ctrl.backend)
    assert not v._input.isEnabled(), "saisie rouverte pendant le stream"
    v._worker = None


# ── 2. Filtre hors-sujet ─────────────────────────────────────────

def test_legit_arduino_questions_are_not_off_scope():
    for q in ("How do I build a weather station with a BME280?",
              "Mon code pour la station meteo ne compile pas",
              "j'ai suivi un tuto YouTube pour le servo, pourquoi il tremble ?",
              "how to print capital letters on the LCD?"):
        assert not is_off_scope(q), q
    assert is_off_scope("quelle est la capitale de l'Italie ?")
    assert is_off_scope("what is the capital of France")
    assert is_off_scope("quel temps fera-t-il a Paris ?")


# ── 3. Guillemets dans les blocs de code ─────────────────────────

def test_code_block_quotes_are_not_double_escaped():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    _ALIVE.append(app)
    from ui.chat.chat_message import ChatMessage
    m = ChatMessage(role="assistant",
                    text='```cpp\nSerial.println("Bonjour");\n```',
                    dark_theme=True)
    _ALIVE.append(m)
    plain = m._browser.toPlainText()
    assert "&quot;" not in plain, plain
    assert 'Serial.println("Bonjour");' in plain, plain


# ── 6. Initialiseur multi-ligne ──────────────────────────────────

_KEYS = ["char keys[2][2] = {", "  {'1','2'},", "  {'3','4'}", "};"]


def test_multiline_initializer_is_deduplicated_as_a_whole():
    a = Feature(id="f1", prompt="", global_lines=list(_KEYS))
    b = Feature(id="f2", prompt="", global_lines=list(_KEYS))
    out = assemble([a, b])
    assert out.count("{'1','2'},") == 1, out
    assert out.count("};") == 1, out
    cleaned = clean_feature_contributions(b, [a])
    assert cleaned.global_lines == [], cleaned.global_lines


def test_struct_member_is_not_stripped_by_a_global_of_the_same_name():
    a = Feature(id="f1", prompt="", global_lines=["int count;"])
    b = Feature(id="f2", prompt="", global_lines=[
        "struct S {", "  int count;", "};"])
    out = assemble([a, b])
    assert "struct S {" in out and out.count("int count;") == 2, out


# ── 7. Objet global construit avec arguments ─────────────────────

def test_constructed_global_is_deduplicated_and_reported():
    assert declared_name("LiquidCrystal_I2C lcd(0x27, 16, 2);") == "lcd"
    assert declared_name("DHT dht(DHTPIN, DHTTYPE);") == "dht"
    assert declared_name("delay(1000);") is None
    assert declared_name("else if (x) {") is None
    line = "LiquidCrystal_I2C lcd(0x27, 16, 2);"
    a = Feature(id="f1", prompt="", global_lines=[line])
    b = Feature(id="f2", prompt="", global_lines=[line])
    assert assemble([a, b]).count(line) == 1
    assert "lcd" in build_context_summary([a])


# ── 8. Constantes qui ne sont pas des broches ────────────────────

class _Board:
    def pins(self):
        return [f"D{n}" for n in range(2, 14)]

    def has_pin(self, t):
        return t in self.pins()

    def has_capability(self, t, c):
        return c in ("digital", "pwm") and self.has_pin(t)


def test_non_pin_constants_are_left_alone():
    a = Feature(id="f1", prompt="", global_lines=["const int PIN_LED = 3;"],
                loop_lines=["digitalWrite(PIN_LED, HIGH);"])
    b = Feature(id="f2", prompt="", global_lines=["const int NB_BIPS = 3;",
                                                  "const int PIN_BUZ = 5;"],
                loop_lines=["for (int i = 0; i < NB_BIPS; i++) tone(PIN_BUZ, 440);"])
    r = reassign_conflicting_pins(b, [a], _Board())
    assert r.moves == [] and r.warnings == [], (r.moves, r.warnings)
    assert "const int NB_BIPS = 3;" in r.feature.global_lines
    c = Feature(id="f3", prompt="", global_lines=["int etat = 0;"],
                loop_lines=["etat = digitalRead(7);"])
    d = Feature(id="f4", prompt="", global_lines=["int compteur = 0;"],
                loop_lines=["compteur++;"])
    r = reassign_conflicting_pins(d, [c], _Board())
    assert r.warnings == [] and r.moves == [], r.warnings


# ── 9. Modifier ne touche que les lignes de la fonctionnalite ────

_SKETCH = """const int L = 13;
const int BUZ = 5;

void setup() {
  pinMode(L, OUTPUT);
}

void loop() {
  digitalWrite(L, HIGH);
  delay(1000);
  digitalWrite(L, LOW);
  delay(1000);
  // note de l'eleve
  if (digitalRead(2) == LOW) {
    tone(BUZ, 440);
    delay(1000);
  }
}
"""


def test_replace_removes_only_the_old_feature_lines():
    old = Feature(id="f2", prompt="", loop_lines=[
        "if (digitalRead(2) == LOW) {", "  tone(BUZ, 440);",
        "  delay(1000);", "}"])
    new = Feature(id="f2", prompt="", loop_lines=["tone(BUZ, 880);"])
    out = splice_replace(_SKETCH, old, new)
    assert out.count("delay(1000);") == 2, out
    assert "digitalWrite(L, LOW);" in out
    assert "tone(BUZ, 880);" in out and "tone(BUZ, 440);" not in out


# ── 10. Modifier une constante change bien sa valeur ─────────────

def test_replace_applies_a_changed_constant_value():
    old = Feature(id="f2", prompt="", global_lines=["const int BUZ = 5;"],
                  loop_lines=["tone(BUZ, 440);"])
    new = Feature(id="f2", prompt="", global_lines=["const int BUZ = 6;"],
                  loop_lines=["tone(BUZ, 440);"])
    code = ("const int BUZ = 5;\n\nvoid setup() {\n}\n\n"
            "void loop() {\n  tone(BUZ, 440);\n}\n")
    out = splice_replace(code, old, new)
    assert "const int BUZ = 6;" in out and "BUZ = 5" not in out, out
    assert out.count("const int BUZ") == 1


TESTS = [
    test_reset_during_stream_leaves_the_chat_usable,
    test_no_second_stream_while_one_runs,
    test_legit_arduino_questions_are_not_off_scope,
    test_code_block_quotes_are_not_double_escaped,
    test_multiline_initializer_is_deduplicated_as_a_whole,
    test_struct_member_is_not_stripped_by_a_global_of_the_same_name,
    test_constructed_global_is_deduplicated_and_reported,
    test_non_pin_constants_are_left_alone,
    test_replace_removes_only_the_old_feature_lines,
    test_replace_applies_a_changed_constant_value,
]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed")
    return 1 if failed else 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)

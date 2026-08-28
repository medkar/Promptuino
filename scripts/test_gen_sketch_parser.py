"""Tests for the SLM mini-sketch parser (ui/generation/sketch_parser.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.generation.sketch_parser import parse_sketch, SketchParseError


FULL = """#include <Servo.h>
Servo myServo;
const int LED = 13;
void setup() {
  pinMode(LED, OUTPUT);
  myServo.attach(9);
}
void loop() {
  blink();
}
void blink() {
  digitalWrite(LED, HIGH);
}
"""


def test_parse_includes():
    assert parse_sketch(FULL).includes == ["#include <Servo.h>"]


def test_parse_globals():
    c = parse_sketch(FULL)
    assert "Servo myServo;" in c.global_lines
    assert "const int LED = 13;" in c.global_lines


def test_parse_setup_lines():
    c = parse_sketch(FULL)
    assert c.setup_lines == ["pinMode(LED, OUTPUT);", "myServo.attach(9);"]


def test_parse_loop_lines():
    assert parse_sketch(FULL).loop_lines == ["blink();"]


def test_parse_functions_excludes_setup_loop():
    c = parse_sketch(FULL)
    assert [f.name for f in c.functions] == ["blink"]
    assert "digitalWrite(LED, HIGH);" in c.functions[0].code


def test_parse_include_directly_before_function():
    """An #include with NO ';'-terminated statement between it and the function
    must NOT be swallowed into the function's signature span. Regression:
    `#include <Wire.h>` right before `void setup()` (with `// FEATURE:` above)
    was carved away with the function span and LOST — generated sketches then
    failed to compile (Wire used, header absent). Hit gemma AND Claude, since
    both place the include directly before setup()."""
    sketch = (
        "// FEATURE: Scanner I2C\n"
        "#include <Wire.h>\n"
        "\n"
        "void setup() {\n"
        "  Wire.begin();\n"
        "}\n"
        "void loop() {\n"
        "  Wire.beginTransmission(1);\n"
        "}\n"
    )
    c = parse_sketch(sketch)
    assert c.includes == ["#include <Wire.h>"], c.includes
    assert c.setup_lines == ["Wire.begin();"], c.setup_lines
    assert c.loop_lines == ["Wire.beginTransmission(1);"], c.loop_lines


def test_parse_multiple_includes_directly_before_function():
    sketch = "#include <Wire.h>\n#include <SPI.h>\nvoid setup() {}\n"
    c = parse_sketch(sketch)
    assert c.includes == ["#include <Wire.h>", "#include <SPI.h>"], c.includes


def test_parse_define_directly_before_function_not_lost():
    # A #define (no ';') directly before the function must reach globals, not be
    # swallowed into the function span.
    sketch = "#define ADDR 0x3C\nvoid setup() { begin(ADDR); }\n"
    c = parse_sketch(sketch)
    assert "#define ADDR 0x3C" in c.global_lines, c.global_lines
    assert c.setup_lines == ["begin(ADDR);"], c.setup_lines


def test_parse_strips_markdown_fence():
    fenced = "```cpp\nvoid loop() { foo(); }\n```"
    assert parse_sketch(fenced).loop_lines == ["foo();"]


def test_parse_feature_without_setup_or_loop():
    # A feature may contribute only a function + one loop line
    c = parse_sketch("void buzz() { tone(8, 440); }")
    assert [f.name for f in c.functions] == ["buzz"]
    assert c.setup_lines == []
    assert c.loop_lines == []


def test_parse_empty_raises():
    try:
        parse_sketch("   \n  \n")
        assert False, "devait lever SketchParseError"
    except SketchParseError:
        pass


def test_parse_prose_raises():
    try:
        parse_sketch("Je ne peux pas générer ce code, désolé.")
        assert False, "devait lever SketchParseError"
    except SketchParseError:
        pass


def test_parse_multiline_global_array_kept_whole():
    # A multi-line global array (melody) must not lose ANY line — the middle
    # line has neither ';' nor '{' nor '#'.
    sketch = (
        "int melody[] = {\n"
        "  262, 294, 330\n"
        "};\n"
        "void loop() {\n"
        "  tone(8, melody[0]);\n"
        "}\n"
    )
    c = parse_sketch(sketch)
    joined = "\n".join(c.global_lines)
    assert "int melody[] = {" in joined
    assert "262, 294, 330" in joined        # middle line preserved
    assert "};" in joined


# --- Guard "forgotten setup()/loop() wrappers" for a weak SLM ---------------

# The model emitted feature code as FREE instructions (no void setup()/loop()):
# executable calls must be rescued into setup() (illegal at global scope),
# declarations must stay in globals.
LOOSE = """#include <Wire.h>
#include <Adafruit_SSD1306.h>
const int PIN_LED_EXTRA = 8;
pinMode(PIN_LED_EXTRA, OUTPUT);
digitalWrite(PIN_LED_EXTRA, HIGH);
#define SCREEN_ADDRESS 0x3C
Adafruit_SSD1306 oledDisplay(128, 64, &Wire, -1);
if (!oledDisplay.begin(SSD1306_SWITCHCAPVCC, SCREEN_ADDRESS)) {
}
oledDisplay.clearDisplay();
oledDisplay.display();
"""


def test_rescue_executables_go_to_setup():
    c = parse_sketch(LOOSE)
    # Declarations -> globals
    assert "const int PIN_LED_EXTRA = 8;" in c.global_lines
    assert "#define SCREEN_ADDRESS 0x3C" in c.global_lines
    assert "Adafruit_SSD1306 oledDisplay(128, 64, &Wire, -1);" in c.global_lines
    # Executables -> setup (NOT in globals)
    assert "pinMode(PIN_LED_EXTRA, OUTPUT);" in c.setup_lines
    assert "digitalWrite(PIN_LED_EXTRA, HIGH);" in c.setup_lines
    assert "oledDisplay.clearDisplay();" in c.setup_lines
    assert "oledDisplay.display();" in c.setup_lines
    assert not any("pinMode" in g or "oledDisplay." in g for g in c.global_lines)


def test_rescue_multiline_block_stays_whole_in_setup():
    # The if {...} block redirected to setup must stay WHOLE there (opening +
    # closing), not get split.
    c = parse_sketch(LOOSE)
    joined = "\n".join(c.setup_lines)
    assert "if (!oledDisplay.begin(SSD1306_SWITCHCAPVCC, SCREEN_ADDRESS)) {" in joined
    assert "}" in c.setup_lines


def test_rescue_inactive_when_setup_present():
    # If setup() exists, NO rescue: a multi-line global stays global.
    c = parse_sketch(FULL)
    assert "Servo myServo;" in c.global_lines
    assert "myServo.attach(9);" not in c.global_lines   # bien dans setup()
    assert "myServo.attach(9);" in c.setup_lines


TESTS = [
    test_parse_includes, test_parse_globals, test_parse_setup_lines,
    test_parse_loop_lines, test_parse_functions_excludes_setup_loop,
    test_parse_include_directly_before_function,
    test_parse_multiple_includes_directly_before_function,
    test_parse_define_directly_before_function_not_lost,
    test_parse_strips_markdown_fence, test_parse_feature_without_setup_or_loop,
    test_parse_empty_raises, test_parse_prose_raises,
    test_parse_multiline_global_array_kept_whole,
    test_rescue_executables_go_to_setup,
    test_rescue_multiline_block_stays_whole_in_setup,
    test_rescue_inactive_when_setup_present,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

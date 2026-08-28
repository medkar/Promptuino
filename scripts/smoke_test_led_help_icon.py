"""Smoke test: the LED green "i" help icon (anode/cathode wiring direction).

Verifies end-to-end that a LED component gets a green `_HelpInfoItem` placed
just BELOW the gear (same white-disc format as the gear, an "i" instead of a
gear), that a click opens the localized wiring-direction info modal, and that
it shares the gear's hover-counter visibility. A short tooltip hints at the
click.

Run: python scripts/smoke_test_led_help_icon.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from ui.i18n import lang_manager
from ui.wiring.wiring_diagram_dialog import (
    WiringDiagramDialog, _HelpInfoItem, _GearActionItem, _t,
)
from ui.wiring.layout.pipeline import analyze_netlist

BOARD = "arduino_uno_r3"
LED_CODE = (
    "void setup(){pinMode(8,OUTPUT);}\n"
    "void loop(){digitalWrite(8,HIGH);delay(500);"
    "digitalWrite(8,LOW);delay(500);}\n"
)


class _FakeLeftClick:
    """Minimal stand-in for a QGraphicsSceneMouseEvent (left button)."""
    def button(self):
        return Qt.MouseButton.LeftButton

    def accept(self):
        pass


app = QApplication.instance() or QApplication(sys.argv)

netlist = analyze_netlist(LED_CODE, BOARD, prompt="allumer une LED")
led_refs = [c.ref for c in netlist.components if c.type == "led"]
assert led_refs, f"no LED in netlist (types={[c.type for c in netlist.components]})"
led_ref = led_refs[0]
print("LED ref:", led_ref)

dlg = WiringDiagramDialog(LED_CODE, BOARD, netlist=netlist)
dlg._regenerate()
sv = dlg._schema_view

# 1) A green help "i" item exists for the LED, with the short hover hint.
assert led_ref in sv._help_icon_items, (
    f"no help icon for LED {led_ref} (have {list(sv._help_icon_items)})"
)
help_item = sv._help_icon_items[led_ref]
assert isinstance(help_item, _HelpInfoItem)
expected_hint = _t("led_wiring_help_tooltip", "fr")
assert help_item.toolTip() == expected_hint, help_item.toolTip()
assert "cliquer" in expected_hint.lower(), expected_hint
print("hover hint (fr):", expected_hint)

# 2) The "i" sits BELOW the gear (both 22px discs, gear at top+2).
gear = sv._gear_icon_items.get(led_ref)
assert isinstance(gear, _GearActionItem), "LED should have a gear"
assert help_item.pos().y() > gear.pos().y(), (
    f"help.y={help_item.pos().y()} should be > gear.y={gear.pos().y()}"
)
assert abs(help_item.pos().x() - gear.pos().x()) < 0.01, (
    f"help.x={help_item.pos().x()} vs gear.x={gear.pos().x()}"
)
print(f"gear @({gear.pos().x():.1f},{gear.pos().y():.1f})  "
      f"help @({help_item.pos().x():.1f},{help_item.pos().y():.1f})  OK below")

# 3) Clicking the "i" invokes the help click handler with the LED ref.
assert sv._help_click_fn is not None, "click handler not wired"
# Bound methods are re-created per attribute access, so compare func + self.
assert (sv._help_click_fn.__func__ is dlg._on_help_clicked.__func__
        and sv._help_click_fn.__self__ is dlg), "click handler mismatch"
recorded = []
sv._help_click_fn = lambda r: recorded.append(r)
help_item.mousePressEvent(_FakeLeftClick())
assert recorded == [led_ref], f"click did not fire for {led_ref}: {recorded}"
sv._help_click_fn = dlg._on_help_clicked  # restore
print("click fires _help_click_fn(led_ref): OK")

# 4) The click handler opens a SILENT (NoIcon) modal with the anode/cathode
#    explanation. Patch exec() so nothing blocks, and read back the box.
captured = {}
_orig_exec = QMessageBox.exec


def _fake_exec(self):
    captured.update(title=self.windowTitle(), text=self.text(),
                    icon=self.icon())
    return int(QMessageBox.StandardButton.Ok)


QMessageBox.exec = _fake_exec
try:
    dlg._on_help_clicked(led_ref)
finally:
    QMessageBox.exec = _orig_exec
assert captured.get("title") == _t("led_wiring_help_title", "fr")
body = captured.get("text", "")
assert "anode" in body.lower() and "cathode" in body.lower(), body
assert captured.get("icon") == QMessageBox.Icon.NoIcon, (
    f"popup must be silent (NoIcon), got {captured.get('icon')}"
)
print("modal body (fr), NoIcon (silent):\n  " + body.replace("\n", "\n  "))

# 5) Visibility is shared with the gear (hidden until hover/selection).
assert not help_item.isVisible(), "help icon should start hidden"
sv._on_edit_hover_enter(led_ref)
assert help_item.isVisible() and gear.isVisible(), "hover should reveal both"
sv._edit_hover_counts[led_ref] = 0
sv._refresh_edit_icon(led_ref)
assert not help_item.isVisible(), "leaving hover should hide the help icon"
print("visibility shared with gear: OK")

# 6) Multi-language modal bodies are distinct and non-empty.
for lg, needle in (("en", "long leg"), ("es", "pata larga"),
                   ("it", "gamba lunga")):
    lang_manager.set_language(lg)
    body_lg = _t("led_wiring_help_body", lg)
    assert needle in body_lg, f"[{lg}] '{needle}' missing from: {body_lg!r}"
    print(f"  [{lg}] '{needle}' present: OK")
lang_manager.set_language("fr")

print("\nALL OK — green LED 'i' below the gear, info on click, localized.")

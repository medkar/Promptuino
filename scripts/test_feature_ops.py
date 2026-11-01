"""Helpers purs _strip_feature_metadata / _regen_plan + modele Feature."""
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from ui.generation import Feature
from ui.studio_view import _strip_feature_metadata, _regen_plan

def _mk(fid, prompt): return Feature(id=fid, prompt=prompt, summary=prompt)

def test_strip_metadata():
    meta = {("f1", "D5"): "led", ("f2", "D9"): "buzzer", ("f2", "A0"): "ldr"}
    out = _strip_feature_metadata(meta, {"f2"})
    assert out == {("f1", "D5"): "led"}, out

def test_strip_metadata_triple_key():
    meta = {("f1", "D5", "res"): "220", ("f3", "D9", "freq"): 880}
    out = _strip_feature_metadata(meta, {"f3"})
    assert out == {("f1", "D5", "res"): "220"}, out

def test_regen_single():
    t, p = _regen_plan([_mk("f2", "lis le cap")])
    assert t == "f2" and p == "lis le cap", (t, p)

def test_regen_multi_merges():
    t, p = _regen_plan([_mk("f1", "lis le cap"), _mk("f2", "affiche le cap")])
    assert t == ["f1", "f2"] and "lis le cap" in p and "affiche le cap" in p, (t, p)

def test_prompt_history_backfill_and_roundtrip():
    # Construction legacy (prompt seul) -> l'historique est seme avec.
    f = Feature(id="f1", prompt="clignote la LED")
    assert f.prompts == ["clignote la LED"]
    assert f.first_prompt == "clignote la LED"
    # Round-trip to_dict/from_dict conserve l'historique complet.
    f.prompts = ["clignote la LED", "passe-la sur D9"]
    f.prompt = "passe-la sur D9"
    f2 = Feature.from_dict(f.to_dict())
    assert f2.prompts == ["clignote la LED", "passe-la sur D9"], f2.prompts
    assert f2.first_prompt == "clignote la LED"
    # Dict d'un vieux projet (sans cle "prompts") -> backfill depuis prompt.
    legacy = {"id": "f1", "prompt": "vieux prompt"}
    f3 = Feature.from_dict(legacy)
    assert f3.prompts == ["vieux prompt"], f3.prompts

def test_full_prompt_joins_history():
    f = Feature(id="f1", prompt="passe-la sur D9",
                prompts=["clignote la LED", "passe-la sur D9"])
    assert f.full_prompt() == "clignote la LED\n+ passe-la sur D9"
    # Un seul prompt -> pas de jointure.
    assert Feature(id="f2", prompt="un buzzer").full_prompt() == "un buzzer"

def test_regen_plan_uses_full_history():
    f = Feature(id="f1", prompt="passe-la sur D9",
                prompts=["clignote la LED", "passe-la sur D9"])
    t, p = _regen_plan([f])
    assert t == "f1" and "clignote la LED" in p and "passe-la sur D9" in p, (t, p)

def test_label_fallback_uses_first_prompt():
    from ui.generation.gen_prompts import feature_label
    f = Feature(id="f1", prompt="passe-la sur D9", summary="",
                prompts=["clignote la LED", "passe-la sur D9"])
    assert feature_label(f) == "clignote la LED", feature_label(f)
    # Le summary IA garde la priorite quand il existe.
    f.summary = "LED clignotante sur D9"
    assert feature_label(f) == "LED clignotante sur D9"

TESTS = [test_strip_metadata, test_strip_metadata_triple_key, test_regen_single,
         test_regen_multi_merges, test_prompt_history_backfill_and_roundtrip,
         test_full_prompt_joins_history, test_regen_plan_uses_full_history,
         test_label_fallback_uses_first_prompt]
def main():
    f = 0
    for t in TESTS:
        try: t(); print("OK  ", t.__name__)
        except AssertionError as e: f += 1; print("FAIL", t.__name__, e)
    print(f"\n{len(TESTS)-f}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(1 if f else 0)
if __name__ == "__main__": main()

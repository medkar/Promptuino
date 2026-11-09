"""Audit du 2026-11-06 : ecrans IA (ui/ia_view.py, ui/contexte_curseur.py,
ui/chatgpt_section.py). Un test par constat corrige.

Aucun reseau, aucune ecriture dans ~/Documents/Promptuino : la configuration
est un double, les sections ne sont jamais construites par leur `__init__`
quand il lirait le disque.

Run : python scripts/test_audit_ai_screens.py
"""
from __future__ import annotations
import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QApplication, QComboBox, QSlider

_APP = QApplication.instance() or QApplication(sys.argv)


def _molette(widget) -> QWheelEvent:
    ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                     Qt.ScrollPhase.NoScrollPhase, False)
    ev.setAccepted(True)
    QApplication.sendEvent(widget, ev)
    return ev


# ── 1 + 2. une liste ou un curseur sans focus ignore la molette ─────────

def test_a_control_without_focus_ignores_the_wheel():
    from ui.molette import ComboSansMolette, SliderSansMolette
    combo = ComboSansMolette()
    combo.addItems(["a", "b", "c"])
    slider = SliderSansMolette(Qt.Orientation.Horizontal)
    slider.setRange(0, 100)
    slider.setValue(50)
    vus = []
    combo.currentIndexChanged.connect(vus.append)
    slider.valueChanged.connect(vus.append)
    for w in (combo, slider):
        assert not w.hasFocus()
        ev = _molette(w)
        assert ev.isAccepted() is False, "l'evenement doit remonter a la page"
    assert combo.currentIndex() == 0 and slider.value() == 50 and not vus, vus


def test_a_focused_control_still_takes_the_wheel():
    from ui.molette import ComboSansMolette
    combo = ComboSansMolette()
    combo.addItems(["a", "b", "c"])
    combo.show()
    combo.activateWindow()
    combo.setFocus()
    _APP.processEvents()
    if not combo.hasFocus():            # plateforme sans focus : rien a prouver
        print("     (focus indisponible hors ecran : cas ignore)")
        return
    _molette(combo)
    assert combo.currentIndex() == 1


def test_the_ai_tab_controls_all_refuse_the_wheel():
    """Toutes les listes et tous les curseurs de l'onglet (et de la fenetre
    d'accueil ChatGPT) sont des SansMolette -- un nouveau QComboBox nu qui s'y
    glisserait redonnerait le defaut."""
    import re
    from ui.molette import ComboSansMolette, SliderSansMolette
    import ui.ia_view as ia_view, ui.chatgpt_section as cs
    import ui.contexte_curseur as cc
    assert issubclass(ia_view._ModelCombo, ComboSansMolette)
    assert issubclass(cs._ComboModeles, ComboSansMolette)
    for mod in (ia_view, cs, cc):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert not re.search(r"=\s*QComboBox\(\)", src), mod.__name__
        assert not re.search(r"=\s*QSlider\(", src), mod.__name__


# ── Section Cloud : une VRAIE section, ai_config bouchonne ──────────────
# Aucune ecriture disque / trousseau, aucune sonde ni recherche reseau.

class _Rec:
    def __init__(self):
        self.calls = []

    def __call__(self, *a, **k):
        self.calls.append(a)


def _cloud():
    import ui.ia_view as ia_view
    from ui.ai_config import ai_config
    orig = {n: getattr(ai_config, n) for n in
            ("api_key", "model_for", "set_model", "set_api_key")}
    ai_config.api_key = lambda pid: ""
    ai_config.model_for = lambda pid: ""
    ai_config.set_model = _Rec()
    ai_config.set_api_key = _Rec()

    def restore():
        for n, v in orig.items():
            setattr(ai_config, n, v)
    try:
        sec = ia_view._CloudSection()
    except Exception:
        restore()
        raise
    sec._start_model_probe = _Rec()
    sec._start_models_fetch = _Rec()
    return sec, restore


def _choisir(sec, pid, modele):
    i = sec._provider_combo.findData(pid)
    sec._provider_combo.blockSignals(True)
    sec._provider_combo.setCurrentIndex(i)
    sec._provider_combo.blockSignals(False)
    sec._model_combo.blockSignals(True)
    sec._model_combo.setEditText(modele)
    sec._model_combo.blockSignals(False)


# ── 3. un autre modele cloud recree l'instance active ───────────────────

def test_choosing_a_cloud_model_rebuilds_the_active_backend():
    sec, restore = _cloud()
    try:
        _choisir(sec, "gemini", "modele-b")
        vus = []
        sec.activated.connect(lambda: vus.append(1))
        sec.radio.setChecked(False)
        sec._on_model_chosen()
        assert vus == [], "section inactive : rien a recreer"
        sec.radio.setChecked(True)
        sec._on_model_chosen()
        assert vus == [1], "le chat gardait l'ancien modele"
    finally:
        restore()


# ── 4. une nouvelle cle invalide les verdicts de sonde et re-sonde ──────

def test_saving_a_new_key_drops_the_old_probe_verdicts_and_reprobes():
    sec, restore = _cloud()
    try:
        _choisir(sec, "gemini", "gemini-x")
        sec._probed_pairs.add(("gemini", "gemini-x"))
        sec._probe_verdicts[("gemini", "gemini-x")] = (False, "API key not valid")
        sec._probe_verdicts[("openai", "gpt")] = (True, "")     # autre fournisseur
        sec._key_input.setText("bonne-cle")
        sec._on_save()
        assert ("gemini", "gemini-x") not in sec._probe_verdicts,             "le verdict de l'ANCIENNE cle pilote encore la pastille"
        assert ("openai", "gpt") in sec._probe_verdicts, "autre fournisseur intact"
        assert sec._start_model_probe.calls == [("gemini", "gemini-x")],             sec._start_model_probe.calls
        # Cle effacee : verdicts oublies, aucune sonde sans cle.
        sec._start_model_probe.calls.clear()
        sec._probe_verdicts[("gemini", "gemini-x")] = (True, "")
        sec._key_input.setText("")
        sec._on_save()
        assert ("gemini", "gemini-x") not in sec._probe_verdicts
        assert sec._start_model_probe.calls == []
    finally:
        restore()


# ── 5. LM Studio : une autre adresse recree le moteur actif ─────────────

def test_changing_the_lmstudio_url_rebuilds_the_active_engine():
    import ui.ia_view as ia_view
    from PyQt6.QtWidgets import QLineEdit, QWidget

    class _Cfg:
        lmstudio_base_url = "http://127.0.0.1:1234/v1"

    vrai = ia_view.ai_config
    ia_view.ai_config = _Cfg()
    try:
        page = ia_view._LMStudioPage.__new__(ia_view._LMStudioPage)
        QWidget.__init__(page)
        page._url_input = QLineEdit()
        rafraichi = _Rec()
        page.refresh_availability = rafraichi
        vus = []
        page.reglage_change.connect(lambda: vus.append(1))
        # Adresse inchangee : on rafraichit, sans recreer.
        page._url_input.setText("http://127.0.0.1:1234/v1")
        page._on_url_edited()
        assert vus == [] and len(rafraichi.calls) == 1
        # Nouvelle adresse : le chat appelait encore l'ancienne.
        page._url_input.setText("http://127.0.0.1:1235/v1")
        page._on_url_edited()
        assert _Cfg.lmstudio_base_url == "http://127.0.0.1:1235/v1" or             ia_view.ai_config.lmstudio_base_url == "http://127.0.0.1:1235/v1"
        assert vus == [1], vus
    finally:
        ia_view.ai_config = vrai


TESTS = [
    test_choosing_a_cloud_model_rebuilds_the_active_backend,
    test_saving_a_new_key_drops_the_old_probe_verdicts_and_reprobes,
    test_changing_the_lmstudio_url_rebuilds_the_active_engine,
    test_a_control_without_focus_ignores_the_wheel,
    test_a_focused_control_still_takes_the_wheel,
    test_the_ai_tab_controls_all_refuse_the_wheel,
]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()

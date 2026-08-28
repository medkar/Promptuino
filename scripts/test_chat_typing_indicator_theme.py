"""L'indicateur de frappe du chat (« Réflexion en cours… ») suit le thème ET
la langue, et un changement de thème PENDANT un stream est rattrapé à la fin.

Bug d'origine : `_TypingIndicator` figeait `theme_manager.current.signal_ok` et
`lang_manager.current.chat_thinking` à l'instanciation, et ni `_apply_theme` ni
`_apply_lang` de `ChatView` ne le référençaient — contrairement aux 5 autres
usages de RobotLoader/LoaderLabel qui appellent `set_color(c.signal_ok)`. Un
stream peut durer 180 s : basculer le thème pendant ce temps laissait le robot
en #00d9a0 (dark) sur fond clair, et « Réflexion en cours » en français après
un passage en anglais.

Deuxième volet : `_apply_theme` saute délibérément le re-thème de la
conversation pendant un stream (la bulle en cours est référencée par le
worker), mais rien ne le rattrapait ensuite — le gel devenait définitif
jusqu'au prochain toggle fait hors stream.

Runner standalone offscreen : python scripts/test_chat_typing_indicator_theme.py
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg

from PyQt6.QtWidgets import QApplication as _QApplication
_APP = _QApplication.instance() or _QApplication([])

from ui.chat.chat_controller import ChatController
from ui.chat.chat_message import ChatMessage
from ui.chat.chat_view import ChatView, _StreamWorker
from ui.i18n import lang_manager
from ui.theme import theme_manager, DARK, LIGHT

# Prevents Python GC from destroying the QObjects between tests (premature
# destruction -> C++ singletons invalidated through the signal cleanup).
_ALIVE: list = []


def _view() -> ChatView:
    v = ChatView(ChatController(backend=None, user_mode="beginner"))
    _ALIVE.append(v)
    return v


class _Backend:
    name = "Mock"

    def chat_stream(self, system, messages):
        yield "hi"

    def chat(self, system, messages):
        return "hi"

    def cancel(self):
        pass


def _restore(dark: bool, lang: str) -> None:
    if dark:
        theme_manager.apply_dark()
    else:
        theme_manager.apply_light()
    lang_manager.set_language(lang)


# ── 1. Thème ─────────────────────────────────────────────────────

def test_the_typing_indicator_follows_the_theme():
    dark0, lang0 = theme_manager.is_dark, lang_manager.lang
    try:
        theme_manager.apply_dark()
        v = _view()
        v._show_typing_indicator()
        ind = v._typing_indicator
        assert ind is not None
        assert DARK.signal_ok in ind._robot.styleSheet(), ind._robot.styleSheet()

        theme_manager.apply_light()
        assert LIGHT.signal_ok in ind._robot.styleSheet(), (
            f"robot fige : {ind._robot.styleSheet()!r}")
        assert LIGHT.signal_ok in ind._lbl.styleSheet(), (
            f"label fige : {ind._lbl.styleSheet()!r}")
        assert DARK.signal_ok not in ind._robot.styleSheet()
        v._remove_typing_indicator()
    finally:
        _restore(dark0, lang0)


# ── 2. Langue ────────────────────────────────────────────────────

def test_the_typing_indicator_follows_the_language():
    dark0, lang0 = theme_manager.is_dark, lang_manager.lang
    try:
        lang_manager.set_language("fr")
        v = _view()
        v._show_typing_indicator()
        ind = v._typing_indicator
        fr = lang_manager.current.chat_thinking.rstrip("…. ")
        assert fr in ind._lbl.text(), ind._lbl.text()

        lang_manager.set_language("en")
        en = lang_manager.current.chat_thinking.rstrip("…. ")
        assert en != fr, "les deux libelles doivent differer, sinon on ne teste rien"
        assert en in ind._lbl.text(), (
            f"libelle fige : {ind._lbl.text()!r} (attendu {en!r})")
        v._remove_typing_indicator()
    finally:
        _restore(dark0, lang0)


# ── 3. Absent la plupart du temps : ne doit pas planter ──────────

def test_theme_and_language_switches_are_safe_without_an_indicator():
    dark0, lang0 = theme_manager.is_dark, lang_manager.lang
    try:
        v = _view()
        assert v._typing_indicator is None
        theme_manager.toggle()
        lang_manager.set_language("es")
        theme_manager.toggle()
        lang_manager.set_language("it")
        assert v._typing_indicator is None
    finally:
        _restore(dark0, lang0)


def test_an_indicator_created_after_the_switch_is_born_in_the_right_theme():
    dark0, lang0 = theme_manager.is_dark, lang_manager.lang
    try:
        v = _view()
        theme_manager.apply_light()
        lang_manager.set_language("en")
        v._show_typing_indicator()
        ind = v._typing_indicator
        assert LIGHT.signal_ok in ind._robot.styleSheet()
        assert lang_manager.current.chat_thinking.rstrip("…. ") in ind._lbl.text()
        v._remove_typing_indicator()
    finally:
        _restore(dark0, lang0)


# ── 4. Rattrapage du thème à la fin du stream ────────────────────

def _fake_stream(v: ChatView) -> None:
    """Met la vue dans l'etat « stream en cours » sans lancer de thread."""
    v._worker = _StreamWorker(_Backend(), "", [])
    _ALIVE.append(v._worker)
    v._set_streaming_ui(True)


def test_a_theme_switch_during_a_stream_is_caught_up_at_teardown():
    dark0, lang0 = theme_manager.is_dark, lang_manager.lang
    try:
        theme_manager.apply_dark()
        v = _view()
        v.controller.history.append({"role": "user", "content": "salut", "ts": "t"})
        v._rebuild_conversation()
        _fake_stream(v)

        theme_manager.apply_light()
        # Deliberately frozen while the worker is alive.
        bubbles = [v._conv_lay.itemAt(i).widget()
                   for i in range(v._conv_lay.count())]
        bubbles = [b for b in bubbles if isinstance(b, ChatMessage)]
        assert bubbles and all(b._dark for b in bubbles), (
            "le re-theme ne doit PAS avoir lieu pendant le stream")
        assert v._theme_catchup_pending is True

        v._teardown_stream()
        bubbles = [v._conv_lay.itemAt(i).widget()
                   for i in range(v._conv_lay.count())]
        bubbles = [b for b in bubbles if isinstance(b, ChatMessage)]
        assert bubbles, "la conversation ne doit pas etre videe"
        assert not any(b._dark for b in bubbles), (
            "thème fige apres la fin du stream")
        assert v._theme_catchup_pending is False
    finally:
        _restore(dark0, lang0)


def test_the_catch_up_keeps_the_bubbles_that_are_not_in_the_history():
    """Le rattrapage ne doit pas manger la bulle d'erreur / de redirection
    ajoutee juste avant la fin du stream (elle n'est pas dans l'historique)."""
    dark0, lang0 = theme_manager.is_dark, lang_manager.lang
    try:
        theme_manager.apply_dark()
        v = _view()
        v.controller.history.append({"role": "user", "content": "salut", "ts": "t"})
        v._rebuild_conversation()
        _fake_stream(v)
        theme_manager.apply_light()
        v._append_temp_bubble("assistant", "erreur backend", is_error=True)

        v._teardown_stream()
        bubbles = [v._conv_lay.itemAt(i).widget()
                   for i in range(v._conv_lay.count())]
        bubbles = [b for b in bubbles if isinstance(b, ChatMessage)]
        texts = [b.text for b in bubbles]
        assert "erreur backend" in texts, (
            f"bulle hors historique perdue : {texts}")
        assert "salut" in texts, texts
        assert not any(b._dark for b in bubbles), texts
        assert [b.is_error for b in bubbles if b.text == "erreur backend"] == [True]
    finally:
        _restore(dark0, lang0)


def test_the_catch_up_is_idempotent_and_free_when_nothing_was_missed():
    dark0, lang0 = theme_manager.is_dark, lang_manager.lang
    try:
        theme_manager.apply_dark()
        v = _view()
        v.controller.history.append({"role": "user", "content": "salut", "ts": "t"})
        v._rebuild_conversation()
        before = [v._conv_lay.itemAt(i).widget()
                  for i in range(v._conv_lay.count())]
        assert v._theme_catchup_pending is False
        v._catch_up_theme_after_stream()
        v._catch_up_theme_after_stream()
        after = [v._conv_lay.itemAt(i).widget()
                 for i in range(v._conv_lay.count())]
        assert before == after, "aucun theme rate -> aucune bulle ne doit bouger"

        # And after a real catch-up, a second call changes nothing either.
        _fake_stream(v)
        theme_manager.apply_light()
        v._teardown_stream()
        once = [v._conv_lay.itemAt(i).widget()
                for i in range(v._conv_lay.count())]
        v._catch_up_theme_after_stream()
        twice = [v._conv_lay.itemAt(i).widget()
                 for i in range(v._conv_lay.count())]
        assert once == twice, "2e appel = no-op"
    finally:
        _restore(dark0, lang0)


def test_stop_also_catches_the_theme_up():
    """Stop ne passe PAS par _teardown_stream (il detache le worker) : c'est
    quand meme une fin de stream pour l'utilisateur."""
    dark0, lang0 = theme_manager.is_dark, lang_manager.lang
    try:
        theme_manager.apply_dark()
        v = _view()
        v.set_backend(_Backend())
        v.controller.history.append({"role": "user", "content": "salut", "ts": "t"})
        v._rebuild_conversation()
        _fake_stream(v)
        theme_manager.apply_light()

        v._on_stop_clicked()
        bubbles = [v._conv_lay.itemAt(i).widget()
                   for i in range(v._conv_lay.count())]
        bubbles = [b for b in bubbles if isinstance(b, ChatMessage)]
        assert bubbles and not any(b._dark for b in bubbles), (
            "thème fige apres un Stop")
        assert v._theme_catchup_pending is False
    finally:
        _restore(dark0, lang0)


def test_the_attach_button_looks_disabled_when_it_is_disabled():
    """« Joindre » est desactive tant qu'aucun backend n'est actif ET pendant
    TOUTE la duree d'une reponse en streaming (`setEnabled` x2 dans
    chat_view). Or sa feuille ne declarait aucun `:disabled` : mesure a 0 %
    de pixels differents entre actif et inactif — le bouton etait mort tout
    en s'affichant comme vivant, a chaque generation.

    Mesure au RENDU, pas sur la source : c'est la cascade complete (feuille
    d'application + feuille locale) qui decide, et une regle presente dans le
    source peut tres bien etre ecrasee."""
    from PyQt6.QtGui import QPixmap
    from ui.theme import app_qss

    def pixels(w):
        px = QPixmap(w.size())
        px.fill()
        w.render(px)
        img = px.toImage()
        return [img.pixel(x, y) for y in range(img.height())
                for x in range(img.width())]

    ancien = _APP.styleSheet()
    _APP.setStyleSheet(app_qss(theme_manager.current))
    try:
        v = _view()
        v.show()
        _APP.processEvents()
        btn = v._attach_btn
        btn.setEnabled(True)
        _APP.processEvents()
        actif = pixels(btn)
        btn.setEnabled(False)
        _APP.processEvents()
        inactif = pixels(btn)
    finally:
        _APP.setStyleSheet(ancien)

    diff = sum(1 for a, d in zip(actif, inactif) if a != d)
    assert diff > 0, (
        "« Joindre » se peint a l'identique desactive et actif : rien ne dit "
        "a l'utilisateur qu'il est hors service pendant une generation")


TESTS = [
    test_the_attach_button_looks_disabled_when_it_is_disabled,
    test_the_typing_indicator_follows_the_theme,
    test_the_typing_indicator_follows_the_language,
    test_theme_and_language_switches_are_safe_without_an_indicator,
    test_an_indicator_created_after_the_switch_is_born_in_the_right_theme,
    test_a_theme_switch_during_a_stream_is_caught_up_at_teardown,
    test_the_catch_up_keeps_the_bubbles_that_are_not_in_the_history,
    test_the_catch_up_is_idempotent_and_free_when_nothing_was_missed,
    test_stop_also_catches_the_theme_up,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"OK   {t.__name__}")
        except Exception as e:
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)

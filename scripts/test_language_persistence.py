"""La langue choisie survit au redemarrage (2026-08-11).

Trouve par l'audit des « conventions appliquees a la main » : sur les DEUX
preferences globales de l'app, une seule etait persistee. Le theme l'est
depuis le 2026-06-24 (`session.theme_is_dark`, restaure dans main.py) ; la
langue ne l'etait nulle part. Un utilisateur lisant l'espagnol devait la
rechoisir a CHAQUE lancement — et le defaut se voyait d'autant moins depuis
une machine dont le defaut, le francais, etait deja le bon.

Le correctif calque exactement le mecanisme du theme : une propriete sur
`session`, restauree et re-sauvee dans main.py. Ce fichier verrouille les
deux moities, plus la symetrie avec le theme (c'est elle qui rendait
l'absence lisible comme un bug).

Run : python scripts/test_language_persistence.py
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.i18n import TRANSLATIONS
import ui.session as session_mod


def _session_neuve():
    """Une Session isolee sur un fichier temporaire.

    ⚠️ `Session._save` ecrit dans `session_mod._SESSION_PATH`, une CONSTANTE
    DE MODULE — pas dans un attribut d'instance. Poser un `self._path` ne
    detourne donc rien : une premiere version de ce test l'a fait, et a
    ECRASE le session.json reel de l'utilisateur (racine de l'espace de
    travail, tutoriels vus, compteurs de progression, theme) en y ecrivant
    son unique cle. Le seul detournement qui marche est de remplacer la
    constante, ce que fait `_isole()` ci-dessous.
    """
    s = session_mod.Session.__new__(session_mod.Session)
    s._data = {}
    return s


def _isole(fn):
    """Execute `fn` avec _SESSION_PATH pointe sur un dossier temporaire, et le
    remet en place quoi qu'il arrive."""
    vrai = session_mod._SESSION_PATH
    d = tempfile.mkdtemp(prefix="promptuino-lang-")
    session_mod._SESSION_PATH = Path(d) / "session.json"
    try:
        return fn(session_mod._SESSION_PATH)
    finally:
        session_mod._SESSION_PATH = vrai


# ── Le magasin ──────────────────────────────────────────────────────────────

def test_the_default_matches_the_language_manager_default():
    """« fr » des deux cotes. Un defaut different ferait basculer la langue au
    premier lancement, sans que personne n'ait rien choisi."""
    assert _session_neuve().language == "fr"


def test_a_chosen_language_is_written_and_read_back():
    def corps(chemin):
        s = _session_neuve()
        s.language = "es"
        assert s.language == "es"
        # Relu depuis le DISQUE, pas depuis l'objet : c'est la promesse.
        assert json.loads(chemin.read_text(encoding="utf-8"))["language"] == "es"
    _isole(corps)


def test_writing_the_same_language_twice_does_not_rewrite_the_file():
    """Meme discipline que theme_is_dark : le setter sort tot si rien ne
    change. `lang_manager.changed` peut etre emis pour d'autres raisons."""
    def corps(chemin):
        s = _session_neuve()
        s.language = "it"
        avant = chemin.stat().st_mtime_ns
        s.language = "it"
        assert chemin.stat().st_mtime_ns == avant
    _isole(corps)


def test_an_empty_value_never_erases_the_choice():
    def corps(_):
        s = _session_neuve()
        s.language = "en"
        s.language = ""
        assert s.language == "en"
    _isole(corps)


def test_a_corrupt_value_degrades_to_the_default():
    """session.py ne connait PAS la table de traduction et ne doit pas la
    connaitre. Une valeur aberrante ne doit donc pas remonter telle quelle
    sous une forme qui casserait l'appelant."""
    s = _session_neuve()
    s._data["language"] = 42          # ecrit a la main, ou fichier abime
    assert s.language == "fr"


# ── Le branchement dans main.py ─────────────────────────────────────────────

def _main_src() -> str:
    return (ROOT / "main.py").read_text(encoding="utf-8")


def test_main_restores_the_language_at_startup():
    assert re.search(r"lang_manager\.set_language\(\s*session\.language\s*\)",
                     _main_src()), "main.py ne restaure pas la langue"


def test_main_saves_the_language_on_every_change():
    src = _main_src()
    assert "lang_manager.changed.connect" in src, \
        "main.py ne se branche pas sur le changement de langue"
    assert '"language"' in src or "session.language" in src


def test_the_restore_happens_before_the_main_window_is_built():
    """Sinon la fenetre nait en francais puis se retraduit — et tout widget
    qui ne suit pas le signal resterait dans la mauvaise langue."""
    src = _main_src()
    assert src.index("lang_manager.set_language(session.language)") \
        < src.index("window = MainWindow()")


def test_language_is_persisted_the_same_way_as_the_theme():
    """LA symetrie. C'est son absence qui faisait le defaut : deux preferences
    globales, une sauvee, l'autre non. Si quelqu'un retire l'une, ce test dit
    que l'autre attend le meme sort."""
    src = (ROOT / "ui" / "session.py").read_text(encoding="utf-8")
    for prop in ("def theme_is_dark", "def language"):
        assert src.count(prop) == 2, f"{prop} : getter + setter attendus"


def test_every_known_language_round_trips():
    def corps(_):
        for code in TRANSLATIONS:
            s = _session_neuve()
            s.language = code
            assert s.language == code, code
    _isole(corps)


def test_this_test_file_never_writes_the_real_session():
    """LA garde de ce fichier. Sa premiere version a ecrase le session.json
    reel de l'utilisateur : elle detournait `self._path`, alors que `_save`
    ecrit dans la constante de module `_SESSION_PATH`. On verifie qu'apres
    tous les tests ci-dessus, la constante est bien celle d'origine ET que
    le vrai fichier n'a pas ete touche."""
    assert session_mod._SESSION_PATH == _VRAI_CHEMIN,         "un test a laisse _SESSION_PATH detourne"
    if _EMPREINTE_DEPART is not None:
        actuel = _VRAI_CHEMIN.stat().st_mtime_ns
        assert actuel == _EMPREINTE_DEPART,             "le session.json REEL a ete modifie par ce test"


_VRAI_CHEMIN = session_mod._SESSION_PATH
_EMPREINTE_DEPART = (_VRAI_CHEMIN.stat().st_mtime_ns
                     if _VRAI_CHEMIN.exists() else None)

TESTS = [
    test_the_default_matches_the_language_manager_default,
    test_a_chosen_language_is_written_and_read_back,
    test_writing_the_same_language_twice_does_not_rewrite_the_file,
    test_an_empty_value_never_erases_the_choice,
    test_a_corrupt_value_degrades_to_the_default,
    test_main_restores_the_language_at_startup,
    test_main_saves_the_language_on_every_change,
    test_the_restore_happens_before_the_main_window_is_built,
    test_language_is_persisted_the_same_way_as_the_theme,
    test_every_known_language_round_trips,
    test_this_test_file_never_writes_the_real_session,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"OK   {t.__name__}")
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)

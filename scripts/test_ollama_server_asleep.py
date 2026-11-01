"""#117 : « ouvrez l'application Ollama » -- alors qu'elle EST ouverte.

Mesure du 2026-09-14 sur un vrai poste : le tray `ollama app.exe` tournait
(PID 28508) pendant que 127.0.0.1:11434 refusait la connexion. L'application
conseillait alors d'ouvrir Ollama -- une chose deja faite. C'est le meme
cul-de-sac que le #79 a ferme un cran plus haut (<< executez : ollama
serve >>, incomprehensible pour qui decouvre l'app), mais une situation plus
bas.

Il y a donc TROIS situations, pas deux :

    pas installe            -> telecharger Ollama
    installe, pas lance     -> ouvrir l'application Ollama
    installe, lance, muet   -> demarrer le serveur        <- ce ticket

⚠️ Le message CONSTATE et ne diagnostique pas. La cause d'un processus sans
serveur n'a PAS ete mesuree (veille, mise a jour, service arrete...) et
l'ecrire serait presenter une supposition comme une certitude -- ce que ce
projet s'interdit partout ailleurs.

Run: python scripts/test_ollama_server_asleep.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")

from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv)

import ui.ia_view as ia_view  # noqa: E402
from ui.ia_view import _BackendSection as Section  # noqa: E402
from ui.i18n import TRANSLATIONS  # noqa: E402


class _FauxCombo:
    def currentText(self) -> str:
        return "gemma4:e2b"


def _section() -> Section:
    """Section Ollama minimale, JAMAIS construite par `__init__` (qui batirait
    de vrais widgets et lirait le disque) -- meme motif que
    scripts/test_model_probe.py."""
    s = Section.__new__(Section)
    s.backend_id = "ollama"
    s._is_ollama = True
    s._availability_state = None
    s._model_combo = _FauxCombo()
    s._lbl_availability = QLabel()
    return s


def _etat(*, installe: bool, processus: bool, serveur: bool = False) -> str:
    """Rend l'etat calcule pour une situation donnee, en detournant les trois
    sondes au NIVEAU DU MODULE -- c'est la que `refresh_availability` les lit."""
    vrais = (ia_view.is_server_running, ia_view.is_installed,
             ia_view.is_process_running, ia_view.is_model_available)
    ia_view.is_server_running = lambda: serveur
    ia_view.is_installed = lambda: installe
    ia_view.is_process_running = lambda: processus
    ia_view.is_model_available = lambda m: True
    try:
        s = _section()
        s.refresh_availability()
        return s._availability_state[0]
    finally:
        (ia_view.is_server_running, ia_view.is_installed,
         ia_view.is_process_running, ia_view.is_model_available) = vrais


# ── les trois situations ──────────────────────────────────────────────────

def test_the_three_situations_are_distinct():
    """LE test du ticket. Avant, les deux dernieres lignes rendaient le meme
    etat -- donc le meme conseil, faux dans un cas sur deux."""
    assert _etat(installe=False, processus=False) == "ollama_not_installed"
    assert _etat(installe=True, processus=False) == "ollama_server_down"
    assert _etat(installe=True, processus=True) == "ollama_server_asleep"


def test_a_running_server_short_circuits_everything():
    """Serveur qui repond : ni PATH, ni liste de processus. Les deux sondes
    coutent un acces disque et un SOUS-PROCESSUS -- les payer sur le chemin
    normal serait une regression de reactivite."""
    appels = []
    vrais = (ia_view.is_server_running, ia_view.is_installed,
             ia_view.is_process_running, ia_view.is_model_available)
    ia_view.is_server_running = lambda: True
    ia_view.is_installed = lambda: appels.append("installe") or True
    ia_view.is_process_running = lambda: appels.append("processus") or True
    ia_view.is_model_available = lambda m: True
    try:
        s = _section()
        s.refresh_availability()
        assert s._availability_state[0] == "ollama_ok"
        assert appels == [], appels
    finally:
        (ia_view.is_server_running, ia_view.is_installed,
         ia_view.is_process_running, ia_view.is_model_available) = vrais


# ── le message ────────────────────────────────────────────────────────────

def test_the_message_states_the_fact_without_inventing_a_cause():
    """Il dit ce qui est OBSERVE (ouvert / ne repond pas) et ne nomme aucune
    cause -- elle n'a pas ete mesuree."""
    for lg in ("fr", "en", "es", "it"):
        msg = TRANSLATIONS[lg].ia_ollama_server_asleep.lower()
        for invente in ("veille", "sleep", "crash", "plant", "mise à jour",
                        "update", "redémarr", "restart"):
            assert invente not in msg, (lg, invente, msg)


def test_the_message_carries_the_internal_action_link():
    """Sans le lien, le niveau 1 laisserait l'utilisateur informe mais bloque
    -- exactement le cul-de-sac qu'on corrige."""
    for lg in ("fr", "en", "es", "it"):
        msg = TRANSLATIONS[lg].ia_ollama_server_asleep
        assert Section._LIEN_DEMARRER_OLLAMA in msg, lg


def test_both_new_keys_are_really_translated():
    """Quatre copies du francais passeraient un test de presence."""
    for cle in ("ia_ollama_server_asleep", "ia_ollama_starting"):
        vus = {getattr(TRANSLATIONS[lg], cle) for lg in ("fr", "en", "es", "it")}
        assert len(vus) == 4, (cle, vus)


# ── le lien doit etre CLIQUABLE ───────────────────────────────────────────

def test_the_label_no_longer_opens_links_itself():
    """⛔ La regression a ne pas refaire : avec `setOpenExternalLinks(True)`,
    Qt ouvre TOUT lien lui-meme et n'emet PAS `linkActivated` -- le lien
    interne serait passe au systeme comme une URL, donc inerte."""
    s = _section()
    s._availability_state = ("ollama_server_asleep", None)
    s._render_availability()
    assert s._lbl_availability.openExternalLinks() is False


def test_the_internal_link_starts_the_server_and_rechecks():
    """Le clic LANCE, puis RE-VERIFIE : `start_server` ne dit que << lancement
    tente >>, le serveur mettant une a deux secondes a ecouter. Afficher un
    vert sur la foi de ce retour montrerait un etat que personne n'a
    constate."""
    lances, reverifs = [], []
    vrai_start, vrai_timer = ia_view.start_server, ia_view.QTimer.singleShot
    ia_view.start_server = lambda: lances.append(1) or True
    ia_view.QTimer.singleShot = staticmethod(
        lambda ms, fn: reverifs.append(ms))
    try:
        s = _section()
        s.refresh_availability = lambda: None
        s._on_availability_link(Section._LIEN_DEMARRER_OLLAMA)
        assert lances == [1], lances
        assert reverifs and reverifs[0] >= 1000, reverifs
        assert TRANSLATIONS["fr"].ia_ollama_starting.rstrip("…") \
            in s._lbl_availability.text()
    finally:
        ia_view.start_server = vrai_start
        ia_view.QTimer.singleShot = vrai_timer


def test_an_http_link_still_opens_outside():
    """Le lien << le telecharger >> du message << pas installe >> doit
    continuer d'ouvrir ollama.com : le repartiteur lui rend le comportement
    que `setOpenExternalLinks(False)` vient de lui retirer."""
    ouverts = []
    vrai = ia_view.QDesktopServices.openUrl
    ia_view.QDesktopServices.openUrl = staticmethod(
        lambda url: ouverts.append(url.toString()))
    try:
        _section()._on_availability_link("https://ollama.com")
        assert ouverts == ["https://ollama.com"], ouverts
    finally:
        ia_view.QDesktopServices.openUrl = vrai


# ── la pastille de la barre d'etat ────────────────────────────────────────

def test_the_new_state_reddens_the_status_pill():
    """Un etat inconnu tombe dans la branche d'erreur de `statusbar` -- on le
    VERIFIE plutot que de s'y fier : y ajouter la nouvelle cle a KINDS_OK
    ferait annoncer un modele pret alors que rien ne repond."""
    from ui.statusbar import KINDS_OK, KINDS_WARN
    assert "ollama_server_asleep" not in KINDS_OK
    assert "ollama_server_asleep" not in KINDS_WARN


# ── les sondes elles-memes ────────────────────────────────────────────────

def test_the_probes_never_raise():
    """Elles tournent sur le fil graphique : une exception y viderait l'ecran
    d'etat. Ne pas savoir vaut mieux que planter."""
    from ui.ai_backends.ollama_backend import is_process_running, executable_path
    assert isinstance(is_process_running(), bool)
    chemin = executable_path()
    assert chemin is None or isinstance(chemin, str)


def test_starting_the_server_hides_its_console():
    """Rappel du #91 : un sous-processus lance sans `creationflags` ouvre une
    fenetre noire dans l'application INSTALLEE. Verrouille ici en plus de la
    garde globale, parce que ce chemin-ci est neuf."""
    import ast
    src = (ROOT / "ui" / "ai_backends" / "ollama_backend.py").read_text(
        encoding="utf-8")
    arbre = ast.parse(src)
    lancements = [n for n in ast.walk(arbre)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)
                  and n.func.attr in ("run", "Popen")]
    assert lancements, "plus aucun sous-processus ? verifier ce test"
    for n in lancements:
        assert any(k.arg == "creationflags" for k in n.keywords), n.lineno


TESTS = [
    test_the_three_situations_are_distinct,
    test_a_running_server_short_circuits_everything,
    test_the_message_states_the_fact_without_inventing_a_cause,
    test_the_message_carries_the_internal_action_link,
    test_both_new_keys_are_really_translated,
    test_the_label_no_longer_opens_links_itself,
    test_the_internal_link_starts_the_server_and_rechecks,
    test_an_http_link_still_opens_outside,
    test_the_new_state_reddens_the_status_pill,
    test_the_probes_never_raise,
    test_starting_the_server_hides_its_console,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()

"""La generation n'est plus TUEE parce qu'elle est lente (TODO #24).

Une requete qui depassait 300 s etait tuee et l'utilisateur perdait tout pour
une demande simplement complexe. Le couperet est retire des trois backends ; la
sortie est desormais le bouton << Annuler >>, plus un delai.

CE QUE CES TESTS VERROUILLENT. La partie visible (deux messages dans le
journal) est la moins risquee. Les trois qui comptent sont invisibles :

  1. l'annulation ne doit PLUS passer par `QThread.terminate()`. Elle le
     faisait, sur un thread bloque dans `subprocess.communicate()` ou
     `urlopen()` -- le crash natif 0xC0000409 que ce depot a deja paye. Et
     comme le delai dur a disparu, cette methode est devenue la SEULE sortie :
     elle n'a plus le droit d'echouer.
  2. seule la GENERATION perd son delai. La reparation, l'explication et le
     lint le gardent : ils n'ont pas de bouton d'annulation, donc le leur
     retirer n'ajouterait qu'une requete que plus rien n'arreterait.
  3. la sentinelle d'`openai_compat` ne peut pas etre `None` -- `None` y veut
     dire << aucun delai >>, la valeur meme que la generation doit transmettre.
     Les confondre ferait retomber la generation sur les 120 s qu'on vient de
     lui retirer, en silence et avec un code qui a l'air juste.

Run: python scripts/test_generation_no_hard_timeout.py
"""
import inspect
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtCore import QThread

import ui.ai_backends.claude_code as cc
import ui.ai_backends.ollama_backend as ob
import ui.ai_backends.openai_compat as oc
import ui.studio_view as sv
from ui.i18n import lang_manager
from ui.studio.generation_flow import GenerateWorker

LANGS = ("fr", "en", "es", "it")
_TRIPLE = chr(34) * 3


def _body(fn) -> str:
    """Le source SANS les docstrings.

    Necessaire, et pas cosmetique : plusieurs des docstrings visees NOMMENT
    `terminate()` pour l'interdire. Les laisser ferait rougir le test qui
    verifie qu'on ne l'appelle plus, pour la raison exactement inverse de
    celle qu'il surveille. On garde les segments PAIRS du decoupage,
    c'est-a-dire ce qui tombe hors des triples guillemets.
    """
    return "".join(inspect.getsource(fn).split(_TRIPLE)[::2])


# -- 1. l'annulation --------------------------------------------------------

def test_no_cancel_path_calls_terminate_on_the_generation_worker():
    """LA garde, et elle balaie le FICHIER ENTIER — pas une methode.

    ⚠️ La premiere version ne regardait que `_cancel_gen_worker`, et elle
    passait au vert alors que `_cancel_beginner` gardait son `terminate()` :
    annuler en mode **Debutant** plantait encore, alors que le mode n'est
    qu'un affichage. Un garde nomme d'apres UNE methode ne protege qu'elle ;
    le defaut, lui, est une COPIE. D'ou un balayage du module.

    `QThread.terminate()` sur un thread bloque dans une E/S native est le
    crash 0xC0000409 que ce depot a deja paye."""
    source = Path(sv.__file__).read_text(encoding="utf-8")
    fautifs = [ligne.strip() for ligne in source.splitlines()
               if "_gen_worker.terminate()" in ligne]
    assert not fautifs, fautifs


def test_both_modes_stop_the_worker_through_the_same_door():
    """<< Le mode n'est qu'un affichage >> : Debutant et int/avance doivent
    annuler par le MEME chemin, sinon l'un des deux derive."""
    for fn in (sv.StudioView._cancel_gen_worker, sv.StudioView._cancel_beginner):
        assert "_stop_gen_worker_safely" in _body(fn), fn.__name__


def test_cancelling_a_generation_asks_the_backend_to_stop():
    """Sans ca, couper le delai dur laisserait l'utilisateur sans AUCUNE
    sortie : le thread est bloque dans generate_code, rien ne le reveille."""
    assert "backend.cancel()" in _body(sv.StudioView._stop_gen_worker_safely)


def test_the_worker_exposes_its_backend():
    assert isinstance(GenerateWorker.backend, property)


def test_every_backend_can_actually_be_cancelled():
    """`AIBackend.cancel` est un no-op par defaut. Un backend qui tient une
    E/S bloquante DOIT redefinir -- sinon annuler ne fait rien du tout."""
    for cls in (cc.ClaudeCodeBackend, ob.OllamaBackend, oc.OpenAICompatBackend):
        assert "cancel" in cls.__dict__, cls.__name__


def test_the_detach_does_not_use_the_chat_reaping_trick():
    """`GenerateWorker.finished` est un signal MAISON qui masque celui de
    QThread. Se connecter dessus pour recolter reveillerait exactement les
    callbacks que le detachement vient de couper -- d'ou une liste de parking
    plutot que la recolte du chat."""
    assert GenerateWorker.finished is not QThread.finished
    corps = _body(sv.StudioView._detach_gen_worker)
    assert "_detached_gen_workers.append" in corps, corps
    assert "deleteLater" not in corps, corps


# -- 2. le delai dur --------------------------------------------------------

def test_only_the_generation_loses_its_timeout_on_ollama():
    assert "timeout=None" in _body(ob.OllamaBackend.generate_code)
    for autre in (ob.OllamaBackend.fix_code, ob.OllamaBackend.explain_error,
                  ob.OllamaBackend.lint_code):
        assert "timeout=None" not in _body(autre), autre.__name__


def test_only_the_generation_loses_its_timeout_on_claude_code():
    assert "timeout=None" in _body(cc.ClaudeCodeBackend.generate_code)
    for autre in (cc.ClaudeCodeBackend.fix_code,
                  cc.ClaudeCodeBackend.explain_error,
                  cc.ClaudeCodeBackend.lint_code):
        assert "timeout=None" not in _body(autre), autre.__name__


def test_only_the_generation_loses_its_timeout_on_openai_compat():
    assert "timeout=None" in _body(oc.OpenAICompatBackend.generate_code)
    for autre in (oc.OpenAICompatBackend.fix_code,
                  oc.OpenAICompatBackend.lint_code):
        assert "timeout=None" not in _body(autre), autre.__name__


def test_the_openai_sentinel_is_not_none():
    """Le piege du jour, attrape a l'ecriture. `_complete` rend le defaut
    quand le drapeau vaut la sentinelle ; si la sentinelle ETAIT `None`,
    `generate_code(timeout=None)` reprendrait les 120 s qu'on vient de lui
    retirer -- silencieusement, avec un code qui a l'air juste."""
    assert oc._DEFAULT_TIMEOUT is not None
    defaut = inspect.signature(
        oc.OpenAICompatBackend._complete).parameters["timeout"].default
    assert defaut is oc._DEFAULT_TIMEOUT


def test_there_is_a_hook_to_close_the_inflight_response():
    """Seul point d'accroche pour annuler : sans delai, fermer la reponse
    depuis le thread UI est la seule sortie.

    ⚠️ Les deux backends ne s'y prennent PAS pareil, et ce n'est pas une
    incoherence. Ollama passe par un parametre de `_post`, une fonction privee
    du module. `openai_compat` ne le pouvait pas : son transport est
    INJECTABLE, donc toucher a la signature de `post_json` casse toute
    doublure — ce qui est arrive, avec un << Reponse illisible du
    fournisseur >> sans rapport. D'ou une methode OPTIONNELLE, lue par
    `getattr`."""
    assert "register" in inspect.signature(ob._post).parameters
    assert hasattr(oc._UrllibTransport, "close_inflight")
    assert "register" not in inspect.signature(
        oc._UrllibTransport.post_json).parameters
    assert "getattr" in _body(oc.OpenAICompatBackend.cancel)


# -- 3. le watchdog ---------------------------------------------------------

def test_the_hard_delay_is_where_the_generation_used_to_die():
    """300 s n'est pas un nombre rond choisi au hasard : c'est la seconde
    exacte ou l'utilisateur perdait tout. Le message la remplace."""
    assert sv._GEN_SLOW_HARD_MS == cc._CLI_TIMEOUT * 1000
    assert sv._GEN_SLOW_HARD_MS == ob._TIMEOUT_GEN * 1000
    assert sv._GEN_SLOW_SOFT_MS < sv._GEN_SLOW_HARD_MS


def test_the_watchdog_kills_nothing():
    """Tout l'interet du ticket : NON BLOQUANT. Il ecrit, et c'est tout."""
    corps = _body(sv.StudioView._on_gen_slow)
    for interdit in ("cancel", "terminate", "_gen_worker", "quit()"):
        assert interdit not in corps, (interdit, corps)


def test_the_watchdog_removes_the_live_line_before_writing():
    """`set_live_line` previent que rien d'autre ne doit ecrire pendant
    l'animation : sinon l'ancre selectionnerait le message avec la ligne
    animee et le tick suivant l'EFFACERAIT."""
    corps = _body(sv.StudioView._on_gen_slow)
    assert corps.index("clear_live_line") < corps.index("begin_phase"), corps


def test_both_loader_exits_stop_the_watchdog():
    """Une minuterie qui survit ecrirait << c'est plus long que d'habitude >>
    sur un journal ou le code est deja pret."""
    for fn in (sv.StudioView._stop_gen_loader,
               sv.StudioView._stop_gen_loader_ready):
        assert "_stop_gen_slow_watchdog" in _body(fn), fn.__name__


def test_both_messages_exist_in_the_four_languages():
    for code in LANGS:
        lang_manager.set_language(code)
        s = lang_manager.current
        for attr in ("studio_gen_slow_soft", "studio_gen_slow_hard"):
            txt = getattr(s, attr, "")
            assert txt and txt.strip(), (code, attr)


def test_neither_message_claims_the_generation_was_stopped():
    """L'honnetete du message EST le ticket : la generation CONTINUE. Un mot
    d'echec ferait croire le contraire et pousserait a tout relancer -- soit
    exactement la perte que #24 supprime."""
    interdits = ("echou", "fail", "error", "erreur", "abandon", "cancelled",
                 "timeout", "expir")
    for code in LANGS:
        lang_manager.set_language(code)
        s = lang_manager.current
        for attr in ("studio_gen_slow_soft", "studio_gen_slow_hard"):
            bas = getattr(s, attr).lower()
            for mot in interdits:
                assert mot not in bas, (code, attr, mot)


TESTS = [
    test_no_cancel_path_calls_terminate_on_the_generation_worker,
    test_both_modes_stop_the_worker_through_the_same_door,
    test_cancelling_a_generation_asks_the_backend_to_stop,
    test_the_worker_exposes_its_backend,
    test_every_backend_can_actually_be_cancelled,
    test_the_detach_does_not_use_the_chat_reaping_trick,
    test_only_the_generation_loses_its_timeout_on_ollama,
    test_only_the_generation_loses_its_timeout_on_claude_code,
    test_only_the_generation_loses_its_timeout_on_openai_compat,
    test_the_openai_sentinel_is_not_none,
    test_there_is_a_hook_to_close_the_inflight_response,
    test_the_hard_delay_is_where_the_generation_used_to_die,
    test_the_watchdog_kills_nothing,
    test_the_watchdog_removes_the_live_line_before_writing,
    test_both_loader_exits_stop_the_watchdog,
    test_both_messages_exist_in_the_four_languages,
    test_neither_message_claims_the_generation_was_stopped,
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

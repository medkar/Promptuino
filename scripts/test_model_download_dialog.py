"""La fenetre « Modeles… » d'Ollama : un telechargement SURVIT a la fenetre.

Trouve le 2026-11-06 en preparant le #121 : fermer la fenetre pendant un
telechargement faisait PLANTER l'application entiere (« QThread: Destroyed
while thread is still running ») — le fil du telechargement appartenait a la
fenetre, detruite a la fermeture. Aucun test ne couvrait cette fenetre.
Le comportement voulu par l'auteur, le meme que pour LM Studio : le
telechargement continue, et la fenetre rouverte montre ou il en est.

Aucun reseau : `telecharger` est remplace par un faux qui avance au rythme
du test, et l'espace disque par une reponse fixee.

Run: python scripts/test_model_download_dialog.py
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")

from PyQt6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv)

import ui.model_download_dialog as mdd  # noqa: E402
from ui.i18n import TRANSLATIONS, lang_manager  # noqa: E402

# ⛔ JAMAIS les vrais serveurs : « Charger » libere d'abord les AUTRES modeles
# (2026-11-06) -- non remplacee, cette etape dechargerait ceux de
# l'utilisateur. Remplacee pour TOUT le fichier ; `_LIBERATIONS` note les
# demandes, `_A_LIBERER` dit ce que la fausse liberation rend.
import ui.memoire_modeles as _mm  # noqa: E402
_LIBERATIONS: list = []
_A_LIBERER: list = []
_mm.liberer_autres = lambda moteur, modele, url: (
    _LIBERATIONS.append((moteur, modele)) or list(_A_LIBERER))


class _Faux:
    """Un `telecharger` pilote par le test : il avance quand on le lui dit."""

    def __init__(self, total=1000, err=None):
        self.total, self.err = total, err
        self.recu = 0
        self.fin = threading.Event()
        self.arrete = threading.Event()

    def __call__(self, nom, progression, arret):
        dernier = -1
        while not self.fin.is_set():
            if arret():
                self.arrete.set()
                return None
            if self.recu != dernier:
                dernier = self.recu
                progression(self.recu, self.total, "pulling")
            time.sleep(0.01)
        progression(self.total, self.total, "success")
        return self.err


class _Detour:
    def __init__(self, module, **remplacements):
        self.module, self.remp, self.vrais = module, remplacements, {}

    def __enter__(self):
        for nom, valeur in self.remp.items():
            self.vrais[nom] = getattr(self.module, nom)
            setattr(self.module, nom, valeur)
        return self

    def __exit__(self, *a):
        for nom, valeur in self.vrais.items():
            setattr(self.module, nom, valeur)


def _attendre(condition, delai=5.0):
    fin = time.time() + delai
    while time.time() < fin:
        _APP.processEvents()
        if condition():
            return True
        time.sleep(0.02)
    return False


def _fermer(d):
    """Comme a l'ecran : fermer, puis laisser Qt DETRUIRE la fenetre
    (WA_DeleteOnClose). `processEvents` seul n'execute pas les DeferredDelete."""
    d.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    _APP.processEvents()


def _environnement(faux, espace=True, locaux=None, charges=None, maxis=None,
                   vram=None):
    locaux = {} if locaux is None else locaux
    charges = {} if charges is None else charges
    maxis = {} if maxis is None else maxis
    return _Detour(mdd, telecharger=faux,
                   modeles_locaux=lambda: dict(locaux),
                   modeles_charges=lambda: dict(charges),
                   contexte_max=lambda n: maxis.get(n, 131072),
                   espace_suffisant=lambda t: espace,
                   espace_partiels=lambda: 0,
                   espace_disque_libre=lambda: 10**9,
                   vram_totale=lambda: vram)


def _nettoyer():
    """Un test qui echoue ne doit pas laisser un telechargement aux suivants."""
    t = mdd._COURANT
    if t is not None:
        t.annuler()
        t.attendre(3000)
    mdd._COURANT = None


# ── le defaut ─────────────────────────────────────────────────────────────

def test_closing_during_a_download_neither_crashes_nor_stops_it():
    """Avant : le processus MOURAIT ici. Si ce test « disparait » de la sortie
    du lanceur avec un code d'erreur, c'est ce plantage-la qui est revenu."""
    faux = _Faux()
    with _environnement(faux):
        d = mdd.ModelDownloadDialog()
        d._lancer("faux:1b")
        faux.recu = 300
        assert _attendre(lambda: d._barre.value() == 30), d._barre.value()
        _fermer(d)
        faux.recu = 600
        time.sleep(0.2)
        _APP.processEvents()
        assert not faux.arrete.is_set(), "fermer la fenetre a ARRETE le telechargement"
        assert mdd._COURANT is not None and mdd._COURANT.en_cours()
        faux.fin.set()
        assert _attendre(lambda: not mdd._COURANT.en_cours())


def test_a_reopened_window_shows_where_the_download_is():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    faux = _Faux()
    with _environnement(faux):
        d1 = mdd.ModelDownloadDialog()
        d1._lancer("faux:1b")
        faux.recu = 200
        assert _attendre(lambda: d1._barre.value() == 20)
        _fermer(d1)
        faux.recu = 700
        time.sleep(0.2)
        _APP.processEvents()
        d2 = mdd.ModelDownloadDialog()
        assert not d2._zone.isHidden(), "la fenetre rouverte ne montre rien"
        assert "faux:1b" in d2._lbl_etat.text(), d2._lbl_etat.text()
        assert _attendre(lambda: d2._barre.value() == 70), d2._barre.value()
        assert not d2._btn_annuler.isHidden(), "Annuler doit rester possible"
        assert d2._lbl_note_annul.text() == s.md_keeps_running
        assert not d2._btn_autre.isEnabled(), "un seul telechargement a la fois"
        faux.fin.set()
        assert _attendre(lambda: d2._lbl_etat.text() == s.md_done), d2._lbl_etat.text()
    assert mdd._COURANT is None, "une issue affichee n'a plus a etre gardee"


def test_a_download_finished_while_closed_says_so_once():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    faux = _Faux()
    with _environnement(faux):
        d1 = mdd.ModelDownloadDialog()
        d1._lancer("faux:1b")
        assert _attendre(lambda: mdd._COURANT is not None and mdd._COURANT.en_cours())
        _fermer(d1)
        faux.fin.set()
        assert _attendre(lambda: not mdd._COURANT.en_cours())
        d2 = mdd.ModelDownloadDialog()
        assert d2._lbl_etat.text() == s.md_done, d2._lbl_etat.text()
        assert mdd._COURANT is None
        _fermer(d2)
        d3 = mdd.ModelDownloadDialog()
        assert d3._zone.isHidden(), "l'issue ne se repete pas a chaque ouverture"


def test_the_disk_guard_still_works_with_the_window_closed():
    """⛔ Ollama PREALLOUE le fichier entier : la garde qui annule quand le
    total depasse l'espace libre vivait dans la fenetre. Fenetre fermee, un
    telechargement poursuivi l'aurait remplie sans controle."""
    faux = _Faux(total=10**12)
    with _environnement(faux, espace=False):
        d = mdd.ModelDownloadDialog()
        d._lancer("enorme:1t")       # hors suggeres : aucune taille connue avant
        _fermer(d)
        faux.recu = 1
        # La garde tourne sur le fil PRINCIPAL (signal mis en file) : il faut
        # pomper les evenements, un `Event.wait` la bloquerait elle aussi.
        assert _attendre(faux.arrete.is_set), \
            "la garde d'espace ne tourne plus fenetre fermee"
        assert _attendre(lambda: not mdd._COURANT.en_cours())
        assert mdd._COURANT.issue["manque_espace"] == 10**12


def test_cancel_still_stops_the_download():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    faux = _Faux()
    with _environnement(faux):
        d = mdd.ModelDownloadDialog()
        d._lancer("faux:1b")
        assert _attendre(lambda: mdd._COURANT is not None and mdd._COURANT.en_cours())
        d._btn_annuler.click()
        assert faux.arrete.wait(5)
        assert _attendre(lambda: d._lbl_etat.text() == s.md_cancelled), d._lbl_etat.text()
    assert mdd._COURANT is None


def test_quitting_the_app_interrupts_and_waits_for_the_download():
    """Le fil survit a la fenetre, donc il peut tourner a la SORTIE de
    l'app : l'interrompre et l'attendre, sinon le meme plantage revient,
    a la fermeture de Promptuino cette fois."""
    faux = _Faux()
    with _environnement(faux):
        d = mdd.ModelDownloadDialog()
        d._lancer("faux:1b")
        assert _attendre(lambda: mdd._COURANT is not None and mdd._COURANT.en_cours())
        _fermer(d)
        t = mdd._COURANT
        mdd._arreter_a_la_sortie()
        assert faux.arrete.is_set(), "quitter n'a pas interrompu le telechargement"
        assert t._worker.isFinished(), "le fil tourne encore a la sortie"


def test_the_issue_is_published_only_once_the_thread_has_stopped():
    """Quand la fenetre apprend l'issue (et lache la derniere reference), le
    fil doit etre ARRETE. ⚠️ Ce test verifie l'ordre, il ne reproduit pas le
    plantage natif vu une fois sous `-j 6` : celui-la n'a pas pu etre
    provoque a la demande (voir `_Telechargement._fini`)."""
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")

    class _Lent(mdd._Worker):
        """Traine APRES `fini` : sans l'attente, l'issue partirait pendant
        que le fil tourne encore (verifie en retirant l'attente)."""
        def run(self):
            super().run()
            time.sleep(0.3)

    faux = _Faux()
    vu = []
    with _environnement(faux), _Detour(mdd, _Worker=_Lent):
        d = mdd.ModelDownloadDialog()
        d._lancer("faux:1b")
        t = mdd._COURANT
        t.fini.connect(lambda _i: vu.append(t._worker.isFinished()))
        faux.fin.set()
        assert _attendre(lambda: d._lbl_etat.text() == s.md_done), d._lbl_etat.text()
    assert vu == [True], vu


# ── Charger / Decharger, comme la fenetre LM Studio (2026-11-06) ─────────

_LOCAUX = {"gemma4:e2b": (7162405886, "5,1 Md"), "llama3.1:8b": (4920753328, "8 Md")}


def test_each_installed_model_offers_load_or_unload():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    with _environnement(_Faux(), locaux=_LOCAUX, charges={"llama3.1:8b": 8192}):
        d = mdd.ModelDownloadDialog()
        assert [b.text() for b in d._btns_geste] == [s.lms_load, s.lms_unload], \
            [b.text() for b in d._btns_geste]
        textes = [w.text() for w in d._dl_host.findChildren(mdd.QLabel)]
        assert any("llama3.1:8b" in t and s.lms_loaded.format(n=8192) in t
                   for t in textes), textes


def test_load_uses_the_generation_context_and_rereads():
    import ui.ai_backends.ollama_backend as ob
    import ui.ollama_models as om
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    demandes, charges = [], {}        # le bouchon de /api/ps lit CE dict

    class _Backend:
        def __init__(self, modele):
            pass

        def generation_context(self):
            return 6144

    def charger(nom, ctx, **_k):
        demandes.append((nom, ctx))
        charges[nom] = ctx
        return True, ""

    with _environnement(_Faux(), locaux=_LOCAUX, charges=charges), \
         _Detour(om, charger=charger), _Detour(ob, OllamaBackend=_Backend):
        d = mdd.ModelDownloadDialog()
        d._btns_geste[0].click()                      # gemma4:e2b, pas charge
        assert _attendre(lambda: demandes and not d._occupe), demandes
        assert demandes == [("gemma4:e2b", 6144)], demandes
        assert d._btns_geste[0].text() == s.lms_unload, "la liste n'a pas ete relue"


def test_loading_from_the_window_frees_the_others_and_says_so():
    """Decision de l'auteur (2026-11-06) : passer de LM Studio a Ollama libere
    le modele de LM Studio, et inversement."""
    import ui.ai_backends.ollama_backend as ob
    import ui.ollama_models as om
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")

    class _Backend:
        def __init__(self, modele):
            pass

        def generation_context(self):
            return 16384

    _LIBERATIONS.clear()
    _A_LIBERER[:] = [("google/gemma-4-e4b", "LM Studio")]
    try:
        with _environnement(_Faux(), locaux=_LOCAUX), \
             _Detour(om, charger=lambda nom, ctx, **k: (True, "")), \
             _Detour(ob, OllamaBackend=_Backend):
            d = mdd.ModelDownloadDialog()
            d._btns_geste[0].click()
            assert _attendre(lambda: _LIBERATIONS and not d._occupe), _LIBERATIONS
    finally:
        _A_LIBERER.clear()
    assert _LIBERATIONS == [("ollama", "gemma4:e2b")], _LIBERATIONS   # 1re ligne
    assert d._lbl_libere.text() == s.mem_freed.format(
        liste="google/gemma-4-e4b (LM Studio)")


def test_a_refused_load_is_said_in_red_under_the_list():
    import ui.ai_backends.ollama_backend as ob
    import ui.ollama_models as om
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")

    class _Backend:
        def __init__(self, modele):
            pass

        def generation_context(self):
            return 8192

    with _environnement(_Faux(), locaux=_LOCAUX), \
         _Detour(om, charger=lambda nom, ctx, **k: (False, "not enough memory")), \
         _Detour(ob, OllamaBackend=_Backend):
        d = mdd.ModelDownloadDialog()
        d._btns_geste[0].click()
        assert _attendre(lambda: not d._occupe and not d._lbl_info.isHidden())
    # Refus pour manque de memoire : la phrase courte, plus le texte brut (2026-11-06).
    assert d._lbl_info.text() == s.load_no_memory_short


def test_a_model_below_the_floor_is_marked_unusable_and_cannot_be_loaded():
    """Decision de l'auteur (2026-11-06) : dire qu'il est inutilisable, et
    que c'est son contexte qui est trop petit."""
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    with _environnement(_Faux(), locaux=_LOCAUX, maxis={"gemma4:e2b": 8192}):
        d = mdd.ModelDownloadDialog()
        textes = [w.text() for w in d._dl_host.findChildren(mdd.QLabel)]
        assert any("gemma4:e2b" in t and s.md_unusable_ctx.format(n=8192) in t
                   for t in textes), textes
        assert not d._btns_geste[0].isEnabled(), "un modele inutilisable se charge"
        assert d._btns_geste[1].isEnabled()


def test_the_cards_memory_is_said_once_in_windows_units():
    """QA du 2026-11-06 : « 17.1 Go » sur chaque ligne se lisait comme la
    taille des modeles, et ne correspondait pas aux 16 Go de la carte."""
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    vram = 16311 * 1024 * 1024                       # la RTX 5060 Ti de l'auteur
    with _environnement(_Faux(), locaux=_LOCAUX, vram=vram):
        d = mdd.ModelDownloadDialog()
        assert d._lbl_vram.text() == s.md_vram.format(vram="16 Go"), d._lbl_vram.text()
        textes = " ".join(w.text() for w in d.findChildren(mdd.QLabel))
        assert "17.1" not in textes and "16 Go)" not in textes, "repete par ligne"


def test_nothing_running_means_nothing_shown():
    with _environnement(_Faux()):
        d = mdd.ModelDownloadDialog()
        assert d._zone.isHidden()


def test_the_note_exists_in_the_four_languages():
    for code, s in TRANSLATIONS.items():
        assert s.md_keeps_running.strip(), code


TESTS = [
    test_closing_during_a_download_neither_crashes_nor_stops_it,
    test_a_reopened_window_shows_where_the_download_is,
    test_a_download_finished_while_closed_says_so_once,
    test_the_disk_guard_still_works_with_the_window_closed,
    test_cancel_still_stops_the_download,
    test_quitting_the_app_interrupts_and_waits_for_the_download,
    test_the_issue_is_published_only_once_the_thread_has_stopped,
    test_each_installed_model_offers_load_or_unload,
    test_load_uses_the_generation_context_and_rereads,
    test_loading_from_the_window_frees_the_others_and_says_so,
    test_a_refused_load_is_said_in_red_under_the_list,
    test_a_model_below_the_floor_is_marked_unusable_and_cannot_be_loaded,
    test_the_cards_memory_is_said_once_in_windows_units,
    test_nothing_running_means_nothing_shown,
    test_the_note_exists_in_the_four_languages,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}", flush=True)
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {type(e).__name__}: {e}", flush=True)
        finally:
            _nettoyer()
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()

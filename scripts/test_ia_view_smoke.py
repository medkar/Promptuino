"""IAView refonte smoke test. Run: python scripts/test_ia_view_smoke.py"""
from __future__ import annotations
import os, sys, types
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_store = {}
fk = types.ModuleType("keyring")
fk.get_password = lambda s, k: _store.get((s, k))
fk.set_password = lambda s, k, v: _store.__setitem__((s, k), v)
fk.delete_password = lambda s, k: _store.pop((s, k), None)
sys.modules["keyring"] = fk

from PyQt6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from ui.ia_view import IAView
from ui.ai_backends.providers import PROVIDERS


def test_iaview_builds_and_lists_providers():
    v = IAView()
    combo = v._cloud._provider_combo
    items = [combo.itemData(i) for i in range(combo.count())]
    for p in PROVIDERS:
        assert p.id in items, f"provider {p.id} missing from combo"
    assert "custom" in items, "custom entry missing from combo"
    # Model selector is now an editable combo (pick from /models or type one).
    assert v._cloud._model_combo.isEditable(), "model combo must be editable"


# ── La pastille et `is_available()` ne peuvent plus se contredire ───────────
# Defaut d'origine (brief LM Studio, 2026-11-02) : DEUX endroits repondaient a
# « cette configuration est-elle complete ? ». `is_available()` exigeait une
# cle de tout le monde, la pastille n'en reclamait pas a « custom ». Un serveur
# local sans cle avait donc une pastille non rouge et une generation MORTE.

def test_the_dot_shares_the_key_rule_instead_of_judging_again():
    """⛔ La garde porte sur le NON-DEDOUBLEMENT, pas sur une couleur.

    Une garde de couleur passerait au vert avec deux regles d'accord par
    hasard sur le cas teste. Ce qu'il faut interdire, c'est que
    `_publier_etat` se remette a juger la cle lui-meme -- meme precedent que
    `test_no_mode_test_survives_in_the_resolution_path`.
    """
    import inspect
    src = inspect.getsource(IAView._publier_etat)
    assert "backend_requires_key" in src, (
        "la pastille doit poser la question de la cle par la source PARTAGEE, "
        "pas s'en fabriquer une"
    )


def test_a_keyless_local_server_is_reported_configured():
    """Le cas du Fablab, de bout en bout : la pastille ET le backend."""
    from ui.ai_config import ai_config
    from ui.ai_backends import get_backend_instance
    from ui.ai_status import ai_status

    ai_config._data["custom_base_url"] = "http://localhost:1234/v1"
    ai_config._data["custom_model"] = "gemma-4"
    ai_config._data["ai_backend"] = "custom"
    _store.clear()                      # aucune cle au trousseau

    backend = get_backend_instance("custom")
    assert backend.is_available() is True, "le backend doit etre utilisable"

    v = IAView()
    v._active_backend = backend
    ai_status.set_state("depart")
    v._publier_etat()
    assert ai_status.state != "cloud_key_missing", (
        "la pastille ne doit plus reclamer une cle a un serveur local"
    )


def test_a_cloud_provider_without_its_key_is_reported_missing():
    """⛔ La garde symetrique : ne pas « reparer » jusqu'a mentir."""
    from ui.ai_config import ai_config
    from ui.ai_backends import get_backend_instance
    from ui.ai_status import ai_status

    ai_config._data["ai_backend"] = "openai"
    _store.clear()                      # aucune cle
    v = IAView()
    v._active_backend = get_backend_instance("openai")
    v._publier_etat()
    assert ai_status.state == "cloud_key_missing", ai_status.state


# ── La section « Local » : un radio, une liste, une page par moteur ─────────
# Maquette demandee par l'utilisateur (2026-11-04) : « La radio dira juste
# Local et via une liste deroulante, on pourra choisir ollama et LM studio, ce
# qui changera les champs affiches en-dessous. »

def test_the_local_radio_groups_both_engines():
    from ui.ai_backends import LOCAL_BACKENDS
    v = IAView()
    combo = v._local._combo
    ids = [combo.itemData(i) for i in range(combo.count())]
    assert ids == list(LOCAL_BACKENDS), ids
    assert "ollama" in ids and "lmstudio" in ids, ids
    assert v._local.radio.text(), "le radio Local doit porter un libelle"


def test_the_engine_list_shows_brand_names():
    """Les entrees ne sont PAS traduites : « Ollama » et « LM Studio » sont des
    marques, comme le « Ollama (local) » ecrit en dur depuis toujours."""
    v = IAView()
    combo = v._local._combo
    libelles = [combo.itemText(i) for i in range(combo.count())]
    assert "Ollama" in libelles and "LM Studio" in libelles, libelles


def test_choosing_an_engine_changes_the_page():
    v = IAView()
    v._local.select_engine("ollama")
    assert v._local._stack.currentWidget() is v._local.pages["ollama"]
    v._local.select_engine("lmstudio")
    assert v._local._stack.currentWidget() is v._local.pages["lmstudio"]


def test_both_engines_have_the_SAME_context_setting():
    """La decision s'est INVERSEE. Le 2026-11-04 : « LM studio ne permet pas
    de regler la taille du contexte via promptuino donc pas necessaire de
    mettre le slider » -- vrai par l'API compatible OpenAI. Le 2026-11-06,
    l'API native v1 charge a la taille demandee (mesure), et l'auteur veut
    « la meme mecanique pour Ollama ET LM Studio ». Le MEME widget, donc."""
    from ui.contexte_curseur import CurseurContexte
    v = IAView()
    for moteur in ("ollama", "lmstudio"):
        assert isinstance(v._local.pages[moteur]._ctx, CurseurContexte), moteur


def test_the_lmstudio_page_has_a_manage_models_button():
    """La decision s'est INVERSEE. Le 2026-11-04 : « ne gere pas le
    telechargement de modeles sur LM Studio depuis promptuino ». Le
    2026-11-06, l'auteur leve la reserve : « faire comme on a fait avec
    Ollama » (TODO #121). Le bouton ouvre `LMStudioModelsDialog`, et porte le
    meme libelle que celui d'Ollama."""
    from ui.i18n import lang_manager
    v = IAView()
    page = v._local.pages["lmstudio"]
    assert page._btn_models.text() == lang_manager.current.md_manage


def test_the_lmstudio_page_has_an_address_field_prefilled():
    """⛔ 127.0.0.1 et NON « localhost » : sur Windows, « localhost » peut
    resoudre en IPv6 quand le serveur n'ecoute qu'en IPv4. Le CLI de LM Studio
    documente lui-meme `--bind "127.0.0.1" (default)`."""
    from ui.ai_config import ai_config
    v = IAView()
    page = v._local.pages["lmstudio"]
    page.load_key()
    assert page._url_input.text() == ai_config.lmstudio_base_url
    assert "127.0.0.1" in page._url_input.text(), page._url_input.text()
    assert "localhost" not in page._url_input.text()


def test_ollama_keeps_every_field_it_had():
    """⛔ NON-REGRESSION, et c'etait le vrai risque de cette tache. La section
    Ollama n'est pas reecrite : elle devient une PAGE, radio masque. Ses champs
    doivent etre tous la, a l'identique."""
    v = IAView()
    page = v._local.pages["ollama"]
    # `_ctx` remplace `_ctx_slider` + `_lbl_ctx_value` (2026-11-06) : le
    # reglage de contexte commun aux deux moteurs.
    for attr in ("_ctx", "_model_combo",
                 "_btn_dl_model", "_lbl_availability", "_lbl_model_status"):
        assert hasattr(page, attr), f"Ollama a perdu {attr}"
    assert not page.radio.isVisible(), "le radio d'Ollama doit etre masque"


def test_a_saved_local_backend_checks_the_local_radio():
    """⛔ AUCUNE MIGRATION DE CONFIGURATION : `ai_config.backend_id` garde
    l'id CONCRET (`ollama`, `lmstudio`), jamais « local ». Un fichier existant
    doit donc marcher tel quel."""
    from ui.ai_config import ai_config
    for bid in ("ollama", "lmstudio"):
        ai_config._data["ai_backend"] = bid
        v = IAView()
        assert v._local.radio.isChecked(), bid
        assert v._local.current_id() == bid, (bid, v._local.current_id())
        assert v._local._stack.currentWidget() is v._local.pages[bid]


def test_the_checked_id_survives_a_page_without_a_radio():
    """⛔ Garde d'un crash que j'ai trouve en relisant les usages, pas a
    l'execution : `_get_checked_id` iterait `_sections` en appelant `.radio`,
    et `_LMStudioPage` n'en a pas. PyQt aurait masque l'AttributeError en
    « super-class __init__() was never called »."""
    from ui.ai_config import ai_config
    ai_config._data["ai_backend"] = "lmstudio"
    v = IAView()
    assert v._get_checked_id() == "lmstudio", v._get_checked_id()
    v._local.select_engine("ollama")
    assert v._get_checked_id() == "ollama", v._get_checked_id()


def test_both_pages_are_reachable_by_theme_and_language():
    """Les pages entrent dans `_sections`, le dictionnaire que le theme, la
    langue ET la pastille parcourent. Les y oublier rendrait LM Studio
    invisible a ces trois chemins."""
    v = IAView()
    assert "ollama" in v._sections and "lmstudio" in v._sections
    assert v._sections["lmstudio"] is v._local.pages["lmstudio"]


def test_the_sections_are_ordered_chatgpt_local_cloud():
    """Ordre decide par l'auteur le 2026-11-06 : Compte ChatGPT, puis Local,
    puis Cloud (cle d'API) en dernier."""
    v = IAView()
    lay = v._card.layout()
    rang = {id(lay.itemAt(i).widget()): i for i in range(lay.count())
            if lay.itemAt(i).widget() is not None}
    assert rang[id(v._chatgpt)] < rang[id(v._local)] < rang[id(v._cloud)], rang


def test_a_local_setting_change_refreshes_the_active_backend():
    """⛔ Trouve le 2026-11-06 : le `model_changed` de la page LM Studio
    n'etait branche a RIEN -- choisir un autre modele ne recreait pas le
    moteur actif, le chat et la generation gardaient l'ancien. Meme chemin
    pour un changement de taille de contexte, sur les deux moteurs."""
    from ui.ai_config import ai_config
    avant = ai_config._data["ai_backend"]
    ai_config._data["ai_backend"] = "lmstudio"        # en memoire seulement
    try:
        v = IAView()
        recus = []
        v.backend_activated.connect(recus.append)
        page = v._local.pages["lmstudio"]
        page.model_changed.emit("google/gemma-4-e4b")
        assert len(recus) == 1, "choisir un modele LM Studio ne recree rien"
        page.reglage_change.emit()
        assert len(recus) == 2, "changer le contexte ne recree rien"
        assert recus[-1].backend_id == "lmstudio"
        v._local.pages["ollama"].reglage_change.emit()
        assert len(recus) == 2, "un reglage d'Ollama ne touche pas LM Studio"
    finally:
        ai_config._data["ai_backend"] = avant


def main() -> int:
    test_iaview_builds_and_lists_providers()
    test_the_local_radio_groups_both_engines()
    test_the_engine_list_shows_brand_names()
    test_choosing_an_engine_changes_the_page()
    test_both_engines_have_the_SAME_context_setting()
    test_the_lmstudio_page_has_a_manage_models_button()
    test_the_lmstudio_page_has_an_address_field_prefilled()
    test_ollama_keeps_every_field_it_had()
    test_a_saved_local_backend_checks_the_local_radio()
    test_the_checked_id_survives_a_page_without_a_radio()
    test_both_pages_are_reachable_by_theme_and_language()
    test_the_dot_shares_the_key_rule_instead_of_judging_again()
    test_a_keyless_local_server_is_reported_configured()
    test_a_cloud_provider_without_its_key_is_reported_missing()
    test_the_sections_are_ordered_chatgpt_local_cloud()
    test_a_local_setting_change_refreshes_the_active_backend()
    print("OK : 17 tests")
    sys.stdout.flush()   # os._exit skips buffer flushing
    os._exit(0)   # avoid Qt teardown crash on exit (project convention for offscreen tests)


if __name__ == "__main__":
    main()

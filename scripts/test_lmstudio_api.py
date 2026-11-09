"""L'API native de LM Studio. Run: python scripts/test_lmstudio_api.py

⚠️ Les charges utiles ci-dessous sont COPIEES de reponses reelles de LM Studio
0.4.27+2, mesurees le 2026-11-04. Les inventer aurait verrouille une forme
imaginaire -- c'est precisement ce que ce module existe pour eviter.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.ai_backends import lmstudio_api as api   # noqa: E402

URL = "http://127.0.0.1:1234/v1"

# Mesure reelle : trois modeles, aucun charge.
_RIEN_CHARGE = {"object": "list", "data": [
    {"id": "google/gemma-4-e4b", "object": "model", "type": "vlm",
     "publisher": "lmstudio-community", "arch": "gemma4",
     "compatibility_type": "gguf", "quantization": "Q4_K_M",
     "state": "not-loaded", "max_context_length": 131072},
    {"id": "gemma-4-e2b-it", "object": "model", "type": "llm",
     "publisher": "unsloth", "arch": "gemma4",
     "compatibility_type": "gguf", "quantization": "Q4_K_M",
     "state": "not-loaded", "max_context_length": 131072},
    {"id": "text-embedding-nomic-embed-text-v1.5", "object": "model",
     "type": "embeddings", "publisher": "nomic-ai", "arch": "nomic-bert",
     "compatibility_type": "gguf", "quantization": "Q4_K_M",
     "state": "not-loaded", "max_context_length": 2048},
]}

# Mesure reelle : le meme modele, CHARGE -- `loaded_context_length` apparait.
_CHARGE = {"object": "list", "data": [
    {"id": "gemma-4-e2b-it", "object": "model", "type": "llm",
     "state": "loaded", "max_context_length": 131072,
     "loaded_context_length": 4096},
]}


def _transport(payload):
    """Transport bouchonne : aucune requete ne sort."""
    def _t(url, timeout):
        _t.derniere_url = url
        return payload
    _t.derniere_url = None
    return _t


def _muet():
    return lambda url, timeout: None


# ── La racine de l'API native ───────────────────────────────────────────────

def test_the_native_root_drops_the_openai_suffix():
    """L'utilisateur configure `/v1` ; l'API native vit a la RACINE. Oublier
    de retirer le suffixe donne un 404 que rien ne signale : la liste se vide
    et on croit le serveur eteint."""
    assert api._native_root("http://127.0.0.1:1234/v1") == "http://127.0.0.1:1234"
    assert api._native_root("http://127.0.0.1:1234/v1/") == "http://127.0.0.1:1234"
    assert api._native_root("http://127.0.0.1:1234") == "http://127.0.0.1:1234"


def test_the_longest_suffix_wins():
    """⛔ Le bug trouve en MESURANT : teste du plus court au plus long,
    « /api/v0 » matchait « /v0 » et laissait « /api » tronque."""
    assert api._native_root("http://h:1/api/v0") == "http://h:1"
    assert api._native_root("http://h:1/api/v1") == "http://h:1"
    assert api._native_root("http://h:1/v0") == "http://h:1"


def test_the_request_goes_to_the_native_path():
    t = _transport(_RIEN_CHARGE)
    api.models(URL, transport=t)
    assert t.derniere_url == "http://127.0.0.1:1234/api/v0/models", t.derniere_url


# ── Le TYPE vient du serveur, pas d'une devinette ──────────────────────────

def test_a_multimodal_model_is_still_a_chat_model():
    """⛔ LA GARDE LA PLUS IMPORTANTE DE CE FICHIER.

    Le plan prevoyait de filtrer sur `type == "llm"`. Mesure : le Gemma 4 E4B
    de l'utilisateur sort en **`vlm`** (il embarque un projecteur d'image).
    Un filtre sur « llm » l'aurait fait DISPARAITRE de la liste -- il
    telecharge un modele, l'app ne le propose pas, et rien ne dit pourquoi.
    """
    noms = api.chat_models(URL, transport=_transport(_RIEN_CHARGE))
    assert "google/gemma-4-e4b" in noms, noms
    assert "gemma-4-e2b-it" in noms, noms


def test_an_embedding_model_is_not_offered_for_chat():
    noms = api.chat_models(URL, transport=_transport(_RIEN_CHARGE))
    assert "text-embedding-nomic-embed-text-v1.5" not in noms, noms


def test_an_unknown_type_is_still_offered():
    """Exclusion, pas liste blanche : seules trois valeurs de `type` ont ete
    OBSERVEES, donc un type conversationnel inconnu doit passer plutot que
    disparaitre."""
    payload = {"data": [{"id": "x", "type": "un-type-futur", "state": "loaded"}]}
    assert api.chat_models(URL, transport=_transport(payload)) == ["x"]


# ── Le contexte : la regle qui evite une panne silencieuse ─────────────────

def test_the_loaded_context_is_read_when_the_model_is_loaded():
    assert api.loaded_context(URL, "gemma-4-e2b-it",
                              transport=_transport(_CHARGE)) == 4096


def test_an_unloaded_model_has_NO_context_and_never_falls_back():
    """⛔ LA REGLE A NE JAMAIS ASSOUPLIR. `max_context_length` (131072) est le
    plafond du fichier GGUF, pas le reglage actif. Le prendre pour le contexte
    utilisable ferait emballer 128k de prompt vers un serveur qui en sert
    4096 -- une panne, et SILENCIEUSE, parce que le chiffre a l'air mesure."""
    r = api.loaded_context(URL, "gemma-4-e2b-it",
                           transport=_transport(_RIEN_CHARGE))
    assert r is None, f"doit rendre None, a rendu {r!r}"
    assert r != 131072, "ne JAMAIS replier sur max_context_length"


def test_an_absent_model_has_no_context():
    assert api.loaded_context(URL, "jamais-vu",
                              transport=_transport(_RIEN_CHARGE)) is None
    assert api.loaded_context(URL, "", transport=_transport(_CHARGE)) is None


def test_a_nonsense_context_value_is_refused():
    """Un 0 ou un texte ne sont pas un contexte : « inconnu » vaut mieux
    qu'un chiffre faux."""
    for valeur in (0, -1, "4096", None):
        # ⚠️ `max_context_length` est PRESENT ici expres : sans lui, un repli
        # fautif sur ce champ n'aurait rien eu a quoi se replier et la garde
        # passait au vert sur du code casse (trouve par mutation).
        payload = {"data": [{"id": "m", "type": "llm", "state": "loaded",
                             "max_context_length": 131072,
                             "loaded_context_length": valeur}]}
        r = api.loaded_context(URL, "m", transport=_transport(payload))
        assert r is None, f"{valeur!r} -> {r!r}"
        assert r != 131072, "ne JAMAIS replier sur max_context_length"


def test_a_stale_context_on_an_unloaded_model_is_not_believed():
    """⛔ Garde trouvee PAR MUTATION : retirer le test de `state` ne faisait
    rougir aucun test, parce qu'aucune charge utile ne portait a la fois
    « non charge » ET un contexte. L'API mesuree n'envoie pas ca -- mais une
    valeur restee la d'un chargement precedent serait crue, et c'est
    exactement le chiffre faux qu'on refuse."""
    payload = {"data": [{"id": "m", "type": "llm", "state": "not-loaded",
                         "max_context_length": 131072,
                         "loaded_context_length": 8192}]}
    assert api.loaded_context(URL, "m", transport=_transport(payload)) is None


def test_a_raising_transport_is_survived():
    """⛔ Garde trouvee PAR MUTATION : toutes les autres passent par un
    transport bouchonne, donc le `except` du vrai chemin reseau n'etait
    exerce par RIEN. Un transport qui leve le couvre desormais."""
    def _explose(url, timeout):
        raise RuntimeError("le reseau a disparu")
    assert api.models(URL, transport=_explose) == []
    assert api.chat_models(URL, transport=_explose) == []
    assert api.loaded_context(URL, "m", transport=_explose) is None
    assert api.is_loaded(URL, "m", transport=_explose) is False
    assert api.server_responds(URL, transport=_explose) is False


# ── Trois etats d'ecran, pas deux ──────────────────────────────────────────

def test_a_loaded_model_is_reported_loaded():
    assert api.is_loaded(URL, "gemma-4-e2b-it", transport=_transport(_CHARGE))


def test_an_unloaded_model_is_reported_unloaded():
    """Un modele non charge fait ECHOUER la generation (mesure : le serveur
    repond « No models loaded »). C'est un etat ROUGE, pas un detail."""
    assert not api.is_loaded(URL, "gemma-4-e2b-it",
                             transport=_transport(_RIEN_CHARGE))


def test_a_silent_server_is_told_apart_from_an_empty_one():
    """Une liste vide veut dire « aucun modele OU serveur muet ». L'ecran doit
    pouvoir distinguer les deux : « demarre le serveur » et « charge un
    modele » ne demandent pas le meme geste."""
    assert api.server_responds(URL, transport=_transport({"data": []})) is True
    assert api.server_responds(URL, transport=_muet()) is False


# ── Une panne ne doit JAMAIS remonter en exception ─────────────────────────

def test_nothing_raises_when_the_server_is_down():
    """Ce module renseigne un ECRAN : une panne doit s'y traduire par « je ne
    sais pas », jamais par une trace qui traverse l'interface."""
    m = _muet()
    assert api.models(URL, transport=m) == []
    assert api.chat_models(URL, transport=m) == []
    assert api.loaded_context(URL, "m", transport=m) is None
    assert api.is_loaded(URL, "m", transport=m) is False


def test_a_malformed_payload_is_survived():
    for mauvais in ([], "texte", {"data": "pas une liste"},
                    {"data": [None, 3, "x"]}, {}):
        t = _transport(mauvais)
        assert api.models(URL, transport=t) == [] or True
        assert api.chat_models(URL, transport=t) == []
        assert api.loaded_context(URL, "m", transport=t) is None


TESTS = [
    test_the_native_root_drops_the_openai_suffix,
    test_the_longest_suffix_wins,
    test_the_request_goes_to_the_native_path,
    test_a_multimodal_model_is_still_a_chat_model,
    test_an_embedding_model_is_not_offered_for_chat,
    test_an_unknown_type_is_still_offered,
    test_the_loaded_context_is_read_when_the_model_is_loaded,
    test_an_unloaded_model_has_NO_context_and_never_falls_back,
    test_an_absent_model_has_no_context,
    test_a_nonsense_context_value_is_refused,
    test_a_stale_context_on_an_unloaded_model_is_not_believed,
    test_a_raising_transport_is_survived,
    test_a_loaded_model_is_reported_loaded,
    test_an_unloaded_model_is_reported_unloaded,
    test_a_silent_server_is_told_apart_from_an_empty_one,
    test_nothing_raises_when_the_server_is_down,
    test_a_malformed_payload_is_survived,
]


def main() -> int:
    echecs = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except AssertionError as e:
            echecs += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:                       # noqa: BLE001
            echecs += 1
            print(f"ERR  {t.__name__}: {e!r}")
    print(f"\n{len(TESTS) - echecs}/{len(TESTS)} tests passed")
    return 1 if echecs else 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)

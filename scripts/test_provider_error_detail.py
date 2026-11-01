"""Le message du fournisseur doit atteindre l'utilisateur.

L'app recevait de Google « This model models/gemini-2.5-flash is no longer
available to new users. Please upgrade » — la cause ET la solution — et
affichait « Modèle ou URL introuvable ». `HttpError` portait pourtant déjà le
corps de la réponse ; deux lignes le jetaient.

Run: python scripts/test_provider_error_detail.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.ai_backends.openai_compat import (
    _error_message, _provider_detail, _status_kind,
)

# Corps REEL renvoye par Google le 2026-09-03 (tronque) : une LISTE, pas un
# objet. C'est la forme qu'un extracteur naif aurait ratee.
_GEMINI_404 = json.dumps([{
    "error": {
        "code": 404,
        "message": ("This model models/gemini-2.5-flash is no longer "
                    "available to new users. Please upgrade."),
        "status": "NOT_FOUND",
    }
}])
_OPENAI_404 = json.dumps({"error": {"message": "The model `x` does not exist",
                                    "type": "invalid_request_error"}})


def test_a_list_body_is_read():
    """Gemini repond une LISTE. Un extracteur qui suppose un objet rendrait
    vide, et l'utilisateur reverrait le message aveugle."""
    d = _provider_detail(_GEMINI_404)
    assert "no longer available to new users" in d, d


def test_an_object_body_is_read():
    d = _provider_detail(_OPENAI_404)
    assert "does not exist" in d, d


def test_an_unparsable_body_falls_back_to_its_text():
    d = _provider_detail("<html>502 Bad Gateway</html>")
    assert "502" in d, d


def test_an_empty_body_yields_nothing():
    assert _provider_detail("") == ""
    assert _provider_detail("{}") == ""


def test_the_detail_is_bounded():
    """Un fournisseur peut repondre une page entiere : le message reste
    lisible dans un QLabel."""
    long_body = json.dumps({"error": {"message": "x" * 5000}})
    assert len(_provider_detail(long_body)) <= 240


def test_the_detail_is_on_one_line():
    """Des retours a la ligne bruts casseraient l'affichage."""
    d = _provider_detail(json.dumps({"error": {"message": "a\n\n  b\tc"}}))
    assert "\n" not in d and "\t" not in d, repr(d)
    assert d == "a b c", repr(d)


def test_the_generic_message_stays_in_front():
    """Le texte generique est TRADUIT, celui du fournisseur ne l'est pas :
    on ajoute, on ne remplace pas."""
    seul = _error_message("notfound")
    avec = _error_message("notfound", "detail du fournisseur")
    assert avec.startswith(seul), (seul, avec)
    assert "detail du fournisseur" in avec


def test_no_detail_leaves_the_message_untouched():
    """Le comportement d'avant, quand le corps ne porte rien."""
    assert _error_message("notfound", "") == _error_message("notfound")


def test_a_404_is_still_a_notfound():
    """La classification des statuts ne bouge pas."""
    assert _status_kind(404) == "notfound"
    assert _status_kind(401) == "auth"
    assert _status_kind(403) == "auth"
    assert _status_kind(429) == "quota"


def test_no_error_site_drops_the_body():
    """Garde structurelle : AUCUN traitement de `HttpError` ne doit fabriquer
    son message sans le corps de la reponse. C'est la ligne exacte qui jetait
    celui de Google.

    ⚠️ On n'ancre PAS un nombre de sites. La premiere version exigeait
    exactement 2 et a rougi des l'ajout d'un troisieme (la sonde de modele,
    2026-09-04) -- alors que ce site faisait precisement ce qu'il fallait.
    Un compte fige transforme un ajout correct en echec.
    """
    import ast
    chemin = ROOT / "ui" / "ai_backends" / "openai_compat.py"
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    blocs = 0
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Try):
            continue
        for handler in noeud.handlers:
            nom = getattr(handler.type, "id", None)
            if nom != "HttpError":
                continue
            corps = "\n".join(ast.unparse(n) for n in handler.body)
            # Seuls comptent les blocs qui FABRIQUENT un message pour
            # l'utilisateur. Ceux qui se contentent de classer l'erreur
            # (`list_models_detailed` rend un code, pas une phrase) n'ont
            # rien a faire du corps -- les exiger rendrait la garde fausse.
            if "_error_message" not in corps:
                continue
            blocs += 1
            assert "body" in corps, (
                f"un `except HttpError` ligne {handler.lineno} fabrique son "
                f"message sans le corps de la reponse :\n{corps}")
    assert blocs >= 2, f"{blocs} bloc(s) porteur(s) de message trouve(s)"


TESTS = [
    test_a_list_body_is_read,
    test_an_object_body_is_read,
    test_an_unparsable_body_falls_back_to_its_text,
    test_an_empty_body_yields_nothing,
    test_the_detail_is_bounded,
    test_the_detail_is_on_one_line,
    test_the_generic_message_stays_in_front,
    test_no_detail_leaves_the_message_untouched,
    test_a_404_is_still_a_notfound,
    test_no_error_site_drops_the_body,
]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  OK   {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""La pastille << Modele IA >> de la barre d'etat dit-elle la verite ?

⛔ **Le defaut d'origine (TODO #80)** : elle etait VERTE EN DUR --
`statusbar._refresh` ne consultait rien, aucune branche, aucun appel. Elle ne
se trompait que quand on avait besoin d'elle, le pire mode d'echec.

Ces tests pilotent `ai_status` (l'etat partage, sans reseau) et lisent la
couleur de la pastille. Aucun serveur n'est contacte : c'est tout l'interet
du montage -- le correctif naif (appeler `is_server_running()` dans
`_refresh`) coutait 2 030 ms serveur eteint, sur le fil graphique.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")

from PyQt6.QtWidgets import QApplication          # noqa: E402

_app = QApplication.instance() or QApplication([])

from ui.ai_status import ai_status                # noqa: E402
from ui.statusbar import StatusBar                # noqa: E402
from ui.theme import theme_manager                # noqa: E402


def _couleur(barre) -> str:
    """La couleur posee sur la pastille IA, extraite de sa feuille."""
    feuille = barre._dot_ia.styleSheet()
    return feuille.split("color: ")[1].split(";")[0].strip()


def test_sans_information_la_pastille_est_grise_pas_verte():
    """Le piege du correctif : sans etat publie, retomber sur du vert
    recreerait le defaut d'origine. None doit donner du GRIS."""
    ai_status.set_state(None)
    barre = StatusBar()
    c = theme_manager.current
    assert _couleur(barre) == c.text_secondary, _couleur(barre)
    assert _couleur(barre) != c.signal_ok


def test_un_backend_en_panne_rougit_la_pastille():
    """Le scenario du signalement : rouge dans l'onglet, vert en bas."""
    barre = StatusBar()
    c = theme_manager.current
    for kind in ("ollama_server_down", "ollama_not_installed", "cli_missing",
                 "cloud_key_missing"):
        ai_status.set_state(kind)
        assert _couleur(barre) == c.signal_error, (kind, _couleur(barre))


def test_le_modele_manquant_est_un_avertissement_pas_une_panne():
    barre = StatusBar()
    ai_status.set_state("ollama_model_missing")
    assert _couleur(barre) == theme_manager.current.signal_warn


def test_les_etats_sains_gardent_le_phosphore():
    barre = StatusBar()
    c = theme_manager.current
    for kind in ("ollama_ok", "cli_ok", "cloud_key_ok"):
        ai_status.set_state(kind)
        assert _couleur(barre) == c.signal_ok, (kind, _couleur(barre))


def test_un_etat_inconnu_est_traite_en_erreur_jamais_en_vert():
    """Un kind futur non prevu doit rougir : mieux vaut du rouge en trop
    qu'un retour silencieux au vert menteur."""
    barre = StatusBar()
    ai_status.set_state("etat_invente_par_une_version_future")
    assert _couleur(barre) == theme_manager.current.signal_error


def test_la_publication_declenche_le_rafraichissement():
    """La barre s'abonne a ai_status.changed : publier suffit, personne
    n'appelle _refresh a la main."""
    ai_status.set_state(None)
    barre = StatusBar()
    ai_status.set_state("ollama_server_down")
    assert _couleur(barre) == theme_manager.current.signal_error


def test_le_bloc_carte_survit_a_une_carte_branchee():
    """Le crash du 2026-08-28 : la branche CONNECTED du bloc carte referencait
    une variable supprimee avec le vert-en-dur. Elle ne tourne que carte
    BRANCHEE -- aucun test ne la couvrait, et un NameError dans un slot PyQt6
    abort NATIVEMENT (0xC0000409), sans traceback. On force l'etat via un
    substitut, on exige que _refresh survive et rende le phosphore."""
    import ui.statusbar as sb

    class _FauxBoard:
        state = sb.BoardState.CONNECTED
        env = "arduino"
        model = "uno_r3"

        class _Sig:
            def connect(self, *_): pass
        changed = _Sig()
        state_changed = _Sig()

    vrai = sb.board_manager
    sb.board_manager = _FauxBoard()
    try:
        barre = StatusBar()
        barre._refresh()          # NameError ici = le crash d'origine
        feuille = barre._dot.styleSheet()
        assert theme_manager.current.signal_ok in feuille, feuille
    finally:
        sb.board_manager = vrai


TESTS = [
    test_sans_information_la_pastille_est_grise_pas_verte,
    test_un_backend_en_panne_rougit_la_pastille,
    test_le_modele_manquant_est_un_avertissement_pas_une_panne,
    test_les_etats_sains_gardent_le_phosphore,
    test_un_etat_inconnu_est_traite_en_erreur_jamais_en_vert,
    test_la_publication_declenche_le_rafraichissement,
    test_le_bloc_carte_survit_a_une_carte_branchee,
]


def main() -> int:
    rate = 0
    for t in TESTS:
        try:
            t()
            print(f"  OK   {t.__name__}")
        except Exception as e:                     # noqa: BLE001
            rate += 1
            print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - rate}/{len(TESTS)} tests passed")
    return 1 if rate else 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)

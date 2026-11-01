"""QA (2026-08-10) : remplacer par l'engrenage un composant que le detecteur
reconnait AVEC CERTITUDE ne survivait pas a la reouverture du schema.

Mesure d'origine, reproduite ci-dessous :

    « Allume un relais sur la broche 7 »
    -> composant relay, _confidence == 'high'
    -> collect_ambiguous(netlist) == []

La boucle qui rejoue `_wiring_resolutions` n'itere que sur `collect_ambiguous`
(plus la cible de l'engrenage quand il y en a une). Le choix de l'utilisateur
etait donc ECRIT dans le projet et jamais RELU : a la reouverture, le relais
revenait.

Le defaut etait deja decrit pour les PLACEHOLDERS dans le docstring de
`_already_resolved_refs` (« nothing would re-apply its own saved resolution on
reopen »), sans etre generalise aux composants surs.

Ces tests montent la SITUATION -- un vrai netlist issu de `markers`, pas des
composants fabriques a la main.

Run : python scripts/test_confident_resolution_replay.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)   # ref module-level

from ui.studio_view import StudioView
from ui.wiring.ambiguity_dialog import collect_ambiguous
from ui.wiring.markers import extract_netlist

RELAY_CODE = """
const int RELAY_PIN = 7;
void setup() { pinMode(RELAY_PIN, OUTPUT); }
void loop() {
  digitalWrite(RELAY_PIN, HIGH); delay(2000);
  digitalWrite(RELAY_PIN, LOW);  delay(58000);
}
"""


def _netlist():
    return extract_netlist(RELAY_CODE, "arduino_uno_r3",
                           prompt="Allume un relais branche sur la broche 7")


def _view(resolutions: dict):
    """StudioView sans `__init__` : la methode testee ne lit que
    `_wiring_resolutions` et appelle `_resolution_key_for`."""
    sv = StudioView.__new__(StudioView)
    sv._wiring_resolutions = dict(resolutions)
    return sv


def test_the_situation_is_what_broke_it():
    """Le prealable, sans lequel les tests suivants ne prouveraient rien : le
    relais est SUR, donc absent de collect_ambiguous."""
    nl = _netlist()
    relay = next(c for c in nl.components if c.type == "relay")
    assert relay.attributes.get("_confidence") == "high"
    assert collect_ambiguous(nl) == []


def test_a_saved_swap_is_replayed_on_reopen():
    nl = _netlist()
    sv = _view({})
    relay = next(c for c in nl.components if c.type == "relay")
    key = sv._resolution_key_for(relay, nl)
    assert key[1], f"cle degeneree : {key!r}"
    sv._wiring_resolutions = {key: "buzzer"}

    assert sv._replay_confident_resolutions(nl, [], None) is True
    assert next(c for c in nl.components if c.ref == relay.ref).type == "buzzer"


def test_nothing_saved_changes_nothing():
    nl = _netlist()
    sv = _view({})
    assert sv._replay_confident_resolutions(nl, [], None) is False
    assert [c.type for c in nl.components] == ["relay"]


def test_the_gear_target_is_left_alone():
    """La cible de l'engrenage va etre rouverte : la figer ici reviendrait a
    ignorer le clic de l'utilisateur."""
    nl = _netlist()
    sv = _view({})
    relay = next(c for c in nl.components if c.type == "relay")
    sv._wiring_resolutions = {sv._resolution_key_for(relay, nl): "buzzer"}
    assert sv._replay_confident_resolutions(nl, [], relay.ref) is False
    assert relay.type == "relay"


def test_a_component_already_ambiguous_is_not_applied_twice():
    """La boucle principale s'en occupe deja ; le faire ici aussi appliquerait
    deux transformations a la suite sur le meme composant."""
    nl = _netlist()
    sv = _view({})
    relay = next(c for c in nl.components if c.type == "relay")
    sv._wiring_resolutions = {sv._resolution_key_for(relay, nl): "buzzer"}
    assert sv._replay_confident_resolutions(nl, [relay], None) is False
    assert relay.type == "relay"


def test_a_saved_type_equal_to_the_current_one_is_a_no_op():
    nl = _netlist()
    sv = _view({})
    relay = next(c for c in nl.components if c.type == "relay")
    sv._wiring_resolutions = {sv._resolution_key_for(relay, nl): "relay"}
    assert sv._replay_confident_resolutions(nl, [], None) is False


def test_a_degenerate_key_is_ignored():
    """Une cle dont la part « net » est vide est commune a TOUS les
    placeholders d'une meme fonction : s'y fier ferait muter le mauvais
    composant. Meme regle que `_already_resolved_refs`."""
    nl = _netlist()
    relay = next(c for c in nl.components if c.type == "relay")
    for pin in relay.pins:
        pin.net = ""
    sv = _view({})
    key = sv._resolution_key_for(relay, nl)
    sv._wiring_resolutions = {(key[0], ""): "buzzer"}
    assert sv._replay_confident_resolutions(nl, [], None) is False
    assert relay.type == "relay"


# ── QA du 2026-08-27 : le rejeu frappait les COMPAGNONS de l'inference ──────
# Trouve par mouchard in-app pendant la QA (section V). Le harnais ci-dessus
# monte ses netlists avec `extract_netlist`, qui ne fait PAS tourner
# l'inference : il n'y a donc jamais eu de resistance serie dans ces tests, et
# le cas le plus banal du corpus debutant -- une LED sur une broche numerique
# -- n'etait couvert par rien.
LED_CODE = """
void setup() { pinMode(7, OUTPUT); }
void loop() { digitalWrite(7, HIGH); }
"""


def _led_netlist():
    """Netlist COMPLETE (inference comprise) : c'est elle qui insere la
    resistance serie, donc elle seule qui reproduit la collision de cles."""
    from ui.wiring.layout.pipeline import analyze_netlist
    return analyze_netlist(LED_CODE, "arduino_uno_r3", prompt="")


def test_la_resistance_serie_partage_la_cle_de_sa_led():
    """Le prealable, sans lequel le test suivant ne prouverait rien.

    La LED vit sur un net interne (NET_x) et sa resistance fait le pont
    jusqu'a la broche Arduino. `_resolution_key_for` remonte ce pont pour la
    LED, et lit D7 DIRECTEMENT sur la resistance : les deux composants
    repondent donc a la MEME cle.
    """
    nl = _led_netlist()
    sv = _view({})
    led = next(c for c in nl.components if c.type == "led")
    res = next(c for c in nl.components if c.type == "resistor")
    assert sv._resolution_key_for(led, nl) == ("", "D7")
    assert sv._resolution_key_for(res, nl) == ("", "D7")


def test_la_resistance_serie_ne_recoit_pas_la_resolution_de_sa_led():
    """Repondre << LED >> a la modale, puis rouvrir, fabriquait une DEUXIEME
    LED : la resistance serie repond a la meme cle, n'est pas ambigue, et
    `_replay_confident_resolutions` balayait tout ce qui n'est pas ambigu.

    Mesure du 2026-08-27, deux tours sur le sketch ci-dessus : tour 1 rend
    `D1 led + R1 resistor` (correct), tour 2 rend `D1 led + R1 LED + deux
    resistances` -- et le pont de D1 etant casse, sa cle degenerait ensuite
    vers le net interne `NET_A`, qui partait dans le projet.
    """
    nl = _led_netlist()
    led = next(c for c in nl.components if c.type == "led")
    res = next(c for c in nl.components if c.type == "resistor")
    sv = _view({sv_key: "led" for sv_key in [("", "D7")]})
    # La LED est ambigue (sortie numerique nue) donc deja traitee ailleurs ;
    # la resistance, elle, ne l'est pas -- c'est tout le probleme.
    sv._replay_confident_resolutions(nl, [led], None)
    assert res.type == "resistor", (
        "la resistance serie a recu la resolution de la LED qu'elle accompagne")
    assert sum(1 for c in nl.components if c.type == "led") == 1, \
        [(c.ref, c.type) for c in nl.components]


def test_un_composant_sans_role_reste_rejouable():
    """La garde doit etre ETROITE : elle ne vise que les compagnons poses par
    l'inference (`role` = series / pullup), jamais un composant que le
    detecteur a produit. Sinon elle reprendrait d'une main ce que le correctif
    du 2026-08-10 avait donne -- le relais remplace a l'engrenage.
    """
    nl = _netlist()
    relay = next(c for c in nl.components if c.type == "relay")
    assert "role" not in relay.attributes, relay.attributes
    sv = _view({})
    sv._wiring_resolutions = {sv._resolution_key_for(relay, nl): "buzzer"}
    assert sv._replay_confident_resolutions(nl, [], None) is True
    assert relay.type == "buzzer"


def test_aucun_role_de_compagnon_n_echappe_a_la_liste():
    """Garde de derive : `COMPANION_ROLES` doit couvrir TOUS les roles ecrits
    par les deux modules qui posent des compagnons.

    Sans elle, ajouter demain une pull-up sous un role neuf reintroduirait le
    defaut EN SILENCE -- le nouveau compagnon partagerait la cle de son
    composant et recevrait son rejeu, sans qu'aucun test ne rougisse.
    """
    import re
    from ui.wiring.netlist import COMPANION_ROLES
    ecrits = set()
    for nom in ("ui/wiring/inference.py", "ui/wiring/implicit_actions.py"):
        chemin = Path(__file__).resolve().parents[1] / nom
        texte = chemin.read_text(encoding="utf-8")
        ecrits |= set(re.findall(r'"role":\s*"([a-z_]+)"', texte))
    assert ecrits, "aucun role trouve : la regex a decroche du code"
    orphelins = ecrits - set(COMPANION_ROLES)
    assert not orphelins, (
        f"roles de compagnon absents de COMPANION_ROLES : {sorted(orphelins)}")


TESTS = [
    test_the_situation_is_what_broke_it,
    test_a_saved_swap_is_replayed_on_reopen,
    test_nothing_saved_changes_nothing,
    test_the_gear_target_is_left_alone,
    test_a_component_already_ambiguous_is_not_applied_twice,
    test_a_saved_type_equal_to_the_current_one_is_a_no_op,
    test_a_degenerate_key_is_ignored,
    # QA 2026-08-27 : les compagnons de l'inference partagent la cle du
    # composant qu'ils accompagnent.
    test_la_resistance_serie_partage_la_cle_de_sa_led,
    test_la_resistance_serie_ne_recoit_pas_la_resolution_de_sa_led,
    test_un_composant_sans_role_reste_rejouable,
    test_aucun_role_de_compagnon_n_echappe_a_la_liste,
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

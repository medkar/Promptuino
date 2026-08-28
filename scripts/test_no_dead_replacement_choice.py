"""Le picker ne propose que ce qui ABOUTIT (TODO #67).

Le defaut repare : l'utilisateur ouvrait l'engrenage d'un BME280, choisissait
<< DS18B20 >> dans une liste que l'app lui presentait, validait -- et RIEN ne
changeait. `_apply_choice` jetait le `ReplaceResult` et sortait par un `return`
: pas de message, pas de trace. Mesure du 2026-08-26 : **110 choix morts**, sur
41 des 172 types remplacables.

DEUX CAUSES, et une seule etait celle du ticket :

  A. 13 choix ou la cible n'etait meme pas un type de cablage --
     `candidates_of_function` retombait sur le `corpus_id` quand `svg_type`
     manquait, sortant `adafruit-mpu6050` la ou l'app connait `mpu6050`.
  B. 97 choix ou la famille FONCTIONNELLE range ensemble ce que le moteur
     refuse : un BME280 (I2C) et un DS18B20 (OneWire) mesurent tous deux une
     temperature, mais ne se cablent pas pareil.

⛔ ET LA DEUXIEME PORTE ETAIT LE VRAI TROU. Filtrer la seule famille n'aurait
fait que DEPLACER le defaut : le balayage de bibliotheque du picker proposait
n'importe quel type des qu'on tapait son nom. D'ou un predicat unique applique
aux DEUX portes, et un test qui balaie les deux.

⚠️ CE TEST INTERROGE LE VRAI MOTEUR (`replace_component`), il ne recopie pas sa
regle. Reecrire << meme categorie ou transform dedie >> ici ferait passer au
vert deux copies du meme malentendu.

Run: python scripts/test_no_dead_replacement_choice.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.clarification_groups import CLARIFY_GROUPS, candidates_of_function
from ui.component_registry import REGISTRY, SOFTWARE_ONLY_DOCUMENTS
from ui.wiring.ambiguity_dialog import _DEFAULT_TRANSFORMS
from ui.wiring.categories import CATEGORY_OF_TYPE, category_of
from ui.wiring.component_replace import replace_component
from ui.wiring.netlist import Component, Netlist, Pin
from ui.wiring.picker_logic import visible_items
from ui.wiring.replacement_ui import (CROSS_CATEGORY_PROMOTIONS,
                                      can_replace_with,
                                      full_candidate_choices, is_replaceable)

_PINS = [Pin("VCC", "5V"), Pin("GND", "GND"), Pin("SDA", "A4"), Pin("SCL", "A5")]


def _composant(type_id: str) -> Component:
    return Component(ref="U1", type=type_id,
                     pins=[Pin(p.name, p.net) for p in _PINS])


def _aboutit(source: str, cible: str) -> bool:
    """Ce que le MOTEUR en dit, pour de vrai.

    Les cinq types a transform dedie sont exclus du test : `_apply_choice` les
    court-circuite AVANT d'atteindre le moteur, donc leur passer par ici
    mesurerait un chemin que la production ne prend pas."""
    if cible in _DEFAULT_TRANSFORMS:
        return True
    c = _composant(source)
    return replace_component(Netlist(board_id="uno", components=[c]),
                             "U1", cible).ok


def _types_remplacables() -> list[str]:
    return [t for t in sorted(CATEGORY_OF_TYPE) if is_replaceable(t)]


# -- L'INVARIANT ------------------------------------------------------------

def test_no_choice_in_the_list_is_refused_by_the_engine():
    """LA garde, porte n°1 : la liste que le picker affiche d'emblee."""
    morts = []
    for t in _types_remplacables():
        for cible, _ in full_candidate_choices(_composant(t), "fr"):
            if cible == t:
                continue
            if not _aboutit(t, cible):
                morts.append((t, category_of(t), cible, category_of(cible)))
    assert not morts, f"{len(morts)} choix morts, ex. {morts[:5]}"


def test_no_choice_reached_by_TYPING_is_refused_by_the_engine():
    """LA garde, porte n°2 -- celle qu'on aurait pu oublier.

    Le balayage de bibliotheque ajoute au picker TOUT type dont le nom matche
    la frappe. Sans filtre, taper << ds18b20 >> sur un projet BME280 le faisait
    apparaitre, cliquable, sans effet. Filtrer la seule famille fonctionnelle
    aurait laisse ce trou grand ouvert."""
    morts = []
    for t in _types_remplacables()[:60]:      # echantillon large, 4 frappes chacun
        for frappe in ("ds18b20", "st7735", "servo", "a"):
            g = visible_items(_composant(t), frappe, "fr")
            for groupe in (g.category, g.promotions, g.yours):
                for item in groupe:
                    if item.type_id == t or item.type_id.startswith("custom:"):
                        continue
                    if not _aboutit(t, item.type_id):
                        morts.append((t, frappe, item.type_id))
    assert not morts, f"{len(morts)} choix morts a la frappe, ex. {morts[:5]}"


# -- La regle est LUE, pas inventee -----------------------------------------

def test_the_cross_category_rule_comes_from_the_dedicated_transforms():
    """`can_replace_with` autorise un changement de categorie pour les cinq
    types a transform dedie -- et pour eux seuls. Ce n'est pas un choix
    arbitraire : ce sont exactement ceux dont quelqu'un a ECRIT le recablage.

    Si les deux listes divergent, le predicat ment dans un sens ou dans
    l'autre : soit il propose un swap sans recette, soit il cache une
    requalification qui marcherait."""
    assert set(CROSS_CATEGORY_PROMOTIONS) == set(_DEFAULT_TRANSFORMS)


def test_relaxing_the_engine_guard_is_not_the_fix():
    """⛔ Le moteur DOIT continuer de refuser un changement de categorie.

    Mesure du 2026-08-26, garde neutralisee pour voir : `bme280 -> ds18b20`
    sort un `DQ=A4` plausible, mais `bme280 -> dht22` cable **DATA sur GND**
    (capteur mort) et `oled_ssd1306 -> st7735` met **trois broches de signal
    sur GND**. Le repli positionnel produit du cablage FAUX aussi souvent que
    du juste. Ce test existe pour que la prochaine idee de << il suffit de
    lever la garde >> rougisse au lieu d'etre livree."""
    assert not _aboutit("bme280", "ds18b20")
    assert not _aboutit("oled_ssd1306", "st7735")


# -- La fuite d'identifiants corpus -----------------------------------------

def test_a_functional_family_never_yields_an_unresolved_corpus_id():
    """Cause A. `candidates_of_function` retombait sur le `corpus_id` quand
    `svg_type` manquait : `adafruit-mpu6050` la ou l'app connait `mpu6050`.

    La correspondance est DERIVEE du registre (`Component.documents`), jamais
    ecrite a la main -- six equivalences recopiees a la main deriveraient.

    ⚠️ LE CRITERE EST << L'IDENTITE EST-ELLE RESOLUE ? >>, PAS << EST-CE
    DESSINABLE ? >>, et deux exemptions le montrent. Premiere redaction de ce test : elle exigeait un type de
    cablage et faisait rougir sur `eeprom` -- qui est pourtant un composant du
    registre parfaitement resolu, simplement `wiring="none"` (la memoire est
    DANS le microcontroleur, il n'y a rien a brancher). Meme cas pour
    `ina3221`, `wiring="unknown"`. Confondre les deux, c'est appeler defaut ce
    que le registre dit correctement ; `can_replace_with` les ecarte en aval,
    et c'est la son role."""
    ids_composants = {c.id for c in REGISTRY}
    fuites = []
    for g in CLARIFY_GROUPS:
        for t in candidates_of_function(g.key):
            if t in CATEGORY_OF_TYPE or t in ids_composants:
                continue
            # `SOFTWARE_ONLY_DOCUMENTS` : un document que le registre exempte
            # EXPRES d'avoir un composant (`ntpclient`, `accelstepper`...). Lire
            # la meme liste que le detecteur de derive du registre, plutot que
            # d'en tenir une seconde qui divergerait.
            if t in SOFTWARE_ONLY_DOCUMENTS:
                continue
            fuites.append((g.key, t))
    assert not fuites, fuites


def test_the_registry_resolution_restores_real_candidates():
    """Le correctif ne fait pas que retirer : il RAJOUTE six candidats
    legitimes qui n'atteignaient jamais l'utilisateur."""
    assert "mpu6050" in candidates_of_function("imu")
    assert "ccs811" in candidates_of_function("co2")
    assert "lora_sx1276" in candidates_of_function("sans_fil")
    assert "tcs34725" in candidates_of_function("couleur")


# -- Ce qui doit RESTER -----------------------------------------------------

def test_the_legitimate_options_are_untouched():
    """Le filtre ne doit pas amputer ce qui marchait : meme categorie et
    requalifications restent proposees."""
    choix = [t for t, _ in full_candidate_choices(_composant("bme280"), "fr")]
    for attendu in ("aht20", "led", "buzzer", "servo"):
        assert attendu in choix, (attendu, choix)
    assert "ds18b20" not in choix, choix


TESTS = [
    test_no_choice_in_the_list_is_refused_by_the_engine,
    test_no_choice_reached_by_TYPING_is_refused_by_the_engine,
    test_the_cross_category_rule_comes_from_the_dedicated_transforms,
    test_relaxing_the_engine_guard_is_not_the_fix,
    test_a_functional_family_never_yields_an_unresolved_corpus_id,
    test_the_registry_resolution_restores_real_candidates,
    test_the_legitimate_options_are_untouched,
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

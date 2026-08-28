"""Pure helpers (no Qt) for the component replacement UI (SP2).

Headless-testable; consumed by AmbiguityDialog (via picker_logic).
"""
from __future__ import annotations

from .netlist import Component
from .categories import (category_of, candidates_in,
                         NON_REPLACEABLE, NO_SWAP_PEER)
from .instructions import _label as _human_label
from .replacement_catalog import label_of as _catalog_label
from ..clarification_groups import (CLARIFY_GROUPS, functions_of_component,
                                    candidates_of_function)


def build_replacement_choices(component: Component,
                              lang: str = "fr") -> list[tuple[str, str]]:
    """List (type_id, humanized label) of replacement candidates, current
    type first. Prefer the FUNCTIONAL family (screens with screens, temp
    sensors with temp sensors) when the component belongs to one; otherwise
    fall back to the SAME electrical category. [] if not replaceable."""
    functions = functions_of_component(component.type)
    if functions:
        # `functions` est un set : itérer dans l'ordre de déclaration de
        # CLARIFY_GROUPS, sinon l'ordre de la dropdown/des tuiles change à
        # chaque lancement (hash aléatoire des str — revue 2026-07-29 #3).
        ordered_keys = [g.key for g in CLARIFY_GROUPS if g.key in functions]
        seen: set[str] = set()
        members: list[str] = []
        for key in ordered_keys:
            for tid in candidates_of_function(key):
                if tid not in seen:
                    seen.add(tid)
                    members.append(tid)
        # #67 : la famille est fonctionnelle, pas electrique — elle range un
        # BME280 (I2C) et un DS18B20 (OneWire) ensemble parce qu'ils mesurent
        # tous deux une temperature. Le moteur, lui, refuse. On ne garde donc
        # que ce qui aboutira.
        ordered = [component.type] + [t for t in members
                                      if t != component.type
                                      and can_replace_with(component.type, t)]
        return [(t, _catalog_label(t) or _human_label(t, lang)) for t in ordered]

    cat = category_of(component.type)
    if cat is None or cat == NON_REPLACEABLE:
        return []
    if cat == NO_SWAP_PEER:
        # ⛔ NE PAS APPELER `candidates_in` ICI (TODO #62). `NO_SWAP_PEER` n'est
        # pas une classe electrique, c'est l'ABSENCE de classe : ses membres
        # n'ont en commun que de n'avoir aucun pair. Les grouper proposerait de
        # remplacer un HX711 (pont de jauge) par un TM1637 (afficheur 7
        # segments) -- verifie a l'ecriture, la liste sortait bien les 8 d'un
        # coup. Ce serait un defaut PIRE que l'engrenage muet qu'on repare.
        #
        # On rend donc le type COURANT seul. `full_candidate_choices` y ajoute
        # les echappatoires inter-categories, la bibliotheque de l'utilisateur
        # et la recherche : une liste de pairs vide se dit par une liste vide.
        return [(component.type,
                 _catalog_label(component.type)
                 or _human_label(component.type, lang))]
    members2 = candidates_in(cat)
    ordered = [component.type] + [t for t in members2 if t != component.type]
    return [(t, _catalog_label(t) or _human_label(t, lang)) for t in ordered]


# Cross-category promotions offered in BOTH modals when the pin could be a
# different KIND of component (mirrors AmbiguityDialog._CANDIDATES ; the guard
# test_promotion_lists_do_not_diverge keeps the two in sync).
CROSS_CATEGORY_PROMOTIONS: tuple[str, ...] = (
    "led", "buzzer", "servo", "dc_motor", "module_generic")


def can_replace_with(source_type: str, target_type: str) -> bool:
    """Ce remplacement ABOUTIRA-T-IL ? (TODO #67)

    ⚠️ LE PICKER N'A PAS LE DROIT DE PROPOSER AUTRE CHOSE. Avant ce predicat,
    il proposait 110 choix que `component_replace.replace_component` refusait :
    l'utilisateur ouvrait l'engrenage d'un BME280, choisissait << DS18B20 >>
    dans une liste que l'app lui presentait, validait -- et RIEN ne changeait.
    `_apply_choice` jetait le `ReplaceResult` et sortait par un `return` : pas
    de message, pas de trace.

    LA REGLE N'EST PAS INVENTEE, elle est LUE dans le code existant :
    `CROSS_CATEGORY_PROMOTIONS` et les transforms dedies d'`ambiguity_dialog`
    sont exactement la MEME liste de cinq (verifie, et `_apply_choice` court-
    circuite dessus avant d'atteindre le moteur). Un type a donc le droit de
    changer de categorie si, et seulement si, quelqu'un a ecrit comment le
    recabler.

    ⛔ ET IL NE SUFFIT PAS DE LEVER LA GARDE DU MOTEUR. Mesure du 2026-08-26,
    en la neutralisant pour voir : `bme280 -> ds18b20` sort un `DQ=A4`
    plausible, mais `bme280 -> dht22` cable **DATA sur GND** (capteur mort) et
    `oled_ssd1306 -> st7735` met **trois broches de signal sur GND**. Le repli
    positionnel du moteur produit du cablage FAUX aussi souvent que du juste --
    exactement la devinette presentee comme une certitude que les filets de
    `markers.py` existent pour supprimer. Faire aboutir ces swaps demande la
    connaissance de recablage PAR PAIRE, celle qu'encodent les cinq transforms.

    Module pur : ne lit que les categories, jamais `ambiguity_dialog` (Qt).
    """
    if target_type in CROSS_CATEGORY_PROMOTIONS:
        # Les cinq seuls types a transform dedie : `_apply_choice` les
        # court-circuite AVANT le moteur, donc ils aboutissent toujours.
        return True
    # Tout le reste EST la regle du moteur, appelee plutot que recopiee.
    from .component_replace import swap_is_allowed
    return swap_is_allowed(source_type, target_type)


def full_candidate_choices(component: Component,
                           lang: str = "fr") -> list[tuple[str, str]]:
    """SINGLE full candidate set for the disambiguation modals (beginner tiles
    AND advanced list): same-category / functional family
    (build_replacement_choices) FIRST, then the cross-category promotions
    (CROSS_CATEGORY_PROMOTIONS) not already present. Current type first,
    deduplicated. [] if not replaceable.

    The promotions are offered even for a specific component (e.g. a screen):
    they are the "this is actually a different kind of component" escape
    hatches, identical to what the advanced modal shows."""
    base = build_replacement_choices(component, lang)
    if not base:
        # Composant NON RECONNU (include inconnu -> boîte placeholder, ou
        # câblage I2C présumé) : aucune famille ni catégorie, mais l'utilisateur
        # doit quand même pouvoir dire ce que c'est — sinon la boîte est un
        # cul-de-sac alors que le bandeau promet « clique sur l'engrenage »
        # (revue 2026-07-29). Type courant + échappatoires inter-catégories.
        # Un type explicitement NON_REPLACEABLE (résistance, pile…) reste [].
        if not (is_uncertain_component(component)
                or is_user_declared(component)):
            return []
        base = [(component.type,
                 _catalog_label(component.type)
                 or _human_label(component.type, lang))]
    present = {t for t, _ in base}
    out = list(base)
    for t in CROSS_CATEGORY_PROMOTIONS:
        if t not in present:
            out.append((t, _catalog_label(t) or _human_label(t, lang)))
    # La bibliotheque de l'utilisateur, apres les promotions. C'est cet ajout
    # qui fait de la modale « la bibliotheque de composants » — et il est ici,
    # en amont de la divergence tuiles/liste, pour que la parite
    # debutant/avance reste vraie sans double maintenance.
    from ..declared_components import registry
    present = {t for t, _ in out}
    for decl in registry():
        if decl.type_id not in present:
            out.append((decl.type_id, decl.name))
    return out


def is_replaceable(type_id: str) -> bool:
    """True si l'utilisateur a le droit de corriger ce composant.

    ⚠️ LA REGLE EST << A QUI EST-IL ? >>, PAS << A-T-IL UN PAIR ? >> (TODO
    #62). Seule l'infrastructure que l'APP ajoute elle-meme -- resistance de
    limitation, pile, driver deduit d'un moteur -- reste non remplacable :
    l'utilisateur ne l'a pas choisie.

    Le fourre-tout d'avant CONTREDISAIT `build_replacement_choices`, qui
    consulte d'abord la famille FONCTIONNELLE et ignore la categorie. Mesure du
    2026-08-26 : un `tm1637` avait 9 candidats et un `tm1638` 17 -- que
    l'engrenage, coupe ici, n'a jamais pu montrer. Deux autorites en desaccord
    sur la meme question, et c'est la plus severe qui gagnait.
    """
    cat = category_of(type_id)
    return cat is not None and cat != NON_REPLACEABLE


# Attributs posés par les filets de sécurité du détecteur quand il N'EST PAS
# sûr de ce qu'il a dessiné (cf. markers.py) :
#   - `unrecognized`     : #include inconnu -> boîte placeholder NON câblée ;
#   - `presumed_wiring`  : include inconnu dans un sketch I2C -> câblage
#                          VCC/GND/SDA/SCL PRÉSUMÉ (pas lu dans le code).
# Ces composants ne sont dans aucune catégorie : sans ce marqueur ils
# seraient non éditables (aucune option proposée, engrenage muet).
UNCERTAIN_ATTRS: tuple[str, ...] = ("unrecognized", "presumed_wiring")


def is_uncertain_component(component: Component) -> bool:
    """True si le détecteur a produit ce composant « faute de mieux » (type non
    reconnu ou câblage présumé) — il doit rester corrigeable par l'utilisateur."""
    return any(bool(component.attributes.get(a)) for a in UNCERTAIN_ATTRS)


def is_user_declared(component: Component) -> bool:
    """True if the user described this component themselves (pins + wiring).

    Such a component belongs to no electrical category, so `is_replaceable`
    says False — without this flag it would become a dead end: no option
    offered, silent gear. Exactly the defect fixed on 2026-07-29 for
    placeholders."""
    return bool(component.attributes.get("user_declared"))


def should_warn_divergence(component: Component, chosen_type: str) -> bool:
    """True if a code/schematic divergence must be warned about before applying:
    signature-detected component AND chosen type different from the current one."""
    return (bool(component.attributes.get("signature_detected"))
            and chosen_type != component.type)

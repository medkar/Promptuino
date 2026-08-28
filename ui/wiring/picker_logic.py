"""Logique pure du picker de composants de la modale d'ambiguite.

Champ vide -> les candidats de la categorie detectee (full_candidate_choices,
la MEME source que l'ancien combo et les anciennes tuiles). Des qu'on tape ->
toute la bibliotheque (categories.CATEGORY_OF_TYPE + composants declares),
accents replies, insensible a la casse.

Pas de Qt : testable seul, et le widget n'a plus qu'a afficher.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from .categories import CATEGORY_OF_TYPE, NON_REPLACEABLE
from .replacement_ui import build_replacement_choices, full_candidate_choices


def _fold(text: str) -> str:
    """minuscules + accents replies, meme esprit que declared_components."""
    nfd = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(ch for ch in nfd if not unicodedata.combining(ch))


@dataclass(frozen=True)
class PickerItem:
    type_id: str
    name: str


@dataclass
class PickerGroups:
    category: list = field(default_factory=list)     # meme classe electrique
    promotions: list = field(default_factory=list)   # requalifications
    yours: list = field(default_factory=list)        # composants declares
    crossed_filter: bool = False                     # la frappe a depasse la categorie


def _label_for(type_id: str, lang: str) -> str:
    """Nom affichable d'un type — MEME resolution que `component_index`.

    `_label` n'est jamais faux : absent de `_TYPE_LABEL` il rend l'ID BRUT, si
    bien qu'un `x or y` ne joindrait jamais le catalogue de remplacement — le
    defaut deja paye au chantier du registre. C'est donc l'APPARTENANCE qui
    tranche, exactement comme `component_index._registry_components`, et ce
    n'est pas un detail de style : la fiche d'un composant tire son nom de la,
    un type sans fiche (`module_generic`…) tire le sien d'ici. Deux
    resolutions differentes nommeraient le meme composant de deux facons dans
    la meme fenetre.
    """
    from ..declared_components import TYPE_PREFIX
    from .instructions import _TYPE_LABEL, _label
    from .replacement_catalog import label_of
    if type_id.startswith(TYPE_PREFIX) or type_id in _TYPE_LABEL:
        return _label(type_id, lang)
    return label_of(type_id) or type_id


def _all_library_items(lang: str) -> list[PickerItem]:
    from ..declared_components import TYPE_PREFIX, registry
    items = [PickerItem(t, _label_for(t, lang))
             for t, cat in CATEGORY_OF_TYPE.items() if cat != NON_REPLACEABLE]
    items += [PickerItem(f"{TYPE_PREFIX}{d.id}", d.name) for d in registry()]
    return items


def _matches(item: PickerItem, needle: str, keywords: tuple = ()) -> bool:
    hay = _fold(item.name) + " " + _fold(item.type_id) \
        + " " + " ".join(_fold(k) for k in keywords)
    return needle in hay


def _keywords_of(type_id: str) -> tuple:
    """Mots-cles d'un type, cures ou declares.

    Les composants declares en ont aussi (c'est par eux que le prompt les
    reconnait) : les ignorer rendrait introuvable, dans SA propre
    bibliotheque, un composant que l'utilisateur a lui-meme nomme.

    Le balayage lineaire du registre (148 entrees) par item a l'air couteux —
    il ne l'est pas, MESURE le 2026-08-12 : une frappe complete coute 2,8 ms,
    dont 2,45 ms de repliage d'accents dans `_matches` et moins de 0,12 ms
    ici. L'indexer dans un dict memoise ne gagne que 3,5 % du total. Ne pas
    « optimiser » ce point sans remesurer : le vrai poste est le folding.
    """
    from ..declared_components import TYPE_PREFIX, find_by_type
    from ..component_registry import registry
    if type_id.startswith(TYPE_PREFIX):
        decl = find_by_type(type_id)
        return tuple(decl.keywords) if decl is not None else ()
    for comp in registry():
        if comp.id == type_id:
            return comp.keywords
    return ()


def visible_items(component, query: str, lang: str) -> PickerGroups:
    from ..declared_components import TYPE_PREFIX
    from .replacement_ui import can_replace_with
    groups = PickerGroups()
    base = full_candidate_choices(component, lang)
    # Rien a proposer = rien a proposer, MEME en tapant. Infrastructure
    # (resistance, pile, driver deja infere) : un type explicitement
    # NON_REPLACEABLE n'est jamais propose, et `full_candidate_choices` le dit
    # deja en rendant []. Mais le balayage de bibliotheque plus bas ne
    # demandait l'avis de personne : champ vide correctement inerte, une
    # lettre tapee et l'app proposait de transformer une resistance en LED. Un
    # picker construit sans passer d'abord par `replacement_ui.is_replaceable`
    # ne doit pas etre le trou par lequel l'infrastructure redevient
    # proposable.
    #
    # La condition DELEGUE au lieu de retester `category_of(...) ==
    # NON_REPLACEABLE` : ce predicat-la se tromperait sur les echappatoires du
    # 2026-07-29. Un placeholder tire son type du nom de la lib inconnue
    # (`_clean_lib_name`), qui peut tomber sur un id justement classe
    # NON_REPLACEABLE (`hx711`, `tm1637`…) ; `full_candidate_choices` lui rend
    # quand meme des candidats parce qu'il est `unrecognized`, et le bandeau
    # « clique sur l'engrenage pour corriger » ne doit pas mentir. Une seule
    # autorite, aucune divergence a maintenir.
    if not base:
        return groups
    same_cat = {t for t, _ in build_replacement_choices(component, lang)}
    # Le libelle rendu par `full_candidate_choices` (catalogue d'abord) est
    # ECARTE au profit de `_label_for` (appartenance a `_TYPE_LABEL` d'abord) :
    # cf. sa docstring — une seule regle de nommage par fenetre.
    for type_id, _ in base:
        item = PickerItem(type_id, _label_for(type_id, lang))
        if type_id.startswith(TYPE_PREFIX):
            groups.yours.append(item)
        elif type_id in same_cat:
            groups.category.append(item)
        else:
            groups.promotions.append(item)

    needle = _fold(query.strip())
    if not needle:
        return groups

    shown = {i.type_id for g in (groups.category, groups.promotions,
                                 groups.yours) for i in g}
    groups.category = [i for i in groups.category
                       if _matches(i, needle, _keywords_of(i.type_id))]
    groups.promotions = [i for i in groups.promotions
                         if _matches(i, needle, _keywords_of(i.type_id))]
    groups.yours = [i for i in groups.yours
                    if _matches(i, needle, _keywords_of(i.type_id))]
    # La frappe traverse le filtre : tout type de la bibliotheque qui matche
    # rejoint le groupe promotions (requalification), sans doublon.
    #
    # ⚠️ MAIS SEULEMENT S'IL PEUT ABOUTIR (TODO #67). C'est ICI que se trouvait
    # le vrai trou : filtrer la seule famille fonctionnelle n'aurait fait que
    # DEPLACER le defaut — ce balayage-ci proposait n'importe quel type du
    # catalogue des qu'on tapait son nom, et le moteur le refusait en silence.
    # Taper << ds18b20 >> sur un projet BME280 le faisait apparaitre, cliquable,
    # sans effet. Une seule autorite (`can_replace_with`) aux DEUX portes.
    for item in _all_library_items(lang):
        if item.type_id in shown:
            continue
        if not (item.type_id.startswith(TYPE_PREFIX)
                or can_replace_with(component.type, item.type_id)):
            continue
        if _matches(item, needle, _keywords_of(item.type_id)):
            target = (groups.yours if item.type_id.startswith(TYPE_PREFIX)
                      else groups.promotions)
            target.append(item)
            groups.crossed_filter = True
    return groups

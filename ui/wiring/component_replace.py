"""Pure engine for replacing a wired component with another of the same
category. Re-wires by role (power -> rails, signal -> kept MCU pin,
internal NET_* bridges traced back) and removes the inferred siblings tied to
the signal net of the old type ; the pipeline inference (apply_rules) regenerates
those of the new type at the next build.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .netlist import Component, Pin, Netlist
from .categories import category_of, NON_REPLACEABLE, NO_SWAP_PEER
from .layout.component_catalog import CATALOG, role_of

_ROLE_FIXED_NET = {
    "vcc": "5V",
    "gnd": "GND",
    "sda": "A4",
    "scl": "A5",
}
_BUS_NETS = frozenset(_ROLE_FIXED_NET.values())


def is_self_sufficient(type_id: str) -> bool:
    """Ce type se cable-t-il SANS rien emprunter au composant remplace ?

    Vrai quand CHACUNE de ses broches a un role a net fixe (`_ROLE_FIXED_NET` :
    vcc, gnd, sda, scl). Un tel composant n'a besoin d'aucune broche de signal
    de la source : le remplacement le cable entierement, sans deviner.

    ⚠️ C'EST UNE PROPRIETE STRUCTURELLE, PAS UN SEUIL (TODO #68). C'est ce qui
    la distingue des deux pistes ecartees : elle ne se calibre pas sur un
    echantillon, elle se LIT dans le catalogue. Mesure du 2026-08-26 : 37 types
    la satisfont (36 en I2C), et 180 swaps simules -- 5 sources tres
    differentes x 36 cibles -- ne produisent **aucune** broche mal cablee.

    ⛔ Et elle exclut exactement les cas casses : `ds18b20` (role `data`),
    `dht22` (`data`), `st7735` (`cs`/`sck`/`signal`), `ir_receiver` (`signal`)
    -- ceux ou le repli positionnel du moteur mettait une broche de signal sur
    GND, ou la broche OUT sur 5V.
    """
    entry = CATALOG.get(type_id)
    if entry is None:
        return False
    return all((role_of(type_id, i) or "signal") in _ROLE_FIXED_NET
               for i in range(1, entry.pin_count + 1))


def swap_is_allowed(source_type: str, target_type: str) -> bool:
    """LA regle du remplacement, en UN seul endroit.

    ⚠️ EXTRAITE ICI LE 2026-08-26 PARCE QUE LE DEPOT A PAYE CE DEFAUT TROIS
    FOIS DE SUITE : #62 (deux autorites sur << remplacable >>), #67 (le
    predicat de l'UI rouvrait par la recherche ce que l'autre bloquait), puis
    #68 -- ou une garde anti-divergence a montre que le MOTEUR acceptait
    `tm1637 -> hx711`, un afficheur 7 segments remplace par un pont de jauge,
    pendant que l'UI le refusait. Chaque fois, deux morceaux de code
    repondaient a la meme question et se contredisaient.

    `replacement_ui.can_replace_with` n'ajoute plus qu'une chose a ceci : les
    cinq requalifications a transform dedie, qui ne passent JAMAIS par le
    moteur (`_apply_choice` les court-circuite).

    Trois cas, dans l'ordre :
      - cible sans categorie, ou infrastructure ajoutee par l'app -> non ;
      - categorie DIFFERENTE -> oui si la cible est AUTOSUFFISANTE (TODO #68) ;
      - meme categorie -> oui, sauf pour `NO_SWAP_PEER`, qui n'est pas une
        classe electrique mais l'ABSENCE de classe : seule une famille
        FONCTIONNELLE partagee y autorise l'echange.
    """
    return not swap_refusal_reason(source_type, target_type)


def swap_refusal_reason(source_type: str, target_type: str) -> str:
    """Pourquoi ce remplacement est refuse, "" s'il est permis.

    ⚠️ REND LA RAISON, PAS UN BOOLEEN, et ce n'est pas cosmetique : une
    premiere version de `swap_is_allowed` rendait `ok=False` avec un message
    unique << remplacement refuse >>, et `test_cross_category_rejected` l'a
    attrapee. Trois causes tres differentes devenaient indiscernables dans le
    journal -- << ce type ne se remplace pas >>, << pas la meme categorie >> et
    << aucune famille commune >> demandent trois corrections differentes.
    """
    target_cat = category_of(target_type)
    if target_cat is None or target_cat == NON_REPLACEABLE:
        return f"type non remplaçable : {target_type}"
    source_cat = category_of(source_type)
    if target_cat != source_cat:
        if is_self_sufficient(target_type):
            return ""
        return (f"catégorie différente : {source_type}({source_cat}) -> "
                f"{target_type}({target_cat})")
    if target_cat == NO_SWAP_PEER:
        from ..clarification_groups import functions_of_component
        if functions_of_component(source_type) & functions_of_component(target_type):
            return ""
        return (f"aucune famille commune : {source_type} -> {target_type}")
    return ""


@dataclass
class ReplaceResult:
    ok: bool
    netlist: Netlist
    removed_refs: list[str] = field(default_factory=list)
    added_refs: list[str] = field(default_factory=list)
    divergence: bool = False
    reason: str = ""


def _trace_signal_net(net: str, netlist: Netlist, exclude_ref: str) -> str:
    """Traces an internal bridge net (NET_*) back to the real MCU pin via the
    inferred component that bridges it (e.g. series R: NET_X -> D5). Returns `net`
    as-is if it isn't internal or if the chain leads nowhere."""
    seen: set[str] = set()
    cur = net
    while cur.startswith("NET_") and cur not in seen:
        seen.add(cur)
        nxt = None
        for c in netlist.components:
            if c.ref == exclude_ref:
                continue
            nets = [p.net for p in c.pins]
            if cur in nets:
                other = [n for n in nets if n != cur]
                if other:
                    nxt = other[0]
                    break
        if nxt is None:
            break
        cur = nxt
    return cur


def _signal_nets_by_role(old: Component, netlist: Netlist) -> dict[str, str]:
    """MCU net carried by each 'signal-like' role pin of the old
    component, indexed by role. Internal bridge nets (NET_*) are traced
    back to the real MCU pin."""
    out: dict[str, str] = {}
    for idx, pin in enumerate(old.pins, start=1):
        role = role_of(old.type, idx) or "signal"
        if role not in _ROLE_FIXED_NET:
            out[role] = _trace_signal_net(pin.net, netlist, old.ref)
    return out


def replace_component(netlist: Netlist, ref: str, new_type: str) -> ReplaceResult:
    """Replaces component `ref` with `new_type` (same category mandatory).
    Mutates and returns the netlist. ok=False (netlist unchanged) if ref unknown, or
    new_type unknown/non-replaceable, or different category."""
    old = next((c for c in netlist.components if c.ref == ref), None)
    if old is None:
        return ReplaceResult(False, netlist, reason=f"ref inconnu : {ref}")

    new_cat = category_of(new_type)
    old_cat = category_of(old.type)
    refus = swap_refusal_reason(old.type, new_type)
    if refus:
        return ReplaceResult(False, netlist, reason=refus)

    divergence = bool(old.attributes.get("signature_detected"))
    # Traces computed BEFORE any sibling removal: otherwise the NET_* bridge of a
    # removed series R no longer leads anywhere and the signal pin dangles.
    signal_nets = _signal_nets_by_role(old, netlist)
    old_pins_traced = [
        (p.name, p.net if p.net in _BUS_NETS
         else _trace_signal_net(p.net, netlist, old.ref))
        for p in old.pins
    ]
    fallback_signal = next(iter(signal_nets.values()), None)

    # Removal of inferred siblings tied to the signal net (after computing traces).
    old_signal_nets = {p.net for p in old.pins} - _BUS_NETS
    removed = [c.ref for c in netlist.components
               if c.inferred and c.ref != ref
               and any(p.net in old_signal_nets for p in c.pins)]
    if removed:
        netlist.components = [c for c in netlist.components
                              if c.ref not in removed]

    new_entry = CATALOG.get(new_type)
    if new_entry is None:
        # Type outside CATALOG (generic rendering): keep the existing
        # topology, with the already-traced nets (no re-trace post-removal).
        new_pins = [Pin(name=n, net=net) for n, net in old_pins_traced]
    else:
        new_pins = []
        for idx in range(1, new_entry.pin_count + 1):
            role = role_of(new_type, idx) or "signal"
            label = new_entry.pin_labels.get(idx) or str(idx)
            if role in _ROLE_FIXED_NET:
                net = _ROLE_FIXED_NET[role]
            else:
                # signal-like: by role, otherwise positional (same index, net
                # traced from the old pin), otherwise 1st available signal, otherwise GND.
                net = signal_nets.get(role)
                if net is None and idx <= len(old_pins_traced):
                    net = old_pins_traced[idx - 1][1]
                if net is None:
                    net = fallback_signal or "GND"
            new_pins.append(Pin(name=label, net=net))

    old.type = new_type
    old.pins = new_pins
    old.inferred = False
    old.attributes["category"] = new_cat
    old.attributes["user_locked"] = True

    return ReplaceResult(True, netlist, removed_refs=removed,
                         divergence=divergence)

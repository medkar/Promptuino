"""Replay the user's declared-component library onto a freshly built netlist.

Runs as a DEDICATED pass, before the ambiguity cascade: that cascade only
iterates over `collect_ambiguous` (the `_confidence == "low"` components), and
a placeholder is deliberately NOT marked that way — which is what keeps it from
opening a modal on every schematic opening (decision 2026-07-29).

No Qt widget is built and no dialog is opened here — but this module is NOT
import-safe in a Qt-free context: it imports `.ambiguity_dialog` (for
`apply_saved_resolution`, the single application point, reused rather than
duplicated), which does `from PyQt6.QtWidgets import ...` at module level.
Unlike `.netlist`, whose no-Qt contract is real, this one only promises not to
construct or show anything. Consumed by StudioView.
"""
from __future__ import annotations

from .netlist import (
    Netlist, SEVERITY_INFO, SEVERITY_WARNING, SAFETY_NET_WARNING_CODES,
)
# TODO #45 : le predicat « ce net porte-t-il aussi un bus I2C ? » vit dans
# `instructions`, qui n'importe que `.netlist` — aucun cycle possible, d'ou
# l'import au niveau module. Le reutiliser plutot que reecrire la liste
# {A4, A5} est ce qui empeche les deux fichiers de deriver le jour ou une
# carte nomme ses broches autrement.
from .instructions import i2c_alias_for_net
from .ambiguity_dialog import apply_saved_resolution
from ..declared_components import (
    TYPE_PREFIX, find_by_header, find_by_type, normalize_header,
)

# Warnings raised by the detector's safety nets. Once the user has declared the
# component they no longer describe anything, so they are removed rather than
# left to contradict the schematic. Defined in `netlist` since the 2026-08-10
# QA: `_apply_declared` needs the SAME set, and having it private here is what
# let it keep `presumed_analog_component` alive.
_OBSOLETE_CODES = SAFETY_NET_WARNING_CODES

# TODO #45 : exclusions de la collision — on ne signale que ce qu'on SAIT.
# Les labels de bus valent des DEUX cotes (fiche et adverse) : le partage
# SPI/I2C est legitime, et c'est le LABEL du composant qui le dit, jamais la
# capacite de la broche carte (D13 -> ['digital','sck'] sur Uno : la capacite
# est une possibilite, pas un usage — le caillou du ticket). `_BUS_CAPS`
# (ui/generation/pin_reassign.py) n'a donc RIEN a faire ici : D13 est aussi la
# broche de la LED integree que tout sketch debutant pilote, et s'y fier
# rendrait muette la collision la plus frequente du corpus debutant.
_SHARED_BUS_LABELS = {"SDA", "SCL", "SCK", "MISO", "MOSI"}
_RAIL_NETS = {"GND", "5V", "3V3", "3.3V", "VIN"}

# Bookkeeping attribute set on a component right after an OPT-OUT transform
# is applied (e.g. custom:as7341 -> led). Needed because the transform
# usually WIPES `attributes` wholesale (`_to_led` does
# `c.attributes = {}`), taking the original "header" down with
# it. Without an echo, a component already opted out earlier in the SAME
# reopening (this pass runs before every ambiguity/gear edit, cf module
# docstring) would look like an ordinary "led" with no header at all -- so
# re-choosing the `custom:` type for it could never find, and therefore
# never clear, the opt-out it is meant to undo. Read by
# StudioView._declared_opt_candidate; already-normalized.
OPTOUT_HEADER_ECHO_ATTR = "_declared_header_echo"

# TODO #45, QA V1 (2026-08-27) : les trois constats que cette passe emet sur
# une fiche declaree. Retires ensemble avant tout rejeu -- un verdict se
# REMPLACE, il ne s'empile pas. Les deux premiers sont aussi ceux qui donnent
# la pastille d'attention (`_CONFRONTATION_CODES`, wiring_diagram_dialog) ;
# le troisieme est la reassurance qui les accompagne.
_VERDICT_CODES = frozenset({
    "declared_pins_diverge_from_code",
    "declared_pin_already_claimed",
    "declared_unconnected_pins",
})

# La preuve du code (broches vues au constructeur), photographiee AVANT toute
# transformation. `apply_saved_resolution` vide `SAFETY_NET_ATTRS`, donc
# l'attribut ne survit pas a la premiere application -- or le verdict doit
# pouvoir etre rejoue APRES la modale (cf. `refresh_declared_verdict`).
CTOR_SNAPSHOT_KEY = "_declared_ctor_pins"


def capture_constructor_pins(netlist: Netlist) -> dict[str, list[str]]:
    """Photographie `constructor_pins` pour toute la netlist, et la range
    dans `metadata`.

    A appeler juste apres l'analyse, avant que quoi que ce soit ne mute la
    netlist. Idempotente au sens ou rappeler la fonction sur une netlist deja
    transformee ECRASERAIT la photo par une version appauvrie : c'est pour ca
    que les deux appelants la posent au plus tot et que le rejeu se contente
    de RELIRE `metadata`.
    """
    snap = {c.ref: list(c.attributes.get("constructor_pins") or [])
            for c in netlist.components
            if c.attributes.get("constructor_pins")}
    netlist.metadata[CTOR_SNAPSHOT_KEY] = snap
    return snap


def refresh_declared_verdict(netlist: Netlist) -> None:
    """Rejoue le verdict sur la netlist que l'utilisateur va VRAIMENT voir.

    Le defaut d'origine (trouve en QA V1, 2026-08-27) : la confrontation
    naissait dans `apply_library_to_netlist`, appelee AVANT l'ouverture de la
    modale d'ambiguite. Or c'est DANS cette modale que le crayon d'une card
    modifie la fiche. Le verdict portait donc sur l'etat d'AVANT l'action de
    l'utilisateur -- un tour de retard systematique, dans les deux sens :
    corriger les broches laissait le message a l'ecran, et en casser de
    nouvelles ne disait rien du tout. Ce silence-la etait le plus grave : le
    schema dessinait sereinement une fiche que le code contredit.

    ⚠️ La population n'est PAS `changed` (les refs que la passe bibliotheque
    a transformees) mais « tout ce qui EST une fiche declaree a l'arrivee ».
    Il le faut : un composant declare pour la premiere fois DANS la modale
    n'a jamais traverse la passe bibliotheque -- il n'existait aucune entree
    a rejouer quand elle a tourne. Elargissement assume et volontaire : une
    fiche appliquee depuis une resolution de projet est desormais confrontee
    elle aussi, ce qui est exactement la promesse du ticket.

    ⚠️ A appeler AVANT `inference.apply_rules`, la ou la netlist a la meme
    forme qu'au moment ou le verdict etait rendu jusqu'ici. Plus tard, les
    composants que l'inference INSERE (pull-up d'un DS18B20 sur le net DATA
    de son propre capteur...) deviendraient des adverses de collision : on
    fabriquerait des faux positifs en croyant seulement corriger un ordre.
    """
    netlist.warnings = [w for w in netlist.warnings
                        if w.code not in _VERDICT_CODES]
    refs = [c.ref for c in netlist.components
            if c.type.startswith(TYPE_PREFIX)]
    if refs:
        _emit_verdict(netlist, refs,
                      netlist.metadata.get(CTOR_SNAPSHOT_KEY) or {})


def apply_library_to_netlist(netlist: Netlist,
                             skip_refs=frozenset(),
                             opt_outs: dict[str, str] | None = None
                             ) -> list[str]:
    """Turn every still-unrecognised box whose header matches the library into
    the declared component. Returns the refs that changed.

    `skip_refs`: components already resolved by the current project — the user
    acted HERE, which is more specific than their library.

    `opt_outs`: normalized header -> type_id the user picked INSTEAD of the
    declaration, in a PAST session (gear -> "this is not my declared
    component", picked something else). Checked FIRST: an opt-out for this
    header wins over the library entry every time the schematic reopens, not
    just in the session where the choice was made — `skip_refs` alone cannot
    carry that, because a placeholder's `_resolution_key_for` degenerates to
    an empty net and is deliberately excluded from `_already_resolved_refs`.
    If the opt-out itself names a `custom:` type, it is applied exactly like
    a normal declaration (same dispatch inside `apply_saved_resolution`).
    """
    opt_outs = opt_outs or {}
    changed: list[str] = []
    # La photo doit exister meme si cette passe ne change RIEN : un composant
    # declare pour la premiere fois dans la modale n'a aucune entree a
    # rejouer ici, et c'est pourtant lui que `refresh_declared_verdict` devra
    # confronter ensuite. Posee seulement si l'appelant ne l'a pas deja
    # faite -- StudioView la prend au plus tot, juste apres l'analyse.
    if CTOR_SNAPSHOT_KEY not in netlist.metadata:
        capture_constructor_pins(netlist)
    ctor_by_ref: dict[str, list[str]] = {}
    for c in list(netlist.components):
        if c.ref in skip_refs:
            continue
        if not (c.attributes.get("unrecognized")
                or c.attributes.get("presumed_wiring")):
            continue
        header_key = normalize_header(c.attributes.get("header") or "")
        # TODO #45 : la preuve (broches vues dans le constructeur) est VIDEE
        # par apply_saved_resolution (SAFETY_NET_ATTRS) — c'est voulu, ces
        # attributs signifient « filet actif ». On la LIT avant, on ne la
        # garde pas : markers la recalcule a chaque analyse, donc la
        # confrontation ci-dessous compare toujours au code ACTUEL.
        #
        # ⚠️ Indexe par `c.ref` capture ICI et relu APRES transformation :
        # ca ne tient que parce que les deux chemins d'application mutent le
        # composant SUR PLACE, et aucun des deux ne le PROMET. Si l'un se met
        # a renumeroter les refs, la confrontation ne retrouvera plus rien et
        # l'avertissement disparaitra EN SILENCE -- la pire espece de panne
        # pour un ticket dont le sujet est justement le silence.
        ctor_by_ref[c.ref] = list(c.attributes.get("constructor_pins") or [])
        opt_out_type = opt_outs.get(header_key) if header_key else None
        if opt_out_type is not None:
            apply_saved_resolution(c, opt_out_type, netlist)
            if c.type == opt_out_type:
                changed.append(c.ref)
                if not opt_out_type.startswith(TYPE_PREFIX):
                    c.attributes[OPTOUT_HEADER_ECHO_ATTR] = header_key
            continue
        decl = find_by_header(c.attributes.get("header") or "")
        if decl is None:
            continue
        apply_saved_resolution(c, decl.type_id, netlist)
        if c.type == decl.type_id:      # guard: registry entry vanished
            changed.append(c.ref)
    if not changed:
        return []
    netlist.warnings = [
        w for w in netlist.warnings
        if not (w.code in _OBSOLETE_CODES
                and any(r in changed for r in w.refs))
    ]
    _emit_verdict(netlist, changed, ctor_by_ref)
    return changed


def _emit_verdict(netlist: Netlist, refs, ctor_by_ref) -> None:
    """Les trois constats portes sur une fiche declaree : la divergence avec
    le code, la collision avec le schema, puis la reassurance.

    Extrait de `apply_library_to_netlist` pour pouvoir etre rejoue apres la
    modale (`refresh_declared_verdict`, QA V1 du 2026-08-27) : la fiche peut
    changer APRES que la passe bibliotheque a rendu son verdict, et un
    verdict perime est soit un mensonge, soit un silence.
    """
    for ref in refs:
        c = netlist.by_ref(ref)
        if c is None or not c.type.startswith(TYPE_PREFIX):
            # Opted out to a non-declared type (e.g. "led"): the component is
            # no longer a declaration, so "unconnected pins" is not this
            # module's business to warn about.
            continue
        entry = find_by_type(c.type)
        name = entry.name if entry is not None else c.type
        # TODO #45, warning 1 : ces valeurs sont passees au CONSTRUCTEUR du
        # composant, et la fiche ne les cable pas. Deux choses visibles se
        # contredisent -- c'est tout ce qu'on affirme, et le message ne dit
        # rien de plus. Seule direction sure : l'inverse (« ta fiche cable D9
        # que le code ne montre pas ») serait un faux positif systematique,
        # l'indice ne couvrant ni `begin(pin)` ni l'I2C sans constructeur.
        #
        # ⚠️ L'INDICE N'EST PAS UNE PREUVE D'USAGE, et le message ne le
        # pretend plus. `markers._constructor_pins_for` retient TOUT litteral
        # 0..13 de N'IMPORTE QUEL argument -- `markers` l'ecrit lui-meme la ou
        # il pose l'attribut : « indice utile SANS inventer de cablage ». Donc
        # `MonEcran lcd(16, 2)` fait sortir « D2 » (16 est hors plage et
        # tombe ; 2 devient une broche). FAUX POSITIF CONNU ET ASSUME : c'est
        # le prix du refus de se taire. D'ou un message qui rapporte le FAIT
        # (« le code passe ces valeurs au constructeur ») et invite a ignorer
        # si ce ne sont pas des broches, au lieu d'affirmer un usage.
        # Fige par test_un_litteral_qui_n_est_pas_une_broche_declenche_quand_meme.
        # Ne PAS durcir en devinant (position de l'argument, nom de la classe) :
        # ce serait exactement l'invention de cablage que le filet refuse.
        #
        # L'ORDRE COMPTE, mais CE MODULE NE CONTROLE QUE LE SIEN. La pastille
        # d'attention est donnee a ce ref PARCE QUE ce warning existe --
        # clause `_CONFRONTATION_CODES` de `_compute_info_refs`
        # (wiring_diagram_dialog), ajoutee par ce meme ticket, sans laquelle
        # un composant declare n'en avait AUCUNE (la declaration vide les
        # attributs de filet).
        #
        # ⚠️ CE PAVE A LONGTEMPS AFFIRME QUE L'ORDRE D'EMISSION DECIDAIT DE
        # L'INFOBULLE. Ce n'est plus vrai (revue finale, 2026-08-27) :
        # `_compute_info_tooltips` fait desormais gagner les codes de
        # confrontation, en PASSE 1, avant sa regle « premier warning par
        # ref ». Il le fallait -- cette regle depend de l'ordre d'emission de
        # TOUTE la netlist, pas du notre : `pin_double_use` est emis dans
        # `analyze_netlist`, donc bien avant nous, et gagnait toujours.
        #
        # Ce qu'on ordonne ici reste reel et garde sa valeur : les lignes du
        # panneau d'instructions, et le depart entre DEUX confrontations
        # portant la meme ref (la passe 1 retient la premiere). Nos trois
        # ajouts sont tous en fin de liste ; l'ordre RELATIF de la
        # contradiction et de la reassurance est verrouille par
        # test_la_contradiction_passe_avant_la_reassurance.
        declared_nets = {pin.net for pin in c.pins if pin.net}
        missing = [net for net in (ctor_by_ref.get(ref) or [])
                   if net not in declared_nets]
        if missing:
            pins_str = ", ".join(missing)
            netlist.add_warning(
                code="declared_pins_diverge_from_code",
                severity=SEVERITY_WARNING,
                message=(f"Le code passe {pins_str} au constructeur de ce "
                         f"composant, et la fiche « {name} » ne les câble "
                         f"pas. Harmonise, ou ignore si ce ne sont pas des "
                         f"broches."),
                refs=[ref],
                params={"name": name, "pins": pins_str},
            )
        # TODO #45, warning 2 : un net de signal de la fiche deja porte par
        # un AUTRE composant du schema. Meme discipline que le warning 1 --
        # on ne signale que ce qu'on SAIT etre une collision, d'ou trois
        # exclusions (rails, alias I2C, labels de bus des DEUX cotes), toutes
        # motivees au-dessus de `_SHARED_BUS_LABELS`.
        #
        # ⚠️ `refs` porte les DEUX composants, mais le MESSAGE est ecrit du
        # point de vue de la FICHE. La pastille d'attention ne va donc qu'a
        # la PREMIERE ref (`_confrontation_addressees`, wiring_diagram_dialog,
        # revue finale du 2026-08-27) : un servo detecte avec certitude, sans
        # aucune pastille avant ce ticket, en gagnait une qui le designait
        # lui-meme comme le coupable. Le lien vers l'adverse garde sa valeur
        # ailleurs -- ne pas retirer la 2e ref pour autant.
        #
        # ⚠️ LIMITE ASSUMEE : la ref adverse est nommee TELLE QUELLE. Si le
        # net Arduino est porte par la resistance serie d'une LED (la LED
        # vivant, elle, sur un net interne NET_x), c'est la resistance qu'on
        # nomme — exact, a defaut d'etre elegant. Remonter le bridge jusqu'au
        # composant « interessant » (ce que fait `_arduino_signal_pin` cote
        # ambiguite) est DIFFERE : le net annonce, lui, est juste dans tous
        # les cas, et c'est lui qui rend le constat actionnable.
        #
        # Emis APRES la divergence et AVANT `declared_unconnected_pins` : cf.
        # le pave d'ordre ci-dessus -- une reassurance ne doit jamais passer
        # devant un constat dans le panneau d'instructions, et entre deux
        # confrontations sur la meme ref c'est la premiere qui prend
        # l'infobulle.
        seen_nets: set[str] = set()
        for pin in c.pins:
            net = (pin.net or "").strip()
            # Un net vide, c'est une broche non connectee — le sujet du
            # warning suivant, pas de celui-ci. Et un seul constat par net :
            # une fiche qui met deux broches sur D7 n'a pas a le dire deux
            # fois.
            if not net or net in seen_nets:
                continue
            seen_nets.add(net)
            if net.upper() in _RAIL_NETS or i2c_alias_for_net(net):
                continue
            if (pin.name or "").strip().upper() in _SHARED_BUS_LABELS:
                continue
            # La PREMIERE ref adverse suffit : le constat est « ce trou est
            # deja pris », pas un inventaire de tout ce qui s'y branche.
            other_ref = next(
                (o.ref for o in netlist.components if o.ref != ref
                 for op in o.pins
                 if op.net == net
                 and (op.name or "").strip().upper() not in _SHARED_BUS_LABELS),
                None)
            if other_ref is None:
                continue
            netlist.add_warning(
                code="declared_pin_already_claimed",
                severity=SEVERITY_WARNING,
                message=(f"La fiche « {name} » câble {net}, déjà utilisée "
                         f"par un autre composant du schéma ({other_ref})."),
                refs=[ref, other_ref],
                params={"name": name, "net": net, "ref": other_ref},
            )
        # Coexiste volontairement avec les deux confrontations ci-dessus :
        # des constats independants, des messages differents, aucun
        # dedoublonnage. D'ou des `if` plutot que le `continue` d'origine,
        # qui sautait toute la suite des qu'aucune broche n'etait libre.
        open_pins = [p.name for p in c.pins if not p.net]
        if open_pins:
            pins_str = ", ".join(open_pins)
            netlist.add_warning(
                code="declared_unconnected_pins",
                severity=SEVERITY_INFO,
                message=f"« {name} » : broches non connectées : {pins_str}.",
                refs=[ref],
                params={"name": name, "pins": pins_str},
            )

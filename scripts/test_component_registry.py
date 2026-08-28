"""The component registry: one identity per component.

Before this module a component existed nowhere as an object. It was rebuilt on
the fly by FOUR independent join mechanisms that did not know each other --
literal string equality between corpus ids and catalog types (51 cases, working
by accident), a hand-written alias table, the `svg_type` of the clarification
groups, and `HardwareModule.chips`. They already disagreed: the "temperature"
group referenced a `bme280` absent from the catalog, silently absorbed by a
generic rectangle.

Run: python scripts/test_component_registry.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ui.component_registry as reg


def test_vocabularies_are_closed_and_disjoint_enough():
    assert "sensor" in reg.FUNCTIONS and "motor_driver" in reg.FUNCTIONS
    # `Sensor` AND `Sensors` both exist as corpus categories -- the registry
    # must NOT inherit that mess, so its vocabulary is its own.
    assert "Sensors" not in reg.FUNCTIONS
    assert set(reg.MOUNTINGS) == {"breadboard", "off_board", "on_mcu"}
    assert set(reg.WIRING_STATES) == {"known", "unknown", "none"}


def test_component_fields_and_defaults():
    c = reg.Component(id="led", function="output", mounting="breadboard",
                      wiring="known")
    assert c.documents == () and c.keywords == ()
    # Tache 1 (#44) : les champs lib/description par defaut = etat "none",
    # exactement ce que les entrees existantes disaient deja.
    assert c.lib_name == ""
    assert c.lib_to_determine is False
    assert c.description == ""


def test_every_entry_uses_the_closed_vocabularies():
    """A typo in a function name must fail the suite, not silently create a
    16th category the way the corpus did."""
    for c in reg.registry():
        assert c.function in reg.FUNCTIONS, (c.id, c.function)
        assert c.mounting in reg.MOUNTINGS, (c.id, c.mounting)
        assert c.wiring in reg.WIRING_STATES, (c.id, c.wiring)


def test_ids_are_unique():
    ids = [c.id for c in reg.registry()]
    assert len(ids) == len(set(ids)), \
        [i for i in ids if ids.count(i) > 1][:10]


def test_by_id_and_components_for_document():
    probe = reg.Component(id="__probe__", function="sensor",
                          mounting="breadboard", wiring="unknown",
                          documents=("doc-a", "doc-b"))
    items = (*reg.registry(), probe)
    assert reg.by_id("__probe__", items) is probe
    assert reg.by_id("__absent__", items) is None
    assert probe in reg.components_for_document("doc-a", items)
    assert reg.components_for_document("doc-absent", items) == ()


def test_non_component_catalog_types_are_declared():
    """`resistor`, `battery_external` and `module_generic` are structure or a
    detector fallback, not components anyone looks up. They are the ONLY
    catalog types allowed to have no registry entry."""
    assert reg.NON_COMPONENT_CATALOG_TYPES == frozenset(
        {"resistor", "battery_external", "module_generic"})


def _catalog():
    from ui.wiring.layout.component_catalog import CATALOG
    return CATALOG


def _corpus_ids():
    from ui.rag import all_corpus_entries
    return {str(e.get("id") or "") for e in all_corpus_entries()}


def test_guard_1_every_catalog_type_has_an_entry():
    """Otherwise a component the schematic can draw is invisible to the tab."""
    missing = sorted(set(_catalog())
                     - reg.NON_COMPONENT_CATALOG_TYPES
                     - {c.id for c in reg.registry()})
    assert not missing, missing


def test_guard_2_every_referenced_document_exists():
    """No dangling reference. This is what the four tacit conventions could
    never guarantee -- the `bme280` of the temperature clarify group pointed at
    a catalog entry that did not exist, silently."""
    known = _corpus_ids()
    dangling = sorted({d for c in reg.registry() for d in c.documents
                       if d not in known})
    assert not dangling, dangling


def test_guard_3_wiring_state_matches_the_catalog():
    """`known` <=> present in the catalog. Combined with guard 1: the catalog
    is EXACTLY the set of drawable components. Filling a pinout in later
    therefore becomes a deliberate move, never a side effect."""
    cat = set(_catalog())
    for c in reg.registry():
        if c.wiring == "known":
            assert c.id in cat, f"{c.id} says known but has no catalog entry"
        else:
            assert c.id not in cat, f"{c.id} is {c.wiring} but IS in the catalog"


def test_off_board_mounting_matches_the_layout_engine():
    """`mounting == "off_board"` <=> the id has a dedicated footprint in
    `_OFF_BB_DIMS` (`ui/wiring/layout/layout.py`), the placement engine's own
    source of truth for what does NOT sit on the breadboard. `mounting` is
    hand-written data (this module stays Qt/wiring-free), so nothing enforced
    it against the engine that actually cares -- six motor/driver types
    (l298n, uln2003, l293d_module, dc_motor, stepper_motor, nema17) were
    entered as `breadboard` although the router places them off-BB. Catches
    drift in BOTH directions: a catalog type added off-BB without being
    marked, or a type marked off-BB that the engine does not actually treat
    that way."""
    from ui.wiring.layout.layout import _OFF_BB_DIMS
    off_bb_types = set(_OFF_BB_DIMS) - reg.NON_COMPONENT_CATALOG_TYPES
    for c in reg.registry():
        if c.wiring != "known":
            continue
        expected = c.id in off_bb_types
        actual = c.mounting == "off_board"
        assert actual == expected, (
            c.id, c.mounting, "in _OFF_BB_DIMS" if expected else "not in _OFF_BB_DIMS")


def test_guard_5_clarify_group_svg_types_resolve():
    """Green from day one: `wiring='unknown'` being a legal state, the `bme280`
    ghost enters the registry as a real component we cannot draw yet."""
    from ui.clarification_groups import CLARIFY_GROUPS
    ids = {c.id for c in reg.registry()}
    unresolved = sorted({cand.svg_type for g in CLARIFY_GROUPS
                         for cand in g.candidates
                         if cand.svg_type and cand.svg_type not in ids})
    assert not unresolved, unresolved


def test_every_named_wiring_type_has_an_entry():
    """The `markers` -> registry direction, covered by NOTHING until now.

    The other guards walk catalog -> registry, corpus -> registry,
    `_OFF_BB_DIMS` -> registry, `svg_type` -> registry, `chips` -> registry and
    registry -> labels. Yet the checklist
    "Ajouter un composant au pipeline de câblage" in CLAUDE.md describes a case
    (b) -- a generic component, no catalog entry, drawn by `resolve_generic` --
    whose whole existence is a `markers` type plus a lexicon plus a label.
    Eight of them were live and invisible in the tab (`relay`, `thermistor`,
    `microphone`, `ky018`, `encoder`, `lora_sx1276`, `ds3231`, `ds1307`): the
    app wires a relay and names it in the instructions, and "Composants"
    answered nothing for "relais".

    `_TYPE_LABEL` is the enumerable source for this: it is exactly the set of
    types the wiring names to a human, which is the definition of a component
    somebody may look up. The reverse of guard 6, and the pair closes the loop:
    a wiring type without an identity, or an identity without a name, both turn
    the suite red.
    """
    from ui.wiring.instructions import _TYPE_LABEL
    missing = sorted(set(_TYPE_LABEL)
                     - {c.id for c in reg.registry()}
                     - reg.NON_COMPONENT_CATALOG_TYPES
                     - reg.NON_COMPONENT_WIRING_TYPES)
    assert not missing, (
        "types nommes par le cablage sans identite au registre -- soit creer "
        f"l'entree, soit la declarer non-composant : {missing}")


def test_non_component_wiring_types_are_really_not_components():
    """Guard on that escape hatch, same discipline as SOFTWARE_ONLY_DOCUMENTS:
    an exempted type must be named by the wiring (otherwise the exemption is
    stale) and must NOT have a registry entry (otherwise it is a component and
    the exemption hides nothing)."""
    from ui.wiring.instructions import _TYPE_LABEL
    ids = {c.id for c in reg.registry()}
    for t in reg.NON_COMPONENT_WIRING_TYPES:
        assert t in _TYPE_LABEL, t
        assert t not in ids, t


def test_one_component_one_identity_no_double_spelling():
    """The corollary the review caught: this chantier gave `rotary_encoder`,
    `lora` and `rtc` labels for components the wiring already named `encoder`,
    `lora_sx1276` and `ds3231`/`ds1307` -- "encodeur rotatif" existed twice,
    under two ids. Harmless today, a trap tomorrow: the day #41 draws
    `rotary_encoder`, guard 3 would demand a catalog entry under THAT id while
    `markers` kept emitting `encoder`, and nothing would go red.

    Wiring identifiers win, being written into saved projects."""
    ids = {c.id for c in reg.registry()}
    for dead, alive in (("rotary_encoder", "encoder"),
                        ("lora", "lora_sx1276"),
                        ("rtc", "ds3231")):
        assert dead not in ids, f"{dead} fait doublon avec {alive}"
        assert alive in ids, alive


def test_hardware_module_chips_resolve():
    """The other half of the promise guard 5 only kept in part.

    The spec (§5) says `ClarifyCandidate.svg_type` AND `HardwareModule.chips`
    keep their free strings, the registry merely CHECKING that they resolve.
    Only `svg_type` was covered -- yet `chips` is one of the four join
    mechanisms this chantier exists to replace, and its own docstring calls its
    entries "ids corpus ET types wiring des puces", i.e. component identities.

    The HW-612's two chips resolve today; nothing guaranteed they would
    tomorrow. Adding a module with `chips=("bmp180",)` would have passed the
    whole suite green.
    """
    from ui.hardware_modules import MODULES
    ids = {c.id for c in reg.registry()}
    unresolved = sorted({chip for m in MODULES for chip in m.chips
                         if chip not in ids})
    assert not unresolved, unresolved


def test_every_module_chip_actually_forces_a_library():
    """The half of the chips guard that checking the REGISTRY cannot cover.

    `test_hardware_module_chips_resolve` above checks `chips` against registry
    ids -- but `rag.module_forced_libs` looks them up in the CORPUS, and it is
    deliberately tolerant: « Une puce absente du corpus est ignoree ». So a chip
    that exists as a component but has no corpus document passes that guard,
    and the module silently forces ONE library instead of two. Nothing says so:
    not the suite, not the user, not the log.

    This asserts the behaviour instead of a proxy -- it calls the real function
    with a prompt naming the module, and counts. A module that forces fewer
    libraries than it has chips is a half-applied module.

    Measured 2026-08-18: hw-612 has both `mpu9250` and `bmp280` on both sides,
    so nothing bites today. The guard exists for the modules ADDED NEXT, which
    is exactly when a typo or a corpus-less chip would slip through unseen.
    """
    from ui.hardware_modules import MODULES
    from ui.rag import module_forced_libs
    corpus = _corpus_ids()

    # DEUX situations a ne PAS confondre, et c'est tout l'interet de la garde :
    #
    #   (a) la puce ne resout NULLE PART -- inconnue du registre et absente du
    #       corpus. C'est une faute de frappe ou un id invente : ERREUR.
    #   (b) la puce est un composant connu SANS document (`documents=()`), comme
    #       une LED ou un relais. Elle ne force aucune bibliotheque, et c'est la
    #       VERITE, pas un defaut -- `l3g4200d`, `itg3200` et `bmp085` sont dans
    #       ce cas au 2026-08-18.
    #
    # Une garde qui rejetterait (b) interdirait de declarer un GY-80 dont deux
    # puces sur quatre n'ont pas encore de lib au corpus, alors que forcer les
    # deux autres + nommer la carte au modele vaut mieux que rien.
    inconnues = []
    for m in MODULES:
        for chip in m.chips:
            comp = reg.by_id(chip)
            if comp is None and chip not in corpus:
                inconnues.append(f"{m.id}/{chip}")
            elif comp is not None:
                pendants = [d for d in comp.documents if d not in corpus]
                if pendants:
                    inconnues.append(f"{m.id}/{chip} -> document(s) fantome(s) "
                                     f"{pendants}")
    assert not inconnues, (
        "ces puces de module ne resolvent nulle part (faute de frappe, ou "
        f"document inexistant) : {sorted(inconnues)}")

    # Et la fonction REELLE doit livrer une bibliotheque pour chaque puce qui en
    # a une -- c'est le cas (mpu6050 -> adafruit-mpu6050) que l'egalite de
    # chaine ratait en silence.
    for m in MODULES:
        attendues = sum(
            1 for chip in m.chips
            if (reg.by_id(chip) is not None and reg.by_id(chip).documents)
            or (reg.by_id(chip) is None and chip in corpus)
        )
        # Le premier mot-cle est la reference de la carte : c'est ainsi que
        # l'utilisateur la nomme.
        forcees = module_forced_libs(f"j'utilise un {m.keywords[0]}")
        assert len(forcees) >= attendues, (
            f"{m.id} : {attendues} puce(s) documentee(s) mais seulement "
            f"{len(forcees)} bibliotheque(s) forcee(s) — module a moitie "
            f"applique")


def test_a_library_serving_two_components_is_referenced_twice():
    """The N<->N, concretely: one library, two components, zero duplication.
    This is the case the alias table had to write out twice."""
    both = {c.id for c in reg.components_for_document("dht-sensor-library")}
    assert {"dht11", "dht22"} <= both, sorted(both)


def test_a_document_can_attach_to_an_existing_component():
    """`onebutton` and `stepper` describe libraries for components that ALREADY
    exist in the catalog. None of the four previous join mechanisms could
    express that -- they all assumed one document, one component."""
    assert "onebutton" in (reg.by_id("button") or reg.Component(
        id="", function="input", mounting="breadboard", wiring="none")).documents
    assert "stepper" in (reg.by_id("stepper_motor") or reg.Component(
        id="", function="motor", mounting="off_board", wiring="none")).documents


def test_eeprom_is_a_component_with_nothing_to_wire():
    """The case that sharpened the three-state design: real memory, a real
    library (<EEPROM.h>), integrated on the board."""
    e = reg.by_id("eeprom")
    assert e is not None
    assert e.wiring == "none" and e.mounting == "on_mcu"
    assert "eeprom" in e.documents


def test_drift_no_corpus_document_is_orphaned():
    """THE forward-looking guard, and the real deliverable of this chantier.

    A corpus document that describes a component, referenced by no registry
    entry, turns the suite RED. That is what catches "someone added a BMP390 to
    the corpus and forgot the component" -- the exact drift that produced two
    half-true entries for one component on 2026-07-30, which the previous test
    could not see because it asserted the uniqueness of a set built BY
    deduplication (tautological by construction).

    Software-only documents are declared once, so the guard stays actionable
    instead of noisy.
    """
    referenced = {d for c in reg.registry() for d in c.documents}
    orphans = sorted(_corpus_ids() - referenced - reg.SOFTWARE_ONLY_DOCUMENTS)
    assert not orphans, (
        "documents sans composant -- soit creer l'entree, soit la declarer "
        f"logiciel pur dans SOFTWARE_ONLY_DOCUMENTS : {orphans}")


def test_software_only_documents_are_really_software():
    """Guard on the escape hatch itself: a declared software-only document must
    exist in the corpus, and must NOT be referenced by any component -- the
    list is an exemption, not a second way to attach a document."""
    known = _corpus_ids()
    referenced = {d for c in reg.registry() for d in c.documents}
    for doc in reg.SOFTWARE_ONLY_DOCUMENTS:
        assert doc in known, doc
        assert doc not in referenced, doc


def test_the_unknown_pinout_debt_is_real_and_bounded():
    """Real components we cannot draw yet. The count is asserted loosely on
    purpose: this test guards that the debt EXISTS and is declared, not its
    exact size -- it shrinks as pinouts get filled in (TODO).

    Upper bound raised 30 -> 60 on 2026-08-12 (tache 2, #44): the 19 bare-pin
    replacement candidates of Lot A entered the registry as `unknown` by
    design (none has a catalog footprint), which is the point of the chantier,
    not a drift.

    Raised again 60 -> 90 on 2026-08-12 (tache 3, #44), same cause and last
    time for this chantier: the 34 bus candidates (I2C/SPI/UART/ultrasonic)
    close Lot A, and none of them has a catalog footprint either. Actual
    count: 74 as of 2026-08-12. The headroom is deliberately narrower than
    last time (16, ~20 %) because this debt is now expected to SHRINK, not
    grow: Lot B adds no component, and TODO #41 removes entries from here by
    filling pinouts in. A third bump would mean somebody is adding undrawable
    components in bulk again -- worth a look rather than a reflex.

    2026-08-19 : la dette RETRECIT, comme ce docstring l'annoncait. Deux lots
    Fritzing le meme jour : un premier de 5 (`ds18b20`, `hmc5883`, `bmp085`,
    `ds3231`, `mpu6050`), puis un second de 40 releve sur le CLONE COMPLET du
    depot (2569 fiches — l'API GitHub tronquait ses reponses et avait fait
    sous-estimer la couverture reelle a 10/72 au lieu de 46/72, cf. TODO #57).
    77 -> 32. `ds18b20` puis `bme280` etaient cites en dur ici comme exemples
    de la dette ; ils n'en font plus partie, et c'est le resultat voulu, pas
    une regression. `ccs811` reste hors des deux lots, et tient le role.
    """
    unknown = [c.id for c in reg.registry() if c.wiring == "unknown"]
    assert 10 <= len(unknown) <= 90, sorted(unknown)
    assert "ccs811" in unknown


def test_guard_6_every_component_has_a_translated_label():
    """`ui/component_index.py` names every registry-derived card via
    `ui.wiring.instructions._label(comp.id, lang)` -- the design spec's own
    call ("the registry refers to `_label`, it does not duplicate the
    translated name"). `_label`'s fallback when `_TYPE_LABEL` has NO ENTRY at
    all for an id is the RAW id itself, so a component missing from that
    table would print its slug verbatim on a card ("sd_card", "ina3221")
    instead of a name a beginner recognizes -- worse than before this
    chantier for the very `wiring="unknown"` population it introduced to be
    MORE honest, not less readable.

    Checked as table membership, NOT as `_label(...) != comp.id` string
    comparison: two entries genuinely translate to the same spelling as their
    id in at least one language ("buzzer" is "buzzer" in fr AND en;
    "potentiometer" is "potentiometer" in en) -- real, deliberate labels, not
    a fallback. A string-equality guard flags both permanently, which is not
    the bug this guard exists to catch (measured while writing this test:
    those two are the ONLY false positives a naive comparison produces,
    verified against the 10 real gaps it is meant to catch).

    Relaxed for tache 2 (#44, 2026-08-12), as the tache-1 breadcrumb here
    planned: the replacement-candidate entries (Lot A and the ones tasks 3
    will add) are deliberately NOT in _TYPE_LABEL -- their curated label
    comes from `replacement_catalog.label_of`, which `component_index` falls
    back to (language-neutral by documented stance, so no 4-language
    requirement there). The check mirrors the consumer's own arbitration,
    which is by MEMBERSHIP: an id present in _TYPE_LABEL is rendered by
    `_label` and label_of is NEVER consulted, so it must carry all 4
    languages; only an id absent from the table falls back to `label_of`,
    which must then return a non-empty label. A flat OR would be weaker:
    eight pre-existing ids live in BOTH tables (adxl345, ds1307, ds3231,
    max6675, mlx90614, mpu9250, nrf24l01, pcf8574), and deleting one of
    their translations would stay green while the user got the French
    fallback. Stuffing the new ids into _TYPE_LABEL instead would silently
    re-kill the component_index fallback (the curated labels live in
    replacement_catalog)."""
    from ui.wiring.instructions import _TYPE_LABEL
    from ui.wiring.replacement_catalog import label_of
    missing = []
    for c in reg.registry():
        if c.id in _TYPE_LABEL:
            missing += [(c.id, lang) for lang in ("fr", "en", "es", "it")
                        if not (_TYPE_LABEL[c.id].get(lang) or "").strip()]
        elif not (label_of(c.id) or "").strip():
            missing.append((c.id, "label_of"))
    assert not missing, missing


def test_lib_name_and_lib_to_determine_are_exclusive():
    """Les deux champs encodent un axe a trois etats : les poser ensemble
    serait une contradiction. Garde sur TOUTES les entrees du registre."""
    from ui.component_registry import registry
    for comp in registry():
        assert not (comp.lib_name and comp.lib_to_determine), comp.id


def test_58_the_six_undrawable_components_are_now_drawn():
    """#58 : les six composants que #57 avait laisses non dessinables ont
    desormais une entree catalogue et ne sont plus `unknown`.

    Verifie les DEUX cotes, parce qu'ils peuvent diverger : le registre dit
    `known` (promesse faite a l'utilisateur dans l'onglet Composants) et le
    catalogue porte reellement le brochage (ce que le schema dessine).
    """
    from ui.wiring.layout.component_catalog import CATALOG
    six = ("sharp_memory_display", "gc9a01", "winc1500", "eink_display",
           "stspin220", "tmc2209")
    for cid in six:
        comp = reg.by_id(cid)
        assert comp is not None, cid
        assert comp.wiring == "known", (cid, comp.wiring)
        assert cid in CATALOG, cid


def test_58_the_stepsticks_keep_both_ground_pins():
    """Un StepStick a DEUX broches GND physiques. Les de-doubloner rendrait
    le compte impair et dessinerait une carte qui n'existe pas."""
    from ui.wiring.layout.component_catalog import CATALOG
    for cid, expected in (("stspin220", 14), ("tmc2209", 16)):
        entry = CATALOG[cid]
        assert entry.pin_count == expected, (cid, entry.pin_count)
        grounds = [lbl for lbl in entry.pin_labels.values() if lbl == "GND"]
        assert len(grounds) == 2, (cid, entry.pin_labels)


# Le lot #69 : id -> bibliotheque VERIFIEE dans l'index Arduino le
# 2026-08-27. `None` = aucune bibliotheque necessaire.
#
# ⚠️ Les MQ sont a `None`, et c'est une DECISION, pas un oubli. Un MQ est un
# capteur ANALOGIQUE : `analogRead` suffit, la bibliotheque ne fait que la
# conversion en ppm. Les deux MQ qui etaient deja au corpus (`mq2`, `mq135`)
# disent exactement la meme chose ; leur donner une lib aurait introduit une
# divergence avec eux, et fait croire a l'utilisateur qu'il doit installer
# quelque chose pour lire une tension.
_LOT_69 = {
    "mq131": None, "mq136": None, "mq137": None, "mq138": None,
    "mq214": None, "mq216": None, "mq303a": None, "mq306a": None,
    "mq307a": None, "mq309a": None,
    "mhz14a": "MH-Z CO2 Sensors",
    "mhz1311a": "MHZCO2",
    "rcwl0516": "RCWL0516",
    "rcwl1005": "RCWL_1X05",
    "rcwl1605": "RCWL_1X05",
    "jsn_sr04t": "jsnsr04t",
}


def test_69_le_lot_d_identites_porte_ses_bibliotheques_verifiees():
    """Les 16 composants reveles par le balayage des serigraphies (#69).

    La bibliotheque vit dans le DOCUMENT du corpus, pas dans `lib_name` :
    c'est ce que dit la docstring de `Component` (<< library facts for
    components with NO corpus document >>), et c'est ce qui supprime la
    divergence mesuree le 2026-08-27 -- le registre affichait une
    bibliotheque, et la recherche en direct de l'index Arduino en utilisait
    une autre pour 2 pieces sur 4.
    """
    import json
    from pathlib import Path
    corpus = {e["id"]: e for e in json.loads(
        (Path(__file__).resolve().parents[1] / "assets" / "rag"
         / "corpus.json").read_text(encoding="utf-8"))}
    par_id = {c.id: c for c in reg.registry()}
    for cid, lib in _LOT_69.items():
        assert cid in par_id, f"{cid} a disparu du registre"
        comp = par_id[cid]
        assert comp.documents == (cid,), (cid, comp.documents)
        assert not comp.lib_name, (
            f"{cid} porte lib_name ET un document : deux sources pour un "
            f"meme fait, exactement ce que ce lot supprime")
        assert cid in corpus, f"{cid} absent du corpus"
        assert corpus[cid].get("arduino_lib_name") == lib, (
            cid, corpus[cid].get("arduino_lib_name"), lib)


def test_69_hc12_reste_hors_du_registre():
    """Le module radio HC-12 n'a AUCUNE entree, et c'est mesure.

    `lookup_component('hc12')` rend « libasm » -- « Cross assembler and
    disassembler for retro CPUs » -- parce que le HC12 de Motorola est un
    microcontrolleur ancien. Un faux positif parfait : statut `found`, une
    bibliotheque bien reelle, et aucun rapport avec le module radio.

    Balayage de l'index entier le 2026-08-27 : une seule fiche nomme
    « HC-12 », et c'est un pilote multi-usage (NiusWireless, qui vise aussi
    RFID-RC522, LoRa, NRF24L01 et HC-05/06). Pas de bibliotheque dediee, donc
    pas d'identite -- meme regle que les neuf references ecartees du #57.

    ⛔ Ne pas << completer >> sans source neuve. Ce test rougit si quelqu'un
    ajoute l'entree, et c'est le but : le prochain a la voir manquer doit
    tomber sur cette explication, pas sur un oubli apparent.
    """
    ids = {c.id for c in reg.registry()}
    for absent in ("hc12", "hc-12", "ajsr04m", "aj_sr04m"):
        assert absent not in ids, (
            f"{absent} est entre au registre sans source verifiee")


def test_69_les_variantes_mhz19_sont_des_MOTS_CLES_pas_des_composants():
    """Premiere des deux questions que le ticket demandait de trancher.

    Le registre n'a pas de notion de variante, et en fabriquer une pour
    quatre entrees serait pire que quatre entrees. Le precedent existait
    d'ailleurs deja dans le code : `mhz19` portait B et C en mots-cles bien
    avant ce lot. D et E les rejoignent.

    MH-Z14A et MH-Z1311A, eux, sont bien des composants : des pieces
    distinctes, avec leur propre bibliotheque.
    """
    ids = {c.id for c in reg.registry()}
    mhz19 = next(c for c in reg.registry() if c.id == "mhz19")
    mots = {k.upper() for k in mhz19.keywords}
    for v in ("MH-Z19B", "MH-Z19C", "MH-Z19D", "MH-Z19E"):
        assert v in mots, f"{v} absent des mots-cles de mhz19"
        assert v.lower().replace("-", "") not in ids, \
            f"{v} est AUSSI un composant : la variante a ete dedoublee"
    assert "mhz14a" in ids and "mhz1311a" in ids


TESTS = [
    test_vocabularies_are_closed_and_disjoint_enough,
    test_component_fields_and_defaults,
    test_every_entry_uses_the_closed_vocabularies,
    test_ids_are_unique,
    test_by_id_and_components_for_document,
    test_non_component_catalog_types_are_declared,
    test_guard_1_every_catalog_type_has_an_entry,
    test_guard_2_every_referenced_document_exists,
    test_guard_3_wiring_state_matches_the_catalog,
    test_off_board_mounting_matches_the_layout_engine,
    test_guard_5_clarify_group_svg_types_resolve,
    test_hardware_module_chips_resolve,
    test_every_module_chip_actually_forces_a_library,
    test_every_named_wiring_type_has_an_entry,
    test_non_component_wiring_types_are_really_not_components,
    test_one_component_one_identity_no_double_spelling,
    test_a_library_serving_two_components_is_referenced_twice,
    test_a_document_can_attach_to_an_existing_component,
    test_eeprom_is_a_component_with_nothing_to_wire,
    test_drift_no_corpus_document_is_orphaned,
    test_software_only_documents_are_really_software,
    test_the_unknown_pinout_debt_is_real_and_bounded,
    test_guard_6_every_component_has_a_translated_label,
    test_lib_name_and_lib_to_determine_are_exclusive,
    test_58_the_six_undrawable_components_are_now_drawn,
    test_58_the_stepsticks_keep_both_ground_pins,
    # TODO #69 (2026-08-27) : le lot d'identites du balayage.
    test_69_le_lot_d_identites_porte_ses_bibliotheques_verifiees,
    test_69_hc12_reste_hors_du_registre,
    test_69_les_variantes_mhz19_sont_des_MOTS_CLES_pas_des_composants,
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

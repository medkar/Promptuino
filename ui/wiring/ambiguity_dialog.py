"""Confirmation modal for ambiguous components from the static detector.

When parsing the Arduino code yields low-confidence components
(typically an OUTPUT pin classified as LED by default without a clear
hint in the prompt or the context), this modal lists them and lets
the user pick the right type.

UX: one box per ambiguous pin, which recalls the prompt excerpt that
mentioned this pin (so a beginner understands what we're talking
about), followed by radio-buttons for the classic candidates (red
LED, buzzer, generic module). Confirming applies the choices to the
netlist (in-place mutation).
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QRadioButton,
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from ..i18n import lang_manager, localize_button_box
from ..theme import (
    theme_manager, primary_button_qss, secondary_button_qss,
    radio_checkbox_qss, bare_button_qss,
)
from .categories import category_of, NON_REPLACEABLE
from .component_replace import replace_component
from .instructions import _label as _type_label
from .markers import (STEPPER_DRIVERS, apply_stepper_driver_swap,
                      find_pin_excerpt)
from .netlist import Component, Netlist, Pin
from ..declared_components import TYPE_PREFIX


def _install_combo_search(combo: "QComboBox") -> None:
    """Rend un QComboBox recherchable au clavier sans autoriser la saisie
    libre : editable + completer MatchContains insensible a la casse, mais
    InsertPolicy.NoInsert (la selection reste contrainte aux items)."""
    from PyQt6.QtWidgets import QCompleter
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    completer = combo.completer()
    if completer is None:
        completer = QCompleter(combo.model(), combo)
        combo.setCompleter(completer)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    completer.setFilterMode(Qt.MatchFlag.MatchContains)
    completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
    # A la fin de l'edition (Entree / perte de focus) : on COMMET la recherche
    # quand elle designe un item sans ambiguite, puis on realigne le texte sur
    # l'item courant.
    #
    # Le realignement seul (ce que faisait la version d'origine) rendait le
    # champ DECORATIF : `NoInsert` laisse le texte libre s'afficher sans que
    # `currentIndex` bouge, donc taper « ssd » puis Entree revenait a « LED »
    # et valider la modale n'appliquait RIEN -- un echec silencieux. Une
    # recherche qui correspondait et une recherche qui ne correspondait a rien
    # se comportaient identiquement (QA C2, 2026-08-08).
    edit = combo.lineEdit()
    if edit is not None:
        edit.editingFinished.connect(
            lambda c=combo: _commit_combo_search(c))
        # ... et Entree s'ARRETE ici (cf. _EnterCommitsSearch).
        filt = _EnterCommitsSearch(combo)
        edit.installEventFilter(filt)


class _EnterCommitsSearch(QObject):
    """Enter in the search field commits the search and goes NO FURTHER.

    Neutralising the button box at construction time is not enough: measured
    on the real layout, Qt puts `isDefault` back on OK when the dialog is
    shown, so the key travelled up to the QDialog, clicked that button and
    VALIDATED the modal -- the user typed a search and the window closed on
    him (QA C2, 2026-08-08). Swallowing the key where it is typed is the local
    fix; fighting the default-button machinery would have to be re-won at
    every show().

    The guarantee lives HERE and not in the host dialog: a search combo must
    be safe to drop into any window, without that window having to know it
    must neutralise Return.

    When the completer offers exactly ONE completion, Enter takes it -- the
    field may still hold the partial text the user typed ("ssd"), measured:
    navigating the popup does not write the highlighted item into the field.
    With several completions we fall back to the normal rule, which refuses
    to guess rather than silently picking the first (`match_index`).
    """

    def __init__(self, combo: "QComboBox"):
        super().__init__(combo)
        self._combo = combo

    def eventFilter(self, obj, ev):
        if ev.type() != QEvent.Type.KeyPress:
            return False
        if ev.key() not in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return False
        combo = self._combo
        completer = combo.completer()
        if completer is not None:
            popup = completer.popup()
            if popup is not None and popup.isVisible():
                popup.hide()
            if completer.completionCount() == 1:
                idx = match_index([combo.itemText(i)
                                   for i in range(combo.count())],
                                  completer.currentCompletion())
                if idx is not None:
                    combo.setCurrentIndex(idx)
        _commit_combo_search(combo)
        return True                       # consumed: never reaches the dialog


# NOTE (2026-08-13) : le crayon logé DANS la liste déroulante a disparu avec
# elle — chaque card porte désormais le sien (`ambiguity_cards.ComponentCard`).
# `_place_pencil_in_combo` et ses trois constantes de placement ont été
# supprimées : elles ne décrivaient plus aucun widget de l'application.
# `_install_combo_search` / `match_index` restent, eux : ce sont des helpers
# génériques de combo de recherche, testés seuls (`test_combo_search.py`).


def match_index(items: list[str], text: str) -> int | None:
    """Index designated by `text` among `items`, or None if it designates
    nothing unambiguously. Pure -- the matching rule is tested without Qt.

    An EXACT match wins first, so typing the full text of an item selects it
    even when that text is a prefix of others ("LED" against "LED RGB").
    Otherwise a `contains` match counts only when it is UNIQUE: "oled" facing
    two OLED screens must not silently pick the first, which would present a
    guess as a choice. Case-insensitive, like the completer.
    """
    needle = (text or "").strip().casefold()
    if not needle:
        return None
    exact = [i for i, it in enumerate(items) if it.casefold() == needle]
    if len(exact) == 1:
        return exact[0]
    partial = [i for i, it in enumerate(items) if needle in it.casefold()]
    return partial[0] if len(partial) == 1 else None


def _commit_combo_search(combo: "QComboBox") -> None:
    """Apply the typed search to the real selection, then realign the text."""
    items = [combo.itemText(i) for i in range(combo.count())]
    idx = match_index(items, combo.lineEdit().text())
    if idx is not None:
        combo.setCurrentIndex(idx)
    combo.setEditText(combo.itemText(combo.currentIndex()))


# Candidates by initial detected type. (label_user, type_id, transform_fn)
# transform_fn(component, netlist) mutates the component in place to
# reclassify it. The netlist is passed to let transforms clean up
# orphan components (typically the series R of the initial LED added
# by the inference rules before the modal, which becomes dangling
# when reclassified to buzzer / motor / module).
# Each transform RECREATES the pin list in the format expected by the
# target type (LED A/K, buzzer +/-, module SIG, motor M+/M-, etc.).

def _signal_net(c: Component) -> str | None:
    """Extract the net of the component's signal pin, whatever its
    name (A for LED, SIG for module_generic, + for buzzer, etc.)."""
    for name in ("A", "SIG", "+", "DATA"):
        p = c.pin(name)
        if p is not None:
            return p.net
    return c.pins[0].net if c.pins else None


def _arduino_signal_pin(c: Component, netlist=None) -> str | None:
    """Find the original Arduino pin that drives this component, even
    if apply_rules bridged it via an internal net (e.g. LED + series R:
    LED.A = NET_X, R.A = D6, R.B = NET_X -> we return D6).

    Without netlist, just returns signal_net(c) (no walk-up possible)."""
    from .inference import _is_signal_net

    def _walkable(p) -> bool:
        return p is not None and (_is_signal_net(p.net)
                                  or p.net.startswith("NET_"))

    # La broche de signal ne peut JAMAIS être un rail. Deux pièges payés en
    # QA AC (2026-08-31), même pathologie par deux portes : `pins[0]` d'un
    # écran I2C est VCC (clé de swap `('', '5V')` → un DHT11 héritait du
    # « led » de l'écran remplacé), et la broche « A » d'un POTENTIOMÈTRE
    # est sa patte 5V (titre de modale « Broche 5V », même clé dégénérée) —
    # « A » veut dire anode pour une LED, mais juste « première patte » pour
    # un pot. On garde donc A/SIG seulement si leur net est un signal (ou un
    # pont NET_ remontable) ; sinon première broche signal ; repli inchangé
    # sur `pins[0]` quand rien n'est un signal (placeholder à nets vides :
    # sa clé dégénérée `('', '')` est un comportement documenté).
    sig = c.pin("A") or c.pin("SIG")
    if not _walkable(sig):
        sig = next((p for p in c.pins if _walkable(p)),
                   sig or (c.pins[0] if c.pins else None))
    if sig is None:
        return None
    if not sig.net.startswith("NET_") or netlist is None:
        return sig.net
    # Bridged via NET_X: look for an inferred component with a pin on
    # NET_X and return the other pin (= the Arduino pin).
    for rc in netlist.components:
        if rc.ref == c.ref or not rc.inferred:
            continue
        if any(p.net == sig.net for p in rc.pins):
            for p in rc.pins:
                if p.net != sig.net and not p.net.startswith("NET_"):
                    return p.net
    return sig.net   # fallback


def _drop_orphan_companions(c: Component, netlist=None) -> None:
    """Remove companion components added by the inference rules
    (typically the series R of a LED) that become orphans when
    reclassifying `c` to a different type. We detect series R whose
    pin B is on the bridge_net currently assigned to pin A of c."""
    if netlist is None:
        return
    a_pin = c.pin("A")
    if a_pin is None:
        return
    bridge_net = a_pin.net
    if not bridge_net.startswith("NET_"):
        return   # no internal bridge, no inference to clean up
    to_drop = [
        rc for rc in netlist.components
        if rc.type == "resistor" and rc.inferred
        and rc.attributes.get("role") == "series"
        and any(p.net == bridge_net for p in rc.pins)
    ]
    dropped_refs = {rc.ref for rc in to_drop}
    for rc in to_drop:
        netlist.components.remove(rc)
    if dropped_refs:
        netlist.warnings = [
            w for w in netlist.warnings
            if not (w.code == "led_series_resistor"
                    and w.params.get("resistor_ref") in dropped_refs)
        ]


def _to_led(c: Component, netlist=None) -> None:
    """Reclassify an ambiguous output as a plain LED — with NO colour.

    We do not know the colour and nothing in the code can tell us: only the
    prompt can (`markers` annotates `color` when the user actually writes
    "LED rouge"). Assuming red used to leak everywhere — the wiring
    instructions said "LED rouge", and any unexpected value reaching this
    fallback silently became a red LED. `LED_COLOR_TO_R` already defaults to
    220 Ω for an unknown colour, which is exactly what red mapped to, so
    dropping the assumption changes no series resistor.
    """
    # Keep the series R: it's legitimate for a LED (the rule regenerates
    # it anyway on the next apply_rules if we dropped it).
    net = _signal_net(c)
    if net is None:
        return
    c.type = "led"
    c.pins = [Pin("A", net), Pin("K", "GND")]
    c.attributes = {}


def _to_buzzer(c: Component, netlist=None) -> None:
    # We read the Arduino pin BEFORE dropping the R (which holds the info)
    arduino_pin = _arduino_signal_pin(c, netlist)
    _drop_orphan_companions(c, netlist)
    if arduino_pin is None:
        return
    c.type = "buzzer"
    c.pins = [Pin("+", arduino_pin), Pin("-", "GND")]
    c.attributes = {}


def _to_servo(c: Component, netlist=None) -> None:
    # Servo directly on Arduino: signal on SIG, power 5V + GND. No series
    # R (the servo is driven in PWM 50 Hz, power comes from the 5V rail).
    arduino_pin = _arduino_signal_pin(c, netlist)
    _drop_orphan_companions(c, netlist)
    if arduino_pin is None:
        return
    c.type = "servo"
    c.pins = [Pin("VCC", "5V"), Pin("GND", "GND"), Pin("SIG", arduino_pin)]
    c.attributes = {}


def _to_module_generic(c: Component, netlist=None) -> None:
    arduino_pin = _arduino_signal_pin(c, netlist)
    _drop_orphan_companions(c, netlist)
    if arduino_pin is None:
        return
    c.type = "module_generic"
    c.pins = [Pin("SIG", arduino_pin)]
    c.attributes = {"label": "?"}


def _to_dc_motor(c: Component, netlist=None, driver_type: str | None = None) -> None:
    """Reclassify LED -> DC motor. The motor is NEVER wired directly
    on Arduino (needs an H-bridge). We store the Arduino pin in
    attributes['_control_pin'] so the inference rule can add the
    driver + battery_external + wire it all up.

    `driver_type` (optional): H-bridge driver type chosen by the user
    (cf _DC_DRIVERS). Stored in attributes['_chosen_driver'] and read
    with priority by the inference rule (above the global suggested).

    If the component carries the grouping flags (`_grouped_pwm_pin` +
    `_grouped_dir_pins`, added by markers._group_dc_motor_pins), we
    use the PWM pin as _control_pin and propagate the direction pins
    via `_aux_dir_pins` so inference.py wires them on IN1/IN2 of the
    driver instead of fixed IN2=GND."""
    grouped_pwm = c.attributes.get("_grouped_pwm_pin")
    grouped_dirs = c.attributes.get("_grouped_dir_pins")
    if grouped_pwm:
        # Grouped mode: _control_pin = PWM pin. The grouped LED still
        # received a series R from apply_rules (= LED.A bridged via NET_X) --
        # it must be removed before conversion to avoid an orphan R
        # between the PWM pin and a NET_X that will no longer be referenced.
        _drop_orphan_companions(c, netlist)
        arduino_pin = grouped_pwm
    else:
        arduino_pin = _arduino_signal_pin(c, netlist)
        _drop_orphan_companions(c, netlist)
        if arduino_pin is None:
            return
    c.type = "dc_motor"
    c.pins = [Pin("M+", "GND"), Pin("M-", "GND")]
    attrs: dict = {"_control_pin": arduino_pin}
    if driver_type:
        attrs["_chosen_driver"] = driver_type
    if grouped_dirs:
        attrs["_aux_dir_pins"] = list(grouped_dirs)
    c.attributes = attrs


# H-bridge drivers offered to drive a dc_motor. (label_user, type_id)
# All 5 are from the catalog (cf ui/wiring/layout/component_catalog.py). L293D has 2
# variants (bare DIP and breakout module) that only the user can decide --
# which is why we offer them in this modal, but NOT in auto
# detection from the prompt (cf markers._MOTOR_DRIVER_KEYWORDS).
_DC_DRIVERS: list[str] = ["l298n", "l293d_module", "l293d", "tb6612fng", "drv8833"]

# Plain part numbers need no translation. The 2 breakout/DIP qualifiers DO
# (French "module breakout" / "DIP nu") -- resolved at build time via
# DIALOG_LABELS so a language switch before opening the modal is honored
# (a module-level dict frozen at import time would not have been).
_DC_DRIVER_PLAIN_LABEL = {
    "l298n": "L298N", "tb6612fng": "TB6612FNG", "drv8833": "DRV8833",
}


def _driver_label(d_type: str, lang: str) -> str:
    if d_type in _DC_DRIVER_PLAIN_LABEL:
        return _DC_DRIVER_PLAIN_LABEL[d_type]
    from .visual_ambiguity_catalog import dialog_label
    key = "driver_label_l293d_module" if d_type == "l293d_module" \
        else "driver_label_l293d_dip"
    return dialog_label(key, lang)


# Candidates offered to reclassify an ambiguous component. Covers the
# frequent cases (LED by default, DC motor for OUTPUT pin driving a
# motor, buzzer for piezo, module_generic for pins that match no
# recognized pattern).
_CANDIDATES: list[tuple[str, str, callable]] = [
    ("LED",                "led",            _to_led),
    ("Buzzer",             "buzzer",         _to_buzzer),
    ("Servo",              "servo",          _to_servo),
    ("Moteur DC",          "dc_motor",       _to_dc_motor),
    ("Module générique",   "module_generic", _to_module_generic),
]
# Map type_id -> transform for the default of _chosen (the user keeps
# the initial type if they don't touch the modal).
_DEFAULT_TRANSFORMS: dict[str, callable] = {
    type_id: tr for _, type_id, tr in _CANDIDATES
}


def collect_ambiguous(netlist: Netlist) -> list[Component]:
    """Return the low-confidence components in the netlist."""
    return [
        c for c in netlist.components
        if c.attributes.get("_confidence") == "low"
    ]


def is_silently_resolved_servo(component: Component) -> bool:
    """True if the prompt names this output as a servo, so the resolver
    peels it off instead of sending it to the modal.

    Point de verite UNIQUE de cette regle : `studio_view.
    _resolve_wiring_netlist` applique le peel-off, et rien d'autre ne doit le
    reecrire a la main -- deux copies finiraient par diverger, et la
    divergence ferait ouvrir la modale sur un servo qui n'y arrive jamais.

    ⚠️ Cette fonction avait un second appelant, `collect_re_editable`, qui
    decidait l'etat du bouton du schema. Il a disparu le 2026-08-29 : le
    bouton s'appelle desormais « Modifier les composants » et ouvre TOUT le
    schema (`collect_all_editable`), donc son etat ne depend plus de
    l'ambiguite. Le peel-off, lui, n'a pas bouge."""
    return component.attributes.get("_prompt_suggested_type") == "servo"


def collect_all_editable(netlist: Netlist,
                         editable_refs: set[str] | None = None) -> list[Component]:
    """TOUS les composants du schéma que l'utilisateur peut corriger.

    C'est ce qu'ouvre « Modifier les composants » (ex-« Modifier les choix »),
    par opposition à `collect_re_editable`, qui ne rendait que les composants
    **incertains**. Deux raisons de changer, demandées le 2026-08-29 :

    - on ne pouvait pas revenir sur un composant que le détecteur avait
      reconnu **avec certitude** ; seul son engrenage y donnait accès, et
      encore fallait-il le trouver dans le schéma ;
    - avec deux fonctionnalités ambiguës générées à la suite, la première
      cessait d'être joignable par ce bouton.

    ⚠️ **Le critère est celui de l'ENGRENAGE, pas une deuxième règle.**
    `gear_menu_editable` décide déjà quels composants portent un engrenage
    dans le schéma ; s'en écarter ferait deux populations « modifiables » qui
    finiraient par diverger. Elle est importée ici plutôt que recopiée, et
    l'import est local : ce module est chargé par des tests sans Qt utile, et
    `wiring_diagram_dialog` traîne toute la scène graphique.

    Les composants d'INFRASTRUCTURE restent dehors — résistance de
    limitation, pile, driver déduit d'un moteur : l'utilisateur ne les a pas
    choisis (`is_replaceable`, règle du TODO #62).
    """
    from .wiring_diagram_dialog import gear_menu_editable
    refs = editable_refs or set()
    return [c for c in netlist.components
            if gear_menu_editable(c, c.ref in refs)]


def include_scoped_target(ambiguous: list, netlist, scoped_to_ref):
    """Ensure the target component of a scoped edit (gear 'Edit this
    component') is in the list to moderate, EVEN if it was detected
    with certainty (medium/high/signature) and is therefore not in
    collect_ambiguous (which only returns the low-confidence ones). Mutates
    and returns the list. No-op if scoped_to_ref is None or already present."""
    if scoped_to_ref is None:
        return ambiguous
    if any(c.ref == scoped_to_ref for c in ambiguous):
        return ambiguous
    target = next((c for c in netlist.components if c.ref == scoped_to_ref), None)
    if target is not None:
        ambiguous.append(target)
    return ambiguous


def ungroup_motor_in_netlist(component: Component, netlist,
                              dir_confidence: str = "high") -> None:
    """Mutate the netlist: remove the `_grouped_*` flags from `component`
    and recreate ambiguous LEDs for the direction pins. Idempotent
    (no-op if not grouped or if dirs already present).

    Use case: a grouped motor candidate (1 PWM-owner + N dirs
    encapsulated in flags) must be reclassified into N distinct LEDs
    when the user chooses "these are LEDs" (otherwise `_to_led`
    only mutates the PWM-owner, losing the dirs).

    Module-level version of `AmbiguityDialog._ungroup_motor_no_rebuild`
    for reuse from `apply_saved_resolution`."""
    if "_grouped_pwm_pin" not in component.attributes:
        return
    dir_pins = component.attributes.pop("_grouped_dir_pins", None) or []
    component.attributes.pop("_grouped_pwm_pin", None)
    if netlist is None:
        return
    for dir_pin in dir_pins:
        existing = next(
            (cc for cc in netlist.components
             if cc.pin("A") is not None and cc.pin("A").net == dir_pin),
            None,
        )
        if existing is not None:
            continue
        ref_new = netlist.next_ref("D")
        led = Component(
            ref=ref_new, type="led", fn_id=component.fn_id,
            pins=[Pin("A", dir_pin), Pin("K", "GND")],
            attributes={"_confidence": dir_confidence},
            inferred=True,
        )
        netlist.add_component(led)


def regroup_motor_in_netlist(pwm_pin: str, dir_pins: list[str],
                              netlist, orig_ref: str | None = None) -> None:
    """Module-level inverse of `ungroup_motor_in_netlist`: restore the
    grouped motor candidate on `pwm_pin`. Find the PWM LED, put back
    the `_grouped_*` flags + confidence low, then delete the LEDs of the
    dir pins (created during the ungroup). Idempotent (no-op if already
    grouped or PWM not found).

    PWM LED lookup: by `orig_ref` if provided (STABLE, recommended),
    otherwise by `pin('A').net == pwm_pin`. The net fallback is only
    reliable BEFORE `inference.apply_rules`: after, inference inserts a
    bridge (NET_X) between pin A and the Arduino pin (LED series R case)
    and the comparison fails silently (cf the same pitfall documented on
    `AmbiguityDialog._regroup_motor_no_rebuild`). Passing `orig_ref`
    avoids this pitfall entirely."""
    if netlist is None:
        return
    pwm_led = None
    if orig_ref is not None:
        pwm_led = next(
            (c for c in netlist.components if c.ref == orig_ref), None,
        )
    if pwm_led is None:
        pwm_led = next(
            (c for c in netlist.components
             if c.pin("A") is not None and c.pin("A").net == pwm_pin),
            None,
        )
    if pwm_led is None:
        return
    if pwm_led.attributes.get("_grouped_pwm_pin") == pwm_pin:
        return
    pwm_led.type = "led"
    pwm_led.attributes["_grouped_pwm_pin"] = pwm_pin
    pwm_led.attributes["_grouped_dir_pins"] = list(dir_pins)
    pwm_led.attributes["_confidence"] = "low"
    for dir_pin in dir_pins:
        dir_led = next(
            (c for c in netlist.components
             if c.pin("A") is not None and c.pin("A").net == dir_pin),
            None,
        )
        if dir_led is None:
            continue
        try:
            netlist.components.remove(dir_led)
        except ValueError:
            pass


def _apply_declared(component: Component, type_id: str, netlist=None) -> None:
    """Apply a user declaration: exact pins and nets given by the user.

    Does NOT go through replace_component: this is not a same-category swap,
    it is a direct assignment. The safety-net attributes are dropped (they no
    longer describe anything) but `signature_detected` stays False — that flag
    means "read in the code", and a declaration is not."""
    from ..declared_components import find_by_type
    decl = find_by_type(type_id)
    if decl is None:
        return          # entry removed from the library: leave the box as-is
    from .netlist import SAFETY_NET_ATTRS, SAFETY_NET_WARNING_CODES
    ungroup_motor_in_netlist(component, netlist)
    # #70 (2026-08-27) : les compagnons que l'inference a poses pour l'ANCIEN
    # composant n'ont plus rien a accompagner. Une LED requalifiee en fiche
    # declaree laissait sa resistance serie derriere elle, pontant D7 vers un
    # NET_ interne que plus personne ne porte -- le schema dessinait une
    # resistance branchee sur du vide.
    #
    # ⚠️ AVANT la reassignation des broches, obligatoirement :
    # `_drop_orphan_companions` retrouve le pont en lisant `component.pin("A")`,
    # et la ligne suivante remplace justement toutes les broches par celles de
    # la fiche. Appele apres, il ne trouverait plus rien et ne ferait rien --
    # une correction qui a l'air d'etre la sans agir. C'est le meme ordre que
    # les quatre transformations historiques, qui lisent la broche Arduino
    # avant de laisser tomber la R.
    #
    # Les autres chemins etaient deja couverts : `_to_buzzer`, `_to_servo`,
    # `_to_module_generic` et `_to_dc_motor` appellent ce nettoyage, et le
    # chemin catalogue retire ses freres inferes dans `replace_component`.
    # Celui-ci ne faisait ni l'un ni l'autre -- `apply_saved_resolution` lui
    # rend la main et RETOURNE aussitot.
    _drop_orphan_companions(component, netlist)
    component.type = type_id
    component.pins = [Pin(name=p.label, net=p.net) for p in decl.pins]
    for attr in SAFETY_NET_ATTRS:
        component.attributes.pop(attr, None)
    # Et les AVERTISSEMENTS que ces filets ont poses. Les retirer des attributs
    # sans retirer les messages laissait le schema dire « composant presume »
    # sur un composant que l'utilisateur venait de decrire lui-meme -- il
    # contredisait la correction a l'instant ou elle etait faite (QA L4,
    # 2026-08-10). `presumed_analog` etait le cas visible : un potentiometre
    # devine n'est ni `unrecognized` ni `presumed_wiring`, donc le rejeu de la
    # bibliotheque (`declared_apply`), qui nettoyait deja ces warnings, ne le
    # regardait meme pas.
    if netlist is not None:
        netlist.warnings = [
            w for w in netlist.warnings
            if not (w.code in SAFETY_NET_WARNING_CODES
                    and component.ref in (w.refs or []))
        ]
    component.attributes["user_declared"] = True
    component.attributes["signature_detected"] = False
    component.inferred = False


def apply_saved_resolution(component: Component, type_id: str,
                            netlist=None,
                            driver_type: str | None = None) -> None:
    """Apply a resolution already chosen by the user (without going
    through the modal). Used by the wiring dialog to silently apply
    the choices persisted across successive openings.
    The optional netlist enables cleanup of orphan companions.
    `driver_type` is forwarded to _to_dc_motor only (the other
    transforms ignore it)."""
    from ..declared_components import TYPE_PREFIX as _CUSTOM_PREFIX
    if type_id.startswith(_CUSTOM_PREFIX):
        _apply_declared(component, type_id, netlist)
        component.attributes["_confidence"] = "high"
        return
    # Catalog type without a dedicated transform (large scraped catalog): route
    # to the generic replacement motor rather than the _to_led
    # fallback (which would wrongly transform into a red LED).
    if type_id not in _DEFAULT_TRANSFORMS:
        cat = category_of(type_id)
        if cat is not None and cat != NON_REPLACEABLE and netlist is not None:
            replace_component(netlist, component.ref, type_id)
            return
    transform = _DEFAULT_TRANSFORMS.get(type_id, _to_led)
    if type_id == "dc_motor":
        transform(component, netlist, driver_type=driver_type)
    else:
        # If a grouped motor candidate is requalified as non-motor
        # (LED, buzzer, module_generic), it must first be ungrouped
        # to preserve the direction pins encapsulated in flags.
        ungroup_motor_in_netlist(component, netlist)
        transform(component, netlist)
    component.attributes["_confidence"] = "high"


# NOTE (2026-07-29) : l'ancien duo `_confirm_divergence` /
# `apply_with_divergence_guard` (confirmation AVANT remplacement d'une puce
# détectée par signature) a été SUPPRIMÉ : mort en production depuis que
# StudioView._resolve_wiring_netlist_tracked propose la RÉGÉNÉRATION à la
# validation (un seul popup, décision D 2026-07-08). La modale NON scopée ne
# peut pas toucher une puce à signature (collect_ambiguous ne retourne que les
# _confidence == "low") — seul le chemin scopé (engrenage) le peut, et il est
# couvert par le wrapper tracked.


def _humanize_pin(net: str) -> str:
    """`D7` -> "Digital pin 7", `A0` -> "Analog pin A0" (localized)."""
    from .visual_ambiguity_catalog import dialog_label
    lang = lang_manager.lang
    if net.startswith("D") and net[1:].isdigit():
        return dialog_label("pin_digital", lang).format(n=net[1:])
    if net.startswith("A") and net[1:].isdigit():
        return dialog_label("pin_analog", lang).format(net=net)
    return dialog_label("pin_generic", lang).format(net=net)


# `find_pin_excerpt` is now defined in `markers.py` and shared
# with the disambiguation layer (which uses it for per-pin scoping).
# Re-export to preserve the current API.
_find_prompt_excerpt = find_pin_excerpt


_RAIL_WIDTH = 244
"""Largeur du rail. Mesuree pour tenir « Moteur suppose 2 » et « Broche
numerique 11 » sur une ligne dans les quatre langues, sans imposer sa largeur
au panneau de detail (le picker a besoin de deux colonnes de cards)."""

_RAIL_BAR_W = 3
_RAIL_RADIUS = 6


class _RailRow(QPushButton):
    """Une ligne du rail des decisions (TODO #73).

    Deux lignes de texte -- le sujet, puis ce qui est actuellement retenu --
    plus une pastille d'etat, le tout dans un QPushButton pour heriter du
    CLAVIER : le rail se parcourt a la tabulation et s'active a l'Espace,
    comme la pile de sections qu'il remplace.

    L'element actif est marque par la seule barre phosphore a gauche, SANS
    fond plein : c'est la convention maison, tranchee par l'utilisateur le
    2026-07-08 (cf. `settings_dialog._NavButton` et `sidebar.NavButton`). La
    maquette de discussion proposait un fond teinte -- la convention gagne.

    ⚠️ `setAutoDefault(False)` + `setDefault(False)` : le piege des modales du
    cablage (`test_dialog_enter_key.py`). Cette modale contient un champ de
    saisie (la recherche du picker) et, sans ca, Entree dans ce champ remonte
    au premier bouton autoDefault de la fenetre -- qui serait desormais une
    ligne de rail, donc un saut de page au lieu d'une validation.
    """

    def __init__(self, title: str, value: str, *,
                 indented: bool = False, parent=None):
        super().__init__(parent)
        self._active = False
        self._hover = False
        self._done = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoDefault(False)
        self.setDefault(False)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Minimum)
        # Le bouton ne dessine RIEN lui-meme : la barre active est peinte
        # dans `paintEvent` et le texte vit dans les libelles enfants. C'est
        # exactement le contrat de `bare_button_qss` -- transparent, sans
        # bordure, sans marge interne --, et la propriete doit etre posee
        # AVANT le premier affichage pour que le selecteur morde.
        self.setProperty("variant", "bare")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(24 if indented else 9, 7, 9, 7)
        lay.setSpacing(8)

        # Les libelles ne doivent PAS intercepter la souris, sinon le clic
        # n'atteint jamais le bouton qui les porte.
        self._lbl_state = QLabel("")
        self._lbl_state.setFixedWidth(12)
        self._lbl_title = QLabel(title)
        self._lbl_title.setWordWrap(True)
        self._lbl_value = QLabel(value)
        self._lbl_value.setWordWrap(True)
        for lbl in (self._lbl_state, self._lbl_title, self._lbl_value):
            lbl.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        lay.addWidget(self._lbl_state, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(1)
        col.addWidget(self._lbl_title)
        col.addWidget(self._lbl_value)
        lay.addLayout(col, 1)

    # -- etat -----------------------------------------------------------
    def set_texts(self, title: str, value: str) -> None:
        self._lbl_title.setText(title)
        self._lbl_value.setText(value)

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self.apply_theme(theme_manager.current)

    def set_done(self, done: bool) -> None:
        self._done = bool(done)
        self.apply_theme(theme_manager.current)

    def is_active(self) -> bool:
        return self._active

    def is_done(self) -> bool:
        return self._done

    # -- rendu ----------------------------------------------------------
    def enterEvent(self, e):
        self._hover = True
        self.apply_theme(theme_manager.current)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.apply_theme(theme_manager.current)
        super().leaveEvent(e)

    def apply_theme(self, c) -> None:
        if self._active:
            titre = c.text_primary
        elif self._hover:
            titre = c.signal_ok
        else:
            titre = c.text_secondary
        poids = 700 if self._active else 600
        self.setStyleSheet(bare_button_qss(c))
        self._lbl_title.setStyleSheet(
            f"color: {titre}; background: transparent;"
            f" font-size: 9pt; font-weight: {poids};")
        self._lbl_value.setStyleSheet(
            f"color: {c.text_secondary}; background: transparent;"
            " font-size: 8pt;")
        # ✓ phosphore quand l'utilisateur a tranche, puce neutre sinon. La
        # puce n'est PAS ambre : une decision non encore confirmee n'est pas
        # un avertissement, seulement quelque chose qui reste a faire.
        self._lbl_state.setText("\u2713" if self._done else "\u25cf")
        self._lbl_state.setStyleSheet(
            f"color: {c.signal_ok if self._done else c.disabled_text};"
            " background: transparent; font-size: 9pt;")
        self.update()

    def paintEvent(self, e):
        if self._active:
            c = theme_manager.current
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            card = QRectF(self.rect())
            path = QPainterPath()
            path.addRoundedRect(card, _RAIL_RADIUS, _RAIL_RADIUS)
            p.setClipPath(path)
            p.fillRect(
                QRectF(card.left(), card.top(), _RAIL_BAR_W, card.height()),
                QColor(c.nav_active_border),
            )
            p.end()
        super().paintEvent(e)


class AmbiguityDialog(QDialog):
    """Modal that presents the ambiguous components and collects the
    user choice. After `exec()`:
    - if Confirm: `apply_choices(netlist)` mutates the netlist in place
    - if Cancel: no mutation, the caller can either re-render with
      the default values or abort the rendering
    """

    # Contextual '?' bridge (F2 step 4): clicking the help button of an
    # ambiguity groupbox emits this signal then closes the modal (reject).
    # Payload: (pin_arduino, type_initial_detecte). The caller (StudioView)
    # builds the chat prefix + system_extras from these 2 pieces of info.
    help_requested = pyqtSignal(str, str)

    # Même pont, mais pour la section consolidée « N moteurs DC » : là, la
    # question n'est pas « quel composant sur CETTE broche ? » mais « ces N
    # broches forment-elles UN moteur ou des sorties séparées ? ». Payload :
    # les broches du groupe, jointes. Les deux autres sections avaient leur
    # '?' depuis F2 ; celle-ci ne l'a récupéré qu'en reprenant l'affordance de
    # la modale débutant supprimée le 2026-08-13 (elle l'avait, nous non).
    motor_help_requested = pyqtSignal(str)

    # Le crayon d'une tuile deja declaree vient de REMPLACER sa librairie.
    # Payload : (ancienne_lib, DeclaredComponent sauvegarde). Cette modale n'a
    # aucun acces au Studio — c'est par ici qu'elle lui demande de proposer la
    # regeneration, exactement comme la fiche de l'onglet « Composants » le fait
    # deja. Sans ce signal, cette porte restait muette (TODO #52).
    lib_changed_in_form = pyqtSignal(str, object)

    def __init__(self, ambiguous: list[Component], parent=None,
                 *, prompt: str = "", context: str = "",
                 prompts_by_fn: dict | None = None,
                 suggested_dc_driver: str | None = None,
                 netlist: Netlist | None = None,
                 motors_limit: int | None = None,
                 initial_choices: dict[str, str] | None = None,
                 ungrouped_groupings: list[dict] | None = None):
        super().__init__(parent)
        self._ambiguous = ambiguous
        self._prompt = prompt
        self._context = context
        self._prompts_by_fn = prompts_by_fn or {}
        # Editorial DC motor limit: if provided AND the number of grouped
        # motors exceeds it, the modal opens auto in partial mode with
        # the first `motors_limit` PWMs pre-checked, and blocks any
        # additional check (cf _toggle_motor_grouping). Also shows an
        # explanatory warning banner at the top (cf _build).
        self._motors_limit: int | None = motors_limit
        # Full netlist: allows walking back to the original Arduino pin
        # when `inference.apply_rules` has already bridged the signal pin via
        # an internal net (e.g. LED.A = NET_X instead of D6 after adding the
        # series R). Without the netlist, we'd fall back on the label "Broche
        # NET_X" which makes no sense to the user.
        self._netlist = netlist
        # Driver suggested by Phase A (markers._detect_suggested_dc_driver
        # from prompt+user doc). Used to pre-check the driver radio when
        # the user switches to "Moteur DC", but stays modifiable.
        self._suggested_dc_driver = suggested_dc_driver
        # ref -> transform_id (string of the type_id, not the callable -- we
        # resolve at apply_choices time, simpler to handle the
        # dc_motor-with-driver case).
        self._chosen_type: dict[str, str] = {}
        # Refs sur lesquelles l'utilisateur a REELLEMENT tranche. Distinct de
        # `_chosen_type`, que le prompt ou une session precedente peuvent
        # remplir : confondre les deux ferait afficher « confirme » sur des
        # lignes que personne n'a regardees.
        self._decided: set[str] = set()
        # ⚠️ INITIALISE ICI, avant toute restitution. Place plus bas, cette
        # ligne ECRASAIT ce que la restitution des choix venait de poser : a
        # la reouverture de « Modifier les choix », la ligne « N moteurs DC »
        # restait grise et il fallait RE-cliquer le pilote deja selectionne
        # pour la faire passer au vert (QA, 2026-08-29).
        self._motors_decided = False
        # ref -> driver_type when chosen_type == "dc_motor". Otherwise absent.
        self._chosen_driver: dict[str, str] = {}
        # Pre-checking from the prompt suggestions (set by
        # markers._disambiguate_with_prompt when the user explicitly
        # mentions "moteur" on a pin). If the prompt also mentions the
        # driver, studio_view already resolved without a modal -- here we only
        # see the "type known but driver unknown" case: we pre-check the
        # type so the user only has to choose the driver.
        for c in ambiguous:
            suggested_type = c.attributes.get("_prompt_suggested_type")
            if suggested_type:
                self._chosen_type[c.ref] = suggested_type
            suggested_driver = c.attributes.get("_prompt_suggested_driver")
            if suggested_driver:
                self._chosen_driver[c.ref] = suggested_driver
        # Choix DEJA faits par l'utilisateur, restitues par l'appelant.
        # « Modifier mes choix » (`force_remodal`) rejoue TOUTES les
        # ambiguites sans appliquer les resolutions sauvegardees -- c'est
        # voulu, l'utilisateur veut pouvoir tout redecider. Mais sans ceci la
        # modale rouvrait sur les valeurs par defaut et il PERDAIT ce qu'il
        # avait deja tranche (retour utilisateur, 2026-08-29). Le pilote de
        # chaque moteur etait deja restitue de cette facon ; le type ne
        # l'etait pas.
        #
        # Pose APRES les suggestions du prompt : un choix explicite de
        # l'utilisateur prime sur une deduction. Et marque `_decided` --
        # il a vraiment choisi, le rail n'a pas a le lui redemander.
        for _ref, _tid in (initial_choices or {}).items():
            self._chosen_type[_ref] = _tid
            # ⚠️ PAS `_decided.add` directement : un moteur groupe n'a pas de
            # ligne a lui dans le rail, il vit dans la section consolidee qui
            # lit `_motors_decided`. En marquant au mauvais endroit, la ligne
            # « N moteurs DC » restait grise a la reouverture de « Modifier
            # les choix » et il fallait RE-cliquer le pilote deja selectionne
            # pour la faire passer au vert (QA, 2026-08-29).
            self._mark_decided(_ref)

        # ref -> frame containing the driver cards, for show/hide
        # depending on whether the user checked "Moteur DC" or not.
        self._driver_frames: dict[str, QFrame] = {}
        # ref -> ComponentPicker (recherche + cards) de la section classique,
        # et ref -> {type_driver: card} du sous-menu « Quel driver ? ». Deux
        # CACHES DE WIDGETS, donc vides a chaque reconstruction, comme
        # `_driver_frames` — les choix, eux, vivent dans `_chosen_type` /
        # `_chosen_driver` et survivent (cf. `_build`).
        self._pickers: dict[str, "QWidget"] = {}
        self._driver_cards: dict[str, dict[str, "QWidget"]] = {}
        # Les fiches de la bibliotheque, indexees par cle, memoisees PAR LANGUE
        # pour la duree de la modale : `build_index` relit le cache de lookups
        # sur le disque, ce qui n'a rien a faire dans le chemin d'une
        # reconstruction (une case a cocher de moteur en declenche une).
        self._infos_by_key: dict[str, dict] = {}
        # Bouton « Créer un composant » par section (QA G2). Le crayon
        # « corriger la déclaration » (QA G4) n'est plus un bouton de section :
        # chaque card porte le sien, toujours actif (modifier un composant
        # qu'on n'a pas declare, c'est le REPRENDRE A SON COMPTE — meme regle
        # que l'onglet « Composants », QA I4).
        self._declare_buttons: dict[str, QPushButton] = {}

        # ── Rail des decisions (TODO #73) ──────────────────────────────
        # Refs sur lesquelles l'utilisateur a REELLEMENT clique. Distinct de
        # `_chosen_type`, qui est pre-rempli par la pre-selection du
        # detecteur des la construction : confondre les deux ferait afficher
        # « confirme » sur des lignes que personne n'a regardees.
        # Decision courante, retenue par CLE et non par index : une
        # reconstruction change la longueur de la liste (degrouper un moteur
        # y ajoute trois lignes), un index survivrait en pointant ailleurs.
        self._current_key: str | None = None
        self._entries: list[dict] = []
        self._rail_rows: list[_RailRow] = []

        # Snapshot of the original groupings (= what the auto-detector
        # found). Used by the "Garder une partie" mode to allow the
        # bidirectional toggle: unchecking a motor ungroups it; re-checking
        # it re-groups it. Without this snapshot, re-grouping would be
        # impossible (the _grouped_* flags are lost at the mutation).
        # Format: [{"pwm": "D6", "dirs": ["D7", "D8"], "ref": "D1"}, ...].
        # `ref` = ref of the PWM component, indispensable for the re-grouping
        # after ungrouping: the component's pin "A" may be on a
        # bridge net (`NET_X` injected by LED series R inference, etc.)
        # rather than on the direct Arduino pin, so the lookup by
        # `pin("A").net == pwm_pin` would fail. The ref is stable.
        self._original_groupings: list[dict] = []
        for c in ambiguous:
            if c.attributes.get("_grouped_pwm_pin"):
                self._original_groupings.append({
                    "pwm": c.attributes["_grouped_pwm_pin"],
                    "dirs": list(c.attributes["_grouped_dir_pins"]),
                    "ref": c.ref,
                })
        # Groupements que l'APPELANT a deja defaits avant d'ouvrir : sa
        # pre-passe rejoue une decision « ce n'est pas un moteur » deja
        # sauvegardee. Sans eux, le rail ignorerait que ces broches ont forme
        # un moteur et n'offrirait pas « Regrouper en moteur » — la decision
        # serait irreversible precisement la ou l'utilisateur vient la revoir.
        _defaits = {g["pwm"] for g in (ungrouped_groupings or [])}
        _connus = {g["pwm"] for g in self._original_groupings}
        for g in (ungrouped_groupings or []):
            if g["pwm"] not in _connus:
                self._original_groupings.append(dict(g))

        # Deterministic sort of the groupings by pin number (D3 < D5 < D9...)
        # so the pre-checking in limit mode is predictable.
        def _pin_order(g):
            net = g["pwm"]
            if net.startswith("D") and net[1:].isdigit():
                return (0, int(net[1:]))
            if net.startswith("A") and net[1:].isdigit():
                return (1, int(net[1:]))
            return (2, 0)
        self._original_groupings.sort(key=_pin_order)

        # PWMs TO WIRE (= checked in the partial UI). Key
        # semantics: an unchecked motor stays recognized as dc_motor but will
        # be marked _skip_wiring=True at apply_choices -> it appears in
        # the "Detectes mais non cables" section of the right panel, without
        # cluttering the schema. The classic ungrouping option stays
        # available via the "Pas un moteur ?" button (cf _build_partial_
        # checkboxes_subframe), for the detector false-positive case.
        # Normal case: all initially checked (= all wired).
        # motors_limit-exceeded case: only the first `motors_limit`
        # PWMs (by pin order). No automatic ungrouping.
        limit_active = (
            self._motors_limit is not None
            and len(self._original_groupings) > self._motors_limit
        )
        if limit_active:
            self._currently_kept_pwms: set[str] = {
                g["pwm"] for g in
                self._original_groupings[: self._motors_limit]
            }
        else:
            self._currently_kept_pwms: set[str] = {
                g["pwm"] for g in self._original_groupings
            } - _defaits
        # PWMs declared "these are motors" (vs detector false
        # positives). All declared motor by default since the detector
        # grouped them. The user can uncheck to ungroup the pins into
        # individual ambiguities, without making the row disappear (the
        # row stays visible to allow the re-correction).
        # Unchecking 'Moteur' automatically greys out 'Cabler ce moteur'.
        # ⚠️ Les groupements DEFAITS en sont exclus : l'utilisateur a deja dit
        # que ce n'etaient pas des moteurs. Les y mettre les re-proposerait
        # comme tels, ce qui est exactement le defaut qu'on repare.
        self._motor_declared_real: set[str] = {
            g["pwm"] for g in self._original_groupings
        } - _defaits

        from .visual_ambiguity_catalog import dialog_label
        self.setWindowTitle(dialog_label("adv_window_title", lang_manager.lang))
        self.setModal(True)
        self.setMinimumWidth(540)
        self._build()
        self._update_ok_state()
        # Centralized styling of the controls (buttons + radios/checkboxes); re-applied
        # on each theme change. cf theme.*_button_qss / radio_checkbox_qss.
        theme_manager.changed.connect(self._apply_control_styles)

    def _cap_height_to_screen(self) -> None:
        """Limit the modal's max height to 80% of the screen height
        so it doesn't overflow visually. The internal QScrollArea handles
        the scroll if the content is longer."""
        screen = self.screen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        max_h = int(avail.height() * 0.80)
        self.setMaximumHeight(max_h)

    def _build(self) -> None:
        # Structure: vertical root layout contains:
        #   1. intro (fixed at the top)
        #   2. QScrollArea with all the ambiguity sections
        #      (vertical scroll if the content overflows)
        #   3. OK/Cancel buttons (fixed at the bottom)
        # The scroll prevents the modal from growing beyond the
        # screen height when the user ungroups N motors into 2N+ LEDs.
        if self.layout() is None:
            root = QVBoxLayout(self)
            root.setContentsMargins(16, 16, 16, 12)
            root.setSpacing(10)
        else:
            root = self.layout()
            while root.count():
                item = root.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()
            # NB: we do NOT clear _chosen_type / _chosen_driver in order to
            # preserve the user's choices across rebuilds
            # (otherwise the partial mode with bidirectional toggle would
            # lose the chosen driver on each check/uncheck). The
            # section builders pre-check the radios based on
            # these dicts. Only the Qt widget caches are emptied -- the
            # widgets are recreated by the section builders.
            #
            # ⚠️ Vider `_pickers` est OBLIGATOIRE, et la raison n'est PAS que
            # les widgets viennent d'etre detruits : `deleteLater()` n'est pas
            # execute dans la boucle imbriquee d'un `exec()` (piege maison,
            # `processEvents` ne le fait pas davantage), donc un picker laisse
            # ici resterait un objet C++ bien VIVANT et aucun RuntimeError ne
            # signalerait quoi que ce soit.
            #
            # Ce qui casse est plus discret : `_update_ok_state` GRISE Valider
            # quand un picker n'a aucune selection effective (regle Q9). Un
            # picker survivant a la reconstruction qui l'a retire de l'ecran
            # continue de gater cette decision, invisible et intouchable.
            # Reproduit : decocher un moteur, taper dans le picker classique
            # qui apparait une recherche qui masque le choix, recocher le
            # moteur -> la section classique disparait, son picker reste dans
            # ce dictionnaire, et Valider est grise DEFINITIVEMENT sans que
            # rien a l'ecran ne dise pourquoi. Verrouille par
            # `test_a_rebuild_does_not_leave_an_offscreen_picker_gating_validate`
            # (`scripts/test_ambiguity_cards_smoke.py`).
            self._driver_frames.clear()
            self._pickers.clear()
            self._driver_cards.clear()

        # '?' buttons recreated on each build -> we start from an empty list
        # (used to re-style them on theme change).
        self._help_buttons: list[QPushButton] = []
        # Same idea for the motors-limit banner below: it only exists when the
        # limit is exceeded, and a rebuild destroys it. Reset here so
        # `_apply_control_styles` never touches a widget deleted by a rebuild.
        self._warn_label: QLabel | None = None

        # Priority warning banner when motors_limit is active and the
        # number of detected motors exceeds it. Placed BEFORE the intro
        # so it's not drowned in the text. Orange color visible but
        # not alarmist (= editorial info, not a blocking error).
        from .visual_ambiguity_catalog import dialog_label
        lang = lang_manager.lang
        if (self._motors_limit is not None
                and len(self._original_groupings) > self._motors_limit):
            n_detected = len(self._original_groupings)
            warn = QLabel(
                dialog_label("motors_limit_warning", lang).format(
                    n=n_detected, limit=self._motors_limit)
            )
            warn.setWordWrap(True)
            # Colors come from the theme, applied by `_apply_control_styles`
            # (called at the end of this build and on every theme change).
            self._warn_label = warn
            root.addWidget(warn)

        intro = QLabel(dialog_label("adv_intro", lang))
        intro.setWordWrap(True)
        root.addWidget(intro)

        # ── Rail des decisions + panneau de detail (TODO #73) ─────────────
        # Avant : toutes les sections empilees dans UN defileur. A trois
        # broches ambigues, les deux tiers du contenu etaient hors ecran et
        # rien ne disait combien de decisions attendaient -- il fallait faire
        # defiler pour le decouvrir.
        #
        # ⚠️ LES SECTIONS SONT TOUJOURS TOUTES CONSTRUITES, et ce n'est pas
        # un reste de l'ancienne structure : c'est ce qui remplit `_pickers`
        # et, par la pre-selection de `_build_classic_section`,
        # `_chosen_type`. Ne construire que la page courante rendrait
        # « Valider » DEFINITIVEMENT gris -- `_update_ok_state` exige un type
        # par composant, et une section jamais construite n'en pose aucun.
        # Le seul changement est le CONTENANT.
        grouped_components = [c for c in self._ambiguous
                              if c.attributes.get("_grouped_pwm_pin")]
        # UNE SEULE vue pour les moteurs, quel qu'en soit le nombre. Le seuil
        # etait a 2 : un moteur unique passait par `_build_grouped_section`
        # (radios « Oui c'est un moteur DC / Non c'est autre chose »), deux ou
        # plus par la section consolidee (cases a cocher). Deux presentations
        # pour la meme question, et l'utilisateur tombait sur l'une ou l'autre
        # selon la porte : « la vue est differente entre la modif composant
        # via engrenage et modifier mes choix » (QA, 2026-08-29).
        #
        # La page reste affichee meme si tous les moteurs sont decoches : sans
        # elle, les cases permettant la correction inverse disparaitraient.
        consolidate_motors = len(self._original_groupings) >= 1

        self._entries = []
        self._rail_rows = []
        self._regroup_buttons: list[QPushButton] = []
        self._stack = QStackedWidget()
        self._stack.setObjectName("ambiguityStack")

        if consolidate_motors:
            self._add_decision_page(
                self._build_consolidated_motors_section(grouped_components),
                kind="motors", component=None)

        # ⚠️ **Les moteurs de NIVEAU 1 (nommes par le CODE, `signature_
        # detected`) ont leur section a eux** (QA AB2, 2026-08-31). Ouverts
        # par « Modifier les composants », ils passaient par la section
        # classique : deux pages JUMELLES toutes deux titrees « Broche
        # numerique 9 » — leurs broches remontent au MEME signal Arduino, la
        # clef degeneree que le #86 (a) documentait — avec un picker offrant
        # de les requalifier en LED, alors que le code appelle la lib L298N.
        # Pire : valider aurait ecrit leurs resolutions sous cette clef
        # PARTAGEE (moteurs + driver confondus), la corruption exacte que le
        # #86 (a) predisait si une porte d'edition s'ouvrait sans corriger la
        # clef. Meme patron que la section stepper du T6 : la seule question
        # legitime est LE PILOTE.
        lib_motors = [c for c in self._ambiguous
                      if c.type == "dc_motor"
                      and c.attributes.get("signature_detected")]
        if lib_motors:
            self._add_decision_page(
                self._build_lib_motors_section(lib_motors),
                kind="pin", component=lib_motors[0])

        for c in self._ambiguous:
            if c in grouped_components:
                # Les moteurs groupes vivent TOUS dans la section consolidee
                # ci-dessus, seuls ou a plusieurs (2026-08-29). Il n'existe
                # plus de section « un seul moteur ».
                continue
            if c in lib_motors:
                continue
            if c.type in STEPPER_DRIVERS:
                # Un driver pas-a-pas ne pose pas la question << quelle est
                # cette broche ? >> : le code l'a nomme. La seule question est
                # << laquelle de ces quatre variantes ? >>.
                self._add_decision_page(
                    self._build_stepper_driver_section(c),
                    kind="pin", component=c)
                continue
            self._add_decision_page(self._build_classic_section(c),
                                    kind="pin", component=c)

        split = QHBoxLayout()
        split.setContentsMargins(0, 0, 0, 0)
        split.setSpacing(12)

        # Le rail est TOUJOURS la, meme pour une seule decision. Il a d'abord
        # ete masque dans ce cas -- une ligne n'apprend rien et coute 244 px
        # au picker -- mais la modale changeait alors de FORME selon la porte
        # par laquelle on entrait : l'engrenage (« Modifier ce composant… »)
        # n'ouvre qu'un composant et donnait une fenetre sans rien de commun
        # avec celle de la generation. Une seule mise en page, quelle que soit
        # la porte (decision utilisateur, QA X4, 2026-08-29).
        self._rail_host = self._build_rail()
        split.addWidget(self._rail_host)
        self._vsep = QWidget()
        self._vsep.setObjectName("ambiguityVSep")
        self._vsep.setFixedWidth(1)
        split.addWidget(self._vsep)
        split.addWidget(self._stack, stretch=1)

        holder = QWidget()
        holder.setLayout(split)
        holder.setMinimumHeight(400)
        root.addWidget(holder, stretch=1)
        # Le rail prend sa largeur EN PLUS de celle du picker, qui a besoin
        # de ses deux colonnes de cards : sans cette reprise, la grille
        # retombait a une colonne des que le rail apparaissait.
        self.setMinimumWidth(860)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        # Without this the two buttons read « OK » / « Cancel » whatever the
        # app's language: Qt translates its standard buttons from the SYSTEM
        # locale, not from lang_manager.
        localize_button_box(self._buttons)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        # Cette modale contient un CHAMP DE SAISIE — celui de la recherche du
        # `ComponentPicker` (avant 2026-08-13, c'était la liste déroulante
        # éditable). Sans ceci, Entrée dans ce champ remonte au bouton
        # autoDefault et VALIDE la modale (même classe de bug que le champ zoom
        # du schéma — « je tape 100 ça revient à 83% », revue 2026-07-29 #5).
        # Ça ne SUFFIT pas : Qt remet `isDefault` sur OK au show() — d'où
        # `keyPressEvent`. Verrouillé par `test_dialog_enter_key.py`.
        for btn in self._buttons.buttons():
            btn.setAutoDefault(False)
            btn.setDefault(False)
        root.addWidget(self._buttons)
        # Cap the modal height at 80% of the screen to prevent
        # it from overflowing when the content is very long.
        self._cap_height_to_screen()
        # Centralized styling of the controls recreated by this build (OK/Cancel +
        # radios + checkboxes). The labels/cards keep their own style.
        self._apply_control_styles(theme_manager.current)
        # Restaure la decision courante PAR CLE (cf. `_current_key`), sinon
        # retombe sur la premiere non confirmee -- pas sur la premiere tout
        # court : rouvrir la modale doit poser l'utilisateur devant ce qui
        # lui reste a faire.
        self._select_decision(self._index_for_key(self._current_key))

    # ── Rail des décisions (TODO #73) ─────────────────────────────────

    def _add_decision_page(self, section, *, kind: str,
                           component: Component | None) -> None:
        """Enveloppe une section dans SON défileur et l'ajoute à la pile.

        Un défileur par page, pas un seul autour de la pile : chaque page
        garde ainsi sa position, et une page courte n'hérite pas du vide de
        la plus longue (`QStackedWidget` prend la taille de son plus grand
        enfant).

        ⚠️ La barre verticale n'est plus TOUJOURS visible. Elle l'était pour
        « signaler qu'on peut défiler » — un signal que le rail porte
        désormais bien mieux, en disant ce qui existe au lieu de suggérer
        qu'il y a peut-être autre chose. Une barre sur une page qui tient
        entièrement à l'écran est devenue du bruit.
        """
        scroll = QScrollArea()
        scroll.setObjectName("ambiguityScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(section)
        lay.addStretch(1)
        scroll.setWidget(host)
        self._stack.addWidget(scroll)
        self._entries.append({
            "kind": kind,
            "component": component,
            "sub_of": (self._sub_of(component)
                       if component is not None else None),
        })

    def _section_net(self, c: Component) -> str:
        """Broche Arduino qui NOMME la section de ce composant.

        Même remontée que `_build_classic_section` : sans elle, un composant
        dont l'inférence a ponté la broche de signal (LED + R série ->
        `NET_X`) serait « Broche NET_X » dans le rail et « Broche 6 » dans
        son propre titre.
        """
        net = _arduino_signal_pin(c, self._netlist)
        if net is None:
            sig = (c.pin("A") or c.pin("SIG") or
                   (c.pins[0] if c.pins else None))
            net = sig.net if sig else "?"
        return net

    def _sub_of(self, c: Component) -> str | None:
        """Le groupement moteur d'origine d'où cette broche a été libérée,
        s'il a été dégroupé. C'est ce qui permet au rail de la remettre SOUS
        son moteur, avec le bouton qui l'y regroupe.

        Couvre aussi le moteur UNIQUE : sa section groupée disparaît dès
        qu'on le dégroupe (le composant perd ses attributs `_grouped_*`),
        donc sans le rail il n'existait AUCUN chemin de retour — le trou
        était le même que pour les moteurs multiples, en plus discret.
        """
        if c.attributes.get("_grouped_pwm_pin"):
            return None
        net = self._section_net(c)
        for g in self._original_groupings:
            if g["pwm"] in self._motor_declared_real:
                continue
            if net == g["pwm"] or net in g["dirs"]:
                return g["pwm"]
        return None

    @staticmethod
    def _entry_key(entry: dict) -> str:
        comp = entry["component"]
        return "motors" if comp is None else comp.ref

    def _entry_done(self, entry: dict) -> bool:
        """✓ = l'utilisateur a tranché ET la décision est COMPLÈTE.

        Les deux conditions comptent, et pour des raisons différentes : sans la
        première, la déduction du détecteur passerait pour un choix ; sans la
        seconde, le rail annonce ✓ sur une ligne qui continue de bloquer
        « Valider » — c'est ce que la QA X4 a trouvé, un moteur confirmé dont
        le pilote n'était pas choisi.
        """
        if entry["component"] is None:
            if not self._motors_decided:
                return False
            return all(self._is_complete(c) for c in self._ambiguous
                       if c.attributes.get("_grouped_pwm_pin"))
        c = entry["component"]
        return c.ref in self._decided and self._is_complete(c)

    def _entry_title(self, entry: dict) -> str:
        from .visual_ambiguity_catalog import dialog_label
        lang = lang_manager.lang
        c = entry["component"]
        if c is None:
            return dialog_label("motors_detected_title", lang).format(
                k=len(self._original_groupings))
        if (c.type == "dc_motor"
                and c.attributes.get("signature_detected")):
            # La page des moteurs de NIVEAU 1 : son ancre est un moteur dont
            # la broche remonte au driver — la titrer « Broche numerique 9 »
            # donnait deux lignes jumelles (QA AB2, 2026-08-31). Le titre dit
            # le LOT, comme la section consolidee.
            k = sum(1 for m in self._ambiguous
                    if m.type == "dc_motor"
                    and m.attributes.get("signature_detected"))
            return dialog_label("motors_detected_title", lang).format(k=k)
        # Un composant groupe n'a plus d'entree a lui : il est dans la
        # section consolidee, dont le titre est rendu juste au-dessus.
        net = self._section_net(c)
        if not net or net == "?":
            # Aucune broche cablee -- typiquement un placeholder d'`#include`
            # inconnu. `_humanize_pin` rendait alors « Broche  », un titre
            # VIDE et illisible (releve en QA, 2026-08-29). C'est le NOM du
            # composant qui porte l'information dans ce cas.
            return _type_label(c.type, lang)
        return _humanize_pin(net)

    def _entry_value(self, entry: dict) -> str:
        """Ce qui est actuellement retenu pour cette décision."""
        from .visual_ambiguity_catalog import dialog_label
        from .picker_logic import _label_for
        lang = lang_manager.lang
        c = entry["component"]
        if c is None:
            n = len(self._original_groupings)
            k = sum(1 for g in self._original_groupings
                    if g["pwm"] in self._motor_declared_real)
            if k == n:
                return dialog_label("rail_motors_all", lang).format(n=n)
            if k == 0:
                return dialog_label("rail_motors_none", lang)
            return dialog_label("rail_motors_some", lang).format(k=k, n=n)
        tid = self._chosen_type.get(c.ref)
        if tid is None and c.attributes.get("_grouped_pwm_pin"):
            tid = "dc_motor"
        # None = rien n'est retenu. Retomber sur `c.type` reintroduirait dans
        # le rail la devinette qu'on vient de retirer du picker.
        if tid is None:
            return None
        return _label_for(tid, lang)

    def _rail_value_text(self, entry: dict) -> str:
        """Le libellé du choix, préfixé de « proposé : » tant que
        l'utilisateur n'a rien cliqué. La distinction n'est pas cosmétique :
        toutes les sections arrivent PRÉ-SÉLECTIONNÉES sur la déduction du
        détecteur, et afficher celle-ci comme un choix ferait dire à
        l'utilisateur ce qu'il n'a pas dit."""
        from .visual_ambiguity_catalog import dialog_label
        lang = lang_manager.lang
        val = self._entry_value(entry)
        if val is None:
            return dialog_label("rail_undecided", lang)
        if self._entry_done(entry):
            return val
        return dialog_label("rail_proposed", lang).format(label=val)

    def _more_subs_after(self, index: int, pwm: str) -> bool:
        return any(e["sub_of"] == pwm for e in self._entries[index + 1:])

    def _make_regroup_button(self, pwm: str) -> QPushButton:
        from .visual_ambiguity_catalog import dialog_label
        lang = lang_manager.lang
        grp = next((g for g in self._original_groupings
                    if g["pwm"] == pwm), None)
        pins = ", ".join([pwm] + list(grp["dirs"])) if grp else pwm
        btn = QPushButton(dialog_label("rail_regroup", lang))
        btn.setToolTip(dialog_label("rail_regroup_tip", lang).format(
            pins=pins))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setAutoDefault(False)
        btn.setDefault(False)
        btn.setSizePolicy(QSizePolicy.Policy.Preferred,
                          QSizePolicy.Policy.Fixed)
        btn.clicked.connect(
            lambda _=False, p=pwm: self._regroup_from_rail(p))
        self._regroup_buttons.append(btn)
        return btn

    def _regroup_from_rail(self, pwm: str) -> None:
        """« Regrouper en moteur », depuis le rail.

        Passe par `_toggle_motor_declared` au lieu d'appeler le regroupement
        directement : c'est LE point de passage qui remet aussi le câblage et
        reconstruit. Le court-circuiter laisserait un moteur reconnu mais
        silencieusement non câblé.
        """
        self._toggle_motor_declared(pwm, is_motor=True)

    def _build_rail(self) -> QWidget:
        from .visual_ambiguity_catalog import dialog_label
        lang = lang_manager.lang
        host = QWidget()
        host.setObjectName("ambiguityRail")
        host.setFixedWidth(_RAIL_WIDTH)
        outer = QVBoxLayout(host)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        n = len(self._entries)
        self._rail_title = QLabel(dialog_label(
            "rail_title_one" if n == 1 else "rail_title_many",
            lang).format(n=n))
        self._rail_sub = QLabel("")
        self._rail_sub.setWordWrap(True)
        outer.addWidget(self._rail_title)
        outer.addWidget(self._rail_sub)
        outer.addSpacing(6)

        # Le rail défile SI la liste est longue, mais il ne défile pas dans
        # le cas courant : c'est toute la promesse du maître-détail — savoir
        # ce qui reste sans avoir à chercher.
        scroll = QScrollArea()
        scroll.setObjectName("ambiguityScrollRail")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)

        for i, entry in enumerate(self._entries):
            row = _RailRow(self._entry_title(entry),
                           self._rail_value_text(entry),
                           indented=entry["sub_of"] is not None)
            row.set_done(self._entry_done(entry))
            row.clicked.connect(
                lambda _=False, k=i: self._select_decision(k))
            lay.addWidget(row)
            self._rail_rows.append(row)
            # « Regrouper » se pose après la DERNIÈRE broche libérée par ce
            # moteur. C'est le correctif de fond du ticket : l'annulation
            # vivait dans la section consolidée restée tout en haut, à deux
            # écrans des broches qu'elle venait de faire apparaître.
            pwm = entry["sub_of"]
            if pwm is not None and not self._more_subs_after(i, pwm):
                lay.addWidget(self._make_regroup_button(pwm))

        lay.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll, stretch=1)
        self._refresh_rail_header()
        return host

    def _index_for_key(self, key: str | None) -> int:
        """Index de la décision portant cette clé ; à défaut la première non
        confirmée — pas la première tout court : une reconstruction doit
        reposer l'utilisateur devant ce qui lui reste à faire."""
        if key is not None:
            for i, e in enumerate(self._entries):
                if self._entry_key(e) == key:
                    return i
        for i, e in enumerate(self._entries):
            if not self._entry_done(e):
                return i
        return 0

    def _select_decision(self, index: int) -> None:
        if not self._entries:
            return
        index = max(0, min(index, len(self._entries) - 1))
        self._stack.setCurrentIndex(index)
        self._current_key = self._entry_key(self._entries[index])
        for j, row in enumerate(self._rail_rows):
            row.set_active(j == index)

    def _refresh_rail_header(self) -> None:
        from .visual_ambiguity_catalog import dialog_label
        sub = getattr(self, "_rail_sub", None)
        if sub is None:
            return
        lang = lang_manager.lang
        left = sum(1 for e in self._entries if not self._entry_done(e))
        sub.setText(dialog_label("rail_all_done", lang) if left == 0
                    else dialog_label("rail_remaining", lang).format(n=left))

    def _refresh_rail(self) -> None:
        """Met à jour les libellés et l'état du rail SANS reconstruire : un
        clic sur une card ne doit pas détruire le picker qui vient de
        l'émettre."""
        for row, entry in zip(self._rail_rows, self._entries):
            row.set_texts(self._entry_title(entry),
                          self._rail_value_text(entry))
            row.set_done(self._entry_done(entry))
        self._refresh_rail_header()

    def _on_user_picked(self, ref: str) -> None:
        """Un clic RÉEL sur une card, par opposition à la pré-sélection.

        Séparé de `_on_type_toggled`, que `_build` appelle lui aussi pour
        poser la déduction du détecteur : les confondre ferait défiler les
        pages toutes seules pendant la construction, et marquerait
        « confirmé » des décisions que personne n'a regardées.

        L'avance ne fait PAS le tour de la liste : elle s'arrête à la
        dernière. Revenir au début arracherait l'utilisateur à l'endroit où
        il travaille ; l'en-tête du rail dit ce qui reste.
        """
        self._decided.add(ref)
        self._refresh_rail()
        # L'avance part de la page QUI PORTE ce picker, pas de la page
        # affichee. Les deux coincident quand l'utilisateur clique ce qu'il
        # voit -- mais s'en remettre a `currentIndex()` ferait dependre la
        # destination d'un etat qui n'a rien a voir avec le choix emis.
        cur = next((i for i, e in enumerate(self._entries)
                    if self._entry_key(e) == ref), self._stack.currentIndex())
        nxt = next((i for i in range(cur + 1, len(self._entries))
                    if not self._entry_done(self._entries[i])), None)
        if nxt is not None:
            self._select_decision(nxt)

    def keyPressEvent(self, ev):
        """Enter NEVER validates this modal -- it is the search field's key.

        Neutralising the button box is not enough: Qt puts `isDefault` back on
        OK at show() time, so the key reached the dialog and closed it while
        the user was searching (QA C2, 2026-08-08). Whoever holds the focus,
        validating stays an explicit click on OK. Escape still cancels
        (QDialog handles it below).
        """
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            ev.accept()
            return
        super().keyPressEvent(ev)

    def _apply_control_styles(self, c) -> None:
        """Apply the agreed style (consistent with the rest of the app) to the WHOLE
        modal: background + labels + group boxes + scrollable zone, OK/Cancel
        buttons, radios/checkboxes, combos (dropdowns) and the green '?' help button.
        Re-called on each rebuild and each theme change."""
        # Background + labels + group boxes + scroll: inherited by children not
        # styled individually (the combos/buttons/radios set their own).
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c.main_bg}; }}
            QLabel {{ color: {c.text_primary}; background: transparent; }}
            QScrollArea#ambiguityScroll {{
                background: transparent; border: none;
            }}
            QScrollArea#ambiguityScroll > QWidget > QWidget {{
                background: transparent;
            }}
            QScrollArea#ambiguityScrollRail {{
                background: transparent; border: none;
            }}
            QScrollArea#ambiguityScrollRail > QWidget > QWidget {{
                background: transparent;
            }}
            QWidget#ambiguityVSep {{ background-color: {c.border}; }}
            QGroupBox {{
                color: {c.text_primary};
                background-color: {c.surface};
                border: 1px solid {c.border};
                border-radius: 8px;
                margin-top: 10px;
                padding: 10px;
                font-weight: 600;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 4px;
                color: {c.text_primary};
            }}
        """)
        # Motors-limit warning banner: same recipe as NudgeBanner(variant=
        # "info") -- solid `signal_warn` amber plus the contrasting
        # `btn_primary_text` -- instead of the literal hex it used to hard-code,
        # which stayed light-on-light in the dark theme. QSS on the label rather
        # than QPalette: the modal-wide sheet just above declares
        # `QLabel { background: transparent; }`, and a matching QSS rule beats
        # the palette, so only the label's own sheet can win.
        warn_lbl = getattr(self, "_warn_label", None)
        if warn_lbl is not None:
            warn_lbl.setStyleSheet(
                f"QLabel {{ background: {c.signal_warn}; "
                f"color: {c.btn_primary_text}; border: none; "
                f"border-radius: 6px; padding: 8px 10px; }}"
            )
        if hasattr(self, "_buttons"):
            ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
            cancel_btn = self._buttons.button(
                QDialogButtonBox.StandardButton.Cancel)
            if ok_btn is not None:
                ok_btn.setStyleSheet(primary_button_qss(c))
            if cancel_btn is not None:
                cancel_btn.setStyleSheet(secondary_button_qss(c))
        # Radios + checkboxes: a single stylesheet on the modal, inherited by all
        # the child QRadioButton/QCheckBox (recreated on each _build).
        radio_qss = radio_checkbox_qss(c)
        for w in self.findChildren((QRadioButton, QCheckBox)):
            w.setStyleSheet(radio_qss)
        # ⚠️ PLUS de boucle sur les QComboBox (2026-08-13). Cette modale n'en
        # contient plus aucun depuis le passage aux cards — mais `findChildren`
        # descend aussi dans les dialogues ENFANTS : la boucle ne pouvait donc
        # plus atteindre QUE des widgets etrangers, et repeindre les listes du
        # formulaire de declaration avec la recette d'ici au premier changement
        # de theme. C'est exactement la fuite que
        # `test_declare_form_same_from_both_doors.py` verrouille.
        # '?' help buttons: styled by theme.help_button_qss via the `help`
        # variant, so the theme change is handled by the application sheet --
        # nothing to re-apply per button here.
        # « Créer un composant » : style secondaire, plus un état ENFONCÉ
        # nettement vert. Sorti de la liste déroulante, c'est lui seul qui dit
        # que ce composant sera décrit à la main plutôt que choisi.
        for b in getattr(self, "_declare_buttons", {}).values():
            b.setStyleSheet(secondary_button_qss(c, radius=8,
                                                 padding="0 14px"))
        # ── Rail des décisions (TODO #73) ─────────────────────────────
        # Chaque ligne se repeint elle-même : son apparence dépend d'un état
        # (active / survolée / confirmée) que seule elle connaît.
        for row in getattr(self, "_rail_rows", []):
            row.apply_theme(c)
        title = getattr(self, "_rail_title", None)
        if title is not None:
            title.setStyleSheet(
                f"color: {c.text_primary}; background: transparent;"
                " font-size: 10pt; font-weight: 700;")
        sub = getattr(self, "_rail_sub", None)
        if sub is not None:
            sub.setStyleSheet(
                f"color: {c.text_secondary}; background: transparent;"
                " font-size: 8pt;")
        for btn in getattr(self, "_regroup_buttons", []):
            btn.setStyleSheet(secondary_button_qss(
                c, radius=6, font_pt=8, padding="5px 10px"))

    @staticmethod
    def _darken(hex_color: str, factor: float = 0.82) -> str:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"#{int(r*factor):02x}{int(g*factor):02x}{int(b*factor):02x}"

    def _make_help_button(self, pin_net: str,
                          type_initial: str) -> QPushButton:
        """Build a round GREEN 24x24 '?' button. Click closes the modal
        and emits `help_requested(pin_net, type_initial)` so the caller
        opens the chat with a structured context (F2 step 4)."""
        btn = self._new_help_button()
        btn.clicked.connect(
            lambda _checked=False, p=pin_net, t=type_initial:
                self._on_help_clicked(p, t)
        )
        return btn

    def _make_motor_help_button(self, pins: list[str]) -> QPushButton:
        """'?' of the consolidated N-motors section. Same button, other
        question: the payload is the WHOLE pin group, not one pin, because
        what the user hesitates on there is a dichotomy (one motor vs N
        separate outputs), not a component choice."""
        btn = self._new_help_button()
        joined = ", ".join(pins)
        btn.clicked.connect(
            lambda _checked=False, p=joined: self._on_motor_help_clicked(p)
        )
        return btn

    def _new_help_button(self) -> QPushButton:
        """Bare '?' button, no click wiring — shared by the two bridges
        above so their look and their Enter-key behaviour cannot drift."""
        btn = QPushButton("?")
        btn.setFixedSize(24, 24)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # Même omission que dans la modale débutant : sans ceci, Entrée peut
        # tomber sur le bouton d'aide, qui ferme la modale en rejetant.
        btn.setAutoDefault(False)
        btn.setDefault(False)
        # Styled by theme.help_button_qss (application sheet). Property set
        # BEFORE the first show, which is what makes it take effect without a
        # style unpolish/polish -- measured, cf. the plan of 2026-08-11.
        btn.setProperty("variant", "help")
        self._help_buttons.append(btn)
        btn.setToolTip(lang_manager.current.chat_help_tooltip)
        return btn

    def _on_help_clicked(self, pin_net: str, type_initial: str) -> None:
        """Click on '?': closes the modal (reject) and propagates the signal
        to the caller which will open the chat with context (F2 step 4)."""
        self.help_requested.emit(pin_net, type_initial)
        self.reject()

    def _on_motor_help_clicked(self, pins: str) -> None:
        """Same, for the consolidated motors section."""
        self.motor_help_requested.emit(pins)
        self.reject()

    def _build_classic_section(self, c: Component) -> QGroupBox:
        """Standard section: 1 pin = 1 ambiguity with the 4 usual radios
        (red LED / Buzzer / DC motor / Module). In-line driver sub-menu
        under DC motor for the Phase B driver choice."""
        # Walk back to the original Arduino pin via the internal bridge_net if
        # apply_rules already ran (typically LED + series R: anode bridged
        # via NET_X instead of Dn). Without the netlist, fall back on the direct net.
        net = _arduino_signal_pin(c, self._netlist)
        if net is None:
            sig_pin = (c.pin("A") or c.pin("SIG") or
                       (c.pins[0] if c.pins else None))
            net = sig_pin.net if sig_pin else "?"
        group = QGroupBox(_humanize_pin(net))
        group_lay = QVBoxLayout(group)
        group_lay.setSpacing(6)

        fn_prompt = self._prompts_by_fn.get(c.fn_id, "") if c.fn_id else ""
        excerpt = (
            _find_prompt_excerpt(fn_prompt, net, "")
            or _find_prompt_excerpt(self._prompt, net, self._context)
        )
        from .visual_ambiguity_catalog import dialog_label
        if c.attributes.get("signature_detected"):
            # Niveau 1 : rien n'a été deviné. La phrase « pas de mention
            # explicite dans ton prompt » parlait de l'extrait PAR BROCHE
            # (le prompt ne nomme pas « D9 ») et devenait fausse dès que le
            # prompt nommait le composant (QA AC1, 2026-08-31).
            ctx_label = QLabel(
                dialog_label("signature_excerpt", lang_manager.lang))
        elif excerpt:
            ctx_label = QLabel(dialog_label(
                "prompt_excerpt", lang_manager.lang).format(excerpt=excerpt))
        else:
            ctx_label = QLabel(
                dialog_label("prompt_excerpt_missing", lang_manager.lang))
        ctx_label.setWordWrap(True)
        ctx_label.setTextFormat(Qt.TextFormat.RichText)
        # Context text + '?' button ON THE SAME LINE (vertical space
        # saving): the '?' closes the modal and opens the chat (F2 step 4).
        ctx_row = QHBoxLayout()
        ctx_row.setContentsMargins(0, 0, 0, 0)
        ctx_row.setSpacing(8)
        ctx_row.addWidget(ctx_label, 1)
        ctx_row.addWidget(self._make_help_button(net, c.type or "led"),
                          0, Qt.AlignmentFlag.AlignTop)
        group_lay.addLayout(ctx_row)

        # ⛔ AUCUNE pre-selection quand le detecteur n'est pas sur.
        # `_confidence == "low"` veut dire que `c.type` est un DEFAUT (toute
        # sortie numerique nue sort en « led »), pas une deduction : cocher
        # cette card ferait passer une ignorance pour une reponse, et
        # « Valider » serait actif au-dessus de questions auxquelles personne
        # n'a repondu. Depuis ce changement, la modale exige un choix par
        # broche -- c'est le sens meme d'une modale d'ambiguite.
        #
        # Deux cas gardent LEUR pre-selection, et ce sont de vraies
        # informations, pas des defauts :
        #   - `_chosen_type` deja rempli : le prompt a nomme le composant
        #     (`_prompt_suggested_type`), ou l'utilisateur a deja choisi et
        #     une reconstruction ne doit pas le lui reprendre ;
        #   - composant PAS `low` : c'est l'engrenage ouvert sur un composant
        #     lu dans le code, ou le type courant est ce qu'il faut montrer.
        precheck_type = self._chosen_type.get(c.ref)
        if precheck_type is None and c.attributes.get("_confidence") != "low":
            precheck_type = c.type

        # ── Picker de composants : recherche + cards ──────────────────────
        # MEMES candidats qu'avec la liste deroulante qu'il remplace
        # (`full_candidate_choices`, via `picker_logic`) : ce qui change est la
        # facon de choisir, pas ce qui est proposable. La card est celle de
        # l'onglet « Composants » — un composant ne se decrit pas autrement
        # selon l'ecran qui l'affiche.
        from .component_picker import ComponentPicker
        picker = ComponentPicker(c, lang_manager.lang)
        # `select("")` DESELECTIONNE. L'appel est inconditionnel a dessein :
        # le picker se pre-selectionne LUI-MEME sur `component.type` a la
        # construction (« jamais vierge »), ce qui reste juste partout
        # ailleurs mais pas ici -- sur une ambiguite, ce type est un defaut.
        # C'est l'appelant qui sait faire la difference, pas le picker.
        picker.select(precheck_type or "")
        # Enregistre AVANT l'entonnoir : `_update_ok_state` interroge les
        # pickers, et il doit voir celui-ci des le premier appel.
        self._pickers[c.ref] = picker
        # `select()` n'emet RIEN (c'est un ordre de la modale, pas un choix de
        # l'utilisateur) : l'entonnoir est donc appele a la main. Sans
        # pre-selection il n'y a rien a annoncer -- et surtout rien a poser
        # dans `_chosen_type`, dont l'absence est ce qui grise « Valider ».
        if precheck_type:
            self._on_type_toggled(c.ref, precheck_type)
        picker.type_chosen.connect(
            lambda tid, ref=c.ref: self._on_type_toggled(ref, tid))
        # Le rail suit le CLIC, pas le changement de selection. Depuis la
        # suppression de la pre-selection, un premier clic change toujours
        # quelque chose et `type_chosen` suffirait -- mais RE-cliquer la card
        # deja choisie n'emet rien, et ce geste doit rester un geste (il
        # reconfirme et fait avancer). Reste indispensable au chemin de
        # l'engrenage, ou le composant arrive bel et bien pre-selectionne sur
        # son type lu dans le code.
        picker.card_clicked.connect(
            lambda _tid, ref=c.ref: self._on_user_picked(ref))
        # Regle Q9 (heritee de LibChoiceDialog) : rien d'invisible n'est
        # validable. Sans ce branchement, « Valider » resterait actif au-dessus
        # d'un picker vide — masquer une card n'est pas un clic, et
        # `_update_ok_state` n'est appele que depuis les entonnoirs de choix.
        picker.selection_cleared.connect(self._update_ok_state)
        # Le crayon d'une card. Le picker a deja traduit : `custom:<id>` pour
        # une entree declaree, l'id nu de la fiche pour un composant cure.
        picker.edit_requested.connect(
            lambda tid, ref=c.ref: self._edit_component(ref, tid))
        group_lay.addWidget(picker)
        # « Créer un composant » est une ACTION, pas un candidat : dans la
        # liste elle se lisait comme un type de composant de plus, et il
        # fallait la trouver tout en bas d'une liste qui en compte des
        # dizaines. Un bouton sous le picker, comme dans l'onglet
        # « Composants » (QA G2, 2026-08-08).
        btn_declare = QPushButton(dialog_label("declare_tile",
                                               lang_manager.lang))
        btn_declare.setSizePolicy(QSizePolicy.Policy.Maximum,
                                  QSizePolicy.Policy.Fixed)
        btn_declare.setFixedHeight(40)
        btn_declare.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_declare.setAutoDefault(False)
        btn_declare.setDefault(False)
        # Le formulaire s'ouvre AU CLIC, pas à la validation de la modale :
        # « Créer un composant » est une action, et une action qui ne fait
        # rien de visible se lit comme une case à cocher (QA G2, 2026-08-08).
        # Bénéfice de bord : le choix devient un vrai type `custom:<slug>`
        # tout de suite, donc le sentinel DECLARE_OPTION_ID ne traverse plus
        # la modale — c'est lui qui, resté en place, transformait un composant
        # en LED au rechargement (revue 2026-07-30).
        btn_declare.clicked.connect(
            lambda _=False, ref=c.ref: self._declare_now(ref))
        self._declare_buttons[c.ref] = btn_declare
        declare_row = QHBoxLayout()
        declare_row.setContentsMargins(0, 0, 0, 0)
        declare_row.addWidget(btn_declare)
        declare_row.addStretch(1)
        group_lay.addLayout(declare_row)

        # In-line "Quel driver ?" sub-menu — visible if dc_motor selected.
        driver_frame = self._build_driver_subframe(c.ref)
        self._driver_frames[c.ref] = driver_frame
        driver_frame.setVisible(precheck_type == "dc_motor")
        group_lay.addWidget(driver_frame)

        return group

    def _build_lib_motors_section(self, motors: list) -> QGroupBox:
        """Les moteurs que le CODE nomme (bibliotheque de driver, niveau 1) :
        UNE section pour le lot, et une seule question — quelle carte pilote.

        ⛔ Pas de picker, pas de cases a decocher : « est-ce un moteur ? »
        est tranche par le code (`L298N motor(...)`), le requalifier en LED
        contredirait les appels de lib du sketch. Le driver COURANT est
        pre-selectionne — il a ete lu dans le code, c'est une certitude a
        corriger, pas une question ouverte. En changer passe par la
        REGENERATION (studio) : c'est le code qui nomme le driver, donc c'est
        le code qui doit changer — rien n'est ecrit dans les resolutions de
        cablage, leurs clefs etant degenerees pour ces moteurs (#86 (a)).
        """
        from .visual_ambiguity_catalog import dialog_label
        lang = lang_manager.lang
        group = QGroupBox(dialog_label("motors_detected_title", lang)
                          .format(k=len(motors)))
        lay = QVBoxLayout(group)
        lay.setSpacing(6)
        info = QLabel(dialog_label("lib_motors_question", lang))
        info.setWordWrap(True)
        info.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(info)
        courant = next((c.attributes.get("_chosen_driver")
                        for c in motors
                        if c.attributes.get("_chosen_driver")), "l298n")
        anchor = motors[0].ref
        refs = [c.ref for c in motors]

        def _choisir(dt, _refs=tuple(refs), _anchor=anchor):
            for r in _refs:
                self._chosen_driver[r] = dt
            self._on_user_picked(_anchor)
            self._update_ok_state()

        lay.addLayout(self._build_driver_grid(anchor, _choisir))
        cards = self._driver_cards[anchor]
        if courant in cards:
            cards[courant].set_selected(True)
        for c in motors:
            self._chosen_type[c.ref] = "dc_motor"
            self._chosen_driver[c.ref] = courant
        # Le driver courant est une CERTITUDE lue dans le code, pas une
        # question ouverte : la ligne du rail nait cochee et « Valider » est
        # actif d'emblee — meme regle que la pre-selection de la section
        # stepper.
        self._mark_decided(anchor)
        return group

    def _build_stepper_driver_section(self, c: Component) -> QGroupBox:
        """L'engrenage d'un driver pas-a-pas : ses 4 variantes, en cards.

        ⛔ **Pas de picker de composants ici.** Un driver n'est pas
        remplacable par une LED : `is_replaceable` rend False pour les quatre
        (regle du #62, l'utilisateur n'a pas choisi l'infrastructure). Ce
        qu'on lui propose est le choix qu'il a REELLEMENT a faire -- quelle
        variante il tient dans la main -- et rien d'autre.

        Le type courant EST pre-selectionne, contrairement a une ambiguite :
        il a ete lu dans le code (`#include`), ce n'est pas un defaut. Montrer
        une grille vierge ferait passer une certitude pour une question.
        """
        from .visual_ambiguity_catalog import dialog_label
        lang = lang_manager.lang
        group = QGroupBox(_type_label(c.type, lang))
        lay = QVBoxLayout(group)
        lay.setSpacing(6)
        info = QLabel(dialog_label("stepper_driver_question", lang))
        info.setWordWrap(True)
        info.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(info)
        lay.addLayout(self._build_driver_grid(
            c.ref,
            lambda dt, ref=c.ref: self._on_stepper_driver_picked(ref, dt),
            drivers=list(STEPPER_DRIVERS)))
        # ⚠️ Le choix DEJA fait prime sur le type detecte. `initial_choices`
        # (rempli avant `_build`) porte ce que l'utilisateur a tranche ; sans
        # cette lecture, rouvrir l'engrenage sur un driver qu'on venait de
        # remplacer reaffichait l'ANCIEN coche -- le schema disait DRV8825, la
        # modale disait A4988 (mesure de revue, 2026-08-29).
        courant = self._chosen_type.get(c.ref) or c.type
        cards = self._driver_cards[c.ref]
        if courant in cards:
            cards[courant].set_selected(True)
        self._chosen_type[c.ref] = courant
        return group

    def _on_stepper_driver_picked(self, ref: str, d_type: str) -> None:
        """Le choix passe par `_chosen_type`, comme toute autre decision.

        C'est ce qui le fait remonter au rail, a << Valider >> et a
        `apply_choices` sans une seconde plomberie -- une decision de plus,
        pas un mecanisme de plus."""
        self._chosen_type[ref] = d_type
        self._on_user_picked(ref)
        self._update_ok_state()

    def _build_consolidated_motors_section(
            self, motors: list[Component]) -> QGroupBox:
        """Consolidated section: N candidate DC motors (>=2) grouped into
        a SINGLE UI with Oui / Garder une partie / Non choices + 1 shared
        driver sub-menu. Solves the visual overload problem when the
        user has 2+ motors.

        The title/description list ALL the originally detected motors
        (= `_original_groupings`), not only the currently grouped ones.
        Otherwise in partial mode with a few motors ungrouped, the user
        would lose track of the unchecked motors that they could re-check
        to undo their choice. The refs passed to the callbacks are, on
        the other hand, the STILL-GROUPED refs (= what the shared driver
        applies to at click time).
        """
        # K = original number of detected motors (stable across
        # rebuilds). `motors` = those STILL grouped now (can be
        # 0, 1 or K in partial mode).
        from .visual_ambiguity_catalog import dialog_label
        lang = lang_manager.lang
        k = len(self._original_groupings)
        title = dialog_label("motors_detected_title", lang).format(k=k)
        group = QGroupBox(title)
        group_lay = QVBoxLayout(group)
        group_lay.setSpacing(6)

        # '?' at the top right, like the two other sections. The payload is
        # EVERY pin of EVERY original grouping (PWM + directions): the
        # question spans the whole family, so answering it for a single pin
        # would answer the wrong question.
        all_pins: list[str] = []
        for g in self._original_groupings:
            all_pins.extend([g["pwm"], *g["dirs"]])
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.addStretch(1)
        header_row.addWidget(self._make_motor_help_button(all_pins))
        group_lay.addLayout(header_row)

        # Short intro: the per-motor detail (PWM + dir pins) is repeated
        # by each block of the partial subframe below, no need to
        # list it twice.
        desc = QLabel(dialog_label("motors_groups_desc", lang))
        desc.setWordWrap(True)
        desc.setTextFormat(Qt.TextFormat.RichText)
        group_lay.addWidget(desc)

        # Currently grouped refs -- used by the shared driver. Recomputed
        # on each rebuild (may differ from [m.ref for m in motors] if
        # `motors` captures invalid refs after mutation, but in
        # practice they are equivalent since motors is filtered in
        # _build).
        currently_grouped_refs = [m.ref for m in motors]

        # Per-motor checkboxes (1 row = 2 cb: Moteur + Cabler) always
        # visible. No more Oui/Garder une partie/Non radios since 2026-05-26:
        # the 2-checkbox-per-row UI covers all cases
        # equivalently (all checked = "Oui", some checked = "Garder une
        # partie", none checked = "Non"). Simpler, less redundancy.
        partial_frame = self._build_partial_checkboxes_subframe()
        self._partial_checkboxes_frame = partial_frame
        group_lay.addWidget(partial_frame)

        # Shared driver picker, always visible when at least 1 motor
        # is still grouped (otherwise it would apply to 0 refs, with no effect).
        if currently_grouped_refs:
            driver_frame = self._build_shared_driver_subframe(
                currently_grouped_refs)
            self._driver_frames["__consolidated__"] = driver_frame
            group_lay.addWidget(driver_frame)

        # Implicit promotion: every still-grouped motor is confirmed
        # as dc_motor (which was previously imposed by the Oui /
        # Garder une partie radio). If the user unchecks 'Moteur' on a row,
        # that row leaves currently_grouped_refs on the next rebuild
        # and its ref disappears from _chosen_type via _chosen_type.pop()
        # in _ungroup_motor_no_rebuild.
        for r in currently_grouped_refs:
            self._chosen_type[r] = "dc_motor"

        return group

    def _build_partial_checkboxes_subframe(self) -> QFrame:
        """Sub-frame of the consolidated section. 1 BLOCK per originally
        detected motor, each block contains:

        - A label "Moteur supposé N : broche X (PWM) + broches Y, Z"
        - Checkbox "C'est bien un moteur" (pre-checked): declares the nature
          of the group. Unchecking ungroups the pins into individual
          ambiguities (LED/BTN/other to reclassify in the classic section)
          BUT keeps the block visible to allow re-correction. Auto-greys the
          2nd checkbox.
        - Checkbox "Câbler le moteur" (pre-checked if in
          `_currently_kept_pwms`): inclusion in the schema. Subject to the
          `motors_limit` limit. Greyed out as long as 'C'est bien un moteur'
          is unchecked.

        Vertical layout (label + 2 stacked cb) rather than side-by-side
        to improve readability when there are 2+ motors.
        """
        from PyQt6.QtWidgets import QCheckBox, QHBoxLayout
        from .visual_ambiguity_catalog import dialog_label
        lang = lang_manager.lang
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 6, 0, 6)
        layout.setSpacing(10)

        def _short(net: str) -> str:
            return net[1:] if net.startswith("D") and net[1:].isdigit() else net

        for i, grp in enumerate(self._original_groupings, start=1):
            pwm = grp["pwm"]
            dirs = grp["dirs"]
            dir_short = ", ".join(_short(p) for p in dirs)
            is_motor = pwm in self._motor_declared_real

            block = QVBoxLayout()
            block.setContentsMargins(0, 0, 0, 0)
            block.setSpacing(2)

            # Label "Assumed motor N: ..."
            label = QLabel(dialog_label("assumed_motor_label", lang).format(
                i=i, pwm=_short(pwm), dirs=dir_short))
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setWordWrap(True)
            block.addWidget(label)

            # Checkbox 'C'est bien un moteur' (indented).
            cb_motor = QCheckBox(dialog_label("motor_confirm_checkbox", lang))
            cb_motor.setChecked(is_motor)
            cb_motor.setToolTip(dialog_label("motor_confirm_tooltip", lang))
            cb_motor.toggled.connect(
                lambda checked, p=pwm:
                    self._toggle_motor_declared(p, is_motor=checked)
            )
            row_motor = QHBoxLayout()
            row_motor.setContentsMargins(20, 0, 0, 0)
            row_motor.addWidget(cb_motor)
            row_motor.addStretch(1)
            block.addLayout(row_motor)

            # Checkbox 'Wire the motor' (indented, greyed out if non-motor).
            cb_wire = QCheckBox(dialog_label("wire_motor_checkbox", lang))
            cb_wire.setChecked(pwm in self._currently_kept_pwms)
            cb_wire.setEnabled(is_motor)
            cb_wire.toggled.connect(
                lambda checked, p=pwm:
                    self._toggle_motor_grouping(p, keep=checked)
            )
            row_wire = QHBoxLayout()
            row_wire.setContentsMargins(20, 0, 0, 0)
            row_wire.addWidget(cb_wire)
            row_wire.addStretch(1)
            block.addLayout(row_wire)

            block_wrap = QFrame()
            block_wrap.setLayout(block)
            layout.addWidget(block_wrap)

        return frame

    def _component_infos(self) -> dict:
        """Fiches de la bibliotheque indexees par cle, memoisees PAR LANGUE.

        `build_index` relit le cache de lookups sur le DISQUE : l'appeler a
        chaque reconstruction de section (une case a cocher de moteur en
        declenche une, et il y a une section par composant) paierait ce
        disque N fois pour un resultat identique. La memoisation est indexee
        par langue parce que les noms en dependent.
        """
        lang = lang_manager.lang
        cached = self._infos_by_key.get(lang)
        if cached is None:
            from ..component_index import build_index
            cached = {i.key: i for i in build_index(lang)}
            self._infos_by_key[lang] = cached
        return cached

    def _driver_card(self, d_type: str):
        """Une card de driver : la fiche de la bibliotheque si elle existe,
        sinon un repli qui n'affiche que le nom.

        ⚠️ MESURE le 2026-08-13 : les CINQ drivers de `_DC_DRIVERS` ont une
        fiche, donc le repli ne sert jamais pour eux — il est defensif (une
        entree retiree du registre un jour, un driver ajoute avant sa fiche).
        Ce qui distingue les deux L293D est donc le NOM DE LA FICHE (« driver
        L293D (module) » contre « driver L293D », traduits tous les deux) plus
        le nombre de broches affiche par la card (13 contre 16), et non plus
        `_driver_label` et ses qualificatifs « module breakout » / « DIP nu ».
        Garde : `test_ambiguity_i18n.
        test_driver_card_labels_tell_the_two_l293d_apart_in_each_language`."""
        from .ambiguity_cards import ComponentCard
        info = self._component_infos().get(d_type)
        if info is not None:
            return ComponentCard(info)
        return ComponentCard.fallback(d_type,
                                      _driver_label(d_type, lang_manager.lang))

    def _build_driver_grid(self, key: str, on_pick,
                          drivers: list[str] | None = None) -> QGridLayout:
        """Des drivers en cards, 2 colonnes, exclusivite arbitree ici.

        `drivers` vaut les 5 drivers DC par defaut ; les moteurs pas-a-pas
        passent les leurs (`STEPPER_DRIVERS`). Deux grilles ecrites deux fois
        auraient diverge sur l'exclusivite et le crayon -- c'est la LISTE qui
        change, pas le comportement.

        Une card ne connait pas ses soeurs (meme contrat que dans le picker) :
        c'est la modale qui eteint les autres. `key` indexe le lot de cards
        (une ref de composant, ou `__consolidated__` pour le driver partage)."""
        grid = QGridLayout()
        grid.setSpacing(8)
        cards: dict[str, object] = {}
        for pos, d_type in enumerate(drivers or _DC_DRIVERS):
            card = self._driver_card(d_type)
            card.picked.connect(
                lambda _card, k=key, dt=d_type:
                    self._on_driver_card(k, dt, on_pick))
            # Le crayon de la card : meme porte que partout ailleurs. `ref=None`
            # parce qu'un driver n'est PAS le composant qu'on est en train
            # d'identifier — reprendre le L298N a son compte corrige sa
            # librairie, ca ne requalifie pas la broche. Sans ce branchement, le
            # crayon serait un bouton mort, ce que la card ne doit jamais etre.
            card.edit_requested.connect(
                lambda _key, dt=d_type: self._edit_component(None, dt))
            cards[d_type] = card
            grid.addWidget(card, pos // 2, pos % 2)
        self._driver_cards[key] = cards
        return grid

    def _on_driver_card(self, key: str, d_type: str, on_pick) -> None:
        """Clic sur une card de driver : exclusivite puis enregistrement."""
        for dt, card in self._driver_cards.get(key, {}).items():
            card.set_selected(dt == d_type)
        on_pick(d_type)

    def _build_shared_driver_subframe(self, refs: list[str]) -> QFrame:
        """Shared driver sub-menu: 1 choice applied simultaneously to
        all the refs in the list. Pre-checks with priority the driver
        already chosen for one of the refs (= persists a user choice across
        rebuilds), otherwise the suggested_dc_driver from phase A if
        provided. Hidden by default, shown when 'Oui' / 'Partial'."""
        from .visual_ambiguity_catalog import dialog_label
        lang = lang_manager.lang
        driver_frame = QFrame()
        driver_lay = QVBoxLayout(driver_frame)
        driver_lay.setContentsMargins(28, 4, 0, 4)
        driver_lay.setSpacing(6)
        driver_lay.addWidget(QLabel(
            f"<i>{dialog_label('driver_question_shared', lang)}</i>"))
        key = "__consolidated__"
        driver_lay.addLayout(self._build_driver_grid(
            key, lambda dt, rs=list(refs): self._on_shared_driver_toggled(rs,
                                                                         dt)))
        # Pre-check: existing _chosen_driver for a dominant ref, otherwise
        # suggested_dc_driver from phase A. Gives priority to the user choice.
        already_chosen = None
        for r in refs:
            if r in self._chosen_driver:
                already_chosen = self._chosen_driver[r]
                break
        precheck_driver = already_chosen or self._suggested_dc_driver
        cards = self._driver_cards[key]
        if precheck_driver is not None and precheck_driver in cards:
            cards[precheck_driver].set_selected(True)
            for r in refs:
                self._chosen_driver[r] = precheck_driver
        return driver_frame

    def _on_shared_driver_toggled(
            self, refs: list[str], driver_type: str) -> None:
        """Driver card callback in the consolidated section: applies
        the choice to all the refs simultaneously."""
        for r in refs:
            self._chosen_driver[r] = driver_type
            self._mark_decided(r)
        self._update_ok_state()
        self._refresh_rail()

    def _mark_decided(self, ref: str) -> None:
        """Note que ce composant a ete TRANCHE, du bon cote.

        Deux etats derriere une meme idee : une broche se marque dans
        `_decided`, un moteur groupe dans `_motors_decided` — le rail ne lui
        donne pas de ligne a lui, il vit dans la section consolidee. Router
        cela au petit bonheur est ce qui a fait deux fois mentir le rail.

        Sans ça, la ligne du rail restait grise et « proposé » alors que
        l'utilisateur venait de fournir la dernière information qui manquait :
        « Valider » s'activait sous ses yeux sans que le rail bouge (relevé en
        QA X4, 2026-08-29). Un pilote appartient à la décision « moteurs » —
        ce n'est pas une case à part.
        """
        comp = next((c for c in self._ambiguous if c.ref == ref), None)
        if comp is not None and comp.attributes.get("_grouped_pwm_pin"):
            self._motors_decided = True
        else:
            self._decided.add(ref)

    def _build_driver_subframe(self, ref: str) -> QFrame:
        """In-line "Quel driver ?" sub-menu, the 5 DC drivers in cards —
        meme facture que les composants juste au-dessus.
        Visible only when the main type is dc_motor.
        Pre-checks with priority the persisted _chosen_driver[ref] (after
        rebuild), otherwise the suggested_dc_driver (Phase A) if provided."""
        from .visual_ambiguity_catalog import dialog_label
        lang = lang_manager.lang
        driver_frame = QFrame()
        driver_lay = QVBoxLayout(driver_frame)
        driver_lay.setContentsMargins(28, 4, 0, 4)
        driver_lay.setSpacing(6)
        driver_lay.addWidget(QLabel(
            f"<i>{dialog_label('driver_question', lang)}</i>"))
        driver_lay.addLayout(self._build_driver_grid(
            ref, lambda dt, r=ref: self._on_driver_toggled(r, dt)))
        precheck_driver = (self._chosen_driver.get(ref)
                           or self._suggested_dc_driver)
        cards = self._driver_cards[ref]
        if precheck_driver is not None and precheck_driver in cards:
            cards[precheck_driver].set_selected(True)
            self._chosen_driver[ref] = precheck_driver
        driver_frame.setVisible(False)
        return driver_frame

    def _on_type_toggled(self, ref: str, type_id: str) -> None:
        """Main type choice funnel: records the choice, shows
        the driver sub-menu if type==dc_motor, hides it otherwise.

        Idempotent : il est appele par la pre-selection d'une section, par un
        clic sur une card, et par le picker lui-meme quand une recherche
        effacee redonne a voir un choix deja fait."""
        self._chosen_type[ref] = type_id
        frame = self._driver_frames.get(ref)
        if frame is not None:
            frame.setVisible(type_id == "dc_motor")
        self._update_ok_state()

    def _edit_component(self, ref: str | None, type_id: str) -> None:
        """Crayon d'une card. Deux chemins, exactement comme l'onglet.

        `custom:<id>` -> corriger MON entree. Autre chose -> l'ADOPTER :
        modifier un composant qu'on n'a pas decrit soi-meme, c'est le
        REPRENDRE A SON COMPTE (QA I4), et le formulaire s'ouvre pre-rempli
        avec ce que l'app sait de lui.

        Le crayon n'est plus grise sur un composant cure : chaque card porte le
        sien, et il agit sur ELLE, plus sur « le choix courant ».

        `ref=None` : la card n'appartient a aucun composant a requalifier — le
        sous-menu « Quel driver ? » est fait des memes cards. Le formulaire
        s'ouvre pareil (corriger la librairie du L298N reste utile), mais rien
        n'est re-selectionne : le driver n'est pas ce qu'on identifie ici, et
        poser son type sur le composant le transformerait EN driver.
        """
        if str(type_id).startswith(TYPE_PREFIX):
            self._edit_declared(ref, type_id)
        else:
            self._adopt_component(ref, type_id)

    def _adopt_component(self, ref: str | None, key: str) -> None:
        """Reprendre a son compte un composant qu'on n'a pas declare.

        Meme brouillon que la fiche de l'onglet « Composants »
        (`declared_components.adoptable_entry`) : nom, librairie retenue, et
        brochage du catalogue quand il y en a un — jamais une broche inventee.

        Sans brouillon (les echappatoires `module_generic`, `uart_module` :
        des types, pas des composants — aucune fiche a reprendre), on ouvre le
        formulaire vierge pre-rempli par le COMPOSANT, comme « Creer un
        composant ». Un crayon muet se lirait comme une panne.
        """
        from ..declared_components import adoptable_entry
        draft = adoptable_entry(key, lang_manager.lang)
        if draft is None:
            if ref is not None:
                self._declare_now(ref)
            return
        from .declare_component_dialog import (DeclareComponentDialog,
                                               resolve_board_nets)
        # Capture AVANT d'ouvrir (meme raison que dans `_edit_declared`).
        old_lib = getattr(draft, "lib", "") or ""
        dlg = DeclareComponentDialog(
            self, component=None, existing=draft,
            board_nets=resolve_board_nets(), lang=lang_manager.lang)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        saved = getattr(dlg, "result_component", None)
        if saved is None:
            return
        self.lib_changed_in_form.emit(old_lib, saved)
        self._select_declared(ref, saved.type_id)

    def _edit_declared(self, ref: str | None, type_id: str) -> None:
        """Rouvre le formulaire sur l'entrée déclarée que la card désigne.

        Même entrée que le crayon des tuiles Débutant et que celui de la fiche
        de l'onglet « Composants » : les trois portes mènent au même endroit,
        sinon corriger une déclaration dépendrait du mode où l'on se trouve.
        """
        if not type_id or not str(type_id).startswith(TYPE_PREFIX):
            return
        from ..declared_components import find_by_type
        entry = find_by_type(type_id)
        if entry is None:
            return
        from .declare_component_dialog import (DeclareComponentDialog,
                                               resolve_board_nets)
        # Capture AVANT d'ouvrir : apres acceptation, l'entree porte deja la
        # nouvelle librairie et l'ancienne est perdue (TODO #52).
        old_lib = getattr(entry, "lib", "") or ""
        dlg = DeclareComponentDialog(
            self, component=None, existing=entry,
            board_nets=resolve_board_nets(), lang=lang_manager.lang)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if getattr(dlg, "removed", False):
            self._forget_declared_type(
                ref, getattr(dlg, "removed_type_id", type_id))
            return
        updated = getattr(dlg, "result_component", None)
        if updated is None:
            return
        # Cette modale n'a AUCUN accès au Studio : elle le prévient par signal.
        # Sans ça, changer la librairie depuis ce crayon-là modifiait bien
        # `components.json` mais ne proposait ni régénération ni avertissement
        # `lib_swap_unchecked` — le code continuait de référencer l'ancienne
        # librairie en silence (TODO #52, signalé à l'écran le 2026-08-12).
        # L'émission est inconditionnelle ; c'est `StudioView` qui décide de se
        # taire quand la librairie n'a pas bougé, pour que la règle vive à un
        # seul endroit et non dans chaque porte.
        self.lib_changed_in_form.emit(old_lib, updated)
        self._select_declared(ref, updated.type_id)

    def _select_declared(self, ref: str | None, type_id: str) -> None:
        """Montrer et choisir le composant qui vient d'être enregistré.

        `ref=None` (crayon d'une card de DRIVER) : rien à sélectionner — cf.
        `_edit_component`.

        Trois gestes, dans cet ordre, et aucun n'est décoratif :

        - **vider la recherche** : un filtre encore en place peut masquer le
          type qu'on vient d'enregistrer, et un choix masqué n'est pas
          validable (règle Q9) — « Valider » serait grisé juste après un
          enregistrement réussi ;
        - **`refresh_index()`** : sans lui, la fiche fraîche s'affiche en card
          de REPLI (nom seul, ni bibliothèque, ni description, ni pastille
          « Perso ») à côté de ses voisines complètes ;
        - **`_on_type_toggled` EN DERNIER** : `select()` est silencieux, donc
          c'est lui qui enregistre le choix — et il appelle `_update_ok_state`,
          qui interroge le picker. L'appeler avant laisserait « Valider » grisé
          sur une sélection pourtant faite.
        """
        if ref is None:
            return
        picker = self._pickers.get(ref)
        if picker is not None:
            picker.set_query("")
            picker.refresh_index()
            picker.select(type_id)
        self._on_type_toggled(ref, type_id)

    def _forget_declared_type(self, ref: str | None, type_id: str) -> None:
        """L'entrée déclarée vient d'être RETIRÉE de la bibliothèque : le
        picker ne doit plus l'offrir, et le choix courant doit revenir sur un
        type qui existe encore.

        `_on_remove` supprimait bien l'entrée du disque, mais l'écran n'en
        rendait pas compte : la liste continuait de proposer le type `custom:`
        disparu, et le choisir ne faisait plus RIEN (`_apply_declared` →
        `find_by_type` → None → « on laisse la boîte telle quelle »). Le
        drapeau `removed` existait exactement pour ça et n'était lu nulle part
        — deux occurrences dans tout le dépôt, l'initialisation et l'écriture
        (QA 2026-08-10).

        Repli sur la PREMIÈRE card : `full_candidate_choices` commence par le
        type que le détecteur avait proposé, et le picker garde cet ordre —
        c'est donc l'état d'avant la déclaration, le plus honnête et le seul
        qu'on sache reconstruire.
        """
        picker = self._pickers.get(ref)
        if picker is None:
            return
        # La recherche d'abord : le repli doit être choisi parmi TOUT ce qui
        # est proposable, pas parmi ce qu'un filtre laissait voir.
        picker.set_query("")
        picker.refresh_index()
        ids = picker.visible_type_ids()
        if not ids:
            return
        picker.select(ids[0])
        # Appel explicite : `select()` n'émet rien. `_on_type_toggled` est
        # idempotent.
        self._on_type_toggled(ref, ids[0])

    def _declare_now(self, ref: str) -> None:
        """Ouvre le formulaire de déclaration pour `ref`, séance tenante.

        Annuler ne change RIEN (même contrat qu'à la validation). Enregistrer
        ajoute le composant aux candidats et le sélectionne : le choix est
        alors un type réel, pas un marqueur à résoudre plus tard.
        """
        comp = next((c for c in self._ambiguous if c.ref == ref), None)
        if comp is None:
            return
        from .declare_component_dialog import (DeclareComponentDialog,
                                               resolve_board_nets)
        dlg = DeclareComponentDialog(
            self, component=comp, board_nets=resolve_board_nets(),
            lang=lang_manager.lang)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if getattr(dlg, "removed", False):
            # Le formulaire ouvert sur un placeholder retrouve son entrée par
            # en-tête (`entry_for_header`) : « Retirer » est donc atteignable
            # depuis CETTE porte aussi, pas seulement depuis le crayon.
            self._forget_declared_type(ref,
                                       getattr(dlg, "removed_type_id", ""))
            return
        decl = getattr(dlg, "result_component", None)
        if decl is None:
            return
        self._select_declared(ref, decl.type_id)

    def _on_ungroup_requested(self, ref: str) -> None:
        """Callback "Non, c'est autre chose" on a DC motor grouping:
        undoes the grouping by recreating N separate ambiguous components
        (1 per pin of the group), then rebuilds the dialog. The direction
        pins become classic ambiguous LEDs that the user can handle
        one by one with the 4 standard radios."""
        target = next((c for c in self._ambiguous if c.ref == ref), None)
        if target is None or "_grouped_pwm_pin" not in target.attributes:
            return
        self._ungroup_motor_no_rebuild(target)
        # Rebuild of the dialog: the choices already made by the user on the
        # other components are lost (the radios are recreated), that's
        # the tradeoff for a simple UI. In practice the ungrouping
        # happens on the first click, before any other choice.
        self._build()
        self._update_ok_state()

    def _ungroup_motor_no_rebuild(self, target: Component) -> None:
        """Mutate the netlist: remove the _grouped_* flags from `target` and
        recreate N-1 ambiguous LEDs for the direction pins. Idempotent
        (no-op if already ungrouped). No rebuild -- caller must call
        _build() after if needed.

        Also cleans up _chosen_type/_chosen_driver for target: the PWM
        becomes a classic ambiguous LED, the user must re-choose a
        type (otherwise the post-rebuild classic section would have dc_motor
        internally but no radio visually checked)."""
        if "_grouped_pwm_pin" not in target.attributes:
            return
        dir_pins = target.attributes.pop("_grouped_dir_pins")
        target.attributes.pop("_grouped_pwm_pin")
        target.attributes["_confidence"] = "low"
        self._chosen_type.pop(target.ref, None)
        self._chosen_driver.pop(target.ref, None)
        # `_decided` suit `_chosen_type` : le choix vient d'etre efface, le
        # rail ne doit plus annoncer cette ligne comme confirmee.
        self._decided.discard(target.ref)
        # `target` stays as-is (ambiguous LED on the PWM pin), it has just
        # lost its grouping flags -> it will be shown in the classic section
        # on the next rebuild.

        # Create N-1 ambiguous LEDs for the direction pins, avoiding
        # duplicates if a LED already exists on the same pin (idempotence
        # after repeated uncheck/check on the same motor).
        idx = self._ambiguous.index(target)
        for offset, dir_pin in enumerate(dir_pins, start=1):
            existing = next(
                (c for c in self._ambiguous
                 if c.pin("A") is not None and c.pin("A").net == dir_pin),
                None,
            )
            if existing is not None:
                continue
            if self._netlist is not None:
                ref_new = self._netlist.next_ref("D")
            else:
                ref_new = f"{target.ref}_grp_{dir_pin}"
            led = Component(
                ref=ref_new, type="led", fn_id=target.fn_id,
                pins=[Pin("A", dir_pin), Pin("K", "GND")],
                attributes={"_confidence": "low"},
                inferred=True,
            )
            self._ambiguous.insert(idx + offset, led)
            if self._netlist is not None:
                self._netlist.add_component(led)

    def _regroup_motor_no_rebuild(self, pwm_pin: str) -> None:
        """Inverse of _ungroup_motor_no_rebuild: restore the grouping
        of a previously ungrouped motor. Look for the ambiguous LED on
        the PWM pin + the ambiguous LEDs on each (original) dir pin and
        merge: put back the _grouped_* flags on the PWM, delete the
        dir pin LEDs from _ambiguous and from the netlist. Idempotent."""
        orig = next(
            (g for g in self._original_groupings if g["pwm"] == pwm_pin),
            None,
        )
        if orig is None:
            return
        dirs = orig["dirs"]
        # Find the PWM LED in _ambiguous by REF (stable). The lookup
        # by `pin("A").net == pwm_pin` doesn't work: if inference has
        # inserted a bridge (NET_X) between pin A and the Arduino pin (LED
        # series R case), pin A points to NET_X and the comparison
        # fails silently.
        ref = orig.get("ref")
        pwm_led = next(
            (c for c in self._ambiguous if c.ref == ref),
            None,
        ) if ref else None
        if pwm_led is None:
            return  # PWM gone (user already converted it -> no-op)
        # Already grouped -> nothing to do.
        if pwm_led.attributes.get("_grouped_pwm_pin") == pwm_pin:
            return
        # Restore the grouped flags.
        pwm_led.attributes["_grouped_pwm_pin"] = pwm_pin
        pwm_led.attributes["_grouped_dir_pins"] = list(dirs)
        pwm_led.attributes["_confidence"] = "low"
        pwm_led.type = "led"
        # The user may have classified the PWM in the classic section
        # after uncheck -> remove their choice now that it returns
        # to grouped status.
        self._chosen_type.pop(pwm_led.ref, None)
        self._chosen_driver.pop(pwm_led.ref, None)
        self._decided.discard(pwm_led.ref)
        # Delete the ambiguous LEDs on the dir pins (which appeared during
        # the previous ungroup).
        for dir_pin in dirs:
            dir_led = next(
                (c for c in self._ambiguous
                 if c.pin("A") is not None and c.pin("A").net == dir_pin),
                None,
            )
            if dir_led is None:
                continue
            self._ambiguous.remove(dir_led)
            if self._netlist is not None:
                try:
                    self._netlist.components.remove(dir_led)
                except ValueError:
                    pass
            self._chosen_type.pop(dir_led.ref, None)
            self._chosen_driver.pop(dir_led.ref, None)
            self._decided.discard(dir_led.ref)

    def _toggle_motor_grouping(self, pwm_pin: str, keep: bool) -> None:
        """Toggle 'to wire / not to wire' of a motor in the 'Garder
        une partie' mode. The motor stays GROUPED as dc_motor in all
        cases -- only the _currently_kept_pwms flag changes, which determines
        whether apply_choices will mark _skip_wiring=True (unchecked) or not (checked).

        To switch to 'pas un moteur en fait' mode (= ungroup into
        ambiguous components), the user goes through the dedicated button of the
        checkbox subframe, not through this method.

        If `motors_limit` is active and we would try to exceed the
        limit, we refuse -- the checkbox is reset to False on the next
        rebuild. A non-blocking toast signals the limit."""
        self._motors_decided = True
        if keep:
            if (self._motors_limit is not None
                    and pwm_pin not in self._currently_kept_pwms
                    and len(self._currently_kept_pwms)
                        >= self._motors_limit):
                # Refusal: too many motors checked. We don't mutate the state,
                # we rebuild so the checkbox goes back to False.
                self._show_limit_toast()
                self._build()
                self._update_ok_state()
                return
            self._currently_kept_pwms.add(pwm_pin)
        else:
            self._currently_kept_pwms.discard(pwm_pin)
        self._build()
        self._update_ok_state()

    def _toggle_motor_declared(self, pwm_pin: str, is_motor: bool) -> None:
        """Toggle 'Moteur' checkbox of the partial subframe (nature
        declaration). Bidirectional:

        - Uncheck (is_motor=False): ungroups the motor into individual
          ambiguous LEDs (dir pins reclassified one by one in the
          classic section). The row stays visible in the partial subframe
          to allow re-correction. Also removes from
          `_currently_kept_pwms` (a non-motor can't be wired).
        - Re-check (is_motor=True): restores the grouping (deletes
          the individual LEDs created during the previous uncheck).

        Distinct from `_toggle_motor_grouping` which touches ONLY
        `_currently_kept_pwms` (= wire yes/no).
        """
        self._motors_decided = True
        if is_motor:
            self._motor_declared_real.add(pwm_pin)
            self._regroup_motor_no_rebuild(pwm_pin)
            # Recocher « c'est un moteur » doit rendre l'etat d'AVANT le
            # decochage, cablage compris : celui-ci l'avait retire de
            # `_currently_kept_pwms` (un non-moteur ne se cable pas) et rien
            # ne l'y remettait. L'annulation etait donc a MOITIE faite — le
            # moteur revenait reconnu mais silencieusement absent du schema.
            if (self._motors_limit is None
                    or len(self._currently_kept_pwms) < self._motors_limit):
                self._currently_kept_pwms.add(pwm_pin)
        else:
            self._motor_declared_real.discard(pwm_pin)
            target = next(
                (c for c in self._ambiguous
                  if c.attributes.get("_grouped_pwm_pin") == pwm_pin),
                None,
            )
            if target is not None:
                self._ungroup_motor_no_rebuild(target)
            self._currently_kept_pwms.discard(pwm_pin)
        self._build()
        self._update_ok_state()

    def _show_limit_toast(self) -> None:
        """Non-blocking tooltip centered on the modal, showing the limit
        reached. Disappears after ~2s. Uses QToolTip rather than a
        QMessageBox to stay non-modal and discreet -- the user understands
        immediately and the main modal stays interactive."""
        from PyQt6.QtCore import QPoint
        from PyQt6.QtWidgets import QToolTip
        from .visual_ambiguity_catalog import dialog_label
        msg = dialog_label("motors_limit_toast", lang_manager.lang).format(
            limit=self._motors_limit)
        # Position: center of the modal, a bit below the top to avoid
        # the title bar. mapToGlobal to switch to screen coords.
        center = self.rect().center()
        pos = self.mapToGlobal(QPoint(center.x() - 150, 80))
        QToolTip.showText(pos, msg, self)

    def _on_driver_toggled(self, ref: str, driver_type: str) -> None:
        """DC driver radio callback."""
        self._chosen_driver[ref] = driver_type
        self._mark_decided(ref)
        self._update_ok_state()
        self._refresh_rail()

    def _update_ok_state(self) -> None:
        """Enable the OK button only when each component has a
        chosen type AND, if dc_motor, a chosen driver.

        Special case: a component still grouped as motor (with
        `_grouped_pwm_pin`) automatically counts as a confirmed dc_motor
        even without an explicitly checked radio -- the mere presence in the
        partial list implies 'it's a motor'. The driver remains required
        ONLY for the motors to wire (= in _currently_kept_pwms);
        the non-wired motors don't need a driver since they
        leave the netlist before inference."""
        if not hasattr(self, "_buttons"):
            return
        ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setEnabled(
            all(self._is_complete(c) for c in self._ambiguous))

    def _is_complete(self, c: Component) -> bool:
        """Ce composant a-t-il tout ce qu'il faut pour être appliqué ?

        ⚠️ **Point de vérité UNIQUE**, et il l'est devenu sur un défaut réel :
        le rail affichait ✓ sur « N moteurs DC » dès que l'utilisateur touchait
        une case, alors que le PILOTE pouvait manquer. « Valider » restait donc
        gris pendant que le rail annonçait tout réglé — et rien à l'écran ne
        disait où était le manque (relevé en QA X4, 2026-08-29). Deux
        réponses à la même question ne doivent pas exister.
        """
        # Règle Q9 : rien d'invisible n'est validable. Une recherche qui
        # masque la card choisie ramène le picker à « aucune sélection
        # effective » — le souvenir du choix, lui, survit dans
        # `_chosen_type` (effacer la recherche le rend à nouveau
        # validable : l'utilisateur n'a rien annulé).
        picker = self._pickers.get(c.ref)
        if picker is not None and picker.current_type_id() is None:
            return False
        tid = self._chosen_type.get(c.ref)
        grouped_pwm = c.attributes.get("_grouped_pwm_pin")
        # Promotion implicite : groupé = moteur DC confirmé.
        if tid is None and grouped_pwm is not None:
            tid = "dc_motor"
        if tid is None:
            return False
        # Le pilote n'est exigé que des moteurs À CÂBLER : les autres quittent
        # la netlist avant l'inférence.
        if tid == "dc_motor":
            will_be_wired = (
                grouped_pwm is None
                or grouped_pwm in self._currently_kept_pwms
            )
            if will_be_wired and c.ref not in self._chosen_driver:
                return False
        return True

    def apply_choices(self, netlist: Netlist) -> None:
        """Mutate the netlist: apply each transform to its component.
        The netlist is passed to the transform so it can remove
        orphan companions (e.g. the series R of a reclassified LED).
        For dc_motor, also passes the chosen driver_type.

        In partial mode with motors_limit, the unchecked motors (= whose
        PWM is NOT in _currently_kept_pwms) are marked
        _skip_wiring=True after transform: they stay recognized as
        dc_motor but inference will remove them from the active netlist to
        store them in `metadata["_skipped_motors"]`. The dedicated section of
        render_instructions shows them in the right panel."""
        from .declare_component_dialog import DECLARE_OPTION_ID
        for c in self._ambiguous:
            type_id = self._chosen_type.get(c.ref)
            # ⚠️ Un driver pas-a-pas ne passe PAS par le dispatch generique.
            # Mesure du 2026-08-29 : `apply_saved_resolution(a4988,
            # "drv8825")` rend une **LED** -- ce dispatch ne connait que les
            # transformations de composants ambigus et retombe sur son defaut
            # pour tout le reste. Un driver n'est pas une sortie ambigue.
            if c.type in STEPPER_DRIVERS:
                if type_id is not None:
                    apply_stepper_driver_swap(c, type_id)
                continue
            # Un moteur de NIVEAU 1 (nomme par le code) ne se transforme pas
            # ici : le changement de driver passe par la REGENERATION cote
            # studio (`chosen_driver_for`), jamais par une mutation de
            # netlist — le code est la source, c'est lui qui doit changer.
            if (c.type == "dc_motor"
                    and c.attributes.get("signature_detected")):
                continue
            # Capture the "is this motor to wire?" info BEFORE the
            # transform (which removes _grouped_pwm_pin once in dc_motor).
            grouped_pwm = c.attributes.get("_grouped_pwm_pin")
            skip_wiring = (
                grouped_pwm is not None
                and grouped_pwm not in self._currently_kept_pwms
            )
            # Pre-apply the type to an unchecked motor even if the user
            # didn't explicitly check a dc_motor radio: they confirmed
            # via the checkbox that it IS a motor (just not to wire).
            if type_id is None and grouped_pwm is not None:
                type_id = "dc_motor"
                self._chosen_type[c.ref] = "dc_motor"
            if type_id is None:
                continue
            if type_id == DECLARE_OPTION_ID:
                # "Décrire mon composant…" chosen in the advanced dropdown:
                # open the same form as the beginner path, right where the
                # result gets applied (not earlier — cancelling here must
                # leave the component untouched, like any other choice).
                from .declare_component_dialog import (
                    DeclareComponentDialog, resolve_board_nets,
                )
                dlg = DeclareComponentDialog(
                    self, component=c, board_nets=resolve_board_nets(),
                    lang=lang_manager.lang)
                if dlg.exec() != QDialog.DialogCode.Accepted:
                    continue          # cancelled: leave this component alone
                if dlg.result_component is None:
                    # Accepted via the "Remove" path (existing=... entry
                    # point, not wired yet) has no new declaration to apply.
                    # Mirrors StudioView._open_declare_dialog's None handling.
                    continue
                type_id = dlg.result_component.type_id
                self._chosen_type[c.ref] = type_id
            # Divergence code/schéma (puce détectée changée) : plus de popup ici.
            # StudioView propose LA régénération à la validation (un seul popup)
            # et ferme le schéma si l'utilisateur accepte.
            apply_saved_resolution(
                c, type_id, netlist,
                driver_type=self._chosen_driver.get(c.ref),
            )
            if type_id == "dc_motor" and skip_wiring:
                c.attributes["_skip_wiring"] = True
            # Mark as confirmed so the modal doesn't resurface
            # if we regenerate with the same code/prompt.
            c.attributes["_confidence"] = "high"

    def chosen_driver_for(self, ref: str) -> str | None:
        """Driver chosen for a given ref (None if type != dc_motor
        or not yet chosen). Used by the caller to persist
        the choice in _wiring_resolutions."""
        return self._chosen_driver.get(ref)

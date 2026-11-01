"""Netlist data model (components, pins, wires, warnings).

Everything is a dataclass + JSON-serializable. No Qt dependency — we must
be able to manipulate a netlist in CLI / tests without an event loop.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


# Severities of warnings produced by inference / conflict detection.
SEVERITY_INFO    = "info"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR   = "error"

# Warnings raised by the DETECTOR'S SAFETY NETS. They all say the same kind of
# thing -- "the app guessed here" -- and they stop describing anything the
# moment the user declares the component themselves. Whoever applies a
# declaration must drop them, otherwise the schematic contradicts the
# correction the user just made.
#
# Lives here, in the Qt-free module both consumers can import: the library
# replay (`declared_apply`) and the single application point
# (`ambiguity_dialog._apply_declared`). It used to be private to the former,
# so the latter silently kept `presumed_analog_component` alive on a component
# the user had just described (QA L4, 2026-08-10).
SAFETY_NET_WARNING_CODES = frozenset({
    "unwired_unknown_component",
    "unwired_unknown_component_pins",
    "presumed_i2c_wiring",
    "presumed_analog_component",
    "undrawable_component",
    # Le type deduit POSSEDE une reference et le prompt ne l'a pas
    # donnee : on a choisi un numero de piece que personne n'a ecrit.
    "presumed_from_description",
})

# Valeurs de `attributes["role"]` qui marquent un composant POSE PAR
# L'INFERENCE pour en accompagner un autre — resistance serie d'une LED ou
# d'un buzzer, pull-up d'un bouton ou d'un DHT. Ecrites par `inference` et
# `implicit_actions` ; lues ici pour qu'un seul endroit fasse foi.
#
# ⚠️ Ce n'est PAS une decoration : un compagnon partage la CLE DE RESOLUTION du
# composant qu'il accompagne. La LED vit sur un net interne et sa resistance
# fait le pont jusqu'a la broche Arduino, donc `_resolution_key_for` rend
# ('', 'D7') pour les DEUX — en remontant le pont pour la LED, en lisant la
# broche directement sur la resistance. Rejouer une resolution sauvegardee sur
# un compagnon transforme donc la resistance en ce que l'utilisateur avait
# choisi pour SA LED (QA du 2026-08-27 : une LED fantome a chaque reouverture
# du schema, sur le cas le plus banal du corpus debutant).
#
# Un compagnon n'a JAMAIS ete un choix de l'utilisateur : il n'a rien a
# recevoir d'un rejeu.
COMPANION_ROLES = frozenset({"series", "pullup"})

# Attributes the same safety nets set on the component itself. Same lifetime,
# same reason to disappear.
SAFETY_NET_ATTRS = ("unrecognized", "presumed_wiring", "presumed_analog",
                    "presumed_from_description", "constructor_pins")


@dataclass
class Pin:
    """A component pin connected to a net.

    `name`  : canonical name of the component (e.g. "A", "K", "DATA").
    `net`   : net name (e.g. "5V", "GND", "D2", "NET_A").
    """
    name: str
    net: str


@dataclass
class Component:
    """A netlist component (LED, resistor, sensor, etc.).

    `ref`        : reference (U1, D1, R1, …). Unique within the netlist.
    `type`       : catalog type (`led`, `resistor`, `dht22`, …).
    `pins`       : list of Pin (the order follows the catalog).
    `attributes` : custom values (`{"color": "red", "value": "10k"}`).
    `fn_id`      : id of the owning feature ("fn-1") or "".
    `inferred`   : True if added by inference.py (e.g. LED resistor).
    """
    ref: str
    type: str
    pins: list[Pin] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    fn_id: str = ""
    inferred: bool = False

    def pin(self, name: str) -> Pin | None:
        for p in self.pins:
            if p.name == name:
                return p
        return None


@dataclass
class Warning_:
    """Warning attached to the netlist (conflicts, inferences, etc.).

    `code` identifies the reason in a stable way ; `params` carries the
    values to inject into the message templates (i18n on the
    `instructions.py` side). `message` remains for compatibility — it contains
    a raw FR version, usable in debug or as a fallback.
    """
    code: str           # stable identifier (e.g. "led_series_resistor")
    severity: str       # SEVERITY_*
    message: str        # raw FR message (debug/fallback only)
    refs: list[str] = field(default_factory=list)
    params: dict[str, str] = field(default_factory=dict)


# Renamed in the public namespace without colliding with the builtin.
Warning = Warning_


@dataclass
class Netlist:
    """Complete description of a circuit: components + connections + meta.

    `nets` is derived automatically from `components` (cache).
    """
    board_id: str
    components: list[Component] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── Access ────────────────────────────────────────────────
    def by_ref(self, ref: str) -> Component | None:
        for c in self.components:
            if c.ref == ref:
                return c
        return None

    def by_fn(self, fn_id: str) -> list[Component]:
        return [c for c in self.components if c.fn_id == fn_id]

    def nets(self) -> dict[str, list[tuple[str, str]]]:
        """Returns {net: [(ref, pin_name), ...]} on the fly."""
        out: dict[str, list[tuple[str, str]]] = {}
        for c in self.components:
            for p in c.pins:
                out.setdefault(p.net, []).append((c.ref, p.name))
        return out

    # ── Mutations ────────────────────────────────────────────
    def add_component(self, c: Component) -> None:
        if any(x.ref == c.ref for x in self.components):
            raise ValueError(f"duplicate component ref: {c.ref}")
        self.components.append(c)

    def remove_by_fn(self, fn_id: str) -> None:
        self.components = [c for c in self.components if c.fn_id != fn_id]

    def next_ref(self, prefix: str) -> str:
        """Generates a unique ref of the form <prefix><N> (R1, R2, ...)."""
        used = {c.ref for c in self.components}
        n = 1
        while f"{prefix}{n}" in used:
            n += 1
        return f"{prefix}{n}"

    def add_warning(self, code: str, severity: str, message: str,
                    refs: list[str] | None = None,
                    params: dict[str, str] | None = None) -> None:
        self.warnings.append(Warning(
            code=code, severity=severity, message=message,
            refs=list(refs or []),
            params=dict(params or {}),
        ))

    # ── Serialization ────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "board_id": self.board_id,
            "components": [
                {
                    "ref": c.ref,
                    "type": c.type,
                    "fn_id": c.fn_id,
                    "inferred": c.inferred,
                    "pins": [{"name": p.name, "net": p.net} for p in c.pins],
                    "attributes": dict(c.attributes),
                }
                for c in self.components
            ],
            "warnings": [asdict(w) for w in self.warnings],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Netlist":
        nl = cls(
            board_id=data.get("board_id", ""),
            metadata=dict(data.get("metadata", {})),
        )
        for cd in data.get("components", []) or []:
            nl.components.append(Component(
                ref=cd["ref"],
                type=cd["type"],
                fn_id=cd.get("fn_id", ""),
                inferred=bool(cd.get("inferred", False)),
                pins=[Pin(name=p["name"], net=p["net"])
                      for p in cd.get("pins", []) or []],
                attributes=dict(cd.get("attributes", {})),
            ))
        for wd in data.get("warnings", []) or []:
            nl.warnings.append(Warning(
                code=wd.get("code", ""),
                severity=wd.get("severity", SEVERITY_INFO),
                message=wd.get("message", ""),
                refs=list(wd.get("refs", []) or []),
                params=dict(wd.get("params", {}) or {}),
            ))
        return nl

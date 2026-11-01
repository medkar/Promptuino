"""Model (pure, no Qt) of the per-component dropdown menu of the schematic.

Decides which entries to display for a given component. The dialog
(wiring_diagram_dialog) builds the QMenu from this list and wires the
handlers according to `kind`. Keeps the decision testable without PyQt.

Order: "Modifier ce composant..." (if editable) -> 1 entry per available
implicit action -> "Ce n'est pas le bon composant" (always, last). The
optional separator before the last entry is handled on the dialog side.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MenuEntry:
    """A menu entry. `kind` drives the handler on the dialog side:
    - "edit"            -> _edit_component(ref)
    - "implicit"        -> _run_implicit_action(ref, action_id)
    - "wrong_component" -> _on_wrong_component_entry(ref)
    `action_id` is only set for kind == "implicit".
    """
    kind: str
    label: str
    action_id: str | None = None


def menu_entries(*, editable: bool, actions, labels: dict) -> list[MenuEntry]:
    """Build the ordered list of menu entries for a component.

    `actions` : result of implicit_actions.available_actions(component,
        netlist) -- objects exposing `.id` and `.label`.
    `labels` : dict with the keys "edit" and "wrong_component" (localized).
    """
    out: list[MenuEntry] = []
    if editable:
        out.append(MenuEntry("edit", labels["edit"]))
    for act in actions:
        out.append(MenuEntry("implicit", act.label, action_id=act.id))
    out.append(MenuEntry("wrong_component", labels["wrong_component"]))
    return out

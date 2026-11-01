"""Form where the user describes a component the detector could not recognise.

Name, pin count, then one row per pin: label + which board net it goes to.
The electrical role is NOT asked — it is derived from the net and the label
(declared_components.role_for) and stored, so the user never meets the word.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QScrollArea, QWidget, QGridLayout, QMessageBox,
)

from ..declared_components import (
    DeclaredComponent, DeclaredPin, DRAWABLE_PIN_COUNTS, default_keywords,
    is_drawable_pin_count, library_file_unusable, load, new_entry_id,
    normalize_header, role_for, save, set_registry, upsert,
)
from ..theme import destructive_button_qss, theme_manager
from .instructions import i2c_alias_for_net

# Sentinel option id of the "Describe my component…" tile / list entry.
DECLARE_OPTION_ID = "__declare__"

NOT_CONNECTED = ""      # value of the "(not connected)" combo entry

# Echelle d'espacement du formulaire. DEUX valeurs, pas plus : la proximite
# est ce qui dit a l'oeil ce qui va ensemble, et une echelle a cinq crans ne
# dit plus rien.
GROUP_GAP = 16          # entre deux sujets differents
ROW_GAP = 6             # entre elements d'un meme sujet (champ <-> legende)

# La liste de broches se cale sur son contenu jusqu'a ce nombre de lignes,
# puis defile. Sans ce calage elle est la VICTIME de tout le reste : elle
# porte seule le facteur d'etirement, donc une legende qui passe sur deux
# lignes lui prend sa derniere broche. Mesure le 2026-08-12 : la 4e broche
# passait sous la barre de defilement des que la marge s'elargissait de 9 px —
# et une traduction un peu plus longue produisait deja le meme effet.
PIN_LIST_MAX_ROWS = 8

# Marge AUTOUR du bloc de broches, et marges DEDANS. Le bloc etait flush de
# tous les cotes : contenu a 4 px de ses bords, dernier menu deroulant a 5 px
# de la barre de defilement (que l'auto-masquage force visible, donc elle
# prend ses 10 px en permanence). Ce qui se dessine sur le pourtour du bloc —
# cadre, anneau de focus selon le style du bureau — n'avait alors nulle part
# ou aller et sortait rogne a droite et en bas.
PIN_BLOCK_INSET = 6                       # entre le bloc et ses voisins
PIN_GRID_MARGINS = (12, 10, 12, 12)       # entre le contenu et les bords du bloc

_LABELS = {
    "title":       {"fr": "Décrire mon composant",
                    "en": "Describe my component",
                    "es": "Describir mi componente",
                    "it": "Descrivi il mio componente"},
    "name":        {"fr": "Nom", "en": "Name", "es": "Nombre", "it": "Nome"},
    "pin_count":   {"fr": "Nombre de broches", "en": "Number of pins",
                    "es": "Número de pines", "it": "Numero di pin"},
    "lib":         {"fr": "Librairie Arduino (si tu la connais)",
                    "en": "Arduino library (if you know it)",
                    "es": "Biblioteca Arduino (si la conoces)",
                    "it": "Libreria Arduino (se la conosci)"},
    "lib_placeholder": {"fr": "à déterminer",
                        "en": "to be determined",
                        "es": "por determinar",
                        "it": "da determinare"},
    # TODO #51 : le champ reste VIDE dans les deux cas, donc seul ce texte
    # distingue « aucune » de « à déterminer » à l'écran. Deux décisions
    # opposées qui se ressemblaient : c'est exactement le défaut du ticket.
    "lib_none":    {"fr": "aucune n'est nécessaire",
                    "en": "none is needed",
                    "es": "no hace falta ninguna",
                    "it": "non ne serve alcuna"},
    "lib_pick":    {"fr": "Chercher…", "en": "Search…",
                    "es": "Buscar…", "it": "Cerca…"},
    "lib_clear":   {"fr": "Effacer", "en": "Clear",
                    "es": "Borrar", "it": "Cancella"},
    "lib_hint":    {"fr": "Laissé vide, l'app la déterminera à la première "
                          "génération.",
                    "en": "Left blank, the app will work it out at the first "
                          "generation.",
                    "es": "Si se deja vacío, la app la determinará en la "
                          "primera generación.",
                    "it": "Se lasciato vuoto, l'app la determinerà alla "
                          "prima generazione."},
    "keywords":    {"fr": "Reconnaître ce composant quand le prompt "
                          "contient :",
                    "en": "Recognize this component when the prompt "
                          "contains:",
                    "es": "Reconocer este componente cuando el prompt "
                          "contiene:",
                    "it": "Riconosci questo componente quando il prompt "
                          "contiene:"},
    "pin_label":   {"fr": "Broche", "en": "Pin", "es": "Pin", "it": "Pin"},
    "pin_net":     {"fr": "Connectée à", "en": "Connected to",
                    "es": "Conectada a", "it": "Collegata a"},
    "not_wired":   {"fr": "(non connectée)", "en": "(not connected)",
                    "es": "(sin conectar)", "it": "(non collegato)"},
    "save":        {"fr": "Enregistrer", "en": "Save", "es": "Guardar",
                    "it": "Salva"},
    "cancel":      {"fr": "Annuler", "en": "Cancel", "es": "Cancelar",
                    "it": "Annulla"},
    # « Supprimer » et non « Retirer de ma librairie » : le libellé long
    # decrivait le MECANISME (d'ou l'entree part) la ou l'utilisateur veut
    # lire l'ACTE. Il se confondait de surcroit avec « retirer le composant du
    # schema », qui n'existe pas — c'est ce quiproquo qui a laisse la decision
    # sur ce bouton en suspens deux jours (2026-08-10).
    "remove":      {"fr": "Supprimer",
                    "en": "Delete",
                    "es": "Eliminar",
                    "it": "Elimina"},
    "drawable":    {"fr": "Le schéma sait dessiner 2 à 8 broches en ligne "
                          "(9, 11 et 13 aussi), ou 10 à 40 par pas de 2 en "
                          "double rangée.",
                    "en": "The schematic can draw 2 to 8 pins in a row "
                          "(9, 11 and 13 too), or 10 to 40 in steps of 2 as "
                          "a double row.",
                    "es": "El esquema puede dibujar de 2 a 8 pines en fila "
                          "(también 9, 11 y 13), o de 10 a 40 de 2 en 2 en "
                          "doble fila.",
                    "it": "Lo schema sa disegnare da 2 a 8 pin in fila "
                          "(anche 9, 11 e 13), o da 10 a 40 a passi di 2 su "
                          "doppia fila."},
    "err_name":    {"fr": "Donne un nom à ton composant.",
                    "en": "Give your component a name.",
                    "es": "Dale un nombre a tu componente.",
                    "it": "Dai un nome al tuo componente."},
    "err_labels":  {"fr": "Chaque broche doit avoir un nom, et deux broches ne "
                          "peuvent pas porter le même.",
                    "en": "Every pin needs a name, and two pins cannot share "
                          "the same one.",
                    "es": "Cada pin necesita un nombre, y dos pines no pueden "
                          "tener el mismo.",
                    "it": "Ogni pin deve avere un nome, e due pin non possono "
                          "avere lo stesso."},
    "err_library_unusable": {
        "fr": "Ta librairie de composants (components.json) n'a pas pu "
              "être lue — elle vient peut-être d'une version plus récente de "
              "Promptuino. Pour ne pas l'écraser, ce composant n'a pas été "
              "enregistré.",
        "en": "Your component library (components.json) could not be read — "
              "it may come from a newer version of Promptuino. To avoid "
              "overwriting it, this component was not saved.",
        "es": "No se pudo leer tu biblioteca de componentes "
              "(components.json); puede provenir de una versión más "
              "reciente de Promptuino. Para no sobrescribirla, este "
              "componente no se guardó.",
        "it": "La tua libreria di componenti (components.json) non è stata "
              "leggibile — potrebbe provenire da una versione più recente "
              "di Promptuino. Per non sovrascriverla, questo componente non "
              "è stato salvato.",
    },
}


def _t(key: str, lang: str) -> str:
    entry = _LABELS.get(key, {})
    return entry.get(lang) or entry.get("fr") or key


def _field_group(row: QHBoxLayout, hint: QLabel) -> QVBoxLayout:
    """Un champ et SA legende, serres a `ROW_GAP` l'un de l'autre.

    Le groupe est ensuite pose dans la colonne principale, qui espace a
    `GROUP_GAP` : la legende reste donc deux fois plus proche du champ qu'elle
    explique que du champ suivant. C'est cette difference, pas la valeur
    absolue, qui la rattache a quelque chose.
    """
    group = QVBoxLayout()
    group.setSpacing(ROW_GAP)
    group.addLayout(row)
    group.addWidget(hint)
    return group


def prefill_pins(component, board_nets: list[str]) -> list[tuple[str, str]]:
    """Rows (label, net) to open the form with, from what the code let slip.

    `component is None` -> creation from the "Composants" tab: there is no
    schematic, so "VCC -> 5V" has no meaning. Returns [] and the form starts
    with blank, unconnected pins.

    - presumed I2C wiring -> the four presumed pins, to confirm or correct;
    - placeholder with `constructor_pins` -> the pins seen in the constructor,
      in order, on the first rows. Pins that do not exist on this board are
      dropped rather than silently offered.
    Pure function (no Qt) so it can be tested headless.
    """
    if component is None:
        return []
    pins = list(getattr(component, "pins", []) or [])
    rows = [(p.name, p.net if p.net in board_nets else "") for p in pins]
    if component.attributes.get("presumed_wiring"):
        return rows
    ctor = [p for p in (component.attributes.get("constructor_pins") or [])]
    for i, net in enumerate(ctor):
        if i >= len(rows):
            break
        rows[i] = (rows[i][0], net if net in board_nets else "")
    return rows


def filter_persistable_choices(chosen: dict[str, str],
                               cancelled_refs=frozenset()) -> dict[str, str]:
    """Entries of `chosen` (ref -> type_id) safe to write into
    `_wiring_resolutions`.

    Excludes:
    - refs whose "Describe my component…" form was cancelled: cancelling
      must mean "nothing changed", never "the sentinel is now the saved
      type" (2026-07-30 review finding -- a persisted sentinel silently
      degrades the component to a red LED on the next reload, since
      apply_saved_resolution("__declare__", ...) matches no known type);
    - defensively, any leftover DECLARE_OPTION_ID even for a ref not listed
      in `cancelled_refs`, so a future caller that forgets to track
      cancellations still cannot leak the sentinel to disk.

    Pure / no Qt, so it is testable headless.
    """
    return {ref: type_id for ref, type_id in chosen.items()
            if ref not in cancelled_refs and type_id != DECLARE_OPTION_ID}


def entry_for_header(header: str):
    """The declared entry already attached to this `#include`, or None.

    Used so the form opens the EXISTING entry in edit mode instead of a blank
    sheet -- otherwise re-declaring a component to correct it would recreate
    the duplicate that `upsert` was introduced to remove.
    """
    from ..declared_components import find_by_header
    return find_by_header(header)


def _registry_config_file() -> str | None:
    """Config arduino-cli du workspace, pour la recherche de librairie.

    None si aucune carte n'est sélectionnée ou si arduino-cli est absent : la
    modale dégrade alors proprement (elle dit que la recherche est
    indisponible et garde les choix déjà listés). Même règle que
    `StudioView._registry_config_file` — dupliquée ici plutôt qu'importée
    parce que ce module ne doit pas dépendre de la vue.
    """
    try:
        from ..board_manager import board_manager, get_fqbn
        from .. import arduino_cli
        env, model = board_manager.env, board_manager.model
        fqbn = get_fqbn(env, model) if (env and model) else None
        if not fqbn or not arduino_cli.is_available():
            return None
        from ..workspace import workspace_manager
        return workspace_manager.cli_config(fqbn)
    except Exception:
        return None


def _board_architecture() -> str:
    """Architecture de la carte selectionnee, "" si inconnue. Dupliquee ici
    plutot qu'importee de la vue, meme raison que `_registry_config_file` :
    ce module ne doit pas dependre de `studio_view`."""
    try:
        from ..board_manager import board_manager, get_fqbn
        env, model = board_manager.env, board_manager.model
        fqbn = get_fqbn(env, model) if (env and model) else ""
        parts = (fqbn or "").split(":")
        return parts[1] if len(parts) >= 2 else ""
    except Exception:
        return ""


def resolve_board_nets() -> list[str]:
    """Net names of the currently selected board, for the pin-net combos.

    Uses the same env/model -> board_id -> Board resolution as the rest of
    StudioView (`board_manager` + `boards.board_id_for_env_model`), so the
    combo offers the real pinout of the connected board. Falls back to the
    literal Uno/Nano pinout (covers ~90% of cases, cf.
    `ui/wiring/boards.py:board_id_for_env_model`) when the board isn't in the
    wiring catalog yet (e.g. ESP32, "bientôt disponible") or the lookup fails
    for any other reason.
    """
    try:
        from ..board_manager import board_manager
        from .boards import board_id_for_env_model, load_board
        board_id = board_id_for_env_model(board_manager.env or "arduino",
                                          board_manager.model or "")
        board = load_board(board_id) if board_id else None
        nets = board.pins() if board is not None else []
        if nets:
            return nets
    except Exception:
        pass
    return (["5V", "3V3", "GND"]
            + [f"D{i}" for i in range(14)]
            + [f"A{i}" for i in range(6)])


class DeclareComponentDialog(QDialog):
    """Form. `result_component` holds the DeclaredComponent after Accepted."""

    def __init__(self, parent=None, *, component=None, existing=None,
                 board_nets: list[str] | None = None, lang: str = "fr") -> None:
        super().__init__(parent)
        self._lang = lang
        # Opening from a placeholder whose header already matches a declared
        # entry must edit THAT entry, not start a blank sheet -- otherwise
        # correcting a declaration would recreate the duplicate `upsert` was
        # introduced to remove.
        if existing is None and component is not None:
            existing = entry_for_header(component.attributes.get("header") or "")
        self._existing = existing
        # TODO #51 : le 3e etat. Le champ `lib` reste VIDE dans les deux cas
        # (« a determiner » et « aucune »), donc il ne peut pas porter la
        # distinction -- c'est tout l'objet du ticket. Ce drapeau la porte.
        self._no_lib = bool(getattr(existing, "no_lib", False))
        # `board_nets=None` (creation from the "Composants" tab, no schema
        # in hand) must still produce a usable pin-net combo.
        self._board_nets = list(board_nets or []) or resolve_board_nets()
        self._component = component
        self.result_component: DeclaredComponent | None = None
        # `removed` seul ne suffit pas a l'appelant : pour retirer l'entree de
        # SA liste il lui faut le type qui vient de disparaitre, et apres
        # `accept()` il n'a plus de quoi le retrouver (`find_by_type` ne
        # repondra plus). On le lui donne ici.
        self.removed = False
        self.removed_type_id = ""
        self.setWindowTitle(_t("title", lang))
        self.setMinimumWidth(460)
        self._rows: list[tuple[QLineEdit, QComboBox]] = []
        self._build()

    # -- construction ---------------------------------------------------
    def _build(self) -> None:
        lay = QVBoxLayout(self)
        # Deux distances, et deux seulement : GROUP_GAP entre deux sujets
        # differents, ROW_GAP entre des elements qui parlent de la meme chose.
        # Sans ca, Qt met la meme valeur partout (~6 px) et une legende se
        # retrouve aussi loin du champ qu'elle explique que du champ suivant —
        # elle n'appartient alors visuellement a rien.
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(GROUP_GAP)

        head = QHBoxLayout()
        head.setSpacing(ROW_GAP)
        head.addWidget(QLabel(_t("name", self._lang)))
        self._name = QLineEdit(self._existing.name if self._existing else "")
        head.addWidget(self._name, 1)
        lay.addLayout(head)

        lib_row = QHBoxLayout()
        lib_row.setSpacing(ROW_GAP)
        lib_row.addWidget(QLabel(_t("lib", self._lang)))
        # NON éditable : le nom d'une librairie doit venir du registre Arduino,
        # pas d'une frappe. Saisi à la main, il est faux à une lettre près et
        # l'erreur ne se voit qu'à la génération suivante — vu en QA I5, où
        # « Grove Ultrasonic » (au lieu de « Grove Ultrasonic Ranger ») était
        # introuvable au registre. On passe donc par la recherche.
        self._lib = QLineEdit(self._existing.lib if self._existing else "")
        self._lib.setReadOnly(True)
        self._lib.setPlaceholderText(_t("lib_placeholder", self._lang))
        lib_row.addWidget(self._lib, 1)
        self._btn_pick_lib = QPushButton(_t("lib_pick", self._lang))
        self._btn_pick_lib.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_pick_lib.setAutoDefault(False)
        self._btn_pick_lib.setDefault(False)
        self._btn_pick_lib.clicked.connect(self._on_pick_lib)
        lib_row.addWidget(self._btn_pick_lib)
        # Une librairie choisie doit pouvoir être RETIRÉE : un composant peut
        # légitimement n'en demander aucune, et le champ étant en lecture
        # seule, l'effacer à la main n'est plus possible.
        self._btn_clear_lib = QPushButton(_t("lib_clear", self._lang))
        self._btn_clear_lib.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_clear_lib.setAutoDefault(False)
        self._btn_clear_lib.setDefault(False)
        self._btn_clear_lib.clicked.connect(self._on_clear_lib)
        lib_row.addWidget(self._btn_clear_lib)
        self._refresh_lib_state()
        lib_hint = QLabel(_t("lib_hint", self._lang))
        lib_hint.setWordWrap(True)
        lay.addLayout(_field_group(lib_row, lib_hint))

        kw_row = QHBoxLayout()
        kw_row.setSpacing(ROW_GAP)
        kw_row.addWidget(QLabel(_t("keywords", self._lang)))
        # Pre-filled with the name, and kept in sync with it -- UNTIL the
        # user edits the field themselves (`_keywords_dirty`, set by
        # `textEdited`, never by `textChanged`: the programmatic sync below
        # must not count as a user edit).
        # The flag means "the user typed in this field", NOT "we are editing an
        # existing entry" (2026-07-30 review): seeded to True in edit mode, the
        # sync was dead even when the field had never been touched, so renaming
        # "Foo" to "Bar" left keywords=("Foo",) -- the component stayed
        # recognised under its old name and not under the new one. An existing
        # entry whose keywords are still exactly its name has NOT been edited;
        # anything else has, and a rename must not overwrite it.
        self._keywords_dirty = (
            self._existing is not None
            and tuple(self._existing.keywords)
            != default_keywords(self._existing.name))
        initial_kw = (", ".join(self._existing.keywords) if self._existing
                     else self._name.text())
        self._keywords = QLineEdit(initial_kw)
        kw_row.addWidget(self._keywords, 1)
        lay.addLayout(kw_row)
        self._name.textChanged.connect(self._sync_keywords_from_name)
        self._keywords.textEdited.connect(self._on_keywords_edited)

        cnt = QHBoxLayout()
        cnt.setSpacing(ROW_GAP)
        cnt.addWidget(QLabel(_t("pin_count", self._lang)))
        self._count = QComboBox()
        for n in sorted(DRAWABLE_PIN_COUNTS):
            self._count.addItem(str(n), n)
        cnt.addWidget(self._count)
        cnt.addStretch(1)

        hint = QLabel(_t("drawable", self._lang))
        hint.setWordWrap(True)
        lay.addLayout(_field_group(cnt, hint))

        self._grid_host = QWidget()
        # Fond OPAQUE, via QPalette (regle CLAUDE.md, jamais de QSS ici).
        # Sans lui, agrandir la fenetre laissait des PIXELS PERIMES dans le
        # bloc : les lignes de la grille se deplacaient et personne ne
        # repeignait la zone qu'elles quittaient — mesure le 2026-08-12, un
        # « (non connectee) » fantome restait imprime sous la ligne VCC.
        pal = self._grid_host.palette()
        pal.setColor(self._grid_host.backgroundRole(),
                     pal.color(QPalette.ColorRole.Base))
        self._grid_host.setPalette(pal)
        self._grid_host.setAutoFillBackground(True)
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(*PIN_GRID_MARGINS)
        self._grid.setHorizontalSpacing(GROUP_GAP)
        self._grid.setVerticalSpacing(ROW_GAP)
        # Les deux colonnes se partagent la largeur A EGALITE. Sans stretch,
        # « Connectée à » restait a la largeur de son contenu (154 px) pendant
        # que « Broche » avalait tout le reste — deux tailles de controles
        # sur la meme ligne, pour deux reponses de meme importance.
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1)
        self._scroll = QScrollArea()
        # Sans cadre, comme les 16 autres zones de defilement de l'app — ce
        # formulaire etait le seul a en garder un. Il ne s'en apercevait pas
        # toujours : ouvert depuis le schema, la feuille de style de la modale
        # parente (`ambiguity_dialog`, `QScrollArea { border: none }`) le
        # supprimait deja par cascade, alors que depuis l'onglet Composants il
        # restait. Le meme formulaire avait donc deux aspects selon la porte.
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(self._grid_host)
        # Le bloc ne touche pas ses voisins : il garde une marge a lui.
        pin_box = QVBoxLayout()
        pin_box.setContentsMargins(PIN_BLOCK_INSET, 0,
                                   PIN_BLOCK_INSET, PIN_BLOCK_INSET)
        pin_box.addWidget(self._scroll)
        lay.addLayout(pin_box, 1)

        btns = QHBoxLayout()
        btns.setSpacing(ROW_GAP)
        # « Supprimer » seulement pour une entrée RÉELLEMENT dans la
        # bibliothèque. Une fiche devinée reprise à son compte (QA I4) arrive
        # ici pré-remplie mais pas encore enregistrée : proposer de la retirer
        # d'un endroit où elle n'est pas encore serait un bouton sans objet.
        if self._existing is not None and any(
                c.id == self._existing.id for c in load()):
            b_rm = QPushButton(_t("remove", self._lang))
            b_rm.setAutoDefault(False); b_rm.setDefault(False)
            # Rouge dès le repos : c'est le seul geste irréversible de ce
            # formulaire, il ne doit pas se présenter comme ses voisins.
            b_rm.setStyleSheet(destructive_button_qss(theme_manager.current))
            b_rm.setCursor(Qt.CursorShape.PointingHandCursor)
            b_rm.clicked.connect(self._on_remove)
            btns.addWidget(b_rm)
        btns.addStretch(1)
        b_cancel = QPushButton(_t("cancel", self._lang))
        b_ok = QPushButton(_t("save", self._lang))
        for b in (b_cancel, b_ok):
            b.setAutoDefault(False); b.setDefault(False)
        b_cancel.clicked.connect(self.reject)
        b_ok.clicked.connect(self._on_save)
        btns.addWidget(b_cancel); btns.addWidget(b_ok)
        lay.addLayout(btns)

        # Connecte APRES _seed(). Avant, le setCurrentIndex de _seed declenchait
        # un premier _rebuild_rows (lignes par defaut « 1 »..« 4 ») que le
        # second, une ligne plus bas, retirait aussitot. Or un deleteLater pose
        # pendant __init__ n'est execute par la boucle imbriquee d'exec() que
        # bien plus tard, voire jamais : DIX widgets restaient vivants, enfants
        # du conteneur, visibles, a leur geometrie DE CONSTRUCTION
        # (0,0,640x480). Le champ de saisie geant couvrait tout le bloc et se
        # peignait par-dessous — c'etait LE « cadre vert au survol, rogne a
        # droite et en bas » chasse toute la matinee du 2026-08-12 (640 px + 26
        # de marge = le bord fantome mesure a ~665 sur la capture).
        self._seed()
        self._count.currentIndexChanged.connect(lambda _i: self._rebuild_rows())

    def _seed(self) -> None:
        """Initial rows: existing entry if editing, else the code's hints."""
        if self._existing is not None:
            rows = [(p.label, p.net) for p in self._existing.pins]
        elif self._component is not None:
            rows = prefill_pins(self._component, self._board_nets)
        else:
            rows = [("", ""), ("", "")]
        n = len(rows) if is_drawable_pin_count(len(rows)) else 4
        self._count.setCurrentIndex(max(0, self._count.findData(n)))
        self._rebuild_rows(rows)

    def _rebuild_rows(self, rows: list[tuple[str, str]] | None = None) -> None:
        if rows is None:
            rows = [(le.text(), cb.currentData()) for le, cb in self._rows]
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                # setParent(None) AVANT deleteLater : la suppression differee
                # peut ne s'executer que tres tard (cf. commentaire dans
                # _build). Un widget retire du layout mais toujours enfant
                # reste VISIBLE et se peint. Le detacher tout de suite le fait
                # disparaitre quoi qu'il advienne du deleteLater.
                w.setParent(None)
                w.deleteLater()
        self._rows = []
        n = self._count.currentData() or 4
        self._grid.addWidget(QLabel(_t("pin_label", self._lang)), 0, 0)
        self._grid.addWidget(QLabel(_t("pin_net", self._lang)), 0, 1)
        for i in range(n):
            label, net = rows[i] if i < len(rows) else ("", "")
            # Nom par défaut « 1 », « 2 »… : le formulaire refuse d'enregistrer
            # tant qu'une broche n'a pas de nom, ce qui bloquait le cas où on
            # déclare un composant pour lui APPRENDRE SA BIBLIOTHÈQUE et non
            # pour le dessiner (QA G3, 2026-08-08). Un numéro n'invente rien —
            # c'est ce que le dessin générique affiche de toute façon — et
            # reste modifiable. La règle « tous distincts » est préservée.
            if not label:
                label = str(i + 1)
            le = QLineEdit(label)
            cb = QComboBox()
            cb.addItem(_t("not_wired", self._lang), NOT_CONNECTED)
            for net_name in self._board_nets:
                # Affichage « A4 (SDA) », valeur stockée « A4 ». Un débutant
                # cherche la broche SDA imprimée sur sa carte, pas A4 -- même
                # si c'est le même trou (QA 2026-08-08). L'alias est PUREMENT
                # visuel : le net enregistré ne change pas, donc le routage
                # n'est pas touché. `findData` ci-dessous continue de chercher
                # le net, pas le libellé.
                alias = i2c_alias_for_net(net_name)
                cb.addItem(f"{net_name} ({alias})" if alias else net_name,
                           net_name)
            idx = cb.findData(net)
            cb.setCurrentIndex(idx if idx >= 0 else 0)
            # Meme hauteur que le champ de nom d'en face. Le theme leur donne
            # des paddings differents (champ 6px/33px de haut, combo 0/21px) :
            # deux controles de la meme ligne, pour deux reponses de meme
            # importance, ne doivent pas avoir deux gabarits.
            cb.setMinimumHeight(le.sizeHint().height())
            self._grid.addWidget(le, i + 1, 0)
            self._grid.addWidget(cb, i + 1, 1)
            self._rows.append((le, cb))
        # TOUT l'espace vertical excedentaire va dans un rang vide en fin de
        # grille. Sans lui, agrandir la fenetre distribuait cet espace ENTRE
        # les rangs : l'en-tete « Broche » flottait au milieu du vide et
        # chaque ligne se relogeait a chaque pixel de redimensionnement
        # (mesure : la ligne VCC sautait de y=30 a y=201). L'ancien rang
        # d'etirement est remis a zero d'abord — QGridLayout n'oublie jamais
        # un stretch, meme quand le rang n'a plus d'items.
        prev = getattr(self, "_stretch_row", None)
        if prev is not None:
            self._grid.setRowStretch(prev, 0)
        self._stretch_row = n + 1
        self._grid.setRowStretch(self._stretch_row, 1)
        self._fit_pin_list()

    def _fit_pin_list(self) -> None:
        """Hauteur PLANCHER de la liste, calee sur son contenu (cf.
        PIN_LIST_MAX_ROWS).

        Un plancher, pas une hauteur fixe : la liste doit encore s'etirer si
        l'utilisateur agrandit la fenetre — elle ne doit simplement plus
        retrecir sous ce que ses lignes demandent.
        """
        scroll = getattr(self, "_scroll", None)
        if scroll is None or not self._rows:
            return
        row_h = (self._rows[0][0].sizeHint().height()
                 + self._grid.verticalSpacing())
        margins = self._grid.contentsMargins()
        chrome = margins.top() + margins.bottom() + 2 * scroll.frameWidth()
        # +1 ligne : l'en-tete « Broche / Connectee a ».
        cap = row_h * (PIN_LIST_MAX_ROWS + 1)
        scroll.setMinimumHeight(
            min(self._grid_host.sizeHint().height(), cap) + chrome)

    def _on_pick_lib(self) -> None:
        """Ouvre la recherche de librairie du registre Arduino.

        La MÊME modale que le bouton « Changer de librairie » du bandeau et
        de la fiche : trois portes, une seule façon de choisir une librairie.
        Le jeton de recherche est le nom du composant — c'est celui que
        l'utilisateur a écrit et le seul que l'app connaisse ici.

        Annuler laisse le champ intact (`chosen_lib` vide). « Laisser l'app
        décider » VIDE le champ : un composant déclaré porte sa bibliothèque
        sur SA PROPRE entrée (`DeclaredComponent.lib`), jamais dans
        `component-libs.json` (l'autre magasin, réservé aux simples jetons de
        part-number) — donc effacer la préférence ici ne touche PAS
        `clear_preference`, seul ce champ du formulaire.
        """
        from ..lib_choice_dialog import LibChoiceDialog
        from ..registry_lookup import cached_lookups
        name = self._name.text().strip()
        current = self._lib.text().strip()
        # Alternatives déjà mémorisées pour ce composant, s'il en a : évite
        # une recherche réseau quand la réponse est connue.
        alternatives: list[str] = []
        try:
            for tok, entry in (cached_lookups() or {}).items():
                if tok.strip().casefold() == name.casefold():
                    alternatives = list(entry.get("alternatives") or [])
                    break
        except Exception:
            alternatives = []
        dlg = LibChoiceDialog(self, token=name or current,
                              current_lib=current, alternatives=alternatives,
                              config_file=_registry_config_file(),
                              arch=_board_architecture(),
                              current_no_lib=self._no_lib)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        # TODO #51 : les TROIS sorties, et chacune remet le drapeau a sa
        # valeur. Ne traiter que la nouvelle aurait laisse l'affirmation
        # COLLEE a la fiche : cocher « aucune », puis revenir choisir une vraie
        # bibliotheque, aurait garde les deux.
        if dlg.no_library_requested:
            self._no_lib = True
            self._lib.setText("")
        elif dlg.clear_requested:
            self._no_lib = False
            self._lib.setText("")
        elif dlg.chosen_lib:
            self._no_lib = False
            self._lib.setText(dlg.chosen_lib)
        self._refresh_lib_state()

    def _refresh_lib_state(self) -> None:
        """Rend le 3e etat VISIBLE : sans ca, « aucune » et « a determiner »
        se ressemblent a l'ecran -- champ vide dans les deux cas -- alors que
        ce sont deux decisions opposees."""
        self._lib.setPlaceholderText(
            _t("lib_none", self._lang) if self._no_lib
            else _t("lib_placeholder", self._lang))

    def _on_clear_lib(self) -> None:
        """« Retirer » veut dire « a determiner », PAS « aucune ».

        Sans cette remise a plat, retirer la bibliotheque d'une fiche qui
        portait deja l'affirmation l'aurait laissee en place : l'app aurait
        continue de dire au modele qu'aucune bibliotheque n'est necessaire
        alors que l'utilisateur venait de rendre la question ouverte."""
        self._no_lib = False
        self._lib.setText("")
        self._refresh_lib_state()

    def _sync_keywords_from_name(self, text: str) -> None:
        """Mirrors the name into the keywords field, as long as the user has
        not typed into it themselves (see `_on_keywords_edited`)."""
        if not self._keywords_dirty:
            self._keywords.setText(text)

    def _on_keywords_edited(self, _text: str) -> None:
        self._keywords_dirty = True

    # -- validation -----------------------------------------------------
    def _on_save(self) -> None:
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, _t("title", self._lang),
                                _t("err_name", self._lang))
            return
        labels = [le.text().strip() for le, _ in self._rows]
        if any(not l for l in labels) or len(set(labels)) != len(labels):
            QMessageBox.warning(self, _t("title", self._lang),
                                _t("err_labels", self._lang))
            return
        if library_file_unusable():
            # The file exists but this build could not parse it (unknown
            # future schema version, or corrupt). `load()` degrades that to
            # [] on purpose (never crash) -- but saving now would write a
            # fresh version-1 file containing only THIS entry, silently
            # destroying whatever was on disk. Refuse instead.
            QMessageBox.warning(self, _t("title", self._lang),
                                _t("err_library_unusable", self._lang))
            return
        # Id: the existing entry's if editing (renaming must not orphan it),
        # else `new_entry_id` -- which reuses the slug when the entry holding
        # it bears the SAME name (that is the merge rule) and suffixes only
        # when it bears a different one (a renamed entry left its old slug
        # behind; merging into it would destroy it).
        items = load()
        cid = (self._existing.id if self._existing
               else new_entry_id(name, items))
        header = normalize_header(
            (self._component.attributes.get("header") if self._component else "") or "")
        headers = (header,) if header else ()
        pins = tuple(
            DeclaredPin(label=lbl, role=role_for(lbl, cb.currentData() or ""),
                        net=cb.currentData() or "")
            for lbl, (_, cb) in zip(labels, self._rows)
        )
        lib = self._lib.text().strip()
        kw_text = self._keywords.text().strip()
        keywords = (tuple(k.strip() for k in kw_text.split(",") if k.strip())
                    if kw_text else default_keywords(name))
        # Le NOM est toujours un mot-clé. La synchronisation automatique
        # s'arrête dès que les mots-clés diffèrent du défaut — pour ne pas
        # écraser une saisie — mais l'enregistrement les UNIONNE, pour ne pas
        # oublier ce que la bibliothèque savait. Résultat : le premier
        # renommage laisse deux mots-clés, l'entrée paraît dès lors
        # personnalisée, et TOUS les renommages suivants laissaient le nom en
        # arrière (mesuré : entrée « AS7341V3 », mots-clés restés « AS7341 »,
        # « AS7341V2 »). Le nom affiché cessait donc d'être un déclencheur —
        # or c'est justement celui que l'utilisateur lit et réécrira. On
        # l'ajoute sans rien retirer : les mots-clés saisis restent (QA G4bis).
        if not any(k.strip().casefold() == name.casefold() for k in keywords):
            keywords = (*keywords, name)
        decl = DeclaredComponent(id=cid, name=name, headers=headers, pins=pins,
                                 lib="" if self._no_lib else lib,
                                 keywords=keywords, no_lib=self._no_lib)
        items = upsert(items, decl)
        save(items)
        set_registry(items)
        self.result_component = next((c for c in items if c.id == cid), decl)
        self.accept()

    def _on_remove(self) -> None:
        items = [c for c in load() if c.id != self._existing.id]
        save(items)
        set_registry(items)
        self.removed = True
        self.removed_type_id = self._existing.type_id
        self.accept()

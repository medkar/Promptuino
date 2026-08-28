"""Logic + widget of the generation modal.

`default_action` is a pure function (tested outside Qt). The QDialog
`GenerationModal` is added in Task 10.
"""
from __future__ import annotations

from .feature_model import Feature
from .gen_prompts import feature_combo_label, feature_combo_tooltip

# Possible actions
REGENERATE = "regenerate"
ADD = "add"
CORRECT = "correct"


def default_action(features: list[Feature], prompt: str) -> str:
    """Action pré-sélectionnée à l'ouverture : 'regenerate' s'il n'y a pas
    encore de fonctionnalité, sinon 'add'. (Le mode 'correct' n'est plus
    déduit d'un préfixe de prompt : il est forcé explicitement via
    GenerationModal(default_override=CORRECT), cf. StudioView.open_modify_flow.)"""
    if not features:
        return REGENERATE
    return ADD


# ── Qt widget (the only Qt import of the package) ──────────────────────────────
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QRadioButton, QLabel, QCheckBox, QPushButton,
    QHBoxLayout, QButtonGroup, QWidget, QScrollArea,
)
from PyQt6.QtCore import Qt

from ui.i18n import lang_manager
from ..theme import (
    theme_manager, primary_button_qss, secondary_button_qss, radio_checkbox_qss,
)


class GenerationModal(QDialog):
    """Modal with 3 actions (Regenerate / Add / Correct) with a pre-selected
    default. Returns (action, target) via .result_choice after exec().

    For CORRECT, `target` is the LIST of checked feature ids (≥1); for the
    other actions, `target` is None. Checking several features (or « Tout
    sélectionner ») requests merging them into a single one (cf studio_view)."""

    def __init__(self, features, prompt: str, parent=None, *,
                 preselect_target_id=None, default_override=None):
        super().__init__(parent)
        s = lang_manager.current
        self._features = features
        self.result_choice = None      # (action, target) after accept

        self.setWindowTitle(s.gen_modal_title)
        self.setMinimumWidth(420)
        root = QVBoxLayout(self)

        self._group = QButtonGroup(self)
        self._rb = {}
        for action, label, desc in (
            (REGENERATE, s.gen_modal_regenerate, s.gen_modal_regenerate_desc),
            (ADD, s.gen_modal_add, s.gen_modal_add_desc),
            (CORRECT, s.gen_modal_correct, s.gen_modal_correct_desc),
        ):
            rb = QRadioButton(label)
            self._group.addButton(rb)
            self._rb[action] = rb
            root.addWidget(rb)
            sub = QLabel(desc)
            sub.setStyleSheet("color: gray; margin-left: 22px;")
            root.addWidget(sub)

        # Selector for feature(s) to modify (visible only for Correct).
        # Multi-selection via checkboxes + "Select all": checking a
        # single feature keeps the granular modification (the rest intact);
        # checking ≥2 features merges their code into a single one (cf studio_view).
        self._target_w = QWidget()
        tl = QVBoxLayout(self._target_w)
        tl.setContentsMargins(22, 0, 0, 0)
        tl.setSpacing(4)
        tl.addWidget(QLabel(s.gen_modal_target))

        self._all_cb = QCheckBox(s.gen_modal_target_all)
        self._all_cb.clicked.connect(self._on_all_clicked)
        tl.addWidget(self._all_cb)

        # Scrollable list of features (safeguard if there are many features).
        self._feat_cbs: list[tuple[QCheckBox, str]] = []
        list_w = QWidget()
        ll = QVBoxLayout(list_w)
        ll.setContentsMargins(14, 0, 0, 0)
        ll.setSpacing(2)
        for f in features:
            # Label = summary + compact pins (« Clignote la LED — D5 »);
            # tooltip = full summary + all pins (on hover).
            cb = QCheckBox(feature_combo_label(f))
            cb.setToolTip(feature_combo_tooltip(f))
            cb.toggled.connect(self._on_feat_toggled)
            ll.addWidget(cb)
            self._feat_cbs.append((cb, f.id))
        ll.addStretch(1)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(list_w)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setMaximumHeight(180)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tl.addWidget(self._scroll)
        root.addWidget(self._target_w)

        # Preselection: the feature guessed from the CORRECTION pin, otherwise
        # the 1st (always guarantees ≥1 checked at opening). blockSignals avoids
        # touching `_ok` (not yet created) via the toggled slot.
        preselect_done = False
        if preselect_target_id is not None:
            for cb, fid in self._feat_cbs:
                if fid == preselect_target_id:
                    cb.blockSignals(True); cb.setChecked(True); cb.blockSignals(False)
                    preselect_done = True
                    break
        if not preselect_done and self._feat_cbs:
            cb = self._feat_cbs[0][0]
            cb.blockSignals(True); cb.setChecked(True); cb.blockSignals(False)

        # Buttons.
        btns = QHBoxLayout()
        btns.addStretch(1)
        self._cancel = QPushButton(s.gen_modal_cancel)
        self._cancel.setAutoDefault(False)
        self._cancel.clicked.connect(self.reject)
        self._ok = QPushButton(s.gen_modal_validate)
        self._ok.setAutoDefault(True)
        self._ok.setDefault(True)          # Enter validates the modal
        self._ok.clicked.connect(self._on_validate)
        btns.addWidget(self._cancel)
        btns.addWidget(self._ok)
        root.addLayout(btns)

        # Pre-selected default + (un)gray the impossible options.
        default = default_override or default_action(features, prompt)
        if not features:
            self._rb[ADD].setEnabled(False)
            self._rb[CORRECT].setEnabled(False)
        self._rb[default].setChecked(True)
        self._group.buttonToggled.connect(lambda *_: self._refresh_target())
        self._sync_all_cb()
        self._refresh_target()

        # Centralized style (green on hover): outlined radios, « Valider » =
        # primary (filled), « Annuler » = secondary (outlined). cf theme.*.
        self._apply_theme()
        theme_manager.changed.connect(self._apply_theme)

    def _apply_theme(self, *_):
        c = theme_manager.current
        # radio_checkbox_qss also covers the QCheckBox (boxes + « Tout
        # select all"): green check/bullet, green text on hover.
        self.setStyleSheet(radio_checkbox_qss(c))
        self._ok.setStyleSheet(primary_button_qss(c))
        self._cancel.setStyleSheet(secondary_button_qss(c))

    def _selected_ids(self) -> list[str]:
        """Ids of the checked features, in display order."""
        return [fid for cb, fid in self._feat_cbs if cb.isChecked()]

    def _on_all_clicked(self, checked: bool):
        for cb, _ in self._feat_cbs:
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)
        self._update_ok_state()

    def _on_feat_toggled(self, _checked: bool = False):
        self._sync_all_cb()
        self._update_ok_state()

    def _sync_all_cb(self):
        """"Select all" checked iff all the features are."""
        all_checked = bool(self._feat_cbs) and all(
            cb.isChecked() for cb, _ in self._feat_cbs)
        self._all_cb.blockSignals(True)
        self._all_cb.setChecked(all_checked)
        self._all_cb.blockSignals(False)

    def _update_ok_state(self):
        # « Valider » disabled as long as no feature is checked in Correct
        # mode (otherwise we would validate a modification without a target).
        if not hasattr(self, "_ok"):
            return
        if self._rb[CORRECT].isChecked() and self._features:
            self._ok.setEnabled(bool(self._selected_ids()))
        else:
            self._ok.setEnabled(True)

    def _refresh_target(self):
        self._target_w.setVisible(
            self._rb[CORRECT].isChecked() and len(self._features) > 0
        )
        self._update_ok_state()
        # Re-fit the dialog to its content: when the « modifier » section is
        # hidden, the dialog would otherwise keep its larger height and the
        # QVBoxLayout would spread the leftover space into the description
        # QLabels (vertical policy Preferred) -> the gaps between rows change.
        # adjustSize() shrinks/grows it to the current content each toggle.
        self.adjustSize()

    def _on_validate(self):
        action = next(a for a, rb in self._rb.items() if rb.isChecked())
        target = None
        if action == CORRECT and self._features:
            target = self._selected_ids()
            if not target:                # guard: no feature checked
                return
        self.result_choice = (action, target)
        self.accept()

"""CodePanel — fenêtre de code réutilisable (Prompt 3 du plan
PATHFINDER-2026-07-05).

Regroupe le sélecteur de fonctionnalités (dropdown), l'éditeur de code, le
voile « busy » (opération en cours, édition bloquée) et l'overlay
« génération de commentaires ». Instanciable 2× (vue avancée IA/stable ; la
fenêtre stable passe `can_regenerate=False` — pas de ↻). Le panneau possède
SON timer d'animation pour le voile (le timer du studio ne sert plus qu'à la
ligne animée du journal).

Frontière : le studio se connecte DIRECTEMENT à `panel.editor.*` (signaux
d'aide/verrou) et aux signaux `regen_requested`/`delete_requested` du
`panel.feature_dropdown` (actions métier ↻/🗑 posées SUR CHAQUE LIGNE du popup,
émises pour UNE fonctionnalité à la fois) ; le dropdown est PLACÉ hors panneau
par le studio (ligne d'outils) mais ses `selection_changed`/`hover_preview`
sont consommés EN INTERNE (surlignage par fonctionnalité + scroll)."""
from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget,
)

from ..code_editor import CodeEditor
from ..feature_dropdown import FeatureDropdown
from ..i18n import lang_manager
from ..robot_loader import LoaderLabel, RobotLoader
from ..theme import feature_color, theme_manager


class CodePanel(QWidget):
    def __init__(self, embed_chips: bool = True,
                 can_regenerate: bool = True, parent=None):
        super().__init__(parent)
        self._can_regenerate = can_regenerate
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # Sélecteur des fonctionnalités générées (dropdown cochable). Le
        # panneau le CRÉE et câble le surlignage, mais le studio le PLACE
        # lui-même hors panneau (ligne d'outils). `embed_chips` conservé pour
        # compat de signature ; il n'ajoute plus rien dans la colonne.
        self.feature_dropdown = FeatureDropdown(can_regenerate=can_regenerate)
        self.feature_dropdown.selection_changed.connect(self._on_chips_selection)
        self.feature_dropdown.hover_preview.connect(self._on_chips_hover)

        self.editor = CodeEditor()
        self.editor.setMinimumHeight(280)
        # Largeur : c'est l'éditeur qui CÈDE quand la place manque (la
        # colonne droite 380px ne doit jamais être rognée) ; plancher bas
        # (220) pour les cas extrêmes seulement.
        self.editor.setMinimumWidth(220)
        self.editor.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        lay.addWidget(self.editor, stretch=1)

        # État surlignage : fonctionnalités connues + sélection/survol puces.
        self._features: list = []
        self._selected_ids: list[str] = []
        self._hover_id: str = ""

        # Overlay « génération de commentaires » : petite carte ancrée en
        # haut à droite de l'éditeur (remplace l'ancien curseur sablier
        # global). Enfant de l'éditeur -> rendue au-dessus du code.
        self._cmt_overlay = QFrame(self.editor)
        self._cmt_overlay.setObjectName("cmtOverlay")
        self._cmt_overlay.setVisible(False)
        _ov = QHBoxLayout(self._cmt_overlay)
        _ov.setContentsMargins(12, 7, 12, 7)
        _ov.setSpacing(8)
        self._robot_cmt = RobotLoader(point_size=12)
        _ov.addWidget(self._robot_cmt)
        self._lbl_cmt_text = LoaderLabel(point_size=10)
        _ov.addWidget(self._lbl_cmt_text)

        # Voile « busy » : pendant une opération (génération / vérif /
        # compile / upload), couvre le code (édition impossible) avec le
        # robot + un texte centré. Enfant de l'éditeur, pleine surface.
        self._veil = QFrame(self.editor)
        self._veil.setObjectName("codeVeil")
        self._veil.setVisible(False)
        _vl = QVBoxLayout(self._veil)
        _vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _vl.setSpacing(10)
        self._veil_robot = RobotLoader(point_size=22)
        self._veil_text = LoaderLabel(point_size=11)
        _vl.addWidget(self._veil_robot, alignment=Qt.AlignmentFlag.AlignHCenter)
        _vl.addWidget(self._veil_text, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._veil_on = False
        self._veil_text_base = ""
        self._veil_idx = 0
        self._veil_timer = QTimer(self)
        self._veil_timer.setInterval(250)   # vitesse robot (cf. RobotLoader)
        self._veil_timer.timeout.connect(self._tick_veil)

        # Reposition des overlays au resize de l'éditeur.
        self.editor.installEventFilter(self)

        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)

    # ── API ────────────────────────────────────────────────────────────

    def set_features(self, features, busy: bool = False):
        """Peuple le dropdown des fonctionnalites (place hors panneau par le
        studio). busy=True grise le bouton dropdown et replie le popup (donc
        ses actions ↻/🗑 par ligne deviennent inaccessibles)."""
        self._features = list(features)
        self.feature_dropdown.set_features(features)
        self.feature_dropdown.set_busy(busy)
        present = {f.id for f in self._features}
        self._selected_ids = [i for i in self._selected_ids if i in present]
        self.refresh_highlights()

    def set_busy(self, text: str | None):
        """Voile busy : `text` -> voile affiché avec ce libellé (l'édition
        est bloquée par readOnly, restauré à la levée — le verrou
        intermédiaire passe par set_locked, indépendant) ; None -> levé."""
        if text is not None:
            self._veil_text_base = text.rstrip("…. ")
            if not self._veil_on:
                self._veil_on = True
                self.editor.setReadOnly(True)        # édition bloquée
                self._veil_robot.show()
                self._veil_text.show()
                self._veil.setGeometry(self.editor.rect())
                self._veil.setVisible(True)
                self._veil.raise_()
                self._veil_idx = 0
                self._tick_veil()
                self._veil_timer.start()
        elif self._veil_on:
            self._veil_on = False
            self._veil.setVisible(False)
            # L'éditeur n'est jamais read-only par mode (l'intermédiaire
            # passe par set_edit_locked) -> on le restaure éditable.
            self.editor.setReadOnly(False)
            self._veil_timer.stop()
        # Le dropdown se grise et replie son popup pendant l'opération (ses
        # actions ↻/🗑 par ligne deviennent donc inaccessibles).
        self.feature_dropdown.set_busy(self._veil_on)

    def is_busy(self) -> bool:
        return self._veil_on

    def set_locked(self, locked: bool):
        """Verrou d'édition du mode intermédiaire : l'édition est bloquée
        (popup via edit_attempted) mais le curseur/sélection/copie restent
        disponibles (≠ readOnly)."""
        self.editor.set_edit_locked(locked)

    def refresh_highlights(self, features=None):
        """(Re)pose les fonds de ligne : ids sélectionnés + survol courant,
        chacun à la couleur de sa puce (feature_color, dérivée de l'ID —
        stable à travers réordres/suppressions). `features` (optionnel)
        resynchronise la liste de référence AVANT le rendu (cf.
        _set_code_with_attribution appelé pendant une vérif alors qu'une
        puce est sélectionnée)."""
        if features is not None:
            self._features = list(features)
        wanted = set(self._selected_ids)
        if self._hover_id:
            wanted.add(self._hover_id)
        colors: dict[str, QColor] = {}
        for f in self._features:
            if f.id in wanted:
                colors[f.id] = QColor(feature_color(f.id))
        self.editor.set_feature_highlights(colors)

    def clear_selection(self):
        """Réinitialise sélection + survol (changement de projet) : sinon la
        teinte de l'ANCIEN projet survivrait sur le nouveau (ids f1/f2
        génériques). Efface aussi les fonds de ligne."""
        self._selected_ids = []
        self._hover_id = ""
        self.feature_dropdown.clear_selection()
        self.refresh_highlights()

    def show_comment_loader(self, show: bool):
        """Carte loader « génération des commentaires » en haut à droite."""
        if show:
            self._lbl_cmt_text.set_text(lang_manager.current.studio_addcmt_loading)
            self._robot_cmt.start()
            self._lbl_cmt_text.start()
            self._reposition_cmt_overlay()
            self._cmt_overlay.setVisible(True)
            self._cmt_overlay.raise_()
        else:
            self._robot_cmt.stop()
            self._lbl_cmt_text.stop()
            self._cmt_overlay.setVisible(False)

    # ── Interne ────────────────────────────────────────────────────────

    def _on_chips_selection(self, ids: list):
        """Sélection de puces -> surlignage persistant + scroll vers la
        première ligne de la dernière puce nouvellement sélectionnée."""
        prev = set(self._selected_ids)
        self._selected_ids = list(ids)
        self.refresh_highlights()
        new_ids = [i for i in ids if i not in prev]
        if new_ids:
            self.editor.scroll_to_first_owned(new_ids[-1])

    def _on_chips_hover(self, fid: str):
        """Survol d'une puce = aperçu temporaire ADDITIF (retombe au leave,
        la sélection persistante reste)."""
        self._hover_id = fid
        self.refresh_highlights()

    def _tick_veil(self):
        i = self._veil_idx
        self._veil_idx += 1
        self._veil_robot.setText(RobotLoader.FRAMES[i % len(RobotLoader.FRAMES)])
        self._veil_text.setText(self._veil_text_base + "." * (i % 4))

    def _reposition_cmt_overlay(self):
        """Ancre l'overlay en haut à droite de l'éditeur (marge 12 px)."""
        self._cmt_overlay.adjustSize()
        m = 12
        x = self.editor.width() - self._cmt_overlay.width() - m
        self._cmt_overlay.move(max(m, x), m)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.editor and event.type() == QEvent.Type.Resize:
            if self._cmt_overlay.isVisible():
                self._reposition_cmt_overlay()
            # Le voile doit toujours couvrir tout l'éditeur.
            if self._veil_on:
                self._veil.setGeometry(self.editor.rect())
        return super().eventFilter(obj, event)

    def apply_theme(self, c):
        # Carte loader commentaires : opaque, texte + spinner en vert
        # phosphore (signal_ok).
        self._cmt_overlay.setStyleSheet(f"""
            QFrame#cmtOverlay {{
                background-color: {c.sidebar_bg};
                border: 1px solid {c.border};
                border-radius: 8px;
            }}
            QLabel {{
                background: transparent; color: {c.signal_ok};
                font-size: 10pt; font-weight: 600;
            }}
        """)
        self._robot_cmt.set_color(c.signal_ok)
        self._lbl_cmt_text.set_color(c.signal_ok)
        # Voile busy : noir semi-transparent -> le code reste devinable
        # dessous mais l'édition est bloquée ; robot + texte en phosphore.
        self._veil.setStyleSheet(
            "QFrame#codeVeil { background-color: rgba(0, 0, 0, 0.85); }"
        )
        self._veil_robot.set_color(c.signal_ok)
        self._veil_text.set_color(c.signal_ok)

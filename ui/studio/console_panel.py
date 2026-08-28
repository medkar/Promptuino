"""ConsolePanel — journal fusionné + moniteur série (Prompt 2 du plan
PATHFINDER-2026-07-05).

Un seul composant pour le couple « LogWidget + SerialMonitorWidget » qui
était construit et câblé À LA MAIN dans deux zones de studio_view (débutant
et colonne droite int/avancé) : data_received→append_serial, autoscroll,
en-tête « Sortie console » à l'ouverture du port. Le moniteur série est le
MOTEUR (worker/port) : son affichage interne est masqué, la sortie série va
dans le journal fusionné ; ses contrôles sont placés soit dans une barre
fixe en bas du journal (`serial_bar_in_log=True`, variante int/avancé),
soit là où l'appelant veut (variante débutant : title row du studio)."""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from ..i18n import lang_manager
from ..serial_monitor import SerialMonitorWidget
from .log_widget import LogWidget


class ConsolePanel(QWidget):
    # Relais des signaux du journal (mêmes noms/contrats que LogWidget)
    # + de la connexion série, pour que l'appelant ne câble que le panel.
    help_with_error_requested = pyqtSignal(str)
    action_clicked = pyqtSignal(str)
    connection_changed = pyqtSignal(bool)

    def __init__(self, serial_bar_in_log: bool = False, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.log = LogWidget()
        # #9 : plancher de hauteur pour que le journal reste lisible au
        # rétrécissement (≤ ce que le plancher éditeur laisse à la colonne).
        self.log.setMinimumHeight(110)
        lay.addWidget(self.log)

        self.serial = SerialMonitorWidget()
        self.serial.set_title_visible(False)
        self.serial.set_display_visible(False)

        # Câblage UNIQUE journal<->série (était dupliqué dans les 2 zones) :
        self.serial.data_received.connect(self.log.append_serial)
        self.serial.autoscroll_changed.connect(self.log.set_auto_scroll)
        self.log.set_auto_scroll(self.serial.is_autoscroll())
        self.serial.connection_changed.connect(self._on_connection_changed)

        self.log.help_with_error_requested.connect(self.help_with_error_requested)
        self.log.action_clicked.connect(self.action_clicked)

        if serial_bar_in_log:
            # Barre FIXE en bas du journal, HORS défilement : 2 rangées
            # (contrôles Connecter|auto-scroll|baud, puis ligne d'envoi).
            bar = QWidget()
            v = QVBoxLayout(bar)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(6)
            v.addWidget(self.serial.get_ctrl_widget())
            v.addWidget(self.serial.get_send_widget())
            self.log.set_bottom_bar(bar)

    def _on_connection_changed(self, connected: bool):
        """Ouverture du port -> en-tête coloré « Sortie console : » pour
        séparer visuellement le journal compile/upload de la sortie série
        (orange : distinct des phases compile/upload et du vert succès)."""
        if connected:
            self.log.begin_serial_section(
                lang_manager.current.serial_console_header, "#f97316")
        self.connection_changed.emit(connected)

    # ── API pour compile_service / studio ─────────────────────────────

    def close_serial(self):
        """Ferme le port s'il est ouvert (libère le port pour arduino-cli)."""
        if self.serial.is_open():
            self.serial.close_port()

    def clear_for_operation(self):
        """Prépare la console pour une nouvelle opération : port fermé +
        journal vidé (les boutons d'action sont réinitialisés par clear)."""
        self.close_serial()
        self.log.clear()

    def reopen_on_success(self):
        """Rouvre le port série — à n'appeler QUE sur succès d'upload (sur
        échec/annulation la carte garde son ancien firmware : reconnecter
        ferait croire à un upload réussi)."""
        self.serial.open_port()

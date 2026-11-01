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

        self._serial_bar = None
        self.set_serial_bar_in_log(serial_bar_in_log)

    def set_serial_bar_in_log(self, in_log: bool) -> None:
        """Place les contrôles série DANS le journal, ou les en retire.

        TODO #99 (2026-09-08). C'est le « changement d'habit » qui permet à UNE
        SEULE console de servir les trois modes. Avant, l'habit était figé à la
        construction (`serial_bar_in_log`), donc le mode Débutant — qui place
        ses contrôles dans sa ligne de titre plutôt que sous le journal —
        exigeait une SECONDE `ConsolePanel`. Deux consoles, c'est deux
        journaux et deux ports : passer en Débutant coupait la liaison série
        en cours et changeait de transcription.

        `in_log=False` ne détruit rien : le widget de contrôles reste vivant et
        l'appelant est libre de le monter où il veut. C'est ce qui permet
        l'aller-retour entre modes sans jamais fermer le port.
        """
        if in_log:
            if self._serial_bar is None:
                bar = QWidget()
                v = QVBoxLayout(bar)
                v.setContentsMargins(0, 0, 0, 0)
                v.setSpacing(6)
                v.addWidget(self.serial.get_ctrl_widget())
                v.addWidget(self.serial.get_send_widget())
                self._serial_bar = bar
            else:
                # Les contrôles ont pu être reparentés ailleurs entre-temps :
                # on les réclame, sinon la barre se remonte vide.
                lay = self._serial_bar.layout()
                lay.addWidget(self.serial.get_ctrl_widget())
                lay.addWidget(self.serial.get_send_widget())
            self.log.set_bottom_bar(self._serial_bar)
        else:
            self.log.set_bottom_bar(None)

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

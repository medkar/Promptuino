"""La section « Compte ChatGPT » de l'ecran Modele IA (TODO #122).

Troisieme choix radio, a cote de Cloud et Local (decision de l'auteur). Meme
SURFACE que les autres sections, parce que `IAView` et la pastille les lisent
indifferemment : `radio`, `backend_id`, `_availability_state`, `load_key`,
`refresh_availability`, `apply_theme`, `apply_lang`.

Regles du guide d'interface d'OpenAI (developers.openai.com/siwc/
ui-ux-guidelines) : bouton « Continue with ChatGPT » ; « Using ChatGPT plan »
pres du choix du modele avec « Manage usage » ; fenetre d'accueil UNE seule
fois. Les libelles sont traduits dans les 4 langues, « ChatGPT » jamais.

⛔ Aucun appel reseau a la construction : la vue est construite au demarrage
de l'app. L'etat se lit dans le trousseau (`chatgpt_auth.session.compte()`) ;
la liste des modeles n'est demandee qu'a l'ouverture du menu ou apres une
connexion, dans un fil.
"""
from __future__ import annotations

import webbrowser

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QRadioButton,
    QSlider, QVBoxLayout, QWidget,
)

from . import chatgpt_auth
from .ai_config import ai_config
from .i18n import Strings, lang_manager
from .molette import ComboSansMolette, SliderSansMolette
from .reflexion import NIVEAUX_CHATGPT
from .taches_fond import lancer_en_fond
from .theme import (ColorScheme, combo_qss, primary_button_qss,
                    radio_checkbox_qss, secondary_button_qss, slider_qss,
                    theme_manager)


class _ComboModeles(ComboSansMolette):
    """Relit la liste a l'ouverture : le catalogue depend du compte."""

    def __init__(self, a_l_ouverture, parent=None):
        super().__init__(parent)
        self._a_l_ouverture = a_l_ouverture

    def showPopup(self):
        self._a_l_ouverture()
        super().showPopup()


class FenetreAccueil(QDialog):
    """« You're using your ChatGPT plan » + « Got it » — une seule fois."""

    def __init__(self, parent=None):
        super().__init__(parent)
        s, c = lang_manager.current, theme_manager.current
        self.setWindowTitle(s.ia_chatgpt_welcome_title)
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 16)
        lay.setSpacing(12)
        titre = QLabel(s.ia_chatgpt_welcome_title)
        titre.setStyleSheet(f"font-size: 13pt; font-weight: 700; color: {c.text_primary};")
        lay.addWidget(titre)
        texte = QLabel(s.ia_chatgpt_welcome_text)
        texte.setWordWrap(True)
        texte.setStyleSheet(f"font-size: 10pt; color: {c.text_secondary};")
        lay.addWidget(texte)
        bas = QHBoxLayout()
        bas.addStretch()
        self.bouton = QPushButton(s.ia_chatgpt_welcome_ok)
        self.bouton.setAutoDefault(False)
        self.bouton.setStyleSheet(primary_button_qss(c))
        self.bouton.clicked.connect(self.accept)
        bas.addWidget(self.bouton)
        lay.addLayout(bas)
        self.setStyleSheet(f"QDialog {{ background-color: {c.main_bg}; }}")


class ChatGPTSection(QWidget):
    model_changed = pyqtSignal(str)
    # Une connexion vient de reussir : `IAView` coche et active ce choix.
    connecte = pyqtSignal()
    # Le niveau de reflexion a change : `IAView` recree le moteur actif.
    reglage_change = pyqtSignal()

    def __init__(self, parent=None, *, session=None, ouvrir=None,
                 accueil=None):
        super().__init__(parent)
        self.backend_id = "chatgpt"
        self._session = session or chatgpt_auth.session
        # Injectables pour les tests : le navigateur et la fenetre d'accueil.
        self._ouvrir = ouvrir or webbrowser.open
        self._accueil = accueil or (lambda: FenetreAccueil(self).exec())
        self._availability_state: "tuple[str, str | None] | None" = None
        self._en_connexion = False
        self._annule = False
        self._erreur = ""
        self._build()
        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)
        self.refresh_availability()

    # ── Construction ──────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.radio = QRadioButton()
        self.radio.setCursor(Qt.CursorShape.PointingHandCursor)
        root.addWidget(self.radio)
        root.addSpacing(6)

        contenu = QWidget()
        lay = QVBoxLayout(contenu)
        lay.setContentsMargins(28, 0, 0, 0)
        lay.setSpacing(8)
        root.addWidget(contenu)

        self._lbl_sous_titre = QLabel()
        self._lbl_sous_titre.setWordWrap(True)
        lay.addWidget(self._lbl_sous_titre)

        # Deconnecte : le bouton officiel, et l'attente pendant la connexion.
        rang = QHBoxLayout()
        self._btn_connecter = QPushButton()
        self._btn_connecter.setFixedHeight(34)
        self._btn_connecter.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_connecter.setAutoDefault(False)
        self._btn_connecter.clicked.connect(self._connecter)
        rang.addWidget(self._btn_connecter)
        self._btn_annuler = QPushButton()
        self._btn_annuler.setAutoDefault(False)
        self._btn_annuler.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_annuler.clicked.connect(self._annuler)
        self._btn_annuler.hide()
        rang.addWidget(self._btn_annuler)
        rang.addStretch(1)
        lay.addLayout(rang)

        # Connecte : le compte, puis le modele.
        rang_compte = QHBoxLayout()
        self._lbl_compte = QLabel()
        rang_compte.addWidget(self._lbl_compte, 1)
        self._btn_deconnecter = QPushButton()
        self._btn_deconnecter.setAutoDefault(False)
        self._btn_deconnecter.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_deconnecter.clicked.connect(self._deconnecter)
        rang_compte.addWidget(self._btn_deconnecter)
        self._zone_compte = QWidget()
        self._zone_compte.setLayout(rang_compte)
        rang_compte.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._zone_compte)

        rang_modele = QHBoxLayout()
        rang_modele.setContentsMargins(0, 0, 0, 0)
        self._lbl_modele = QLabel()
        self._lbl_modele.setFixedWidth(56)
        rang_modele.addWidget(self._lbl_modele)
        self._combo = _ComboModeles(self._relire_modeles)
        self._combo.setFixedHeight(34)
        self._combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._combo.textActivated.connect(self._modele_choisi)
        rang_modele.addWidget(self._combo, 1)
        self._zone_modele = QWidget()
        self._zone_modele.setLayout(rang_modele)
        lay.addWidget(self._zone_modele)

        # Le niveau de reflexion (TODO #123, decision de l'auteur : « un
        # slider ») : trois crans, comme la maquette d'OpenAI (« Model
        # speed : Instant / Medium / High »), visible avec le choix du modele.
        self._zone_reflexion = QWidget()
        lay_r = QVBoxLayout(self._zone_reflexion)
        lay_r.setContentsMargins(0, 4, 0, 0)
        lay_r.setSpacing(2)
        self._lbl_reflexion = QLabel()
        lay_r.addWidget(self._lbl_reflexion)
        self._curseur = SliderSansMolette(Qt.Orientation.Horizontal)
        self._curseur.setRange(0, len(NIVEAUX_CHATGPT) - 1)
        self._curseur.setSingleStep(1)
        self._curseur.setPageStep(1)
        self._curseur.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._curseur.setTickInterval(1)
        self._curseur.setCursor(Qt.CursorShape.PointingHandCursor)
        self._curseur.valueChanged.connect(self._cran_bouge)
        self._curseur.sliderReleased.connect(self._cran_lache)
        lay_r.addWidget(self._curseur)
        crans = QHBoxLayout()
        # 3 px a droite : le « é » final d'« Élevé » deborde de sa chasse et
        # etait rogne au bord de la section (capture du 2026-11-06).
        crans.setContentsMargins(0, 0, 3, 0)
        self._lbl_crans = [QLabel() for _ in NIVEAUX_CHATGPT]
        for i, lbl in enumerate(self._lbl_crans):
            if i:
                crans.addStretch(1)
            crans.addWidget(lbl)
        lay_r.addLayout(crans)
        self._lbl_reflexion_aide = QLabel()
        self._lbl_reflexion_aide.setWordWrap(True)
        lay_r.addWidget(self._lbl_reflexion_aide)
        lay.addWidget(self._zone_reflexion)
        # La pastille du chat ou de la generation fait defiler les niveaux
        # (P3, 2026-11-07) : le curseur suit, sans rien ecrire.
        from .thinking_etat import thinking_etat
        thinking_etat.change.connect(
            lambda: self._rendre_reflexion(lang_manager.current,
                                           theme_manager.current))

        # « Using ChatGPT plan · Manage usage », pres du choix du modele.
        self._lbl_forfait = QLabel()
        self._lbl_forfait.setTextFormat(Qt.TextFormat.RichText)
        self._lbl_forfait.setOpenExternalLinks(True)
        lay.addWidget(self._lbl_forfait)

        self._lbl_etat = QLabel()
        self._lbl_etat.setWordWrap(True)
        self._lbl_etat.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self._lbl_etat)

    # ── Etat ──────────────────────────────────────────────────
    def refresh_availability(self):
        """Aucun reseau : le trousseau et la configuration suffisent."""
        compte = self._session.compte()
        if not compte:
            etat = ("chatgpt_signed_out", None)
        elif not compte.get("forfait"):
            etat = ("chatgpt_no_plan", compte.get("email") or "")
        elif not ai_config.chatgpt_model:
            etat = ("chatgpt_no_model", compte.get("email") or "")
        else:
            etat = ("chatgpt_ok", compte.get("email") or "")
        self._availability_state = etat
        if ai_config.backend_id == self.backend_id:
            from .ai_status import ai_status
            ai_status.set_state(etat[0])
        self._rendre()

    def _rendre(self):
        if self._availability_state is None:
            return
        s, c = lang_manager.current, theme_manager.current
        genre, email = self._availability_state
        connecte = genre != "chatgpt_signed_out"
        avec_forfait = genre in ("chatgpt_no_model", "chatgpt_ok")
        # Deconnecte, ou connecte SANS le forfait : il faut (re)passer par OpenAI.
        self._btn_connecter.setVisible(not avec_forfait)
        self._btn_connecter.setEnabled(not self._en_connexion)
        self._btn_connecter.setText(s.ia_chatgpt_waiting if self._en_connexion
                                    else s.ia_chatgpt_connect)
        self._btn_annuler.setVisible(self._en_connexion)
        self._zone_compte.setVisible(connecte)
        self._lbl_compte.setText(s.ia_chatgpt_signed_in.format(email=email or "?"))
        self._zone_modele.setVisible(avec_forfait)
        self._zone_reflexion.setVisible(avec_forfait)
        self._rendre_reflexion(s, c)
        self._lbl_forfait.setVisible(avec_forfait)
        lien = (f'<a href="{chatgpt_auth.PAGE_USAGE}" style="color: {c.accent};">'
                f'{s.ia_chatgpt_manage_usage}</a>')
        self._lbl_forfait.setText(
            f'<span style="color:{c.text_secondary};">{s.ia_chatgpt_using_plan}</span>'
            f' · {lien}')
        if self._erreur:
            texte, couleur = self._erreur, c.signal_error
        elif genre == "chatgpt_no_plan":
            texte, couleur = s.ia_chatgpt_no_plan, c.signal_error
        elif genre == "chatgpt_no_model":
            texte, couleur = s.ia_chatgpt_no_model, c.signal_error
        elif genre == "chatgpt_ok":
            texte, couleur = s.ia_chatgpt_ok, c.signal_ok
        else:
            texte, couleur = "", c.text_secondary
        self._lbl_etat.setText(
            f'<span style="color:{couleur};">&#9679; {texte}</span>' if texte else "")
        if self._combo.count() == 0 and ai_config.chatgpt_model:
            self._combo.addItem(ai_config.chatgpt_model)

    # ── Niveau de reflexion ───────────────────────────────────
    def _rendre_reflexion(self, s: Strings, c: ColorScheme):
        """Position, libelles et aide ; n'ecrit rien."""
        from .ai_backends.chatgpt_plan import reflexion_refusee
        self._curseur.blockSignals(True)
        self._curseur.setValue(NIVEAUX_CHATGPT.index(ai_config.chatgpt_reasoning))
        self._curseur.blockSignals(False)
        self._lbl_reflexion.setText(s.chatgpt_reasoning_label)
        for lbl, texte in zip(self._lbl_crans, (s.chatgpt_level_low,
                                                s.chatgpt_level_medium,
                                                s.chatgpt_level_high)):
            lbl.setText(texte)
        refuse = reflexion_refusee(ai_config.chatgpt_model)
        self._lbl_reflexion_aide.setText(s.chatgpt_reasoning_refused if refuse
                                         else s.chatgpt_reasoning_help)
        self._lbl_reflexion_aide.setStyleSheet(
            f"color: {c.signal_warn if refuse else c.text_secondary}; font-size: 9pt;")

    def _cran_bouge(self, _v: int):
        if not self._curseur.isSliderDown():   # clavier, clic, molette
            self._cran_choisi()

    def _cran_lache(self):
        self._cran_choisi()

    def _cran_choisi(self):
        niveau = NIVEAUX_CHATGPT[self._curseur.value()]
        if niveau != ai_config.chatgpt_reasoning:
            ai_config.chatgpt_reasoning = niveau
            self.reglage_change.emit()

    # ── Connexion ─────────────────────────────────────────────
    def _connecter(self):
        if self._en_connexion:
            return
        self._en_connexion, self._annule, self._erreur = True, False, ""
        self._rendre()
        s = lang_manager.current
        page = ("<!doctype html><html><head><meta charset='utf-8'>"
                "<title>Promptuino</title></head>"
                "<body style='font-family:sans-serif;margin:3em'>"
                f"<h2>Promptuino</h2><p>{s.ia_chatgpt_page}</p></body></html>")
        session, ouvrir = self._session, self._ouvrir
        lancer_en_fond(
            "connexion",
            lambda: session.connecter(ouvrir, page_html=page,
                                      annule=lambda: self._annule),
            self._apres_connexion)

    def _annuler(self):
        self._annule = True

    def _apres_connexion(self, paquet):
        _e, r = paquet
        s = lang_manager.current
        self._en_connexion = False
        if not isinstance(r, dict):
            r = {"ok": False, "erreur": "echange", "message": str(r)}
        if r.get("ok"):
            self._erreur = ""
            if r.get("forfait") and not ai_config.chatgpt_welcome_shown:
                ai_config.chatgpt_welcome_shown = True
                self._accueil()
            self.refresh_availability()
            self._relire_modeles()
            self.connecte.emit()
            return
        # Une phrase simple et traduite, JAMAIS le code d'OpenAI (consigne de
        # l'auteur, 2026-11-06 : « pas besoin d'afficher les erreurs » ; vu en
        # QA : « OpenAI a refuse la connexion : invalid_grant »). Un compte
        # gratuit est refuse a l'autorisation par OpenAI lui-meme (QA AW4).
        self._erreur = {
            "annule": "",
            "delai": s.ia_chatgpt_err_timeout,
            "refus": s.ia_chatgpt_err_refused,
            "etat": s.ia_chatgpt_err_check,
            "nonce": s.ia_chatgpt_err_check,
        }.get(r.get("erreur"), s.ia_chatgpt_err_exchange)
        self.refresh_availability()

    def _deconnecter(self):
        self._session.deconnecter()
        self._erreur = ""
        self._combo.clear()
        self.refresh_availability()

    # ── Modeles ───────────────────────────────────────────────
    def _relire_modeles(self):
        if not self._session.compte():
            return
        from .ai_backends.chatgpt_plan import ChatGPTPlanBackend
        backend = ChatGPTPlanBackend(ai_config.chatgpt_model, session=self._session)
        lancer_en_fond("modeles", backend.list_models_detailed, self._apres_modeles)

    def _apres_modeles(self, paquet):
        _e, r = paquet
        modeles = r[0] if isinstance(r, tuple) else []
        garde = ai_config.chatgpt_model
        if garde and garde not in modeles:
            modeles = [garde] + list(modeles)
        actuel = self._combo.currentText()
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItems(modeles)
        if garde in modeles:
            self._combo.setCurrentText(garde)
        elif actuel in modeles:
            self._combo.setCurrentText(actuel)
        self._combo.blockSignals(False)

    def _modele_choisi(self, texte: str):
        modele = texte.strip()
        if not modele:
            return
        ai_config.chatgpt_model = modele
        self.refresh_availability()
        self.model_changed.emit(modele)

    # ── Surface commune ───────────────────────────────────────
    def load_key(self):
        """Aucun reseau ici : le modele enregistre suffit a remplir le choix."""
        if ai_config.chatgpt_model and self._combo.count() == 0:
            self._combo.addItem(ai_config.chatgpt_model)
        self.refresh_availability()

    def apply_theme(self, c: ColorScheme):
        self.radio.setStyleSheet(radio_checkbox_qss(c, font_pt=14, font_weight=700))
        self._lbl_sous_titre.setStyleSheet(f"color: {c.text_secondary}; font-size: 10pt;")
        self._lbl_compte.setStyleSheet(f"color: {c.text_primary}; font-size: 10pt;")
        self._lbl_modele.setStyleSheet(f"color: {c.text_secondary}; font-size: 10pt;")
        self._lbl_reflexion.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 10pt; font-weight: 600;")
        for lbl in self._lbl_crans:
            lbl.setStyleSheet(f"color: {c.text_secondary}; font-size: 9pt;")
        self._curseur.setStyleSheet(slider_qss(c))
        self._lbl_forfait.setStyleSheet("font-size: 9pt;")
        self._lbl_etat.setStyleSheet("font-size: 9pt;")
        self._combo.setStyleSheet(combo_qss(c))
        self._btn_connecter.setStyleSheet(primary_button_qss(c))
        self._btn_annuler.setStyleSheet(secondary_button_qss(c))
        self._btn_deconnecter.setStyleSheet(secondary_button_qss(c))
        self._rendre()

    def apply_lang(self, s: Strings):
        self.radio.setText(s.ia_chatgpt_title)
        self._lbl_sous_titre.setText(s.ia_chatgpt_subtitle)
        self._lbl_modele.setText(s.ia_ollama_model_label)   # « Modele », commun
        self._btn_annuler.setText(s.md_cancel)
        self._btn_deconnecter.setText(s.ia_chatgpt_sign_out)
        self._rendre()

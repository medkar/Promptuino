"""Telecharger un modele Ollama sans passer par un terminal.

Trois sections, qui repondent a trois situations reelles :

1. **Suggeres** — je ne sais pas quoi prendre. Critere : la TAILLE, pour que
   ca tienne dans une carte modeste. ⚠️ Pas un classement de qualite : le
   projet n'a evalue que sa valeur par defaut, et la note sous le titre le dit
   a l'utilisateur au lieu de le laisser croire.
2. **Deja telecharges** — informatif, avec la taille EXACTE (`/api/tags`).
3. **Un autre modele** — je sais ce que je veux. ⚠️ Cette section TELECHARGE
   elle aussi : renvoyer vers un terminal ici aurait rendu la commande
   precisement a l'utilisateur le plus susceptible de vouloir un modele
   precis. Le site sert a TROUVER le nom, pas a installer.

⚠️ La taille d'un modele non telecharge est INCONNUE de l'app (aucune API de
catalogue, cf. `ui/ollama_models.py`) : les valeurs des suggeres sont
indicatives, d'ou le `~`. Celles des modeles locaux sont exactes.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QProgressBar, QFrame, QScrollArea, QWidget,
)

# La valeur par defaut vit dans ai_config._DEFAULTS : on la LIT plutot que
# d'en recopier le nom ici, sans quoi un changement de defaut laisserait le
# badge sur le mauvais modele.
from .ai_config import _DEFAULTS
from .i18n import lang_manager, Strings
from .ollama_models import (
    PAGE_LIBRARY, SUGGERES, espace_disque_libre, espace_partiels,
    espace_suffisant, modeles_locaux, supprimer_modele,
    supprimer_partiels, telecharger, tient_en_vram, vram_totale,
)
from . import icons as IC
from .theme import (ColorScheme, theme_manager, icon_button_qss, input_qss,
                    install_icon_hover, primary_button_qss,
                    secondary_button_qss)


def _go(octets: float) -> str:
    return f"{octets / 1e9:.1f} Go"


class _Worker(QThread):
    """Le telechargement bloque plusieurs minutes : jamais sur le fil graphique."""
    # ⛔ PAS `pyqtSignal(int, int, str)` : l'`int` d'un signal Qt est un entier
    # C++ de 32 bits. Le total de llama3.1:8b (4 920 000 000) DEBORDAIT et
    # ressortait a 625 032 704 -- le << 0,6 Go >> constate par l'utilisateur le
    # 2026-08-28, pendant que la fonction brute rendait 4,92. Un modele sous
    # 2 Gio passait sans deborder, ce qui a fait passer toutes les
    # verifications faites avec qwen2.5:0.5b. `object` transmet l'entier
    # Python tel quel.
    avance = pyqtSignal(object, object, str)
    fini = pyqtSignal(object)          # None = succes, sinon message d'erreur

    def __init__(self, nom: str, parent=None):
        super().__init__(parent)
        self._nom = nom
        self._stop = False

    def annuler(self):
        """Fermer le flux ARRETE reellement le serveur (mesure 2026-08-28)."""
        self._stop = True

    def run(self):
        err = telecharger(self._nom,
                          lambda r, t, e: self.avance.emit(r, t, e),
                          lambda: self._stop)
        self.fini.emit(err)


class ModelDownloadDialog(QDialog):
    """Modale de telechargement. `modele_installe` porte le nom obtenu."""

    modele_installe = pyqtSignal(str)
    modele_supprime = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMinimumWidth(560)
        self._worker: "_Worker | None" = None
        self._annule = False
        self._total_verifie = 0
        self._manque_espace = None
        self._vram = vram_totale()
        self._locaux = modeles_locaux()
        self._lignes: list = []
        self._build()
        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)

    # ── Construction ──────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 16)
        root.setSpacing(10)

        self._lbl_titre = QLabel()
        root.addWidget(self._lbl_titre)

        # ── 1. suggeres ───────────────────────────────────────
        self._lbl_sug = QLabel()
        root.addWidget(self._lbl_sug)
        self._lbl_sug_note = QLabel()
        self._lbl_sug_note.setWordWrap(True)
        self._lbl_sug_note.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(self._lbl_sug_note)

        # Liste BORNEE et defilante : 6 suggeres + la liste des locaux ont
        # fait deborder la fenetre des le premier utilisateur qui a telecharge
        # un modele de plus (capture du 2026-08-28, note d'annulation rognee).
        # objectName scope, comme `ambiguityScroll` : une regle sur le TYPE
        # QScrollArea s'echapperait dans les dialogues enfants (lecon payee).
        sug_host = QWidget()
        sh = QVBoxLayout(sug_host)
        sh.setContentsMargins(0, 0, 6, 0)
        sh.setSpacing(6)
        for nom, taille, params in SUGGERES:
            ligne = QHBoxLayout()
            ligne.setSpacing(8)
            # Icone AVANT le nom (demande utilisateur), le mot en infobulle.
            # `install_icon_hover` est l'idiome maison : les deux rendus
            # (repos / phosphore) sont pre-calcules et SWAPPES au survol --
            # un rendu SVG par evenement avait un lag visible au 1er survol.
            btn = QPushButton()
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setAutoDefault(False)
            btn.setFixedSize(26, 26)
            btn.clicked.connect(lambda _c=False, n=nom: self._lancer(n))
            install_icon_hover(btn, IC.DOWNLOAD, 16,
                               normal_role="text_secondary")
            ligne.addWidget(btn)
            lbl = QLabel()
            lbl.setTextFormat(Qt.TextFormat.RichText)
            ligne.addWidget(lbl, 1)
            sh.addLayout(ligne)
            self._lignes.append((nom, taille, params, lbl, btn))
        sh.addStretch(1)
        self._scroll_sug = QScrollArea()
        self._scroll_sug.setObjectName("mdScroll")
        self._scroll_sug.setWidgetResizable(True)
        self._scroll_sug.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_sug.setFixedHeight(184)
        self._scroll_sug.setWidget(sug_host)
        # Fond : a la PALETTE, regle maison. Le viewport du QScrollArea peint
        # sa couleur de base (noir en sombre) par-dessus le cadre -- les
        # regles QSS << transparent >> ne suffisent pas sur toutes les
        # plateformes de rendu (constate offscreen ET a l'ecran).
        self._scroll_sug.viewport().setAutoFillBackground(False)
        sug_host.setAutoFillBackground(False)
        self._cadre_sug = self._encadrer(self._scroll_sug)
        root.addWidget(self._cadre_sug)
        root.addSpacing(6)

        # ── 2. deja telecharges ───────────────────────────────
        self._lbl_dl = QLabel()
        root.addWidget(self._lbl_dl)
        # Lignes reconstruites par _rendre_listes (la liste bouge apres
        # chaque telechargement) -- MEME formatage que les suggeres.
        self._dl_host = QWidget()
        self._dl_lay = QVBoxLayout(self._dl_host)
        self._dl_lay.setContentsMargins(0, 0, 6, 0)
        self._dl_lay.setSpacing(6)
        self._scroll_dl = QScrollArea()
        self._scroll_dl.setObjectName("mdScroll")
        self._scroll_dl.setWidgetResizable(True)
        self._scroll_dl.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_dl.setFixedHeight(96)
        self._scroll_dl.setWidget(self._dl_host)
        self._scroll_dl.viewport().setAutoFillBackground(False)
        self._dl_host.setAutoFillBackground(False)
        self._cadre_dl = self._encadrer(self._scroll_dl)
        root.addWidget(self._cadre_dl)
        root.addSpacing(6)

        # ── 3. un autre modele ────────────────────────────────
        self._lbl_autre = QLabel()
        root.addWidget(self._lbl_autre)
        self._lbl_autre_aide = QLabel()
        self._lbl_autre_aide.setWordWrap(True)
        self._lbl_autre_aide.setTextFormat(Qt.TextFormat.RichText)
        self._lbl_autre_aide.setOpenExternalLinks(True)
        root.addWidget(self._lbl_autre_aide)

        rang = QHBoxLayout()
        self._champ = QLineEdit()
        self._champ.setPlaceholderText("llama3.1:8b")
        self._champ.returnPressed.connect(self._lancer_saisi)
        rang.addWidget(self._champ, 1)
        self._btn_autre = QPushButton()
        self._btn_autre.setAutoDefault(False)
        self._btn_autre.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_autre.clicked.connect(self._lancer_saisi)
        rang.addWidget(self._btn_autre)
        root.addLayout(rang)

        # ── Progression (masquee tant qu'on ne telecharge pas) ─
        self._zone = QWidget()
        zl = QVBoxLayout(self._zone)
        zl.setContentsMargins(0, 8, 0, 0)
        self._lbl_etat = QLabel()
        zl.addWidget(self._lbl_etat)
        self._barre = QProgressBar()
        self._barre.setObjectName("mdBar")
        self._barre.setFixedHeight(20)
        self._barre.setTextVisible(True)
        zl.addWidget(self._barre)
        self._lbl_note_annul = QLabel()
        self._lbl_note_annul.setWordWrap(True)
        zl.addWidget(self._lbl_note_annul)
        # ⚠️ Il n'existe aucune API pour liberer les partiels ; le module
        # supprime les fichiers `*-partial*` du dossier d'Ollama (mesure :
        # 22/22 serveur allume, 5 072 Mo rendus). Le prix, dit dans le
        # message : plus de reprise, un prochain essai repart de zero.
        self._btn_liberer = QPushButton()
        self._btn_liberer.setAutoDefault(False)
        self._btn_liberer.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_liberer.clicked.connect(self._liberer)
        self._btn_liberer.hide()
        zl.addWidget(self._btn_liberer, alignment=Qt.AlignmentFlag.AlignLeft)
        self._zone.hide()
        root.addWidget(self._zone)

        bas = QHBoxLayout()
        bas.addStretch()
        self._btn_annuler = QPushButton()
        self._btn_annuler.setAutoDefault(False)
        self._btn_annuler.clicked.connect(self._annuler)
        self._btn_annuler.hide()
        bas.addWidget(self._btn_annuler)
        self._btn_fermer = QPushButton()
        self._btn_fermer.setAutoDefault(False)
        self._btn_fermer.clicked.connect(self.accept)
        bas.addWidget(self._btn_fermer)
        root.addLayout(bas)

    def _encadrer(self, contenu: QWidget) -> QWidget:
        """Cadre de section : le motif de `_credits_host` de la fenetre
        « A propos » (surface + bordure + arrondi), deja valide a l'ecran --
        on ne re-invente pas un conteneur."""
        cadre = QWidget()
        cadre.setObjectName("mdCadre")
        # Sans cet attribut, un QWidget nu ne peint NI le fond NI la bordure
        # d'une regle venue d'une feuille ancetre.
        cadre.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(cadre)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.addWidget(contenu)
        return cadre

    # ── Telechargement ────────────────────────────────────────
    def _lancer_saisi(self):
        nom = self._champ.text().strip()
        if nom:
            self._lancer(nom)

    def _lancer(self, nom: str):
        if self._worker is not None and self._worker.isRunning():
            return
        # Refus AVANT lancement quand la taille est connue (suggeres).
        # ⚠️ Important ici plus qu'ailleurs : Ollama PREALLOUE le fichier
        # entier des les premieres secondes -- un modele trop gros ne
        # remplit pas le disque progressivement, il le sature d'un coup.
        taille_connue = next(
            (t for n, t, _p in SUGGERES if n == nom), None)
        if taille_connue and espace_suffisant(taille_connue) is False:
            self._refus_espace(taille_connue, indicatif=True)
            return
        self._total_verifie = 0
        self._en_cours = nom
        self._annule = False
        self._zone.show()
        self._barre.show()
        self._lbl_note_annul.setText("")
        self._btn_liberer.hide()
        self._btn_annuler.show()
        self._barre.setRange(0, 0)          # indetermine tant que `total` manque
        self._lbl_etat.setText(nom)
        self._basculer_boutons(False)
        self._worker = _Worker(nom, self)
        self._worker.avance.connect(self._avance)
        self._worker.fini.connect(self._fini)
        self._worker.start()

    def _avance(self, recu: int, total: int, etape: str):
        # Le `total` est CUMULE et GRANDIT a mesure que les blobs
        # s'annoncent (cf. `cumuler`) : la garde d'espace se rejoue a
        # chaque croissance -- verifier le seul premier blob laissait
        # passer un llama3.1:8b (0,6 Go annonces, 4,9 reels). La
        # preallocation des blobs deja partis a pu se produire ; le
        # bouton << Liberer l'espace >> la rattrape.
        if total > self._total_verifie:
            self._total_verifie = total
            if espace_suffisant(total) is False:
                self._manque_espace = total
                if self._worker is not None:
                    self._worker.annuler()
                return
        if total:
            self._barre.setRange(0, 100)
            self._barre.setValue(int(recu * 100 / total))
            self._lbl_etat.setText(
                f"{self._en_cours} — {_go(recu)} / {_go(total)}  ({etape})")
        else:
            self._lbl_etat.setText(f"{self._en_cours} — {etape}")

    def _fini(self, err):
        s = lang_manager.current
        self._btn_annuler.hide()
        self._basculer_boutons(True)
        if self._manque_espace:
            self._refus_espace(self._manque_espace, indicatif=False)
            self._manque_espace = None
            return
        # ⚠️ `telecharger` rend None DANS LES DEUX CAS -- succes et
        # annulation. Sans ce drapeau, annuler affichait
        # << Telechargement termine >>, ce qui est un mensonge et laissait
        # croire que le modele etait utilisable.
        if self._annule:
            self._lbl_etat.setText(s.md_cancelled)
            self._barre.hide()          # une barre figee a 10 % ment
            if espace_partiels() > 0:
                self._btn_liberer.show()
            self.adjustSize()
            return
        if err:
            self._lbl_etat.setText(s.md_failed.format(err=err))
            self._barre.setRange(0, 100)
            self._barre.setValue(0)
            if espace_partiels() > 0:
                self._btn_liberer.show()
            self.adjustSize()
            return
        self._lbl_etat.setText(s.md_done)
        self._barre.setRange(0, 100)
        self._barre.setValue(100)
        self._locaux = modeles_locaux()
        self._rendre_listes(s)
        self.modele_installe.emit(self._en_cours)

    def _refus_espace(self, taille: int, *, indicatif: bool):
        """Affiche le refus, avec les CHIFFRES -- pas un non sec."""
        s = lang_manager.current
        libre = espace_disque_libre()
        self._zone.show()
        self._barre.hide()
        self._btn_annuler.hide()
        self._basculer_boutons(True)
        prefixe = "~" if indicatif else ""
        self._lbl_etat.setText(s.md_no_space.format(
            taille=prefixe + _go(taille),
            libre=_go(libre) if libre else "?"))
        # Liberer d'anciens partiels est justement un moyen de faire de
        # la place : le bouton s'offre s'il y a quelque chose a rendre.
        if espace_partiels() > 0:
            self._btn_liberer.show()
        self.adjustSize()

    def _annuler(self):
        self._annule = True
        if self._worker is not None:
            self._worker.annuler()
        # ⚠️ On ne promet PAS de liberer l'espace : Ollama a deja reserve le
        # fichier entier. La note sous la barre le dit noir sur blanc.
        self._lbl_note_annul.setText(lang_manager.current.md_cancel_note)
        self.adjustSize()

    def _liberer(self):
        """Supprime les partiels et DIT ce qui s'est passe.

        ⚠️ `verrouilles` > 0 arrive juste apres une annulation (Windows
        garde brievement un verrou, constate en mesurant) : on le dit et
        on laisse le bouton pour reessayer, on ne boucle pas en silence.
        """
        if self._worker is not None and self._worker.isRunning():
            return
        s = lang_manager.current
        n, octets, verrouilles = supprimer_partiels()
        if verrouilles:
            self._lbl_note_annul.setText(s.md_free_locked)
        else:
            self._lbl_note_annul.setText(
                s.md_freed.format(n=n, taille=_go(octets)))
            self._btn_liberer.hide()
        self.adjustSize()

    def _supprimer(self, nom: str):
        """Confirme puis supprime. << Non >> est le bouton PAR DEFAUT.

        ⚠️ Si c'est le modele que Promptuino utilise (`ai_config.ollama_model`),
        la confirmation le DIT : la generation s'arretera jusqu'a nouveau
        choix. On n'interdit pas -- c'est sa machine -- mais on ne laisse pas
        decouvrir la panne apres coup.
        """
        if self._worker is not None and self._worker.isRunning():
            return
        from .ai_config import ai_config
        s = lang_manager.current
        taille = self._locaux.get(nom, (0, ""))[0]
        texte = s.md_delete_confirm.format(nom=nom, taille=_go(taille))
        if nom == ai_config.ollama_model:
            texte += s.md_delete_in_use
        # `ask_yes_no` est l'idiome maison EXACT de ce besoin : boutons
        # traduits dans la langue de l'APP (les standards Yes/No suivent la
        # locale SYSTEME, d'ou des boutons anglais releves par l'utilisateur),
        # style messagebox_qss, et << Non >> par defaut pour une suppression.
        # La premiere version reconstruisait tout ca a la main, en moins bien.
        from .message_box import ask_yes_no
        if not ask_yes_no(self, s.md_delete_title, texte, warning=True):
            return
        err = supprimer_modele(nom)
        if err:
            self._zone.show()
            self._barre.hide()
            self._lbl_etat.setText(s.md_failed.format(err=err))
            self.adjustSize()
            return
        self._zone.show()
        self._barre.hide()
        self._lbl_etat.setText(s.md_deleted.format(nom=nom))
        self._locaux = modeles_locaux()
        self._rendre_listes(s)
        self.adjustSize()
        self.modele_supprime.emit(nom)

    def _basculer_boutons(self, actifs: bool):
        for _n, _t, _p, _l, b in self._lignes:
            b.setEnabled(actifs and _n not in self._locaux)
        self._btn_autre.setEnabled(actifs)
        for b in getattr(self, "_btns_suppr", []):
            b.setEnabled(actifs)

    # ── Lang ──────────────────────────────────────────────────
    def apply_lang(self, s: Strings):
        self.setWindowTitle(s.md_title)
        self._lbl_titre.setText(s.md_title)
        self._lbl_sug.setText(s.md_suggested)
        self._lbl_sug_note.setText(s.md_suggested_note)
        self._lbl_dl.setText(s.md_downloaded)
        self._lbl_autre.setText(s.md_other)
        lien = (f'<a href="{PAGE_LIBRARY}" style="color: '
                f'{theme_manager.current.accent};">ollama.com/library</a>')
        self._lbl_autre_aide.setText(s.md_other_help.format(lien=lien))
        self._btn_autre.setText(s.md_download)
        self._btn_annuler.setText(s.md_cancel)
        self._btn_liberer.setText(s.md_free_space)
        self._btn_fermer.setText(s.md_close)
        self._rendre_listes(s)

    def _rendre_listes(self, s: Strings):
        """Les deux listes dependent de la langue ET de l'etat du disque."""
        for nom, taille, params, lbl, btn in self._lignes:
            local = nom in self._locaux
            vraie = self._locaux[nom][0] if local else None
            # Taille EXACTE si on l'a, indicative sinon (le `~` le dit).
            txt_taille = _go(vraie) if local else f"~{_go(taille)}"
            verdict = tient_en_vram(vraie or taille, self._vram)
            if verdict is True:
                suffixe = " · " + s.md_fits.format(vram=_go(self._vram))
            elif verdict is False:
                suffixe = " · " + s.md_too_big.format(vram=_go(self._vram))
            else:
                suffixe = ""            # on ne sait pas -> on se tait
            badge = (f" · {s.md_default_badge}"
                     if nom == _DEFAULTS.get("ollama_model") else "")
            lbl.setText(f"<b>{nom}</b> — {txt_taille} · {params}{badge}{suffixe}")
            # Un modele deja la : coche phosphore, infobulle, bouton inerte.
            # (Pose APRES le _rebuild du filtre de survol au changement de
            # theme : apply_theme rappelle _rendre_listes en dernier.)
            if local:
                btn.setEnabled(False)
                btn.setIcon(IC.make_icon(
                    IC.CHECK, theme_manager.current.signal_ok, 16))
                btn.setToolTip(s.md_already)
            else:
                btn.setEnabled(True)
                btn.setToolTip(s.md_download)

        self._btns_suppr = []
        # ⚠️ Vidage RECURSIF, et la recursion n'est pas un luxe : les lignes
        # sont des QHBoxLayout imbriques, sur lesquels `it.widget()` rend
        # None -- la premiere version ne detachait que les widgets directs,
        # et les enfants des layouts restaient parentes a l'hote, continuant
        # de SE PEINDRE par-dessus les nouvelles lignes (coche et corbeille
        # superposees, capture utilisateur du 2026-08-28). setParent(None)
        # AVANT deleteLater, lecon deja payee.
        def _vider(lay):
            while lay.count():
                it = lay.takeAt(0)
                w = it.widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()
                sous = it.layout()
                if sous is not None:
                    _vider(sous)
                    sous.deleteLater()
        _vider(self._dl_lay)
        c = theme_manager.current
        if not self._locaux:
            vide = QLabel(s.md_none)
            vide.setStyleSheet(
                f"font-size: 9pt; color: {c.text_secondary};"
                " background: transparent;")
            self._dl_lay.addWidget(vide)
        for n, (taille_l, params_l) in sorted(self._locaux.items()):
            ligne = QHBoxLayout()
            ligne.setSpacing(8)
            ic = QLabel()
            ic.setFixedSize(26, 26)
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ic.setPixmap(IC.make_icon(IC.CHECK, c.signal_ok, 16).pixmap(16, 16))
            ic.setToolTip(s.md_already)
            ic.setStyleSheet("background: transparent;")
            ligne.addWidget(ic)
            verdict_l = tient_en_vram(taille_l, self._vram)
            if verdict_l is True:
                suff = " · " + s.md_fits.format(vram=_go(self._vram))
            elif verdict_l is False:
                suff = " · " + s.md_too_big.format(vram=_go(self._vram))
            else:
                suff = ""
            morceau = f" · {params_l}" if params_l else ""
            lab = QLabel(f"<b>{n}</b> — {_go(taille_l)}{morceau}{suff}")
            lab.setTextFormat(Qt.TextFormat.RichText)
            lab.setStyleSheet(
                f"font-size: 9pt; color: {c.text_primary};"
                " background: transparent;")
            ligne.addWidget(lab, 1)
            # Corbeille : la confirmation porte le danger (<< Non >> par
            # defaut), pas l'icone -- meme discipline que les cles d'API a la
            # desinstallation (#78).
            btn_sup = QPushButton()
            btn_sup.setFixedSize(26, 26)
            btn_sup.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_sup.setAutoDefault(False)
            install_icon_hover(btn_sup, IC.X_ICON, 15,
                               normal_role="text_secondary",
                               hover_role="signal_error")
            btn_sup.setToolTip(s.md_delete_tip)
            btn_sup.setStyleSheet(icon_button_qss(c))
            btn_sup.clicked.connect(lambda _c=False, nn=n: self._supprimer(nn))
            btn_sup.setEnabled(self._worker is None
                               or not self._worker.isRunning())
            self._btns_suppr.append(btn_sup)
            ligne.addWidget(btn_sup)
            self._dl_lay.addLayout(ligne)
        self._dl_lay.addStretch(1)

    # ── Theme ─────────────────────────────────────────────────
    def apply_theme(self, c: ColorScheme):
        # Regles SCOPEES par objectName -- jamais sur le type nu (une regle
        # `QScrollArea` nue cascaderait dans les dialogues enfants, lecon deja
        # payee par la modale d'ambiguite). La barre native dessinait son
        # texte barre d'un trait sombre (capture du 2026-08-28) : fond
        # input_bg, chunk phosphore.
        self.setStyleSheet(
            f"QDialog {{ background-color: {c.main_bg}; }}\n"
            f"QScrollArea#mdScroll {{ background: transparent; border: none; }}\n"
            f"QScrollArea#mdScroll > QWidget > QWidget {{"
            f" background: transparent; }}\n"
            f"QProgressBar#mdBar {{"
            f" background-color: {c.input_bg};"
            f" border: 1px solid {c.border};"
            f" border-radius: 6px;"
            f" color: {c.text_primary};"
            f" text-align: center;"
            f" font-size: 8pt; }}\n"
            f"QProgressBar#mdBar::chunk {{"
            f" background-color: {c.signal_ok};"
            f" border-radius: 5px; }}\n"
            # ⚠️ Regle SCOPEE : une feuille SANS selecteur posee sur le cadre
            # s'appliquait a TOUS ses descendants -- le scroll interieur
            # heritait de la bordure, d'ou un cadre DANS le cadre (constate
            # par l'utilisateur le 2026-08-28). Meme famille de piege que la
            # feuille qui s'echappe dans les dialogues enfants.
            f"QWidget#mdCadre {{"
            f" background-color: {c.main_bg};"
            f" border: 1px solid {c.border};"
            f" border-radius: 6px; }}")
        for w in (self._lbl_titre,):
            w.setStyleSheet(f"font-size: 13pt; font-weight: 700; color: {c.text_primary};")
        for w in (self._lbl_sug, self._lbl_dl, self._lbl_autre):
            w.setStyleSheet(f"font-size: 10pt; font-weight: 600; color: {c.text_primary};")
        for w in (self._lbl_sug_note, self._lbl_autre_aide,
                  self._lbl_etat, self._lbl_note_annul):
            w.setStyleSheet(f"font-size: 9pt; color: {c.text_secondary};")

        for _n, _t, _p, lbl, btn in self._lignes:
            lbl.setStyleSheet(f"font-size: 9pt; color: {c.text_primary};")
            btn.setStyleSheet(icon_button_qss(c))

        # En DERNIER : le filtre de survol vient de reposer l'icone DOWNLOAD
        # sur toutes les lignes (theme change) ; ceci remet la coche sur les
        # modeles deja telecharges.
        self._rendre_listes(lang_manager.current)
        self._champ.setStyleSheet(input_qss(c))
        self._btn_autre.setStyleSheet(secondary_button_qss(c))
        self._btn_annuler.setStyleSheet(secondary_button_qss(c))
        self._btn_liberer.setStyleSheet(secondary_button_qss(c))
        self._btn_fermer.setStyleSheet(primary_button_qss(c))

"""Gerer les modeles LM Studio sans quitter Promptuino (TODO #121).

Meme ossature que `ModelDownloadDialog` (Ollama), qui n'est PAS touchee : ses
particularites (fichiers partiels, preallocation, suppression) n'ont pas
d'equivalent ici. Quatre zones :

1. **Suggeres** — tailles INDICATIVES (le catalogue de LM Studio se trompe
   dans les deux sens, cf. `ui/lmstudio_models.py`) ; exactes une fois local.
2. **Installes** — taille exacte, Charger / Decharger. ⛔ Pas de Supprimer :
   ni l'API ni `lms` ne le permettent (decision de l'auteur : renvoyer vers
   LM Studio, et le dire).
3. **Un autre modele** — identifiant du catalogue ou lien Hugging Face.
4. **Progression** — ⛔ aucun bouton Annuler : l'API n'en a pas. La note dit
   que fermer la fenetre n'arrete pas le telechargement ; une fenetre
   rouverte REPREND le suivi (`lm.suivre` / `lm.suivi`, QA AV2 du
   2026-11-06 : elle repartait a l'aveugle, faute de memoire hors d'elle).

Aucune requete sur le fil graphique au-dela de la lecture de la liste
(locale, quelques ms) : demarrer, suivre, charger et decharger tournent dans
des `_Tache`, gardees en vie par `_EN_VOL` meme si la fenetre se ferme.
"""
from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QProgressBar, QScrollArea, QWidget,
)

from . import icons as IC
from . import contexte
from . import memoire_modeles
from . import erreurs_chargement
from . import lmstudio_models as lm
from .ai_config import ai_config
from .ollama_models import go_carte
from .i18n import lang_manager, Strings
from .ollama_models import tient_en_vram, vram_totale
from .taches_fond import lancer_en_fond  # noqa: F401  (aussi pour ia_view)
from .theme import (ColorScheme, theme_manager, icon_button_qss, input_qss,
                    install_icon_hover, primary_button_qss,
                    secondary_button_qss)


def _go(octets: float) -> str:
    return f"{octets / 1e9:.1f} Go"


def _heure(iso: str) -> str:
    """`2026-11-06T10:05:03.184Z` -> `11:05` en heure locale ; "" si illisible."""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().strftime("%H:%M")
    except Exception:
        return ""


def _installe_de(cle: str, installes: list) -> "dict | None":
    """La fiche locale d'une SUGGESTION, ou None.

    ⚠️ LM Studio n'installe pas sous le nom demande : `google/gemma-3-4b`
    arrive en `gemma-3-4b-it` (mesure du 2026-11-06). Comparer les cles
    exactes laissait la suggestion « a telecharger » apres son telechargement
    (audit 2026-11-06). On compare donc le dernier segment, a l'egalite ou
    suivi d'un suffixe en `-` (`-it`) : `gemma-3-1b` ne prend pas `gemma-3-12b`.
    """
    for f in installes:
        if f["cle"] == cle:
            return f
    base = cle.rsplit("/", 1)[-1].lower()
    for f in installes:
        loc = f["cle"].rsplit("/", 1)[-1].lower()
        if loc == base or loc.startswith(base + "-"):
            return f
    return None


# Les taches de fond vivent dans `ui/taches_fond.py` (partagees avec la
# connexion ChatGPT). `lancer_en_fond` reste importable d'ici.


# ─── La fenetre ──────────────────────────────────────────────────────────

class LMStudioModelsDialog(QDialog):
    """`modeles_changes` : la liste ou l'etat charge a bouge — la page relit."""

    modeles_changes = pyqtSignal()

    def __init__(self, base_url: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMinimumWidth(580)
        self._url = base_url
        self._vram = vram_totale()
        self._etat_api = lm.etat_api(base_url)
        self._installes = (lm.modeles_installes(base_url)
                           if self._etat_api == "ok" else [])
        self._job: "str | None" = None
        self._cle_en_cours: "str | None" = None
        self._etat_en_vol = False
        self._occupe = False             # un chargement / dechargement en cours
        self._lignes: list = []
        self._minuterie = QTimer(self)
        self._minuterie.setInterval(1000)
        self._minuterie.timeout.connect(self._tick)
        self._build()
        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)
        self._reprendre()

    # ── Construction ──────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 16)
        root.setSpacing(10)

        self._lbl_titre = QLabel()
        root.addWidget(self._lbl_titre)

        # Si la v1 manque ou que le serveur se tait, on le DIT en tete et le
        # reste est grise : des boutons actifs qui echouent tous seraient pire.
        self._lbl_bloquant = QLabel()
        self._lbl_bloquant.setWordWrap(True)
        self._lbl_bloquant.setVisible(self._etat_api != "ok")
        root.addWidget(self._lbl_bloquant)

        self._corps = QWidget()
        corps = QVBoxLayout(self._corps)
        corps.setContentsMargins(0, 0, 0, 0)
        corps.setSpacing(10)
        root.addWidget(self._corps)

        # ── 1. suggeres ───────────────────────────────────────
        self._lbl_sug = QLabel()
        corps.addWidget(self._lbl_sug)
        self._lbl_sug_note = QLabel()
        self._lbl_sug_note.setWordWrap(True)
        self._lbl_sug_note.setTextFormat(Qt.TextFormat.RichText)
        corps.addWidget(self._lbl_sug_note)
        # La memoire de la carte, dite UNE fois (et non plus sur chaque ligne,
        # ou elle se lisait comme la taille des modeles -- QA du 2026-11-06).
        self._lbl_vram = QLabel()
        self._lbl_vram.setVisible(bool(self._vram))
        corps.addWidget(self._lbl_vram)
        sug_host = QWidget()
        sh = QVBoxLayout(sug_host)
        sh.setContentsMargins(0, 0, 6, 0)
        sh.setSpacing(6)
        for cle, taille, params in lm.SUGGERES:
            ligne = QHBoxLayout()
            ligne.setSpacing(8)
            btn = QPushButton()
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setAutoDefault(False)
            btn.setFixedSize(26, 26)
            btn.clicked.connect(lambda _c=False, k=cle: self._lancer(k))
            install_icon_hover(btn, IC.DOWNLOAD, 16, normal_role="text_secondary")
            ligne.addWidget(btn)
            lbl = QLabel()
            lbl.setTextFormat(Qt.TextFormat.RichText)
            ligne.addWidget(lbl, 1)
            sh.addLayout(ligne)
            self._lignes.append((cle, taille, params, lbl, btn))
        sh.addStretch(1)
        self._cadre_sug = self._encadrer(self._defilant(sug_host, 184))
        corps.addWidget(self._cadre_sug)

        # ── 2. installes ──────────────────────────────────────
        self._lbl_inst = QLabel()
        corps.addWidget(self._lbl_inst)
        self._inst_host = QWidget()
        self._inst_lay = QVBoxLayout(self._inst_host)
        self._inst_lay.setContentsMargins(0, 0, 6, 0)
        self._inst_lay.setSpacing(6)
        self._cadre_inst = self._encadrer(self._defilant(self._inst_host, 110))
        corps.addWidget(self._cadre_inst)
        self._lbl_suppr = QLabel()
        self._lbl_suppr.setWordWrap(True)
        corps.addWidget(self._lbl_suppr)
        self._lbl_info = QLabel()          # echec d'un chargement, dit tel quel
        self._lbl_info.setWordWrap(True)
        self._lbl_info.hide()
        corps.addWidget(self._lbl_info)
        self._lbl_libere = QLabel()        # ce que le chargement a libere
        self._lbl_libere.setWordWrap(True)
        self._lbl_libere.hide()
        corps.addWidget(self._lbl_libere)

        # ── 3. un autre modele ────────────────────────────────
        self._lbl_autre = QLabel()
        corps.addWidget(self._lbl_autre)
        self._lbl_autre_aide = QLabel()
        self._lbl_autre_aide.setWordWrap(True)
        self._lbl_autre_aide.setTextFormat(Qt.TextFormat.RichText)
        self._lbl_autre_aide.setOpenExternalLinks(True)
        corps.addWidget(self._lbl_autre_aide)
        rang = QHBoxLayout()
        self._champ = QLineEdit()
        self._champ.setPlaceholderText("google/gemma-3-4b")
        self._champ.returnPressed.connect(self._lancer_saisi)
        rang.addWidget(self._champ, 1)
        self._btn_autre = QPushButton()
        self._btn_autre.setAutoDefault(False)
        self._btn_autre.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_autre.clicked.connect(self._lancer_saisi)
        rang.addWidget(self._btn_autre)
        corps.addLayout(rang)

        # ── 4. progression ────────────────────────────────────
        self._zone = QWidget()
        zl = QVBoxLayout(self._zone)
        zl.setContentsMargins(0, 8, 0, 0)
        self._lbl_etat = QLabel()
        self._lbl_etat.setWordWrap(True)
        zl.addWidget(self._lbl_etat)
        self._barre = QProgressBar()
        self._barre.setObjectName("lmsBar")
        self._barre.setFixedHeight(20)
        zl.addWidget(self._barre)
        self._lbl_detail = QLabel()
        zl.addWidget(self._lbl_detail)
        self._lbl_note = QLabel()
        self._lbl_note.setWordWrap(True)
        zl.addWidget(self._lbl_note)
        self._zone.hide()
        corps.addWidget(self._zone)

        self._corps.setEnabled(self._etat_api == "ok")

        bas = QHBoxLayout()
        bas.addStretch()
        self._btn_fermer = QPushButton()
        self._btn_fermer.setAutoDefault(False)
        self._btn_fermer.clicked.connect(self.accept)
        bas.addWidget(self._btn_fermer)
        root.addLayout(bas)

    def _defilant(self, hote: QWidget, hauteur: int) -> QScrollArea:
        # objectName scope : une regle sur le TYPE QScrollArea s'echapperait
        # dans les dialogues enfants (lecon payee).
        sc = QScrollArea()
        sc.setObjectName("lmsScroll")
        sc.setWidgetResizable(True)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sc.setFixedHeight(hauteur)
        sc.setWidget(hote)
        sc.viewport().setAutoFillBackground(False)
        hote.setAutoFillBackground(False)
        return sc

    def _encadrer(self, contenu: QWidget) -> QWidget:
        cadre = QWidget()
        cadre.setObjectName("lmsCadre")
        cadre.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(cadre)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.addWidget(contenu)
        return cadre

    # ── Telechargement ────────────────────────────────────────
    def _lancer_saisi(self):
        cle = self._champ.text().strip()
        if cle:
            self._lancer(cle)

    def _lancer(self, cle: str):
        if self._cle_en_cours is not None:
            return                       # un a la fois, comme pour Ollama
        self._montrer_suivi(cle)
        url = self._url
        lancer_en_fond("demarrer", lambda: lm.demarrer(url, cle), self._resultat)

    def _montrer_suivi(self, cle: str):
        self._cle_en_cours = cle
        self._job = None
        s = lang_manager.current
        self._zone.show()
        self._barre.setRange(0, 0)       # indetermine tant que le total manque
        self._lbl_etat.setText(f"<b>{cle}</b>")
        self._lbl_detail.setText("")
        self._lbl_note.setText(s.lms_keeps_running)
        self._basculer_boutons()

    def _reprendre(self):
        """Une fenetre rouverte reprend le telechargement lance par une
        precedente : LM Studio, lui, ne s'est jamais arrete (QA AV2)."""
        en_cours = lm.suivi(self._url) if self._etat_api == "ok" else None
        if en_cours is None:
            return
        self._montrer_suivi(en_cours["cle"])
        self._job = en_cours["job"]
        self._minuterie.start()
        self._tick()

    def _tick(self):
        if self._etat_en_vol or not self._job:
            return
        self._etat_en_vol = True
        url, job = self._url, self._job
        lancer_en_fond("etat", lambda: lm.etat(url, job), self._resultat)

    def _resultat(self, paquet):
        etiquette, r = paquet
        if isinstance(r, Exception):
            r = {"etat": "echec", "message": str(r)}
        getattr(self, f"_apres_{etiquette}")(r)

    def _apres_demarrer(self, r: dict):
        s = lang_manager.current
        if r.get("etat") == "en_cours":
            self._job = r["job"]
            lm.suivre(self._url, self._cle_en_cours, self._job,
                      avant=[f["cle"] for f in self._installes])
            self._minuterie.start()
            self._tick()                 # le vrai total arrive avec l'etat
        elif r.get("etat") == "deja_la":
            self._terminer(s.md_already)
        elif r.get("etat") == "muet":
            self._terminer(s.ia_lmstudio_server_down, erreur=True)
        else:
            # Jamais le texte brut : quoi faire, ou une phrase simple (2026-11-06).
            self._terminer(erreurs_chargement.telechargement(
                r.get("message"), s), erreur=True)

    def _apres_etat(self, r: dict):
        self._etat_en_vol = False
        s = lang_manager.current
        e = r.get("etat")
        if e in ("en_cours", "en_pause", "inconnu"):
            total, recu = r.get("total"), r.get("recu") or 0
            if total:
                self._barre.setRange(0, 1000)
                self._barre.setValue(int(1000 * min(recu, total) / total))
                morceaux = [s.lms_progress.format(recu=_go(recu), total=_go(total))]
                if r.get("debit"):
                    morceaux.append(f"{r['debit'] / 1e6:.1f} Mo/s")
                if r.get("fin") and _heure(r["fin"]):
                    morceaux.append(s.lms_eta.format(heure=_heure(r["fin"])))
                self._lbl_detail.setText(" · ".join(morceaux))
            if e == "en_pause":
                self._lbl_detail.setText(s.lms_paused)
        elif e == "termine":
            self._terminer(s.md_done)
        elif e == "perdu":
            # LM Studio oublie un job termine (voir `lm.etat`). Un modele
            # apparu depuis le depart = arrive ; le nom demande ne prouve
            # rien, il s'installe sous un autre. Sans suivi, rien ne compare.
            suivi = lm.suivi(self._url)
            maintenant = {f["cle"] for f in lm.modeles_installes(self._url)}
            avant = suivi["avant"] if suivi else maintenant
            if maintenant - avant:
                self._terminer(s.md_done)
            else:
                self._terminer(s.lms_lost, erreur=True)
        elif e == "muet":
            self._terminer(s.ia_lmstudio_server_down, erreur=True)
        else:
            # Jamais le texte brut : quoi faire, ou une phrase simple (2026-11-06).
            self._terminer(erreurs_chargement.telechargement(
                r.get("message"), s), erreur=True)

    def _terminer(self, texte: str, *, erreur: bool = False):
        self._minuterie.stop()
        lm.oublier(self._url)
        self._job = None
        self._cle_en_cours = None
        self._barre.setRange(0, 1000)
        self._barre.setValue(0 if erreur else 1000)
        self._lbl_detail.setText(texte)
        self._lbl_note.setText("")
        self._relire()

    # ── Charger / decharger ───────────────────────────────────
    def _charger(self, cle: str, btn=None):
        # Pendant un chargement, le bouton de la ligne dit « Annuler »
        # (2026-11-07) : couper la requete fait abandonner LM Studio (mesure).
        if self._occupe and getattr(self, "_coupure_chg", None):
            self._chg_annule = True
            self._coupure_chg.couper()
            return
        from .ai_backends.coupure import Coupure
        coupure = self._coupure_chg = Coupure(unique=True)
        self._chg_annule = False
        self._occuper(True)
        if btn is not None:
            btn.setText(lang_manager.current.md_cancel)
            btn.setEnabled(True)               # c'est lui qui annule
        url = self._url
        # A la taille reglee sur la page ; `charger` la borne au modele.
        voulu = ai_config.lmstudio_num_ctx

        def tache():
            # D'abord les AUTRES modeles, sur les deux moteurs (2026-11-06).
            liberes = memoire_modeles.liberer_autres("lmstudio", cle, url)
            if coupure.annulee:                  # annule pendant la liberation
                return False, "", liberes
            ok, msg = lm.charger(url, cle, voulu, coupure=coupure)
            return ok, msg, liberes
        lancer_en_fond("charger", tache, self._resultat)

    def _decharger(self, instance: str):
        self._occuper(True)
        url = self._url
        lancer_en_fond("decharger", lambda: lm.decharger(url, instance),
                       self._resultat)

    def _apres_charger(self, r):
        self._apres_geste(r, decharge=False)

    def _apres_decharger(self, r):
        self._apres_geste(r, decharge=True)

    def _apres_geste(self, r, *, decharge: bool):
        s = lang_manager.current
        if not isinstance(r, tuple):
            r = (False, "")
        ok, msg = r[0], r[1]
        libere = memoire_modeles.phrase(r[2] if len(r) > 2 else [], s.mem_freed)
        self._lbl_libere.setText(libere)
        self._lbl_libere.setVisible(bool(libere))
        annule = not decharge and getattr(self, "_chg_annule", False)
        self._coupure_chg = None
        self._chg_annule = False
        if annule:
            # Un choix, pas une panne : pas de rouge.
            self._lbl_info.hide()
            self._lbl_libere.setText(
                " ".join(t for t in (libere, s.load_cancelled) if t))
            self._lbl_libere.setVisible(True)
        elif ok:
            self._lbl_info.hide()
        else:
            # Jamais le texte brut de LM Studio : une phrase simple (2026-11-06).
            self._lbl_info.setText(erreurs_chargement.message(
                "lmstudio", msg, s, decharge=decharge))
            self._lbl_info.show()
        self._occuper(False)
        self._relire()

    def _occuper(self, occupe: bool):
        self._occupe = occupe
        self._basculer_boutons()

    # ── Rendu ─────────────────────────────────────────────────
    def _relire(self):
        self._installes = (lm.modeles_installes(self._url)
                           if self._etat_api == "ok" else [])
        self._rendre_listes(lang_manager.current)
        self._basculer_boutons()
        self.modeles_changes.emit()

    def _basculer_boutons(self):
        libre = self._cle_en_cours is None
        for cle, _t, _p, _l, btn in self._lignes:
            btn.setEnabled(libre and _installe_de(cle, self._installes) is None)
        self._btn_autre.setEnabled(libre)
        for b in getattr(self, "_btns_geste", []):
            b.setEnabled(not self._occupe and not b.property("inutilisable"))

    def _suffixe_vram(self, taille, s: Strings) -> str:
        verdict = tient_en_vram(taille, self._vram) if taille else None
        if verdict is True:
            return " · " + s.md_fits.format(vram=_go(self._vram))
        if verdict is False:
            return " · " + s.md_too_big.format(vram=_go(self._vram))
        return ""                        # on ne sait pas -> on se tait

    def _rendre_listes(self, s: Strings):
        c = theme_manager.current
        for cle, taille, params, lbl, btn in self._lignes:
            local = _installe_de(cle, self._installes)
            vraie = local["taille"] if local else None
            txt = _go(vraie) if vraie else f"~{_go(taille)}"
            lbl.setText(f"<b>{cle}</b> — {txt} · {params}"
                        f"{self._suffixe_vram(vraie or taille, s)}")
            if local:
                btn.setIcon(IC.make_icon(IC.CHECK, c.signal_ok, 16))
                btn.setToolTip(s.md_already)
            else:
                btn.setToolTip(s.md_download)

        # Vidage RECURSIF, setParent(None) avant deleteLater : des lignes
        # orphelines continuaient de se peindre dans la fenetre Ollama.
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
        _vider(self._inst_lay)
        self._btns_geste = []
        if not self._installes:
            vide = QLabel(s.md_none)
            vide.setStyleSheet(f"font-size: 9pt; color: {c.text_secondary};"
                               " background: transparent;")
            self._inst_lay.addWidget(vide)
        for f in self._installes:
            ligne = QHBoxLayout()
            ligne.setSpacing(8)
            morceaux = [p for p in (f["params"], f["quant"]) if p]
            details = (" · " + " · ".join(morceaux)) if morceaux else ""
            charge = ""
            if f["instances"]:
                ctx = f["instances"][0][1]
                charge = " · " + (s.lms_loaded.format(n=ctx) if ctx
                                  else s.lms_loaded.split("·")[0].strip())
            taille = _go(f["taille"]) if f["taille"] else "?"
            # Sous le plancher : INUTILISABLE, et la ligne dit pourquoi
            # (decision de l'auteur, 2026-11-06).
            inutilisable = not contexte.utilisable(f["ctx_max"])
            raison = (" · " + s.md_unusable_ctx.format(n=f["ctx_max"])
                      if inutilisable else "")
            lab = QLabel(f"<b>{f['cle']}</b> — {taille}{details}{charge}{raison}"
                         f"{self._suffixe_vram(f['taille'], s)}")
            lab.setTextFormat(Qt.TextFormat.RichText)
            lab.setWordWrap(True)
            lab.setStyleSheet(f"font-size: 9pt; color: {c.text_primary};"
                              " background: transparent;")
            ligne.addWidget(lab, 1)
            btn = QPushButton(s.lms_unload if f["instances"] else s.lms_load)
            btn.setAutoDefault(False)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(secondary_button_qss(c))
            if f["instances"]:
                btn.clicked.connect(
                    lambda _c=False, i=f["instances"][0][0]: self._decharger(i))
            elif inutilisable:
                # Marque, pas seulement grise : `_basculer_boutons` re-active
                # tous les boutons apres chaque geste (trouve par le test).
                btn.setProperty("inutilisable", True)
                btn.setEnabled(False)
                btn.setToolTip(s.ctx_unusable.format(
                    n=f["ctx_max"], min=contexte.CTX_PROMPTUINO))
            else:
                btn.setToolTip(s.lms_load_tip.format(
                    n=contexte.ramener(ai_config.lmstudio_num_ctx, f["ctx_max"])))
                btn.clicked.connect(
                    lambda _c=False, k=f["cle"], b=btn: self._charger(k, b))
            self._btns_geste.append(btn)
            ligne.addWidget(btn)
            self._inst_lay.addLayout(ligne)
        self._inst_lay.addStretch(1)

    # ── Langue ────────────────────────────────────────────────
    def apply_lang(self, s: Strings):
        self.setWindowTitle(s.lms_title)
        self._lbl_titre.setText(s.lms_title)
        if self._etat_api == "ancien":
            self._lbl_bloquant.setText(s.lms_need_update)
        elif self._etat_api == "muet":
            self._lbl_bloquant.setText(s.ia_lmstudio_server_down)
        self._lbl_sug.setText(s.md_suggested)
        self._lbl_sug_note.setText(s.md_suggested_note)
        if self._vram:
            self._lbl_vram.setText(s.md_vram.format(vram=go_carte(self._vram)))
        self._lbl_inst.setText(s.md_downloaded)
        self._lbl_suppr.setText(s.lms_delete_hint)
        self._lbl_autre.setText(s.md_other)
        lien = (f'<a href="{lm.PAGE_CATALOGUE}" style="color: '
                f'{theme_manager.current.accent};">lmstudio.ai/models</a>')
        self._lbl_autre_aide.setText(s.lms_other_help.format(lien=lien))
        self._btn_autre.setText(s.md_download)
        self._btn_fermer.setText(s.md_close)
        if self._cle_en_cours is not None:
            self._lbl_note.setText(s.lms_keeps_running)
        self._rendre_listes(s)
        self._basculer_boutons()

    # ── Theme ─────────────────────────────────────────────────
    def apply_theme(self, c: ColorScheme):
        # Regles SCOPEES par objectName, jamais sur le type nu.
        self.setStyleSheet(
            f"QDialog {{ background-color: {c.main_bg}; }}\n"
            f"QScrollArea#lmsScroll {{ background: transparent; border: none; }}\n"
            f"QScrollArea#lmsScroll > QWidget > QWidget {{ background: transparent; }}\n"
            f"QProgressBar#lmsBar {{ background-color: {c.input_bg};"
            f" border: 1px solid {c.border}; border-radius: 6px;"
            f" color: {c.text_primary}; text-align: center; font-size: 8pt; }}\n"
            f"QProgressBar#lmsBar::chunk {{ background-color: {c.signal_ok};"
            f" border-radius: 5px; }}\n"
            f"QWidget#lmsCadre {{ background-color: {c.main_bg};"
            f" border: 1px solid {c.border}; border-radius: 6px; }}")
        self._lbl_titre.setStyleSheet(
            f"font-size: 13pt; font-weight: 700; color: {c.text_primary};")
        for w in (self._lbl_sug, self._lbl_inst, self._lbl_autre):
            w.setStyleSheet(f"font-size: 10pt; font-weight: 600; color: {c.text_primary};")
        for w in (self._lbl_sug_note, self._lbl_vram, self._lbl_autre_aide, self._lbl_suppr,
                  self._lbl_etat, self._lbl_detail, self._lbl_note):
            w.setStyleSheet(f"font-size: 9pt; color: {c.text_secondary};")
        self._lbl_bloquant.setStyleSheet(f"font-size: 10pt; color: {c.signal_error};")
        self._lbl_info.setStyleSheet(f"font-size: 9pt; color: {c.signal_error};")
        self._lbl_libere.setStyleSheet(f"font-size: 9pt; color: {c.text_secondary};")
        for _k, _t, _p, lbl, btn in self._lignes:
            lbl.setStyleSheet(f"font-size: 9pt; color: {c.text_primary};")
            btn.setStyleSheet(icon_button_qss(c))
        self._champ.setStyleSheet(input_qss(c))
        self._btn_autre.setStyleSheet(secondary_button_qss(c))
        self._btn_fermer.setStyleSheet(primary_button_qss(c))
        # En DERNIER : le filtre de survol vient de reposer l'icone
        # DOWNLOAD ; ceci remet la coche sur les modeles deja installes.
        self._rendre_listes(lang_manager.current)

    def done(self, r):
        # Le telechargement continue dans LM Studio (la note le dit) ; on
        # arrete seulement de l'interroger. Son numero reste dans `lm` : la
        # prochaine fenetre reprendra le suivi.
        self._minuterie.stop()
        super().done(r)

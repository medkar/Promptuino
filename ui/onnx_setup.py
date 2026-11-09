"""First-launch setup pour le modele ONNX RAG.

Le modele `model.onnx` (~448 Mo) n'est PAS embarque dans l'installeur pour
le garder leger. Au 1er lancement de l'app, si le fichier est manquant,
on affiche un dialog PyQt qui le telecharge depuis une URL configurable.

Edition de l'URL : modifier la constante `ONNX_MODEL_URL` ci-dessous avant
de builder l'installeur (ou positionner l'env var `PROMPTUINO_ONNX_URL`).
"""
from __future__ import annotations

import hashlib
import os
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox,
    QProgressBar, QPushButton, QVBoxLayout,
)

# Les deux emplacements possibles du modele et la regle de choix vivent
# dans `ui/model_path.py` -- module PUR, partage avec `ui/rag.py`, qui doit
# lire le meme fichier que celui qu'on ecrit ici.
from .i18n import lang_manager
from .model_path import (is_model_available, model_path,
                         user_model_path, bundled_model_path)
from .theme import (
    ColorScheme, theme_manager, primary_button_qss, secondary_button_qss,
)


# ─── Configuration ───────────────────────────────────────────────────────
# URL du modele ONNX (448 Mio), publie le 2026-08-28 sur Hugging Face.
# Peut etre override par la variable d'env `PROMPTUINO_ONNX_URL`.
#
# ⚠️ L'URL est EPINGLEE SUR UN COMMIT, jamais sur `main`. Deux raisons :
#   1. un envoi ulterieur dans le depot ne doit pas changer ce que
#      telechargent les installeurs deja distribues ;
#   2. `assets/rag/embeddings.npy` est aligne sur CET export exactement, et
#      tout le pipeline repose sur des seuils MESURES (plancher 0,50,
#      relative_gate 0,85, plafond de bruit 0,495). Un autre export les
#      deplace en silence.
#
# ⛔ Ne PAS remplacer par le depot officiel du modele : il heberge bien un
# `onnx/model.onnx`, mais c'est un autre fichier (470 301 610 octets contre
# 470 216 988 ici, mesure le 2026-08-28) -- version d'optimum et opset
# differents. Les variantes quantifiees `qint8` changent les vecteurs de
# facon certaine.
ONNX_MODEL_URL = (
    "https://huggingface.co/medkar/promptuino-embeddings/resolve/"
    "96317bee6225055e315bcfa88655978cd8afe940/model.onnx"
)

# Checksum SHA-256 attendu (optionnel - mettre "" pour skip la verification).
# ⛔ NE PAS REVIDER : un modele corrompu ne planterait pas, il produirait des
# vecteurs faux et degraderait le RAG en SILENCE.
# Calcul en local : python -c "import hashlib; print(hashlib.sha256(open('assets/rag/model/model.onnx','rb').read()).hexdigest())"
ONNX_MODEL_SHA256 = "005d51beaafb6721f3a8a2227749f2c518356fa087d9c2983da7aabaab8f84cd"

# Expected size (bytes) for the progress bar when the server does not
# return a Content-Length header. 0 = indeterminate progress.
# Taille EXACTE du fichier publie (le CDN Hugging Face renvoie bien un
# Content-Length, donc cette valeur ne sert que de repli).
ONNX_MODEL_SIZE_BYTES = 470216988


def get_model_url() -> str:
    """URL effective (env var override si presente, sinon constante)."""
    return os.environ.get("PROMPTUINO_ONNX_URL") or ONNX_MODEL_URL


# ─── Worker thread de telechargement ─────────────────────────────────────
class _DownloadWorker(QThread):
    """Telecharge le modele en arriere-plan, emet progress / done / failed."""
    # ⚠️ `object` et non `int` : l'`int` d'un signal Qt est 32 bits, et un
    # total au-dela de 2 Gio deborderait (defaut CONSTATE sur le
    # telechargeur de modeles Ollama, 2026-08-28). Le modele ONNX actuel
    # (470 Mo) passe, mais la constante est a un changement de modele de
    # mentir.
    progress = pyqtSignal(object, object)   # (bytes_done, bytes_total)
    done = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, url: str, dest: Path) -> None:
        super().__init__()
        self._url = url
        self._dest = dest
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        tmp = self._dest.with_suffix(self._dest.suffix + ".partial")
        try:
            self._dest.parent.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(self._url, headers={
                "User-Agent": "Promptuino/1.0 (model-download)",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                if total == 0:
                    total = ONNX_MODEL_SIZE_BYTES
                done = 0
                chunk = 1024 * 256   # 256 KiB
                with open(tmp, "wb") as out:
                    while True:
                        if self._cancel.is_set():
                            out.close()
                            tmp.unlink(missing_ok=True)
                            self.failed.emit(lang_manager.current.onnx_cancelled)
                            return
                        block = resp.read(chunk)
                        if not block:
                            break
                        out.write(block)
                        done += len(block)
                        self.progress.emit(done, total)
            # Verification SHA-256 si configure
            if ONNX_MODEL_SHA256:
                h = hashlib.sha256()
                with open(tmp, "rb") as f:
                    for block in iter(lambda: f.read(1024 * 1024), b""):
                        h.update(block)
                if h.hexdigest() != ONNX_MODEL_SHA256.lower():
                    tmp.unlink(missing_ok=True)
                    self.failed.emit(lang_manager.current.onnx_err_checksum)
                    return
            # Renomme le .partial -> .onnx
            if self._dest.exists():
                self._dest.unlink()
            tmp.rename(self._dest)
            self.done.emit()
        except urllib.error.HTTPError as e:
            tmp.unlink(missing_ok=True)
            self.failed.emit(lang_manager.current.onnx_err_http.replace(
                "{code}", str(e.code)).replace("{reason}", str(e.reason)))
        except urllib.error.URLError as e:
            tmp.unlink(missing_ok=True)
            self.failed.emit(lang_manager.current.onnx_err_network.replace(
                "{reason}", str(e.reason)))
        except Exception as e:
            tmp.unlink(missing_ok=True)
            self.failed.emit(lang_manager.current.onnx_err_unexpected.replace(
                "{detail}", f"{type(e).__name__}: {e}"))


# ─── Dialog PyQt ─────────────────────────────────────────────────────────
class OnnxDownloadDialog(QDialog):
    """Dialog modal qui telecharge le model.onnx au 1er lancement.

    Usage :
        dlg = OnnxDownloadDialog()
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Modele OK, lancer l'app
        else:
            # Echec ou annulation, quitter
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # ⚠️ Ce dialogue etait ecrit en francais EN DUR, sans accents, et
        # n'etait donc traduit dans aucune des 4 langues -- alors qu'il est
        # le TOUT PREMIER ecran qu'un utilisateur voit. Meme defaut que les
        # boutons << Voir le schema >> corriges le 2026-08-10 : invisible en
        # francais, la seule langue dans laquelle l'app est essayee a la
        # main.
        s = lang_manager.current
        self.setWindowTitle(s.onnx_window_title)
        self.setModal(True)
        self.setMinimumWidth(520)
        self._worker: _DownloadWorker | None = None
        self._build_ui()
        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        title = QLabel(lang_manager.current.onnx_title)
        title.setStyleSheet("font-size: 13pt; font-weight: 600;")
        layout.addWidget(title)

        desc = QLabel(lang_manager.current.onnx_desc)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self._status = QLabel(lang_manager.current.onnx_ready)
        layout.addWidget(self._status)

        self._progress = QProgressBar()
        self._progress.setMinimum(0)
        self._progress.setMaximum(100)
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_cancel = QPushButton(lang_manager.current.onnx_btn_cancel)
        self._btn_cancel.clicked.connect(self._on_cancel)
        btn_row.addWidget(self._btn_cancel)
        self._btn_start = QPushButton(lang_manager.current.onnx_btn_start)
        self._btn_start.setDefault(True)
        self._btn_start.clicked.connect(self._start_download)
        btn_row.addWidget(self._btn_start)
        layout.addLayout(btn_row)

    # ── Theme ────────────────────────────────────────────────────
    def apply_theme(self, c: ColorScheme) -> None:
        # "Download" = primary (filled), "Cancel" = secondary
        # (outlined); centralized style convention (green on hover).
        self._btn_start.setStyleSheet(primary_button_qss(c))
        self._btn_cancel.setStyleSheet(secondary_button_qss(c))

    def _start_download(self) -> None:
        url = get_model_url()
        if not url or url.startswith("https://example.com"):
            QMessageBox.critical(
                self, lang_manager.current.onnx_url_missing_title,
                lang_manager.current.onnx_url_missing_text,
            )
            return
        # Toujours l'emplacement INSCRIPTIBLE : `model_path()` rendrait le
        # chemin embarque si un fichier tronque y trainait, et on
        # retomberait sur le PermissionError de Program Files.
        dest = user_model_path()
        self._btn_start.setEnabled(False)
        self._status.setText(lang_manager.current.onnx_running)
        self._worker = _DownloadWorker(url, dest)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, done: int, total: int) -> None:
        if total <= 0:
            self._progress.setMaximum(0)   # indetermine
            return
        pct = int(done * 100 / total)
        self._progress.setValue(pct)
        mb_done = done / (1024 * 1024)
        mb_total = total / (1024 * 1024)
        self._status.setText(
            lang_manager.current.onnx_progress.format(
                done=mb_done, total=mb_total, pct=pct)
        )

    def _on_done(self) -> None:
        self._progress.setValue(100)
        self._status.setText(lang_manager.current.onnx_done)
        self.accept()

    def _on_failed(self, msg: str) -> None:
        self._btn_start.setEnabled(True)
        self._status.setText(lang_manager.current.onnx_failed)
        QMessageBox.critical(self, lang_manager.current.onnx_error_title, msg)

    def _on_cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        self.reject()

    def finish_worker(self) -> None:
        """Waits for a download thread still running after the dialog closed.

        `_on_cancel` only waits 2 s so the window closes at once, but the
        worker tests the cancel flag BETWEEN two 256 KiB reads, and one read
        may block up to the 30 s socket timeout on a slow network. The caller
        then quits (or sys.exit in --download-model mode) and Qt aborts on a
        QThread destroyed while running (audit 2026-11-06). The window is
        already gone: waiting here costs nothing visible."""
        w = self._worker
        if w is not None and w.isRunning():
            w.cancel()
            w.wait()

    def closeEvent(self, event) -> None:
        self._on_cancel()
        super().closeEvent(event)


# La ligne temoin : la PREMIERE entree du corpus. Une seule suffit -- si
# l'encodeur differe, il differe partout ; en comparer 157 couterait 157 fois
# plus pour la meme reponse.
_LIGNE_TEMOIN = 0

# ⚠️ Mesure du 2026-11-05 : deux exports ONNX DIFFERENTS du meme modele
# rendent des vecteurs **bit a bit identiques** (ecart max 0.0). Ce seuil n'a
# donc pas a trancher un cas limite -- il n'en existe pas. Il est large expres,
# pour attraper un AUTRE modele (vecteurs sans rapport) sans jamais rougir sur
# du bruit numerique.
_ECART_TOLERE = 1e-4


def modele_accorde_a_la_matrice(chemin=None) -> "tuple[bool, str]":
    """Ce modele produit-il les vecteurs de `embeddings.npy` ? -> (verdict, raison)

    ⛔ **C'est la question que l'empreinte NE POSE PAS.** Elle demande « ce
    fichier est-il l'octet-pour-octet publie ? », alors que ce qui compte est
    « ce modele et cette matrice s'accordent-ils ? ».

    Mesure du 2026-11-05, sur cette machine : deux exports ONNX du meme
    modele, de taille IDENTIQUE a l'octet pres (470 216 988) et d'empreintes
    differentes, rendent des vecteurs **bit a bit identiques** -- ils ne
    different que par des metadonnees du protobuf, pas par les poids.
    L'empreinte criait donc au loup sur une configuration parfaitement saine,
    et faisait proposer un retelechargement de 448 Mo pour rien.

    ⚠️ Et elle laissait un trou que ce controle ferme : RIEN ne reliait la
    matrice au modele qui l'a produite. `embeddings.fingerprint.json` note
    l'empreinte des TEXTES encodes, jamais celle de l'encodeur.

    ⛔ Le texte temoin vient de `ui/embedding_text.py`, la source PARTAGEE avec
    le producteur de la matrice. Le recopier ici garantirait une derive : j'ai
    failli le faire, et ma version etait fausse sur trois points (prefixe du
    nom, mauvais tokenizer, mots-cles non doubles en minuscules) -- trois
    ecarts invisibles a la relecture, qui auraient fait rougir un modele sain.

    Rend `(False, raison)` quand la verification est **impossible** autant que
    quand elle echoue : l'appelant ne doit pas confondre « desaccord » et
    « je n'ai pas pu regarder ».
    """
    try:
        import json

        import numpy as np

        from . import rag
        from .embedding_text import embedding_text

        if not rag._CORPUS_PATH.is_file() or not rag._EMBEDDINGS_PATH.is_file():
            return False, "corpus ou matrice absent"
        entrees = json.loads(rag._CORPUS_PATH.read_text(encoding="utf-8"))
        if len(entrees) <= _LIGNE_TEMOIN:
            return False, "corpus trop court"

        stockee = np.load(rag._EMBEDDINGS_PATH, mmap_mode="r")
        if stockee.shape[0] <= _LIGNE_TEMOIN:
            return False, "matrice trop courte"

        # ⛔ ON JUGE LE FICHIER QUE `modele_conforme` JUGE, pas celui que
        # `rag` a sous la main. Les deux sont le meme en production -- mais
        # pas quand un appelant passe un chemin, et surtout pas dans les
        # tests, qui detournent `onnx_setup.model_path` seul. Sans cette
        # bascule, le controle aurait charge le VRAI modele, repondu
        # « d'accord », et declare conforme un fichier corrompu : il aurait
        # transforme la garde en no-op au lieu de la completer.
        cible = chemin or model_path()
        sauve = (rag._model_path, rag._session, rag._tokenizer)
        try:
            rag._model_path = lambda: cible
            rag._session = None
            rag._tokenizer = None
            if not rag._load_encoder():
                return False, "encodeur indisponible"
            vecteur = rag.encode([embedding_text(entrees[_LIGNE_TEMOIN])])
        finally:
            # La session construite ici ne sert qu'au controle : on rend a
            # `rag` l'etat qu'il avait, et sa prochaine utilisation rechargera
            # le modele qu'il doit vraiment lire.
            rag._model_path, rag._session, rag._tokenizer = sauve

        if vecteur is None or len(vecteur) == 0:
            return False, "encodage vide"

        ecart = float(np.abs(vecteur[0] - stockee[_LIGNE_TEMOIN]).max())
        if ecart <= _ECART_TOLERE:
            return True, ""
        return False, f"vecteurs differents (ecart {ecart:.4g})"
    except Exception as e:                                   # noqa: BLE001
        # Un controle de demarrage ne fait pas tomber l'application : il rend
        # « je ne sais pas », et l'appelant decide.
        return False, f"verification impossible ({e!r})"


def modele_conforme() -> "tuple[bool, str]":
    """Le `model.onnx` present est-il CELUI qu'on attend ? -> (verdict, raison).

    ⛔ **Ne pas se contenter de `is_model_available()`** : elle repond
    << un fichier existe et fait plus d'1 Mio >>, ce qui etait suffisant tant
    que le modele ne changeait jamais. Le jour ou une version en embarque un
    autre, l'utilisateur qui MET A JOUR garde le sien : le fichier existe, la
    porte se ferme, aucun telechargement n'est declenche -- pendant que
    `assets/rag/embeddings.npy`, lui, voyage dans l'installeur et arrive en
    version NEUVE. On se retrouve avec un ancien modele et une nouvelle
    matrice.

    ⚠️ Et rien ne le dirait : la seule garde d'execution compare le NOMBRE DE
    LIGNES de la matrice au nombre d'entrees du corpus (`rag.py`), or ces deux
    fichiers voyagent ensemble -- leurs comptes s'accorderaient parfaitement.
    L'application ne planterait pas, elle produirait des vecteurs issus d'un
    autre export et degraderait la recherche EN SILENCE. C'est exactement ce
    que l'empreinte existe pour empecher, et elle n'etait verifiee que sur un
    fichier FRAICHEMENT TELECHARGE.

    Deux controles, du moins cher au plus sur :

    - **la taille**, gratuite, et elle suffit a separer deux exports : celui
      du projet fait 470 216 988 octets quand la variante voisine de
      `sentence-transformers` en fait 470 301 610 ;
    - **l'empreinte**, qui attrape en plus un fichier corrompu. Mesure du
      2026-10-27 : **0,44 s** pour 470 Mio. Cette lecture rechauffe au
      passage le cache disque dont `onnxruntime` se servira pour charger le
      meme fichier, donc le cout net est plus faible que ces 0,44 s.
    """
    p = model_path()
    if not p.is_file():
        return False, "absent"
    taille = p.stat().st_size
    if ONNX_MODEL_SIZE_BYTES and taille != ONNX_MODEL_SIZE_BYTES:
        return False, (f"taille {taille} au lieu de {ONNX_MODEL_SIZE_BYTES} "
                       f"({p})")
    if ONNX_MODEL_SHA256:
        h = hashlib.sha256()
        with p.open("rb") as f:
            for bloc in iter(lambda: f.read(1024 * 1024), b""):
                h.update(bloc)
        if h.hexdigest() != ONNX_MODEL_SHA256.lower():
            # ⛔ UNE EMPREINTE DIFFERENTE N'EST PLUS UN VERDICT, C'EST UNE
            # QUESTION. Mesure du 2026-11-05 : deux exports du meme modele, de
            # taille identique a l'octet pres, rendent des vecteurs bit a bit
            # identiques. Conclure ici faisait proposer 448 Mo de
            # telechargement sur une configuration saine.
            #
            # ⚠️ Le cout reste nul dans le cas courant : on n'arrive ici
            # qu'APRES l'echec de l'empreinte. Les deux chemins mesures le
            # 2026-11-05 -- empreinte 0,34 s, comportement 0,94 s dont 0,92 de
            # chargement de session, que la premiere generation paierait de
            # toute facon.
            accorde, pourquoi = modele_accorde_a_la_matrice(p)
            if accorde:
                print("[ONNX] empreinte differente, mais les vecteurs "
                      "s'accordent avec embeddings.npy : autre export du "
                      "meme modele, rien a retelecharger.")
                return True, ""
            return False, f"empreinte differente ({p}) ; {pourquoi}"
    return True, ""


def ensure_model_or_exit(app: QApplication | None = None) -> bool:
    """Verifie que le modele attendu est present, propose le DL sinon.

    A appeler depuis main() AVANT MainWindow().

    Returns:
        True si le modele est disponible (existant ou DL reussi)
        False si l'utilisateur a annule (caller doit sortir)
    """
    conforme, raison = modele_conforme()
    if conforme:
        return True
    if raison != "absent":
        print(f"[ONNX] modele present mais NON CONFORME : {raison}"
              " -> retelechargement")
        # ⚠️ Le telechargement ecrit TOUJOURS dans l'emplacement inscriptible
        # (`user_model_path`), jamais a cote du code. Un fichier perime
        # EMBARQUE ne serait donc pas remplace, et `model_path()` continuerait
        # de le preferer : on le dit au lieu d'envoyer tourner en rond.
        if model_path() == bundled_model_path():
            print("[ONNX] ce fichier est celui LIVRE AVEC LE CODE : le "
                  "telechargement ne peut pas le remplacer. Le regenerer "
                  "(scripts/export_onnx_model.py) ou le supprimer.")
    dlg = OnnxDownloadDialog()
    accepted = dlg.exec() == QDialog.DialogCode.Accepted
    dlg.finish_worker()
    return accepted

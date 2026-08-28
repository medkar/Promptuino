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


def _model_path() -> Path:
    """Emplacement local du modele.onnx.

    Aligne sur la logique de `ui/rag.py` : `Path(__file__).parent.parent`
    pointe vers le repo root en dev et vers `_internal/` en mode PyInstaller
    bundle (convention 6.x). Mauvais piege a eviter : `sys.executable.parent`
    pointe vers le dossier ROOT du bundle (= sibling de `_internal/`), pas
    vers `_internal/` lui-meme.
    """
    base = Path(__file__).resolve().parent.parent
    return base / "assets" / "rag" / "model" / "model.onnx"


def is_model_available() -> bool:
    """True si le model.onnx local existe et n'est pas vide."""
    p = _model_path()
    return p.exists() and p.stat().st_size > 1_000_000   # > 1 MiB sanity


def get_model_url() -> str:
    """URL effective (env var override si presente, sinon constante)."""
    return os.environ.get("PROMPTUINO_ONNX_URL") or ONNX_MODEL_URL


# ─── Worker thread de telechargement ─────────────────────────────────────
class _DownloadWorker(QThread):
    """Telecharge le modele en arriere-plan, emet progress / done / failed."""
    progress = pyqtSignal(int, int)   # (bytes_done, bytes_total)
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
                "User-Agent": "PromptuinoUI/1.0 (model-download)",
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
                            self.failed.emit("Telechargement annule par l'utilisateur.")
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
                    self.failed.emit(
                        "Le fichier telecharge ne correspond pas au checksum attendu.\n"
                        "Le serveur a peut-etre renvoye un fichier corrompu."
                    )
                    return
            # Renomme le .partial -> .onnx
            if self._dest.exists():
                self._dest.unlink()
            tmp.rename(self._dest)
            self.done.emit()
        except urllib.error.HTTPError as e:
            tmp.unlink(missing_ok=True)
            self.failed.emit(f"Erreur HTTP {e.code} : {e.reason}")
        except urllib.error.URLError as e:
            tmp.unlink(missing_ok=True)
            self.failed.emit(f"Erreur reseau : {e.reason}")
        except Exception as e:
            tmp.unlink(missing_ok=True)
            self.failed.emit(f"Erreur inattendue : {type(e).__name__}: {e}")


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
        self.setWindowTitle("Configuration initiale - PromptuinoUI")
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

        title = QLabel("Telechargement du modele de recherche")
        title.setStyleSheet("font-size: 13pt; font-weight: 600;")
        layout.addWidget(title)

        desc = QLabel(
            "PromptuinoUI a besoin d'un modele d'embedding (~449 Mo) pour la "
            "recommandation de librairies Arduino. Ce fichier n'est telecharge "
            "qu'une seule fois, puis stocke localement."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self._status = QLabel("Pret a telecharger.")
        layout.addWidget(self._status)

        self._progress = QProgressBar()
        self._progress.setMinimum(0)
        self._progress.setMaximum(100)
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_cancel = QPushButton("Annuler")
        self._btn_cancel.clicked.connect(self._on_cancel)
        btn_row.addWidget(self._btn_cancel)
        self._btn_start = QPushButton("Telecharger")
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
                self, "URL non configuree",
                "L'URL du modele ONNX n'est pas configuree.\n\n"
                "Edite ui/onnx_setup.py:ONNX_MODEL_URL ou positionne la "
                "variable d'environnement PROMPTUINO_ONNX_URL.",
            )
            return
        dest = _model_path()
        self._btn_start.setEnabled(False)
        self._status.setText(f"Telechargement en cours depuis {url}...")
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
            f"Telechargement : {mb_done:.1f} / {mb_total:.1f} Mo  ({pct}%)"
        )

    def _on_done(self) -> None:
        self._progress.setValue(100)
        self._status.setText("Telechargement termine.")
        self.accept()

    def _on_failed(self, msg: str) -> None:
        self._btn_start.setEnabled(True)
        self._status.setText("Echec.")
        QMessageBox.critical(self, "Erreur de telechargement", msg)

    def _on_cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        self.reject()

    def closeEvent(self, event) -> None:
        self._on_cancel()
        super().closeEvent(event)


def ensure_model_or_exit(app: QApplication | None = None) -> bool:
    """Verifie que le modele est present, propose le DL sinon.

    A appeler depuis main() AVANT MainWindow().

    Returns:
        True si le modele est disponible (existant ou DL reussi)
        False si l'utilisateur a annule (caller doit sortir)
    """
    if is_model_available():
        return True
    dlg = OnnxDownloadDialog()
    return dlg.exec() == QDialog.DialogCode.Accepted

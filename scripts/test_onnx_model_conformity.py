"""Un modele ONNX PERIME doit etre remplace, pas accepte en silence.

Question posee par l'utilisateur le 2026-10-27, en regardant une release
partir : *« que se passerait-il si sur une prochaine release je change le
modele ONNX, et qu'un utilisateur fait une mise a jour ? »*

La reponse etait : **rien**, et c'etait un defaut latent.

    ensure_model_or_exit()  ->  if is_model_available(): return True
    is_model_available()    ->  le fichier existe ET fait plus d'1 Mio.

L'empreinte `ONNX_MODEL_SHA256` n'etait verifiee que dans le chemin de
TELECHARGEMENT, donc sur un fichier qu'on venait de recevoir. Un fichier
deja present n'etait jamais controle : l'utilisateur qui met a jour garde le
sien, pendant que `assets/rag/embeddings.npy` arrive en version NEUVE dans
l'installeur.

⛔ **Et rien ne l'aurait dit.** La seule garde d'execution compare le NOMBRE
DE LIGNES de la matrice au nombre d'entrees du corpus -- or ces deux fichiers
voyagent ensemble, leurs comptes s'accordent toujours. L'application ne
plante pas : elle produit des vecteurs issus d'un autre export et degrade la
recherche de bibliotheques EN SILENCE. C'est la panne exacte que la constante
existe pour empecher ; elle gardait la mauvaise porte.

⚠️ Les tests ci-dessous fabriquent de PETITS fichiers et detournent les
constantes : le predicat est generique, et on ne peut pas forger 470 Mio
ayant l'empreinte attendue. Ce qui est verrouille, c'est qu'il SAIT DIRE NON
-- un controle qui ne refuse jamais rien passerait au vert sur n'importe quoi.

Run: python scripts/test_onnx_model_conformity.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")

from PyQt6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv)

import ui.onnx_setup as onnx  # noqa: E402


def _fichier(octets: bytes) -> Path:
    d = Path(tempfile.mkdtemp(prefix="onnx_test_"))
    p = d / "model.onnx"
    p.write_bytes(octets)
    return p


class _Decor:
    """Detourne `model_path` et les deux constantes le temps d'un test."""

    def __init__(self, chemin: Path, taille=None, sha=None):
        self.c, self.taille, self.sha = chemin, taille, sha

    def __enter__(self):
        self.vrais = (onnx.model_path, onnx.ONNX_MODEL_SIZE_BYTES,
                      onnx.ONNX_MODEL_SHA256)
        onnx.model_path = lambda: self.c
        onnx.ONNX_MODEL_SIZE_BYTES = self.taille
        onnx.ONNX_MODEL_SHA256 = self.sha
        return self

    def __exit__(self, *a):
        (onnx.model_path, onnx.ONNX_MODEL_SIZE_BYTES,
         onnx.ONNX_MODEL_SHA256) = self.vrais


_BON = b"le modele attendu" * 100
_SHA_BON = hashlib.sha256(_BON).hexdigest()


# ── le predicat sait dire OUI ─────────────────────────────────────────────

def test_the_expected_file_is_accepted():
    p = _fichier(_BON)
    with _Decor(p, len(_BON), _SHA_BON):
        ok, raison = onnx.modele_conforme()
    assert ok, raison


# ── et surtout NON : c'est tout l'objet du ticket ─────────────────────────

def test_a_model_of_another_size_is_refused():
    """LE cas du ticket : une version suivante embarque un autre export. Les
    deux exports connus du meme modele different de 84 622 octets."""
    p = _fichier(_BON + b"quatre octets de plus")
    with _Decor(p, len(_BON), _SHA_BON):
        ok, raison = onnx.modele_conforme()
    assert not ok
    assert "taille" in raison, raison


def test_a_corrupted_file_of_the_SAME_size_is_refused():
    """La taille seule ne suffit pas : deux fichiers de meme longueur peuvent
    differer. C'est ce que l'empreinte attrape, et la raison pour laquelle on
    paie 0,43 s au demarrage plutot que de s'arreter a un `stat()`."""
    faux = bytearray(_BON)
    faux[0] ^= 0xFF
    p = _fichier(bytes(faux))
    with _Decor(p, len(_BON), _SHA_BON):
        ok, raison = onnx.modele_conforme()
    assert not ok
    assert "empreinte" in raison, raison


def test_an_absent_file_says_absent():
    """Distinguer << absent >> de << present mais faux >> : le second merite
    un message a l'utilisateur, le premier est le cas nominal d'un poste
    neuf."""
    p = Path(tempfile.mkdtemp(prefix="onnx_test_")) / "model.onnx"
    with _Decor(p, len(_BON), _SHA_BON):
        ok, raison = onnx.modele_conforme()
    assert not ok
    assert raison == "absent", raison


# ── le fil : c'est bien CE controle qui garde la porte ────────────────────

def test_the_gate_no_longer_rests_on_is_model_available_alone():
    """⛔ La regression a ne pas refaire. `is_model_available()` repond
    << un fichier existe et fait plus d'1 Mio >> : elle laissait passer
    n'importe quel modele. Verifie sur la SOURCE, parce que la fonction gardee
    ouvre une fenetre."""
    import inspect
    src = inspect.getsource(onnx.ensure_model_or_exit)
    assert "modele_conforme()" in src, src
    corps = src.split('"""')[-1]          # apres la docstring
    assert "is_model_available()" not in corps, corps


def test_a_stale_BUNDLED_model_is_called_out():
    """Le telechargement ecrit toujours dans l'emplacement INSCRIPTIBLE. Un
    fichier perime livre A COTE DU CODE ne serait donc pas remplace, et
    `model_path()` continuerait de le preferer. Le code doit le DIRE plutot
    que d'envoyer l'utilisateur tourner en rond."""
    import inspect
    src = inspect.getsource(onnx.ensure_model_or_exit)
    assert "bundled_model_path()" in src, src


def test_the_two_constants_are_never_emptied():
    """⛔ « NE PAS REVIDER » dit le commentaire du module, et pour cause : une
    empreinte vide desactive la verification, donc un modele corrompu
    passerait. On verrouille les DEUX, le controle de taille etant le seul
    gratuit."""
    assert onnx.ONNX_MODEL_SHA256, "empreinte vidée"
    assert len(onnx.ONNX_MODEL_SHA256) == 64, onnx.ONNX_MODEL_SHA256
    assert onnx.ONNX_MODEL_SIZE_BYTES > 1_000_000, onnx.ONNX_MODEL_SIZE_BYTES


TESTS = [
    test_the_expected_file_is_accepted,
    test_a_model_of_another_size_is_refused,
    test_a_corrupted_file_of_the_SAME_size_is_refused,
    test_an_absent_file_says_absent,
    test_the_gate_no_longer_rests_on_is_model_available_alone,
    test_a_stale_BUNDLED_model_is_called_out,
    test_the_two_constants_are_never_emptied,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()

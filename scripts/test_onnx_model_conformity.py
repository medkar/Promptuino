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
import pathlib
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


# ── #120 : une empreinte differente est une QUESTION, pas un verdict ───────
# Defaut trouve le 2026-11-05 en lancant l'app : elle a propose de telecharger
# 448 Mo alors que le modele present etait un AUTRE EXPORT du meme modele --
# taille identique a l'octet pres, empreinte differente, et des vecteurs **bit
# a bit identiques** a `embeddings.npy`. La garde posait une question plus
# stricte que ce qu'elle protege.

def test_a_different_export_that_agrees_is_accepted():
    """⛔ LE CAS MESURE. Empreinte differente + vecteurs d'accord = conforme.

    On simule l'accord en detournant le controle comportemental : le juger
    pour de vrai demanderait deux exports ONNX de 448 Mo dans un test.
    """
    p = _fichier(_BON)
    vrai = onnx.modele_accorde_a_la_matrice
    onnx.modele_accorde_a_la_matrice = lambda chemin=None: (True, "")
    try:
        with _Decor(p, len(_BON), "0" * 64):      # empreinte qui ne colle pas
            ok, raison = onnx.modele_conforme()
    finally:
        onnx.modele_accorde_a_la_matrice = vrai
    assert ok, f"un export d'accord doit etre accepte : {raison}"


def test_a_different_export_that_DISAGREES_is_still_refused():
    """⛔ LA GARDE SYMETRIQUE, sans laquelle le correctif serait un no-op.

    C'est le defaut que le #120 (0cd425c) existe pour fermer : un autre
    modele + la matrice livree degradent la recherche EN SILENCE.
    """
    p = _fichier(_BON)
    vrai = onnx.modele_accorde_a_la_matrice
    onnx.modele_accorde_a_la_matrice = lambda chemin=None: (False, "vecteurs differents")
    try:
        with _Decor(p, len(_BON), "0" * 64):
            ok, raison = onnx.modele_conforme()
    finally:
        onnx.modele_accorde_a_la_matrice = vrai
    assert not ok
    assert "empreinte" in raison and "vecteurs" in raison, raison


def test_the_behavioural_check_is_only_asked_after_the_hash_fails():
    """Le cout reste nul dans le cas courant : l'empreinte qui colle ne doit
    JAMAIS declencher le chargement d'une session ONNX (0,92 s mesures)."""
    p = _fichier(_BON)
    appels = []
    vrai = onnx.modele_accorde_a_la_matrice
    onnx.modele_accorde_a_la_matrice = lambda chemin=None: (appels.append(1), (True, ""))[1]
    try:
        with _Decor(p, len(_BON), _SHA_BON):      # empreinte CORRECTE
            ok, _ = onnx.modele_conforme()
    finally:
        onnx.modele_accorde_a_la_matrice = vrai
    assert ok
    assert appels == [], "l'empreinte qui colle ne doit rien demander de plus"


def test_the_behavioural_check_judges_the_file_it_was_given():
    """⛔ Defaut de MA premiere version, attrape par un test existant : le
    controle chargeait le modele que `rag` connait, pas celui qu'on juge. Il
    aurait declare conforme un fichier corrompu -- transformant la garde en
    no-op au lieu de la completer."""
    p = _fichier(b"ceci n'est pas un modele ONNX" * 50)
    ok, raison = onnx.modele_accorde_a_la_matrice(p)
    assert not ok, "un fichier qui n'est pas un modele ne peut pas s'accorder"
    assert "encodeur" in raison or "impossible" in raison, raison


def test_an_unverifiable_check_is_not_an_agreement():
    """« Je n'ai pas pu regarder » n'est pas « d'accord ». Rendre True sur une
    verification impossible ferait accepter n'importe quoi le jour ou la
    matrice manque."""
    import ui.rag as rag
    vrai = rag._EMBEDDINGS_PATH
    rag._EMBEDDINGS_PATH = pathlib.Path("/nexiste/pas/embeddings.npy")
    try:
        ok, raison = onnx.modele_accorde_a_la_matrice()
    finally:
        rag._EMBEDDINGS_PATH = vrai
    assert not ok
    assert raison, "une raison doit etre donnee"


def test_a_raising_check_is_not_an_agreement():
    """⛔ Garde trouvee PAR MUTATION : mon test precedent passait par un
    retour explicite (« matrice absente ») et n'exercait JAMAIS le `except`.
    Transformer ce `except` en `return True` ne faisait rougir personne --
    donc une panne imprevue aurait valu « modele d'accord »."""
    import ui.rag as rag
    vrai = rag.encode

    def _explose(_textes):
        raise RuntimeError("onnxruntime a disparu")

    rag.encode = _explose
    try:
        ok, raison = onnx.modele_accorde_a_la_matrice()
    finally:
        rag.encode = vrai
    assert not ok, "une exception ne vaut PAS un accord"
    assert "impossible" in raison, raison


def test_the_check_leaves_the_runtime_encoder_as_it_found_it():
    """Le controle bascule `rag` sur le fichier juge : il DOIT le rendre.
    Sans ca, l'app tournerait ensuite sur l'encodeur d'un test."""
    import ui.rag as rag
    avant = (rag._model_path, rag._session, rag._tokenizer)
    onnx.modele_accorde_a_la_matrice(_fichier(b"pas un modele" * 100))
    apres = (rag._model_path, rag._session, rag._tokenizer)
    assert avant == apres, "l'etat de `rag` a fui hors du controle"


def test_the_moved_rule_produces_the_same_texts():
    """⛔ La regle du texte d'embedding a DEMENAGE dans `ui/embedding_text.py`
    pour etre partagee avec le producteur de la matrice. Preuve que le
    deplacement n'a rien change : l'empreinte des textes de
    `embeddings.fingerprint.json` doit tomber pile.

    ⚠️ C'est la garde qui compte le plus de ce lot. J'ai failli RECOPIER cette
    regle dans le controle, et ma copie etait fausse sur trois points (prefixe
    du nom, mauvais tokenizer, mots-cles non doubles en minuscules) -- trois
    ecarts invisibles a la relecture, qui auraient fait rougir un modele sain.
    """
    import importlib.util
    import json
    racine = pathlib.Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "b", racine / "scripts" / "build_rag_embeddings.py")
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)

    corpus = json.loads((racine / "assets" / "rag" / "corpus.json")
                        .read_text(encoding="utf-8"))
    fp = json.loads((racine / "assets" / "rag" / "embeddings.fingerprint.json")
                    .read_text(encoding="utf-8"))
    textes = [b._embedding_text(e) for e in corpus]
    assert b._texts_fingerprint(textes) == fp["sha256"], (
        "le texte donne a l'encodeur a CHANGE -- la matrice ne lui correspond "
        "plus, et le controle d'accord rougirait sur un modele sain"
    )


def test_the_builder_does_not_keep_its_own_copy_of_the_rule():
    """Une copie qui traine redevient la source d'une derive."""
    racine = pathlib.Path(__file__).resolve().parents[1]
    src = (racine / "scripts" / "build_rag_embeddings.py").read_text(encoding="utf-8")
    assert "from ui.embedding_text import" in src, (
        "le builder doit IMPORTER la regle, pas la redefinir"
    )
    assert "expanded.append(kl)" not in src, (
        "la construction du texte est encore ecrite dans le builder"
    )


TESTS = [
    test_the_expected_file_is_accepted,
    test_a_model_of_another_size_is_refused,
    test_a_corrupted_file_of_the_SAME_size_is_refused,
    test_an_absent_file_says_absent,
    test_the_gate_no_longer_rests_on_is_model_available_alone,
    test_a_stale_BUNDLED_model_is_called_out,
    test_the_two_constants_are_never_emptied,
    test_a_different_export_that_agrees_is_accepted,
    test_a_different_export_that_DISAGREES_is_still_refused,
    test_the_behavioural_check_is_only_asked_after_the_hash_fails,
    test_the_behavioural_check_judges_the_file_it_was_given,
    test_an_unverifiable_check_is_not_an_agreement,
    test_a_raising_check_is_not_an_agreement,
    test_the_check_leaves_the_runtime_encoder_as_it_found_it,
    test_the_moved_rule_produces_the_same_texts,
    test_the_builder_does_not_keep_its_own_copy_of_the_rule,
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

"""References SERIGRAPHIEES des cartes generiques (TODO #57, 2026-08-26).

L'utilisateur lit ce qui est ecrit sur SA carte (<< KY-040 >>, << GY-909 >>,
<< HW-290 >>), pas le nom de la puce soudee dessus. Ces alias font le pont.

⛔ LA REGLE DE SOURCE, ET C'EST TOUT L'ENJEU. Un alias faux est PIRE que pas
d'alias : il fait affirmer a l'app, avec autorite, le mauvais composant. Le
precedent est ecrit dans le ticket -- un << GY-6180 >> invente le 2026-08-18 --
et le defaut corrige ce jour-la en est la preuve grandeur nature : `gy-87` et
`gy-86` etaient poses sur `hw-612`, qui n'a AUCUNE de leurs puces.

D'ou le critere retenu, volontairement etroit : **la bibliotheque doit nommer
elle-meme la puce ET la carte**, dans l'index Arduino (source de premiere main
-- c'est l'auteur de la lib qui declare quelles cartes elle vise). ⚠️ Ce critere
ne suffit PAS a lui seul : voir `test_a_board_specific_library_is_a_WARNING_
not_a_mapping`, l'erreur que ce fichier a commise a sa premiere version. Mesure du
2026-08-26 : 18 references de carte apparaissent ainsi dans l'index, dont deux
(`gy-30`, `gy-521`) etaient DEJA au corpus, ce qui valide la methode.

⛔ CE QUI A ETE ECARTE, et pourquoi -- a ne pas << completer >> plus tard sans
source :
  - `gy-50`, `gy-512` : la bibliotheque cite la reference sans nommer aucune
    puce. Une reference sans puce n'est pas une correspondance.
  - `hw-201` : capteur d'obstacle infrarouge, alors que `ir_reflective_sensor`
    est un suiveur de ligne (QRE1113). Deux objets voisins, pas le meme -- le
    piege du << connecteur SD contre module SPI >> d'un lot precedent.
  - `vma-430` : module GPS u-blox avec sa PROPRE bibliotheque ; l'aliaser au
    `gps` generique (TinyGPS++) enverrait la mauvaise.
  - `gy-21` : SHT21, alors que le registre connait `sht25` et `si7021`. Meme
    famille, pieces differentes -- exactement la substitution qui compile et se
    trompe en silence.

Run : python scripts/test_board_aliases.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui import component_registry as reg
from ui.hardware_modules import MODULES, detect_module
from ui.rag import named_corpus_libs, prompt_names_a_chip
from ui.registry_lookup import detect_unknown_part_tokens


# Chaque ligne : (reference lue sur la carte, id du corpus vise, la phrase de
# l'index Arduino qui l'affirme). La 3e colonne n'est pas decorative : c'est la
# source, et elle doit rester lisible par la personne qui relira ce fichier.
_ALIAS_CORPUS = (
    ("GY-909", "mlx90614",
     "MLX90614 chip in GY909 Temperature sensor"),
    ("KY-040", "encoder",
     "Library for KY-040 rotary encoders"),
)


def test_a_board_specific_library_is_a_WARNING_not_a_mapping():
    """⛔ L'ERREUR QUE CE FICHIER A LUI-MEME COMMISE, corrigee le 2026-08-27.

    Le critere << la bibliotheque doit nommer la puce ET la carte >> a fait
    ajouter `GY-33 -> adafruit-tcs34725`, sur la foi de cette phrase de l'index
    Arduino : << A library for the GY-33 (TCS34725) colour sensor module >>.
    La source etait bonne ; l'INFERENCE etait fausse.

    Car une bibliotheque qui nomme une carte dit l'une de DEUX choses :
      (a) << je pilote la puce, et cette carte est un breakout transparent >>
          -- le cas du MS5611 de Rob Tillaart, qui cite GY-63 ;
      (b) << je pilote CETTE CARTE, parce que la bibliotheque de la puce n'y
          arrive pas >> -- le cas du GY-33.

    Et (b) est justement le signe qu'il ne faut PAS mapper la carte vers
    l'entree corpus de la puce. Verifie ensuite sur deux sources : le GY-33
    intercale son propre microcontroleur, repond en 0x5A, et la puce nue reste
    injoignable a 0x29. Un utilisateur aurait recu la bibliotheque Adafruit,
    qui parle a 0x29, et n'aurait rien trouve.

    Regle retenue : quand une bibliotheque SPECIFIQUE A LA CARTE existe en plus
    de celle de la puce, c'est un signal de verification, pas une
    correspondance. Le GY-33 est desormais un piege materiel
    (`gy33-mcu-in-front-of-tcs34725`), ce qui est sa juste place.
    """
    libs = [x.get("id") for x in named_corpus_libs("un capteur de couleur GY-33")]
    assert "adafruit-tcs34725" not in libs, libs
    # et la puce elle-meme reste parfaitement joignable
    assert "adafruit-tcs34725" in [
        x.get("id") for x in named_corpus_libs("un capteur TCS34725")]


def test_a_sourced_alias_reaches_the_library_of_its_own_chip():
    """Le coeur du chantier : lire la serigraphie suffit."""
    for ref, corpus_id, _source in _ALIAS_CORPUS:
        libs = [x.get("id") for x in named_corpus_libs(f"j'utilise un {ref}")]
        assert corpus_id in libs, (ref, corpus_id, libs)


def test_a_sourced_alias_makes_the_header_authoritative():
    """Nommer sa carte DOIT valoir nommer sa puce.

    `prompt_names_a_chip` decide de l'autorite de l'en-tete RAG : imperatif
    quand l'utilisateur a nomme sa reference, hedge quand l'app a devine. Un
    alias qui resoudrait la bibliotheque sans basculer ce drapeau laisserait le
    modele libre d'ignorer la bonne lib."""
    for ref, _corpus_id, _source in _ALIAS_CORPUS:
        assert prompt_names_a_chip(f"j'utilise un {ref}") is True, ref


def test_a_sourced_alias_is_no_longer_an_unknown_part():
    """L'autre moitie du benefice, et elle est facile a perdre de vue.

    Sans l'alias, << GY-33 >> a la forme d'un numero de piece inconnu : le
    retrieval semantique est COUPE et une recherche au registre Arduino part
    pour rien. L'alias doit donc aussi retirer le jeton de cette liste."""
    for ref, _corpus_id, _source in _ALIAS_CORPUS:
        assert detect_unknown_part_tokens(f"j'utilise un {ref}") == [], ref


def test_the_boards_that_are_the_same_board_share_one_module():
    """`hw-290` et `gy-87` sont LA MEME carte, serigraphiee autrement selon le
    revendeur. C'est le cas d'usage qui a motive ce chantier, et il ne se
    represente pas comme deux modules."""
    a, b = detect_module("ma carte GY-87"), detect_module("ma carte HW-290")
    assert a is not None and b is not None
    assert a.id == b.id == "gy-87", (a, b)


def test_no_board_reference_is_claimed_by_two_components():
    """La garde de collision, transposee des pieges materiels.

    Deux composants qui revendiquent la meme serigraphie, c'est une source
    fausse quelque part : une carte porte les puces qu'elle porte. Le defaut
    corrige le 2026-08-26 avait exactement cette forme -- `gy-87` vivait sur
    `hw-612` alors qu'il decrit une autre carte."""
    vus: dict[str, str] = {}
    doublons = []
    for comp in reg.REGISTRY:
        for kw in comp.keywords:
            k = kw.lower().replace(" ", "").replace("-", "")
            if not _looks_like_a_board_reference(k):
                continue
            if k in vus and vus[k] != comp.id:
                doublons.append((k, vus[k], comp.id))
            vus[k] = comp.id
    assert doublons == [], doublons


def _looks_like_a_board_reference(token: str) -> bool:
    """gy87 / hw290 / ky040 : deux a cinq lettres de famille, puis des chiffres."""
    import re
    return bool(re.fullmatch(r"(gy|hw|ky|cjmcu|zs|vma)\d{2,4}", token))


def test_every_module_is_named_and_labelled():
    """Un module est une boite DESSINEE : sans nom court il sort vide, sans
    libelle traduit les instructions affichent son id brut."""
    from ui.wiring.component_names import short_name
    from ui.wiring.instructions import _TYPE_LABEL
    for m in MODULES:
        nom = short_name(m.id, "fr")
        assert nom and len(nom) <= 13, (m.id, nom)
        assert m.id in _TYPE_LABEL, m.id
        for lang in ("fr", "en", "es", "it"):
            assert _TYPE_LABEL[m.id].get(lang), (m.id, lang)


def test_a_module_never_forces_a_library_of_a_chip_it_lacks():
    """LA GARDE QUI AURAIT ATTRAPE LE DEFAUT DE 2026-08-26.

    Elle part de la reference que l'utilisateur ecrit, va jusqu'aux
    bibliotheques REELLEMENT forcees, et verifie qu'aucune n'appartient a une
    puce absente de la carte. Une garde qui se serait contentee de comparer des
    ids de modules aurait laisse passer `gy-87` -> `hw-612`."""
    from ui.rag import module_forced_libs
    for ref, module_id in (("GY-87", "gy-87"), ("HW-290", "gy-87"),
                           ("GY-86", "gy-86"), ("GY-91", "hw-612"),
                           ("GY-80", "gy-80"), ("GY-85", "gy-85")):
        mod = detect_module(f"ma carte {ref}")
        assert mod is not None and mod.id == module_id, (ref, mod)
        autorises = set()
        for chip in mod.chips:
            comp = reg.by_id(chip)
            autorises.update(comp.documents if comp else (chip,))
        for lib in module_forced_libs(f"ma carte {ref}"):
            assert lib.get("id") in autorises, (ref, lib.get("id"), autorises)


TESTS = [
    test_a_board_specific_library_is_a_WARNING_not_a_mapping,
    test_a_sourced_alias_reaches_the_library_of_its_own_chip,
    test_a_sourced_alias_makes_the_header_authoritative,
    test_a_sourced_alias_is_no_longer_an_unknown_part,
    test_the_boards_that_are_the_same_board_share_one_module,
    test_no_board_reference_is_claimed_by_two_components,
    test_every_module_is_named_and_labelled,
    test_a_module_never_forces_a_library_of_a_chip_it_lacks,
]


def main() -> int:
    for t in TESTS:
        t()
        print(f"  OK {t.__name__}")
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

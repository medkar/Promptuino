"""La reference serigraphiee sur la carte doit suffire (TODO #54, etape 2).

Le constat qui a lance ceci : un debutant lit ce qui est ecrit sur sa carte —
« GY-521 », « GY-80 » — pas la datasheet de la puce qui est dessus. Mesure du
2026-08-18, AVANT ce lot : AUCUNE reference GY-xxx n'etait reconnue. Elles
partaient toutes au registre Arduino, qui ne trouve rien : il n'existe pas de
bibliotheque « GY-521 », la puce dessus est un MPU6050. L'app repondait donc
« composant inconnu » sur du materiel parfaitement connu d'elle.

Deux mecanismes, et le choix entre eux n'est pas cosmetique :

  - Carte a UNE puce (GY-521 = MPU6050) -> ALIAS dans les `keywords` de
    l'entree corpus. C'est le motif deja documente pour VMA335 = BME280 :
    `prompt_names_a_chip` et le boost lexical lisent `corpus.json`
    directement, donc AUCUN rebuild des embeddings.
  - Carte a PLUSIEURS puces (GY-80 = ADXL345 + L3G4200D + HMC5883L + BMP085)
    -> `HardwareModule`. C'est ce que `hardware_modules` existe pour dire, et
    ce qui permet au cablage de fusionner la boite.

⚠️ Forme JOINTE obligatoire cote corpus. `_signature_tokens` ne garde que les
jetons de >= 4 caracteres AVEC un chiffre : « GY-521 » se decoupe en `gy` +
`521`, dont aucun ne passe. C'est `gy521` qui devient le jeton, et le prompt le
produit grace au joint des tirets de `_prompt_tokens` (TODO #56).

Run : python scripts/test_board_references.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui.rag as rag
from ui.hardware_modules import MODULES, detect_module

# (prompt realiste, document corpus attendu). Realiste et non « utilise un
# GY-30 » : un prompt qui ne dit RIEN a faire n'a pas de quoi franchir le
# plancher, boost ou pas, et le tester serait tester le plancher.
CARTES_UNE_PUCE = [
    ("lis l'accelerometre de mon GY-521",                "adafruit-mpu6050"),
    ("lis les axes de mon GY-52",                        "adafruit-mpu6050"),
    ("mesure la luminosite en lux avec un GY-302",       "bh1750"),
    ("mesure la luminosite avec un GY-30",               "bh1750"),
    ("lis la boussole GY-271",                           "hmc5883l"),
    ("lis le magnetometre GY-273",                       "hmc5883l"),
    ("mesure la temperature sans contact avec un GY-906", "mlx90614"),
    ("lis la centrale inertielle GY-9250",               "mpu9250"),
]


def test_a_single_chip_board_reference_retrieves_its_chip():
    rates = []
    for prompt, doc in CARTES_UNE_PUCE:
        libs = rag.retrieve_libs(prompt, k=3, threshold=rag._CODEGEN_MIN_SCORE)
        if not libs or libs[0].get("id") != doc:
            rates.append((prompt, doc, [l.get("id") for l in libs]))
    assert not rates, rates


def test_a_board_reference_counts_as_naming_a_component():
    """Sinon la lib arriverait sous en-tete HEDGE, cf. #37 et TODO #56."""
    for prompt, _ in CARTES_UNE_PUCE:
        assert rag.prompt_names_a_chip(prompt), prompt


def test_an_invented_reference_is_still_unknown():
    """La contrepartie sans laquelle le reste ne vaut rien.

    Les alias ne doivent pas rendre l'app credule : une reference qui n'existe
    pas doit rester inconnue, sinon elle serait servie avec autorite.
    """
    for faux in ("utilise un GY-999", "lis un GY-4242", "branche un ZZ-521"):
        assert not rag.prompt_names_a_chip(faux), faux


def test_the_multi_chip_boards_force_their_chips():
    """✅ 2026-08-26 (#54, derniere etape) : les deux cartes sont COMPLETES.

    Elles etaient declarees "volontairement PARTIELLES" dans
    `hardware_modules.py` — plus maintenant. Une puce ne force sa bibliotheque
    que si elle a un DOCUMENT corpus : `bmp085` a recu le sien au lot #60
    (2026-08-21), `l3g4200d` et `itg3200` le leur ici. GY-80 passe de 3/4 a
    4/4, GY-85 de 2/3 a 3/3."""
    attendus = {
        "je branche un GY-80 sur mon Arduino": {"adxl345", "hmc5883l",
                                                "bmp085", "l3g4200d"},
        "lis les 9 axes de mon GY-85":         {"adxl345", "hmc5883l",
                                                "itg3200"},
        "un hw-612":                           {"mpu9250", "bmp280"},
    }
    for prompt, docs in attendus.items():
        forcees = {l["id"] for l in rag.module_forced_libs(prompt)}
        assert forcees == docs, (prompt, sorted(forcees), sorted(docs))


def test_the_module_separator_is_tolerated():
    """« GY-80 », « GY80 » et « GY 80 » designent la meme carte."""
    for ecriture in ("GY-80", "GY80", "gy 80"):
        m = detect_module(f"je branche un {ecriture}")
        assert m is not None and m.id == "gy-80", ecriture


def test_a_module_reference_does_not_leak_into_a_neighbour():
    """GY-80 et GY-85 sont deux cartes differentes, et « 10 dof » appartient
    au HW-612 — teste en premier. Une collision d'alias ferait forcer les puces
    de la mauvaise carte, en silence."""
    assert detect_module("un GY-85").id == "gy-85"
    assert detect_module("un GY-80").id == "gy-80"
    assert detect_module("une centrale 10 dof").id == "hw-612"


def test_every_added_alias_points_at_an_existing_entry():
    """Garde de derive : un alias vers un document supprime ne dirait rien."""
    corpus = json.loads((ROOT / "assets" / "rag" / "corpus.json")
                        .read_text(encoding="utf-8"))
    ids = {e["id"] for e in corpus}
    manquants = sorted({doc for _, doc in CARTES_UNE_PUCE if doc not in ids})
    assert not manquants, manquants


def test_the_corpus_still_has_the_same_number_of_entries():
    """Les alias de CE lot (references de cartes) s'ajoutent aux mots-cles
    d'entrees EXISTANTES, jamais en creant un doublon — c'est ce qui permet
    de ne PAS reconstruire les embeddings pour EUX : `prompt_names_a_chip` et
    le boost lexical lisent corpus.json directement, alignes par position sur
    la matrice d'embeddings.

    155 est une CARACTERISATION de l'etat actuel, pas un invariant : le
    corpus #60 (2026-08-21) a fait grossir le compte de 91 a 137 en ajoutant
    46 vraies nouvelles entrees (2 des 48 composants vises, max1704x et
    microsd_card_module, ont suivi la meme regle d'alias que ce test decrit
    et n'ont donc PAS grossi le compte) — et CE lot-la a bel et bien
    reconstruit les embeddings (`python scripts/build_rag_embeddings.py`).
    Si ce nombre bouge encore, verifier lequel des deux mecanismes a ete
    utilise et reconstruire les embeddings en consequence ; ce test existe
    pour forcer ce constat, pas pour l'empecher.

    137 -> 139 le 2026-08-26 (#54, derniere etape) : `l3g4200d` et `itg3200`,
    puis 139 -> 155 le 2026-08-27 (#69) : le lot d'identites revele par le
    balayage des serigraphies rejoint le corpus, pour que la bibliotheque
    vienne d'UNE source au lieu d'etre devinee en direct a chaque prompt.
    les deux gyroscopes qui manquaient a GY-80 et GY-85. Mecanisme 2 (vraies
    entrees), donc embeddings RECONSTRUITS — et verifies bit a bit : les 137
    premieres lignes de la matrice sont inchangees, les deux neuves sont en
    position 137 et 138, exactement la ou le corpus les met. C'est cette
    verification-la qui garantit l'alignement, pas le compte de lignes de
    `test_rag_corpus_sync`."""
    corpus = json.loads((ROOT / "assets" / "rag" / "corpus.json")
                        .read_text(encoding="utf-8"))
    assert len(corpus) == 155, len(corpus)


TESTS = [
    test_a_single_chip_board_reference_retrieves_its_chip,
    test_a_board_reference_counts_as_naming_a_component,
    test_an_invented_reference_is_still_unknown,
    test_the_multi_chip_boards_force_their_chips,
    test_the_module_separator_is_tolerated,
    test_a_module_reference_does_not_leak_into_a_neighbour,
    test_every_added_alias_points_at_an_existing_entry,
    test_the_corpus_still_has_the_same_number_of_entries,
]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  OK   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERR  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} test(s) au vert")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

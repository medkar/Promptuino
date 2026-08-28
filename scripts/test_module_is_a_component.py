"""Un module EST un composant, et il en CONTIENT d'autres.

Pour l'utilisateur, une carte GY-80 est un objet qu'il possede : un composant.
Elle porte quatre puces, qui sont elles aussi des composants. L'architecture ne
disait pas ca : `HardwareModule` etait un objet SEPARE du registre, et les trois
modules n'existaient donc nulle part comme identite.

Mesure du 2026-08-18, AVANT ce changement : `hw-612`, `gy-80` et `gy-85`
etaient absents du registre, et l'onglet Composants rendait ZERO fiche pour
« hw-612 » comme pour « GY-80 ». Un utilisateur qui possede un HW-612 ne le
trouvait pas dans sa bibliotheque, alors que l'app le reconnait, force ses
bibliotheques et fusionne sa boite dans le schema.

Ce que ca coutait, constate sur piece : GY-80 et GY-85 ont ete ajoutes sans
libelle humain et AUCUNE garde ne l'a vu, parce que la garde des libelles
verifie contre le REGISTRE et que les modules n'y etaient pas. Le schema aurait
affiche le slug brut. Ce qui n'est pas un composant echappe aux gardes qui
protegent les composants.

La composition est de l'IDENTITE, pas du dessin : « un GY-80 est une carte qui
porte ces quatre puces » decrit ce que l'objet EST. Elle vit donc dans le
registre (`Component.contains`), et `HardwareModule` la LIT au lieu de la
redeclarer -- une seule source de verite, pas deux listes a garder d'accord.

Run : python scripts/test_module_is_a_component.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui.component_registry as reg
from ui.hardware_modules import MODULES, detect_module

MODULE_IDS = ("hw-612", "gy-80", "gy-85")


def test_every_module_is_a_registry_component():
    absents = [m.id for m in MODULES if reg.by_id(m.id) is None]
    assert not absents, (
        f"ces modules n'existent nulle part comme identite : {absents}")


def test_a_module_declares_what_it_contains():
    for m in MODULES:
        c = reg.by_id(m.id)
        assert c.contains, f"{m.id} ne declare aucune puce"


def test_everything_a_component_contains_resolves():
    """Garde de derive. Une puce fantome ferait un module a moitie applique,
    en silence -- exactement ce que la jointure par egalite de chaine faisait
    avant le 2026-08-18."""
    ids = {c.id for c in reg.registry()}
    pendantes = sorted({p for c in reg.registry() for p in c.contains
                        if p not in ids})
    assert not pendantes, pendantes


def test_an_ordinary_component_contains_nothing():
    """`contains` est vide par defaut : seule une carte multi-puces en a un."""
    for cid in ("led", "dht22", "bh1750"):
        assert reg.by_id(cid).contains == (), cid


def test_the_module_chips_come_from_the_registry():
    """UNE source de verite. `HardwareModule.chips` lit `Component.contains`
    au lieu de le redeclarer : deux listes divergeraient, et la divergence ne
    se verrait qu'a la generation."""
    for m in MODULES:
        assert tuple(m.chips) == reg.by_id(m.id).contains, m.id


def test_the_module_keywords_come_from_the_registry():
    """Meme raison, et c'est ce qui rend le module CHERCHABLE dans l'onglet."""
    for m in MODULES:
        assert tuple(m.keywords) == reg.by_id(m.id).keywords, m.id
        assert m.keywords, f"{m.id} sans mot-cle ne serait jamais detecte"


def test_a_module_is_findable_in_the_components_tab():
    from ui.component_index import build_index, filter_components
    import ui.declared_components as dc
    dc.set_registry([])
    comps = build_index()
    for requete in ("hw-612", "GY-80", "GY-85"):
        out = filter_components(comps, query=requete)
        assert out, f"aucune fiche pour {requete!r}"


def test_every_module_has_a_human_label_in_the_four_languages():
    """Le defaut introduit le 2026-08-18 et que rien n'avait vu."""
    from ui.wiring.instructions import _TYPE_LABEL
    for mid in MODULE_IDS:
        libelles = _TYPE_LABEL.get(mid)
        assert libelles, f"{mid} s'afficherait comme slug brut"
        for lang in ("fr", "en", "es", "it"):
            assert libelles.get(lang, "").strip(), f"{mid}/{lang}"


def test_detection_still_works_after_the_move():
    """Les mots-cles ont demenage ; la detection doit etre inchangee."""
    assert detect_module("un hw-612").id == "hw-612"
    assert detect_module("je branche un GY-80").id == "gy-80"
    assert detect_module("un GY 85").id == "gy-85"
    assert detect_module("une centrale 10 dof").id == "hw-612"
    assert detect_module("un capteur de temperature") is None


def test_the_modules_still_force_their_libraries():
    """✅ 2026-08-26 (#54, derniere etape) : les DEUX cartes sont COMPLETES.

    Chronologie, parce qu'elle explique pourquoi ce test a change deux fois :
    au depart GY-80 ne forcait que 2 puces sur 4 et GY-85 2 sur 3 ; le lot #60
    (2026-08-21) a donne son entree corpus a `bmp085` (GY-80 -> 3/4) ; ce
    lot-ci donne la leur a `l3g4200d` et `itg3200`, les deux gyroscopes.

    Une puce ne peut etre forcee que si elle a un DOCUMENT corpus : le module
    connait ses puces par le registre, mais ce qu'il force est leur
    bibliotheque, et c'est le corpus qui la porte. Une puce sans document est
    donc nommee au modele sans que sa lib le soit -- ce que ce test rendait
    visible."""
    from ui.rag import module_forced_libs
    attendus = {
        "un hw-612": {"mpu9250", "bmp280"},
        "un GY-80":  {"adxl345", "hmc5883l", "bmp085", "l3g4200d"},
        "un GY-85":  {"adxl345", "hmc5883l", "itg3200"},
    }
    for prompt, docs in attendus.items():
        assert {l["id"] for l in module_forced_libs(prompt)} == docs, prompt


TESTS = [
    test_every_module_is_a_registry_component,
    test_a_module_declares_what_it_contains,
    test_everything_a_component_contains_resolves,
    test_an_ordinary_component_contains_nothing,
    test_the_module_chips_come_from_the_registry,
    test_the_module_keywords_come_from_the_registry,
    test_a_module_is_findable_in_the_components_tab,
    test_every_module_has_a_human_label_in_the_four_languages,
    test_detection_still_works_after_the_move,
    test_the_modules_still_force_their_libraries,
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

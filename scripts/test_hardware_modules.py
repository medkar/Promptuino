"""Registre des modules hardware nommés (ui/hardware_modules.py)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.hardware_modules import detect_module, MODULES, HardwareModule


def test_hw612_detected_multilingual():
    """⚠️ CE TEST AFFIRMAIT LE DEFAUT jusqu'au 2026-08-26 (TODO #57).

    Il exigeait que << lis le module GY-87 >> et << modulo gy-86 >> resolvent
    vers `hw-612`. Or cette carte porte un MPU9250 + BMP280, la GY-87 un
    MPU6050 + HMC5883L + BMP180 et la GY-86 un MPU6050 + HMC5883L + MS5611 :
    aucune puce commune avec le hw-612 pour la premiere, aucune non plus pour
    la seconde. L'utilisateur qui lisait la serigraphie de SA carte se voyait
    forcer les bibliotheques de puces qu'elle n'a pas -- exactement le defaut
    que ce projet combat partout ailleurs : affirmer, avec autorite, le
    mauvais composant.

    Les deux cartes ont desormais leur propre module ; ce test ne garde plus
    que ce qui est vrai du hw-612, `gy-91` compris (celle-la EST un
    MPU9250 + BMP280)."""
    for p in ("fais un truc avec un HW-612", "utilise mon hw612",
              "lis le module GY-91", "10 DOF imu"):
        m = detect_module(p)
        assert m is not None and m.id == "hw-612", (p, m)


def test_a_board_resolves_to_the_module_that_has_ITS_chips():
    """La garde qui empeche le retour du defaut ci-dessus.

    Elle ne verifie pas seulement l'id du module : elle verifie que les puces
    du module detecte sont bien celles de la CARTE. Un futur alias pose sur le
    mauvais module repasserait le test d'id ; il ne passe pas celui-ci.

    Sources (2026-08-26) : la composition de chaque carte est affirmee par ses
    revendeurs, et pour le GY-87 par la bibliotheque << HW290 >> de l'index
    Arduino elle-meme. `hw-290` est un ALIAS du GY-87, pas une autre carte :
    c'est la meme, serigraphiee differemment selon le revendeur.
    """
    attendu = {
        "GY-87": ("mpu6050", "hmc5883l", "bmp180"),
        "gy87": ("mpu6050", "hmc5883l", "bmp180"),
        "HW-290": ("mpu6050", "hmc5883l", "bmp180"),
        "hw290": ("mpu6050", "hmc5883l", "bmp180"),
        "GY-86": ("mpu6050", "hmc5883l", "ms5611"),
        "gy 86": ("mpu6050", "hmc5883l", "ms5611"),
        "GY-91": ("mpu9250", "bmp280"),
        "HW-612": ("mpu9250", "bmp280"),
    }
    for texte, puces in attendu.items():
        m = detect_module(f"j ai une carte {texte}")
        assert m is not None, texte
        assert m.chips == puces, (texte, m.id, m.chips, puces)


def test_the_boards_that_differ_do_not_share_a_module():
    """Trois cartes, trois modules : elles ne se confondent plus.

    Le GY-86 et le GY-87 ne different que par leur BAROMETRE (MS5611 contre
    BMP180) -- une seule puce sur trois, mais deux bibliotheques differentes.
    C'est exactement l'ecart qu'un alias approximatif efface."""
    ids = {t: detect_module(f"module {t}").id
           for t in ("GY-86", "GY-87", "GY-91")}
    assert len(set(ids.values())) == 3, ids


def test_no_false_positive_on_generic_word():
    # un mot générique isolé ne doit PAS matcher
    for p in ("lis un capteur", "allume une led", "fais un accelerometre"):
        assert detect_module(p) is None, p


def test_chips_are_corpus_ids():
    hw = next(m for m in MODULES if m.id == "hw-612")
    assert hw.chips == ("mpu9250", "bmp280"), hw.chips
    assert hw.i2c_pins == ("VCC", "GND", "SDA", "SCL")


def test_module_forced_libs_returns_chip_entries():
    from ui.rag import module_forced_libs
    libs = module_forced_libs("fais un sketch avec mon HW-612")
    ids = [l.get("id") for l in libs]
    assert ids == ["mpu9250", "bmp280"], ids
    # prompt sans module -> rien de forcé
    assert module_forced_libs("allume une led") == []


def test_module_detected_all_syntaxes():
    # UNE entree canonique doit couvrir toutes les syntaxes.
    for p in ("un HW-612", "hw612", "hw 612", "hw_612",
              "capteur GY-91", "gy91", "gy 91"):
        m = detect_module(p)
        assert m is not None and m.id == "hw-612", (p, m)


def test_no_match_inside_longer_token():
    # Un alias ne doit pas matcher au milieu d'un token alphanumerique plus long.
    for p in ("agy91", "gy910", "hw6120", "xhw612"):
        assert detect_module(p) is None, p


def test_chips_needing_lookup_empty_when_no_module():
    from ui.hardware_modules import module_chips_needing_lookup
    assert module_chips_needing_lookup("allume une led") == []


def test_chips_needing_lookup_empty_when_all_chips_documented():
    # hw-612 : ses deux puces (mpu9250, bmp280) ont un document corpus, donc
    # le chemin SYNCHRONE existant les force deja. Rien a chercher au reseau.
    from ui.hardware_modules import module_chips_needing_lookup
    assert module_chips_needing_lookup("un module HW-612") == []


def test_chips_needing_lookup_returns_libname_only_chips():
    # Registre factice : une puce documentee (ignoree, deja forcee par le
    # chemin synchrone), une puce lib_name-only (RETENUE), une puce sans rien
    # (ignoree, rien de verifie a chercher).
    from ui import component_registry as reg
    from ui.component_registry import Component
    from ui.hardware_modules import module_chips_needing_lookup, HardwareModule
    fake = (
        Component(id="fake-module", function="sensor", mounting="breadboard",
                  wiring="unknown", contains=("chip_doc", "chip_lib", "chip_bare"),
                  keywords=("hw-999",)),
        Component(id="chip_doc", function="sensor", mounting="breadboard",
                  wiring="unknown", documents=("some-doc",)),
        Component(id="chip_lib", function="sensor", mounting="breadboard",
                  wiring="unknown", lib_name="Fake Lib"),
        Component(id="chip_bare", function="sensor", mounting="breadboard",
                  wiring="unknown"),
    )
    fake_mods = (HardwareModule(id="fake-module", label="Fake",
                                i2c_pins=("VCC", "GND", "SDA", "SCL")),)
    original = reg.REGISTRY
    reg.REGISTRY = fake
    try:
        out = module_chips_needing_lookup("j'ai un HW-999", modules=fake_mods)
    finally:
        reg.REGISTRY = original
    assert out == [("Fake Lib", "chip_lib", "fake-module")], out


def test_chips_needing_lookup_on_production_data_gy80():
    """Donnees de PRODUCTION, pas une fixture : gy-80 ACTIVE ce chemin.

    Aucun test n'exercait cette fonction sur MODULES/REGISTRY reels, et c'est
    ce trou qui a laisse passer deux defauts a la fois (revue du 2026-08-20) :
    le tuple rendait un NOM DE BIBLIOTHEQUE la ou tout l'aval attend une
    identite de puce, et la doc affirmait que le chemin « ne s'active pour
    personne ». La fixture voisine ne pouvait rien y faire : elle avait pris
    par coincidence un cas ou id et lib_name coincident, ce qui n'arrive que
    pour 3 des 48 entrees lib_name-only reelles.

    ⚠️ Attendu passe de `[("Adafruit BMP085 Library", "bmp085", "gy-80")]` a
    `[]` le 2026-08-21 (lot #60, task 6) : `bmp085` a recu sa propre entree
    corpus + son `documents` au registre, donc il a maintenant « un document »
    -- exactement le cas que cette fonction, par construction (cf. sa
    docstring), exclut de son retour : le chemin synchrone (`module_forced_libs`)
    le prend desormais en charge directement, plus besoin d'une recherche au
    registre Arduino.

    Consequence assumee : PLUS AUCUNE puce de MODULES n'est aujourd'hui
    lib_name-only-sans-document (verifie -- bmp085 etait la derniere), donc ce
    chemin est desormais inactif sur les donnees de production tant qu'un
    futur module n'introduit pas une nouvelle puce dans ce cas. La semantique
    du tuple (lib_name vs chip_id, l'identite qui doit survivre) reste
    couverte par la fixture `test_chips_needing_lookup_returns_libname_only_chips`
    ci-dessus, qui n'a pas cette dependance a l'etat du registre reel."""
    from ui.hardware_modules import module_chips_needing_lookup

    out = module_chips_needing_lookup("lis la pression avec mon GY-80")
    assert out == [], out


TESTS = [test_hw612_detected_multilingual, test_no_false_positive_on_generic_word,
         test_chips_are_corpus_ids, test_module_forced_libs_returns_chip_entries,
         test_module_detected_all_syntaxes, test_no_match_inside_longer_token,
         test_chips_needing_lookup_empty_when_no_module,
         test_chips_needing_lookup_empty_when_all_chips_documented,
         test_chips_needing_lookup_returns_libname_only_chips,
         test_chips_needing_lookup_on_production_data_gy80,
         test_a_board_resolves_to_the_module_that_has_ITS_chips,
         test_the_boards_that_differ_do_not_share_a_module]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

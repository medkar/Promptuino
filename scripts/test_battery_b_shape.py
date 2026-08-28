"""#60 -- la batterie B est-elle bien FORMEE ? (indépendante de tout corpus)
Run: python scripts/test_battery_b_shape.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BATTERY = ROOT / "scripts" / "bench_rag_prompts_b.json"
LANGS = ("fr", "en", "es", "it")

# ── Deux tables d'exception, ECRITES A LA MAIN ───────────────────────────────
# Aucune des deux n'est une règle devinée : chaque ligne dit pourquoi ce
# composant-là échappe à la forme générale. Une règle déduite se serait élargie
# toute seule au premier cas qui lui ressemble.

# `expect[0]` est TOUJOURS le composant sous test ; les ids suivants sont des
# entrées corpus DÉJÀ présentes qui répondent correctement au même besoin.
# Sans elles, la mesure « avant » compterait `wrong` une bibliothèque exacte,
# et le gain du chantier serait surestimé (c'est le SENS de l'erreur qui compte
# ici, pas son ampleur).
_EQUIVALENT_IDS: dict[str, list[str]] = {
    # bmp085 et bmp180 partagent la même bibliothèque (Adafruit BMP085
    # Library) : celui des deux qui perd serait `wrong` avec la lib exacte.
    "bmp085": ["bmp180"],
    "bmp180": ["bmp085"],
    # L'entrée corpus `max17043` s'appelle « MAX17043/48 I2C LiPo battery fuel
    # gauge » — même famille, même lib.
    "max1704x": ["max17043"],
    # `lib_name` du registre = « SD », et l'entrée corpus `sd` s'appelle « SD ».
    "microsd_card_module": ["sd"],
}

# Deux ids du registre sont des FAMILLES à joker final : aucune puce ne porte
# la référence « MAX1704x » ni « SEN5x » (les vraies sont MAX17043/44/48/49 et
# SEN54/SEN55). Le boost lexical étant un match de token EXACT, écrire le
# joker dans la bande `named` ne pourrait rien atteindre. Les autres familles
# tronquées n'ont pas ce problème : leur id est un PRÉFIXE de la référence
# réelle (`lps28` ⊂ LPS28DFW), donc le token exact existe.
_NAMED_REFERENCE_EXCEPTIONS: dict[str, str] = {
    "max1704x": "max17048",
    "sen5x": "sen55",
}

# Les 48 ids visés par le chantier #60, ECRITS A LA MAIN (même discipline que
# les deux tables ci-dessus) : `_the_48()` filtrait à l'origine sur
# `not c.documents` -- un marqueur valable UNIQUEMENT tant que la task 6 du
# chantier n'avait pas encore rempli ce champ. Une fois `documents` renseigné
# (son but même), ce filtre retombait à zéro composant en silence. La liste
# figée ici reste vraie après coup : elle décrit QUELS composants ce chantier
# visait, pas un état transitoire du registre.
_THE_48_IDS: tuple[str, ...] = (
    "ads7830", "adt7410", "adxl335", "bluefruit_le", "bmp085", "bmp180",
    "dotstar", "drv8825", "ds3502", "eink_display", "esp8266", "fram",
    "gc9a01", "hdc1008", "hdc3021", "hmc6352", "i2c_multiplexer", "ina228",
    "lps28", "lsm303", "mma8452q", "mmc5603", "mpl3115a2", "mpr121",
    "mprls", "mq2", "nau7802", "opt4048", "sen5x", "sharp_memory_display",
    "sht25", "si1145", "si4713", "sim800l", "spi_flash", "stspin220",
    "thermal_printer", "tmc2209", "tmp006", "tmp007", "tmp102", "trellis",
    "tsl2561", "water_flow_sensor", "winc1500", "wiz820io", "max1704x",
    "microsd_card_module",
)


def _cases():
    return json.loads(BATTERY.read_text(encoding="utf-8"))


def _flat(s: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _the_48():
    from ui.component_registry import by_id
    out = [by_id(cid) for cid in _THE_48_IDS]
    missing = [cid for cid, c in zip(_THE_48_IDS, out) if c is None]
    assert not missing, f"ids absents du registre : {missing}"
    return out


def test_every_component_has_eight_cases():
    """48 composants x 2 bandes x 4 langues."""
    cases = _cases()
    ids = {c.id for c in _the_48()}
    assert len(ids) == 48, len(ids)
    for cid in sorted(ids):
        # `expect[0]` = le composant sous test (cf. `_EQUIVALENT_IDS`) : c'est
        # lui qui attribue le cas, pas la liste entière — sinon les 8 cas de
        # bmp085 et les 8 de bmp180 se compteraient deux fois chacun.
        mine = [c for c in cases if c["expect"] and c["expect"][0] == cid]
        assert len(mine) == 8, f"{cid}: {len(mine)} cas (attendu 8)"
        for band in ("described", "named"):
            per_lang = {c["lang"] for c in mine if c["band"] == band}
            assert per_lang == set(LANGS), f"{cid}/{band}: {per_lang}"
    assert len(cases) == 384, len(cases)


def test_the_described_band_never_writes_the_reference():
    """La bande `described` mesure l'atteignabilité SANS référence. Y écrire
    la référence mesurerait le boost lexical, donc la bande `named`.

    DEUX formes, parce qu'aucune ne suffit :

    1. l'id aplati (« dotstar », « fram », « trellis » — pas un chiffre
       dedans, invisible à la règle 2) ;
    2. TOUT token en forme de référence, quel qu'il soit. La v1 de cette garde
       promettait en commentaire de surveiller « les parties alphanumériques
       de 4+ caractères » et ne le faisait pas : « YF-S201 » dans un prompt de
       `water_flow_sensor`, « TCA9548A » dans un de `i2c_multiplexer` ou
       « APA102 » dans un de `dotstar` passaient au vert. La forme retenue est
       celle du code de production (`registry_lookup._is_part_shaped`) : ≥ 4
       caractères, des chiffres ET des lettres.

    On ne DÉLÈGUE pas à `registry_lookup.detect_unknown_part_tokens`, qui
    filtre en plus les tokens que le corpus connaît déjà : la garde
    s'affaiblirait exactement au moment où le chantier ajoute les 48 entrées.
    """
    import re
    # Formes jointes (« ZXQ-9000 » -> « zxq9000ss »), comme la production.
    hyphen = re.compile(r"\b[a-z0-9]+(?:-[a-z0-9]+)+\b")
    word = re.compile(r"[a-z0-9]+")

    def part_shaped(prompt: str) -> list[str]:
        low = prompt.lower()
        toks = word.findall(low) + [m.replace("-", "")
                                    for m in hyphen.findall(low)]
        return sorted({t for t in toks if len(t) >= 4
                       and any(ch.isdigit() for ch in t)
                       and any(ch.isalpha() for ch in t)})

    for c in _cases():
        if c["band"] != "described":
            continue
        cid = c["expect"][0]
        assert _flat(cid) not in _flat(c["prompt"]), \
            f"{cid}: la reference est ecrite dans un prompt `described`"
        found = part_shaped(c["prompt"])
        assert not found, (
            f"{cid}/{c['lang']}: un prompt `described` contient une reference "
            f"en toutes lettres {found}: {c['prompt']!r}")


def test_the_named_band_always_writes_the_reference():
    """La référence attendue est l'id... sauf pour les deux ids à joker.

    `_NAMED_REFERENCE_EXCEPTIONS` (table écrite à la main) : écrire « SEN5x »
    ou « MAX1704x » n'atteindrait rien, le boost lexical étant un match de
    token exact et aucune puce ne portant ces noms-là.
    """
    for c in _cases():
        if c["band"] != "named":
            continue
        cid = c["expect"][0]
        wanted = _NAMED_REFERENCE_EXCEPTIONS.get(cid, cid)
        assert _flat(wanted) in _flat(c["prompt"]), (
            f"{cid}: la reference {wanted!r} manque dans un prompt `named`: "
            f"{c['prompt']!r}")
    # La table ne doit pas survivre à ses composants (id renommé, retiré…).
    ids = {c.id for c in _the_48()}
    for cid in _NAMED_REFERENCE_EXCEPTIONS:
        assert cid in ids, f"exception orpheline: {cid}"


def test_no_prompt_is_reused():
    """Deux composants qui partageraient un prompt rendraient la mesure
    inclassable."""
    cases = _cases()
    seen: dict[str, str] = {}
    for c in cases:
        key = c["prompt"].strip().lower()
        assert key not in seen or seen[key] == c["expect"][0], \
            f"prompt partage par {seen.get(key)} et {c['expect'][0]}: {key!r}"
        seen[key] = c["expect"][0]


def test_every_case_has_the_required_fields():
    for c in _cases():
        for field in ("prompt", "lang", "band", "expect", "added", "source"):
            assert field in c, (field, c)
        assert c["lang"] in LANGS, c
        assert c["band"] in ("described", "named"), c
        # `expect` peut porter PLUSIEURS ids (cf. `_EQUIVALENT_IDS`), mais
        # jamais zéro : un `expect` vide ferait classer `wrong` tout ce qui est
        # injecté, sans que rien ne puisse jamais être correct.
        assert isinstance(c["expect"], list) and c["expect"], c
        cid = c["expect"][0]
        assert c["expect"] == [cid] + _EQUIVALENT_IDS.get(cid, []), (
            "les ids acceptables doivent venir de la table ecrite a la main, "
            "pas d'un ajout au fil de l'eau", c)
        if c["band"] == "described":
            assert c.get("specificity") == "vague", c


def test_no_described_prompt_is_silenced_by_the_basic_component_gate():
    """`rag.build_lib_context` rend un contexte VIDE quand
    `_prompt_is_basic_component(prompt) and not prompt_names_a_chip(prompt)`.

    Un seul mot suffit (« bouton », « led »), et sur la bande `described` —
    qui n'écrit jamais la référence — `prompt_names_a_chip` ne peut PAS
    rattraper : le silence est définitif, quelle que soit l'entrée corpus
    écrite plus tard. Sept prompts étaient dans ce cas, et le dégât était
    asymétrique par langue (« tira »/« striscia » ne sont pas dans les
    exceptions de `led`, « ruban »/« strip » si) : l'écart par langue mesuré
    en fin de chantier aurait porté un artefact qui ne vient pas de la langue.

    La réparation est du côté de la BATTERIE. Retoucher
    `_BASIC_NO_LIB_KEYWORDS` reviendrait à modifier le code de production pour
    faire passer une mesure.
    """
    from ui.rag import _prompt_is_basic_component
    silenced = [(c["expect"][0], c["lang"], c["prompt"])
                for c in _cases()
                if c["band"] == "described"
                and _prompt_is_basic_component(c["prompt"])]
    assert not silenced, silenced


TESTS = [
    test_every_component_has_eight_cases,
    test_the_described_band_never_writes_the_reference,
    test_the_named_band_always_writes_the_reference,
    test_no_prompt_is_reused,
    test_every_case_has_the_required_fields,
    test_no_described_prompt_is_silenced_by_the_basic_component_gate,
]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  OK   {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

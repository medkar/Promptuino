"""TODO #40 (c) — le bloc d'API ne doit pas contredire son propre exemple.

Le defaut, mesure le 2026-08-10 sur les 77 entrees du corpus qui ont a la fois
des signatures et un exemple : **19 d'entre elles injectaient un bloc
contradictoire**. L'en-tete dit « API (use only these — do NOT invent
others) », le plafond coupe la liste a 10 signatures par classe x 2 classes, et
l'exemple officiel — imprime trois lignes plus bas, dans le MEME bloc — appelle
des methodes absentes de cette liste.

Ce que le plafond coupait, ce n'etait pas de l'accessoire :

    adafruit-bme280      readTemperature, readPressure, readHumidity, readAltitude
    dallas-temperature   requestTemperatures, getTempCByIndex
    liquidcrystal-i2c    init, backlight, setCursor
    adafruit-ssd1306     setCursor, setTextColor, setTextSize
    mfrc522              PICC_IsNewCardPresent, PICC_ReadCardSerial
    adafruit-neopixel    Color

Autrement dit la raison d'etre de chaque bibliotheque.

LA CAUSE N'ETAIT PAS LE PLAFOND, C'ETAIT L'ORDRE. La selection prenait les
premieres classes et les premieres methodes dans l'ordre de DECLARATION du
header, qui n'a aucun rapport avec l'usage :

  - BME280 : la vraie classe `Adafruit_BME280` est la 4e sur 4 ; `_MAX_CLASSES`
    valant 2, on emettait deux wrappers unified-sensor que personne n'appelle
    et on n'atteignait jamais les `read*` ;
  - DallasTemperature : les 10 premieres methodes declarees sont des
    constructeurs et du parametrage ; `requestTemperatures` arrive trop loin ;
  - LiquidCrystal_I2C : `init`, `backlight` et `setCursor` sont derriere
    `noBlink`, `noCursor` et consorts.

Le correctif de 2026-08-10 n'a PAS touche aux plafonds : il a change ce qu'on
met dans les 20 places, l'exemple officiel etant la meilleure verite terrain
disponible sur ce qui sert — et il est deja dans le bloc.

⛔ IL N'Y A PLUS DE PLAFOND DU TOUT DEPUIS LE 2026-08-26 (TODO #66).

Deux etapes ce jour-la. D'abord les plafonds ont cede devant l'exemple : trier
ne suffisait pas, car quand l'exemple appelle PLUS de methodes qu'une place ne
le permet, le surplus etait coupe quand meme — cinq entrees (`tmp102`,
`ina228`, `si4713`, `bluefruit_le`, `nau7802`) emettaient encore un bloc
contradictoire. Puis ils ont ete SUPPRIMES, sur mesure et sur decision de
l'utilisateur.

Ce qui les a condamnes : leur justification nommait « Gemma 3 4B », un modele
qui n'a JAMAIS existe dans ce depot (`git log -S "gemma3" --all` est vide, le
defaut a l'epoque etait `gemma4:e2b`), et la panne n'a pas pu etre reproduite.
Le banc `scripts/bench_api_ceiling_scope.py` a ensuite tranche sur 72
generations et 2 modeles : tout injecter ne degrade RIEN (18/18 des deux cotes
sur les taches dans le perimetre de l'exemple, zero fonction inventee), tandis
que le plafond faisait perdre la cible HORS de ce perimetre (2/18 contre
18/18). Il ne provoquait pas d'hallucination — il provoquait du repli
maladroit, et parfois la perte de la tache.

Restent DEUX filtres, qui ne sont pas des plafonds : le dedoublonnage des
surcharges par nom, et `_is_internal_name` pour les aides internes que
l'exemple n'appelle pas. C'est ce que verifie
`test_everything_documented_is_emitted_except_the_two_filters`.

Le tri par l'exemple, lui, RESTE : sans plafond il ne decide plus QUI est emis,
mais il decide encore dans quel ORDRE — et un modele lit une liste du haut vers
le bas.

Run : python scripts/test_api_signature_selection.py
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui import rag

CALL_RE = re.compile(r"\b(\w+)\s*\.\s*(\w+)\s*\(")
# Methodes du coeur Arduino (Serial, String…) : appelees par les exemples mais
# jamais documentees par la lib, donc hors sujet ici.
CORE = {"begin", "print", "println", "write", "read", "available", "flush",
        "printf", "c_str", "length", "toInt", "toFloat", "trim", "concat",
        "equals", "substring", "indexOf", "charAt", "reserve"}


def _emitted(entry: dict) -> set[str]:
    block = rag._format_api_signatures(entry.get("api_signatures") or {},
                                       entry.get("example_code") or "")
    return {rag._function_name(l[4:].strip())
            for l in block.splitlines() if l.startswith("  - ")}


def _documented(entry: dict) -> set[str]:
    api = entry.get("api_signatures") or {}
    return {rag._function_name(s) for v in api.values() for s in v}


def _called_by_example(entry: dict) -> set[str]:
    return {m for _obj, m in CALL_RE.findall(entry.get("example_code") or "")}


def _entries():
    return [e for e in rag.all_corpus_entries()
            if e.get("api_signatures") and e.get("example_code")]


# ── L'invariant du chantier ───────────────────────────────────────────────────

def test_no_block_contradicts_its_own_example():
    """LE test. Toute methode que l'exemple APPELLE et que la lib DOCUMENTE
    doit figurer dans la liste — sinon le bloc dit au modele deux choses
    incompatibles, et lui apprend que la liste n'est pas fiable."""
    fautifs = []
    for e in _entries():
        manquantes = (_called_by_example(e) & _documented(e)) - _emitted(e) - CORE
        if manquantes:
            fautifs.append((e.get("id"), sorted(manquantes)))
    assert not fautifs, f"{len(fautifs)} entrees contradictoires : {fautifs[:6]}"


# ── Les cas nommes, pour que l'echec DISE ce qui est casse ────────────────────

def _emitted_for(cid: str) -> set[str]:
    e = rag.corpus_entry(cid)
    assert e is not None, cid
    return _emitted(e)


def test_bme280_finally_reaches_its_real_class():
    """La classe utile est la 4e sur 4 : c'est le cas ou l'ordre des CLASSES
    (et pas seulement des methodes) decide de tout."""
    emis = _emitted_for("adafruit-bme280")
    assert "readTemperature" in emis, sorted(emis)


def test_dallas_emits_the_two_calls_every_ds18b20_sketch_makes():
    emis = _emitted_for("dallas-temperature")
    assert {"requestTemperatures", "getTempCByIndex"} <= emis, sorted(emis)


def test_lcd_emits_init_backlight_and_setcursor():
    emis = _emitted_for("liquidcrystal-i2c")
    assert {"init", "backlight", "setCursor"} <= emis, sorted(emis)


def test_a_display_can_place_its_text():
    for cid in ("adafruit-ssd1306", "adafruit-ili9341"):
        emis = _emitted_for(cid)
        assert {"setCursor", "setTextSize"} <= emis, (cid, sorted(emis))


def test_neopixel_can_build_a_color():
    assert "Color" in _emitted_for("adafruit-neopixel")


# ── Ce qui ne doit PAS avoir change ───────────────────────────────────────────

def test_everything_documented_is_emitted_except_the_two_filters():
    """LE contrat depuis le 2026-08-26 : il n'y a PLUS de plafond.

    Ce test a porte trois contrats successifs, et les deux premiers sont morts
    de la meme facon — la mesure a rendu leur raison d'etre caduque :

      1. jusqu'au 2026-08-10 : « le bloc ne depasse jamais 20 signatures » ;
      2. jusqu'au 2026-08-26 : « le plafond cede devant l'exemple, et devant
         lui seul » ;
      3. aujourd'hui : « TOUT est emis, sauf deux filtres nommes ».

    Les plafonds sont supprimes parce que le banc a montre qu'ils ne
    protegeaient de rien (zero fonction inventee sur 72 generations) et
    coutaient cher hors du perimetre de l'exemple (2/18 contre 18/18).

    Restent DEUX filtres, et ce ne sont pas des plafonds :
      - le dedoublonnage des surcharges PAR NOM ;
      - `_is_internal_name`, pour les aides internes que l'exemple n'appelle
        pas.

    Ce test verifie exactement ca : ce qui est emis est ce qui est documente,
    aux deux filtres pres. Une entree qui perdrait une methode pour une autre
    raison — un plafond qui reviendrait par la fenetre — le fait rougir.
    """
    manquantes = []
    for e in _entries():
        emis = _emitted(e)
        appelees = _called_by_example(e)
        attendu = {n for n in _documented(e)
                   if not rag._is_internal_name(n) or n in appelees}
        perdu = attendu - emis
        if perdu:
            manquantes.append((e.get("id"), sorted(perdu)[:6]))
    assert not manquantes, (
        f"{len(manquantes)} entrees perdent des signatures que ni le "
        f"dedoublonnage ni le filtre des internes n'expliquent — un plafond "
        f"serait-il revenu ? {manquantes[:4]}")


def test_no_overload_is_emitted_twice():
    """Le dedoublonnage est l'un des deux filtres qui subsistent : sans lui,
    `readline` occuperait six lignes du bloc de `bluefruit_le`."""
    for e in _entries():
        bloc = rag._format_api_signatures(e.get("api_signatures") or {},
                                          e.get("example_code") or "")
        noms = [rag._function_name(l[4:].strip())
                for l in bloc.splitlines() if l.startswith("  - ")]
        # Un meme nom peut legitimement apparaitre dans DEUX classes
        # differentes ; c'est au sein d'une classe que la surcharge se
        # dedoublonne. On compte donc par classe.
        par_classe, courante = {}, None
        for ligne in bloc.splitlines():
            if ligne.startswith("- "):
                courante = ligne[2:].rstrip(":")
                par_classe[courante] = []
            elif ligne.startswith("  - ") and courante:
                par_classe[courante].append(
                    rag._function_name(ligne[4:].strip()))
        for cls, ns in par_classe.items():
            assert len(ns) == len(set(ns)), (e.get("id"), cls,
                                             [n for n in ns if ns.count(n) > 1])


def test_without_an_example_the_order_is_the_declaration_order():
    """Sans exemple, rien ne permet de classer : l'ordre reste celui du header.

    ⚠️ Ce test affirmait AUSSI un nombre — les 10 premieres seulement, soit
    `_MAX_SIGS_PER_CLASS`. Cette moitie-la est morte avec les plafonds
    (2026-08-26) ; l'affirmation sur l'ORDRE, elle, tient toujours et reste ce
    que ce test protege."""
    api = {"C": [f"void m{i}();" for i in range(20)]}
    bloc = rag._format_api_signatures(api)
    noms = [rag._function_name(l[4:].strip())
            for l in bloc.splitlines() if l.startswith("  - ")]
    assert noms == [f"m{i}" for i in range(20)], noms


def test_internals_are_still_filtered_when_the_example_ignores_them():
    api = {"GFX": ["void startWrite();", "void writePixel(int x);",
                   "void fillCircleHelper(int r);", "void drawCircle(int r);"]}
    noms = {rag._function_name(l[4:].strip())
            for l in rag._format_api_signatures(api, "gfx.drawCircle(3);").splitlines()
            if l.startswith("  - ")}
    assert noms == {"drawCircle"}, noms


def test_but_an_internal_the_example_CALLS_is_kept():
    """`writeDisplay` (HT16K33) tombait sous la regle anti-`write*` de GFX,
    alors que l'exemple officiel de la lib l'appelle. Un filtre concu pour une
    bibliotheque ne doit pas amputer une autre."""
    api = {"HT16K33": ["void writeDisplay();", "void setBrightness(int b);"]}
    noms = {rag._function_name(l[4:].strip())
            for l in rag._format_api_signatures(api, "m.writeDisplay();").splitlines()
            if l.startswith("  - ")}
    assert "writeDisplay" in noms, noms


def test_the_block_keeps_its_imperative_header():
    bloc = rag._format_api_signatures({"C": ["void m();"]}, "c.m();")
    assert bloc.startswith("API (use only these")


def test_render_lib_block_passes_the_example_through():
    """Verrou structurel : si `_render_lib_block` cessait de transmettre
    l'exemple, tous les tests ci-dessus resteraient verts en appelant
    `_format_api_signatures` directement, et le defaut reviendrait dans le
    contexte reellement injecte."""
    e = rag.corpus_entry("adafruit-bme280")
    bloc = rag._render_lib_block(dict(e))
    # ⚠️ Chercher « readTemperature » dans le bloc ENTIER serait vert sans rien
    # prouver : l'exemple de code, qui l'appelle, fait partie du bloc. On ne
    # regarde que les lignes de la LISTE d'API.
    liste = {rag._function_name(l[4:].strip())
             for l in bloc.splitlines() if l.startswith("  - ")}
    assert "readTemperature" in liste, sorted(liste)


# ── Le choix de la SURCHARGE emise (QA AB2 ter du #82, 2026-08-31) ──────

def test_the_emitted_overload_follows_the_example_then_simplicity():
    """« Premiere declaree gagne » trahissait un modele obeissant : la lib
    L298N declare `forwardFor(delay, callback)` avant `forwardFor(delay)`,
    donc le bloc n'annoncait que la variante a callback -- et le reparateur,
    somme de suivre « ces signatures exactes », ecrivait un callback invente
    au lieu du correctif d'une ligne (mesure sur la vraie chaine : 0/4 -> 4/4
    une fois la variante simple annoncee).

    Et « la plus simple gagne » TOUT COURT etait pire par endroits : pour un
    CONSTRUCTEUR la plus simple est souvent la degeneree
    (`Adafruit_NeoPixel(void)`, `Encoder()`), et le L298N passait au
    constructeur 2 broches que le cablage ignore deliberement (#83). La regle
    juste est celle du formateur depuis #40 (c) : l'EXEMPLE est la verite
    terrain -- la surcharge dont l'arite colle a l'appel de l'exemple gagne
    (valeurs par defaut respectees), la plus simple quand il se tait.
    """
    from ui.rag import corpus_entry, _format_api_signatures

    def bloc(eid):
        e = corpus_entry(eid)
        return _format_api_signatures(e.get("api_signatures") or {},
                                      e.get("example_code") or "")

    l298n = bloc("l298n")
    # L'exemple instancie a 3 arguments : le constructeur emis les garde.
    assert "L298N(uint8_t pinEnable, uint8_t pinIN1, uint8_t pinIN2)"         in l298n, l298n
    # L'exemple n'appelle pas forwardFor : la variante SIMPLE gagne.
    assert "void forwardFor(unsigned long delay)" in l298n, l298n
    assert "CallBackFunction" not in l298n.split("forwardFor")[1]         .splitlines()[0], l298n

    # Les constructeurs degeneres ne gagnent jamais contre l'exemple.
    assert "Adafruit_NeoPixel(void)" not in bloc("adafruit-neopixel")
    assert "Encoder(uint8_t pin1, uint8_t pin2)" in bloc("encoder")


TESTS = [
    test_no_block_contradicts_its_own_example,
    test_bme280_finally_reaches_its_real_class,
    test_dallas_emits_the_two_calls_every_ds18b20_sketch_makes,
    test_lcd_emits_init_backlight_and_setcursor,
    test_a_display_can_place_its_text,
    test_neopixel_can_build_a_color,
    test_everything_documented_is_emitted_except_the_two_filters,
    test_no_overload_is_emitted_twice,
    test_without_an_example_the_order_is_the_declaration_order,
    test_internals_are_still_filtered_when_the_example_ignores_them,
    test_but_an_internal_the_example_CALLS_is_kept,
    test_the_block_keeps_its_imperative_header,
    test_render_lib_block_passes_the_example_through,
    test_the_emitted_overload_follows_the_example_then_simplicity,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"OK   {t.__name__}")
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)

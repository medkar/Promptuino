"""Pieges materiels au chat : tri structurel + entree BME280/BMP280 (#59).

Run : python scripts/test_chat_hardware_traps.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.chat.chat_prompts import (_is_concept_entry, _format_concepts,
                                  _format_rag)
from ui.chat.chat_rag import (CorpusHit, CorpusIndex, load_concepts,
                              load_default_corpus)


def test_invariant_libraries_carry_no_reference_facts():
    """CE QUI FONDE le tri structurel de `_is_concept_entry`.

    Si une entree de corpus.json gagnait un jour `summary`/`facts`, elle
    basculerait cote « faits de reference » et son bloc de prompt changerait
    sans que personne ne l'ait decide. Ce test force la decision au lieu de
    laisser la derive passer.

    Passe par `load_default_corpus()` (le vrai chemin de production), pas par
    une relecture locale du fichier -- sinon un changement de chemin ferait
    tester un autre fichier que celui que l'app charge reellement.
    """
    offenders = [e.get("id") for e in load_default_corpus()
                 if e.get("summary") or e.get("facts")]
    assert offenders == [], offenders


def test_invariant_concepts_all_carry_reference_facts():
    """L'autre moitie de l'invariant : une entree de concepts.json sans
    `summary` NI `facts` serait rendue comme une bibliotheque fantome
    (« Headers: (no headers) ») et ses faits seraient jetes."""
    offenders = [e.get("id") for e in load_concepts()
                 if not (e.get("summary") or e.get("facts"))]
    assert offenders == [], offenders


def test_a_new_category_is_routed_by_structure_not_by_name():
    """Une categorie INCONNUE de tout code doit etre routee correctement du
    seul fait qu'elle porte des faits. C'est le coeur du chantier : la
    liste blanche precedente l'aurait envoyee cote bibliotheque."""
    entry = {"id": "x", "name": "X", "category": "hardware_trap",
             "summary": "s", "facts": ["f1"]}
    assert _is_concept_entry(entry) is True


def test_a_library_entry_is_still_not_a_concept():
    """Non-regression : une vraie entree de librairie reste cote
    bibliotheque, sinon elle perdrait ses headers dans le prompt."""
    entry = {"id": "servo", "name": "Servo", "category": "Motors",
             "headers": ["Servo.h"], "description": "d"}
    assert _is_concept_entry(entry) is False


def test_facts_reach_the_prompt_for_a_new_category():
    """Le rendu, pas seulement le tri : les faits doivent apparaitre."""
    entry = {"id": "x", "name": "Piege X", "category": "hardware_trap",
             "summary": "resume", "facts": ["fait actionnable 42"]}
    rendered = _format_concepts([CorpusHit(entry=entry, score=1.0)])
    assert "Piege X" in rendered
    assert "resume" in rendered
    assert "fait actionnable 42" in rendered


def test_the_library_formatter_would_have_dropped_the_facts():
    """Prouve le defaut que ce chantier corrige : passe par le mauvais
    formateur, le fait actionnable DISPARAIT. Sans cette demonstration,
    l'interet du tri structurel reste une affirmation."""
    entry = {"id": "x", "name": "Piege X", "category": "hardware_trap",
             "summary": "resume", "facts": ["fait actionnable 42"]}
    rendered = _format_rag([CorpusHit(entry=entry, score=1.0)])
    assert "fait actionnable 42" not in rendered
    assert "(no headers)" in rendered


def test_the_bme280_trap_entry_exists_and_is_well_formed():
    entry = next((e for e in load_concepts()
                  if e.get("id") == "bme280-vs-bmp280"), None)
    assert entry is not None, "entree bme280-vs-bmp280 absente"
    assert entry.get("category") == "hardware_trap", entry.get("category")
    assert entry.get("summary"), "summary vide"
    assert entry.get("facts"), "facts vide"
    # Le diagnostic DOIT etre actionnable : le registre et ses deux valeurs.
    joined = " ".join(entry["facts"]).lower()
    for token in ("0xd0", "0x60", "0x58"):
        assert token in joined, (token, joined)


# Production config: the chat queries the COMBINED index (91 libraries +
# concepts), never `load_concepts()` alone. For the SLM backend it uses
# top_k=1 / min_score=0.7 (ui/chat/chat_controller.py, _SLM_TOP_K /
# _SLM_MIN_SCORE) -- the most demanding setting (fewer, harder-to-clear
# slots) since the LLM path (top_k=3 / min_score=0.5) is strictly more
# permissive. Building the index on `load_concepts()` alone (as this file
# used to) tests a configuration production never runs: it let the
# 2026-08-20 hijack (see below) through undetected.
_SLM_TOP_K = 1
_SLM_MIN_SCORE = 0.7


def _production_index() -> CorpusIndex:
    return CorpusIndex.from_entries(load_default_corpus() + load_concepts())


def test_the_symptom_finds_the_trap_in_four_languages():
    """L'utilisateur arrive par le SYMPTOME, pas par le nom du piege --
    qu'il ignore. Si seuls « bme280 »/« bmp280 » matchaient, l'entree
    serait injoignable au moment ou elle sert.

    Aux parametres SLM (top_k=1) : le cas le plus exigeant. S'il passe, le
    cas LLM (top_k=3, seuil plus bas) passe aussi.
    """
    index = _production_index()
    questions = [
        "mon BME280 ne renvoie jamais l'humidite",
        "my BME280 humidity is always 0",
        "mi BME280 no da humedad",
        "il mio BME280 non restituisce umidita",
    ]
    for q in questions:
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert "bme280-vs-bmp280" in ids, (q, ids)


def test_the_symptom_finds_the_trap_by_board_reference():
    """Un debutant nomme la reference SERIGRAPHIEE sur la carte, pas la puce
    qu'il ignore. Verifie (2026-08-20, table croisee sur
    lamaplc.com/doku.php?id=sensor:bmp_bme + une seconde source) : les
    cartes GY-BMP280-3.3 et HW-611 portent un BMP280 (pas d'humidite).
    GY-91 et CJMCU-280 ne sont PAS verifies -- ne pas les ajouter en alias
    ni les sonder ici comme positifs, cf. l'incident de reference inventee
    du 2026-08-18."""
    index = _production_index()
    questions = [
        "mon HW-611 ne donne pas d'humidite",
        "my GY-BMP280 has no humidity",
    ]
    for q in questions:
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert "bme280-vs-bmp280" in ids, (q, ids)


def test_the_trap_does_not_hijack_unrelated_questions():
    """Une entree qui remonterait sur tout serait du bruit permanent.

    Garde contre la regression du 2026-08-20 : six alias-phrases contenant
    des mots-outils frequents en francais (« ne », « marche », « pas »)
    avaient un IDF enorme sur un corpus quasi entierement anglais, si bien
    que n'importe quelle plainte generique avec une negation faisait gagner
    l'entree BME280/BMP280 en top_k=1 -- masquant la vraie reponse (ex.
    « je ne comprends pas millis() » perdait `millis-overflow`). Sonde des
    plaintes generiques dans les 4 langues, plus une question sans rapport
    avec le materiel, aux parametres SLM reels (index combine, top_k=1,
    seuil 0.7) -- construire l'index sur `load_concepts()` seul (ancienne
    version de ce test) ne l'aurait pas detectee : les deux phrases sondees
    alors ('comment allumer une LED', 'what is PWM') ne portent aucune
    negation.
    """
    index = _production_index()
    questions = [
        "ma LED ne marche pas",
        "mon servo ne marche pas",
        "my sensor is not working",
        "mi sensor no funciona",
        "il mio sensore non funziona",
        "je ne comprends pas millis()",
    ]
    for q in questions:
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert "bme280-vs-bmp280" not in ids, (q, ids)
    # And the unrelated question still finds its OWN correct entry -- the
    # hijack was not just noise, it was actively burying the right answer.
    ids = [h.entry.get("id") for h in
           index.query("je ne comprends pas millis()",
                       top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
    assert "millis-overflow" in ids, ids


def test_the_mpu9250_trap_entry_exists_and_is_well_formed():
    """Second piege materiel (2026-08-20). Meme forme que le BME280/BMP280 :
    une puce vendue pour une autre, distinguables par un registre d'identite.

    Verifie (wolles-elektronikkiste.de + le depot MPU6500_aka-fake9250) : un
    MPU9250 est un MPU6500 PLUS un magnetometre AK8963 ; les faux sont des
    MPU6500 nus, et WHO_AM_I (0x75) rend 0x71 pour le vrai, 0x70 pour le
    MPU6500.
    """
    entry = next((e for e in load_concepts()
                  if e.get("id") == "mpu9250-vs-mpu6500"), None)
    assert entry is not None, "entree mpu9250-vs-mpu6500 absente"
    assert entry.get("category") == "hardware_trap", entry.get("category")
    assert entry.get("summary"), "summary vide"
    assert entry.get("facts"), "facts vide"
    # Le diagnostic DOIT etre actionnable : le registre et ses deux valeurs.
    joined = " ".join(entry["facts"]).lower()
    for token in ("0x75", "0x71", "0x70"):
        assert token in joined, (token, joined)


def test_the_mpu9250_symptom_finds_the_trap_in_four_languages():
    """Comme pour le BME280 : l'utilisateur arrive par le SYMPTOME (pas de
    magnetometre / boussole muette), pas par le nom du piege.

    Les alias retenus sont des mots de CONTENU rares (`magnetometre`,
    `boussole`, `ak8963`, `0x71`), jamais des mots-outils -- c'est la lecon
    du 2026-08-20, ou six alias-phrases avaient detourne toutes les plaintes
    generiques francaises.
    """
    index = _production_index()
    questions = [
        "mon MPU9250 ne donne pas de magnetometre",
        "my MPU9250 has no magnetometer",
        "mi MPU9250 no tiene magnetometro",
        "il mio MPU9250 non ha magnetometro",
    ]
    for q in questions:
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert "mpu9250-vs-mpu6500" in ids, (q, ids)


def test_the_mpu9250_trap_is_reachable_by_board_reference():
    """HW-612 porte un MPU9250 -- c'est la donnee CUREE de ce depot
    (`component_registry.by_id('hw-612').contains`), pas une supposition.
    Un utilisateur nomme sa carte, pas sa puce."""
    index = _production_index()
    ids = [h.entry.get("id") for h in
           index.query("mon HW-612 magnetometre absent",
                       top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
    assert "mpu9250-vs-mpu6500" in ids, ids


def test_the_ds18b20_and_oled_traps_exist_and_are_well_formed():
    """Troisieme et quatrieme pieges (2026-08-20).

    `ds18b20-counterfeit` : verifie sur cpetrich/counterfeit_DS18B20, la
    reference du sujet. Le tell est l'ADRESSE ROM (motif 28-..-00-00-..),
    lisible sans bibliotheque supplementaire puisque les exemples OneWire
    l'impriment deja.

    `ssd1306-vs-sh1106` : NUANCE assumee -- ce n'est pas une contrefacon
    mais deux controleurs legitimes dans des modules d'apparence identique,
    vendus indistinctement comme « OLED SSD1306 ». Le SH1106 a 132 colonnes
    dont la zone visible commence a la colonne 2, d'ou le decalage de 2 px.
    """
    by_id = {e.get("id"): e for e in load_concepts()}
    for cid, tokens in (
            ("ds18b20-counterfeit", ("rom", "28-")),
            ("ssd1306-vs-sh1106", ("132", "column")),
    ):
        entry = by_id.get(cid)
        assert entry is not None, f"entree {cid} absente"
        assert entry.get("category") == "hardware_trap", entry.get("category")
        assert entry.get("summary"), (cid, "summary vide")
        assert entry.get("facts"), (cid, "facts vide")
        joined = " ".join(entry["facts"]).lower()
        for token in tokens:
            assert token in joined, (cid, token)


def test_the_ds18b20_trap_is_reachable_in_four_languages():
    """Le symptome porte sur la CONTREFACON, pas sur la temperature en
    general -- sinon on volerait la place de la bibliotheque Dallas, qui est
    la bonne reponse a « comment lire un DS18B20 »."""
    index = _production_index()
    questions = [
        "DS18B20 ne marche pas en alimentation parasite",
        "my DS18B20 is a fake clone",
        "mi DS18B20 falsificado",
        "il mio DS18B20 contraffatto",
    ]
    for q in questions:
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert "ds18b20-counterfeit" in ids, (q, ids)


def test_the_oled_trap_is_reachable_by_the_shift_symptom():
    """Aux parametres SLM (top_k=1), seules les formulations FR/EN mesurees
    gagnent -- cf. `test_the_oled_trap_loses_to_the_library_in_es_it`."""
    index = _production_index()
    questions = [
        "mon ecran OLED est decale de 2 pixels",
        "my SSD1306 display is shifted",
        "OLED pixels parasites sur le bord",
    ]
    for q in questions:
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert "ssd1306-vs-sh1106" in ids, (q, ids)


def test_the_oled_trap_is_reachable_in_es_and_it_but_only_just():
    """⚠️ LIMITE LEVEE, PUIS DELIBEREMENT NON VERROUILLEE (2026-08-26).

    Ce test s'appelait `..._loses_to_the_library_in_es_it_at_slm_params` et
    figeait une limite mesuree le 2026-08-20 : en espagnol et en italien
    l'entree BIBLIOTHEQUE gagnait le seul creneau du mode SLM, 10.16 contre
    9.82. Il a rougi apres l'ajout de huit entrees -- exactement ce qu'il
    demandait de faire, REMESURER plutot que ceder.

    Remesure : le piege gagne desormais les deux, mais de justesse.

        pantalla OLED desplazada   piege 11.50  bibliotheque 11.44   +0.06
        schermo OLED spostato      piege 11.62  bibliotheque 11.61   +0.01

    ⛔ ON N'ASSERTE PAS CE RESULTAT-LA. Un centieme d'ecart n'est pas un
    acquis : le prochain lot d'entrees le refera basculer dans un sens ou dans
    l'autre, et un test qui l'affirme serait instable par construction --
    il rougirait sans qu'aucun defaut n'existe.

    Ce qui EST stable, et donc ce que ce test garde : le piege est joignable
    en mode LLM (`top_k=3`) dans les quatre langues. Le mode SLM sur ces deux
    formulations est un pile ou face documente, pas une promesse.
    """
    index = _production_index()
    for q in ("mon ecran OLED est decale", "my OLED display is shifted",
              "pantalla OLED desplazada", "schermo OLED spostato"):
        llm = [h.entry.get("id") for h in index.query(q, top_k=3, min_score=0.5)]
        assert "ssd1306-vs-sh1106" in llm, (q, llm)


def test_the_qmc5883l_trap_exists_and_names_both_i2c_addresses():
    """Cinquieme piege. Le meilleur diagnostic des cinq : une simple analyse
    du bus I2C tranche (0x1E = HMC5883L, 0x0D = QMC5883L), et l'app sait deja
    generer un scanner I2C (`rag._prompt_is_i2c_scan`).

    Particularite : ici la SERIGRAPHIE MENT -- la carte GY-271 porte souvent
    « HMC5883L » alors que la puce est une QMC5883L d'un autre fabricant.
    """
    entry = next((e for e in load_concepts()
                  if e.get("id") == "hmc5883l-vs-qmc5883l"), None)
    assert entry is not None, "entree hmc5883l-vs-qmc5883l absente"
    assert entry.get("category") == "hardware_trap", entry.get("category")
    joined = " ".join(entry["facts"]).lower()
    for token in ("0x1e", "0x0d"):
        assert token in joined, (token, joined)


def test_the_qmc5883l_trap_is_reachable_by_symptom_and_by_board():
    index = _production_index()
    questions = [
        "mon GY-271 renvoie des zeros",
        "my HMC5883L reads zeros",
        "GY-271 adresse I2C 0x0D",
        "mon module QMC5883L",
    ]
    for q in questions:
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert "hmc5883l-vs-qmc5883l" in ids, (q, ids)


def test_the_two_magnetometer_traps_do_not_steal_each_other():
    """DEUX pieges parlent desormais de magnetometre. Ils doivent rester
    distincts : le MPU9250 est « pas de magnetometre DU TOUT », le GY-271 est
    « le magnetometre est la mais la mauvaise bibliotheque le lit ».

    C'est pour ca que `boussole`/`magnetometre`, deja alias du piege MPU9250,
    n'ont PAS ete repris sur le GY-271 : deux entrees partageant leurs alias
    se voleraient mutuellement leurs questions en top_k=1.
    """
    index = _production_index()
    cases = [
        ("my MPU9250 has no magnetometer", "mpu9250-vs-mpu6500"),
        ("mon HW-612 magnetometre absent", "mpu9250-vs-mpu6500"),
        ("my compass reads zeros", "hmc5883l-vs-qmc5883l"),
        ("mon GY-271 renvoie des zeros", "hmc5883l-vs-qmc5883l"),
    ]
    for q, expected in cases:
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert ids and ids[0] == expected, (q, expected, ids)


def test_the_lcd_trap_exists_and_names_both_i2c_addresses():
    """SIXIEME piege, premier lot du TODO #63 -- et le premier pris dans
    l'ORDRE du registre plutot que de memoire, ce qui est tout l'objet du
    ticket : la methode de #59 listait des candidats puis les verifiait, soit
    de la confirmation.

    Diagnostic actionnable : un scan I2C tranche (0x27 = PCF8574,
    0x3F = PCF8574A), et l'app sait deja generer ce scanner
    (`rag._prompt_is_i2c_scan`). Source : documentation PCF8574/PCF8574A --
    plages 0x20-0x27 et 0x38-0x3F.
    """
    entry = next((e for e in load_concepts()
                  if e.get("id") == "lcd-i2c-pcf8574-address"), None)
    assert entry is not None, "entree lcd-i2c-pcf8574-address absente"
    assert entry.get("category") == "hardware_trap", entry.get("category")
    joined = " ".join(entry["facts"]).lower()
    for token in ("0x27", "0x3f", "pcf8574a"):
        assert token in joined, (token, joined)


def test_the_lcd_trap_is_reachable_by_symptom_and_by_address():
    """L'utilisateur arrive par le symptome (« il reste vierge ») ou par
    l'adresse qu'un scanner vient de lui donner -- jamais par le nom du
    piege."""
    index = _production_index()
    questions = [
        "mon LCD I2C reste vierge",
        "my I2C LCD shows only blocks",
        "LCD i2c senza testo",
        "adresse 0x27 ou 0x3F",
        "PCF8574A",
    ]
    for q in questions:
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert "lcd-i2c-pcf8574-address" in ids, (q, ids)


def test_the_lcd_trap_is_reachable_in_es_but_only_just():
    """✅ LIMITE LEVEE, ET DELIBEREMENT NON RE-VERROUILLEE -- la seconde de la
    journee apres celle du piege OLED.

    Ce test figeait une defaite mesuree le 2026-08-26 : << pantalla LCD I2C en
    blanco >> perdait contre l'entree bibliotheque, 15.53 contre 15.08. Il a
    rougi apres l'ajout des lots suivants, ce qu'il demandait explicitement --
    REMESURER plutot que ceder.

    Remesure sur 43 pieges : le piege gagne, **17.32 contre 17.26**. Six
    centiemes.

    ⛔ ON N'ASSERTE PAS CE RESULTAT. L'ecart etait de 0.45 en defaveur, il est
    de 0.06 en faveur : c'est un pile ou face que le prochain lot refera
    basculer. Un test qui l'affirme rougirait sans qu'aucun defaut n'existe.

    Ce qui EST stable, et ce que ce test garde : la joignabilite en mode LLM.
    Meme raisonnement, meme forme que `test_the_oled_trap_is_reachable_in_es_
    and_it_but_only_just`.
    """
    index = _production_index()
    llm = [h.entry.get("id") for h in
           index.query("pantalla LCD I2C en blanco", top_k=3, min_score=0.5)]
    assert "lcd-i2c-pcf8574-address" in llm, llm


def test_the_lcd_trap_does_not_steal_the_oled_questions():
    """Deux pieges parlent desormais d'AFFICHAGE. Ils doivent rester
    distincts : c'est pour ca que `oled` et `ecran decale`, deja alias du
    piege SSD1306, n'ont PAS ete repris sur le LCD."""
    index = _production_index()
    for q in ("my OLED display is shifted", "mon ecran OLED est decale"):
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert "lcd-i2c-pcf8574-address" not in ids, (q, ids)


def test_the_lot1_traps_exist_and_carry_their_decisive_value():
    """Lot 1 du fan-out (#63). Trois entrees, trois diagnostics ACTIONNABLES --
    la regle 3 du ticket : une valeur a lire, pas un << mefie-toi >>.

    Sources verifiees a la main avant integration, pas sur parole d'agent :
    la page Adafruit 5183 dit mot pour mot << Inside is the AHT20 >> et
    << I2C address 0x38 (cannot be changed) >> ; le README d'ADS1115_WE a bien
    une section << Beware of fake modules >> donnant BOGI/BRPI dans les deux
    sens ; l'issue 35 d'Arduino_APDS9960 donne 0xA8 et le remede 0x7F.
    """
    par_id = {e.get("id"): e for e in load_concepts()}
    attendu = {
        "ads1115-vs-ads1015": ("7.8125", "860", "3300"),
        "dht20-i2c-in-dht-housing": ("0x38", "nan"),
        "apds9960-clone-id-a8": ("0x92", "0xab", "0xa8", "0x7f"),
    }
    for tid, jetons in attendu.items():
        entry = par_id.get(tid)
        assert entry is not None, f"entree {tid} absente"
        assert entry.get("category") == "hardware_trap", tid
        joined = " ".join(entry["facts"]).lower()
        for jeton in jetons:
            assert jeton in joined, (tid, jeton)


def test_the_apds_fix_admits_it_costs_the_colour_sensor():
    """⚠️ CORRECTION APPORTEE A LA VERIFICATION, pas par l'agent.

    Le rapport disait << ecrire 0x7F dans 0x80 active tous les modes >>. En
    ouvrant l'issue, elle ajoute : << when setting the 0x80 register to 0x7F,
    the RGB detector gets disabled >>. Sans ce bemol le conseil est une
    demi-verite -- on rend les gestes en perdant la couleur, et l'utilisateur
    l'apprendrait en debuggant.
    """
    entry = next(e for e in load_concepts()
                 if e.get("id") == "apds9960-clone-id-a8")
    joined = " ".join(entry["facts"]).lower()
    assert "disables the rgb" in joined, joined


def test_the_lot1_traps_are_reachable_by_symptom_and_by_value():
    index = _production_index()
    cas = [
        ("mon ADS1115 varie par pas de 16", "ads1115-vs-ads1015"),
        ("ADS1015 sold as ADS1115", "ads1115-vs-ads1015"),
        ("mon DHT20 renvoie NaN", "dht20-i2c-in-dht-housing"),
        ("DHT20 i2c 0x38", "dht20-i2c-in-dht-housing"),
        ("APDS9960 id 0xA8", "apds9960-clone-id-a8"),
        ("registre 0x92 renvoie 0xa8", "apds9960-clone-id-a8"),
    ]
    for q, attendu in cas:
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert attendu in ids, (q, ids)


def test_a_part_name_query_loses_to_the_library_entry():
    """LIMITE STRUCTURELLE DU MECANISME, mesuree TROIS fois maintenant.

    Quand la question est dominee par le NOM de la puce, l'entree BIBLIOTHEQUE
    du corpus gagne le seul creneau du mode SLM :

      « pantalla OLED desplazada »   ssd1306        bat  ssd1306-vs-sh1106
      « pantalla LCD I2C en blanco » liquidcrystal  bat  lcd-i2c-...  15.53/15.08
      « mon APDS9960 refuse begin »  apds9960       bat  apds9960-...  7.51/6.36

    Ce n'est pas trois accidents, c'est la meme mecanique : le piege se gagne
    par le SYMPTOME ou par une VALEUR, jamais en criant plus fort que la
    bibliotheque sur son propre nom. On NE retouche PAS les alias pour cela --
    ajouter la requete elle-meme serait de la calibration sur echantillon.
    En mode LLM (top_k=3) les trois pieges sont bien injectes."""
    index = _production_index()
    for q, piege in (("mon APDS9960 refuse begin", "apds9960-clone-id-a8"),):
        slm = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert piege not in slm, (q, slm, "la limite a bouge")
        llm = [h.entry.get("id") for h in index.query(q, top_k=3, min_score=0.5)]
        assert piege in llm, (q, llm)


_LOT234 = ("si7021-htu21d-swap", "nrf24l01-si24r1-clone",
           "st7735-controller-variant", "pms5003-silent-revision",
           "max31855-vs-max6675-boards", "mcp4725-address-variant",
           "max3010x-part-id-mixup", "vl53l0x-vs-vl53l1x",
           "mpu6050-relabelled-icm20689", "ina219-vs-ina226",
           "sx127x-vs-sx126x-ra01")


def test_the_lots234_traps_are_well_formed():
    """Onze entrees de plus, issues du fan-out par agents (#63). Chacune a ete
    integree APRES verification d'au moins une source a la main -- les agents
    cherchaient et proposaient, ils n'ecrivaient rien."""
    par_id = {e.get("id"): e for e in load_concepts()}
    for tid in _LOT234:
        entry = par_id.get(tid)
        assert entry is not None, f"entree {tid} absente"
        assert entry.get("category") == "hardware_trap", tid
        assert entry.get("summary") and entry.get("facts"), tid


def test_no_two_traps_share_an_alias():
    """LA regle du ticket : deux entrees qui partagent un alias se volent
    leurs questions en top_k=1. Avec vingt pieges, la verifier a l'oeil n'est
    plus possible -- d'ou un balayage."""
    from collections import Counter
    compte = Counter(a for e in load_concepts()
                     if e.get("category") == "hardware_trap"
                     for a in e.get("aliases", []))
    partages = [a for a, n in compte.items() if n > 1]
    assert not partages, partages


def test_the_lots234_traps_are_reachable_by_their_decisive_value():
    """Chaque piege se gagne par sa VALEUR ou son symptome propre."""
    index = _production_index()
    cas = [
        ("SNB_3 vaut 0x32", "si7021-htu21d-swap"),
        ("Si24R1", "nrf24l01-si24r1-clone"),
        ("greentab colstart", "st7735-controller-variant"),
        ("mon PMS5003 lit trop bas", "pms5003-silent-revision"),
        ("cold junction 128.00", "max31855-vs-max6675-boards"),
        ("mon MCP4725 ne repond pas a 0x62", "mcp4725-address-variant"),
        ("MAX30102 part_id 0x15", "max3010x-part-id-mixup"),
        ("registre 0xC0 vaut 0xEE", "vl53l0x-vs-vl53l1x"),
        ("mon GY-521 renvoie 0x98", "mpu6050-relabelled-icm20689"),
        ("Ra-01S LoRa begin retourne 0", "sx127x-vs-sx126x-ra01"),
    ]
    for q, attendu in cas:
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert attendu in ids, (q, ids)


_BLOC_B = ("tm1637-6digit-reversed", "tm1638-led-key-vs-qyf",
           "28byj48-gearbox-ratio-mismatch", "ina3221-breakout-shared-rail",
           "mq135-ppm-without-referent")


def test_a_shifted_st7735_reaches_its_own_trap():
    """✅ DEFAUT CORRIGE, et mon diagnostic d'origine etait FAUX.

    Ce test s'appelait `..._still_reaches_the_oled_trap` et figeait une
    mauvaise reponse : << mon ST7735 decale de deux pixels >> atteignait le
    piege SSD1306/SH1106, qui parlait d'un controleur OLED a quelqu'un qui
    tenait un TFT.

    ⚠️ LA PREMIERE ANALYSE SE TROMPAIT DE COUPABLE. J'avais conclu que le
    piege OLED gagnait << par la densite de ses FAITS >>, tente de restreindre
    son alias `ecran decale`, mesure aucun effet, et abandonne. La remesure sur
    un index de 36 entrees dit autre chose : le piege ST7735 marquait **6.61**
    parce qu'il n'avait AUCUN vocabulaire de decalage en francais. L'agent
    avait soigneusement evite `ecran decale`, deja pris, sans rien mettre a la
    place.

    EVITER UN MOT DEJA PRIS NE SUFFIT PAS : IL FAUT LE REMPLACER PAR SA FORME
    QUALIFIEE. Quatre alias qualifies par la reference (`st7735 decale`,
    `tft decale de deux pixels`...) font passer l'entree de 6.61 a **17.45**.
    C'est la regle que le ticket enonce pour les deux magnetometres ; elle
    n'avait simplement pas ete appliquee jusqu'au bout.
    """
    index = _production_index()
    for q in ("mon ST7735 decale de deux pixels", "my ST7735 image is shifted",
              "ST7735 greentab colstart"):
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert ids == ["st7735-controller-variant"], (q, ids)


def test_the_two_display_traps_keep_their_own_questions():
    """La contrepartie : corriger le ST7735 ne doit rien couter au piege OLED.
    Deux pieges d'affichage coexistent tant que chacun garde SON vocabulaire
    qualifie -- meme regle que pour les deux magnetometres."""
    index = _production_index()
    for q in ("my OLED display is shifted", "pantalla OLED desplazada"):
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert ids == ["ssd1306-vs-sh1106"], (q, ids)


def test_the_scope_now_covers_traps_that_are_not_chip_substitutions():
    """⚠️ ELARGISSEMENT DELIBERE DU PERIMETRE (decision utilisateur,
    2026-08-26). Les vingt premieres entrees repondaient toutes a << la puce
    n'est pas celle qui est ecrite dessus >>. Ces cinq-la non : la puce EST la
    bonne, c'est la carte, la mecanique ou la documentation qui trompe.

    Du point de vue de l'utilisateur c'est pourtant le meme moment -- son
    montage ne fait pas ce qu'il devrait et le nom sur la carte ne l'aide pas.
    Ce test existe pour que l'elargissement soit une DECISION lisible plutot
    qu'une derive : si quelqu'un juge un jour que le perimetre doit se
    refermer, ces cinq ids sont la liste exacte a retirer."""
    par_id = {e.get("id"): e for e in load_concepts()}
    for tid in _BLOC_B:
        entry = par_id.get(tid)
        assert entry is not None, f"entree {tid} absente"
        assert entry.get("category") == "hardware_trap", tid
        assert entry.get("summary") and entry.get("facts"), tid


def test_the_bloc_b_traps_are_reachable_by_their_own_evidence():
    """Chacun se gagne par un CHIFFRE ou un symptome qui n'appartient qu'a
    lui -- 321654 pour l'afficheur, 63.68395 pour le reducteur."""
    index = _production_index()
    cas = [
        ("mon afficheur montre 321654", "tm1637-6digit-reversed"),
        ("TM1637 six chiffres ordre inverse", "tm1637-6digit-reversed"),
        ("mon TM1638 affiche des chiffres illisibles", "tm1638-led-key-vs-qyf"),
        ("QYF-TM1638 clavier 16 touches", "tm1638-led-key-vs-qyf"),
        ("63.68395", "28byj48-gearbox-ratio-mismatch"),
        ("MQ-135 ppm sans referent", "mq135-ppm-without-referent"),
        ("rzero 76.63", "mq135-ppm-without-referent"),
    ]
    for q, attendu in cas:
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert attendu in ids, (q, ids)


def test_adding_traps_did_not_cost_the_earlier_ones_their_questions():
    """LA garde de non-regression, et elle vise une surprise MESUREE.

    Ajouter des entrees deplace l'index pour les ANCIENNES : mon entree
    MCP4725 accaparait cinq adresses nues et a fait perdre au piege LCD sa
    propre question << adresse 0x27 ou 0x3F >>. Une adresse nue n'est pas un
    alias distinctif quand vingt-cinq entrees en portent.

    Le correctif fut de restreindre l'entree fautive -- jamais de retoucher le
    test qui l'a attrapee, ni le seuil. Cette garde rejoue les questions
    signatures des lots precedents a chaque ajout."""
    index = _production_index()
    for q, attendu in (("adresse 0x27 ou 0x3F", "lcd-i2c-pcf8574-address"),
                       ("mon GY-271 renvoie des zeros", "hmc5883l-vs-qmc5883l"),
                       ("mon GY-521 renvoie 0x98", "mpu6050-relabelled-icm20689"),
                       ("cold junction 128.00", "max31855-vs-max6675-boards"),
                       ("SNB_3 vaut 0x32", "si7021-htu21d-swap"),
                       ("registre 0xC0 vaut 0xEE", "vl53l0x-vs-vl53l1x")):
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert attendu in ids, (q, ids, "un ajout a coute sa question a un ancien")


_VAGUE2 = ("mfrc522-clone-version-register",
           "ds3231-module-charges-the-coin-cell",
           "motor-shield-v2-all-call-address",
           "lsm303-name-hides-five-chips", "l3g4200d-gy50-three-gyros",
           "hmc6352-eight-bit-address",
           "itg3200-reserved-full-scale-at-reset",
           "mcp41xxx-is-not-a-mechanical-pot")


def test_the_vague2_traps_are_well_formed():
    """Huit entrees de la seconde vague d'agents. Trois lots sur cinq ont ete
    coupes par une limite de session ; ces huit viennent des deux lots
    complets, et chacune a ete integree apres verification d'au moins une
    source a la main."""
    par_id = {e.get("id"): e for e in load_concepts()}
    for tid in _VAGUE2:
        entry = par_id.get(tid)
        assert entry is not None, f"entree {tid} absente"
        assert entry.get("category") == "hardware_trap", tid
        assert entry.get("summary") and entry.get("facts"), tid


def test_the_vague2_traps_are_reachable_by_their_own_evidence():
    index = _production_index()
    cas = [
        ("firmware version 0x88", "mfrc522-clone-version-register"),
        ("ma pile CR2032 a gonfle sur le module RTC",
         "ds3231-module-charges-the-coin-cell"),
        ("ZS-042 charge la pile", "ds3231-module-charges-the-coin-cell"),
        ("mon shield moteur repond a deux adresses",
         "motor-shield-v2-all-call-address"),
        ("quel LSM303 ai-je", "lsm303-name-hides-five-chips"),
        ("mon gyroscope GY-50 ne repond pas a 0x68",
         "l3g4200d-gy50-three-gyros"),
        ("HMC6352 adresse 0x42 ou 0x21", "hmc6352-eight-bit-address"),
    ]
    for q, attendu in cas:
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert attendu in ids, (q, ids)


def test_the_ds3231_trap_says_which_track_must_not_be_cut():
    """Cette entree touche a la SECURITE : le module pousse un courant de
    charge dans une pile qui n'en accepte aucun, et une pile bombee peut
    s'ouvrir. Le remede doit donc dire non seulement quoi couper, mais ce
    qu'il ne faut SURTOUT pas couper -- la piste qui alimente le DS3231
    lui-meme, sans quoi on repare en cassant l'horloge."""
    entry = next(e for e in load_concepts()
                 if e.get("id") == "ds3231-module-charges-the-coin-cell")
    joint = " ".join(entry["facts"]).lower()
    assert "pin 14" in joint, joint
    assert "3.3" in joint, joint


def test_a_generic_complaint_word_is_what_hijacks():
    """⚠️ LECON MESUREE DE LA VAGUE 2, et elle corrige la regle du ticket.

    Le ticket interdit << tout mot-outil >> dans les alias, resumes et faits.
    Un balayage montre que `not`, `fail`, `work` et `sensor` sont presents
    dans PRESQUE TOUTES les entrees, y compris les six livrees avant, et que
    la quasi-totalite ne detourne rien. L'interdit brut n'est donc pas la
    vraie regle.

    Ce qui detourne vraiment se voit a la MESURE : l'entree LSM303 disait
    << reads a WORKING accelerometer >> et gagnait << my sensor is not
    working >>. Reformulee en << sound accelerometer values >>, elle rend la
    question et garde les siennes.

    Ce test verrouille le resultat, pas le vocabulaire : la garde qui compte
    reste `test_neither_trap_hijacks_unrelated_questions`."""
    index = _production_index()
    ids = [h.entry.get("id") for h in
           index.query("my sensor is not working",
                       top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
    assert "lsm303-name-hides-five-chips" not in ids, ids


_LOT8 = ("ads7830-interleaved-channels",
         "tsl2561-library-checks-the-wrong-nibble",
         "mmc5603-identity-register-reads-zero")


def test_the_lot8_fragments_survived_the_session_cut():
    """Trois rapports arrives AVANT que la limite de session ne coupe leur
    lot. Ils etaient complets et sources, donc exploitables tels quels -- il
    aurait ete absurde de refaire la recherche."""
    par_id = {e.get("id"): e for e in load_concepts()}
    for tid in _LOT8:
        entry = par_id.get(tid)
        assert entry is not None, f"entree {tid} absente"
        assert entry.get("category") == "hardware_trap", tid
        assert entry.get("summary") and entry.get("facts"), tid


def test_the_lot8_traps_carry_their_decisive_evidence():
    """Chacun repose sur une valeur verifiee A LA MAIN dans le source de la
    bibliotheque de reference, pas sur parole d'agent :
      - ADS7830 : l'en-tete donne bien SINGLE_CH0=0x08, SINGLE_CH2=0x09,
        SINGLE_CH1=0x0C -- l'entrelacement est dans le code ;
      - TSL2561 : `init()` fait bien `if (x & 0x05)`, dont les deux bits
        vivent dans le quartet de REVISION."""
    par_id = {e.get("id"): e for e in load_concepts()}
    joint = " ".join(par_id["ads7830-interleaved-channels"]["facts"]).lower()
    for jeton in ("0x08", "0x09", "0x0c"):
        assert jeton in joint, jeton
    joint = " ".join(par_id["tsl2561-library-checks-the-wrong-nibble"]["facts"]).lower()
    assert "0x05" in joint and "revision" in joint, joint


def test_the_lot8_traps_are_reachable():
    index = _production_index()
    for q, attendu in (("canaux entrelaces ADS7830",
                        "ads7830-interleaved-channels"),
                       ("no TSL2561 detected",
                        "tsl2561-library-checks-the-wrong-nibble"),
                       ("mon MMC5603 renvoie une identite a zero",
                        "mmc5603-identity-register-reads-zero")):
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert attendu in ids, (q, ids)


def test_the_word_sensor_is_what_hijacks_twice_over():
    """⚠️ LA MEME FUITE, DEUX FOIS DE SUITE, ET C'EST LE MEME MOT.

    L'entree LSM303 disait << reads a WORKING accelerometer >>, l'entree
    TSL2561 << refuses sound SENSORS >> et << no SENSOR detected >>. Les deux
    gagnaient << my sensor is not working >> et volaient la question a
    l'entree generique qui doit y repondre.

    ⛔ ET POURTANT UNE LISTE DE MOTS INTERDITS NE MARCHERAIT PAS : un balayage
    montre que `sensor`, `not`, `fail` et `work` sont presents dans presque
    toutes les entrees, y compris les six livrees avant cette journee, sans
    rien detourner. Ce qui compte n'est pas le mot, c'est son POIDS relatif
    dans une entree donnee -- et cela, seule la mesure le dit.

    D'ou la division du travail : `test_neither_trap_hijacks_unrelated_questions`
    reste la garde qui decide, celle-ci ne fait que nommer les deux cas pour
    que la lecon ne se reperde pas au prochain lot."""
    index = _production_index()
    ids = [h.entry.get("id") for h in
           index.query("my sensor is not working",
                       top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
    for coupable in ("lsm303-name-hides-five-chips",
                     "tsl2561-library-checks-the-wrong-nibble"):
        assert coupable not in ids, (coupable, ids)


_LOT9 = ("ina169-shunt-100x", "tmc2209-eighth-step-default",
         "stspin220-ten-volt-ceiling",
         "tca9548a-collides-at-its-own-address", "guva-s12sd-gain-varies",
         "lps28-fs-mode-halves-sensitivity", "sen5x-sel-pin-selects-i2c")


def test_the_lot9_traps_are_well_formed():
    par_id = {e.get("id"): e for e in load_concepts()}
    for tid in _LOT9:
        entry = par_id.get(tid)
        assert entry is not None, f"entree {tid} absente"
        assert entry.get("category") == "hardware_trap", tid
        assert entry.get("summary") and entry.get("facts"), tid


def test_the_lot9_traps_are_reachable():
    index = _production_index()
    for q, attendu in (
            ("mon INA169 lit un courant 100 fois trop grand",
             "ina169-shunt-100x"),
            ("mon TMC2209 tourne huit fois trop peu",
             "tmc2209-eighth-step-default"),
            ("STSPIN220 en 12 volts", "stspin220-ten-volt-ceiling"),
            ("mon TCA9548A entre en conflit d adresse",
             "tca9548a-collides-at-its-own-address"),
            ("GUVA-S12SD indice UV faux", "guva-s12sd-gain-varies"),
            ("LPS28DFW lit 506 hPa", "lps28-fs-mode-halves-sensitivity"),
            ("mon SEN55 est absent du scan", "sen5x-sel-pin-selects-i2c")):
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert attendu in ids, (q, ids)


def test_two_traps_that_would_destroy_the_part_say_so_first():
    """Deux entrees de ce lot ne decrivent pas une lecture fausse mais une
    piece DETRUITE : le STSPIN220 alimente en 12 volts, et le TMC2209 dont
    chaque mouvement sort huit fois trop court. Leur premier fait doit porter
    le chiffre qui tranche, pas une generalite."""
    par_id = {e.get("id"): e for e in load_concepts()}
    assert "10 volts" in par_id["stspin220-ten-volt-ceiling"]["facts"][0]
    assert "full step" in par_id["tmc2209-eighth-step-default"]["facts"][0]


def test_the_qualified_symptom_rule_was_applied_to_lot9():
    """⚠️ LA LECON DU ST7735, APPLIQUEE AVANT DE COMMITTER cette fois.

    L'entree TCA9548A n'avait aucun vocabulaire de conflit en francais et se
    faisait battre par l'entree BIBLIOTHEQUE `i2c_multiplexer` sur sa propre
    question. Le remede n'est pas de restreindre la voisine mais d'ajouter le
    symptome QUALIFIE PAR LA REFERENCE -- `tca9548a conflit d adresse` -- ce
    qui la fait gagner sans rien couter a personne."""
    index = _production_index()
    for q in ("mon TCA9548A entre en conflit d adresse",
              "multiplexeur reste seul au scan"):
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert ids == ["tca9548a-collides-at-its-own-address"], (q, ids)


_LOT7 = ("sht15-two-wire-is-not-i2c", "sht25-unpowered-clamps-the-bus",
         "us100-jumper-selects-serial-mode",
         "drv8825-vref-differs-from-a4988", "sim800l-wants-a-four-volt-rail",
         "esp8266-needs-more-than-the-board-rail", "wiz820io-is-a-w5200",
         "tmp102-half-degree-is-typical",
         "tmp006-object-temperature-is-uncalibrated")


def test_the_lot7_traps_are_well_formed():
    par_id = {e.get("id"): e for e in load_concepts()}
    for tid in _LOT7:
        entry = par_id.get(tid)
        assert entry is not None, f"entree {tid} absente"
        assert entry.get("category") == "hardware_trap", tid
        assert entry.get("summary") and entry.get("facts"), tid


def test_the_lot7_traps_are_reachable():
    index = _production_index()
    for q, attendu in (
            ("mon SHT15 est absent du scanner", "sht15-two-wire-is-not-i2c"),
            ("capteur non alimente bloque le bus",
             "sht25-unpowered-clamps-the-bus"),
            ("cavalier a l arriere du US-100",
             "us100-jumper-selects-serial-mode"),
            ("mon moteur chauffe apres swap DRV8825",
             "drv8825-vref-differs-from-a4988"),
            ("mon SIM800L s eteint tout seul",
             "sim800l-wants-a-four-volt-rail"),
            ("ESP-01 50 milliamps",
             "esp8266-needs-more-than-the-board-rail"),
            ("TMP102 un degre d ecart", "tmp102-half-degree-is-typical")):
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert attendu in ids, (q, ids)


def test_the_sht15_entry_says_an_empty_scan_is_normal():
    """Le plus contre-intuitif du lot : un scan I2C VIDE est le resultat
    ATTENDU pour un SHT15 sain, parce que la piece n'a pas d'adresse. Sans
    cette phrase l'entree ferait chercher un defaut inexistant."""
    entry = next(e for e in load_concepts()
                 if e.get("id") == "sht15-two-wire-is-not-i2c")
    joint = " ".join(entry["facts"]).lower()
    assert "expected result" in joint, joint


def test_four_generic_words_had_to_be_purged_by_measurement():
    """⚠️ QUATRIEME ET CINQUIEME OCCURRENCE DU MEME MECANISME.

    Apres `working` (LSM303) et `sensor` (TSL2561), ce lot en a produit deux
    de plus : l'alias francais `ne pas tourner le driver` du DRV8825 gagnait
    << je ne peux pas uploader le sketch >>, et `working voltage` de l'ESP8266
    gagnait << my sensor is not working >>.

    ⚠️ ET IL A FALLU DEUX PASSES SUR L'ESP8266. La premiere reformulation a
    laisse un `Working voltage` en tete de fait et un `is not five volt
    tolerant` en alias. C'est un balayage des JETONS COMMUNS avec la requete
    -- pas une relecture -- qui les a designes. A cinquante-deux entrees,
    relire ne suffit plus."""
    index = _production_index()
    pieges = {e["id"] for e in load_concepts()
              if e.get("category") == "hardware_trap"}
    for q in ("my sensor is not working", "je ne peux pas uploader le sketch"):
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert not [i for i in ids if i in pieges], (q, ids)


def test_neither_trap_hijacks_unrelated_questions():
    """Garde ELARGIE a TOUS les pieges : chaque entree `hardware_trap` est un
    candidat de plus pour detourner une plainte generique. Cette garde doit
    croitre avec le fichier, sinon le prochain piege ajoute reintroduira le
    defaut du 2026-08-20 sans que rien ne rougisse.

    Elle a deja mordu deux fois : sur des ALIAS a mots-outils, puis sur des
    FACTS ou « not »/« sensor »/« dead » avaient fui. Les deux fois, le
    correctif etait de reformuler l'entree -- jamais de toucher au seuil.
    """
    index = _production_index()
    traps = {"bme280-vs-bmp280", "mpu9250-vs-mpu6500",
             "ds18b20-counterfeit", "ssd1306-vs-sh1106",
             "hmc5883l-vs-qmc5883l", "lcd-i2c-pcf8574-address",
             "ads1115-vs-ads1015", "dht20-i2c-in-dht-housing",
             "apds9960-clone-id-a8"} | set(_LOT234) | set(_BLOC_B) | set(_VAGUE2) | set(_LOT8) | set(_LOT9) | set(_LOT7)
    questions = [
        "ma LED ne marche pas",
        "mon servo ne marche pas",
        "my sensor is not working",
        "je ne comprends pas millis()",
        "mi sensor no funciona",
        "il mio sensore non funziona",
        "je ne peux pas uploader le sketch",
        "comment allumer une LED",
        "what is PWM",
    ]
    for q in questions:
        ids = {h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)}
        assert not (ids & traps), (q, ids)



_LOT8B = ("si1145-uv-index-is-inferred",
          "hdc3021-tape-still-over-the-element",
          "hdc1008-successor-drops-the-address-pins",
          "si4713-mute-until-reset-is-pulsed",
          "ds3502-powers-up-writing-to-eeprom",
          "adxl335-is-ratiometric-to-its-regulator")


def test_the_lot8b_traps_are_well_formed():
    par_id = {e.get("id"): e for e in load_concepts()}
    for tid in _LOT8B:
        entry = par_id.get(tid)
        assert entry is not None, f"entree {tid} absente"
        assert entry.get("category") == "hardware_trap", tid
        assert entry.get("summary") and entry.get("facts"), tid


def test_the_lot8b_traps_are_reachable():
    """FORMULATIONS MESUREES, pas esperees. Chacune a ete jouee avant d'etre
    ecrite ici : en top_k=1 il n'y a qu'une place, et le piege la dispute a
    l'entree corpus de la MEME puce (cf. le test suivant)."""
    index = _production_index()
    for q, attendu in (
            ("mon SI1145 donne un indice UV eleve sous une lampe de bureau",
             "si1145-uv-index-is-inferred"),
            ("mon HDC3021 donne la temperature mais l humidite reste plate",
             "hdc3021-tape-still-over-the-element"),
            ("HDC1080 identity 0x1050 my driver refuses the chip",
             "hdc1008-successor-drops-the-address-pins"),
            ("mon Si4713 n apparait pas au scan i2c au demarrage",
             "si4713-mute-until-reset-is-pulsed"),
            ("DS3502 wiper stops responding after a long fade",
             "ds3502-powers-up-writing-to-eeprom"),
            ("mon ADXL335 a plat lit 338 au lieu de 512",
             "adxl335-is-ratiometric-to-its-regulator")):
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert attendu in ids, (q, ids)


def test_a_trap_competes_with_the_corpus_entry_of_its_own_chip():
    """CE QUI LIMITE LA JOIGNABILITE, ET CE N'EST PAS UN DETOURNEMENT.

    Mesure du 2026-08-26 : 43 des 58 pieges ont un JUMEAU dans corpus.json --
    la puce y a sa fiche de bibliotheque. En top_k=1 il n'y a qu'une place,
    et sur une question sans symptome (<< probleme avec mon X >>) c'est le
    jumeau qui la prend 33 fois sur 43.

    ⛔ NE PAS << corriger >> en bourrant les pieges d'alias : les deux entrees
    parlent legitimement de la meme puce, et celle du corpus est une bonne
    reponse a une question qui ne decrit aucun symptome. Ce qui fait gagner le
    piege, c'est que la question porte le SYMPTOME -- mesure au-dessus, 14 des
    18 formulations realistes du lot 8 l'atteignent.

    Ce test fige le fait, pour qu'un futur lot ne le redecouvre pas comme un
    bug."""
    index = _production_index()
    corpus_ids = {e.get("id") for e in load_default_corpus()}
    assert "adxl335" in corpus_ids and "si1145" in corpus_ids
    vague = [h.entry.get("id") for h in
             index.query("probleme avec mon adxl335",
                         top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
    assert vague == ["adxl335"], vague
    precis = [h.entry.get("id") for h in
              index.query("mon ADXL335 a plat lit 338 au lieu de 512",
                          top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
    assert precis == ["adxl335-is-ratiometric-to-its-regulator"], precis


def test_french_filler_words_carry_a_huge_weight_in_an_english_index():
    """LA SEPTIEME FUITE, ET LA PREMIERE EN FRANCAIS.

    L'entree TMP102 portait l'alias << un degre d ecart AVEC MON thermometre >>.
    Dans un index majoritairement anglais, << avec >> et << mon >> sont RARES,
    donc leur poids est enorme -- l'inverse exact de leur valeur informative.
    L'entree volait ainsi les questions d'autres puces : mesure du 2026-08-26,
    << probleme avec mon mq135 >> et << probleme avec mon itg3200 >> tombaient
    tous deux sur le TMP102.

    ⚠️ La mesure a aussi CORRIGE l'alarme : sur douze questions vagues en
    francais, un seul piege sortait (SIM800L sur << ca s eteint tout seul >>),
    et c'est la BONNE reponse. Les mots << tout >> et << qui >> d'autres
    entrees ne detournent rien et ont ete laisses en place -- on ne purge pas
    sur la peur, seulement sur la mesure."""
    index = _production_index()
    for chip in ("mq135", "itg3200"):
        ids = [h.entry.get("id") for h in
               index.query(f"probleme avec mon {chip}",
                           top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert "tmp102-half-degree-is-typical" not in ids, (chip, ids)
    ids = [h.entry.get("id") for h in
           index.query("mon TMP102 a un degre d ecart avec mon thermometre",
                       top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
    assert "tmp102-half-degree-is-typical" in ids, ids



def test_the_gy33_trap_exists_because_an_alias_was_wrong():
    """NE PAS le lire comme un piege de plus : c'est la trace d'une FAUTE.

    Le 2026-08-26, le chantier des alias de cartes (#57) a ajoute
    `GY-33 -> adafruit-tcs34725` sur la foi d'une phrase exacte de l'index
    Arduino. Verification le lendemain : cette carte intercale son propre
    microcontroleur, repond en 0x5A, et la puce nue reste injoignable a 0x29 --
    la bibliotheque Adafruit parle a 0x29 et ne trouve rien. L'alias a ete
    retire ET le cas transforme en piege, sa juste place.

    La lecon est dans `test_a_board_specific_library_is_a_WARNING_not_a_mapping`
    (`scripts/test_board_aliases.py`) : l'existence d'une bibliotheque
    SPECIFIQUE A LA CARTE, en plus de celle de la puce, signale que la carte
    n'est pas un breakout transparent."""
    index = _production_index()
    for q in ("mon GY-33 est introuvable au scan i2c",
              "GY-33 answers at 0x5A instead of 0x29"):
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert "gy33-mcu-in-front-of-tcs34725" in ids, (q, ids)
    entry = {e.get("id"): e for e in load_concepts()}[
        "gy33-mcu-in-front-of-tcs34725"]
    joint = " ".join(entry["facts"]).lower()
    assert "0x5a" in joint and "0x29" in joint, joint



_QUEUE = ("mhz19b-black-pcb-imitation", "mcp23017-vs-mcp23s17")


def test_the_queue_traps_are_reachable():
    """Les deux survivantes de la QUEUE du #63 (2026-08-27).

    Cinq propositions d'agents dormaient, jamais integrees faute d'avoir
    rouvert leurs sources. Rouvertes : `gy33` (integree la veille, elle
    contredisait un alias), ces deux-ci, et DEUX ECARTEES --
    `ili9341-vs-ili9342` (la substitution n'est documentee nulle part, et le
    registre d'identite se lit mal en SPI, il reclame une commande non
    documentee 0xD9) et `mlx90614-remarked-parts` (aucune source)."""
    index = _production_index()
    for q, attendu in (
            ("mon MH-Z19B a un circuit imprime noir",
             "mhz19b-black-pcb-imitation"),
            ("MH-Z19B reads too low compared to another meter",
             "mhz19b-black-pcb-imitation"),
            ("mes ppm de co2 semblent trop bas",
             "mhz19b-black-pcb-imitation"),
            ("mon MCP23017 est absent du scan i2c",
             "mcp23017-vs-mcp23s17"),
            ("MCP23S17 does it answer on i2c",
             "mcp23017-vs-mcp23s17"),
            ("expandeur de broches introuvable entre 0x20 et 0x27",
             "mcp23017-vs-mcp23s17")):
        ids = [h.entry.get("id") for h in
               index.query(q, top_k=_SLM_TOP_K, min_score=_SLM_MIN_SCORE)]
        assert attendu in ids, (q, ids)


def test_an_entry_must_use_the_words_the_user_TYPES():
    """⛔ MA PROPRE FAUTE DE REDACTION, mesuree le 2026-08-27.

    La 1re version de l'entree MCP disait << two-wire bus >> et << four-wire
    serial >>, par prudence de style, et n'ecrivait NI `i2c` NI `spi` dans ses
    faits. Resultat mesure : 5,01 sur son propre numero de piece, battue par
    n'importe quelle entree portant `i2c`, et 1 formulation joignable sur 4.
    Reecrite avec le vocabulaire que l'utilisateur tape reellement : 6 sur 6.

    ⚠️ CECI AFFINE `test_a_trap_competes_with_the_corpus_entry_of_its_own_chip`
    (ci-dessus) : la compétition avec le jumeau corpus n'est PAS seulement
    structurelle. Le jumeau gagne quand la question ne porte aucun symptome,
    OU quand l'entree evite le vocabulaire de la question. Le second cas se
    repare a l'ecriture ; le premier, non."""
    par_id = {e.get("id"): e for e in load_concepts()}
    attendu = {"mcp23017-vs-mcp23s17": ("i2c", "spi"),
               "mhz19b-black-pcb-imitation": ("co2", "ppm")}
    for tid, mots in attendu.items():
        joint = " ".join(par_id[tid]["facts"]).lower()
        for mot in mots:
            assert mot in joint, (tid, mot)


def test_the_queue_entries_confess_what_could_not_be_sourced():
    """Deux affirmations circulent sur les imitations de MH-Z19B -- une plage
    de 10000 ppm annoncee au demarrage, une constante de 436 au lieu de 410.
    Elles venaient d'un RESUME de moteur de recherche, et n'etaient sur aucune
    des pages ouvertes. L'entree le DIT au lieu de les taire : sans ca, un
    prochain lot les reprendrait comme acquises."""
    par_id = {e.get("id"): e for e in load_concepts()}
    joint = " ".join(par_id["mhz19b-black-pcb-imitation"]["facts"]).lower()
    assert "rumour" in joint and "10000" in joint and "436" in joint, joint


TESTS = [
    test_invariant_libraries_carry_no_reference_facts,
    test_invariant_concepts_all_carry_reference_facts,
    test_a_new_category_is_routed_by_structure_not_by_name,
    test_a_library_entry_is_still_not_a_concept,
    test_facts_reach_the_prompt_for_a_new_category,
    test_the_library_formatter_would_have_dropped_the_facts,
    test_the_bme280_trap_entry_exists_and_is_well_formed,
    test_the_symptom_finds_the_trap_in_four_languages,
    test_the_symptom_finds_the_trap_by_board_reference,
    test_the_trap_does_not_hijack_unrelated_questions,
    test_the_mpu9250_trap_entry_exists_and_is_well_formed,
    test_the_mpu9250_symptom_finds_the_trap_in_four_languages,
    test_the_mpu9250_trap_is_reachable_by_board_reference,
    test_the_ds18b20_and_oled_traps_exist_and_are_well_formed,
    test_the_ds18b20_trap_is_reachable_in_four_languages,
    test_the_oled_trap_is_reachable_by_the_shift_symptom,
    test_the_oled_trap_is_reachable_in_es_and_it_but_only_just,
    test_the_qmc5883l_trap_exists_and_names_both_i2c_addresses,
    test_the_qmc5883l_trap_is_reachable_by_symptom_and_by_board,
    test_the_two_magnetometer_traps_do_not_steal_each_other,
    test_the_lcd_trap_exists_and_names_both_i2c_addresses,
    test_the_lcd_trap_is_reachable_by_symptom_and_by_address,
    test_the_lcd_trap_is_reachable_in_es_but_only_just,
    test_the_lcd_trap_does_not_steal_the_oled_questions,
    test_the_lot1_traps_exist_and_carry_their_decisive_value,
    test_the_apds_fix_admits_it_costs_the_colour_sensor,
    test_the_lot1_traps_are_reachable_by_symptom_and_by_value,
    test_a_part_name_query_loses_to_the_library_entry,
    test_the_lots234_traps_are_well_formed,
    test_no_two_traps_share_an_alias,
    test_the_lots234_traps_are_reachable_by_their_decisive_value,
    test_a_shifted_st7735_reaches_its_own_trap,
    test_the_two_display_traps_keep_their_own_questions,
    test_the_scope_now_covers_traps_that_are_not_chip_substitutions,
    test_the_bloc_b_traps_are_reachable_by_their_own_evidence,
    test_adding_traps_did_not_cost_the_earlier_ones_their_questions,
    test_the_vague2_traps_are_well_formed,
    test_the_vague2_traps_are_reachable_by_their_own_evidence,
    test_the_ds3231_trap_says_which_track_must_not_be_cut,
    test_a_generic_complaint_word_is_what_hijacks,
    test_the_lot8_fragments_survived_the_session_cut,
    test_the_lot8_traps_carry_their_decisive_evidence,
    test_the_lot8_traps_are_reachable,
    test_the_word_sensor_is_what_hijacks_twice_over,
    test_the_lot9_traps_are_well_formed,
    test_the_lot9_traps_are_reachable,
    test_two_traps_that_would_destroy_the_part_say_so_first,
    test_the_qualified_symptom_rule_was_applied_to_lot9,
    test_the_lot7_traps_are_well_formed,
    test_the_lot7_traps_are_reachable,
    test_the_sht15_entry_says_an_empty_scan_is_normal,
    test_four_generic_words_had_to_be_purged_by_measurement,
    test_neither_trap_hijacks_unrelated_questions,
    test_the_lot8b_traps_are_well_formed,
    test_the_lot8b_traps_are_reachable,
    test_a_trap_competes_with_the_corpus_entry_of_its_own_chip,
    test_french_filler_words_carry_a_huge_weight_in_an_english_index,
    test_the_gy33_trap_exists_because_an_alias_was_wrong,
    test_the_queue_traps_are_reachable,
    test_an_entry_must_use_the_words_the_user_TYPES,
    test_the_queue_entries_confess_what_could_not_be_sourced,
]


def main() -> int:
    for t in TESTS:
        try:
            t()
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
            raise
        print(f"  OK {t.__name__}")
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

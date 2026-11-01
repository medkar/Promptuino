"""Tests du pipeline « composant hors-corpus » (spec 2026-07-29).

Sans réseau : la détection est purement lexicale, le choix de candidat et la
fabrication d'entrée ad hoc sont testés sur des données fabriquées, et le
lookup réel est seulement vérifié dans son mode dégradé (config absente).
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ── Détection lexicale ────────────────────────────────────────────────────────

def test_detects_unknown_part_number():
    from ui.registry_lookup import detect_unknown_part_tokens as d
    assert d("lis la couleur avec un capteur AS7341") == ["as7341"]


def test_detects_hyphenated_reference():
    from ui.registry_lookup import detect_unknown_part_tokens as d
    # « ZXQ-9000 » : les moitiés (« zxq », « 9000 ») ne sont pas des
    # part-numbers, la forme jointe « zxq9000 » oui.
    assert d("utilise mon module chinois ZXQ-9000") == ["zxq9000"]


def test_known_chips_are_not_flagged():
    from ui.registry_lookup import detect_unknown_part_tokens as d
    # Puces du corpus → connues, rien à chercher au registre.
    assert d("affiche la temperature du DHT22 sur un oled SSD1306") == []


def test_noise_is_not_flagged():
    from ui.registry_lookup import detect_unknown_part_tokens as d
    assert d("allume une led sur la broche 13") == []
    assert d("un sketch pour esp32 en 115200 bauds") == []   # blocklist + digits purs
    assert d("l'adresse i2c est 0x40") == []                 # littéral hex
    assert d("") == []


def test_named_module_is_not_flagged():
    from ui.registry_lookup import detect_unknown_part_tokens as d
    # HW-612 = module multi-puces NOMMÉ, résolu par hardware_modules (forçage
    # de ses puces corpus) — pas un composant inconnu.
    assert d("lis l'orientation avec un HW-612") == []


def test_detection_is_capped():
    from ui.registry_lookup import detect_unknown_part_tokens as d
    from ui.registry_lookup import _MAX_UNKNOWN_TOKENS
    toks = d("branche un AAA1111, un BBB2222 et un CCC3333")
    assert len(toks) == _MAX_UNKNOWN_TOKENS, toks


# ── Choix du candidat registre ────────────────────────────────────────────────

def _fake_search_results():
    return [
        {"name": "SparkFun Qwiic AS7341L 10-Channel Spectral Sensor",
         "latest": {"author": "SparkFun Electronics",
                    "sentence": "Spectral sensor."}},
        {"name": "DFRobot_AS7341",
         "latest": {"author": "DFRobot", "sentence": "11 channel sensor."}},
        {"name": "Adafruit AS7341",
         "latest": {"author": "Adafruit", "sentence": "AS7341 sensors."}},
        {"name": "Some Color Lib",
         "latest": {"author": "Rando", "sentence": "colors, unrelated"}},
    ]


def test_pick_candidate_deterministic():
    from ui.registry_lookup import _pick_candidate
    winner, others = _pick_candidate("as7341", _fake_search_results())
    # Token dans le nom + auteur établi le mieux classé + nom le plus court.
    assert winner["name"] == "Adafruit AS7341", winner
    # La lib dont ni le nom ni la description ne mentionnent le token n'est
    # JAMAIS candidate (c'est la substitution silencieuse qu'on éradique).
    assert "Some Color Lib" not in others, others
    assert set(others) == {"DFRobot_AS7341",
                           "SparkFun Qwiic AS7341L 10-Channel Spectral Sensor"}


def test_pick_candidate_refuses_irrelevant():
    from ui.registry_lookup import _pick_candidate
    winner, others = _pick_candidate("zxq9000", [
        {"name": "Foo", "latest": {"author": "Bar", "sentence": "baz"}}])
    assert winner is None and others == []


# ── Entrée ad hoc (exemple + headers) ─────────────────────────────────────────

def test_pick_example_prefers_basic_and_truncates():
    from ui.registry_lookup import _pick_example, _headers_of
    from ui.registry_lookup import _MAX_EXAMPLE_CHARS
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "examples" / "fancy_demo").mkdir(parents=True)
        (root / "examples" / "basic_read").mkdir(parents=True)
        (root / "examples" / "fancy_demo" / "fancy_demo.ino").write_text(
            "void setup(){/*FANCY*/}\nvoid loop(){}", encoding="utf-8")
        (root / "examples" / "basic_read" / "basic_read.ino").write_text(
            "void setup(){/*BASIC*/}\nvoid loop(){}", encoding="utf-8")
        ex = _pick_example(str(td))
        assert "BASIC" in ex and "FANCY" not in ex

        # Troncature à la frontière de ligne + marqueur explicite.
        big = "\n".join(f"int v{i} = {i};" for i in range(1000))
        (root / "examples" / "basic_read" / "basic_read.ino").write_text(
            big, encoding="utf-8")
        ex = _pick_example(str(td))
        assert ex.endswith("// … (example truncated)")
        assert len(ex) <= _MAX_EXAMPLE_CHARS + 40

        # Headers : métadonnées registre prioritaires, sinon scan *.h.
        (root / "src").mkdir()
        (root / "src" / "Foo.h").write_text("//", encoding="utf-8")
        assert _headers_of(str(td), ["Bar.h"]) == ["Bar.h"]
        assert _headers_of(str(td), []) == ["Foo.h"]


def test_adhoc_entry_is_injected_like_corpus_entry():
    from ui.rag import build_lib_context
    entry = {"id": "as7341", "name": "Adafruit AS7341",
             "headers": ["Adafruit_AS7341.h"], "keywords": ["as7341"],
             "example_code": "void setup(){/*ADHOC*/}", "api_signatures": {},
             "_registry": True}
    ctx = build_lib_context("lis un as7341", forced_libs=[entry])
    assert "Adafruit AS7341" in ctx
    assert "Adafruit_AS7341.h" in ctx
    assert "ADHOC" in ctx


# ── Cas orphelin ──────────────────────────────────────────────────────────────

def test_forced_empty_list_suppresses_retrieval():
    from ui.rag import build_lib_context
    # forced_libs=[] (liste vide ≠ None) : le retrieval sémantique bruité est
    # SUPPRIMÉ — le SLM ne reçoit pas les APIs d'une autre puce.
    assert build_lib_context("lis la couleur avec un AS7341",
                             forced_libs=[]) == ""


def test_retrieved_context_is_hedged_when_no_chip_named():
    # #38 point 2. Un composant seulement DECRIT peut faire remonter la lib
    # d'une AUTRE puce (mesure : les bandes de score se chevauchent, aucun seuil
    # ne les separe). On ne peut pas empecher le retrieval de se tromper, mais on
    # peut cesser de presenter le resultat comme faisant AUTORITE : le modele
    # recoit le droit explicite d'ignorer la section.
    from ui.rag import build_lib_context
    ctx = build_lib_context("mesure la distance avec un capteur a ultrasons")
    if ctx:                                   # depend du corpus, tolerant
        assert "Possibly relevant" in ctx, ctx[:200]
        assert "IGNORE this section" in ctx
        assert "written for a different part" in ctx


def test_named_chip_context_stays_authoritative():
    # Contrat inverse : quand l'utilisateur NOMME sa puce, l'en-tete reste
    # imperatif (sinon on affaiblirait le cas qui marche bien).
    from ui.rag import build_lib_context
    ctx = build_lib_context("affiche la temperature du DHT22")
    if ctx:
        assert "reference these exact APIs" in ctx, ctx[:200]
        assert "Possibly relevant" not in ctx


def test_forced_libs_context_stays_authoritative():
    # Libs FORCEES (module nomme, registre, clarification) : autorite aussi.
    from ui.rag import build_lib_context, corpus_entry
    entry = corpus_entry("adafruit-ssd1306")
    ctx = build_lib_context("affiche du texte", forced_libs=[dict(entry)])
    assert "reference these exact APIs" in ctx
    assert "Possibly relevant" not in ctx


# ── Supplément retrieval : déclencheur composant déclaré (TODO #40, part 1) ───
# `forced_libs` supprime TOUJOURS le retrieval par défaut (comportement de
# juillet, inchangé) — sauf quand l'appelant affirme explicitement, via
# `declared_component_forced=True`, que le seul déclencheur est le composant
# déclaré de l'utilisateur (jamais le part-number inconnu, dont la suppression
# reste délibérée et mesurée, cf. `test_forced_empty_list_suppresses_retrieval`
# et le 3e test ci-dessous). Charge le vrai modèle ONNX (corpus réel).

_FAKE_DECLARED_ENTRY = {
    "id": "declared-my-home-sensor",
    "name": "MyHomeSensor",
    "headers": ["MyHomeSensor.h"],
    "keywords": ["myhomesensor"],
    "example_code": "void setup(){/*HOME_SENSOR*/}",
    "api_signatures": {},
    "_registry": True,
}


def test_declared_component_forced_supplements_with_a_described_chip():
    # ⚠️ Ce test exerçait le supplément avec un chip NOMMÉ (« …avec un dht22 »)
    # et vérifiait qu'il arrivait HEDGÉ — ce qui contredisait la règle
    # catégorielle de #37, verrouillée deux tests plus haut par
    # `test_named_chip_context_stays_authoritative` : une puce nommée fait
    # AUTORITÉ. Il était vert, mais il exerçait la mauvaise situation. Depuis
    # le rattrapage de #40 partie 2 (a), une puce nommée rejoint le bloc
    # impératif ; le supplément hedgé garde son vrai domaine, la puce
    # seulement DÉCRITE. Le prompt ci-dessous ne nomme aucune puce
    # (`named_corpus_libs` renvoie [], mesuré) et fait tout de même remonter
    # les libs de température par similarité (0.522 / 0.505).
    from ui.rag import build_lib_context, named_corpus_libs
    prompt = "lis mon capteur maison et affiche la temperature ambiante"
    assert named_corpus_libs(prompt) == [], "le prompt ne doit NOMMER aucune puce"
    ctx = build_lib_context(
        prompt, forced_libs=[_FAKE_DECLARED_ENTRY],
        declared_component_forced=True)
    # Les DEUX en-têtes sont présents : le déclaré reste impératif, la lib
    # retrouvée par similarité reste hedgée — jamais fusionnés (#37).
    assert "reference these exact APIs" in ctx, ctx[:200]
    assert "Possibly relevant" in ctx, ctx[:200]
    assert "IGNORE this section" in ctx
    # Les DEUX libs sont documentées.
    assert "MyHomeSensor" in ctx and "HOME_SENSOR" in ctx
    assert "DallasTemperature" in ctx or "DHT.h" in ctx


def test_declared_component_forced_makes_a_NAMED_chip_authoritative():
    # Le pendant du test ci-dessus, et la raison pour laquelle il a changé de
    # prompt : la même situation avec une puce NOMMÉE doit produire UN bloc
    # impératif, pas un bloc hedgé. C'est la règle de #37 appliquée sans
    # exception au déclencheur « composant déclaré ».
    from ui.rag import build_lib_context
    ctx = build_lib_context(
        "lis mon capteur maison et affiche la temperature avec un dht22",
        forced_libs=[_FAKE_DECLARED_ENTRY], declared_component_forced=True)
    assert "MyHomeSensor" in ctx and "DHT.h" in ctx
    assert "reference these exact APIs" in ctx, ctx[:200]
    assert "Possibly relevant" not in ctx, ctx[:400]


def test_declared_component_forced_no_second_block_when_retrieval_empty():
    from ui.rag import build_lib_context
    # Prompt générique (comme test_generic_prompt_injects_no_lib) : rien ne
    # dépasse le plancher d'injection -> UN SEUL bloc, pas d'en-tête orphelin.
    ctx = build_lib_context(
        "utilise mon capteur maison pour lire une valeur et l'afficher",
        forced_libs=[_FAKE_DECLARED_ENTRY], declared_component_forced=True)
    assert "reference these exact APIs" in ctx, ctx[:200]
    assert "Possibly relevant" not in ctx, ctx[:300]
    assert "MyHomeSensor" in ctx


def test_unknown_part_number_forced_still_suppresses_the_SIMILARITY_retrieval():
    # ⚠️ Ce test affirmait « DHT not in ctx » : il verrouillait le fait que la
    # coupe du retrieval emportait AUSSI une puce que l'utilisateur avait
    # écrite noir sur blanc. Le commentaire d'origine le disait sans y voir un
    # défaut (« même un chip nommé […] n'obtient aucun contexte »). Mesuré le
    # 2026-08-10 : 29 des 91 entrées du corpus tombaient ainsi, dont servo,
    # NeoPixel, HX711, keypad, IRremote, PIR, GPS, L298N (cf. TODO #40 partie
    # 2 (a) et `scripts/test_named_chip_survives_suppression.py`).
    #
    # Ce qui doit rester coupé, et qui l'est : la SIMILARITÉ. Pour un AS7341,
    # elle remonte TCS34725 (0.522) — un autre capteur de couleur, la
    # substitution qui compile et se trompe en silence.
    from ui.rag import build_lib_context
    as7341 = {"id": "as7341", "name": "Adafruit AS7341",
             "headers": ["Adafruit_AS7341.h"], "keywords": ["as7341"],
             "example_code": "void setup(){/*ADHOC*/}", "api_signatures": {},
             "_registry": True}
    ctx = build_lib_context(
        "lis la couleur de la lumiere avec un as7341",
        forced_libs=[as7341])
    assert "Adafruit AS7341" in ctx
    assert "TCS34725" not in ctx, ctx     # le voisin fonctionnel reste dehors
    assert "Possibly relevant" not in ctx


def test_declared_component_forced_dedupes_lib_retrieved_twice():
    from ui.rag import build_lib_context, corpus_entry
    dht = corpus_entry("dht-sensor-library")
    assert dht is not None
    # La lib forcée EST celle que le retrieval retrouverait aussi (même prompt
    # que le 1er test, mais forced_libs = le vrai DHT au lieu d'un composant
    # sans rapport) -> ne doit apparaitre qu'UNE fois, jamais avec 2 tons.
    ctx = build_lib_context(
        "lis mon capteur maison et affiche la temperature avec un dht22",
        forced_libs=[dht], declared_component_forced=True)
    assert ctx.count("### DHT sensor library") == 1, ctx
    assert "Possibly relevant" not in ctx, (
        "rien de NOUVEAU a retrouver -> pas de second bloc")


def test_studio_wires_declared_component_forced_without_unknown_token():
    # Verrou structurel (comme test_studio_pipeline_wired) : le flag doit
    # rester calculé AVANT l'ajout du token declare a `unknown`, sinon un
    # prompt nommant a la fois un composant declare ET un part-number inconnu
    # serait traite a tort comme "declare seul" -> reintroduirait la toxicite
    # mesuree du declencheur part-number (cf. test juste au-dessus).
    src = (ROOT / "ui" / "studio_view.py").read_text(encoding="utf-8")
    assert "declared_component_forced" in src
    idx_flag = src.find("declared_component_forced = (declared_req is not None")
    idx_has_unknown = src.find("has_unknown_part_token = bool(unknown)")
    idx_append = src.find("unknown = [*unknown[:_MAX_UNKNOWN_TOKENS - 1], token]")
    assert -1 not in (idx_flag, idx_has_unknown, idx_append)
    assert idx_has_unknown < idx_flag < idx_append, (
        "has_unknown_part_token doit etre capture AVANT le calcul du flag, "
        "lui-meme AVANT que le token declare ne rejoigne `unknown`")


def test_named_part_late_in_context_file_still_ranks_first():
    # #38 point 4, MESURÉ : pas besoin de découper le fichier de contexte pour
    # qu'une puce NOMMÉE tardivement remonte — le boost lexical scanne le texte
    # ENTIER (seule la similarité sémantique est tronquée à 128 tokens). Ce test
    # verrouille cette propriété, qui est la raison pour laquelle le découpage a
    # été écarté (il n'apportait rien et amplifiait le bruit).
    from ui.rag import retrieve_libs
    filler = "\n".join(
        f"Note de montage numero {i} : alimentation, masse commune, "
        f"cablage soigne et verification visuelle avant mise sous tension."
        for i in range(30))
    doc = filler + "\nCapteur de temperature et humidite DHT22 sur la broche 2."
    libs = retrieve_libs(f"cable mon montage\n{doc}", k=3, threshold=0.0,
                         relative_gate=0.0)
    assert libs and libs[0].get("id") == "dht-sensor-library", \
        [(l.get("id"), round(l["_score"], 3)) for l in libs]


def test_orphan_directive_content():
    from ui.registry_lookup import unknown_component_directive as d
    txt = d(["zxq9000"])
    assert "zxq9000" in txt
    assert "different chip" in txt          # LA garantie : pas d emprunt
    assert d([]) == ""


def test_the_directive_no_longer_promises_todo_comments():
    """Decision utilisateur 2026-08-08 (QA A2) : on abandonne les `// TODO`.

    La banniere les annoncait, le modele ne les emettait pas de facon fiable
    (constat en QA : aucune section TODO dans le code genere). Promettre une
    section absente du code est pire que ne rien dire. L interdiction
    d emprunter la lib d une AUTRE puce, elle, reste -- c est l echec
    silencieux que ce pipeline existe pour supprimer.
    """
    from ui.registry_lookup import unknown_component_directive as d
    assert "TODO" not in d(["zxq9000"])


def test_a_failed_install_is_not_an_unknown_component():
    """QA A4 (2026-08-08). Quand l'installation de la lib echoue (reseau
    coupe), `lookup_component` repartait avec le statut INITIAL `not_found` :
    l'utilisateur lisait « composant inconnu au registre Arduino » alors que le
    registre venait de le TROUVER. Deux diagnostics opposes menant a deux
    actions opposees -- « cherche une autre puce » contre « rebranche ton
    reseau ». Meme confusion que celle corrigee dans `_search_registry`.
    """
    from ui import registry_lookup as rl

    def body(mod):
        calls = []

        def fake_run(cmd):
            calls.append(cmd)
            if "search" in cmd:
                import json
                return 0, json.dumps({"libraries": [
                    {"name": "Adafruit AS7341",
                     "latest": {"author": "Adafruit",
                                "sentence": "AS7341 sensor."}}]})
            return 1, "network is unreachable"      # l'INSTALL echoue

        old = mod.arduino_cli._run
        old_avail = mod.arduino_cli.is_available
        mod.arduino_cli._run = fake_run
        mod.arduino_cli.is_available = lambda: True
        try:
            r = mod.lookup_component("as7341", "cfg")
        finally:
            mod.arduino_cli._run = old
            mod.arduino_cli.is_available = old_avail

        assert r.status == "install_failed", r.status
        assert r.lib_name == "Adafruit AS7341", r.lib_name   # on sait laquelle
        assert r.entry is None                                # rien a injecter
        assert any("installation" in l for l in r.log), r.log

    _with_temp_cache(body)


def test_a_failed_install_is_not_cached():
    """Un echec reseau ne doit pas se figer : la prochaine tentative, en ligne,
    doit reussir."""
    from ui import registry_lookup as rl

    def body(mod):
        def fake_run(cmd):
            if "search" in cmd:
                import json
                return 0, json.dumps({"libraries": [
                    {"name": "Adafruit AS7341",
                     "latest": {"author": "Adafruit", "sentence": "AS7341."}}]})
            return 1, "boom"

        old, old_avail = mod.arduino_cli._run, mod.arduino_cli.is_available
        mod.arduino_cli._run = fake_run
        mod.arduino_cli.is_available = lambda: True
        try:
            mod.lookup_component("as7341", "cfg")
        finally:
            mod.arduino_cli._run, mod.arduino_cli.is_available = old, old_avail
        assert mod._cache_get("as7341") is None, "un echec ne se cache pas"

    _with_temp_cache(body)


def test_lookup_degrades_without_cli():
    # `_with_temp_cache` comme ses voisins ci-dessous : `_cache_get` est
    # consulte AVANT la verification du CLI, donc un vrai
    # ~/Documents/Promptuino/registry-cache.json contenant « as7341 »
    # repondait « found » et ce test echouait. Il ne passait que sur une
    # machine n'ayant jamais cherche cette puce -- trou d'hermeticite
    # demasque par une passe de QA reelle le 2026-08-08.
    def body(rl):
        r = rl.lookup_component("as7341", None)
        assert r.status == "unavailable" and r.entry is None
    _with_temp_cache(body)


# ── Search that BROKE vs search that found nothing (2026-08-03 review) ────
#
# A broken search and an empty search are opposite messages to the user --
# "retry, something's wrong" versus "this part does not exist, stop looking".
# `_search_registry`'s dedup refactor briefly collapsed the two; these two
# tests pin the distinction so a future refactor cannot quietly re-collapse
# it. Wrapped in `_with_temp_cache` so the shared "as7341" token used all
# over this file cannot hit a cache entry left by another test (or a real
# registry-cache.json) and short-circuit before the search is ever attempted.

def test_lookup_reports_unavailable_when_the_search_subprocess_raises():
    """Must read as a BROKEN search (status=unavailable, "échouée" in the
    log), never as "introuvable" -- which would tell the user the part does
    not exist when the truth is the search itself never completed."""
    def body(rl):
        old_available = rl.arduino_cli.is_available
        old_run = rl.arduino_cli._run
        rl.arduino_cli.is_available = lambda: True
        def _boom(*_a, **_k):
            raise OSError("simulated subprocess failure")
        rl.arduino_cli._run = _boom
        try:
            r = rl.lookup_component("as7341", "dummy.yaml")
        finally:
            rl.arduino_cli.is_available = old_available
            rl.arduino_cli._run = old_run
        assert r.status == "unavailable", r.status
        log = " ".join(r.log)
        assert "échouée" in log, r.log
        assert "introuvable" not in log, r.log
    _with_temp_cache(body)


def test_lookup_reports_unavailable_when_the_search_exits_non_zero():
    def body(rl):
        old_available = rl.arduino_cli.is_available
        old_run = rl.arduino_cli._run
        rl.arduino_cli.is_available = lambda: True
        rl.arduino_cli._run = lambda *_a, **_k: (1, "")
        try:
            r = rl.lookup_component("as7341", "dummy.yaml")
        finally:
            rl.arduino_cli.is_available = old_available
            rl.arduino_cli._run = old_run
        assert r.status == "unavailable", r.status
        log = " ".join(r.log)
        assert "échouée" in log, r.log
        assert "introuvable" not in log, r.log
    _with_temp_cache(body)


# ── Cache persistant (#38 point 1) ────────────────────────────────────────────

def _with_temp_cache(fn):
    """Execute fn() avec le cache redirige vers un fichier temporaire."""
    from ui import registry_lookup as rl
    with tempfile.TemporaryDirectory() as td:
        old = rl._CACHE_PATH
        rl._CACHE_PATH = Path(td) / "registry-cache.json"
        try:
            return fn(rl)
        finally:
            rl._CACHE_PATH = old


def test_cache_round_trip():
    def body(rl):
        entry = {"id": "as7341", "name": "Adafruit AS7341",
                 "headers": ["Adafruit_AS7341.h"], "keywords": ["as7341"],
                 "example_code": "void setup(){}", "api_signatures": {}}
        assert rl._cache_get("as7341") is None
        rl._cache_put("as7341", "Adafruit AS7341", entry, ["DFRobot_AS7341"])
        rec = rl._cache_get("as7341")
        assert rec["lib_name"] == "Adafruit AS7341"
        assert rec["entry"]["headers"] == ["Adafruit_AS7341.h"]
        assert rec["alternatives"] == ["DFRobot_AS7341"]
    _with_temp_cache(body)


def test_cache_hit_works_offline_without_cli():
    # L'interet principal : une puce deja vue reste utilisable SANS reseau et
    # meme SANS arduino-cli (config_file=None) — cas etablissement scolaire.
    def body(rl):
        entry = {"id": "as7341", "name": "Adafruit AS7341",
                 "headers": ["Adafruit_AS7341.h"], "keywords": ["as7341"],
                 "example_code": "void setup(){/*CACHED*/}",
                 "api_signatures": {}}
        rl._cache_put("as7341", "Adafruit AS7341", entry, [])
        # Toute tentative de sous-processus ferait echouer le test.
        def _boom(*a, **k):
            raise AssertionError("le cache doit eviter tout appel arduino-cli")
        old_run = rl.arduino_cli._run
        rl.arduino_cli._run = _boom
        try:
            r = rl.lookup_component("as7341", None)   # None = pas de CLI
        finally:
            rl.arduino_cli._run = old_run
        assert r.status == "found", r.status
        assert r.entry["example_code"] == "void setup(){/*CACHED*/}"
        assert "mémorisée" in " ".join(r.log)
    _with_temp_cache(body)


def test_a_stale_cache_does_not_beat_an_explicit_preference():
    """Revue finale 2026-07-30 : le hit de cache intervenait AVANT la logique
    `preferred_lib`, si bien qu'une lib SAISIE a la main ne servait jamais des
    que le token avait ete vu une fois — c'est-a-dire dans l'etat normal apres
    la premiere generation. L'utilisateur corrigeait la lib au crayon, le
    journal repondait « memorisee, pas de nouvelle recherche » et rien dans
    l'UI ne permettait de purger le cache : correction manuelle inoperante."""
    def body(rl):
        entry = {"id": "grove moisture sensor", "name": "MauvaiseLib",
                 "headers": ["Mauvaise.h"], "keywords": ["grove"],
                 "example_code": "", "api_signatures": {}}
        rl._cache_put("grove moisture sensor", "MauvaiseLib", entry, [])
        # Preference DIFFERENTE de ce qui est en cache -> le cache est perime
        # par definition : on doit rechercher (ici sans CLI, donc echec
        # HONNETE) et surtout ne pas rendre la valeur memorisee.
        r = rl.lookup_component("grove moisture sensor", None,
                                preferred_lib="Grove Moisture Sensor")
        assert r.lib_name != "MauvaiseLib", r.lib_name
        assert r.entry is None, r.entry
        assert "mémorisée, pas de nouvelle recherche" not in " ".join(r.log)
        # Preference qui CONCORDE (a la casse pres) -> le cache sert toujours.
        r2 = rl.lookup_component("grove moisture sensor", None,
                                 preferred_lib="mauvaiselib")
        assert r2.status == "found" and r2.lib_name == "MauvaiseLib", r2.lib_name
    _with_temp_cache(body)


def test_cache_tolerates_corruption_and_caps_size():
    def body(rl):
        rl._CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        rl._CACHE_PATH.write_text("{ pas du json", encoding="utf-8")
        assert rl._cache_load() == {}          # jamais d'exception
        assert rl._cache_get("as7341") is None
        # Version differente -> ignore (invalidation de schema).
        rl._CACHE_PATH.write_text('{"v": 999, "entries": {"x": {}}}',
                                  encoding="utf-8")
        assert rl._cache_load() == {}
        # Plafond de taille : les plus anciens sortent.
        for i in range(rl._CACHE_MAX_ENTRIES + 5):
            rl._cache_put(f"tok{i}", f"Lib {i}",
                          {"id": f"tok{i}", "name": f"Lib {i}"}, [])
        entries = rl._cache_load()
        assert len(entries) == rl._CACHE_MAX_ENTRIES, len(entries)
        assert "tok0" not in entries           # evince
        assert f"tok{rl._CACHE_MAX_ENTRIES + 4}" in entries   # conserve
    _with_temp_cache(body)


def test_cache_rejects_malformed_record():
    def body(rl):
        rl._CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        rl._CACHE_PATH.write_text(
            '{"v": 1, "entries": {"as7341": {"lib_name": "X"}}}',
            encoding="utf-8")                  # pas d'`entry`
        assert rl._cache_get("as7341") is None
    _with_temp_cache(body)


# ── i18n + branchement studio ─────────────────────────────────────────────────

def test_i18n_keys_all_languages():
    from ui.i18n import TRANSLATIONS
    for code in ("fr", "en", "es", "it"):
        s = TRANSLATIONS[code]
        assert "{part}" in s.registry_lib_found and "{lib}" in s.registry_lib_found, code
        assert "{part}" in s.registry_lib_not_found, code


def test_studio_pipeline_wired():
    src = (ROOT / "ui" / "studio_view.py").read_text(encoding="utf-8")
    assert "detect_unknown_part_tokens" in src
    assert "RegistryLookupWorker" in src
    assert "unknown_component_directive" in src
    assert "_continue_generation" in src


def test_journal_loader_starts_before_prompt_assembly():
    # Le sink RAG ecrit les diagnostics « [RAG] … » dans le journal PENDANT
    # l'assemblage du prompt (augment_user_prompt). _start_gen_loader vide le
    # journal : le demarrer APRES effacerait ces lignes -> diagnostics de
    # nouveau invisibles. On verrouille l'ordre dans _continue_generation.
    src = (ROOT / "ui" / "studio_view.py").read_text(encoding="utf-8")
    body = src.split("def _continue_generation", 1)[1]
    body = body.split("\n    def ", 1)[0]          # jusqu'a la methode suivante
    loader = body.find("_start_gen_loader()")
    assembly = min((i for i in (body.find("augment_user_prompt("),
                                body.find("_assemble_generation_prompt("))
                    if i != -1), default=-1)
    assert loader != -1, "_continue_generation doit demarrer le loader"
    assert assembly != -1, "_continue_generation doit assembler le prompt"
    assert loader < assembly, (
        "_start_gen_loader() doit preceder l'assemblage du prompt "
        f"(loader={loader}, assemblage={assembly})")


def test_a_bare_token_preference_reaches_the_lookup():
    """The gap this chantier closes: only DECLARED components could carry a
    preference. A plain part-number named in a prompt had nowhere to hold one,
    so the heuristic's guess came back forever."""
    import ui.component_libs as cl
    import ui.declared_components as dc
    from ui.studio_view import _preferred_libs_for_tokens
    cl._LIBRARY_PATH = Path(tempfile.mkdtemp(prefix="pref-")) / "component-libs.json"
    cl.set_registry({})
    dc.set_registry([])
    cl.set_preference("as7341", "DFRobot AS7341")
    assert _preferred_libs_for_tokens(["as7341"]) == {"as7341": "DFRobot AS7341"}
    assert _preferred_libs_for_tokens(["other"]) == {}
    assert _preferred_libs_for_tokens([]) == {}


TESTS = [
    test_detects_unknown_part_number,
    test_detects_hyphenated_reference,
    test_known_chips_are_not_flagged,
    test_noise_is_not_flagged,
    test_named_module_is_not_flagged,
    test_detection_is_capped,
    test_pick_candidate_deterministic,
    test_pick_candidate_refuses_irrelevant,
    test_pick_example_prefers_basic_and_truncates,
    test_adhoc_entry_is_injected_like_corpus_entry,
    test_forced_empty_list_suppresses_retrieval,
    test_retrieved_context_is_hedged_when_no_chip_named,
    test_named_chip_context_stays_authoritative,
    test_forced_libs_context_stays_authoritative,
    test_declared_component_forced_supplements_with_a_described_chip,
    test_declared_component_forced_makes_a_NAMED_chip_authoritative,
    test_declared_component_forced_no_second_block_when_retrieval_empty,
    test_unknown_part_number_forced_still_suppresses_the_SIMILARITY_retrieval,
    test_declared_component_forced_dedupes_lib_retrieved_twice,
    test_studio_wires_declared_component_forced_without_unknown_token,
    test_named_part_late_in_context_file_still_ranks_first,
    test_orphan_directive_content,
    test_the_directive_no_longer_promises_todo_comments,
    test_a_failed_install_is_not_an_unknown_component,
    test_a_failed_install_is_not_cached,
    test_lookup_degrades_without_cli,
    test_lookup_reports_unavailable_when_the_search_subprocess_raises,
    test_lookup_reports_unavailable_when_the_search_exits_non_zero,
    test_cache_round_trip,
    test_cache_hit_works_offline_without_cli,
    test_a_stale_cache_does_not_beat_an_explicit_preference,
    test_cache_tolerates_corruption_and_caps_size,
    test_cache_rejects_malformed_record,
    test_i18n_keys_all_languages,
    test_studio_pipeline_wired,
    test_journal_loader_starts_before_prompt_assembly,
    test_a_bare_token_preference_reaches_the_lookup,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

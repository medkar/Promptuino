"""Task 9 (seams purs) : decider si un swap de composant dans le schema doit
regenerer le code, et mapper un type wiring vers son corpus_id pour forcer la
bonne lib. L'integration (wrapper + confirm + regen) se verifie en UI.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)

from ui.studio_view import _chip_swap_regen_target, _apply_lib_overrides
from ui.clarification_groups import corpus_id_of_type
from ui.generation.feature_model import Feature


def test_screen_to_screen_regenerates():
    # ecran -> autre ecran = vrai changement de lib. Non-regression #82 : ce
    # cas passait deja par ClarifyGroups avant le routage registre, et passe
    # encore (test_chip_swaps_are_untouched_by_the_registry_routing dupliquait
    # cette assertion mot pour mot -- retire le 2026-08-29, zero couverture en
    # plus, mutation-verifie).
    assert _chip_swap_regen_target("oled_ssd1306", "sh1106") == "sh1106"


def test_no_change_no_regen():
    assert _chip_swap_regen_target("oled_ssd1306", "oled_ssd1306") is None


def test_bare_target_regenerates_to_drop_lib():
    # Puce a lib -> cible NUE (LED) : le code doit LACHER la lib de l'ecran
    # (sinon il pilote toujours le SSD1306 — divergence silencieuse, revue
    # 2026-07-29). Regeneration proposee.
    assert _chip_swap_regen_target("oled_ssd1306", "led") == "led"


def test_bare_to_bare_no_regen():
    # Aucun des deux n'a d'entree corpus : le cablage change, pas le code.
    # NB : "button" figurait ici jusqu'au 2026-08-29 (#82) -- FAUX depuis que
    # le registre existe (2026-07-31) : il A une entree ("onebutton", une
    # vraie bibliotheque). Cf. test_a_registry_only_mapping_also_regenerates.
    # Non-regression #82 : led/relay restent tous deux sans cid meme routes
    # par le registre (test_chip_swaps_are_untouched_by_the_registry_routing
    # dupliquait cette assertion mot pour mot -- retire le 2026-08-29).
    assert _chip_swap_regen_target("led", "relay") is None


def test_a_corpus_entry_without_a_library_still_regenerates():
    """Garde-fou ajoute le 2026-08-10 : `buzzer`, `ldr` et `mq135` ont une
    entree corpus SANS `arduino_lib_name`, et doivent quand meme declencher
    l'offre -- ce qui compte est que le CODE doive changer (`digitalWrite` ->
    `tone()` / `analogRead`), pas qu'une librairie change.

    Ce comportement n'etait documente que dans un COMMENTAIRE de test, et
    resserrer `_has_lib` sur `arduino_lib_name` le supprimait avec 23/23 au
    vert. C'est ce trou-la que ce test bouche."""
    from ui.rag import corpus_entry
    from ui.clarification_groups import corpus_id_of_type
    for bare in ("buzzer", "ldr", "mq135"):
        entry = corpus_entry(corpus_id_of_type(bare))
        assert entry is not None, bare
        assert not (entry.get("arduino_lib_name") or "").strip(), (
            f"{bare} a gagne une librairie : ce test ne prouve plus rien")
        assert _chip_swap_regen_target("led", bare) == bare, bare


def test_a_registry_only_mapping_also_regenerates():
    """Trouvaille faite en implementant #82 : cette suite affirmait depuis le
    2026-07-29 que `_chip_swap_regen_target("button", "led")` rend None, une
    ligne ecrite AVANT que le registre (2026-07-31) ne declare que le document
    de "button" est "onebutton" (vraie bibliotheque, contrairement a
    buzzer/ldr/mq135 ci-dessus). "button" n'est ambigu avec rien, donc aucun
    `ClarifyGroup` ne le liste et `corpus_id_of_type` le manquait
    structurellement -- pas parce qu'il n'a pas d'entree corpus. Meme racine
    que les drivers : le registre la connait, et #82 la fait desormais
    compter. Passer de bouton (digitalRead) a LED (digitalWrite) change bien
    le code."""
    assert _chip_swap_regen_target("button", "led") == "led"


def test_driver_swaps_now_have_a_target_via_the_registry():
    """Mesure du 2026-08-29 : _chip_swap_regen_target rendait None pour TOUS
    les couples de drivers -- corpus_id_of_type derive des ClarifyGroup, qui
    excluent moteurs et drivers. Le registre, lui, connait les
    correspondances. Sans cible, changer de driver ne peut jamais offrir de
    regeneration."""
    assert _chip_swap_regen_target("l298n", "drv8833") == "drv8833"
    assert _chip_swap_regen_target("drv8833", "l298n") == "l298n"
    assert _chip_swap_regen_target("a4988", "drv8825") == "drv8825"
    # tb6612fng: entree corpus SANS lib depuis #83 -- compte quand meme
    # (meme regle que buzzer/ldr : c'est le CODE qui doit changer).
    assert _chip_swap_regen_target("l298n", "tb6612fng") == "tb6612fng"


def test_regenerate_feature_with_chip_resolves_driver_swaps_via_the_registry():
    """Verrouille le VRAI defaut trouve en revue (2026-08-29) : avant #82,
    `_regenerate_feature_with_chip` (ui/studio_view.py -- le SECOND appelant
    de la resolution type->corpus, distinct de `_chip_swap_regen_target`)
    resolvait old_cid/new_cid via `corpus_id_of_type` SEULE. Reverter
    uniquement ces deux lignes vers `corpus_id_of_type` laissait la suite au
    vert (225/225) : aucun test n'appelait cette methode avec un type de
    driver, chaque test banned_lib_ids/forced_lib_ids construit un Feature
    a la main avec des identifiants deja resolus. Celui-ci appelle la VRAIE
    methode -- mutation-verifie : il echoue si les deux lignes sont
    reverties vers `corpus_id_of_type`."""
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("intermediate")
    v._features = [Feature(id="f1", prompt="pilote un moteur DC avec un L298N")]
    v.save_project = lambda *a, **k: None
    v._start_assembly_verify = lambda: False
    captured = {}

    def fake_launch(action, fn_id, prompt, from_scratch=False,
                    forced_override=None):
        captured["prompt"] = prompt
        captured["forced_override"] = forced_override
    v._launch_generation = fake_launch

    v._regenerate_feature_with_chip("f1", "l298n", "drv8833")

    feat = next(f for f in v._features if f.id == "f1")
    assert feat.banned_lib_ids == ["l298n"], feat.banned_lib_ids
    assert feat.forced_lib_ids == ["drv8833"], feat.forced_lib_ids
    ids = [lib.get("id") for lib in (captured["forced_override"] or [])]
    assert ids == ["drv8833"], ids
    note = captured["prompt"].split("\n\n")[-1]
    assert "DRV8833" in note and "L298N" in note, note
    assert "use the DRV8833" in note, note


def test_corpus_id_of_type_has_no_second_caller_in_studio_view():
    """Garde structurelle (meme forme que
    `test_no_mode_test_survives_in_the_resolution_path`,
    scripts/test_unified_modal_all_modes.py) : `corpus_id_of_type` ne doit
    avoir QU'UN SEUL appelant dans ce fichier, `_corpus_id` -- le point de
    passage unique par le registre (#82). Un second appelant reproduirait
    en silence le defaut que le test ci-dessus verrouille par le
    comportement ; celui-ci verrouille la FORME du code, pour qu'un
    TROISIEME appelant futur ne puisse pas rouvrir le meme trou sans faire
    rougir la suite. Mutation-verifie."""
    src = (Path(__file__).resolve().parents[1]
           / "ui" / "studio_view.py").read_text(encoding="utf-8")
    start = src.index("def _corpus_id(")
    end = src.index("\ndef ", start + 10)  # prochaine def de niveau module
    body = src[start:end]
    assert body.count("corpus_id_of_type(") == 1, (
        "`_corpus_id` doit etre le SEUL appelant de `corpus_id_of_type` -- "
        "introuvable dans son propre corps.")
    rest = src[:start] + src[end:]
    offenders = [ln.strip() for ln in rest.splitlines()
                 if "corpus_id_of_type(" in ln]
    assert not offenders, (
        "`corpus_id_of_type` a un second appelant hors de `_corpus_id` : "
        f"{offenders} -- doit passer par le registre (`_corpus_id`), pas "
        "par ClarifyGroups seul (#82).")


def test_empty_no_regen():
    assert _chip_swap_regen_target("oled_ssd1306", "") is None


def test_corpus_id_of_type_maps_wiring_type():
    # svg_type 'oled_ssd1306' -> corpus_id 'adafruit-ssd1306'
    assert corpus_id_of_type("oled_ssd1306") == "adafruit-ssd1306"
    # 'sh1106' : corpus_id == type wiring
    assert corpus_id_of_type("sh1106") == "sh1106"
    assert corpus_id_of_type("does-not-exist") is None


# ── Durabilite du swap (revue 2026-07-29, bug #1) ────────────────────────────

def test_feature_persists_lib_overrides():
    # Round-trip .promptuino.json : les swaps survivent au reload du projet.
    f = Feature(id="f1", prompt="affiche du texte sur un ecran",
                banned_lib_ids=["adafruit-ssd1306"], forced_lib_ids=["sh1106"])
    f2 = Feature.from_dict(f.to_dict())
    assert f2.banned_lib_ids == ["adafruit-ssd1306"]
    assert f2.forced_lib_ids == ["sh1106"]
    # Projets d'avant la fonctionnalite : champs absents -> listes vides.
    legacy = Feature.from_dict({"id": "f1", "prompt": "x"})
    assert legacy.banned_lib_ids == [] and legacy.forced_lib_ids == []


def test_apply_lib_overrides_replays_swap_on_regen():
    # Scenario du bug : swap SSD1306->SH1106, puis clic ↻ plus tard. Le
    # forcage recalcule le defaut RAG (SSD1306 pour un prompt qui le nomme) ;
    # les overrides persistes doivent bannir SSD1306 et re-forcer SH1106.
    from ui.rag import corpus_entry
    feat = Feature(id="f1", prompt="ecran",
                   banned_lib_ids=["adafruit-ssd1306"],
                   forced_lib_ids=["sh1106"])
    default = [dict(corpus_entry("adafruit-ssd1306"))]
    out = _apply_lib_overrides(default, [feat])
    ids = [lib.get("id") for lib in out]
    assert "adafruit-ssd1306" not in ids, ids
    assert "sh1106" in ids, ids


def test_apply_lib_overrides_ban_only_no_longer_suppresses_retrieval():
    # #85 : swap vers une cible NUE (ban sans remplacant) -> None, PAS [].
    # La liste vide coupait TOUT le retrieval de la generation (mesure
    # 2026-08-31 : une feature servo+capteur perdait aussi le contexte du
    # capteur), pendant que la lib bannie revenait quand meme par le
    # sauvetage des puces nommees. Le ban filtre desormais l'injection
    # (rag.build_lib_context(banned_libs=...)), le retrieval tourne.
    feat = Feature(id="f1", prompt="ecran",
                   banned_lib_ids=["adafruit-ssd1306"], forced_lib_ids=[])
    assert _apply_lib_overrides(None, [feat]) is None


def test_banned_lib_ids_exposes_the_bans_of_the_targeted_features():
    # #85 : la porte unique du ban. C'est cet ensemble que _start_generation
    # descend jusqu'au RAG -- s'il oublie une feature, la lib bannie revient.
    from ui.studio_view import _banned_lib_ids
    f1 = Feature(id="f1", prompt="ecran",
                 banned_lib_ids=["adafruit-ssd1306"], forced_lib_ids=[])
    f2 = Feature(id="f2", prompt="servo", banned_lib_ids=["servo"])
    assert _banned_lib_ids([f1, f2]) == {"adafruit-ssd1306", "servo"}
    assert _banned_lib_ids([Feature(id="f3", prompt="x")]) == frozenset()


def test_start_generation_threads_the_bans_down_to_the_prompt_assembly():
    """#85, test de FIL (lecon des trois bancs verts du 2026-08-31 : tester la
    chaine que l'app appelle, pas une reconstitution). Un ensemble calcule
    mais jamais transmis serait invisible aux tests unitaires du RAG ; ici on
    conduit _start_generation avec une feature bannie et on verifie que
    augment_user_prompt recoit bien les bans."""
    import ui.studio_view as sv
    v = sv.StudioView()
    v._on_mode_changed("intermediate")
    feat = Feature(id="f1", prompt="un servo qui suit le potentiometre",
                   banned_lib_ids=["servo"], forced_lib_ids=[])
    v._features = [feat]
    seen = {}

    def _record_augment(instr, **kw):
        seen["banned_libs"] = kw.get("banned_libs")
        return instr

    orig_augment = sv.augment_user_prompt
    orig_backstage = sv.StudioView._prompt_backstage
    sv.augment_user_prompt = _record_augment
    # Coulisses annulees : la generation s'arrete proprement juste APRES
    # l'assemblage du prompt -- aucun backend appele.
    sv.StudioView._prompt_backstage = (
        lambda self, *a, **k: sv._BACKSTAGE_CANCELLED)
    try:
        v._start_generation(None, sv.CORRECT, "f1",
                            "change la vitesse", from_scratch=False)
    finally:
        sv.augment_user_prompt = orig_augment
        sv.StudioView._prompt_backstage = orig_backstage
    assert seen.get("banned_libs") == frozenset({"servo"}), seen


def test_apply_lib_overrides_noop_without_overrides():
    feat = Feature(id="f1", prompt="x")
    assert _apply_lib_overrides(None, [feat]) is None
    sentinel = [{"id": "dht-sensor-library"}]
    assert _apply_lib_overrides(sentinel, [feat]) is sentinel


def test_regen_note_restates_the_swap():
    # QA B1 (2026-08-08) : le forcage de libs etait bien re-applique au ↻, mais
    # le prompt STOCKE de la fonctionnalite nomme toujours l'ancienne puce
    # (« ... ecran OLED SSD1306 ») et le modele suit le prompt. Le swap
    # lui-meme marchait parce qu'il ajoutait une consigne ; le ↻ envoyait le
    # prompt nu, donc la puce remplacee revenait.
    from ui.studio_view import _lib_override_note
    feat = Feature(id="f1", prompt="affiche du texte sur un ecran OLED SSD1306",
                   banned_lib_ids=["adafruit-ssd1306"],
                   forced_lib_ids=["sh1106"])
    note = _lib_override_note([feat])
    assert note, "un swap persiste doit produire une consigne"
    low = note.lower()
    assert "sh1106" in low, note              # la lib a utiliser
    assert "ssd1306" in low, note             # celle a ne plus utiliser
    assert "not" in low or "instead" in low, note


def test_regen_note_for_a_ban_without_replacement():
    # Swap vers une cible NUE (LED...) : la consigne est de LACHER l'ancienne
    # lib, pas d'en adopter une nouvelle -- ne rien inventer.
    from ui.studio_view import _lib_override_note
    feat = Feature(id="f1", prompt="ecran",
                   banned_lib_ids=["adafruit-ssd1306"], forced_lib_ids=[])
    note = _lib_override_note([feat])
    assert note and "ssd1306" in note.lower(), note
    assert "sh1106" not in note.lower(), note


def test_regen_note_is_empty_without_overrides():
    from ui.studio_view import _lib_override_note
    assert _lib_override_note([Feature(id="f1", prompt="x")]) == ""
    assert _lib_override_note([]) == ""


def test_the_prompt_renames_the_chip_instead_of_contradicting_it():
    # Plus elegant que d'ajouter une consigne qui contredit le prompt : quand
    # l'ancienne puce est NOMMEE, on la remplace par la nouvelle, et la phrase
    # reste coherente. La consigne ne sert plus que de repli.
    from ui.studio_view import _prompt_with_lib_overrides
    feat = Feature(id="f1", prompt="affiche du texte sur un ecran OLED SSD1306",
                   banned_lib_ids=["adafruit-ssd1306"],
                   forced_lib_ids=["sh1106"])
    out = _prompt_with_lib_overrides(feat.prompt, [feat])
    # C'est la DEMANDE qui doit avoir ete corrigee. La consigne qui suit peut
    # legitimement nommer la lib bannie (« Do NOT use Adafruit SSD1306 ») :
    # elle parle de la BIBLIOTHEQUE, plus de la puce demandee.
    request = out.split("\n\n")[0]
    assert "SSD1306" not in request.upper(), request
    assert "SH1106" in request, request        # casse du nom, pas du keyword
    # Plus de clause « meme si la demande ci-dessus la nomme encore » : elle
    # serait fausse maintenant que la phrase a ete corrigee.
    assert "still names it" not in out, out


def test_a_chip_not_named_in_the_prompt_falls_back_on_the_directive():
    # Rien a remplacer : la consigne reste le seul moyen de dire au modele
    # quelle lib utiliser.
    from ui.studio_view import _prompt_with_lib_overrides
    feat = Feature(id="f1", prompt="affiche du texte sur un ecran",
                   banned_lib_ids=["adafruit-ssd1306"],
                   forced_lib_ids=["sh1106"])
    out = _prompt_with_lib_overrides(feat.prompt, [feat])
    assert "SH1106" in out.upper(), out
    assert "still names it" in out, out


def test_no_substitution_when_the_target_has_no_part_number():
    # `adafruit-vl53l0x` n'expose aucun numero de piece exploitable dans ses
    # keywords : substituer donnerait n'importe quoi, on s'abstient et la
    # consigne prend le relais. Mesure faite avant d'ecrire la regle.
    from ui.studio_view import _part_numbers, _prompt_with_lib_overrides
    assert _part_numbers("adafruit-vl53l0x") == []
    feat = Feature(id="f1", prompt="mesure la distance avec un HC-SR04",
                   banned_lib_ids=["newping"],
                   forced_lib_ids=["adafruit-vl53l0x"])
    out = _prompt_with_lib_overrides(feat.prompt, [feat])
    assert "HC-SR04" in out, "sans cible sure, ne pas toucher au prompt"
    assert "still names it" in out, out


def test_no_substitution_when_the_target_covers_several_chips():
    # `dht-sensor-library` couvre DHT11/DHT22/DHT21/AM2302/AM2301 : prendre le
    # premier transformerait un DHT11 en DHT22. On s'abstient.
    from ui.studio_view import _part_numbers, _prompt_with_lib_overrides
    assert len(_part_numbers("dht-sensor-library")) > 1
    feat = Feature(id="f1", prompt="lis la temperature avec un AHT20",
                   banned_lib_ids=["adafruit-aht20"],
                   forced_lib_ids=["dht-sensor-library"])
    out = _prompt_with_lib_overrides(feat.prompt, [feat])
    assert "AHT20" in out, out


def test_the_prompt_is_untouched_without_any_swap():
    from ui.studio_view import _prompt_with_lib_overrides
    feat = Feature(id="f1", prompt="allume une LED")
    assert _prompt_with_lib_overrides(feat.prompt, [feat]) == "allume une LED"


# ── Le swap doit SURVIVRE a la generation qu'il declenche (QA B1, 2026-08-08) ─
#
# Tous les tests ci-dessus passent les identifiants AU CONSTRUCTEUR de Feature.
# Aucun ne fait traverser une generation a la Feature -- et c'est precisement la
# que le swap mourait : la Feature est RECONSTRUITE apres chaque generation, et
# les deux constructions oubliaient ces deux champs. Le mecanisme etait donc
# vert de bout en bout sur des objets faits main, et mort en usage reel.

def test_clean_feature_contributions_keeps_the_user_s_lib_choices():
    """`clean_feature_contributions` soustrait le code RE-EMIS -- elle n'a
    aucune raison de toucher aux decisions de l'utilisateur."""
    from ui.generation import clean_feature_contributions
    feat = Feature(id="f1", prompt="ecran", includes=["#include <A.h>"],
                   banned_lib_ids=["adafruit-ssd1306"],
                   forced_lib_ids=["sh1106"])
    out = clean_feature_contributions(feat, [])
    assert out.banned_lib_ids == ["adafruit-ssd1306"], out.banned_lib_ids
    assert out.forced_lib_ids == ["sh1106"], out.forced_lib_ids


_SKETCH = (
    "// FEATURE: affiche du texte\n"
    "#include <Adafruit_SH110X.h>\n"
    "Adafruit_SH1106G display(128, 64, &Wire);\n"
    "void setup() {\n  display.begin(0x3C, true);\n}\n"
    "void loop() {\n}\n"
)


def _view_with_swapped_feature():
    """StudioView portant UNE fonctionnalite dont la puce a ete swappee.
    La verification compile et la sauvegarde sont neutralisees : on teste la
    reconstruction de la Feature, pas la chaine de livraison."""
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("intermediate")
    v._features = [Feature(id="f1",
                           prompt="affiche du texte sur un ecran OLED SSD1306",
                           banned_lib_ids=["adafruit-ssd1306"],
                           forced_lib_ids=["sh1106"])]
    v.save_project = lambda *a, **k: None
    v._start_assembly_verify = lambda: False
    return v


def test_the_swap_survives_the_regeneration_it_triggers():
    """Le scenario reel de QA B1 : swap SSD1306 -> SH1106, la regeneration
    part, puis on clique ↻. Avant le correctif, la Feature regenere naissait
    SANS les identifiants -> le ↻ envoyait le prompt nu -> le RAG recalculait
    son defaut et le SSD1306 revenait en silence."""
    from ui.studio_view import CORRECT
    v = _view_with_swapped_feature()
    v._pending_action = (CORRECT, "f1")
    v._pending_from_scratch = True
    v._on_generation_done(_SKETCH)
    feat = next(f for f in v._features if f.id == "f1")
    assert feat.banned_lib_ids == ["adafruit-ssd1306"], feat.banned_lib_ids
    assert feat.forced_lib_ids == ["sh1106"], feat.forced_lib_ids


def test_the_regenerated_feature_still_carries_the_swap_into_the_next_prompt():
    """Bout en bout : apres la regeneration, le prompt du ↻ SUIVANT doit
    toujours renommer la puce. C'est l'observable de la procedure B1."""
    from ui.studio_view import CORRECT, _prompt_with_lib_overrides
    v = _view_with_swapped_feature()
    v._pending_action = (CORRECT, "f1")
    v._pending_from_scratch = True
    v._on_generation_done(_SKETCH)
    feat = next(f for f in v._features if f.id == "f1")
    out = _prompt_with_lib_overrides(feat.full_prompt(), [feat])
    # La DEMANDE est renommee. `SSD1306` reste attendu plus bas, dans la
    # clause « Do NOT use ... » qui nomme la lib bannie -- assertion scopee a
    # la phrase, sinon elle interdirait la directive elle-meme.
    request = out.splitlines()[0]
    assert "SH1106" in request.upper(), out
    assert "SSD1306" not in request.upper(), out


def test_the_swap_directive_names_components_not_identifiers():
    """QA B1-bis (2026-08-08) : la consigne envoyee au modele disait
    « Replace the oled_ssd1306 with a sh1106 » -- des identifiants internes.
    `label_of` ne connait que le catalogue de remplacement et rend None pour
    les types du cablage ; c'est `_label` qui porte le nom humain."""
    from ui.wiring.replacement_catalog import label_of
    from ui.wiring.instructions import _label as _type_label
    for t in ("oled_ssd1306", "sh1106", "led"):
        assert label_of(t) is None, f"{t}: le repli n'est donc jamais exerce ?"
    assert _type_label("oled_ssd1306", "en") == "SSD1306 OLED screen"
    assert _type_label("sh1106", "en") == "OLED display (SH1106)"
    # Le repli ultime reste le type brut : un type sans libelle ne doit pas
    # faire disparaitre la consigne.
    assert (_type_label("type_inexistant", "en") or "type_inexistant")


def test_dead_divergence_guard_removed():
    # Revue 2026-07-29 bug #2 : l'ancien garde etait mort en production et son
    # smoke test donnait une fausse couverture -> supprimes tous les deux.
    src = (Path(__file__).resolve().parents[1]
           / "ui" / "wiring" / "ambiguity_dialog.py").read_text(encoding="utf-8")
    assert "def apply_with_divergence_guard" not in src
    assert "def _confirm_divergence" not in src


TESTS = [
    test_screen_to_screen_regenerates, test_no_change_no_regen,
    test_bare_target_regenerates_to_drop_lib, test_bare_to_bare_no_regen,
    test_a_corpus_entry_without_a_library_still_regenerates,
    test_a_registry_only_mapping_also_regenerates,
    test_driver_swaps_now_have_a_target_via_the_registry,
    test_regenerate_feature_with_chip_resolves_driver_swaps_via_the_registry,
    test_corpus_id_of_type_has_no_second_caller_in_studio_view,
    test_empty_no_regen, test_corpus_id_of_type_maps_wiring_type,
    test_feature_persists_lib_overrides,
    test_apply_lib_overrides_replays_swap_on_regen,
    test_apply_lib_overrides_ban_only_no_longer_suppresses_retrieval,
    test_banned_lib_ids_exposes_the_bans_of_the_targeted_features,
    test_start_generation_threads_the_bans_down_to_the_prompt_assembly,
    test_apply_lib_overrides_noop_without_overrides,
    test_regen_note_restates_the_swap,
    test_regen_note_for_a_ban_without_replacement,
    test_regen_note_is_empty_without_overrides,
    test_clean_feature_contributions_keeps_the_user_s_lib_choices,
    test_the_swap_survives_the_regeneration_it_triggers,
    test_the_regenerated_feature_still_carries_the_swap_into_the_next_prompt,
    test_the_swap_directive_names_components_not_identifiers,
    test_the_prompt_renames_the_chip_instead_of_contradicting_it,
    test_a_chip_not_named_in_the_prompt_falls_back_on_the_directive,
    test_no_substitution_when_the_target_has_no_part_number,
    test_no_substitution_when_the_target_covers_several_chips,
    test_the_prompt_is_untouched_without_any_swap,
    test_dead_divergence_guard_removed,
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

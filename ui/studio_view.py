"""
Studio view — main development tab.

Layout (intermediate/advanced):
  ┌──────────────────────────────────────────┐
  │  [Débutant]  [Intermédiaire]  [Avancé]  │
  ├──────────────────────────────────────────┤
  │  Prompt IA                               │
  │  ┌────────────────────────────────────┐  │
  │  │ prompt field                       │  │
  │  └────────────────────────────────────┘  │
  │  [Générer le code]  <possible error>     │  ← inter/advanced
  │  Code généré                             │  ← inter/advanced
  │  ┌────────────────────────────────────┐  │
  │  │ colored editor                     │  │  ← inter/advanced
  │  └────────────────────────────────────┘  │
  │  [Compiler & Uploader] <status>          │  ← inter/advanced
  │  Sortie                                  │  ← inter/advanced
  │  ┌────────────────────────────────────┐  │
  │  │ output area (read-only)            │  │  ← inter/advanced
  │  └────────────────────────────────────┘  │
  └──────────────────────────────────────────┘
"""
import copy
import re as _re
import shutil
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QEvent, QPoint, QSize
from PyQt6.QtGui import (
    QPalette, QColor, QPainter, QTextCursor,
    QKeySequence, QShortcut,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QSizePolicy, QScrollArea,
    QDialog, QMessageBox, QLineEdit, QToolTip, QSlider,
    QCheckBox, QFileDialog, QSpacerItem, QMenu, QApplication,
)

from .theme import (
    ColorScheme, theme_manager,
    primary_button_qss, secondary_button_qss, radio_checkbox_qss,
    neutral_button_qss, selection_bg, install_icon_hover, context_menu_qss, danger_button_qss,
    slider_qss, chip_button_qss,
)
from .fonts import MONO_CSS, mono_caps_font
from .i18n import lang_manager, Strings
from .message_box import ask_yes_no
from .robot_loader import RobotLoader
from .topbar import ModeSelector
from .ai_config import ai_config
from .session import session
from . import progress_nudge as PN
from .nudge_banner import NudgeBanner
from .studio import (
    LogWidget, ConsolePanel, CodePanel, phase_div_html, phase_title_html,
)
from .studio.compile_service import CompileService, PHASE_COLORS
from .studio.generation_flow import (
    GenerateWorker as _GenerateWorker,
    build_codegen_preview as _build_codegen_preview,
    build_codegen_parts as _build_codegen_parts,
    PromptPreviewDialog as _PromptPreviewDialog,
)
from .ai_backends import get_backend_instance
from .project_manager import (
    Project, ProjectType, project_manager,
    is_name_valid, type_dir,
)
from .rag import augment_user_prompt, set_status_sink as rag_set_status_sink
from .feature_transfer_dialog import FeatureTransferDialog
from . import icons as IC
from ui.generation import (
    Feature, parse_sketch, SketchParseError, assemble, assemble_with_map,
    splice_add,
    splice_replace, SpliceError, is_dirty, build_context_summary,
    build_feature_instruction, build_modify_instruction, build_regen_instruction,
    extract_feature_summary,
    feature_label, next_feature_id,
    FEATURE_SUMMARY_DIRECTIVE, REGENERATE, ADD, CORRECT,
)
from ui.generation.line_attribution import (
    transfer_map, match_contributions, single_feature_map,
)
from ui.generation.feature_resync import sync_features_from_editor
from ui.generation.feature_model import MANUAL_ID
from ui.generation.gen_modal import GenerationModal


def should_verify_assembly(action: str, n_features: int) -> bool:
    """Vrai si l'operation a ASSEMBLE plusieurs fonctionnalites (risque de
    couplage type 'lis X' + 'affiche X'). REGENERATE = 1 fonctionnalite
    coherente -> jamais."""
    return action in (ADD, CORRECT) and n_features >= 2


def _strip_feature_metadata(meta: dict, ids: set) -> dict:
    """Retire les entrees dont la 1re composante de cle (fn_id) est dans `ids`.
    Sert au nettoyage de _wiring_resolutions / _implicit_actions a la suppression
    d'une fonctionnalite (cles `(fn_id, ...)`)."""
    return {k: v for k, v in meta.items() if k[0] not in ids}


def _regen_plan(selected: list) -> tuple:
    """(target, prompt) pour regenerer une selection de fonctionnalites :
    1 -> (id, prompt) = remplacement en place ; >=2 -> ([ids], prompts combines)
    = fusion (chemin CORRECT a >=2 cibles). Le prompt rejoue l'INTENT COMPLET
    (full_prompt = prompt d'origine + toutes les modifications), pas seulement
    le dernier delta — sinon la regeneration perdrait les modifs precedentes."""
    from .generation.gen_prompts import combine_feature_prompts
    if len(selected) == 1:
        return selected[0].id, selected[0].full_prompt()
    return ([f.id for f in selected],
            combine_feature_prompts([f.full_prompt() for f in selected]))


def _corpus_id(t: str) -> str | None:
    """Corpus id d'un type wiring. Le REGISTRE d'abord : c'est lui qui possede
    l'identite d'un composant, et seul le 1er document lui appartient -- meme
    PRINCIPE que `Component.default_document` (`ui/component_registry.py:166`,
    la vraie autorite ici), pas la regle de `lib_by_header` : celle-ci porte
    sur le 1er HEADER d'une entree corpus, une structure differente ; meme
    motif, autre proprietaire.

    `corpus_id_of_type` (ClarifyGroups) reste le repli, mais il est INERTE sur
    le domaine atteignable AUJOURD'HUI (mesure 2026-08-29, pas une projection) :
    des 62 types que les `ClarifyGroup` couvrent, le registre en resout deja
    50 directement -- ce sont les seuls qui sont de VRAIS types wiring. Les 12
    restants (`rtclib`, `sd`, `lora`...) sont des identifiants de corpus BRUTS
    que `clarification_groups.candidates_of_function` documente deja comme
    n'etant JAMAIS des types wiring (TODO #67, meme fichier). Le repli est
    donc gardé pour un candidat FUTUR de ClarifyGroup absent du registre, pas
    parce qu'il couvre un cas reel aujourd'hui. Et les groupes EXCLUENT
    deliberement moteurs et drivers, ce qui rendait None pour tous leurs
    couples (mesure 2026-08-29, #82).

    Module-level (et non plus imbriquee dans `_chip_swap_regen_target`, comme
    a l'origine de #82) : `_regenerate_feature_with_chip` en a besoin aussi.
    Avant, elle resolvait old_cid/new_cid via `corpus_id_of_type` SEULE --
    une SECONDE autorite en desaccord avec celle-ci. Mesure : un swap de
    driver (l298n -> drv8833) y rendait `new_entry=None` malgre une entree
    corpus reelle, et la consigne envoyee au modele disait
    « stop using the L298N library » sans jamais dire d'utiliser celle du
    DRV8833 -- le defaut exact que #82 corrige ici, laisse en place la-bas
    (revue 2026-08-29)."""
    from .clarification_groups import corpus_id_of_type
    from .component_registry import by_id
    comp = by_id(t)
    if comp is not None and comp.documents:
        return comp.documents[0]
    return corpus_id_of_type(t)


def _chip_swap_regen_target(old_type: str, new_type: str) -> str | None:
    """`new_type` si remplacer `old_type` par `new_type` dans le schema oblige
    le CODE a changer : types differents ET l'un des deux mappe vers une entree
    corpus. Couvre trois sens :
      - cible a lib (SSD1306 -> SH1106) : le code doit passer a la lib du SH1106 ;
      - cible NUE mais source a lib (SSD1306 -> LED) : le code doit LACHER la
        lib du SSD1306 (sinon il pilote toujours l'ecran — divergence
        silencieuse, cf. revue 2026-07-29) ;
      - aucune lib des deux cotes mais une entree corpus quand meme (LED ->
        buzzer) : pas de librairie en jeu, mais `digitalWrite` doit devenir
        `tone()`. L'offre est utile, et c'est voulu (cf. `_has_lib`).
    None si meme type, ou si aucun des deux n'a d'entree corpus (LED -> relais :
    le cablage change, le code non).

    ⚠️ Le docstring a longtemps dit « change vraiment la LIBRAIRIE », ce que le
    code ne fait pas et n'a jamais fait. Formulation corrigee le 2026-08-10,
    apres qu'elle a failli faire « corriger » le comportement voulu.

    ⚠️ Mesure du 2026-08-29 (#82, apres le passage de `_corpus_id` par le
    REGISTRE) : sur les 217 types wiring/registre connus (`registry()` +
    `component_catalog.CATALOG` + `component_registry.
    NON_COMPONENT_WIRING_TYPES` -- ce dernier ne contient QU'`uart_module`,
    un seul type structurel, pas « quelques »), `_has_lib` bascule de False a
    True pour 104 d'entre eux -- ZERO dans l'autre sens (mesure rejouable :
    balayer ce meme ensemble, comparer `corpus_id_of_type` seul contre
    `_corpus_id`). Bien plus large que les seuls drivers du ticket : servo,
    neopixel, keypad, hx711, mpu6050, gps, pir, sd_card... La direction est
    uniforme SUR L'OFFRE (plus d'offres de regeneration, jamais moins) et
    chaque offre reste confirmee par l'utilisateur (`_confirm_regen_after_swap`)
    -- mais ce n'est PAS prouve par une suite verte, seulement par cette
    mesure : un appelant qui gate desormais sur `signature_detected`
    (`_resolve_wiring_netlist_tracked`) empeche la plupart des 104 de se
    declencher aujourd'hui, ce qui n'est pas la meme chose que « inoffensif
    partout ».

    ⚠️ « Uniforme » NE VAUT QUE POUR L'OFFRE -- pas pour ACCEPTER l'offre.
    Une fois acceptee, `_regenerate_feature_with_chip` peut bannir la lib de
    depart SANS remplacant et ce chemin est lui-meme beaucoup plus atteignable
    depuis #82 (50 -> 154 types a cid non vide, mesure separement). Trouvaille
    de revue (2026-08-29), NON CORRIGEE ICI, mesuree bout en bout : cf. le
    docstring de `_regenerate_feature_with_chip` pour le detail et pourquoi le
    correctif evident (ne jamais persister un ban sans remplacant) serait
    FAUX -- il romprait un comportement voulu depuis 2026-07-29.

    Effet de bord assume, non corrige : deux types qui partagent LE MEME
    document (ds1307/ds3231 -> rtclib, gps/gps_em406 -> tinygps-plus,
    sd_card/microsd_card_module -> sd) -- ou, pour bmp085/bmp180, deux
    documents DIFFERENTS mais la MEME bibliotheque installee
    (Adafruit_BMP085.h) -- offrent desormais une regeneration qui ne
    changera RIEN au code une fois lancee. L'offre reste correcte (elle ne
    ment pas : le CODE devrait bien etre revu), seulement inutile dans ce
    cas precis."""
    from .rag import corpus_entry

    def _has_lib(t: str) -> bool:
        # Volontairement « une entree corpus existe », PAS « elle porte un
        # arduino_lib_name ». Trois types dessinables ont une entree SANS
        # librairie (`buzzer`, `ldr`, `mq135`, mesure 2026-08-10) et doivent
        # quand meme declencher l'offre : ce qui compte est que le CODE doive
        # changer, pas qu'une lib change. Passer d'une LED a un buzzer fait
        # passer `digitalWrite` a `tone()` ; a une LDR, a `analogRead`.
        # Resserrer ce test sur `arduino_lib_name` supprimerait ces trois cas
        # en silence -- et AUCUN test ne le rattraperait (essaye le
        # 2026-08-10 : 23/23 au vert malgre la regression).
        cid = _corpus_id(t)
        return bool(cid) and corpus_entry(cid) is not None

    if not new_type or new_type == old_type:
        return None
    if _has_lib(new_type) or _has_lib(old_type):
        return new_type
    return None


def _apply_lib_overrides(forced, features) -> list[dict] | None:
    """Ré-applique les swaps de puce PERSISTÉS sur les features ciblées
    (`banned_lib_ids` / `forced_lib_ids`, cf. _regenerate_feature_with_chip)
    au forçage de libs d'une génération. Sans ce hook, un ↻ ultérieur
    recalculait le défaut RAG et la puce remplacée revenait en silence.

    Retour : la liste ajustée, ou None quand il ne reste rien à forcer.

    ⚠️ Jusqu'au #85 (2026-08-31), un ban sans remplaçant rendait une liste
    VIDE — qui supprimait TOUT le retrieval de la génération (mesuré : une
    feature servo+capteur perdait aussi le contexte du capteur), pendant que
    la lib bannie revenait quand même par le sauvetage des puces nommées de
    `_build_lib_context`. Le ban est désormais appliqué là où les libs
    s'injectent (`_banned_lib_ids` → `rag.build_lib_context(banned_libs=…)`,
    porte unique) : ici on rend None et le retrieval tourne, filtré."""
    from .rag import corpus_entry
    banned = {cid for f in features
              for cid in getattr(f, "banned_lib_ids", [])}
    forced_ids = [cid for f in features
                  for cid in getattr(f, "forced_lib_ids", [])]
    if not banned and not forced_ids:
        return forced
    out = [lib for lib in (forced or []) if lib.get("id") not in banned]
    for cid in forced_ids:
        if cid not in banned and all(lib.get("id") != cid for lib in out):
            entry = corpus_entry(cid)
            if entry is not None:
                out.append(dict(entry))
    if out:
        return out
    return None if banned else forced


def _banned_lib_ids(features) -> frozenset[str]:
    """Ids corpus bannis par les swaps persistés des features ciblées (#85).
    Transmis à `rag.build_lib_context(banned_libs=…)`, qui les écarte de
    TOUTES les portes d'injection (retrieval, sauvetage des puces nommées,
    forced résiduel) — au lieu de couper le retrieval entier comme le faisait
    la liste vide de `_apply_lib_overrides`."""
    return frozenset(cid for f in features
                     for cid in getattr(f, "banned_lib_ids", []))


# A part number: ONE word, >= 4 chars, letters AND digits (same shape as
# `registry_lookup.detect_unknown_part_tokens`). Deliberately narrow: it is
# what makes a textual substitution SAFE. Corpus keywords also hold usage
# phrases ("OLED screen", "afficher texte ecran OLED") which two entries of
# the same family SHARE -- substituting those would mangle the sentence.
_PART_NUMBER_RE = _re.compile(r"^[A-Za-z][A-Za-z0-9\-]{3,}$")


def _part_numbers(corpus_id: str) -> list[str]:
    """Part numbers advertised by a corpus entry's keywords, in order."""
    from .rag import corpus_entry
    out: list[str] = []
    for kw in (corpus_entry(corpus_id) or {}).get("keywords") or []:
        k = kw.strip()
        if " " in k or not _PART_NUMBER_RE.match(k):
            continue
        if not (any(c.isdigit() for c in k) and any(c.isalpha() for c in k)):
            continue
        if k.lower() not in (x.lower() for x in out):
            out.append(k)
    return out


def _canonical_part_number(corpus_id: str) -> str | None:
    """The one chip a corpus entry is NAMED after, or None.

    Not a tuned heuristic but a structural property: a library named after a
    chip serves that chip. Measured across the corpus --
    `sh1106` ("SH1106 OLED display (I2C)") advertises sh1106 AND sh1107 but
    is named after the first; `adafruit-bme280` advertises BME280 and its
    VMA335 alias, named after BME280. A FAMILY library names none of them:
    "DHT sensor library" covers DHT11/DHT22/DHT21/AM2302/AM2301, "NewPing"
    covers HC-SR04/SRF05 -- and returning None there is what stops a rename
    from turning a DHT11 into a DHT22.
    """
    from .rag import corpus_entry
    name = ((corpus_entry(corpus_id) or {}).get("name") or "").lower()
    if not name:
        return None
    raw = (corpus_entry(corpus_id) or {}).get("name") or ""
    hits = [p for p in _part_numbers(corpus_id) if p.lower() in name]
    if len(hits) != 1:
        return None
    # Return the form as WRITTEN IN THE NAME ("SH1106"), not the keyword's own
    # casing ("sh1106"): it lands in a sentence the user will read.
    at = name.index(hits[0].lower())
    return raw[at:at + len(hits[0])]


def _prompt_with_lib_overrides(prompt: str, features) -> str:
    """Prompt to SEND when regenerating `features`, chip swaps applied.

    Preferred form: RENAME the chip in the sentence ("... un écran OLED
    SSD1306" -> "... un écran OLED SH1106"), so the request says what the user
    now wants instead of being contradicted by a directive underneath.

    The rename only fires when it is SAFE, which is rarer than it looks
    (measured on the corpus before writing this):
      - the banned entry must advertise a part number that the prompt names;
      - exactly ONE library may be forced, and it must be NAMED after a single
        chip (`_canonical_part_number`). A family library -- "DHT sensor
        library", "NewPing" -- names none, so nothing is rewritten and a DHT11
        can never silently become a DHT22.
    Otherwise the prompt is left ALONE and the directive carries the message.

    ⚠️ For the CALLER: this is the prompt to SEND, never the visible prompt
    field -- it is an internal regeneration prompt, not something the user
    wrote (same reason as `_regenerate_feature_with_chip`).
    """
    banned = [cid for f in features
              for cid in getattr(f, "banned_lib_ids", [])]
    forced = [cid for f in features
              for cid in getattr(f, "forced_lib_ids", [])]
    renamed = False
    out = prompt
    target = _canonical_part_number(forced[0]) if len(forced) == 1 else None
    if target:
        for cid in banned:
            for tok in _part_numbers(cid):
                new, n = _re.subn(rf"\b{_re.escape(tok)}\b", target,
                                  out, flags=_re.IGNORECASE)
                if n:
                    out, renamed = new, True
    note = _lib_override_note(features, chip_renamed=renamed)
    return (out.rstrip() + "\n\n" + note) if note else out


def _lib_override_note(features, *, chip_renamed: bool = False) -> str:
    """Machine directive restating the chip swaps persisted on `features`,
    or "" when there is none.

    `chip_renamed` says the prompt itself was already corrected
    (`_prompt_with_lib_overrides`), so the directive drops the clause about
    the request still naming the old chip -- which would now be false.

    `_apply_lib_overrides` already forces the right libraries into the RAG
    context -- but the feature's STORED prompt still names the old chip
    ("... un écran OLED SSD1306"), and the model follows the prompt over the
    injected context. The swap itself worked precisely because it appended
    such a directive; the ↻ path sent the bare prompt, so the replaced chip
    came back in silence (QA B1, 2026-08-08).

    English like every other machine directive in the prompt (Serial,
    FEATURE_SUMMARY…): the user's own text stays in his language.

    ⚠️ For the CALLER: append this to the prompt SENT, never to the visible
    prompt field -- it is an internal regeneration prompt, not something the
    user wrote (same reason as `_regenerate_feature_with_chip`).
    """
    from .rag import corpus_entry

    def _names(ids) -> list[str]:
        out = []
        for cid in ids:
            entry = corpus_entry(cid)
            name = (entry or {}).get("name") or cid
            if name not in out:
                out.append(name)
        return out

    banned = _names([cid for f in features
                     for cid in getattr(f, "banned_lib_ids", [])])
    forced = _names([cid for f in features
                     for cid in getattr(f, "forced_lib_ids", [])])
    if not banned and not forced:
        return ""
    tail = ("" if chip_renamed
            else " — the component was replaced, even if the request above "
                 "still names it")
    if banned and forced:
        return (f"Use the {', '.join(forced)} library and API. "
                f"Do NOT use {', '.join(banned)}{tail}.")
    if forced:
        return f"Use the {', '.join(forced)} library and API."
    # Ban without replacement (swap towards a bare component): the directive
    # is to DROP the old library, not to adopt a new one -- inventing a
    # replacement here is exactly what we are trying to prevent.
    return f"Do NOT use {', '.join(banned)}{tail}."


def _declared_lookup_token(component) -> str:
    """Search token for a declared component. SINGLE source of truth for
    this derivation: `_declared_lookup_request` (what gets searched) and
    `_write_back_declared_lib` (which result belongs to this entry) must
    agree on the same token, or the write-back could pick a
    `RegistryLookupResult` by its position in the list instead of by the
    component it actually answers for."""
    return component.name.strip().lower()


def _declared_lookup_request(prompt: str) -> tuple[str, str] | None:
    """(search token, preferred lib) for the declared component this prompt
    names, or None.

    Module-level on purpose: testable without instantiating the view.

    The token is the entry's NAME, not a part-number: `detect_unknown_part_tokens`
    requires digits AND letters, so it would never fire on "Grove Moisture
    Sensor" — precisely the component that made that shape rule get dropped
    (spec 2026-07-30). Returns None on collision: with two entries triggered
    we would not know which one to inject nor which one to correct.
    """
    from .declared_components import match_prompt
    hit = match_prompt(prompt)
    if hit is None:
        return None
    return (_declared_lookup_token(hit), hit.lib)


def _preferred_libs_for_tokens(tokens: list[str]) -> dict[str, str]:
    """Library preferences for these lookup tokens, "" entries dropped.

    Module-level on purpose: testable without instantiating the view, same
    reason as `_declared_lookup_request`.
    """
    from .component_libs import preferred_lib_for
    out: dict[str, str] = {}
    for tok in tokens:
        lib = preferred_lib_for(tok)
        if lib:
            out[tok] = lib
    return out


def _lib_was_already_decided(r) -> bool:
    """True quand la librairie utilisée était DÉJÀ décidée pour ce token.

    « Décidée » = une préférence enregistrée (fiche déclarée qui porte sa lib,
    ou choix explicite via « Changer de librairie ») qui correspond à ce
    qui vient d'être utilisé. Dans ce cas l'app n'a rien deviné, donc la
    bannière n'a rien à annoncer.

    Volontairement STRICT sur l'égalité : si la préférence existe mais ne
    correspond pas, ce n'est pas « déjà décidé », c'est un choix contredit —
    et ça, `_preference_was_overridden` le DIT, bannière comprise. Les deux
    helpers se partagent le même `preferred_lib_for` et ne peuvent donc pas
    se contredire.

    Module-level, même raison que son voisin : testable sans vue.
    """
    from .component_libs import preferred_lib_for
    from .registry_lookup import norm_lib_name
    pref = preferred_lib_for(getattr(r, "token", ""))
    lib = getattr(r, "lib_name", "")
    return bool(pref) and norm_lib_name(pref) == norm_lib_name(lib)


def _preference_was_overridden(r) -> str:
    """The user's stored preference for this token when the generation used
    a DIFFERENT library, "" otherwise.

    One helper for two consumers -- the banner message and the button gate
    (`StudioView._apply_registry_results`). They must agree by construction:
    telling the user their choice was overridden while hiding the button that
    fixes it is worse than saying nothing.

    Module-level on purpose: testable without instantiating the view, same
    reason as `_preferred_libs_for_tokens` -- it never touched `self` to begin
    with (an earlier version wrongly carried one as a bound method).
    """
    from .component_libs import preferred_lib_for
    from .registry_lookup import norm_lib_name
    pref = preferred_lib_for(r.token)
    if pref and norm_lib_name(pref) != norm_lib_name(r.lib_name):
        return pref
    return ""


# Header of an `#include` line, whichever of the three real spellings it
# arrives in (`#include <Foo.h>`, `#include "Foo.h"`), captured WITHOUT the
# angle brackets / quotes.
_SET_MOTOR_RE = _re.compile(r"\bsetMotor\s*\(")


def stepper_code_is_driver_agnostic(code: str) -> bool:
    """True si le code pilote son moteur pas-a-pas SANS bibliotheque de
    driver -- typiquement `AccelStepper(DRIVER, STEP, DIR)`, ou du step/dir
    a la main.

    ⚠️ **Sans cette question, la fonctionnalite de swap se contredisait
    elle-meme** (mesure du 2026-08-29). Les quatre drivers sont broche-a-
    broche compatibles en step/dir, et c'est PRECISEMENT pourquoi l'app ne
    peut pas les distinguer dans le code et pourquoi l'utilisateur a besoin
    de les corriger a la main. Mais trois d'entre eux ont une bibliotheque au
    corpus (l'A4988 n'en a AUCUNE : docs=()), si bien qu'un swap A4988 ->
    DRV8825 declenchait << le code ne semble pas inclure DRV8825 >> -- vrai a
    la lettre, faux en substance : le sketch AccelStepper pilote deja un
    DRV8825 sans rien changer.

    La question est donc : le code cite-t-il la bibliotheque PROPRE d'un de
    ces drivers ? Si non, aucune bibliotheque n'est en jeu et le swap ne
    touche pas le code.

    ⚠️ **Ce predicat est NECESSAIRE au constat, pas suffisant, et la premiere
    redaction pretendait le contraire** (<< si oui, la divergence est reelle
    et le constat legitime >>). Mesure de revue, 2026-08-29 : sur le cas le
    plus probable -- code `DRV8825.h`, l'utilisateur choisit un A4988 --
    `missing_libs_for_resolved` rend `[]`, parce que l'A4988 n'a AUCUNE entree
    corpus (`documents=()`). Rendre False laisse donc seulement le constat
    POSSIBLE ; c'est le registre qui decide s'il sort. Ecrire l'inverse
    faisait promettre a ce filtre un comportement qu'il n'a pas.
    """
    from .component_registry import by_id
    from .rag import corpus_entry
    from .wiring.markers import STEPPER_DRIVERS

    bas = (code or "").lower()
    for type_id in STEPPER_DRIVERS:
        fiche = by_id(type_id)
        if fiche is None or not fiche.documents:
            continue
        doc = corpus_entry(fiche.documents[0]) or {}
        for header in (doc.get("headers") or []):
            if header and header.lower() in bas:
                return False
    return True


def _stepper_types() -> tuple[str, ...]:
    """Les drivers pas-a-pas, importes tard : `ui.wiring.markers` traine tout
    le detecteur, et ce module est deja lourd a charger."""
    from .wiring.markers import STEPPER_DRIVERS
    return STEPPER_DRIVERS


def missing_libs_for_resolved(code: str, components) -> list[tuple[str, str]]:
    """(type, nom de bibliothèque) pour chaque composant fraîchement résolu
    dont la bibliothèque n'apparaît nulle part dans le code.

    Passer une LED en servo écrit un servo dans le schéma pendant que le code
    continue de faire clignoter la broche avec `digitalWrite` — et rien ne le
    disait (question utilisateur, 2026-08-29). L'offre de régénération
    existante (`_chip_swap_regen_target`) ne peut pas couvrir ce cas : elle
    exige `signature_detected`, donc un composant LU dans le code, alors que
    la modale d'ambiguïté ne traite QUE des composants incertains.

    ⚠️ **Constat, pas verdict.** On regarde si le fichier d'en-tête est cité
    quelque part ; rien n'interdit une inclusion indirecte. D'où le « ne
    semble pas » du message, et l'absence de toute action automatique.

    ⚠️ **La correspondance type → corpus passe par le REGISTRE**, pas par
    `clarification_groups.corpus_id_of_type` : celui-ci dérive sa table des
    `ClarifyGroup`, qui excluent délibérément moteurs et servos, et répond
    donc `None` pour `servo`, `neopixel` et `dc_motor` — précisément les cas
    qu'on veut couvrir (mesuré le 2026-08-29).

    Muet, et chaque silence est voulu :
    - composant SANS bibliothèque (LED, buzzer, relais, LDR…) : il n'y a rien
      à manquer, `digitalWrite` suffit ;
    - composant DÉCLARÉ par l'utilisateur (`custom:`) : l'app ne connaît pas
      son code, l'accuser de ne pas correspondre serait une devinette ;
    - en-tête déjà présent : c'est le cas normal, on se tait.
    """
    from .component_registry import by_id
    from .declared_components import TYPE_PREFIX
    from .rag import corpus_entry

    bas = (code or "").lower()
    manquants: list[tuple[str, str]] = []
    vus: set[str] = set()
    for c in components:
        type_id = (getattr(c, "type", "") or "").strip()
        if not type_id or type_id in vus or type_id.startswith(TYPE_PREFIX):
            continue
        fiche = by_id(type_id)
        if fiche is None or not fiche.documents:
            continue
        # Seul le PREMIER document appartient au composant — même règle que
        # `lib_by_header` : les suivants sont des compagnons.
        doc = corpus_entry(fiche.documents[0])
        if not doc:
            continue
        headers = [h for h in (doc.get("headers") or []) if h]
        lib = (doc.get("arduino_lib_name") or "").strip()
        if not headers or not lib:
            continue
        if any(h.lower() in bas for h in headers):
            continue
        vus.add(type_id)
        manquants.append((type_id, lib))
    return manquants


def code_says_motor_but_none_chosen(code: str, resolved_types) -> bool:
    """Should we warn that the code drives a motor while the schematic has
    none? Honesty warning, ported from the beginner branch on 2026-08-13
    when the two modals became one -- a truth worth telling a beginner is
    worth telling everyone, and an advanced user is no better served by
    discovering the mismatch at compile time.

    Pure on purpose: the condition is the whole feature, and it is the only
    part of that warning a test can pin down.

    Fires when the sketch calls `setMotor(...)` and NOTHING the user just
    resolved came out a DC motor. Deliberately silent when:
    - a component DID come out `dc_motor` (no mismatch);
    - nothing was resolved at all (an empty list means the modal was
      cancelled or never opened -- the user made no claim to contradict);
    - a pin was resolved to a component the user DECLARED themselves
      (`custom:`). This case fired in the beginner branch and no longer
      does: someone who has just described their own hardware may well have
      described a motor driver, and the app has no ground to tell them their
      schematic has no motor. Being wrong there is worse than being quiet.
    """
    from .declared_components import TYPE_PREFIX
    types = [t for t in resolved_types if t]
    if not types or not _SET_MOTOR_RE.search(code or ""):
        return False
    if any(t == "dc_motor" for t in types):
        return False
    if any(str(t).startswith(TYPE_PREFIX) for t in types):
        return False
    return True


_INCLUDE_TOKEN_RE = _re.compile(r'#\s*include\s*[<"]([^>"]+)[>"]')


def _normalize_include(raw) -> str:
    """Basename of a header, case-folded -- whichever of the three real
    spellings it arrives in (`#include <Foo.h>`, `#include "Foo.h"`, or a
    bare `Foo.h`), and however much path precedes it. Shared by both sides
    of the comparison in `_features_using_includes` below.

    "" for anything that is not a string (not just falsy): both sides this
    function feeds ultimately trace back to a JSON file a technical user can
    hand-edit (the registry cache's `headers`, see `_after_lib_preference_changed`),
    so a stray number or null in that list must normalize away quietly rather
    than crash the caller -- especially since the click handler that reads it
    runs AFTER the preference write has already landed on disk (there is no
    "abort the write" to fall back to)."""
    if not isinstance(raw, str):
        return ""
    text = raw.strip()
    m = _INCLUDE_TOKEN_RE.search(text)
    if m:
        text = m.group(1)
    text = text.replace("\\", "/").rsplit("/", 1)[-1]
    return text.strip().lower()


def _features_using_includes(features, includes: list[str]) -> set[str]:
    """Ids of the features whose code includes one of these headers.

    Matching is on the HEADER FILE, never the library name: the library name
    does not appear in the generated code at all, and two libraries for the
    same chip routinely ship the same include. Case and folder are ignored --
    includes round-trip through the feature model and the lookup cache, and a
    spelling difference must not silently skip a regeneration.

    Module-level on purpose: testable without instantiating the view.
    """
    wanted = {_normalize_include(h) for h in includes}
    wanted.discard("")
    if not wanted:
        return set()
    out: set[str] = set()
    for f in features:
        for inc in f.includes:
            if _normalize_include(inc) in wanted:
                out.add(f.id)
                break
    return out


def _write_back_declared_lib(prompt: str, results: list) -> None:
    """Records on the declared entry the library the registry just resolved,
    plus its REAL `#include`s — which later serve as the attachment key for
    wiring. Without this, the result would be thrown away and the card would
    stay on "library unknown" forever.

    Does nothing if the prompt does not name exactly one declared entry.
    Does nothing either if no result carries THIS entry's own token: a
    prompt can legitimately also name an unrelated unknown part (task 5
    adds the declared token to `unknown`, it does not replace it), so
    `results` may hold several entries — picking "the first one with an
    `.entry`" would silently attach a different chip's library, exactly the
    substitution this whole pipeline exists to prevent. Better to write
    nothing than to write something that belongs to another component.
    """
    from .declared_components import (library_file_unusable, load,
                                     match_prompt, normalize_header, save,
                                     set_registry, upsert)
    hit = match_prompt(prompt)
    if hit is None:
        return
    if library_file_unusable():
        # Same protection as the form's `_on_save`: components.json exists but
        # this build cannot parse it, so `load()` degrades to [] on purpose and
        # saving would replace the whole library with this single entry.
        # Unreachable today only because an unreadable file yields an empty
        # registry -- that is an implicit invariant, not a check, and the
        # second write path must carry the first one's guard (2026-07-30
        # review). Silent here rather than a dialog: this runs mid-generation,
        # and the form already warns whenever the user is the one writing.
        return
    wanted = _declared_lookup_token(hit)
    found = next((r for r in results
                  if getattr(r, "token", None) == wanted
                  and getattr(r, "entry", None) is not None), None)
    if found is None:
        return
    lib = str(found.entry.get("arduino_lib_name")
              or getattr(found, "lib_name", "") or "").strip()
    heads = tuple(normalize_header(h)
                  for h in (found.entry.get("headers") or []))
    if not lib and not heads:
        return
    updated = replace(hit, lib=hit.lib or lib,
                      headers=tuple(dict.fromkeys((*hit.headers, *heads))))
    items = upsert(load(), updated)
    save(items)
    set_registry(items)


# ── Arduino code parsing/merging helpers ─────────────────────────────────────

def _strip_fences(code: str) -> str:
    """Remove Markdown ```cpp ... ``` fences if present."""
    code = code.strip()
    if code.startswith('```'):
        lines = code.splitlines()
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == '```':
                end = i
                break
        code = '\n'.join(lines[1:end]).strip()
    return code


def _find_function(code: str, name: str):
    """
    Locate a void function by its name.
    Returns (func_start, body_start, body_end) or None.
    body_start: index after '{'; body_end: index of the closing '}'.
    """
    m = _re.search(rf'\bvoid\s+{name}\s*\(\s*\)', code)
    if not m:
        return None
    brace = code.find('{', m.end())
    if brace == -1:
        return None
    depth = 0
    for i in range(brace, len(code)):
        if code[i] == '{':
            depth += 1
        elif code[i] == '}':
            depth -= 1
            if depth == 0:
                return (m.start(), brace + 1, i)
    return None


def _reindent(body: str, indent: str = '  ') -> list:
    """De-indent the body to the minimum, then re-indent with `indent`."""
    lines = body.splitlines()
    non_empty = [l for l in lines if l.strip()]
    if not non_empty:
        return []
    min_ind = min(len(l) - len(l.lstrip()) for l in non_empty)
    return [indent + l[min_ind:] if l.strip() else '' for l in lines]


def _merge_generated_code(existing: str, generated: str) -> str:
    """
    Merge the AI-generated code into the existing template structure.
    - Keeps the header comments and the setup/loop structure.
    - Injects includes/globals, setup body, loop body and extra functions
      at the right places without overwriting the existing content.
    """
    generated = _strip_fences(generated)

    gen_setup = _find_function(generated, 'setup')
    gen_loop  = _find_function(generated, 'loop')
    ex_setup  = _find_function(existing,  'setup')
    ex_loop   = _find_function(existing,  'loop')

    if ex_setup is None or ex_loop is None:
        return generated

    gen_setup_body = generated[gen_setup[1]:gen_setup[2]].strip() if gen_setup else ''
    gen_loop_body  = generated[gen_loop[1]:gen_loop[2]].strip()   if gen_loop  else ''
    gen_extra      = generated[gen_loop[2] + 1:].strip()          if gen_loop  else ''
    gen_pre        = generated[:gen_setup[0]].strip()              if gen_setup else generated.strip()

    ex_setup_body  = existing[ex_setup[1]:ex_setup[2]].strip()
    ex_loop_body   = existing[ex_loop[1]:ex_loop[2]].strip()
    ex_extra       = existing[ex_loop[2] + 1:].strip()

    parts = []

    # Header: comments + any existing globals
    parts.append(existing[:ex_setup[0]].rstrip())
    if gen_pre:
        parts.append(gen_pre)
    parts.append('')

    # setup()
    parts.append('void setup() {')
    if ex_setup_body:
        parts.extend(_reindent(ex_setup_body))
    if gen_setup_body:
        if ex_setup_body:
            parts.append('')
        parts.extend(_reindent(gen_setup_body))
    parts.append('}')
    parts.append('')

    # loop()
    parts.append('void loop() {')
    if ex_loop_body:
        parts.extend(_reindent(ex_loop_body))
    if gen_loop_body:
        if ex_loop_body:
            parts.append('')
        parts.extend(_reindent(gen_loop_body))
    parts.append('}')

    if ex_extra:
        parts.append('')
        parts.append(ex_extra)
    if gen_extra:
        parts.append('')
        parts.append(gen_extra)

    return '\n'.join(parts)


def _append_extra(existing: str, new_code: str) -> str:
    """Appends new function(s) from new_code after loop() in existing code."""
    new_code = _strip_fences(new_code)
    gen_loop  = _find_function(new_code, 'loop')
    gen_setup = _find_function(new_code, 'setup')
    if gen_loop:
        extra = new_code[gen_loop[2] + 1:].strip()
    elif gen_setup:
        extra = new_code[gen_setup[2] + 1:].strip()
    else:
        extra = new_code.strip()
    if not extra:
        return existing
    ex_loop = _find_function(existing, 'loop')
    if ex_loop is None:
        return existing + '\n\n' + extra
    after_loop = existing[ex_loop[2] + 1:].strip()
    base = existing[:ex_loop[2] + 1]
    if after_loop:
        return base + '\n\n' + after_loop + '\n\n' + extra
    return base + '\n\n' + extra


from .board_manager import board_manager, BOARDS, get_fqbn, BoardState
from . import arduino_cli


def _strip_line_comments(line: str, in_block: bool) -> tuple[str, bool]:
    """Strip C/C++ comments from a line.

    Returns (line_without_comments, in_block_after). The `in_block` flag
    allows chaining across several lines to handle multi-line `/* ... */`
    blocks. The contents of strings ("...") and char literals ('...')
    are preserved: a `//` inside a string does not open a comment.
    """
    out: list[str] = []
    in_string = False
    in_char = False
    j = 0
    n = len(line)
    while j < n:
        c = line[j]
        if in_block:
            if c == '*' and j + 1 < n and line[j + 1] == '/':
                in_block = False
                j += 2
                continue
            j += 1
            continue
        if in_string:
            if c == '\\' and j + 1 < n:
                out.append(c); out.append(line[j + 1]); j += 2; continue
            if c == '"':
                in_string = False
            out.append(c); j += 1; continue
        if in_char:
            if c == '\\' and j + 1 < n:
                out.append(c); out.append(line[j + 1]); j += 2; continue
            if c == "'":
                in_char = False
            out.append(c); j += 1; continue
        # Normal mode
        if c == '"':
            in_string = True; out.append(c); j += 1; continue
        if c == "'":
            in_char = True; out.append(c); j += 1; continue
        if c == '/' and j + 1 < n:
            if line[j + 1] == '/':
                # End-of-line comment: stop here.
                break
            if line[j + 1] == '*':
                in_block = True
                j += 2
                continue
        out.append(c); j += 1
    return ''.join(out), in_block


def _strip_comments(code: str) -> str:
    """Strip all C/C++ comments from the code.

    - `// end of line`: removes up to the end (the preceding code stays).
    - `/* ... */` single-line or multi-line: removes that portion.
    - A line that became empty after stripping AND that originally
      contained a comment is removed entirely (no phantom blank in
      the copied/pasted code).
    - Original blank lines are preserved (intentional separators).
    """
    out_lines: list[str] = []
    in_block = False
    for raw in code.splitlines():
        original_was_blank = not raw.strip()
        stripped, in_block = _strip_line_comments(raw, in_block)
        stripped = stripped.rstrip()
        if not stripped:
            if original_was_blank:
                out_lines.append("")
            # otherwise: 100% comment line → removed
        else:
            out_lines.append(stripped)
    trailing = '\n' if code.endswith('\n') else ''
    return '\n'.join(out_lines) + trailing


def _map_lines_strip_comments(old_full: str) -> dict[int, int]:
    """Map each line of `old_full` to its index in `_strip_comments(old_full)`.

    Exact mirror of `_strip_comments` — no heuristic diff: a line is
    preserved if its stripped content is non-empty OR if it was blank
    originally, otherwise it is removed and has no entry.

    Used by the "Show comments" toggle to remap the tracker's
    ownerships without going through difflib (which fails when a
    block mixes declarations with an inline comment + pure comments and
    produces a replace with differing cardinalities).
    """
    mapping: dict[int, int] = {}
    in_block = False
    new_idx = 0
    for old_idx, raw in enumerate(old_full.splitlines()):
        original_was_blank = not raw.strip()
        stripped_line, in_block = _strip_line_comments(raw, in_block)
        stripped_line = stripped_line.rstrip()
        if stripped_line or original_was_blank:
            mapping[old_idx] = new_idx
            new_idx += 1
    return mapping


def _split_into_comment_groups(full_code: str) -> list[list[str]]:
    """Split `full_code` into consecutive groups.

    Each group = list of lines ending with ONE "preserved" line
    (code line OR original blank line — those that `_strip_comments`
    keeps), preceded by the 100% comment lines attached to it.
    The number of groups equals the number of lines of `_strip_comments(full)`.

    Used to re-inject comments after an edit in stripped mode:
    each comment is attached to the code line that follows it, and that
    association is recovered via the indices.
    """
    lines = full_code.splitlines()
    groups: list[list[str]] = []
    buffer: list[str] = []
    in_block = False
    for raw in lines:
        original_was_blank = not raw.strip()
        stripped_line, in_block = _strip_line_comments(raw, in_block)
        stripped_line = stripped_line.rstrip()
        if not stripped_line and not original_was_blank:
            # 100% comment line (potentially multi-line)
            buffer.append(raw)
        else:
            # Preserved line: close the group.
            groups.append(buffer + [raw])
            buffer = []
    if buffer:
        # Trailing comments (after the last preserved line):
        # attach them to the last group so they are not lost.
        if groups:
            groups[-1].extend(buffer)
        else:
            groups = [buffer]
    return groups


def _restore_comments_after_edits(old_full: str, old_stripped: str,
                                  new_stripped: str) -> str:
    """Re-inject the comments of `old_full` into `new_stripped`.

    Uses a `difflib.SequenceMatcher` diff between `old_stripped` and
    `new_stripped` to identify the unchanged blocks (which keep the
    corresponding comments from `old_full`) and the modified blocks
    (which take the raw lines of `new_stripped` without comments).

    Special case: a `replace` of the same cardinality (renaming a
    variable in a line, changing a constant, etc.) keeps the
    surrounding comments by replacing only the preserved line.
    """
    if old_stripped == new_stripped:
        return old_full
    import difflib
    old_groups = _split_into_comment_groups(old_full)
    old_lines = old_stripped.splitlines()
    new_lines = new_stripped.splitlines()
    # Sanity: if the invariant len(groups) == len(old_stripped.splitlines())
    # is broken (degenerate case), fall back to "loses the comments" mode.
    if len(old_groups) != len(old_lines):
        return new_stripped
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    out: list[str] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == 'equal':
            for k in range(i1, i2):
                out.extend(old_groups[k])
        elif op == 'replace' and (i2 - i1) == (j2 - j1):
            # Same cardinality: keep the comments of the groups
            # and replace only the preserved line (the last of the group).
            for offset in range(i2 - i1):
                group = old_groups[i1 + offset]
                out.extend(group[:-1])
                out.append(new_lines[j1 + offset])
        else:
            # delete (j1==j2, adds nothing), insert (i1==i2), or replace
            # with differing cardinality: lose the comments of this
            # zone, take the raw lines of the new stripped.
            for k in range(j1, j2):
                out.append(new_lines[k])
    trailing = '\n' if old_full.endswith('\n') or new_stripped.endswith('\n') else ''
    return '\n'.join(out) + trailing


def _map_lines_by_diff(old_code: str, new_code: str) -> dict[int, int]:
    """Map old_line_idx -> new_line_idx via `SequenceMatcher`, tolerant
    to content modifications (not only to pure insertions).

    - `equal` block  → 1-to-1 mapping position by position;
    - `replace` block of the SAME cardinality → 1-to-1 mapping position by
      position (the line was rewritten in place, preserve the
      ownership of the function that owned it);
    - asymmetric `insert` / `delete` / `replace` block → lost lines
      (no entry in the mapping, the function loses those lines).

    Used by the `repair_code` tool which is allowed to restructure,
    unlike `add_comments` (simple insertions) which keeps its own
    stricter `_map_lines_after_insertions`.
    """
    import difflib
    old_lines = old_code.splitlines()
    new_lines = new_code.splitlines()
    mapping: dict[int, int] = {}
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == 'equal' or (op == 'replace' and (i2 - i1) == (j2 - j1)):
            for offset in range(i2 - i1):
                mapping[i1 + offset] = j1 + offset
    return mapping


def _map_lines_after_insertions(old_code: str, new_code: str) -> dict[int, int]:
    """Map each line index of `old_code` to its new index in
    `new_code`, under the assumption that `new_code` only INSERTS
    lines (comments) without modifying or reordering the existing content.

    Algorithm: walk in parallel through both lists; for each
    old line, advance in new_code until finding a line
    whose `strip()` is identical. Empty lines match each
    other. An old line that cannot be found (the AI drifted from the contract) is
    omitted from the mapping — the associated function will lose that line.

    Used by the "Add pedagogical comments" tool to
    preserve the tracker's ownerships after replacing the code.
    """
    old_lines = old_code.splitlines()
    new_lines = new_code.splitlines()
    mapping: dict[int, int] = {}
    j = 0
    for i, old in enumerate(old_lines):
        old_s = old.strip()
        while j < len(new_lines):
            if new_lines[j].strip() == old_s:
                mapping[i] = j
                j += 1
                break
            j += 1
    return mapping


def _find_scaffolding_lines(code: str) -> set[int]:
    """Identify the 0-indexed lines that form the neutral scaffolding.

    Scaffolding = `void setup()` / `void loop()` signatures + their
    corresponding opening and closing braces. The INNER content of these blocks
    is NOT included — that content belongs to the user function.

    Used by the 1st generation (Q2b of the roadmap): when creating the
    first Function, it should own all lines EXCEPT the
    scaffolding.
    """
    lines = code.splitlines()
    scaffold: set[int] = set()
    i = 0
    n = len(lines)
    sig_re = _re.compile(r'^\s*void\s+(setup|loop)\s*\(\s*\)\s*\{?\s*$')
    while i < n:
        if sig_re.match(lines[i]):
            scaffold.add(i)
            # opening brace potentially on the next line
            depth = lines[i].count('{') - lines[i].count('}')
            j = i
            while depth == 0 and j + 1 < n and '{' not in lines[j]:
                j += 1
                scaffold.add(j)
                depth += lines[j].count('{') - lines[j].count('}')
            # find the closing brace that brings depth back to 0
            while j + 1 < n and depth > 0:
                j += 1
                depth += lines[j].count('{') - lines[j].count('}')
                if depth == 0:
                    scaffold.add(j)
                    break
            i = j + 1
        else:
            i += 1
    return scaffold


# Arduino lines manipulated by the "Moniteur série" checkbox (Advanced mode).
# `Serial` with a left boundary to avoid matching mySerial/SoftwareSerial,
# `.begin(|print(|println(` with an opening parenthesis to avoid breaking a
# creative symbol name. The (kind) group is used to tell begin from a print.
_SERIAL_STMT_RE = _re.compile(
    r'(?<![A-Za-z0-9_])Serial\s*\.\s*(begin|print|println)\s*\('
)
_SERIAL_COMMENTED_RE = _re.compile(
    r'^(\s*)//\s*((?:Serial\s*\.\s*(?:begin|print|println)\s*\().*)$'
)
# Name of the functions to comment/uncomment (without Serial itself).
_SERIAL_COMMENT_MARK = "// "

# `_wiring_resolutions` key prefix for a "declared-component opt-out": the
# user picked a DIFFERENT type than their library's declaration for a given
# `#include` header, via the gear. Stored as `("", DECLARED_OPTOUT_PREFIX +
# normalized_header)` -> chosen type_id, reusing `_wiring_resolutions` (and
# its existing persistence / serialization) rather than adding new plumbing.
# Net-keyed resolutions cannot express this: a placeholder's net is empty by
# construction, so its normal `_resolution_key_for` key degenerates to
# `(fn_id, "")`, which `_already_resolved_refs` deliberately never trusts
# (see its docstring) -- the header is the only stable handle available.
_DECLARED_OPTOUT_PREFIX = "declared_optout::"


def _comment_out_serial(code: str) -> str:
    """Comment out all lines containing `Serial.(begin|print|println)(...)`.

    Does not touch lines already commented (// ... Serial...) nor matches
    inside a /* ... */ block. Preserves indentation by inserting the
    `// ` right after the leading spaces/tabs.
    """
    out_lines: list[str] = []
    in_block_comment = False
    for raw in code.splitlines(keepends=False):
        line = raw
        if in_block_comment:
            if '*/' in line:
                in_block_comment = False
            out_lines.append(line)
            continue
        # Detect a /* that is not closed on the same line.
        if '/*' in line and '*/' not in line.split('/*', 1)[1]:
            in_block_comment = True
            out_lines.append(line)
            continue
        stripped = line.lstrip()
        # Line already commented inline (// ...): leave it as-is.
        if stripped.startswith('//'):
            out_lines.append(line)
            continue
        if _SERIAL_STMT_RE.search(line):
            indent_len = len(line) - len(stripped)
            indent = line[:indent_len]
            out_lines.append(f"{indent}{_SERIAL_COMMENT_MARK}{stripped}")
        else:
            out_lines.append(line)
    return '\n'.join(out_lines) + ('\n' if code.endswith('\n') else '')


def _uncomment_serial(code: str) -> str:
    """Uncomment lines of the form `// Serial.(begin|print|println)(...)`.

    Uncomments ONLY if the commented code is exactly a Serial call — so it
    does not touch a user comment like "// uses Serial".
    """
    out_lines: list[str] = []
    for raw in code.splitlines(keepends=False):
        m = _SERIAL_COMMENTED_RE.match(raw)
        if m:
            out_lines.append(f"{m.group(1)}{m.group(2)}")
        else:
            out_lines.append(raw)
    return '\n'.join(out_lines) + ('\n' if code.endswith('\n') else '')


# Watchdog << la generation prend plus de temps que prevu >> (TODO #24).
# NE TUE RIEN : deux messages non bloquants dans le journal, c'est tout.
#
# ⚠️ 300 s N'EST PAS UN NOMBRE ROND CHOISI AU HASARD : c'est EXACTEMENT le
# delai qui tuait la generation avant ce ticket (`_CLI_TIMEOUT` de claude_code,
# `_TIMEOUT_GEN` d'ollama). A la seconde ou l'utilisateur perdait tout, il lit
# desormais que sa generation continue. Ne pas << arrondir >> ces valeurs sans
# savoir ce que la seconde d'entre elles commemore.
_GEN_SLOW_SOFT_MS = 120_000
_GEN_SLOW_HARD_MS = 300_000

_PROMPT_H = 80
_OUTPUT_H = 110

# « Coulisses du prompt » (#42). When on, the 4 generation flows (Regenerate /
# Add / Modify via the single button + the beginner Generate-and-upload) show
# what is really sent BEFORE sending it, and let the user validate or cancel.
#
# It replaces a module-level `_DEBUG_SHOW_PROMPT` flag driven by a Help-menu
# checkbox that reset on every launch. Two things were wrong with it: the state
# now lives in `session` (a preference nobody wants to re-tick at each launch),
# and the modal was a dead end — it returned before the backend, so seeing the
# prompt and generating were mutually exclusive.
#
# Sentinel rather than None: the validated message CAN legitimately be empty
# (the user cleared the pane), and an empty string must not read as "cancelled".
_BACKSTAGE_CANCELLED = object()


def debug_show_prompt_enabled() -> bool:
    """Current state of « Coulisses du prompt ». Kept under its historical
    name for the callers that only ask the question."""
    return session.prompt_backstage


def set_debug_show_prompt(enabled: bool) -> None:
    """Enable/disable « Coulisses du prompt ». Persisted, unlike the dev
    toggle it replaces."""
    session.prompt_backstage = bool(enabled)


# ── Génération IA (worker + aperçu de prompt) ─────────────────────────────────
# Déménagés dans ui/studio/generation_flow.py (Prompt 4, 1re tranche) ;
# alias de compat ci-dessous pour les sites appelants du studio.


# ── Pedagogical log widget ────────────────────────────────────────────────────
# (couleurs de phases : PHASE_COLORS, déménagé dans ui/studio/compile_service)


class _GridBackground(QWidget):
    """Background of the Studio content area: flat main_bg + subtle
    millimeter grid painted with QPainter (spec §5 — QSS can't do a grid).
    Lines every 24 px; per-theme dedicated gray -> visible but discreet in light
    as in dark (LIGHT gray on white background, DARK gray on dark background).
    """
    _STEP = 24
    _GRID_DARK = QColor("#191e29")    # discreet dark gray on main_bg (#10141d)
    _GRID_LIGHT = QColor("#f1f2f5")   # very light gray, barely marked on white

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg = QColor(theme_manager.current.main_bg)
        self._line = self._grid_color()

    def _grid_color(self) -> QColor:
        return self._GRID_DARK if theme_manager.is_dark else self._GRID_LIGHT

    def set_bg(self, hex_color: str):
        self._bg = QColor(hex_color)
        self._line = self._grid_color()   # recomputed on theme change
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg)
        p.setPen(self._line)
        w, h = self.width(), self.height()
        x = self._STEP
        while x < w:
            p.drawLine(x, 0, x, h)
            x += self._STEP
        y = self._STEP
        while y < h:
            p.drawLine(0, y, w, y)
            y += self._STEP
        p.end()


class _ElidingLabel(QLabel):
    """QLabel that displays its full text when there is room, and elides
    it (« … ») when space is lacking — WITHOUT forcing the minimum width of its
    parent (minimumSizeHint width set back to 0).

    Used for section titles and the comments slider label: otherwise
    their width (long text, e.g. « _GÉNÉRER UNE FONCTIONNALITÉ ») prevents the code
    area from shrinking when the chat AND the sidebar are open at the same time,
    and the right column (buttons + log) ends up clipped."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._full_text = text

    def setText(self, text: str):
        self._full_text = text
        self._elide()

    def text(self) -> str:           # returns the logical text, not the elided one
        return self._full_text

    def minimumSizeHint(self) -> QSize:
        # Normal height, but min width 0: the label no longer blocks the layout.
        return QSize(0, super().minimumSizeHint().height())

    def sizeHint(self) -> QSize:
        # Preferred size = that of the FULL TEXT (otherwise, once elided, the
        # sizeHint would shrink to the truncated text and the label would stay small even
        # when the room comes back).
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self._full_text) + 2,
                     super().sizeHint().height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def _elide(self):
        fm = self.fontMetrics()
        if fm.horizontalAdvance(self._full_text) <= self.width():
            super().setText(self._full_text)
            self.setToolTip("")
        else:
            super().setText(fm.elidedText(
                self._full_text, Qt.TextElideMode.ElideRight, max(0, self.width())))
            self.setToolTip(self._full_text)   # full text on hover if truncated


# Accepted extensions for the shared context file (prompt + chat).
# Union of the old studio set (.md/.txt) and the chat one (code/log/csv):
# the context file is now common to both areas, so any readable
# text must be accepted regardless of the drop zone.
_CONTEXT_EXTS = (".md", ".txt", ".ino", ".cpp", ".c", ".h", ".csv", ".log")

# Max width of the file name in the context badge (px) -> truncation …
_BADGE_LABEL_MAX_W = 140


class _PromptTextEdit(QPlainTextEdit):
    """AI prompt QPlainTextEdit with context file drop.

    Emits `file_dropped(path, supported)` when the user drops a
    single local file. `supported` is True for the extensions in
    `_CONTEXT_EXTS`, False otherwise — StudioView validates and displays a
    suitable error message. Other drops (text, multi-files, non-local URL)
    fall back to the native QPlainTextEdit behavior.
    """
    file_dropped = pyqtSignal(str, bool)
    submit_requested = pyqtSignal()   # Enter (without Shift) -> starts generation

    _ACCEPTED_EXTS = _CONTEXT_EXTS

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._overlay_btn = None
        self._overlay_left = None   # widget anchored just to the left of the button

    def focusInEvent(self, event):
        super().focusInEvent(event)
        # Click (or Tab) in an ALREADY FILLED field -> select all to
        # replace the text at once. Deferred via QTimer(0): the click
        # first positions the cursor (which would deselect), our
        # selectAll runs AFTER. Subsequent clicks (field already focused) do
        # not re-fire focusInEvent -> position the cursor normally.
        if (event.reason() in (
                Qt.FocusReason.MouseFocusReason,
                Qt.FocusReason.TabFocusReason,
                Qt.FocusReason.BacktabFocusReason)
                and self.toPlainText().strip()):
            QTimer.singleShot(0, self.selectAll)

    def set_overlay_button(self, btn) -> None:
        """Anchor a floating button at the bottom-right of the field (+ Attach, spec §4
        option B: child of the field, repositioned on resizeEvent)."""
        self._overlay_btn = btn
        btn.setParent(self)
        self._reposition_overlay()
        btn.show()

    def set_overlay_left(self, widget) -> None:
        """Anchor a widget (file chip) just to the LEFT of the overlay button. Its
        visibility is managed by the widget itself; we only place it."""
        self._overlay_left = widget
        widget.setParent(self)
        self._reposition_overlay()

    def _reposition_overlay(self) -> None:
        b = self._overlay_btn
        if b is None:
            return
        m = 8
        b.adjustSize()
        b.move(self.width() - b.width() - m, self.height() - b.height() - m)
        b.raise_()
        # File chip stuck to the left of the button, vertically centered ON the
        # button (different heights -> bottom alignment misaligns).
        lw = self._overlay_left
        if lw is not None:
            gap = 6
            lw.adjustSize()
            lw.move(max(m, b.x() - gap - lw.width()),
                    b.y() + (b.height() - lw.height()) // 2)
            lw.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_overlay()

    def _single_local_file(self, event) -> Path | None:
        md = event.mimeData()
        if not md.hasUrls():
            return None
        urls = md.urls()
        if len(urls) != 1:
            return None
        u = urls[0]
        if not u.isLocalFile():
            return None
        return Path(u.toLocalFile())

    def dragEnterEvent(self, event):
        if self._single_local_file(event) is not None:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._single_local_file(event) is not None:
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        p = self._single_local_file(event)
        if p is not None:
            event.acceptProposedAction()
            supported = p.suffix.lower() in self._ACCEPTED_EXTS
            self.file_dropped.emit(str(p), supported)
            return
        super().dropEvent(event)

    def keyPressEvent(self, event):
        # Enter (without Shift) starts generation; Shift+Enter = new line.
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
            self.submit_requested.emit()
            return
        super().keyPressEvent(event)


# ── "Context" badge (always visible above the prompt) ────────────────────────

class _ContextBadge(QWidget):
    """Small info line above the prompt, always visible.

    Two states:
      - Empty: + icon and label "Ajouter un fichier de contexte (.md/.txt)".
        Click on the + or on the label => emits add_clicked (StudioView then
        opens a QFileDialog).
      - Filled: label "Contexte : hardware.md (342 car.)" + × button.
        Click on × => emits remove_clicked.
    """
    add_clicked    = pyqtSignal()
    remove_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(8)

        # + icon (empty mode) — same dimension as the cross for a
        # balanced rendering.
        self._btn_add = QPushButton()
        self._btn_add.setFixedSize(18, 18)
        self._btn_add.setIconSize(QSize(14, 14))
        self._btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_add.setFlat(True)
        self._btn_add.clicked.connect(self.add_clicked.emit)
        row.addWidget(self._btn_add, 0, Qt.AlignmentFlag.AlignVCenter)

        # Document icon before the file name (filled mode only).
        # QLabel + pixmap rather than QPushButton to avoid adding
        # unwanted interactivity — it is just a decorative glyph.
        self._file_icon = QLabel()
        self._file_icon.setFixedSize(14, 14)
        self._file_icon.setScaledContents(True)
        row.addWidget(self._file_icon, 0, Qt.AlignmentFlag.AlignVCenter)

        # Label common to both modes. Clickable in empty mode only.
        # No stretch here: the label takes its natural width so that
        # the × button sticks right after the file name.
        self._lbl = QLabel()
        self._lbl.setWordWrap(False)
        self._lbl.mousePressEvent = self._on_label_clicked
        row.addWidget(self._lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        # × button: same size as the +, for a symmetric rendering and a
        # crisp cross (12px inside an 18px looked asymmetric
        # to the eye — lucide's round line-caps truncate visually).
        self._btn_remove = QPushButton()
        self._btn_remove.setFixedSize(18, 18)
        self._btn_remove.setIconSize(QSize(14, 14))
        self._btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_remove.setFlat(True)
        self._btn_remove.clicked.connect(self.remove_clicked.emit)
        row.addWidget(self._btn_remove, 0, Qt.AlignmentFlag.AlignVCenter)

        # Push all content to the left — without this stretch, the layout
        # would center/stretch the elements.
        row.addStretch(1)

        self._has_context = False
        self.clear_info()
        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self._on_lang_changed)

    def _on_label_clicked(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and not self._has_context):
            self.add_clicked.emit()

    def _on_lang_changed(self, _):
        # Refresh the label when the language changes: only the empty mode
        # has a fixed label, the filled mode is refreshed by set_info
        # on each project update.
        if not self._has_context:
            self.clear_info()

    def set_info(self, name: str):
        """Filled mode: file name truncated (…) to a max width (full
        name in the tooltip), without prefix or counter."""
        from PyQt6.QtGui import QFontMetrics
        s = lang_manager.current
        fm = QFontMetrics(self._lbl.font())
        self._lbl.setText(
            fm.elidedText(name, Qt.TextElideMode.ElideRight, _BADGE_LABEL_MAX_W))
        self._lbl.setToolTip(name)
        self._btn_remove.setToolTip(s.studio_context_remove)
        self._btn_remove.setVisible(True)
        self._btn_add.setVisible(False)
        self._file_icon.setVisible(True)
        self._lbl.setCursor(Qt.CursorShape.ArrowCursor)
        self._has_context = True
        self.setVisible(True)   # filled -> show the attached file

    def clear_info(self):
        # Empty state: the badge is entirely HIDDEN (the « + Ajouter un
        # fichier de contexte » hint is redundant with the « + Joindre » button of the
        # prompt field). It only reappears once a file is attached.
        s = lang_manager.current
        self._lbl.setText(s.studio_context_add_hint)
        self._btn_add.setToolTip(s.studio_context_add_tooltip)
        self._btn_remove.setVisible(False)
        self._btn_add.setVisible(True)
        self._file_icon.setVisible(False)
        self._lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._has_context = False
        self.setVisible(False)

    def apply_theme(self, c: ColorScheme):
        # Global QSS of the widget + its children: avoid QPalette to avoid
        # the classic conflict with the border rules applied in QSS.
        # Subtle background + softened border, label font-size aligned on the
        # app's standard sizes (9pt).
        self.setStyleSheet(f"""
            _ContextBadge {{
                background-color: {c.surface};
                border: 1px solid {c.border};
                border-radius: 6px;
            }}
            QLabel {{
                background-color: transparent;
                color: {c.text_primary};
            }}
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 9px;
            }}
            QPushButton:hover {{
                background-color: {c.border};
            }}
        """)
        # Reduced file name font + bounded width (truncation handled
        # in set_info). setFont (not QSS font-size) so that QFontMetrics
        # measures the real rendered size during elision.
        lbl_font = self._lbl.font()
        lbl_font.setPixelSize(10)
        self._lbl.setFont(lbl_font)
        self._lbl.setMaximumWidth(_BADGE_LABEL_MAX_W)
        # Lucide icons rendered in the secondary color by default; hover
        # handled by the QSS above (background that lights up).
        self._btn_add.setIcon(IC.make_icon(IC.PLUS, c.text_secondary, 14))
        self._btn_remove.setIcon(IC.make_icon(IC.X_ICON, c.text_secondary, 14))
        self._file_icon.setPixmap(
            IC.make_icon(IC.FILE_TEXT, c.text_secondary, 14).pixmap(14, 14)
        )


# ── Main view ─────────────────────────────────────────────────────────────────

class StudioView(QWidget):

    projects_tab_requested = pyqtSignal()
    project_created        = pyqtSignal(object)   # emits the Project created from the Studio
    project_renamed        = pyqtSignal(str, object)  # (old_path, renamed Project)
    project_title_changed  = pyqtSignal(str)   # name of the current project ("" if none)
    project_loaded         = pyqtSignal(object)   # loaded Project (or None)
    chat_context_changed   = pyqtSignal(dict)     # code+prompt+wiring payload to ChatView
    chat_help_requested    = pyqtSignal(str, str)   # prefix_text, system_extras
    wrong_component_help_requested = pyqtSignal(str, str, object)  # prefix, extras, ctx
    # TODO #49 : une exception non rattrapee a ete signalee. Le signal existe
    # POUR le changement de thread — `threading.excepthook` s'execute dans le
    # thread fautif, et toucher un widget depuis la ne serait pas sur.
    unhandled_exception_reported = pyqtSignal()

    def __init__(self, parent=None, mode_selector: "ModeSelector | None" = None):
        super().__init__(parent)
        # The mode selector now lives in the topbar — we receive a
        # shared reference. If none is provided (e.g. unit tests), we
        # create a local one as a fallback.
        self._mode_selector_external = mode_selector is not None
        self._mode_selector = mode_selector if mode_selector is not None else ModeSelector()
        self._gen_worker: _GenerateWorker | None = None
        # Minuteries du watchdog << plus long que prevu >> (#24), creees a la
        # premiere generation par `_install_gen_slow_watchdog`.
        self._gen_slow_soft_timer = None
        self._gen_slow_hard_timer = None
        # Workers de generation ANNULES qui n'ont pas encore rendu la main.
        # Garder la reference evite un GC pendant que le thread tourne — cf.
        # `_detach_gen_worker`, qui explique pourquoi ils ne sont pas recoltes.
        self._detached_gen_workers: list = []
        self._registry_worker = None   # lookup registre Arduino (hors-corpus)
        self._cu_worker:  arduino_cli.CompileUploadWorker | None = None
        self._cu_running: bool = False
        # Restauration du bouton actif (IA ou stable) — appelée à l'annulation
        # pour restaurer le BON bouton synchroniquement (les deux fenêtres
        # partagent la garde _cu_running).
        self._cu_active_restore = None
        self._beginner_running: bool = False
        # #12: UNIFIED generation state across modes. None = no
        # generation; "advanced" = inter/advanced generation in progress; "beginner" =
        # beginner « Générer et uploader » in progress. Drives _sync_generation_buttons
        # so that changing mode during a generation keeps displaying the
        # loader (« ◐ Annuler ») on the displayed mode's button, without stopping it.
        self._gen_busy: str | None = None
        # Data stored for the compile phase of beginner mode
        self._beg_fqbn: str = ""
        self._beg_port: str = ""
        self._beg_backend = None
        self._beg_board_name: str = ""
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._hide_status_labels)
        # « In operation » buttons (generation / compile / upload): the
        # triggering button carries only its cancellation label (« Annuler »).
        # {button: (original text, cancellation label)}.
        self._spinner_btns: dict = {}
        # Loader d'opération : timer + index de la LIGNE ANIMÉE du journal
        # (« Génération en cours… »). Le voile sur le code a son propre timer
        # dans le CodePanel (Prompt 3) — ils ne sont plus frame-synchrones.
        # `_gen_loader_journal` = journal figé le temps de la génération.
        self._loader_idx: int = 0
        self._gen_loader_journal = None
        self._loader_timer = QTimer(self)
        self._loader_timer.setInterval(250)   # robot speed (cf. RobotLoader)
        self._loader_timer.timeout.connect(self._tick_loader)
        self._has_generated: bool = False
        self._last_prompt: str = ""
        # Persistent resolutions of the ambiguous wiring components,
        # living beyond the dialog lifecycle. Key: (fn_id, pin_net),
        # value: type_id chosen by the user (led / buzzer /
        # module_generic). Mutated by WiringDiagramDialog when the user
        # validates the ambiguities modal.
        self._wiring_resolutions: dict[tuple[str, str], str] = {}
        # Pedagogical log of the auto repairs from the LAST advanced
        # compilation (in-session: survives the upload, cleared on the next compile).
        self._last_repair_steps: list[dict] = []
        # Which editor the CompileService writes repaired code to. Always "ia"
        # except during a MANUAL repair targeting the stable window (routed by
        # _on_service_code_updated). Reset after each manual repair.
        self._active_repair_target: str = "ia"
        self._manual_repair_running: bool = False
        self._manual_repair: dict | None = None
        # The behavioral-review modal, opened IMMEDIATELY on click and driven
        # once the compile-first cascade finishes (spinner meanwhile).
        self._manual_repair_dialog = None
        # ── Generation orchestrator (Task 11) ─────────────────────────────────
        self._features: list[Feature] = []
        # Modèle de fonctionnalités de la fenêtre STABLE (Task 5) : distinct de
        # `_features` (fenêtre IA). Baseline stable posée au transfert IA->stable
        # et à toute suppression stable (Task 6 s'en sert pour le dirty-check).
        self._stable_features: list[Feature] = []
        self._stable_baseline = ""
        # (Sélection/survol des puces + surlignage du code : gérés DANS le
        # CodePanel — Prompt 3.)
        # Pin moves (conflict reassignment) awaiting a notice.
        self._pending_reassign: tuple[list, list] = ([], [])
        self._code_baseline: str = ""     # last sketch produced by the engine
        # (action, target) in progress. For CORRECT, target = list of feature
        # ids to modify (≥2 → merge); otherwise None.
        self._pending_action: tuple[str, str | list[str] | None] | None = None
        self._pending_from_scratch: bool = False   # ↻ vs Modifier (cf. _mk)
        # « editor content -> (features, wiring_resolutions, implicit_actions,
        # line_owners) » index: allows resynchronizing the features, their
        # wiring metadata AND the line->feature attribution map (#29) on
        # undo/redo (Ctrl+Z de-indexes, redo re-indexes). 4-tuple.
        self._feature_index: dict[str, tuple] = {}
        self._suppress_resync: bool = False   # true during a generation set_code
        # STABLE window undo/redo index (mirror of _feature_index, for the
        # stable side): « code -> (stable_features, line_owners) ». Feeds the
        # native Ctrl+Z of the stable editor so a transfer / delete is undoable
        # (the stable text is now applied via an UNDOABLE cursor insert).
        self._stable_feature_index: dict[str, tuple] = {}
        self._suppress_stable_resync: bool = False
        # Vérification d'assemblage (multi-fonctionnalités) : worker de compile
        # en tâche de fond + drapeau « 1 seule tentative de recombinaison ».
        self._verify_worker = None
        self._recombine_attempted = False
        self._recombine_eligible = False      # v2 : recombine autorisé (multi-features couplées)
        self._verify_delivered_code = ""       # code provisoire livré à la vérif (garde anti-perte d'édition)
        self._busy_text_override = None         # texte du voile pendant vérif/recombine (sinon « Génération »)
        self._gen_revert_code = ""             # baseline éditeur AVANT la génération
        self._gen_revert_features: list[Feature] = []  # baseline features AVANT la génération
        # State of the Level 3 implicit actions (cf
        # ui/wiring/implicit_actions.py). Key (fn_id, pin_arduino,
        # action_id). Value: bool for toggles (servo, BTN/DHT
        # pullup), str for selectors (LED series R "220"/.../"1000",
        # buzzer series R "none"/"100"/"220"). Mutated by WiringDiagramDialog
        # on gear click, saved in `.promptuino.json` via
        # `wiring_implicit_actions`.
        self._implicit_actions: dict[tuple[str, str, str], object] = {}
        # Snapshot of the code just before a generation worker (1st gen)
        # is started. Used to determine, after reception, which lines
        # are REALLY new (to highlight) vs already present in the
        # template (scaffolding + pedagogical comments).
        self._current_project: Project | None = None
        # List of the Studio Functions. Decoupled from the project to allow
        # using the Studio without a loaded project: as long as there is no
        # project, the functions live in RAM. When a project is loaded
        # via load_project(), this list BECOMES a direct reference to
        # project.functions — appends/mutations therefore propagate.
        # cascade, local regeneration). Each entry = full snapshot
        # capable of restoring the state: code + deep-copy of the Functions +
        # colors. QPlainTextEdit's native text undo cannot
        # restore the metadata (prompts, colors, ownerships) — hence
        # this dedicated stack.
        self._dirty: bool = False
        self._loading: bool = False
        # Auto-save: debounce triggered on each mutation.
        # Only active if a project is current (otherwise we wouldn't know
        # where to save — project creation stays manual via the button).
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.setInterval(1500)
        self._auto_save_timer.timeout.connect(self._auto_save)
        # Debounce for the #31 hand-edit capture (standalone orphan code ->
        # `manual` feature). Long enough to not run the round-trip check on
        # every keystroke; restarted while the user keeps typing.
        self._manual_capture_timer = QTimer(self)
        self._manual_capture_timer.setSingleShot(True)
        self._manual_capture_timer.setInterval(700)
        self._manual_capture_timer.timeout.connect(self._run_manual_capture)
        self._manual_capture_target = "ia"
        # Nudge de progression (#35) : un « segment » d'édition manuelle = une
        # suite de retouches à la main, bornée par une génération ou un upload.
        # Ce drapeau reste vrai tant que le segment courant est ouvert (déjà
        # compté) ; il retombe sur génération/upload -> le prochain edit ouvre un
        # nouveau segment. Compte pour la popup (5 segments) ET le bandeau (15).
        self._manual_edit_segment_open = False
        # Popup « passe en Avancé » due mais DIFFÉRÉE : le seuil est atteint
        # pendant la frappe (debounce 700 ms) — surgir à ce moment-là volerait
        # le focus et avalerait la touche suivante (revue 2026-07-29 #7). On
        # l'affiche à la prochaine frontière de segment (génération/upload).
        self._manual_edit_popup_due = False
        self._build()
        self._install_project_bar()
        # TODO #49 : l'excepthook sauve le processus, mais laisse l'interface
        # dans l'etat ou elle etait. On se rebranche dessus pour la deverouiller.
        self.unhandled_exception_reported.connect(self._recover_from_unhandled)
        try:
            from .crash_log import on_unhandled
            on_unhandled(self.unhandled_exception_reported.emit)
        except Exception:
            pass          # un filet absent ne doit pas empecher le Studio d'ouvrir
        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)

    # ── Construction ──────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Main area: scrollable content ───────────────────────
        # DEUX grilles : `_content` (scrollé, remplit le viewport, comme avant)
        # ET `_main_row_w` (statique, pleine largeur). Le viewport est rétréci
        # de ~14px quand la scrollbar apparaît -> cette bande de droite (gouttière
        # de la scrollbar, fond transparent cf. main.py) laissait voir un fond
        # plat sans grille. La grille statique de `_main_row_w` la remplit donc
        # jusqu'à la bordure du chat. (Les lignes verticales coïncident car même
        # pas de 24px depuis x=0 ; les horizontales de la gouttière sont derrière
        # la poignée de scrollbar, négligeable.)
        self._main_row_w = _GridBackground()   # grille statique pleine largeur
        main_row = QHBoxLayout(self._main_row_w)
        main_row.setContentsMargins(0, 0, 0, 0)
        main_row.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Scroll vertical à la demande : la vue Avancé 2 fenêtres (2 éditeurs +
        # boutons par fenêtre + console haute) dépasse la hauteur du viewport
        # sur une petite fenêtre -> on scrolle plutôt que de rogner.
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        main_row.addWidget(scroll, stretch=1)

        self._content = _GridBackground()   # grille scrollée, remplit le viewport
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(32, 16, 32, 16)
        self._layout.setSpacing(12)
        scroll.setWidget(self._content)
        self._scroll = scroll

        root.addWidget(self._main_row_w, stretch=1)

        # ── Prompt (always visible) ────────────────────────────
        # "Prompt IA title" row + Comments slider (Advanced mode only).
        # The slider chooses the verbosity level of the comments generated
        # by the AI: None / Minimal / Standard / Detailed. Placed to the right of the
        # label, with a stretch between the two to keep the title on the left.
        self._prompt_header_w = QWidget()
        prompt_header = QHBoxLayout(self._prompt_header_w)
        prompt_header.setContentsMargins(0, 0, 0, 0)
        prompt_header.setSpacing(12)

        self._lbl_prompt = _ElidingLabel()
        prompt_header.addWidget(self._lbl_prompt)
        prompt_header.addStretch(1)

        self._comments_slider_w = QWidget()
        cw = QHBoxLayout(self._comments_slider_w)
        cw.setContentsMargins(0, 0, 0, 0)
        cw.setSpacing(8)

        self._lbl_comments_label = _ElidingLabel()
        cw.addWidget(self._lbl_comments_label)

        self._comments_slider = QSlider(Qt.Orientation.Horizontal)
        self._comments_slider.setMinimum(0)
        self._comments_slider.setMaximum(3)
        self._comments_slider.setValue(2)  # 2 = Standard (default)
        self._comments_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._comments_slider.setTickInterval(1)
        self._comments_slider.setPageStep(1)
        self._comments_slider.setSingleStep(1)
        self._comments_slider.setFixedWidth(168)   # spec Phase 3 §4
        self._comments_slider.valueChanged.connect(
            self._on_comments_verbosity_changed
        )
        cw.addWidget(self._comments_slider)

        # Label that displays the name of the current level (None/Minimal/Standard/
        # Detailed). Fixed width to avoid the slider jumping when the
        # word changes length between two levels.
        self._lbl_comments_value = QLabel()
        self._lbl_comments_value.setMinimumWidth(70)
        cw.addWidget(self._lbl_comments_value)

        self._comments_slider_w.setVisible(False)  # shown only in advanced
        prompt_header.addWidget(self._comments_slider_w)

        # Serial Monitor checkbox (Advanced mode only). Checked by default:
        # injects Serial.begin(9600) at the head of setup() and allows
        # Serial.print/println in the generated code. Unchecked: the init line
        # and all Serial.print/println are commented out (not removed).
        self._chk_serial_monitor = QCheckBox()
        self._chk_serial_monitor.setChecked(True)
        self._chk_serial_monitor.setVisible(False)
        self._chk_serial_monitor.toggled.connect(self._on_serial_monitor_toggled)
        prompt_header.addWidget(self._chk_serial_monitor)

        self._layout.addWidget(self._prompt_header_w)

        # AI context badge — always visible above the prompt.
        # Empty mode: "Ajouter un fichier..." prompt + + button. Filled mode:
        # label "Contexte : <name> (<N> car.)" + × button. Dropping on the
        # prompt below also triggers _on_context_dropped.
        self._context_badge = _ContextBadge()
        self._context_badge.add_clicked.connect(self._on_context_add_clicked)
        self._context_badge.remove_clicked.connect(self._on_context_removed)
        # Placed as an overlay to the left of the « Joindre » button (cf set_overlay_left
        # below), no longer above the prompt.

        # Prompt field + Generate button side by side
        # (the button is hidden in beginner mode)
        prompt_row = QHBoxLayout()
        prompt_row.setContentsMargins(0, 0, 0, 0)
        prompt_row.setSpacing(10)

        self._prompt_field = _PromptTextEdit()
        self._prompt_field.setFixedHeight(_PROMPT_H)
        self._prompt_field.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed,
        )
        self._prompt_field.file_dropped.connect(self._on_context_dropped)
        self._prompt_field.submit_requested.connect(self._on_prompt_submit)
        # « + Attach » button floating at the bottom-right of the prompt field (spec §4):
        # same action as the context badge (QFileDialog .md/.txt).
        self._btn_attach_prompt = QPushButton("+ Attach")
        self._btn_attach_prompt.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_attach_prompt.setAutoDefault(False)
        self._btn_attach_prompt.clicked.connect(self._on_context_add_clicked)
        self._prompt_field.set_overlay_button(self._btn_attach_prompt)
        # Context file chip anchored just to the left of the « Joindre » button.
        self._prompt_field.set_overlay_left(self._context_badge)
        # Rotating tips in the placeholder (every 10 s, cf #24).
        from .prompt_tips import PromptTipRotator
        self._prompt_tips = PromptTipRotator(self._prompt_field)
        self._prompt_tips.start()
        prompt_row.addWidget(self._prompt_field, 1, Qt.AlignmentFlag.AlignTop)

        # Generate button + Iterate button + spinner below column
        self._gen_col_w = QWidget()
        self._gen_col_w.setFixedWidth(180)
        gen_col = QVBoxLayout(self._gen_col_w)
        gen_col.setContentsMargins(0, 0, 0, 0)
        gen_col.setSpacing(4)
        gen_col.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._btn_generate = QPushButton(lang_manager.current.studio_generate)
        self._btn_generate.setFixedSize(180, _PROMPT_H)   # same height as the prompt field
        self._btn_generate.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_generate.setAutoDefault(False)
        self._btn_generate.clicked.connect(self._on_generate_clicked)
        gen_col.addWidget(self._btn_generate)

        self._gen_spin_row = QWidget()
        gsr = QHBoxLayout(self._gen_spin_row)
        gsr.setContentsMargins(0, 0, 0, 0)
        gsr.setSpacing(6)
        self._lbl_gen_spinner = QLabel("◐")
        self._lbl_gen_spinner.setFixedWidth(16)
        gsr.addWidget(self._lbl_gen_spinner)
        self._lbl_gen_spin_text = QLabel()
        self._lbl_gen_spin_text.setWordWrap(True)
        gsr.addWidget(self._lbl_gen_spin_text, stretch=1)
        self._gen_spin_row.setVisible(False)
        # #7: the status label row is no longer displayed (loader now
        # INSIDE the Generate button) — widget kept for theme/language refs
        # but NOT placed (frees the space).

        prompt_row.addWidget(self._gen_col_w, 0, Qt.AlignmentFlag.AlignTop)

        self._layout.addLayout(prompt_row)

        # (Le bandeau des fonctionnalités — puces sélectionnables — est créé
        # par le CodePanel mais PLACÉ ici, pleine largeur sous le prompt :
        # insertion faite à la construction du panneau, juste avant la zone
        # d'erreur ci-dessous.)

        # Generation error (inter/advanced, hidden by default)
        self._lbl_gen_error = QLabel()
        self._lbl_gen_error.setVisible(False)
        self._lbl_gen_error.setWordWrap(True)
        self._layout.addWidget(self._lbl_gen_error)

        # Bandeau de nudge de progression (en tête de la colonne de contenu,
        # visible dans tous les modes ; masqué tant qu'aucun nudge n'est dû).
        self._nudge_target_mode = ""
        self._nudge_banner = NudgeBanner()
        self._nudge_banner.action_requested.connect(self._on_nudge_action)
        self._layout.insertWidget(0, self._nudge_banner)
        # Bannière info « composant hors-corpus » (spec 2026-07-29) : dit quelle
        # lib du registre Arduino a été utilisée pour un part-number inconnu du
        # corpus, ou avoue qu'aucune référence n'existe. Message + croix, plus
        # un bouton d'action (« Changer de bibliothèque ») quand au moins un
        # composant trouvé a des alternatives (Task 4, TODO #39).
        self._registry_banner = NudgeBanner(variant="info")
        # (token, lib_name, alternatives) for each ACTIONABLE component of the
        # last banner shown -- i.e. the ones the action button can offer a
        # choice for. Consumed by _on_change_lib_requested.
        self._registry_choices: list[tuple[str, str, list[str]]] = []
        # Composants que ni le corpus ni le registre ne connaissent, retenus
        # pour la question pré-remplie du bouton « demander de l'aide ».
        self._registry_unknown: list[str] = []
        # {lookup token: module alias} for tokens derived from a silkscreened
        # module reference ("hw-617" -> "tca9548a"). Read by
        # _apply_registry_results so the banner can name BOTH what the user
        # typed and what was actually searched -- never letting a translation
        # pass for the user's own words (spec 2026-08-20).
        self._registry_aliases: dict[str, str] = {}
        # {lookup token: registry search query} for those same tokens. The
        # token is the chip IDENTITY ("bmp085"), the query is the verified
        # library name ("Adafruit BMP085 Library") -- of the 48 lib_name-only
        # registry entries only 3 have both equal, so the two must not be
        # collapsed. Passed to RegistryLookupWorker by both generation paths.
        self._registry_search_queries: dict[str, str] = {}
        # TODO #51 : jetons dont l'utilisateur AFFIRME qu'ils ne
        # demandent aucune bibliotheque. Vaut pour la generation en
        # cours seulement, comme ses deux voisines.
        self._registry_no_library: list[str] = []
        # TODO #61 : les libs de la DERNIÈRE construction de contexte ont-elles
        # été choisies par similarité sémantique pour un prompt qui ne nommait
        # rien de reconnu ? Posé par `_note_resemblance`, que
        # `rag.build_lib_context` rappelle à chaque assemblage.
        self._last_resemblance = False
        # Accumulator for the regeneration offer (Task 6, TODO #39): ids of
        # features affected by a library change, and the (old, new) library
        # names, queued by `_after_lib_preference_changed` and consumed once
        # by `_offer_lib_swap_regeneration` -- shared by BOTH entry points
        # (this banner's loop, and the Composants tab's single-component
        # button) so neither can prompt with a different notion of what
        # "affected" means.
        self._pending_lib_swap_ids: set[str] = set()
        self._pending_lib_swap_pairs: list[tuple[str, str]] = []
        self._registry_banner.action_requested.connect(
            self._on_change_lib_requested)
        self._registry_banner.action2_requested.connect(
            self._open_chat_help_unknown_parts)
        self._layout.insertWidget(1, self._registry_banner)
        # Miroir des diagnostics « [RAG] … » dans le journal : sur stdout
        # uniquement, ils étaient invisibles dans l'app packagée (désync
        # embeddings, aucune lib retenue… = échecs silencieux).
        rag_set_status_sink(self._on_rag_status)

        # ── "Générer et envoyer" button (beginner only) ───────────────
        self._beginner_row = QWidget()
        beg_layout = QVBoxLayout(self._beginner_row)
        beg_layout.setContentsMargins(0, 4, 0, 0)
        beg_layout.setSpacing(8)
        beg_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        beg_btn_row = QHBoxLayout()
        beg_btn_row.setContentsMargins(0, 0, 0, 0)
        beg_btn_row.setSpacing(8)
        # The 3 beginner buttons stretch equally to occupy the full
        # width (= prompt field width, full width in beginner mode).
        _beg_btn_h = 44

        self._btn_generate_send = QPushButton()
        self._btn_generate_send.setFixedHeight(_beg_btn_h)
        self._btn_generate_send.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._btn_generate_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_generate_send.clicked.connect(self._on_generate_and_send)
        beg_btn_row.addWidget(self._btn_generate_send, 1)

        self._btn_upload_only = QPushButton()
        self._btn_upload_only.setFixedHeight(_beg_btn_h)
        self._btn_upload_only.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._btn_upload_only.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_upload_only.setEnabled(False)
        self._btn_upload_only.clicked.connect(self._on_upload_only)
        beg_btn_row.addWidget(self._btn_upload_only, 1)

        # « Voir le schéma » — beginner mode. Introduced 2026-05-27 as a
        # temporary lever to test the disambiguation cascade, made PERMANENT on
        # 2026-08-10: it is the beginner's only door to the schematic, hence to
        # the visual disambiguation modal, which targets that very mode. The
        # button follows the CODE, not the generation (fixed 2026-08-08, cf. QA
        # procedure E1) — someone pasting their own sketch can open it too.
        self._btn_view_schema = QPushButton()
        self._btn_view_schema.setFixedHeight(_beg_btn_h)
        self._btn_view_schema.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._btn_view_schema.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_view_schema.setEnabled(False)
        self._btn_view_schema.clicked.connect(self._open_wiring_diagram_dialog)
        beg_btn_row.addWidget(self._btn_view_schema, 1)

        beg_layout.addLayout(beg_btn_row)

        # #7 moved the loader INTO the buttons: the old « in progress / done »
        # status row is no longer used. Both labels are kept
        # (referenced by apply_theme / _hide_status_labels / debug preview) but
        # NOT placed in the layout — otherwise they reserved a phantom space between
        # the buttons and the log (setRetainSizeWhenHidden). Parented to
        # _beginner_row so they don't become floating windows.
        self._lbl_beg_spinner = QLabel("◐", self._beginner_row)
        self._lbl_beg_spinner.setVisible(False)
        self._lbl_beginner_status = QLabel(self._beginner_row)
        self._lbl_beginner_status.setVisible(False)

        self._layout.addWidget(self._beginner_row)

        # ── Beginner view: full-width MERGED Journal (#6) ────────────
        # Exactly like the advanced console: a single LogWidget receives the
        # compile/upload log AND the serial output. No more « Instructions de
        # branchement » panel. Called « Journal » (studio_output_label).
        self._beg_bottom_row_w = QWidget()
        beg_vbox = QVBoxLayout(self._beg_bottom_row_w)
        beg_vbox.setContentsMargins(0, 8, 0, 0)
        beg_vbox.setSpacing(4)

        # Beginner merged console = ConsolePanel (journal + moteur série
        # câblés en interne : data_received -> append_serial, autoscroll,
        # en-tête « Sortie console » à l'ouverture du port). Aliases : les
        # nombreux sites existants continuent de lire _beg_output_area /
        # _serial_monitor_beg (mêmes objets).
        self._beg_console = ConsolePanel()
        self._beg_output_area = self._beg_console.log
        self._serial_monitor_beg = self._beg_console.serial
        # In beginner: keep the Connect/Disconnect button in the console,
        # but not the baud selector (user request).
        self._serial_monitor_beg.set_connect_visible(True)
        self._serial_monitor_beg.set_baud_visible(False)

        # Title row: « Journal » label + serial controls (autoscroll/baud).
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        self._lbl_serial_beg_title = _ElidingLabel()   # text = studio_output_label
        self._lbl_serial_beg_title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(self._lbl_serial_beg_title)
        title_row.addWidget(self._serial_monitor_beg.get_ctrl_widget(), stretch=1)
        beg_vbox.addLayout(title_row)

        self._beg_console.help_with_error_requested.connect(
            self._on_error_help_requested
        )
        beg_vbox.addWidget(self._beg_console, stretch=1)

        # « instructions » widgets kept (referenced by apply_theme/lang)
        # but NOT placed: the instructions window is removed from beginner
        # mode (#6).
        self._lbl_instructions_title = _ElidingLabel()
        self._beg_instructions_w = QWidget()

        self._layout.addWidget(self._beg_bottom_row_w, stretch=1)

        # ── Editor + Compiler & Uploader side by side (inter/advanced) ──
        # Code header: "Code" label on the left + "Afficher les
        # commentaires" checkbox on the right. The checkbox toggles between the
        # full version (with comments, stored in _code_with_comments)
        # and the stripped version (100% comment lines removed,
        # inline comments removed). Checked = full editable code;
        # unchecked = read-only stripped version.
        self._code_header_w = QWidget()
        code_header = QHBoxLayout(self._code_header_w)
        # Top margin of 8 px: aligns the prompt -> « _Code généré » gap (inter/advanced)
        # with the buttons -> « _Journal » gap of beginner mode (the beginner
        # log block has the same 8 px top margin). User request.
        code_header.setContentsMargins(0, 8, 0, 0)
        code_header.setSpacing(10)
        self._lbl_code = _ElidingLabel()
        code_header.addWidget(self._lbl_code)
        code_header.addStretch(1)

        # Section d'outils RÉUTILISABLE (case « Afficher les commentaires » +
        # nombre de lignes + pastille OUTILS) groupée dans un widget
        # reparentable : en Intermédiaire dans cet en-tête ; en Avancé,
        # reparentée dans l'en-tête de la fenêtre IA (cf. _mount_editor_console).
        self._code_tools_w = QWidget()
        _ct = QHBoxLayout(self._code_tools_w)
        # Référence conservée : le dropdown IA (créé APRÈS _code_panel) sera
        # inséré juste après la case commentaires (index 1), cf. bloc 4a.
        self._code_tools_layout = _ct
        _ct.setContentsMargins(0, 0, 0, 0)
        _ct.setSpacing(0)
        self._chk_show_comments = QCheckBox()
        self._chk_show_comments.setChecked(True)
        self._chk_show_comments.toggled.connect(self._on_show_comments_toggled)
        _ct.addWidget(self._chk_show_comments)
        _ct.addSpacing(12)
        self._lbl_code_meta = _ElidingLabel()   # « N lignes » (Updated via _update_code_meta)
        _ct.addWidget(self._lbl_code_meta)
        _ct.addSpacing(12)
        self._btn_ai_tools = QPushButton()   # « Outils » label via _apply_lang
        self._btn_ai_tools.setFixedHeight(24)
        self._btn_ai_tools.setCursor(Qt.CursorShape.PointingHandCursor)
        # Lambda zéro-arg (piège clicked(bool)) : cible = fenêtre IA.
        self._btn_ai_tools.clicked.connect(lambda: self._open_ai_tools_menu("ia"))
        _ct.addWidget(self._btn_ai_tools)
        # SPARKLES icon: white (text_primary) at rest to match the dropdown
        # label, GREEN on hover (QSS can't recolor a QIcon -> dedicated filter).
        install_icon_hover(self._btn_ai_tools, IC.SPARKLES, 13,
                           normal_role="text_primary")

        # Slot d'accueil de la section d'outils en Intermédiaire (le point de
        # montage fixe ; la section le quitte pour la fenêtre IA en Avancé).
        self._int_tools_slot = QWidget()
        _its = QHBoxLayout(self._int_tools_slot)
        _its.setContentsMargins(0, 0, 0, 0)
        _its.addWidget(self._code_tools_w)
        code_header.addWidget(self._int_tools_slot)

        # Align the end of the checkbox with the right edge of the editor (the
        # code_row row reserves a fixed 380 px column + 10 px of spacing on the right).
        # SHRINKABLE spacer (Maximum policy: prefers 390 px for alignment
        # when there is room, but can drop to 0): otherwise this fixed spacer
        # inflates the min width of the code area and the right column overflows when
        # the chat + the sidebar are open (user choice: the editor yields).
        self._code_header_spacer = QSpacerItem(
            380 + 10, 0, QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)
        code_header.addItem(self._code_header_spacer)
        self._layout.addWidget(self._code_header_w)
        # Storage of the "with comments" version: used when the
        # checkbox is unchecked to be able to redisplay the full code
        # when re-checking. None = no toggle in progress.
        # `_stripped_at_decoche` keeps the stripped version at the moment of
        # unchecking: on re-check, diff with the current editor to
        # re-inject the comments on the unchanged lines, and
        # accept as-is the zones modified by the user.
        # État du toggle « Afficher les commentaires » PAR FENÊTRE de code
        # (mode avancé 2 fenêtres : « ia » = éditeur principal, « stable » =
        # 2e éditeur). Dict pour ne pas mélanger les deux états.
        self._code_with_comments: dict[str, str | None] = {"ia": None, "stable": None}
        self._stripped_at_decoche: dict[str, str | None] = {"ia": None, "stable": None}
        # Cible courante des outils / de la case commentaires (posée par la
        # fenêtre dont le contrôle a été actionné, avant de lancer l'action).
        self._code_target: str = "ia"

        self._code_compile_w = QWidget()
        code_row = QHBoxLayout(self._code_compile_w)
        code_row.setContentsMargins(0, 0, 0, 0)
        code_row.setSpacing(10)

        # Fenêtre de code réutilisable (Prompt 3) = éditeur + voile busy +
        # overlay « génération de commentaires » + overlay ↻/🗑 par
        # fonctionnalité + dropdown (placé hors panneau, cf. ci-dessous). Le
        # panneau porte SON timer d'animation pour le voile (le timer du studio
        # ne pilote plus que la ligne animée du journal). Alias : les sites
        # existants gardent _editor.
        self._code_panel = CodePanel(embed_chips=False)
        self._editor = self._code_panel.editor
        # Actions ↻/🗑 de la fenêtre IA : posées sur CHAQUE LIGNE du popup, émises
        # pour une fonctionnalité à la fois (liste à 1 élément, cible "ia").
        self._code_panel.feature_dropdown.regen_requested.connect(
            lambda ids: self._on_chips_regen(ids, target="ia"))
        self._code_panel.feature_dropdown.delete_requested.connect(
            lambda ids: self._on_chips_delete(ids, target="ia"))
        # Dropdown des fonctionnalités (fenêtre IA) placé sur la ligne d'outils
        # partagée, JUSTE APRÈS le bouton « Outils » — même ordre que la fenêtre
        # stable (cf. _st_hdr) pour un placement identique sur les 2 fenêtres.
        self._code_tools_layout.addSpacing(12)
        self._code_tools_layout.addWidget(self._code_panel.feature_dropdown)
        # #33 : l'édition manuelle est désormais libre dans tous les modes -> plus
        # de popup « passer en Avancé » sur edit_attempted (sinon il s'ouvrirait
        # sous le voile busy, où l'éditeur read-only émet edit_attempted à chaque
        # frappe -> conflit). set_edit_locked reste dispo (verrou réactivable) ;
        # la popup a été repurposée en nudge « 2 fenêtres » (#35,
        # _show_advanced_nudge_popup, déclenchée par le compteur d'édition
        # manuelle, pas par edit_attempted).
        self._editor.help_with_function_requested.connect(
            self._on_code_help_requested
        )
        self._editor.help_with_selection_requested.connect(
            self._on_code_selection_help_requested
        )
        # Slot de l'éditeur IA (reparenté selon le mode : colonne gauche en
        # Intermédiaire, colonne IA en Avancé). Marges nulles -> invisible.
        self._int_editor_slot = QWidget()
        _ies = QVBoxLayout(self._int_editor_slot)
        _ies.setContentsMargins(0, 0, 0, 0)
        _ies.addWidget(self._code_panel)
        code_row.addWidget(self._int_editor_slot, stretch=1)

        # Right column: Compile button + status + stretch.
        # Same width as the Generate column (180) so that the editor and the
        # prompt field have exactly the same width and are aligned.
        cu_col_w = QWidget()
        cu_col_w.setFixedWidth(380)   # right column (spec Phase 3 §5: 230 +~65%)
        cu_col = QVBoxLayout(cu_col_w)
        cu_col.setContentsMargins(0, 0, 0, 0)
        cu_col.setSpacing(10)

        self._btn_compile = QPushButton()
        self._btn_compile.setFixedHeight(52)   # #8: more prominent (spec §5)
        self._btn_compile.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_compile.clicked.connect(self._on_compile_upload)

        # Spinner row: during compilation displays [animated icon +
        # phase text]; at the end reused to display the
        # final status (✓ success / ✗ error). No separate widget for the status
        # -> the button no longer moves when the message is displayed.
        self._cu_spin_row = QWidget()
        csr = QHBoxLayout(self._cu_spin_row)
        csr.setContentsMargins(0, 0, 0, 0)
        csr.setSpacing(6)
        self._lbl_cu_spinner = QLabel("◐")
        self._lbl_cu_spinner.setFixedWidth(16)
        csr.addWidget(self._lbl_cu_spinner)
        self._lbl_cu_spin_text = QLabel()
        self._lbl_cu_spin_text.setWordWrap(True)
        csr.addWidget(self._lbl_cu_spin_text, stretch=1)
        self._cu_spin_row.setVisible(False)
        # #7: loader now INSIDE the Compile button; label row not placed
        # (widget kept for theme/language refs). Frees the space (#8).

        # "Voir le schéma" button (inter/advanced). Replaces access via the
        # sidebar tool `wiring_diagram` removed with the side menu (cf TODO #1).
        # Lives in `_code_compile_w` -> automatically hidden in beginner mode
        # (which has its own button). Enabled as soon as there is generated code
        # via `_refresh_action_button_styles`.
        self._btn_view_schema_adv = QPushButton()
        self._btn_view_schema_adv.setFixedHeight(52)   # #8: consistent with Compile
        self._btn_view_schema_adv.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_view_schema_adv.setEnabled(False)
        self._btn_view_schema_adv.clicked.connect(self._open_wiring_diagram_dialog)

        # Contrôles compile IA (Compiler&Uploader + Voir le schéma) : widget
        # reparenté (avec la console) entre Intermédiaire et Avancé.
        self._ia_controls_w = QWidget()
        _iac = QVBoxLayout(self._ia_controls_w)
        _iac.setContentsMargins(0, 0, 0, 0)
        _iac.setSpacing(10)
        _iac.addWidget(self._btn_compile)
        _iac.addWidget(self._btn_view_schema_adv)
        self._ia_controls_slot = QWidget()
        _iacs = QVBoxLayout(self._ia_controls_slot)
        _iacs.setContentsMargins(0, 0, 0, 0)
        _iacs.addWidget(self._ia_controls_w)
        cu_col.addWidget(self._ia_controls_slot)

        # ── Merged STDOUT (spec Phase 3 §5) ───────────────────────────
        # A SINGLE read-only console under the buttons: the LogWidget keeps the
        # error coloring + the « aide sur cette erreur » button; the
        # serial data is routed into it (cf _serial_monitor.data_received).
        self._lbl_output = _ElidingLabel()
        self._lbl_output.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # ConsolePanel int/avancé : journal + moteur série câblés en interne,
        # avec la barre série FIXE en bas du journal (2 rangées : contrôles
        # Connecter|auto-scroll|baud puis ligne d'envoi — hors défilement).
        # Aliases : les sites existants gardent _output_area/_serial_monitor.
        self._adv_console = ConsolePanel(serial_bar_in_log=True)
        self._output_area = self._adv_console.log
        self._serial_monitor = self._adv_console.serial
        # Narrow strip (380 px): reduced font to fit everything on ONE line.
        self._serial_monitor.set_compact(True)
        self._adv_console.help_with_error_requested.connect(
            self._on_error_help_requested
        )
        self._adv_console.action_clicked.connect(self._on_output_action)

        # Console partagée (label « Sortie » + ConsolePanel) : widget reparenté
        # (colonne droite en Intermédiaire, bas de page pleine largeur en Avancé).
        self._console_w = QWidget()
        _cw = QVBoxLayout(self._console_w)
        _cw.setContentsMargins(0, 0, 0, 0)
        _cw.setSpacing(10)
        _cw.addWidget(self._lbl_output)
        _cw.addWidget(self._adv_console, stretch=1)
        self._int_console_slot = QWidget()
        _ics = QVBoxLayout(self._int_console_slot)
        _ics.setContentsMargins(0, 0, 0, 0)
        _ics.addWidget(self._console_w, stretch=1)
        cu_col.addWidget(self._int_console_slot, stretch=1)

        # UN SEUL chemin compile/upload (Prompt 2) : le service crée et câble
        # les CompileUploadWorker vers la console cible (étapes au journal,
        # done standard, règles série). Les deux moteurs série lui sont
        # confiés : port exclusif -> tout ce qui est ouvert est fermé avant
        # un upload.
        self._compile_service = CompileService(
            on_code_updated=self._on_service_code_updated,
            serials=(self._serial_monitor_beg, self._serial_monitor),
        )

        # Old "Moniteur Série" title: kept (referenced by apply_theme /
        # apply_lang) but not placed — the dedicated serial header is gone.
        self._lbl_serial_title = _ElidingLabel()
        self._lbl_serial_title.setVisible(False)

        code_row.addWidget(cu_col_w)

        # The code+output area (advanced) is now a single horizontal
        # row: editor (flex) | right column 230px (compile + schema
        # + merged STDOUT). No more vertical splitter or bottom row.
        self._layout.addWidget(self._code_compile_w, stretch=1)

        # ── Conteneur Avancé : 2 fenêtres (IA | stable) + console en bas ──
        # Slots vides ici ; _mount_editor_console (Task 5) y monte _code_panel /
        # _ia_controls_w / _console_w quand on passe en Avancé.
        self._advanced_area_w = QWidget()
        _adv_v = QVBoxLayout(self._advanced_area_w)
        _adv_v.setContentsMargins(0, 0, 0, 0)
        _adv_v.setSpacing(10)

        _adv_top = QHBoxLayout()
        _adv_top.setContentsMargins(0, 0, 0, 0)
        _adv_top.setSpacing(10)

        # Colonne IA : en-tête (titre + section d'outils reparentée) + slot
        # éditeur (rempli au mount) + slot contrôles compile.
        _ia_col = QVBoxLayout()
        _ia_col.setContentsMargins(0, 0, 0, 0)
        _ia_col.setSpacing(8)
        _ia_hdr = QHBoxLayout()
        _ia_hdr.setContentsMargins(0, 0, 0, 0)
        self._lbl_window_ai = _ElidingLabel()
        _ia_hdr.addWidget(self._lbl_window_ai)
        _ia_hdr.addStretch(1)
        # Slot d'accueil de la section d'outils PARTAGÉE (la même que
        # l'Intermédiaire) : reparentée ici en Avancé (cf. _mount_editor_console).
        self._adv_ia_tools_slot = QWidget()
        _aits = QHBoxLayout(self._adv_ia_tools_slot)
        _aits.setContentsMargins(0, 0, 0, 0)
        _ia_hdr.addWidget(self._adv_ia_tools_slot)
        _ia_col.addLayout(_ia_hdr)
        self._adv_ia_editor_slot = QWidget()
        _aies = QVBoxLayout(self._adv_ia_editor_slot)
        _aies.setContentsMargins(0, 0, 0, 0)
        _ia_col.addWidget(self._adv_ia_editor_slot, stretch=1)
        self._adv_ia_controls_slot = QWidget()
        _aics = QVBoxLayout(self._adv_ia_controls_slot)
        _aics.setContentsMargins(0, 0, 0, 0)
        _ia_col.addWidget(self._adv_ia_controls_slot)
        _ia_col_w = QWidget()
        _ia_col_w.setLayout(_ia_col)

        # Colonne centrale : DEUX chevrons de transfert empilés — « » » (IA ->
        # stable) et « « » (stable -> IA) en dessous. Les deux ouvrent la MÊME
        # popup bidirectionnelle ; les deux sens affichés sont une affordance.
        # Sans contour, verts au survol, libellés en infobulle (apply_lang).
        # Le bloc est recentré verticalement sur la ZONE DES ÉDITEURS (pas les
        # boutons du dessous) par _reposition_transfer_block, déclenché par
        # l'eventFilter Resize/Show du conteneur pleine hauteur.
        self._btn_transfer = QPushButton("»")
        self._btn_transfer.clicked.connect(self._on_transfer_to_stable)
        self._btn_transfer_back = QPushButton("«")
        self._btn_transfer_back.clicked.connect(self._on_transfer_to_stable)
        # Hauteur serrée (le glyphe 22pt n'occupe que la mi-hauteur de sa
        # boîte de ligne) -> les deux chevrons sont visuellement accolés.
        for _b in (self._btn_transfer, self._btn_transfer_back):
            _b.setFixedHeight(24)
            _b.setCursor(Qt.CursorShape.PointingHandCursor)
        self._transfer_col_w = QWidget()
        self._transfer_col_w.setFixedWidth(44)
        # Le bloc se comporte comme UN SEUL contrôle : curseur main partout
        # (interstices compris) et hover vert COLLECTIF via le sélecteur
        # descendant `#transferBlock:hover QPushButton` (cf. apply_theme).
        self._transfer_block = QWidget(self._transfer_col_w)
        self._transfer_block.setObjectName("transferBlock")
        self._transfer_block.setCursor(Qt.CursorShape.PointingHandCursor)
        _trb = QVBoxLayout(self._transfer_block)
        _trb.setContentsMargins(0, 0, 0, 0)
        _trb.setSpacing(0)
        _trb.addWidget(self._btn_transfer)
        _trb.addWidget(self._btn_transfer_back)
        self._transfer_col_w.installEventFilter(self)
        # Collective hover handled PROGRAMMATICALLY (eventFilter Enter/Leave
        # on the block AND the buttons): a QSS descendant selector with
        # :hover on the ANCESTOR (`#transferBlock:hover QPushButton`) is not
        # honored by Qt — the ancestor pseudo-state is ignored, the rule
        # applied permanently (chevrons stuck green).
        self._transfer_block.installEventFilter(self)
        self._btn_transfer.installEventFilter(self)
        self._btn_transfer_back.installEventFilter(self)

        # Colonne stable : en-tête (titre + section d'outils PROPRE, câblée sur
        # l'éditeur stable) + éditeur libre (2e CodePanel, sans puces) + bouton
        # upload dédié (compile+upload SANS IA) + « Voir le schéma » stable.
        _st_col = QVBoxLayout()
        _st_col.setContentsMargins(0, 0, 0, 0)
        _st_col.setSpacing(8)
        _st_hdr = QHBoxLayout()
        _st_hdr.setContentsMargins(0, 0, 0, 0)
        self._lbl_window_stable = _ElidingLabel()
        _st_hdr.addWidget(self._lbl_window_stable)
        _st_hdr.addStretch(1)
        # Section d'outils DÉDIÉE à la fenêtre stable (instances distinctes ;
        # elles ciblent l'éditeur stable via target="stable").
        self._chk_show_comments_st = QCheckBox()
        self._chk_show_comments_st.setChecked(True)
        self._chk_show_comments_st.toggled.connect(
            lambda ch: self._on_show_comments_toggled(ch, "stable"))
        _st_hdr.addWidget(self._chk_show_comments_st)
        _st_hdr.addSpacing(12)
        self._lbl_code_meta_st = _ElidingLabel()
        _st_hdr.addWidget(self._lbl_code_meta_st)
        _st_hdr.addSpacing(12)
        self._btn_ai_tools_st = QPushButton()
        self._btn_ai_tools_st.setFixedHeight(24)
        self._btn_ai_tools_st.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_ai_tools_st.clicked.connect(
            lambda: self._open_ai_tools_menu("stable"))
        _st_hdr.addWidget(self._btn_ai_tools_st)
        install_icon_hover(self._btn_ai_tools_st, IC.SPARKLES, 13,
                           normal_role="text_primary")
        _st_col.addLayout(_st_hdr)
        # Fenêtre stable : pas de régénération IA -> can_regenerate=False (chaque
        # ligne du popup n'expose que 🗑). Son dropdown va dans l'en-tête stable.
        self._stable_panel = CodePanel(embed_chips=False, can_regenerate=False)
        _st_hdr.addSpacing(12)
        _st_hdr.addWidget(self._stable_panel.feature_dropdown)
        self._stable_panel.feature_dropdown.delete_requested.connect(
            lambda ids: self._on_chips_delete(ids, target="stable"))
        self._stable_panel.editor.textChanged.connect(self._on_stable_edited)
        _st_col.addWidget(self._stable_panel, stretch=1)
        self._btn_compile_stable = QPushButton()
        self._btn_compile_stable.setFixedHeight(52)
        self._btn_compile_stable.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_compile_stable.clicked.connect(self._on_stable_compile_upload)
        _st_col.addWidget(self._btn_compile_stable)
        # « Voir le schéma » câblé sur le CODE STABLE (≠ bouton IA qui lit
        # l'éditeur principal). Slot sans argument (piège clicked(bool)).
        self._btn_view_schema_stable = QPushButton()
        self._btn_view_schema_stable.setFixedHeight(52)
        self._btn_view_schema_stable.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_view_schema_stable.clicked.connect(
            self._open_stable_wiring_diagram_dialog)
        _st_col.addWidget(self._btn_view_schema_stable)
        _st_col_w = QWidget()
        _st_col_w.setLayout(_st_col)

        _adv_top.addWidget(_ia_col_w, stretch=1)
        _adv_top.addWidget(self._transfer_col_w)   # pleine hauteur, cf. bloc
        _adv_top.addWidget(_st_col_w, stretch=1)
        _adv_v.addLayout(_adv_top, stretch=1)

        # Console partagée en bas (slot rempli au mount).
        self._adv_console_slot = QWidget()
        _acs = QVBoxLayout(self._adv_console_slot)
        _acs.setContentsMargins(0, 0, 0, 0)
        _adv_v.addWidget(self._adv_console_slot)

        self._advanced_area_w.setVisible(False)
        self._layout.addWidget(self._advanced_area_w, stretch=1)

        self._mode_selector.mode_changed.connect(self._on_mode_changed)
        # Veto du changement de mode pendant une génération / un upload : le
        # switch utilisateur (clic sur le sélecteur) est refusé tant qu'une
        # opération tourne (les switches programmatiques — chargement projet —
        # passent par _on_mode_changed directement et ne sont PAS vétés).
        self._mode_selector._can_switch = self._may_switch_mode
        self._on_mode_changed("beginner")

        # On each serial port open, the monitors read the current
        # code to detect Serial.begin(...) and adjust the baud combo.
        # The user can still override manually via the combo.
        self._serial_monitor.set_code_source(self._editor.toPlainText)
        self._serial_monitor_beg.set_code_source(self._editor.toPlainText)

        # Auto-connect: open the port when a board is detected (USB plug-in)
        board_manager.state_changed.connect(self._on_board_state_changed)

    # ── Automatic board connection ────────────────────────────

    def _on_board_state_changed(self, state: str):
        """Handle the USB unplug of the board (cleanup only).

        Intentionally, the serial port is NOT opened when the board
        appears (CONNECTED): at startup, if the Arduino already has code
        flashed with a baud different from the default (9600), auto-opening
        would generate a stream of badly decoded bytes, saturate the read
        loop and slow down the UI (click latencies). The connection is
        now made only on explicit action:
          - after an upload (cf compile_service, reopen_on_success)
          - or a click on "Connecter" (advanced mode)
        In both cases, `open_port()` first scans the code via
        `set_code_source` to tune the baudrate to Serial.begin(...).
        """
        if state != BoardState.CONNECTED:
            self._serial_monitor.close_port()
            self._serial_monitor_beg.close_port()

    # ── Event filter: read-only popup ────────────────────────
    # (merged with the _name_edit filter below, see eventFilter())

    def _show_advanced_nudge_popup(self):
        # Popup « passe en Avancé » (message 2 fenêtres) déclenchée après
        # MANUAL_EDIT_NUDGE_THRESHOLD segments d'édition manuelle en
        # Intermédiaire (#35). Réutilise l'ancienne popup readonly (rendue
        # dormante par #33) : centrée sur l'éditeur, boutons OK + « Passer en
        # Avancé ». Le message est le même que le bandeau (source unique).
        s = lang_manager.current
        c = theme_manager.current
        dlg = QDialog(self, Qt.WindowType.Popup)
        dlg.setWindowFlags(Qt.WindowType.Popup)
        dlg.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        lbl = QLabel(s.nudge_intermediate_to_advanced)
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"font-size: 10pt; color: {c.text_primary};")
        layout.addWidget(lbl)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        # Same control style as the rest of the app (cf. theme helpers):
        # « passer en mode » = PRIMARY (plein -> vert au survol : c'est l'action
        # principale du popup), OK = SECONDARY (filaire -> vert au survol).
        btn_ok = QPushButton(s.readonly_popup_ok)
        btn_ok.setFixedHeight(36)
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setStyleSheet(secondary_button_qss(c, radius=8, padding="0 24px"))
        btn_ok.clicked.connect(lambda: dlg.done(0))
        btn_switch = QPushButton(s.readonly_popup_switch)
        btn_switch.setFixedHeight(36)
        btn_switch.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_switch.setStyleSheet(primary_button_qss(c, radius=8, padding="0 20px"))
        btn_switch.clicked.connect(lambda: dlg.done(1))
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_switch)
        layout.addLayout(btn_row)
        dlg.setStyleSheet(f"""
            QDialog {{
                background-color: {c.sidebar_bg};
                border: 1px solid {c.border};
                border-radius: 12px;
            }}
        """)
        dlg.adjustSize()
        # Center on the editor
        geo = self._editor.geometry()
        pos = self._editor.mapToGlobal(geo.center())
        dlg.move(pos.x() - dlg.width() // 2, pos.y() - dlg.height() // 2)
        accepted = dlg.exec() == 1
        if accepted:
            self._mode_selector._select("advanced")

    def _show_overwrite_confirm(self, msg: str | None = None,
                                show_switch: bool = False) -> str:
        """
        Returns 'cancel', 'accept' or 'switch'.
        'switch' is only possible if show_switch=True.
        """
        s = lang_manager.current
        c = theme_manager.current
        dlg = QDialog(self, Qt.WindowType.Popup)
        dlg.setWindowFlags(Qt.WindowType.Popup)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        lbl = QLabel(msg if msg is not None else s.studio_overwrite_msg)
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"font-size: 10pt; color: {c.text_primary};")
        layout.addWidget(lbl)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        # Mêmes helpers que le reste : Annuler = SECONDARY (filaire -> vert),
        # « passer en mode » = PRIMARY (plein -> vert). « Remplacer » garde son
        # rouge destructif (pas de helper, c'est un signal d'action risquée).
        btn_cancel = QPushButton(s.studio_overwrite_cancel)
        btn_cancel.setFixedHeight(36)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(secondary_button_qss(c, radius=8, padding="0 20px"))
        btn_accept = QPushButton(s.studio_overwrite_accept)
        btn_accept.setFixedHeight(36)
        btn_accept.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_accept.setStyleSheet(danger_button_qss(c, font_weight=600))
        btn_cancel.clicked.connect(lambda: dlg.done(0))
        btn_accept.clicked.connect(lambda: dlg.done(1))
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_accept)
        if show_switch:
            btn_switch = QPushButton(s.studio_overwrite_switch)
            btn_switch.setFixedHeight(36)
            btn_switch.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_switch.setStyleSheet(primary_button_qss(c, radius=8, padding="0 20px"))
            btn_switch.clicked.connect(lambda: dlg.done(2))
            btn_row.addWidget(btn_switch)
        layout.addLayout(btn_row)
        dlg.setStyleSheet(f"""
            QDialog {{
                background-color: {c.sidebar_bg};
                border: 1px solid {c.border};
                border-radius: 12px;
            }}
        """)
        dlg.adjustSize()
        # Anchor: the editor if visible (inter/advanced modes), otherwise the
        # full view (beginner mode or hidden editor).
        anchor = self._editor if self._editor.isVisible() else self
        pos = anchor.mapToGlobal(anchor.rect().center())
        dlg.move(pos.x() - dlg.width() // 2, pos.y() - dlg.height() // 2)
        result = dlg.exec()
        if result == 1:
            return "accept"
        if result == 2:
            return "switch"
        return "cancel"

    # ── Visibility by mode ────────────────────────────────────

    def _mount_editor_console(self, mode_id: str):
        """Monte les widgets partagés (éditeur IA, contrôles compile IA,
        console, section d'outils du code) dans le conteneur du mode actif.
        Une seule instance de chaque -> aucun contenu/état perdu au changement
        de mode."""
        if mode_id == "advanced":
            self._adv_ia_editor_slot.layout().addWidget(self._code_panel)
            self._adv_ia_controls_slot.layout().addWidget(self._ia_controls_w)
            self._adv_console_slot.layout().addWidget(self._console_w)
            self._adv_ia_tools_slot.layout().addWidget(self._code_tools_w)
        else:
            self._int_editor_slot.layout().addWidget(self._code_panel)
            self._ia_controls_slot.layout().addWidget(self._ia_controls_w)
            self._int_console_slot.layout().addWidget(self._console_w)
            self._int_tools_slot.layout().addWidget(self._code_tools_w)

    def _may_switch_mode(self, mode_id: str) -> bool:
        """Veto du sélecteur : refuse un changement de mode UTILISATEUR pendant
        une génération (incl. vérif v2) ou un upload — sinon on masque/vide une
        opération en cours (console partagée, bouton « Annuler » qui part dans
        le conteneur caché…). Un tooltip explique le refus."""
        if self._gen_busy is not None or self._cu_running or self._beginner_running:
            from PyQt6.QtGui import QCursor
            QToolTip.showText(QCursor.pos(),
                              lang_manager.current.studio_mode_locked_busy)
            return False
        return True

    def _on_mode_changed(self, mode_id: str):
        self._current_mode = mode_id
        show = mode_id != "beginner"
        self._gen_col_w.setVisible(show)
        self._btn_generate.setVisible(show)
        self._beginner_row.setVisible(not show)
        self._beg_bottom_row_w.setVisible(not show)
        # _code_header_w = en-tête « Code » (commun). _code_compile_w
        # (Intermédiaire) vs _advanced_area_w (Avancé) : un seul visible.
        adv = mode_id == "advanced"
        # En Avancé, l'en-tête partagé « Code généré » est masqué (chaque
        # fenêtre a son propre titre + sa section d'outils) ; en Intermédiaire
        # il reste (titre + section d'outils reparentée dedans).
        self._code_header_w.setVisible(show and not adv)
        self._mount_editor_console(mode_id)
        self._code_compile_w.setVisible(show and not adv)
        self._advanced_area_w.setVisible(adv)
        # Console plus haute en Avancé (2 fenêtres, pleine largeur en bas) ; en
        # Intermédiaire elle retrouve son min naturel (110, colonne de droite —
        # inchangé). Le surplus de hauteur passe par le scroll vertical du
        # QScrollArea de contenu.
        self._adv_console.setMinimumHeight(240 if adv else 0)
        # Fenêtres de code 50% plus hautes en Avancé (2 éditeurs empilés + console
        # pleine largeur -> la vue dépasse souvent le viewport et rend les
        # éditeurs à leur hauteur MINIMALE ; on relève ce plancher). 280 (hérité
        # de CodePanel, partagé avec l'Intermédiaire) -> round(280 * 1.5) = 420.
        # Toggle par mode car `_code_panel` est reparenté (ne pas figer 420 côté
        # Intermédiaire). Le surplus passe par le scroll vertical du contenu.
        _code_h = 420 if adv else 280
        self._code_panel.editor.setMinimumHeight(_code_h)
        self._stable_panel.editor.setMinimumHeight(_code_h)
        # Comments slider reserved for Advanced mode: verbosity level
        # of the generated comments (None/Minimal/Standard/Detailed).
        self._comments_slider_w.setVisible(mode_id == "advanced")
        # "Moniteur série" checkbox reserved for Advanced mode.
        self._chk_serial_monitor.setVisible(mode_id == "advanced")
        if not show:
            self._hide_gen_error()
            # #12: NO LONGER cancel an in-progress generation on mode change.
            # It continues in the background; the indicator (loader « ◐ Annuler »)
            # is resynchronized at the end of the method on the displayed mode's button.
        # Serial send: visible only in advanced mode
        self._serial_monitor.set_send_visible(mode_id == "advanced")
        # Connect/Disconnect button: exposed in advanced AND intermediate
        # (user request). Auto-connect in beginner -> no button.
        self._serial_monitor.set_connect_visible(
            mode_id in ("advanced", "intermediate"))
        # Édition manuelle LIBRE dans tous les modes affichant l'éditeur (#33) :
        # le verrou Intermédiaire est retiré (la capture #31 « Éditions
        # manuelles » + le clic droit d'attribution s'appliquent donc aussi en
        # Intermédiaire). setReadOnly reste piloté UNIQUEMENT par le voile busy
        # (génération / vérif / upload), jamais par le mode.
        self._editor.setReadOnly(False)
        self._editor.set_edit_locked(False)
        # Template: displayed if the editor is empty in inter/advanced.
        # Also replace when the current content is a known template
        # (e.g. switching inter -> advanced must remove the comments).
        if mode_id in ("intermediate", "advanced"):
            current = self._editor.toPlainText()
            if not current.strip() or self._is_template_or_scaffolded(current):
                self._editor.setPlainText(lang_manager.editor_template())
                # When switching to advanced mode, if the box is checked, inject
                # Serial.begin into the template before any generation: it
                # will thus belong to the scaffolding, not the future f1.
                if mode_id == "advanced" and self._chk_serial_monitor.isChecked():
                    self._apply_serial_monitor_state(True, mark_dirty=False)
            # La fenêtre stable (Avancé) affiche AUSSI le squelette « avant
            # génération » tant qu'elle est vide/template.
            if mode_id == "advanced":
                self._ensure_stable_template()
        # Reset the iteration state on each mode change,
        # but keep _has_generated if real code (non-template) is
        # already present in the editor: the next click on Generate must
        # then display the overwrite confirmation. The template may
        # contain scaffolding (Serial.begin) injected by the checkbox —
        # that does not count as a user generation.
        current_code = self._editor.toPlainText()
        self._has_generated = (
            bool(current_code.strip())
            and not self._is_template_or_scaffolded(current_code)
        )
        self._last_prompt = ""
        self._refresh_action_button_styles()
        self._serial_monitor_beg.set_send_visible(False)

        # On mode change, close the other mode's monitor but
        # do NOT automatically open the target mode's: the port is
        # only opened on explicit action (upload or click on "Connecter") to
        # avoid connecting at a wrong baudrate at startup and saturating
        # the read loop (observed UI latencies).
        if show:
            self._serial_monitor_beg.close_port()
        else:
            self._serial_monitor.close_port()

        # #12: reflect the « generation in progress » state on the new mode's
        # button (loader « ◐ Annuler » if a generation is running, otherwise normal state).
        self._sync_generation_buttons()
        # Bandeau des fonctionnalités (puces) : visible seulement Int/Avancé.
        self._refresh_feature_chips()

        # (Re)signal the program state (« Code prêt : … » / « Aucun code
        # généré ») in the DISPLAYED mode's log — ALL MODES, not just
        # beginner. Log cleared first to avoid stacking on each
        # mode switch.
        (self._beg_output_area if mode_id == "beginner"
         else self._output_area).clear()
        self._beg_mark_program_ready()

    # ── AI context file ──────────────────────────────────────

    def _context_file_abs_path(self) -> Path | None:
        """Absolute path of the current project's context file, or None."""
        proj = self._current_project
        if proj is None or not proj.context_file_path:
            return None
        return proj.path / proj.context_file_path

    def _context_material(self) -> tuple[str, str]:
        """(name, truncated content) of the shared context file, for the push
        to the chat. ('', '') if no context. The content is truncated to
        100 KB to bound the chat's system prompt; code generation,
        for its part, reads the full file via `_inject_context`."""
        ctx = self._context_file_abs_path()
        if ctx is None or not ctx.exists():
            return "", ""
        try:
            content = ctx.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return "", ""
        MAX = 100_000
        if len(content) > MAX:
            content = content[:MAX]
        return ctx.name, content

    def _project_chip_hint(self) -> str:
        """Les puces que le sketch actuel utilise deja — « bme280 ds18b20 ».

        TODO #64. Sur un prompt de SUITE (« arrondis la temperature a un
        chiffre apres la virgule »), le retrieval ne voit que le prompt nu et
        injectait la bibliotheque d'une AUTRE puce de la meme famille. Cet
        indice ne pese que sur le CLASSEMENT des libs retrouvees — voir
        `rag._build_lib_context`, parametre `ranking_hint`.

        Lu sur le code AFFICHE, pas sur les fonctionnalites : c'est le sketch
        que l'utilisateur a sous les yeux et que la generation va modifier.
        Naturellement vide a la premiere generation (pas de code, pas
        d'indice), donc AUCUN test d'action n'est necessaire ici — et rien ne
        depend du mode, qui n'est qu'un affichage.
        """
        from .project_chips import chip_hint
        try:
            return chip_hint(self.get_code())
        except Exception:
            return ""

    def _context_full_text(self) -> str:
        """FULL content of the context file (for code generation,
        unlike `_context_material` truncated to 100 KB for the chat). ''
        if no context / file gone / empty / unreadable."""
        ctx_path = self._context_file_abs_path()
        if ctx_path is None:
            return ""
        try:
            content = ctx_path.read_text(encoding="utf-8")
        except Exception:
            return ""
        return content if content.strip() else ""

    def _inject_context(self, user_prompt: str) -> str:
        """Prepend the content of the context file to the user prompt
        (FULL generation):
            CONTEXT:
            <file content>

            TASK:
            <user prompt>

        Returns the prompt as-is if there is no context (generation must
        not fail because of that)."""
        content = self._context_full_text()
        if not content:
            return user_prompt
        return f"CONTEXT:\n{content}\n\nTASK:\n{user_prompt}"

    def _context_block(self) -> str:
        """Context block (attached file) to PREFIX to the
        Add / Modify instructions, read-only. Empty if no file. Separated from
        the prompt so as not to pollute the « NEW FEATURE » / « MODIFICATION
        REQUEST » sections of those instructions."""
        content = self._context_full_text()
        if not content:
            return ""
        return (f"CONTEXT (provided by the user, read-only — wiring / notes):\n"
                f"{content}\n\n")

    def _on_context_dropped(self, src_path: str, supported: bool):
        """Handler for dropping a file on the prompt's QPlainTextEdit.

        Copies the file into the project folder and updates
        project.context_file_path. Refuses cleanly if:
          - no current project (the user must at least create
            the Untitled project by clicking Generate once),
          - unsupported extension (.md/.txt only in V1),
          - read impossible (locked file, exotic encoding).
        """
        s = lang_manager.current
        title = s.studio_prompt_label  # « Générer une fonctionnalité » — generic title
        if not supported:
            QMessageBox.warning(self, title, s.studio_context_invalid_ext)
            return
        if self._current_project is None:
            if not self._auto_create_untitled():
                QMessageBox.warning(self, title, s.studio_context_need_project)
                return
        src = Path(src_path)
        try:
            # Preliminary check: readable as UTF-8.
            src.read_text(encoding="utf-8")
        except Exception:
            QMessageBox.warning(self, title, s.studio_context_read_error)
            return

        project = self._current_project
        # Destination: <project_folder>/<source_file_name>. Keep
        # the original name so the user can find their way, except on
        # collision with the project's .ino or .promptuino.json — in
        # that case rename to "context.md"/"context.txt".
        dest_name = src.name
        reserved = {project.ino_path.name, project.meta_path.name}
        if dest_name in reserved:
            dest_name = f"context{src.suffix.lower()}"
        dest = project.path / dest_name

        # If an old context existed with another name, remove it
        # so as not to leave an orphan file.
        old = self._context_file_abs_path()
        if old is not None and old.exists() and old.resolve() != dest.resolve():
            try:
                old.unlink()
            except Exception:
                pass

        try:
            shutil.copyfile(src, dest)
        except Exception:
            QMessageBox.warning(self, title, s.studio_context_read_error)
            return

        project.context_file_path = dest_name
        self._update_context_badge()
        # Re-push to the chat: the document becomes visible in the chip.
        self._emit_chat_context()
        self._mark_dirty()

    def attach_context_file(self, src_path: str) -> None:
        """Public entry point (used by the chat via MainWindow): routes a
        file dropped/chosen on the chat side to the shared context mechanism,
        validating the extension as for a drop on the prompt."""
        supported = Path(src_path).suffix.lower() in _CONTEXT_EXTS
        self._on_context_dropped(src_path, supported)

    def _on_context_removed(self):
        """Detach the context file from the project and remove it from the folder.

        The user can always re-drag it from its original
        location if needed. We don't keep an orphan in the project
        folder to avoid confusion."""
        project = self._current_project
        if project is None or not project.context_file_path:
            return
        ctx = self._context_file_abs_path()
        if ctx is not None and ctx.exists():
            try:
                ctx.unlink()
            except Exception:
                pass
        project.context_file_path = ""
        self._update_context_badge()
        # Re-push to the chat: the chip disappears along with the badge.
        self._emit_chat_context()
        self._mark_dirty()

    def _update_context_badge(self):
        """Synchronize the badge (empty/filled state) with the current project."""
        ctx = self._context_file_abs_path()
        if ctx is None or not ctx.exists():
            self._context_badge.clear_info()
        else:
            self._context_badge.set_info(ctx.name)
        # The file name changes the chip width -> reposition the overlay
        # so it stays stuck to the left of the « Joindre » button.
        if hasattr(self, "_prompt_field"):
            self._prompt_field._reposition_overlay()

    def _on_context_add_clicked(self):
        """Open a QFileDialog to choose a .md/.txt and route it to the
        same handler as drag&drop."""
        s = lang_manager.current
        path, _filter = QFileDialog.getOpenFileName(
            self,
            s.studio_context_picker_title,
            "",
            s.studio_context_picker_filter,
        )
        if not path:
            return
        supported = Path(path).suffix.lower() in _CONTEXT_EXTS
        self._on_context_dropped(path, supported)

    # ── AI generation ─────────────────────────────────────────

    # ── Task 11 orchestrator (dormant — wired in Task 12) ─────────────────────

    def _on_prompt_submit(self):
        """Enter in the prompt field -> start the current mode's generation.

        Ignored if a generation is already in progress (button disabled / beginner
        run) so as not to restart or cancel inadvertently."""
        if self._current_mode == "beginner":
            if not self._beginner_running and self._gen_busy is None:
                self._on_generate_and_send()
        elif self._gen_busy is None:
            self._on_generate_clicked()

    def _on_generate_clicked(self):
        """Single entry point inter/advanced.

        1st generation (no feature) → DIRECT regeneration, no modal.
        Otherwise → modal {Regenerate / Add / Modify}. Resolving the backend
        (potentially slow: `is_available`) is done AFTER the decision, so
        the modal opens instantly.
        """
        # #12: if a generation is running (started in any mode), the
        # button displays « ◐ Annuler » -> a click cancels instead of restarting.
        if self._gen_busy is not None or self._beginner_running:
            self._cancel_generation()
            return
        s = lang_manager.current
        prompt = self.get_prompt()
        if not prompt:
            self._show_gen_error(s.studio_err_no_prompt)
            return
        if not self._features:
            action, target_id = REGENERATE, None
        else:
            # TODO #88 : une demande de MODIFICATION déguisée en ajout (« le
            # clignotement ne doit avoir lieu QUE SI… ») ne peut pas être
            # rattrapée en aval — le contrat d'Ajout interdit au modèle de
            # toucher au code existant, il fabrique donc un second
            # comportement en parallèle (mesuré 2/2, ça compile et la demande
            # n'est pas satisfaite). On la reconnaît ICI et la modale s'ouvre
            # sur « Modifier <la bonne fonctionnalité> » — proposée, jamais
            # imposée.
            from .generation.add_router import modification_target
            cible_modif = modification_target(prompt, self._features)
            decision = self._open_action_modal(
                prompt,
                default_override=CORRECT if cible_modif else None,
                preselect_target_id=cible_modif,
                modification_hint=bool(cible_modif))
            if decision is None:
                return
            action, target_id = decision
        self._launch_generation(action, target_id, prompt)

    def _open_action_modal(self, prompt: str, *, default_override=None,
                           preselect_target_id=None,
                           modification_hint: bool = False):
        """Ouvre la modale {Régénérer/Ajouter/Modifier} et renvoie
        (action, target_id), ou None si annulée. `default_override` force
        l'action pré-cochée (cf. open_modify_flow) ; `preselect_target_id`
        pré-coche la fonction cible en mode Modifier ;
        `modification_hint` (#88) affiche la phrase qui EXPLIQUE la
        présélection quand elle vient du routeur — une présélection muette
        passerait pour un défaut arbitraire."""
        modal = GenerationModal(self._features, prompt, self,
                                preselect_target_id=preselect_target_id,
                                default_override=default_override,
                                modification_hint=modification_hint)
        if (modal.exec() != QDialog.DialogCode.Accepted
                or modal.result_choice is None):
            return None
        return modal.result_choice

    def _launch_generation(self, action, target_id, prompt: str,
                           *, from_scratch: bool = False,
                           forced_override=None) -> None:
        """Tail commun : crée le projet sans-titre, vérifie le backend, lance.

        `from_scratch` (↻ régénération par fonctionnalité) : régénère depuis le
        prompt sans fournir le code actuel — cf. `_start_generation`."""
        s = lang_manager.current
        if not self._auto_create_untitled():
            return
        self._hide_gen_error()
        self._set_generating(True)
        backend = get_backend_instance(ai_config.backend_id)
        if backend is None or not backend.is_available():
            self._set_generating(False)
            self._show_gen_error(s.studio_err_no_backend)
            return
        self._start_generation(backend, action, target_id, prompt,
                               from_scratch=from_scratch,
                               forced_override=forced_override)

    # ── Outils par fonctionnalité (dropdown + overlay ↻/🗑) ──────────────
    # (Sélection/survol + surlignage : gérés DANS le CodePanel — Prompt 3. Le
    # studio ne garde que les actions métier ↻/🗑, émises par l'overlay du
    # panneau et portant la sélection courante + une cible de fenêtre.)

    def _features_for(self, target: str) -> list:
        return self._stable_features if target == "stable" else self._features

    def _panel_for(self, target: str):
        return self._stable_panel if target == "stable" else self._code_panel

    def _editor_for(self, target: str):
        return self._panel_for(target).editor

    def _confirm_delete_features(self, ids: set, target: str) -> bool:
        """Confirmation de suppression (partagée IA/stable) : message enrichi
        de l'avertissement « retouches manuelles » si l'éditeur ciblé a été
        édité depuis son assemblage (dirty vs baseline de la fenêtre)."""
        s = lang_manager.current
        msg = s.feature_chips_delete_confirm.format(n=len(ids))
        editor = self._editor_for(target)
        baseline = self._code_baseline if target == "ia" else self._stable_baseline
        if is_dirty(editor.toPlainText(), baseline):
            msg += "\n\n" + s.feature_delete_dirty_warn
        return ask_yes_no(self, s.feature_select_delete_title, msg,
                          warning=True)

    def _on_chips_delete(self, ids: list, target: str = "ia"):
        """🗑 (overlay fonctionnalité) : supprime les fonctionnalités sélectionnées
        (déterministe), après confirmation — enrichie de l'avertissement
        « retouches manuelles » si le code a été édité depuis l'assemblage.
        `target` (« ia »/« stable ») = fenêtre d'origine."""
        ids = set(ids)
        if not ids:
            return
        if not self._confirm_delete_features(ids, target):
            return
        self._delete_features(ids, target=target)

    def _delete_features(self, ids: set, target: str = "ia"):
        """Retire les fonctionnalités `ids` : ré-assemble depuis les restantes,
        nettoie les métadonnées tied-to-fn_id, sauve. Pas de vérif/recombine
        (suppression déterministe et voulue). `target` route vers la fenêtre
        IA (chemin existant) ou stable (`_delete_stable_features`)."""
        if target == "stable":
            self._delete_stable_features(ids)
            return
        # --- IA : chemin existant, INCHANGE (ne pas modifier) ---
        remaining = [f for f in self._features if f.id not in ids]
        # État AVANT (cible d'un Ctrl+Z) puis APRÈS, comme Ajouter/Modifier.
        # L'index AVANT capture aussi les métadonnées câblage intactes -> un
        # Ctrl+Z restaure fonctionnalités ET résolutions (cf. _index_features).
        self._index_features(self.get_code(), self._features)
        self._features = remaining
        # Nettoyage des métadonnées indexées par fn_id AVANT l'index APRÈS
        # (sinon un redo restaurerait des métadonnées de fn_id supprimés).
        self._wiring_resolutions = _strip_feature_metadata(self._wiring_resolutions, ids)
        self._implicit_actions = _strip_feature_metadata(self._implicit_actions, ids)
        self._commit_generated_code(assemble(remaining), remaining)
        self._last_prompt = self.get_prompt()
        self._refresh_action_button_styles()
        self._refresh_feature_chips()
        s = lang_manager.current
        self._active_output_area().begin_phase(
            s.feature_deleted_msg, theme_manager.current.text_secondary)

    def _delete_stable_features(self, ids: set):
        """Suppression deterministe cote fenetre stable : re-assemble depuis les
        restantes, ecrit dans l'editeur stable (undoable), persiste. Pas de
        verif/IA. Index AVANT/APRES -> la suppression est annulable (Ctrl+Z)."""
        self._index_stable_features(self._stable_panel.editor.toPlainText())
        remaining = [f for f in self._stable_features if f.id not in ids]
        self._stable_features = remaining
        code = assemble(remaining)
        self._set_stable_code(code)              # undoable (suppresses resync)
        self._reset_comments_state("stable")     # code complet -> case Commentaires cochée
        self._stable_baseline = code
        self._update_code_meta()
        self._refresh_stable_features()          # repeuple dropdown + attribution
        self._index_stable_features(code)
        self.save_project()
        s = lang_manager.current
        self._active_output_area().begin_phase(
            s.feature_deleted_msg, theme_manager.current.text_secondary)

    def _refresh_stable_features(self):
        """Dropdown + surlignage de la fenetre stable depuis _stable_features.
        Le dropdown stable se grise aussi pendant une generation IA / un upload
        (symetrique de _refresh_feature_chips), pas seulement quand la fenetre
        stable elle-meme est voilee (sinon 🗑 stable actif pendant l'operation)."""
        busy = (self._gen_busy is not None or self._cu_running
                or self._stable_panel.is_busy())
        self._stable_panel.set_features(self._stable_features, busy)
        self._reattribute(self._stable_panel.editor, self._stable_features)

    def _reattribute(self, editor, features):
        """(Re)pose la carte lignes->fonctionnalite d'un editeur depuis `features`
        (meme logique 3-cas que load_project pour l'IA)."""
        from .code_format import reindent_code
        code_now = editor.toPlainText()
        asm_code, asm_map = assemble_with_map(features)
        if reindent_code(asm_code) == code_now or asm_code == code_now:
            editor.set_line_owners(asm_map)
        elif len(features) == 1 and not is_dirty(code_now, reindent_code(asm_code)):
            editor.set_line_owners(single_feature_map(code_now, features[0].id))
        else:
            lines = code_now.split("\n")
            editor.set_line_owners(match_contributions(lines, features, [None] * len(lines)))

    def _on_chips_regen(self, ids: list, target: str = "ia"):
        """↻ (overlay fonctionnalité) : régénère les fonctionnalités sélectionnées
        depuis leur(s) prompt(s). 1 = remplacement en place ; ≥2 = fusion.
        Interdit hors fenêtre IA (la fenêtre stable n'a pas de ↻)."""
        if target != "ia":
            return   # régénération interdite hors fenêtre IA (garde)
        if ids:
            self._regenerate_features(set(ids))

    def _regenerate_features(self, ids: set):
        selected = [f for f in self._features if f.id in ids]
        if not selected:
            return
        target, prompt = _regen_plan(selected)
        # _on_generation_done lit get_prompt() pour le .prompt de la fonctionnalité
        # (re)générée -> on synchronise le champ avec le prompt réinjecté.
        self.set_prompt(prompt)
        # Swaps de puce persistés : le forçage de libs est déjà ré-appliqué par
        # `_apply_lib_overrides`, mais le prompt ci-dessus NOMME encore
        # l'ancienne puce et le modèle suit le prompt -> elle revenait (QA B1).
        # La consigne s'ajoute au prompt ENVOYÉ, jamais au champ visible
        # (set_prompt ci-dessus) : c'est un prompt interne, pas une saisie.
        sent_prompt = _prompt_with_lib_overrides(prompt, selected)
        # ↻ = VRAIE régénération : on repart du/des prompt(s), PAS du code actuel
        # (sinon le chemin « Modifier » renverrait le même code -> no-op). La
        # fusion reste celle de CORRECT (remplace la/les fonctionnalité(s) ciblée(s),
        # garde les autres). `from_scratch` ne change que la construction du prompt.
        self._launch_generation(CORRECT, target, sent_prompt, from_scratch=True)

    def _open_declare_dialog(self, component):
        """Open the declaration form for `component`. Returns the
        DeclaredComponent, or None if the user cancelled."""
        from .wiring.declare_component_dialog import (
            DeclareComponentDialog, resolve_board_nets,
        )
        dlg = DeclareComponentDialog(
            self, component=component, board_nets=resolve_board_nets(),
            lang=lang_manager.lang)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return dlg.result_component

    def _open_declare_dialog_for_entry(self, entry) -> bool:
        """Open the declaration form directly on an already-declared entry:
        the pencil on a custom tile in the beginner ambiguity modal (#38,
        wired 2026-07-30). Edits the entry the tile represents, independent
        of any single netlist component -- unlike `_open_declare_dialog`,
        there is no result to feed back into a choice.

        Returns True when the form was accepted (saved OR removed), so the
        caller can refresh whatever displays the library: the entry may have
        been renamed, or removed altogether.

        Capture `old_lib` AVANT d'ouvrir, et previens ensuite : sans ca, changer
        la librairie depuis CETTE porte modifiait bien `components.json` mais ne
        proposait ni regeneration ni avertissement `lib_swap_unchecked` — le code
        continuait de referencer l'ancienne librairie EN SILENCE (signale a
        l'ecran le 2026-08-12, TODO #52). C'est le meme defaut qu'en QA I6 : une
        porte deplacee sans rebrancher ce qu'il y avait derriere. La fiche de
        l'onglet « Composants » le faisait deja
        (`main_window._notify_lib_chosen_in_form`) ; les deux crayons du schema
        etaient restes muets."""
        from .wiring.declare_component_dialog import (
            DeclareComponentDialog, resolve_board_nets,
        )
        old_lib = getattr(entry, "lib", "") or ""
        dlg = DeclareComponentDialog(
            self, component=None, existing=entry, board_nets=resolve_board_nets(),
            lang=lang_manager.lang)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False
        self.notify_lib_chosen_in_form(old_lib, dlg.result_component)
        return True

    def notify_lib_chosen_in_form(self, old_lib: str, saved) -> None:
        """Point de passage UNIQUE des portes du schema vers l'offre de
        regeneration, apres une edition d'entree declaree dans le formulaire.

        Public parce que `AmbiguityDialog` (mode avance) n'a aucun acces au
        Studio et doit y arriver par un signal — cf. `lib_changed_in_form`.

        Muet quand rien n'a ete sauve (formulaire annule, ou entree supprimee :
        `result_component` est alors None) et quand la librairie n'a PAS change
        — proposer de regenerer un code qui reference deja la bonne librairie
        serait du bruit.

        Le jeton est le **nom** de l'entree en minuscules, jamais son id :
        `_declared_lookup_token` en est la source de verite, et c'est sous ce
        nom que le retour d'ecriture a rempli le cache.
        """
        if saved is None:
            return
        new_lib = (saved.lib or "").strip()
        if (old_lib or "").strip() == new_lib:
            return
        self.on_lib_chosen_in_form(_declared_lookup_token(saved),
                                   old_lib, new_lib)

    # ── Régénération après changement de composant dans le schéma (Task 9) ──
    def _resolve_wiring_netlist_tracked(self, code, board_id, prompt, context,
                                        prompts_by_fn, *, force_remodal=False,
                                        scoped_to_ref=None):
        """Wrapper de `_resolve_wiring_netlist` passé au WiringDiagramDialog :
        détecte quand une édition remplace une puce DÉTECTÉE PAR SIGNATURE par
        un autre type qui change les libs du code (cf.
        `_chip_swap_regen_target` : puce→puce OU puce→composant nu). Propose
        AUSSITÔT (à la validation du nouveau composant) de régénérer ; si oui, on
        ferme le schéma et la régénération part à sa fermeture (un seul popup).

        ⚠️ Le tracking couvre les DEUX portes depuis la QA AC1 (2026-08-31) :
        l'engrenage (scoped_to_ref) ET « Modifier les composants » (non
        scopé). Ce wrapper disait « le cas non scopé n'a pas besoin de
        tracking : la modale non scopée ne voit que les composants low » —
        un invariant que le #81 a rendu FAUX en rendant tout composant
        éditable (`collect_all_editable`). Conséquence mesurée : un swap
        écran → LED validé par cette porte n'offrait jamais la
        régénération, en silence. On photographie donc TOUTES les puces
        signature avant résolution, et on compare par ref après (les
        transforms conservent la ref) ; une seule question par validation,
        comme la branche moteur de la boucle d'acceptation."""
        dlg = getattr(self, "_open_wiring_dialog", None)
        cur_nl = getattr(dlg, "_netlist", None) if dlg is not None else None
        before: dict[str, tuple[str, str]] = {}
        if cur_nl is not None:
            for c0 in cur_nl.components:
                if c0.attributes.get("signature_detected"):
                    before[c0.ref] = (c0.type, c0.fn_id or "")
        nl = self._resolve_wiring_netlist(
            code, board_id, prompt, context, prompts_by_fn,
            force_remodal=force_remodal, scoped_to_ref=scoped_to_ref)
        if (nl is not None and before
                and getattr(self, "_pending_regen_swap", None) is None):
            for c1 in nl.components:
                old = before.get(c1.ref)
                if old is None or old[0] == c1.type:
                    continue
                old_type, fn_id = old
                # ⛔ Exemption #84 : un swap entre drivers pas-a-pas step/dir
                # (a4988 <-> drv8825...) n'offre JAMAIS la regeneration — ils
                # sont broche-a-broche compatibles et le code AccelStepper est
                # agnostique. La generalisation « deux portes » (QA AC1) avait
                # perdu cette asymetrie voulue : la popup affirmait « le code
                # decrit encore un a4988 », ce qui est faux — le code ne
                # decrit aucun driver (rattrape en QA AD1, 2026-08-31).
                if (old_type in _stepper_types()
                        and c1.type in _stepper_types()):
                    continue
                tgt = _chip_swap_regen_target(old_type, c1.type)
                if tgt is None:
                    continue
                fn = (fn_id or (c1.fn_id or "")
                      or self._feature_for_chip_swap(old_type, tgt))
                if fn and self._confirm_regen_after_swap(old_type, tgt):
                    # Décision prise ICI (à la validation) : on mémorise et on
                    # ferme le schéma ; la régénération part à sa fermeture.
                    self._pending_regen_swap = (fn, old_type, tgt)
                    dlg = getattr(self, "_open_wiring_dialog", None)
                    if dlg is not None:
                        from PyQt6.QtCore import QTimer
                        QTimer.singleShot(0, dlg.accept)
                # Une seule question par validation — qu'elle ait été
                # acceptée ou refusée (même règle que `_swap_deja_demande`
                # dans la boucle d'acceptation).
                break
        return nl

    def _process_pending_chip_swaps(self) -> None:
        """À la fermeture du schéma : régénère la fonctionnalité si l'utilisateur
        a accepté au moment de la validation du nouveau composant (le popup et la
        décision ont lieu là, pas ici)."""
        swap = getattr(self, "_pending_regen_swap", None)
        self._pending_regen_swap = None
        if swap is None:
            return
        fn_id, old_type, new_type = swap
        self._regenerate_feature_with_chip(fn_id, old_type, new_type)

    def _feature_for_chip_swap(self, old_type: str, new_type: str) -> str:
        """Retrouve la feature concernée par un swap quand le composant détecté
        n'a pas de fn_id (cas I2C). Feature unique -> elle ; sinon celle dont le
        prompt matche la famille fonctionnelle de la puce ; sinon ''."""
        if len(self._features) == 1:
            return self._features[0].id
        from .clarification_groups import (functions_of_component,
                                           functions_in_prompt)
        fams = functions_of_component(old_type) | functions_of_component(new_type)
        if fams:
            for f in self._features:
                if set(functions_in_prompt(f.full_prompt())) & fams:
                    return f.id
        return ""

    def _confirm_regen_after_swap(self, old_type: str, new_type: str) -> bool:
        """Demande si l'utilisateur veut régénérer le code après avoir changé
        une puce dans le schéma (le code garde encore l'ancienne puce)."""
        from PyQt6.QtWidgets import QMessageBox
        from .wiring.replacement_catalog import label_of
        s = lang_manager.current
        old_lbl = label_of(old_type) or old_type
        new_lbl = label_of(new_type) or new_type
        box = QMessageBox(self)
        box.setWindowTitle(s.chip_swap_regen_title)
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(s.chip_swap_regen_body.format(old=old_lbl, new=new_lbl))
        yes = box.addButton(s.chip_swap_regen_yes,
                            QMessageBox.ButtonRole.AcceptRole)
        box.addButton(s.chip_swap_regen_no, QMessageBox.ButtonRole.RejectRole)
        try:
            from .theme import messagebox_qss
            box.setStyleSheet(messagebox_qss(theme_manager.current))
        except Exception:
            pass
        box.exec()
        return box.clickedButton() is yes

    def _regenerate_feature_with_chip(self, fn_id: str, old_type: str,
                                      new_type: str) -> None:
        """Régénère UNIQUEMENT la fonctionnalité `fn_id` en forçant la NOUVELLE
        puce (et en retirant l'ancienne du forçage) — réutilise le chemin de
        régénération par fonctionnalité (comme le bouton ↻).

        Le choix est PERSISTÉ sur la Feature (banned/forced_lib_ids, sauvés
        dans .promptuino.json) : les ↻ ultérieurs le ré-appliquent via
        `_apply_feature_lib_overrides` — sans ça, le prochain ↻ recalculait le
        défaut RAG et l'ancienne puce revenait en silence.

        old_cid/new_cid passent par `_corpus_id` (module-level, PAS
        `corpus_id_of_type` seule) depuis #82 : c'était la SECONDE autorité
        qui divergeait de `_chip_swap_regen_target` — un swap l298n->drv8833
        y rendait `new_entry=None` malgré une entrée corpus réelle, donc
        aucun `forced_lib_ids`, et la consigne ci-dessous disait « stop using
        the L298N » sans jamais dire d'utiliser celle du DRV8833.

        ✅ La trouvaille de la revue du 2026-08-29 est CORRIGÉE (#85,
        2026-08-31). Quand `new_cid` est vide (cible NUE, ex. servo -> relay),
        `old_cid` est banni SANS remplaçant — et jusqu'au #85 la génération
        suivante en payait deux prix mesurés : `_apply_lib_overrides` rendait
        `[]` (liste vide, pas None), ce qui coupait TOUT le retrieval RAG (une
        feature servo+capteur perdait aussi le contexte du capteur) ; et la
        lib bannie revenait quand même en bloc IMPÉRATIF par le sauvetage des
        puces nommées de `_build_lib_context` dès que le prompt l'écrivait.
        Désormais le ban descend séparément (`_banned_lib_ids` →
        `rag.build_lib_context(banned_libs=…)`), le retrieval tourne filtré,
        et un ban est inconditionnel (nommer la puce ne la ramène pas — le
        swap est postérieur au prompt). La persistance d'un ban sans
        remplaçant, elle, reste voulue depuis 64c4ef4 : c'est elle qui fait
        lâcher la lib au code régénéré (`test_bare_target_regenerates_to_
        drop_lib`)."""
        from .rag import corpus_entry, forced_libs_for_generation
        from .wiring.replacement_catalog import label_of
        from .wiring.instructions import _label as _type_label
        feat = next((f for f in self._features if f.id == fn_id), None)
        if feat is None:
            return
        # `label_of` ne connaît que le catalogue de remplacement et rend None
        # pour les types du câblage (mesuré : oled_ssd1306, sh1106, led). Le
        # repli sur le type BRUT envoyait au modèle « Replace the oled_ssd1306
        # with a sh1106 » — des identifiants internes là où une phrase lisible
        # était prévue (QA B1-bis, 2026-08-08). `_type_label` porte le nom
        # humain ×4 langues ; on le prend en ANGLAIS, comme toute consigne
        # machine du prompt.
        new_lbl = label_of(new_type) or _type_label(new_type, "en") or new_type
        old_lbl = label_of(old_type) or _type_label(old_type, "en") or old_type
        old_cid = _corpus_id(old_type)
        new_cid = _corpus_id(new_type)
        new_entry = corpus_entry(new_cid) if new_cid else None
        # Persistance du swap : l'ancienne lib est bannie, la nouvelle forcée.
        # Un re-swap qui revient à l'ancienne puce la dé-bannit (symétrique).
        if old_cid:
            if old_cid not in feat.banned_lib_ids:
                feat.banned_lib_ids.append(old_cid)
            if old_cid in feat.forced_lib_ids:
                feat.forced_lib_ids.remove(old_cid)
        if new_cid:
            if new_cid in feat.banned_lib_ids:
                feat.banned_lib_ids.remove(new_cid)
            if new_entry is not None and new_cid not in feat.forced_lib_ids:
                feat.forced_lib_ids.append(new_cid)
        self.save_project()
        base = forced_libs_for_generation(feat.full_prompt())
        forced = [lib for lib in base if lib.get("id") != old_cid]
        if new_entry is not None and all(
                lib.get("id") != new_entry.get("id") for lib in forced):
            forced.append(new_entry)
        # Directive en ANGLAIS, comme toutes les consignes machine du prompt
        # (Serial, FEATURE_SUMMARY…) — le prompt utilisateur reste dans sa
        # langue, la consigne n'a pas à en changer (revue 2026-07-29 #6).
        if new_entry is not None:
            swap_note = (f"Replace the {old_lbl} with a {new_lbl}: use the "
                         f"{new_lbl} library and API, not the {old_lbl} ones.")
        else:
            # Cible sans lib propre (LED nue…) : la consigne est de LÂCHER la
            # lib de l'ancienne puce, pas d'en adopter une nouvelle.
            swap_note = (f"Replace the {old_lbl} with a {new_lbl}: stop using "
                         f"the {old_lbl} library and API.")
        prompt = feat.full_prompt().rstrip() + "\n\n" + swap_note
        # NB : on ne touche PAS au champ prompt visible (set_prompt) — le texte
        # assemblé ici est un prompt interne de régénération, pas une saisie
        # utilisateur (revue 2026-07-29 : il partait ensuite dans Générer/
        # Ajouter comme si l'utilisateur l'avait écrit).
        self._launch_generation(CORRECT, fn_id, prompt, from_scratch=True,
                                forced_override=(forced or None))

    def _offer_non_blocking_rewrite(self) -> None:
        """TODO #89 — après livraison : si une fonctionnalité fige la boucle
        et qu'une AUTRE lit une entrée, le dire et proposer de la réécrire
        sans `delay()`.

        Mesuré le 2026-08-31 : 6 fonctionnalités générées sur 8 bloquent
        (médiane 2 000 ms), et la conversion rend 3/3 un code qui compile,
        sans blocage restant ni attente active. Le défaut est donc fréquent
        ET le remède marche — les deux conditions pour mériter une offre.

        ⚠️ **Une seule question par fonctionnalité bloquante.** Un refus se
        mémorise (`_blocking_offer_declined`) : re-proposer à chaque
        génération suivante ferait de l'avertissement du décor, et le décor
        finit par ne plus être lu (leçon des nudges, QA G3). La mémoire est
        volontairement en SESSION et non sur disque : elle vaut pour le
        travail en cours, et rouvrir le projet plus tard reposera la
        question — l'utilisateur aura peut-être changé d'avis, ou ajouté la
        fonctionnalité que le blocage gêne vraiment.

        Silencieux dans tous les autres cas : une seule fonctionnalité, un
        blocage sous le seuil, ou aucune victime (personne ne lit d'entrée).
        """
        if self._gen_busy is not None or self._beginner_running:
            return
        from .generation.blocking_scan import find_conflict, non_blocking_directive
        conflit = find_conflict(self._features)
        if conflit is None:
            return
        if conflit.blocker_id in getattr(self, "_blocking_offer_declined", set()):
            return
        feat = next((f for f in self._features
                     if f.id == conflit.blocker_id), None)
        if feat is None:
            return
        from .generation import feature_combo_label
        victimes = ", ".join(
            feature_combo_label(f) for f in self._features
            if f.id in conflit.victim_ids)
        s = lang_manager.current
        from PyQt6.QtWidgets import QMessageBox
        box = QMessageBox(self)
        box.setWindowTitle(s.blocking_offer_title)
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(s.blocking_offer_body.format(
            feature=feature_combo_label(feat),
            sec=f"{conflit.blocker_ms / 1000:.1f}".rstrip("0").rstrip("."),
            victims=victimes))
        oui = box.addButton(s.blocking_offer_yes,
                            QMessageBox.ButtonRole.AcceptRole)
        box.addButton(s.blocking_offer_no, QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not oui:
            self._blocking_offer_declined = (
                getattr(self, "_blocking_offer_declined", set())
                | {conflit.blocker_id})
            return
        # Régénération de la SEULE fonctionnalité bloquante, par le chemin du
        # swap de puce : prompt interne (le champ visible n'est pas touché —
        # ce texte est une consigne machine, pas une saisie utilisateur) et
        # `from_scratch` pour rejouer l'intention complète.
        prompt = (feat.full_prompt().rstrip() + "\n\n"
                  + non_blocking_directive())
        self._launch_generation(CORRECT, feat.id, prompt, from_scratch=True)

    def open_modify_flow(self, seed: str) -> None:
        """Flux « Modifier » GUIDÉ (déclenché par le chat). Affiche d'abord un
        popup expliquant qu'on passe en mode Intermédiaire et qu'il faut cliquer
        sur « Générer » puis « Modifier ». Si l'utilisateur confirme : bascule en
        Intermédiaire (si Débutant) et recopie le texte dans le prompt — mais on
        ne clique PAS « Générer » à sa place (geste pédagogique : l'élève
        découvre le bouton Générer et l'option Modifier)."""
        if not self._confirm_modify_guidance():
            return
        if self._current_mode == "beginner":
            self._mode_selector._select("intermediate")
        self.set_prompt(seed)

    def _confirm_modify_guidance(self) -> bool:
        """Popup explicatif du flux « Modifier depuis le chat ». True si
        l'utilisateur confirme (on bascule + on remplit le prompt), False s'il
        annule. Boutons : Annuler (secondary) puis Compris (primary)."""
        s = lang_manager.current
        c = theme_manager.current
        dlg = QDialog(self)
        dlg.setWindowTitle(s.modify_guidance_title)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        lbl = QLabel(s.modify_guidance_body)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"font-size: 10pt; color: {c.text_primary};")
        layout.addWidget(lbl)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_cancel = QPushButton(s.gen_modal_cancel)
        btn_cancel.setAutoDefault(False)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(secondary_button_qss(c, radius=8, padding="6px 16px"))
        btn_cancel.clicked.connect(lambda: dlg.done(0))
        btn_ok = QPushButton(s.modify_guidance_ok)
        btn_ok.setAutoDefault(True)
        btn_ok.setDefault(True)
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setStyleSheet(primary_button_qss(c, radius=8, padding="6px 16px"))
        btn_ok.clicked.connect(lambda: dlg.done(1))
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)
        dlg.setStyleSheet(
            f"QDialog {{ background-color: {c.sidebar_bg}; }} "
            f"QLabel {{ background: transparent; }}"
        )
        return dlg.exec() == 1

    def _correct_targets(self, target) -> list:
        """Features targeted by a CORRECT action, in the order of
        `self._features`. Accepts a list of ids (multi-selection from the modal)
        OR a single id (compat / legacy persistence). Ignores vanished ids."""
        if isinstance(target, (list, tuple, set)):
            ids = set(target)
        elif target is not None:
            ids = {target}
        else:
            ids = set()
        return [f for f in self._features if f.id in ids]

    def _start_generation(self, backend, action, target_id, prompt,
                          *, from_scratch: bool = False, forced_override=None):
        self._hide_gen_error()
        # v2 — baseline de revert : éditeur + features AVANT cette génération.
        # Capturé ICI, avant toute mutation. Sur échec final de la vérif on y
        # revient (1ʳᵉ génération -> template vide ; code antérieur -> ce code).
        self._gen_revert_code = self.get_code()
        self._gen_revert_features = [copy.deepcopy(f) for f in self._features]
        # Annule une vérif encore en cours (génération relancée pendant la vérif).
        if self._verify_worker and self._verify_worker.isRunning():
            self._verify_worker.cancel()
            self._verify_worker.wait(2000)
        forced = (forced_override if forced_override is not None
                  else self._resolve_lib_ambiguity(prompt))
        # Swaps de puce persistés sur les features ciblées (schéma) : bans et
        # forçages ré-appliqués à CHAQUE régénération (idempotent — y compris
        # sur le forced_override du swap lui-même). Les bans descendent
        # SÉPARÉMENT jusqu'au RAG (#85) : ils filtrent l'injection au lieu de
        # couper le retrieval.
        banned_libs: frozenset[str] = frozenset()
        if action == CORRECT:
            targets = self._correct_targets(target_id)
            forced = _apply_lib_overrides(forced, targets)
            banned_libs = _banned_lib_ids(targets)
        self._pending_action = (action, target_id)
        # ↻ (from_scratch) vs Modifier : lu par _on_generation_done pour
        # l'historique des prompts (un ↻ rejoue l'intent existant, il ne
        # doit PAS y appendre le prompt réinjecté — doublon sinon).
        self._pending_from_scratch = bool(from_scratch)
        # Bannière registre d'une génération précédente : obsolète.
        self._registry_banner.setVisible(False)
        # Composant hors-corpus (spec 2026-07-29) : un part-number inconnu du
        # corpus rend le retrieval sémantique toxique (des libs SANS RAPPORT
        # passent le plancher 0.50 sur le bruit de la phrase). On le coupe et
        # on interroge le registre Arduino à la place — en worker, car
        # l'installation de la lib est réseau. La suite du flux vit dans
        # _continue_generation.
        from .registry_lookup import RegistryLookupWorker
        # TODO #40 (part 1): whether the eventual `forced_libs` may safely be
        # SUPPLEMENTED with normal retrieval (declared-component trigger) or
        # must stay fully suppressed (unknown-part-number trigger — measured
        # toxic, see registry_lookup's module docstring). The arbitration
        # lives in `_registry_request`, shared with the beginner path.
        unknown, preferred, declared_component_forced = \
            self._registry_request(prompt)
        if unknown:
            self._set_generating(True)
            self._start_gen_loader()
            self._registry_worker = RegistryLookupWorker(
                unknown, self._registry_config_file(),
                preferred_libs=preferred,
                search_queries=self._registry_search_queries)
            self._registry_worker.done.connect(
                lambda results: self._continue_generation(
                    backend, action, target_id, prompt,
                    forced=forced, registry_results=results,
                    declared_component_forced=declared_component_forced,
                    banned_libs=banned_libs))
            self._registry_worker.start()
            return
        self._continue_generation(backend, action, target_id, prompt,
                                  forced=forced, registry_results=None,
                                  declared_component_forced=declared_component_forced,
                                  banned_libs=banned_libs)

    def _registry_request(self, prompt: str) -> tuple[list[str], dict, bool]:
        """(tokens à chercher au registre, préférences de lib, déclaré-forcé).

        Extrait de `_start_generation` pour être partagé avec le chemin
        DÉBUTANT, qui ne l'appelait pas du tout : une puce hors-corpus y
        passait sans recherche, sans bannière et sans en-têtes réels, et le
        modèle inventait un `#include` (QA G6, 2026-08-08). Le mode n'est
        qu'un affichage — le prompt envoyé doit être le même. C'est la
        duplication de cette logique qui avait laissé les deux chemins
        diverger, d'où la mise en commun plutôt qu'une seconde copie.

        ⚠️ **Effet de bord sur `self`, en plus des trois valeurs rendues** :
        deux tables sont RÉÉCRITES à chaque appel, pour les tokens issus d'une
        référence de module sérigraphiée (spec 2026-08-20) —
        `self._registry_aliases` ({token: alias}, lue par
        `_apply_registry_results` pour nommer l'alias ET la puce) et
        `self._registry_search_queries` ({token: requête registre}, passée au
        worker). Elles ne sont pas rendues avec le reste parce que la
        signature à trois valeurs est dépaquetée aux deux chemins de
        génération ; les deux tables valent pour la génération en cours
        seulement, d'où la remise à zéro plutôt qu'un cumul.
        """
        from .registry_lookup import _MAX_UNKNOWN_TOKENS, detect_unknown_part_tokens
        from .component_libs import no_library_for
        unknown = detect_unknown_part_tokens(prompt)
        # Capturé AVANT l'ajout du token déclaré : un prompt qui nomme À LA
        # FOIS un composant déclaré et un vrai part-number inconnu ne doit
        # jamais être traité comme déclaré-seul (cf. TODO #40 partie 1).
        has_unknown_part_token = bool(unknown)
        preferred: dict[str, str] = _preferred_libs_for_tokens(unknown)
        declared_req = _declared_lookup_request(prompt)
        declared_component_forced = (declared_req is not None
                                     and not has_unknown_part_token)
        if declared_req is not None:
            token, pref_lib = declared_req
            if token not in unknown:
                # Re-tronqué APRÈS l'ajout : le plafond est appliqué dans
                # detect_unknown_part_tokens, et le token abandonné est
                # toujours un part-number DÉTECTÉ, jamais le déclaré.
                unknown = [*unknown[:_MAX_UNKNOWN_TOKENS - 1], token]
            if pref_lib:
                preferred[token] = pref_lib
        # Silkscreened module reference ("HW-617") whose chip carries a
        # VERIFIED library but no corpus document: search that library by the
        # same off-corpus pipeline. The alias is remembered so the banner can
        # say "HW-617 recognised as TCA9548A" rather than pretending the user
        # typed the chip name. Shares the SAME token budget as real unknown
        # part-numbers -- a module must not buy itself extra lookups.
        #
        # The token is the CHIP id, never the library name: it is what the
        # cache, the ad-hoc corpus entry, the "Composants" card and the banner
        # all show (see `hardware_modules.module_chips_needing_lookup` and
        # `registry_lookup.lookup_component`). The verified library name is
        # only what gets typed into the registry search.
        from .hardware_modules import module_chips_needing_lookup
        self._registry_aliases = {}
        self._registry_search_queries = {}
        for lib_name, chip_id, alias in module_chips_needing_lookup(prompt):
            if len(unknown) >= _MAX_UNKNOWN_TOKENS:
                break
            token = (chip_id or "").strip().lower()
            if not token or token in unknown:
                continue
            unknown.append(token)
            # A preference the USER stored for this chip WINS over the
            # registry's verified name. `_preferred_libs_for_tokens` ran
            # before this token existed, so it has to be asked again here --
            # without it, "Changer de bibliothèque" was decorative for module
            # chips (the choice was silently overwritten on every generation)
            # and `_preference_was_overridden` then announced that the user's
            # library was "introuvable au registre", which nothing had checked.
            preferred[token] = (_preferred_libs_for_tokens([token]).get(token)
                                or lib_name)
            self._registry_search_queries[token] = lib_name
            self._registry_aliases[token] = alias
        # TODO #51 — l'affirmation « aucune bibliotheque » COUPE la recherche.
        #
        # ⚠️ Filtrer ici, et pas plus loin, est le coeur du correctif : laisser
        # le jeton partir au registre reviendrait a chercher ce que
        # l'utilisateur vient de dire inutile, et surtout a laisser un resultat
        # « trouve » CONTREDIRE son affirmation -- l'app forcerait une
        # bibliotheque contre son avis explicite, en silence. C'est aussi
        # gratuit : une recherche en moins, et un jeton rendu au budget.
        no_lib = [tok for tok in unknown if no_library_for(tok)]
        if no_lib:
            unknown = [tok for tok in unknown if tok not in set(no_lib)]
            for tok in no_lib:
                preferred.pop(tok, None)
                self._registry_search_queries.pop(tok, None)
        self._registry_no_library = no_lib
        return unknown, preferred, declared_component_forced

    def _registry_config_file(self) -> str | None:
        """Config arduino-cli du workspace, pour le lookup registre. None si
        aucune carte sélectionnée ou arduino-cli absent — le lookup dégrade
        alors en « unavailable » (pas de substitution silencieuse)."""
        env, model = board_manager.env, board_manager.model
        fqbn = get_fqbn(env, model) if (env and model) else None
        if not fqbn or not arduino_cli.is_available():
            return None
        from .workspace import workspace_manager
        return workspace_manager.cli_config(fqbn)

    def _board_architecture(self) -> str:
        """Architecture de la carte selectionnee (« arduino:avr:uno » -> « avr »).

        Chaine vide quand aucune carte n'est choisie : la modale n'affiche alors
        AUCUNE revendication de compatibilite. Presenter une ignorance comme un
        verdict est precisement ce que le pipeline hors-corpus supprime.
        """
        try:
            from .board_manager import board_manager, get_fqbn
            env, model = board_manager.env, board_manager.model
            fqbn = get_fqbn(env, model) if (env and model) else ""
            parts = (fqbn or "").split(":")
            return parts[1] if len(parts) >= 2 else ""
        except Exception:
            return ""

    def _note_resemblance(self, by_resemblance: bool) -> None:
        """Rappel de `rag.build_lib_context` (TODO #61) : les libs injectées
        viennent-elles d'une devinette ? Remis à zéro avant chaque assemblage,
        pour qu'une exception au milieu du RAG ne laisse pas la valeur de la
        génération précédente décider de la bannière."""
        self._last_resemblance = bool(by_resemblance)

    def _maybe_resemblance_banner(self, *, action: str, from_scratch: bool,
                                  has_targets: bool) -> None:
        """Avoue à l'utilisateur que la bibliothèque a été choisie par
        ressemblance -- l'asymétrie que ce ticket ferme : le modèle recevait un
        en-tête hedgé (« if NONE matches, IGNORE this section entirely »), et
        l'humain ne recevait rien.

        Muette sur un « Modifier » : le modèle y reçoit le code actuel de la
        fonctionnalité, donc la référence est écrite dedans, pas devinée. La
        règle vit dans `info_banner`, hors Qt, avec son test.

        ⚠️ Ne CORRIGE pas l'injection elle-même : sur un « Modifier », l'app
        pousse quand même la lib d'une autre puce au modèle (mesuré : MAX31855
        à 0,512 sur un projet BME280). C'est un défaut du RAG, pas de
        l'affichage — TODO #64. La trace reste au journal, où les lignes
        `[RAG] retrieved: …` nomment déjà les libs injectées.
        """
        from .info_banner import numbered, should_disclose_resemblance
        if not should_disclose_resemblance(
                by_resemblance=self._last_resemblance, action=action,
                from_scratch=bool(from_scratch), has_targets=bool(has_targets)):
            return
        self._registry_banner.show_nudge(
            numbered([lang_manager.current.rag_guess_by_resemblance]), "", "")

    def _apply_registry_results(self, forced, results, prompt: str = ""):
        """Intègre les résultats du lookup registre : les entrées ad hoc
        rejoignent `forced_libs` (mécanisme d'injection existant) ; si RIEN
        n'est trouvé, `forced_libs=[]` (liste vide ≠ None) SUPPRIME le
        retrieval sémantique — plus jamais les libs bruitées d'une autre puce.
        Retourne (forced, directive_orpheline) et affiche bannière + journal.

        Termine aussi par le retour d'écriture (`_write_back_declared_lib`) :
        si `prompt` désigne un composant déclaré, la lib retenue et ses
        `#include` réels sont enregistrés sur son entrée — sinon le résultat
        serait jeté et la carte resterait indéfiniment sur « lib à
        déterminer »."""
        s = lang_manager.current
        from .registry_lookup import unknown_component_directive
        found = [r for r in results if r.entry is not None]
        # Une installation ECHOUEE n'est pas un composant inconnu : le registre
        # le connaissait. Message distinct, et surtout PAS la directive
        # « composant inconnu » — on ne va pas générer du code (cf. l'abandon
        # dans `_continue_generation`), donc rien à dire au modèle.
        blocked = [r for r in results if r.status == "install_failed"]
        # A token derived from a silkscreened module reference is NOT what the
        # user typed: the banner names both, so a translation never passes for
        # their own words (spec 2026-08-20). Read here too, one step earlier
        # than the messages, because it also decides what "missing" means.
        aliases = getattr(self, "_registry_aliases", {})

        def _not_searched(r) -> bool:
            """Le registre n'a même pas pu être INTERROGÉ pour cette puce de
            module (« unavailable » = aucune carte sélectionnée, ou
            arduino-cli absent). Ce n'est pas « introuvable » : c'est
            « pas cherché », et les deux mènent à des actions opposées.

            Sans cette distinction, un prompt « GY-80 » sans carte branchée
            dégradait une puce parfaitement connue en COMPOSANT INCONNU —
            directive `UNKNOWN COMPONENT` injectée au modèle et bannière
            « aucune librairie trouvée au registre » — alors que rien n'avait
            été cherché. Volontairement BORNÉ aux tokens de module : le
            classement `unavailable` → `missing` des autres chemins est
            antérieur et hors du périmètre de ce correctif.
            """
            return r.status == "unavailable" and r.token in aliases

        not_searched = [r for r in results if _not_searched(r)]
        missing = [r for r in results
                   if r.entry is None and r.status != "install_failed"
                   and not _not_searched(r)]
        for r in results:
            for line in r.log:
                print(line, flush=True)
                self._on_rag_status(line)
        if found:
            forced = (list(forced) if forced else []) \
                + [r.entry for r in found]
        elif forced is None:
            forced = []
        directive = (unknown_component_directive([r.token for r in missing])
                     if missing else "")
        # La bannière annonce une DEVINETTE. Quand la lib vient d'une décision
        # déjà mémorisée — une fiche déclarée qui porte sa lib, ou un choix
        # explicite de l'utilisateur — l'app n'a rien deviné : le répéter à
        # chaque génération est du bruit, et un bruit qui finit par se lire
        # comme du décor (QA G3, 2026-08-08). La fiche de l'onglet
        # « Composants » reste le domicile durable de cette information, avec
        # son propre bouton « Changer de bibliothèque » : l'échappatoire n'est
        # pas perdue, elle change juste d'endroit.

        def _msg(r, plain_tmpl, module_tmpl, **kw):
            alias = aliases.get(r.token, "")
            if alias:
                return module_tmpl.format(alias=alias.upper(),
                                          part=r.token.upper(), **kw)
            return plain_tmpl.format(part=r.token.upper(), **kw)

        msgs = [_msg(r, s.registry_lib_found, s.registry_module_lib_found,
                     lib=r.lib_name)
                for r in found if not _lib_was_already_decided(r)]
        msgs += [_msg(r, s.registry_lib_not_found,
                      s.registry_module_lib_not_found)
                 for r in missing]
        msgs += [_msg(r, s.registry_install_failed,
                      s.registry_module_install_failed, lib=r.lib_name)
                 for r in blocked]
        # « Pas cherché » a son propre message : dire « introuvable » ici
        # serait affirmer un résultat qu'aucune recherche n'a produit.
        msgs += [s.registry_module_lib_unavailable.format(
                     alias=aliases.get(r.token, "").upper(),
                     part=r.token.upper())
                 for r in not_searched]
        # A preference that no longer resolves must be SAID, not left in the
        # log: `lookup_component` already falls back to the normal search and
        # journals it, so the generation silently used another library than the
        # one the user picked -- the exact silence this chantier exists to end.
        for r in found:
            pref = _preference_was_overridden(r)
            if pref:
                msgs.append(s.registry_pref_not_found.format(
                    pref=pref, part=r.token.upper(), lib=r.lib_name))
        # Remember what the banner is talking about, so its action button can
        # open the choice dialog on the right component. Actionable when there
        # is something to choose between, OR when the user's stored preference
        # did not survive: in that case `alternatives` can legitimately be
        # empty (only one relevant library existed in the registry), yet the
        # dialog is still the way out -- it carries a search field. Announcing
        # that a choice was overridden while hiding the only way to correct it
        # would be the very defect this chantier removes.
        self._registry_choices = [
            (r.token, r.lib_name, list(r.alternatives))
            for r in found
            if r.alternatives or _preference_was_overridden(r)
        ]
        # Composants restés inconnus : on retient leurs noms pour la question
        # pré-remplie du chat. Un SEUL bouton les couvre tous — la question
        # les liste, plutôt qu'un bouton par composant.
        self._registry_unknown = [r.token.upper() for r in missing]
        if msgs:
            from .info_banner import numbered
            self._registry_banner.show_nudge(
                numbered(msgs),
                s.registry_change_lib if self._registry_choices else "",
                s.registry_ask_chat if self._registry_unknown else "")
        _write_back_declared_lib(prompt, results)
        return forced, directive

    def _on_change_lib_requested(self) -> None:
        """Banner action: let the user replace the library the app guessed.

        Handles each actionable component of the banner in turn -- a prompt can
        legitimately name two unknown parts, and silently dropping the second
        would leave a wrong guess in place with no way back to it. The
        regeneration offer itself is asked ONCE, after the loop -- see
        `_offer_lib_swap_regeneration`.
        """
        from .lib_choice_dialog import LibChoiceDialog
        from .component_libs import (
            clear_preference, no_library_for, set_no_library, set_preference,
        )
        for token, current, alternatives in list(self._registry_choices):
            dlg = LibChoiceDialog(
                self, token=token, current_lib=current,
                alternatives=alternatives,
                config_file=self._registry_config_file(),
                arch=self._board_architecture(),
                current_no_lib=no_library_for(token))
            if not dlg.exec():
                continue
            if dlg.no_library_requested:
                # TODO #51. ⚠️ PAS de garde « rien a effacer » comme le clear
                # juste dessous : celui-la ne fait qu'annuler, alors qu'ici
                # l'utilisateur AJOUTE une affirmation. Elle vaut d'etre
                # enregistree meme quand aucune preference ne la precedait --
                # c'est justement le cas le plus courant.
                set_no_library(token)
                self._after_lib_preference_changed(token, current, "")
                continue
            if dlg.clear_requested:
                if not current:
                    # Rien a effacer : cette entree n'a deja aucune
                    # preference connue. clear_preference serait un no-op
                    # sur le fichier, mais laisser
                    # _after_lib_preference_changed mettre quand meme une
                    # regeneration en file produirait une popup qui ne
                    # verifie rien de reel ("le code utilise encore —").
                    # Meme regle que `on_lib_chosen_in_form` pour la
                    # creation : pas de preference precedente => rien n'a
                    # ete remplace => silence total, rien a proposer.
                    continue
                # TODO #39: return value discarded -- a failed disk write
                # degrades silently to session-only (no user-facing error
                # path yet), same accepted limitation as the set case below.
                clear_preference(token)
                self._after_lib_preference_changed(token, current, "")
                continue
            if not dlg.chosen_lib:
                continue
            # TODO #39: return value discarded -- a failed disk write degrades
            # silently to session-only (no user-facing error path yet).
            set_preference(token, dlg.chosen_lib)
            self._after_lib_preference_changed(token, current, dlg.chosen_lib)
        self._offer_lib_swap_regeneration()

    def _after_lib_preference_changed(self, token: str, old_lib: str,
                                      new_lib: str) -> None:
        """Hook run right after a library preference changed.

        Finds the features whose code still includes the header of the
        library just replaced (matched on the HEADER FILE, not the library
        name -- see `_features_using_includes`) and QUEUES them for the
        regeneration offer. Deliberately does not prompt itself: prompting
        here would fire once per changed component, so picking new libraries
        for two components from one banner action would show two modal
        prompts back to back for what the user experienced as one action.
        `_offer_lib_swap_regeneration` prompts once, with the union, after
        the caller is done changing preferences -- `_on_change_lib_requested`
        calls it after its whole loop, `on_change_lib_for_component` calls it
        right after its one change. Both funnel through this same hook first,
        so the two entry points cannot diverge on what "affected" means.

        Silent no-op when nothing is affected AND headers were actually
        known: a popup about code that does not exist would be noise. But
        "no cache record for this token" is NOT the same fact as "checked,
        nothing uses it" -- see the branch below. Collapsing the two would
        silently hollow out entry point 2's own promise: the Composants tab
        card is durable (`component_libs` never evicts) and can be acted on
        long after the lookup cache -- bounded, LRU -- has forgotten the
        record that would have told us what to check.
        """
        self._registry_banner.setVisible(False)
        from .registry_lookup import cached_lookups
        # TODO #39: durable fix is to persist the resolved `headers` INSIDE
        # component_libs.json, alongside the preference itself -- that store
        # never evicts, unlike this lookup cache -- so this offer survives
        # eviction instead of degrading to "unknown" below. Deliberately
        # deferred: it is a schema change, out of scope for this chantier.
        rec = cached_lookups().get(token)
        if not isinstance(rec, dict):
            self._warn_lib_swap_unchecked(token, new_lib)
            return
        entry = rec.get("entry")
        headers = list(entry.get("headers") or []) if isinstance(entry, dict) else []
        ids = _features_using_includes(self._features, headers)
        if not ids:
            return
        self._pending_lib_swap_ids |= ids
        self._pending_lib_swap_pairs.append((old_lib, new_lib))

    def _warn_lib_swap_unchecked(self, token: str, new_lib: str) -> None:
        """Tells the user we could not verify whether their code still uses
        the OLD library's header after this change: the registry lookup
        cache holds no record for `token` (evicted -- bounded LRU -- or there
        never was one), so `_features_using_includes` has nothing to compare
        against. Staying silent here would look EXACTLY like "checked,
        nothing uses it" -- the wrong kind of confidence to fake, and the
        precise silence TODO #39 exists to remove.

        Surfaced through BOTH channels `_apply_registry_results` already uses
        for registry log lines: `_on_rag_status` for the permanent journal
        trail, AND the info banner. Journal-only would not be enough here --
        this chantier's own QA note (section I5 of the plan) already calls a
        message that "lives only in the journal" the exact silence to avoid,
        and this fires from a deliberate user action that deserves a visible
        answer, not one buried in a scrolling log.
        """
        s = lang_manager.current
        msg = s.lib_swap_unchecked.format(part=token.upper(), new=new_lib or "—")
        self._on_rag_status(f"[REGISTRY] {msg}")
        self._registry_banner.show_nudge(msg, "")

    def _offer_lib_swap_regeneration(self) -> None:
        """Prompt ONCE for every library preference changed since the last
        call, covering the UNION of features `_after_lib_preference_changed`
        queued. Shared tail of both entry points (banner loop, Composants tab
        single change) so a user who fixes two libraries from one banner
        gets one combined offer instead of two modal prompts in a row for
        what they experienced as a single action.

        No-op, and nothing left pending, when nothing was queued -- either no
        preference actually changed, or none of the changed components'
        headers are used by any feature yet.
        """
        ids = self._pending_lib_swap_ids
        pairs = self._pending_lib_swap_pairs
        self._pending_lib_swap_ids = set()
        self._pending_lib_swap_pairs = []
        if not ids:
            return
        # Usually a single (old, new) pair -- the multi-component case joins
        # names so the one popup still names everything that changed, rather
        # than silently reporting only the last swap. `old` covers the WHOLE
        # lot regardless of branch below: a cleared entry still used an old
        # library, and the popup that follows a clear names it too.
        old = ", ".join(dict.fromkeys(o for o, _ in pairs if o))
        # A CLEAR (`dlg.clear_requested`, routed here with new_lib="" by
        # `_after_lib_preference_changed`) has no "new" library -- the user
        # erased their choice, they did not make one. As soon as one clear
        # sits in the same lot as a real change, no sentence naming "the new
        # library" is true for the WHOLE lot any more (it would impute to the
        # change an erasure that has nothing to do with it, or vice versa) --
        # so ONE clear in the lot is enough to route the ENTIRE popup to the
        # message that never names a new library, rather than silently
        # dropping the clear from `new` while it stays in `old`.
        if any(not n for _, n in pairs):
            if self._confirm_lib_swap_regen_cleared(old):
                self._regenerate_features(ids)
            return
        new = ", ".join(dict.fromkeys(n for _, n in pairs if n))
        if self._confirm_lib_swap_regen(old, new):
            self._regenerate_features(ids)

    def _confirm_lib_swap_regen(self, old: str, new: str) -> bool:
        """Yes/no popup offering to regenerate the code still using a library
        the user just replaced. Same construction as the wiring chip-swap
        sibling `_confirm_regen_after_swap`: RichText QMessageBox,
        Accept/Reject buttons, themed best-effort.

        Only reached for a lot with NO clear in it (`_offer_lib_swap_regeneration`
        routes any lot containing one to `_confirm_lib_swap_regen_cleared`
        instead) -- so `new` is guaranteed non-empty here, same as before
        « Laisser l'app decider » existed. `old` stays a best-effort read
        (`preferred_lib_for` or the cache's `lib_name`) that CAN come back ""
        -- e.g. a hand-edited cache with `headers` set but `lib_name` blank
        still yields matched features -- hence the em-dash fallback on `old`
        alone.
        """
        from PyQt6.QtWidgets import QMessageBox
        s = lang_manager.current
        box = QMessageBox(self)
        box.setWindowTitle(s.lib_swap_regen_title)
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(s.lib_swap_regen_body.format(old=old or "—", new=new or "—"))
        yes = box.addButton(s.lib_swap_regen_yes,
                            QMessageBox.ButtonRole.AcceptRole)
        box.addButton(s.lib_swap_regen_no, QMessageBox.ButtonRole.RejectRole)
        try:
            from .theme import messagebox_qss
            box.setStyleSheet(messagebox_qss(theme_manager.current))
        except Exception:
            pass
        box.exec()
        return box.clickedButton() is yes

    def _confirm_lib_swap_regen_cleared(self, old: str) -> bool:
        """Sibling of `_confirm_lib_swap_regen` for a lot that contains at
        least one CLEARED preference. Never names a "new" library -- there
        is none to name for a clear, and per the routing rule above this is
        reached as soon as ONE clear taints the whole lot -- it only asserts
        what stays true for every entry in the lot: the code still uses
        `old` (ALL old libraries in the lot, per the caller).

        The regeneration offer itself keeps its full meaning here: the
        preference was just erased, so regenerating now is exactly what
        fulfils the pinned card's own promise ("l'app cherchera a nouveau a
        la prochaine generation") -- do not read the absence of a new
        library as a reason to drop the offer.

        Kept as its own method, not an `if` inside `_confirm_lib_swap_regen`,
        so neither body has to reason about a parameter it does not use.
        """
        from PyQt6.QtWidgets import QMessageBox
        s = lang_manager.current
        box = QMessageBox(self)
        box.setWindowTitle(s.lib_swap_regen_title)
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(s.lib_swap_regen_body_cleared.format(old=old or "—"))
        yes = box.addButton(s.lib_swap_regen_yes,
                            QMessageBox.ButtonRole.AcceptRole)
        box.addButton(s.lib_swap_regen_no, QMessageBox.ButtonRole.RejectRole)
        try:
            from .theme import messagebox_qss
            box.setStyleSheet(messagebox_qss(theme_manager.current))
        except Exception:
            pass
        box.exec()
        return box.clickedButton() is yes

    def on_change_lib_for_component(self, token: str) -> None:
        """Entry point 2: the "Change library" button of a component card in
        the Composants tab (`ComponentsView.change_lib_requested`).

        Goes through the SAME dialog and the same after-effect as the banner
        -- one behaviour, two doors. Reads the current library
        (`preferred_lib_for` first -- it already knows about a declared
        component -- else the cached lookup record's `lib_name`) and the
        cached alternatives, opens `LibChoiceDialog`, and on a real choice
        applies it exactly like one iteration of `_on_change_lib_requested`'s
        loop, then offers the regeneration right away -- there is no loop
        here for it to wait on.
        """
        from .lib_choice_dialog import LibChoiceDialog
        from .component_libs import (
            clear_preference, no_library_for, preferred_lib_for,
            set_no_library, set_preference,
        )
        from .registry_lookup import cached_lookups
        rec = cached_lookups().get(token)
        if not isinstance(rec, dict):
            rec = {}
        current = (preferred_lib_for(token)
                  or str(rec.get("lib_name") or "").strip())
        # str()-coerced: unlike `_registry_choices` (built from the trusted
        # RegistryLookupResult dataclass), this reads the raw cache FILE --
        # the same one `_cache_get`'s docstring already treats as hand-editable.
        alternatives = [str(a) for a in (rec.get("alternatives") or []) if a]
        dlg = LibChoiceDialog(
            self, token=token, current_lib=current,
            alternatives=alternatives,
            config_file=self._registry_config_file(),
            arch=self._board_architecture(),
            current_no_lib=no_library_for(token))
        if not dlg.exec():
            return
        if dlg.no_library_requested:
            # TODO #51, meme regle qu'en porte 1 : une affirmation s'enregistre
            # meme sans preference precedente.
            set_no_library(token)
            self._after_lib_preference_changed(token, current, "")
            self._offer_lib_swap_regeneration()
            return
        if dlg.clear_requested:
            if not current:
                # Meme garde qu'en porte 1 (banniere) : cette fiche n'a deja
                # aucune preference connue (`preferred_lib_for` ET le cache
                # registre sont vides -- cas reel ici, contrairement a la
                # porte 1 dont `current` vient toujours d'un lookup resolu).
                # Rien a effacer, rien a proposer.
                return
            # TODO #39: return value discarded -- same accepted limitation as
            # _on_change_lib_requested (session-only fallback on a failed
            # write).
            clear_preference(token)
            self._after_lib_preference_changed(token, current, "")
            self._offer_lib_swap_regeneration()
            return
        if not dlg.chosen_lib:
            return
        # TODO #39: return value discarded -- same accepted limitation as
        # _on_change_lib_requested (session-only fallback on a failed write).
        set_preference(token, dlg.chosen_lib)
        self._after_lib_preference_changed(token, current, dlg.chosen_lib)
        self._offer_lib_swap_regeneration()

    def on_lib_chosen_in_form(self, token: str, old_lib: str,
                              new_lib: str) -> None:
        """Entry point 3: the library was picked INSIDE the declaration form
        (« Créer un composant » → « Chercher… »), which writes it on the
        declared entry itself instead of going through `set_preference`.

        The choice is durable either way -- a declared entry owns its own
        library (`component_libs.preferred_lib_for`). What was missing is the
        AFTER-EFFECT: without this, changing a library from the form skipped
        both the regeneration offer and the `lib_swap_unchecked` warning, while
        the banner door kept them. Measured 2026-08-10 during QA I6: the
        Composants tab's own button had been replaced by the pencil, and its
        signal (`ComponentsView.change_lib_requested`) stopped being emitted
        at all -- so `on_change_lib_for_component` above became unreachable and
        the whole tail went with it. One behaviour, three doors.

        Two early exits, both meaning "nothing was REPLACED":
        - no previous library: the component never had one, so no existing code
          can be using it. Warning here would fire on every creation;
        - same library: not a change at all.
        Neither is the ambiguous case `_warn_lib_swap_unchecked` exists for
        (a real replacement whose impact we cannot verify).
        """
        from .registry_lookup import norm_lib_name
        if not (old_lib or "").strip():
            return
        if norm_lib_name(old_lib) == norm_lib_name(new_lib):
            return
        self._after_lib_preference_changed(token, old_lib, new_lib)
        self._offer_lib_swap_regeneration()

    def _continue_generation(self, backend, action, target_id, prompt, *,
                             forced, registry_results,
                             declared_component_forced: bool = False,
                             banned_libs: frozenset[str] = frozenset()):
        """Seconde moitié de _start_generation, après l'éventuel lookup
        registre asynchrone (composant hors-corpus).

        ``declared_component_forced`` : cf. `rag.build_lib_context` — vrai
        seulement quand `forced` provient du déclencheur composant déclaré
        SANS part-number inconnu impliqué (calculé dans `_start_generation`,
        AVANT l'ajout du token déclaré à `unknown`, pour ne jamais confondre
        les deux déclencheurs sur un prompt qui nomme les deux).

        ``banned_libs`` (#85) : libs bannies par les swaps persistés des
        features CIBLÉES — donc seul le chemin CORRECT (Modifier / ↻ ciblé)
        en reçoit ; Add et REGENERATE n'appliquent pas les overrides et
        passent l'ensemble vide."""
        if registry_results is not None and self._gen_busy is None:
            return   # génération annulée pendant le lookup registre
        # Loader démarré AVANT l'assemblage du prompt : _start_gen_loader vide
        # le journal, et l'assemblage (augment_user_prompt) y écrit déjà les
        # diagnostics « [RAG] … » via le sink. Le démarrer après les effacerait
        # aussitôt. No-op si le lookup registre l'a déjà démarré.
        if self._gen_loader_journal is None:
            self._start_gen_loader()
        # Remis à zéro AVANT l'assemblage : une exception dans le RAG
        # empêcherait le rappel, et la valeur de la génération précédente
        # déciderait de la bannière (TODO #61).
        self._last_resemblance = False
        from_scratch = self._pending_from_scratch
        orphan_directive = ""
        if registry_results is not None:
            forced, orphan_directive = self._apply_registry_results(
                forced, registry_results, prompt)
            # Installation impossible : on ABANDONNE la génération (décision
            # utilisateur 2026-08-08). Sans la bibliothèque téléchargée il n'y
            # a ni en-têtes réels ni exemple officiel à injecter — le code
            # produit ne pourrait pas être fonctionnel, et lui donner l'aspect
            # d'un résultat ferait perdre du temps. Le débutant hors ligne se
            # heurte au mur dans les deux cas ; autant que la cause soit dite
            # tout de suite et qu'elle soit actionnable. Un composant DÉJÀ VU
            # n'est pas concerné : `_cache_get` répond avant toute recherche.
            blocked = [r for r in registry_results
                       if r.status == "install_failed"]
            if blocked:
                self._stop_gen_loader()
                r = blocked[0]
                self._show_gen_error(
                    lang_manager.current.registry_install_failed.format(
                        part=r.token.upper(), lib=r.lib_name))
                return
        # TODO #51 — l'affirmation de l'utilisateur atteint le modele.
        #
        # ⚠️ POSEE HORS du bloc ci-dessus, et c'est necessaire : ces jetons ont
        # justement ete RETIRES de la recherche (`_registry_request`), donc
        # quand ils sont les seuls du prompt il n'y a AUCUN `registry_results`
        # et `_apply_registry_results` ne tourne jamais. Mettre la directive
        # la-dedans l'aurait rendue muette dans le cas le plus courant : un
        # prompt qui ne parle que de composants sans bibliotheque.
        #
        # Pas de banniere : elle annonce des DEVINETTES, et ici l'app n'a rien
        # devine -- c'est l'utilisateur qui a decide. Le repeter a chaque
        # generation serait le bruit que `_lib_was_already_decided` supprime
        # deja pour une lib choisie.
        if self._registry_no_library:
            from .registry_lookup import no_library_directive
            said = no_library_directive(self._registry_no_library)
            orphan_directive = ((orphan_directive + "\n\n" + said).strip()
                                if orphan_directive else said)
        board_name = self._board_name()
        if action == REGENERATE:
            # Full generation (reuses the existing prompt assembly).
            user_prompt = self._assemble_generation_prompt(
                prompt, forced_libs=forced, extra_directive=orphan_directive,
                declared_component_forced=declared_component_forced)
        elif action == CORRECT and self._correct_targets(target_id):
            selected = self._correct_targets(target_id)
            sel_ids = {f.id for f in selected}
            others = [f for f in self._features if f.id not in sel_ids]
            context = build_context_summary(others)
            if from_scratch:
                # ↻ Regenerate: fresh implementation FROM THE PROMPT, without the
                # feature's current code (otherwise "modify" keeps everything =
                # same code, no-op). Others are shared read-only for collision
                # avoidance; the merge still replaces the targeted feature(s).
                instr = build_regen_instruction(
                    prompt, context, board_hint=board_name)
            else:
                # Modify: we supply the CURRENT code of the targeted feature(s)
                # + the instruction to change ONLY what is asked. Avoids losing
                # the rest of the behavior (e.g. a frequency) when regenerating the
                # block. Several checked features → we assemble their code together
                # (they will merge into one at commit, cf _on_generation_done).
                instr = build_modify_instruction(
                    assemble(selected), prompt, context, board_hint=board_name)
            # Attached context document (pins/notes) at the top, read-only.
            instr = self._context_block() + instr
            if orphan_directive:
                instr = instr + "\n\n" + orphan_directive
            user_prompt = augment_user_prompt(instr, retrieval_prompt=prompt,
                                              forced_libs=forced,
                                              retrieval_context=self._context_full_text(),
                                              declared_component_forced=declared_component_forced,
                                              on_resemblance=self._note_resemblance,
                                              ranking_hint=self._project_chip_hint(),
                                              banned_libs=banned_libs)
        else:
            # Add (or Correct without an existing target -> add): we supply the
            # EXISTING sketch to the model (read-only) so it does not have to
            # guess it or re-declare it, + a concise reminder of the pins/names taken.
            context = build_context_summary(self._features)
            instr = build_feature_instruction(
                prompt, board_hint=board_name,
                existing_code=self.get_code(), used_summary=context)
            # Attached context document (pins/notes) at the top, read-only.
            instr = self._context_block() + instr
            if orphan_directive:
                instr = instr + "\n\n" + orphan_directive
            user_prompt = augment_user_prompt(instr, retrieval_prompt=prompt,
                                              forced_libs=forced,
                                              retrieval_context=self._context_full_text(),
                                              declared_component_forced=declared_component_forced,
                                              on_resemblance=self._note_resemblance,
                                              ranking_hint=self._project_chip_hint())
        # « Coulisses du prompt » (#42) : la modale est une ÉTAPE, plus un
        # cul-de-sac. Avant, ce bloc sortait par un `return` sec — voir le
        # prompt et générer s'excluaient. Annuler garde ce comportement,
        # Envoyer poursuit avec exactement le message affiché.
        validated = self._prompt_backstage(
            backend, user_prompt, board_name, rules_prompt=prompt)
        if validated is _BACKSTAGE_CANCELLED:
            self._set_generating(False)
            return
        # Affichée APRÈS le contrôle d'annulation : sur une annulation, rien
        # n'est parti au modèle, donc rien ne doit s'afficher (sinon « une
        # bibliothèque a été proposée » resterait à l'écran pour une requête
        # jamais envoyée).
        self._maybe_resemblance_banner(
            action=action, from_scratch=from_scratch,
            has_targets=bool(self._correct_targets(target_id)))
        self._warn_if_prompt_overflows(backend, user_prompt, board_name,
                                       rules_prompt=prompt)
        self._set_generating(True)
        self._gen_worker = _GenerateWorker(
            backend, user_prompt, board_name, self._current_mode,
            comment_verbosity=self._comments_verbosity(),
            rules_prompt=prompt, user_message=validated,
        )
        self._gen_worker.finished.connect(self._on_generation_done)
        self._gen_worker.error.connect(self._on_gen_error)
        # Le loader du journal est démarré en tête de _continue_generation
        # (avant l'assemblage du prompt) — cf. commentaire là-bas.
        self._gen_worker.start()

    def _warn_if_prompt_overflows(self, backend, user_prompt: str,
                                  board_name: str,
                                  rules_prompt: str | None = None):
        """Avertit quand le prompt ne laisse plus de place à la réponse (#48).

        Rien ne le vérifiait : au-delà d'une certaine taille de projet, le
        modèle perd le DÉBUT du contexte et écrit du code qui ignore une partie
        du sketch, sans un mot. Le symptôme n'est pas une erreur, c'est un
        résultat plausible et faux.

        On DIT, on n'agit pas : découper ou résumer le sketch automatiquement
        est un autre chantier, et probablement pas souhaitable — mieux vaut
        apprendre à l'utilisateur que son projet a dépassé ce que son modèle
        local peut lire, et qu'un modèle cloud (128 k à 1 M) lève la limite.

        Partagé par les quatre chemins de génération, comme
        `_prompt_backstage` : le mode n'est qu'un affichage, et c'est la
        duplication qui les avait fait diverger en août (QA G6)."""
        try:
            from .generation.context_budget import prompt_overflows
            system, user_msg = _build_codegen_parts(
                backend, user_prompt, board_name,
                self._current_mode, self._comments_verbosity(),
                rules_prompt=rules_prompt)
            trop = prompt_overflows(system, user_msg, backend)
            if not trop:
                return
            self._active_output_area().begin_phase(
                lang_manager.current.prompt_too_long.format(**trop), "#f59e0b")
        except Exception:
            pass          # un avertissement absent ne doit pas bloquer la génération

    def _recover_from_unhandled(self):
        """Deverrouille ce qui etait verrouille, et le DIT (TODO #49).

        L'excepthook fait tres bien son travail : mesure, PyQt6 n'abandonne le
        processus que si le hook est celui par defaut, donc l'app survit. Mais
        elle survivait DANS L'ETAT OU ELLE ETAIT. Le cas reel : une exception
        partie du callback du worker registre laissait `_gen_busy` arme, le
        bouton bloque sur « ◐ Annuler » et la ligne animee du journal en train
        de tourner — une app qui a l'air plantee alors qu'elle tourne.

        Ne fait rien si rien n'etait en cours : un message qui apparait sans
        raison apprend a ignorer les messages."""
        if self._gen_busy is None:
            return
        etait = self._gen_busy
        try:
            self._stop_gen_loader()
        except Exception:
            pass
        try:
            if etait == "beginner":
                self._restore_beginner_btn()
            else:
                self._set_generating(False)
        except Exception:
            pass
        try:
            self._active_output_area().begin_phase(
                lang_manager.current.crash_recovered, "#f59e0b")
        except Exception:
            pass

    def _prompt_backstage(self, backend, user_prompt: str, board_name: str,
                          *, rules_prompt: str | None = None):
        """« Coulisses du prompt » (#42). Returns the user message to send —
        the one shown, possibly edited — or `_BACKSTAGE_CANCELLED`.

        Returns `None` when the feature is off, which is exactly what
        `GenerateWorker(user_message=...)` expects to mean "compose it
        yourself": the normal path is untouched, no branch downstream.

        Shared by the beginner path and the int/advanced one on purpose. The
        mode is only a display layer — duplicating this is how the two paths
        drifted before (QA G6).

        ⚠️ Ne touche PAS à l'état de génération (`_gen_busy`) : il vaut
        « beginner » ou « advanced » selon le chemin, et le remettre à zéro
        ici le ferait aussi quand l'utilisateur ENVOIE — bouton débutant
        restauré pendant qu'une génération tourne. Chaque appelant restaure
        le sien à l'annulation."""
        if not session.prompt_backstage:
            return None
        # Rien n'est en train d'être généré tant que la modale est ouverte :
        # laisser la ligne animée du journal tourner derrière affirmerait le
        # contraire. Elle repart si — et seulement si — l'utilisateur envoie.
        self._stop_gen_loader()
        system, user_msg = _build_codegen_parts(
            backend, user_prompt, board_name,
            self._current_mode, self._comments_verbosity(),
            rules_prompt=rules_prompt,
        )
        dlg = _PromptPreviewDialog(
            lang_manager.current.backstage_title, system, user_msg, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return _BACKSTAGE_CANCELLED
        if dlg.edited():
            # Un prompt modifié à la main n'est plus reproductible depuis
            # l'état du projet : la Feature garde la demande écrite par
            # l'utilisateur, pas ce texte. Le dire ici plutôt que de le
            # laisser découvrir au premier ↻ qui rend autre chose.
            self._active_output_area().begin_phase(
                lang_manager.current.backstage_edited, "#f59e0b")
        self._start_gen_loader()         # la génération part pour de bon
        return dlg.user_message()

    def _resolve_lib_ambiguity(self, bare_prompt: str):
        """Plus de MODALE avant generation (decision 2026-07-08) : plus de
        fenetre de clarification. Mais on garde les forcages SILENCIEUX (libs
        des modules NOMMES comme HW-612 + puces NOMMEES d'une famille comme
        SSD1306/VMA335) via forced_libs_for_generation. Les familles restees
        ambigues sont laissees au RAG, corrigees a posteriori dans le schema."""
        from .rag import forced_libs_for_generation
        return forced_libs_for_generation(bare_prompt) or None

    def _gen_action_label(self, action, from_scratch: bool) -> str:
        """Étiquette énumérée de l'action de génération pour la télémétrie
        (liste FERMÉE : first / regenerate / add / modify)."""
        if action == ADD:
            return "add"
        if action == CORRECT:
            # ↻ (from_scratch) = vraie régénération ; sinon = Modifier.
            return "regenerate" if from_scratch else "modify"
        # REGENERATE : 1re génération (aucune fonctionnalité) vs régé complète.
        return "first" if not self._features else "regenerate"

    def _assemble_generation_prompt(self, prompt: str,
                                    forced_libs: list[dict] | None = None,
                                    extra_directive: str = "",
                                    declared_component_forced: bool = False) -> str:
        """Assemble the FULL generation prompt (Regenerate + beginner).

        IDENTICAL for all modes (the mode is just a display): injected project
        context + Serial directive. The "bare" version is used for the RAG
        retrieval (otherwise the boilerplate dominates the embedding).
        ``extra_directive``: appended verbatim (e.g. the UNKNOWN COMPONENT
        instruction when neither corpus nor registry knows the part).
        ``declared_component_forced``: forwarded to `augment_user_prompt` /
        `rag.build_lib_context` (see there) — defaults to False, so the
        beginner call site (which never triggers the declared-component
        lookup) is unaffected."""
        bare = prompt
        prompt = self._inject_context(prompt)
        if self._current_mode != "advanced":
            prompt = prompt + ("\nAlways include Serial.begin(9600) in setup() "
                               "for serial communication.")
        else:
            prompt = prompt + self._serial_prompt_directive()
        prompt = prompt + "\n\n" + FEATURE_SUMMARY_DIRECTIVE
        if extra_directive:
            prompt = prompt + "\n\n" + extra_directive
        return augment_user_prompt(prompt, retrieval_prompt=bare,
                                   forced_libs=forced_libs,
                                   retrieval_context=self._context_full_text(),
                                   declared_component_forced=declared_component_forced,
                                   on_resemblance=self._note_resemblance,
                                   ranking_hint=self._project_chip_hint())

    def _reset_generation_ui(self, journal_msg: str | None = None,
                             color: str = "#f97316"):
        """Sortie de génération SANS livraison (erreur backend, parse KO,
        annulation utilisateur) : purge les états en attente et libère le
        verrou (voile + bouton). Les purges supplémentaires par rapport à
        certains anciens sites (_pending_reassign, _busy_text_override) sont
        sans effet hors génération — c'est voulu, un seul rituel."""
        self._pending_action = None
        self._pending_reassign = ([], [])
        self._busy_text_override = None
        self._stop_gen_loader()            # retire la ligne animée du journal
        if journal_msg:
            self._active_output_area().begin_phase(journal_msg, color)
        self._set_generating(False)

    def _on_gen_error(self, msg: str):
        self._reset_generation_ui()
        _m = msg.lower()
        _ec = ("timeout" if "timeout" in _m
               else "backend" if any(w in _m for w in ("connection", "refused", "unavailable", "unreachable"))
               else "unknown")
        self._show_gen_error(msg)

    def _index_features(self, code: str, features: list[Feature]) -> None:
        """Associates an editor state with its feature list, the per-feature
        wiring metadata AND the line->feature attribution map (for undo/redo):
        restoring the features without their `_wiring_resolutions`/
        `_implicit_actions`/map would silently lose the user's wiring choices
        (or the highlighting, #29) after a Ctrl+Z."""
        self._feature_index[code] = (
            [copy.deepcopy(f) for f in features],
            dict(self._wiring_resolutions),
            dict(self._implicit_actions),
            list(self._editor.line_owners()),
        )
        if len(self._feature_index) > 200:        # memory safeguard
            del self._feature_index[next(iter(self._feature_index))]

    def _index_stable_features(self, code: str) -> None:
        """STABLE analogue of `_index_features`: associate a stable-editor state
        with its feature list + line-owner map, so a native Ctrl+Z that reverts
        the text can restore the matching `_stable_features` + highlighting."""
        self._stable_feature_index[code] = (
            [copy.deepcopy(f) for f in self._stable_features],
            list(self._stable_panel.editor.line_owners()),
        )
        if len(self._stable_feature_index) > 200:
            del self._stable_feature_index[next(iter(self._stable_feature_index))]

    def _set_stable_code(self, code: str) -> None:
        """UNDOABLE replacement of the STABLE editor content (select-all +
        insertText in an EditBlock, like `set_code`) so native Ctrl+Z reverts
        it — unlike setPlainText() which clears the undo stack. Suppresses the
        stable resync during the write."""
        ed = self._stable_panel.editor
        self._suppress_stable_resync = True
        try:
            cursor = ed.textCursor()
            cursor.beginEditBlock()
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.insertText(code)
            cursor.endEditBlock()
        finally:
            self._suppress_stable_resync = False

    def _set_code_silent(self, code: str) -> None:
        """set_code() without triggering the feature resync (the generation
        commit (re)indexes the before/after state itself)."""
        self._suppress_resync = True
        try:
            self.set_code(code)
        finally:
            self._suppress_resync = False

    def _set_code_with_attribution(self, new_code: str,
                                   features: "list[Feature]") -> None:
        """Remplacement moteur du code + carte lignes->fonctionnalité (#29).
        Si `new_code` est l'assemblage (réindenté) de `features` -> carte
        EXACTE d'assemble_with_map (reindent_code préserve nombre et ordre
        des lignes). Sinon (splice sur éditeur retouché, texte réparé) ->
        transfert diff positionnel depuis l'état courant + matching des
        contributions. Ne pose rien si set_code a refusé le remplacement
        (garde anti-perte : code vide / setup-loop manquants)."""
        from .code_format import reindent_code
        old_lines = self.get_code().split("\n")
        old_map = self._editor.line_owners()
        self._set_code_silent(new_code)
        if self.get_code() != new_code:
            return                       # set_code a refusé -> ancres intactes
        asm_code, asm_map = assemble_with_map(features)
        if reindent_code(asm_code) == new_code:
            new_map = asm_map
        else:
            new_lines = new_code.split("\n")
            base = transfer_map(old_lines, old_map, new_lines)
            new_map = match_contributions(new_lines, features, base)
        self._editor.set_line_owners(new_map)
        self._code_panel.refresh_highlights(features)

    def _resync_features_from_editor(self) -> None:
        """Resynchronizes `self._features` with the current editor content.

        Every state produced by a generation (before AND after) is indexed. A
        Ctrl+Z / Ctrl+Y brings the editor back to an indexed state -> we restore
        the corresponding feature list (the feature disappears/reappears from the
        "Modify" selector). A manual edit matches no state ->
        features unchanged (just "dirty")."""
        if self._suppress_resync:
            return
        entry = self._feature_index.get(self.get_code())
        if entry is None:
            # No indexed state matches -> a genuine hand edit. Schedule the
            # debounced #31 capture (standalone orphan code -> `manual`).
            self._schedule_manual_capture("ia")
            return
        feats, wiring, implicit, line_map = entry
        self._features = [copy.deepcopy(f) for f in feats]
        self._wiring_resolutions = dict(wiring)
        self._implicit_actions = dict(implicit)
        self._code_baseline = self.get_code()
        self._has_generated = bool(self._features)
        self._refresh_action_button_styles()
        # Le bandeau de puces doit suivre : après un Ctrl+Z d'une suppression,
        # les fonctionnalités restaurées doivent RÉAPPARAÎTRE dans la bande.
        self._refresh_feature_chips()
        self._editor.set_line_owners(line_map)
        self._code_panel.refresh_highlights()

    @staticmethod
    def _feature_from_parsed(parsed, fid: str, prompt: str, summary: str,
                             prompts: list[str] | None = None,
                             carry_from: "list[Feature] | None" = None) -> Feature:
        """Construction unique d'une Feature depuis un sketch parsé.
        `parsed=None` (SketchParseError) -> Feature sans contributions (le
        code brut reste dans l'éditeur, la fonctionnalité garde son intent).
        `prompts` vide/None -> __post_init__ seed [prompt].

        `carry_from` = les Features que celle-ci REMPLACE. La régénération
        fabrique un objet neuf : ses décisions utilisateur (swap de puce) ne
        viennent pas du sketch et seraient perdues sans être reprises ici —
        le ↻ repartait alors du prompt nu et le RAG ressuscitait l'ancienne
        puce en silence (QA B1, 2026-08-08). Même raison que `prompts` juste
        au-dessus : ça appartient à l'IDENTITÉ de la fonctionnalité, pas au
        texte produit. Union ordonnée quand plusieurs sont fusionnées."""
        kw = {}
        if parsed is not None:
            kw = dict(includes=parsed.includes, global_lines=parsed.global_lines,
                      setup_lines=parsed.setup_lines, loop_lines=parsed.loop_lines,
                      functions=parsed.functions)

        def _union(attr: str) -> list[str]:
            out: list[str] = []
            for f in (carry_from or []):
                for cid in getattr(f, attr, []):
                    if cid not in out:
                        out.append(cid)
            return out

        return Feature(id=fid, prompt=prompt, summary=summary,
                       prompts=list(prompts or []),
                       banned_lib_ids=_union("banned_lib_ids"),
                       forced_lib_ids=_union("forced_lib_ids"), **kw)

    def _features_with_id(self, fid: str) -> "list[Feature]":
        """La Feature portant `fid`, en liste (vide si aucune) — de quoi
        alimenter `carry_from` quand la reconstruction REPREND un id existant
        (Régénérer, débutant, recombine : tous produisent « f1 »)."""
        return [f for f in self._features if f.id == fid]

    def _commit_generated_code(self, code: str | None = None,
                               features: "list[Feature] | None" = None, *,
                               reindent: bool = True, save: bool = True,
                               own_all_lines_to: str | None = None):
        """Rituel UNIQUE de livraison du code généré : remplace le code
        (ré-indenté — le modèle local indente mal, et la réparation
        d'accolade déterministe s'appuie sur l'indentation), fige le
        baseline, indexe l'état APRÈS pour l'undo, marque le projet généré,
        pousse le contexte chat, sauve.
        L'index de l'état AVANT reste à la charge de l'appelant (il capture
        les features/métadonnées d'avant le commit).
        `code=None` -> commit d'état sans remplacement de texte (vérif v2
        réussie : le code réparé est déjà dans l'éditeur).
        `own_all_lines_to` -> attribution single-feature directe (génération
        débutant : le sketch n'est pas un assemblage de contributions), et
        seulement si set_code a accepté le remplacement (sinon l'ancien
        contenu, peut-être multi-fonctionnalités, serait attribué en bloc =
        fausse couleur, #29)."""
        from .code_format import reindent_code
        if features is not None:
            self._features = features
        if code is not None:
            if reindent:
                code = reindent_code(code)
            if own_all_lines_to is not None:
                self._set_code_silent(code)
                if self.get_code() == code:
                    self._editor.set_line_owners(
                        single_feature_map(code, own_all_lines_to))
            else:
                self._set_code_with_attribution(code, self._features)
        self._code_baseline = self.get_code()
        self._index_features(self._code_baseline, self._features)
        self._has_generated = bool(self._features)
        self._emit_chat_context()
        if save:
            self.save_project()

    def _on_generation_done(self, code: str):
        # Guard: stale signal (previous worker) or double trigger.
        if self._pending_action is None:
            return
        s = lang_manager.current
        action, target_id = self._pending_action
        try:
            parsed = parse_sketch(code)
        except SketchParseError:
            self._reset_generation_ui()
            self._show_gen_error(s.studio_err_parse_failed)
            return
        summary = extract_feature_summary(code)   # short AI summary (may be "")

        # We build the INTENDED feature list locally and only commit it
        # (`self._features = new_features`) on success — this way a Cancel
        # at the warning never leaves the list out of sync with the code.
        if action == REGENERATE:
            # Regenerate always wipes the existing code: an explicitly
            # destructive action, knowingly chosen -> no warning, we reassemble
            # from the single new feature.
            new_features = [self._feature_from_parsed(
                parsed, "f1", self.get_prompt(), summary,
                carry_from=self._features_with_id("f1"))]
            # Regeneration = single feature -> no inter-feature conflict.
            self._pending_reassign = ([], [])
            new_code = assemble(new_features)
        elif action == ADD:
            feat = self._feature_from_parsed(
                parsed, next_feature_id(self._features), self.get_prompt(),
                summary)
            feat = self._clean_new_feature(feat)
            feat = self._reassign_new_feature_pins(feat)
            new_features = self._features + [feat]
            new_code = self._apply_feature_change(action, None, feat, new_features)
        else:  # CORRECT (UI label « Modifier »)
            # Historique des prompts : Modifier APPEND le prompt du delta à
            # l'historique de la cible ; ↻ (from_scratch) rejoue l'intent
            # existant SANS l'appendre (le champ contient full_prompt() —
            # l'appendre dupliquerait tout l'historique).
            from_scratch = getattr(self, "_pending_from_scratch", False)

            def _mk(fid, prompts=None, carry_from=None):
                hist = [p for p in (prompts or []) if p and p.strip()]
                if not hist:
                    hist = [self.get_prompt()]
                return self._feature_from_parsed(parsed, fid, hist[-1],
                                                 summary, prompts=hist,
                                                 carry_from=carry_from)
            selected = self._correct_targets(target_id)
            if not selected:
                # Target not found (e.g. legacy project without features): we fall
                # back to ADD rather than silently losing the generation.
                feat = _mk(next_feature_id(self._features))
                feat = self._clean_new_feature(feat)
                feat = self._reassign_new_feature_pins(feat)
                new_features = self._features + [feat]
                new_code = self._apply_feature_change(ADD, None, feat, new_features)
            elif len(selected) == 1:
                # Granular modification: we replace the single targeted feature,
                # the others stay unchanged.
                old = selected[0]
                hist = list(old.prompts) if from_scratch \
                    else list(old.prompts) + [self.get_prompt()]
                new_feat = _mk(old.id, prompts=hist, carry_from=[old])
                new_feat = self._clean_new_feature(new_feat)
                new_feat = self._reassign_new_feature_pins(new_feat)
                new_features = [new_feat if f.id == old.id else f
                                for f in self._features]
                new_code = self._apply_feature_change(action, old, new_feat, new_features)
            else:
                # Merge: ≥2 features modified together → the regenerated sketch
                # cannot be re-split into N → we replace them with ONE merged
                # feature, placed where the 1st selected one was. The unchecked
                # features stay separate. Its history = the union of the merged
                # histories (order of the list), + the delta prompt if Modifier.
                sel_ids = {f.id for f in selected}
                merged_id = selected[0].id
                hist = [p for f in selected for p in f.prompts]
                if not from_scratch:
                    hist = hist + [self.get_prompt()]
                new_feat = _mk(merged_id, prompts=hist, carry_from=selected)
                new_feat = self._clean_new_feature(new_feat, exclude_ids=sel_ids)
                new_feat = self._reassign_new_feature_pins(new_feat, exclude_ids=sel_ids)
                new_features = []
                for f in self._features:
                    if f.id == merged_id:
                        new_features.append(new_feat)
                    elif f.id in sel_ids:
                        continue          # absorbed by the merged feature
                    else:
                        new_features.append(f)
                new_code = self._apply_merge_change(selected, new_feat, new_features)

        if new_code is None:        # cancelled by the user (warning)
            self._reset_generation_ui()
            return
        # Atomic commit. On indexe l'état AVANT (cible d'un Ctrl+Z possible) ;
        # le rituel réindente, pose le code, indexe l'état APRÈS et sauve.
        # v2 : la LIBÉRATION du verrou (voile + bouton) et le « Code prêt » sont
        # DIFFÉRÉS jusqu'à ce que la vérif compile confirme la livraison (ou qu'on
        # revienne au baseline sur échec). Voir la fin de cette méthode et
        # _finalize_verify_success / _finalize_verify_failure. Tant que la vérif
        # tourne, l'éditeur reste VERROUILLÉ (le code n'est pas encore « livré »).
        self._index_features(self.get_code(), self._features)
        self._pending_action = None
        self._commit_generated_code(new_code, new_features)
        # Bandeau de puces à jour tout de suite (#29 revue finale) : sinon il
        # affiche encore les anciennes fonctionnalités pendant la fenêtre de
        # vérif compile (verrouillée) qui suit.
        self._refresh_feature_chips()
        self._last_prompt = self.get_prompt()

        # Non-blocking notice of reassigned pins (int/advanced only).
        moves, warnings = getattr(self, "_pending_reassign", ([], []))
        self._pending_reassign = ([], [])
        if self._current_mode != "beginner" and (moves or warnings):
            from PyQt6.QtWidgets import QMessageBox
            from .generation import format_reassign_notice
            QMessageBox.information(self, "Broches réaffectées",
                                    format_reassign_notice(moves, warnings))

        # Une génération ferme le segment d'édition manuelle courant (#35) : le
        # prochain edit à la main ouvrira un nouveau segment.
        self._manual_edit_segment_open = False
        # Popup « passe en Avancé » différée pendant la frappe : frontière de
        # segment atteinte -> affichage APRÈS la pile courante (singleShot 0,
        # sinon exec() bloquerait la suite de _on_generation_done — la vérif).
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._maybe_show_deferred_manual_popup)
        # Nudge de progression (app-wide, #35) : 15 ACTIONS en Intermédiaire →
        # bandeau Avancé. Comptent désormais Ajouter, Modifier ET Régénérer (les
        # segments d'édition manuelle sont comptés à part, cf. _run_manual_capture).
        if self._current_mode == "intermediate" and action in (ADD, CORRECT, REGENERATE):
            session.bump_progress_count(PN.COUNTER_INTERMEDIATE)
            self._maybe_intermediate_banner_nudge()

        # v2 — TOUTE génération doit compiler avant d'être livrée : compile +
        # réparation IA (≤2) en tâche de fond, sans upload. Le multi-fonctionnalités
        # garde la stratégie « recombine » en cas de couplage (scope).
        self._recombine_eligible = should_verify_assembly(action, len(self._features))
        self._recombine_attempted = False
        self._verify_delivered_code = self.get_code()
        if not self._start_assembly_verify():
            # Pas de vérif possible (pas d'arduino-cli / carte) : on libère
            # tout de suite, et on DIT que le code n'a pas été compilé.
            self._set_generating(False)
            self._refresh_action_button_styles()
            self._stop_gen_loader_ready(unverified=self._verify_skip_reason())

    def _active_console(self) -> ConsolePanel:
        """Console du mode courant : beginner -> _beg_console, sinon
        _adv_console. La génération ET la vérif v2 s'y écrivent."""
        return (self._beg_console if self._current_mode == "beginner"
                else self._adv_console)

    def _active_output_area(self):
        """Journal (LogWidget) de la console du mode courant."""
        return self._active_console().log

    def _on_rag_status(self, msg: str) -> None:
        """Ligne de diagnostic RAG/registre dans le journal du mode courant.
        Best-effort : ne doit JAMAIS remonter d'exception dans le pipeline de
        génération (le sink est appelé depuis build_lib_context)."""
        try:
            self._active_output_area().append_raw(msg)
        except Exception:
            pass

    def _start_assembly_verify(self) -> bool:
        """v2 — compile le code généré + réparation IA (≤2 cycles), en tâche de
        fond, SANS upload. Garantit que seul du code qui compile est livré ET
        détecte un couplage multi-fonctionnalités (erreur de scope). Le verrou
        (voile + bouton « Annuler ») reste actif jusqu'à la livraison. Les étapes
        (compilation / réparation / re-compilation) s'affichent au journal.

        Retourne True si la vérif a démarré, False si impossible (pas
        d'arduino-cli / pas de carte) — l'appelant libère alors le verrou."""
        env, model = board_manager.env, board_manager.model
        fqbn = get_fqbn(env, model) if (env and model) else None
        if not fqbn or not arduino_cli.is_available():
            return False
        s = lang_manager.current
        out = self._active_output_area()
        # Stoppe l'animation « Génération… » SANS écrire « Code prêt » : la phase
        # de vérif prend le relais dans le journal.
        self._stop_gen_loader()
        out.begin_phase(s.studio_verifying, "#3b82f6")
        # Le voile passe de « Génération » à « Vérification » (verrou maintenu).
        self._busy_text_override = s.studio_verifying
        self._refresh_busy_loader()
        # Réinitialise le suivi des réparations : ce qui sera émis ci-dessous
        # reflète UNIQUEMENT cette vérif (-> libellé « Réparé ✓ » si non vide).
        self._last_repair_steps = []
        backend = get_backend_instance(ai_config.backend_id)
        self._verify_worker = self._compile_service.run(
            code=self.get_code(), fqbn=fqbn,
            backend=backend if (backend and backend.is_available()) else None,
            board_name=self._board_name(),
            console=self._active_console(), verify_only=True,
            on_repair_steps=self._on_cu_repair_steps,
            on_done=self._on_assembly_verify_done,
        )
        return True

    def _on_assembly_verify_done(self, ok: bool, errors: str):
        if ok:
            self._finalize_verify_success()
            return
        # Couplage multi-fonctionnalités : une seule tentative de recombine.
        if self._recombine_eligible and not self._recombine_attempted:
            self._recombine_attempted = True
            s = lang_manager.current
            # Note explicite : on dit POURQUOI on recombine (réparation KO).
            self._active_output_area().append_explanation(s.studio_repair_insufficient)
            self._start_recombine()
            return
        self._finalize_verify_failure(errors)

    def _finalize_verify_success(self):
        """La vérif a réussi : le code en éditeur compile. On le fige comme
        baseline + on sauve. Si une réparation a modifié le code, on
        resynchronise le MODÈLE de fonctionnalités depuis l'éditeur (canonique)
        — sinon transfert/suppression/réordre repartiraient d'un modèle
        périmé (chantier 2, spec réparation 2026-07-06)."""
        if self._last_repair_steps:
            self._resync_features_after_repair("ia")
        self._commit_generated_code()      # code déjà en éditeur (réparé)
        # Code livré : on libère le verrou (voile + bouton).
        self._busy_text_override = None
        self._set_generating(False)
        self._refresh_action_button_styles()
        s = lang_manager.current
        # « Réparé ✓ » si une réparation a été appliquée pendant cette vérif,
        # sinon « Le code compile ✓ » (compilé direct).
        label = (s.studio_verify_repaired_ok if self._last_repair_steps
                 else s.studio_verify_ok)
        self._active_output_area().begin_phase(
            label, theme_manager.current.signal_ok)
        # TODO #89 : le code est LIVRÉ (il compile) — et il peut être
        # correct fonctionnalité par fonctionnalité tout en étant cassé à la
        # COMPOSITION : un `delay()` fige la boucle ENTIÈRE, donc le bouton
        # d'une autre fonctionnalité ne répond plus qu'une fois par tour. On
        # le dit ici, après la livraison, jamais avant : tant que la vérif
        # tourne, il n'y a pas encore de code à commenter.
        self._offer_non_blocking_rewrite()

    def _finalize_verify_failure(self, errors: str):
        """Échec final (compile KO + réparations KO, recombine épuisé ou non
        éligible). v2 : on ne LIVRE JAMAIS de code cassé -> revert au baseline
        capturé avant la génération (1ʳᵉ génération -> template vide ; code
        antérieur -> ce code), puis on expose le pont chat « Demander de l'aide ».
        Garde : si l'utilisateur a édité le code provisoire pendant la vérif, on
        respecte son travail (pas de revert)."""
        s = lang_manager.current
        out = self._active_output_area()
        # Chantier 3 : si la réparation a laissé un code structurellement cassé
        # alors qu'assemble(features) est propre, OFFRIR une reconstruction
        # déterministe depuis le modèle (plutôt que de revert au baseline
        # pré-génération, qui jette la génération). Choix explicite de l'user.
        if (self.get_code() == self._verify_delivered_code
                and self._can_reconstruct_from_features("ia")
                and self._confirm_reconstruct_from_features("ia")):
            self._reconstruct_from_features("ia")
            self._busy_text_override = None
            self._set_generating(False)
            self._refresh_action_button_styles()
            return
        if self.get_code() == self._verify_delivered_code:
            self._features = [copy.deepcopy(f) for f in self._gen_revert_features]
            self._set_code_with_attribution(self._gen_revert_code, self._features)
            self._code_baseline = self._gen_revert_code
            self._index_features(self._gen_revert_code, self._features)
            self._has_generated = bool(self._features)
            self._emit_chat_context()
            self.save_project()
        # Fin de l'opération : on libère le verrou (voile + bouton).
        self._busy_text_override = None
        self._set_generating(False)
        self._refresh_action_button_styles()
        out.set_failed(s.studio_verify_failed)
        if errors:
            out.append_explanation(errors)
        out.set_done(False, errors)   # expose le bouton « Demander de l'aide »

    def _start_recombine(self):
        from .generation.gen_prompts import combine_feature_prompts
        from .generation.feature_model import ai_features
        s = lang_manager.current
        out = self._active_output_area()
        out.begin_phase(s.studio_recombine, "#8b5cf6")
        # Le voile indique « régénération… » (verrou maintenu).
        self._busy_text_override = s.studio_recombine
        self._refresh_busy_loader()
        # Exclut `manual` de l'intent (code manuel = pas de prompt à rejouer).
        combined = combine_feature_prompts(
            [f.full_prompt() for f in ai_features(self._features)])
        backend = get_backend_instance(ai_config.backend_id)
        if backend is None:
            # Pas de backend : impossible de recombiner -> échec final (revert).
            self._finalize_verify_failure("")
            return
        self._gen_worker = _GenerateWorker(
            backend, combined, self._board_name(), self._current_mode,
            comment_verbosity=self._comments_verbosity(),
        )
        self._gen_worker.finished.connect(self._on_recombine_done)
        self._gen_worker.error.connect(self._on_gen_error)
        self._gen_worker.start()

    def _on_recombine_done(self, code: str):
        from .code_format import reindent_code
        from .generation.gen_prompts import combine_feature_prompts
        from .generation.feature_model import MANUAL_ID, ai_features
        summary = extract_feature_summary(code)
        ai_feats = ai_features(self._features)
        combined_prompt = combine_feature_prompts(
            [f.full_prompt() for f in ai_feats])
        # La fusion garde l'UNION des historiques (une régénération future
        # rejoue tous les intents d'origine, pas le texte combiné dérivé).
        # `manual` (sans historique) n'y contribue pas.
        hist = [p for f in ai_feats for p in f.prompts] or [combined_prompt]
        try:
            p = parse_sketch(code)
        except SketchParseError:
            p = None
        f1 = self._feature_from_parsed(p, "f1", combined_prompt, summary,
                                       prompts=hist, carry_from=ai_feats)
        # Préserve la feature `manual` : le recombine fusionne les intents IA en
        # f1, mais le code MANUEL n'a pas d'intent -> il serait perdu s'il était
        # collapsé. On le garde à part (toujours en dernier).
        manual = [f for f in self._features if f.id == MANUAL_ID]
        self._features = [f1] + manual
        new_code = reindent_code(assemble(self._features))
        self._set_code_with_attribution(new_code, self._features)
        # Provisoire : PAS _commit_generated_code ici (pas de baseline, pas
        # d'index, pas de save) tant que la re-vérif n'a pas confirmé (v2).
        self._verify_delivered_code = self.get_code()
        # _recombine_attempted == True -> un nouvel échec ira vers
        # _finalize_verify_failure (revert au baseline pré-génération).
        if not self._start_assembly_verify():
            # Plus de vérif possible (cas limite) : on livre le code recombiné.
            self._finalize_verify_success()

    def _maybe_progress_nudge(self, *, mode: str, counter_key: str,
                              threshold: int, nudge_key: str,
                              message: str, action_label: str,
                              target_mode: str) -> None:
        """Affiche le nudge `nudge_key` UNE seule fois (drapeau app-wide) si on
        est encore dans `mode` et que le compteur a atteint `threshold`. Le nudge
        est un bandeau non-bloquant et actionnable (`action_label` bascule vers
        `target_mode`)."""
        if not PN.should_show_nudge(
            count=session.progress_count(counter_key),
            threshold=threshold,
            seen=session.nudge_seen(nudge_key),
            in_target_mode=(self._current_mode == mode),
        ):
            return
        self._nudge_target_mode = target_mode
        self._nudge_banner.show_nudge(message, action_label)
        session.mark_nudge_seen(nudge_key)

    def _maybe_intermediate_banner_nudge(self) -> None:
        """Bandeau vert Intermédiaire→Avancé au seuil d'ACTIONS (#35). Message
        « 2 fenêtres », une seule fois (drapeau app-wide)."""
        self._maybe_progress_nudge(
            mode="intermediate",
            counter_key=PN.COUNTER_INTERMEDIATE,
            threshold=PN.INTERMEDIATE_EDIT_THRESHOLD,
            nudge_key=PN.NUDGE_INTERMEDIATE,
            message=lang_manager.current.nudge_intermediate_to_advanced,
            action_label=lang_manager.current.readonly_popup_switch,
            target_mode="advanced",
        )

    def _register_manual_edit_segment(self) -> None:
        """Compte UN segment d'édition manuelle (#35) : ouvert au 1er edit à la
        main qui suit une génération/upload, refermé par la prochaine
        génération/upload. Uniquement en Intermédiaire. Chaque segment compte
        pour la popup (MANUAL_EDIT_NUDGE_THRESHOLD) ET le bandeau
        (INTERMEDIATE_EDIT_THRESHOLD)."""
        if self._current_mode != "intermediate" or self._manual_edit_segment_open:
            return
        self._manual_edit_segment_open = True
        session.bump_progress_count(PN.COUNTER_MANUAL_EDIT)
        session.bump_progress_count(PN.COUNTER_INTERMEDIATE)
        # Popup prioritaire ce tick : si elle s'affiche, on ne double pas avec le
        # bandeau (qui pourra tomber au prochain segment/action).
        if not self._maybe_manual_edit_popup():
            self._maybe_intermediate_banner_nudge()

    def _maybe_manual_edit_popup(self) -> bool:
        """Popup « 2 fenêtres » après MANUAL_EDIT_NUDGE_THRESHOLD segments
        d'édition manuelle en Intermédiaire, une seule fois (app-wide). Retourne
        True si elle a été affichée."""
        # Nudge RÉPÉTÉ (QA C5) : il revient à seuils croissants puis se tait.
        # `showings_so_far` reconstruit le compte pour les sessions d'avant ce
        # compteur, sinon un utilisateur de longue date verrait toute la série
        # se déclencher d'un coup.
        count = session.progress_count(PN.COUNTER_MANUAL_EDIT)
        shown = PN.showings_so_far(
            shown=session.nudge_shown(PN.NUDGE_MANUAL_EDIT),
            legacy_seen=session.nudge_seen(PN.NUDGE_MANUAL_EDIT),
            count=count,
            thresholds=PN.MANUAL_EDIT_NUDGE_THRESHOLDS,
        )
        if not PN.should_show_repeating_nudge(
            count=count,
            thresholds=PN.MANUAL_EDIT_NUDGE_THRESHOLDS,
            shown=shown,
            in_target_mode=(self._current_mode == "intermediate"),
        ):
            return False
        # Le compteur d'affichages est la source ; le drapeau historique reste
        # écrit pour que `showings_so_far` sache reconstruire une session qui
        # n'aurait que lui.
        session.mark_nudge_seen(PN.NUDGE_MANUAL_EDIT)
        session.set_nudge_shown(PN.NUDGE_MANUAL_EDIT, shown + 1)
        # Ne PAS afficher ici : on est dans le timeout du debounce de frappe
        # (l'utilisateur est en train de taper). Différé à la prochaine
        # frontière de segment — cf. _maybe_show_deferred_manual_popup.
        self._manual_edit_popup_due = True
        return True

    def _maybe_show_deferred_manual_popup(self) -> None:
        """Affiche la popup « passe en Avancé » due (cf.
        _maybe_manual_edit_popup) à une frontière de segment (fin de
        génération/upload) — jamais pendant la frappe. Abandonnée si
        l'utilisateur a déjà quitté l'Intermédiaire entre-temps."""
        if not getattr(self, "_manual_edit_popup_due", False):
            return
        self._manual_edit_popup_due = False
        if self._current_mode != "intermediate":
            return
        self._show_advanced_nudge_popup()

    @staticmethod
    def _nudge_direction(target_mode: str) -> str:
        """Sens du nudge, énuméré (b2i = débutant→intermédiaire,
        i2a = intermédiaire→avancé)."""
        return "b2i" if target_mode == "intermediate" else "i2a"

    def _on_nudge_action(self) -> None:
        """Clic sur le bouton du bandeau de nudge : ferme le bandeau et bascule
        vers le mode visé."""
        self._nudge_banner.hide()
        if self._nudge_target_mode:
            self._mode_selector._select(self._nudge_target_mode)

    def _clean_new_feature(self, feat: Feature, exclude_ids=None) -> Feature:
        """Removes from the feature what it RE-EMITS from existing features (the
        SLM sometimes spits out the whole sketch instead of the delta) BEFORE storing it.
        Guarantees that its content = its own contributions only → the "Modify" label
        and `resolve_feature_pins` no longer expose foreign pins/refs
        (e.g. servo shown with "PIN_LED"). Called BEFORE the reassignment, so
        that it only reasons about the feature's own pins.

        `exclude_ids` = the features to EXCLUDE from "the existing set" (default: just
        `feat`). In a merge (≥2 features modified together), we exclude
        ALL the merged features: the resulting feature absorbs their code,
        so it must not be "cleaned" of it."""
        from .generation import clean_feature_contributions
        exclude = exclude_ids if exclude_ids is not None else {feat.id}
        _existing = [f for f in self._features if f.id not in exclude]
        return clean_feature_contributions(feat, _existing)

    def _reassign_new_feature_pins(self, feat: Feature, exclude_ids=None) -> Feature:
        """Pin safety net: moves the pins of `feat` that conflict with ANOTHER
        existing feature to valid free pins. Returns the feature
        (possibly mutated) and records the moves/warnings in
        `self._pending_reassign` for the int/advanced notice.

        `exclude_ids` = features to EXCLUDE from the conflict test (default: just
        `feat`). In a merge, we exclude all the merged features (their
        pins are absorbed by `feat`, not in conflict with it)."""
        from .wiring.boards import board_id_for_env_model, load_board
        from .generation import reassign_conflicting_pins
        _bid = board_id_for_env_model(board_manager.env or "arduino",
                                      board_manager.model or "")
        _board = load_board(_bid) if _bid else None
        # existing = all features EXCEPT the one(s) we replace (MODIFY case).
        exclude = exclude_ids if exclude_ids is not None else {feat.id}
        _existing = [f for f in self._features if f.id not in exclude]
        _res = reassign_conflicting_pins(feat, _existing, _board)
        self._pending_reassign = (_res.moves, _res.warnings)
        return _res.feature

    def _apply_feature_change(self, action, old_feature, new_feature, new_features):
        """Applies the change while PRESERVING the editor's manual work.

        - Editor intact (== assembled baseline): we reassemble cleanly (nothing
          to preserve).
        - Editor edited by hand: we SPLICE into the current text. `splice_add`
          never removes anything -> "Add" NEVER deletes a manual addition;
          `splice_replace` only touches the targeted block. The overwrite
          warning appears ONLY if the splice is impossible (anchors broken
          by inline edits) and we therefore have to reassemble.

        Returns the new code, or None if the user refuses the overwrite.
        The caller commits `self._features` only if the return is non-None."""
        current = self._editor.toPlainText()
        if not self._code_baseline or not is_dirty(current, self._code_baseline):
            return assemble(new_features)
        try:
            if action == ADD:
                return splice_add(current, new_feature)
            return splice_replace(current, old_feature, new_feature)
        except SpliceError:
            # Splice impossible (broken anchors) -> reassembling would lose the
            # manual edits: we warn before overwriting.
            if self._confirm_inline_overwrite() != "accept":
                return None
            return assemble(new_features)

    def _apply_merge_change(self, old_features, new_feature, new_features):
        """Applies a MERGE (≥2 features → 1).

        Collapsing N features into one is an explicit and irreversible structural
        change (we will no longer be able to "Modify" them
        separately): we ALWAYS warn the user about it, with a
        dedicated message "they will be merged into one" — and NOT the old
        "manual edits" warning which was not the right
        message in this case.

        Returns the new code, or None if the user refuses."""
        if self._confirm_merge_features(len(old_features)) != "accept":
            return None
        return assemble(new_features)

    def _confirm_merge_features(self, n: int) -> str:
        s = lang_manager.current
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(s.studio_merge_features_title)
        box.setText(s.studio_merge_features_body.format(n=n))
        ok = box.addButton(s.gen_modal_validate, QMessageBox.ButtonRole.AcceptRole)
        box.addButton(s.gen_modal_cancel, QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return "accept" if box.clickedButton() is ok else "cancel"

    def _confirm_inline_overwrite(self) -> str:
        s = lang_manager.current
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(s.studio_inline_overwrite_title)
        box.setText(s.studio_inline_overwrite_body)
        ok = box.addButton(s.gen_modal_validate, QMessageBox.ButtonRole.AcceptRole)
        box.addButton(s.gen_modal_cancel, QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return "accept" if box.clickedButton() is ok else "cancel"

    def _on_ai_tool_requested(self, tool_id: str):
        """Dispatch: each tool_id emitted by the panel finds its
        concrete action here. Tools not yet implemented open a
        "coming soon" placeholder."""
        if tool_id == "explain_lines":
            self._open_explain_dialog()
            return
        if tool_id == "add_comments":
            self._run_add_comments()
            return
        if tool_id == "repair_code":
            self._run_repair_code()
            return
        if tool_id == "format_code":
            self._run_format_code()
            return
        if tool_id == "wiring_diagram":
            self._open_wiring_diagram_dialog()
            return
        s = lang_manager.current
        QMessageBox.information(
            self, s.studio_ai_tools_title, s.studio_tool_coming_soon,
        )

    def _close_open_wiring_dialog(self) -> None:
        """Closes the schema modal if it is open.

        Called by the "?" bridges: the schema modal (WiringDiagramDialog)
        is blocking (exec), so as long as it is open it hides the
        chat we just requested. We close it deferred (QTimer 0) because
        we are called from a nested handler (ambiguity modal
        reopened from the schema) — closing on the next event-loop
        turn avoids destroying a dialog in the middle of event processing.
        """
        dlg = getattr(self, "_open_wiring_dialog", None)
        if dlg is not None:
            QTimer.singleShot(0, dlg.reject)

    def _open_chat_help_unknown_parts(self) -> None:
        """Banner action: ask the chat about the components the app could not
        identify (QA A2, 2026-08-08).

        ONE question lists them all rather than one button per component: the
        user's situation is "the app doesn't know my parts", and splitting it
        would make him ask the same question twice.
        """
        if not self._registry_unknown:
            return
        parts = ", ".join(self._registry_unknown)
        s = lang_manager.current
        prefix = s.chat_help_prefix_unknown.format(parts=parts)
        extras = (
            f"UNKNOWN COMPONENT CONTEXT : les composants {parts} ne figurent "
            f"ni dans le corpus de l'application ni dans le registre de "
            f"bibliotheques Arduino. Le code a donc ete genere SANS reference, "
            f"et risque de ne pas fonctionner.\n"
            f"Aide l'eleve concretement : comment identifier la puce a partir "
            f"des marquages du composant, ou trouver sa documentation ou une "
            f"bibliotheque, et quoi joindre a l'application (un fichier .md "
            f"ou .txt de documentation) pour que la generation suivante soit "
            f"informee. Ne propose PAS de changer de composant : l'eleve a le "
            f"composant qu'il a."
        )
        self.chat_help_requested.emit(prefix, extras)

    def _open_chat_help_motor(self, *, pins: str) -> None:
        """'?' bridge from the consolidated motors section of the modal.

        Unlike the standard bridge (1 pin, choice between components),
        here the question is a dichotomy: do these N pins form ONE
        motor (PWM + direction via driver) or SEPARATE outputs? The
        prefix and the LLM context make this choice explicit."""
        from .i18n import lang_manager
        s = lang_manager.current
        prefix = s.chat_help_prefix_motor.format(pins=pins)
        extras = (
            f"AMBIGUITY CONTEXT (candidat moteur, "
            f"broches {pins}) :\n"
            f"- Ces broches forment soit UN moteur DC (1 broche PWM pour la "
            f"vitesse + 1-2 broches de direction, pilotees via un driver "
            f"H-bridge type L298N), soit DES sorties independantes "
            f"(plusieurs LED/buzzer/servo non lies).\n"
            f"L'eleve veut comprendre comment trancher selon son montage "
            f"reel. Explique simplement, sans jargon electronique, et "
            f"conclus par une recommandation basee sur le materiel typique."
        )
        self.chat_help_requested.emit(prefix, extras)
        self._close_open_wiring_dialog()

    def _open_chat_help_from_ambiguity(
            self, *, pin: str, type_initial: str) -> None:
        """Contextual '?' bridge from AmbiguityDialog (int/advanced mode).
        Builds a technically-oriented prefix + system_extras with the Arduino
        pin and the initial detected type (F2 step 4 Task 3)."""
        from .i18n import lang_manager
        s = lang_manager.current
        # Standard candidates according to the initial detected type.
        candidates_map = {
            "led": "LED, buzzer, moteur DC, servo, stepper",
            "potentiometer": "potentiometre, photoresistance (LDR), "
                             "capteur de temperature, capteur de son",
            "module_generic": "module generique 3-pin (DHT, capteur PIR, "
                              "buzzer actif, IR receiver)",
            "dc_motor": "moteur DC avec driver H-bridge, plusieurs LEDs "
                        "independantes, autre montage 3-broches",
        }
        candidates = candidates_map.get(
            type_initial, "plusieurs types possibles"
        )
        prefix = s.chat_help_prefix_technique.format(
            pin=pin, candidates=candidates,
        )
        extras = (
            f"AMBIGUITY CONTEXT (mode int/avance) :\n"
            f"- Pin Arduino : {pin}\n"
            f"- Type initial detecte par le parseur : {type_initial}\n"
            f"- Candidats consideres : {candidates}\n"
            f"L'eleve veut un explainer technique pedagogique : que faire "
            f"de cette ambiguite, comment trancher selon son hardware reel "
            f"(observation visuelle / multimetre / datasheet du module)."
        )
        self.chat_help_requested.emit(prefix, extras)
        self._close_open_wiring_dialog()

    def _on_wrong_component(self, ref: str, netlist) -> bool:
        """F2-5 safety net: "Ask for advice in the chat" entry of the gear
        menu. ALWAYS opens the correction chat (all modes) with the
        component context; returns True (the dialog closes). At the
        conclusion (CORRECTION: marker), the chat offers "Correct in
        Studio" which fills the prompt with the real component (cf chat_view)."""
        target = next(
            (c for c in netlist.components if c.ref == ref), None,
        )
        if target is None:
            return False
        old_type = target.type
        pins = ", ".join(p.net for p in target.pins if p.net) or "?"
        original_prompt = self.get_prompt()

        from .i18n import lang_manager
        s = lang_manager.current
        prefix = s.chat_help_prefix_wrong_component.format(
            ref=ref, type=old_type,
        )
        known_ids = ("led, buzzer, servo, dc_motor, dht11, dht22, bmp280, "
                     "ds18b20, hcsr04, potentiometer")
        extras = (
            "COMPONENT ADVICE (the student clicked a component on the wiring "
            "schema to ask about it).\n"
            f"- The schema currently shows this component as: {old_type}\n"
            f"- It is wired on pin(s): {pins}\n"
            f"- Original generation prompt: {original_prompt}\n"
            "Answer the student's question about THIS component, helpfully and "
            "simply. Do NOT write code. Do NOT ask the student to install or "
            "download any library (Promptuino installs them automatically). "
            "Avoid pin numbers and jargon when you can. IF, during the "
            "conversation, it becomes clear the component was mis-detected "
            "(it is actually a DIFFERENT physical component), end THAT message "
            "with EXACTLY one line:\n"
            "CORRECTION: <id>\n"
            f"where <id> is one of [{known_ids}], or 'leds:N' for N "
            "independent LEDs. Only add that line when you are confident the "
            "real component differs from what the schema shows; otherwise just "
            "answer normally (no marker)."
        )
        ctx = {
            "old_type": old_type,
            "pins": pins,
            "original_prompt": original_prompt,
        }
        self.wrong_component_help_requested.emit(prefix, extras, ctx)
        self._close_open_wiring_dialog()
        return True

    def _on_code_help_requested(self, function_name: str,
                                  function_body: str) -> None:
        """Contextual '?' right-click bridge in CodeEditor: pre-loads
        the chat with an explanation of the function (F2 step 4)."""
        from .i18n import lang_manager
        s = lang_manager.current
        prefix = s.chat_help_prefix_code.format(function=function_name)
        extras = (
            f"FUNCTION BODY (full source) :\n"
            f"```cpp\n{function_body}\n```\n"
            f"L'eleve a clic-droit sur cette fonction depuis l'editeur "
            f"de code et veut une explication pedagogique. Concentre-toi "
            f"sur le QUOI (ce que fait la fonction) et le POURQUOI "
            f"(intent + interactions hardware), pas sur le COMMENT (syntaxe)."
        )
        self.chat_help_requested.emit(prefix, extras)

    def _on_code_selection_help_requested(self, selected_text: str,
                                           function_name: str) -> None:
        """Contextual '?' bridge from the CodeEditor with an active SELECTION
        (Fix 3). The student highlighted a few lines and right-clicked to
        ask for a targeted explanation. The prefix does not name the
        function (it may not be inside one) but the system_extras includes the
        name of the enclosing function when it exists -- context
        useful to the LLM without overloading the visible question."""
        from .i18n import lang_manager
        s = lang_manager.current
        prefix = s.chat_help_prefix_selection
        ctx_hint = (
            f"(Inside function `{function_name}`.)\n"
            if function_name else
            "(Outside any function -- global scope, includes, or "
            "comments.)\n"
        )
        extras = (
            f"SELECTED LINES (focus of the question) :\n"
            f"```cpp\n{selected_text}\n```\n"
            + ctx_hint
            + "L'eleve a selectionne ces lignes precisement dans "
            "l'editeur de code et veut une explication ciblee SUR CES "
            "LIGNES uniquement -- pas sur la fonction entiere ni sur "
            "le fichier. Concentre-toi sur ce que font ces lignes "
            "specifiquement et pourquoi (intent + interactions hardware). "
            "Utilise le reste du code comme contexte de comprehension, "
            "mais ne l'explique pas."
        )
        self.chat_help_requested.emit(prefix, extras)

    def _on_error_help_requested(self, error_text: str) -> None:
        """Contextual '?' bridge from the LogWidget (compile/upload error
        console). Pre-loads the chat with the error in context
        (F2 step 4)."""
        from .i18n import lang_manager
        s = lang_manager.current
        prefix = s.chat_help_prefix_error
        extras = (
            f"COMPILATION ERROR :\n"
            f"```\n{error_text[:2000]}\n```\n"
            f"L'eleve a clique 'Aide sur cette erreur' depuis le panneau "
            f"console. Explique-lui en francais simple ce qui a echoue, "
            f"sur quelle ligne probable, et comment corriger."
        )
        self.chat_help_requested.emit(prefix, extras)

    def _resolution_key_for(self, component, netlist=None) -> tuple[str, str]:
        """Persistent key of an ambiguous component: (fn_id, pin_arduino).

        To stay stable across generations:
        - Grouped case (DC motor candidate, _grouped_pwm_pin set): we
          use the PWM pin (= real Arduino pin, stable).
        - Standard case: we walk up via the bridge_net (NET_X) to the
          real Arduino pin via `_arduino_signal_pin`. Without this walk-up,
          the key would point to "NET_A" which is unstable (regenerated on
          every parse) -> miss on reload.
        """
        from .wiring.ambiguity_dialog import _arduino_signal_pin
        # Priority 1: grouped PWM pin (DC motor case).
        grouped_pwm = component.attributes.get("_grouped_pwm_pin")
        if grouped_pwm:
            return (component.fn_id or "", grouped_pwm)
        # Priority 2: Arduino pin walked up via bridge.
        net = _arduino_signal_pin(component, netlist)
        if net is None:
            sig = (component.pin("A") or component.pin("SIG") or
                   (component.pins[0] if component.pins else None))
            net = sig.net if sig else "?"
        return (component.fn_id or "", net)

    def _replay_confident_resolutions(self, netlist, ambiguous,
                                      scoped_to_ref) -> bool:
        """Rejoue les résolutions sauvegardées des composants dont le détecteur
        est SÛR. Rend True si le netlist a été modifié.

        La boucle d'application principale n'itère que sur `collect_ambiguous`
        (`_confidence == "low"`), plus la cible de l'engrenage quand il y en a
        une (`include_scoped_target`). Or l'engrenage peut remplacer un
        composant détecté avec CERTITUDE — c'est même explicitement son rôle.
        Le choix partait donc bien dans `_wiring_resolutions` et dans le
        projet, mais plus rien ne le RELISAIT : à la réouverture, le composant
        d'origine revenait, et l'utilisateur voyait son remplacement disparaître
        sans explication (QA, 2026-08-10 : relais remplacé par un capteur
        déclaré, perdu au rechargement).

        Mesuré : « Allume un relais sur la broche 7 » sort un relais à
        `_confidence == "high"` et `collect_ambiguous` renvoie une liste VIDE.

        Le défaut était déjà décrit un cran plus bas, pour les placeholders, dans
        `_already_resolved_refs` (« since a placeholder is never in
        `collect_ambiguous` either, nothing would re-apply its own saved
        resolution on reopen ») — sans être généralisé aux composants sûrs.

        Trois refus délibérés :
        - ces composants ne sont JAMAIS ajoutés à `unresolved` : seul
          l'engrenage doit les amener à la modale, sinon un `force_remodal`
          global se mettrait à proposer des composants que le code identifie
          sans ambiguïté ;
        - la cible de l'engrenage est sautée : elle va être rouverte, la figer
          ici reviendrait à ignorer le clic ;
        - une clé dont la part « net » est vide est ignorée, même raison que
          `_already_resolved_refs` : elle est commune à TOUS les placeholders
          d'une même fonction, et c'est la bibliothèque de composants déclarés
          qui s'occupe de ceux-là.
        """
        from .wiring.ambiguity_dialog import apply_saved_resolution
        from .wiring.markers import (STEPPER_DRIVERS,
                                     apply_stepper_driver_swap)  # noqa: F401
        from .wiring.netlist import COMPANION_ROLES
        seen = {c.ref for c in ambiguous}
        mutated = False
        for c in list(netlist.components):
            if c.ref in seen or c.ref == scoped_to_ref:
                continue
            # QUATRIÈME refus, ajouté après la QA du 2026-08-27 : les
            # compagnons posés par l'inférence (résistance série, pull-up)
            # PARTAGENT la clé du composant qu'ils accompagnent — la LED vit
            # sur un net interne, sa résistance fait le pont jusqu'à la broche
            # Arduino, et `_resolution_key_for` rend ('', 'D7') pour les deux.
            # Sans ce saut, répondre « LED » à la modale puis rouvrir le schéma
            # transformait la résistance en une SECONDE LED, cassait le pont de
            # la vraie, et faisait dégénérer sa clé vers le net interne — qui
            # partait ensuite dans le projet. Mesuré sur `digitalWrite(7, HIGH)`
            # seul : 2 composants au premier tour, 4 au second.
            #
            # Un compagnon n'a jamais été un choix de l'utilisateur : il n'a
            # rien à recevoir d'un rejeu. La garde est volontairement ÉTROITE
            # (le `role`, pas `inferred` — une LED détectée est `inferred` elle
            # aussi), sans quoi elle reprendrait ce que ce rejeu existe
            # justement pour rendre.
            if c.attributes.get("role") in COMPANION_ROLES:
                continue
            key = self._resolution_key_for(c, netlist)
            if not key[1]:
                continue
            # ⚠️ Un driver pas-a-pas rejoue SON chemin, sous SA cle. Deux
            # raisons, la seconde mesuree en revue le 2026-08-29 :
            #   - `apply_saved_resolution(a4988, "drv8825")` rend une **LED**
            #     (ce dispatch ne connait que les composants ambigus) ;
            #   - la cle NUE d'un driver est PARTAGEE. `_resolution_key_for`
            #     remonte au signal Arduino, et le NEMA17 relie au driver y
            #     aboutit aussi : les deux valent `('', 'D2')`. Ecrire le type
            #     du driver sous cette cle-la faisait heriter le MOTEUR (et, sur
            #     un TMC2209 UART, la PILE) d'une resolution qui n'etait pas la
            #     sienne -- ils devenaient des LED a la reouverture. Le suffixe
            #     dedie, que le plan exigeait et que j'avais economise, supprime
            #     la collision a la source.
            if c.type in STEPPER_DRIVERS:
                choisi = self._wiring_resolutions.get(
                    (key[0], key[1] + "::_stepper_driver"))
                if choisi and apply_stepper_driver_swap(c, choisi):
                    mutated = True
                continue
            saved = self._wiring_resolutions.get(key)
            if not saved or saved == c.type:
                continue
            driver = (self._wiring_resolutions.get((key[0], key[1] + "::_driver"))
                      if saved == "dc_motor" else None)
            apply_saved_resolution(c, saved, netlist, driver_type=driver)
            mutated = True
        return mutated

    def _already_resolved_refs(self, netlist) -> set[str]:
        """Refs already resolved by a saved `_wiring_resolutions` entry,
        keyed via `_resolution_key_for` -- used to keep the declared-
        component library from overriding a resolution the user made HERE,
        in the current project.

        Only trusts keys whose net part is non-empty. An `unrecognized`
        placeholder has no wired pin, so its key degenerates to
        `(fn_id, "")` -- indistinguishable from any OTHER placeholder in the
        same function. Treating that as "already resolved" backfires twice:
        resolving one placeholder via the gear would silently suppress the
        library for every sibling placeholder sharing the same empty key,
        and since a placeholder is never in `collect_ambiguous` either,
        nothing would re-apply its own saved resolution on reopen -- it
        would regress to a raw, unwired box with the safety-net warnings
        back. The declared-component library is exactly the mechanism meant
        to handle these boxes, so a net-keyed guard must stay out of its way
        for them.
        """
        out: set[str] = set()
        for c in netlist.components:
            try:
                key = self._resolution_key_for(c, netlist)
            except Exception:
                continue
            if key[1] and key in self._wiring_resolutions:
                out.add(c.ref)
        return out

    def _declared_optouts(self) -> dict[str, str]:
        """Normalized header -> type_id, from every `declared_optout::`
        entry in `_wiring_resolutions`. Fed to `apply_library_to_netlist` so
        a past "no, it's actually a led" choice keeps winning over the
        declared-component library on every reopening, not just the session
        where it was made."""
        out: dict[str, str] = {}
        for (fn_id, net), type_id in self._wiring_resolutions.items():
            if fn_id == "" and net.startswith(_DECLARED_OPTOUT_PREFIX):
                out[net[len(_DECLARED_OPTOUT_PREFIX):]] = type_id
        return out

    def _persist_declared_optout(self, comp, normalized_header: str,
                                 type_id: str) -> None:
        """Record (or clear) the user's choice for a declared component's
        header. Called right after a manual resolution is applied to a
        component that WAS an opt-out candidate before the mutation (cf
        `_declared_opt_candidate`).

        - Non-`custom:` type_id -> the user opted OUT of the declaration for
          this header: persist the opt-out so it survives reopening, and
          stamp `OPTOUT_HEADER_ECHO_ATTR` on `comp` so a LATER edit (in this
          same reopening, before the netlist is re-parsed) can still find
          the header even though the transform just wiped `attributes`.
        - `custom:` type_id -> the user (re)confirmed a declaration for
          this header: only the PERSISTED opt-out is removed (it must not
          keep overriding the fresh declaration on reload). The echo
          attribute on `comp` is deliberately left in place: `_apply_declared`
          mutates `attributes` IN PLACE and never restores a "header" entry
          once a wholesale-replacing transform (e.g. `_to_led`) has
          wiped it -- popping the echo here would strand the NEXT opt-out
          with no handle at all. Reproduced (review 2026-07-30 #1):
          custom:as7341 -> led -> custom:as7341 -> buzzer -- with the echo
          popped on the 3rd step, the 4th step found no header and silently
          persisted nothing. The echo is harmless to leave in place: it is
          never itself persisted to disk, and is recomputed fresh (from the
          raw placeholder's "header", or from the opt-out replay) on every
          reopening.
        """
        if not normalized_header:
            return
        from .declared_components import TYPE_PREFIX
        from .wiring.declared_apply import OPTOUT_HEADER_ECHO_ATTR
        key = ("", _DECLARED_OPTOUT_PREFIX + normalized_header)
        if type_id.startswith(TYPE_PREFIX):
            self._wiring_resolutions.pop(key, None)
        else:
            self._wiring_resolutions[key] = type_id
            comp.attributes[OPTOUT_HEADER_ECHO_ATTR] = normalized_header

    def _declared_opt_candidate(self, comp) -> tuple[bool, str]:
        """(is_candidate, normalized_header) for `comp`, read BEFORE any
        mutation the caller is about to apply.

        A component is an opt-out candidate if it still carries the
        detector's "header" attribute (genuinely unrecognized / presumed
        wiring, or a user-declared component -- `_apply_declared` keeps
        "header" intact) OR the echo left behind by an EARLIER opt-out
        applied during this same reopening (`OPTOUT_HEADER_ECHO_ATTR`) --
        without the echo fallback, re-choosing the declared type for a
        component the opt-out pass already converted this session (e.g.
        custom:as7341 -> led, then back to custom:as7341) would find no
        header to key off, and the stale opt-out would linger forever.
        """
        from .declared_components import normalize_header
        from .wiring.declared_apply import OPTOUT_HEADER_ECHO_ATTR
        is_declared_state = bool(
            comp.attributes.get("unrecognized")
            or comp.attributes.get("presumed_wiring")
            or comp.attributes.get("user_declared"))
        raw_header = comp.attributes.get("header") or ""
        if raw_header:
            return is_declared_state, normalize_header(raw_header)
        echo = comp.attributes.get(OPTOUT_HEADER_ECHO_ATTR) or ""
        if echo:
            return True, echo
        return is_declared_state, ""

    def _editable_wiring_refs(self, netlist) -> set[str]:
        """Refs of components that have a saved resolution in
        `_wiring_resolutions`. Used by the interactive schema (Level 2):
        only these components have an individual edit pencil.

        Also includes the drivers (l298n, l293d, etc.) associated with an
        editable motor via `_paired_motor`: the driver is added by
        inference (not in the code), its key is not in
        `_wiring_resolutions` directly, but the user can
        click on it to open the modal of the associated motor.

        Excludes the `resistor`s: a series/pullup R shares the same
        `_resolution_key_for` as its parent component (LED, BTN, DHT,
        buzzer) because both walk up to the same Arduino pin via the
        bridge_net. Without exclusion, the pencil would also appear on
        the R, which is misleading — the R has no ambiguity to resolve,
        it is an implicit passive of the parent component.
        """
        from .wiring.markers import STEPPER_DRIVERS
        out: set[str] = set()
        # Les drivers pas-a-pas sont editables SANS resolution prealable, et
        # c'est la seule population dans ce cas. Ils sont detectes par
        # SIGNATURE (le code nomme la puce), donc ils ne passent jamais par la
        # modale d'ambiguite -- mais un A4988 et un DRV8825 sont broche-a-
        # broche compatibles et se ressemblent, et on a le droit de corriger
        # ce que la signature a suppose. `is_replaceable` rend False pour eux
        # (regle du #62), donc sans cette inclusion l'engrenage n'apparait
        # jamais et il n'existe AUCUNE porte vers ce choix.
        for c in netlist.components:
            if c.type not in STEPPER_DRIVERS:
                continue
            # ⛔ Seulement s'il est REELLEMENT remplacable. Un TMC2209 detecte
            # en UART n'a ni STEP ni DIR, donc `apply_stepper_driver_swap` le
            # refuse -- a juste titre, il n'y a aucune broche a reporter. Mais
            # l'engrenage s'ouvrait quand meme : l'utilisateur choisissait,
            # validait, et RIEN ne bougeait sans un mot. Une porte qui ne mene
            # nulle part ment autant qu'un mauvais schema.
            step, direction = c.pin("STEP"), c.pin("DIR")
            if (step is not None and direction is not None
                    and step.net and direction.net):
                out.add(c.ref)
        if not self._wiring_resolutions:
            return out
        editable_motors: set[str] = set()
        for c in netlist.components:
            if c.type == "resistor":
                continue
            try:
                key = self._resolution_key_for(c, netlist)
            except Exception:
                continue
            if key in self._wiring_resolutions:
                out.add(c.ref)
                editable_motors.add(c.ref)
        # Explicit inclusion of drivers paired with an editable motor.
        for c in netlist.components:
            if c.type == "resistor":
                continue
            paired = c.attributes.get("_paired_motor")
            if not paired:
                continue
            for motor_ref in (m.strip() for m in str(paired).split(",")):
                if motor_ref in editable_motors:
                    out.add(c.ref)
                    break
        return out

    def _wiring_has_choices_to_edit(self, code: str, board_id: str,
                                     prompt: str, context: str,
                                     prompts_by_fn: dict) -> bool:
        """True if a global "Edit choices" would actually open the modal.

        Drives the enabled state of the schema dialog's button. It re-analyzes
        the CODE rather than reading the dialog's netlist, and that is the
        whole difficulty of this predicate: the dialog holds a RESOLVED
        netlist, where resolving has already cleared `_confidence == "low"`
        — asking it would answer "nothing to edit" every time.

        Cheap enough to run on every render (measured 2026-08-17: 0.58 ms per
        `analyze_netlist`), which is what keeps the state in step with the
        netlist instead of freezing at construction time.

        Mirrors `_resolve_wiring_netlist` up to the modal decision: same
        analysis, same declared-library pass, then `collect_all_editable`.

        ⚠️ Le critere a change le 2026-08-29 : c'etait `collect_re_editable`
        (les seules AMBIGUITES). Le bouton s'appelle desormais « Modifier les
        composants » et ouvre TOUT ce qui porte un engrenage, donc il reste
        actif tant que le schema contient un composant corrigible -- y compris
        apres que toutes les ambiguites ont ete tranchees.

        Fails OPEN (True) rather than raising: a probe for a button state must
        never break the schema, and of the two possible errors — a button that
        does nothing, or a feature the user can no longer reach — only the
        second takes something away. The button is the cosmetic one."""
        try:
            from .wiring.layout import pipeline as _v2
            from .wiring.ambiguity_dialog import collect_all_editable
            from .wiring.declared_apply import apply_library_to_netlist
            netlist = _v2.analyze_netlist(
                code, board_id, prompt=prompt, context=context,
                prompts_by_fn=prompts_by_fn,
                suppressed_headers=self._banned_wiring_headers(),
            )
            apply_library_to_netlist(
                netlist, skip_refs=self._already_resolved_refs(netlist),
                opt_outs=self._declared_optouts(),
            )
            return bool(collect_all_editable(
                netlist, self._editable_wiring_refs(netlist)))
        except Exception:
            return True

    def _banned_wiring_headers(self) -> frozenset[str]:
        """En-têtes des libs BANNIES par un swap de puce (cible nue) sur au
        moins une feature — et forcées par aucune. Passés à `analyze_netlist`
        (→ `markers._strip_suppressed_includes`) : un `#include` orphelin
        laissé par la régénération recréait la boîte de la puce remplacée, et
        la résolution sauvegardée du swap s'y réappliquait (QA AC1,
        2026-08-31 — l'écran banni renaissait en « LED anode 5V »).

        Règle simple assumée : les includes sont globaux au sketch, le ban
        est par feature. Une lib bannie dans une feature ET re-forcée dans
        une autre (re-swap inverse) reste dessinée ; une lib bannie quelque
        part et simplement utilisée ailleurs perdrait sa boîte — cas
        construit, accepté et documenté ici plutôt que deviné."""
        from .rag import corpus_entry
        forced = {cid for f in self._features
                  for cid in getattr(f, "forced_lib_ids", [])}
        out: set[str] = set()
        for f in self._features:
            for cid in getattr(f, "banned_lib_ids", []):
                if cid in forced:
                    continue
                entry = corpus_entry(cid) or {}
                out.update(h for h in (entry.get("headers") or []) if h)
        return frozenset(out)

    def _resolve_wiring_netlist(self, code: str, board_id: str,
                                 prompt: str, context: str,
                                 prompts_by_fn: dict,
                                 force_remodal: bool = False,
                                 scoped_to_ref: str | None = None):
        """Analysis phase + ambiguity modal BEFORE opening the wiring
        dialog. Returns the resolved netlist, or None if the user
        cancels the modal (in which case the dialog must not open).

        `force_remodal=True`: bypasses the saved resolutions and
        re-triggers the modal for ALL ambiguous components. Used
        by the dialog's "Modify choices" button. If the user
        validates, the new resolutions overwrite the old ones; if they
        cancel, the old ones stay intact (we return None).

        `scoped_to_ref`: ref of the only component to re-modal
        (Level 2 of the interactive schema: per-component pencil). All
        the other ambiguous components apply their saved resolution.
        Implies force_remodal for THIS ref. If the modal is cancelled,
        the old resolution of the ref stays intact.
        """
        # Édition câblage initiée par l'utilisateur (« Modifier les choix » /
        # crayon par composant) — vs auto-résolution à l'ouverture (sans flag).
        if force_remodal or scoped_to_ref:
            pass
        from .wiring.layout import pipeline as _v2
        from .wiring.ambiguity_dialog import (
            AmbiguityDialog, apply_saved_resolution, collect_all_editable,
            collect_ambiguous, include_scoped_target,
            is_silently_resolved_servo,
        )
        from .wiring import inference

        netlist = _v2.analyze_netlist(
            code, board_id, prompt=prompt, context=context,
            prompts_by_fn=prompts_by_fn,
            suppressed_headers=self._banned_wiring_headers(),
        )
        # La preuve du code (broches vues au constructeur) est photographiée
        # ICI, au plus tôt : la première application venue la détruit
        # (SAFETY_NET_ATTRS), et le verdict sur les fiches déclarées doit
        # pouvoir être rejoué tout en bas, une fois la modale passée.
        from .wiring.declared_apply import (apply_library_to_netlist,
                                            capture_constructor_pins,
                                            refresh_declared_verdict)
        capture_constructor_pins(netlist)
        # Bibliothèque de composants déclarés : passe DÉDIÉE, avant la cascade
        # d'ambiguïté. Elle ne peut pas rejoindre cette cascade, qui n'itère que
        # sur collect_ambiguous (_confidence == "low") — un placeholder n'est
        # délibérément pas marqué ainsi. On saute les composants déjà résolus
        # dans CE projet : l'utilisateur y a agi, c'est plus spécifique que sa
        # bibliothèque.
        _already = self._already_resolved_refs(netlist)
        if apply_library_to_netlist(netlist, skip_refs=_already,
                                     opt_outs=self._declared_optouts()):
            mutated_by_library = True
        else:
            mutated_by_library = False
        # « Modifier les composants » (bouton global du schéma) ouvre TOUS les
        # composants corrigibles, pas les seules ambiguïtés : on doit pouvoir
        # revenir sur un composant reconnu avec certitude, et retrouver ceux
        # d'une fonctionnalité générée plus tôt (demandé le 2026-08-29).
        # L'ouverture AUTOMATIQUE du schéma, elle, ne montre que les
        # ambiguïtés — c'est une question, pas un inventaire.
        if force_remodal and scoped_to_ref is None:
            ambiguous = collect_all_editable(
                netlist, self._editable_wiring_refs(netlist))
        else:
            ambiguous = collect_ambiguous(netlist)
        # SP2: the manual replacement (gear "Modify this component")
        # also targets components detected WITH certainty (named LED,
        # servo via Servo.h, OLED I2C...), absent from collect_ambiguous. We
        # guarantee that the scoped ref reaches the modal.
        ambiguous = include_scoped_target(ambiguous, netlist, scoped_to_ref)
        unresolved: list = []
        mutated = mutated_by_library

        # Auto-applies the persisted resolutions (unless force_remodal,
        # in which case everything goes through the modal). For dc_motor, we
        # also retrieve the persisted chosen driver (key with the
        # '_driver' suffix in _wiring_resolutions).
        # In scoped mode on a grouped DC motor, we must also re-modal
        # its siblings (other motors with `_grouped_pwm_pin`). Otherwise the
        # modal only sees 1 motor and does not offer the "1 shared
        # driver" mode, which ends up creating 2 separate drivers after
        # inference (the other motor keeps its old resolution).
        scoped_sibling_refs: set[str] = set()

        # Pre-pass: if a grouped LED (= auto-detected DC motor) has a
        # saved resolution that is NOT "dc_motor", the user has
        # explicitly said "these pins are not a motor" -- we ungroup
        # BEFORE the application loop, otherwise the direction pins stay
        # invisible (removed by _create_motor_group, never recreated).
        # Typical case: detector groups 6 pins into 2 motors, user
        # confirmed 1 motor + ungrouped the other (= 3 individual LEDs/btns).
        # Without this pre-pass: next session the detector re-groups,
        # the load sees "saved=led" on the PWM but loses the dir pins.
        # Skip the pre-pass in global force-remodal ("Modify choices"):
        # the user wants to re-decide everything, we keep the original grouping
        # so they can re-mark a partially ungrouped motor.
        #
        # Also skip when we detect > _MOTORS_HARD_LIMIT grouped motors:
        # in that case force_all_grouped_modal will be True and the modal opens
        # with motors_limit=2. The pre-pass would interfere by ungrouping
        # some motors based on stale saved resolutions (e.g.: pin
        # D6 saved as led in an earlier session when it was
        # a simple LED, and now it is the PWM of motor M2 -> the
        # pre-pass would ungroup M2 wrongly). We want the modal to see all
        # the grouped motors and let the user choose.
        _MOTORS_HARD_LIMIT = 2
        grouped_count_pre = sum(
            1 for c in ambiguous
            if c.attributes.get("_grouped_pwm_pin")
        )
        # NB (2026-08-13): a third term used to sit here — skip the pre-pass
        # for a scoped edit of a grouped motor, in BEGINNER MODE ONLY. It was
        # safe only because the beginner modal rebuilt the partial state from
        # `saved_pin_types` (a reclassified motor came back as an UNCHECKED
        # row). `AmbiguityDialog`, now the only modal, has no equivalent: it
        # pre-checks EVERY grouped motor. Keeping the skip would have silently
        # re-proposed as a motor what the user had already declared not to be
        # one. The pre-pass therefore runs for everyone, which is what the
        # advanced path has always done.
        # ⛔ Le terme `force_remodal and scoped_to_ref is None` a ete RETIRE
        # le 2026-08-29. Il faisait sauter la pre-passe pour « Modifier les
        # choix », au motif qu'on veut pouvoir « re-marquer un moteur
        # partiellement degroupe » — donc en re-proposant en moteur ce que
        # l'utilisateur venait de declarer ne pas en etre un. Releve en QA :
        # « j'avais choisi un moteur + 3 LED, mais si je veux modifier mes
        # choix, les deux sont consideres comme moteurs ».
        #
        # Ce qui justifiait ce saut a disparu : le rail porte desormais un
        # bouton « Regrouper en moteur », donc revenir en arriere ne demande
        # plus qu'on reparte d'un etat faux. Les groupements defaits sont
        # transmis a la modale (`ungrouped_groupings`) pour que ce bouton
        # existe aussi sur ce chemin.
        ungrouped_groupings: list[dict] = []
        skip_prepass = grouped_count_pre > _MOTORS_HARD_LIMIT
        if not skip_prepass:
            from .wiring.netlist import Component, Pin
            for c in list(ambiguous):
                if not c.attributes.get("_grouped_pwm_pin"):
                    continue
                key = self._resolution_key_for(c, netlist)
                saved = self._wiring_resolutions.get(key)
                if saved is None or saved == "dc_motor":
                    continue
                # Saved as non-motor -> ungroup this motor.
                dir_pins = c.attributes.pop("_grouped_dir_pins")
                pwm_pin = c.attributes.pop("_grouped_pwm_pin")
                # Memoire du groupement DEFAIT : la modale en a besoin pour
                # offrir « Regrouper en moteur ». Sans elle, la seule trace
                # de ce montage disparait au moment meme ou l'utilisateur
                # gagne le droit de le contredire.
                ungrouped_groupings.append(
                    {"pwm": pwm_pin, "dirs": list(dir_pins), "ref": c.ref})
                for dir_pin in dir_pins:
                    ref_new = netlist.next_ref("D")
                    new_led = Component(
                        ref=ref_new, type="led", fn_id=c.fn_id,
                        pins=[Pin("A", dir_pin), Pin("K", "GND")],
                        attributes={"_confidence": "low"},
                        inferred=True,
                    )
                    netlist.add_component(new_led)
                    ambiguous.append(new_led)

        # Freres moteurs d'une edition scopee — calcules ICI, APRES la
        # pre-passe. Avant, ils l'etaient AVANT : la cible apparaissait encore
        # groupee alors que la pre-passe s'appretait a la degrouper, et
        # l'engrenage d'une LED embarquait le groupe moteur voisin « sans
        # raison » (releve en QA, 2026-08-29). Le partage d'un pont en H
        # double reste la seule raison d'embarquer un frere : deux editions
        # separees creeraient deux pilotes la ou le materiel n'en a qu'un.
        if scoped_to_ref is not None:
            target = next(
                (c for c in ambiguous if c.ref == scoped_to_ref), None)
            if (target is not None
                    and target.attributes.get("_grouped_pwm_pin")):
                for c in ambiguous:
                    if (c.ref != scoped_to_ref
                            and c.attributes.get("_grouped_pwm_pin")):
                        scoped_sibling_refs.add(c.ref)

        # Pre-pass: if N candidate DC motors are grouped but at least
        # ONE has neither a saved resolution nor a per-prompt resolution, we force
        # ALL the candidate motors to the modal to get the consistent
        # consolidated view. Otherwise, a partial save (= K-1 saved + 1 new)
        # shows a "1 DC motor" modal that misses the context of the others
        # (typical case: code regenerated by LLM with partially
        # different pins, old saves persist and a single motor goes to the
        # modal, without the shared driver sub-menu).
        force_all_grouped_modal = False
        # Editorial limit: if more than _MOTORS_HARD_LIMIT candidate DC
        # motors are detected, we force the modal (skip auto-resolve)
        # with the `motors_limit` param so the user chooses which to
        # keep. Otherwise we would have the "short-circuited render" case which deprives
        # the user of any choice.
        _MOTORS_HARD_LIMIT = 2
        grouped_motors_all = [c for c in ambiguous
                               if c.attributes.get("_grouped_pwm_pin")]
        if (not force_remodal and scoped_to_ref is None
                and len(grouped_motors_all) > _MOTORS_HARD_LIMIT):
            # Force all motors to the modal, ignore the saved/prompt.
            # The user must choose 2 of N, the modal opens automatically in
            # partial mode with the first 2 PWMs pre-checked.
            force_all_grouped_modal = True
        elif not force_remodal and scoped_to_ref is None:
            grouped_motors = grouped_motors_all
            if len(grouped_motors) >= 2:
                for c in grouped_motors:
                    k = self._resolution_key_for(c, netlist)
                    # Complet = le driver aussi : un `dc_motor` herite de
                    # l'ancienne auto-resolution (type sans pilote) repart en
                    # modale, et ne doit pas retenir ses freres hors de la
                    # vue consolidee (meme regle que `has_prompt` ci-dessous).
                    has_saved = (
                        k in self._wiring_resolutions
                        and (self._wiring_resolutions[k] != "dc_motor"
                             or (k[0], k[1] + "::_driver")
                             in self._wiring_resolutions)
                    )
                    # Meme exigence que la branche d'auto-resolution : une
                    # suggestion SANS driver ne resout plus rien, donc elle ne
                    # doit pas non plus retenir ses freres hors de la modale
                    # -- sans quoi on recree la vue fragmentee « 1 moteur »
                    # que ce0ca54 avait eliminee.
                    has_prompt = (
                        c.attributes.get("_prompt_suggested_type") == "dc_motor"
                        and bool(c.attributes.get("_prompt_suggested_driver"))
                    )
                    if not has_saved and not has_prompt:
                        force_all_grouped_modal = True
                        break

        # Les composants que le détecteur reconnaît avec CERTITUDE ne sont pas
        # dans `ambiguous`, mais l'engrenage a pu les remplacer : leur
        # résolution se rejoue ici, jamais via la modale (cf. la méthode).
        if self._replay_confident_resolutions(netlist, ambiguous, scoped_to_ref):
            mutated = True

        for c in ambiguous:
            key = self._resolution_key_for(c, netlist)
            # In scoped mode, only the target ref (+ its DC siblings for
            # the dual H-bridge case) should go to the modal. The other
            # components keep their saved resolution.
            is_scoped_target = (
                scoped_to_ref is not None
                and (c.ref == scoped_to_ref
                     or c.ref in scoped_sibling_refs)
            )
            should_modal_global = (force_remodal and scoped_to_ref is None)
            # Force all grouped candidate motors to the modal together
            # when at least one is not silently resolvable (cf
            # pre-pass above).
            is_grouped_motor = bool(c.attributes.get("_grouped_pwm_pin"))
            if (is_scoped_target or should_modal_global
                    or (force_all_grouped_modal and is_grouped_motor)):
                unresolved.append(c)
            elif key in self._wiring_resolutions:
                saved_type = self._wiring_resolutions[key]
                saved_driver = None
                if saved_type == "dc_motor":
                    driver_key = (key[0], key[1] + "::_driver")
                    saved_driver = self._wiring_resolutions.get(driver_key)
                if (saved_type == "dc_motor" and saved_driver is None
                        and is_grouped_motor):
                    # ⚠️ **Un `dc_motor` sauvegarde SANS son driver n'est pas
                    # une decision complete** — personne n'a jamais choisi le
                    # pilote. Cet etat vient de l'ancienne auto-resolution
                    # silencieuse (avant le 2026-08-31), qui persistait le
                    # type et laissait l'inference poser son L298N par
                    # defaut : tout projet moteur cree avant cette date le
                    # porte, et il SILENCIAIT la nouvelle modale — mesure en
                    # QA AB1, deuxieme passe : « toujours pas de modale ».
                    # On retourne a la modale UNE fois (moteurs coches, seule
                    # la question du driver reste) ; l'acceptation ecrit
                    # `::_driver` et le silence revient, legitime cette fois.
                    unresolved.append(c)
                    continue
                apply_saved_resolution(c, saved_type, netlist,
                                        driver_type=saved_driver)
                mutated = True
            elif (c.attributes.get("_prompt_suggested_type") == "dc_motor"
                    and c.attributes.get("_prompt_suggested_driver")):
                # Le prompt (ou le code) nomme le moteur ET son pilote :
                # auto-resolution sans modale, il n'y a plus de question.
                # Type et driver restent editables par l'engrenage. Persiste
                # pour que les ouvertures suivantes restent silencieuses.
                #
                # ⚠️ **Le silence EXIGE le driver depuis le 2026-08-31**
                # (decision utilisateur, QA AB1 du #82). Avant, un moteur
                # suggere SANS pilote etait resolu quand meme, et l'inference
                # posait le L298N par defaut (« historical behavior
                # preserved ») : un driver que personne n'a nomme s'affichait
                # sans un mot. Le #82 venait pourtant d'acter que le choix du
                # driver appartient a la MODALE -- et le cas est frequent,
                # pas marginal : il suffit que le modele nomme ses variables
                # `motor...` (ce qu'il fait des que le prompt parle de
                # moteurs) pour que la suggestion se pose sans puce. Ces
                # moteurs-la tombent desormais dans `unresolved` : la modale
                # s'ouvre, moteurs deja coches, et ne pose que LA question
                # restante -- quelle carte pilote.
                suggested_type = c.attributes["_prompt_suggested_type"]
                suggested_driver = c.attributes.get("_prompt_suggested_driver")
                apply_saved_resolution(c, suggested_type, netlist,
                                        driver_type=suggested_driver)
                self._wiring_resolutions[key] = suggested_type
                self._wiring_resolutions[
                    (key[0], key[1] + "::_driver")
                ] = suggested_driver
                mutated = True
            elif scoped_to_ref is not None:
                # ⛔ EN MODE SCOPÉ, ON N'EMBARQUE QUE LA CIBLE (et ses frères
                # moteurs, traités par `is_scoped_target` plus haut).
                #
                # Ce `else` embarquait TOUT composant sans résolution
                # sauvegardée, y compris ici — en contradiction directe avec
                # le commentaire de `is_scoped_target` juste au-dessus. Relevé
                # en QA le 2026-08-29 : l'engrenage d'une LED ouvrait la
                # modale avec le groupe moteur du schéma à côté, « sans
                # raison ». Le rail n'a rien créé, il a rendu VISIBLE ce que
                # la modale recevait déjà.
                #
                # Ne pas l'ajouter le laisse EXACTEMENT dans l'état où le
                # schéma l'affiche déjà — il n'est ni résolu ni dé-résolu — et
                # « Modifier les choix » (global) continue de l'offrir.
                pass
            else:
                unresolved.append(c)

        # Servo peel-off: LEDs annotated `_prompt_suggested_type=servo`
        # by steps 1+2 (prompt explicitly mentions servo on the pin)
        # -> silent auto-resolution to servo. Mirrors the logic of the
        # dc_motor + driver auto-resolve above. Without this peel-off, these
        # LEDs would fall into Case C (silent auto-LED) and the user would see
        # a LED instead of a servo. No "LED vs servo" modal here: a prompt
        # that says "servo" is not ambiguous (cf memory
        # feedback-visual-modal-ux-decisions item 5).
        #
        # Ran in BEGINNER MODE ONLY until 2026-08-13, which made the two modes
        # persist DIFFERENT `_wiring_resolutions` for the same code + prompt —
        # a direct breach of the project rule that the mode is a display, not
        # a fork in the project state. The evidence this peels on (the code or
        # the prompt named a servo) does not depend on who is looking.
        if unresolved:
            # Shared predicate with `collect_re_editable`: the "Edit choices"
            # button must predict this peel-off, or it stays clickable on a
            # sketch whose only ambiguity is a prompt-named servo.
            servo_annotated = [c for c in unresolved
                               if is_silently_resolved_servo(c)]
            if servo_annotated:
                # Pre-calc of the keys BEFORE mutation (cf
                # feedback-resolution-key-stability: `_arduino_signal_pin`
                # walks up the NET_X bridge of the LED series R, but after
                # `_to_servo` the R is dropped and the pin is no longer bridged).
                keys_servo = [
                    self._resolution_key_for(c, netlist) for c in servo_annotated
                ]
                for c in servo_annotated:
                    apply_saved_resolution(c, "servo", netlist)
                for c, key in zip(servo_annotated, keys_servo):
                    self._wiring_resolutions[key] = "servo"
                unresolved = [c for c in unresolved if c not in servo_annotated]
                mutated = True

        # Mandatory modal for ambiguities not yet seen (or for
        # all of them in force_remodal mode). Cancel = abort without touching
        # the existing saved resolutions. We pass the driver
        # suggested by Phase A (markers._detect_suggested_dc_driver from
        # prompt+doc) so the modal pre-checks the right driver radio.
        if unresolved:
            # Pre-selects in the modal the driver ALREADY CHOSEN (persisted
            # in _wiring_resolutions) for each grouped motor, so that
            # the user finds their last choice instead of the default on
            # reopening (gear). Read by the modal via
            # `_prompt_suggested_driver`.
            for _c in unresolved:
                if not _c.attributes.get("_grouped_pwm_pin"):
                    continue
                _k = self._resolution_key_for(_c, netlist)
                _saved_drv = self._wiring_resolutions.get(
                    (_k[0], _k[1] + "::_driver"))
                if _saved_drv:
                    _c.attributes["_prompt_suggested_driver"] = _saved_drv
            # If the editorial limit forced the "all to the modal" mode
            # (cf block above), we pass motors_limit to the modal so
            # it opens automatically in partial mode with pre-checking and
            # overflow blocking. Otherwise None (standard behavior).
            n_grouped_unresolved = sum(
                1 for c in unresolved
                if c.attributes.get("_grouped_pwm_pin")
            )
            modal_motors_limit = (
                _MOTORS_HARD_LIMIT
                if n_grouped_unresolved > _MOTORS_HARD_LIMIT
                else None
            )
            # Choix deja tranches, restitues a la modale. Sans eux,
            # « Modifier mes choix » rouvrait sur les valeurs par defaut et
            # l'utilisateur perdait tout ce qu'il avait decide -- le pilote de
            # chaque moteur etait deja restitue juste au-dessus, le type ne
            # l'etait pas (retour utilisateur, 2026-08-29).
            #
            # ⚠️ Les cles degenerees sont ignorees : un placeholder a des nets
            # VIDES, donc `_resolution_key_for` rend `(fn_id, "")` pour TOUS,
            # et ils se confondraient. Meme raison que `_already_resolved_refs`.
            initial_choices: dict[str, str] = {}
            for _c in unresolved:
                _key = self._resolution_key_for(_c, netlist)
                if not _key[1]:
                    continue
                _saved_type = self._wiring_resolutions.get(_key)
                if _saved_type:
                    initial_choices[_c.ref] = _saved_type
            modal = AmbiguityDialog(
                unresolved, parent=self,
                prompt=prompt, context=context,
                prompts_by_fn=prompts_by_fn,
                suggested_dc_driver=netlist.metadata.get("_suggested_dc_driver"),
                netlist=netlist,
                motors_limit=modal_motors_limit,
                initial_choices=initial_choices,
                # ⛔ JAMAIS en mode scopé. Ces groupements défaits existent
                # pour que « Regrouper en moteur » reste offert sur
                # « Modifier les choix » ; en mode scopé ils RECREENT une
                # ligne « N moteurs DC » dans le rail, à côté du seul
                # composant qu'on a demandé à modifier. C'est la 3e cause,
                # et la mienne, du défaut « le moteur est là sans raison »
                # (QA, 2026-08-29) : l'engrenage doit montrer UNE ligne.
                ungrouped_groupings=(
                    [] if scoped_to_ref is not None else ungrouped_groupings),
            )
            # Contextual '?' bridge: if the student clicks the help button of a
            # groupbox, the modal closes (reject) and we open the chat with
            # the context (F2 step 4 Task 3).
            def _on_amb_help(pin_net: str, type_initial: str) -> None:
                self._open_chat_help_from_ambiguity(
                    pin=pin_net, type_initial=type_initial,
                )
            modal.help_requested.connect(_on_amb_help)

            # Same bridge for the consolidated "N DC motors" section, whose
            # question is a dichotomy over the whole pin family rather than a
            # component choice on one pin.
            def _on_amb_motor_help(pins: str) -> None:
                self._open_chat_help_motor(pins=pins)
            modal.motor_help_requested.connect(_on_amb_motor_help)
            # Le crayon d'une tuile deja declaree a remplace sa librairie : meme
            # offre de regeneration que la fiche de l'onglet « Composants » et
            # que le crayon du schema debutant. Les trois portes passent par
            # `notify_lib_chosen_in_form` (TODO #52).
            modal.lib_changed_in_form.connect(self.notify_lib_chosen_in_form)
            if modal.exec() != modal.DialogCode.Accepted:
                return None   # cancelled -> abort
            # Pre-computes the keys BEFORE apply_choices: the mutation
            # (_to_dc_motor replaces pins [A,K] with [M+,M-] with net=GND)
            # would otherwise break the pin_arduino lookup.
            keys_before = [
                self._resolution_key_for(c, netlist) for c in unresolved
            ]
            # Header snapshot BEFORE apply_choices, same reasoning: a
            # transform like _to_led replaces component.attributes
            # wholesale, wiping "header" -- must be captured now or the
            # opt-out below can never be recorded.
            _cand_hdr_pairs = [self._declared_opt_candidate(c) for c in unresolved]
            # Types AVANT application : le constat de bibliotheque manquante
            # ne parle que de ce qui a VRAIMENT change. Depuis que
            # « Modifier les composants » ouvre tout le schema, le lancer sur
            # des composants qu'on n'a pas touches en ferait un message
            # bavard -- donc ignore.
            _types_avant = [c.type for c in unresolved]
            declared_candidate_before2 = [p[0] for p in _cand_hdr_pairs]
            header_before2 = [p[1] for p in _cand_hdr_pairs]
            modal.apply_choices(netlist)
            # UNE seule question de regeneration par validation, meme si les
            # deux moteurs d'un pont en H double changent de driver ensemble.
            # ⚠️ Le drapeau est indispensable et distinct de
            # `_pending_regen_swap` : celui-ci reste vide quand l'utilisateur
            # REFUSE, si bien qu'un garde base dessus reposait la question au
            # moteur suivant (attrape par le test, 2026-08-29).
            _swap_deja_demande = False
            # Persistence of the choices — generation AND edit via the gear
            # (scoped): recorded in _wiring_resolutions to survive
            # reopening (keys pre-computed BEFORE apply_choices, cf
            # feedback-resolution-key-stability).
            for c, key, was_declared_candidate, header in zip(
                    unresolved, keys_before,
                    declared_candidate_before2, header_before2):
                if c.type in _stepper_types():
                    # Cle DEDIEE : la cle nue est partagee avec le NEMA17 du
                    # meme driver (cf. le commentaire du rejeu ci-dessus).
                    self._wiring_resolutions[
                        (key[0], key[1] + "::_stepper_driver")] = c.type
                    continue
                if (c.type == "dc_motor"
                        and c.attributes.get("signature_detected")):
                    # ⛔ Un moteur de NIVEAU 1 n'ecrit JAMAIS de resolution :
                    # sa cle est DEGENEREE (les deux moteurs et leur driver
                    # remontent au meme signal Arduino — mesure au #86 (a) :
                    # tous trois valent `('', 'D9')`), donc ecrire ici ferait
                    # heriter les trois du meme type, la corruption exacte que
                    # le ticket predisait si une porte d'edition s'ouvrait
                    # sans corriger la clef. Et il n'y a rien a persister :
                    # le code EST la source. Changer de driver passe par la
                    # REGENERATION — meme mecanique que le swap de puce, une
                    # seule question par validation (T5).
                    _courant = c.attributes.get("_chosen_driver") or "l298n"
                    _choisi = modal.chosen_driver_for(c.ref)
                    if (_choisi and _choisi != _courant
                            and not _swap_deja_demande
                            and getattr(self, "_pending_regen_swap",
                                        None) is None):
                        _tgt = _chip_swap_regen_target(_courant, _choisi)
                        if _tgt is not None:
                            _fn = (c.fn_id
                                   or self._feature_for_chip_swap(
                                       _courant, _choisi))
                            if _fn:
                                _swap_deja_demande = True
                                if self._confirm_regen_after_swap(
                                        _courant, _choisi):
                                    self._pending_regen_swap = (
                                        _fn, _courant, _choisi)
                    continue
                self._wiring_resolutions[key] = c.type
                if c.type == "dc_motor":
                    driver = modal.chosen_driver_for(c.ref)
                    if driver is not None:
                        _dkey = (key[0], key[1] + "::_driver")
                        _ancien = self._wiring_resolutions.get(_dkey)
                        self._wiring_resolutions[_dkey] = driver
                        # Changer de driver, c'est changer de puce. La
                        # divergence est REELLE meme sans bibliotheque : le
                        # code broches-nues d'un TB6612 a un STBY, celui d'un
                        # DRV8833 un SLEEP, celui d'un L298N un ENA. Jusqu'ici
                        # ce choix etait persiste EN SILENCE (spec
                        # << certitude d'abord >>, constat C4).
                        #
                        # Meme mecanisme que les puces : une seule offre par
                        # validation (les deux moteurs d'un pont en H double
                        # changent ensemble), jamais de regeneration sans
                        # confirmation, et la cible passe par le registre
                        # (tache 1 -- sans elle `_chip_swap_regen_target`
                        # rendait None pour TOUS les couples de drivers).
                        if (_ancien is not None and _ancien != driver
                                and not _swap_deja_demande
                                and getattr(self, "_pending_regen_swap",
                                            None) is None):
                            _tgt = _chip_swap_regen_target(_ancien, driver)
                            if _tgt is not None:
                                _fn = (c.fn_id
                                       or self._feature_for_chip_swap(
                                           _ancien, _tgt))
                                if _fn:
                                    _swap_deja_demande = True
                                    if self._confirm_regen_after_swap(
                                            _ancien, _tgt):
                                        self._pending_regen_swap = (
                                            _fn, _ancien, _tgt)
                # Guard against the "Décrire mon composant…" sub-dialog
                # being cancelled INSIDE apply_choices: apply_saved_resolution
                # is then never called for this ref, c.type stays the raw
                # placeholder lib name (neither a catalog type nor
                # `custom:...`) -- persisting THAT as an opt-out would make
                # apply_saved_resolution fall through to the red-LED default
                # on the next reopening. `unrecognized`/`presumed_wiring`
                # being cleared is the actual signal that a transform ran.
                if (was_declared_candidate and header
                        and not (c.attributes.get("unrecognized")
                                 or c.attributes.get("presumed_wiring"))):
                    self._persist_declared_optout(c, header, c.type)
            # Code/wiring mismatch: motor code but no motor choice -> warn
            # (long-term vision: modal BEFORE gen). The wiring will be right
            # while the code still drives a motor, and only the user can
            # reconcile the two. Read AFTER apply_choices, which is what
            # turned each choice into a real `c.type`.
            if code_says_motor_but_none_chosen(
                    code, [c.type for c in unresolved]):
                from PyQt6.QtWidgets import QMessageBox
                s = lang_manager.current
                QMessageBox.information(
                    self,
                    s.motor_mismatch_title,
                    s.motor_mismatch_body,
                )
            # Bibliothèque manquante : le composant choisi en demande une que
            # le code ne cite pas. Constat SEUL — aucune régénération n'est
            # proposée ni lancée (décision utilisateur, 2026-08-29) : l'app
            # signale, l'utilisateur décide.
            _changes = [c for c, avant in zip(unresolved, _types_avant)
                        if c.type != avant]
            # Un swap entre drivers pas-a-pas ne change RIEN au code quand
            # celui-ci pilote en step/dir generique : les quatre sont
            # broche-a-broche compatibles, un sketch AccelStepper les pilote
            # tous. Sans ce filtre, la fonctionnalite de swap declenchait sa
            # propre fausse alerte -- mesure du 2026-08-29.
            if stepper_code_is_driver_agnostic(code):
                from .wiring.markers import STEPPER_DRIVERS as _SD
                _changes = [c for c in _changes if c.type not in _SD]
            _manquants = missing_libs_for_resolved(code, _changes)
            if _manquants:
                from PyQt6.QtWidgets import QMessageBox
                from .wiring.instructions import _label as _lbl
                s = lang_manager.current
                lang = lang_manager.lang
                _lignes = "<br>".join(
                    f"• <b>{_lbl(t, lang)}</b> — <code>{lib}</code>"
                    for t, lib in _manquants)
                QMessageBox.information(
                    self,
                    s.lib_mismatch_title,
                    s.lib_mismatch_body.format(items=_lignes),
                )
            mutated = True
            # Persist the choices to disk right away so they
            # survive the app closing (without waiting for the user to
            # trigger an explicit save or for the auto-save to fire on
            # another dirty change).
            if self._current_project is not None:
                self.save_project()

        # Le verdict sur les fiches déclarées est rendu ICI, et pas dans la
        # passe bibliothèque plus haut : c'est DANS la modale que le crayon
        # d'une card modifie une fiche, et un verdict rendu avant décrivait un
        # schéma que l'utilisateur ne verrait jamais (QA V1, 2026-08-27 — un
        # tour de retard dans les deux sens : message périmé après une
        # correction, silence complet après une casse).
        #
        # ⚠️ AVANT `inference.apply_rules`, délibérément : plus bas, les
        # composants que l'inférence INSÈRE deviendraient des adverses de
        # collision. On corrige un ordre, on ne déplace pas la frontière de ce
        # que l'app sait.
        refresh_declared_verdict(netlist)
        if mutated:
            inference.apply_rules(netlist)
            inference.detect_conflicts(netlist)
        # Applies the Level 3 implicit actions (servo external_power,
        # etc.). After inference so the base is in its
        # canonical state before the user overrides.
        if self._implicit_actions:
            self._apply_saved_implicit_actions(netlist)
        return netlist

    def _apply_saved_implicit_actions(self, netlist) -> None:
        """Applies the implicit actions saved in
        `_implicit_actions` onto `netlist`. For each entry
        (fn_id, pin_arduino, action_id) -> saved_value:
        - Toggle (act.choices is None): compares act.is_active to
          saved_value (bool) and flips via apply_action() if they differ.
        - Selector: compares act.value to saved_value (str) and calls
          apply_action(value=saved_value) if they differ.
        """
        from .wiring import implicit_actions as _ia
        for (fn_id, pin_arduino, action_id), saved_state in self._implicit_actions.items():
            target = None
            for c in netlist.components:
                try:
                    key = self._resolution_key_for(c, netlist)
                except Exception:
                    continue
                if key == (fn_id, pin_arduino):
                    target = c
                    break
            if target is None:
                continue
            for act in _ia.available_actions(target, netlist):
                if act.id != action_id:
                    continue
                if act.choices is None:
                    # Toggle: compare bool
                    if act.is_active != bool(saved_state):
                        _ia.apply_action(target, act.id, netlist)
                else:
                    # Selector: compare value
                    if str(act.value) != str(saved_state):
                        _ia.apply_action(target, act.id, netlist,
                                          value=saved_state)
                break

    def _toggle_implicit_action_for_ref(self, ref: str,
                                         action_id: str,
                                         netlist,
                                         value=None) -> bool:
        """Applies the implicit action `action_id` on the component
        identified by `ref` in `netlist`. Mutates netlist + updates
        `_implicit_actions` + saves the project. Returns True if applied.

        - Toggle (action without `choices`): `value` ignored, flips.
        - Selector (action with `choices`): `value` is the target
          value (str for LED/Buzzer series R).

        Called by WiringDiagramDialog on the gear click. The dialog then
        takes care of regenerating the schema with the mutated netlist.
        """
        from .wiring import implicit_actions as _ia
        target = next((c for c in netlist.components if c.ref == ref), None)
        if target is None:
            return False
        act = next(
            (a for a in _ia.available_actions(target, netlist)
             if a.id == action_id),
            None,
        )
        if act is None:
            return False
        _ia.apply_action(target, action_id, netlist, value=value)
        # Persists the new state. The key follows the wiring_resolutions pattern
        # (fn_id, pin_arduino) + action_id to stay stable across regen.
        try:
            key2 = self._resolution_key_for(target, netlist)
        except Exception:
            return True
        new_act = next(
            (a for a in _ia.available_actions(target, netlist)
             if a.id == action_id),
            None,
        )
        if new_act is None:
            return True
        full_key = (key2[0], key2[1], action_id)
        # Toggle persists act.is_active (bool), selector persists act.value.
        if new_act.choices is None:
            self._implicit_actions[full_key] = bool(new_act.is_active)
        else:
            self._implicit_actions[full_key] = new_act.value
        if self._current_project is not None:
            self.save_project()
        return True

    def _open_wiring_diagram_dialog(self):
        """Schéma du code IA (éditeur principal / fenêtre de gauche). Slot
        sans argument (évite le piège clicked(bool))."""
        # Prompts per feature: each Feature has 1 prompt. Indexed by "fn-N"
        # token so the modal and the disambiguation use the right prompt.
        prompts_by_fn: dict[str, str] = {}
        for feat in self._features:
            if not feat.prompt:
                continue
            tok = (f"fn-{feat.id[1:]}"
                   if feat.id.startswith("f") and feat.id[1:].isdigit()
                   else feat.id)
            prompts_by_fn[tok] = feat.prompt
        self._open_wiring_for(self._editor.toPlainText(), prompts_by_fn)

    def _open_stable_wiring_diagram_dialog(self):
        """Schéma du code STABLE (fenêtre de droite). Pas de fonctionnalités
        -> pas de prompts par fonction (désambiguïsation depuis le code seul).
        Slot sans argument (évite le piège clicked(bool))."""
        code = self._stable_panel.editor.toPlainText()
        if not code.strip():
            from PyQt6.QtGui import QCursor
            QToolTip.showText(QCursor.pos(), lang_manager.current.studio_err_no_code)
            return
        self._open_wiring_for(code, {})

    def _open_wiring_for(self, code: str, prompts_by_fn: dict):
        # Non-AI tool: no backend check. The flow is in 2 phases:
        # 1. analyze + ambiguity modal (if needed) -- the user
        #    MUST resolve the ambiguities before seeing the schema.
        # 2. opening the dialog with the already-resolved netlist.
        from .wiring.boards import board_id_for_env_model
        from .wiring.wiring_diagram_dialog import WiringDiagramDialog
        env, model = board_manager.env, board_manager.model
        board_id = board_id_for_env_model(env or "arduino", model or "")

        prompt = self._prompt_field.toPlainText().strip()
        ctx_path = self._context_file_abs_path()
        context = ""
        if ctx_path is not None:
            try:
                context = ctx_path.read_text(encoding="utf-8")
            except OSError:
                context = ""

        # Phase 1: analyze + possible modal
        netlist = self._resolve_wiring_netlist(
            code, board_id, prompt, context, prompts_by_fn,
        )
        if netlist is None:
            return   # modal cancelled -> we do NOT open the dialog

        # Phase 2: opening the dialog with the already-resolved netlist
        dlg = WiringDiagramDialog(
            code, board_id, self,
            prompt=prompt, context=context,
            project_name=(self._current_project.name
                          if self._current_project is not None else ""),
            resolutions=self._wiring_resolutions,
            prompts_by_fn=prompts_by_fn,
            netlist=netlist,
            resolve_fn=self._resolve_wiring_netlist_tracked,
            editable_refs_fn=self._editable_wiring_refs,
            can_edit_choices_fn=self._wiring_has_choices_to_edit,
            toggle_implicit_action_fn=self._toggle_implicit_action_for_ref,
            wrong_component_fn=self._on_wrong_component,
        )
        # Remembers the open schema modal: a "?" bridge (re-editing the
        # choices from the schema) must be able to close it, otherwise it stays
        # on top and hides the chat (blocking modal).
        self._open_wiring_dialog = dlg
        try:
            dlg.exec()
        finally:
            self._open_wiring_dialog = None
        # Task 9 : si une puce détectée a été remplacée dans le schéma (vrai
        # changement de lib), proposer de régénérer la fonctionnalité concernée.
        self._process_pending_chip_swaps()

    def _open_explain_dialog(self):
        s = lang_manager.current
        backend = get_backend_instance(ai_config.backend_id)
        if backend is None or not backend.is_available():
            QMessageBox.warning(
                self, s.studio_ai_tools_title, s.studio_explain_no_backend,
            )
            return
        from .explain_code_dialog import ExplainCodeDialog
        ed = self._tools_editor()
        code = ed.toPlainText()
        cursor = ed.textCursor()
        # QTextCursor.selectedText() encodes line breaks as U+2029.
        selection = cursor.selectedText().replace(" ", "\n")
        dlg = ExplainCodeDialog(
            backend, code, selection, self._board_name(), self,
        )
        dlg.exec()

    def _open_lint_dialog(self):
        s = lang_manager.current
        backend = get_backend_instance(ai_config.backend_id)
        if backend is None or not backend.is_available():
            QMessageBox.warning(
                self, s.studio_ai_tools_title, s.studio_explain_no_backend,
            )
            return
        from .lint_code_dialog import LintCodeDialog
        dlg = LintCodeDialog(
            backend, self._editor.toPlainText(), self._board_name(), self,
        )
        dlg.exec()

    # ── Checkbox "Afficher les commentaires" ─────────────────

    # (tool_id, i18n key of the label) — the order = the menu display order.
    # Each tool_id is resolved by _on_ai_tool_requested (existing dispatch).
    # The wiring schema is NOT a tool -> it has its own entry point
    # (« Voir le schéma »), absent from this list.
    _AI_TOOLS_MENU = (
        ("explain_lines",  "studio_tool_explain_lines"),
        ("add_comments",   "studio_tool_add_comments"),
        # « Analyser / Réparer »: merge of the old lint (antipattern audit)
        # and the repair -> analyzes + proposes a fix + applies.
        ("repair_code",    "studio_tool_repair"),
        # « Formater le code »: deterministic re-indentation (no AI). If a
        # closing brace is missing AND we can locate it via the indentation,
        # we add it too.
        ("format_code",    "studio_tool_format"),
    )

    def _open_ai_tools_menu(self, target: str = "ia"):
        """« Outils » pill of the code header: opens the AI tools
        dropdown menu (themed via context_menu_qss), wired to the
        _on_ai_tool_requested dispatch. The menu anchors below the button.
        `target` = fenêtre visée (« ia » / « stable ») ; posée comme cible
        courante pour toute la durée du menu."""
        self._code_target = target
        btn = self._btn_ai_tools_st if target == "stable" else self._btn_ai_tools
        s = lang_manager.current
        c = theme_manager.current
        menu = QMenu(self)
        # Common themed base + override specific to THIS menu: on hover, we keep
        # the background unchanged and only turn the TEXT green (user request, vs
        # the default background highlight of context menus). The last
        # QMenu::item:selected rule wins (same selector).
        menu.setStyleSheet(
            context_menu_qss(c)
            + f"QMenu::item:selected {{ background-color: transparent;"
            f" color: {c.signal_ok}; }}"
        )
        for tool_id, label_key in self._AI_TOOLS_MENU:
            act = menu.addAction(getattr(s, label_key))
            act.triggered.connect(
                lambda _checked=False, tid=tool_id: self._on_ai_tool_requested(tid)
            )
        # Anchoring below the button (bottom-left corner) of the target window.
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _update_code_meta(self):
        """Line counter of the code header: « N lignes » (without the
        filename — removed at the user's request). Updated on every change of
        code / language."""
        if not hasattr(self, "_editor") or not hasattr(self, "_lbl_code_meta"):
            return   # called early (project bar init) before the code area
        word = lang_manager.current.studio_lines_word
        self._lbl_code_meta.setText(f"{self._editor.blockCount()} {word}")
        if hasattr(self, "_lbl_code_meta_st"):
            self._lbl_code_meta_st.setText(
                f"{self._stable_panel.editor.blockCount()} {word}")

    # ── Cible des outils / commentaires (fenêtre IA vs stable) ──────────
    def _tools_editor(self, target: str | None = None):
        t = target or self._code_target
        return self._stable_panel.editor if t == "stable" else self._editor

    def _tools_panel(self, target: str | None = None):
        t = target or self._code_target
        return self._stable_panel if t == "stable" else self._code_panel

    def _tools_chk(self, target: str | None = None):
        t = target or self._code_target
        return (self._chk_show_comments_st if t == "stable"
                else self._chk_show_comments)

    def _tools_apply(self, code: str, *, attributed: bool = True):
        """Applique un code transformé par un outil à l'éditeur CIBLE. IA =
        remplacement moteur avec attribution des lignes (`attributed`) ou
        set_code simple (commentaires, où le nombre de lignes change).
        Stable : depuis la refonte 2 fenêtres, le stable A des
        fonctionnalités -> on repose la carte lignes->fonctionnalité après
        setPlainText (qui recrée tous les blocs SANS userData), même recette
        que le chemin IA (transfert positionnel depuis l'ancienne carte +
        matching des contributions). Sans ça, le surlignage stable mourait
        après une réparation Outils et ne revenait qu'au rechargement du
        projet (bug 2026-07-06 n°3). Marque le projet dirty."""
        if self._code_target == "stable":
            ed = self._stable_panel.editor
            old_lines = ed.toPlainText().split("\n")
            old_map = ed.line_owners()
            ed.setPlainText(code)
            new_lines = code.split("\n")
            base = transfer_map(old_lines, old_map, new_lines)
            ed.set_line_owners(
                match_contributions(new_lines, self._stable_features, base))
            self._stable_panel.refresh_highlights(self._stable_features)
        elif attributed:
            self._set_code_with_attribution(code, self._features)
        else:
            self.set_code(code)
        self._mark_dirty()

    def _on_show_comments_toggled(self, checked: bool, target: str = "ia"):
        """Toggles between full code (checked) and stripped code (unchecked)
        pour la fenêtre `target` (« ia » / « stable »)."""
        if self._loading:
            return
        ed = self._tools_editor(target)
        if not checked:
            self._code_with_comments[target] = ed.toPlainText()
            self._stripped_at_decoche[target] = _strip_comments(
                self._code_with_comments[target])
            self._loading = True
            try:
                ed.setPlainText(self._stripped_at_decoche[target])
            finally:
                self._loading = False
        else:
            if self._code_with_comments[target] is None:
                return
            new_full = _restore_comments_after_edits(
                self._code_with_comments[target],
                self._stripped_at_decoche[target] or "",
                ed.toPlainText(),
            )
            self._loading = True
            try:
                ed.setPlainText(new_full)
            finally:
                self._loading = False
            self._code_with_comments[target] = None
            self._stripped_at_decoche[target] = None

    def _reset_comments_state(self, target: str) -> None:
        """After a STRUCTURAL code replacement (delete / transfer) that writes
        the full assembled code (comments included), re-check the « Comments »
        box of `target` and DROP the stale stripped/full snapshot. Otherwise the
        box stays unticked over commented code, and re-ticking would re-inject
        the OLD code's comments into the new one (bug review 2026-07-06 #3)."""
        chk = self._tools_chk(target)
        if not chk.isChecked():
            self._loading = True
            try:
                chk.setChecked(True)
            finally:
                self._loading = False
        self._code_with_comments[target] = None
        self._stripped_at_decoche[target] = None

    def _run_format_code(self):
        """« Formater le code » tool: DETERMINISTIC re-indentation (no AI).
        - balanced code → we reformat;
        - a closing brace is missing AND locatable via the indentation → we
          add it then reformat;
        - non-locatable imbalance → message (the compilation will run
          the full AI analysis)."""
        from .code_format import reindent_code, insert_missing_brace, is_balanced
        s = lang_manager.current
        code = self._tools_editor().toPlainText()
        if is_balanced(code):
            formatted = reindent_code(code)
            if formatted != code:
                # Diff whitespace-only -> transfer_map (normalisé) récupère
                # la carte lignes->fonctionnalité à 100 % (#29).
                self._tools_apply(formatted)
            return
        # Imbalanced: try to locate a missing closing brace.
        fixed = insert_missing_brace(code)
        if fixed is not None:
            self._tools_apply(reindent_code(fixed))
            QMessageBox.information(
                self, s.studio_ai_tools_title, s.studio_format_brace_added,
            )
            return
        QMessageBox.warning(
            self, s.studio_ai_tools_title, s.studio_format_unbalanced,
        )

    def _on_service_code_updated(self, code: str):
        """CompileService repaired-code sink. Routed to the ACTIVE repair
        target editor (chantier 1) — EXCEPT during a MANUAL repair, which is a
        PREVIEW: the cascade result is only BUFFERED, the editor stays
        untouched until the user clicks « Appliquer » (so « Annuler » changes
        nothing — bug 2026-07-06 where the compile fix was applied silently)."""
        if self._manual_repair_running and self._manual_repair is not None:
            self._manual_repair["repaired_code"] = code
            return
        if self._active_repair_target == "stable":
            self._write_repaired_to_target(code, "stable")
        else:
            self._set_code_with_attribution(code, self._features)

    def _write_repaired_to_target(self, code: str, target: str):
        """Write repaired `code` to the target editor WITH line attribution
        (same recipe as the IA path / _tools_apply stable branch)."""
        if target == "stable":
            ed = self._stable_panel.editor
            old_lines = ed.toPlainText().split("\n")
            old_map = ed.line_owners()
            ed.blockSignals(True); ed.setPlainText(code); ed.blockSignals(False)
            new_lines = code.split("\n")
            base = transfer_map(old_lines, old_map, new_lines)
            ed.set_line_owners(
                match_contributions(new_lines, self._stable_features, base))
            self._stable_panel.refresh_highlights(self._stable_features)
            self._update_code_meta()
        else:
            self._set_code_with_attribution(code, self._features)

    def _run_repair_code(self):
        """« Analyser / Réparer » (chantier 1) : COMPILE D'ABORD, puis route.
        - compile impossible (pas d'arduino-cli / carte) → mode AUDIT direct
          (comportement historique : la dialog cherche les antipatterns).
        - compile KO → cascade de réparation (identique à l'auto, via
          verify_only) IN-PLACE au journal, ✓/✗ réel ; modèle resynchronisé
          au succès ; revert au code d'origine + diagnostic à l'échec.
        - compile OK direct → mode AUDIT (le code compile, on chasse les
          antipatterns)."""
        s = lang_manager.current
        backend = get_backend_instance(ai_config.backend_id)
        if backend is None or not backend.is_available():
            QMessageBox.warning(
                self, s.studio_ai_tools_title, s.studio_explain_no_backend,
            )
            return
        t = self._code_target
        if self._tools_chk().isChecked():
            source_code = self._tools_editor().toPlainText()
        else:
            source_code = self._code_with_comments[t] or self._tools_editor().toPlainText()
        # Compile-first requires arduino-cli + a selected board. Otherwise we
        # cannot detect compile errors -> fall back to AUDIT only.
        env, model = board_manager.env, board_manager.model
        fqbn = get_fqbn(env, model) if (env and model) else None
        if (not fqbn or not arduino_cli.is_available()
                or self._cu_running or self._gen_busy is not None
                or self._beginner_running or self._manual_repair_running):
            self._open_audit_dialog(backend, source_code, t)
            return
        self._manual_repair = {"target": t, "original": source_code,
                               "backend": backend}
        self._active_repair_target = t
        self._manual_repair_running = True
        self._last_repair_steps = []
        self._active_output_area().begin_phase(s.studio_compiling, "#3b82f6")
        self._verify_worker = self._compile_service.run(
            code=source_code, fqbn=fqbn,
            backend=backend, board_name=self._board_name(),
            console=self._active_console(), verify_only=True,
            on_repair_steps=self._on_cu_repair_steps,
            on_done=self._on_manual_repair_done,
            on_finished=self._on_manual_repair_finished,
        )
        # Open the modal RIGHT AWAY (spinner) — the compile+cascade+review runs
        # behind it and _on_manual_repair_done drives it. exec() blocks while
        # the worker (queued to this thread) fires the done callback.
        from .repair_code_dialog import RepairCodeDialog
        dlg = RepairCodeDialog(backend, source_code, self._board_name(), self,
                               deferred=True)
        dlg.apply_requested.connect(
            lambda code, tt=t: self._apply_repair_result(code, tt))
        dlg.summary_ready.connect(self._log_repair_summary)
        self._manual_repair_dialog = dlg
        dlg.exec()
        self._manual_repair_dialog = None

    def _log_behavior_findings(self, findings) -> None:
        """Layer B: log the deterministic behavioral lint to the journal (a
        report — the code is not modified). Findings are French-only in V1
        (see behavior_lint docstring)."""
        s = lang_manager.current
        out = self._active_output_area()
        out.begin_phase(s.studio_behavior_lint_title, "#f59e0b")
        if not findings:
            out.append_explanation(s.studio_behavior_lint_none)
            return
        for f in findings:
            mark = "⛔" if f.severity == "error" else "⚠"
            out.append_explanation(f"{mark} L{f.line} · {f.message}  → {f.fix_hint}")

    def _build_review_call(self, backend, source_code: str, target: str):
        """Log layer B (deterministic lint) and build the layer C review call
        (None if no intent / ineligible backend -> the dialog falls back to the
        antipattern audit). Shared by the immediate and the deferred paths."""
        from .generation.behavior_lint import lint_behavior
        from .generation.behavior_review import conformance_available, build_intent
        self._log_behavior_findings(lint_behavior(source_code, self._board_name()))
        intent = build_intent(self._features_for(target))
        if not (intent and conformance_available(backend)):
            return None
        evidence = self._active_console().serial.recent_output()
        if evidence:
            self._active_output_area().append_explanation(
                lang_manager.current.studio_behavior_evidence_joined)
        return (lambda: backend.review_conformance(
            source_code, intent, self._board_name(), evidence=evidence,
            language=lang_manager.ai_lang_name()))

    def _open_audit_dialog(self, backend, source_code: str, target: str):
        """Immediate behavioral review (spec 2026-07-06) — used when compiling
        is impossible (no arduino-cli / board): B lint logged + C review in the
        3-column dialog if eligible, else the antipattern audit."""
        from .repair_code_dialog import RepairCodeDialog
        review_call = self._build_review_call(backend, source_code, target)
        dlg = RepairCodeDialog(backend, source_code, self._board_name(), self,
                               review_call=review_call)
        dlg.apply_requested.connect(
            lambda code, tt=target: self._apply_repair_result(code, tt))
        dlg.summary_ready.connect(self._log_repair_summary)
        dlg.exec()

    def _on_manual_repair_done(self, ok: bool, errors: str):
        """Done of the compile-first manual repair (verify_only cascade). Drives
        the ALREADY-OPEN modal. PREVIEW: nothing has been applied to the editor
        (the cascade result was buffered) — the review runs on the buffered
        code, and applying happens ONLY on the modal's « Appliquer »."""
        info = self._manual_repair or {}
        t = info.get("target", "ia")
        backend = info.get("backend")
        s = lang_manager.current
        out = self._active_output_area()
        dlg = self._manual_repair_dialog
        if ok:
            if self._last_repair_steps:
                out.begin_phase(s.studio_verify_repaired_ok,
                                theme_manager.current.signal_ok)
            else:
                out.begin_phase(s.studio_verify_ok, theme_manager.current.signal_ok)
            # The code now compiles (directly OR after the buffered repair) ->
            # review the REPAIRED code (buffer), or the original if no fix. The
            # modal diff baseline stays the TRUE original so it shows BOTH the
            # cascade fixes AND the review fix. Nothing is applied yet.
            current = info.get("repaired_code") or info.get("original", "")
            review_call = self._build_review_call(backend, current, t)
            if dlg is not None:
                dlg.set_pre_summary(self._cascade_summary_text())
                dlg.start_deferred(review_call)
            else:
                self._open_audit_dialog(backend, current, t)
        else:
            # Buffered preview -> the editor was never touched, nothing to
            # revert; just surface the diagnostic.
            out.set_failed(s.studio_verify_failed)
            if errors:
                out.set_done(False, errors)      # exposes « demander de l'aide »
            if dlg is not None:
                dlg.show_compile_failure(errors or s.studio_verify_failed)

    @staticmethod
    def _repair_step_line_bullets(before: str, after: str) -> list[str]:
        """Per-changed-line markdown bullets for ONE cascade step, derived from
        its before/after code — used when the step has no model summary (a
        deterministic / line-anchored fix). Gives the CONCRETE line(s) instead
        of a vague « N corrections »."""
        import difflib
        s = lang_manager.current
        a, b = before.split("\n"), after.split("\n")
        out: list[str] = []
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
                None, a, b, autojunk=False).get_opcodes():
            if tag == "equal":
                continue
            if tag == "replace":
                for k in range(max(i2 - i1, j2 - j1)):
                    old = a[i1 + k].strip() if i1 + k < i2 else ""
                    new = b[j1 + k].strip() if j1 + k < j2 else ""
                    if old and new:
                        out.append(s.studio_cascade_line_changed.format(
                            n=j1 + k + 1, old=old, new=new))
                    elif new:
                        out.append(s.studio_cascade_line_added.format(
                            n=j1 + k + 1, code=new))
                    elif old:
                        out.append(s.studio_cascade_line_removed.format(
                            n=i1 + k + 1, code=old))
            elif tag == "delete":
                for k in range(i1, i2):
                    if a[k].strip():
                        out.append(s.studio_cascade_line_removed.format(
                            n=k + 1, code=a[k].strip()))
            elif tag == "insert":
                for k in range(j1, j2):
                    if b[k].strip():
                        out.append(s.studio_cascade_line_added.format(
                            n=k + 1, code=b[k].strip()))
        return out

    def _cascade_summary_text(self) -> str:
        """Markdown recap of the compile-cascade fixes (double declaration,
        etc.) applied BEFORE the review — for the modal's summary column, so
        the modal lists BOTH the cascade AND the review fixes. Each step uses
        its model summary if any, else the concrete changed LINES (from its
        before/after). Empty if no cascade fix. Full before/after stays in the
        journal's « voir les corrections » button."""
        steps = self._last_repair_steps or []
        if not steps:
            return ""
        s = lang_manager.current
        lines: list[str] = []
        for st in steps:
            summ = (st.get("summary") or "").strip()
            if summ:
                lines.append(summ)
                continue
            bullets = self._repair_step_line_bullets(
                st.get("code_before", ""), st.get("code_after", ""))
            lines.extend(bullets[:8])       # cap: avoid a giant list
        body = "\n".join(lines) if lines else s.studio_cascade_fixes_generic.format(
            n=len(steps))
        return f"{s.studio_cascade_fixes_header}\n{body}"

    def _on_manual_repair_finished(self):
        """QThread.finished of the manual repair: reset the routing/flags."""
        self._manual_repair_running = False
        self._active_repair_target = "ia"
        self._manual_repair = None

    def _apply_repair_result(self, new_code: str, target: str = "ia"):
        """Replaces the editor code with the repaired version, then
        resynchronises the feature model from it (canonical — chantier 2)."""
        self._code_target = target
        self._tools_apply(new_code)
        self._resync_features_after_repair(target)

    def _log_repair_summary(self, summary: str):
        """Logs the summary in the journal — same color as the automatic
        'repair' phase for visual consistency."""
        if not summary:
            return
        s = lang_manager.current
        self._output_area.begin_phase(
            s.studio_repair_summary, PHASE_COLORS["repair"],
        )
        self._output_area.append_raw(summary)

    def _on_cu_repair_steps(self, steps: list):
        """Automatic compilation repairs: we record them and
        show the « voir les corrections » button. The code has already been applied
        by the worker — here we just make the history viewable (even after
        the upload), on demand. Shown on BOTH journals (beginner +
        advanced): only the one of the current mode is visible, and the auto
        repair runs in all modes.

        EXCEPT during a MANUAL repair (Tools): the 3-column modal already shows
        every correction (cascade in its summary + review in the diff). The
        journal button would DUPLICATE it and mislead — it points at a PREVIEW
        that isn't applied if the user cancels (TODO #32). We still RECORD the
        steps (the modal's pre-summary reads them), we just don't surface the
        button. Only the automatic paths (verify v2 / upload) show it."""
        self._last_repair_steps = steps or []
        if self._last_repair_steps and not self._manual_repair_running:
            s = lang_manager.current
            self._output_area.show_repairs_action(
                s.studio_repairs_link.format(n=len(self._last_repair_steps)),
            )

    def _on_output_action(self, href: str):
        """Click on a journal action link."""
        if href == "repairs" and self._last_repair_steps:
            self._open_applied_repairs_dialog()

    def _open_applied_repairs_dialog(self):
        """Read-only 3-column view of the repairs applied automatically during a
        compile/upload — the SAME modal as the manual repair (TODO #32), in a
        display-only mode, replacing the old stepper RepairHistoryDialog:
        consolidated original -> final diff + the cascade explanation (the
        concrete changed lines)."""
        from .repair_code_dialog import RepairCodeDialog
        steps = self._last_repair_steps
        original = steps[0].get("code_before", "") or ""
        final = steps[-1].get("code_after", "") or ""
        RepairCodeDialog(None, original, self._board_name(), self,
                         applied=(final, self._cascade_summary_text())).exec()

    def _run_add_comments(self):
        """Launches the comment generation directly in the background
        and applies the result to the editor as soon as it arrives — no
        intermediate dialog, no validation."""
        s = lang_manager.current
        backend = get_backend_instance(ai_config.backend_id)
        if backend is None or not backend.is_available():
            QMessageBox.warning(
                self, s.studio_ai_tools_title, s.studio_explain_no_backend,
            )
            return
        # If the checkbox is unchecked, the editor shows the stripped version.
        # Source of truth = _code_with_comments (captured when unchecking).
        # We send the most complete version we know.
        t = self._code_target
        self._addcmt_target = t          # figé pour le callback async
        if self._tools_chk().isChecked():
            source_code = self._tools_editor().toPlainText()
        else:
            source_code = self._code_with_comments[t] or self._tools_editor().toPlainText()
        from .add_comments_dialog import _AddCommentsWorker
        # Overlay loader (top-right of the editor) rather than the
        # global hourglass cursor.
        self._tools_panel().show_comment_loader(True)
        self._addcmt_worker = _AddCommentsWorker(
            backend, source_code,
            lang_manager.ai_lang_name(), self._board_name(),
        )
        self._addcmt_worker.finished.connect(self._on_add_comments_done)
        self._addcmt_worker.error.connect(self._on_add_comments_error)
        self._addcmt_worker.start()

    def _on_add_comments_done(self, new_code: str):
        t = getattr(self, "_addcmt_target", "ia")
        self._code_target = t
        self._tools_panel(t).show_comment_loader(False)
        new_code = new_code.rstrip() + "\n"
        # Auto-checks the checkbox so the user sees the comments
        # that were just generated. If it was already checked, the set
        # does not emit a signal.
        chk = self._tools_chk(t)
        if not chk.isChecked():
            self._loading = True
            try:
                chk.setChecked(True)
            finally:
                self._loading = False
            self._code_with_comments[t] = None
        self._apply_add_comments_result(new_code)

    def _on_add_comments_error(self, msg: str):
        self._tools_panel(getattr(self, "_addcmt_target", "ia")).show_comment_loader(False)
        s = lang_manager.current
        QMessageBox.warning(
            self, s.studio_ai_tools_title,
            s.studio_addcmt_error.format(msg=msg),
        )

    def _apply_add_comments_result(self, new_code: str):
        """Replaces the editor code with the commented version."""
        self._tools_apply(new_code, attributed=False)

    def _refresh_feature_chips(self):
        """Sélecteur des fonctionnalités (dropdown, dans la ligne d'outils) :
        peuplé en Int/Avancé. Pendant une opération (génération/vérif, voile)
        le dropdown est grisé et l'overlay ↻/🗑 masqué (pas de saut de layout).
        En débutant, la ligne d'outils entière est masquée (_code_compile_w) :
        rien à faire."""
        if not hasattr(self, "_code_panel"):
            return
        # En débutant, le dropdown est enfant de la ligne d'outils, elle-même
        # masquée avec _code_compile_w -> pas de branchement spécial ; on peuple
        # quand même (état cohérent au retour en Int/Avancé).
        busy = (self._gen_busy is not None or self._cu_running
                or self._code_panel.is_busy())
        self._code_panel.set_features(self._features, busy)

    def _set_generating(self, active: bool):
        # #7/#12: int/advanced generation feeds the unified _gen_busy state; the
        # rendering (« ◐ Annuler » loader in the current mode's button) is delegated
        # to _sync_generation_buttons to stay consistent across modes.
        self._gen_busy = "advanced" if active else None
        self._sync_generation_buttons()
        self._refresh_feature_chips()
        self._refresh_stable_features()   # gris le dropdown stable aussi (#busy)

    def _sync_generation_buttons(self):
        """#12 + loader/Cancel: reflects the UNIFIED generation state (_gen_busy)
        on the « Générer » button of the currently displayed mode.

        In progress → loader BEFORE « Annuler » + red style + clickable button
        (click = cancel, regardless of the mode in which the generation started).
        Stopped → we restore the normal text/style. The other mode's button
        (hidden) must never keep an orphan spinner."""
        s = lang_manager.current
        busy = self._gen_busy is not None
        if self._current_mode == "beginner":
            active_btn, idle_btn = self._btn_generate_send, self._btn_generate
        else:
            active_btn, idle_btn = self._btn_generate, self._btn_generate_send
        self._stop_btn_spinner(idle_btn)
        if busy:
            active_btn.setEnabled(True)                       # clickable -> cancels
            active_btn.setStyleSheet(self._cancel_btn_style())
            self._start_btn_spinner(active_btn, label=s.studio_cancel)
        else:
            self._stop_btn_spinner(active_btn)
            self._refresh_action_button_styles()             # restores the style
            if self._current_mode == "beginner":
                # « Générer et uploader » stays disabled as long as a beginner
                # operation is still running (e.g. upload-only without generation).
                self._btn_generate_send.setEnabled(not self._beginner_running)
            else:
                self._btn_generate.setEnabled(True)

    def _cancel_generation(self):
        """Cancels the generation actually in progress, regardless of the
        displayed mode (#12: we can cancel from any mode)."""
        if self._gen_busy == "beginner" or self._beginner_running:
            self._cancel_beginner()        # handles gen+upload AND upload-only
        else:
            self._cancel_gen_worker()

    def _cancel_gen_worker(self):
        """Interrupts the int/advanced generation OR the v2 compile verification
        and restores the Generate button. Cancelling DURING the verification
        keeps the provisional code as-is (the user chooses not to wait).

        ⛔ NE PLUS JAMAIS APPELER `QThread.terminate()` ICI (TODO #24). C'est
        ce que faisait cette methode, sur un thread bloque dans
        `subprocess.communicate()` ou `urlopen()` — soit exactement le crash
        natif 0xC0000409 que ce depot a deja paye. Le contraste etait visible
        a trois lignes d'ecart : le worker de verification, juste en dessous,
        etait deja decrit comme « annulable proprement (cancel() tue le
        sous-process — pas terminate()) ».

        Le remede est celui du chat (`chat_view._on_stop_clicked`) : demander au
        BACKEND de couper son E/S, puis attendre brievement, puis DETACHER si
        le thread s'attarde. Un thread orphelin coute un objet ; `terminate()`
        coute le processus.

        ⚠️ Cette methode est devenue le SEUL moyen de sortir d'une generation
        qui n'avance pas : #24 a retire le delai dur des trois backends. Elle
        n'a plus le droit d'echouer en silence.
        """
        self._stop_gen_worker_safely()
        # v2 : la vérif (compile + réparation) tourne dans un worker dédié,
        # annulable proprement (cancel() tue le sous-process — pas terminate()).
        if self._verify_worker and self._verify_worker.isRunning():
            self._verify_worker.cancel()
            self._verify_worker.wait(3000)
        s = lang_manager.current
        self._reset_generation_ui(s.studio_cancel + ".")

    def _stop_gen_worker_safely(self):
        """Arrete le worker de generation SANS `QThread.terminate()`.

        ⚠️ EXTRAIT EN COMMUN LE 2026-08-26, et pas par gout du facteur commun :
        le correctif initial de #24 n'avait desinfecte que le chemin
        int/avance. `_cancel_beginner` gardait son `terminate()` — donc annuler
        en mode **Debutant** plantait encore, alors que << le mode n'est qu'un
        affichage >>. Deux copies d'un arret dangereux, une seule corrigee :
        c'est exactement ce qu'un point de passage unique empeche.
        """
        if not (self._gen_worker and self._gen_worker.isRunning()):
            return
        try:
            self._gen_worker.backend.cancel()
        except Exception:
            pass              # un backend sans override, ou deja fini
        self._gen_worker.wait(2000)
        if self._gen_worker.isRunning():
            self._detach_gen_worker()

    def _detach_gen_worker(self):
        """Coupe les callbacks UI du worker de generation et le laisse mourir
        en arriere-plan (`cancel()` a deja ete demande).

        POURQUOI GARDER UNE REFERENCE : detruire un `QThread` qui tourne encore
        plante. On le gare donc dans une liste, et on ne le recolte pas — le
        chat, lui, recolte sur `QThread.finished`, ce qui est IMPOSSIBLE ici :
        `GenerateWorker.finished` est un `pyqtSignal(str)` MAISON qui MASQUE
        celui de QThread (verifie : `GenerateWorker.finished is
        QThread.finished` est faux). Se connecter au signal maison
        reveillerait precisement les callbacks qu'on vient de couper.

        Le cout assume est donc un objet QThread par annulation qui s'attarde
        — rare, borne par les annulations de l'utilisateur, et sans commune
        mesure avec un `terminate()`.
        """
        w = self._gen_worker
        self._gen_worker = None
        if w is None:
            return
        for sig in (w.finished, w.error):
            try:
                sig.disconnect()
            except TypeError:
                pass          # aucune connexion -> rien a couper
        self._detached_gen_workers.append(w)

    def undo(self):
        """Text undo of the focused widget (falls back to the code editor).
        Reached via Ctrl+Z, the topbar arrow and the Édition menu."""
        fw = self.focusWidget()
        if isinstance(fw, QPlainTextEdit):
            fw.undo()
        else:
            self._editor.undo()

    def redo(self):
        """Text redo on the focused widget (falls back to the code editor).
        Reached via Ctrl+Y / Ctrl+Shift+Z, the topbar arrow and the Édition menu."""
        fw = self.focusWidget()
        if isinstance(fw, QPlainTextEdit):
            fw.redo()
        else:
            self._editor.redo()

    # ── Beginner Mode: Generate and send ────────────────────

    def _on_generate_and_send(self):
        # #12: during a generation, the button shows « ◐ Annuler » -> cancels.
        if self._gen_busy is not None or self._beginner_running:
            self._cancel_generation()
            return
        s = lang_manager.current
        prompt = self.get_prompt()
        if not prompt:
            self._show_beginner_status(s.studio_err_no_prompt, error=True)
            return
        backend = get_backend_instance(ai_config.backend_id)
        if backend is None or not backend.is_available():
            self._show_beginner_status(s.studio_err_no_backend, error=True)
            return
        if not arduino_cli.is_available():
            self._show_beginner_status(s.studio_err_no_cli, error=True)
            return
        env, model = board_manager.env, board_manager.model
        if not env or not model:
            self._show_beginner_status(s.studio_err_no_board, error=True)
            return
        fqbn = get_fqbn(env, model)
        if not fqbn:
            self._show_beginner_status(s.studio_err_no_fqbn, error=True)
            return
        port = board_manager.port or arduino_cli._find_port_auto()
        if not port:
            self._show_beginner_status(s.studio_err_no_port, error=True)
            return

        # Overwrite confirmation if code has already been generated.
        if self._has_generated:
            choice = self._show_overwrite_confirm(
                s.studio_beginner_overwrite_msg, show_switch=True
            )
            if choice == "cancel":
                return
            if choice == "switch":
                self._mode_selector._select("intermediate")
                return
            # Overwrite accepted, but we do NOT clear the code now: if
            # the user cancels the generation, the old code must remain. The
            # replacement happens at the very last moment in _on_beg_gen_done
            # (_set_code_silent), just before pasting the new sketch — which
            # recreates a fresh f1 with up-to-date lines anyway.
            # (Beginner generation does not read the editor: passing a template
            # here changed nothing in the output, only the display.)

        # bare_prompt = raw USER prompt (get_prompt()), not the assembled instruction.
        bare_prompt = prompt
        forced = self._resolve_lib_ambiguity(bare_prompt)

        # Materializes the Untitled project at the start of the generation.
        if not self._auto_create_untitled():
            self._show_beginner_status(s.studio_err_no_backend, error=True)
            return

        # Composant hors-corpus : MÊME pipeline qu'en Intermédiaire/Avancé.
        # Il manquait ici (QA G6) — un débutant nommant une puce inconnue
        # recevait du code écrit contre un `#include` inventé, sans bannière
        # ni avertissement. C'est le mode où ça compte le plus : c'est celui
        # de ceux qui nomment un capteur au hasard.
        unknown, preferred, declared_forced = self._registry_request(bare_prompt)
        if unknown:
            # Verrou posé AVANT le worker (comme en int/avancé) : sans lui, un
            # second clic pendant la recherche relancerait une génération.
            self._beginner_running = True
            self._gen_busy = "beginner"
            self._sync_generation_buttons()
            self._show_beginner_status(s.studio_generating)
            self._start_gen_loader()
            from .registry_lookup import RegistryLookupWorker
            self._registry_worker = RegistryLookupWorker(
                unknown, self._registry_config_file(),
                preferred_libs=preferred,
                search_queries=self._registry_search_queries)
            self._registry_worker.done.connect(
                lambda results: self._continue_beginner_generation(
                    backend, fqbn, port, bare_prompt, forced,
                    registry_results=results,
                    declared_component_forced=declared_forced))
            self._registry_worker.start()
            return
        self._continue_beginner_generation(backend, fqbn, port, bare_prompt,
                                           forced)

    def _continue_beginner_generation(self, backend, fqbn, port,
                                      bare_prompt: str, forced,
                                      registry_results=None,
                                      declared_component_forced: bool = False):
        """Suite de `_on_generate_and_send`, après la recherche au registre.

        Découpé pour la même raison qu'en int/avancé : l'installation d'une
        lib est réseau, donc elle vit dans un worker et la génération reprend
        ici."""
        s = lang_manager.current
        # Bannière registre/ressemblance d'une génération précédente :
        # obsolète (miroir de `_start_generation`, ligne ~3378 — seul chemin
        # débutant à masquer avant tout). AVANT `_apply_registry_results`,
        # sinon on effacerait la bannière du registre que celui-ci vient
        # d'afficher.
        self._registry_banner.setVisible(False)
        orphan_directive = ""
        if registry_results is not None:
            forced, orphan_directive = self._apply_registry_results(
                forced, registry_results, bare_prompt)
            # Installation impossible : on ABANDONNE, comme en int/avancé.
            # Sans la lib téléchargée il n'y a ni en-têtes réels ni exemple à
            # injecter — livrer quand même ferait perdre du temps, et le
            # débutant se heurterait au mur à la compilation sans savoir
            # pourquoi.
            blocked = [r for r in registry_results
                       if r.status == "install_failed"]
            if blocked:
                self._restore_beginner_btn()
                self._stop_gen_loader()
                r = blocked[0]
                self._show_beginner_status(
                    s.registry_install_failed.format(
                        part=r.token.upper(), lib=r.lib_name), error=True)
                return

        # Remember the parameters for the compile phase
        self._beg_fqbn       = fqbn
        self._beg_port       = port
        self._beg_backend    = backend
        self._beg_board_name = self._board_name()

        self._beginner_running = True
        self._gen_busy = "beginner"                        # #12: unified state
        self._btn_upload_only.setEnabled(False)
        # #7/#12: « ◐ Annuler » loader (red, clickable) on « Générer et
        # uploader » via the unified indicator — it stays visible if we change
        # mode during the generation.
        self._sync_generation_buttons()
        self._show_beginner_status(s.studio_generating)

        # Prompt assembled by the shared helper: the beginner sends
        # exactly the same prompt as the other modes. We keep the RAW
        # prompt (before RAG augmentation) for the motor gating.
        # Remis à zéro AVANT l'assemblage (cf. `_continue_generation`).
        self._last_resemblance = False
        prompt = self._assemble_generation_prompt(
            bare_prompt, forced_libs=forced,
            extra_directive=orphan_directive,
            declared_component_forced=declared_component_forced)
        # « Coulisses du prompt » (#42) : même étape qu'en int/avancé. Le mode
        # n'est qu'un affichage — la modale doit se comporter pareil des deux
        # côtés, sinon le prompt divergerait selon le mode.
        validated = self._prompt_backstage(
            backend, prompt, self._beg_board_name, rules_prompt=bare_prompt)
        if validated is _BACKSTAGE_CANCELLED:
            self._restore_beginner_btn()
            self._lbl_beginner_status.setVisible(False)
            return
        # Affichée APRÈS le contrôle d'annulation (même raison qu'en
        # int/avancé). Le débutant régénère TOUT depuis le prompt (son
        # 2ᵉ prompt écrase, avec confirmation) : c'est l'action qui parle,
        # pas le mode.
        self._maybe_resemblance_banner(
            action=REGENERATE, from_scratch=False, has_targets=False)
        self._warn_if_prompt_overflows(backend, prompt, self._beg_board_name,
                                       rules_prompt=bare_prompt)
        self._gen_worker = _GenerateWorker(
            backend, prompt, self._beg_board_name, self._current_mode,
            comment_verbosity=self._comments_verbosity(),
            rules_prompt=bare_prompt, user_message=validated,
        )
        self._gen_worker.finished.connect(self._on_beg_gen_done)
        self._gen_worker.error.connect(self._on_beg_gen_error)
        # Generation loader DIRECTLY in the journal (animated line).
        # PAS deux fois : `_start_gen_loader` EFFACE le journal, et la
        # recherche registre vient d'y écrire ses lignes `[REGISTRY] …`. Les
        # relancer ici les emporterait — le diagnostic disparaîtrait juste
        # avant d'être lu.
        if self._gen_loader_journal is None:
            self._start_gen_loader()
        self._gen_worker.start()

    def _on_beg_gen_done(self, code: str):
        # The beginner always regenerates: we (re)place a single f1 feature
        # (parsed if possible) to keep a consistent model if the user
        # then switches to int/advanced, and we persist the baseline + the project.
        summary = extract_feature_summary(code)
        try:
            p = parse_sketch(code)
        except SketchParseError:
            p = None
        f1 = self._feature_from_parsed(p, "f1", self.get_prompt(), summary,
                                       carry_from=self._features_with_id("f1"))
        self._index_features(self.get_code(), self._features)   # état AVANT (undo)
        # Décision 2026-07-05 : le code généré en débutant est réindenté AUSSI
        # (le rituel s'en charge) -> état projet identique quel que soit le
        # mode qui a généré.
        self._commit_generated_code(code, [f1], own_all_lines_to="f1")
        self._last_prompt = self.get_prompt()

        # Nudge de progression (app-wide) : 5 générations débutant → Intermédiaire.
        session.bump_progress_count(PN.COUNTER_BEGINNER)
        self._maybe_progress_nudge(
            mode="beginner",
            counter_key=PN.COUNTER_BEGINNER,
            threshold=PN.BEGINNER_GEN_THRESHOLD,
            nudge_key=PN.NUDGE_BEGINNER,
            message=lang_manager.current.nudge_beginner_to_intermediate,
            action_label=lang_manager.current.studio_overwrite_switch,
            target_mode="intermediate",
        )

        # Generation done: the animated journal line is REPLACED by
        # « Code prêt : … ». The compile log will follow below.
        # Même honnêteté qu'en int/avancé : sans carte ni arduino-cli, rien ne
        # compilera derrière (ni ici, ni via « Générer et envoyer »), donc le
        # libellé le dit au lieu d'annoncer un vert acquis.
        self._stop_gen_loader_ready(unverified=self._verify_skip_reason())

        # « Générer ET uploader »: chain the compilation + the upload (chain
        # RESTORED — it had disappeared at commit 0733cdc during the I1 features fix,
        # leaving the button spinning indefinitely without ever uploading). The
        # « ◐ Annuler » loader stays active (_gen_busy = "beginner") until
        # _restore_beginner_btn, wired to _cu_worker.finished. We do NOT refresh
        # the styles here: it would overwrite the button's red « Annuler » style;
        # _restore_beginner_btn handles it at the very end.
        # NO clear(): we keep « Code prêt : … » and the compilation log
        # follows below (continuous narrative, no overwriting).
        self._cu_worker = self._compile_service.run(
            code=self.get_code(), fqbn=self._beg_fqbn, port=self._beg_port,
            backend=self._beg_backend if (self._beg_backend and self._beg_backend.is_available()) else None,
            board_name=self._beg_board_name,
            console=self._beg_console,
            on_error_notify=lambda m: self._show_beginner_status(
                m or "Erreur.", error=True),
            on_finished=self._restore_beginner_btn,
        )

    def _on_beg_gen_error(self, msg: str):
        self._stop_gen_loader()              # stops the animated journal line
        self._show_beginner_status(msg, error=True)
        self._restore_beginner_btn()

    def _on_upload_only(self):
        """Beginner mode: compiles and uploads the current code without
        regenerating. Reuses the CompileUploadWorker pipeline."""
        if self._beginner_running:
            self._cancel_beginner()
            return
        pf = self._preflight_compile_upload(
            lambda m: self._show_beginner_status(m, error=True))
        if pf is None:
            return
        _code, fqbn, port = pf     # le worker relit get_code() au lancement
        backend = get_backend_instance(ai_config.backend_id)
        self._beg_fqbn       = fqbn
        self._beg_port       = port
        self._beg_backend    = backend if (backend and backend.is_available()) else None
        self._beg_board_name = self._board_name()

        self._beginner_running = True
        self._btn_generate_send.setEnabled(False)
        self._btn_upload_only.setEnabled(False)
        self._start_btn_spinner(self._btn_upload_only)   # loader in the button (#7)

        self._cu_worker = self._compile_service.run(
            code=self.get_code(), fqbn=self._beg_fqbn, port=self._beg_port,
            backend=self._beg_backend,
            board_name=self._beg_board_name,
            console=self._beg_console, clear=True,
            on_error_notify=lambda m: self._show_beginner_status(
                m or "Erreur.", error=True),
            on_finished=self._restore_beginner_btn,
        )

    def _restore_beginner_btn(self):
        self._beginner_running = False
        self._gen_busy = None                              # #12: end of generation
        self._btn_upload_only.setEnabled(self._uploadable())
        self._stop_btn_spinner(self._btn_upload_only)
        # #7/#12: restores the « Générer et uploader » button (loader/Cancel
        # stop + normal style + re-enable) via the unified indicator.
        self._sync_generation_buttons()

    def _cancel_beginner(self):
        # Meme arret sain que le chemin int/avance (#24) : ce site appelait
        # encore `terminate()`, donc annuler en Debutant plantait toujours.
        self._stop_gen_worker_safely()
        if self._cu_worker and self._cu_worker.isRunning():
            # cancel() (kill the subprocess) instead of terminate() (which
            # crashes the app when the thread is mid-subprocess).
            self._cu_worker.cancel()
            self._cu_worker.wait(3000)
        s = lang_manager.current
        # Stop the animated journal line BEFORE writing « Annulé » (otherwise
        # clear_live_line, which erases from the anchor to the end, would also take
        # away the cancellation message).
        self._stop_gen_loader()
        # #12: VOLUNTARY cancellation -> neutral line in the journal (begin_phase),
        # especially NOT set_done(False) which would reveal the « Demander de l'aide
        # sur cette erreur » button (a cancellation is not an error).
        self._beg_output_area.begin_phase(s.studio_cancel + ".", "#f97316")
        self._restore_beginner_btn()
        # Annulation = pas de succès : on ne rouvre pas la console (la carte garde
        # son firmware précédent ; reconnecter ferait croire à un upload réussi).

    def _show_beginner_status(self, msg: str, *, error: bool = False, success: bool = False):
        # #7: no more « in progress / done » label. Only ERRORS (pre-flight:
        # no board/port/code…) are shown — a CLEAR message in red in the
        # beginner journal, WITHOUT the « ask for help » button (a config/wiring
        # problem, not a code error). Same as _set_cu_status (advanced).
        # set_done(False) only wrote the button, never the message -> silent journal.
        # We ADD the message below the existing one (e.g. below « Code prêt »), we
        # no longer clear the journal.
        if error and msg:
            self._beg_output_area.hide_actions()
            self._beg_output_area.begin_phase(msg, "#ef4444")   # red = error

    def _show_gen_error(self, msg: str):
        # #7/#12: generation error in the dedicated label _lbl_gen_error. We
        # reset the unified state to stopped (the button loader/Cancel is restored
        # by _sync_generation_buttons).
        self._gen_busy = None
        self._sync_generation_buttons()
        self._lbl_gen_error.setText(msg)
        self._lbl_gen_error.setVisible(True)

    def _hide_gen_error(self):
        self._lbl_gen_error.setVisible(False)

    def _beg_mark_program_ready(self):
        """Writes the program state in the journal of the CURRENT MODE: in
        beginner `_beg_output_area` (the editor is hidden there, it is the only
        visible signal), in int/advanced `_output_area`. Called after a generation, on
        opening a project and on mode switch -> « Code prêt : … » is
        visible in ALL modes.

        - If a program was actually generated (`_has_generated`): « Code prêt
          — <description> », where the description comes from the feature summaries
          (`feature_label` = AI title `// FEATURE:` otherwise falls back to the prompt,
          never empty; titles joined if several features).
        - Otherwise: « Aucun code généré » (neutral).

        Guard on `_has_generated` (and NOT `get_code()`): an empty project already
        carries the setup()/loop() skeleton of the template -> `get_code()` would be non-empty
        and would show « prêt » wrongly. `_has_generated` distinguishes real
        generated code from mere scaffolding (cf. `_is_template_or_scaffolded`)."""
        journal = (self._beg_output_area if self._current_mode == "beginner"
                   else self._output_area)
        text, color = self._program_ready_text()
        journal.begin_phase(text, color)

    def _program_ready_text(self) -> tuple[str, str]:
        """(text, color) of the beginner program state. « Code prêt : … »
        (green) if a real program was generated (`_has_generated`, not just the
        template skeleton), otherwise « Aucun code généré » (neutral). Shared between
        `_beg_mark_program_ready` (journal line) and `_stop_gen_loader_ready`
        (replaces the animated loader at the end of generation)."""
        s = lang_manager.current
        if self._has_generated:
            desc = " ; ".join(
                lbl for lbl in (feature_label(f) for f in self._features) if lbl
            )
            text = (s.studio_program_ready.format(desc) if desc
                    else s.studio_program_ready_plain)
            return text, theme_manager.current.signal_ok
        return s.studio_no_code_generated, theme_manager.current.text_secondary

    # ── Compilation + Upload ──────────────────────────────────

    def _preflight_compile_upload(self, notify, code: str | None = None) -> tuple[str, str, str] | None:
        """Vérifications pré-vol compile/upload, IDENTIQUES débutant et
        int/avancé : code présent, arduino-cli, carte, FQBN, port. Retourne
        (code, fqbn, port) ou None après avoir signalé l'erreur via
        `notify(message)` (callback d'affichage du mode appelant). `code=None`
        (défaut) = le code IA (`get_code`) ; sinon un code explicite (fenêtre
        stable)."""
        s = lang_manager.current
        code = (self.get_code() if code is None else code).strip()
        if not code:
            notify(s.studio_err_no_code)
            return None
        if not arduino_cli.is_available():
            notify(s.studio_err_no_cli)
            return None
        env, model = board_manager.env, board_manager.model
        if not env or not model:
            notify(s.studio_err_no_board)
            return None
        fqbn = get_fqbn(env, model)
        if not fqbn:
            notify(s.studio_err_no_fqbn)
            return None
        port = board_manager.port or arduino_cli._find_port_auto()
        if not port:
            notify(s.studio_err_no_port)
            return None
        return code, fqbn, port

    def _on_compile_upload(self):
        if self._cu_running:
            self._cancel_cu_worker()
            return
        s = lang_manager.current
        pf = self._preflight_compile_upload(
            lambda m: self._set_cu_status(m, error=True))
        if pf is None:
            return
        code, fqbn, port = pf

        backend = get_backend_instance(ai_config.backend_id)
        board_name = self._board_name()

        self._last_repair_steps = []   # reset: no stale corrections button
        self._cu_running = True
        self._cu_active_restore = self._restore_compile_btn
        self._btn_compile.setStyleSheet(self._cancel_btn_style())
        # Loader BEFORE « Annuler » (red clickable button -> cancel). #7
        self._start_btn_spinner(self._btn_compile, label=s.studio_cancel)

        if self._current_mode == "advanced":
            self._btn_compile_stable.setEnabled(False)
            self._adv_console.log.clear()
            self._adv_console.log.begin_phase(
                s.studio_console_src_ai, "#3b82f6")
        self._cu_worker = self._compile_service.run(
            code=code, fqbn=fqbn, port=port,
            backend=backend if (backend and backend.is_available()) else None,
            board_name=board_name,
            console=self._adv_console, clear=(self._current_mode != "advanced"),
            on_repair_steps=self._on_cu_repair_steps,
            repairs_label=lambda n: lang_manager.current
                .studio_repairs_link.format(n=n),
            on_finished=self._on_ia_upload_finished,
        )

    def _on_ia_upload_finished(self):
        """QThread.finished of the IA compile+upload. If the cascade repaired
        the code (already written to the editor by `_on_service_code_updated`),
        make the feature MODEL canonical again — the auto compile+upload path
        is the last one that applied repairs to the editor WITHOUT a resync
        (verify v2 does it in `_finalize_verify_success`, manual on Apply).
        Chantier 2 gap closed here (TODO #32). Then restore the button.
        Verified no-op when no repair happened or the model already matches."""
        if self._last_repair_steps:
            self._resync_features_after_repair("ia")
        self._restore_compile_btn()

    def _cancel_cu_worker(self):
        """Interrupts the running worker and restores the button state."""
        if self._cu_worker and self._cu_worker.isRunning():
            # cancel() (kill the subprocess) instead of terminate() (which
            # crashes the app when the thread is mid-subprocess).
            self._cu_worker.cancel()
            self._cu_worker.wait(3000)
        s = lang_manager.current
        # #12: voluntary cancellation = neutral line (begin_phase), not
        # set_done(False) which would show the « Demander de l'aide » button.
        self._output_area.begin_phase(s.studio_cancel + ".", "#f97316")
        # Restaure le BON bouton (IA ou stable) selon l'upload en cours.
        (self._cu_active_restore or self._restore_compile_btn)()
        # Annulation = pas de succès : on ne rouvre pas la console (cohérent avec
        # l'échec ; reconnecter afficherait l'ancien firmware, fausse impression
        # de réussite). L'utilisateur peut reconnecter via « Connecter ».

    def _restore_compile_btn(self):
        """Resets the Compile button to its normal state (called by done or
        QThread.finished): stops the loader (#7) and restores text + style."""
        self._cu_running = False
        # Un upload/compile ferme le segment d'édition manuelle courant (#35).
        self._manual_edit_segment_open = False
        # Frontière de segment : affiche la popup « passe en Avancé » différée
        # (jamais pendant la frappe — revue 2026-07-29 #7).
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._maybe_show_deferred_manual_popup)
        s = lang_manager.current
        self._stop_btn_spinner(self._btn_compile)
        self._btn_compile.setText(s.studio_compile_upload)
        self._btn_compile.setStyleSheet(self._normal_btn_style())
        self._btn_compile_stable.setEnabled(True)

    def _confirm_overwrite_stable(self) -> bool:
        """Confirmation d'écrasement du code stable (réutilise le popup
        générique du studio ; True = écraser)."""
        return self._show_overwrite_confirm(
            lang_manager.current.studio_transfer_overwrite_msg) == "accept"

    def _on_transfer_to_stable(self):
        """Chevrons » : ouvre la popup de transfert PAR FONCTIONNALITÉ (spec
        2026-07-06) — drag & drop bidirectionnel, staging appliqué d'un bloc.
        Fallback legacy (copie intégrale + confirmation) quand AUCUNE
        fonctionnalité n'existe nulle part : un projet en code brut n'a rien
        à montrer dans la popup. Bloqué pendant une génération/upload."""
        if self._gen_busy is not None or self._cu_running or self._beginner_running:
            return
        # A modal opened below (popup / confirm) grabs the mouse before the
        # chevrons receive their Leave -> they'd stay green until hovered again.
        # Re-sync their hover from the real cursor position once we're back
        # (user 2026-07-08).
        try:
            if not self._features and not self._stable_features:
                self._transfer_all_code_to_stable()
                return
            dirty_ia = is_dirty(self.get_code(), self._code_baseline)
            dirty_stable = is_dirty(self._stable_panel.editor.toPlainText(),
                                    self._stable_baseline)
            # Le transfert reconstruit le code via assemble(features) : si une
            # réparation (auto / Outils) a modifié un éditeur SANS re-découper
            # les features, le modèle est périmé -> on le resynchronise depuis
            # l'éditeur (bug 2026-07-06 : « ancienne version transférée »).
            ia_feats = self._features_synced_for_transfer(self._features,
                                                          self._editor)
            stable_feats = self._features_synced_for_transfer(
                self._stable_features, self._stable_panel.editor)
            dlg = FeatureTransferDialog(
                ia_feats, stable_feats,
                dirty_ia=dirty_ia, dirty_stable=dirty_stable, parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted.value \
                    or not dlg.staging.has_changes():
                return
            ia, stable, removed = dlg.result()
            self._apply_feature_transfer(
                ia, stable, removed,
                ia_changed=dlg._side_changed("ia"),
                stable_changed=dlg._side_changed("stable"),
                recap_msg=" · ".join(dlg._recap_parts(lang_manager.current)))
        finally:
            self._refresh_transfer_hover_from_cursor()

    def _verified_resync(self, features, editor, capture_manual: bool = False):
        """Feature list reflecting the CURRENT editor, under verification.

        A repair (auto / Tools) or a hand edit modifies the editor text without
        re-splitting the model, so assemble(features) would emit the stale code.
        We rebuild the contributions from the editor + owner map, but ONLY trust
        the result when assemble(resynced) faithfully reproduces the editor
        (the owner map is heuristic after a structural repair). Otherwise we
        return the ORIGINAL `features` (same object) — the caller detects the
        no-op by identity. Guards: empty model / bare template (resync would
        rebuild EMPTY contributions and could false-accept).

        Two-tier when `capture_manual` (TODO #31):
        1. try routing orphan (hand-typed) lines to a `manual` feature — kept
           only if it still round-trips (standalone / trailing code) ;
        2. else the legacy neighbor-attach (also the ONLY tier for repair) ;
        3. else stale. No regression: interleaved edits fall to tier 2."""
        if not features:
            return features
        code = editor.toPlainText()
        if self._is_template_or_scaffolded(code):
            return features
        if not is_dirty(code, assemble(features)):
            return features                       # model already faithful
        owners = editor.line_owners()
        if capture_manual:
            cand = sync_features_from_editor(features, code, owners,
                                             manual_id=MANUAL_ID)
            if cand and not is_dirty(assemble(cand), code):
                return cand                       # standalone hand edits captured
        resynced = sync_features_from_editor(features, code, owners)
        if not is_dirty(assemble(resynced), code):
            return resynced                       # verified faithful (neighbor)
        return features                           # unsafe -> fall back

    def _features_synced_for_transfer(self, features, editor):
        """Transfer popup: reflect the editor before rebuilding via assemble
        (defensive net — the model is normally kept canonical by
        `_resync_features_after_repair` / the manual-capture trigger, but a
        divergence here is still flagged by the popup's dirty warning).
        Captures manual edits so the `manual` card is up to date."""
        return self._verified_resync(features, editor, capture_manual=True)

    def _can_reconstruct_from_features(self, target: str = "ia") -> bool:
        """True if the editor is structurally broken (unbalanced braces/parens)
        but assemble(features) is clean — i.e. rebuilding from the model would
        give valid structure. Chantier 3: the feature model is a known-good
        structure (assemble is balanced by construction), a free deterministic
        recovery a repair SLM can't match."""
        from .arduino_cli import _is_structurally_balanced
        features = self._features_for(target)
        if not features:
            return False
        editor_code = self._editor_for(target).toPlainText()
        return (not _is_structurally_balanced(editor_code)
                and _is_structurally_balanced(assemble(features)))

    def _reconstruct_from_features(self, target: str = "ia") -> None:
        """Rewrite the target editor with assemble(features): a clean sketch
        rebuilt from the (balanced-by-construction) model. Resets the baseline,
        re-poses the attribution, saves. Manual edits are lost (the caller
        confirms first)."""
        features = self._features_for(target)
        code = assemble(features)
        if target == "stable":
            ed = self._stable_panel.editor
            ed.blockSignals(True); ed.setPlainText(code); ed.blockSignals(False)
            self._stable_baseline = code
            self._update_code_meta()
            self._refresh_stable_features()
        else:
            self._set_code_with_attribution(code, self._features)
            self._code_baseline = code
            self._index_features(code, self._features)
        self.save_project()
        s = lang_manager.current
        self._active_output_area().begin_phase(
            s.studio_reconstruct_done, theme_manager.current.signal_ok)

    def _confirm_reconstruct_from_features(self, target: str = "ia") -> bool:
        """Confirm popup before rebuilding from features (manual edits lost).
        Cancel = secondary (wire), Rebuild = primary (green): rebuilding is a
        recovery, not a destructive replace, so no red button."""
        s = lang_manager.current
        c = theme_manager.current
        dlg = QDialog(self)
        dlg.setWindowTitle(s.studio_reconstruct_title)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(16)
        lbl = QLabel(s.studio_reconstruct_msg)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"font-size: 10pt; color: {c.text_primary};")
        layout.addWidget(lbl)
        row = QHBoxLayout()
        row.addStretch(1)
        b_cancel = QPushButton(s.gen_modal_cancel)
        b_cancel.setAutoDefault(False)
        b_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        b_cancel.setStyleSheet(secondary_button_qss(c, radius=8, padding="6px 16px"))
        b_cancel.clicked.connect(lambda: dlg.done(0))
        b_ok = QPushButton(s.studio_reconstruct_ok)
        b_ok.setDefault(True)
        b_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        b_ok.setStyleSheet(primary_button_qss(c, radius=8, padding="6px 16px"))
        b_ok.clicked.connect(lambda: dlg.done(1))
        row.addWidget(b_cancel)
        row.addWidget(b_ok)
        layout.addLayout(row)
        dlg.setStyleSheet(f"QDialog {{ background-color: {c.sidebar_bg}; }} "
                          f"QLabel {{ background: transparent; }}")
        return dlg.exec() == 1

    def _resync_features_after_repair(self, target: str = "ia") -> None:
        """Make the feature MODEL canonical again after a repair: rebuild the
        `Feature.*_lines` from the (repaired) editor so the model matches the
        code. Neighbor-attach only (a repair edits existing features, it does
        not add hand-typed code -> no manual capture)."""
        self._apply_verified_resync(target, capture_manual=False, save=False)

    def _apply_verified_resync(self, target: str, *, capture_manual: bool,
                               save: bool) -> None:
        """Shared commit of a verified resync — used by the repair
        canonicalization AND the #31 manual capture. Rebuilds the model from the
        editor; if it changed (and is trusted), refreshes the dropdown, the
        owner map / highlight and (IA) the undo index, and saves when asked.
        No-op when the resync is untrusted (same object returned)."""
        editor = self._editor_for(target)
        features = self._features_for(target)
        synced = self._verified_resync(features, editor,
                                       capture_manual=capture_manual)
        if synced is features:
            return                                # unchanged / not trusted
        if target == "stable":
            self._stable_features = synced
            self._refresh_stable_features()       # re-poses owners + highlight
        else:
            self._features = synced
            # Text is UNCHANGED (a repair already applied it; a hand edit IS the
            # editor content) -> only re-pose the owner map. NEVER re-set the
            # text here: setPlainText would reset the cursor + wipe the undo
            # stack under the user 700 ms after they stopped typing.
            self._reattribute(self._editor, self._features)
            self._refresh_feature_chips()         # dropdown + highlight refresh
            # Realign the undo index on this (code, model) pair.
            self._index_features(self.get_code(), self._features)
        if save:
            self.save_project()

    def _schedule_manual_capture(self, target: str) -> None:
        """Debounce a hand-edit capture pass (#31): standalone orphan code
        becomes the `manual` feature. Skipped during programmatic writes or
        while a generation / repair / upload runs (those aren't user edits)."""
        if (self._suppress_resync or self._gen_busy is not None
                or self._cu_running or self._manual_repair_running
                or self._beginner_running or getattr(self, "_loading", False)):
            return
        self._manual_capture_target = target
        self._manual_capture_timer.start()

    def _run_manual_capture(self) -> None:
        """Debounce timeout: rebuild the model from the edited editor, routing
        standalone hand edits to the `manual` feature (verified — a no-op if it
        doesn't round-trip, so interleaved edits stay in their neighbor)."""
        if (self._gen_busy is not None or self._cu_running
                or self._manual_repair_running or self._beginner_running):
            return
        self._apply_verified_resync(self._manual_capture_target,
                                    capture_manual=True, save=True)
        # Nudge #35 : une retouche à la main = (ré)ouverture d'un segment.
        self._register_manual_edit_segment()

    def _feature_menu_items(self, target: str) -> list:
        """Choices for the editor's « Assign to a feature » submenu (#31):
        (id, label, color) per feature of the target window, plus ALWAYS the
        `manual` bucket (assignable even if it doesn't exist yet)."""
        from .theme import feature_color
        from .generation.gen_prompts import feature_combo_label
        s = lang_manager.current
        items, seen = [], set()
        for f in self._features_for(target):
            label = (s.studio_manual_feature_label if f.id == MANUAL_ID
                     else feature_combo_label(f, max_len=40))
            items.append((f.id, label, feature_color(f.id)))
            seen.add(f.id)
        if MANUAL_ID not in seen:
            items.append((MANUAL_ID, s.studio_manual_feature_label,
                          feature_color(MANUAL_ID)))
        return items

    def _on_assign_lines(self, start: int, end: int, feature_id: str,
                         target: str) -> None:
        """Right-click failsafe (#31): re-attribute editor lines [start,end] to
        `feature_id` (a real feature or `manual`). The visual attribution (owner
        map + highlight) ALWAYS takes effect; the MODEL becomes canonical when
        the new attribution round-trips (a clean block), else it stays
        best-effort — the chosen feature is still surfaced so the dropdown and
        highlight work. The editor TEXT is never touched."""
        editor = self._editor_for(target)
        code = editor.toPlainText()
        lines = code.split("\n")
        owners = list(editor.line_owners())
        owners += [None] * (len(lines) - len(owners))
        lo, hi = max(0, start), min(len(lines) - 1, end)
        if lo > hi:
            return
        for i in range(lo, hi + 1):
            owners[i] = feature_id
        editor.set_line_owners(owners)                    # visual override now
        features = self._features_for(target)
        rebuilt = sync_features_from_editor(features, code, owners,
                                            manual_id=MANUAL_ID)
        if rebuilt and not is_dirty(assemble(rebuilt), code):
            new_features = rebuilt                         # canonical
        else:
            # Not a clean block: keep the model, but make sure the chosen
            # feature exists so the dropdown + highlight surface it.
            new_features = list(features)
            if not any(f.id == feature_id for f in new_features):
                lbl = (lang_manager.current.studio_manual_feature_label
                       if feature_id == MANUAL_ID else "")
                new_features.append(Feature(id=feature_id, prompt="", summary=lbl))
        # Drop a now-orphaned `manual` bucket: if NO editor line is attributed
        # to it anymore (e.g. the user re-assigned all its lines away), it must
        # disappear from the model/dropdown instead of lingering empty.
        if MANUAL_ID not in owners:
            new_features = [f for f in new_features if f.id != MANUAL_ID]
        self._commit_assigned(target, new_features)

    def _commit_assigned(self, target: str, features: list) -> None:
        """Commit an assignment: refresh the dropdown + highlight WITHOUT
        re-posing the owner map (the editor already carries the override) and
        WITHOUT touching the text. Index (IA, for undo) + save."""
        if target == "stable":
            self._stable_features = features
            self._stable_panel.set_features(features, self._stable_panel.is_busy())
            self._stable_panel.refresh_highlights(features)
        else:
            self._features = features
            self._refresh_feature_chips()                 # dropdown + highlight
            self._index_features(self.get_code(), self._features)
        self.save_project()

    def _transfer_all_code_to_stable(self):
        """Legacy full-buffer copy (pre-popup chevron behavior), kept for
        projects WITHOUT features: copies the AI editor TEXT as-is (manual
        edits preserved) + ownership map. Confirmation if stable is non-empty
        and different."""
        ai_code = self.get_code()
        cur = self._stable_panel.editor.toPlainText()
        if cur.strip() and cur != ai_code and not self._confirm_overwrite_stable():
            return
        self._stable_panel.editor.setPlainText(ai_code)
        self._stable_features = [copy.deepcopy(f) for f in self._features]
        # Code identique a cet instant -> on recopie la carte d'ownership IA.
        self._stable_panel.editor.set_line_owners(list(self._editor.line_owners()))
        self._stable_baseline = ai_code
        self._stable_panel.set_features(self._stable_features,
                                        self._stable_panel.is_busy())
        self.save_project()

    def _apply_feature_transfer(self, ia, stable, removed_ia_ids, *,
                                ia_changed: bool, stable_changed: bool,
                                recap_msg: str = ""):
        """Applies the popup result atomically (spec §D): each MODIFIED
        window is reassembled from its feature list, single save, one journal
        line. The IA side follows the delete-flow pattern: undo checkpoint
        BEFORE the swap, metadata cleanup of removed features, then
        _commit_generated_code (which indexes the AFTER state)."""
        if ia_changed:
            self._index_features(self.get_code(), self._features)
            self._features = list(ia)
            self._wiring_resolutions = _strip_feature_metadata(
                self._wiring_resolutions, removed_ia_ids)
            self._implicit_actions = _strip_feature_metadata(
                self._implicit_actions, removed_ia_ids)
            self._commit_generated_code(assemble(self._features), self._features)
            self._refresh_action_button_styles()
            self._refresh_feature_chips()
        if stable_changed:
            # Index the BEFORE state, apply UNDOABLY, index the AFTER state ->
            # a native Ctrl+Z on the stable editor reverts the transfer.
            self._index_stable_features(self._stable_panel.editor.toPlainText())
            self._stable_features = list(stable)
            code = assemble(self._stable_features)
            self._set_stable_code(code)              # undoable (suppresses resync)
            self._reset_comments_state("stable")     # code complet -> case Commentaires cochée
            self._stable_baseline = code
            self._update_code_meta()
            self._refresh_stable_features()
            self._index_stable_features(code)
        self.save_project()
        s = lang_manager.current
        self._active_output_area().begin_phase(
            recap_msg or s.feature_transfer_title,
            theme_manager.current.text_secondary)

    def _on_stable_compile_upload(self):
        """Compile + upload la fenêtre STABLE, SANS réparation IA
        (backend=None). Partage la garde _cu_running (un seul upload à la
        fois) et la console avec la fenêtre IA ; désactive le bouton IA
        pendant l'opération."""
        if self._cu_running:
            self._cancel_cu_worker()
            return
        s = lang_manager.current
        code = self._stable_panel.editor.toPlainText()
        pf = self._preflight_compile_upload(
            lambda m: self._set_cu_status(m, error=True), code=code)
        if pf is None:
            return
        code, fqbn, port = pf
        board_name = self._board_name()
        self._last_repair_steps = []
        self._cu_running = True
        self._cu_active_restore = self._restore_stable_btn
        self._btn_compile.setEnabled(False)          # un seul upload à la fois
        self._btn_compile_stable.setStyleSheet(self._cancel_btn_style())
        self._start_btn_spinner(self._btn_compile_stable, label=s.studio_cancel)
        self._adv_console.log.clear()
        self._adv_console.log.begin_phase(s.studio_console_src_stable, "#8b5cf6")
        self._cu_worker = self._compile_service.run(
            code=code, fqbn=fqbn, port=port,
            backend=None,                      # <-- jamais de réparation IA
            board_name=board_name,
            console=self._adv_console, clear=False,   # déjà nettoyé ci-dessus
            on_finished=self._restore_stable_btn,
        )

    def _restore_stable_btn(self):
        self._cu_running = False
        s = lang_manager.current
        self._btn_compile.setEnabled(True)
        self._stop_btn_spinner(self._btn_compile_stable)
        self._btn_compile_stable.setText(s.studio_compile_upload_stable)
        self._btn_compile_stable.setStyleSheet(self._normal_btn_style())

    def _set_cu_status(self, msg: str, *, error: bool = False, success: bool = False):
        """PRE-FLIGHT compile/upload error (no board, no port, no
        code, arduino-cli absent…): it is a config/wiring problem,
        NOT a code error. We show it CLEARLY in the journal (red
        line), WITHOUT the « demander de l'aide sur cette erreur » button (the AI
        can do nothing for « plug in a board »). The real COMPILATION errors
        go through the compile_service done standard (append_explanation +
        set_done(False) which exposes the help button).

        The message is ADDED below the existing one (e.g. below « Code prêt »), we
        do not clear the journal; we just hide any stale button."""
        if error and msg:
            self._output_area.hide_actions()
            self._output_area.begin_phase(msg, "#ef4444")   # red = error

    # ── « busy » buttons + veil + generation loader ────────────
    #
    # The robot is not shown in the buttons: the triggering button
    # only carries its cancellation label (« Annuler »). During an operation
    # (generation / compile / upload) in int/advanced, a VEIL covers the code
    # (editing impossible, robot + text centered) — driven by _start/_stop_btn_
    # spinner -> _refresh_busy_loader. IN ADDITION, the GENERATION writes an
    # animated line -> « Code prêt » directly in the current mode's journal
    # (uniform across all modes, cf. _start_gen_loader). In beginner, no veil
    # (the editor is hidden): only the journal line.

    def _busy_text_for(self, btn) -> str:
        s = lang_manager.current
        # v2 : pendant la vérif / le recombine, le voile affiche l'étape en cours
        # (« Vérification… » / « régénération… ») plutôt que « Génération ».
        if self._busy_text_override:
            return self._busy_text_override
        if btn in (self._btn_generate, self._btn_generate_send):
            return s.studio_generating
        if btn is self._btn_upload_only:
            return s.studio_uploading
        return s.studio_compiling

    def _start_btn_spinner(self, btn, label: str = ""):
        """Remembers the text of `btn`, shows its cancellation label (`label`,
        e.g. « Annuler ») to stay clickable, and updates the veil."""
        if btn not in self._spinner_btns:
            self._spinner_btns[btn] = (btn.text(), label)
        if label:
            btn.setText(label)
        self._refresh_busy_loader()

    def _stop_btn_spinner(self, btn):
        """Restores the original text of `btn` and updates the veil."""
        if btn in self._spinner_btns:
            saved, _label = self._spinner_btns.pop(btn)
            btn.setText(saved)
        self._refresh_busy_loader()

    def _busy_panel_for(self, btn):
        """Fenêtre visée par le voile selon le bouton déclencheur : la fenêtre
        STABLE pour son propre upload (`_btn_compile_stable`), la fenêtre IA
        (générée) sinon — génération, vérif/recombine et upload IA ciblent
        tous `_code_panel`."""
        if btn is self._btn_compile_stable:
            return self._stable_panel
        return self._code_panel

    def _refresh_busy_loader(self):
        """Shows/hides the veil according to the operating buttons (int/advanced).
        Text = that of the last started button ; the veil covers the WINDOW that
        button drives (stable window for a stable upload, IA window otherwise)."""
        if self._spinner_btns:
            btn = next(reversed(self._spinner_btns))
            self._set_busy_loader(True, self._busy_text_for(btn),
                                  panel=self._busy_panel_for(btn))
        else:
            self._set_busy_loader(False)

    def _set_busy_loader(self, active: bool, text: str = "", panel=None):
        """Voile sur le code (édition impossible) pendant une opération, en
        int/avancé seulement (en débutant l'éditeur est masqué -> pas de
        voile, c'est la ligne du journal qui informe). `panel` = la fenêtre
        voilée (IA ou stable) ; l'AUTRE fenêtre est toujours dé-voilée pour ne
        jamais laisser un voile figé sur la mauvaise fenêtre (ex. uploader le
        stable ne doit pas voiler l'IA). Le voile (robot + texte) est animé par
        le timer INTERNE au CodePanel (Prompt 3)."""
        target = (panel or self._code_panel) if (
            active and self._current_mode != "beginner") else None
        for p in (self._code_panel, self._stable_panel):
            p.set_busy(text if p is target else None)
        # Voile posé -> puces grisées ; retiré -> réactivables (les 2 fenêtres).
        self._refresh_feature_chips()
        self._refresh_stable_features()

    # ── Operation loader: timer de la LIGNE ANIMÉE du journal ────────
    def _install_gen_slow_watchdog(self):
        """Deux minuteries a un coup qui n'ARRETENT rien (TODO #24).

        Le defaut repare : une generation qui depassait 300 s etait TUEE, et
        l'utilisateur perdait tout parce que sa demande etait complexe. Le
        couperet a ete retire des trois backends ; restait a ne pas laisser
        l'utilisateur devant une ligne animee qui tourne sans fin.

        Les delais ne sont pas pris au hasard. **300 s est exactement la ou la
        generation MOURAIT** : au lieu de tout perdre a cet instant precis, on
        y lit desormais que ca continue. 120 s est la moitie, assez tot pour
        rassurer avant l'inquietude, assez tard pour ne pas se declencher sur
        une generation normale.

        Modele : le watchdog du chat (`chat_view`), a une difference pres qui
        interdit de le recopier — le chat STREAME, ses minuteries se relancent
        a chaque chunk et mesurent donc un SILENCE. Ici `generate_code` est un
        appel bloquant sans chunk : il n'y a rien a relancer, ces minuteries
        mesurent le temps ECOULE. Meme UX, mecanique differente.
        """
        for attr, ms, msg in (
                ("_gen_slow_soft_timer", _GEN_SLOW_SOFT_MS, "soft"),
                ("_gen_slow_hard_timer", _GEN_SLOW_HARD_MS, "hard")):
            t = getattr(self, attr, None)
            if t is None:
                t = QTimer(self)
                t.setSingleShot(True)
                t.timeout.connect(
                    lambda kind=msg: self._on_gen_slow(kind))
                setattr(self, attr, t)
            t.start(ms)

    def _stop_gen_slow_watchdog(self):
        """Coupe les deux minuteries. Appelee par les DEUX sorties du loader
        (succes et erreur/annulation) : une minuterie qui survit a la fin
        d'une generation ecrirait << c'est plus long que d'habitude >> sur un
        journal ou le code est deja pret."""
        for attr in ("_gen_slow_soft_timer", "_gen_slow_hard_timer"):
            t = getattr(self, attr, None)
            if t is not None:
                t.stop()

    def _on_gen_slow(self, kind: str):
        """Ecrit un message NON BLOQUANT dans le journal. N'annule rien,
        ne touche pas au worker, ne change aucun etat.

        ⚠️ L'ordre des trois appels n'est pas cosmetique. `set_live_line`
        previent : << use only when nothing else writes to the log at the same
        time (otherwise the anchor comes loose) >>. Ecrire pendant que la ligne
        animee tourne ferait selectionner le message par l'ancre au tick
        suivant, qui l'EFFACERAIT. On retire donc la ligne animee d'abord ; le
        tick suivant la recree en dessous du message.
        """
        journal = self._gen_loader_journal
        if journal is None:
            return                      # generation deja finie
        s = lang_manager.current
        journal.clear_live_line()
        journal.begin_phase(
            s.studio_gen_slow_soft if kind == "soft" else s.studio_gen_slow_hard,
            theme_manager.current.signal_warn)

    def _start_gen_loader(self):
        """Resets the current mode's journal and starts the animated line
        « Génération en cours… » (uniform across all modes), SYNCHRONOUS with the veil
        (same timer/frame). The editor blocking is ensured by the veil."""
        # Force-disconnect the serial console for the whole generation: a live
        # connection holds the COM port (which the upload that may follow needs
        # free) and would keep streaming the OLD program's output into the
        # journal while the new code is being generated. Idempotent + updates
        # the « Connect » button via close_port() -> _set_ui_connected(False).
        self._serial_monitor.close_port()
        self._serial_monitor_beg.close_port()
        # Journal frozen for the whole duration (robust to a mode change
        # during the generation, allowed by #12).
        self._gen_loader_journal = (
            self._beg_output_area if self._current_mode == "beginner"
            else self._output_area)
        self._gen_loader_journal.clear()
        self._ensure_loader_timer()
        self._install_gen_slow_watchdog()

    def _ensure_loader_timer(self):
        """Démarre le timer de la ligne animée du journal s'il est arrêté
        (repart à la frame 0) et peint immédiatement une 1re frame."""
        if not self._loader_timer.isActive():
            self._loader_idx = 0
            self._tick_loader()
            self._loader_timer.start()

    def _maybe_stop_loader_timer(self):
        """Arrête le timer quand la ligne animée du journal ne tourne plus
        (le voile a son propre timer, dans le CodePanel)."""
        if self._gen_loader_journal is None:
            self._loader_timer.stop()

    def _tick_loader(self):
        """Fait avancer la ligne animée « Génération en cours… » du journal
        (le voile est animé à part par le CodePanel)."""
        i = self._loader_idx
        self._loader_idx += 1
        raw = RobotLoader.FRAMES[i % len(RobotLoader.FRAMES)]
        nd = i % 4
        if self._gen_loader_journal is not None:
            esc = raw.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            pad = max(0, 7 - len(raw))                   # fixed width = max frame
            frame = "&nbsp;" * (pad // 2) + esc + "&nbsp;" * (pad - pad // 2)
            dots = "." * nd + "&nbsp;" * (3 - nd)        # 3 reserved dots
            color = theme_manager.current.signal_ok
            txt = lang_manager.current.studio_generating
            html = phase_div_html(
                f'<span style="font-family: Consolas, monospace; font-size: 10pt; '
                f'color: {color}; font-weight: bold;">{frame}&nbsp;&nbsp;{txt}{dots}'
                f'</span>', color)
            self._gen_loader_journal.set_live_line(html)

    def _verify_skip_reason(self) -> str:
        """Pourquoi la vérification compile ne peut PAS tourner, ou "" si elle
        le peut. Localisé : ça s'affiche.

        `_start_assembly_verify` se contente d'un `return False` dans ce cas,
        et l'appelant écrivait alors « Code prêt » — le même libellé qu'un code
        réellement compilé ET réparé. La promesse « toute génération compile
        avant d'être livrée » ne tenait donc pas, en silence. Et ce n'est pas
        un cas limite : `fqbn` est nul dès qu'AUCUNE CARTE n'est sélectionnée,
        soit l'état normal d'un débutant qui n'a pas encore branché la sienne
        (QA A4b, 2026-08-08)."""
        s = lang_manager.current
        if not arduino_cli.is_available():
            return s.studio_unverified_no_cli
        env, model = board_manager.env, board_manager.model
        if not (env and model and get_fqbn(env, model)):
            return s.studio_unverified_no_board
        return ""

    def _stop_gen_loader_ready(self, unverified: str = ""):
        """Stops the journal line and REPLACES it with « Code prêt : … ».

        `unverified` (cf. `_verify_skip_reason`) : la raison pour laquelle le
        code n'a PAS été compilé. Elle est accolée au libellé et le fait
        passer en ambre — annoncer en vert, du même mot, un code vérifié et un
        code jamais compilé est exactement le genre de devinette présentée
        comme une certitude que les filets du câblage existent pour éviter."""
        if self._gen_loader_journal is not None:
            text, color = self._program_ready_text()
            if unverified:
                text = f"{text} ({unverified})"
                color = theme_manager.current.signal_warn
            self._gen_loader_journal.set_live_line(phase_title_html(text, color))
            self._gen_loader_journal.commit_live_line()
            self._gen_loader_journal = None
        self._stop_gen_slow_watchdog()
        self._maybe_stop_loader_timer()

    def _stop_gen_loader(self):
        """Stops the journal line WITHOUT « Code prêt » (error / cancellation)."""
        if self._gen_loader_journal is not None:
            self._gen_loader_journal.clear_live_line()
            self._gen_loader_journal = None
        self._stop_gen_slow_watchdog()
        self._maybe_stop_loader_timer()

    def _hide_status_labels(self):
        self._cu_spin_row.setVisible(False)
        self._lbl_beginner_status.setVisible(False)

    def _normal_btn_style(self) -> str:
        # PRIMARY button (centralized agreed style): solid btn_primary_bg ->
        # GREEN on hover. cf theme.primary_button_qss.
        return primary_button_qss(theme_manager.current, font_pt=11,
                                  padding="0 26px")

    def _secondary_btn_style(self) -> str:
        """SECONDARY button (centralized agreed style): transparent outline
        (white border in dark / gray in light) -> GREEN border + text on
        hover. cf theme.secondary_button_qss."""
        return secondary_button_qss(theme_manager.current, font_pt=10,
                                    padding="0 18px")

    def _neutral_btn_style(self) -> str:
        """NEUTRAL button: solid OPAQUE in the background color (main_bg) -> does
        NOT let the window behind show through (unlike the transparent
        outline), GREEN border + text on hover. cf theme.neutral_button_qss."""
        return neutral_button_qss(theme_manager.current, font_pt=10,
                                  padding="0 18px")

    def _refresh_action_button_styles(self):
        """The int/advanced generation button is now UNIQUE (the modal
        handles Regenerate/Add/Modify): it always stays in primary style
        (blue). In beginner mode, « Generer et uploader » switches to secondary
        after a generation in favor of « Uploader »."""
        self._btn_generate.setStyleSheet(self._normal_btn_style())
        # Beginner mode: after generation, « Generer et uploader »
        # de-emphasizes in favor of « Uploader » but stays OPAQUE (neutral
        # style = main_bg background) instead of transparent outline, so as not to
        # let the window behind show through (user request).
        if self._has_generated and self._current_mode == "beginner":
            self._btn_generate_send.setStyleSheet(self._neutral_btn_style())
        else:
            self._btn_generate_send.setStyleSheet(self._normal_btn_style())
        self._btn_upload_only.setStyleSheet(self._normal_btn_style())
        if not self._beginner_running:
            self._btn_upload_only.setEnabled(self._uploadable())
        # "Voir le schéma" BEGINNER button: primary style (white) like the
        # two other beginner buttons (user request).
        self._btn_view_schema.setStyleSheet(self._normal_btn_style())
        # "Voir le schéma" int/advanced button: NEUTRAL style (solid background
        # color -> opaque, does not let the grid show through; black text in light;
        # green on hover). cf theme.neutral_button_qss (user request).
        self._btn_view_schema_adv.setStyleSheet(
            neutral_button_qss(theme_manager.current, font_pt=11, padding="0 18px")
        )
        # « Voir le schéma » STABLE : même style neutre.
        if hasattr(self, "_btn_view_schema_stable"):
            self._btn_view_schema_stable.setStyleSheet(
                neutral_button_qss(theme_manager.current, font_pt=11, padding="0 18px")
            )
        # L'ACTIVATION des trois boutons suit le CODE, pas la génération.
        self._refresh_schema_buttons()

    def _code_is_drawable(self, code: str) -> bool:
        """True when `code` holds a real program rather than the bare editor
        template (possibly scaffolded with `Serial.begin`)."""
        return bool(code.strip()) and not self._is_template_or_scaffolded(code)

    def _uploadable(self) -> bool:
        """True quand il y a un vrai programme à téléverser.

        Même raison que `_refresh_schema_buttons` : on téléverse du CODE, pas
        une génération. `_has_generated` répond « une génération a-t-elle eu
        lieu ? » et reste faux pour du code écrit ou collé à la main — le
        bouton Schéma a été corrigé le 2026-08-08, celui-ci était resté en
        arrière (QA E1). Les pré-requis matériels (carte, port, arduino-cli)
        ne sont PAS testés ici : `_preflight_compile_upload` les vérifie au
        clic et sait dire lequel manque, ce qu'un bouton grisé ne peut pas."""
        return self._code_is_drawable(self._editor.toPlainText())

    def _refresh_schema_buttons(self) -> None:
        """Enable the three « Voir le schéma » buttons from the CODE present.

        The schematic is DERIVED from the code, so its button must follow the
        code -- not `_has_generated`, which answers « has a GENERATION
        happened? » and stays False for code the user typed or pasted himself
        (`_apply_verified_resync` is a no-op when hand-written code does not
        round-trip, so no feature is created and the flag never flips).
        Consequence before this fix: in Advanced mode, someone writing his own
        sketch could NEVER open the schematic (QA section E, 2026-08-08). The
        stable window already applied this rule; the two others did not.

        Cheap on purpose (setEnabled only, no restyling): it runs on every
        keystroke.
        """
        if not hasattr(self, "_btn_view_schema"):
            return   # called before the buttons exist (early init)
        drawable = self._code_is_drawable(self._editor.toPlainText())
        self._btn_view_schema.setEnabled(drawable)
        self._btn_view_schema_adv.setEnabled(drawable)
        if hasattr(self, "_btn_view_schema_stable"):
            self._btn_view_schema_stable.setEnabled(
                self._code_is_drawable(
                    self._stable_panel.editor.toPlainText()))
        # « Uploader » (débutant) suit la même règle, et pour la même raison :
        # on téléverse du code, pas une génération. Sans ce rafraîchissement
        # il resterait grisé jusqu'à la prochaine génération, donc coller un
        # sketch donnerait le schéma mais pas l'upload (QA E1).
        if hasattr(self, "_btn_upload_only") and not self._beginner_running:
            self._btn_upload_only.setEnabled(self._uploadable())

    def _cancel_btn_style(self) -> str:
        """Style of the button that INTERRUPTS a running compilation. Kept as a
        method (rather than a `variant` property) because the three call sites
        SWAP this style onto a button that is already shown: a dynamic property
        set after the first show does not take effect without a style
        unpolish/polish, whereas setStyleSheet applies immediately."""
        return danger_button_qss(theme_manager.current)

    def _is_template_or_scaffolded(self, code: str) -> bool:
        """True if `code` is a known template, possibly enriched
        with the `Serial.begin(9600);` scaffolding injected by the
        "Serial Monitor" checkbox. Used instead of `is_known_template` so
        that the mode change and going through this scaffolding do not
        wrongly flip `_has_generated` to True.
        """
        if lang_manager.is_known_template(code):
            return True
        # Removes a single `Serial.begin(N);` line if it is present
        # at the start of an indented block (i.e. in a function body, not
        # a comment) then re-tests the pure template.
        stripped = _re.sub(
            r'^[ \t]*Serial\.begin\s*\(\s*\d+\s*\)\s*;[ \t]*\n',
            '',
            code,
            count=1,
            flags=_re.MULTILINE,
        )
        return stripped != code and lang_manager.is_known_template(stripped)

    def _board_name(self) -> str:
        env, model = board_manager.env, board_manager.model
        if env and model:
            return f"{BOARDS.get(env, {}).get('label', env)} {model}"
        return "Arduino Uno"

    def resizeEvent(self, event):
        """Limits the width of the Tools panel to 1/3 of the Studio.

        Recomputed on every window resize. The floor
        stays 180px (comfortable minimum width for the cards) — if the
        window becomes very narrow, the third may drop below that
        threshold and the minimum wins.
        """
        super().resizeEvent(event)

    # ── Theme ─────────────────────────────────────────────────

    def apply_theme(self, c: ColorScheme):
        p = self.palette()
        p.setColor(QPalette.ColorRole.Window, QColor(c.main_bg))
        self.setPalette(p)
        self.setAutoFillBackground(True)
        # Scroll transparent : la gouttière de scrollbar laisse voir la grille
        # statique de `_main_row_w` derrière (cf. build).
        self._scroll.setStyleSheet("background: transparent; border: none;")
        self._content.set_bg(c.main_bg)       # grille du viewport (scrollée)
        self._main_row_w.set_bg(c.main_bg)    # grille statique pleine largeur
        # (Overlay commentaires + voile busy : thème appliqué par le
        # CodePanel lui-même — Prompt 3.)
        # Section headers in mono-caps 8 pt text_secondary (spec §6, style
        # « _GÉNÉRER UNE FONCTIONNALITÉ », « _ » prefix added at setText #10).
        # Capitals + letter-spacing via QFont (impossible in QSS).
        for lbl in (self._lbl_prompt, self._lbl_code, self._lbl_output,
                    self._lbl_instructions_title, self._lbl_serial_beg_title,
                    self._lbl_serial_title,
                    self._lbl_window_ai, self._lbl_window_stable):
            lbl.setFont(mono_caps_font(8))
            # Section titles in white (text_primary) — user request:
            # more readable than the previous discreet gray (text_secondary).
            lbl.setStyleSheet(
                f"color: {c.text_primary}; background: transparent;"
            )
        # « Outils » pill of the code header: same look as the « Fonctionnalités »
        # dropdown button (filled main_bg + border, white text in the default UI
        # font — NO mono-caps), edge that tints to phosphor on hover.
        _tools_btn_qss = f"""
            QPushButton {{
                background-color: {c.main_bg};
                border: 1px solid {c.border};
                border-radius: 4px;
                padding: 1px 7px;
                color: {c.text_primary};
            }}
            QPushButton:hover {{
                border-color: {c.signal_ok};
                color: {c.signal_ok};
            }}
        """
        self._btn_ai_tools.setStyleSheet(_tools_btn_qss)
        # Default UI font (same as the dropdown label) -> label reads « Outils »,
        # not « OUTILS ». No setFont: inherit the app default like the dropdown.
        # SPARKLES icon handled by install_icon_hover (white at rest -> green on
        # hover, follows the theme). Do not re-set it here (otherwise it overwrites the filter).
        # Line counter: discreet mono, small size.
        _meta_qss = (
            f"font-family: {MONO_CSS}; color: {c.text_secondary};"
            f" background: transparent; font-size: 8pt;"
        )
        self._lbl_code_meta.setStyleSheet(_meta_qss)
        # Section d'outils DÉDIÉE à la fenêtre stable (mêmes styles).
        if hasattr(self, "_btn_ai_tools_st"):
            self._btn_ai_tools_st.setStyleSheet(_tools_btn_qss)
            self._lbl_code_meta_st.setStyleSheet(_meta_qss)
        # "Comments" slider (Advanced mode): secondary label + themed track and
        # handle.
        self._lbl_comments_label.setStyleSheet(
            f"font-size: 9pt; color: {c.text_secondary};"
        )
        # Level label: mono caps, signal_ok color (spec §3).
        self._lbl_comments_value.setStyleSheet(
            f"font-family: 'Cascadia Mono', Consolas, monospace;"
            f" font-size: 9pt; font-weight: 600; letter-spacing: 1px;"
            f" color: {c.signal_ok};"
        )
        # « + Attach » button floating in the prompt field: discreet (surface +
        # border), secondary text, tints on hover.
        # `bg=c.code_bg`: this chip floats over the prompt FIELD, whose
        # background is code_bg -- its chat twin sits on `surface` instead.
        # That difference is the whole reason `chip_button_qss` takes `bg=`.
        self._btn_attach_prompt.setStyleSheet(chip_button_qss(c, bg=c.code_bg))
        self._comments_slider.setStyleSheet(slider_qss(c))
        # « Moniteur série » / « Afficher les commentaires » checkboxes: centralized
        # agreed style (white/gray outline indicator -> GREEN on hover and when checked,
        # with a white check). cf theme.radio_checkbox_qss.
        chk_style = radio_checkbox_qss(c, font_pt=9)
        self._chk_serial_monitor.setStyleSheet(chk_style)
        self._chk_show_comments.setStyleSheet(chk_style)
        if hasattr(self, "_chk_show_comments_st"):
            self._chk_show_comments_st.setStyleSheet(chk_style)
        self._lbl_gen_error.setStyleSheet("font-size: 9pt; color: #ef4444;")
        self._beg_instructions_w.setStyleSheet(f"""
            QWidget {{
                background-color: {c.sidebar_bg};
                border: 1px solid {c.border};
                border-radius: 8px;
            }}
            QLabel {{
                background-color: transparent;
                border: none;
            }}
        """)

        spin_style = f"font-size: 11pt; color: {c.accent}; font-weight: bold;"
        text_style = f"font-size: 9pt; font-style: italic; color: {c.accent};"
        for lbl in (self._lbl_gen_spinner, self._lbl_beg_spinner, self._lbl_cu_spinner):
            lbl.setStyleSheet(spin_style)
        for lbl in (self._lbl_gen_spin_text, self._lbl_cu_spin_text):
            lbl.setStyleSheet(text_style)

        # Prompt area: background via QPalette (Base=input_bg); border/rounding/
        # padding in QSS (spec §3). background-color redundant but reliable when
        # a style sheet is applied (both equal input_bg, zero conflict).
        pf = self._prompt_field.palette()
        pf.setColor(QPalette.ColorRole.Base, QColor(c.input_bg))
        pf.setColor(QPalette.ColorRole.Text, QColor(c.text_primary))
        pf.setColor(QPalette.ColorRole.PlaceholderText, QColor(c.text_secondary))
        self._prompt_field.setPalette(pf)
        self._prompt_field.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {c.input_bg};
                color: {c.text_primary};
                border: 1px solid {c.border};
                border-radius: 6px;
                padding: 12px 14px;
                font-size: 10pt;
                selection-background-color: {selection_bg(c)};
                selection-color: {c.text_primary};
            }}
            QPlainTextEdit:focus {{ border-color: {c.signal_ok}; }}
        """)

        btn_style = self._normal_btn_style()
        if not self._cu_running:
            self._btn_compile.setStyleSheet(btn_style)
        # Advanced 2-window mode: stable-editor compile button (primary) +
        # transfer chevrons (» IA->stable / « stable->IA) : SANS contour,
        # blancs au repos, verts au survol — hover COLLECTIF géré par
        # l'eventFilter (cf. _set_transfer_hover). Le changement de thème
        # repose l'état repos.
        self._btn_compile_stable.setStyleSheet(self._normal_btn_style())
        self._set_transfer_hover(False)
        # Action buttons (generate/iterate/generate_send/upload_only):
        # styles handled by _refresh_action_button_styles (toggles primary
        # /secondary depending on _has_generated).
        self._refresh_action_button_styles()

    # ── Language ────────────────────────────────────────────────

    def apply_lang(self, s: Strings):
        # If no generation has been done and the editor still contains
        # a known template (pure or enriched with the Serial.begin scaffolding),
        # we replace it with the template in the new language and
        # re-inject the scaffolding if applicable.
        if (not self._has_generated
                and self._is_template_or_scaffolded(self._editor.toPlainText())):
            self._editor.setPlainText(lang_manager.editor_template())
            if (self._current_mode == "advanced"
                    and self._chk_serial_monitor.isChecked()):
                self._apply_serial_monitor_state(True, mark_dirty=False)
        # #10: all the Studio section titles are prefixed with « _ » (console
        # cursor, Direction B theme). The prefix is purely visual -> applied
        # here, not in the i18n strings (which stay reusable elsewhere, e.g.
        # QMessageBox title).
        self._lbl_prompt.setText("_" + s.studio_prompt_label)
        self._lbl_comments_label.setText(s.studio_comments_label)
        self._refresh_comments_value_label()
        self._chk_serial_monitor.setText(s.studio_serial_monitor_chk)
        self._chk_show_comments.setText(s.studio_show_comments)
        # Prompt placeholder = rotating tips (PromptTipRotator): it
        # handles the language change itself (listens to lang_manager.changed).
        self._btn_attach_prompt.setText(s.studio_attach)
        self._btn_attach_prompt.setToolTip(s.studio_context_add_tooltip)
        self._prompt_field._reposition_overlay()
        self._lbl_code.setText("_" + s.studio_code_label)
        # « Outils » pill: translated label (rendered in capitals by the
        # mono-caps font -> « OUTILS »), + tooltip.
        self._btn_ai_tools.setText(s.studio_ai_tools_label)
        self._btn_ai_tools.setToolTip(s.studio_ai_tools_title)
        # Section d'outils de la fenêtre stable (mêmes libellés).
        if hasattr(self, "_btn_ai_tools_st"):
            self._chk_show_comments_st.setText(s.studio_show_comments)
            self._btn_ai_tools_st.setText(s.studio_ai_tools_label)
            self._btn_ai_tools_st.setToolTip(s.studio_ai_tools_title)
        self._update_code_meta()   # the word « lignes » depends on the language
        self._btn_generate.setText(s.studio_generate)
        if not self._cu_running:
            self._btn_compile.setText(s.studio_compile_upload)
        self._btn_generate_send.setText(s.studio_generate_send)
        self._btn_upload_only.setText(s.studio_upload_only)
        # The three « Voir le schéma » buttons (beginner / AI / stable) carried
        # the French label HARD-CODED at construction while `studio_action_schema`
        # existed, translated, and was quoted to the chat as the app's own
        # vocabulary — the app named the button in one language and described it
        # in another. Same key on all three: it is the same action.
        self._btn_view_schema.setText(s.studio_action_schema)
        self._btn_view_schema_adv.setText(s.studio_action_schema)
        if hasattr(self, "_btn_view_schema_stable"):
            self._btn_view_schema_stable.setText(s.studio_action_schema)
        self._lbl_output.setText("_" + s.studio_output_label)
        self._lbl_gen_spin_text.setText(s.studio_generating)
        self._lbl_instructions_title.setText("_" + s.studio_instructions_title)
        self._lbl_serial_beg_title.setText("_" + s.studio_output_label)  # « Journal » (#6)
        self._lbl_serial_title.setText("_" + s.serial_title)
        # Advanced 2-window mode: window titles + transfer/stable-upload buttons.
        self._lbl_window_ai.setText("_" + s.studio_window_ai)
        self._lbl_window_stable.setText("_" + s.studio_window_stable)
        # Chevrons de transfert (posés à la construction) ; les libellés
        # n'apparaissent qu'en infobulle.
        self._btn_transfer.setToolTip(s.studio_transfer_to_stable)
        self._btn_transfer_back.setToolTip(s.studio_transfer_to_ai)
        self._btn_compile_stable.setText(s.studio_compile_upload_stable)

    # ── Comments verbosity slider (Advanced mode) ──────────

    _COMMENTS_LEVEL_KEYS = (
        "studio_comments_none",
        "studio_comments_minimal",
        "studio_comments_standard",
        "studio_comments_detailed",
    )

    def _on_comments_verbosity_changed(self, _v: int):
        self._refresh_comments_value_label()
        # Persistence: the chosen level is saved in the project.
        # _mark_dirty respects the _loading flag (no dirty on opening).
        self._mark_dirty()

    def _refresh_comments_value_label(self):
        s = lang_manager.current
        idx = self._comments_slider.value()
        idx = max(0, min(len(self._COMMENTS_LEVEL_KEYS) - 1, idx))
        self._lbl_comments_value.setText(
            getattr(s, self._COMMENTS_LEVEL_KEYS[idx]).upper()   # mono caps (spec §3)
        )

    def _comments_verbosity(self) -> int:
        """Current level, applied only in Advanced mode (ignored otherwise).

        Returns 0 (none), 1 (minimal), 2 (standard) or 3 (detailed).
        """
        return self._comments_slider.value()

    def _serial_prompt_directive(self) -> str:
        """Serial directive to add to the LLM prompt (Advanced mode only).

        - Checked: asks the AI to include Serial.begin(9600) in
          setup() and allows Serial.print/println for debugging.
        - Unchecked: formally forbids any Serial call.

        Note: we no longer inject Serial.begin via editor-side scaffolding
        (it led to duplicates when the AI added one back). So it is
        the AI that places the line, period.
        """
        if self._chk_serial_monitor.isChecked():
            return (
                "\nInclude Serial.begin(9600) in setup() for serial "
                "communication. You may use Serial.print/Serial.println "
                "at meaningful points to log state or debug information."
            )
        return (
            "\nDo NOT use Serial.print, Serial.println or Serial.begin "
            "anywhere in the generated code. The serial port is disabled."
        )

    # ── Serial Monitor checkbox (Advanced mode) ───────────────────

    def _on_serial_monitor_toggled(self, checked: bool):
        """Runtime toggle: mute / unmute the current code + marks dirty.

        - Checked: uncomments the existing `// Serial.(begin|print|println)(...)`.
          (We no longer inject Serial.begin scaffolding — the
          duplicates were a problem: the AI added one back on each
          generation. The prompt directive now asks the AI to
          place the line itself.)
        - Unchecked: comments out every `Serial.(begin|print|println)(...)` line.

        The tracker is suspended during the edit so the lines
        keep their original tag via their QTextBlock.
        """
        if self._loading:
            return
        self._apply_serial_monitor_state(checked, mark_dirty=True)

    def _apply_serial_monitor_state(self, checked: bool, *, mark_dirty: bool):
        """Applies the checkbox state to the editor content.

        Used by the user toggle (mark_dirty=True) and by loading
        a project or setting up the template (mark_dirty=False).
        """
        doc = self._editor.document()
        self._loading = True
        try:
            if checked:
                self._uncomment_serial_in_document(doc)
            else:
                self._comment_out_serial_in_document(doc)
        finally:
            self._loading = False
        if mark_dirty:
            self._mark_dirty()

    def _comment_out_serial_in_document(self, doc):
        cursor = QTextCursor(doc)
        in_block_comment = False
        block = doc.firstBlock()
        while block.isValid():
            text = block.text()
            if in_block_comment:
                if '*/' in text:
                    in_block_comment = False
                block = block.next()
                continue
            if '/*' in text and '*/' not in text.split('/*', 1)[1]:
                in_block_comment = True
                block = block.next()
                continue
            stripped = text.lstrip()
            if stripped.startswith('//'):
                block = block.next()
                continue
            if _SERIAL_STMT_RE.search(text):
                indent_len = len(text) - len(stripped)
                indent = text[:indent_len]
                new_text = f"{indent}{_SERIAL_COMMENT_MARK}{stripped}"
                cursor.setPosition(block.position())
                cursor.movePosition(
                    QTextCursor.MoveOperation.EndOfBlock,
                    QTextCursor.MoveMode.KeepAnchor,
                )
                cursor.insertText(new_text)
            block = block.next()

    def _uncomment_serial_in_document(self, doc):
        cursor = QTextCursor(doc)
        block = doc.firstBlock()
        while block.isValid():
            text = block.text()
            m = _SERIAL_COMMENTED_RE.match(text)
            if m:
                new_text = f"{m.group(1)}{m.group(2)}"
                cursor.setPosition(block.position())
                cursor.movePosition(
                    QTextCursor.MoveOperation.EndOfBlock,
                    QTextCursor.MoveMode.KeepAnchor,
                )
                cursor.insertText(new_text)
            block = block.next()

    # ── Public API ──────────────────────────────────────────

    def get_prompt(self) -> str:
        return self._prompt_field.toPlainText().strip()

    def set_prompt(self, prompt: str) -> None:
        """Pre-fills the AI Prompt field with `prompt` and gives it focus.
        Used by the "Open in Studio" button from the chat."""
        self._prompt_field.setPlainText(prompt)
        self._prompt_field.setFocus()
        cursor = self._prompt_field.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._prompt_field.setTextCursor(cursor)

    def copy_code_to_clipboard(self) -> None:
        """Copies the whole editor code (Édition menu > Copier le code)."""
        QApplication.clipboard().setText(self._editor.toPlainText())

    def clear_prompt(self) -> None:
        """Clears the AI prompt field (Édition menu > Effacer le prompt).
        clear() would wipe the undo stack — go through the cursor so the
        action stays undoable via Ctrl+Z."""
        cursor = self._prompt_field.textCursor()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.removeSelectedText()
        cursor.endEditBlock()

    def set_code(self, code: str):
        """Replaces the editor content with ``code``.

        Code-loss safeguard: if the AI returns empty or text
        without `setup()`/`loop()`, we refuse the overwrite and leave the
        previous code intact (typical case: post-compile repair phase
        fails, the AI answers with a free-text explanation instead of a
        sketch). The replacement is atomic and undoable via Ctrl+Z —
        unlike setPlainText() which clears the undo stack.
        """
        if not code or not code.strip():
            print("[set_code] refus : code vide", flush=True)
            return
        if "setup(" not in code or "loop(" not in code:
            print("[set_code] refus : setup()/loop() manquants — code precedent conserve", flush=True)
            return

        # Undoable replacement: select-all + insertText in an EditBlock.
        cursor = self._editor.textCursor()
        cursor.beginEditBlock()
        try:
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.insertText(code)
        finally:
            cursor.endEditBlock()

        m = _re.search(r'Serial\.begin\s*\(\s*(\d+)\s*\)', code)
        if m:
            self._serial_monitor.suggest_baud(m.group(1))
            self._serial_monitor_beg.suggest_baud(m.group(1))

    def get_code(self) -> str:
        return self._editor.toPlainText()

    # ─── Project management (Phase 3) ──────────────────────────

    def _install_project_bar(self):
        """Adds the top bar: "+" New project button + dirty marker.

        The project name is shown in the window title (via the
        `project_title_changed` signal). Saving is done via Ctrl+S or
        the debounced auto-save (no more Save button in the bar)."""
        self._project_bar = QWidget()
        self._project_bar.setFixedHeight(52)
        row = QHBoxLayout(self._project_bar)
        row.setContentsMargins(24, 6, 24, 6)
        row.setSpacing(10)

        # "+" button: triggers the creation of a new project (studio reset
        # + inline name entry). Same shortcut as File > New project.
        # The text label is no longer shown next to it (the project name occupies
        # that place); the "+" + tooltip are enough as the action.
        self._btn_new_project = QPushButton()
        self._btn_new_project.setFixedSize(28, 28)
        self._btn_new_project.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_new_project.setFlat(True)
        self._btn_new_project.clicked.connect(self._begin_inline_new_project)
        row.addWidget(self._btn_new_project)

        # "Nouveau projet" label kept (referenced by apply_lang) but NOT
        # placed in the layout: the project name now takes that place.
        self._lbl_new_project = QLabel()
        self._lbl_new_project.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lbl_new_project.mousePressEvent = (
            lambda e: self._begin_inline_new_project()
            if e.button() == Qt.MouseButton.LeftButton else None
        )

        # Project name shown IN-CONTENT (Phase 3 §6, user decision): big
        # title (≈22px = 16pt). Double-click = rename (reuses the inline flow).
        self._lbl_project_name = QLabel()
        self._lbl_project_name.mouseDoubleClickEvent = (
            lambda e: self._begin_inline_rename()
            if e.button() == Qt.MouseButton.LeftButton else None
        )
        row.addWidget(self._lbl_project_name)

        # Inline edit field (new project / rename). Hidden by default;
        # revealed by `_begin_inline_rename` (which then hides the name label).
        self._name_edit = QLineEdit()
        self._name_edit.setMaxLength(80)
        self._name_edit.setFixedHeight(30)
        self._name_edit.setMinimumWidth(220)
        self._name_edit.setVisible(False)
        self._name_edit.returnPressed.connect(self._commit_inline_rename)
        self._name_edit.installEventFilter(self)
        row.addWidget(self._name_edit)

        # Board badge (env · model · port) — follows board_manager (Phase 3 §6).
        self._lbl_board_badge = QLabel()
        self._lbl_board_badge.setVisible(False)
        row.addWidget(self._lbl_board_badge)

        # "Unsaved" indicator.
        self._lbl_dirty = QLabel("•")
        self._lbl_dirty.setFixedWidth(10)
        self._lbl_dirty.setVisible(False)
        row.addWidget(self._lbl_dirty)

        row.addStretch()

        # Inserts the bar at the very top of the Studio (above the scroll)
        self.layout().insertWidget(0, self._project_bar)

        # The board badge follows the board state (connection / manual selection).
        board_manager.changed.connect(self._update_board_badge)
        board_manager.state_changed.connect(self._update_board_badge)

        # Dirty tracking
        self._editor.textChanged.connect(self._mark_dirty)
        self._editor.textChanged.connect(self._update_code_meta)
        # Le bouton « Voir le schéma » suit le CODE : il doit donc se
        # (dé)griser à la frappe, pas seulement aux moments où l'app
        # recalcule ses styles.
        self._editor.textChanged.connect(self._refresh_schema_buttons)
        # Resync features <-> editor content (handles undo/redo).
        self._editor.textChanged.connect(self._resync_features_from_editor)
        # #31 right-click « Assign to a feature » failsafe (both windows).
        self._editor.set_feature_provider(lambda: self._feature_menu_items("ia"))
        self._editor.assign_lines_to_feature.connect(
            lambda s, e, i: self._on_assign_lines(s, e, i, "ia"))
        self._stable_panel.editor.set_feature_provider(
            lambda: self._feature_menu_items("stable"))
        self._stable_panel.editor.assign_lines_to_feature.connect(
            lambda s, e, i: self._on_assign_lines(s, e, i, "stable"))
        self._prompt_field.textChanged.connect(self._mark_dirty)
        self._mode_selector.mode_changed.connect(self._mark_dirty)

        # Keyboard shortcut
        QShortcut(QKeySequence.StandardKey.Save, self, activated=self.save_project)
        # Ctrl+Z / Ctrl+Shift+Z: delegated to the focused widget (editor / prompt).
        QShortcut(QKeySequence.StandardKey.Undo, self, activated=self.undo)
        QShortcut(QKeySequence.StandardKey.Redo, self, activated=self.redo)

        theme_manager.changed.connect(self._apply_project_bar_theme)
        lang_manager.changed.connect(self._apply_project_bar_lang)
        self._apply_project_bar_theme(theme_manager.current)
        self._apply_project_bar_lang(lang_manager.current)
        self._update_project_header()

    def _apply_project_bar_theme(self, c: ColorScheme):
        p = self._project_bar.palette()
        p.setColor(QPalette.ColorRole.Window, QColor(c.sidebar_bg))
        self._project_bar.setPalette(p)
        self._project_bar.setAutoFillBackground(True)
        self._lbl_dirty.setStyleSheet(
            f"color: {c.accent}; font-size: 14pt; font-weight: 700;"
        )
        # "+" button (new project): circle with an accent border,
        # transparent background, fills with the accent tint on hover.
        self._btn_new_project.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1.5px solid {c.accent};
                border-radius: 14px;
            }}
            QPushButton:hover {{ background-color: {c.nav_hover_bg}; }}
        """)
        self._btn_new_project.setIcon(IC.make_icon(IC.PLUS, c.accent, 16))
        self._lbl_new_project.setStyleSheet(
            f"color: {c.text_primary}; font-size: 10pt; font-weight: 600;"
            "background: transparent; border: none;"
        )
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {c.main_bg};
                color: {c.text_primary};
                border: 1px solid {c.border};
                border-radius: 6px;
                padding: 2px 8px;
                font-size: 11pt; font-weight: 600;
            }}
            QLineEdit:focus {{ border: 1px solid {c.accent}; }}
        """)
        # Project name: big title (≈22px spec = 16pt), medium bold.
        self._lbl_project_name.setStyleSheet(
            f"color: {c.text_primary}; font-size: 16pt; font-weight: 600;"
            " background: transparent; border: none;"
        )
        # Board badge: discreet pill (secondary text + surface + border).
        self._lbl_board_badge.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 9pt;"
            f" background: {c.surface}; border: 1px solid {c.border};"
            f" border-radius: 4px; padding: 2px 8px;"
        )
        self._update_project_header()

    def _apply_project_bar_lang(self, s: Strings):
        self._btn_new_project.setToolTip(s.mn_new_project)
        self._lbl_new_project.setText(s.mn_new_project)
        self._update_project_header()

    def _update_project_header(self):
        # Project name shown IN-CONTENT (Phase 3 §6) + board badge + dirty,
        # AND pushed in parallel into the window title (main_window).
        s = lang_manager.current
        if self._current_project is not None:
            self._lbl_project_name.setText(self._current_project.name)
        else:
            self._lbl_project_name.setText(s.studio_untitled)
        # Ce titre se RENOMME au double-clic, et ne le disait nulle part : ni
        # curseur, ni infobulle, ni effet de survol — alors que c'est la seule
        # porte de renommage depuis le Studio. La phrase existait déjà,
        # traduite dans les 4 langues, branchée sur rien. Posé ici (et non à la
        # construction) pour suivre le changement de langue, puisque
        # `_update_project_header` est rappelé par `apply_lang`.
        self._lbl_project_name.setToolTip(s.studio_function_rename_tip)
        self._lbl_project_name.setCursor(Qt.CursorShape.PointingHandCursor)
        # Name visible except during inline editing (mutually exclusive).
        self._lbl_project_name.setVisible(not self._name_edit.isVisible())
        self._lbl_dirty.setVisible(self._dirty and self._current_project is not None)
        self._update_board_badge()
        # Empty string = no project => title "PromptuinoUI".
        name = self._current_project.name if self._current_project is not None else ""
        self.project_title_changed.emit(name)
        self._update_code_meta()   # the .ino filename depends on the project

    def _update_board_badge(self, *_):
        """Project bar board badge: "env · model · port" when a
        board is connected/selected, hidden otherwise (Phase 3 §6)."""
        bm = board_manager
        if (bm.state in (BoardState.CONNECTED, BoardState.MANUAL)
                and bm.env and bm.model):
            env_label = BOARDS.get(bm.env, {}).get("label", bm.env)
            parts = [env_label, bm.model]
            if bm.port:
                parts.append(bm.port)
            self._lbl_board_badge.setText(" · ".join(parts))
            self._lbl_board_badge.setVisible(True)
        else:
            self._lbl_board_badge.setVisible(False)

    def _ensure_stable_template(self):
        """Place le squelette éditeur dans la fenêtre stable si elle est vide
        ou ne contient qu'un template/scaffold (état « avant génération », le
        même skelette que l'éditeur IA). Ne marque PAS le projet dirty
        (signaux bloqués) ; le bouton « Voir le schéma » stable est rafraîchi
        par l'appelant (_on_mode_changed / load_project appellent ensuite
        _refresh_action_button_styles)."""
        st = self._stable_panel.editor.toPlainText()
        if st.strip() and not self._is_template_or_scaffolded(st):
            return
        self._stable_panel.editor.blockSignals(True)
        try:
            self._stable_panel.editor.setPlainText(lang_manager.editor_template())
        finally:
            self._stable_panel.editor.blockSignals(False)

    def _on_stable_edited(self):
        """Édition de la fenêtre stable -> projet dirty + MAJ des boutons + (sur
        undo/redo) restauration de l'état stable indexé, sinon capture #31."""
        # Le bouton schéma stable suit le contenu même pendant un load (activé
        # dès qu'il y a du code restauré) ; le dirty, lui, est supprimé au load.
        self._refresh_action_button_styles()
        self._update_code_meta()   # rafraîchit AUSSI le compteur de lignes stable
        if getattr(self, "_loading", False) or self._suppress_stable_resync:
            return
        entry = self._stable_feature_index.get(self._stable_panel.editor.toPlainText())
        if entry is not None:
            # Ctrl+Z / Ctrl+Y vers un état indexé (transfert / suppression) ->
            # on restaure les fonctionnalités stable + la carte de surlignage.
            feats, line_map = entry
            self._stable_features = [copy.deepcopy(f) for f in feats]
            self._stable_baseline = self._stable_panel.editor.toPlainText()
            self._stable_panel.editor.set_line_owners(line_map)
            self._stable_panel.set_features(
                self._stable_features, self._stable_panel.is_busy())
            self._mark_dirty()
            return
        self._mark_dirty()
        # Hand edit on stable -> debounced #31 capture (standalone -> `manual`).
        self._schedule_manual_capture("stable")

    def _mark_dirty(self, *args):
        if self._loading:
            return
        if not self._dirty:
            self._dirty = True
            self._update_project_header()
        # Restarts the auto-save debounce on each keystroke; we do not save
        # as long as the user keeps typing.
        if self._current_project is not None:
            self._auto_save_timer.start()

    def _set_dirty(self, dirty: bool):
        self._dirty = dirty
        self._update_project_header()
        if not dirty:
            self._auto_save_timer.stop()

    def _auto_save(self):
        """Silent save triggered by the debounce."""
        if self._dirty and self._current_project is not None:
            self.save_project()

    def _emit_chat_context(self) -> None:
        """Pushes the current project context to the chat panel."""
        project = self._current_project
        if project is None:
            # No project: push an empty context to clear the one
            # of the previous project in the chat panel.
            self.chat_context_changed.emit({
                "code": "",
                "wiring_summary": [],
                "original_prompt": "",
                "user_material": "",
                "context_name": "",
                "last_compile_error": "",
            })
            return
        code = self._editor.toPlainText() if hasattr(self, "_editor") else (project.code or "")
        # Shared context file: pushed as-is to the chat (name for
        # the chip + content for the system prompt) so the document is
        # visible and usable on BOTH sides (prompt + chat).
        ctx_name, ctx_material = self._context_material()
        self.chat_context_changed.emit({
            "code": code,
            "wiring_summary": [],   # V2: humanize from the netlist
            "original_prompt": project.last_prompt or "",
            "user_material": ctx_material,
            "context_name": ctx_name,
            "last_compile_error": "",
        })

    def load_project(self, project: Project):
        """Loads a project into the Studio (code + prompt + mode)."""
        if self._dirty and self._current_project is not None:
            action = self._confirm_unsaved()
            if action == "cancel":
                return
            if action == "save":
                self.save_project()

        # Bannière d'info du projet PRÉCÉDENT : elle ne parle que de la
        # dernière génération, donc elle ment dès qu'on change de projet.
        # Répare les DEUX messages qu'elle porte : celui du registre (défaut
        # antérieur, atténué parce qu'il nomme un composant) et celui de la
        # ressemblance, entièrement relatif au dernier prompt — « Aucune
        # référence reconnue dans ta demande » dans un projet où l'on n'a rien
        # demandé (revue finale #61, 2026-08-21). Placé APRÈS le contrôle de
        # sauvegarde — seul endroit d'où `load_project` renonce encore — et
        # avant tout le reste.
        self._registry_banner.setVisible(False)
        # Même raison, pour les refus de l'offre « rendre non bloquante »
        # (#89) : ils sont indexés par ID de fonctionnalité, et les ids sont
        # PAR PROJET (`fn-1`, `fn-2`…). Sans cette remise à zéro, refuser
        # dans un projet faisait taire l'offre dans le suivant — la
        # fonctionnalité bloquante du nouveau projet portant le même id
        # (relevé en QA AF1, 2026-08-31).
        self._blocking_offer_declined = set()

        code   = project_manager.load_code(project)
        prompt = project.last_prompt or ""
        mode   = project.mode if project.mode in ("beginner", "intermediate", "advanced") else "beginner"

        # Disconnect the serial monitor of the PREVIOUS project: otherwise the port stays
        # open and keeps streaming into the new project's journal.
        self._serial_monitor.close_port()
        self._serial_monitor_beg.close_port()

        self._loading = True
        try:
            self._current_project = project
            if self._mode_selector._active != mode:
                self._mode_selector._active = mode
                self._mode_selector.apply_theme(theme_manager.current)
                self._on_mode_changed(mode)
            # Inject code + prompt (overwrites the possibly placed template).
            self._editor.setPlainText(code)
            self._stable_panel.editor.setPlainText(
                getattr(project, "stable_code", "") or "")
            # Projet sans code stable (nouveau / legacy) -> squelette « avant
            # génération » dans la fenêtre stable (comme l'éditeur IA).
            self._ensure_stable_template()
            self._stable_features = list(getattr(project, "stable_features", []))
            self._stable_baseline = self._stable_panel.editor.toPlainText()
            self._stable_panel.clear_selection()
            self._refresh_stable_features()   # dropdown + attribution stable
            self._prompt_field.setPlainText(prompt)
            verbosity = max(0, min(3, int(getattr(project, "comment_verbosity", 2))))
            self._comments_slider.setValue(verbosity)
            self._refresh_comments_value_label()
            # The checkbox will reflect the saved state; we do NOT re-mute the code
            # on opening: it was already saved in the intended state.
            self._chk_serial_monitor.setChecked(bool(getattr(project, "serial_monitor", True)))
            # Loads the features of the new pipeline.
            self._features = list(project.features)
            self._code_baseline = code
            # Reset du surlignage inter-projets (#29 revue finale) : les ids
            # f1/f2 étant génériques, la sélection de puces (et donc la teinte
            # posée sur l'éditeur) survivrait sinon au changement de projet ->
            # teinte de l'ANCIEN projet posée sur le nouveau.
            self._code_panel.clear_selection()
            # Carte lignes->fonctionnalité (#29) : recalcul, rien n'est persisté.
            # Posée AVANT _index_features (qui lit line_owners()) : sinon
            # l'état de base serait indexé avec une carte toute-None et un
            # Ctrl+Z y revenant perdrait le surlignage (#29 revue finale).
            from .code_format import reindent_code
            code_now = self.get_code()
            asm_code, asm_map = assemble_with_map(self._features)
            if reindent_code(asm_code) == code_now or asm_code == code_now:
                self._editor.set_line_owners(asm_map)
            elif len(self._features) == 1 and not is_dirty(code_now, reindent_code(asm_code)):
                # Comparaison à l'ASSEMBLAGE (pas à `self._code_baseline`, qui
                # vient d'être posé au même contenu deux lignes plus haut ->
                # `is_dirty(code_now, self._code_baseline)` serait toujours
                # False, rendant la garde morte, #29 revue finale).
                self._editor.set_line_owners(single_feature_map(code_now, self._features[0].id))
            else:
                lines = code_now.split("\n")
                base = [None] * len(lines)
                self._editor.set_line_owners(
                    match_contributions(lines, self._features, base))
            # New undo/redo index for this project (the loaded state is its base).
            self._feature_index = {}
            self._stable_feature_index = {}
            self._index_features(self.get_code(), self._features)
            # An empty project is saved with the setup()/loop() skeleton of the
            # template -> `code.strip()` would be true. We exclude the template (like
            # on mode change) so as not to turn on `_has_generated` wrongly
            # (otherwise « Code prêt » / active schema button on an empty project).
            self._has_generated = bool(self._features) or (
                bool(code.strip()) and not self._is_template_or_scaffolded(code)
            )
            self._last_prompt = prompt
            # "Voir le schema" button beginner mode: re-enable on opening
            # the project if generated code is present.
            self._btn_view_schema.setEnabled(self._has_generated)
            self._refresh_action_button_styles()
            # Restores the persisted wiring resolutions. Key stored
            # as the string "fn_id|pin_net" -> turned back into a tuple.
            self._wiring_resolutions = {}
            for k_str, v in (project.wiring_resolutions or {}).items():
                if "|" in k_str:
                    fn_id, pin_net = k_str.split("|", 1)
                    self._wiring_resolutions[(fn_id, pin_net)] = v
            # Restores the Level 3 implicit actions. Key
            # "fn_id|pin_net|action_id" -> tuple. Value preserved as
            # is (bool for toggles, str for selectors).
            self._implicit_actions = {}
            for k_str, v in (project.wiring_implicit_actions or {}).items():
                parts = k_str.split("|", 2)
                if len(parts) == 3 and isinstance(v, (bool, str, int, float)):
                    self._implicit_actions[tuple(parts)] = v
            self._update_context_badge()
        finally:
            self._loading = False
        self._set_dirty(False)
        # Journals: start fresh on opening a project — the beginner
        # AND the int/advanced (otherwise the previous project's journal persists). We
        # also reset the repair history (no stale
        # « voir les corrections » button).
        self._beg_output_area.clear()
        self._output_area.clear()
        self._last_repair_steps = []
        # Signals the program state (« Code prêt : … » if code is present)
        # in the current mode's journal — all modes (mode-aware helper).
        self._beg_mark_program_ready()
        self._refresh_feature_chips()
        session.last_project_path = str(project.path)
        self.project_loaded.emit(project)
        self._emit_chat_context()
    # ── Auto creation / inline rename ──────────────────────

    def _infer_project_type(self) -> ProjectType:
        """Infers the project type from the current board, Arduino by default."""
        env_to_type = {
            "arduino": ProjectType.ARDUINO,
            "esp32":   ProjectType.ESP32,
        }
        return env_to_type.get(board_manager.env, ProjectType.ARDUINO)

    def _auto_create_untitled(self) -> bool:
        """Creates a unique 'Sans-titre' project if no project is loaded.

        Called at the start of a generation to materialize the current
        project. On failure, the error is propagated via _show_gen_error.
        """
        if self._current_project is not None:
            return True
        ptype = self._infer_project_type()
        base_dir = type_dir(ptype)
        base_dir.mkdir(parents=True, exist_ok=True)
        name = project_manager.unique_name("Sans-titre", base_dir)
        try:
            project = project_manager.create(
                name, ptype, initial_code=self.get_code()
            )
        except Exception as e:
            self._show_gen_error(str(e))
            return False
        self._current_project = project
        session.last_project_path = str(project.path)
        self._update_project_header()
        self.project_created.emit(project)
        return True

    def _begin_inline_new_project(self) -> None:
        """Creates a new project: resets the Studio and opens the inline entry.

        If a project is loaded and there are unsaved changes,
        offers save / ignore / cancel. Otherwise, resets the studio to
        its initial state (editor template, empty prompt, empty functions) and
        reveals the edit field so the user types the name directly.
        """
        if self._dirty and self._current_project is not None:
            action = self._confirm_unsaved()
            if action == "cancel":
                return
            if action == "save":
                self.save_project()
                # Save As cancelled => we abandon the creation rather than
                # silently losing the edits.
                if self._dirty:
                    return

        # Reset of the project state: mimics on_project_deleted + reset of the
        # edit fields (editor + prompt) to start from a clean template.
        self._current_project = None
        self._auto_save_timer.stop()
        # Reset of the wiring resolutions + Level 3 implicit actions:
        # otherwise the previous project's choices stay in memory and
        # apply silently to the new project (short-circuit
        # the ambiguity modal, bias the gears, etc.).
        self._wiring_resolutions = {}
        self._implicit_actions = {}
        # Même raison pour les refus de l'offre « rendre non bloquante »
        # (#89) : indexés par ID de fonctionnalité, et les ids sont PAR
        # PROJET — la fonctionnalité bloquante du nouveau projet porte le
        # même `fn-2`, donc un refus précédent la faisait taire (relevé en
        # QA AF1, 2026-08-31 ; c'est ce chemin-ci que la manip empruntait,
        # pas `load_project`).
        self._blocking_offer_declined = set()
        self._features = []
        self._stable_features = []
        self._code_baseline = ""
        self._stable_baseline = ""
        self._feature_index = {}
        self._stable_feature_index = {}

        self._loading = True
        try:
            self._editor.setPlainText(lang_manager.editor_template())
            # Efface le code stable du projet précédent (re-templaté plus bas).
            self._stable_panel.editor.setPlainText("")
            self._prompt_field.setPlainText("")
            self._comments_slider.setValue(2)  # Standard by default
            self._refresh_comments_value_label()
            self._chk_serial_monitor.setChecked(True)  # checked by default
        finally:
            self._loading = False
        # If we are in advanced mode with the checkbox checked, we inject Serial.begin
        # into the freshly placed template — this way the 1st generation will not
        # carry it (it belongs to the scaffolding).
        if self._current_mode == "advanced" and self._chk_serial_monitor.isChecked():
            self._apply_serial_monitor_state(True, mark_dirty=False)

        # Remise à zéro des DEUX fenêtres de fonctionnalités : sinon le dropdown
        # + le surlignage gardent les fonctionnalités du projet précédent, et le
        # code stable de l'ancien projet subsiste (cf. _features/_stable_features
        # remis à [] ci-dessus).
        self._ensure_stable_template()
        self._update_code_meta()          # compteur « N lignes » stable après re-template
        self._stable_baseline = self._stable_panel.editor.toPlainText()
        self._code_panel.clear_selection()
        self._refresh_feature_chips()
        self._stable_panel.clear_selection()
        self._refresh_stable_features()

        self._has_generated = False
        self._last_prompt = ""
        self._refresh_action_button_styles()
        # Resets the context badge to "empty" mode: without this reset, it keeps
        # the filename attached to the previous project, and the × cannot
        # delete anything (the current project is None).
        self._update_context_badge()
        self._set_dirty(False)
        session.last_project_path = ""
        self._update_project_header()
        # Notifies the chat that the current project has changed (None here).
        self.project_loaded.emit(None)
        self._emit_chat_context()

        # Chains onto the inline entry: the field is pre-filled with
        # 'Sans-titre' and selected so the user types directly.
        self._begin_inline_rename()

    def _begin_inline_rename(self) -> None:
        """Shows the inline edit field pre-filled with the current name.

        If no project is materialized, pre-fills with 'Sans-titre': the
        validation will create the project with the entered name. If the user
        validates without changing, nothing is saved."""
        self._name_edit.setVisible(True)
        self._lbl_project_name.setVisible(False)   # name <-> editing exclusive
        default_name = self._current_project.name if self._current_project else "Sans-titre"
        self._name_edit.setText(default_name)
        self._name_edit.selectAll()
        self._name_edit.setFocus(Qt.FocusReason.MouseFocusReason)

    def _cancel_inline_rename(self) -> None:
        """Restores the label display without renaming."""
        self._name_edit.setVisible(False)
        self._update_project_header()

    def _commit_inline_rename(self) -> None:
        """Validates the entered name.

        - Existing project: renames folder + .ino.
        - No project: materializes the project with the entered name (it is
          the other way to trigger saving, in addition to
          generation). If the name is empty/identical to the pre-fill, we cancel.
        """
        name = self._name_edit.text().strip()
        s = lang_manager.current

        # Case 1: no project => on-the-fly creation with the chosen name.
        if self._current_project is None:
            # Empty name: we cancel. Otherwise we create, including if the user
            # left the "Sans-titre" pre-fill (collision resolved as
            # "Sans-titre (1)", "Sans-titre (2)"... by unique_name).
            if not name:
                self._cancel_inline_rename()
                return
            if not is_name_valid(name):
                QToolTip.showText(
                    self._name_edit.mapToGlobal(self._name_edit.rect().bottomLeft()),
                    s.projects_invalid_name, self._name_edit,
                )
                return
            ptype = self._infer_project_type()
            base_dir = type_dir(ptype)
            base_dir.mkdir(parents=True, exist_ok=True)
            # Collision: suffix (1), (2)… automatically.
            name = project_manager.unique_name(name, base_dir)
            try:
                project = project_manager.create(
                    name, ptype, initial_code=self.get_code()
                )
            except Exception as e:
                QToolTip.showText(
                    self._name_edit.mapToGlobal(self._name_edit.rect().bottomLeft()),
                    str(e), self._name_edit,
                )
                return
            self._current_project = project
            self._name_edit.clear()
            self._name_edit.setVisible(False)
            session.last_project_path = str(project.path)
            self.project_created.emit(project)
            # Full save of the current metadata (prompt, mode, etc.).
            self.save_project()
            self._update_project_header()
            # Notifies the chat of the new current project (empty history
            # for a freshly created project).
            self.project_loaded.emit(project)
            self._emit_chat_context()
            return

        # Case 2: existing project => rename of the folder + .ino.
        if not name or name == self._current_project.name:
            self._cancel_inline_rename()
            return
        if not is_name_valid(name):
            QToolTip.showText(
                self._name_edit.mapToGlobal(self._name_edit.rect().bottomLeft()),
                s.projects_invalid_name, self._name_edit,
            )
            return
        # Collision: suffix (1), (2)… automatically. exclude=itself
        # to allow re-typing an identical name without a false conflict.
        name = project_manager.unique_name(
            name, self._current_project.path.parent,
            exclude=self._current_project.path,
        )
        old_path = str(self._current_project.path)
        try:
            project = project_manager.rename(self._current_project, name)
        except Exception as e:
            QToolTip.showText(
                self._name_edit.mapToGlobal(self._name_edit.rect().bottomLeft()),
                str(e), self._name_edit,
            )
            return
        self._current_project = project
        self._name_edit.clear()
        self._name_edit.setVisible(False)
        self._update_project_header()
        session.last_project_path = str(project.path)
        # Immediately persists the new state (code/prompt/meta) and notifies.
        self.save_project()
        self.project_renamed.emit(old_path, project)

    def _refresh_transfer_hover_from_cursor(self):
        """Re-evaluate the chevron hover from the ACTUAL cursor position. Used
        after a modal (transfer popup / overwrite confirm) closes: the modal
        stole the mouse before the chevrons got their Leave, so they'd stay
        green until hovered again (user 2026-07-08)."""
        from PyQt6.QtGui import QCursor
        blk = getattr(self, "_transfer_block", None)
        if blk is None:
            return
        inside = blk.rect().contains(blk.mapFromGlobal(QCursor.pos()))
        self._set_transfer_hover(inside)

    def _set_transfer_hover(self, hover: bool):
        """Chevron block styling: WHITE at rest, phosphor green when hovered
        — collectively (both chevrons change together, cf. eventFilter)."""
        c = theme_manager.current
        color = c.signal_ok if hover else c.text_primary
        self._transfer_block.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {color};
                font-size: 22pt;
                font-weight: bold;
                padding: 0 6px;
            }}
        """)

    def _reposition_transfer_block(self):
        """Centers the chevron block on the vertical band of the CODE
        editors (union of the IA and stable editors), NOT on the full column
        height — the compile/schema buttons below must not weigh in."""
        cont = self._transfer_col_w
        blk = self._transfer_block
        blk.adjustSize()
        tops: list[int] = []
        bottoms: list[int] = []
        for ed in (self._editor, self._stable_panel.editor):
            top = cont.mapFromGlobal(ed.mapToGlobal(QPoint(0, 0))).y()
            tops.append(top)
            bottoms.append(top + ed.height())
        band_top, band_bottom = min(tops), max(bottoms)
        y = band_top + (band_bottom - band_top - blk.height()) // 2
        blk.move(max(0, (cont.width() - blk.width()) // 2), max(0, y))

    def eventFilter(self, obj, event) -> bool:
        # Central chevron block: re-centered on the editors band whenever the
        # full-height container is laid out (mode switch, window resize,
        # console toggle... all end up resizing it).
        if obj is getattr(self, "_transfer_col_w", None) \
                and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            # Deferred: the editors' geometry is not settled yet during the
            # container's own Resize (single layout pass).
            QTimer.singleShot(0, self._reposition_transfer_block)
            return False
        # Collective hover of the chevron block: entering the block OR one of
        # its buttons greens BOTH chevrons; a Leave whose cursor is still
        # inside the block (moving block <-> button) is ignored.
        if obj in (getattr(self, "_transfer_block", None),
                   getattr(self, "_btn_transfer", None),
                   getattr(self, "_btn_transfer_back", None)):
            if event.type() == QEvent.Type.Enter:
                self._set_transfer_hover(True)
            elif event.type() == QEvent.Type.Leave:
                from PyQt6.QtGui import QCursor
                blk = self._transfer_block
                inside = blk.rect().contains(blk.mapFromGlobal(QCursor.pos()))
                self._set_transfer_hover(inside)
            return False
        # (Le repositionnement des overlays de l'éditeur au resize — carte
        #  commentaires + voile busy — est géré par le CodePanel, Prompt 3.)
        # Ne reste ici que le filtre du champ de renommage inline.
        edit = getattr(self, "_name_edit", None)
        if edit is not None and obj is edit:
            if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                self._cancel_inline_rename()
                return True
            if event.type() == QEvent.Type.FocusOut:
                # Blur: if the user typed something, we attempt the
                # rename; otherwise we cancel silently.
                if edit.text().strip():
                    self._commit_inline_rename()
                else:
                    self._cancel_inline_rename()
                return False
        return super().eventFilter(obj, event)

    def save_project(self):
        if self._current_project is None:
            # Before generation, nothing to persist: the project is materialized
            # by _auto_create_untitled() at the start of the generation.
            return
        # Persistence of the comment verbosity level (advanced mode).
        self._current_project.comment_verbosity = int(self._comments_slider.value())
        # Persistence of the "Serial Monitor" state (advanced mode).
        self._current_project.serial_monitor = bool(self._chk_serial_monitor.isChecked())
        try:
            # Serializes the tuple keys (fn_id, pin_net) to the string "fn_id|pin_net"
            # for JSON persistence.
            wiring_res_serialized = {
                f"{k[0]}|{k[1]}": v
                for k, v in self._wiring_resolutions.items()
            }
            implicit_actions_serialized = {
                f"{k[0]}|{k[1]}|{k[2]}": v
                for k, v in self._implicit_actions.items()
            }
            project_manager.save(
                self._current_project,
                code=self.get_code(),
                mode=self._current_mode,
                board_env=board_manager.env or "",
                board_model=board_manager.model or "",
                last_prompt=self.get_prompt(),
                ai_backend=ai_config.backend_id,
                features=self._features,
                wiring_resolutions=wiring_res_serialized,
                wiring_implicit_actions=implicit_actions_serialized,
                stable_code=self._stable_panel.editor.toPlainText(),
                stable_features=self._stable_features,
            )
        except Exception as e:
            QMessageBox.warning(self, lang_manager.current.studio_save, str(e))
            return
        self._set_dirty(False)

    # ── External syncs (Phase 4) ──────────────────────────

    def has_unsaved_changes(self) -> bool:
        return self._dirty

    def can_discard_changes(self) -> bool:
        """
        Called by MainWindow before a destructive action (window close, etc.).
        Returns True if we can continue, False if the user cancelled.
        """
        # With no current project, there is nothing to lose (no generation has
        # been launched, so nothing is persisted). We do not bother the user.
        if not self._dirty or self._current_project is None:
            return True
        action = self._confirm_unsaved()
        if action == "cancel":
            return False
        if action == "save":
            self.save_project()
            return not self._dirty   # False if Save As cancelled
        return True   # discard

    def on_project_deleted(self, project: Project):
        """Called when a project is deleted from the Projects tab."""
        if self._current_project is None:
            return
        if str(self._current_project.path) == str(project.path):
            self._current_project = None
            self._dirty = False
            self._auto_save_timer.stop()
            # Reset of the wiring resolutions + Level 3 implicit actions.
            # Otherwise they stay in memory and would be applied to the
            # next project (even with a different name, even with different code).
            self._wiring_resolutions = {}
            self._implicit_actions = {}
            self._features = []
            self._stable_features = []
            self._code_baseline = ""
            self._stable_baseline = ""
            self._feature_index = {}
            self._stable_feature_index = {}
            # The stable window is NOT replaced by a later generation (unlike the
            # IA editor) -> clear its MODEL and its EDITOR code here, else
            # save_project() on the NEXT project persists the DELETED project's
            # stable code/features (leak + ghost dropdown). Mirror of « New
            # project » (bug review 2026-07-06 #1).
            self._loading = True
            try:
                self._stable_panel.editor.setPlainText("")
            finally:
                self._loading = False
            self._ensure_stable_template()
            self._stable_baseline = self._stable_panel.editor.toPlainText()
            self._stable_panel.clear_selection()
            self._refresh_stable_features()
            self._code_panel.clear_selection()
            self._refresh_feature_chips()     # _features=[] -> pas de dropdown fantôme
            self._update_code_meta()          # compteurs de lignes des 2 fenêtres
            self._update_project_header()
            if session.last_project_path == str(project.path):
                session.last_project_path = ""
            # Notifies the chat that the current project has disappeared.
            self.project_loaded.emit(None)
            self._emit_chat_context()

    def on_project_renamed(self, old_path: str, project: Project):
        """Called when a project is renamed from the Projects tab."""
        if session.last_project_path == old_path:
            session.last_project_path = str(project.path)
        if self._current_project is None:
            return
        if str(self._current_project.path) == old_path:
            self._current_project = project
            self._update_project_header()

    def _confirm_unsaved(self) -> str:
        """Returns 'save', 'discard' or 'cancel'."""
        s = lang_manager.current
        name = self._current_project.name if self._current_project else ""
        box = QMessageBox(self)
        box.setWindowTitle(s.studio_unsaved_title)
        box.setText(s.studio_unsaved_msg.format(name=name))
        btn_save    = box.addButton(s.studio_unsaved_save,    QMessageBox.ButtonRole.AcceptRole)
        btn_discard = box.addButton(s.studio_unsaved_discard, QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel  = box.addButton(s.studio_unsaved_cancel,  QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_save)
        box.exec()
        clicked = box.clickedButton()
        if clicked is btn_save:
            return "save"
        if clicked is btn_discard:
            return "discard"
        return "cancel"
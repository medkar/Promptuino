"""#61 -- la bannière avoue une lib choisie par ressemblance.

Run: python scripts/test_resemblance_notice.py
"""
from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ui.rag as rag
from ui.info_banner import numbered, should_disclose_resemblance

# Importer ui.studio_view charge PyQt6 : il faut une QApplication vivante,
# meme si aucun widget n'est construit ici (motif de test_chip_swap_regen.py,
# test_module_alias_lookup.py).
from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)


# ── Mise en forme : liste numérotée ───────────────────────────────────────────

def test_no_message_renders_nothing():
    assert numbered([]) == ""
    assert numbered(["", ""]) == ""


def test_a_single_message_carries_no_number():
    """Numéroter un élément unique est du bruit : c'est le cas courant."""
    assert numbered(["Composant AS7341 : librairie trouvée."]) == \
        "Composant AS7341 : librairie trouvée."


def test_two_messages_are_numbered_and_separated():
    """Avant : `"<br>".join(...)` collait les messages. Le cas réel est un
    prompt qui nomme DEUX part-numbers inconnus."""
    out = numbered(["premier", "second"])
    assert out == "1. premier<br><br>2. second", out


def test_three_messages_keep_counting():
    out = numbered(["a", "b", "c"])
    assert out == "1. a<br><br>2. b<br><br>3. c", out


def test_empty_messages_are_dropped_before_numbering():
    """Un message vide ne doit pas consommer un numéro."""
    assert numbered(["a", "", "b"]) == "1. a<br><br>2. b"


# ── La règle d'affichage ──────────────────────────────────────────────────────

def test_nothing_to_disclose_when_nothing_was_guessed():
    assert not should_disclose_resemblance(
        by_resemblance=False, action="correct", from_scratch=False,
        has_targets=True)
    assert not should_disclose_resemblance(
        by_resemblance=False, action="add", from_scratch=False,
        has_targets=False)


def test_modify_is_silent_the_reference_is_in_the_code():
    """La remarque de l'utilisateur (2026-08-21) : « finalement affiche la
    température en °C au lieu de °F » après un premier prompt qui nommait la
    puce. Sur un Modifier le modèle reçoit le code actuel de la
    fonctionnalité -- la référence y est écrite, pas devinée."""
    assert not should_disclose_resemblance(
        by_resemblance=True, action="correct", from_scratch=False,
        has_targets=True)


def test_regenerate_from_scratch_speaks():
    """↻ repart du prompt SANS le code de la fonctionnalité : rien sur quoi
    s'appuyer, donc c'est bien une devinette."""
    assert should_disclose_resemblance(
        by_resemblance=True, action="correct", from_scratch=True,
        has_targets=True)


def test_correct_without_a_surviving_target_speaks():
    """`_correct_targets` peut être vide (id disparu) : le chemin retombe sur
    un ajout, qui ne fournit pas le code de la fonctionnalité ciblée."""
    assert should_disclose_resemblance(
        by_resemblance=True, action="correct", from_scratch=False,
        has_targets=False)


def test_add_speaks():
    """Le code existant est fourni en lecture seule, mais le prompt décrit un
    composant NEUF : c'est une devinette sur ce composant-là."""
    assert should_disclose_resemblance(
        by_resemblance=True, action="add", from_scratch=False,
        has_targets=False)


def test_full_regenerate_speaks():
    assert should_disclose_resemblance(
        by_resemblance=True, action="regenerate", from_scratch=False,
        has_targets=False)


def test_the_rule_never_looks_at_the_mode():
    """Garde fondatrice : le mode n'est qu'un affichage. Le chemin débutant
    parle parce que son ACTION régénère tout, pas parce qu'il est débutant."""
    src = (ROOT / "ui" / "info_banner.py").read_text(encoding="utf-8")
    assert "_current_mode" not in src, \
        "la règle d'affichage ne doit jamais dépendre du mode"


def test_correct_constant_has_not_drifted():
    """`info_banner` RECOPIE `CORRECT` au lieu de l'importer : `ui.generation`
    ré-exporte `gen_modal`, qui importe Qt, et ce module doit rester chargeable
    sans lui. La copie doit donc être surveillée."""
    from ui.info_banner import _CORRECT
    from ui.generation import CORRECT
    assert _CORRECT == CORRECT, (_CORRECT, CORRECT)


def test_info_banner_imports_no_qt():
    """Garde d'IMPORT, pas de texte.

    Écrite d'abord en sous-chaînes (« "PyQt6" not in src »), elle interdisait
    au commentaire du module de NOMMER ce qu'il évite — il ne pouvait plus
    expliquer pourquoi `CORRECT` est recopié sans faire rougir sa propre
    garde. On lit donc les nœuds d'import de l'AST : c'est l'import qui ferait
    rentrer Qt, pas le fait d'en parler.
    """
    import ast
    tree = ast.parse(
        (ROOT / "ui" / "info_banner.py").read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append("." * node.level + (node.module or ""))
    for name in imported:
        assert not name.startswith("PyQt6"), f"import Qt interdit : {name}"
        assert "generation" not in name, (
            f"importer ui.generation ferait rentrer Qt par gen_modal : {name}")


# ── La provenance des libs, rapportée par `rag` ───────────────────────────────
#
# `retrieve_libs` est remplacée par un bouchon : tout ce que ces tests
# vérifient est LEXICAL et STRUCTUREL (quelle branche a été prise), donc ils
# tournent sans l'encodeur ONNX et rendent un verdict déterministe.

_FAKE_LIB = {
    "id": "fake-lib",
    "name": "Fake Lib",
    "headers": ["Fake.h"],
    "example_code": "void setup() {}",
    "api_signatures": {},
    "_score": 0.9,
}


@contextlib.contextmanager
def _retrieval_returns(libs):
    """Remplace `rag.retrieve_libs` le temps d'un appel. Le stub accepte les
    memes parametres nommes que la vraie fonction (**kw : banned_ids de #85,
    et les suivants) — sinon l'appel echoue en silence dans le try/except de
    `_build_lib_context` et le test mesure un contexte vide, pas le defaut."""
    original = rag.retrieve_libs
    rag.retrieve_libs = lambda prompt, k=3, threshold=None, **kw: list(libs)
    try:
        yield
    finally:
        rag.retrieve_libs = original


def _report_for(prompt: str, libs, **kwargs):
    """(contexte, appels reçus par on_resemblance) pour un prompt."""
    calls: list[bool] = []
    with _retrieval_returns(libs):
        ctx = rag.build_lib_context(prompt, on_resemblance=calls.append,
                                    **kwargs)
    return ctx, calls


def test_a_described_prompt_reports_a_guess():
    ctx, calls = _report_for("lis la temperature ambiante", [_FAKE_LIB])
    assert ctx, "une lib a bien ete injectee"
    assert calls == [True], calls


def test_a_named_chip_reports_no_guess():
    """En-tete imperatif : l'utilisateur a nomme sa puce, rien n'est devine."""
    ctx, calls = _report_for("lis la temperature avec un dht22", [_FAKE_LIB])
    assert ctx, "une lib a bien ete injectee"
    assert calls == [False], calls


def test_forced_libs_report_no_guess():
    ctx, calls = _report_for("lis un capteur", [], forced_libs=[_FAKE_LIB])
    assert ctx
    assert calls == [False], calls


def test_the_i2c_scanner_is_not_a_guess():
    """FAUX POSITIF MESURÉ le 2026-08-21 : `scanner i2c` n'a pas de
    `forced_libs`, ne nomme aucune puce, et reçoit pourtant l'exemple `Wire`
    -- de façon DÉTERMINISTE. Il faisait 4 des 6 déclenchements de la bande
    « générique » du banc. La condition porte sur la PROVENANCE des libs,
    jamais sur le texte de l'en-tête."""
    ctx, calls = _report_for("fais un scanner i2c", [_FAKE_LIB])
    assert ctx, "l'exemple Wire est bien injecte"
    assert calls == [False], calls


def test_a_basic_component_reports_no_guess():
    """Rien n'est injecté -> rien à avouer, et surtout pas « nomme ta LED »."""
    ctx, calls = _report_for("fais clignoter une led", [_FAKE_LIB])
    assert ctx == "", ctx
    assert calls == [False], calls


def test_an_empty_retrieval_reports_no_guess():
    ctx, calls = _report_for("lis la temperature ambiante", [])
    assert ctx == "", ctx
    assert calls == [False], calls


def test_the_callback_fires_exactly_once_on_every_path():
    """La garde qui empêche une valeur périmée : un appelant lit le drapeau
    APRÈS l'appel, donc toute sortie doit l'avoir posé."""
    cases = [
        ("lis la temperature ambiante", [_FAKE_LIB], {}),
        ("lis la temperature avec un dht22", [_FAKE_LIB], {}),
        ("fais un scanner i2c", [_FAKE_LIB], {}),
        ("fais clignoter une led", [_FAKE_LIB], {}),
        ("lis la temperature ambiante", [], {}),
        ("lis un capteur", [], {"forced_libs": [_FAKE_LIB]}),
        ("lis un capteur", [], {"forced_libs": []}),
    ]
    for prompt, libs, kwargs in cases:
        _, calls = _report_for(prompt, libs, **kwargs)
        assert len(calls) == 1, (prompt, kwargs, calls)


def test_existing_callers_are_untouched():
    """`on_resemblance` est optionnel : ne pas le passer ne change RIEN au
    contexte produit — trois sites de production et six scripts de test
    appellent ces fonctions sans lui.

    Revue finale (Minor 2) : la version précédente n'assertait que « le
    contexte n'est pas vide ». Une mutation qui corrompait le contexte pour
    tous les appelants sans rappel passait donc au vert. On compare désormais
    les DEUX formes, sur plusieurs chemins — c'est l'égalité qui est la
    non-régression, pas la non-vacuité.
    """
    cases = [
        ("lis la temperature ambiante", [_FAKE_LIB], {}),
        ("lis la temperature avec un dht22", [_FAKE_LIB], {}),
        ("fais un scanner i2c", [_FAKE_LIB], {}),
        ("lis un capteur", [], {"forced_libs": [_FAKE_LIB]}),
    ]
    for prompt, libs, kwargs in cases:
        with _retrieval_returns(libs):
            without = rag.build_lib_context(prompt, **kwargs)
        with _retrieval_returns(libs):
            with_cb = rag.build_lib_context(prompt, on_resemblance=lambda _v: None,
                                            **kwargs)
        assert without == with_cb, (prompt, kwargs)
        assert without, ("contexte vide, le cas ne prouve rien", prompt)


def test_augment_user_prompt_forwards_the_report():
    calls: list[bool] = []
    with _retrieval_returns([_FAKE_LIB]):
        out = rag.augment_user_prompt(
            "INSTRUCTIONS\nlis la temperature ambiante",
            retrieval_prompt="lis la temperature ambiante",
            on_resemblance=calls.append)
    assert "Fake Lib" in out, out[:200]
    assert calls == [True], calls


# ── Le message et son branchement ─────────────────────────────────────────────

def test_the_message_exists_in_all_four_languages():
    from ui.i18n import TRANSLATIONS
    seen = {}
    for code, s in TRANSLATIONS.items():
        msg = getattr(s, "rag_guess_by_resemblance", "")
        assert msg, f"{code}: clé 'rag_guess_by_resemblance' manquante/vide"
        seen[code] = msg
    # Revue (Minor 5) : une clé absente en es/it retomberait souvent sur
    # l'anglais par copier-coller plutot que de rester vide -- la garde
    # ci-dessus ne l'aurait pas vu. Les 4 textes doivent etre distincts.
    assert len(set(seen.values())) == len(seen), \
        f"au moins une langue recopie une autre : {seen}"


def test_the_message_claims_neither_naming_nor_use():
    """Deux affirmations que l'app ne peut pas faire (spec 2026-08-21) :
    « aucun composant NOMMÉ » (prompt_names_a_chip ne connaît que le corpus --
    « Grove Moisture Sensor » EST un nom, simplement non reconnu), et « la
    bibliothèque a été UTILISÉE » (l'en-tête est hedgé, le modèle a le droit
    de l'ignorer). Le message dit à la place « composant RECONNU » et
    « PROPOSÉE » (jamais nommé, jamais utilisée) -- et ne nomme AUCUNE
    bibliothèque.

    ⚠️ Cette garde a PRIS DU POIDS le 2026-08-21 : le message disait d'abord
    « aucune référence reconnue », et l'utilisateur a demandé « composant »
    (« un débutant réfléchira en termes de composants »). Le mot « composant »
    étant désormais DANS le message, seul l'écart reconnu/nommé le sépare de
    l'affirmation interdite -- une reformulation distraite en « aucun composant
    nommé » suffirait à faire mentir l'app.

    Revue (Minor 3) : la version precedente n'assertait que l'absence de
    gabarits `{lib}`/`{part}` non formates, ce qu'aucun message statique ne
    contient jamais -- une mutation remplacant tout le texte par les deux
    affirmations interdites passait quand meme. On verifie ici directement
    l'absence des deux affirmations, dans les 4 langues -- fragile a une
    reformulation qui garderait le meme sens avec d'autres mots, mais c'est
    la seule maniere de tester ce que le nom et la docstring annoncent."""
    from ui.i18n import TRANSLATIONS
    # (aucun composant NOMME, la bibliotheque a ete UTILISEE) par langue.
    forbidden = {
        "fr": ("composant nommé", "a été utilisée"),
        "en": ("named component", "was used"),
        "es": ("componente nombrado", "fue utilizada"),
        "it": ("componente nominato", "è stata utilizzata"),
    }
    for code, s in TRANSLATIONS.items():
        msg = s.rag_guess_by_resemblance.lower()
        assert "{lib}" not in msg and "{part}" not in msg, \
            f"{code}: le message ne doit nommer aucune bibliotheque"
        for phrase in forbidden[code]:
            assert phrase not in msg, \
                f"{code}: affirmation interdite trouvee ({phrase!r}) : {msg}"


def test_the_studio_never_decides_the_banner_from_the_mode():
    """Garde fondatrice, même forme que
    `test_no_mode_test_survives_in_the_resolution_path` : le mode n'est qu'un
    affichage. Le corps de la méthode qui décide ne doit contenir AUCUNE
    occurrence de `_current_mode`, commentaires compris."""
    src = (ROOT / "ui" / "studio_view.py").read_text(encoding="utf-8")
    marker = "    def _maybe_resemblance_banner("
    assert marker in src, "la methode d'affichage est introuvable"
    start = src.index(marker)
    rest = src[start + len(marker):]
    end = rest.index("\n    def ")
    body = rest[:end]
    assert "_current_mode" not in body, \
        "la banniere ne doit jamais dependre du mode"


def test_no_mode_test_gates_the_calls_to_the_banner():
    """Le complément du test précédent, et la vraie serrure.

    Revue finale (Minor 3) : la garde ci-dessus ne scrute que le CORPS de
    `_maybe_resemblance_banner`. Une mutation qui enveloppait l'appel débutant
    dans `if self._current_mode != "beginner":` passait donc au vert — le mode
    aurait décidé de la bannière sans que rien ne rougisse.

    On regarde ici les lignes qui ENTOURENT chaque appel. La fenêtre est
    volontairement étroite (10 lignes avant) : `_continue_generation` lit
    légitimement `_current_mode` ailleurs dans la même méthode, pour choisir
    la console où écrire — ce n'est pas une décision de câblage.
    """
    lines = (ROOT / "ui" / "studio_view.py").read_text(
        encoding="utf-8").splitlines()
    calls = [i for i, l in enumerate(lines)
             if "self._maybe_resemblance_banner(" in l]
    assert len(calls) == 2, calls
    for i in calls:
        window = "\n".join(lines[max(0, i - 10):i + 1])
        # Le message ne recopie PAS la source : `studio_view.py` contient des
        # caractères hors cp1252 (« 2ᵉ »), et un `print` de l'échec plantait
        # alors le rapporteur du script sur une console Windows — un test dont
        # l'échec crashe l'affichage est pire qu'un test absent. Le numéro de
        # ligne suffit à retrouver l'endroit.
        assert "_current_mode" not in window, (
            f"un test de mode commande l'affichage de la banniere, "
            f"dans les 10 lignes avant la ligne {i + 1}")


def test_the_registry_banner_uses_the_numbered_renderer():
    """`"<br>".join(msgs)` collait les messages : deux part-numbers inconnus
    dans un même prompt produisaient un pavé illisible."""
    src = (ROOT / "ui" / "studio_view.py").read_text(encoding="utf-8")
    assert '"<br>".join(msgs)' not in src, \
        "la banniere registre doit passer par info_banner.numbered"
    assert "numbered(msgs)" in src


def test_the_three_assembly_sites_report_back():
    """Les trois appels à `augment_user_prompt` doivent passer le rappel :
    en oublier un rendrait la bannière muette sur une action entière."""
    src = (ROOT / "ui" / "studio_view.py").read_text(encoding="utf-8")
    n_calls = src.count("augment_user_prompt(")
    n_reports = src.count("on_resemblance=self._note_resemblance")
    assert n_calls == 3, f"{n_calls} appels a augment_user_prompt (attendu 3)"
    assert n_reports == 3, f"{n_reports} sites rapportent (attendu 3)"


# ── Comportement dans StudioView (revue, Important 2) ─────────────────────────
#
# Les tests ci-dessus sont STRUCTURELS (presence de la methode, absence de
# `_current_mode`, comptage de sous-chaines) : aucun n'observait qu'un
# `show_nudge` a reellement lieu. La revue a prouve, en supprimant les DEUX
# appels a `_maybe_resemblance_banner`, que la suite restait 28/28 -- d'ou ces
# tests de COMPORTEMENT, motif `StudioView.__new__` + attributs bouchons de
# `scripts/test_module_alias_lookup.py`.

class _FakeBanner:
    """Bouchon de `NudgeBanner` : suit uniquement ce que
    `_maybe_resemblance_banner` et le masquage du chemin débutant lui font."""

    def __init__(self, visible: bool = False, body=None):
        self.visible = visible
        self.body = body

    def show_nudge(self, body, action="", second=""):
        self.body = body
        self.visible = True

    def setVisible(self, value):
        self.visible = bool(value)


def _bare_studio_view():
    from ui import studio_view
    view = studio_view.StudioView.__new__(studio_view.StudioView)
    view._registry_banner = _FakeBanner()
    return view


def test_a_guessed_generation_shows_the_translated_message():
    """`_maybe_resemblance_banner` doit vraiment appeler `show_nudge`, avec
    exactement le message traduit -- un message seul n'est jamais numéroté
    (`numbered`, section ci-dessus)."""
    from ui import studio_view
    from ui.generation import ADD
    from ui.i18n import lang_manager
    view = _bare_studio_view()
    view._last_resemblance = True
    studio_view.StudioView._maybe_resemblance_banner(
        view, action=ADD, from_scratch=False, has_targets=False)
    assert view._registry_banner.visible
    assert view._registry_banner.body == \
        lang_manager.current.rag_guess_by_resemblance, view._registry_banner.body


def test_a_modify_shows_nothing():
    """Muette sur un Modifier : le modèle y reçoit le code existant."""
    from ui import studio_view
    from ui.generation import CORRECT
    view = _bare_studio_view()
    view._last_resemblance = True
    studio_view.StudioView._maybe_resemblance_banner(
        view, action=CORRECT, from_scratch=False, has_targets=True)
    assert view._registry_banner.body is None
    assert not view._registry_banner.visible


def test_nothing_guessed_shows_nothing_regardless_of_action():
    from ui import studio_view
    from ui.generation import REGENERATE
    view = _bare_studio_view()
    view._last_resemblance = False
    studio_view.StudioView._maybe_resemblance_banner(
        view, action=REGENERATE, from_scratch=False, has_targets=False)
    assert view._registry_banner.body is None
    assert not view._registry_banner.visible


def test_both_generation_paths_call_the_banner():
    """Complément structurel : `_maybe_resemblance_banner` peut fonctionner
    correctement (tests ci-dessus) alors que plus personne ne l'appelle -- la
    revue l'a prouvé en supprimant les deux appels, suite restée 28/28. Les
    deux méthodes de génération (int/avancé -- `_continue_generation` --  ET
    débutant -- `_continue_beginner_generation`) doivent donc l'appeler."""
    src = (ROOT / "ui" / "studio_view.py").read_text(encoding="utf-8")
    assert src.count("self._maybe_resemblance_banner(") == 2, \
        "les deux chemins de generation doivent appeler la banniere"


def test_the_banner_is_shown_only_after_the_backstage_cancel_check():
    """Minor 4 (revue) : affichée avant `_prompt_backstage`, la bannière
    restait à l'écran même quand l'utilisateur ANNULE -- rien n'est parti au
    modèle. L'appel doit suivre le `if validated is _BACKSTAGE_CANCELLED:
    ... return`, dans les DEUX chemins."""
    src = (ROOT / "ui" / "studio_view.py").read_text(encoding="utf-8")
    marker = "if validated is _BACKSTAGE_CANCELLED:"
    positions = [i for i in range(len(src))
                 if src.startswith(marker, i)]
    assert len(positions) == 2, positions
    for pos in positions:
        after = src[pos:pos + 600]
        cancel_return = after.index("return")
        banner_call = after.find("self._maybe_resemblance_banner(")
        assert banner_call != -1, \
            "aucun appel a la banniere apres ce controle d'annulation"
        assert banner_call > cancel_return, \
            "la banniere doit etre affichee APRES le controle d'annulation"


def test_the_beginner_path_hides_a_stale_banner_before_the_registry_results():
    """Preuve de l'Important 1 (revue) : une bannière laissée visible par la
    génération PRÉCÉDENTE (devinée) doit être masquée dès l'entrée de la
    suite débutant, AVANT `_apply_registry_results` -- sinon un prompt qui
    vient de NOMMER sa puce garderait à l'écran le message d'une devinette
    passée. `_apply_registry_results` est remplacée par une bombe : si le
    masquage avait lieu APRÈS (ou pas du tout), ce test ne le verrait pas,
    donc on vérifie aussi que la bombe a bien explosé -- sinon le test ne
    prouverait rien."""
    from ui import studio_view

    class _Boom(Exception):
        pass

    view = _bare_studio_view()
    view._registry_banner.visible = True
    view._registry_banner.body = "message perime d'une generation devinee"

    def _explode(*args, **kwargs):
        raise _Boom()
    view._apply_registry_results = _explode

    raised = False
    try:
        studio_view.StudioView._continue_beginner_generation(
            view, backend=None, fqbn="x", port="y", bare_prompt="p",
            forced=[], registry_results=["sentinelle"])
    except _Boom:
        raised = True
    assert raised, \
        "le test doit atteindre _apply_registry_results pour etre concluant"
    assert view._registry_banner.visible is False, \
        "la banniere perimee doit etre masquee AVANT _apply_registry_results"


def test_opening_another_project_hides_the_banner():
    """Revue finale (Important 1) : la bannière ne parle que de la DERNIÈRE
    génération. Elle survivait à un changement de projet — « Aucune référence
    reconnue dans ta demande » s'affichait dans un projet où l'on n'avait rien
    demandé. Le masquage vit dans `load_project`, avant tout le reste ; on le
    prouve par la même méthode que le chemin débutant (une bombe posée juste
    après, pour garantir que le point d'observation est bien atteint)."""
    from ui import studio_view

    class _Boom(Exception):
        pass

    view = _bare_studio_view()
    view._registry_banner.visible = True
    view._registry_banner.body = "message perime du projet precedent"
    view._dirty = False
    view._current_project = None

    def _explode(_project):
        raise _Boom()

    original = studio_view.project_manager.load_code
    studio_view.project_manager.load_code = _explode
    raised = False
    try:
        studio_view.StudioView.load_project(view, object())
    except _Boom:
        raised = True
    finally:
        studio_view.project_manager.load_code = original

    assert raised, \
        "le test doit atteindre load_code pour que sa conclusion vaille"
    assert view._registry_banner.visible is False, \
        "changer de projet doit masquer la banniere de l'ancien"


TESTS = [
    test_no_message_renders_nothing,
    test_a_single_message_carries_no_number,
    test_two_messages_are_numbered_and_separated,
    test_three_messages_keep_counting,
    test_empty_messages_are_dropped_before_numbering,
    test_nothing_to_disclose_when_nothing_was_guessed,
    test_modify_is_silent_the_reference_is_in_the_code,
    test_regenerate_from_scratch_speaks,
    test_correct_without_a_surviving_target_speaks,
    test_add_speaks,
    test_full_regenerate_speaks,
    test_the_rule_never_looks_at_the_mode,
    test_correct_constant_has_not_drifted,
    test_info_banner_imports_no_qt,
    test_a_described_prompt_reports_a_guess,
    test_a_named_chip_reports_no_guess,
    test_forced_libs_report_no_guess,
    test_the_i2c_scanner_is_not_a_guess,
    test_a_basic_component_reports_no_guess,
    test_an_empty_retrieval_reports_no_guess,
    test_the_callback_fires_exactly_once_on_every_path,
    test_existing_callers_are_untouched,
    test_augment_user_prompt_forwards_the_report,
    test_the_message_exists_in_all_four_languages,
    test_the_message_claims_neither_naming_nor_use,
    test_the_studio_never_decides_the_banner_from_the_mode,
    test_no_mode_test_gates_the_calls_to_the_banner,
    test_the_registry_banner_uses_the_numbered_renderer,
    test_the_three_assembly_sites_report_back,
    test_a_guessed_generation_shows_the_translated_message,
    test_a_modify_shows_nothing,
    test_nothing_guessed_shows_nothing_regardless_of_action,
    test_both_generation_paths_call_the_banner,
    test_the_banner_is_shown_only_after_the_backstage_cancel_check,
    test_the_beginner_path_hides_a_stale_banner_before_the_registry_results,
    test_opening_another_project_hides_the_banner,
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

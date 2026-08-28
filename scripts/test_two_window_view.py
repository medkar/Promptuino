"""Vue avancée 2 fenêtres : i18n, reparentage, transfert, upload stable."""
import os
import sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)
from ui.fonts import setup_fonts
setup_fonts(_APP)

from ui.i18n import lang_manager


def test_i18n_two_window_fields_all_langs():
    fields = ("studio_window_ai", "studio_window_stable", "studio_transfer_to_stable",
              "studio_transfer_overwrite_msg", "studio_console_src_ai",
              "studio_console_src_stable", "studio_compile_upload_stable",
              "studio_mode_locked_busy")
    for lang in ("fr", "en", "es", "it"):
        lang_manager.set_language(lang)
        s = lang_manager.current
        for f in fields:
            assert getattr(s, f), f"{lang}:{f} vide"
    lang_manager.set_language("fr")


def test_mode_switch_reparents_without_losing_content():
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("intermediate")
    v._editor.setPlainText("void setup(){}\nvoid loop(){}\n")
    v._on_mode_changed("advanced")
    _APP.processEvents()
    assert not v._advanced_area_w.isHidden()
    assert v._code_compile_w.isHidden()
    assert v._code_panel.parent() is v._adv_ia_editor_slot
    assert v._console_w.parent() is v._adv_console_slot
    assert "void setup" in v._editor.toPlainText()
    v._on_mode_changed("intermediate")
    _APP.processEvents()
    assert not v._code_compile_w.isHidden()
    assert v._advanced_area_w.isHidden()
    assert v._code_panel.parent() is v._int_editor_slot
    assert "void setup" in v._editor.toPlainText()


def test_transfer_copies_ai_code_to_stable():
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    v._editor.setPlainText("void setup(){}\nvoid loop(){}\n")
    v._stable_panel.editor.setPlainText("")          # stable vide -> copie silencieuse
    v._on_transfer_to_stable()
    _APP.processEvents()
    assert v._stable_panel.editor.toPlainText() == "void setup(){}\nvoid loop(){}\n"


def test_transfer_confirms_when_stable_differs():
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    v._editor.setPlainText("NEW\n")
    v._stable_panel.editor.setPlainText("OLD\n")      # non vide & différent
    v._confirm_overwrite_stable = lambda: False        # refus -> pas de copie
    v._on_transfer_to_stable()
    assert v._stable_panel.editor.toPlainText() == "OLD\n"
    v._confirm_overwrite_stable = lambda: True         # accept -> copie
    v._on_transfer_to_stable()
    assert v._stable_panel.editor.toPlainText() == "NEW\n"


def test_stable_upload_runs_without_ai_backend():
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    v._stable_panel.editor.setPlainText("void setup(){}\nvoid loop(){}\n")
    calls = {}
    def _spy(**kw):
        calls.update(kw)
        return None
    v._compile_service.run = _spy
    # Court-circuite le préflight (pas d'arduino-cli en CI). Signature
    # (notify, code=None) — cf. Step 3.
    v._preflight_compile_upload = lambda notify, code=None: (
        "void setup(){}\nvoid loop(){}\n", "arduino:avr:uno", "COM3")
    v._on_stable_compile_upload()
    assert calls, "compile_service.run non appelé"
    assert calls.get("backend") is None, "l'upload stable ne doit PAS utiliser de backend IA"
    assert calls.get("verify_only") in (False, None)
    assert calls.get("console") is v._adv_console
    assert calls.get("clear") is False   # stable clears manually then run(clear=False)
    assert not v._btn_compile.isEnabled()   # IA button cross-disabled during stable upload


def test_save_and_load_stable_code_via_studio():
    import tempfile
    from pathlib import Path
    from ui.studio_view import StudioView
    from ui.project_manager import Project, ProjectType
    v = StudioView()
    v._on_mode_changed("advanced")
    with tempfile.TemporaryDirectory() as tmp:
        proj = Project(path=Path(tmp) / "p", name="p", type=ProjectType.ARDUINO)
        v._current_project = proj
        v._editor.setPlainText("void setup(){}\nvoid loop(){}\n")
        v._stable_panel.editor.setPlainText("STABLE CODE\n")
        v.save_project()
    assert v._current_project.stable_code == "STABLE CODE\n"


def test_load_project_restores_stable_editor():
    from pathlib import Path
    from ui.studio_view import StudioView
    from ui.project_manager import Project, ProjectType
    import ui.project_manager as pm
    v = StudioView()
    proj = Project(path=Path("x"), name="p", type=ProjectType.ARDUINO,
                   mode="advanced", stable_code="RESTORED\n")
    orig = pm.project_manager.load_code
    pm.project_manager.load_code = lambda p: "void setup(){}\nvoid loop(){}\n"
    try:
        v.load_project(proj)
        _APP.processEvents()
    finally:
        pm.project_manager.load_code = orig
    assert v._stable_panel.editor.toPlainText() == "RESTORED\n"


def test_cancel_restores_the_active_window_button():
    # L'annulation d'un upload doit restaurer LE BON bouton (IA ou stable),
    # pas systématiquement l'IA. On simule un upload stable en cours puis on
    # annule ; le bouton stable doit être restauré (spinner retiré) et l'IA
    # ré-activé.
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    restored = {"stable": 0, "ia": 0}
    v._restore_stable_btn = lambda: restored.__setitem__("stable", restored["stable"] + 1)
    v._restore_compile_btn = lambda: restored.__setitem__("ia", restored["ia"] + 1)
    # État « upload stable en cours » : garde active + callback de restauration ciblé.
    v._cu_running = True
    v._cu_active_restore = v._restore_stable_btn
    v._cu_worker = None                      # pas de worker réel à annuler
    v._cancel_cu_worker()
    assert restored["stable"] == 1, "l'annulation doit restaurer le bouton stable"
    assert restored["ia"] == 0, "l'annulation ne doit PAS restaurer le bouton IA à sa place"


def test_mode_switch_blocked_during_operation():
    # Le sélecteur ne doit pas laisser changer de mode pendant une génération
    # ou un upload (sinon on masque/vide l'opération en cours).
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    assert v._mode_selector._can_switch == v._may_switch_mode   # veto câblé
    assert v._may_switch_mode("intermediate") is True           # au repos : OK
    v._cu_running = True                                        # upload en cours
    assert v._may_switch_mode("intermediate") is False
    v._cu_running = False
    v._gen_busy = "advanced"                                    # génération en cours
    assert v._may_switch_mode("beginner") is False
    v._gen_busy = None
    v._beginner_running = True                                  # upload débutant
    assert v._may_switch_mode("advanced") is False
    v._beginner_running = False


def test_stable_schema_button_follows_stable_code():
    # « Voir le schéma » de la fenêtre stable : activé ⇔ il y a du code stable.
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    v._stable_panel.editor.setPlainText("")
    assert not v._btn_view_schema_stable.isEnabled()
    v._stable_panel.editor.setPlainText("void setup(){}\nvoid loop(){}\n")
    assert v._btn_view_schema_stable.isEnabled()               # via _on_stable_edited


def test_schema_button_follows_the_code_not_the_generation():
    # QA E (2026-08-08) : le bouton « Voir le schéma » des fenêtres IA/débutant
    # suivait `_has_generated` — « une GÉNÉRATION a-t-elle eu lieu ? » — au lieu
    # du CODE. Conséquence : en Avancé, quelqu'un qui écrit ou colle son propre
    # sketch ne pouvait JAMAIS ouvrir le schéma, alors que le schéma se déduit
    # précisément du code. La fenêtre stable appliquait déjà la bonne règle
    # (cf. test ci-dessus) ; les deux autres boutons non.
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    assert not v._btn_view_schema_adv.isEnabled(), "squelette seul : rien à dessiner"

    v._editor.setPlainText(
        "#include <Wire.h>\nvoid setup(){ Wire.begin(); }\nvoid loop(){}\n")
    assert v._btn_view_schema_adv.isEnabled()
    assert v._btn_view_schema.isEnabled()

    # Retour au squelette : le bouton se re-grise, la règle marche dans les
    # deux sens (sinon un projet vidé garderait un bouton actif menant à un
    # schéma vide).
    v._editor.setPlainText(lang_manager.editor_template())
    assert not v._btn_view_schema_adv.isEnabled()


def test_stable_shows_template_before_generation():
    # Avant toute promotion depuis l'IA, la fenêtre stable affiche le même
    # squelette éditeur que la fenêtre IA (état « avant génération »).
    from ui.studio_view import StudioView
    from ui.i18n import lang_manager
    v = StudioView()
    v._on_mode_changed("advanced")
    st = v._stable_panel.editor.toPlainText()
    assert st.strip(), "la fenêtre stable doit contenir le squelette avant génération"
    assert st == lang_manager.editor_template()
    assert v._is_template_or_scaffolded(st)


def test_advanced_code_windows_are_taller():
    # En mode avance, les deux fenetres de code sont 50% plus hautes (plancher
    # 280 -> 420) ; en Intermediaire l'editeur partage retrouve 280.
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    assert v._code_panel.editor.minimumHeight() == 420
    assert v._stable_panel.editor.minimumHeight() == 420
    v._on_mode_changed("intermediate")
    assert v._code_panel.editor.minimumHeight() == 280


def test_stable_upload_veils_stable_window_not_ai():
    # BUG : uploader depuis la fenetre stable voilait la fenetre IA (mauvaise
    # cible du voile). Le voile « edition impossible » doit couvrir la fenetre
    # STABLE (celle qu'on uploade), pas l'autre.
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    v._stable_panel.editor.setPlainText("void setup(){}\nvoid loop(){}\n")
    v._compile_service.run = lambda **kw: None
    v._preflight_compile_upload = lambda notify, code=None: (
        "void setup(){}\nvoid loop(){}\n", "arduino:avr:uno", "COM3")
    v._on_stable_compile_upload()
    assert v._stable_panel.is_busy(), "la fenetre stable doit etre voilee pendant son upload"
    assert not v._code_panel.is_busy(), "la fenetre IA ne doit PAS etre voilee pendant l'upload stable"


def test_ai_upload_veils_ai_window_not_stable():
    # Symetrique : l'upload IA voile la fenetre IA, jamais la stable.
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    v._editor.setPlainText("void setup(){}\nvoid loop(){}\n")
    v._compile_service.run = lambda **kw: None
    v._preflight_compile_upload = lambda notify, code=None: (
        "void setup(){}\nvoid loop(){}\n", "arduino:avr:uno", "COM3")
    v._on_compile_upload()
    assert v._code_panel.is_busy(), "la fenetre IA doit etre voilee pendant son upload"
    assert not v._stable_panel.is_busy(), "la fenetre stable ne doit PAS etre voilee pendant l'upload IA"


def test_per_window_tools_target_isolation():
    # Chaque fenêtre a sa section d'outils ; un outil déclenché sur la fenêtre
    # stable agit sur l'éditeur stable, pas sur l'éditeur IA (et inversement).
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    # Section d'outils partagée reparentée dans la fenêtre IA ; en-tête
    # partagé masqué (chaque fenêtre a son titre).
    assert v._code_tools_w.parent() is v._adv_ia_tools_slot
    assert v._code_header_w.isHidden()
    assert hasattr(v, "_btn_ai_tools_st") and hasattr(v, "_chk_show_comments_st")
    v._editor.setPlainText("void setup(){\n}\nvoid loop(){\n}\n")
    v._stable_panel.editor.setPlainText("void setup(){\nint x=1;\n}\nvoid loop(){\n}\n")
    ia_before = v._editor.toPlainText()
    # Formater (déterministe) ciblant la fenêtre stable.
    v._code_target = "stable"
    v._run_format_code()
    assert v._editor.toPlainText() == ia_before, "l'éditeur IA ne doit pas bouger"
    assert "int x" in v._stable_panel.editor.toPlainText()
    # Retour Intermédiaire : la section revient dans l'en-tête partagé.
    v._on_mode_changed("intermediate")
    assert v._code_tools_w.parent() is v._int_tools_slot
    assert not v._code_header_w.isHidden()


def test_stable_delete_only_touches_stable():
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature
    v = StudioView()
    v._on_mode_changed("advanced")
    v._features = [Feature(id="f1", prompt="led"), Feature(id="f2", prompt="buzz")]
    v._stable_features = [Feature(id="f1", prompt="led"), Feature(id="f2", prompt="buzz")]
    v._stable_panel.editor.setPlainText("void setup(){}\nvoid loop(){}\n")
    # _delete_features(target="stable") ne passe PAS par la confirmation
    # (celle-ci vit dans _on_chips_delete) -> pas de QMessageBox a mocker.
    v._delete_features({"f2"}, target="stable")
    assert [f.id for f in v._stable_features] == ["f1"]
    assert [f.id for f in v._features] == ["f1", "f2"]       # IA intacte
    # Le compteur « N lignes » stable reflete le nouveau code apres suppression
    # (textChanged etant bloque pendant setPlainText, il faut le rafraichir).
    nlines = v._stable_panel.editor.blockCount()
    assert v._lbl_code_meta_st.text().startswith(str(nlines) + " "), \
        v._lbl_code_meta_st.text()


def test_regen_rejected_on_stable():
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    called = {"n": 0}
    v._regenerate_features = lambda ids: called.__setitem__("n", called["n"] + 1)
    v._on_chips_regen(["f1"], target="stable")
    assert called["n"] == 0


class _FakeTransferDialog:
    """Stub of FeatureTransferDialog: simulates a 'transfer all' + accept
    without exec'ing a real modal (offscreen tests)."""
    side_changed = ("stable",)
    accept_code = 1

    def __init__(self, ia, stable, dirty_ia=False, dirty_stable=False,
                 parent=None):
        from ui.feature_transfer import TransferStaging
        self.staging = TransferStaging(ia, stable)
        self._mutate()

    def _mutate(self):
        self.staging.transfer_all()

    def exec(self):
        return self.accept_code

    def result(self):
        return self.staging.result()

    def _side_changed(self, side):
        return side in self.side_changed

    def _recap_parts(self, s):
        return ["stub"]


def _patched(v, dlg_cls):
    import ui.studio_view as sv_mod
    orig = sv_mod.FeatureTransferDialog
    sv_mod.FeatureTransferDialog = dlg_cls
    return orig


def test_transfer_dialog_apply_inherits_features():
    # Features present -> the chevron opens the popup; a staged
    # "transfer all" applied writes assemble(features) into stable.
    import ui.studio_view as sv_mod
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature
    v = StudioView()
    v._on_mode_changed("advanced")
    v._features = [Feature(id="f1", prompt="led",
                           setup_lines=["pinMode(13, OUTPUT);"])]
    v._editor.setPlainText("void setup(){}\nvoid loop(){}\n")
    saves = {"n": 0}
    v.save_project = lambda *a, **k: saves.__setitem__("n", saves["n"] + 1)
    orig = _patched(v, _FakeTransferDialog)
    try:
        v._on_transfer_to_stable()
    finally:
        sv_mod.FeatureTransferDialog = orig
    assert [f.id for f in v._stable_features] == ["f1"]
    st = v._stable_panel.editor.toPlainText()
    assert "pinMode(13, OUTPUT);" in st
    assert "f1" in v._stable_panel.editor.line_owners()
    assert v._stable_baseline == st                  # baseline synced
    assert saves["n"] == 1                           # single save


def test_transfer_dialog_apply_reorders_ia_and_strips_metadata():
    import ui.studio_view as sv_mod
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature

    class _ReorderDeleteDlg(_FakeTransferDialog):
        side_changed = ("ia",)

        def _mutate(self):
            self.staging.reorder("f2", 0, "ia")      # f2 first (independent)
            self.staging.toggle_delete("f1", "ia")   # delete f1

    v = StudioView()
    v._on_mode_changed("advanced")
    v._features = [
        Feature(id="f1", prompt="led", setup_lines=["pinMode(13, OUTPUT);"]),
        Feature(id="f2", prompt="buzzer", setup_lines=["pinMode(9, OUTPUT);"]),
    ]
    # In-memory metadata keys are TUPLES (fn_id, pin_net) — the "f1|D13"
    # string form only exists in persistence.
    v._wiring_resolutions = {("f1", "D13"): "led", ("f2", "D9"): "buzzer"}
    v.save_project = lambda *a, **k: None
    orig = _patched(v, _ReorderDeleteDlg)
    try:
        v._on_transfer_to_stable()
    finally:
        sv_mod.FeatureTransferDialog = orig
    assert [f.id for f in v._features] == ["f2"]     # f1 deleted
    assert "pinMode(9, OUTPUT);" in v.get_code()
    assert "pinMode(13, OUTPUT);" not in v.get_code()
    assert ("f1", "D13") not in v._wiring_resolutions   # metadata stripped
    assert ("f2", "D9") in v._wiring_resolutions


def test_transfer_dialog_cancel_touches_nothing():
    import ui.studio_view as sv_mod
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature

    class _CancelDlg(_FakeTransferDialog):
        accept_code = 0                              # rejected

    v = StudioView()
    v._on_mode_changed("advanced")
    v._features = [Feature(id="f1", prompt="led",
                           setup_lines=["pinMode(13, OUTPUT);"])]
    before = v._stable_panel.editor.toPlainText()
    orig = _patched(v, _CancelDlg)
    try:
        v._on_transfer_to_stable()
    finally:
        sv_mod.FeatureTransferDialog = orig
    assert v._stable_panel.editor.toPlainText() == before
    assert v._stable_features == []


def test_transfer_busy_guard_skips_dialog():
    import ui.studio_view as sv_mod
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature

    class _BoomDlg:
        def __init__(self, *a, **k):
            raise AssertionError("dialog must not be built while busy")

    v = StudioView()
    v._on_mode_changed("advanced")
    v._features = [Feature(id="f1", prompt="led")]
    v._cu_running = True
    orig = _patched(v, _BoomDlg)
    try:
        v._on_transfer_to_stable()                   # must not raise
    finally:
        sv_mod.FeatureTransferDialog = orig
        v._cu_running = False


def test_transfer_block_two_chevrons_wired_and_centered():
    # Both chevrons (>> and <<) open the SAME bidirectional popup; the block
    # is centered on the EDITORS band (not the full column with its buttons).
    import ui.studio_view as sv_mod
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature
    from PyQt6.QtCore import QPoint

    class _RecDlg(_FakeTransferDialog):
        accept_code = 0                          # cancel: no side effects
        built = {"n": 0}

        def __init__(self, *a, **k):
            type(self).built["n"] += 1
            super().__init__(*a, **k)

    v = StudioView()
    v._on_mode_changed("advanced")
    v._features = [Feature(id="f1", prompt="led")]
    assert v._btn_transfer.text() == "»"
    assert v._btn_transfer_back.text() == "«"
    # One visual control: hand cursor on the whole block (gaps included) and
    # a COLLECTIVE hover — white at rest, green when _set_transfer_hover(True)
    # (driven by the Enter/Leave eventFilter; QSS ancestor :hover is not
    # honored by Qt, it left the chevrons permanently green).
    from PyQt6.QtCore import Qt as _Qt
    from ui.theme import theme_manager as _tm
    assert v._transfer_block.cursor().shape() == _Qt.CursorShape.PointingHandCursor
    assert _tm.current.text_primary in v._transfer_block.styleSheet()   # rest
    v._set_transfer_hover(True)
    assert _tm.current.signal_ok in v._transfer_block.styleSheet()      # hover
    v._set_transfer_hover(False)
    assert _tm.current.text_primary in v._transfer_block.styleSheet()
    orig = _patched(v, _RecDlg)
    try:
        v._btn_transfer.click()
        v._btn_transfer_back.click()
    finally:
        sv_mod.FeatureTransferDialog = orig
    assert _RecDlg.built["n"] == 2               # both open the popup
    # Centering: block center ~= editors band center (union of both).
    v.show(); _APP.processEvents()
    v._reposition_transfer_block()
    cont, blk = v._transfer_col_w, v._transfer_block
    tops, bottoms = [], []
    for ed in (v._editor, v._stable_panel.editor):
        top = cont.mapFromGlobal(ed.mapToGlobal(QPoint(0, 0))).y()
        tops.append(top)
        bottoms.append(top + ed.height())
    band_center = (min(tops) + max(bottoms)) / 2
    blk_center = blk.y() + blk.height() / 2
    assert abs(blk_center - band_center) <= 2, (blk_center, band_center)
    v.hide()


def test_transfer_reflects_repaired_editor_not_stale_model():
    # Bug (2026-07-06): the transfer rebuilt from assemble(features), i.e. the
    # PRE-repair model -> the "old version" was transferred. Now the source
    # features are resynced from the (repaired) editor before the popup.
    import ui.studio_view as sv_mod
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature
    from ui.generation import assemble, is_dirty

    class _AllDlg(_FakeTransferDialog):
        side_changed = ("stable",)

    v = StudioView()
    v._on_mode_changed("advanced")
    f1 = Feature(id="f1", prompt="led",
                 global_lines=["const int PIN_LED = 5;"],
                 setup_lines=["pinMode(PIN_LED, OUTPUT);"],
                 loop_lines=["digitalWrite(PIN_LED, HIGH);"])
    f2 = Feature(id="f2", prompt="blink",
                 loop_lines=["digitalWrite( PIN_LED , LOW );", "delay(500);"])
    v._features = [f1, f2]
    v._set_code_with_attribution(assemble([f1, f2]), v._features)
    # Simulated repair: drop the redundant re-drive line in the editor only
    # (the model still has it -> stale).
    repaired = "\n".join(l for l in v.get_code().split("\n")
                         if "digitalWrite( PIN_LED , LOW )" not in l)
    v._set_code_with_attribution(repaired, v._features)
    assert is_dirty(assemble(v._features), v.get_code())      # model is stale
    v.save_project = lambda *a, **k: None
    orig = _patched(v, _AllDlg)
    try:
        v._on_transfer_to_stable()
    finally:
        sv_mod.FeatureTransferDialog = orig
    st = v._stable_panel.editor.toPlainText()
    assert "digitalWrite( PIN_LED , LOW )" not in st          # repaired, not stale
    assert "digitalWrite(PIN_LED, HIGH);" in st               # kept the rest


class _StubReviewDialog:
    instances = []

    def __init__(self, backend, code, board, parent=None, review_call=None):
        self.review_call = review_call
        _StubReviewDialog.instances.append(self)

    def exec(self):
        return 0

    class _Sig:
        def connect(self, *a, **k):
            pass
    apply_requested = _Sig()
    summary_ready = _Sig()


def _patch_review_dialog():
    import ui.repair_code_dialog as rc
    orig = rc.RepairCodeDialog
    rc.RepairCodeDialog = _StubReviewDialog
    _StubReviewDialog.instances = []
    return orig


def test_open_audit_runs_lint_and_offers_conformance():
    # B (lint) logged + C (review) armed when there's an intent + eligible be.
    import ui.repair_code_dialog as rc
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature
    v = StudioView()
    v._on_mode_changed("advanced")
    v._features = [Feature(id="f1", prompt="allume la LED",
                           prompts=["allume la LED"])]
    logged = {"n": 0}
    v._log_behavior_findings = lambda f: logged.__setitem__("n", logged["n"] + 1)
    be = type("B", (), {"is_slm": lambda self: False,
                        "review_conformance": lambda self, *a, **k: ("", "")})()
    orig = _patch_review_dialog()
    try:
        v._open_audit_dialog(be, "void setup(){}\nvoid loop(){}\n", "ia")
    finally:
        rc.RepairCodeDialog = orig
    assert logged["n"] == 1                                    # B ran
    assert _StubReviewDialog.instances[-1].review_call is not None  # C armed


def test_open_audit_without_features_uses_plain_audit():
    import ui.repair_code_dialog as rc
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    v._features = []                                    # no intent
    v._log_behavior_findings = lambda f: None
    be = type("B", (), {"is_slm": lambda self: False,
                        "review_conformance": lambda self, *a, **k: ("", "")})()
    orig = _patch_review_dialog()
    try:
        v._open_audit_dialog(be, "void setup(){}\nvoid loop(){}\n", "ia")
    finally:
        rc.RepairCodeDialog = orig
    assert _StubReviewDialog.instances[-1].review_call is None   # plain audit


def test_manual_repair_routes_code_to_stable():
    # Chantier 1 : le callback CompileService écrit dans l'éditeur du target
    # ACTIF (stable ici), pas l'IA en dur.
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature
    from ui.generation import assemble
    v = StudioView()
    v._on_mode_changed("advanced")
    v._stable_features = [Feature(id="s1", prompt="led",
                                  setup_lines=["pinMode(5, OUTPUT);"])]
    v._stable_panel.editor.setPlainText(assemble(v._stable_features))
    ia_before = v._editor.toPlainText()
    v._active_repair_target = "stable"
    v._update_code_meta = lambda *a, **k: None
    v._on_service_code_updated("void setup(){ REPAIRED; }\nvoid loop(){}\n")
    assert "REPAIRED" in v._stable_panel.editor.toPlainText()
    assert v._editor.toPlainText() == ia_before          # IA untouched


class _StubReviewModal:
    """Stand-in for the already-open (deferred) RepairCodeDialog."""
    def __init__(self):
        self.pre_summary = None
        self.started = False
        self.review_call = "unset"
        self.failure = None

    def set_pre_summary(self, text):
        self.pre_summary = text

    def start_deferred(self, review_call=None):
        self.started = True
        self.review_call = review_call

    def show_compile_failure(self, message):
        self.failure = message


def test_cascade_summary_lists_lines_when_no_model_summary():
    # A cascade step WITHOUT a model summary must fall back to the concrete
    # changed LINES (removed / added / changed), not a vague « N corrections ».
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    before = "const int X = 1;\nconst int X = 2;\nvoid loop(){ digitalWirte(); }\n"
    after = "const int X = 1;\nvoid loop(){ digitalWrite(); }\n"
    v._last_repair_steps = [{"kind": "fix", "summary": "",
                             "code_before": before, "code_after": after}]
    txt = v._cascade_summary_text()
    assert "const int X = 2;" in txt and "retirée" in txt      # dup removed
    assert "digitalWirte" in txt and "digitalWrite" in txt      # typo changed
    assert "voir le détail dans le journal" not in txt          # not the generic


def test_cascade_summary_uses_model_summary_when_present():
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    v._last_repair_steps = [{"kind": "fix", "summary": "- **Ligne 3 :** point-virgule"}]
    assert "point-virgule" in v._cascade_summary_text()


def test_manual_repair_preview_buffers_cascade_not_editor():
    # PREVIEW: during a manual repair, the cascade result is BUFFERED, the
    # editor stays untouched (Cancel must change nothing — bug 2026-07-06).
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    v._editor.blockSignals(True); v._editor.setPlainText("ORIGINAL\n")
    v._editor.blockSignals(False)
    v._manual_repair_running = True
    v._manual_repair = {"target": "ia", "original": "ORIGINAL\n"}
    v._on_service_code_updated("REPAIRED\n")
    assert v.get_code() == "ORIGINAL\n"                   # editor untouched
    assert v._manual_repair["repaired_code"] == "REPAIRED\n"  # buffered


def test_manual_repair_done_reviews_buffer_without_applying():
    # done drives the modal on the BUFFERED (repaired) code and does NOT touch
    # the editor / model (no resync here — that happens only on Apply).
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    got = {"resync": False}
    v._build_review_call = lambda be, code, t: got.__setitem__("code", code) or "RC"
    v._resync_features_after_repair = lambda t="ia": got.__setitem__("resync", True)
    v.save_project = lambda *a, **k: None
    v._cascade_summary_text = lambda: "CASCADE"
    v._editor.blockSignals(True); v._editor.setPlainText("ORIGINAL\n")
    v._editor.blockSignals(False)
    dlg = _StubReviewModal(); v._manual_repair_dialog = dlg
    v._manual_repair = {"target": "ia", "original": "ORIGINAL\n",
                        "repaired_code": "REPAIRED\n", "backend": object()}
    v._last_repair_steps = [{"kind": "fix"}]
    v._on_manual_repair_done(True, "")
    assert got.get("code") == "REPAIRED\n"               # review on the buffer
    assert dlg.started and dlg.pre_summary == "CASCADE"
    assert got["resync"] is False                        # NOT applied yet
    assert v.get_code() == "ORIGINAL\n"                  # editor still untouched


def test_manual_repair_done_no_repair_reviews_original():
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    got = {}
    v._build_review_call = lambda be, code, t: got.update(code=code) or "RC"
    dlg = _StubReviewModal(); v._manual_repair_dialog = dlg
    v._manual_repair = {"target": "ia", "original": "ORIG\n", "backend": object()}
    v._last_repair_steps = []                            # compiled directly
    v._on_manual_repair_done(True, "")
    assert got.get("code") == "ORIG\n" and dlg.started   # no buffer -> original


def test_manual_repair_done_ko_leaves_editor_and_shows_failure():
    # Preview: on failure the editor was never touched (buffered) -> unchanged;
    # the diagnostic is surfaced in the modal.
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature
    from ui.generation import assemble
    v = StudioView()
    v._on_mode_changed("advanced")
    f1 = Feature(id="f1", prompt="led", setup_lines=["pinMode(5, OUTPUT);"])
    v._features = [f1]
    original = assemble([f1])
    v._set_code_with_attribution(original, v._features)
    dlg = _StubReviewModal(); v._manual_repair_dialog = dlg
    v._manual_repair = {"target": "ia", "original": original, "backend": object()}
    v._last_repair_steps = []
    v._on_manual_repair_done(False, "error: boom")
    assert v.get_code() == original                      # editor untouched
    assert dlg.failure == "error: boom"                  # shown in the modal


def test_run_repair_falls_back_to_audit_without_cli():
    import ui.studio_view as sv_mod
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    fake_be = type("B", (), {"is_available": lambda self: True})()
    orig_get = sv_mod.get_backend_instance
    orig_avail = sv_mod.arduino_cli.is_available
    sv_mod.get_backend_instance = lambda *a, **k: fake_be
    sv_mod.arduino_cli.is_available = lambda: False       # no compiler
    opened = {}
    v._open_audit_dialog = lambda backend, code, t: opened.update(t=t)
    try:
        v._run_repair_code()
    finally:
        sv_mod.get_backend_instance = orig_get
        sv_mod.arduino_cli.is_available = orig_avail
    assert opened.get("t") == "ia"                        # audit fallback


def test_can_reconstruct_predicate():
    # Chantier 3 : offrir « reconstruire depuis les features » SEULEMENT si
    # l'éditeur est structurellement cassé (accolades déséquilibrées) ET
    # assemble(features) est équilibré ET il y a des features.
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature
    from ui.generation import assemble
    v = StudioView()
    v._on_mode_changed("advanced")
    f1 = Feature(id="f1", prompt="led",
                 setup_lines=["if (x) {", "go();", "}"])
    v._features = [f1]
    v._set_code_with_attribution(assemble([f1]), v._features)
    assert not v._can_reconstruct_from_features("ia")     # balanced editor
    # Break the editor: drop a closing brace.
    broken = v.get_code().replace("}\n}", "}", 1)
    v._editor.blockSignals(True); v._editor.setPlainText(broken)
    v._editor.blockSignals(False)
    assert v._can_reconstruct_from_features("ia")          # editor unbalanced
    v._features = []
    assert not v._can_reconstruct_from_features("ia")      # no features


def test_reconstruct_applies_assembled_code():
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature
    from ui.generation import assemble
    v = StudioView()
    v._on_mode_changed("advanced")
    f1 = Feature(id="f1", prompt="led",
                 global_lines=["const int PIN_LED = 5;"],
                 setup_lines=["pinMode(PIN_LED, OUTPUT);"])
    v._features = [f1]
    v._editor.blockSignals(True); v._editor.setPlainText("void setup(){ BROKEN")
    v._editor.blockSignals(False)
    v.save_project = lambda *a, **k: None
    v._reconstruct_from_features("ia")
    assert v.get_code() == assemble([f1])
    assert "f1" in v._editor.line_owners()


def test_verify_failure_offers_reconstruct_then_skips_revert():
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature
    from ui.generation import assemble
    v = StudioView()
    v._on_mode_changed("intermediate")
    f1 = Feature(id="f1", prompt="led", setup_lines=["if (x) {", "go();", "}"])
    v._features = [f1]
    v._set_code_with_attribution(assemble([f1]), v._features)
    # Editor left structurally broken by a failed repair.
    v._editor.blockSignals(True)
    v._editor.setPlainText(v.get_code().replace("}\n}", "}", 1))
    v._editor.blockSignals(False)
    v._verify_delivered_code = v.get_code()
    v._gen_revert_code = "void setup(){}\nvoid loop(){}\n"
    v._gen_revert_features = []
    v.save_project = lambda *a, **k: None
    v._set_generating = lambda *a, **k: None
    v._confirm_reconstruct_from_features = lambda t="ia": True    # user accepts
    v._finalize_verify_failure("error")
    assert v.get_code() == assemble([f1])          # reconstructed, not reverted
    assert [f.id for f in v._features] == ["f1"]   # features kept


def test_verify_failure_reverts_when_reconstruct_declined():
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature
    from ui.generation import assemble
    v = StudioView()
    v._on_mode_changed("intermediate")
    f1 = Feature(id="f1", prompt="led", setup_lines=["if (x) {", "go();", "}"])
    v._features = [f1]
    v._set_code_with_attribution(assemble([f1]), v._features)
    v._editor.blockSignals(True)
    v._editor.setPlainText(v.get_code().replace("}\n}", "}", 1))
    v._editor.blockSignals(False)
    v._verify_delivered_code = v.get_code()
    v._gen_revert_code = "void setup(){}\nvoid loop(){}\n"
    v._gen_revert_features = []
    v.save_project = lambda *a, **k: None
    v._set_generating = lambda *a, **k: None
    v._confirm_reconstruct_from_features = lambda t="ia": False   # user declines
    v._finalize_verify_failure("error")
    assert v.get_code() == "void setup(){}\nvoid loop(){}\n"      # reverted
    assert v._features == []


def test_resync_after_repair_makes_model_canonical():
    # Chantier 2 (spec réparation) : après une réparation, le modèle
    # Feature.*_lines doit refléter le code réparé de l'éditeur (sinon
    # transfert/suppression/réordre repartent d'un modèle périmé).
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature
    from ui.generation import assemble, is_dirty
    v = StudioView()
    v._on_mode_changed("advanced")
    f1 = Feature(id="f1", prompt="led",
                 global_lines=["const int PIN_LED = 5;"],
                 setup_lines=["pinMode(PIN_LED, OUTPUT);"],
                 loop_lines=["digitalWrite(PIN_LED, HIGH);"])
    f2 = Feature(id="f2", prompt="blink",
                 loop_lines=["digitalWrite( PIN_LED , LOW );", "delay(500);"])
    v._features = [f1, f2]
    v._set_code_with_attribution(assemble([f1, f2]), v._features)
    # Repair drops the redundant re-drive in the editor (model stays stale).
    repaired = "\n".join(l for l in v.get_code().split("\n")
                         if "digitalWrite( PIN_LED , LOW )" not in l)
    v._set_code_with_attribution(repaired, v._features)
    assert is_dirty(assemble(v._features), v.get_code())   # stale before
    v._resync_features_after_repair("ia")
    assert not is_dirty(assemble(v._features), v.get_code())  # canonical after


def test_resync_after_repair_noop_when_unfaithful():
    # If assemble(resynced) can't reproduce the editor (owner map too rough),
    # the model is left untouched — no silent corruption.
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature
    from ui.generation import assemble
    v = StudioView()
    v._on_mode_changed("advanced")
    f1 = Feature(id="f1", prompt="led",
                 setup_lines=["pinMode(PIN_LED, OUTPUT);"])
    v._features = [f1]
    v._set_code_with_attribution(assemble([f1]), v._features)
    before = [f.setup_lines[:] for f in v._features]
    # Editor rewritten to something the map can't faithfully re-split back.
    v._editor.blockSignals(True)
    v._editor.setPlainText("void setup(){\n  totallyDifferent();\n}\nvoid loop(){}\n")
    v._editor.blockSignals(False)
    v._resync_features_after_repair("ia")
    assert [f.setup_lines for f in v._features] == before   # unchanged


def test_finalize_verify_success_resyncs_model():
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature
    from ui.generation import assemble, is_dirty
    v = StudioView()
    v._on_mode_changed("intermediate")
    f1 = Feature(id="f1", prompt="led",
                 global_lines=["const int PIN_LED = 5;"],
                 loop_lines=["digitalWrite(PIN_LED, HIGH);",
                             "digitalWrite( PIN_LED , HIGH );"])
    v._features = [f1]
    v._set_code_with_attribution(assemble([f1]), v._features)
    repaired = "\n".join(l for l in v.get_code().split("\n")
                         if "digitalWrite( PIN_LED , HIGH )" not in l)
    v._set_code_with_attribution(repaired, v._features)
    v._last_repair_steps = [{"kind": "fix"}]      # a repair happened
    v.save_project = lambda *a, **k: None
    v._set_generating = lambda *a, **k: None       # avoid UI plumbing
    v._finalize_verify_success()
    assert not is_dirty(assemble(v._features), v.get_code())


def test_manual_repair_suppresses_journal_button():
    # TODO #32: in a MANUAL repair the 3-column modal already shows every
    # correction, so the journal « voir les corrections » button must NOT
    # appear (it points at a non-applied PREVIEW if the user cancels). The
    # steps are still recorded (the modal's pre-summary reads them).
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    shown = {"n": 0}
    v._output_area.show_repairs_action = \
        lambda *a, **k: shown.__setitem__("n", shown["n"] + 1)
    steps = [{"kind": "fix"}]
    v._manual_repair_running = True
    v._on_cu_repair_steps(steps)
    assert v._last_repair_steps == steps                 # recorded
    assert shown["n"] == 0                                # suppressed in manual
    v._manual_repair_running = False
    v._on_cu_repair_steps(steps)
    assert shown["n"] == 1                                # shown on auto path


def test_ia_upload_finished_resyncs_model():
    # TODO #32 / chantier 2: the auto compile+upload applies repairs to the
    # editor WITHOUT a resync -> the model would go stale. _on_ia_upload_finished
    # makes it canonical again when a repair happened, then restores the button.
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature
    from ui.generation import assemble, is_dirty
    v = StudioView()
    v._on_mode_changed("advanced")
    f1 = Feature(id="f1", prompt="led",
                 global_lines=["const int PIN_LED = 5;"],
                 loop_lines=["digitalWrite(PIN_LED, HIGH);",
                             "digitalWrite( PIN_LED , HIGH );"])
    v._features = [f1]
    v._set_code_with_attribution(assemble([f1]), v._features)
    repaired = "\n".join(l for l in v.get_code().split("\n")
                         if "digitalWrite( PIN_LED , HIGH )" not in l)
    v._set_code_with_attribution(repaired, v._features)   # editor fixed, model stale
    assert is_dirty(assemble(v._features), v.get_code())  # stale before
    v._last_repair_steps = [{"kind": "fix"}]
    restored = {"n": 0}
    v._restore_compile_btn = lambda: restored.__setitem__("n", 1)
    v._on_ia_upload_finished()
    assert not is_dirty(assemble(v._features), v.get_code())  # canonical after
    assert restored["n"] == 1                             # button restored


def test_applied_repairs_dialog_is_readonly_consolidated():
    # TODO #32: the journal « voir les corrections » button opens the SAME
    # 3-column modal as the manual repair, in a read-only mode (no « Appliquer »):
    # consolidated original -> final diff + the cascade explanation.
    from ui.repair_code_dialog import RepairCodeDialog
    from ui.i18n import lang_manager
    original = "int x=0\nvoid setup(){}\nvoid loop(){}\n"
    final = "int x = 0;\nvoid setup(){}\nvoid loop(){}\n"
    dlg = RepairCodeDialog(None, original, "Arduino", None,
                           applied=(final, "- **Ligne 1** point-virgule"))
    assert not dlg._btn_apply.isVisibleTo(dlg)           # nothing to apply
    assert dlg._new_code.strip() == final.strip()        # final code shown
    assert dlg.windowTitle() == lang_manager.current.studio_repair_history_title
    dlg.deleteLater()


def test_repairs_link_opens_applied_dialog():
    # The journal action routes to the read-only applied-repairs modal, and
    # only when there ARE recorded steps.
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    called = {"n": 0}
    v._open_applied_repairs_dialog = lambda: called.__setitem__("n", called["n"] + 1)
    v._last_repair_steps = [{"kind": "fix", "code_before": "a\n", "code_after": "b\n"}]
    v._on_output_action("repairs")
    assert called["n"] == 1
    v._last_repair_steps = []
    v._on_output_action("repairs")
    assert called["n"] == 1                               # no steps -> no-op


def test_stable_tools_apply_keeps_attribution():
    # Bug n3 (2026-07-06): applying a repaired code on the STABLE window went
    # through a bare setPlainText -> line owners wiped -> feature highlight
    # dead until the project was reloaded. _tools_apply must re-pose the map.
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature
    from ui.generation import assemble
    v = StudioView()
    v._on_mode_changed("advanced")
    f1 = Feature(id="f1", prompt="led",
                 global_lines=["const int PIN_LED = 5;"],
                 setup_lines=["pinMode(PIN_LED, OUTPUT);"],
                 loop_lines=["digitalWrite(PIN_LED, HIGH);"])
    v._stable_features = [f1]
    code = assemble([f1])
    v._stable_panel.editor.setPlainText(code)
    v._refresh_stable_features()
    assert "f1" in v._stable_panel.editor.line_owners()
    # Simulated repair: one line rewritten (line count unchanged) ...
    repaired = code.replace("digitalWrite(PIN_LED, HIGH);",
                            "digitalWrite(PIN_LED, LOW );")
    v._code_target = "stable"
    v._tools_apply(repaired)
    assert "f1" in v._stable_panel.editor.line_owners()
    # ... and a structural repair (one line ADDED -> positional transfer).
    repaired2 = repaired.replace("void loop() {",
                                 "void loop() {\n  delay(1);")
    v._tools_apply(repaired2)
    assert "f1" in v._stable_panel.editor.line_owners()


def test_stable_delete_is_undoable():
    # Bug user 2026-07-07: a stable-side structured op (transfer / delete) must
    # be undoable. The stable window now has an undo index + undoable text set;
    # reverting the text to the indexed BEFORE state restores stable_features.
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature
    from ui.generation import assemble
    v = StudioView(); v._on_mode_changed("advanced")
    f1 = Feature(id="f1", prompt="led", loop_lines=["digitalWrite(13, HIGH);"])
    f2 = Feature(id="f2", prompt="buz", loop_lines=["tone(9, 440);"])
    v._stable_features = [f1, f2]
    before = assemble([f1, f2])
    ed = v._stable_panel.editor
    ed.blockSignals(True); ed.setPlainText(before); ed.blockSignals(False)
    v._refresh_stable_features()
    v.save_project = lambda *a, **k: None
    v._delete_stable_features({"f2"})
    assert [f.id for f in v._stable_features] == ["f1"]           # deleted
    assert "tone(9, 440);" not in ed.toPlainText()
    # simulate the native Ctrl+Z: text reverts to the indexed BEFORE state.
    ed.blockSignals(True); ed.setPlainText(before); ed.blockSignals(False)
    v._on_stable_edited()
    assert [f.id for f in v._stable_features] == ["f1", "f2"]     # restored
    assert "f2" in ed.line_owners()                              # owners restored too


def test_project_deleted_resets_stable_window():
    # Bug review 2026-07-06 #1: deleting the current project must reset the
    # STABLE model + editor, else its features/code leak to the next project.
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature
    from ui.generation import assemble
    v = StudioView(); v._on_mode_changed("advanced")
    f1 = Feature(id="f1", prompt="led", loop_lines=["digitalWrite(13, HIGH);"])
    v._stable_features = [f1]
    v._stable_panel.editor.setPlainText(assemble([f1]))
    v._stable_baseline = assemble([f1])
    v._refresh_stable_features()

    class _P:
        def __init__(self, p): self.path = p
    proj = _P("some/proj.promptuino.json")
    v._current_project = proj
    v.on_project_deleted(proj)
    assert v._stable_features == []                                   # model reset
    assert "digitalWrite(13, HIGH);" not in v._stable_panel.editor.toPlainText()


def test_stable_dropdown_grays_during_generation():
    # Bug review 2026-07-06 #4: the stable dropdown must gray out during a
    # generation / upload (not only when the stable window itself is veiled).
    from ui.studio_view import StudioView
    v = StudioView(); v._on_mode_changed("advanced")
    v._gen_busy = None; v._cu_running = False
    v._refresh_stable_features()
    assert not v._stable_panel.feature_dropdown._busy       # idle -> active
    v._gen_busy = "advanced"
    v._refresh_stable_features()
    assert v._stable_panel.feature_dropdown._busy           # generating -> grayed


def test_reset_comments_state_rechecks_and_clears():
    # Bug review 2026-07-06 #3: after a structural stable replacement the
    # « Comments » box is re-checked and the stale snapshot dropped.
    from ui.studio_view import StudioView
    v = StudioView(); v._on_mode_changed("advanced")
    chk = v._tools_chk("stable")
    v._loading = True; chk.setChecked(False); v._loading = False
    v._code_with_comments["stable"] = "X"
    v._stripped_at_decoche["stable"] = "Y"
    v._reset_comments_state("stable")
    assert chk.isChecked()
    assert v._code_with_comments["stable"] is None
    assert v._stripped_at_decoche["stable"] is None


def test_new_project_resets_both_windows():
    # BUG : « Nouveau projet » ne remettait pas a zero la fenetre stable
    # (fonctionnalites + code) ni le dropdown IA (fonctionnalites du projet
    # precedent encore affichees). Tout doit repartir vide.
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature
    v = StudioView()
    v._on_mode_changed("advanced")
    # Simule un projet precedent : features IA + stable + code stable.
    v._features = [Feature(id="f1", prompt="led")]
    v._stable_features = [Feature(id="f1", prompt="led")]
    v._code_panel.set_features(v._features)
    v._stable_panel.set_features(v._stable_features)
    v._stable_panel.editor.setPlainText("void loop(){ /* ancien code stable */ }\n")
    v._dirty = False                    # evite la modale « non enregistre »
    v._begin_inline_new_project()
    assert v._features == []
    assert v._stable_features == []
    # Dropdowns vides -> boutons desactives (0 fonctionnalite).
    assert not v._code_panel.feature_dropdown._btn.isEnabled()
    assert not v._stable_panel.feature_dropdown._btn.isEnabled()
    # Code stable de l'ancien projet efface, remplace par le squelette.
    st = v._stable_panel.editor.toPlainText()
    assert "ancien code stable" not in st
    assert v._is_template_or_scaffolded(st)


def test_intermediate_mode_allows_manual_editing():
    # #33 : l'edition manuelle est desormais LIBRE en Intermediaire (le verrou
    # `_edit_locked` par mode est retire). L'editeur ne doit etre ni edit-locked
    # ni read-only apres un passage en Intermediaire.
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("intermediate")
    assert v._editor._edit_locked is False
    assert not v._editor.isReadOnly()
    # Avance : deja editable (inchange).
    v._on_mode_changed("advanced")
    assert v._editor._edit_locked is False
    assert not v._editor.isReadOnly()


def test_readonly_popup_no_longer_wired():
    # #33 : le popup « passer en Avance » n'est plus branche sur edit_attempted
    # (sinon il s'ouvrirait sous le voile busy, ou l'editeur est read-only et
    # emet edit_attempted a chaque frappe -> conflit avec les voiles busy).
    from ui.studio_view import StudioView
    v = StudioView()
    assert v._editor.receivers(v._editor.edit_attempted) == 0


TESTS = [
    test_i18n_two_window_fields_all_langs,
    test_mode_switch_reparents_without_losing_content,
    test_stable_shows_template_before_generation,
    test_advanced_code_windows_are_taller,
    test_stable_upload_veils_stable_window_not_ai,
    test_ai_upload_veils_ai_window_not_stable,
    test_per_window_tools_target_isolation,
    test_transfer_copies_ai_code_to_stable,
    test_transfer_confirms_when_stable_differs,
    test_stable_upload_runs_without_ai_backend,
    test_save_and_load_stable_code_via_studio,
    test_load_project_restores_stable_editor,
    test_cancel_restores_the_active_window_button,
    test_mode_switch_blocked_during_operation,
    test_stable_schema_button_follows_stable_code,
    test_schema_button_follows_the_code_not_the_generation,
    test_stable_delete_only_touches_stable,
    test_regen_rejected_on_stable,
    test_transfer_dialog_apply_inherits_features,
    test_transfer_dialog_apply_reorders_ia_and_strips_metadata,
    test_transfer_dialog_cancel_touches_nothing,
    test_transfer_busy_guard_skips_dialog,
    test_transfer_block_two_chevrons_wired_and_centered,
    test_transfer_reflects_repaired_editor_not_stale_model,
    test_open_audit_runs_lint_and_offers_conformance,
    test_open_audit_without_features_uses_plain_audit,
    test_manual_repair_routes_code_to_stable,
    test_cascade_summary_lists_lines_when_no_model_summary,
    test_cascade_summary_uses_model_summary_when_present,
    test_manual_repair_preview_buffers_cascade_not_editor,
    test_manual_repair_done_reviews_buffer_without_applying,
    test_manual_repair_done_no_repair_reviews_original,
    test_manual_repair_done_ko_leaves_editor_and_shows_failure,
    test_run_repair_falls_back_to_audit_without_cli,
    test_can_reconstruct_predicate,
    test_reconstruct_applies_assembled_code,
    test_verify_failure_offers_reconstruct_then_skips_revert,
    test_verify_failure_reverts_when_reconstruct_declined,
    test_resync_after_repair_makes_model_canonical,
    test_resync_after_repair_noop_when_unfaithful,
    test_finalize_verify_success_resyncs_model,
    test_manual_repair_suppresses_journal_button,
    test_ia_upload_finished_resyncs_model,
    test_applied_repairs_dialog_is_readonly_consolidated,
    test_repairs_link_opens_applied_dialog,
    test_stable_tools_apply_keeps_attribution,
    test_stable_delete_is_undoable,
    test_project_deleted_resets_stable_window,
    test_stable_dropdown_grays_during_generation,
    test_reset_comments_state_rechecks_and_clears,
    test_new_project_resets_both_windows,
    test_intermediate_mode_allows_manual_editing,
    test_readonly_popup_no_longer_wired,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        t()
        passed += 1
    print(f"{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0)

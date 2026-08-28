"""
AI model selection view (second tab of the sidebar).

Three sections, each fronted by a radio button (all in one QButtonGroup):

  1. Cloud (your key)   — `_CloudSection`: pick an OpenAI-compatible provider
        from the registry (or "Custom"), enter an API key + model. For "Custom"
        a base-URL field is also revealed. The chosen provider id becomes the
        active `ai_config.backend_id`.
  2. Ollama (local)     — `_BackendSection("ollama")`: local model drop-down +
        server/model availability indicator. No key required.
  3. Claude Code (CLI)  — `_BackendSection("claude_code")`: availability
        indicator (CLI detected on PATH or not).

Selecting a radio (or picking a provider while Cloud is selected) sets
`ai_config.backend_id`, rebuilds the active backend via
`get_backend_instance()`, caches it, and emits `backend_activated`.
"""
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import (
    QApplication,
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QRadioButton, QButtonGroup,
    QLineEdit, QComboBox, QScrollArea, QCompleter, QSlider,
)

from .theme import (
    ColorScheme, theme_manager, radio_checkbox_qss, secondary_button_qss,
    combo_qss, selection_bg, input_qss, primary_button_qss, slider_qss
)
from .i18n import lang_manager, Strings
from .ai_config import ai_config, OLLAMA_NUM_CTX_STEPS
from .ai_backends import (
    BACKEND_DEFS, ClaudeCodeBackend,
    is_installed, is_server_running, is_model_available, list_local_models,
    get_backend_instance, PROVIDERS,
)


# Model-fetch error kind -> i18n string attribute on lang_manager.current.
_MODELS_ERR_KEYS = {
    "auth":         "ia_err_auth",
    "quota":        "ia_err_quota",
    "provider":     "ia_err_provider",
    "notfound":     "ia_err_notfound",
    "unsupported":  "ia_models_unsupported",
    "network":      "ia_err_network",
    "bad_response": "ia_err_bad_response",
    "empty":        "ia_models_none",
}


# ── Async model fetch worker ────────────────────────────────────────────────

class _ModelsWorker(QThread):
    """Fetches a cloud provider's model ids OFF the UI thread.

    Builds the backend via `get_backend_instance(provider_id)` and calls
    `.list_models_detailed()` so the UI can distinguish auth errors, network
    failures, unsupported /models endpoints, and empty results from success.
    Never blocks the UI thread.
    """

    finished_models = pyqtSignal(str, list, str)   # (provider_id, model_ids, error_kind)

    def __init__(self, provider_id: str, parent=None):
        super().__init__(parent)
        self._provider_id = provider_id

    def run(self):
        try:
            backend = get_backend_instance(self._provider_id)
            if backend is not None:
                models, kind = backend.list_models_detailed()
            else:
                models, kind = [], "network"
        except Exception:
            # Defensive: list_models_detailed never raises, but a build error might.
            models, kind = [], "bad_response"
        self.finished_models.emit(self._provider_id, list(models or []), kind)


# ── Shared field styles ─────────────────────────────────────────────────────
# Factored out so the Cloud section and the Ollama/Claude sections share the
# exact same look for inputs, combos and the primary "Save" button.

def _input_qss(c: ColorScheme) -> str:
    """Thin wrapper over theme.input_qss, kept so the many call sites below
    read unchanged. The style itself is the app's, not this view's."""
    return input_qss(c, padding="0 10px")


def _primary_btn_qss(c: ColorScheme) -> str:
    """Thin wrapper over theme.primary_button_qss, kept so the « Enregistrer »
    call sites read unchanged.

    Its hand-written copy hovered to `btn_primary_hover` (a paler shade of
    itself) instead of turning GREEN like every other button in the app --
    exactly the « les boutons ne se comportent pas tous pareil au survol »
    this refactor exists to fix. Metrics unchanged, so no button moves."""
    return primary_button_qss(c, padding="0 14px")


class _ModelCombo(QComboBox):
    """Drop-down list of Ollama models. Re-queries the local server on
    each opening of the menu to reflect the models actually available
    (an `ollama pull` while the app is running becomes visible without restart)."""

    def __init__(self, populate, parent=None):
        super().__init__(parent)
        self._populate = populate

    def showPopup(self):
        self._populate()
        super().showPopup()


# ── Cloud section (bring-your-own-key, OpenAI-compatible) ────────────────────

class _CloudSection(QWidget):
    """
    Cloud provider block: radio + title + subtitle, then indented content:
      - a provider combo (one item per registry preset + a final "Custom"),
      - an API-key field (password) + a single "Save" button that persists
        BOTH the key and the model for the selected provider,
      - an EDITABLE model combo (pick from the fetched list or type one;
        empty = provider default) with a loading status,
      - a muted disclaimer about free API tiers,
      - a base-URL field shown ONLY for "Custom" (bound to ai_config.custom_*),
      - a "get a key" link shown when the selected preset exposes a key_url.

    The model list is fetched ASYNCHRONOUSLY (see `_ModelsWorker`) — never on
    construction — when the key is saved, or the provider changes while a key
    already exists (also on load if a key already exists).

    Exposes `self._provider_combo`, `self._model_combo` and
    `selected_provider_id()`.
    Emits `activated` when the user clicks its radio or changes the provider
    while this section is selected (so IAView can re-activate the backend).
    """

    activated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # Reference to the in-flight model fetch worker (None when idle).
        # Kept alive so the QThread is not GC'd mid-run; a new fetch lets the
        # old one finish and ignores its (stale) result via provider-id match.
        self._models_worker: _ModelsWorker | None = None
        # Guard: stop the worker on app exit so Qt never destroys a running
        # QThread (mirrors the pattern in library_view.py).
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_worker)
        self._build()
        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)
        # Async, non-blocking: only fires if a key already exists for the
        # current provider. In tests (empty keyring) this is a no-op.
        self._maybe_fetch_models()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Radio (title)
        self.radio = QRadioButton()
        self.radio.setCursor(Qt.CursorShape.PointingHandCursor)
        root.addWidget(self.radio)
        root.addSpacing(6)

        # Indented content
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(28, 0, 0, 0)
        cl.setSpacing(0)

        self._lbl_subtitle = QLabel()
        self._lbl_subtitle.setWordWrap(True)
        cl.addWidget(self._lbl_subtitle)
        cl.addSpacing(10)

        # Provider combo
        provider_row = QHBoxLayout()
        provider_row.setContentsMargins(0, 0, 0, 0)
        provider_row.setSpacing(8)
        self._lbl_provider = QLabel()
        self._lbl_provider.setFixedWidth(70)
        provider_row.addWidget(self._lbl_provider)
        self._provider_combo = QComboBox()
        self._provider_combo.setFixedHeight(34)
        self._provider_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        for preset in PROVIDERS:
            self._provider_combo.addItem(preset.label, preset.id)
        self._provider_combo.addItem("Custom", "custom")
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        provider_row.addWidget(self._provider_combo, stretch=1)
        cl.addLayout(provider_row)
        cl.addSpacing(14)

        # API key + Save (the Save button persists key AND model)
        key_row = QHBoxLayout()
        key_row.setContentsMargins(0, 0, 0, 0)
        key_row.setSpacing(8)
        self._lbl_key = QLabel()
        self._lbl_key.setFixedWidth(70)
        key_row.addWidget(self._lbl_key)
        self._key_input = QLineEdit()
        self._key_input.setFixedHeight(34)
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        key_row.addWidget(self._key_input, stretch=1)
        self._btn_save = QPushButton()
        self._btn_save.setFixedHeight(34)
        self._btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_save.clicked.connect(self._on_save)
        key_row.addWidget(self._btn_save)
        cl.addLayout(key_row)
        cl.addSpacing(14)

        # Model selector (EDITABLE combo). Populated asynchronously via /models;
        # the user can also type a model id directly (current text = chosen model).
        model_row = QHBoxLayout()
        model_row.setContentsMargins(0, 0, 0, 0)
        model_row.setSpacing(8)
        self._lbl_model = QLabel()
        self._lbl_model.setFixedWidth(70)
        model_row.addWidget(self._lbl_model)
        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.setFixedHeight(34)
        self._model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        # Type-to-filter a (possibly long) model list: the completer matches
        # ANYWHERE in the id (not just the prefix), case-insensitive.
        _completer = self._model_combo.completer()
        if _completer is not None:
            _completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            _completer.setFilterMode(Qt.MatchFlag.MatchContains)
            _completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        model_row.addWidget(self._model_combo, stretch=1)
        cl.addLayout(model_row)
        cl.addSpacing(10)

        # Loading status for the async model fetch (hidden when idle).
        self._lbl_models_status = QLabel()
        self._lbl_models_status.setText("")
        cl.addWidget(self._lbl_models_status)

        # Disclaimer (always visible): some models have a free API tier.
        self._lbl_disclaimer = QLabel()
        self._lbl_disclaimer.setWordWrap(True)
        cl.addWidget(self._lbl_disclaimer)
        cl.addSpacing(8)

        # Base URL field (custom only) — kept in its own widget so it can be
        # shown/hidden as a whole row.
        self._base_row = QWidget()
        base_row = QHBoxLayout(self._base_row)
        base_row.setContentsMargins(0, 0, 0, 0)
        base_row.setSpacing(8)
        self._lbl_base = QLabel()
        self._lbl_base.setFixedWidth(70)
        base_row.addWidget(self._lbl_base)
        self._base_input = QLineEdit()
        self._base_input.setFixedHeight(34)
        base_row.addWidget(self._base_input, stretch=1)
        cl.addWidget(self._base_row)
        cl.addSpacing(6)

        # "Get a key" link (rich text) + save confirmation status
        self._lbl_link = QLabel()
        self._lbl_link.setTextFormat(Qt.TextFormat.RichText)
        self._lbl_link.setOpenExternalLinks(True)
        cl.addWidget(self._lbl_link)

        self._lbl_status = QLabel()
        self._lbl_status.setTextFormat(Qt.TextFormat.RichText)
        cl.addWidget(self._lbl_status)

        root.addWidget(content)

        # Initial field population for the default selection.
        self._reload_fields()

    # ── Selection helpers ────────────────────────────────────────

    def selected_provider_id(self) -> str:
        """The provider id stored as itemData of the current combo entry."""
        return self._provider_combo.currentData()

    def select_provider(self, provider_id: str):
        """Programmatically select `provider_id` in the combo (no activation).
        Also fetch its model list async if a key already exists (covers the
        active-provider restore at startup)."""
        idx = self._provider_combo.findData(provider_id)
        if idx >= 0:
            self._provider_combo.blockSignals(True)
            self._provider_combo.setCurrentIndex(idx)
            self._provider_combo.blockSignals(False)
            self._reload_fields()
            self._maybe_fetch_models()

    # ── Model combo helpers ───────────────────────────────────────

    def _model_text(self) -> str:
        """Current chosen model = the editable combo's line-edit text."""
        return self._model_combo.currentText().strip()

    def _set_model_text(self, text: str):
        """Set the combo's current text without firing signals or inserting an
        item (keeps it purely as a typed value when not in the list)."""
        self._model_combo.blockSignals(True)
        self._model_combo.setCurrentText(text or "")
        self._model_combo.blockSignals(False)

    # ── Async model list ──────────────────────────────────────────

    def _maybe_fetch_models(self):
        """Trigger an async fetch ONLY if a key already exists for the current
        provider. Used on load and on provider change — never blocks."""
        pid = self.selected_provider_id()
        if pid and ai_config.api_key(pid):
            self._start_models_fetch(pid)

    def _start_models_fetch(self, provider_id: str):
        """Spawn a `_ModelsWorker` for `provider_id`. A previous in-flight
        worker is left to finish; its result is ignored because the slot
        checks the provider id against the live selection."""
        s = lang_manager.current
        self._lbl_models_status.setText(s.ia_models_loading)

        worker = _ModelsWorker(provider_id, self)
        worker.finished_models.connect(self._on_models_fetched)
        # Drop our reference once Qt is done with the thread object.
        worker.finished.connect(lambda w=worker: self._clear_worker(w))
        # Schedule deferred deletion so superseded workers are freed promptly.
        worker.finished.connect(worker.deleteLater)
        self._models_worker = worker
        worker.start()

    def _clear_worker(self, worker: "_ModelsWorker"):
        if self._models_worker is worker:
            self._models_worker = None

    def _stop_worker(self):
        """Stop the in-flight models fetch on app exit (avoid destroying a
        running QThread). Mirrors the pattern in library_view.py."""
        w = self._models_worker
        if w is not None and w.isRunning():
            w.requestInterruption()
            w.wait(2000)

    def _on_models_fetched(self, provider_id: str, models: list, error_kind: str):
        """Repopulate the combo with fetched ids, preserving the user's current
        text. On failure, show the appropriate error message in the status label."""
        # Ignore stale results — the user switched provider while the fetch was
        # in flight. Don't touch any widget: the live provider's state is fine.
        if provider_id != self.selected_provider_id():
            return

        s = lang_manager.current
        current = self._model_text()

        if not models:
            # Clear any items left over from a previous provider so they never
            # linger when the new fetch returns empty (e.g. wrong key, network
            # error). The line-edit text (user's typed model) is preserved.
            self._model_combo.blockSignals(True)
            self._model_combo.clear()
            self._model_combo.setCurrentText(current)
            self._model_combo.blockSignals(False)
            attr = _MODELS_ERR_KEYS.get(error_kind, "ia_models_none")
            self._lbl_models_status.setText(getattr(s, attr))
            # Auto-clear only for the benign "empty" case; real errors stay
            # visible until the next fetch so the user knows what went wrong.
            if error_kind in ("", "empty"):
                QTimer.singleShot(4000, lambda: self._lbl_models_status.setText(""))
            return

        # Preferred selection: saved model for this provider, else the value
        # already typed/shown, else the provider default.
        is_custom = (provider_id == "custom")
        saved = ai_config.custom_model if is_custom else ai_config.model_for(provider_id)
        preferred = current or saved

        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        self._model_combo.addItems(models)
        # PRESERVE the user's text: re-apply it even if absent from the list.
        if preferred in models:
            self._model_combo.setCurrentText(preferred)
        else:
            self._model_combo.setCurrentText(current)
        self._model_combo.blockSignals(False)
        self._lbl_models_status.setText("")

    # ── Field (re)loading ─────────────────────────────────────────

    def _reload_fields(self):
        """Reload key/model/base-URL fields from ai_config for the current
        provider, and toggle the base-URL row + the get-key link visibility."""
        pid = self.selected_provider_id()
        is_custom = (pid == "custom")

        # Key is stored per provider id (incl. "custom").
        self._key_input.blockSignals(True)
        self._key_input.setText(ai_config.api_key(pid))
        self._key_input.blockSignals(False)

        # Model + base URL: custom uses dedicated config slots.
        # Drop all dropdown items so the previous provider's model list never
        # lingers after a provider switch; restore the saved model as typed text.
        saved_model = ai_config.custom_model if is_custom else ai_config.model_for(pid)
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        self._model_combo.setCurrentText(saved_model or "")
        self._model_combo.blockSignals(False)

        self._base_input.blockSignals(True)
        self._base_input.setText(ai_config.custom_base_url)
        self._base_input.blockSignals(False)
        self._base_row.setVisible(is_custom)

        self._refresh_link()

    def _refresh_link(self):
        """Show the 'get a key' link when the selected preset has a key_url."""
        pid = self.selected_provider_id()
        preset = next((p for p in PROVIDERS if p.id == pid), None)
        s = lang_manager.current
        if preset is not None and preset.key_url:
            self._lbl_link.setText(
                f'<a href="{preset.key_url}" '
                f'style="color:{theme_manager.current.signal_ok};">'
                f'{s.ia_get_key_link}</a>'
            )
            self._lbl_link.show()
        else:
            self._lbl_link.clear()
            self._lbl_link.hide()

    # ── Slots ─────────────────────────────────────────────────────

    def _on_provider_changed(self, _idx: int):
        """Switching provider reloads fields, and — if this section is the
        active one — re-activates the backend for the new provider.
        Also fetch the model list if a key already exists for that provider."""
        self._reload_fields()
        self._maybe_fetch_models()
        if self.radio.isChecked():
            self.activated.emit()

    def _on_save(self):
        """Persist BOTH the API key and the model for the selected provider."""
        pid = self.selected_provider_id()
        is_custom = (pid == "custom")
        key = self._key_input.text().strip()
        model = self._model_text()

        ai_config.set_api_key(pid, key)
        if is_custom:
            ai_config.custom_model = model
            ai_config.custom_base_url = self._base_input.text().strip()
        else:
            ai_config.set_model(pid, model)

        s = lang_manager.current
        self._lbl_status.setText(
            f'<span style="color:{theme_manager.current.signal_ok};">✓ {s.ia_key_saved}</span>'
        )
        QTimer.singleShot(3000, lambda: self._lbl_status.setText(""))

        # Now that the key is saved, (re)fetch the model list for this provider.
        if key:
            self._start_models_fetch(pid)

        # If this section is the active backend, rebuild it so the new
        # credentials/model take effect immediately.
        if self.radio.isChecked():
            self.activated.emit()

    # ── Theme ──────────────────────────────────────────────────────

    def apply_theme(self, c: ColorScheme):
        # Section title radio: the app's radio, bold. `font_weight` is the
        # helper's own parameter -- the extra rule this used to append by hand
        # produced a byte-identical render, minus the local QSS.
        self.radio.setStyleSheet(radio_checkbox_qss(c, font_pt=14, font_weight=700))
        self._lbl_subtitle.setStyleSheet(f"color: {c.text_secondary}; font-size: 10pt;")

        lbl_style = f"color: {c.text_secondary}; font-size: 10pt;"
        for lbl in (self._lbl_provider, self._lbl_key, self._lbl_model, self._lbl_base):
            lbl.setStyleSheet(lbl_style)

        input_style = _input_qss(c)
        for inp in (self._key_input, self._base_input):
            inp.setStyleSheet(input_style)
        self._provider_combo.setStyleSheet(combo_qss(c))
        # Editable model combo: combo QSS owns the frame and the drop-down area.
        # The embedded line edit is transparent/borderless so it doesn't paint
        # over the combo frame or hide the arrow.
        self._model_combo.setStyleSheet(combo_qss(c))
        if self._model_combo.lineEdit() is not None:
            self._model_combo.lineEdit().setStyleSheet(
                f"QLineEdit {{ background: transparent; border: none; "
                f"color: {c.text_primary}; padding: 0 6px; "
                f"selection-background-color: {selection_bg(c)}; "
                f"selection-color: {c.text_primary}; }}")
        self._btn_save.setStyleSheet(_primary_btn_qss(c))
        self._lbl_status.setStyleSheet("font-size: 9pt;")
        self._lbl_models_status.setStyleSheet(f"color: {c.text_secondary}; font-size: 9pt;")
        self._lbl_disclaimer.setStyleSheet(f"color: {c.text_secondary}; font-size: 9pt;")
        self._lbl_link.setStyleSheet("font-size: 9pt;")
        self._refresh_link()   # re-color the link with the new theme

    # ── Language ────────────────────────────────────────────────────

    def apply_lang(self, s: Strings):
        self.radio.setText(s.ia_cloud_provider_title)
        self._lbl_subtitle.setText(s.ia_cloud_provider_subtitle)
        self._lbl_provider.setText(s.ia_provider_label)
        self._lbl_key.setText(s.ia_api_key_label)
        self._key_input.setPlaceholderText(s.ia_api_key_placeholder)
        self._btn_save.setText(s.ia_save_key)
        self._lbl_model.setText(s.ia_model_label)
        if self._model_combo.lineEdit() is not None:
            self._model_combo.lineEdit().setPlaceholderText(s.ia_model_placeholder)
        self._lbl_disclaimer.setText(s.ia_model_disclaimer)
        self._lbl_base.setText(s.ia_base_url_label)
        self._refresh_link()


# ── Section backend (Ollama + Claude Code CLI) ──────────────────────────────

class _BackendSection(QWidget):
    """
    Block for a non-cloud backend: radio + title, indented content.
    For Ollama: drop-down list of local models + availability indicator.
    For Claude CLI: availability indicator only.
    """

    # Emitted (Ollama only) when the user chooses another model.
    model_changed = pyqtSignal(str)

    def __init__(self, backend_id: str, parent=None):
        super().__init__(parent)
        self.backend_id = backend_id
        # Cached availability state. `apply_lang` simply
        # re-renders from this cache to avoid any network call
        # (the Ollama check can block the UI for up to 3 s).
        self._availability_state: tuple[str, str | None] | None = None
        self._build()
        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)
        self.refresh_availability()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Radio button (title)
        self.radio = QRadioButton()
        self.radio.setCursor(Qt.CursorShape.PointingHandCursor)
        root.addWidget(self.radio)
        root.addSpacing(6)

        # Indented content
        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(28, 0, 0, 0)
        content_layout.setSpacing(0)

        self._lbl_subtitle = QLabel()
        self._lbl_subtitle.setWordWrap(True)
        content_layout.addWidget(self._lbl_subtitle)
        content_layout.addSpacing(10)

        self._is_ollama = (self.backend_id == "ollama")

        if self._is_ollama:
            # ── Ollama: drop-down list of models + server indicator ──
            model_row = QHBoxLayout()
            model_row.setContentsMargins(0, 0, 0, 0)
            model_row.setSpacing(8)

            self._lbl_model_label = QLabel()
            self._lbl_model_label.setFixedWidth(56)
            model_row.addWidget(self._lbl_model_label)

            self._model_combo = _ModelCombo(self._populate_models)
            self._model_combo.setFixedHeight(34)
            self._model_combo.setCursor(Qt.CursorShape.PointingHandCursor)
            self._model_combo.textActivated.connect(self._on_model_selected)
            model_row.addWidget(self._model_combo, stretch=1)
            # Recuperer un modele demandait un TERMINAL (`ollama pull`),
            # ce qui exclut le public vise. Ollama expose
            # `POST /api/pull` : c'est le meme geste, envoye par un
            # programme (TODO #79).
            self._btn_dl_model = QPushButton()
            self._btn_dl_model.setFixedHeight(34)
            self._btn_dl_model.setCursor(Qt.CursorShape.PointingHandCursor)
            self._btn_dl_model.setAutoDefault(False)
            self._btn_dl_model.clicked.connect(self._ouvrir_telechargement)
            model_row.addWidget(self._btn_dl_model)

            content_layout.addLayout(model_row)
            content_layout.addSpacing(6)

            self._lbl_availability = QLabel()
            self._lbl_availability.setWordWrap(True)
            self._lbl_availability.setTextFormat(Qt.TextFormat.RichText)
            content_layout.addWidget(self._lbl_availability)

            content_layout.addSpacing(4)
            self._lbl_model_status = QLabel()
            content_layout.addWidget(self._lbl_model_status)

            content_layout.addSpacing(12)
            self._lbl_ctx_label = QLabel()
            content_layout.addWidget(self._lbl_ctx_label)

            ctx_row = QHBoxLayout()
            ctx_row.setContentsMargins(0, 0, 0, 0)
            ctx_row.setSpacing(8)
            self._ctx_slider = QSlider(Qt.Orientation.Horizontal)
            self._ctx_slider.setMinimum(0)
            self._ctx_slider.setMaximum(len(OLLAMA_NUM_CTX_STEPS) - 1)
            self._ctx_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
            self._ctx_slider.setTickInterval(1)
            self._ctx_slider.setPageStep(1)
            self._ctx_slider.setSingleStep(1)
            self._ctx_slider.setFixedWidth(168)
            try:
                idx = OLLAMA_NUM_CTX_STEPS.index(ai_config.ollama_num_ctx)
            except ValueError:
                idx = OLLAMA_NUM_CTX_STEPS.index(8192)
            self._ctx_slider.setValue(idx)
            self._ctx_slider.setCursor(Qt.CursorShape.PointingHandCursor)
            self._ctx_slider.valueChanged.connect(self._on_ctx_changed)
            ctx_row.addWidget(self._ctx_slider)

            self._lbl_ctx_value = QLabel(f"{OLLAMA_NUM_CTX_STEPS[idx] // 1024}k tokens")
            self._lbl_ctx_value.setMinimumWidth(80)
            ctx_row.addWidget(self._lbl_ctx_value)
            ctx_row.addStretch()
            content_layout.addLayout(ctx_row)

            self._lbl_ctx_help = QLabel()
            self._lbl_ctx_help.setWordWrap(True)
            content_layout.addWidget(self._lbl_ctx_help)

        else:
            # ── Claude Code CLI: availability indicator ──────
            self._lbl_availability = QLabel()
            content_layout.addWidget(self._lbl_availability)

        root.addWidget(self._content)

    # ── Ollama model selection ────────────────────────────────

    def _populate_models(self):
        """(Re)fills the drop-down list with the local models + the saved
        model (even if it is no longer downloaded, so it stays selected).
        Does not emit `textActivated`: programmatic selection only."""
        saved = ai_config.ollama_model
        models = list_local_models()
        if saved and saved not in models:
            models = [saved] + models
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        self._model_combo.addItems(models)
        if saved in models:
            self._model_combo.setCurrentText(saved)
        self._model_combo.blockSignals(False)

    def _on_model_selected(self, text: str):
        model = text.strip()
        if not model:
            return
        ai_config.ollama_model = model   # persists + emits ai_config.changed
        s = lang_manager.current
        self._lbl_model_status.setText(f'<span style="color:{theme_manager.current.signal_ok};">✓ {s.ia_key_saved}</span>')
        QTimer.singleShot(3000, lambda: self._lbl_model_status.setText(""))
        self.refresh_availability()
        self.model_changed.emit(model)

    def _on_ctx_changed(self, idx: int):
        value = OLLAMA_NUM_CTX_STEPS[idx]
        self._lbl_ctx_value.setText(f"{value // 1024}k tokens")
        ai_config.ollama_num_ctx = value

    # ── Public API ───────────────────────────────────────────

    def load_key(self):
        """Loads the current value from ai_config into the field.
        For Ollama, (re)populates the model drop-down."""
        if self._is_ollama:
            self._populate_models()

    def _ouvrir_telechargement(self):
        """Ouvre le telechargeur ; a la fin, la liste locale est relue.

        ⚠️ On ne force AUCUNE selection : l'utilisateur peut telecharger un
        modele pour plus tard sans changer celui qu'il utilise.
        """
        from .model_download_dialog import ModelDownloadDialog
        dlg = ModelDownloadDialog(self)
        dlg.modele_installe.connect(lambda _n: self._populate_models())
        # La suppression change la liste ET peut retirer le modele actif :
        # le combo se recharge, et refresh_availability (apres exec) fera
        # suivre la pastille de la barre d'etat (#80).
        dlg.modele_supprime.connect(lambda _n: self._populate_models())
        dlg.exec()
        self.refresh_availability()

    def showEvent(self, ev):
        """Re-verifie l'etat CHAQUE FOIS que la section redevient visible.

        ⚠️ Sans ceci, le message << ouvrez l'application Ollama, puis revenez
        ici >> etait un mensonge : rien ne re-verifiait quoi que ce soit, et
        l'utilisateur revenait sur un libelle fige jusqu'au redemarrage de
        Promptuino. Il devait donc suivre un conseil qui ne pouvait pas
        marcher -- releve par l'utilisateur le 2026-08-28.

        Le controle est mesure a 27 ms serveur allume ; il est malgre tout
        differe d'un tour de boucle pour que l'onglet s'affiche d'abord.
        """
        super().showEvent(ev)
        QTimer.singleShot(0, self.refresh_availability)

    def refresh_availability(self):
        """Recomputes the availability state then re-renders the label.

        Performs the slow calls (Ollama HTTP, shutil.which Claude CLI).
        Only to be called when a re-check is really needed — not on
        every language change (use `_render_availability` for
        that case).
        """
        if self._is_ollama:
            model = self._model_combo.currentText().strip() or ai_config.ollama_model
            if not is_server_running():
                # ⚠️ Deux situations que l'app confondait en une seule :
                # << pas installe >> et << installe mais arrete >>. Le
                # message unique disait << executez : ollama serve >>, ce
                # qui ne parle qu'a quelqu'un qui a DEJA Ollama -- pour un
                # enseignant qui decouvre l'app, c'etait un cul-de-sac
                # (TODO #79). `shutil.which` tranche, comme pour le CLI
                # Claude juste en dessous.
                # `shutil.which` seul ratait un Ollama installe APRES le
                # demarrage de l'app -- c'est-a-dire juste apres que
                # l'utilisateur ait suivi notre lien. `is_installed`
                # regarde aussi les emplacements par defaut.
                installe = is_installed()
                self._availability_state = (
                    "ollama_server_down" if installe
                    else "ollama_not_installed", None)
            elif not is_model_available(model):
                self._availability_state = ("ollama_model_missing", model)
            else:
                self._availability_state = ("ollama_ok", None)
        else:
            available = ClaudeCodeBackend().is_available()
            self._availability_state = ("cli_ok" if available else "cli_missing", None)

        # La pastille de la barre d'etat lit ce cache (TODO #80) : on ne
        # publie que si CE backend est l'actif -- il y a une section par
        # backend, et publier celle d'un backend non selectionne mentirait.
        if self.backend_id == ai_config.backend_id:
            from .ai_status import ai_status
            ai_status.set_state(self._availability_state[0])

        self._render_availability()

    def _render_availability(self):
        """Re-renders the availability label from the cached state.
        Without network or system call — safe to call from apply_lang."""
        if self._availability_state is None:
            return
        s = lang_manager.current
        kind, extra = self._availability_state

        if kind == "ollama_not_installed":
            txt = (f'<span style="color:{theme_manager.current.signal_error};">'
                   f'&#9679; {s.ia_ollama_not_installed}</span>')
        elif kind == "ollama_server_down":
            txt = f'<span style="color:{theme_manager.current.signal_error};">&#9679; {s.ia_ollama_not_running}</span>'
        elif kind == "ollama_model_missing":
            txt = (
                f'<span style="color:{theme_manager.current.signal_warn};">&#9679; '
                f'{s.ia_ollama_model_missing} {extra}</span>'
            )
        elif kind == "ollama_ok":
            txt = f'<span style="color:{theme_manager.current.signal_ok};">&#9679; {s.ia_ollama_running}</span>'
        elif kind == "cli_ok":
            txt = f'<span style="color:{theme_manager.current.signal_ok};">&#9679; {s.ia_claude_available}</span>'
        elif kind == "cli_missing":
            txt = f'<span style="color:{theme_manager.current.signal_error};">&#9679; {s.ia_claude_unavailable}</span>'
        else:
            return

        self._lbl_availability.setText(txt)
        self._lbl_availability.setTextFormat(Qt.TextFormat.RichText)
        # Le message << pas installe >> porte un lien vers ollama.com :
        # sans ceci, il serait souligne mais inerte.
        self._lbl_availability.setOpenExternalLinks(True)

    # ── Theme ──────────────────────────────────────────────────

    def apply_theme(self, c: ColorScheme):
        # Radio (AI backend selection): agreed centralized style (white/gray
        # wireframe indicator -> GREEN on hover AND when checked) + bold preserved,
        # now through the helper's `font_weight` rather than a rule appended here.
        self.radio.setStyleSheet(radio_checkbox_qss(c, font_pt=14, font_weight=700))
        self._lbl_subtitle.setStyleSheet(f"color: {c.text_secondary}; font-size: 10pt;")

        if self._is_ollama:
            self._lbl_model_label.setStyleSheet(f"color: {c.text_secondary}; font-size: 10pt;")
            self._model_combo.setStyleSheet(combo_qss(c))
            self._lbl_model_status.setStyleSheet("font-size: 9pt;")
            self._lbl_ctx_label.setStyleSheet(
                f"color: {c.text_secondary}; font-size: 10pt; font-weight: 600;")
            self._lbl_ctx_value.setStyleSheet(
                f"color: {c.text_primary}; font-size: 9pt;")
            self._lbl_ctx_help.setStyleSheet(
                f"color: {c.text_secondary}; font-size: 9pt;")
            self._ctx_slider.setStyleSheet(slider_qss(c))

    # ── Language ─────────────────────────────────────────────────

    def apply_lang(self, s: Strings):
        names = {
            "claude_code": "Claude Code (CLI)",
            "ollama":      "Ollama (local)",
        }
        subtitles = {
            "claude_code": s.ia_claude_subtitle,
            "ollama":      s.ia_ollama_subtitle,
        }
        self.radio.setText(names[self.backend_id])
        self._lbl_subtitle.setText(subtitles[self.backend_id])

        if self._is_ollama:
            self._lbl_model_label.setText(s.ia_ollama_model_label)
            self._btn_dl_model.setText(s.md_download)
            self._lbl_ctx_label.setText(s.ia_ollama_ctx_label)
            self._lbl_ctx_help.setText(s.ia_ollama_ctx_help)
        # No refresh_availability here: would make a blocking HTTP call
        # to Ollama (up to 3 s) on every language change.
        self._render_availability()


# ── Main view ─────────────────────────────────────────────────────────────

class IAView(QWidget):

    backend_activated = pyqtSignal(object)  # emits the active AIBackend instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sections: dict[str, _BackendSection] = {}
        self._cloud: _CloudSection | None = None
        self._active_backend = None
        self._build()
        self._load_state()
        # Publie l'etat du backend ACTIF des la construction (TODO #80) : la
        # vue etant construite au demarrage, la pastille de la barre d'etat a
        # une vraie valeur sans que l'utilisateur ouvre jamais cet onglet.
        self._publier_etat()
        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)

    # ── Construction ──────────────────────────────────────────

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self._scroll)

        self._card = QWidget()
        self._card.setFixedWidth(540)
        container = QWidget()
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self._card, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._scroll.setWidget(container)

        layout = QVBoxLayout(self._card)
        layout.setContentsMargins(0, 40, 0, 40)
        layout.setSpacing(0)

        self._group = QButtonGroup(self)
        idx = 0

        # 1. Cloud (bring-your-own-key)
        self._cloud = _CloudSection()
        self._cloud.activated.connect(self._activate_cloud)
        self._group.addButton(self._cloud.radio, idx)
        idx += 1
        layout.addWidget(self._cloud)
        self._add_separator(layout)

        # 2 + 3. Ollama, Claude Code (special non-cloud backends)
        for i, (backend_id, _cls) in enumerate(BACKEND_DEFS):
            section = _BackendSection(backend_id)
            self._sections[backend_id] = section
            self._group.addButton(section.radio, idx)
            idx += 1
            if backend_id == "ollama":
                section.model_changed.connect(self._on_ollama_model_changed)
            layout.addWidget(section)
            # No separator after the last backend section (nothing follows it).
            if i < len(BACKEND_DEFS) - 1:
                self._add_separator(layout)

        layout.addStretch()

        self._group.buttonClicked.connect(self._on_radio_clicked)

    def _add_separator(self, layout: QVBoxLayout):
        layout.addSpacing(24)
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setObjectName("sep")
        layout.addWidget(sep)
        layout.addSpacing(24)

    # ── Initialization ────────────────────────────────────────

    def _load_state(self):
        """Checks the radio of the active backend and loads the keys."""
        for section in self._sections.values():
            section.load_key()

        active_id = ai_config.backend_id
        if active_id in self._sections:
            self._sections[active_id].radio.setChecked(True)
        elif self._is_cloud_id(active_id):
            # Cloud provider (registry id or "custom"): select the Cloud radio
            # and point the combo at the active provider.
            self._cloud.radio.setChecked(True)
            self._cloud.select_provider(active_id)

    @staticmethod
    def _is_cloud_id(backend_id: str) -> bool:
        return backend_id == "custom" or any(p.id == backend_id for p in PROVIDERS)

    # ── Slots ─────────────────────────────────────────────────

    def _on_radio_clicked(self, btn):
        """Clicking a radio directly activates the chosen backend
        (no more intermediate « Activer » button)."""
        if btn is self._cloud.radio:
            self._activate_cloud()
            return

        checked_id = self._get_checked_id()
        if not checked_id or checked_id == ai_config.backend_id:
            return
        ai_config.backend_id = checked_id
        backend = get_backend_instance(ai_config.backend_id)
        self._active_backend = backend
        self._publier_etat()
        self.backend_activated.emit(backend)

    def _publier_etat(self):
        """Publie vers la pastille l'etat du backend COURANT, sans reseau.

        - ollama / claude_code : le cache que leur section a deja calcule ;
        - cloud / custom : la seule chose verifiable sans reseau est la
          presence d'une cle (ou d'une URL pour « custom »). On ne pretend
          jamais que le service repond -- seulement que la configuration
          existe. Lire le trousseau coute quelques millisecondes, et
          seulement ICI (changement de backend), jamais dans le _refresh de
          la barre d'etat.
        """
        from .ai_status import ai_status
        bid = ai_config.backend_id
        section = self._sections.get(bid)
        if section is not None and section._availability_state is not None:
            ai_status.set_state(section._availability_state[0])
            return
        if bid == "custom":
            ok = bool(ai_config.custom_base_url)
        elif any(p.id == bid for p in PROVIDERS):
            ok = bool(ai_config.api_key(bid))
        else:
            ai_status.set_state(None)      # on ne sait pas -> pastille grise
            return
        ai_status.set_state("cloud_key_ok" if ok else "cloud_key_missing")

    def _activate_cloud(self):
        """Activate the cloud provider currently selected in the combo."""
        provider_id = self._cloud.selected_provider_id()
        if not provider_id:
            return
        # Ensure the Cloud radio reflects the active state.
        if not self._cloud.radio.isChecked():
            self._cloud.radio.setChecked(True)
        ai_config.backend_id = provider_id
        backend = get_backend_instance(ai_config.backend_id)
        self._active_backend = backend
        self._publier_etat()
        self.backend_activated.emit(backend)

    def _on_ollama_model_changed(self, model: str):
        """The user chose another Ollama model in the list.
        If Ollama is the active backend, reloads the instance so that the
        chat/generation use the right model. (The status bar updates itself
        via the `ai_config.changed` signal emitted by the `ollama_model`
        setter.)"""
        if ai_config.backend_id == "ollama":
            backend = get_backend_instance("ollama")
            self._active_backend = backend
            self.backend_activated.emit(backend)

    def get_active_backend(self):
        """Returns the active backend instance (or None if not configured).

        The instance is cached: two successive calls return
        the same object.  `_on_radio_clicked` also updates this cache to
        guarantee consistency with the `backend_activated` signal.
        """
        if self._active_backend is None:
            # Lazy first-call: build + cache.
            self._active_backend = get_backend_instance(ai_config.backend_id)
        return self._active_backend

    def _get_checked_id(self) -> str:
        """Return the backend id of the checked non-cloud section (Ollama /
        Claude Code). Cloud is handled separately via the combo."""
        for backend_id, section in self._sections.items():
            if section.radio.isChecked():
                return backend_id
        return ""

    # ── Separators ───────────────────────────────────────────

    def _apply_sep_color(self, c: ColorScheme):
        for sep in self._card.findChildren(QWidget):
            if sep.objectName() == "sep":
                sep.setStyleSheet(f"background-color: {c.border};")

    # ── Theme ─────────────────────────────────────────────────

    def apply_theme(self, c: ColorScheme):
        p = self.palette()
        p.setColor(QPalette.ColorRole.Window, QColor(c.main_bg))
        self.setPalette(p)
        self.setAutoFillBackground(True)
        self._scroll.setStyleSheet("background: transparent; border: none;")
        self._scroll.widget().setStyleSheet(f"background: {c.main_bg};")
        self._apply_sep_color(c)

        self._cloud.apply_theme(c)
        for section in self._sections.values():
            section.apply_theme(c)

    # ── Language ────────────────────────────────────────────────

    def apply_lang(self, s: Strings):
        self._cloud.apply_lang(s)
        for section in self._sections.values():
            section.apply_lang(s)

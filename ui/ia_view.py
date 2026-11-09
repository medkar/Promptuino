"""
AI model selection view (second tab of the sidebar).

Three sections, each fronted by a radio button (all in one QButtonGroup):

  1. Cloud (your key)   — `_CloudSection`: pick an OpenAI-compatible provider
        from the registry (or "Custom"), enter an API key + model. For "Custom"
        a base-URL field is also revealed. The chosen provider id becomes the
        active `ai_config.backend_id`.
  2. Ollama (local)     — `_BackendSection("ollama")`: local model drop-down +
        server/model availability indicator. No key required.
  3. Optional extra backends (supplied by the optional `ui.ai_backends.dev`
        package, absent from an ordinary installation) — one
        `_BackendSection` each: availability indicator only.

Selecting a radio (or picking a provider while Cloud is selected) sets
`ai_config.backend_id`, rebuilds the active backend via
`get_backend_instance()`, caches it, and emits `backend_activated`.
"""
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QPalette, QColor, QDesktopServices
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QApplication,
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QRadioButton, QButtonGroup,
    QLineEdit, QComboBox, QScrollArea, QCompleter, QSlider, QSizePolicy,
    QStackedWidget,
)

from .theme import (
    ColorScheme, theme_manager, radio_checkbox_qss, secondary_button_qss,
    combo_qss, selection_bg, input_qss, primary_button_qss, slider_qss
)
from .i18n import lang_manager, Strings
from .ai_config import ai_config
from . import contexte
from .contexte_curseur import CurseurContexte
from .molette import ComboSansMolette
from .reflexion_interrupteur import InterrupteurReflexion
from .ai_backends import (
    special_backends, extra_backend,
    is_installed, is_server_running, is_model_available, list_local_models,
    is_process_running, start_server,
    get_backend_instance, backend_requires_key, PROVIDERS, LOCAL_BACKENDS,
)
from .ai_backends import lmstudio_api
from . import lmstudio_models
from . import ollama_models
from . import memoire_modeles
from . import debordement
from . import erreurs_chargement
from . import reflexion


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


class _ProbeWorker(QThread):
    """Vérifie qu'un modèle CHOISI répond réellement, HORS du fil d'interface.

    Le listing d'un fournisseur ne dit pas ce qui est accessible (mesuré le
    2026-09-03 : `gemini-2.5-flash` figure dans celui de Google, annoncé
    `generateContent`, et renvoie 404 à l'usage). La seule façon de savoir
    est d'essayer — un appel réel et minimal, ici, jamais sur le fil UI.
    Même motif que `_ModelsWorker` ci-dessus.
    """

    finished_probe = pyqtSignal(str, str, bool, str)  # (provider_id, model, ok, message)

    def __init__(self, provider_id: str, model: str, parent=None):
        super().__init__(parent)
        self._provider_id = provider_id
        self._model = model

    def run(self):
        try:
            backend = get_backend_instance(self._provider_id)
            if backend is not None and hasattr(backend, "probe_model"):
                ok, message = backend.probe_model()
            else:
                ok, message = False, ""
        except Exception as e:
            # Defensif : probe_model ne leve jamais, mais get_backend_instance pourrait.
            ok, message = False, f"{type(e).__name__}: {e}"
        self.finished_probe.emit(self._provider_id, self._model, ok, message)


# ── Shared field styles ─────────────────────────────────────────────────────
# Factored out so the Cloud section and the Ollama/extra sections share the
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


class _ModelCombo(ComboSansMolette):
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
        # Idem pour la sonde (_ProbeWorker) : reference gardee vivante,
        # nouvelle sonde laisse l'ancienne finir.
        self._probe_worker: _ProbeWorker | None = None
        # TOUS les fils lances et pas encore finis, remplaces compris : c'est
        # ce que `_stop_worker` doit traiter a la sortie (audit 2026-11-06).
        self._workers_vivants: set = set()
        # Couples (fournisseur, modele) dont la sonde est EN VOL : l'animation
        # « Verification... » ne vaut que pour le couple AFFICHE (audit
        # 2026-11-06 : elle survivait a un changement de fournisseur, et une
        # sonde perimee qui revenait coupait celle encore en cours).
        self._sondes_en_vol: set[tuple[str, str]] = set()
        # (fournisseur, modele) deja verifies dans CETTE session -- la sonde
        # coute un appel reseau reel, on ne la relance jamais pour le meme
        # couple (spec 2026-09-03, B).
        self._probed_pairs: set[tuple[str, str]] = set()
        # Verdicts de sonde, UN PAR COUPLE (fournisseur, modele). Un seul
        # << dernier verdict >> ne suffisait pas : revenir sur un modele deja
        # sonde laissait affiche le message du PRECEDENT, la deduplication
        # empechant toute nouvelle sonde (QA AI1, 2026-09-04).
        self._probe_verdicts: dict[tuple[str, str], tuple[bool, str]] = {}
        # Animation du << Verification... >> : la sonde dure jusqu'a 30 s
        # (mesure sur gemini-flash-latest), un texte fige laisse croire que
        # l'app est bloquee.
        self._probe_timer: QTimer | None = None
        self._probe_dots = 0
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
        self._provider_combo = ComboSansMolette()
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
        self._model_combo = ComboSansMolette()
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
        # Le modèle se persiste À LA SÉLECTION, sans bouton. Avant, il ne
        # l'était qu'au clic sur « Enregistrer » — un bouton situé dans la
        # ligne de la CLÉ D'API : on changeait de modèle et on repartait en
        # croyant l'avoir changé, l'app continuant d'utiliser l'ancien
        # (spec 2026-09-03, défaut D).
        self._model_combo.activated.connect(self._on_model_chosen)
        _model_edit = self._model_combo.lineEdit()
        if _model_edit is not None:
            # `editingFinished` = Entrée ou perte du focus. PAS
            # `textEdited`, qui écrirait un id incomplet à chaque caractère.
            _model_edit.editingFinished.connect(self._on_model_chosen)
        model_row.addWidget(self._model_combo, stretch=1)
        cl.addLayout(model_row)
        cl.addSpacing(10)

        # Loading status for the async model fetch (hidden when idle).
        self._lbl_models_status = QLabel()
        # Sans ceci, le message du fournisseur est COUPE a la largeur du
        # label : l'utilisateur ne lisait que le texte generique et pas
        # les mots de Google, qui viennent apres (QA AI1, 2026-09-04).
        self._lbl_models_status.setWordWrap(True)
        # `setWordWrap` seul ne suffit pas : la hauteur du label reste
        # celle calculee au premier agencement, et un message plus long
        # arrive plus tard est ECRETE. Il faut lui dire qu'il peut
        # grandir, et redemander un agencement a chaque texte pose
        # (cf. `_set_model_status`).
        self._lbl_models_status.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._lbl_models_status.setText("")
        cl.addWidget(self._lbl_models_status)
        # L'air se met AU-DESSUS du disclaimer, pas en dessous : il appartient
        # visuellement au lien << Obtenir une cle >> qui le suit, pas au
        # message d'erreur qui le precede (retour utilisateur, QA AI1).
        cl.addSpacing(10)

        # Disclaimer (always visible): some models have a free API tier.
        self._lbl_disclaimer = QLabel()
        self._lbl_disclaimer.setWordWrap(True)
        cl.addWidget(self._lbl_disclaimer)

        # Base URL field (custom only) — kept in its own widget so it can be
        # shown/hidden as a whole row.
        self._base_row = QWidget()
        base_row = QHBoxLayout(self._base_row)
        base_row.setContentsMargins(0, 8, 0, 0)
        base_row.setSpacing(8)
        self._lbl_base = QLabel()
        self._lbl_base.setFixedWidth(70)
        base_row.addWidget(self._lbl_base)
        self._base_input = QLineEdit()
        self._base_input.setFixedHeight(34)
        base_row.addWidget(self._base_input, stretch=1)
        cl.addWidget(self._base_row)

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
        provider. Used on load and on provider change — never blocks.

        Sonde AUSSI le modèle déjà enregistré. Sans ça, l'application
        démarrait avec une pastille VERTE sur un modèle mort : elle
        constatait qu'une clé et un modèle existent, et n'avait jamais rien
        vérifié (retour utilisateur, 2026-09-04). L'appel part dans un
        worker, comme le chargement de la liste juste au-dessus — la
        déduplication le limite à une fois par couple et par session.
        """
        pid = self.selected_provider_id()
        if pid and ai_config.api_key(pid):
            self._start_models_fetch(pid)
            modele = self._model_text()
            if modele:
                self._start_model_probe(pid, modele)

    def probe_verdict_for(self, provider_id: str, model: str):
        """Le verdict mémorisé pour ce couple, ou `None` si jamais sondé.

        Lu par `IAView._publier_etat` : la pastille ne doit pas conclure
        d'elle-même à partir de la seule présence d'une clé.
        """
        verdict = self._probe_verdicts.get((provider_id, model))
        return None if verdict is None else verdict[0]

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
        self._workers_vivants.add(worker)
        worker.start()

    def _clear_worker(self, worker: "_ModelsWorker"):
        self._workers_vivants.discard(worker)
        if self._models_worker is worker:
            self._models_worker = None

    def _stop_worker(self):
        """Stop the in-flight models fetches AND probes on app exit (avoid
        destroying a running QThread).

        TOUS les fils encore vivants, pas seulement le dernier de chaque
        sorte : un fil REMPLACE tournait encore, sans reference. Et `run()`
        ne lit jamais `requestInterruption` -- une sonde bloque jusqu'a 90 s.
        Celui qui tourne encore apres 2 s est DETACHE (plus de parent, plus
        de proprietaire Python) : detruire la fenetre ne le detruit plus en
        pleine course, ce qui tuait l'app a la sortie (0xC0000409, audit
        2026-11-06). Le processus qui se termine l'emporte."""
        from PyQt6 import sip
        for w in list(self._workers_vivants):
            if sip.isdeleted(w) or not w.isRunning():
                continue
            w.requestInterruption()
            if not w.wait(2000):
                w.setParent(None)
                sip.transferto(w, None)
        self._workers_vivants.clear()

    # ── Async model probe ───────────────────────────────────────────

    def _start_model_probe(self, provider_id: str, model: str):
        """Lance la sonde pour (provider_id, model), sauf si ce couple a
        déjà été vérifié dans cette session (la sonde coûte un appel réseau
        réel — spec 2026-09-03, B). Un précédent en vol est laissé finir ;
        son résultat sera ignoré par `_on_model_probed` s'il est devenu
        obsolète (fournisseur ou texte du modèle changés entretemps)."""
        if not provider_id or not model:
            return
        key = (provider_id, model)
        if key in self._probed_pairs:
            # Deja sonde : on ne rappelle pas le reseau, mais on REAFFICHE son
            # verdict -- au LABEL comme a la PASTILLE. Ne rafraichir que le
            # label laissait la pastille verte devant un message d'erreur
            # rouge, jusqu'a ce qu'un autre evenement la recalcule (retour
            # utilisateur, QA AI4ter).
            self._refresh_model_status()
            verdict = self._probe_verdicts.get(key)
            if verdict is not None:
                self._publish_probe_state(provider_id, verdict[0])
            return
        self._probed_pairs.add(key)
        self._sondes_en_vol.add(key)
        # La pastille ne sait plus rien tant que la sonde tourne : la laisser
        # VERTE pendant les 30 s d'un modele lent, c'est affirmer un acces
        # qu'on est justement en train de verifier. `None` = grise, la valeur
        # que `ai_status` reserve a << on ne sait pas encore >>.
        self._publish_probe_state(provider_id, None)
        self._start_checking_animation()

        worker = _ProbeWorker(provider_id, model, self)
        worker.finished_probe.connect(self._on_model_probed)
        worker.finished.connect(lambda w=worker: self._clear_probe_worker(w))
        worker.finished.connect(worker.deleteLater)
        self._probe_worker = worker
        self._workers_vivants.add(worker)
        worker.start()

    def _start_checking_animation(self):
        """« Vérification du modèle » avec des points qui s'ajoutent, en vert.

        La sonde dure jusqu'à **30 s** (mesuré sur `gemini-flash-latest`).
        Un texte figé pendant une demi-minute se lit comme une application
        bloquée : l'animation dit que quelque chose se passe encore.
        """
        self._stop_checking_animation()
        self._probe_dots = 0
        self._paint_checking()
        timer = QTimer(self)
        timer.setInterval(400)
        timer.timeout.connect(self._paint_checking)
        timer.start()
        self._probe_timer = timer

    def _paint_checking(self):
        s = lang_manager.current
        self._probe_dots = (self._probe_dots + 1) % 4
        points = "." * self._probe_dots
        self._set_model_status(f"{s.ia_model_checking}{points}",
                               theme_manager.current.signal_ok)

    def _stop_checking_animation(self):
        if self._probe_timer is not None:
            self._probe_timer.stop()
            self._probe_timer.deleteLater()
            self._probe_timer = None

    def _publish_probe_state(self, provider_id: str, ok: "bool | None"):
        """Un modèle injoignable doit ROUGIR la pastille de la barre d'état.

        Elle ne savait jusqu'ici que dire « une clé existe » — elle restait
        donc verte pour un modèle qui ne répond pas (QA AI1, 2026-09-04).
        `ai_status` traite tout état inconnu comme une erreur, donc un état
        dédié suffit à obtenir du rouge sans toucher à ses tables.

        Ne publie que si CE fournisseur est bien le backend actif : sonder un
        modèle qu'on n'a pas activé ne dit rien de ce qui va générer.
        """
        from .ai_status import ai_status
        if ai_config.backend_id != provider_id:
            return
        if ok is None:
            ai_status.set_state(None)          # grise : verification en cours
        else:
            ai_status.set_state("cloud_key_ok" if ok
                                else "cloud_model_unreachable")

    def _sonde_affichee_en_vol(self) -> bool:
        return (self.selected_provider_id(), self._model_text()) \
            in self._sondes_en_vol

    def _clear_probe_worker(self, worker: "_ProbeWorker"):
        self._workers_vivants.discard(worker)
        if self._probe_worker is worker:
            self._probe_worker = None

    def _on_model_probed(self, provider_id: str, model: str, ok: bool, message: str):
        """Affiche le résultat de la sonde -- seulement s'il concerne encore
        ce qui est affiché (fournisseur ET texte du modèle inchangés depuis
        le déclenchement). Sinon, silence : l'utilisateur regarde déjà
        autre chose."""
        self._sondes_en_vol.discard((provider_id, model))
        if provider_id != self.selected_provider_id() or \
                model != self._model_text():
            # Résultat obsolète : on ne l'affiche pas, mais on le RETIENT
            # (il reste vrai pour son couple), et on ne laisse surtout pas
            # « Vérification du modèle… » en place -- SAUF si la sonde du
            # couple affiché tourne encore : elle a droit à son animation.
            self._probe_verdicts[(provider_id, model)] = (ok, message)
            if not self._sonde_affichee_en_vol():
                self._stop_checking_animation()
                self._refresh_model_status()
            return
        # Retenu plutôt qu'écrit : `_refresh_model_status` le réaffichera
        # tant que le couple concerné est celui affiché, et le laissera
        # tomber sinon. (`.replace` et non `.format` y est utilisé : le
        # message vient du fournisseur et peut porter des accolades.)
        self._probe_verdicts[(provider_id, model)] = (ok, message)
        self._stop_checking_animation()
        self._refresh_model_status()
        self._publish_probe_state(provider_id, ok)

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
                # N'efface que SON message : un verdict de sonde arrivé
                # entre-temps restait effacé sans condition (audit 2026-11-06).
                vide = self._lbl_models_status.text()
                QTimer.singleShot(4000, lambda: (
                    self._lbl_models_status.text() == vide
                    and self._lbl_models_status.setText("")))
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
        # Pas `setText("")` : sans modèle choisi, l'avertissement doit rester.
        # Il ne vivait sinon que le temps du chargement de la liste.
        self._refresh_model_status()

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
        self._refresh_model_field_state()
        # L'animation d'une sonde d'un AUTRE couple réécrivait le statut
        # 400 ms plus tard (audit 2026-11-06) : elle s'arrête ici, sauf si le
        # couple maintenant affiché est lui-même en vérification.
        if not self._sonde_affichee_en_vol():
            self._stop_checking_animation()
        self._refresh_model_status()

    def _refresh_model_field_state(self):
        """Grise le champ modèle tant qu'aucune clé n'est enregistrée.

        Sans clé, la liste ne peut pas être chargée et aucune vérification
        n'est possible : proposer un champ actif invite à saisir un modèle
        qui ne sera jamais éprouvé. Le geste utile est en amont — coller sa
        clé (retour utilisateur, QA AI3).
        """
        pid = self.selected_provider_id()
        a_une_cle = bool(ai_config.api_key(pid))
        self._model_combo.setEnabled(a_une_cle)
        # L'invite aussi doit dire le geste POSSIBLE : << choisissez un
        # modele dans la liste >> ne l'est pas tant que la liste ne peut pas
        # etre chargee (retour utilisateur, QA AI3bis).
        edit = self._model_combo.lineEdit()
        if edit is not None:
            s = lang_manager.current
            edit.setPlaceholderText(s.ia_model_placeholder if a_une_cle
                                    else s.ia_model_placeholder_no_key)

    def _set_model_status(self, texte: str, couleur: str = ""):
        """Écrit le statut du modèle, éventuellement coloré, et laisse le
        label reprendre la hauteur qu'il lui faut.

        Sans `updateGeometry`, un message plus long que le précédent reste
        écrêté à la hauteur déjà calculée — c'est ce qui coupait le message
        de Google en plein milieu (retour utilisateur, QA AI1).
        """
        if couleur:
            texte = f'<span style="color:{couleur};">{texte}</span>'
        self._lbl_models_status.setText(texte)
        self._lbl_models_status.updateGeometry()

    def _refresh_model_status(self):
        """Recalcule le statut du modèle À PARTIR DE L'ÉTAT, jamais en
        laissant en place ce qui y était.

        Un seul label porte trois choses : « aucun modèle choisi », le verdict
        de la sonde, et les messages transitoires du chargement de la liste.
        La première version n'effaçait le statut que s'il était son PROPRE
        message — si bien qu'un « Ce modèle a répondu » survivait à un
        changement de fournisseur, et qu'un « n'a pas répondu » accusait un
        modèle qu'on n'avait jamais vérifié (revue finale 2026-09-03). C'est
        exactement le défaut que ce chantier existe pour supprimer, sur
        l'écran qu'il vient de construire.

        Le verdict n'est donc plus écrit dans le label : il est RETENU, avec
        le couple auquel il s'applique, et réaffiché seulement tant que ce
        couple est encore celui affiché.
        """
        s = lang_manager.current
        model = self._model_text()
        if not model:
            # << Aucun modele choisi >> est un CONSTAT : il reste vrai avec
            # ou sans cle. C'est la CONSIGNE qui change de cible -- sans cle,
            # << selectionne-en un dans la liste >> est impossible a suivre,
            # le geste utile etant d'enregistrer sa cle (retour utilisateur,
            # QA AI3bis). Se taire aurait supprime une information vraie.
            a_une_cle = bool(ai_config.api_key(self.selected_provider_id()))
            self._set_model_status(s.ia_model_none_chosen if a_une_cle
                                   else s.ia_model_none_no_key)
            return
        verdict = self._probe_verdicts.get((self.selected_provider_id(), model))
        if verdict is not None:
            ok, message = verdict
            c = theme_manager.current
            self._set_model_status(
                s.ia_model_ok if ok
                else s.ia_model_ko.replace("{detail}", message),
                c.signal_ok if ok else c.signal_error)
            return
        self._set_model_status("")

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

    def _on_model_chosen(self, *_args):
        """Persiste le modèle courant pour le fournisseur sélectionné.

        Branché sur `activated` (choix dans la liste) et sur
        `editingFinished` du champ de saisie (validation au clavier — Entrée
        ou perte du focus). `_set_model_text` (comme `_reload_fields` et
        `_on_models_fetched`) bloque les signaux, donc un remplissage
        programmatique (changement de fournisseur, arrivée de la liste
        asynchrone) ne passe jamais ici : seul un geste de l'utilisateur
        écrit dans la config.
        """
        pid = self.selected_provider_id()
        is_custom = (pid == "custom")
        model = self._model_text()
        if is_custom:
            ai_config.custom_model = model
        else:
            ai_config.set_model(pid, model)
        self._confirm_saved()
        # Verification APRES la persistance (spec 2026-09-03, B) : le
        # listing du fournisseur ne dit pas ce qui est accessible, seul un
        # appel reel le dit.
        self._start_model_probe(pid, model)
        # Le modele enregistre doit AUSSI etre celui de l'instance active : le
        # chat garde sinon le moteur construit avec l'ancien (la generation,
        # qui relit la config a chaque fois, utiliserait le nouveau). Meme
        # condition que `_on_save` : seule la section active recree.
        if self.radio.isChecked():
            self.activated.emit()

    def _confirm_saved(self):
        """Affiche le ✓ de confirmation d'enregistrement.

        Factorisé depuis `_on_save` : la clé (bouton dédié) et le modèle
        (persisté à la sélection) partagent la même confirmation visible.
        """
        s = lang_manager.current
        self._lbl_status.setText(
            f'<span style="color:{theme_manager.current.signal_ok};">'
            f'✓ {s.ia_saved}</span>'
        )
        QTimer.singleShot(3000, lambda: self._lbl_status.setText(""))

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

        # La clé (ou l'URL de base) vient de changer : les verdicts de sonde
        # déjà rendus pour CE fournisseur portaient sur d'autres identifiants
        # et ne valent plus rien. Sans cet oubli volontaire, une sonde tombée
        # en « clé invalide » interdisait de re-vérifier le même modèle après
        # correction de la clé — il aurait fallu redémarrer l'app.
        self._probed_pairs = {(p, m) for (p, m) in self._probed_pairs
                              if p != pid}
        # Les VERDICTS aussi : sans ca, celui de l'ancienne cle restait affiche
        # (« n'a pas repondu — API key not valid » devant une cle bonne) et
        # pilotait la pastille -- verte devant une cle refusee, dans le cas
        # inverse -- jusqu'a ce qu'un autre geste relance une sonde.
        self._probe_verdicts = {k: v for k, v in self._probe_verdicts.items()
                                if k[0] != pid}

        self._refresh_model_field_state()
        self._confirm_saved()

        # Now that the key is saved, (re)fetch the model list for this provider.
        if key:
            self._start_models_fetch(pid)
            # ... et re-verifier le modele avec la NOUVELLE cle.
            self._start_model_probe(pid, model)

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
        # L'invite dépend de la présence d'une clé (QA AI3bis) : la poser ici
        # sans condition écrasait celle du « sans clé » dès la construction
        # (audit 2026-11-06).
        self._refresh_model_field_state()
        self._lbl_disclaimer.setText(s.ia_model_disclaimer)
        self._lbl_base.setText(s.ia_base_url_label)
        self._refresh_link()
        # Le statut du modèle aussi, dans la nouvelle langue -- sauf pendant
        # une vérification : l'animation le réécrit elle-même.
        if self._probe_timer is None:
            self._refresh_model_status()


# ── Section backend (Ollama + optional extras) ──────────────────────────────

class _BackendSection(QWidget):
    """
    Block for a non-cloud backend: radio + title, indented content.
    For Ollama: drop-down list of local models + availability indicator.
    For an optional extra backend: availability indicator only.
    """

    # Emitted (Ollama only) when the user chooses another model.
    model_changed = pyqtSignal(str)
    # Le reglage du contexte a change (2026-11-06) : le moteur actif doit
    # etre relu. Meme signal sur la page LM Studio.
    reglage_change = pyqtSignal()

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

            # Charger / decharger (2026-11-06) : le MEME geste que la page
            # LM Studio, a la demande de l'auteur. ⚠️ Gris, pas rouge :
            # Ollama charge seul a la premiere demande, « pas charge » n'est
            # pas une panne -- c'est la seule difference voulue entre les deux.
            self._lbl_memoire = QLabel()
            self._lbl_memoire.setWordWrap(True)
            self._lbl_memoire.hide()
            content_layout.addWidget(self._lbl_memoire)
            rang_mem = QHBoxLayout()
            rang_mem.setContentsMargins(0, 4, 0, 0)
            # Deux boutons, comme la page LM Studio : « Charger pour
            # Promptuino » / « Recharger » (charge au reglage), et « Decharger ».
            self._btn_charger_mem = QPushButton()
            self._btn_charger_mem.setCursor(Qt.CursorShape.PointingHandCursor)
            self._btn_charger_mem.setAutoDefault(False)
            self._btn_charger_mem.clicked.connect(self._charger_memoire)
            self._btn_charger_mem.hide()
            rang_mem.addWidget(self._btn_charger_mem)
            self._btn_decharger_mem = QPushButton()
            self._btn_decharger_mem.setCursor(Qt.CursorShape.PointingHandCursor)
            self._btn_decharger_mem.setAutoDefault(False)
            self._btn_decharger_mem.clicked.connect(self._decharger_memoire)
            self._btn_decharger_mem.hide()
            rang_mem.addWidget(self._btn_decharger_mem)
            rang_mem.addStretch(1)
            content_layout.addLayout(rang_mem)
            self._lbl_memoire_err = QLabel()
            self._lbl_memoire_err.setWordWrap(True)
            self._lbl_memoire_err.hide()
            content_layout.addWidget(self._lbl_memoire_err)
            # Ce que le chargement a libere ailleurs (decision de l'auteur,
            # 2026-11-06) : dit, jamais fait en silence.
            self._lbl_libere = QLabel()
            self._lbl_libere.setWordWrap(True)
            self._lbl_libere.hide()
            content_layout.addWidget(self._lbl_libere)
            # {"charge", "ctx"} ; None = on ne sait pas, donc on se tait.
            self._memoire: "dict | None" = None
            self._geste_en_cours = False

            # La taille de contexte : le MEME widget que la page LM Studio
            # (decision de l'auteur, 2026-11-06), bornes par le modele choisi.
            content_layout.addSpacing(12)
            self._ctx_max: "int | None" = None
            self._ctx = CurseurContexte()
            self._ctx.regler(None, ai_config.ollama_num_ctx)
            self._ctx.valeur_validee.connect(self._on_ctx_valide)
            content_layout.addWidget(self._ctx)

            # La reflexion (TODO #123) : le MEME interrupteur que LM Studio,
            # a la meme place, desactive par defaut.
            content_layout.addSpacing(10)
            self._think = InterrupteurReflexion()
            self._think.regler(None, ai_config.ollama_think)
            self._think.bascule.connect(self._on_think)
            content_layout.addWidget(self._think)
            # Le niveau d'effort (P4, 2026-11-07) : seulement pour un modele
            # qui annonce des niveaux nommes (gpt-oss).
            from .thinking_niveaux import CurseurNiveaux
            self._niveaux = CurseurNiveaux()
            self._niveaux.niveau_choisi.connect(self._on_niveau)
            content_layout.addWidget(self._niveaux)
            # La pastille du chat ou de la generation a pu changer le reglage.
            from .thinking_etat import thinking_etat
            thinking_etat.change.connect(self._suivre_thinking)

        else:
            # ── Optional extra backend: availability indicator ──────
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
        # `ia_saved` et non `ia_key_saved` : Ollama n'a pas de clé, et la
        # section Cloud dit `ia_saved` pour le même geste (audit 2026-11-06).
        self._lbl_model_status.setText(f'<span style="color:{theme_manager.current.signal_ok};">✓ {s.ia_saved}</span>')
        QTimer.singleShot(3000, lambda: self._lbl_model_status.setText(""))
        self.refresh_availability()
        self.model_changed.emit(model)

    def _on_ctx_valide(self, valeur: int):
        """Enregistre, puis redit l'etat memoire : un modele charge a une
        autre taille propose alors « Recharger ». La generation et le chat
        lisent le reglage en direct ; Ollama recharge seul a la demande
        suivante."""
        ai_config.ollama_num_ctx = valeur
        self._rendre_memoire()
        self.reglage_change.emit()

    def _on_think(self, coche: bool):
        """Enregistre. Le moteur Ollama lit le reglage en direct, comme le
        contexte : il s'applique a la demande suivante."""
        ai_config.ollama_think = coche
        self.reglage_change.emit()

    def _on_niveau(self, niveau: str):
        from .thinking_etat import thinking_etat
        thinking_etat.choisir_niveau(niveau)

    def _suivre_thinking(self):
        """Reflete le reglage partage, SANS reseau : la capacite deja lue
        par l'interrupteur suffit."""
        cap = self._think._cap
        self._think.regler(cap, ai_config.ollama_think)
        niveaux = cap.niveaux if cap is not None else ()
        actuel = (ai_config.ollama_think_level
                  if ai_config.ollama_think_level in niveaux
                  else (cap.allumer if cap is not None else ""))
        self._niveaux.regler(niveaux, actuel)

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

        Performs the slow calls (Ollama HTTP, availability probe of an extra backend).
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
                # (TODO #79). `shutil.which` tranche.
                # `shutil.which` seul ratait un Ollama installe APRES le
                # demarrage de l'app -- c'est-a-dire juste apres que
                # l'utilisateur ait suivi notre lien. `is_installed`
                # regarde aussi les emplacements par defaut.
                # TODO #117 : il y a une TROISIEME situation, mesuree sur
                # un vrai poste le 2026-09-14 -- le tray `ollama app.exe`
                # tournait pendant que 127.0.0.1:11434 refusait la connexion.
                # Dire alors << ouvrez l'application Ollama >> conseille une
                # chose DEJA FAITE : c'est le meme cul-de-sac que le #79 a
                # ferme un cran plus haut. `is_process_running` ne coute son
                # sous-processus que sur ce chemin-la, serveur muet.
                installe = is_installed()
                if not installe:
                    etat = "ollama_not_installed"
                elif is_process_running():
                    etat = "ollama_server_asleep"
                else:
                    etat = "ollama_server_down"
                self._availability_state = (etat, None)
            elif not is_model_available(model):
                self._availability_state = ("ollama_model_missing", model)
            else:
                # Le maximum du modele borne le curseur (decision de
                # l'auteur, 2026-11-06) ; sous le plancher, il est INUTILISABLE
                # et le message dit pourquoi. `/api/show`, local et rapide.
                self._ctx_max = ollama_models.contexte_max(model)
                if contexte.utilisable(self._ctx_max):
                    self._availability_state = ("ollama_ok", None)
                else:
                    self._availability_state = ("ollama_ctx_too_small",
                                                str(self._ctx_max))
            if self._availability_state[0] not in ("ollama_ok",
                                                   "ollama_ctx_too_small"):
                self._ctx_max = None        # serveur ou modele absent : inconnu
            if self._availability_state[0] == "ollama_ctx_too_small":
                self._ctx.bloquer(self._ctx_max)
            else:
                # Affiche le reglage BORNE au modele, sans l'enregistrer :
                # revenir a un plus grand modele retrouve la valeur choisie.
                self._ctx.regler(self._ctx_max, ai_config.ollama_num_ctx)
            # `/api/ps`, local et rapide comme les deux appels ci-dessus.
            self._memoire = (ollama_models.en_memoire(model)
                             if self._availability_state[0] == "ollama_ok"
                             else None)
            # Ce que le modele permet (`/api/show`, local et rapide) : grise
            # l'interrupteur s'il ne sait pas reflechir ou ne sait que ca.
            cap = (ollama_models.reflexion_modele(model)
                   if self._availability_state[0] in ("ollama_ok",
                                                      "ollama_ctx_too_small")
                   else None)
            self._think.regler(cap, ai_config.ollama_think)
            self._suivre_thinking()
        else:
            # Backend facultatif : par la FABRIQUE, qui seule sait s'il
            # existe. S'il a disparu entre-temps, il est simplement indisponible.
            inst = get_backend_instance(self.backend_id)
            available = bool(inst and inst.is_available())
            self._availability_state = (
                "extra_ok" if available else "extra_missing", None)

        # La pastille de la barre d'etat lit ce cache (TODO #80) : on ne
        # publie que si CE backend est l'actif -- il y a une section par
        # backend, et publier celle d'un backend non selectionne mentirait.
        if self.backend_id == ai_config.backend_id:
            from .ai_status import ai_status
            ai_status.set_state(self.etat_publie())

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
        elif kind == "ollama_server_asleep":
            # ⚠️ Le message CONSTATE et ne diagnostique pas : la cause d'un
            # processus sans serveur n'a pas ete mesuree (veille, mise a jour,
            # service arrete...), et l'inventer serait presenter une
            # supposition comme une certitude.
            txt = (f'<span style="color:{theme_manager.current.signal_error};">'
                   f'&#9679; {s.ia_ollama_server_asleep}</span>')
        elif kind == "ollama_model_missing":
            txt = (
                f'<span style="color:{theme_manager.current.signal_warn};">&#9679; '
                f'{s.ia_ollama_model_missing} {extra}</span>'
            )
        elif kind == "ollama_ctx_too_small":
            # Decision de l'auteur : dire que le modele est INUTILISABLE, et
            # preciser que c'est son contexte qui est trop petit.
            txt = (f'<span style="color:{theme_manager.current.signal_error};">'
                   f'&#9679; {s.ctx_unusable.format(n=extra, min=contexte.CTX_PROMPTUINO)}'
                   f'</span>')
        elif kind == "ollama_ok" and self._deborde_ollama():
            # Branche mais LENT (2026-11-06) : une partie du modele n'est pas
            # dans la VRAM -- Ollama le dit lui-meme (`size_vram < size`).
            txt = (f'<span style="color:{theme_manager.current.signal_warn};">'
                   f'&#9679; {s.slow_overflow}</span>')
        elif kind == "ollama_ok":
            txt = f'<span style="color:{theme_manager.current.signal_ok};">&#9679; {s.ia_ollama_running}</span>'
        elif kind in ("extra_ok", "extra_missing"):
            extra = extra_backend(self.backend_id)
            ok = kind == "extra_ok"
            couleur = (theme_manager.current.signal_ok if ok
                       else theme_manager.current.signal_error)
            mot = ""
            if extra is not None:
                mot = extra.available_text if ok else extra.unavailable_text
            txt = f'<span style="color:{couleur};">&#9679; {mot}</span>'
        else:
            return

        self._lbl_availability.setText(txt)
        self._lbl_availability.setTextFormat(Qt.TextFormat.RichText)
        # ⚠️ `setOpenExternalLinks(False)` + `linkActivated`, et PAS `True`
        # comme avant (TODO #117). Avec `True`, Qt ouvre lui-meme TOUT lien et
        # n'emet PAS `linkActivated` : le lien interne
        # « demarrer le serveur » serait passe au systeme comme une URL, donc
        # inerte. Le repartiteur ci-dessous rend son comportement au lien
        # ollama.com, qui continue de s'ouvrir dans le navigateur.
        self._lbl_availability.setOpenExternalLinks(False)
        try:
            self._lbl_availability.linkActivated.disconnect()
        except TypeError:
            pass            # aucune connexion encore posee
        self._lbl_availability.linkActivated.connect(self._on_availability_link)
        if self._is_ollama:
            self._rendre_memoire()

    # ── Charger / decharger (2026-11-06) ──────────────────────────

    def _rendre_memoire(self):
        """Depuis le cache, sans appel. Rien tant que le serveur ou le modele
        manquent, ni quand `/api/ps` se tait : on n'affirme pas « pas
        charge » sur une ignorance. Trois cas, comme la page LM Studio :
        pas charge, charge au reglage, charge a une AUTRE taille."""
        s = lang_manager.current
        visible = (self._availability_state is not None
                   and self._availability_state[0] == "ollama_ok"
                   and self._memoire is not None)
        self._lbl_memoire.setVisible(visible)
        self._btn_charger_mem.setVisible(False)
        self._btn_decharger_mem.setVisible(False)
        if not visible:
            return
        voulu = contexte.ramener(ai_config.ollama_num_ctx, self._ctx_max)
        if not self._memoire["charge"]:
            self._lbl_memoire.setText(s.om_not_loaded)
            self._btn_charger_mem.setVisible(True)
            texte = s.lms_load_for_app
        else:
            ctx = self._memoire["ctx"]
            self._btn_decharger_mem.setVisible(True)
            texte = s.ctx_reload
            if ctx is None:
                self._lbl_memoire.setText(s.om_loaded_unknown)
            elif contexte.accorde(ctx, voulu):
                self._lbl_memoire.setText(s.om_loaded.format(n=ctx))
            else:
                self._lbl_memoire.setText(s.ctx_differs.format(
                    charge=ctx, voulu=voulu))
                self._btn_charger_mem.setVisible(True)
        if not self._geste_en_cours:
            self._btn_charger_mem.setText(texte)
        self._btn_charger_mem.setToolTip(s.om_load_tip)
        self._btn_decharger_mem.setText(s.lms_unload)

    def _modele_memoire(self) -> str:
        return self._model_combo.currentText().strip() or ai_config.ollama_model

    def _charger_memoire(self):
        # Pendant un chargement, le MEME bouton dit « Annuler » (2026-11-07) :
        # couper la requete fait abandonner le chargement au serveur (mesure).
        if self._geste_en_cours and getattr(self, "_coupure_chg", None):
            self._chg_annule = True
            self._coupure_chg.couper()
            return
        modele = self._modele_memoire()
        if self._geste_en_cours or not modele:
            return
        from .ai_backends.coupure import Coupure
        coupure = self._coupure_chg = Coupure(unique=True)
        self._chg_annule = False

        def tache():
            # ⛔ Le contexte de la GENERATION, par sa propre methode -- le
            # reglage, borne au maximum du modele. Mesure du 2026-11-06 : un
            # autre `num_ctx` recharge le modele (7,7 s), donc un bouton qui
            # chargerait a un autre chiffre ne ferait gagner aucun temps.
            from .ai_backends import ollama_backend
            ctx = ollama_backend.OllamaBackend(modele).generation_context()
            # D'abord les AUTRES modeles, sur les deux moteurs (2026-11-06).
            liberes = memoire_modeles.liberer_autres(
                "ollama", modele, ai_config.lmstudio_base_url)
            if coupure.annulee:                  # annule pendant la liberation
                return False, "", liberes
            ok, msg = ollama_models.charger(modele, ctx, coupure=coupure)
            return ok, msg, liberes
        self._lancer_geste_memoire("charger", tache)
        self._btn_charger_mem.setText(lang_manager.current.md_cancel)
        self._btn_charger_mem.setToolTip(
            lang_manager.current.lms_loading.format(m=modele))
        self._btn_charger_mem.setEnabled(True)   # c'est lui qui annule

    def _decharger_memoire(self):
        modele = self._modele_memoire()
        if self._geste_en_cours or not modele:
            return
        self._lancer_geste_memoire("decharger",
                                   lambda: ollama_models.decharger(modele))

    def _lancer_geste_memoire(self, etiquette: str, tache):
        from .taches_fond import lancer_en_fond
        self._geste_en_cours = True
        self._btn_charger_mem.setEnabled(False)
        self._btn_decharger_mem.setEnabled(False)
        self._lbl_memoire_err.hide()
        self._lbl_libere.hide()
        lancer_en_fond(etiquette, tache, self._apres_geste_memoire)

    def _apres_geste_memoire(self, paquet):
        etiquette, r = paquet
        s = lang_manager.current
        if not isinstance(r, tuple):
            r = (False, str(r))
        ok, msg = r[0], r[1]
        libere = memoire_modeles.phrase(r[2] if len(r) > 2 else [], s.mem_freed)
        self._lbl_libere.setText(libere)
        self._lbl_libere.setVisible(bool(libere))
        self._geste_en_cours = False
        self._btn_charger_mem.setEnabled(True)
        self._btn_decharger_mem.setEnabled(True)
        annule = etiquette == "charger" and getattr(self, "_chg_annule", False)
        self._coupure_chg = None
        self._chg_annule = False
        if annule:
            # Un choix, pas une panne : pas de rouge.
            texte = " ".join(t for t in (libere, s.load_cancelled) if t)
            self._lbl_libere.setText(texte)
            self._lbl_libere.setVisible(True)
        elif not ok:
            # Jamais le texte brut d'Ollama : une phrase simple (2026-11-06).
            self._lbl_memoire_err.setText(erreurs_chargement.message(
                "ollama", msg, s, decharge=(etiquette == "decharger")))
            self._lbl_memoire_err.show()
        self.refresh_availability()

    def _deborde_ollama(self) -> bool:
        m = getattr(self, "_memoire", None)
        return bool(m and m.get("charge") and m.get("deborde"))

    def etat_publie(self) -> "str | None":
        """L'etat que la pastille affiche : celui de la page, sauf qu'un
        modele qui a deborde de la carte passe en ORANGE (branche mais lent)."""
        if self._availability_state is None:
            return None
        kind = self._availability_state[0]
        if kind == "ollama_ok" and self._deborde_ollama():
            return "ollama_slow"
        return kind

    _LIEN_DEMARRER_OLLAMA = "promptuino:start-ollama"

    def _on_availability_link(self, href: str) -> None:
        """Repartiteur des liens du message d'etat : action INTERNE, ou URL."""
        if href != self._LIEN_DEMARRER_OLLAMA:
            QDesktopServices.openUrl(QUrl(href))
            return
        # Le lancement est une TENTATIVE : le serveur met une a deux secondes
        # a ecouter (mesure du 2026-09-14, pret au 2e essai). On le dit
        # pendant l'attente, puis on RE-VERIFIE par HTTP -- croire le retour
        # de `start_server` afficherait un vert que personne n'a constate.
        s = lang_manager.current
        self._lbl_availability.setText(
            f'<span style="color:{theme_manager.current.text_secondary};">'
            f'&#9679; {s.ia_ollama_starting}</span>')
        start_server()
        QTimer.singleShot(2500, self.refresh_availability)

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
            self._ctx.apply_theme(c)
            self._think.apply_theme(c)
            self._niveaux.apply_theme(c)
            self._lbl_memoire.setStyleSheet(
                f"color: {c.text_secondary}; font-size: 9pt;")
            self._btn_charger_mem.setStyleSheet(secondary_button_qss(c))
            self._btn_decharger_mem.setStyleSheet(secondary_button_qss(c))
            self._lbl_libere.setStyleSheet(f"color: {c.text_secondary}; font-size: 9pt;")
            self._lbl_memoire_err.setStyleSheet(
                f"color: {c.signal_error}; font-size: 9pt;")
            # Oubli releve par l'utilisateur : le bouton etait le seul
            # widget NU de la section. Primaire, comme << Enregistrer >>
            # de la section cloud -- c'est l'action principale du rang.
            self._btn_dl_model.setStyleSheet(_primary_btn_qss(c))

    # ── Language ─────────────────────────────────────────────────

    def apply_lang(self, s: Strings):
        extra = extra_backend(self.backend_id)
        if extra is not None:
            # Un backend facultatif porte ses propres libelles : ils ne
            # passent pas par l'i18n, ils ne sont pas traduits.
            self.radio.setText(extra.label)
            self._lbl_subtitle.setText(extra.subtitle)
        else:
            self.radio.setText("Ollama (local)")
            self._lbl_subtitle.setText(s.ia_ollama_subtitle)

        if self._is_ollama:
            self._lbl_model_label.setText(s.ia_ollama_model_label)
            self._btn_dl_model.setText(s.md_manage)
            self._ctx.apply_lang(s)
            self._think.apply_lang(s)
            self._niveaux.apply_lang(s)
        # No refresh_availability here: would make a blocking HTTP call
        # to Ollama (up to 3 s) on every language change.
        self._render_availability()


# Les moteurs locaux, dans l'ordre d'affichage de la liste.
# ⚠️ Des MARQUES : non traduites, comme le « Ollama (local) » ecrit en dur
# dans `_BackendSection.apply_lang` depuis toujours.
_LOCAL_LABELS = {"ollama": "Ollama", "lmstudio": "LM Studio"}

# En dessous, le contexte charge est trop petit pour le travail de l'app.
# ⚠️ Ce n'est pas un seuil calibre sur un echantillon. Il vit dans
# `lmstudio_models` parce que le bouton « Charger » demande ce meme nombre :
# deux constantes pourraient diverger, et l'ecran dirait « trop petit » d'un
# modele que l'app vient elle-meme de charger.
from .lmstudio_models import CTX_PROMPTUINO as _LMSTUDIO_CTX_MIN  # noqa: E402


class _LMStudioPage(QWidget):
    """Les champs de LM Studio : une PAGE de la section Local, sans radio.

    ⛔ **Pas de curseur de contexte**, et c'est une decision : LM Studio fixe
    le contexte **au chargement du modele**. Son API compatible OpenAI ne
    permet pas de le changer ; son API native v1, si -- d'ou le bouton
    « Charger pour Promptuino », qui charge le modele choisi a
    `CTX_PROMPTUINO`. Un curseur promettrait un reglage qui ne s'applique
    qu'a un rechargement.

    ✅ **La gestion des modeles est la** (TODO #121, 2026-11-06) : l'auteur a
    leve la reserve du 2026-11-04. Le bouton « Modeles… » ouvre
    `LMStudioModelsDialog` (lister, telecharger, charger, decharger).

    Expose la meme surface que `_BackendSection` (`backend_id`,
    `_availability_state`, `apply_theme`, `apply_lang`, `refresh_availability`,
    `load_key`) parce que `IAView` et la pastille les lisent indifferemment.
    """

    model_changed = pyqtSignal(str)
    reglage_change = pyqtSignal()        # le contexte regle a change

    def __init__(self, parent=None):
        super().__init__(parent)
        self.backend_id = "lmstudio"
        # Meme role que dans `_BackendSection` : le cache que la pastille lit
        # sans jamais mesurer (TODO #80).
        self._availability_state: "tuple[str, str | None] | None" = None
        self._build()
        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._lbl_subtitle = QLabel()
        self._lbl_subtitle.setWordWrap(True)
        root.addWidget(self._lbl_subtitle)
        root.addSpacing(10)

        # ── Adresse du serveur ───────────────────────────────
        url_row = QHBoxLayout()
        url_row.setContentsMargins(0, 0, 0, 0)
        url_row.setSpacing(8)
        self._lbl_url = QLabel()
        self._lbl_url.setFixedWidth(56)
        url_row.addWidget(self._lbl_url)
        self._url_input = QLineEdit()
        self._url_input.setFixedHeight(34)
        # Vider le champ rend le defaut : `ai_config` s'en charge, donc on ne
        # peut pas se retrouver avec un backend sans adresse.
        self._url_input.editingFinished.connect(self._on_url_edited)
        url_row.addWidget(self._url_input, stretch=1)
        root.addLayout(url_row)
        root.addSpacing(6)

        # ── Modele ───────────────────────────────────────────
        model_row = QHBoxLayout()
        model_row.setContentsMargins(0, 0, 0, 0)
        model_row.setSpacing(8)
        self._lbl_model = QLabel()
        self._lbl_model.setFixedWidth(56)
        model_row.addWidget(self._lbl_model)
        self._model_combo = _ModelCombo(self._populate_models)
        self._model_combo.setFixedHeight(34)
        self._model_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._model_combo.textActivated.connect(self._on_model_selected)
        model_row.addWidget(self._model_combo, stretch=1)
        self._btn_models = QPushButton()
        self._btn_models.setFixedHeight(34)
        self._btn_models.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_models.setAutoDefault(False)
        self._btn_models.clicked.connect(self._ouvrir_gestion)
        model_row.addWidget(self._btn_models)
        root.addLayout(model_row)
        root.addSpacing(6)

        self._lbl_availability = QLabel()
        self._lbl_availability.setWordWrap(True)
        self._lbl_availability.setTextFormat(Qt.TextFormat.RichText)
        self._lbl_availability.setOpenExternalLinks(True)
        root.addWidget(self._lbl_availability)

        # Le contexte charge, AVANT les boutons : l'etat d'abord, le geste
        # ensuite -- le meme ordre que la page Ollama (2026-11-06).
        root.addSpacing(4)
        self._lbl_ctx = QLabel()
        self._lbl_ctx.setWordWrap(True)
        root.addWidget(self._lbl_ctx)

        # « Aucun modele charge » et « contexte trop petit » etaient des
        # culs-de-sac : le message renvoyait vers LM Studio. Mesure du
        # 2026-11-04 : une requete sur un modele non charge ECHOUE. Le bouton
        # fait le geste depuis ici, au contexte dont l'app a besoin.
        rang_charger = QHBoxLayout()
        rang_charger.setContentsMargins(0, 4, 0, 0)
        self._btn_charger = QPushButton()
        self._btn_charger.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_charger.setAutoDefault(False)
        self._btn_charger.clicked.connect(self._charger_pour_promptuino)
        self._btn_charger.hide()
        rang_charger.addWidget(self._btn_charger)
        # QA AV1 du 2026-11-06 : « Charger » etait sur la page, « Decharger »
        # seulement dans la fenetre. Les deux gestes, au meme endroit.
        self._btn_decharger = QPushButton()
        self._btn_decharger.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_decharger.setAutoDefault(False)
        self._btn_decharger.clicked.connect(self._decharger_le_modele)
        self._btn_decharger.hide()
        rang_charger.addWidget(self._btn_decharger)
        rang_charger.addStretch(1)
        root.addLayout(rang_charger)
        self._lbl_charge_err = QLabel()
        self._lbl_charge_err.setWordWrap(True)
        self._lbl_charge_err.hide()
        root.addWidget(self._lbl_charge_err)
        self._lbl_libere = QLabel()        # ce que le chargement a libere
        self._lbl_libere.setWordWrap(True)
        self._lbl_libere.hide()
        root.addWidget(self._lbl_libere)
        self._chargement_en_cours = False

        # La taille de contexte : le MEME widget que la page Ollama, a la
        # meme place (decision de l'auteur, 2026-11-06). Elle s'applique au
        # CHARGEMENT : un modele deja charge a une autre taille propose
        # « Recharger ».
        root.addSpacing(12)
        self._ctx_max: "int | None" = None
        self._deborde: "bool | None" = None
        self._verification = 0
        self._ctx = CurseurContexte()
        self._ctx.regler(None, ai_config.lmstudio_num_ctx)
        self._ctx.valeur_validee.connect(self._on_ctx_valide)
        root.addWidget(self._ctx)

        # La reflexion (TODO #123) : le MEME interrupteur que la page Ollama.
        root.addSpacing(10)
        self._think = InterrupteurReflexion()
        self._think.regler(None, ai_config.lmstudio_think)
        self._think.bascule.connect(self._on_think)
        root.addWidget(self._think)
        # Le niveau d'effort (P4) : toujours visible, GRISE -- l'API que
        # l'app utilise n'accepte pas de niveaux (TODO #125).
        from .thinking_niveaux import CurseurNiveaux
        self._niveaux = CurseurNiveaux()
        self._niveaux.niveau_choisi.connect(self._on_niveau)
        root.addWidget(self._niveaux)
        # La pastille du chat ou de la generation a pu changer le reglage.
        from .thinking_etat import thinking_etat
        thinking_etat.change.connect(self._suivre_thinking)

    # ── Saisie ───────────────────────────────────────────────

    def _on_url_edited(self):
        avant = ai_config.lmstudio_base_url
        ai_config.lmstudio_base_url = self._url_input.text()
        # Le champ peut avoir ete vide : on reaffiche ce qui a ete retenu.
        self._url_input.setText(ai_config.lmstudio_base_url)
        self.refresh_availability()
        if ai_config.lmstudio_base_url != avant:
            # Le moteur LM Studio fige son adresse a la construction : sans
            # ceci le chat continuait d'appeler l'ancienne.
            self.reglage_change.emit()

    def _populate_models(self):
        """Les modeles CONVERSATIONNELS du serveur, plus celui qui est
        enregistre meme s'il a disparu (sinon la selection sauterait).

        ⛔ La liste vient de l'API NATIVE et non de `/v1/models`, parce que
        seule la premiere donne le `type` : le Gemma 4 E4B sort en `vlm` et un
        filtre par nom ne saurait pas le garder.
        """
        saved = ai_config.lmstudio_model
        modeles = lmstudio_api.chat_models(ai_config.lmstudio_base_url)
        if saved and saved not in modeles:
            modeles = [saved] + modeles
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        self._model_combo.addItems(modeles)
        if saved in modeles:
            self._model_combo.setCurrentText(saved)
        self._model_combo.blockSignals(False)

    def _on_model_selected(self, text: str):
        modele = text.strip()
        if not modele:
            return
        ai_config.lmstudio_model = modele
        self.refresh_availability()
        self.model_changed.emit(modele)

    # ── Gestion des modeles (TODO #121) ──────────────────────

    def _modele_choisi(self) -> str:
        return (self._model_combo.currentText().strip()
                or ai_config.lmstudio_model)

    def _ouvrir_gestion(self):
        """A la fermeture, la liste et l'etat sont relus : un modele a pu
        etre telecharge, charge ou decharge entre-temps."""
        from .lmstudio_models_dialog import LMStudioModelsDialog
        dlg = LMStudioModelsDialog(ai_config.lmstudio_base_url, self)
        dlg.modeles_changes.connect(self._populate_models)
        dlg.exec()
        self._populate_models()
        self.refresh_availability()

    def _charger_pour_promptuino(self):
        # Pendant un chargement, le MEME bouton dit « Annuler » (2026-11-07) :
        # couper la requete fait abandonner le chargement a LM Studio (mesure).
        if self._chargement_en_cours and getattr(self, "_coupure_chg", None):
            self._chg_annule = True
            self._coupure_chg.couper()
            return
        modele = self._modele_choisi()
        if not modele or self._chargement_en_cours:
            return
        from .lmstudio_models_dialog import lancer_en_fond
        from .ai_backends.coupure import Coupure
        coupure = self._coupure_chg = Coupure(unique=True)
        self._chg_annule = False
        self._chargement_en_cours = True
        self._btn_charger.setEnabled(True)          # c'est lui qui annule
        self._btn_charger.setText(lang_manager.current.md_cancel)
        self._btn_charger.setToolTip(
            lang_manager.current.lms_loading.format(m=modele))
        self._btn_decharger.setEnabled(False)
        self._lbl_charge_err.hide()
        self._lbl_libere.hide()
        url = ai_config.lmstudio_base_url
        voulu = self._voulu()             # le reglage, borne au modele

        def tache():
            etat = lmstudio_models.etat_api(url)
            if etat != "ok":
                return ("bloque", etat)
            # D'abord les AUTRES modeles, sur les deux moteurs (2026-11-06).
            liberes = memoire_modeles.liberer_autres("lmstudio", modele, url)
            if coupure.annulee:                  # annule pendant la liberation
                return ("annule", "", liberes)
            ok, msg = lmstudio_models.charger(url, modele, voulu, coupure=coupure)
            if coupure.annulee:
                return ("annule", "", liberes)
            return ("ok", "", liberes) if ok else ("echec", msg, liberes)

        lancer_en_fond("charger", tache, self._apres_chargement)

    def _decharger_le_modele(self):
        """Libere TOUTES les instances du modele choisi, et seulement elles :
        les autres modeles charges dans LM Studio ne sont jamais touches."""
        modele = self._modele_choisi()
        if not modele or self._chargement_en_cours:
            return
        from .lmstudio_models_dialog import lancer_en_fond
        self._chargement_en_cours = True
        self._btn_charger.setEnabled(False)
        self._btn_decharger.setEnabled(False)
        self._lbl_charge_err.hide()
        url = ai_config.lmstudio_base_url

        def tache():
            etat = lmstudio_models.etat_api(url)
            if etat != "ok":
                return ("bloque", etat)
            fiche = next((f for f in lmstudio_models.modeles_installes(url)
                          if f["cle"] == modele), None)
            for instance, _ctx in (fiche["instances"] if fiche else []):
                ok, msg = lmstudio_models.decharger(url, instance)
                if not ok:
                    return ("echec_decharge", msg)
            return ("ok", "")

        lancer_en_fond("decharger", tache, self._apres_chargement)

    def _apres_chargement(self, paquet):
        _etiquette, r = paquet
        s = lang_manager.current
        if not isinstance(r, tuple):
            r = ("echec", str(r))
        issue, detail = r[0], r[1]
        libere = memoire_modeles.phrase(r[2] if len(r) > 2 else [], s.mem_freed)
        self._lbl_libere.setText(libere)
        self._lbl_libere.setVisible(bool(libere))
        self._chargement_en_cours = False
        self._coupure_chg = None
        self._chg_annule = False
        self._btn_charger.setEnabled(True)
        self._btn_decharger.setEnabled(True)
        self._btn_charger.setText(s.lms_load_for_app)
        if issue == "annule":
            # Un choix, pas une panne : pas de rouge.
            self._lbl_libere.setText(
                " ".join(t for t in (libere, s.load_cancelled) if t))
            self._lbl_libere.setVisible(True)
            texte = ""
        elif issue == "bloque":
            texte = (s.lms_need_update if detail == "ancien"
                     else s.ia_lmstudio_server_down)
        elif issue == "echec":
            # Jamais le texte brut de LM Studio : une phrase simple (2026-11-06).
            texte = erreurs_chargement.message("lmstudio", detail, s)
        elif issue == "echec_decharge":
            texte = erreurs_chargement.message("lmstudio", detail, s, decharge=True)
        else:
            texte = ""
        self._lbl_charge_err.setText(texte)
        self._lbl_charge_err.setVisible(bool(texte))
        self.refresh_availability()

    # ── API publique, celle que `IAView` attend ──────────────

    def load_key(self):
        """LM Studio n'a PAS de cle. Le nom vient de la surface commune avec
        `_BackendSection` ; ici on (re)charge l'adresse et les modeles."""
        self._url_input.setText(ai_config.lmstudio_base_url)
        self._populate_models()

    def showEvent(self, ev):
        super().showEvent(ev)
        QTimer.singleShot(0, self.refresh_availability)

    def refresh_availability(self):
        """Recalcule l'etat, en TROIS temps -- et l'ordre est le sujet.

        ⛔ « Serveur eteint » et « aucun modele charge » ne demandent PAS le
        meme geste, et confondre les deux etait le cul-de-sac que le #79 a
        ferme pour Ollama. Mesure du 2026-11-04 : une requete sur un modele
        non charge ECHOUE (« No models loaded »), donc le second cas est bien
        une panne et non un detail.
        """
        url = ai_config.lmstudio_base_url
        modele = (self._model_combo.currentText().strip()
                  or ai_config.lmstudio_model)

        cap = None                        # la reflexion : inconnue par defaut
        self._ctx_max = None
        self._deborde = None              # inconnu jusqu'a la verification
        self._verification += 1           # une verif en vol devient perimee
        if not lmstudio_api.server_responds(url):
            self._availability_state = ("lmstudio_server_down", None)
        else:
            # Le maximum du modele borne le curseur (decision de l'auteur,
            # 2026-11-06) ; sous le plancher, il est INUTILISABLE. API v1 :
            # un LM Studio plus ancien ne le dit pas -> inconnu, pas inutilisable.
            f = lmstudio_models.fiche(url, modele) if modele else None
            self._ctx_max = f["ctx_max"] if f else None
            cap = reflexion.depuis_lmstudio(f.get("reflexion")) if f else None
            if not contexte.utilisable(self._ctx_max):
                self._availability_state = ("lmstudio_model_unusable",
                                            str(self._ctx_max))
            elif not modele or not lmstudio_api.is_loaded(url, modele):
                self._availability_state = ("lmstudio_no_model", None)
            else:
                ctx = lmstudio_api.loaded_context(url, modele)
                self._availability_state = self._etat_charge(ctx)

        if self._availability_state[0] == "lmstudio_model_unusable":
            self._ctx.bloquer(self._ctx_max)
        else:
            # Le reglage BORNE au modele, affiche sans etre enregistre.
            self._ctx.regler(self._ctx_max, ai_config.lmstudio_num_ctx)
        self._think.regler(cap, ai_config.lmstudio_think)
        self._suivre_thinking()
        self._publier_et_rendre()
        self._verifier_debordement()

    _CHARGES = ("lmstudio_ok", "lmstudio_ctx_differs", "lmstudio_ctx_small")

    def _verifier_debordement(self):
        """Le modele charge a-t-il deborde de la carte ? (2026-11-06)
        Dans un fil : la requete WMI coute environ une seconde."""
        kind, extra = self._availability_state or (None, None)
        if kind not in self._CHARGES or not extra:
            return
        from .taches_fond import lancer_en_fond
        numero, ctx = self._verification, int(extra)
        lancer_en_fond("debordement",
                       lambda: (numero, debordement.lmstudio_deborde(ctx)),
                       self._apres_debordement)

    def _apres_debordement(self, paquet):
        _etiquette, r = paquet
        if not isinstance(r, tuple) or r[0] != self._verification:
            return                        # resultat d'un etat perime
        self._deborde = r[1] if isinstance(r[1], bool) else None
        self._publier_et_rendre()

    def etat_publie(self) -> "str | None":
        """L'etat que la pastille affiche : un modele charge qui a deborde
        de la carte passe en ORANGE (branche mais lent)."""
        if self._availability_state is None:
            return None
        kind = self._availability_state[0]
        if self._deborde and kind in self._CHARGES:
            return "lmstudio_slow"
        return kind

    def _voulu(self) -> int:
        return contexte.ramener(ai_config.lmstudio_num_ctx, self._ctx_max)

    def _etat_charge(self, ctx: "int | None") -> tuple:
        """Le modele choisi est charge a `ctx` tokens : quel etat ?"""
        if ctx is None:
            # Charge, mais le contexte n'est pas lisible. On ne devine pas :
            # l'etat est sain, le contexte sera dit « inconnu ».
            return ("lmstudio_ok", None)
        if ctx < _LMSTUDIO_CTX_MIN:
            return ("lmstudio_ctx_small", str(ctx))
        if not contexte.accorde(ctx, self._voulu()):
            # Il marche, mais pas a la taille reglee : « Recharger ».
            return ("lmstudio_ctx_differs", str(ctx))
        return ("lmstudio_ok", str(ctx))

    def _publier_et_rendre(self):
        if self.backend_id == ai_config.backend_id:
            from .ai_status import ai_status
            ai_status.set_state(self.etat_publie())
        self._render_availability()

    def _on_ctx_valide(self, valeur: int):
        """Enregistre ; un modele charge a une autre taille propose alors
        « Recharger ». Aucun appel reseau : l'etat est recalcule depuis le
        contexte charge deja lu."""
        ai_config.lmstudio_num_ctx = valeur
        kind, extra = self._availability_state or (None, None)
        if kind in ("lmstudio_ok", "lmstudio_ctx_differs") and extra:
            self._availability_state = self._etat_charge(int(extra))
            self._publier_et_rendre()
        else:
            self._render_availability()
        self.reglage_change.emit()

    def _on_think(self, coche: bool):
        """Enregistre ; `reglage_change` recree le moteur actif, qui porte
        le reglage depuis sa construction."""
        ai_config.lmstudio_think = coche
        self.reglage_change.emit()

    def _on_niveau(self, niveau: str):
        from .thinking_etat import thinking_etat
        thinking_etat.choisir_niveau(niveau)

    def _suivre_thinking(self):
        """Reflete le reglage partage, SANS reseau (TODO #125) : la
        capacite deja lue par l'interrupteur suffit."""
        cap = self._think._cap
        self._think.regler(cap, ai_config.lmstudio_think)
        niveaux = cap.niveaux if cap is not None else ()
        actuel = (ai_config.lmstudio_think_level
                  if ai_config.lmstudio_think_level in niveaux
                  else (cap.allumer if cap is not None else ""))
        self._niveaux.regler(niveaux, actuel)

    def _render_availability(self):
        """Reaffiche depuis le cache, sans aucun appel -- donc sur mesure pour
        `apply_lang`."""
        if self._availability_state is None:
            return
        s = lang_manager.current
        c = theme_manager.current
        kind, extra = self._availability_state
        choisi = bool(self._modele_choisi())

        if kind == "lmstudio_server_down":
            # ⚠️ On ne SAIT PAS distinguer « pas installe » de « installe mais
            # serveur arrete » sans deviner un chemin d'installation, propre a
            # chaque systeme. On nomme donc les DEUX gestes plutot que
            # d'affirmer lequel manque -- et le lien d'installation couvre le
            # cas que le message principal laisserait en cul-de-sac.
            txt = (f'<span style="color:{c.signal_error};">&#9679; '
                   f'{s.ia_lmstudio_server_down}</span><br>'
                   f'<span style="color:{c.text_secondary};">'
                   f'{s.ia_lmstudio_not_installed}</span>')
        elif kind == "lmstudio_model_unusable":
            # Decision de l'auteur : dire que le modele est INUTILISABLE, et
            # preciser que c'est son contexte qui est trop petit.
            txt = (f'<span style="color:{c.signal_error};">&#9679; '
                   f'{s.ctx_unusable.format(n=extra, min=contexte.CTX_PROMPTUINO)}'
                   f'</span>')
        elif kind == "lmstudio_no_model":
            txt = (f'<span style="color:{c.signal_error};">&#9679; '
                   f'{s.ia_lmstudio_no_model_loaded}</span>')
        elif self._deborde and kind in self._CHARGES:
            # Branche mais LENT (2026-11-06) : partage graphique ou couches
            # sur le processeur (`ui/debordement.py`).
            txt = (f'<span style="color:{c.signal_warn};">&#9679; '
                   f'{s.slow_overflow}</span>')
        else:
            txt = (f'<span style="color:{c.signal_ok};">&#9679; '
                   f'{s.ia_lmstudio_ok}</span>')
        self._lbl_availability.setText(txt)

        # Charger : pas charge, ou charge trop petit. Recharger : charge a une
        # autre taille que le reglage. Jamais serveur eteint ni inutilisable.
        self._btn_charger.setVisible(
            kind in ("lmstudio_no_model", "lmstudio_ctx_small",
                     "lmstudio_ctx_differs") and choisi)
        if not self._chargement_en_cours:
            self._btn_charger.setText(s.ctx_reload if kind == "lmstudio_ctx_differs"
                                      else s.lms_load_for_app)
        self._btn_charger.setToolTip(s.lms_load_tip.format(n=self._voulu()))
        # Le modele choisi est en memoire : on peut l'en retirer.
        self._btn_decharger.setVisible(
            kind in ("lmstudio_ok", "lmstudio_ctx_small",
                     "lmstudio_ctx_differs") and choisi)
        self._btn_decharger.setText(s.lms_unload)

        # Le contexte, dit separement : il ne change pas la disponibilite.
        if kind in ("lmstudio_server_down", "lmstudio_no_model",
                    "lmstudio_model_unusable"):
            self._lbl_ctx.setText("")
        elif extra is None:
            self._lbl_ctx.setText(s.ia_lmstudio_ctx_unknown)
        elif kind == "lmstudio_ctx_small":
            self._lbl_ctx.setText(s.ia_lmstudio_ctx_too_small.format(n=extra))
        elif kind == "lmstudio_ctx_differs":
            self._lbl_ctx.setText(s.ctx_differs.format(charge=extra,
                                                       voulu=self._voulu()))
        else:
            self._lbl_ctx.setText(s.ia_lmstudio_ctx_loaded.format(n=extra))

    # ── Theme / langue ───────────────────────────────────────

    def apply_theme(self, c: ColorScheme):
        self._lbl_subtitle.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 10pt;")
        for lbl in (self._lbl_url, self._lbl_model):
            lbl.setStyleSheet(f"color: {c.text_secondary}; font-size: 10pt;")
        self._url_input.setStyleSheet(input_qss(c))
        self._model_combo.setStyleSheet(combo_qss(c))
        self._lbl_ctx.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 9pt;")
        self._btn_models.setStyleSheet(_primary_btn_qss(c))
        self._btn_charger.setStyleSheet(secondary_button_qss(c))
        self._btn_decharger.setStyleSheet(secondary_button_qss(c))
        self._lbl_libere.setStyleSheet(f"color: {c.text_secondary}; font-size: 9pt;")
        self._ctx.apply_theme(c)
        self._think.apply_theme(c)
        self._niveaux.apply_theme(c)
        self._lbl_charge_err.setStyleSheet(
            f"color: {c.signal_error}; font-size: 9pt;")
        self._render_availability()

    def apply_lang(self, s: Strings):
        self._lbl_subtitle.setText(s.ia_lmstudio_subtitle)
        self._lbl_url.setText(s.ia_lmstudio_url_label)
        self._lbl_model.setText(s.ia_ollama_model_label)   # « Modele », commun
        self._btn_models.setText(s.md_manage)              # « Modeles… », commun
        self._ctx.apply_lang(s)
        self._think.apply_lang(s)
        self._niveaux.apply_lang(s)
        self._render_availability()


class _LocalSection(QWidget):
    """UN radio « Local », une liste de moteurs, et une page par moteur.

    ⛔ **Le contenu d'Ollama n'est PAS reecrit.** On reutilise
    `_BackendSection("ollama")` telle quelle, radio MASQUE : ses champs, son
    `num_ctx`, ses trois etats de serveur et ses messages ne bougent pas d'une
    ligne. Les redessiner pour « unifier » aurait risque un chantier qui
    marche, sans rien apporter a l'utilisateur.

    ⚠️ Les backends FACULTATIFS (`ui.ai_backends.dev`) ne sont PAS ici : ils
    gardent leur propre radio. Decision de l'utilisateur du 2026-11-04 --
    l'ecran a trois radios n'existe que sur une machine de developpement,
    puisque le paquet n'est pas publie, donc la « coherence » que je plaidais
    ne concernait personne.
    """

    engine_activated = pyqtSignal(str)       # un moteur a ete choisi
    ollama_model_changed = pyqtSignal(str)   # relais vers IAView
    # Un reglage d'un moteur local a change (modele LM Studio, contexte) :
    # IAView recree le moteur actif s'il s'agit de celui-la.
    moteur_regle = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pages: dict = {}
        self._build()
        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.radio = QRadioButton()
        self.radio.setCursor(Qt.CursorShape.PointingHandCursor)
        root.addWidget(self.radio)
        root.addSpacing(6)

        contenu = QWidget()
        cl = QVBoxLayout(contenu)
        cl.setContentsMargins(28, 0, 0, 0)
        cl.setSpacing(0)

        # ── La liste des moteurs ─────────────────────────────
        rang = QHBoxLayout()
        rang.setContentsMargins(0, 0, 0, 0)
        rang.setSpacing(8)
        self._lbl_engine = QLabel()
        self._lbl_engine.setFixedWidth(56)
        rang.addWidget(self._lbl_engine)
        self._combo = ComboSansMolette()
        self._combo.setFixedHeight(34)
        self._combo.setCursor(Qt.CursorShape.PointingHandCursor)
        rang.addWidget(self._combo, stretch=1)
        rang.addStretch()
        cl.addLayout(rang)
        cl.addSpacing(12)

        # ── Une page par moteur ──────────────────────────────
        self._stack = QStackedWidget()
        for backend_id in LOCAL_BACKENDS:
            if backend_id == "ollama":
                page = _BackendSection("ollama")
                # Son radio appartenait a l'ancien ecran : la section devient
                # un contenu, le choix passe par la liste.
                page.radio.setVisible(False)
                page.model_changed.connect(self.ollama_model_changed.emit)
            else:
                page = _LMStudioPage()
                # ⛔ Ce signal n'etait branche a RIEN (trouve le 2026-11-06) :
                # choisir un autre modele LM Studio ne recreait pas le moteur
                # actif, le chat et la generation gardaient l'ancien.
                page.model_changed.connect(
                    lambda _m, b=backend_id: self.moteur_regle.emit(b))
            page.reglage_change.connect(
                lambda b=backend_id: self.moteur_regle.emit(b))
            self.pages[backend_id] = page
            self._stack.addWidget(page)
            self._combo.addItem(_LOCAL_LABELS.get(backend_id, backend_id),
                                backend_id)
        cl.addWidget(self._stack)

        root.addWidget(contenu)
        self._combo.currentIndexChanged.connect(self._on_engine_changed)

    # ── Slots ────────────────────────────────────────────────

    def _on_engine_changed(self, _idx: int):
        backend_id = self.current_id()
        self._stack.setCurrentWidget(self.pages[backend_id])
        # Changer de moteur dans la liste VAUT le choisir -- sinon la liste
        # afficherait un moteur que l'app n'utilise pas, ce que rien ne
        # signalerait.
        self.engine_activated.emit(backend_id)

    # ── API publique ─────────────────────────────────────────

    def current_id(self) -> str:
        return self._combo.currentData() or LOCAL_BACKENDS[0]

    def select_engine(self, backend_id: str) -> None:
        """Pointe la liste SANS activer : sert au chargement de l'etat."""
        if backend_id not in self.pages:
            return
        idx = self._combo.findData(backend_id)
        if idx < 0:
            return
        self._combo.blockSignals(True)
        self._combo.setCurrentIndex(idx)
        self._combo.blockSignals(False)
        self._stack.setCurrentWidget(self.pages[backend_id])

    def apply_theme(self, c: ColorScheme):
        self.radio.setStyleSheet(
            radio_checkbox_qss(c, font_pt=14, font_weight=700))
        self._lbl_engine.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 10pt;")
        self._combo.setStyleSheet(combo_qss(c))

    def apply_lang(self, s: Strings):
        self.radio.setText(s.ia_local_title)
        self._lbl_engine.setText(s.ia_local_engine_label)


# ── Main view ─────────────────────────────────────────────────────────────

class IAView(QWidget):

    backend_activated = pyqtSignal(object)  # emits the active AIBackend instance

    def __init__(self, parent=None):
        super().__init__(parent)
        # ⚠️ Pas seulement des `_BackendSection` : depuis la section Local,
        # ce dictionnaire contient aussi des PAGES (`_LMStudioPage`). Ce
        # qu'elles ont en commun est une SURFACE (`backend_id`,
        # `_availability_state`, `apply_theme`, `apply_lang`, `load_key`,
        # `refresh_availability`), pas une classe -- et `.radio` n'en fait
        # PAS partie.
        self._sections: dict = {}
        self._cloud: _CloudSection | None = None
        self._active_backend = None
        self._build()
        # TODO #95 (2e lot) : c'est L'ÉCRAN où la copie manquait le plus. Le
        # #92 a rendu visible le message brut du fournisseur (« This model is
        # no longer available… Please update your code to use … ») — un texte
        # fait pour être collé dans une recherche, et qu'on ne pouvait pas
        # sélectionner. Ses éléments cliquables sont des radios, listes,
        # boutons et curseurs : AUCUNE `QLabel` n'y est une cible de clic.
        from .selectable_text import make_selectable
        make_selectable(self)
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
        # ⛔ Centree par des ESPACES ELASTIQUES, pas par `AlignHCenter` : Qt
        # calcule la hauteur d'un element aligne sur TOUTE la largeur du
        # conteneur (1 186 px) au lieu des 540 de la carte -- les textes qui
        # passent a la ligne y tiennent en moins de lignes, la carte restait
        # trop basse et le bas de la page Local etait COUPE (capture de
        # l'auteur du 2026-11-06 : 890 px annonces pour 939 necessaires).
        container_layout.addStretch(1)
        container_layout.addWidget(self._card)
        container_layout.addStretch(1)
        self._scroll.setWidget(container)

        layout = QVBoxLayout(self._card)
        layout.setContentsMargins(0, 40, 0, 40)
        layout.setSpacing(0)

        self._group = QButtonGroup(self)
        idx = 0

        # ORDRE decide par l'auteur le 2026-11-06 : Compte ChatGPT, puis
        # Local, puis Cloud (cle d'API) en dernier.
        #
        # 1. Compte ChatGPT (TODO #122) : un choix a part entiere -- decision
        #    de l'auteur du 2026-11-06, de preference a une entree de plus
        #    dans la liste des fournisseurs Cloud.
        from .chatgpt_section import ChatGPTSection
        self._chatgpt = ChatGPTSection()
        self._chatgpt.connecte.connect(self._activer_chatgpt)
        self._chatgpt.model_changed.connect(self._on_chatgpt_model_changed)
        # Le niveau de reflexion (TODO #123) : le moteur le porte depuis sa
        # construction, il est donc recree comme pour un autre modele.
        self._chatgpt.reglage_change.connect(
            lambda: self._on_chatgpt_model_changed(ai_config.chatgpt_model))
        self._sections["chatgpt"] = self._chatgpt
        self._group.addButton(self._chatgpt.radio, idx)
        idx += 1
        layout.addWidget(self._chatgpt)
        self._add_separator(layout)

        # 2. Les backends FACULTATIFS (`ui.ai_backends.dev`) : chacun garde
        #    son propre radio. ⚠️ Decision de l'utilisateur du 2026-11-04 --
        #    l'ecran a trois radios n'existe que sur une machine de
        #    developpement, le paquet n'etant pas publie.
        #    Une FONCTION evaluee ICI, pas une constante figee a l'import.
        for backend_id in special_backends():
            if backend_id in LOCAL_BACKENDS:
                continue          # Ollama vit dans la section Local, en dessous
            section = _BackendSection(backend_id)
            self._sections[backend_id] = section
            self._group.addButton(section.radio, idx)
            idx += 1
            layout.addWidget(section)
            self._add_separator(layout)

        # 3. Local : UN radio, une liste de moteurs, une page par moteur.
        self._local = _LocalSection()
        self._local.engine_activated.connect(self._activer_moteur_local)
        self._local.ollama_model_changed.connect(self._on_ollama_model_changed)
        self._local.moteur_regle.connect(self._on_moteur_regle)
        self._group.addButton(self._local.radio, idx)
        idx += 1
        # ⚠️ Les pages entrent dans `_sections` : c'est ce dictionnaire que la
        # pastille (`_publier_etat`), le theme et la langue parcourent. Les y
        # oublier rendrait LM Studio invisible a ces trois chemins.
        for backend_id, page in self._local.pages.items():
            self._sections[backend_id] = page
        layout.addWidget(self._local)
        self._add_separator(layout)

        # 4. Cloud (bring-your-own-key), en dernier.
        self._cloud = _CloudSection()
        self._cloud.activated.connect(self._activate_cloud)
        self._group.addButton(self._cloud.radio, idx)
        idx += 1
        layout.addWidget(self._cloud)

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
        if active_id in LOCAL_BACKENDS:
            # ⛔ `ai_config.backend_id` porte l'id CONCRET (`ollama`,
            # `lmstudio`), jamais « local » : le radio n'est qu'un
            # regroupement visuel. C'est ce qui evite toute migration de
            # configuration -- un fichier existant marche tel quel.
            self._local.radio.setChecked(True)
            self._local.select_engine(active_id)
            # La page LM Studio ne mesurait son etat qu'a son premier
            # affichage : moteur actif, serveur eteint, la pastille restait
            # grise tant que l'onglet n'etait pas ouvert (audit 2026-11-06,
            # contraire au TODO #80). Differe d'un tour de boucle, pour ne
            # pas allonger la construction ; la page publie elle-meme.
            page = self._local.pages.get(active_id)
            if page is not None and page._availability_state is None:
                QTimer.singleShot(0, page.refresh_availability)
        elif active_id in self._sections:
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
        if btn is self._local.radio:
            # Cocher « Local » active le moteur que la liste montre deja.
            self._activer_moteur_local(self._local.current_id())
            return

        checked_id = self._get_checked_id()
        if not checked_id or checked_id == ai_config.backend_id:
            return
        ai_config.backend_id = checked_id
        backend = get_backend_instance(ai_config.backend_id)
        self._active_backend = backend
        self._publier_etat()
        self.backend_activated.emit(backend)

    def _activer_moteur_local(self, backend_id: str) -> None:
        """Active un moteur de la liste « Local ».

        ⚠️ Appele par DEUX chemins qui doivent faire la meme chose : cocher le
        radio, et changer la liste alors qu'il est deja coche. Les laisser
        diverger ferait afficher un moteur que l'app n'utilise pas, ce que
        rien ne signalerait.
        """
        if not backend_id or backend_id not in LOCAL_BACKENDS:
            return
        # Le radio peut ne pas etre coche si l'utilisateur a change la liste
        # depuis un autre backend actif : choisir un moteur, c'est choisir
        # « Local ».
        if not self._local.radio.isChecked():
            self._local.radio.setChecked(True)
        if backend_id == ai_config.backend_id:
            return
        ai_config.backend_id = backend_id
        backend = get_backend_instance(backend_id)
        self._active_backend = backend
        # La page recalcule son etat : c'est elle qui alimente la pastille.
        page = self._local.pages.get(backend_id)
        if page is not None:
            page.refresh_availability()
        self._publier_etat()
        self.backend_activated.emit(backend)

    def _publier_etat(self):
        """Publie vers la pastille l'etat du backend COURANT, sans reseau.

        - ollama / backends facultatifs : le cache que leur section a deja calcule ;
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
            publie = getattr(section, "etat_publie", None)
            ai_status.set_state(publie() if publie
                                else section._availability_state[0])
            return
        # ⚠️ La clé ne suffit PLUS. `is_available()` exige clé + URL + MODÈLE,
        # et depuis la suppression du modèle par défaut (spec 2026-09-03) une
        # clé peut très bien exister sans modèle : la pastille serait verte —
        # avec halo, le signal le plus fort de l'app — pour une génération qui
        # échouera sur « Aucun modèle IA disponible ». Mieux vaut du rouge en
        # trop que du vert menteur (revue finale 2026-09-03).
        if bid == "custom":
            modele = ai_config.custom_model
            url_ok = bool(ai_config.custom_base_url)
        elif any(p.id == bid for p in PROVIDERS):
            modele = ai_config.model_for(bid)
            url_ok = True                  # l'URL vient du preset
        else:
            ai_status.set_state(None)      # on ne sait pas -> pastille grise
            return
        # ⛔ LES MEMES TROIS QUESTIONS QUE `is_available()`, et la cle par la
        # MEME source : `backend_requires_key`.
        #
        # C'etait le defaut du brief LM Studio : deux endroits repondaient a
        # « cette configuration est-elle complete ? » et se contredisaient.
        # `is_available()` exigeait une cle de TOUT LE MONDE ; ici, « custom »
        # etait declare configure sans cle. Un serveur local sans cle avait
        # donc une pastille non rouge et une generation MORTE -- `is_available()`
        # garde la generation elle-meme, la reparation, l'explication d'erreur
        # et le lint, et aucun de ces chemins ne dit pourquoi il ne fait rien.
        #
        # ⛔ J'AI D'ABORD DELEGUE A `backend.is_available()`, ce qui rendait le
        # desaccord impossible au lieu d'improbable -- et c'etait un piege,
        # mesure : quand `_active_backend` est None (le constructeur appelle
        # cette methode AVANT de le poser), il faut construire l'instance, et
        # `get_backend_instance` lit le singleton `ui.ai_config.ai_config` en
        # direct. Les tests qui substituent `ia_view.ai_config` ne peuvent pas
        # l'intercepter : `test_model_probe` est alors parti lire la VRAIE
        # configuration et le VRAI trousseau. Partager la REGLE, pas
        # l'instance.
        #
        # Le `or` court-circuite : sans exigence de cle, le trousseau n'est
        # meme pas lu.
        cle_ok = (not backend_requires_key(bid)) or bool(ai_config.api_key(bid))
        configure = bool(url_ok and modele and cle_ok)
        if not configure:
            ai_status.set_state("cloud_key_missing")
            return
        # Configuré ne veut pas dire ACCESSIBLE. Tant que la sonde n'a pas
        # répondu pour CE modèle, on ne sait pas — et `None` (gris) est
        # exactement la valeur que ce module réserve à « pas encore
        # d'information ». Vert sur la seule présence d'une clé, c'était le
        # vert menteur : l'app démarrait au vert sur un modèle retiré
        # (retour utilisateur, 2026-09-04).
        verdict = self._cloud.probe_verdict_for(bid, modele)
        if verdict is None:
            ai_status.set_state(None)
            return
        ai_status.set_state("cloud_key_ok" if verdict
                            else "cloud_model_unreachable")

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

    def _activer_chatgpt(self):
        """Une connexion vient de reussir : se connecter, c'est choisir ce
        moteur. Meme chemin qu'un clic sur le radio."""
        if not self._chatgpt.radio.isChecked():
            self._chatgpt.radio.setChecked(True)
        self._on_radio_clicked(self._chatgpt.radio)

    def _on_chatgpt_model_changed(self, model: str):
        """Meme raison que pour Ollama : l'instance active doit porter le
        modele choisi, sinon le chat et la generation garderaient l'ancien."""
        if ai_config.backend_id == "chatgpt":
            backend = get_backend_instance("chatgpt")
            self._active_backend = backend
            self._publier_etat()
            self.backend_activated.emit(backend)

    def _on_moteur_regle(self, backend_id: str):
        """Un reglage d'un moteur local a change (modele LM Studio, taille de
        contexte). S'il est le moteur actif, l'instance est recreee : le
        moteur LM Studio fige son modele et sa fenetre a la construction, et
        le chat comme la generation doivent porter les nouveaux."""
        if ai_config.backend_id == backend_id:
            backend = get_backend_instance(backend_id)
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
        """L'id du backend coche hors cloud : un backend FACULTATIF, ou le
        moteur que la section « Local » montre.

        ⛔ N'itere PLUS `self._sections` a la recherche d'un `.radio`. Depuis
        la section Local, ce dictionnaire contient aussi des PAGES -- et
        `_LMStudioPage` n'a pas de radio : la boucle d'origine levait un
        AttributeError, que PyQt aurait masque en « super-class __init__()
        was never called ». Trouve en relisant les usages apres le
        branchement, pas a l'execution.
        """
        if self._local.radio.isChecked():
            return self._local.current_id()
        for backend_id, section in self._sections.items():
            if backend_id in LOCAL_BACKENDS:
                continue          # une page, pas une section a radio
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
        self._local.apply_theme(c)
        for section in self._sections.values():
            section.apply_theme(c)

    # ── Language ────────────────────────────────────────────────

    def apply_lang(self, s: Strings):
        self._cloud.apply_lang(s)
        self._local.apply_lang(s)
        for section in self._sections.values():
            section.apply_lang(s)

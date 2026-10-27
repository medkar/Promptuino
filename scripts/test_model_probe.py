"""Le modele choisi est VERIFIE, pas filtre (Task 4, spec 2026-09-03, decision B).

<< Ne proposer que les modeles accessibles >> est impossible : le listing d'un
fournisseur ne dit pas ce qui est accessible (gemini-2.5-flash figure dans
celui de Google, annonce generateContent, et renvoie 404 a l'usage). La sonde
(`OpenAICompatBackend.probe_model`) fait donc un appel REEL et minimal, et le
worker Qt (`_ProbeWorker`) l'execute hors du fil d'interface, jamais deux fois
pour le meme couple (fournisseur, modele) dans une session.

Run: python scripts/test_model_probe.py
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Importer ui.ia_view charge PyQt6 : il faut une QApplication vivante avant
# tout, meme si aucun widget construit ici n'est jamais affiche (motif de
# scripts/test_resemblance_notice.py et scripts/test_model_choice_is_saved.py).
from PyQt6.QtWidgets import QApplication, QLabel
_APP = QApplication.instance() or QApplication(sys.argv)

import ui.ia_view as ia_view
from ui.ia_view import _CloudSection as CloudSection
from ui.ai_backends.openai_compat import HttpError, OpenAICompatBackend
from ui.i18n import TRANSLATIONS

# ── Ne JAMAIS toucher la vraie config utilisateur / le vrai reseau ─────────
from ui.ai_config import CONFIG_PATH


def _config_snapshot() -> str | None:
    return CONFIG_PATH.read_text(encoding="utf-8") if CONFIG_PATH.exists() else None


# Corps REEL renvoye par Google le 2026-09-03 (tronque) : une LISTE, pas un
# objet -- mesure documente dans scripts/test_provider_error_detail.py.
_GEMINI_404 = json.dumps([{
    "error": {
        "code": 404,
        "message": ("This model models/gemini-2.5-flash is no longer "
                    "available to new users. Please upgrade."),
        "status": "NOT_FOUND",
    }
}])


def _backend(transport) -> OpenAICompatBackend:
    """Backend OpenAI-compatible avec un TRANSPORT BOUCHON : jamais de vrai
    appel reseau. `probe_model` ne prend aucun autre chemin d'E/S."""
    return OpenAICompatBackend(
        "https://example.invalid/v1", "fake-key", "fake-model",
        backend_id="gemini", label="Gemini", transport=transport,
    )


# ── 1. `probe_model` sur un transport bouchon ───────────────────────────────

class _Transport200Empty:
    """200, contenu vide (chaine) -- cas mesure des modeles a raisonnement
    Gemini 3.x a max_tokens=1."""
    def post_json(self, url, headers, payload, timeout):
        return {"choices": [{"message": {"content": ""}}]}


class _Transport200Null:
    """200, contenu `null` -- meme mesure, variante ou le fournisseur omet
    la cle plutot que d'envoyer une chaine vide."""
    def post_json(self, url, headers, payload, timeout):
        return {"choices": [{"message": {"content": None}}]}


class _Transport200NonEmpty:
    def post_json(self, url, headers, payload, timeout):
        return {"choices": [{"message": {"content": "pong"}}]}


class _Transport404Gemini:
    def post_json(self, url, headers, payload, timeout):
        raise HttpError(404, _GEMINI_404)


class _TransportConnErr:
    def post_json(self, url, headers, payload, timeout):
        raise ConnectionError("network down")


class _WeirdError(Exception):
    """Exception d'un type que `_complete` ne connait pas : verifie que
    `probe_model` ne laisse RIEN remonter, meme un type totalement inedit."""


class _TransportWeirdException:
    def post_json(self, url, headers, payload, timeout):
        raise _WeirdError("cable coupe")


def test_a_200_with_empty_string_content_is_a_success():
    """Une reponse vide EST un succes : on teste l'ACCES, pas le contenu."""
    ok, msg = _backend(_Transport200Empty()).probe_model()
    assert ok is True, (ok, msg)
    assert msg == "", msg


def test_a_200_with_null_content_is_also_a_success():
    ok, msg = _backend(_Transport200Null()).probe_model()
    assert ok is True, (ok, msg)
    assert msg == "", msg


def test_a_200_with_real_content_is_a_success():
    ok, msg = _backend(_Transport200NonEmpty()).probe_model()
    assert ok is True, (ok, msg)
    assert msg == "", msg


def test_a_404_with_the_gemini_body_carries_the_providers_words():
    """Le corps de Gemini est une LISTE JSON (pas un objet) -- `probe_model`
    doit s'appuyer sur `_error_message`/`_provider_detail` (Task 1), pas
    reinventer son propre parsing."""
    ok, msg = _backend(_Transport404Gemini()).probe_model()
    assert ok is False, (ok, msg)
    assert "no longer available to new users" in msg, msg


def test_a_connection_error_is_a_failure_not_an_exception():
    ok, msg = _backend(_TransportConnErr()).probe_model()
    assert ok is False, (ok, msg)
    assert msg, "un message vide n'aide personne a comprendre l'echec"


def test_a_never_seen_exception_type_still_never_propagates():
    """`probe_model` NE LEVE JAMAIS -- meme un type d'exception que
    `_complete` ne rattrape pas explicitement doit rester local."""
    ok, msg = _backend(_TransportWeirdException()).probe_model()
    assert ok is False, (ok, msg)
    assert "cable coupe" in msg, msg


# ── 2. Deduplication : jamais deux fois pour le meme couple ────────────────

class _FakeSignal:
    """Remplace pyqtSignal pour un test qui ne veut ni QThread reel ni
    reseau : seule la logique de `_start_model_probe` est sous test."""
    def connect(self, *_a, **_kw):
        pass


class _FakeProbeWorker:
    """Bouchon de `_ProbeWorker` : n'ouvre AUCUN thread ni connexion, se
    contente d'enregistrer les couples pour lesquels il a ete construit."""
    calls: list[tuple[str, str]] = []

    def __init__(self, provider_id: str, model: str, parent=None):
        _FakeProbeWorker.calls.append((provider_id, model))
        self.finished_probe = _FakeSignal()
        self.finished = _FakeSignal()

    def start(self):
        pass

    def deleteLater(self):
        pass


class _FakeCombo:
    """Bouchon de QComboBox : `_on_models_fetched` ne fait que le remplir."""
    def __init__(self):
        self._texte = ""

    def blockSignals(self, _b): pass
    def clear(self): pass
    def addItems(self, _items): pass
    def currentText(self) -> str: return self._texte
    def setCurrentText(self, t): self._texte = t


class _FakeLineEdit:
    """Bouchon de QLineEdit : `_on_save` n'en lit que le texte."""
    def __init__(self, texte: str = ""):
        self._texte = texte

    def text(self) -> str:
        return self._texte


class _FakeRadio:
    """Bouchon de QRadioButton : `_on_save` n'appelle que `isChecked`."""
    def __init__(self, coche: bool = False):
        self._coche = coche

    def isChecked(self) -> bool:
        return self._coche


def _bare_section() -> CloudSection:
    """Une CloudSection minimale, JAMAIS construite via `__init__` (qui
    batirait de vrais widgets, lirait le trousseau, etc.) -- motif
    `CloudSection.__new__(CloudSection)` deja utilise par
    scripts/test_module_alias_lookup.py pour StudioView. Seuls les
    attributs que `_start_model_probe` lit sont poses a la main."""
    section = CloudSection.__new__(CloudSection)
    section._probed_pairs = set()
    section._probe_worker = None
    # ⚠️ Poser TOUS les attributs que lit le code sous test. Un oubli ne se
    # lit pas comme un AttributeError : PyQt le maquille en << super-class
    # __init__() of type _CloudSection was never called >>, un message qui
    # envoie chercher le defaut au mauvais endroit.
    section._probe_verdicts = {}
    section._probe_timer = None
    section._probe_dots = 0
    section._lbl_models_status = QLabel()
    # L'animation et la pastille sont testees ailleurs : ici on ne veut ni
    # QTimer ni ecriture d'etat global.
    section._start_checking_animation = lambda: None
    section._stop_checking_animation = lambda: None
    section._publish_probe_state = lambda _pid, _ok: None
    # Defauts surchargeables : depuis QA AI1 le chemin de deduplication
    # REAFFICHE le verdict, donc il lit le fournisseur et le modele courants.
    section.selected_provider_id = lambda: "gemini"
    section._model_text = lambda: ""
    return section


# ── 3. L'affichage ne survit pas a ce qui le rendait vrai ──────────────────
#
# Revue finale du 2026-09-03 : la premiere version ecrivait le verdict
# DIRECTEMENT dans le label et ne l'effacait que s'il etait son propre
# message. Un << Ce modele a repondu >> survivait donc a un changement de
# fournisseur, et un << n'a pas repondu >> accusait un modele jamais verifie.

def _texte(section) -> str:
    """Le texte NU du label : depuis QA AI1 il est colore, donc enveloppe
    dans un <span>. Comparer la chaine brute cassait des tests qui portaient
    sur le SENS, pas sur la mise en forme."""
    import re as _re
    return _re.sub(r"<[^>]+>", "", section._lbl_models_status.text())


def _status_section(modele: str = "", pid: str = "gemini") -> CloudSection:
    """⛔ `cle` n'est pas un confort : sans lui, ces tests lisaient le VRAI
    trousseau de la machine. `_refresh_model_status` choisit entre deux
    messages selon qu'une cle existe (<< selectionne-en un dans la liste >>)
    ou non (<< enregistre d'abord ta cle >>) -- donc le meme test passait sur
    un poste qui a une cle Gemini et echouait sur un poste qui n'en a pas.
    Releve le 2026-09-14 : deux tests rouges ici, verts ailleurs, pour cette
    seule raison. Un test ne doit pas dependre de ce que le developpeur a
    enregistre."""
    section = _bare_section()
    section.selected_provider_id = lambda: pid
    section._model_text = lambda: modele
    return section


class _ConfigAvecCle:
    """Trousseau de test : une cle existe pour n'importe quel fournisseur.

    ⚠️ Porte AUSSI `model_for` : `_on_models_fetched` le consulte pour
    pre-selectionner le modele enregistre. Un attribut manquant ne se lit pas
    comme un AttributeError franc dans ces tests -- il remonte dans le message
    d'echec du test voisin."""
    def api_key(self, _pid): return "sk-de-test"
    def model_for(self, _pid): return ""


@contextlib.contextmanager
def _avec_une_cle():
    """Detourne `ia_view.ai_config` le temps du test -- cf. `_status_section`."""
    vrai = ia_view.ai_config
    ia_view.ai_config = _ConfigAvecCle()
    try:
        yield
    finally:
        ia_view.ai_config = vrai


def test_a_verdict_does_not_survive_a_provider_change():
    s = TRANSLATIONS["fr"]
    section = _status_section("gemini-3.5-flash", "gemini")
    section._on_model_probed("gemini", "gemini-3.5-flash", True, "")
    assert _texte(section) == s.ia_model_ok

    section.selected_provider_id = lambda: "openai"   # l'utilisateur change
    section._model_text = lambda: "gpt-4o"
    section._refresh_model_status()
    assert _texte(section) != s.ia_model_ok, \
        "le verdict d'un AUTRE fournisseur reste affiche"


def test_a_failure_verdict_does_not_accuse_the_next_model():
    s = TRANSLATIONS["fr"]
    section = _status_section("gemini-2.5-flash", "gemini")
    section._on_model_probed("gemini", "gemini-2.5-flash", False, "retire")
    assert "retire" in _texte(section)

    section._model_text = lambda: "gemini-3.5-flash"  # autre modele, non teste
    section._refresh_model_status()
    assert "retire" not in _texte(section), \
        "un modele jamais verifie herite de l'echec du precedent"


def test_clearing_the_model_brings_back_the_warning():
    s = TRANSLATIONS["fr"]
    section = _status_section("gemini-3.5-flash", "gemini")
    section._on_model_probed("gemini", "gemini-3.5-flash", True, "")
    section._model_text = lambda: ""                  # champ vide
    with _avec_une_cle():
        section._refresh_model_status()
        assert _texte(section) == s.ia_model_none_chosen


def test_a_stale_probe_result_does_not_freeze_the_checking_message():
    """Un resultat obsolete ne doit pas laisser << Verification... >> pour
    toujours : les deux `return` de garde le figeaient."""
    s = TRANSLATIONS["fr"]
    section = _status_section("gemini-3.5-flash", "gemini")
    section._lbl_models_status.setText(s.ia_model_checking)
    section._on_model_probed("gemini", "un-modele-abandonne", True, "")
    assert _texte(section) != s.ia_model_checking


def test_the_model_list_arriving_keeps_the_warning():
    """Sans modele choisi, l'avertissement doit survivre a l'arrivee de la
    liste -- il ne vivait sinon que le temps du chargement."""
    s = TRANSLATIONS["fr"]
    section = _status_section("", "gemini")
    section._model_combo = _FakeCombo()
    with _avec_une_cle():
        section._on_models_fetched("gemini", ["gemini-3.5-flash"], "")
        assert _texte(section) == s.ia_model_none_chosen


def test_the_pill_is_not_green_without_a_model():
    """Depuis la suppression du modele par defaut, une cle peut exister sans
    modele. La pastille etait alors VERTE AVEC HALO -- le signal le plus fort
    de l'app -- pour une generation qui echouerait aussitot."""
    src = (ROOT / "ui" / "ia_view.py").read_text(encoding="utf-8")
    debut = src.index("    def _publier_etat(self)")
    corps = src[debut:src.index("\n    def ", debut + 20)]
    assert "model_for(bid)" in corps and "custom_model" in corps, \
        "la pastille se contente de nouveau de la cle, sans exiger un modele"


# ── 4. Les quatre defauts remontes par la QA AI1 (2026-09-04) ─────────────

class _Transport200NoContentKey:
    """200, mais `message` SANS clé `content` -- reponse REELLE de Gemini 3.x
    a max_tokens=1 : le token a ete depense a reflechir. `_complete` levait
    KeyError ici, et la sonde declarait injoignable un modele parfaitement
    fonctionnel."""
    def post_json(self, url, headers, payload, timeout):
        return {"choices": [{"finish_reason": "length", "index": 0,
                             "message": {"role": "assistant"}}],
                "usage": {"completion_tokens": 0}}


def test_a_thinking_model_that_spent_its_token_is_a_success():
    ok, msg = _backend(_Transport200NoContentKey()).probe_model()
    assert ok is True, (ok, msg)
    assert msg == "", msg


def test_the_probe_gets_a_generous_timeout():
    """Mesure du 2026-09-04 : `gemini-flash-latest` met 30,6 s a repondre.
    Le delai de la LISTE (15 s) le declarait injoignable."""
    from ui.ai_backends.openai_compat import _LIST_TIMEOUT, _PROBE_TIMEOUT
    assert _PROBE_TIMEOUT >= 60, _PROBE_TIMEOUT
    assert _PROBE_TIMEOUT > _LIST_TIMEOUT, (_PROBE_TIMEOUT, _LIST_TIMEOUT)


def test_the_probe_does_not_parse_the_completion():
    """Garde structurelle : reutiliser `_complete` reintroduirait l'exigence
    de forme qui faisait echouer la sonde sur un modele sain."""
    src = (ROOT / "ui" / "ai_backends" / "openai_compat.py").read_text(
        encoding="utf-8")
    debut = src.index("    def probe_model(self)")
    corps = src[debut:src.index("\n    def ", debut + 20)]
    assert "_complete(" not in corps, \
        "probe_model ne doit pas passer par _complete : il exige un `content`"


def test_returning_to_an_already_probed_model_shows_ITS_verdict():
    """Le defaut signale : aller sur un modele, revenir sur un autre deja
    sonde, et lire le message du PRECEDENT. La deduplication empechait toute
    nouvelle sonde, et un seul verdict etait retenu."""
    s = TRANSLATIONS["fr"]
    original = ia_view._ProbeWorker
    ia_view._ProbeWorker = _FakeProbeWorker
    _FakeProbeWorker.calls = []
    try:
        section = _bare_section()
        section._model_text = lambda: "gemini-2.5-flash"
        section._start_model_probe("gemini", "gemini-2.5-flash")
        section._on_model_probed("gemini", "gemini-2.5-flash", False, "retire")

        section._model_text = lambda: "gemini-flash-latest"
        section._start_model_probe("gemini", "gemini-flash-latest")
        section._on_model_probed("gemini", "gemini-flash-latest", True, "")
        assert _texte(section) == s.ia_model_ok

        # Retour sur le premier : deja sonde -> aucune nouvelle sonde, mais
        # SON verdict doit revenir.
        section._model_text = lambda: "gemini-2.5-flash"
        avant = len(_FakeProbeWorker.calls)
        section._start_model_probe("gemini", "gemini-2.5-flash")
        assert len(_FakeProbeWorker.calls) == avant, "le reseau a ete rappele"
        assert "retire" in _texte(section), \
            _texte(section)
    finally:
        ia_view._ProbeWorker = original


def test_an_unreachable_model_reddens_the_pill():
    """La pastille ne savait dire que << une cle existe >> : elle restait
    verte pour un modele qui ne repond pas. `ai_status` traite tout etat
    inconnu comme une erreur, donc un etat dedie suffit."""
    from ui.ai_status import ai_status, KINDS_OK, KINDS_WARN

    class _ConfigBouchon:
        backend_id = "gemini"

    section = _bare_section()
    section._publish_probe_state = \
        CloudSection._publish_probe_state.__get__(section, CloudSection)
    vrai_config = ia_view.ai_config
    ia_view.ai_config = _ConfigBouchon()
    try:
        section._publish_probe_state("gemini", False)
        etat = ai_status.state
        assert etat is not None and etat not in KINDS_OK and \
            etat not in KINDS_WARN, f"pastille non rouge : {etat!r}"
        section._publish_probe_state("gemini", True)
        assert ai_status.state in KINDS_OK, ai_status.state
        # Un fournisseur qui n'est PAS le backend actif ne publie rien.
        section._publish_probe_state("openai", False)
        assert ai_status.state in KINDS_OK, ai_status.state
    finally:
        ia_view.ai_config = vrai_config
        ai_status.set_state(None)


def test_the_status_label_wraps():
    """Le message du fournisseur est long : sans retour a la ligne, il est
    COUPE et l'utilisateur ne lit que le texte generique."""
    src = (ROOT / "ui" / "ia_view.py").read_text(encoding="utf-8")
    assert "self._lbl_models_status.setWordWrap(True)" in src


def test_the_checking_message_is_animated():
    """30 s de texte fige se lisent comme une app bloquee."""
    src = (ROOT / "ui" / "ia_view.py").read_text(encoding="utf-8")
    for attendu in ("_start_checking_animation", "_paint_checking",
                    "_stop_checking_animation", "signal_ok"):
        assert attendu in src, attendu


def test_the_verdict_is_red_on_failure_and_green_on_success():
    """Demande utilisateur (QA AI1) : un echec doit se voir en ROUGE, un
    succes en VERT. Un message d'erreur de la couleur du texte courant se lit
    comme une information neutre."""
    from ui.theme import theme_manager
    c = theme_manager.current
    section = _status_section("gemini-3.5-flash", "gemini")
    section._on_model_probed("gemini", "gemini-3.5-flash", True, "")
    brut = section._lbl_models_status.text()
    assert c.signal_ok in brut, brut

    section._model_text = lambda: "gemini-2.5-flash"
    section._on_model_probed("gemini", "gemini-2.5-flash", False, "retire")
    brut = section._lbl_models_status.text()
    assert c.signal_error in brut, brut


def test_the_failure_message_carries_only_the_providers_words():
    """Demande utilisateur : plus de << Modele ou URL introuvable -- verifie
    le modele et l'URL de base >> avant l'information utile. Trois fois la
    meme idee, et l'utile passait a la ligne suivante."""
    ok, msg = _backend(_Transport404Gemini()).probe_model()
    assert ok is False
    assert "no longer available to new users" in msg, msg
    assert "URL de base" not in msg and "URL not found" not in msg, msg


def test_an_already_tested_unavailable_model_reddens_the_pill_again():
    """Retour utilisateur (QA AI4ter) : revenir sur un modele indisponible
    DEJA teste laissait la pastille VERTE devant un message d'erreur rouge.
    La deduplication ne rafraichissait que le label."""
    from ui.ai_status import ai_status, KINDS_OK

    class _ConfigBouchon:
        backend_id = "gemini"
        def api_key(self, _pid): return "sk-x"

    original = ia_view._ProbeWorker
    ia_view._ProbeWorker = _FakeProbeWorker
    _FakeProbeWorker.calls = []
    vrai_config = ia_view.ai_config
    ia_view.ai_config = _ConfigBouchon()
    section = _bare_section()
    section._publish_probe_state =         CloudSection._publish_probe_state.__get__(section, CloudSection)
    try:
        section._model_text = lambda: "gemini-2.5-flash"
        section._start_model_probe("gemini", "gemini-2.5-flash")
        section._on_model_probed("gemini", "gemini-2.5-flash", False, "retire")
        assert ai_status.state not in KINDS_OK, ai_status.state

        section._model_text = lambda: "gemini-3.5-flash"
        section._start_model_probe("gemini", "gemini-3.5-flash")
        section._on_model_probed("gemini", "gemini-3.5-flash", True, "")
        assert ai_status.state in KINDS_OK, ai_status.state

        # Retour sur l'indisponible : deja sonde, donc AUCUN appel reseau --
        # mais la pastille doit repasser au rouge.
        section._model_text = lambda: "gemini-2.5-flash"
        avant = len(_FakeProbeWorker.calls)
        section._start_model_probe("gemini", "gemini-2.5-flash")
        assert len(_FakeProbeWorker.calls) == avant, "le reseau a ete rappele"
        assert ai_status.state not in KINDS_OK,             f"pastille restee verte : {ai_status.state!r}"
    finally:
        ia_view._ProbeWorker = original
        ia_view.ai_config = vrai_config
        ai_status.set_state(None)


def test_the_model_field_is_greyed_without_a_key():
    """Retour utilisateur (QA AI3) : sans cle, la liste ne peut pas etre
    chargee et rien ne peut etre verifie. Un champ actif inviterait a saisir
    un modele qui ne sera jamais eprouve."""
    class _Edit:
        def __init__(self): self.invite = ""
        def setPlaceholderText(self, t): self.invite = t

    class _Combo:
        def __init__(self):
            self.actif = None
            self._edit = _Edit()
        def setEnabled(self, v): self.actif = v
        def lineEdit(self): return self._edit

    class _ConfigSansCle:
        def api_key(self, _pid): return ""

    class _ConfigAvecCle:
        def api_key(self, _pid): return "sk-x"

    vrai = ia_view.ai_config
    section = _bare_section()
    section._model_combo = _Combo()
    try:
        from ui.i18n import lang_manager
        s = lang_manager.current
        ia_view.ai_config = _ConfigSansCle()
        section._refresh_model_field_state()
        assert section._model_combo.actif is False
        # L'invite doit dire le geste POSSIBLE : sans cle, ce n'est pas
        # << choisir dans la liste >>.
        assert section._model_combo.lineEdit().invite ==             s.ia_model_placeholder_no_key

        ia_view.ai_config = _ConfigAvecCle()
        section._refresh_model_field_state()
        assert section._model_combo.actif is True
        assert section._model_combo.lineEdit().invite == s.ia_model_placeholder
    finally:
        ia_view.ai_config = vrai


def test_the_no_model_statement_survives_the_absence_of_a_key():
    """Retour utilisateur (QA AI3bis) : << Aucun modele choisi >> est un
    CONSTAT, vrai avec ou sans cle. C'est la CONSIGNE qui devient impossible
    a suivre. Ma premiere version supprimait le constat et gardait la
    consigne -- exactement l'inverse."""
    from ui.i18n import TRANSLATIONS

    class _SansCle:
        def api_key(self, _p): return ""

    section = _status_section("", "gemini")
    vrai = ia_view.ai_config
    ia_view.ai_config = _SansCle()
    try:
        section._refresh_model_status()
        txt = _texte(section)
        assert txt, "le constat a ete supprime au lieu de la consigne"
        assert txt == TRANSLATIONS["fr"].ia_model_none_no_key, txt
    finally:
        ia_view.ai_config = vrai
    for code, tr in TRANSLATIONS.items():
        assert tr.ia_model_none_no_key, code
        assert tr.ia_model_none_no_key != tr.ia_model_none_chosen, code


def test_the_placeholder_no_longer_promises_a_default_model():
    """Il disait << Laisser vide pour le modele par defaut >> -- un reste de
    la fonctionnalite SUPPRIMEE, donc une phrase fausse."""
    from ui.i18n import TRANSLATIONS
    vus = {}
    for code, s in TRANSLATIONS.items():
        txt = s.ia_model_placeholder
        assert txt, code
        for interdit in ("par défaut", "default model", "por defecto",
                         "predefinito"):
            assert interdit not in txt, (code, txt)
        vus[code] = txt
    assert len(set(vus.values())) == len(vus), vus


def _vue_avec_verdict(verdict):
    """Une IAView minimale dont la section cloud rend `verdict`."""
    class _Cloud:
        def probe_verdict_for(self, _pid, _model): return verdict

    vue = ia_view.IAView.__new__(ia_view.IAView)
    vue._sections = {}
    vue._cloud = _Cloud()
    return vue


class _CfgCloud:
    backend_id = "gemini"
    custom_base_url = ""
    custom_model = ""
    def api_key(self, _p): return "sk-x"
    def model_for(self, _p): return "gemini-2.5-flash"


def test_the_pill_is_grey_until_the_model_has_been_probed():
    """Retour utilisateur (2026-09-04) : l'app DEMARRAIT au vert sur un
    modele retire. La pastille concluait de la seule presence d'une cle et
    d'un modele -- elle n'avait rien verifie. `None` (gris) est la valeur que
    ai_status reserve a << pas encore d'information >>."""
    from ui.ai_status import ai_status, KINDS_OK
    vrai = ia_view.ai_config
    ia_view.ai_config = _CfgCloud()
    try:
        ai_status.set_state("cloud_key_ok")      # etat menteur de depart
        ia_view.IAView._publier_etat(_vue_avec_verdict(None))
        assert ai_status.state is None, ai_status.state

        ia_view.IAView._publier_etat(_vue_avec_verdict(False))
        assert ai_status.state not in KINDS_OK and ai_status.state is not None,             ai_status.state

        ia_view.IAView._publier_etat(_vue_avec_verdict(True))
        assert ai_status.state in KINDS_OK, ai_status.state
    finally:
        ia_view.ai_config = vrai
        ai_status.set_state(None)


def test_the_startup_path_probes_the_saved_model():
    """Garde structurelle : c'est `_maybe_fetch_models` -- appele a la
    construction et a la restauration du fournisseur actif -- qui doit lancer
    la sonde. Sans elle, la pastille resterait grise jusqu'a ce que
    l'utilisateur aille lui-meme dans l'onglet."""
    src = (ROOT / "ui" / "ia_view.py").read_text(encoding="utf-8")
    debut = src.index("    def _maybe_fetch_models(self)")
    corps = src[debut:src.index("\n    def ", debut + 20)]
    assert "_start_model_probe" in corps, \
        "le demarrage ne sonde pas le modele deja enregistre"


def test_probe_is_never_relaunched_for_an_already_checked_pair():
    original = ia_view._ProbeWorker
    ia_view._ProbeWorker = _FakeProbeWorker
    _FakeProbeWorker.calls = []
    try:
        section = _bare_section()
        section._start_model_probe("gemini", "gemini-3.5-flash")
        section._start_model_probe("gemini", "gemini-3.5-flash")  # meme couple -> ignore
        section._start_model_probe("gemini", "gemini-3.5-flash")  # x3 -> ignore
        assert _FakeProbeWorker.calls == [("gemini", "gemini-3.5-flash")], \
            _FakeProbeWorker.calls
    finally:
        ia_view._ProbeWorker = original


def test_a_different_model_for_the_same_provider_is_a_new_pair():
    original = ia_view._ProbeWorker
    ia_view._ProbeWorker = _FakeProbeWorker
    _FakeProbeWorker.calls = []
    try:
        section = _bare_section()
        section._start_model_probe("gemini", "gemini-3.5-flash")
        section._start_model_probe("gemini", "gemini-2.5-flash")
        assert _FakeProbeWorker.calls == [
            ("gemini", "gemini-3.5-flash"), ("gemini", "gemini-2.5-flash"),
        ], _FakeProbeWorker.calls
    finally:
        ia_view._ProbeWorker = original


def test_saving_a_key_forgets_that_providers_verdicts():
    """Corriger sa cle doit permettre de RE-verifier le meme modele.

    La deduplication est par session. Sans oubli a l'enregistrement de la
    cle, une sonde tombee en << cle invalide >> interdisait de re-verifier le
    meme modele apres correction : il aurait fallu redemarrer l'app.

    ⚠️ Ce test appelle le VRAI `_on_save`. Sa premiere version recopiait la
    comprehension d'ensemble dans le test au lieu d'appeler la production :
    inverser le filtre dans `_on_save` (garder le perime, oublier les autres)
    la laissait VERTE. Trouve par mutation en revue finale du 2026-09-03 --
    un test qui reimplemente ce qu'il verifie ne verifie rien.
    """
    original = ia_view._ProbeWorker
    ia_view._ProbeWorker = _FakeProbeWorker
    _FakeProbeWorker.calls = []
    ecrits: list[tuple] = []
    try:
        section = _bare_section()
        # Tout ce que `_on_save` touche est bouchonne : ni trousseau, ni
        # config reelle, ni reseau.
        section._key_input = _FakeLineEdit("sk-nouvelle-cle")
        section._base_input = _FakeLineEdit("")
        section.selected_provider_id = lambda: "gemini"
        section._model_text = lambda: "gemini-3.5-flash"
        section._confirm_saved = lambda: None
        section._start_models_fetch = lambda _pid: None
        # Depuis QA AI3, `_on_save` regrise le champ modele : hors
        # sujet ici, et ce test n'a pas de vrai combo.
        section._refresh_model_field_state = lambda: None
        section.radio = _FakeRadio(False)
        vrai_set_api_key = ia_view.ai_config.set_api_key
        vrai_set_model = ia_view.ai_config.set_model
        ia_view.ai_config.set_api_key = lambda p, k: ecrits.append(("key", p))
        ia_view.ai_config.set_model = lambda p, m: ecrits.append(("model", p))

        section._start_model_probe("gemini", "gemini-3.5-flash")
        section._start_model_probe("openai", "gpt-4o")
        assert len(_FakeProbeWorker.calls) == 2, _FakeProbeWorker.calls

        try:
            section._on_save()          # <-- la PRODUCTION, pas une copie
        finally:
            ia_view.ai_config.set_api_key = vrai_set_api_key
            ia_view.ai_config.set_model = vrai_set_model
        assert ecrits, "le bouchon n'a pas ete appele : _on_save n'a pas tourne"

        # Le verdict de `gemini` est perime -> la sonde repart.
        section._start_model_probe("gemini", "gemini-3.5-flash")
        assert _FakeProbeWorker.calls[-1] == ("gemini", "gemini-3.5-flash"), \
            _FakeProbeWorker.calls
        # Celui d'`openai` tient toujours : ses identifiants n'ont pas bouge.
        section._start_model_probe("openai", "gpt-4o")
        assert len(_FakeProbeWorker.calls) == 3, _FakeProbeWorker.calls
    finally:
        ia_view._ProbeWorker = original


def test_an_empty_model_never_starts_a_probe():
    """Rien a verifier si l'utilisateur a vide le champ modele."""
    original = ia_view._ProbeWorker
    ia_view._ProbeWorker = _FakeProbeWorker
    _FakeProbeWorker.calls = []
    try:
        section = _bare_section()
        section._start_model_probe("gemini", "")
        assert _FakeProbeWorker.calls == []
    finally:
        ia_view._ProbeWorker = original


# ── 3. Les 3 cles i18n existent, non vides, dans les 4 langues ─────────────

_NEW_KEYS = ("ia_model_checking", "ia_model_ok", "ia_model_ko")


def test_the_three_keys_exist_and_are_nonempty_in_every_language():
    assert len(TRANSLATIONS) >= 4, \
        f"seulement {len(TRANSLATIONS)} langue(s) chargee(s)"
    for code, s in TRANSLATIONS.items():
        for key in _NEW_KEYS:
            val = getattr(s, key, "")
            assert val, f"{code}: cle '{key}' manquante ou vide"


def test_each_key_is_actually_translated_across_languages():
    """Preuve minimale que ce ne sont pas 4 copies du meme texte : au moins
    deux langues doivent differer pour chaque cle."""
    for key in _NEW_KEYS:
        values = {code: getattr(s, key) for code, s in TRANSLATIONS.items()}
        assert len(set(values.values())) > 1, (key, values)


def test_the_failure_key_carries_a_detail_placeholder():
    """`ia_model_ko` doit pouvoir accueillir le message du fournisseur --
    sans placeholder, `_on_model_probed` afficherait un texte fige."""
    for code, s in TRANSLATIONS.items():
        assert "{detail}" in s.ia_model_ko, \
            f"{code}: 'ia_model_ko' n'a pas de placeholder {{detail}}"


TESTS = [
    test_a_200_with_empty_string_content_is_a_success,
    test_a_200_with_null_content_is_also_a_success,
    test_a_200_with_real_content_is_a_success,
    test_a_404_with_the_gemini_body_carries_the_providers_words,
    test_a_connection_error_is_a_failure_not_an_exception,
    test_a_never_seen_exception_type_still_never_propagates,
    test_a_verdict_does_not_survive_a_provider_change,
    test_a_failure_verdict_does_not_accuse_the_next_model,
    test_clearing_the_model_brings_back_the_warning,
    test_a_stale_probe_result_does_not_freeze_the_checking_message,
    test_the_model_list_arriving_keeps_the_warning,
    test_the_pill_is_not_green_without_a_model,
    test_a_thinking_model_that_spent_its_token_is_a_success,
    test_the_probe_gets_a_generous_timeout,
    test_the_probe_does_not_parse_the_completion,
    test_returning_to_an_already_probed_model_shows_ITS_verdict,
    test_an_unreachable_model_reddens_the_pill,
    test_the_status_label_wraps,
    test_the_checking_message_is_animated,
    test_the_verdict_is_red_on_failure_and_green_on_success,
    test_the_failure_message_carries_only_the_providers_words,
    test_an_already_tested_unavailable_model_reddens_the_pill_again,
    test_the_model_field_is_greyed_without_a_key,
    test_the_no_model_statement_survives_the_absence_of_a_key,
    test_the_placeholder_no_longer_promises_a_default_model,
    test_the_pill_is_grey_until_the_model_has_been_probed,
    test_the_startup_path_probes_the_saved_model,
    test_probe_is_never_relaunched_for_an_already_checked_pair,
    test_a_different_model_for_the_same_provider_is_a_new_pair,
    test_saving_a_key_forgets_that_providers_verdicts,
    test_an_empty_model_never_starts_a_probe,
    test_the_three_keys_exist_and_are_nonempty_in_every_language,
    test_each_key_is_actually_translated_across_languages,
    test_the_failure_key_carries_a_detail_placeholder,
]


def main() -> int:
    before = _config_snapshot()
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  OK   {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
    after = _config_snapshot()
    if before != after:
        failed += 1
        print("  FAIL config utilisateur MODIFIEE par les tests -- "
              f"{CONFIG_PATH} a change")
    else:
        print(f"  (config utilisateur inchangee : {CONFIG_PATH})")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

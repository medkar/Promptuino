"""
AI configuration manager.

Storage:
  - Active backend → ~/Documents/Promptuino/config.json (non-sensitive)
  - API keys      → Windows Credential Manager via `keyring` (never in plaintext on disk)

Migration: if old plaintext keys are found in config.json,
they are migrated to keyring then removed from the file.
"""
import json
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

try:
    import keyring
    _KEYRING_OK = True
except Exception:
    _KEYRING_OK = False

_SERVICE    = "promptuino"
from .paths import DATA_DIR
CONFIG_PATH = DATA_DIR / "config.json"

# Taille de contexte des moteurs locaux (decision de l'auteur, 2026-11-06) :
# la MEME regle pour Ollama et LM Studio, de `CTX_PROMPTUINO` au maximum du
# modele, par pas de `PAS`. Le maximum depend du modele : il s'applique a
# l'usage (`contexte.ramener`), pas ici. Remplace les cinq paliers
# 2 048..32 768 d'Ollama, et le 8 192 par defaut : une valeur plus petite
# enregistree avant passe au plancher a la lecture.
from .contexte import CTX_PROMPTUINO as _CTX_DEFAULT, PAS as _CTX_PAS  # noqa: E402
from .reflexion import NIVEAU_CHATGPT_DEFAUT, niveau_chatgpt  # noqa: E402

_OLLAMA_NUM_CTX_DEFAULT = _CTX_DEFAULT


def _write_config_atomic(data: dict) -> None:
    """Ecrit config.json d'un coup : fichier temporaire du MEME dossier, puis
    os.replace (meme discipline que ui/session.py). Une ecriture en place
    coupee par un plantage laissait un fichier tronque, que `_load` avalait
    en silence : tous les reglages IA revenaient aux defauts (audit
    2026-11-06). Lit `CONFIG_PATH` a l'appel, pour que les tests le
    detournent."""
    import os
    import tempfile
    path = Path(CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".config-",
                                    suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _snap_num_ctx(value) -> int:
    """Sur un pas, jamais sous le plancher ; illisible -> le plancher."""
    try:
        v = int(value) // _CTX_PAS * _CTX_PAS
    except (TypeError, ValueError):
        return _CTX_DEFAULT
    return max(v, _CTX_DEFAULT)


_LMSTUDIO_BASE_URL_DEFAULT = "http://127.0.0.1:1234/v1"

_DEFAULTS: dict = {
    # Ollama : le moteur local, sans compte ni cle d'API -- c'est ce que le
    # README promet (« No account and no API key are needed »).
    "ai_backend":   "ollama",
    "ollama_model": "gemma4:e2b",
    "models":       {},          # {provider_id: model override}
    "custom_base_url": "",
    "custom_model":    "",
    "ollama_num_ctx":  _OLLAMA_NUM_CTX_DEFAULT,
    # LM Studio : serveur LOCAL compatible OpenAI, sans cle.
    # ⛔ 127.0.0.1 et NON « localhost », meme si la documentation de LM Studio
    # ecrit souvent le second : sur Windows « localhost » peut resoudre en IPv6
    # (::1) alors que le serveur n'ecoute qu'en IPv4 -- son propre CLI
    # documente `--bind "127.0.0.1" (default)`. Ce projet s'est deja fait
    # prendre avec Ollama sur cette machine.
    "lmstudio_base_url": _LMSTUDIO_BASE_URL_DEFAULT,
    # ⛔ Aucun modele par defaut (decision du 2026-09-03) : un defaut se
    # recopie dans la config de qui ouvre l'ecran une fois, et survit au
    # modele qu'il nommait.
    "lmstudio_model":    "",
    # Le contexte auquel « Charger » demande a LM Studio de charger le modele.
    "lmstudio_num_ctx":  _CTX_DEFAULT,
    # Compte ChatGPT (TODO #122) : aucun modele par defaut non plus -- le
    # catalogue depend du compte. Les JETONS ne sont jamais ici : trousseau.
    "chatgpt_model":     "",
    # Le guide d'OpenAI : la fenetre d'accueil ne s'affiche qu'UNE fois.
    "chatgpt_welcome_shown": False,
    # La reflexion (TODO #123, decisions de l'auteur du 2026-11-06) :
    # DESACTIVEE par defaut sur les moteurs locaux, le cran du milieu pour
    # ChatGPT. Ce que le MODELE permet se decide a l'usage (`ui.reflexion`).
    "ollama_think":      False,
    "lmstudio_think":    False,
    "chatgpt_reasoning": NIVEAU_CHATGPT_DEFAUT,
}


def migre_backend_retire(backend_id: str) -> "tuple[str, bool]":
    """Rend (backend a utiliser, a-t-on migre ?).

    Une configuration enregistree peut designer un moteur que CETTE version ne
    propose plus : sans correction l'application demarrerait sans moteur, sans
    rien dire. Tout identifiant inconnu de la fabrique bascule donc sur Ollama.

    ⚠️ La regle est « inconnu de cette version », et non « c'etait tel
    backend » : le code n'a ainsi pas besoin de NOMMER ce qu'il a retire, elle
    vaut pour tout retrait futur, et elle rattrape aussi un fichier corrompu.
    Un backend facultatif present (poste de developpement) est connu de la
    fabrique, donc jamais migre -- sans quoi son auteur serait ramene sur
    Ollama a chaque demarrage.

    ⚠️ Fonction PURE, pour qu'un test puisse l'eprouver sans toucher au
    disque ni construire la configuration.
    """
    from .ai_backends.factory import known_backend_ids
    if not backend_id:
        return "ollama", False          # rien n'avait ete choisi : rien a dire
    if backend_id in known_backend_ids():
        return backend_id, False
    return "ollama", True


class AIConfig(QObject):
    """AI configuration singleton — emits `changed` when the active backend changes."""

    changed = pyqtSignal(str)   # emits the new backend_id

    def __init__(self):
        super().__init__(None)
        self._data: dict = dict(_DEFAULTS)
        # dict(_DEFAULTS) is shallow: detach the nested `models` dict so it is
        # never shared with _DEFAULTS across instances.
        self._data["models"] = dict(self._data.get("models", {}))
        # Vrai une seule fois, au demarrage qui a migre : la vue s'en sert
        # pour dire a l'utilisateur ce qui a change, puis n'y revient plus.
        self.backend_migre_depuis_retire = False
        self._load()

    # ── JSON persistence (backend only) ─────────────────

    def _load(self):
        try:
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH, encoding="utf-8") as f:
                    saved = json.load(f)
                if "ai_backend" in saved:
                    bid = saved["ai_backend"]
                    if bid == "anthropic_api":      # migration: old id -> new
                        bid = "anthropic"
                    bid, migre = migre_backend_retire(bid)
                    self._data["ai_backend"] = bid
                    # ⚠️ On ENREGISTRE tout de suite. Sans ca le fichier
                    # garderait l'ancien identifiant, la migration se
                    # rejouerait a chaque demarrage, et le message qui
                    # l'annonce avec elle -- or il doit etre dit UNE fois.
                    if migre:
                        self.backend_migre_depuis_retire = True
                if "ollama_model" in saved:
                    self._data["ollama_model"] = saved["ollama_model"]
                if isinstance(saved.get("models"), dict):
                    self._data["models"] = saved["models"]
                self._data["custom_base_url"] = saved.get("custom_base_url", "")
                self._data["custom_model"] = saved.get("custom_model", "")
                # Une URL vide dans le fichier retombe sur le defaut : un
                # champ efface ne doit pas rendre le backend inutilisable.
                self._data["lmstudio_base_url"] = (
                    saved.get("lmstudio_base_url") or _LMSTUDIO_BASE_URL_DEFAULT
                )
                self._data["lmstudio_model"] = saved.get("lmstudio_model", "")
                self._data["chatgpt_model"] = saved.get("chatgpt_model", "")
                self._data["chatgpt_welcome_shown"] = bool(
                    saved.get("chatgpt_welcome_shown", False))
                self._data["ollama_num_ctx"] = _snap_num_ctx(
                    saved.get("ollama_num_ctx", _OLLAMA_NUM_CTX_DEFAULT)
                )
                self._data["lmstudio_num_ctx"] = _snap_num_ctx(
                    saved.get("lmstudio_num_ctx", _CTX_DEFAULT))
                self._data["ollama_think"] = bool(saved.get("ollama_think", False))
                self._data["lmstudio_think"] = bool(saved.get("lmstudio_think", False))
                self._data["chatgpt_reasoning"] = niveau_chatgpt(
                    saved.get("chatgpt_reasoning"))
                # Migration: plaintext keys present → keyring → removal from the JSON
                self._migrate_plain_keys(saved)
                # ⚠️ Enregistrement de la migration de backend APRES le
                # chargement de tous les champs : fait plus tot, il
                # reecrivait le fichier avec les valeurs PAR DEFAUT et
                # effacait tous les choix de l'utilisateur.
                if self.backend_migre_depuis_retire:
                    self._save_backend()
        except Exception:
            pass

    def _migrate_plain_keys(self, saved: dict):
        """Transfers plaintext keys to keyring and removes them from the JSON."""
        migrated = False
        for field in ("gemini_api_key", "anthropic_api_key"):
            if saved.get(field):
                self._keyring_set(field, saved[field])
                saved.pop(field)
                migrated = True
        if migrated:
            try:
                _write_config_atomic(saved)
            except Exception:
                pass

    def _save_backend(self):
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            existing: dict = {}
            if CONFIG_PATH.exists():
                try:
                    with open(CONFIG_PATH, encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    pass
            # Never rewrite plaintext keys, even if some are still lying around
            existing.pop("gemini_api_key", None)
            existing.pop("anthropic_api_key", None)
            existing["ai_backend"]   = self._data["ai_backend"]
            existing["ollama_model"] = self._data.get("ollama_model", "gemma4:e2b")
            existing["models"]          = self._data.get("models", {})
            existing["custom_base_url"] = self._data.get("custom_base_url", "")
            existing["custom_model"]    = self._data.get("custom_model", "")
            existing["lmstudio_base_url"] = self._data.get(
                "lmstudio_base_url", _LMSTUDIO_BASE_URL_DEFAULT)
            existing["lmstudio_model"]   = self._data.get("lmstudio_model", "")
            existing["chatgpt_model"]    = self._data.get("chatgpt_model", "")
            existing["chatgpt_welcome_shown"] = bool(
                self._data.get("chatgpt_welcome_shown", False))
            existing["ollama_num_ctx"] = self._data.get(
                "ollama_num_ctx", _OLLAMA_NUM_CTX_DEFAULT
            )
            existing["lmstudio_num_ctx"] = self._data.get(
                "lmstudio_num_ctx", _CTX_DEFAULT)
            existing["ollama_think"] = bool(self._data.get("ollama_think", False))
            existing["lmstudio_think"] = bool(self._data.get("lmstudio_think", False))
            existing["chatgpt_reasoning"] = niveau_chatgpt(
                self._data.get("chatgpt_reasoning"))
            _write_config_atomic(existing)
        except Exception:
            pass

    # ── Keyring (API keys) ────────────────────────────────────

    def _keyring_get(self, key: str) -> str:
        if not _KEYRING_OK:
            return ""
        try:
            return keyring.get_password(_SERVICE, key) or ""
        except Exception:
            return ""

    def _keyring_set(self, key: str, value: str):
        if not _KEYRING_OK:
            return
        try:
            if value:
                keyring.set_password(_SERVICE, key, value)
            else:
                try:
                    keyring.delete_password(_SERVICE, key)
                except Exception:
                    pass
        except Exception:
            pass

    # ── Properties ────────────────────────────────────────────

    @property
    def backend_id(self) -> str:
        return self._data["ai_backend"]

    @backend_id.setter
    def backend_id(self, value: str):
        if self._data["ai_backend"] != value:
            self._data["ai_backend"] = value
            self._save_backend()
            self.changed.emit(value)

    def api_key(self, provider_id: str) -> str:
        return self._keyring_get(f"{provider_id}_api_key")

    def clear_all_api_keys(self) -> int:
        """Efface TOUTES les cles d'API du trousseau. Rend le nombre efface.

        Appelee par `main.py --clear-credentials`, que le desinstalleur lance
        si l'utilisateur le demande (TODO #78). Les cles vivent dans le
        Gestionnaire d'identifiants Windows, JAMAIS dans le dossier de l'app :
        une desinstallation ne les emporte donc pas, et personne ne le disait.

        ⚠️ C'est l'APPLICATION qui efface, pas l'installeur : elle seule sait
        quels services elle a ecrits. Une liste recopiee cote Inno Setup
        aurait derive au premier fournisseur ajoute.

        ⚠️ Limite : le trousseau est PAR UTILISATEUR WINDOWS. Si la
        desinstallation est lancee avec elevation sous un autre compte, ce
        sont les cles de CE compte qui seraient visees -- donc aucune.
        """
        if not _KEYRING_OK:
            return 0
        from .ai_backends.providers import PROVIDERS
        from .chatgpt_auth import noms_dans_le_trousseau
        efface = 0
        # La connexion ChatGPT (TODO #122) vit dans le meme service : elle
        # part avec les cles, sinon elle survivrait a la desinstallation. Elle
        # occupe plusieurs entrees (limite de taille de Windows).
        # « custom » n'est pas un preset de PROVIDERS mais a sa propre cle
        # (ia_view -> set_api_key('custom', ...)) : une cle payante distante.
        noms = [f"{p.id}_api_key" for p in PROVIDERS] + ["custom_api_key"]
        for nom in noms + noms_dans_le_trousseau():
            try:
                if keyring.get_password(_SERVICE, nom):
                    keyring.delete_password(_SERVICE, nom)
                    efface += 1
            except Exception:
                pass
        return efface

    def set_api_key(self, provider_id: str, value: str):
        self._keyring_set(f"{provider_id}_api_key", value)

    def model_for(self, provider_id: str) -> str:
        """Le modèle CHOISI pour ce fournisseur, ou "" si aucun.

        Plus de repli sur un défaut du préréglage : les modèles bougent, et un
        défaut écrit une fois se recopie dans la config de tous ceux qui
        ouvrent l'écran. C'est ainsi que `gemini-2.5-flash`, retiré par Google,
        a continué d'être demandé (spec 2026-09-03).
        """
        return self._data.get("models", {}).get(provider_id) or ""

    def set_model(self, provider_id: str, model: str):
        models = dict(self._data.get("models", {}))
        if model:
            models[provider_id] = model
        else:
            models.pop(provider_id, None)
        if models != self._data.get("models"):
            self._data["models"] = models
            self._save_backend()
            self.changed.emit(self._data["ai_backend"])

    @property
    def custom_base_url(self) -> str:
        return self._data.get("custom_base_url", "")

    @custom_base_url.setter
    def custom_base_url(self, value: str):
        if self._data.get("custom_base_url") != value:
            self._data["custom_base_url"] = value
            self._save_backend()

    @property
    def custom_model(self) -> str:
        return self._data.get("custom_model", "")

    @custom_model.setter
    def custom_model(self, value: str):
        if self._data.get("custom_model") != value:
            self._data["custom_model"] = value
            self._save_backend()

    @property
    def lmstudio_base_url(self) -> str:
        return self._data.get("lmstudio_base_url", _LMSTUDIO_BASE_URL_DEFAULT)

    @lmstudio_base_url.setter
    def lmstudio_base_url(self, value: str):
        # Vider le champ rend le defaut, il ne casse pas le backend.
        value = (value or "").strip() or _LMSTUDIO_BASE_URL_DEFAULT
        if self._data.get("lmstudio_base_url") != value:
            self._data["lmstudio_base_url"] = value
            self._save_backend()

    @property
    def lmstudio_model(self) -> str:
        return self._data.get("lmstudio_model", "")

    @lmstudio_model.setter
    def lmstudio_model(self, value: str):
        if self._data.get("lmstudio_model") != value:
            self._data["lmstudio_model"] = value
            self._save_backend()
            # Comme `ollama_model` : sans ce signal, la barre d'etat gardait
            # l'ancien modele (releve par l'auteur le 2026-11-06).
            self.changed.emit(self._data["ai_backend"])

    @property
    def chatgpt_model(self) -> str:
        return self._data.get("chatgpt_model", "")

    @chatgpt_model.setter
    def chatgpt_model(self, value: str):
        if self._data.get("chatgpt_model") != value:
            self._data["chatgpt_model"] = value
            self._save_backend()
            self.changed.emit(self._data["ai_backend"])   # idem : barre d'etat

    @property
    def chatgpt_welcome_shown(self) -> bool:
        return bool(self._data.get("chatgpt_welcome_shown", False))

    @chatgpt_welcome_shown.setter
    def chatgpt_welcome_shown(self, value: bool):
        if self.chatgpt_welcome_shown != bool(value):
            self._data["chatgpt_welcome_shown"] = bool(value)
            self._save_backend()

    @property
    def ollama_model(self) -> str:
        return self._data.get("ollama_model", "gemma4:e2b")

    @ollama_model.setter
    def ollama_model(self, value: str):
        if self._data.get("ollama_model") != value:
            self._data["ollama_model"] = value
            self._save_backend()
            # Notifies the views (status bar, etc.) that the label of the active
            # backend may have changed — re-emits the current backend_id unchanged.
            self.changed.emit(self._data["ai_backend"])

    @property
    def ollama_num_ctx(self) -> int:
        return self._data.get("ollama_num_ctx", _OLLAMA_NUM_CTX_DEFAULT)

    @ollama_num_ctx.setter
    def ollama_num_ctx(self, value: int):
        snapped = _snap_num_ctx(value)
        if self._data.get("ollama_num_ctx") != snapped:
            self._data["ollama_num_ctx"] = snapped
            self._save_backend()
            self.changed.emit(self._data["ai_backend"])

    @property
    def lmstudio_num_ctx(self) -> int:
        return self._data.get("lmstudio_num_ctx", _CTX_DEFAULT)

    @lmstudio_num_ctx.setter
    def lmstudio_num_ctx(self, value: int):
        snapped = _snap_num_ctx(value)
        if self._data.get("lmstudio_num_ctx") != snapped:
            self._data["lmstudio_num_ctx"] = snapped
            self._save_backend()
            self.changed.emit(self._data["ai_backend"])

    # ── Reflexion (TODO #123) ────────────────────────────────
    def _regler(self, cle: str, valeur):
        if self._data.get(cle) != valeur:
            self._data[cle] = valeur
            self._save_backend()
            self.changed.emit(self._data["ai_backend"])

    @property
    def ollama_think(self) -> bool:
        return bool(self._data.get("ollama_think", False))

    @ollama_think.setter
    def ollama_think(self, value: bool):
        self._regler("ollama_think", bool(value))

    @property
    def ollama_think_level(self) -> str:
        """Niveau NOMME choisi pour un modele Ollama qui en a (« low »...),
        "" sinon : le modele prend son niveau par defaut (2026-11-07)."""
        v = self._data.get("ollama_think_level", "")
        return v if isinstance(v, str) else ""

    @ollama_think_level.setter
    def ollama_think_level(self, value: str):
        self._regler("ollama_think_level", str(value or ""))

    @property
    def lmstudio_think_level(self) -> str:
        """Niveau choisi pour un modele LM Studio qui en a (gpt-oss), ""
        sinon (TODO #125, 2026-11-07)."""
        v = self._data.get("lmstudio_think_level", "")
        return v if isinstance(v, str) else ""

    @lmstudio_think_level.setter
    def lmstudio_think_level(self, value: str):
        self._regler("lmstudio_think_level", str(value or ""))

    @property
    def lmstudio_think(self) -> bool:
        return bool(self._data.get("lmstudio_think", False))

    @lmstudio_think.setter
    def lmstudio_think(self, value: bool):
        self._regler("lmstudio_think", bool(value))

    @property
    def chatgpt_reasoning(self) -> str:
        return niveau_chatgpt(self._data.get("chatgpt_reasoning"))

    @chatgpt_reasoning.setter
    def chatgpt_reasoning(self, value: str):
        self._regler("chatgpt_reasoning", niveau_chatgpt(value))

    @property
    def keyring_available(self) -> bool:
        return _KEYRING_OK

    def display_name(self) -> str:
        """Short name of the active backend for the status bar."""
        bid = self._data["ai_backend"]
        from .ai_backends.factory import extra_backend
        extra = extra_backend(bid)
        if extra is not None:
            return extra.status_name
        if bid == "ollama":
            return f"Ollama ({self._data.get('ollama_model', 'gemma4:e2b')})"
        # Releve par l'auteur le 2026-11-06 : sans cette ligne, LM Studio
        # retombait sur son identifiant (« Modele : lmstudio »).
        if bid == "lmstudio":
            return f"LM Studio ({self._data.get('lmstudio_model') or '?'})"
        if bid == "chatgpt":
            return f"ChatGPT ({self._data.get('chatgpt_model') or '?'})"
        if bid == "custom":
            return f"Custom ({self._data.get('custom_model') or '?'})"
        from .ai_backends.providers import get_provider
        preset = get_provider(bid)
        return preset.label if preset else bid


# Global instance — imported by all modules
ai_config = AIConfig()

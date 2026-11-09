"""Backend factory: instantiates the active backend from ai_config + registry."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .base import AIBackend
from .ollama_backend import OllamaBackend
from .openai_compat import OpenAICompatBackend
from .providers import PROVIDERS, get_provider


@dataclass(frozen=True)
class ExtraBackend:
    """A backend supplied by the OPTIONAL package `ui.ai_backends.dev`.

    The application knows nothing about what such a backend is: only this
    shape, which is all the view and the configuration need to list it,
    label it, probe it and build it.
    """
    backend_id: str
    label: str
    subtitle: str
    available_text: str
    unavailable_text: str
    status_name: str
    create: Callable[[], AIBackend]


def _extras() -> dict[str, ExtraBackend]:
    """The optional backends, keyed by id -- EMPTY when the package is absent.

    ⚠️ Absence is the NORMAL state of an installation, not a failure: the
    package is never part of the published tree, so an unguarded import here
    would stop the application from starting. Evaluated on every call, never
    memorised -- the package decides what it offers.
    """
    try:
        from .dev import extra_backends
    except ImportError:
        return {}
    return {e.backend_id: e for e in extra_backends()}


def extra_backend(backend_id: str) -> "ExtraBackend | None":
    return _extras().get(backend_id)


# Les moteurs LOCAUX que l'ecran regroupe sous UN radio « Local », choisis
# dans une liste deroulante.
#
# ⛔ CE N'EST PAS `special_backends()`, et la distinction est le coeur de la
# decision du 2026-11-04 : `special_backends()` dit « qui a son propre radio »
# et inclut les backends FACULTATIFS du paquet `dev`. L'utilisateur a tranche
# qu'ils gardent leur radio -- mon argument (« un radio isole a cote d'un radio
# Local serait incoherent ») ne valait rien, puisque cet ecran n'existe que sur
# une machine de developpement : le paquet n'est pas publie.
LOCAL_BACKENDS: tuple[str, ...] = ("ollama", "lmstudio")


def special_backends() -> list[str]:
    """Backends qui ont leur PROPRE radio dans l'ecran, dans l'ordre d'affichage.

    ⚠️ `lmstudio` n'y est volontairement PAS : il vit dans la liste deroulante
    « Local » (cf. `LOCAL_BACKENDS`). L'ajouter ici lui donnerait un radio de
    plus, ce que la spec refuse.
    """
    return [*_extras(), "ollama"]


def known_backend_ids() -> set[str]:
    """Every backend id this build can actually run."""
    # ⛔ « chatgpt » DOIT y etre : sinon la migration generique du #118 le
    # prendrait pour un moteur retire et ramenerait l'utilisateur sur Ollama
    # a chaque demarrage (TODO #122).
    return {*_extras(), "ollama", "lmstudio", "custom", "chatgpt",
            *(p.id for p in PROVIDERS)}


def backend_requires_key(backend_id: str) -> bool:
    """« Ce backend a-t-il besoin d'une cle d'API pour fonctionner ? »

    ⛔ UNE seule reponse, parce que DEUX ecrans la posaient et se
    contredisaient : `OpenAICompatBackend.is_available()` exigeait une cle de
    tout le monde, pendant que la pastille (`ia_view._publier_etat`)
    considerait « custom » configure sans cle. Resultat mesure : la pastille
    n'etait pas rouge et les fonctions gardees par `is_available()` --
    generation comprise -- etaient mortes sans un mot.

    Derivee, jamais enumeree : les presets portent deja le champ
    `ProviderPreset.requires_key`, qui n'etait lu par personne.
    """
    if backend_id in _extras() or backend_id in ("ollama", "lmstudio",
                                                 "custom"):
        # Backends LOCAUX : le serveur tourne sur la machine, il n'y a aucun
        # compte a authentifier. « custom » en fait partie de fait -- c'est
        # par lui qu'on branche un serveur local compatible OpenAI.
        return False
    if backend_id == "chatgpt":
        # Pas de cle : l'authentification passe par le COMPTE (TODO #122).
        return False
    preset = get_provider(backend_id)
    # Un id inconnu rend True : le defaut prudent est d'exiger la cle plutot
    # que de declarer disponible un backend qu'on ne sait pas construire.
    return preset.requires_key if preset is not None else True


def get_backend_instance(backend_id: str):
    """Build the backend for `backend_id`, reading keys/models from ai_config.

    Returns None for an unknown id.
    """
    from ..ai_config import ai_config   # local import: avoid import cycle

    extra = extra_backend(backend_id)
    if extra is not None:
        return extra.create()
    if backend_id == "ollama":
        return OllamaBackend(ai_config.ollama_model)
    if backend_id == "chatgpt":
        from .chatgpt_plan import ChatGPTPlanBackend, EN_DIRECT
        return ChatGPTPlanBackend(ai_config.chatgpt_model,
                                  effort=EN_DIRECT)
    if backend_id == "lmstudio":
        # Serveur LOCAL compatible OpenAI, sans cle ni plafond de reponse ;
        # la sous-classe n'ajoute que la reflexion (TODO #123).
        # `list_models_detailed()` marche tel quel sur `GET /models`.
        from .lmstudio_backend import LMStudioBackend
        return LMStudioBackend(
            base_url=ai_config.lmstudio_base_url,
            model=ai_config.lmstudio_model,
            reflexion=None,          # relu en direct (pastille)
            # Le contexte auquel l'app charge le modele (2026-11-06). Avant,
            # 8 192 fixes : la garde « prompt trop long » et le budget du
            # chat ignoraient ce qui etait reellement charge. La page signale
            # quand le modele est charge a une autre taille.
            context_window_hint=ai_config.lmstudio_num_ctx,
        )
    if backend_id == "custom":
        return OpenAICompatBackend(
            base_url=ai_config.custom_base_url,
            api_key=ai_config.api_key("custom"),
            model=ai_config.custom_model,
            backend_id="custom", label="Custom",
            requires_key=backend_requires_key("custom"),
            # « custom » est la porte d'un serveur LOCAL compatible OpenAI
            # (cf. `backend_requires_key`) : pas de plafond non plus. Le champ
            # `max_tokens` est facultatif dans ce protocole.
            max_output_tokens=None,
        )
    preset = get_provider(backend_id)
    if preset is None:
        return None
    return OpenAICompatBackend(
        base_url=preset.base_url,
        api_key=ai_config.api_key(backend_id),
        model=ai_config.model_for(backend_id),
        backend_id=preset.id, label=preset.label,
        context_window_hint=preset.context_window_hint,
        requires_key=preset.requires_key,
        extra_headers=preset.extra_headers,
        max_tokens_field=preset.max_tokens_field,
    )

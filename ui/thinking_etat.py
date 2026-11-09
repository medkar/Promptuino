"""L'etat du « thinking » du moteur ACTIF, partage par le chat, la zone de
generation et l'onglet Modele IA (decisions de l'auteur, 2026-11-07).

Un seul reglage par moteur (`ai_config.ollama_think` / `ollama_think_level` /
`lmstudio_think` / `chatgpt_reasoning`) : le chat et la generation restent
COUPLES, quel que soit l'endroit ou l'on bascule. Ce module ajoute ce que le
modele choisi PERMET (lu au serveur dans un fil, garde en memoire par
modele), le geste de la pastille et le signal qui fait suivre les trois
endroits.

Etats publies (`etat()`) :
- "on" / "off"   le modele sait reflechir et on peut le regler ;
- "toujours"     il reflechit toujours (ChatGPT, niveaux nommes d'Ollama) ;
- "absent"       le modele n'a pas de mode thinking ;
- "non_reglable" moteur dont l'app ne regle pas le thinking (cloud par cle,
                 adaptateur personnalise) -- on ne pretend pas qu'il n'en a pas.
Tant que le serveur n'a pas repondu, le reglage enregistre s'affiche
("on"/"off") : ignorer n'est pas savoir que c'est impossible.

Le clic de la pastille (P3) fait DEFILER : desactive -> niveaux croissants ->
desactive, pour un modele qui a des niveaux ; activer/desactiver pour les
autres ; les seuls niveaux, en boucle, pour un modele qui ne se coupe pas
(ChatGPT). Les niveaux se reglent aussi dans l'onglet Modele IA (P4).
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from . import reflexion
from .ai_config import ai_config

_REGLABLES = ("ollama", "lmstudio")


class _ThinkingEtat(QObject):
    change = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._caps: dict = {}          # (moteur, modele) -> Capacite | None
        self._en_lecture: set = set()
        self._branche = False

    # ── Branchement (paresseux : ai_config existe deja a l'import) ──
    def _brancher(self):
        if not self._branche:
            self._branche = True
            ai_config.changed.connect(lambda *_: self._actualiser())

    # ── Lecture ───────────────────────────────────────────────
    @staticmethod
    def _cle() -> "tuple[str, str]":
        b = ai_config.backend_id
        if b == "ollama":
            return b, ai_config.ollama_model
        if b == "lmstudio":
            return b, ai_config.lmstudio_model
        return b, ""

    @staticmethod
    def _voulu(moteur: str) -> bool:
        return bool(ai_config.ollama_think if moteur == "ollama"
                    else ai_config.lmstudio_think)

    def capacite(self):
        """Ce que le modele actif permet, ou None si on ne le sait pas
        (encore). Lance la lecture au serveur si elle manque."""
        self._brancher()
        moteur, modele = self._cle()
        if moteur not in _REGLABLES:
            return None
        cle = (moteur, modele)
        if cle not in self._caps:
            self._lire(cle)
            return None
        return self._caps[cle]

    def niveaux(self) -> tuple:
        """Les niveaux d'effort du modele actif, croissants ; () s'il n'en a
        pas (LM Studio par son API actuelle, la plupart des modeles Ollama)."""
        moteur, _ = self._cle()
        if moteur == "chatgpt":
            return reflexion.NIVEAUX_CHATGPT
        if moteur in _REGLABLES:
            cap = self.capacite()
            return cap.niveaux if cap is not None else ()
        return ()

    def niveau(self) -> str:
        """Le niveau en vigueur, ou "" (pas de niveaux, ou desactive)."""
        niveaux = self.niveaux()
        if not niveaux or self.etat() not in ("on", "toujours"):
            return ""
        moteur, _ = self._cle()
        if moteur == "chatgpt":
            return ai_config.chatgpt_reasoning
        choisi = (ai_config.ollama_think_level if moteur == "ollama"
                  else ai_config.lmstudio_think_level)
        if choisi in niveaux:
            return choisi
        cap = self.capacite()
        defaut = cap.allumer if cap is not None else ""
        return defaut if defaut in niveaux else niveaux[0]

    def etat(self) -> str:
        self._brancher()
        moteur, _modele = self._cle()
        if moteur == "chatgpt":
            return "toujours"
        if moteur not in _REGLABLES:
            return "non_reglable"
        cap = self.capacite()
        if cap is not None and not cap.peut_reflechir:
            return "absent"
        if cap is not None and not cap.peut_couper:
            return "toujours"
        return "on" if self._voulu(moteur) else "off"

    def cliquable(self) -> bool:
        e = self.etat()
        return e in ("on", "off") or (e == "toujours" and len(self.niveaux()) > 1)

    # ── Gestes ────────────────────────────────────────────────
    def basculer(self) -> None:
        """Le clic de la pastille (P3) : etape suivante du cycle."""
        if not self.cliquable():
            return
        moteur, _ = self._cle()
        niveaux = self.niveaux()
        e = self.etat()
        if not niveaux:                                   # oui / non
            self._regler_voulu(moteur, e != "on")
        elif e == "toujours":                             # niveaux en boucle
            i = niveaux.index(self.niveau()) if self.niveau() in niveaux else -1
            self.choisir_niveau(niveaux[(i + 1) % len(niveaux)])
        elif e == "off":                                  # off -> 1er niveau
            self._regler_voulu(moteur, True)
            self.choisir_niveau(niveaux[0])
        else:                                             # niveau suivant, puis off
            i = niveaux.index(self.niveau()) if self.niveau() in niveaux else -1
            if i + 1 < len(niveaux):
                self.choisir_niveau(niveaux[i + 1])
            else:
                self._regler_voulu(moteur, False)
        self.change.emit()

    def choisir_niveau(self, niveau: str) -> None:
        """Le niveau d'effort (P3 depuis la pastille, P4 depuis l'onglet)."""
        moteur, _ = self._cle()
        if moteur == "chatgpt":
            ai_config.chatgpt_reasoning = niveau
        elif moteur == "ollama":
            ai_config.ollama_think_level = niveau
        elif moteur == "lmstudio":
            ai_config.lmstudio_think_level = niveau
        self.change.emit()

    def oublier(self) -> None:
        """A relire (modele installe ou change cote serveur)."""
        self._caps.clear()
        self.change.emit()

    # ── Interne ───────────────────────────────────────────────
    @staticmethod
    def _regler_voulu(moteur: str, valeur: bool):
        if moteur == "ollama":
            ai_config.ollama_think = valeur      # emet ai_config.changed
        elif moteur == "lmstudio":
            ai_config.lmstudio_think = valeur

    def _actualiser(self):
        # Un serveur muet a la derniere lecture est relu a chaque changement
        # de reglage (moteur demarre, modele choisi) -- pas a chaque dessin.
        for cle in [k for k, v in self._caps.items() if v is None]:
            del self._caps[cle]
        self.capacite()                          # relance une lecture si besoin
        self.change.emit()

    def _lire(self, cle):
        if cle in self._en_lecture:
            return
        self._en_lecture.add(cle)
        moteur, modele = cle

        def tache():
            if not modele:
                return None
            if moteur == "ollama":
                from . import ollama_models
                return ollama_models.reflexion_modele(modele)
            from . import lmstudio_models
            f = lmstudio_models.fiche(ai_config.lmstudio_base_url, modele)
            return reflexion.depuis_lmstudio(f.get("reflexion")) if f else None

        def fini(paquet):
            _etiquette, cap = paquet
            self._en_lecture.discard(cle)
            # None (serveur muet) est garde aussi, sinon chaque dessin
            # relancerait une lecture ; `_actualiser` le relit plus tard.
            self._caps[cle] = cap if isinstance(cap, reflexion.Capacite) else None
            self.change.emit()

        from .taches_fond import lancer_en_fond
        lancer_en_fond("thinking", tache, fini)


thinking_etat = _ThinkingEtat()

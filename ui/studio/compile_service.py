"""Un SEUL chemin compile/upload (Prompt 2 du plan PATHFINDER-2026-07-05).

CompileService crée et câble le CompileUploadWorker vers une ConsolePanel
cible : étapes au journal (cu_status_label), sortie brute colorée, code
réparé, gestion STANDARD du done (bannières ✓/✗, télémétrie, règles
série : fermer les ports avant, rouvrir sur SUCCÈS seulement), relais des
réparations pédagogiques. Les runs `verify_only` (vérif v2) délèguent leur
`done` au flux appelant (studio, puis generation_flow au Prompt 4).
`arduino_cli` est INCHANGÉ. Remplace les 4 câblages worker recopiés de
studio_view (gen débutant, upload-only, compile avancé, vérif v2) et les
2 paires de handlers status/done jumeaux."""
from .. import arduino_cli
from ..i18n import lang_manager


# Couleurs des phases du journal (aussi utilisées hors service, ex. le
# résumé de réparation dans studio_view).
PHASE_COLORS = {
    "compile": "#3b82f6",   # blue
    "upload":  "#8b5cf6",   # purple
    "fix":     "#f97316",   # orange
    "repair":  "#ef4444",   # red (last chance after 3 failed fixes)
    "libs":    "#14b8a6",   # teal
    "core":    "#0ea5e9",   # cyan (platform install)
    "explain": "#f43f5e",   # pink
}


def upload_error_class(message: str) -> str:
    """Classe d'erreur télémétrie d'un échec upload (port/timeout/
    compile/unknown) — même cascade débutant et int/avancé."""
    m = (message or "").lower()
    return ("port" if any(w in m for w in ("port", "serial", "device"))
            else "timeout" if "timeout" in m
            else "compile" if any(w in m for w in ("compile", "error:", "undefined"))
            else "unknown")


def cu_status_label(step: str, attempt: int, max_attempts: int):
    """(label, couleur) d'une étape de compile/réparation/upload. Partagé
    par le journal compile/upload (débutant + int/avancé) ET la vérif v2."""
    s = lang_manager.current
    if step == "libs":
        label = s.studio_lib_installing
    elif step == "core":
        label = s.studio_core_installing
    elif step == "explain":
        label = s.studio_explaining
    elif step == "upload":
        label = s.studio_uploading
    elif step == "fix":
        label = f"{s.studio_fix_attempt} ({attempt}/{max_attempts})"
    elif step == "repair":
        label = s.studio_repairing
    else:
        label = (s.studio_compiling if attempt == 1
                 else f"{s.studio_compiling} ({attempt}/{max_attempts})")
    return label, PHASE_COLORS.get(step, "#3b82f6")


class CompileService:
    """Crée, câble et lance les CompileUploadWorker. UNE instance par
    StudioView ; `run()` retourne le worker (le studio le garde dans
    _cu_worker/_verify_worker -> les chemins d'annulation existants
    marchent sans changement)."""

    def __init__(self, *, on_code_updated, serials=()):
        # on_code_updated(code) : remplacement du code réparé dans l'éditeur
        # (attribution des lignes comprise) — fourni par StudioView.
        self._on_code_updated = on_code_updated
        # TOUS les moteurs série de la vue (débutant + int/avancé) : le port
        # est exclusif, on ferme tout ce qui est ouvert avant un upload.
        self._serials = list(serials)
        self._repairs_in_run = 0

    def run(self, *, code: str, fqbn: str, port: str = "", backend=None,
            board_name: str = "Arduino", console, verify_only: bool = False,
            clear: bool = False, on_done=None, on_repair_steps=None,
            on_error_notify=None, on_finished=None, repairs_label=None):
        """Lance un run compile(+upload) vers la console `console`.

        - `verify_only=True` : compile + réparation SANS upload ; `done` est
          relayé TEL QUEL à `on_done(ok, errors)` (flux vérif v2) ; aucune
          manipulation série.
        - upload (défaut) : ferme d'abord TOUS les ports série ouverts,
          `clear=True` vide le journal, puis gestion standard du done —
          succès : télémétrie + bannière ✓ + réouverture du série de LA
          console du run ; échec : télémétrie (classe d'erreur) +
          `on_error_notify(message)` éventuel + bannière ✗ + explication +
          bouton d'aide, SANS réouverture série (l'ancien firmware ferait
          croire à un succès).
        - `repairs_label(n)` : libellé du bouton « voir les corrections »
          ré-affirmé au done (None = pas de bouton, cas débutant — décision
          2026-07-05 : réparations silencieuses).
        - `on_finished` : restauration des boutons (QThread.finished).
        """
        log = console.log
        if not verify_only:
            for sm in self._serials:
                if sm.is_open():
                    sm.close_port()
            if clear:
                log.clear()
        self._repairs_in_run = 0

        worker = arduino_cli.CompileUploadWorker(
            code, fqbn, port,
            backend=backend, board_name=board_name, verify_only=verify_only,
        )
        worker.status.connect(
            lambda step, a, m: log.begin_phase(*cu_status_label(step, a, m)))
        worker.output.connect(log.append_raw)
        worker.code_updated.connect(self._on_code_updated)

        def _track_repairs(steps):
            self._repairs_in_run = len(steps or [])
            if on_repair_steps:
                on_repair_steps(steps)
        worker.repair_steps.connect(_track_repairs)

        if verify_only:
            worker.done.connect(on_done)
        else:
            worker.done.connect(
                lambda ok, msg: self._standard_done(
                    ok, msg, console, on_error_notify, repairs_label))
        if on_finished:
            worker.finished.connect(on_finished)
        worker.start()
        return worker

    def _standard_done(self, success: bool, message: str, console,
                       on_error_notify, repairs_label):
        s = lang_manager.current
        log = console.log
        if success:
            log.set_done(True, s.studio_upload_success)
            # Reconnexion du moniteur série UNIQUEMENT sur succès.
            console.reopen_on_success()
        else:
            if on_error_notify:
                on_error_notify(message)
            # Bannière ✗ explicite D'ABORD (échec impossible à confondre).
            log.set_failed(s.studio_upload_failed)
            if message:
                log.append_explanation(message)
            # Le message expose le bouton « Demander de l'aide sur cette
            # erreur » (F2 étape 4).
            log.set_done(False, message)
        # `done` est le DERNIER signal du worker (après `repair_steps`) : on
        # ré-affirme ici le bouton « voir les corrections » pour qu'il reste
        # visible à côté du bouton d'aide, quel que soit l'ordre des signaux.
        if repairs_label and self._repairs_in_run:
            log.show_repairs_action(repairs_label(self._repairs_in_run))

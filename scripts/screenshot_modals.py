"""Génère de VRAIS screenshots de toutes les modales (dark + light) pour revue
de cohérence visuelle.

Pourquoi ce script : un rendu offscreen sans charger les polices embarquées
affiche le texte en ▢▢▢ (tofu). Ici on appelle `setup_fonts(app)` AVANT de
construire quoi que ce soit -> Geist est chargée depuis assets/fonts/ et le
texte s'affiche réellement.

Usage :
    QT_QPA_PLATFORM=offscreen PYTHONUTF8=1 python -u -c \
        "exec(open('scripts/screenshot_modals.py').read())"

Sortie : docs/screenshots/<nom>-<theme>.png
Chaque modale est instanciée avec des données de démonstration (backend factice,
netlist jouet, features jouets). Les dialogs à worker IA reçoivent un backend
factice qui répond instantanément -> on capture l'état « résultat », pas le
spinner.
"""
from __future__ import annotations
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")

import sys
import time
import traceback
from pathlib import Path

try:
    ROOT = Path(__file__).resolve().parents[1]
except NameError:          # lancé via exec(open(...).read())
    ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication([])

# 1) Polices embarquées AVANT toute construction -> texte rendu (pas de tofu).
from ui.fonts import setup_fonts
setup_fonts(_APP)

from ui.theme import theme_manager, build_app_palette

# Stylesheet/tooltip global comme dans main.py (rendu fidèle). Import best-effort.
try:
    import main as _main
    _APP_STYLE = _main._app_style
    _TOOLTIP = _main._apply_tooltip_palette
except Exception:  # pragma: no cover
    _APP_STYLE = None
    _TOOLTIP = None

OUT = ROOT / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

DEMO_CODE = (
    "void setup() {\n"
    "  pinMode(13, OUTPUT);\n"
    "}\n\n"
    "void loop() {\n"
    "  digitalWrite(13, HIGH);\n"
    "  delay(500);\n"
    "  digitalWrite(13, LOW);\n"
    "  delay(500);\n"
    "}\n"
)

# Code AVEC composants externes -> produit un vrai schéma de câblage (le blink
# sur la broche 13 = LED intégrée, ne câble rien). Servo = signature unique
# (pas d'ambiguïté) + LED externe.
WIRING_CODE = (
    "#include <Servo.h>\n"
    "Servo monServo;\n"
    "const int LED = 8;\n\n"
    "void setup() {\n"
    "  pinMode(LED, OUTPUT);\n"
    "  monServo.attach(9);\n"
    "}\n\n"
    "void loop() {\n"
    "  digitalWrite(LED, HIGH);\n"
    "  monServo.write(90);\n"
    "  delay(500);\n"
    "  digitalWrite(LED, LOW);\n"
    "  delay(500);\n"
    "}\n"
)


class DummyBackend:
    """Backend IA factice : réponses instantanées et crédibles pour capturer
    l'état « résultat » des modales d'action sur le code."""
    name = "Démo"
    display_name = "Démo"

    def add_comments(self, *a, **k):
        return (
            "// Fait clignoter la LED intégrée (broche 13)\n"
            "void setup() {\n"
            "  pinMode(13, OUTPUT); // broche LED en sortie\n"
            "}\n\n"
            "void loop() {\n"
            "  digitalWrite(13, HIGH); // allume la LED\n"
            "  delay(500);             // attend 0,5 s\n"
            "  digitalWrite(13, LOW);  // éteint la LED\n"
            "  delay(500);             // attend 0,5 s\n"
            "}\n"
        )

    def explain_code(self, *a, **k):
        return (
            "### Ce que fait ce programme\n\n"
            "Ce croquis fait **clignoter** la LED intégrée de la carte.\n\n"
            "1. `setup()` configure la broche 13 en sortie.\n"
            "2. `loop()` alterne HIGH / LOW avec un délai de 500 ms,\n"
            "   ce qui produit un clignotement à 1 Hz.\n"
        )

    def lint_code(self, *a, **k):
        return (
            "✓ Aucune erreur bloquante détectée.\n\n"
            "• La broche 13 gagnerait à être nommée par une constante.\n"
            "• `delay()` met le programme en pause ; pour faire plusieurs choses\n"
            "  à la fois, préférez la technique `millis()`.\n"
        )

    def repair_code(self, *a, **k):
        return (DEMO_CODE,
                "Ajout du point-virgule manquant ligne 3 et fermeture de "
                "l'accolade de la fonction loop().")


def _pump(ms: int = 200):
    """Pompe la boucle d'événements ~ms millisecondes (laisse finir les workers
    et arriver les signaux cross-thread)."""
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        _APP.processEvents()
        time.sleep(0.01)


def _shot(name: str, dialog, *, theme_tag: str, settle_ms: int = 250,
          resize=None):
    try:
        if resize:
            dialog.resize(*resize)
        dialog.show()
        dialog.raise_()
        _pump(settle_ms)
        path = OUT / f"{name}-{theme_tag}.png"
        ok = dialog.grab().save(str(path))
        print(f"  {'OK ' if ok else 'ERR'} {path.name}  ({dialog.width()}x{dialog.height()})")
    except Exception as e:  # pragma: no cover
        print(f"  FAIL {name}-{theme_tag}: {e}")
        traceback.print_exc()
    finally:
        try:
            dialog.close()
            dialog.deleteLater()
            _pump(60)
        except Exception:
            pass


def _build_all(theme_tag: str):
    """Construit + capture chaque modale pour le thème courant.

    ⚠️ Les imports sont GROUPÉS PAR SECTION, chacun dans son propre `try`, et
    ce n'est pas de la coquetterie. Ce script a été totalement muet du
    2026-07-29 au 2026-08-11 : un unique bloc d'imports en tête de fonction
    référençait `ui.lib_clarification_dialog`, supprimé ce jour-là — un seul
    module disparu et PLUS AUCUNE capture, dans les deux thèmes, sans le
    moindre message. Une deuxième référence avait pourri à l'identique
    (`_PromptPreviewDialog`, déplacé dans ui/studio/generation_flow.py et
    renommé au chantier #42). Découpé ainsi, un symbole disparu ne coûte plus
    que SA section, et il le DIT au lieu de tout emporter en silence.
    """
    backend = DummyBackend()
    board = "Arduino Uno"

    # ── Modales simples ────────────────────────────────────────────────
    try:
        from ui.settings_dialog import SettingsDialog
        from ui.welcome_dialog import WelcomeDialog
        from ui.onnx_setup import OnnxDownloadDialog
        _shot("settings", SettingsDialog(), theme_tag=theme_tag)
        _shot("welcome", WelcomeDialog(), theme_tag=theme_tag)
        _shot("onnx-download", OnnxDownloadDialog(), theme_tag=theme_tag)
    except Exception as e:
        print(f"  SKIP modales-simples-{theme_tag}: {e}")

    # ── Modales d'action sur le code (worker IA factice) ──────────────
    try:
        from ui.add_comments_dialog import AddCommentsDialog
        from ui.explain_code_dialog import ExplainCodeDialog
        from ui.lint_code_dialog import LintCodeDialog
        from ui.repair_code_dialog import RepairCodeDialog
        _shot("add-comments", AddCommentsDialog(backend, DEMO_CODE, board),
              theme_tag=theme_tag, settle_ms=700)
        _shot("explain-code", ExplainCodeDialog(backend, DEMO_CODE, "", board),
              theme_tag=theme_tag, settle_ms=700)
        _shot("lint-code", LintCodeDialog(backend, DEMO_CODE, board),
              theme_tag=theme_tag, settle_ms=700)
        _shot("repair-code", RepairCodeDialog(backend, DEMO_CODE, board),
              theme_tag=theme_tag, settle_ms=700)
    except Exception as e:
        print(f"  SKIP modales-code-{theme_tag}: {e}")

    # ── Modales « composants » (les trois portes du TODO #44) ─────────
    # Absentes jusqu'au 2026-08-11 : elles sont nées APRÈS ce harnais, et ce
    # sont précisément celles dont la forme est en question.
    try:
        from ui.wiring.declare_component_dialog import DeclareComponentDialog
        from ui.lib_choice_dialog import LibChoiceDialog
        _shot("declare-component",
              DeclareComponentDialog(
                  board_nets=["5V", "GND", "D2", "D3", "A0"], lang="fr"),
              theme_tag=theme_tag, resize=(640, 620))
        _shot("lib-choice",
              LibChoiceDialog(token="as7341",
                              current_lib="Adafruit AS7341",
                              alternatives=["Adafruit AS7341",
                                            "DFRobot_AS7341",
                                            "SparkFun AS7341X"]),
              theme_tag=theme_tag, resize=(520, 480))
    except Exception as e:
        print(f"  SKIP modales-composants-{theme_tag}: {e}")

    # ── Modale de génération (Régénérer / Ajouter / Modifier) ─────────
    try:
        from ui.generation.gen_modal import GenerationModal
        from ui.generation.feature_model import Feature
        feats = [
            Feature(id="f1", prompt="LED qui clignote sur D13"),
            Feature(id="f2", prompt="bouton poussoir sur D2"),
        ]
        _shot("generation-modal",
              GenerationModal(feats, "ajoute un buzzer qui bipe sur D8"),
              theme_tag=theme_tag)
    except Exception as e:
        print(f"  SKIP generation-modal-{theme_tag}: {e}")

    # ── Modale d'ambiguïté câblage ─────────────────────────────────────
    # Une seule depuis le 2026-08-13 : la modale visuelle débutant a été
    # supprimée, celle-ci sert les trois modes et montre désormais les cards.
    try:
        from ui.wiring.netlist import Netlist, Component, Pin
        from ui.wiring.ambiguity_dialog import AmbiguityDialog
        led = Component(ref="D1", type="led",
                        pins=[Pin("A", "D5"), Pin("K", "GND")],
                        attributes={"category": "single_output",
                                    "_confidence": "low"})
        nl1 = Netlist(board_id="uno_r3", components=[led])
        _shot("ambiguity", AmbiguityDialog([led], netlist=nl1),
              theme_tag=theme_tag, resize=(600, 560))
    except Exception as e:
        print(f"  SKIP ambiguite-{theme_tag}: {e}")

    # ── Nouveau projet ─────────────────────────────────────────────────
    try:
        from ui.projects_view import _NewProjectDialog
        _shot("new-project", _NewProjectDialog(), theme_tag=theme_tag)
    except Exception as e:
        print(f"  SKIP new-project-{theme_tag}: {e}")

    # ── « Coulisses du prompt » (#42) ──────────────────────────────────
    # Deux volets depuis le 2026-08-10 : système en lecture seule, message
    # utilisateur éditable. La classe a quitté studio_view pour
    # ui/studio/generation_flow.py et perdu son underscore -- l'ancien import
    # traînait ici, mort.
    try:
        from ui.studio.generation_flow import PromptPreviewDialog
        _shot("prompt-preview",
              PromptPreviewDialog(
                  "Aperçu du prompt",
                  "Tu es un assistant qui génère du code Arduino.\n"
                  "Règles matériel : une résistance série sur chaque LED.\n",
                  "Fais clignoter la LED intégrée (broche 13) "
                  "toutes les 500 ms.\n"),
              theme_tag=theme_tag, resize=(820, 640))
    except Exception as e:
        print(f"  SKIP prompt-preview-{theme_tag}: {e}")

    # ── Schéma de câblage (viewer) ─────────────────────────────────────
    # Le dialog ne fait PAS l'analyse : le parent (StudioView) lui passe un
    # netlist déjà analysé. On reproduit cette étape ici.
    try:
        from ui.wiring.layout import pipeline as _wire
        from ui.wiring.wiring_diagram_dialog import WiringDiagramDialog
        nl_wire = _wire.analyze_netlist(WIRING_CODE, "arduino_uno_r3")
        _shot("wiring-diagram",
              WiringDiagramDialog(WIRING_CODE, "arduino_uno_r3",
                                  netlist=nl_wire),
              theme_tag=theme_tag, settle_ms=1200, resize=(960, 660))
    except Exception as e:
        print(f"  SKIP wiring-diagram-{theme_tag}: {e}")


def main():
    for theme_tag, applier in (("dark", theme_manager.apply_dark),
                               ("light", theme_manager.apply_light)):
        applier()
        c = theme_manager.current
        _APP.setPalette(build_app_palette(c))
        if _APP_STYLE:
            _APP.setStyleSheet(_APP_STYLE(c))
        if _TOOLTIP:
            _TOOLTIP(c)
        print(f"\n=== Thème {theme_tag} ===")
        _build_all(theme_tag)
    print(f"\nScreenshots dans {OUT}")


main()

"""Package ui/studio — découpage progressif de studio_view.py (audit
PATHFINDER-2026-07-05). Chaque bloc extrait vit ici ; studio_view.py garde
des imports de compatibilité le temps de la migration."""
from .log_widget import LogWidget, phase_div_html, phase_title_html
from .console_panel import ConsolePanel
from .code_panel import CodePanel
from .generation_flow import (
    GenerateWorker, build_codegen_preview, build_codegen_parts,
    PromptPreviewDialog,
)

__all__ = ["LogWidget", "ConsolePanel", "CodePanel",
           "GenerateWorker", "build_codegen_preview", "build_codegen_parts",
           "PromptPreviewDialog",
           "phase_div_html", "phase_title_html"]

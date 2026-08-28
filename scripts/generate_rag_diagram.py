"""Render a PNG schema of the RAG system using PyQt6 QPainter.

Run from the repo root:
    python scripts/generate_rag_diagram.py
Output: docs/rag_system_diagram.png
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QGuiApplication,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)


# ---------------------------------------------------------------------------
# Theme — aligned with the app's dark scheme
# ---------------------------------------------------------------------------
BG = QColor("#0F1115")
PANEL = QColor("#171A21")
PANEL_BORDER = QColor("#2A2F3A")
TEXT = QColor("#E6E8EE")
MUTED = QColor("#8A93A6")
ACCENT = QColor("#5B9CFF")
ACCENT_BUILD = QColor("#9B6BFF")
ACCENT_RUNTIME = QColor("#3DD9A5")
ACCENT_LLM = QColor("#FFB74D")
ACCENT_DATA = QColor("#FF6B9C")
ARROW = QColor("#6B7280")

W, H = 1700, 1180
MARGIN = 40


def font(size: int, bold: bool = False) -> QFont:
    f = QFont("Segoe UI", size)
    f.setBold(bold)
    return f


def draw_box(
    p: QPainter,
    rect: QRectF,
    title: str,
    subtitle: str = "",
    body: list[str] | None = None,
    accent: QColor = ACCENT,
    title_size: int = 11,
) -> None:
    p.setPen(QPen(PANEL_BORDER, 1.5))
    p.setBrush(QBrush(PANEL))
    p.drawRoundedRect(rect, 10, 10)

    bar = QRectF(rect.x(), rect.y(), 5, rect.height())
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(accent))
    p.drawRoundedRect(bar, 2.5, 2.5)

    p.setPen(QPen(TEXT))
    p.setFont(font(title_size, bold=True))
    title_rect = QRectF(rect.x() + 14, rect.y() + 8, rect.width() - 22, 22)
    p.drawText(title_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), title)

    y = rect.y() + 32
    if subtitle:
        p.setPen(QPen(MUTED))
        p.setFont(font(9))
        sub_rect = QRectF(rect.x() + 14, y, rect.width() - 22, 16)
        p.drawText(sub_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), subtitle)
        y += 18

    if body:
        p.setPen(QPen(TEXT))
        p.setFont(font(9))
        for line in body:
            line_rect = QRectF(rect.x() + 14, y, rect.width() - 22, 14)
            p.drawText(line_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), line)
            y += 15


def draw_arrow(
    p: QPainter,
    start: QPointF,
    end: QPointF,
    label: str = "",
    color: QColor = ARROW,
    dashed: bool = False,
) -> None:
    pen = QPen(color, 2)
    if dashed:
        pen.setStyle(Qt.PenStyle.DashLine)
    p.setPen(pen)
    p.drawLine(start, end)

    import math
    angle = math.atan2(end.y() - start.y(), end.x() - start.x())
    arrow_len = 11
    arrow_w = 6
    p1 = QPointF(
        end.x() - arrow_len * math.cos(angle) + arrow_w * math.sin(angle),
        end.y() - arrow_len * math.sin(angle) - arrow_w * math.cos(angle),
    )
    p2 = QPointF(
        end.x() - arrow_len * math.cos(angle) - arrow_w * math.sin(angle),
        end.y() - arrow_len * math.sin(angle) + arrow_w * math.cos(angle),
    )
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    p.drawPolygon(QPolygonF([end, p1, p2]))

    if label:
        p.setPen(QPen(MUTED))
        p.setFont(font(8))
        mid = QPointF((start.x() + end.x()) / 2, (start.y() + end.y()) / 2 - 6)
        p.drawText(QRectF(mid.x() - 90, mid.y() - 8, 180, 16),
                   int(Qt.AlignmentFlag.AlignCenter), label)


def draw_section_header(
    p: QPainter,
    x: float,
    y: float,
    w: float,
    title: str,
    subtitle: str,
    color: QColor,
) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    p.drawRoundedRect(QRectF(x, y, 8, 28), 4, 4)
    p.setPen(QPen(TEXT))
    p.setFont(font(15, bold=True))
    p.drawText(QRectF(x + 16, y, w, 18),
               int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
               title)
    p.setPen(QPen(MUTED))
    p.setFont(font(10))
    p.drawText(QRectF(x + 16, y + 16, w, 16),
               int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
               subtitle)


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)

    pm = QPixmap(W, H)
    pm.fill(BG)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Title
    p.setPen(QPen(TEXT))
    p.setFont(font(20, bold=True))
    p.drawText(QRectF(MARGIN, 24, W - 2 * MARGIN, 30),
               int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
               "PromptuinoUI — Système RAG (Retrieval-Augmented Generation)")
    p.setPen(QPen(MUTED))
    p.setFont(font(11))
    p.drawText(QRectF(MARGIN, 54, W - 2 * MARGIN, 18),
               int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
               "Pipeline d'augmentation des prompts avec exemples de libs Arduino — modèle multilingue FR/EN/ES/IT")

    # ============================================================
    # BUILD PHASE (offline, dev-only)
    # ============================================================
    draw_section_header(p, MARGIN, 95, 800,
                        "1. Phase BUILD (offline, dev-only)",
                        "Génération du corpus et des embeddings — non livrée à l'utilisateur final",
                        ACCENT_BUILD)

    cache = QRectF(MARGIN, 145, 320, 110)
    draw_box(p, cache, "Cache local (dev)",
             "~/.cache/promptuino_rag_build/",
             ["• 25 libs Arduino clonées (git)",
              "• Lecture des examples/*.ino",
              "• Extraction métadonnées",
              "• ⚠ Non distribué dans le build final"],
             accent=ACCENT_BUILD)

    builder = QRectF(MARGIN + 360, 145, 320, 110)
    draw_box(p, builder, "build_rag_embeddings.py",
             "Script offline (scripts/)",
             ["• Lit corpus.json",
              "• Encode description + keywords",
              "• Sauve embeddings.npy",
              "• Modèle: MiniLM-L12-v2 multi (~470 MB)"],
             accent=ACCENT_BUILD)

    corpus_box = QRectF(MARGIN + 720, 130, 280, 65)
    draw_box(p, corpus_box, "corpus.json",
             "assets/rag/ — 25 entrées",
             ["id, name, headers, example_code, …"],
             accent=ACCENT_DATA)

    emb_box = QRectF(MARGIN + 720, 205, 280, 65)
    draw_box(p, emb_box, "embeddings.npy",
             "assets/rag/ — float32 L2-norm",
             ["shape (25, 384)  ·  ~38 KB"],
             accent=ACCENT_DATA)

    draw_arrow(p, QPointF(cache.right(), cache.center().y()),
               QPointF(builder.left(), builder.center().y()),
               "métadonnées + code", ARROW)
    draw_arrow(p, QPointF(builder.right(), builder.center().y() - 18),
               QPointF(corpus_box.left(), corpus_box.center().y()),
               "écrit", ARROW)
    draw_arrow(p, QPointF(builder.right(), builder.center().y() + 18),
               QPointF(emb_box.left(), emb_box.center().y()),
               "écrit", ARROW)

    # Smoke test box
    smoke = QRectF(MARGIN + 1040, 145, 280, 110)
    draw_box(p, smoke, "smoke_test_rag_multilingual.py",
             "Validation 100 prompts · 4 langues",
             ["• 25 prompts × FR/EN/ES/IT",
              "• Vérifie top-1 retrieval",
              "• Score actuel : 100/100 ✓",
              "• Lancé après chaque build"],
             accent=ACCENT_BUILD)
    draw_arrow(p, QPointF(emb_box.right(), emb_box.center().y() - 18),
               QPointF(smoke.left(), smoke.center().y()),
               "lit", ARROW, dashed=True)

    # Separator
    p.setPen(QPen(PANEL_BORDER, 1, Qt.PenStyle.DashLine))
    p.drawLine(MARGIN, 305, W - MARGIN, 305)

    # ============================================================
    # RUNTIME PHASE (in-app)
    # ============================================================
    draw_section_header(p, MARGIN, 325, 800,
                        "2. Phase RUNTIME (in-app, à chaque génération)",
                        "Augmentation du prompt utilisateur avec contexte de libs pertinentes",
                        ACCENT_RUNTIME)

    # User prompt
    user = QRectF(MARGIN, 380, 260, 90)
    draw_box(p, user, "Prompt utilisateur",
             "FR / EN / ES / IT",
             ["« lire un capteur DHT22 »",
              "« control a stepper motor »",
              "« leer temperatura DS18B20 »",
              "« display testo su OLED »"],
             accent=ACCENT_RUNTIME)

    # StudioView
    studio = QRectF(MARGIN + 300, 380, 260, 90)
    draw_box(p, studio, "ui/studio_view.py",
             "4 points d'intégration",
             ["• ligne ~2341 (Anthropic)",
              "• ligne ~2458 (Gemini)",
              "• ligne ~3230 (Claude Code CLI)",
              "• ligne ~3423 (Ollama)"],
             accent=ACCENT_RUNTIME)

    # augment_user_prompt
    augment = QRectF(MARGIN + 600, 380, 260, 90)
    draw_box(p, augment, "augment_user_prompt()",
             "ui/rag.py — entrée publique",
             ["1. build_lib_context(prompt)",
              "2. concat ctx + '---' + prompt",
              "3. retourne prompt augmenté",
              "(prompt inchangé si vide)"],
             accent=ACCENT_RUNTIME)

    # retrieve_libs
    retrieve = QRectF(MARGIN + 900, 380, 320, 200)
    draw_box(p, retrieve, "retrieve_libs(prompt, k=3, threshold=0.25)",
             "ui/rag.py — cœur du RAG",
             ["1. _load() lazy + threading.Lock",
              "   ├─ corpus = json.load(corpus.json)",
              "   ├─ embeddings = np.load(.npy)",
              "   └─ model = SentenceTransformer(...)",
              "",
              "2. q = model.encode([prompt], norm=True)",
              "3. sims = embeddings @ q[0]   (cosine)",
              "4. top-K trié desc, filtré ≥ 0.25",
              "5. retourne [{**entry, _score}, …]",
              "",
              "⚠ Toute exception → [] (graceful)"],
             accent=ACCENT,
             title_size=10)

    # build_lib_context
    ctx_box = QRectF(MARGIN + 1260, 380, 280, 200)
    draw_box(p, ctx_box, "build_lib_context()",
             "Format Markdown du contexte",
             ["Pour chaque lib retenue :",
              "  ### Nom de la lib",
              "  Headers: `Lib.h`, `Sub.h`",
              "  Example:",
              "  ```cpp",
              "  /* example_code 30-60 lignes */",
              "  ```",
              "",
              "Préfixe d'instruction :",
              "« Reference these exact APIs… »",
              "",
              "Logs stdout pour traçage [RAG]"],
             accent=ACCENT,
             title_size=10)

    draw_arrow(p, QPointF(user.right(), user.center().y()),
               QPointF(studio.left(), studio.center().y()), "")
    draw_arrow(p, QPointF(studio.right(), studio.center().y()),
               QPointF(augment.left(), augment.center().y()), "")
    draw_arrow(p, QPointF(augment.right(), augment.center().y()),
               QPointF(retrieve.left(), retrieve.center().y()), "")
    draw_arrow(p, QPointF(retrieve.right(), retrieve.center().y()),
               QPointF(ctx_box.left(), ctx_box.center().y()),
               "top-K libs", ARROW)

    # Singletons (lazy)
    sing = QRectF(MARGIN, 500, 540, 90)
    draw_box(p, sing, "Singletons module-level (lazy, thread-safe)",
             "ui/rag.py — chargés une seule fois",
             ["_corpus      : list[dict]      (25 entrées)",
              "_embeddings  : np.ndarray      (25, 384) float32",
              "_model       : SentenceTransformer",
              "_load_failed : bool            (sticky, pas de retry inutile)"],
             accent=ACCENT)

    # Arrow from singletons up to retrieve
    p.setPen(QPen(ARROW, 2, Qt.PenStyle.DashLine))
    p.drawLine(QPointF(sing.right(), sing.center().y() - 20),
               QPointF(retrieve.left(), retrieve.center().y() + 30))
    p.setPen(QPen(MUTED))
    p.setFont(font(8))
    p.drawText(QRectF(sing.right() + 10, sing.center().y() - 40, 200, 16),
               int(Qt.AlignmentFlag.AlignLeft), "lus en mémoire")

    # Data sources arrows (from build phase)
    p.setPen(QPen(ACCENT_DATA, 1.5, Qt.PenStyle.DashLine))
    p.drawLine(QPointF(corpus_box.center().x(), corpus_box.bottom()),
               QPointF(corpus_box.center().x(), 500))
    p.drawLine(QPointF(corpus_box.center().x(), 500),
               QPointF(sing.right() - 100, 500))
    p.drawLine(QPointF(sing.right() - 100, 500),
               QPointF(sing.right() - 100, sing.top()))
    p.drawLine(QPointF(emb_box.center().x() + 30, emb_box.bottom()),
               QPointF(emb_box.center().x() + 30, 490))
    p.drawLine(QPointF(emb_box.center().x() + 30, 490),
               QPointF(sing.right() - 50, 490))
    p.drawLine(QPointF(sing.right() - 50, 490),
               QPointF(sing.right() - 50, sing.top()))
    p.setPen(QPen(MUTED))
    p.setFont(font(8))
    p.drawText(QRectF(sing.right() - 180, 470, 200, 14),
               int(Qt.AlignmentFlag.AlignCenter),
               "livrés dans assets/rag/")

    # ============================================================
    # OUTPUT FLOW (LLM + arduino-cli)
    # ============================================================
    draw_section_header(p, MARGIN, 620, 800,
                        "3. Génération et compilation",
                        "Le prompt augmenté part vers le backend LLM puis arduino-cli",
                        ACCENT_LLM)

    final_prompt = QRectF(MARGIN, 675, 320, 110)
    draw_box(p, final_prompt, "Prompt augmenté final",
             "context Markdown + ---- + tâche",
             ["### LibA  Headers: …  Example: …",
              "### LibB  Headers: …  Example: …",
              "---",
              "Task: <prompt utilisateur original>"],
             accent=ACCENT_LLM)

    llm = QRectF(MARGIN + 360, 675, 320, 110)
    draw_box(p, llm, "Backend LLM (sélectionné dans l'UI)",
             "Génère le code Arduino",
             ["• Anthropic API (claude-*)",
              "• Google Gemini API",
              "• Claude Code CLI (local)",
              "• Ollama (modèles locaux)"],
             accent=ACCENT_LLM)

    code = QRectF(MARGIN + 720, 675, 280, 110)
    draw_box(p, code, "Code Arduino généré",
             ".ino + #include déduits du contexte",
             ["#include <DallasTemperature.h>",
              "#include <OneWire.h>",
              "void setup() { … }",
              "void loop() { … }"],
             accent=ACCENT_LLM)

    cli = QRectF(MARGIN + 1040, 675, 320, 110)
    draw_box(p, cli, "arduino-cli",
             "Compile + upload vers la carte",
             ["• lib_deps résolus via library.properties",
              "  (ex: SSD1306 → tire GFX automatiquement)",
              "• flash sur Arduino UNO/Mega/Nano",
              "• retours stdout/stderr → UI"],
             accent=ACCENT_LLM)

    draw_arrow(p, QPointF(ctx_box.center().x(), ctx_box.bottom()),
               QPointF(final_prompt.center().x() + 60, final_prompt.top()),
               "", ARROW)
    draw_arrow(p, QPointF(final_prompt.right(), final_prompt.center().y()),
               QPointF(llm.left(), llm.center().y()), "")
    draw_arrow(p, QPointF(llm.right(), llm.center().y()),
               QPointF(code.left(), code.center().y()), "")
    draw_arrow(p, QPointF(code.right(), code.center().y()),
               QPointF(cli.left(), cli.center().y()), "")

    # ============================================================
    # FOOTNOTES
    # ============================================================
    draw_section_header(p, MARGIN, 820, 800,
                        "Notes techniques",
                        "Choix d'implémentation et points d'attention",
                        ACCENT)

    note1 = QRectF(MARGIN, 870, 400, 180)
    draw_box(p, note1, "Modèle d'embedding",
             "paraphrase-multilingual-MiniLM-L12-v2",
             ["• 12 layers · 384 dim · 50+ langues",
              "• Couvre FR / EN / ES / IT (UI Promptuino)",
              "• Pilote : sentence-transformers (PyTorch ~470 MB)",
              "• Distribution : ONNX (~120 MB) — TODO",
              "• Texte encodé : description + keywords",
              "• Embeddings L2-normalisés → cosine = dot",
              "",
              "⚠ Les embeddings dépendent du modèle :",
              "tout swap nécessite régénération de .npy"],
             accent=ACCENT)

    note2 = QRectF(MARGIN + 440, 870, 400, 180)
    draw_box(p, note2, "Comportement & dégradation",
             "Sécurité face aux pannes",
             ["• Lazy load au 1er appel (pas au démarrage UI)",
              "• threading.Lock → pas de double init",
              "• _load_failed sticky → pas de retry coûteux",
              "• Toute exception capturée → renvoie []",
              "• Si retrieve_libs() == [] → prompt non modifié",
              "  → le LLM génère sur ses connaissances seules",
              "• Threshold 0.25 : sous ce seuil, lib ignorée",
              "• Logs [RAG] sur stdout pour debug",
              "",
              "✓ Aucun crash si assets/rag/ absent ou corrompu"],
             accent=ACCENT_RUNTIME)

    note3 = QRectF(MARGIN + 880, 870, 400, 180)
    draw_box(p, note3, "Couverture corpus",
             "Tier 1 (actuel) → Tier 2 → Tier 3",
             ["• Tier 1 : 25 libs (actuel)         ~70-75% cas",
              "• + Tier 2 : 7 libs (priorité)       ~88-92%",
              "    PIR, MFRC522, GPS, ILI9341,",
              "    Keypad, L298N, TB6612FNG",
              "• + Tier 3 : 6 libs (ferme)          ~93-95%",
              "    MQ-135, CCS811, MH-Z19,",
              "    LoRa, DRV8833, L293D",
              "",
              "Cible : 38 entrées · 100/100 multilingue",
              "Voir docs/RAG_LIBRARIES_PLAN.md"],
             accent=ACCENT_BUILD)

    note4 = QRectF(MARGIN + 1320, 870, 290, 180)
    draw_box(p, note4, "Évolutions futures",
             "Roadmap RAG",
             ["• Fallback rang 2/3 si",
              "  compile échoue ou rejet UI",
              "  (exclude_ids dans retrieve_libs)",
              "",
              "• Question de clarification",
              "  si catégories mixtes proches",
              "",
              "• Swap ONNX avant distribution",
              "  (700 MB → 120 MB)",
              "",
              "Voir mémoires projet"],
             accent=ACCENT_LLM)

    # Footer
    p.setPen(QPen(MUTED))
    p.setFont(font(9))
    p.drawText(QRectF(MARGIN, H - 30, W - 2 * MARGIN, 16),
               int(Qt.AlignmentFlag.AlignCenter),
               "PromptuinoUI · ui/rag.py · scripts/build_rag_embeddings.py · scripts/smoke_test_rag_multilingual.py · "
               "assets/rag/{corpus.json, embeddings.npy}")

    p.end()

    out = Path(__file__).resolve().parent.parent / "docs" / "rag_system_diagram.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    pm.save(str(out), "PNG")
    print(f"Saved: {out}  ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()

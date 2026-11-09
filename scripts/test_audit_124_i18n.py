"""Audit de gravite basse (TODO #124, 2026-11-07) : textes qui restaient en
francais quelle que soit la langue choisie.

Chaque test bascule la langue en memoire (`lang_manager.set_language`, rien
n'est ecrit sur disque) et la remet en francais a la fin.

Run : python scripts/test_audit_124_i18n.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.i18n import TRANSLATIONS, lang_manager

KEYS = (
    "studio_pins_reassigned_title", "update_dev_build",
    "ia_err_ollama_not_running", "ia_err_ollama_generic",
    "chat_empty_reply", "chat_err_model_invalid", "chat_err_backend_missing",
    "chat_err_api_key", "chat_err_quota", "chat_err_ollama_down",
    "chat_err_anthropic_down", "chat_err_server_down", "chat_err_network",
    "chat_err_generic", "chat_generation_redirect", "chat_offscope_refusal",
    "chat_no_backend_bubble", "chat_empty_message", "gen_pin_moved_notice",
    "gen_pin_shared_bus", "gen_pin_literal_conflict", "gen_pin_no_free",
    "gen_pin_moved_comment", "declared_save_failed", "onnx_err_checksum",
    "onnx_err_http", "onnx_err_network", "onnx_err_unexpected",
    "onnx_url_missing_title", "onnx_url_missing_text",
    "gen_pin_kind_pwm", "gen_pin_kind_analog", "gen_pin_kind_digital",
)


class _En:
    def __enter__(self):
        lang_manager.set_language("en")

    def __exit__(self, *exc):
        lang_manager.set_language("fr")


def test_every_key_exists_in_four_languages_with_the_same_placeholders():
    for key in KEYS:
        ref = None
        for code in ("fr", "en", "es", "it"):
            val = getattr(TRANSLATIONS[code], key, "")
            assert val, f"{key} vide ou absent en {code}"
            ph = sorted(set(re.findall(r"\{(\w+)\}", val)))
            if ref is None:
                ref = ph
            assert ph == ref, f"{key} : marqueurs {ph} en {code}, {ref} en fr"


def test_pin_reassign_speaks_the_chosen_language():
    from ui.generation.pin_reassign import PinMove, format_reassign_notice
    with _En():
        txt = format_reassign_notice(
            [PinMove(const_name="PIN_BTN", kind="digital",
                     old_pin="D9", new_pin="D2")], [])
    assert "moved from D9 to D2" in txt, txt
    assert "déplacé" not in txt


def test_chat_canned_replies_follow_the_language():
    from ui.chat.chat_controller import ChatController, ChatTurnKind
    ctrl = ChatController.__new__(ChatController)
    ctrl.backend = None
    with _En():
        r = ctrl.evaluate_turn("   ")
        assert r.kind == ChatTurnKind.ERROR and r.text == "Empty message."


def test_generation_redirect_names_the_field_as_displayed():
    s = TRANSLATIONS["en"]
    txt = s.chat_generation_redirect.replace("{field}", s.studio_prompt_label)
    assert "**Generate a feature**" in txt


def test_ollama_not_running_is_recognised_in_another_language():
    """Le moteur traduit son message : la detection du chat ne doit pas
    dependre du francais."""
    from ui.chat.chat_view import ChatView
    with _En():
        out = ChatView._friendly_backend_error(
            None, TRANSLATIONS["it"].ia_err_ollama_not_running)
        assert out == TRANSLATIONS["en"].chat_err_ollama_down, out


def test_ollama_backend_messages_are_translated():
    from ui.ai_backends import ollama_backend as ob
    with _En():
        assert ob._msg_not_running() == TRANSLATIONS["en"].ia_err_ollama_not_running
        assert ob._msg_generic(ValueError("x {y}")) == "Ollama error: x {y}"


def test_generic_chat_error_keeps_braces_of_the_detail():
    from ui.chat.chat_view import ChatView
    with _En():
        out = ChatView._friendly_backend_error(None, "weird {thing} happened")
    assert out == "AI engine error: weird {thing} happened", out


TESTS = [
    test_every_key_exists_in_four_languages_with_the_same_placeholders,
    test_pin_reassign_speaks_the_chosen_language,
    test_chat_canned_replies_follow_the_language,
    test_generation_redirect_names_the_field_as_displayed,
    test_ollama_not_running_is_recognised_in_another_language,
    test_ollama_backend_messages_are_translated,
    test_generic_chat_error_keeps_braces_of_the_detail,
]


def main() -> int:
    print("[test_audit_124_i18n]\n")
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  [OK] {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  [FAIL] {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

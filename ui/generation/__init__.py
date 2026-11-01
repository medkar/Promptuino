"""Moteur de génération feature->code du Studio (pur Python, testable hors Qt).

Sauf `gen_modal.GenerationModal` (QDialog), aucun module n'importe Qt.
"""
from .feature_model import (
    Feature, FeatureFunction, next_feature_id, used_pins, used_names,
    used_global_names, declared_name, feature_mentions_pin, serialize_features,
    deserialize_features, resolve_feature_pins, guess_correction_target,
)
from .sketch_parser import parse_sketch, ParsedContributions, SketchParseError
from .assembler import assemble, assemble_with_map, clean_feature_contributions
from .splicer import splice_add, splice_replace, SpliceError
from .edit_classify import normalize_code, is_dirty, classify_edit
from .gen_prompts import (
    build_context_summary, build_feature_instruction, build_modify_instruction,
    build_regen_instruction,
    extract_feature_summary, feature_label, FEATURE_SUMMARY_DIRECTIVE,
    compact_pin_label, feature_combo_label, feature_combo_tooltip,
)
from .gen_modal import default_action, REGENERATE, ADD, CORRECT
from .pin_reassign import (
    reassign_conflicting_pins, ReassignResult, PinMove, format_reassign_notice,
)
from .line_attribution import (
    transfer_map, match_contributions, single_feature_map,
)

__all__ = [
    "Feature", "FeatureFunction", "next_feature_id", "used_pins", "used_names",
    "feature_mentions_pin", "serialize_features", "deserialize_features",
    "parse_sketch", "ParsedContributions", "SketchParseError",
    "assemble", "assemble_with_map", "clean_feature_contributions",
    "splice_add", "splice_replace", "SpliceError",
    "normalize_code", "is_dirty", "classify_edit",
    "used_global_names", "declared_name",
    "resolve_feature_pins", "guess_correction_target",
    "build_context_summary", "build_feature_instruction", "build_modify_instruction",
    "build_regen_instruction",
    "extract_feature_summary", "feature_label", "FEATURE_SUMMARY_DIRECTIVE",
    "compact_pin_label", "feature_combo_label", "feature_combo_tooltip",
    "default_action", "REGENERATE", "ADD", "CORRECT",
    "reassign_conflicting_pins", "ReassignResult", "PinMove",
    "format_reassign_notice",
    "transfer_map", "match_contributions", "single_feature_map",
]

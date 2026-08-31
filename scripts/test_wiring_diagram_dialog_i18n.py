"""Les 10 modales pedagogiques "en savoir plus" de la fin de
ui/wiring/wiring_diagram_dialog.py (apres WiringDiagramDialog, de
_ServoExternalPowerDialog a _MicrosteppingDialog) etaient figees en
francais, peu importe lang_manager -- meme mecanisme de trou que celui deja
corrige dans ui/wiring/instructions.py (cf test_warning_templates.py) et
ui/wiring/visual_ambiguity_catalog.py (cf test_visual_ambiguity_catalog.py) :
une chaine passee EN DUR a un widget ne bouge jamais avec la langue de
l'appli. Bascule l'appli en anglais/espagnol/italien et ces 10 modales-la
restaient seules a ne pas traduire, alors que tout le reste de l'appli le
fait.

Audit initial (grep sur les caracteres accentues) : ~69 chaines. Sous-compte
attendu -- du francais tout-ASCII ("Dans ton prompt", "Choisissez :") passe
au travers d'un grep accentue. Le vrai total, mesure en lisant chaque classe
en entier : 79 nouvelles cles _DIALOG_LABELS.

Meme structure que test_visual_ambiguity_catalog.py (le pendant sur
ui/wiring/visual_ambiguity_catalog.py, corrige le meme jour) : scan AST des
appels `_t("cle", lang)` + des cles referencees par les listes `_CHOICES`
(4 des 10 classes construisent leurs QRadioButton dans une boucle
`for val, key in self._CHOICES: QRadioButton(_t(key, lang))` -- la cle
n'apparait alors jamais comme litteral au site d'appel `_t(...)`, seulement
dans le tuple `(valeur, cle)` de `_CHOICES`, donc un scan qui ne regarderait
que les appels `_t("...", ...)` la manquerait completement).

Run : python scripts/test_wiring_diagram_dialog_i18n.py
"""
from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.wiring.wiring_diagram_dialog import _DIALOG_LABELS

_LANGS = ("fr", "en", "es", "it")
_SRC = ROOT / "ui" / "wiring" / "wiring_diagram_dialog.py"

# Prefixes scopant les 10 modales pedagogiques (cf checklist CLAUDE.md :
# "prefixer pour que ce soit visiblement scope a son dialogue"). Sert a
# isoler les 79 cles ajoutees par ce correctif des ~43 cles preexistantes
# de WiringDiagramDialog (deja correctement localisees, hors perimetre).
_DIALOG_PREFIXES = (
    "servo_power_", "led_series_", "btn_pullup_", "dht_pullup_",
    "ds18b20_pullup_", "l298n_", "l293d_module_", "a4988_vref_",
    "buzzer_series_", "a4988_microstep_", "drv8825_microstep_",
)


def _new_keys() -> set[str]:
    return {k for k in _DIALOG_LABELS
            if any(k.startswith(p) for p in _DIALOG_PREFIXES)}


def _literal_t_calls() -> set[str]:
    """Tous les appels `_t("cle", lang)` dont la cle est un litteral, par
    AST (pas de regex : une cle construite dynamiquement ne doit pas etre
    confondue avec une chaine litterale, et une occurrence en commentaire
    ne doit pas compter)."""
    tree = ast.parse(_SRC.read_text(encoding="utf-8"))
    keys = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None)
        if name != "_t" or not node.args:
            continue
        arg0 = node.args[0]
        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
            keys.add(arg0.value)
    return keys


def _choices_keys() -> set[str]:
    """Toute cle i18n referencee comme DONNEE plutot que comme litteral
    d'appel `_t(...)` :

    - 2e element d'un tuple d'une liste `_CHOICES` (les classes
      _LedSeriesValueDialog, _Ds18b20PullupDialog, _BuzzerSeriesValueDialog
      construisent leurs radios ainsi) ;
    - depuis #87, _MicrosteppingDialog est PARAMETRIQUE par driver : ses
      cles vivent dans `_CHOICES_BY_DRIVER` (dict -> listes de tuples) et
      dans `_TITLE_KEY` / `_TABLE_KEY` (dict -> cle en valeur), appelees
      via `_t(self._TITLE_KEY[drv], ...)` -- invisibles au collecteur de
      litteraux."""
    tree = ast.parse(_SRC.read_text(encoding="utf-8"))
    keys = set()

    def _tuples_of(list_node) -> None:
        for elt in list_node.elts:
            if not (isinstance(elt, ast.Tuple) and len(elt.elts) == 2):
                continue
            key_node = elt.elts[1]
            if isinstance(key_node, ast.Constant) \
                    and isinstance(key_node.value, str):
                keys.add(key_node.value)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if "_CHOICES" in names and isinstance(node.value, ast.List):
            _tuples_of(node.value)
        elif "_CHOICES_BY_DRIVER" in names \
                and isinstance(node.value, ast.Dict):
            for v in node.value.values:
                if isinstance(v, ast.List):
                    _tuples_of(v)
        elif names & {"_TITLE_KEY", "_TABLE_KEY"} \
                and isinstance(node.value, ast.Dict):
            for v in node.value.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    keys.add(v.value)
    return keys


def test_every_t_call_key_has_an_entry():
    """LA garde (meme motif que test_warning_templates.py /
    test_visual_ambiguity_catalog.py) : un appel a une cle absente de
    _DIALOG_LABELS retombe sur son repli francais (`_t` renvoie la cle
    brute en tout dernier recours) en silence -- exactement le defaut
    d'origine de ces 10 classes, reproduit cle par cle plutot que dialogue
    entier."""
    called = _literal_t_calls() | _choices_keys()
    missing = sorted(called - set(_DIALOG_LABELS))
    assert not missing, f"cles appelees sans entree _DIALOG_LABELS : {missing}"


def test_every_new_key_is_really_used():
    """Symetrique : une cle ajoutee mais jamais appelee signale soit un
    oubli de branchement (la chaine francaise d'origine serait alors
    encore en dur quelque part dans le widget), soit une cle morte."""
    called = _literal_t_calls() | _choices_keys()
    unused = sorted(_new_keys() - called)
    assert not unused, f"cles ajoutees mais jamais appelees : {unused}"


def test_every_dialog_label_entry_has_the_four_languages():
    incomplete = {key: sorted(set(_LANGS) - set(entry))
                  for key, entry in _DIALOG_LABELS.items()
                  if set(_LANGS) - set(entry) or not all(entry.values())}
    assert not incomplete, incomplete


def test_no_dialog_label_lost_a_placeholder_along_the_way():
    """Les 4 langues d'une meme cle doivent porter LES MEMES trous : un
    `{ref}` oublie en italien leve un KeyError au .format() -- en italien
    seulement, donc invisible depuis une machine francaise."""
    faulty = []
    for key, entry in _DIALOG_LABELS.items():
        sets = {lang: set(re.findall(r"\{(\w+)\}", entry[lang]))
                for lang in _LANGS if lang in entry}
        if len({frozenset(v) for v in sets.values()}) > 1:
            faulty.append((key, sets))
    assert not faulty, faulty


def test_the_new_keys_really_differ_between_languages():
    """Les 79 cles du jour : quatre copies du francais passeraient le test
    precedent sans rien traduire -- c'est le defaut qu'on corrige, pas sa
    mise en forme. Pas d'exigence de distinction 2 a 2 entre TOUTES les
    langues (cf test suivant : "jumpers" est un emprunt technique identique
    en fr/en/es dans un titre court) -- seul le cas « les 4 langues sont
    IDENTIQUES » (= rien traduit du tout) est fautif ici."""
    for key in sorted(_new_keys()):
        entry = _DIALOG_LABELS[key]
        assert len({entry[l] for l in _LANGS}) > 1, (key, entry)


# Seule collision fr == autre langue parmi les 79 cles du jour, verifiee
# explicitement plutot que supposee : "jumpers" est un emprunt technique
# identique en francais/anglais/espagnol dans un titre court (part-number +
# tiret + mot technique, ex "L298N U1 — jumpers"). L'italien, lui, varie
# deja (singulier "jumper"), ce qui suffit a prouver que la cle a bien ete
# traduite et n'est pas une simple copie oubliee.
_EXPECTED_FR_COLLISION = {
    "l298n_jumper_title": {"en", "es"},
}


def test_fr_is_not_silently_reused_outside_the_known_loanword():
    """Renforce le test precedent : en dehors de l'exception ci-dessus
    (documentee, verifiee par le test suivant), aucune des 79 cles ne doit
    reprendre le francais tel quel dans une autre langue -- c'est
    exactement le defaut d'origine (les 10 dialogues entiers, figes en
    francais) reproduit cle par cle."""
    surprises = []
    for key in sorted(_new_keys()):
        entry = _DIALOG_LABELS[key]
        allowed = _EXPECTED_FR_COLLISION.get(key, set())
        for lang in ("en", "es", "it"):
            if entry[lang] == entry["fr"] and lang not in allowed:
                surprises.append((key, lang))
    assert not surprises, surprises


def test_known_loanword_collision_is_still_real():
    """L'exception ci-dessus doit rester vraie : si une future retouche
    fait diverger fr/en/es sur cette cle, `_EXPECTED_FR_COLLISION` devient
    perimee et devrait etre nettoyee -- ce test le signale au lieu de
    laisser une exception fantome affaiblir le test precedent en
    silence."""
    for key, langs in _EXPECTED_FR_COLLISION.items():
        entry = _DIALOG_LABELS[key]
        for lang in langs:
            assert entry[lang] == entry["fr"], (
                f"{key}/{lang} ne colle plus a fr : "
                "retirer l'exception dans _EXPECTED_FR_COLLISION"
            )


TESTS = [
    test_every_t_call_key_has_an_entry,
    test_every_new_key_is_really_used,
    test_every_dialog_label_entry_has_the_four_languages,
    test_no_dialog_label_lost_a_placeholder_along_the_way,
    test_the_new_keys_really_differ_between_languages,
    test_fr_is_not_silently_reused_outside_the_known_loanword,
    test_known_loanword_collision_is_still_real,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"OK   {t.__name__}")
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    # Meme motif que les autres fichiers de scripts/ qui touchent
    # ui/wiring/wiring_diagram_dialog.py (import PyQt6 au niveau module) :
    # os._exit garde le code de sortie fidele aux assertions plutot qu'a un
    # teardown Qt statique qui peut deraper sous Windows.
    os._exit(0 if passed == len(TESTS) else 1)

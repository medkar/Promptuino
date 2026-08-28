"""Tout avertissement de cablage a son gabarit dans les 4 langues (2026-08-11).

Le mecanisme est propre : `add_warning(code, severity, message, refs, params)`
et `_render_warning_message` traduit PAR CODE via `_WARNING_TEMPLATES`, le
champ `message` n'etant qu'un repli (« Fallback: raw FR message »).

L'audit du 2026-08-11 a mesure que **3 codes sur 17 n'avaient aucun gabarit**
et retombaient donc sur leur repli francais dans les 4 langues :
`dht_data_pullup`, `ds18b20_data_pullup`, `buzzer_series_resistor` — soit
trois des composants les plus courants d'un kit debutant. Le repli marchait
« assez bien » pour ne jamais crever l'ecran : c'est exactement ce qui rend ce
genre de trou durable.

La garde ci-dessous est plus utile que les 3 correctifs : elle rougit au
PROCHAIN `add_warning` ajoute sans gabarit.

Run : python scripts/test_warning_templates.py
"""
import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.wiring.instructions import _WARNING_TEMPLATES

_LANGUES = ("fr", "en", "es", "it")


def _codes_emis() -> set[str]:
    """Tous les `code=` litteraux passes a un add_warning de ui/, par AST.

    Par AST et non par regex : un code construit dynamiquement ne doit pas
    etre confondu avec une chaine litterale, et une occurrence en commentaire
    ne doit pas compter."""
    codes = set()
    for p in sorted((ROOT / "ui").rglob("*.py")):
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for n in ast.walk(arbre):
            if not isinstance(n, ast.Call):
                continue
            nom = getattr(n.func, "attr", None) or getattr(n.func, "id", None)
            if nom != "add_warning":
                continue
            for kw in n.keywords:
                if kw.arg == "code" and isinstance(kw.value, ast.Constant) \
                        and isinstance(kw.value.value, str):
                    codes.add(kw.value.value)
    return codes


def test_every_emitted_code_has_a_template():
    """LA garde. Un code sans gabarit n'echoue jamais bruyamment : il rend son
    message de secours, en francais, et personne ne le voit depuis une machine
    francaise."""
    manquants = sorted(_codes_emis() - set(_WARNING_TEMPLATES))
    assert not manquants, f"codes sans gabarit : {manquants}"


def test_every_template_has_the_four_languages():
    incomplets = {code: sorted(set(_LANGUES) - set(t))
                  for code, t in _WARNING_TEMPLATES.items()
                  if set(_LANGUES) - set(t)}
    assert not incomplets, incomplets


def test_the_three_repaired_codes_really_differ_between_languages():
    """Les 3 du jour. Quatre copies du francais passeraient le test precedent
    sans rien traduire — c'est le defaut qu'on corrige, pas sa mise en forme."""
    for code in ("dht_data_pullup", "ds18b20_data_pullup",
                 "buzzer_series_resistor"):
        t = _WARNING_TEMPLATES[code]
        assert len({t[l] for l in _LANGUES}) == 4, (code, t)


def test_no_template_lost_a_placeholder_along_the_way():
    """Les 4 langues d'un meme code doivent porter LES MEMES trous : un
    `{value}` oublie en italien leve un KeyError a l'affichage, en italien
    seulement."""
    import re
    fautifs = []
    for code, t in _WARNING_TEMPLATES.items():
        jeux = {l: set(re.findall(r"\{(\w+)\}", t[l])) for l in _LANGUES if l in t}
        if len({frozenset(v) for v in jeux.values()}) > 1:
            fautifs.append((code, jeux))
    assert not fautifs, fautifs


def test_a_real_dht_sketch_now_speaks_italian():
    """Mesure de bout en bout, pas sur la table : le message REND-il vraiment
    autre chose en italien qu'en francais ?"""
    from ui.wiring.layout import pipeline as _wire
    from ui.wiring.instructions import _render_warning_message
    code = (
        '#include "DHT.h"\n'
        "DHT dht(2, DHT22);\n"
        "void setup() { Serial.begin(9600); dht.begin(); }\n"
        "void loop() { Serial.println(dht.readTemperature()); delay(2000); }\n"
    )
    nl = _wire.analyze_netlist(code, "arduino_uno_r3")
    pullups = [w for w in nl.warnings if w.code == "dht_data_pullup"]
    assert pullups, "le sketch DHT n'a pas produit l'avertissement attendu"
    w = pullups[0]
    fr = _render_warning_message(w, "fr")
    it = _render_warning_message(w, "it")
    assert fr and it and fr != it, (fr, it)


TESTS = [
    test_every_emitted_code_has_a_template,
    test_every_template_has_the_four_languages,
    test_the_three_repaired_codes_really_differ_between_languages,
    test_no_template_lost_a_placeholder_along_the_way,
    test_a_real_dht_sketch_now_speaks_italian,
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
    os._exit(0 if passed == len(TESTS) else 1)

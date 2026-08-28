"""Reprise du test du plafond, avec le VRAI critère de la panne d'origine.

TODO.md décrit la panne ainsi : le modèle « perdait la tâche de vue et
hallucinait jusqu'à une CONSTANTE (`SSD1306_SWITCHCAPITAL_WRAM`) ». Le premier
essai ne cherchait que des appels `objet.methode(` — il serait passé à côté.

On ajoute donc :
  - les constantes en MAJUSCULES inventées, confrontées aux vraies (extraites
    de l'en-tête réellement installé) ;
  - la « perte de la tâche » : le sketch affiche-t-il encore le texte demandé ?
Et on ARCHIVE chaque sortie, pour pouvoir la relire au lieu de la croire.
"""
import json
import pathlib
import re
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIBS = (pathlib.Path.home() / "Documents" / "PromptuinoUI_projects"
        / "Arduino" / "libraries")
OUT = ROOT / "scripts" / "out" / "api_ceiling"
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import ui.rag as rag

OLLAMA = "http://127.0.0.1:11434/api/generate"
RUNS = 3
MODELES = ["gemma4:e2b", "gemma4:12b"]
TACHE = 'Affiche le texte "Bonjour" sur un ecran OLED SSD1306 en I2C.'

corpus = json.loads((ROOT / "assets" / "rag" / "corpus.json").read_text("utf-8"))
entry = {e["id"]: e for e in corpus}["adafruit-ssd1306"]
sigs, example = entry["api_signatures"], entry["example_code"]

# --- Vérité terrain : constantes RÉELLES des en-têtes installés -------------
VRAIES_CONST: set[str] = set()
for h in LIBS.rglob("*.h"):
    try:
        txt = h.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        continue
    VRAIES_CONST |= set(re.findall(r"#define\s+([A-Z][A-Z0-9_]{3,})", txt))
    VRAIES_CONST |= set(re.findall(r"\b([A-Z][A-Z0-9_]{3,})\s*=", txt))
CORE = {"HIGH", "LOW", "INPUT", "OUTPUT", "INPUT_PULLUP", "LED_BUILTIN",
        "SERIAL", "WHITE", "BLACK", "INVERSE", "SSD1306_WHITE", "SSD1306_BLACK",
        "A0", "A1", "A2", "A3", "A4", "A5", "SDA", "SCL", "OLED_RESET"}

REELLES = {rag._function_name(s) for lst in sigs.values() for s in lst}
REELLES |= {"begin", "display", "clearDisplay", "setTextSize", "setTextColor",
            "setCursor", "println", "print", "write"}
IGNORE_M = {"begin", "print", "println", "printf", "write", "h", "c_str"}

bloc_plafonne = rag._format_api_signatures(sigs, example)
_l = ["API (use only these — do NOT invent others):"]
for cls, lst in sigs.items():
    _l.append(f"- {cls}:")
    _l += [f"  - {s}" for s in lst]
bloc_complet = "\n".join(_l)


def prompt_pour(bloc):
    return (f"Task: {TACHE}\n\nRelevant Arduino libraries — reference these "
            f"exact APIs and patterns when applicable. Do not invent function "
            f"names that are not shown here.\n\n### {entry['name']}\n"
            f"Headers: {', '.join('`' + h + '`' for h in entry['headers'])}\n"
            f"{bloc}\nExample:\n```cpp\n{example}\n```\n\n---\n\n{TACHE}\n"
            f"Reponds uniquement par le code Arduino complet.")


def genere(modele, prompt):
    body = json.dumps({"model": modele, "prompt": prompt, "stream": False,
                       "options": {"num_ctx": 16384, "temperature": 0.2}}).encode()
    req = urllib.request.Request(OLLAMA, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())["response"]


def juge(code):
    methodes = set(re.findall(r"\b\w+\s*\.\s*(\w+)\s*\(", code)) - IGNORE_M
    const = set(re.findall(r"\b([A-Z][A-Z0-9_]{3,})\b", code))
    return (sorted(methodes - REELLES),
            sorted(const - VRAIES_CONST - CORE),
            "Bonjour" in code,
            "void setup" in code and "void loop" in code)


OUT.mkdir(exist_ok=True)
print(f"constantes reelles connues : {len(VRAIES_CONST)}")
print(f"bloc plafonne {len(bloc_plafonne.splitlines())-1} lignes | "
      f"complet {len(bloc_complet.splitlines())-1} lignes\n")

for modele in MODELES:
    print(f"===== {modele} =====")
    for nom, bloc in (("PLAFONNE", bloc_plafonne), ("COMPLET ", bloc_complet)):
        m_inv, c_inv, perdu, mal = [], [], 0, 0
        for i in range(RUNS):
            code = genere(modele, prompt_pour(bloc))
            (OUT / f"{modele.replace(':','_')}_{nom.strip()}_{i}.txt").write_text(
                code, encoding="utf-8")
            mi, ci, tache_ok, struct_ok = juge(code)
            m_inv += mi
            c_inv += ci
            perdu += 0 if tache_ok else 1
            mal += 0 if struct_ok else 1
        print(f"  {nom} : methodes inventees {len(m_inv)} | "
              f"constantes inventees {len(c_inv)} | "
              f"tache perdue {perdu}/{RUNS} | sketch mal forme {mal}/{RUNS}")
        if c_inv:
            print(f"             constantes : {sorted(set(c_inv))[:10]}")
        if m_inv:
            print(f"             methodes   : {sorted(set(m_inv))[:10]}")
    print()
print(f"sorties archivees dans {OUT}")

"""Le plafond de signatures : peut-on TOUT injecter sans dégrader ? (TODO #66)

⚠️ **Distinct de son voisin `bench_api_ceiling.py`**, qui répond à une autre
question. Celui-là cherchait à reproduire la panne d'origine (« les 122
signatures faisaient dérailler le modèle ») sur UNE tâche, et n'y est pas
parvenu. Mais cette tâche était **dans le périmètre de l'exemple officiel** :
le bloc plafonné contenait déjà tout ce qu'il fallait, donc l'expérience ne
pouvait pas voir le cas intéressant.

Ce banc-ci ajoute la moitié manquante : des tâches **HORS du périmètre de
l'exemple**, dont la fonction utile est documentée par la bibliothèque mais
**coupée** par le plafond. C'est là, et seulement là, que le plafond peut faire
du mal — et que tout injecter peut faire du bien.

Deux questions, deux bandes :

  DANS le périmètre — tout injecter DÉGRADE-t-il ? On surveille les méthodes
  et constantes inventées, la tâche perdue, le sketch mal formé.

  HORS du périmètre — le plafond FAIT-IL du mal ? On surveille si le sketch
  appelle la fonction CIBLE, celle qui n'existe que dans le bloc complet.

Conditions identiques à celles de l'app : température 0.25
(`_CODE_TASK_TEMPERATURE`), num_ctx 16384. Chaque sortie est archivée pour
pouvoir être relue plutôt que crue.

Run : python scripts/bench_api_ceiling_scope.py [--runs N] [--modeles a,b]
"""
import json
import pathlib
import re
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIBS = (pathlib.Path.home() / "Documents" / "Promptuino" / "projets"
        / "Arduino" / "libraries")
OUT = ROOT / "scripts" / "out" / "api_ceiling_scope"
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import ui.rag as rag

OLLAMA = "http://127.0.0.1:11434/api/generate"
TEMPERATURE = 0.25   # = ollama_backend._CODE_TASK_TEMPERATURE
NUM_CTX = 16384

# Les trois bibliothèques que le plafond coupe le PLUS (mesuré 2026-08-26) :
# 16/78, 19/74, 20/54 signatures injectées sur documentées.
#
# `cible` est une fonction RÉELLE de la bibliothèque, absente du bloc plafonné.
# `marqueur` sert aux tâches dans le périmètre, où il n'y a pas de cible : le
# sketch fait-il encore ce qu'on lui demandait ?
CAS = [
    dict(lib="adafruit-ssd1306", bande="dans",
         tache='Affiche le texte "Bonjour" sur un ecran OLED SSD1306 en I2C.',
         cible=None, marqueur="Bonjour"),
    dict(lib="adafruit-ssd1306", bande="hors",
         tache="Dessine un cercle PLEIN au centre d'un ecran OLED SSD1306 en "
               "I2C. Rien d'autre : pas de texte.",
         cible={"fillCircle"}, marqueur=None),
    dict(lib="dallas-temperature", bande="dans",
         tache="Lis la temperature d'un DS18B20 sur la broche 2 et affiche-la "
               "en degres Celsius sur le moniteur serie.",
         cible=None, marqueur="Serial"),
    dict(lib="dallas-temperature", bande="hors",
         tache="Lis la temperature d'un DS18B20 sur la broche 2 et affiche-la "
               "en degres FAHRENHEIT sur le moniteur serie.",
         cible={"getTempFByIndex", "getTempF"}, marqueur=None),
    dict(lib="rtclib", bande="dans",
         tache="Affiche l'heure d'un module RTC DS3231 sur le moniteur serie.",
         cible=None, marqueur="Serial"),
    dict(lib="rtclib", bande="hors",
         tache="Affiche la temperature interne du capteur d'un module RTC "
               "DS3231 sur le moniteur serie.",
         cible={"getTemperature"}, marqueur=None),
]

# ── Vérité terrain : constantes RÉELLES des en-têtes installés ───────────────
VRAIES_CONST: set[str] = set()
for h in LIBS.rglob("*.h"):
    try:
        txt = h.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        continue
    VRAIES_CONST |= set(re.findall(r"#define\s+([A-Z][A-Z0-9_]{3,})", txt))
    VRAIES_CONST |= set(re.findall(r"\b([A-Z][A-Z0-9_]{3,})\s*=", txt))

CORE_CONST = {"HIGH", "LOW", "INPUT", "OUTPUT", "INPUT_PULLUP", "LED_BUILTIN",
              "SERIAL", "WHITE", "BLACK", "INVERSE", "A0", "A1", "A2", "A3",
              "A4", "A5", "SDA", "SCL", "DEC", "HEX", "TODO", "LOOP", "SETUP"}
# Méthodes du cœur Arduino : appelées partout, documentées nulle part.
CORE_METH = {"begin", "print", "println", "printf", "write", "read", "available",
             "flush", "c_str", "length", "toInt", "toFloat", "trim", "delay",
             "concat", "equals", "substring", "indexOf", "charAt", "reserve",
             "end", "setTimeout"}


def bloc_complet(sigs: dict) -> str:
    lignes = ["API (use only these — do NOT invent others):"]
    for cls, lst in sigs.items():
        lignes.append(f"- {cls}:")
        lignes += [f"  - {s}" for s in lst]
    return "\n".join(lignes)


def prompt_pour(entry: dict, bloc: str, tache: str) -> str:
    """Même forme que ce que l'app envoie (en-tête impératif + exemple)."""
    return (f"Task: {tache}\n\nRelevant Arduino libraries — reference these "
            f"exact APIs and patterns when applicable. Do not invent function "
            f"names that are not shown here.\n\n### {entry['name']}\n"
            f"Headers: {', '.join('`' + h + '`' for h in entry.get('headers', []))}\n"
            f"{bloc}\nExample:\n```cpp\n{entry.get('example_code', '')}\n```\n"
            f"\n---\n\n{tache}\n"
            f"Reponds uniquement par le code Arduino complet.")


def genere(modele: str, prompt: str) -> str:
    body = json.dumps({"model": modele, "prompt": prompt, "stream": False,
                       "options": {"num_ctx": NUM_CTX,
                                   "temperature": TEMPERATURE}}).encode()
    req = urllib.request.Request(OLLAMA, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())["response"]


_COMMENTAIRE = re.compile(r"//[^\n]*|/\*.*?\*/|\"(?:[^\"\\]|\\.)*\"", re.S)


def _sans_commentaires(code: str) -> str:
    """Retire commentaires ET chaînes littérales.

    ⚠️ Piège de mesure, déjà payé une fois par `bench_api_ceiling.py` et
    re-payé ici au premier essai : sans ça, `NOTE` et `IMPORTANTE` — des mots
    dans des commentaires français — sont comptés comme des constantes
    inventées, et `DS18B20` l'est parce qu'il apparaît dans un
    `Serial.println("Initialisation du DS18B20")`. Le premier dépouillement
    affichait 8 à 12 « constantes inventées » dans TOUTES les conditions ;
    après nettoyage il n'en reste aucune. Un indicateur qui bruite pareil
    partout ne mesure rien."""
    return _COMMENTAIRE.sub(" ", code)


def _definies_par_le_sketch(code: str) -> set[str]:
    """Constantes et types que le sketch déclare LUI-MÊME.

    `SCREEN_WIDTH`, `OLED_RESET`, `ONE_WIRE_BUS` ne sont pas hallucinées : le
    modèle les écrit puis les utilise, ce qui est exactement ce qu'un sketch
    Arduino fait. Les compter serait punir le modèle d'avoir bien travaillé."""
    noms = set(re.findall(r"#define\s+(\w+)", code))
    noms |= set(re.findall(r"\bconst\s+[\w:]+\s+(\w+)", code))
    noms |= set(re.findall(r"\b(?:static\s+)?[\w:]*\b(\w+)\s+\w+\s*=\s*[^=]", code))
    # Types instanciés : `Adafruit_SSD1306 display(...)`, `RTC_DS3231 rtc;`
    noms |= set(re.findall(r"\b([A-Za-z_]\w*)\s+\w+\s*[;(]", code))
    # Le nom de type peut être composite : en retenir aussi les morceaux.
    for n in list(noms):
        noms |= set(re.findall(r"[A-Z][A-Z0-9]{2,}", n))
    return noms


def juge(code: str, reelles: set[str], cas: dict) -> dict:
    net = _sans_commentaires(code)
    methodes = set(re.findall(r"\b\w+\s*\.\s*(\w+)\s*\(", net)) - CORE_METH
    const = set(re.findall(r"\b([A-Z][A-Z0-9_]{3,})\b", net))
    const -= _definies_par_le_sketch(net)
    return dict(
        meth_inventees=sorted(methodes - reelles),
        const_inventees=sorted(const - VRAIES_CONST - CORE_CONST),
        cible_ok=(bool(cas["cible"] & methodes) if cas["cible"] else None),
        marqueur_ok=(cas["marqueur"] in code if cas["marqueur"] else None),
        bien_forme=("void setup" in code and "void loop" in code),
        # Ce que le modèle a appelé POUR DE VRAI. Sans ça, « cible non
        # atteinte » ne dit pas s'il a halluciné ou s'il s'est rabattu sur une
        # fonction réelle mais plus maladroite — or c'est TOUTE la différence,
        # et c'est ce que la première manche a montré (le bloc complet
        # produisait `drawCircle`, le plafonné `drawPixel` : deux vraies
        # fonctions, deux niveaux de maladresse, zéro hallucination).
        methodes_lib=sorted(methodes & reelles),
    )


def main() -> int:
    runs = 3
    modeles = ["gemma4:e2b", "gemma4:12b"]
    for i, a in enumerate(sys.argv[1:]):
        if a == "--runs":
            runs = int(sys.argv[i + 2])
        elif a == "--modeles":
            modeles = sys.argv[i + 2].split(",")

    OUT.mkdir(parents=True, exist_ok=True)
    print(f"constantes reelles connues : {len(VRAIES_CONST)}")
    print(f"temperature {TEMPERATURE} | num_ctx {NUM_CTX} | {runs} run(s)\n")

    resultats = []
    total = len(CAS) * 2 * len(modeles) * runs
    fait = 0
    debut = time.time()
    for cas in CAS:
        entry = rag.corpus_entry(cas["lib"])
        assert entry, cas["lib"]
        sigs = entry["api_signatures"]
        reelles = {rag._function_name(s) for lst in sigs.values() for s in lst}
        plafonne = rag._format_api_signatures(sigs, entry.get("example_code", ""))
        complet = bloc_complet(sigs)
        n_p = sum(1 for l in plafonne.splitlines() if l.startswith("  - "))
        n_c = sum(1 for l in complet.splitlines() if l.startswith("  - "))
        print(f"=== {cas['lib']} [{cas['bande']}] — plafonne {n_p} sigs / "
              f"complet {n_c} sigs")
        print(f"    {cas['tache'][:78]}")
        for modele in modeles:
            for nom, bloc in (("plafonne", plafonne), ("complet", complet)):
                for r in range(runs):
                    code = genere(modele, prompt_pour(entry, bloc, cas["tache"]))
                    stem = (f"{cas['lib']}_{cas['bande']}_"
                            f"{modele.replace(':', '_')}_{nom}_{r}")
                    (OUT / f"{stem}.txt").write_text(code, encoding="utf-8")
                    v = juge(code, reelles, cas)
                    v.update(lib=cas["lib"], bande=cas["bande"], modele=modele,
                             bloc=nom, run=r)
                    resultats.append(v)
                    fait += 1
                    if fait % 6 == 0:
                        ecoule = time.time() - debut
                        print(f"      {fait}/{total} — {ecoule/60:.1f} min "
                              f"(reste ~{(total-fait)*ecoule/fait/60:.0f} min)")
        print()

    (OUT / "resultats.json").write_text(
        json.dumps(resultats, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── Dépouillement ────────────────────────────────────────────────────────
    print("=" * 68)
    for bande, titre in (("dans", "DANS le perimetre — tout injecter degrade-t-il ?"),
                         ("hors", "HORS du perimetre — le plafond fait-il du mal ?")):
        print(f"\n### {titre}")
        for modele in modeles:
            for nom in ("plafonne", "complet"):
                lot = [v for v in resultats if v["bande"] == bande
                       and v["modele"] == modele and v["bloc"] == nom]
                if not lot:
                    continue
                mi = sum(len(v["meth_inventees"]) for v in lot)
                ci = sum(len(v["const_inventees"]) for v in lot)
                mal = sum(1 for v in lot if not v["bien_forme"])
                if bande == "hors":
                    ok = sum(1 for v in lot if v["cible_ok"])
                    detail = f"cible atteinte {ok}/{len(lot)}"
                else:
                    ok = sum(1 for v in lot if v["marqueur_ok"])
                    detail = f"tache tenue {ok}/{len(lot)}"
                print(f"  {modele:12s} {nom:9s} : {detail} | "
                      f"methodes inventees {mi} | constantes inventees {ci} | "
                      f"mal forme {mal}/{len(lot)}")
    print(f"\nsorties archivees dans {OUT}")
    print(f"duree totale : {(time.time()-debut)/60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

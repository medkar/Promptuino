"""Banc SLM #82 : que GENERE le modele pour un prompt moteur sans puce nommee,
maintenant que le retrieval ne lui en pousse plus une ?

La crainte a ecarter par la mesure (pas par le pari) : prive de contexte de
driver, le SLM pourrait piocher une lib dans sa memoire d'entrainement
(AFMotor, vieux shields...) -- la meme devinette qu'avant, mais invisible.
L'espoir a verifier : il ecrit du code en broches nues (analogWrite +
digitalWrite), la forme que TOUT le pipeline de cablage attend (groupement
niveau 3, modale, cards de drivers, offre de regeneration).

Conditions de l'app : le bloc RAG est le VRAI `rag.build_lib_context(prompt)`
(donc post-filtre #82), temperature et num_ctx de `ollama_backend`, modele par
defaut de l'app (gemma4:e2b).

Trois juges par generation :
  - driver_lib : un `#include` de lib de driver/moteur (L298N, TB6612,
    AFMotor, MotorShield, Grove motor, PCA9685...) -> l'echec redoute ;
  - broches_nues : le code pilote par analogWrite/digitalWrite ;
  - cablage : `extract_netlist` + groupement -> combien de moteurs GROUPES le
    detecteur voit (2 attendus pour les prompts "deux moteurs").

Run : python scripts/bench_motor_slm.py [--runs N] [--modele gemma4:e2b]
"""
from __future__ import annotations
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import os  # noqa: E402
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")

from ui import rag  # noqa: E402

OLLAMA = "http://127.0.0.1:11434/api/generate"
TEMPERATURE = 0.25   # = ollama_backend._CODE_TASK_TEMPERATURE
NUM_CTX = 16384

PROMPTS = [
    ("fr", "deux moteurs DC", 2),
    ("en", "two DC motors forward and backward", 2),
    ("fr", "un robot à deux roues qui avance et recule", 2),
]

# Includes qui signeraient une lib de driver sortie de la memoire du modele.
_DRIVER_INCLUDE = re.compile(
    r"#\s*include\s*[<\"]\s*(l29[38]|tb6612|drv88|afmotor|adafruit_motorshield"
    r"|motordriver|grove.*motor|pca9685|adafruit_pwmservodriver)",
    re.IGNORECASE)
_CODE_BLOCK = re.compile(r"```(?:cpp|c\+\+|arduino|c)?\s*(.*?)```", re.S)


def _extraire_code(reponse: str) -> str:
    blocs = _CODE_BLOCK.findall(reponse)
    return max(blocs, key=len) if blocs else reponse


def _generer(modele: str, prompt: str) -> str:
    body = json.dumps({"model": modele, "prompt": prompt, "stream": False,
                       "options": {"num_ctx": NUM_CTX,
                                   "temperature": TEMPERATURE}}).encode()
    req = urllib.request.Request(OLLAMA, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())["response"]


def _juger(code: str) -> dict:
    from ui.wiring.markers import extract_netlist
    driver = _DRIVER_INCLUDE.search(code)
    nu = bool(re.search(r"\banalogWrite\s*\(", code)
              or re.search(r"\bdigitalWrite\s*\(", code))
    try:
        nl = extract_netlist(code, "arduino_uno_r3", prompt="", context="")
        groupes = sorted({c.attributes.get("_grouped_pwm_pin")
                          for c in nl.components
                          if c.attributes.get("_grouped_pwm_pin")})
        types = sorted({c.type for c in nl.components})
    except Exception as exc:            # le juge dit l'echec, ne le cache pas
        groupes, types = [], [f"extract_netlist KO: {exc}"]
    return {"driver_include": driver.group(0) if driver else None,
            "broches_nues": nu, "moteurs_groupes": len(groupes),
            "types": types}


def main() -> int:
    args = sys.argv[1:]
    runs = int(args[args.index("--runs") + 1]) if "--runs" in args else 2
    modele = (args[args.index("--modele") + 1]
              if "--modele" in args else "gemma4:e2b")
    if not rag._load():
        print("MODELE ONNX INDISPONIBLE -- banc impossible.")
        return 2

    fautes = 0
    total = 0
    for lang, tache, attendus in PROMPTS:
        contexte = rag.build_lib_context(tache)
        print(f"\n=== [{lang}] {tache!r} ===")
        print(f"  bloc RAG : {len(contexte)} caracteres"
              f"{' (VIDE)' if not contexte.strip() else ''}")
        for i in range(runs):
            prompt = ((contexte + "\n\n") if contexte.strip() else "") + (
                f"Task: {tache}\n"
                f"Reponds uniquement par le code Arduino complet.")
            t0 = time.time()
            code = _extraire_code(_generer(modele, prompt))
            verdict = _juger(code)
            total += 1
            faute = verdict["driver_include"] is not None
            if faute:
                fautes += 1
            print(f"  run {i + 1} ({time.time() - t0:5.1f}s) : "
                  f"driver={verdict['driver_include'] or 'aucun'}  "
                  f"nu={verdict['broches_nues']}  "
                  f"moteurs groupes={verdict['moteurs_groupes']}"
                  f"  types={verdict['types']}"
                  f"{'  ❌' if faute else ''}")

    print(f"\nBILAN : {fautes}/{total} generations incluent une lib de "
          f"driver sortie de la memoire du modele.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

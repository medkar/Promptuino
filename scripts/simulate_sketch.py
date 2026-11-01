"""Exécuter un sketch Arduino SUR LE PC, sans carte — pour tester ce qu'il
FAIT, pas ce à quoi il ressemble.

Né de la QA AG1 (TODO #90, 2026-08-31) : le défaut d'origine — un compteur
d'appuis qui compte zéro — ne se voit ni à la compilation, ni au schéma, ni
à la lecture (toutes les variantes cassées *ressemblaient* à un anti-rebond).
Il ne se voyait qu'en appuyant sur un vrai bouton. Cet outil remplace le
bouton.

Principe : une fausse API Arduino en C++ (`millis`, `digitalRead`,
`Serial`…), le sketch compilé avec g++ pour la machine hôte, et une
chronologie d'entrées scriptée. Le temps est VIRTUEL : chaque tour de
`loop()` avance d'une milliseconde, `delay(n)` en avance de n. Le sketch ne
sait pas qu'il ne tourne pas sur un Arduino.

Usage :
    python scripts/simulate_sketch.py mon_sketch.ino \\
        --press 2:300-500,800-1000,1300-1500 --ms 2000

    --press  broche:debut-fin[,debut-fin...]   appuis (broche à LOW)
    --analog broche:valeur                      valeur lue par analogRead
    --ms     duree simulee (defaut 3000)

⚠️ **Limites assumées, à connaître avant de conclure** : le temps n'avance
que d'1 ms par tour (une boucle réelle est plus rapide, donc un anti-rebond
de 50 ms est ici *plus* facile à satisfaire — on ne fabrique pas de faux
succès dans l'autre sens) ; pas de vraie liaison série, d'interruptions, ni
de bibliothèques tierces — un sketch qui `#include` une lib ne compilera pas
et l'outil le dira au lieu de deviner.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_STUB = r"""
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <string>
#include <map>
#include <vector>

#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
#define A0 14
#define A1 15
#define A2 16
#define A3 17
#define A4 18
#define A5 19
#define LED_BUILTIN 13
#define DEC 10
#define HEX 16

typedef std::string String;
typedef uint8_t byte;
typedef bool boolean;

static unsigned long g_ms = 0;
// Intervalles d'appui par broche : la broche est LOW pendant l'intervalle.
static std::map<int, std::vector<std::pair<unsigned long, unsigned long>>> g_press;
static std::map<int, int> g_analog;
// Ce que le sketch ECRIT : derniere valeur + nombre de fronts montants.
static std::map<int, int> g_out;
static std::map<int, int> g_rises;

unsigned long millis() { return g_ms; }
unsigned long micros() { return g_ms * 1000UL; }
void delay(unsigned long ms) { g_ms += ms; }
void delayMicroseconds(unsigned int us) { g_ms += us / 1000; }
void pinMode(int, int) {}

int digitalRead(int pin) {
    auto it = g_press.find(pin);
    if (it != g_press.end())
        for (auto &iv : it->second)
            if (g_ms >= iv.first && g_ms < iv.second) return LOW;   // appuye
    return HIGH;                                                    // relache
}
void digitalWrite(int pin, int v) {
    if (v == HIGH && g_out[pin] != HIGH) g_rises[pin]++;
    g_out[pin] = v;
}
int analogRead(int pin) {
    auto it = g_analog.find(pin);
    return it == g_analog.end() ? 0 : it->second;
}
void analogWrite(int, int) {}
// Le buzzer est SUIVI : sans ca, une fonctionnalite sonore est invisible a
// la simulation (trou releve en jouant la QA AG2).
static std::map<int, unsigned int> g_tone;
static std::map<int, int> g_tone_starts;
void tone(int pin, unsigned int f) {
    if (g_tone[pin] == 0) g_tone_starts[pin]++;
    g_tone[pin] = f;
}
void tone(int pin, unsigned int f, unsigned long) { tone(pin, f); }
void noTone(int pin) { g_tone[pin] = 0; }
long map(long x, long a, long b, long c, long d) {
    return (x - a) * (d - c) / (b - a) + c;
}
long random(long a) { return a ? (long)(g_ms % (unsigned long)a) : 0; }
long random(long a, long b) { return b > a ? a + (long)(g_ms % (unsigned long)(b - a)) : a; }
void randomSeed(unsigned long) {}
double constrain(double x, double a, double b) { return x < a ? a : (x > b ? b : x); }
int abs_(int x) { return x < 0 ? -x : x; }

struct SerialStub {
    void begin(long) {}
    operator bool() const { return true; }
    template <typename T> void print(T v) { std::printf("%s", to_s(v).c_str()); }
    template <typename T> void print(T v, int) { std::printf("%s", to_s(v).c_str()); }
    template <typename T> void println(T v) { std::printf("%s\n", to_s(v).c_str()); }
    template <typename T> void println(T v, int) { std::printf("%s\n", to_s(v).c_str()); }
    void println() { std::printf("\n"); }
    int available() { return 0; }
    int read() { return -1; }
    void flush() {}
    static std::string to_s(const char *v) { return v; }
    static std::string to_s(const std::string &v) { return v; }
    static std::string to_s(char v) { return std::string(1, v); }
    static std::string to_s(int v) { return std::to_string(v); }
    static std::string to_s(long v) { return std::to_string(v); }
    static std::string to_s(unsigned int v) { return std::to_string(v); }
    static std::string to_s(unsigned long v) { return std::to_string(v); }
    static std::string to_s(double v) {
        char b[32]; std::snprintf(b, sizeof b, "%.2f", v); return b;
    }
};
static SerialStub Serial;

void setup();
void loop();

int main(int argc, char **argv) {
    unsigned long duree = argc > 1 ? std::strtoul(argv[1], nullptr, 10) : 3000;
    // argv[2] : "pin:debut-fin,debut-fin;pin:..." | argv[3] : "pin:valeur,..."
    if (argc > 2 && std::strlen(argv[2])) {
        char *s = strdup(argv[2]);
        for (char *grp = strtok(s, ";"); grp; grp = strtok(nullptr, ";")) {
            int pin = atoi(grp);
            char *deb = strchr(grp, ':');
            if (!deb) continue;
            char *iv = strtok_r(deb + 1, ",", &deb);
            for (char *save = nullptr; iv; iv = strtok_r(nullptr, ",", &deb)) {
                (void)save;
                unsigned long a = strtoul(iv, nullptr, 10);
                char *tir = strchr(iv, '-');
                unsigned long b = tir ? strtoul(tir + 1, nullptr, 10) : a;
                g_press[pin].push_back({a, b});
            }
        }
    }
    if (argc > 3 && std::strlen(argv[3])) {
        char *s = strdup(argv[3]);
        for (char *grp = strtok(s, ","); grp; grp = strtok(nullptr, ",")) {
            char *d = strchr(grp, ':');
            if (d) g_analog[atoi(grp)] = atoi(d + 1);
        }
    }
    setup();
    while (g_ms < duree) {
        unsigned long avant = g_ms;
        loop();
        if (g_ms == avant) g_ms++;        // un tour = 1 ms minimum
    }
    std::printf("\n--- ETAT FINAL DES SORTIES ---\n");
    for (auto &kv : g_out)
        std::printf("broche %d : %s (%d allumage%s)\n", kv.first,
                    kv.second == HIGH ? "HIGH" : "LOW", g_rises[kv.first],
                    g_rises[kv.first] > 1 ? "s" : "");
    for (auto &kv : g_tone)
        std::printf("buzzer broche %d : %s (%d emission%s)\n", kv.first,
                    kv.second ? "en train de sonner" : "silencieux",
                    g_tone_starts[kv.first],
                    g_tone_starts[kv.first] > 1 ? "s" : "");
    return 0;
}
"""


# Définition de fonction au niveau TOP d'un sketch (colonne 0). Sert à
# fabriquer les prototypes que l'IDE Arduino génère automatiquement et que
# g++ n'a pas : sans eux, un sketch qui appelle une fonction définie APRÈS
# `loop()` ne compile pas (relevé en jouant la QA AG2 — l'outil refusait
# alors de conclure, ce qui était honnête mais bloquant).
_DEF_FONCTION_RE = re.compile(
    r"^((?:static\s+)?(?:unsigned\s+|signed\s+)?"
    r"(?:void|int|long|short|char|byte|bool|boolean|float|double|String|"
    r"uint8_t|uint16_t|uint32_t|int8_t|int16_t|int32_t|size_t)"
    r"(?:\s+long|\s+int)*\s*\**\s*(\w+)\s*\([^;{)]*\))\s*\{",
    re.MULTILINE)


def _prototypes(src: str) -> list[str]:
    """Prototypes des fonctions définies dans le sketch, `setup`/`loop`
    exclus (déjà déclarés par le harnais)."""
    return [f"{m.group(1)};" for m in _DEF_FONCTION_RE.finditer(src)
            if m.group(2) not in ("setup", "loop")]


def _prepare(ino: str) -> tuple[str, list[str]]:
    """Rend (source compilable, avertissements). Retire les `#include` de
    bibliothèques (la fausse API les remplace) et le dit ; ajoute les
    prototypes que l'IDE Arduino fabrique dans notre dos."""
    avertis: list[str] = []
    lignes: list[str] = []
    for ln in ino.split("\n"):
        m = re.match(r"\s*#\s*include\s*[<\"]([^>\"]+)[>\"]", ln)
        if m:
            nom = m.group(1)
            if nom not in ("Arduino.h",):
                avertis.append(nom)
            continue
        lignes.append(ln)
    src = "\n".join(lignes)
    protos = _prototypes(src)
    if protos:
        src = "\n".join(protos) + "\n" + src
    return src, avertis


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sketch")
    ap.add_argument("--press", default="",
                    help="broche:debut-fin[,debut-fin] (plusieurs broches : ;)")
    ap.add_argument("--analog", default="", help="broche:valeur[,broche:valeur]")
    ap.add_argument("--ms", type=int, default=3000, help="duree simulee")
    a = ap.parse_args()

    src, libs = _prepare(Path(a.sketch).read_text(encoding="utf-8", errors="replace"))
    if libs:
        print(f"⚠️  bibliotheques ignorees (la fausse API ne les fournit pas) : "
              f"{', '.join(libs)}\n    -> si le sketch en depend vraiment, la "
              f"compilation va echouer, et c'est honnete : mieux vaut refuser "
              f"que simuler faux.\n")
    d = tempfile.mkdtemp(prefix="sim_ino_")
    cpp = Path(d) / "sketch.cpp"
    cpp.write_text(_STUB + "\n#line 1 \"sketch\"\n" + src, encoding="utf-8")
    exe = Path(d) / "sketch.exe"
    r = subprocess.run(["g++", "-std=c++17", "-w", "-o", str(exe), str(cpp)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("COMPILATION IMPOSSIBLE (la simulation ne conclut PAS) :\n")
        print("\n".join(r.stderr.strip().split("\n")[:12]))
        return 2
    presses = a.press.replace(" ", "")
    run = subprocess.run([str(exe), str(a.ms), presses, a.analog],
                         capture_output=True, text=True, timeout=60)
    print(run.stdout, end="")
    if run.returncode != 0:
        print(f"\n(le sketch s'est termine avec le code {run.returncode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

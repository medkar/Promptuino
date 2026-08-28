"""Genere la batterie C : les prompts de SUITE (TODO #64).

⚠️ Ce script ECRIT la batterie, il ne la mesure pas. Une fois
`bench_rag_prompts_c.json` produit et relu, la batterie est GELEE : la mesurer
puis la retoucher reviendrait a se noter soi-meme.

POURQUOI UNE TROISIEME BATTERIE. A et B ne contiennent que des prompts
INITIAUX. #64 porte sur ce qui arrive APRES : « affiche plutot en Celsius »
lance sur un projet qui tourne deja. Le retrieval y voit le prompt NU -- ni le
code, ni la puce qui y est declaree -- et injecte la lib d'un thermocouple dans
un projet BME280.

CE QUE CHAQUE CAS PORTE EN PLUS DE A ET B : `project_headers`, les `#include`
deja presents. Sans eux la question n'a pas de sens -- « ajoute un ecran » est
legitime, « un autre capteur de temperature » ne l'est pas, et c'est le code
existant qui fait la difference.

CINQ BANDES, et elles n'attendent pas la meme chose :
  unit_change / behaviour  -> AUCUNE lib ne doit etre injectee. Le materiel ne
                              change pas ; le code fait deja autorite.
  add_unnamed              -> la famille demandee DOIT etre injectee, meme si
                              l'utilisateur ne nomme aucune puce. C'est le cas
                              qui interdit la regle « nommer, c'est decider ».
  add_named / replace_named-> la puce nommee DOIT etre injectee.

Run : python scripts/make_bench_rag_prompts_c.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "scripts" / "bench_rag_prompts_c.json"

# Trois projets qui tournent deja, decrits par leurs #include.
PROJETS = {
    "bme280": ["Wire.h", "Adafruit_Sensor.h", "Adafruit_BME280.h"],
    "ds18b20": ["OneWire.h", "DallasTemperature.h"],
    "servo": ["Servo.h"],
}

# (projet, bande, expect, {langue: prompt})
CAS = [
    ("bme280", "unit_change", [], {
        "fr": "finalement affiche la temperature en degres Celsius au lieu de Fahrenheit",
        "en": "actually show the temperature in Celsius instead of Fahrenheit",
        "es": "muestra la temperatura en Celsius en lugar de Fahrenheit",
        "it": "mostra la temperatura in Celsius invece che in Fahrenheit"}),
    ("ds18b20", "unit_change", [], {
        "fr": "arrondis la temperature a un chiffre apres la virgule",
        "en": "round the temperature to one decimal place",
        "es": "redondea la temperatura a un decimal",
        "it": "arrotonda la temperatura a un decimale"}),
    ("bme280", "behaviour", [], {
        "fr": "change la frequence de mesure pour une fois par seconde",
        "en": "change the measurement rate to once per second",
        "es": "cambia la frecuencia de medicion a una vez por segundo",
        "it": "cambia la frequenza di misura a una volta al secondo"}),
    ("servo", "behaviour", [], {
        "fr": "ralentis le mouvement du servomoteur",
        "en": "slow down the servo movement",
        "es": "ralentiza el movimiento del servo",
        "it": "rallenta il movimento del servo"}),
    ("bme280", "add_unnamed", ["adafruit-ssd1306", "sh1106", "liquidcrystal-i2c"], {
        "fr": "ajoute un ecran OLED pour afficher la valeur",
        "en": "add an OLED screen to show the value",
        "es": "anade una pantalla OLED para mostrar el valor",
        "it": "aggiungi uno schermo OLED per mostrare il valore"}),
    ("servo", "add_unnamed", ["newping"], {
        "fr": "ajoute un capteur de distance a ultrasons",
        "en": "add an ultrasonic distance sensor",
        "es": "anade un sensor de distancia por ultrasonidos",
        "it": "aggiungi un sensore di distanza a ultrasuoni"}),
    ("bme280", "add_named", ["adafruit-ssd1306"], {
        "fr": "ajoute un ecran OLED SSD1306 pour afficher la valeur",
        "en": "add an SSD1306 OLED screen to show the value",
        "es": "anade una pantalla OLED SSD1306 para mostrar el valor",
        "it": "aggiungi uno schermo OLED SSD1306 per mostrare il valore"}),
    ("servo", "add_named", ["dht-sensor-library"], {
        "fr": "ajoute un capteur DHT22 pour lire l'humidite",
        "en": "add a DHT22 sensor to read the humidity",
        "es": "anade un sensor DHT22 para leer la humedad",
        "it": "aggiungi un sensore DHT22 per leggere l'umidita"}),
    ("bme280", "replace_named", ["dallas-temperature"], {
        "fr": "finalement lis la temperature avec un DS18B20",
        "en": "actually read the temperature with a DS18B20",
        "es": "lee la temperatura con un DS18B20 en su lugar",
        "it": "leggi invece la temperatura con un DS18B20"}),
    ("servo", "replace_named", ["stepper_28byj48", "accelstepper"], {
        "fr": "remplace le servomoteur par un moteur pas a pas 28BYJ-48",
        "en": "replace the servo with a 28BYJ-48 stepper motor",
        "es": "sustituye el servo por un motor paso a paso 28BYJ-48",
        "it": "sostituisci il servo con un motore passo passo 28BYJ-48"}),
]


def main() -> int:
    from ui.rag import all_corpus_entries
    ids = {e.get("id") for e in all_corpus_entries()}

    cases, inconnus = [], []
    for projet, bande, expect, prompts in CAS:
        # `expect` est une LISTE d'alternatives acceptables : « un ecran OLED »
        # est bien servi par n'importe lequel des ecrans du corpus. On valide
        # chaque id, mais un seul suffira a rendre le cas correct.
        for e in expect:
            if e not in ids:
                inconnus.append((bande, e))
        for lang, prompt in prompts.items():
            cases.append({
                "prompt": prompt,
                "lang": lang,
                "band": bande,
                "expect": expect,
                "project": projet,
                "project_headers": PROJETS[projet],
                "added": "2026-08-26",
                "source": "TODO #64 -- prompts de suite",
            })

    if inconnus:
        print("ERREUR : `expect` inconnus du corpus -- une batterie qui attend "
              "un id inexistant ne peut RIEN prouver :", file=sys.stderr)
        for b, e in inconnus:
            print(f"   [{b}] {e}", file=sys.stderr)
        return 2

    OUT.write_text(json.dumps(cases, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    from collections import Counter
    par_bande = Counter(c["band"] for c in cases)
    print(f"ecrit {OUT.name} : {len(cases)} cas")
    for b, n in par_bande.items():
        print(f"   {b:15s} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

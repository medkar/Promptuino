"""Multilingual smoke-test for retrieve_libs() — FR / EN / ES / IT.

Each entry: (prompt, language, expected_corpus_id_substring).
Top-1 match is correct if the expected substring appears in the top result's id.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui.rag import retrieve_libs  # noqa: E402

# (prompt, lang, expected_id_substring)
CASES: list[tuple[str, str, str]] = [
    # --- French (32 prompts, one per corpus entry) ---
    ("capteur de couleur RGB", "FR", "tcs34725"),
    ("gerer un appui long et un double clic sur un bouton", "FR", "onebutton"),
    ("afficher du texte sur un LCD 16x2", "FR", "liquidcrystal"),
    ("afficher sur un ecran OLED", "FR", "ssd1306"),
    ("lire la temperature et l'humidite avec un DHT22", "FR", "dht"),
    ("controler une bande de LED RGB WS2812", "FR", "neopixel"),
    ("piloter un servomoteur", "FR", "servo"),
    ("parser du JSON", "FR", "arduinojson"),
    ("mesurer une distance avec un capteur ultrason", "FR", "newping"),
    ("lire un capteur de pression et temperature BME280", "FR", "bme280"),
    ("lire un accelerometre MPU6050", "FR", "mpu6050"),
    ("piloter un moteur pas a pas", "FR", "stepper"),
    ("moteur pas a pas avec rampe d'acceleration", "FR", "accelstepper"),
    ("recevoir un signal de telecommande infrarouge", "FR", "irremote"),
    ("recuperer l'heure depuis internet via NTP", "FR", "ntpclient"),
    ("lire la temperature avec une sonde DS18B20", "FR", "dallas"),
    ("communiquer sur le bus 1-Wire", "FR", "onewire"),
    ("publier sur un broker MQTT", "FR", "pubsub"),
    ("lire l'horloge temps reel DS3231", "FR", "rtclib"),
    ("lire un encodeur rotatif", "FR", "encoder"),
    ("ecrire des donnees sur une carte SD", "FR", "sd"),
    ("sauvegarder une valeur dans l'EEPROM", "FR", "eeprom"),
    ("communication serie logicielle softwareserial", "FR", "softwareserial"),
    ("mesurer la luminosite avec un BH1750", "FR", "bh1750"),
    ("piloter deux moteurs DC avec un shield Adafruit", "FR", "motorshield"),
    ("detecter un mouvement avec un capteur PIR", "FR", "pir"),
    ("lire un badge RFID avec MFRC522", "FR", "mfrc522"),
    ("lire la position GPS avec un NEO-6M", "FR", "tinygps"),
    ("afficher du texte couleur sur un ecran TFT 240x320", "FR", "ili9341"),
    ("lire un clavier matriciel 4x4", "FR", "keypad"),
    ("piloter deux moteurs DC avec TB6612FNG", "FR", "tb6612"),
    ("piloter un moteur DC avec L298N", "FR", "l298n"),
    ("mesurer la qualite de l'air avec un capteur MQ-135", "FR", "mq135"),
    ("mesurer le CO2 interieur avec un CCS811", "FR", "ccs811"),
    ("lire un capteur de CO2 NDIR MH-Z19", "FR", "mhz19"),
    ("envoyer un paquet LoRa longue portee", "FR", "lora"),
    ("piloter deux moteurs DC avec un DRV8833", "FR", "drv8833"),
    ("piloter un moteur DC avec un L293D", "FR", "l293d"),

    # --- English (38 prompts, one per corpus entry) ---
    ("RGB color sensor", "EN", "tcs34725"),
    ("handle long press and double click on a button", "EN", "onebutton"),
    ("display text on a 16x2 LCD", "EN", "liquidcrystal"),
    ("show text on an OLED screen", "EN", "ssd1306"),
    ("read DHT22 temperature and humidity", "EN", "dht"),
    ("control a WS2812 LED strip", "EN", "neopixel"),
    ("control a servo motor", "EN", "servo"),
    ("parse JSON on Arduino", "EN", "arduinojson"),
    ("ultrasonic distance sensor", "EN", "newping"),
    ("read BME280 pressure and temperature sensor", "EN", "bme280"),
    ("read MPU6050 accelerometer", "EN", "mpu6050"),
    ("drive a stepper motor", "EN", "stepper"),
    ("stepper motor with acceleration ramp", "EN", "accelstepper"),
    ("receive an infrared remote control signal", "EN", "irremote"),
    ("get time from internet via NTP", "EN", "ntpclient"),
    ("read temperature with a DS18B20 probe", "EN", "dallas"),
    ("communicate on the 1-Wire bus", "EN", "onewire"),
    ("MQTT client", "EN", "pubsub"),
    ("real time clock DS3231", "EN", "rtclib"),
    ("rotary encoder", "EN", "encoder"),
    ("write data to SD card", "EN", "sd"),
    ("save a value to EEPROM", "EN", "eeprom"),
    ("software serial communication", "EN", "softwareserial"),
    ("measure ambient light with BH1750", "EN", "bh1750"),
    ("drive two DC motors with an Adafruit shield", "EN", "motorshield"),
    ("detect motion with a PIR sensor", "EN", "pir"),
    ("read an RFID badge with MFRC522", "EN", "mfrc522"),
    ("read GPS position from a NEO-6M module", "EN", "tinygps"),
    ("display color text on a 240x320 TFT screen", "EN", "ili9341"),
    ("read a 4x4 matrix keypad", "EN", "keypad"),
    ("drive two DC motors with TB6612FNG", "EN", "tb6612"),
    ("drive a DC motor with L298N", "EN", "l298n"),
    ("measure air quality with an MQ-135 sensor", "EN", "mq135"),
    ("measure indoor CO2 and TVOC with CCS811", "EN", "ccs811"),
    ("read NDIR CO2 sensor MH-Z19", "EN", "mhz19"),
    ("send a long range LoRa packet", "EN", "lora"),
    ("drive two DC motors with a DRV8833", "EN", "drv8833"),
    ("drive a DC motor with an L293D", "EN", "l293d"),

    # --- Spanish (38 prompts, one per corpus entry) ---
    ("sensor de color RGB", "ES", "tcs34725"),
    ("gestionar pulsacion larga y doble clic en un boton", "ES", "onebutton"),
    ("mostrar texto en una pantalla LCD 16x2", "ES", "liquidcrystal"),
    ("mostrar en una pantalla OLED", "ES", "ssd1306"),
    ("leer temperatura y humedad con DHT22", "ES", "dht"),
    ("controlar una tira de LED RGB WS2812", "ES", "neopixel"),
    ("controlar un servomotor", "ES", "servo"),
    ("parsear JSON", "ES", "arduinojson"),
    ("medir distancia con sensor ultrasonico", "ES", "newping"),
    ("leer sensor de presion y temperatura BME280", "ES", "bme280"),
    ("leer acelerometro MPU6050", "ES", "mpu6050"),
    ("controlar un motor paso a paso", "ES", "stepper"),
    ("motor paso a paso con rampa de aceleracion", "ES", "accelstepper"),
    ("recibir senal de mando a distancia infrarrojo", "ES", "irremote"),
    ("obtener hora desde internet por NTP", "ES", "ntpclient"),
    ("leer temperatura con una sonda DS18B20", "ES", "dallas"),
    ("comunicar en el bus 1-Wire", "ES", "onewire"),
    ("publicar en un broker MQTT", "ES", "pubsub"),
    ("leer reloj en tiempo real DS3231", "ES", "rtclib"),
    ("leer un codificador rotatorio", "ES", "encoder"),
    ("escribir datos en una tarjeta SD", "ES", "sd"),
    ("guardar un valor en la EEPROM", "ES", "eeprom"),
    ("comunicacion serie por software softwareserial", "ES", "softwareserial"),
    ("medir luminosidad con BH1750", "ES", "bh1750"),
    ("controlar dos motores DC con un shield Adafruit", "ES", "motorshield"),
    ("detectar movimiento con un sensor PIR", "ES", "pir"),
    ("leer una tarjeta RFID con MFRC522", "ES", "mfrc522"),
    ("leer posicion GPS con un modulo NEO-6M", "ES", "tinygps"),
    ("mostrar texto en color en una pantalla TFT 240x320", "ES", "ili9341"),
    ("leer un teclado matricial 4x4", "ES", "keypad"),
    ("controlar dos motores DC con TB6612FNG", "ES", "tb6612"),
    ("controlar un motor DC con L298N", "ES", "l298n"),
    ("medir calidad del aire con un sensor MQ-135", "ES", "mq135"),
    ("medir CO2 interior y COV con CCS811", "ES", "ccs811"),
    ("leer sensor de CO2 NDIR MH-Z19", "ES", "mhz19"),
    ("enviar un paquete LoRa de larga distancia", "ES", "lora"),
    ("controlar dos motores DC con un DRV8833", "ES", "drv8833"),
    ("controlar un motor DC con un L293D", "ES", "l293d"),

    # --- Italian (38 prompts, one per corpus entry) ---
    ("sensore di colore RGB", "IT", "tcs34725"),
    ("gestire pressione lunga e doppio clic su un pulsante", "IT", "onebutton"),
    ("mostrare testo su un display LCD 16x2", "IT", "liquidcrystal"),
    ("mostrare su uno schermo OLED", "IT", "ssd1306"),
    ("leggere temperatura e umidita con DHT22", "IT", "dht"),
    ("controllare una striscia di LED RGB WS2812", "IT", "neopixel"),
    ("controllare un servomotore", "IT", "servo"),
    ("analizzare JSON", "IT", "arduinojson"),
    ("misurare distanza con sensore ultrasuoni", "IT", "newping"),
    ("leggere sensore di pressione e temperatura BME280", "IT", "bme280"),
    ("leggere accelerometro MPU6050", "IT", "mpu6050"),
    ("controllare un motore passo passo", "IT", "stepper"),
    ("motore passo passo con rampa di accelerazione", "IT", "accelstepper"),
    ("ricevere segnale di telecomando infrarosso", "IT", "irremote"),
    ("ottenere ora da internet via NTP", "IT", "ntpclient"),
    ("leggere temperatura con una sonda DS18B20", "IT", "dallas"),
    ("comunicare sul bus 1-Wire", "IT", "onewire"),
    ("pubblicare su un broker MQTT", "IT", "pubsub"),
    ("leggere orologio in tempo reale DS3231", "IT", "rtclib"),
    ("leggere un encoder rotativo", "IT", "encoder"),
    ("scrivere dati su una scheda SD", "IT", "sd"),
    ("salvare un valore nella EEPROM", "IT", "eeprom"),
    ("comunicazione seriale software softwareserial", "IT", "softwareserial"),
    ("misurare luminosita con BH1750", "IT", "bh1750"),
    ("controllare due motori DC con uno shield Adafruit", "IT", "motorshield"),
    ("rilevare movimento con un sensore PIR", "IT", "pir"),
    ("leggere una tessera RFID con MFRC522", "IT", "mfrc522"),
    ("leggere posizione GPS con un modulo NEO-6M", "IT", "tinygps"),
    ("mostrare testo a colori su schermo TFT 240x320", "IT", "ili9341"),
    ("leggere una tastiera matriciale 4x4", "IT", "keypad"),
    ("controllare due motori DC con TB6612FNG", "IT", "tb6612"),
    ("controllare un motore DC con L298N", "IT", "l298n"),
    ("misurare la qualita dell'aria con un sensore MQ-135", "IT", "mq135"),
    ("misurare CO2 interno e COV con CCS811", "IT", "ccs811"),
    ("leggere sensore di CO2 NDIR MH-Z19", "IT", "mhz19"),
    ("inviare un pacchetto LoRa a lunga distanza", "IT", "lora"),
    ("controllare due motori DC con un DRV8833", "IT", "drv8833"),
    ("controllare un motore DC con un L293D", "IT", "l293d"),
]


def main() -> int:
    by_lang: dict[str, list[bool]] = {}
    failures: list[tuple[str, str, str, str]] = []

    for prompt, lang, expected in CASES:
        libs = retrieve_libs(prompt, k=3, threshold=0.0)
        top_id = libs[0].get("id", "") if libs else ""
        ok = expected.lower() in top_id.lower()
        by_lang.setdefault(lang, []).append(ok)
        marker = "OK " if ok else "FAIL"
        score = f"{libs[0]['_score']:.3f}" if libs else "  -  "
        print(f"[{marker}] [{lang}] {score}  {prompt!r}")
        if libs:
            print(f"         -> {top_id}  (expected substring: {expected!r})")
        if not ok:
            failures.append((lang, prompt, expected, top_id))

    print("\n=== Summary ===")
    total_ok = 0
    total = 0
    for lang in ("FR", "EN", "ES", "IT"):
        results = by_lang.get(lang, [])
        if not results:
            continue
        ok = sum(results)
        total_ok += ok
        total += len(results)
        print(f"  {lang}: {ok}/{len(results)}")
    print(f"  TOTAL: {total_ok}/{total}")

    if failures:
        print("\n=== Failures ===")
        for lang, prompt, expected, got in failures:
            print(f"  [{lang}] {prompt!r}")
            print(f"         expected ~{expected!r}, got {got!r}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

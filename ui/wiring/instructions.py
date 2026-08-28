"""Generation of wiring instructions in markdown (MVP3).

Modes:
  - `simple`   : one step per component, short sentence.
  - `detailed` : same step + pedagogical justification.

Languages: FR (default), EN, ES, IT. The warnings emitted by
`inference.py`/`markers.py` carry a `code` + `params` that allow
i18n on the rendering side (the `message` field is no longer consulted).
"""
from __future__ import annotations

from .netlist import (
    Component, Netlist, SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO,
)


_LANGS = ("fr", "en", "es", "it")


# ─── i18n of type labels ──────────────────────────────────────────
_TYPE_LABEL: dict[str, dict[str, str]] = {
    "led":            {"fr": "LED",                       "en": "LED",
                       "es": "LED",                       "it": "LED"},
    "resistor":       {"fr": "résistance",                "en": "resistor",
                       "es": "resistencia",               "it": "resistenza"},
    "button":         {"fr": "bouton-poussoir",           "en": "push-button",
                       "es": "pulsador",                  "it": "pulsante"},
    "potentiometer":  {"fr": "potentiomètre",             "en": "potentiometer",
                       "es": "potenciómetro",             "it": "potenziometro"},
    "buzzer":         {"fr": "buzzer",                    "en": "buzzer",
                       "es": "zumbador",                  "it": "cicalino"},
    "servo":          {"fr": "servomoteur",               "en": "servo motor",
                       "es": "servomotor",                "it": "servomotore"},
    "dht22":          {"fr": "capteur DHT22",             "en": "DHT22 sensor",
                       "es": "sensor DHT22",              "it": "sensore DHT22"},
    "dht11":          {"fr": "capteur DHT11",             "en": "DHT11 sensor",
                       "es": "sensor DHT11",              "it": "sensore DHT11"},
    "hcsr04":         {"fr": "capteur ultrason HC-SR04",  "en": "HC-SR04 ultrasonic sensor",
                       "es": "sensor ultrasónico HC-SR04","it": "sensore a ultrasuoni HC-SR04"},
    "led_matrix":     {"fr": "afficheur matrice LED (MAX7219)",
                       "en": "LED matrix display (MAX7219)",
                       "es": "matriz LED (MAX7219)",
                       "it": "display a matrice LED (MAX7219)"},
    "tm1637":         {"fr": "afficheur 7-segments (TM1637)",
                       "en": "7-segment display (TM1637)",
                       "es": "display 7 segmentos (TM1637)",
                       "it": "display a 7 segmenti (TM1637)"},
    "ht16k33":        {"fr": "matrice LED I2C (HT16K33)",
                       "en": "I2C LED matrix (HT16K33)",
                       "es": "matriz LED I2C (HT16K33)",
                       "it": "matrice LED I2C (HT16K33)"},
    "vl53l0x":        {"fr": "capteur de distance laser (VL53L0X)",
                       "en": "laser distance sensor (VL53L0X)",
                       "es": "sensor de distancia láser (VL53L0X)",
                       "it": "sensore di distanza laser (VL53L0X)"},
    "max30102":       {"fr": "capteur cardiaque/SpO2 (MAX30102)",
                       "en": "heart-rate/SpO2 sensor (MAX30102)",
                       "es": "sensor de pulso/SpO2 (MAX30102)",
                       "it": "sensore battito/SpO2 (MAX30102)"},
    "tcs34725":       {"fr": "capteur de couleur (TCS34725)",
                       "en": "color sensor (TCS34725)",
                       "es": "sensor de color (TCS34725)",
                       "it": "sensore di colore (TCS34725)"},
    "bh1750":         {"fr": "luxmètre (BH1750)",
                       "en": "lux / light meter (BH1750)",
                       "es": "luxómetro (BH1750)",
                       "it": "luxmetro (BH1750)"},
    "ads1115":        {"fr": "convertisseur ADC 16 bits (ADS1115)",
                       "en": "16-bit ADC (ADS1115)",
                       "es": "convertidor ADC 16 bits (ADS1115)",
                       "it": "convertitore ADC 16 bit (ADS1115)"},
    "pca9685":        {"fr": "driver 16 servos/PWM (PCA9685)",
                       "en": "16-channel PWM/servo driver (PCA9685)",
                       "es": "driver de 16 servos/PWM (PCA9685)",
                       "it": "driver 16 servo/PWM (PCA9685)"},
    "sh1106":         {"fr": "écran OLED (SH1106)",
                       "en": "OLED display (SH1106)",
                       "es": "pantalla OLED (SH1106)",
                       "it": "display OLED (SH1106)"},
    "aht20":          {"fr": "capteur température/humidité (AHT20)",
                       "en": "temperature/humidity sensor (AHT20)",
                       "es": "sensor temperatura/humedad (AHT20)",
                       "it": "sensore temperatura/umidità (AHT20)"},
    "bmp280":   {"fr": "capteur de pression/altitude (BMP280)",
                 "en": "pressure/altitude sensor (BMP280)",
                 "es": "sensor de presión/altitud (BMP280)",
                 "it": "sensore di pressione/altitudine (BMP280)"},
    "apds9960": {"fr": "capteur de geste/proximité (APDS9960)",
                 "en": "gesture/proximity sensor (APDS9960)",
                 "es": "sensor de gestos/proximidad (APDS9960)",
                 "it": "sensore di gesti/prossimità (APDS9960)"},
    "mlx90614": {"fr": "thermomètre infrarouge (MLX90614)",
                 "en": "infrared thermometer (MLX90614)",
                 "es": "termómetro infrarrojo (MLX90614)",
                 "it": "termometro a infrarossi (MLX90614)"},
    "sgp30":    {"fr": "capteur de qualité d'air COV (SGP30)",
                 "en": "air quality VOC sensor (SGP30)",
                 "es": "sensor de calidad del aire COV (SGP30)",
                 "it": "sensore di qualità dell'aria COV (SGP30)"},
    "scd30":    {"fr": "capteur de CO₂ (SCD30)",
                 "en": "CO2 sensor (SCD30)",
                 "es": "sensor de CO₂ (SCD30)",
                 "it": "sensore di CO₂ (SCD30)"},
    "pn532":    {"fr": "lecteur NFC/RFID (PN532)",
                 "en": "NFC/RFID reader (PN532)",
                 "es": "lector NFC/RFID (PN532)",
                 "it": "lettore NFC/RFID (PN532)"},
    "pcf8574":  {"fr": "expandeur d'E/S I2C (PCF8574)",
                 "en": "I2C I/O expander (PCF8574)",
                 "es": "expansor de E/S I2C (PCF8574)",
                 "it": "espansore di I/O I2C (PCF8574)"},
    "mcp23017": {"fr": "expandeur d'E/S 16 bits (MCP23017)",
                 "en": "16-bit I/O expander (MCP23017)",
                 "es": "expansor de E/S de 16 bits (MCP23017)",
                 "it": "espansore di I/O a 16 bit (MCP23017)"},
    "max6675":  {"fr": "thermocouple SPI (MAX6675)",
                 "en": "thermocouple amplifier (MAX6675)",
                 "es": "termopar SPI (MAX6675)",
                 "it": "termocoppia SPI (MAX6675)"},
    "mcp9808":  {"fr": "capteur de température précis (MCP9808)",
                 "en": "precision temperature sensor (MCP9808)",
                 "es": "sensor de temperatura de precisión (MCP9808)",
                 "it": "sensore di temperatura di precisione (MCP9808)"},
    "si7021":   {"fr": "capteur température/humidité (Si7021)",
                 "en": "temperature/humidity sensor (Si7021)",
                 "es": "sensor de temperatura/humedad (Si7021)",
                 "it": "sensore di temperatura/umidità (Si7021)"},
    "adxl345":  {"fr": "accéléromètre 3 axes (ADXL345)",
                 "en": "3-axis accelerometer (ADXL345)",
                 "es": "acelerómetro de 3 ejes (ADXL345)",
                 "it": "accelerometro a 3 assi (ADXL345)"},
    # Ajoutés avec leur brochage le 2026-08-19 : devenir dessinable veut dire
    # que le câblage NOMME le composant dans ses instructions, et sans entrée
    # ici `_label` retombe sur le slug brut (« bmp085 »). Leur libellé de FICHE
    # venait déjà de `replacement_catalog.label_of` — c'est le libellé
    # d'INSTRUCTIONS qui manquait, et il ne manquait pas tant qu'on ne les
    # dessinait pas.
    "bmp085":   {"fr": "capteur de pression (BMP085)",
                 "en": "pressure sensor (BMP085)",
                 "es": "sensor de presión (BMP085)",
                 "it": "sensore di pressione (BMP085)"},
    "hmc5883":  {"fr": "magnétomètre/boussole (HMC5883L)",
                 "en": "magnetometer/compass (HMC5883L)",
                 "es": "magnetómetro/brújula (HMC5883L)",
                 "it": "magnetometro/bussola (HMC5883L)"},
    "hmc5883l": {"fr": "magnétomètre/boussole (HMC5883L)",
                 "en": "magnetometer/compass (HMC5883L)",
                 "es": "magnetómetro/brújula (HMC5883L)",
                 "it": "magnetometro/bussola (HMC5883L)"},
    "mcp4725":  {"fr": "convertisseur numérique-analogique (MCP4725)",
                 "en": "digital-to-analog converter (MCP4725)",
                 "es": "convertidor digital-analógico (MCP4725)",
                 "it": "convertitore digitale-analogico (MCP4725)"},
    "ina260":   {"fr": "wattmètre tension/courant (INA260)",
                 "en": "voltage/current power monitor (INA260)",
                 "es": "monitor de tensión/corriente (INA260)",
                 "it": "monitor di tensione/corrente (INA260)"},
    "as5600":   {"fr": "capteur d'angle magnétique (AS5600)",
                 "en": "magnetic angle sensor (AS5600)",
                 "es": "sensor de ángulo magnético (AS5600)",
                 "it": "sensore di angolo magnetico (AS5600)"},
    "veml6075": {"fr": "capteur UV (VEML6075)",
                 "en": "UV sensor (VEML6075)",
                 "es": "sensor UV (VEML6075)",
                 "it": "sensore UV (VEML6075)"},
    "nrf24l01": {"fr": "module radio 2.4 GHz (nRF24L01)",
                 "en": "2.4 GHz radio module (nRF24L01)",
                 "es": "módulo de radio 2.4 GHz (nRF24L01)",
                 "it": "modulo radio 2.4 GHz (nRF24L01)"},
    "fingerprint": {"fr": "capteur d'empreinte digitale",
                    "en": "fingerprint sensor",
                    "es": "sensor de huella dactilar",
                    "it": "sensore di impronte digitali"},
    "drv2605":  {"fr": "driver de vibration haptique (DRV2605)",
                 "en": "haptic motor driver (DRV2605)",
                 "es": "driver de vibración háptica (DRV2605)",
                 "it": "driver di vibrazione aptica (DRV2605)"},
    "tm1638":   {"fr": "module afficheur + boutons (TM1638)",
                 "en": "display + buttons module (TM1638)",
                 "es": "módulo de pantalla + botones (TM1638)",
                 "it": "modulo display + pulsanti (TM1638)"},
    "pcd8544":  {"fr": "écran LCD Nokia 5110 (PCD8544)",
                 "en": "Nokia 5110 LCD (PCD8544)",
                 "es": "pantalla LCD Nokia 5110 (PCD8544)",
                 "it": "display LCD Nokia 5110 (PCD8544)"},
    "ssd1351":  {"fr": "écran OLED couleur (SSD1351)",
                 "en": "color OLED display (SSD1351)",
                 "es": "pantalla OLED a color (SSD1351)",
                 "it": "display OLED a colori (SSD1351)"},
    "bno055":   {"fr": "centrale inertielle 9 axes (BNO055)",
                 "en": "9-DOF IMU (BNO055)",
                 "es": "IMU de 9 ejes (BNO055)",
                 "it": "IMU a 9 assi (BNO055)"},
    "hw-612":   {"fr": "HW-612 (centrale inertielle 10-DOF)",
                 "en": "HW-612 (10-DOF IMU)",
                 "es": "HW-612 (IMU 10-DOF)",
                 "it": "HW-612 (IMU 10-DOF)"},
    "gy-80":    {"fr": "GY-80 (centrale inertielle 10-DOF)",
                 "en": "GY-80 (10-DOF IMU)",
                 "es": "GY-80 (IMU 10-DOF)",
                 "it": "GY-80 (IMU 10-DOF)"},
    "gy-85":    {"fr": "GY-85 (centrale inertielle 9-DOF)",
                 "en": "GY-85 (9-DOF IMU)",
                 "es": "GY-85 (IMU 9-DOF)",
                 "it": "GY-85 (IMU 9-DOF)"},
    # ── Ajoutes le 2026-08-26 (TODO #57) ────────────────────────────────
    # Le GY-87 est aussi vendu sous la serigraphie HW-290 : le libelle nomme
    # les deux, parce que l'utilisateur lit ce qui est ecrit sur SA carte.
    "gy-87":    {"fr": "GY-87 / HW-290 (centrale inertielle 10-DOF)",
                 "en": "GY-87 / HW-290 (10-DOF IMU)",
                 "es": "GY-87 / HW-290 (IMU 10-DOF)",
                 "it": "GY-87 / HW-290 (IMU 10-DOF)"},
    "gy-86":    {"fr": "GY-86 (centrale inertielle 10-DOF)",
                 "en": "GY-86 (10-DOF IMU)",
                 "es": "GY-86 (IMU 10-DOF)",
                 "it": "GY-86 (IMU 10-DOF)"},
    "ms5611":   {"fr": "baromètre MS5611",
                 "en": "MS5611 barometer",
                 "es": "barómetro MS5611",
                 "it": "barometro MS5611"},
    # ── Lot Fritzing #2 du 2026-08-19 (memes composants que le catalogue) ────
    "acs712":   {"fr": 'capteur de courant (ACS712)',
                 "en": 'current sensor (ACS712)',
                 "es": 'sensor de corriente (ACS712)',
                 "it": 'sensore di corrente (ACS712)'},
    "adjd_s311": {"fr": 'capteur de couleur (ADJD-S311)',
                 "en": 'color sensor (ADJD-S311)',
                 "es": 'sensor de color (ADJD-S311)',
                 "it": 'sensore di colore (ADJD-S311)'},
    "bmp180":   {"fr": 'capteur de pression (BMP180)',
                 "en": 'pressure sensor (BMP180)',
                 "es": 'sensor de presión (BMP180)',
                 "it": 'sensore di pressione (BMP180)'},
    "ds3234":   {"fr": 'horloge RTC SPI (DS3234)',
                 "en": 'SPI RTC clock (DS3234)',
                 "es": 'reloj RTC SPI (DS3234)',
                 "it": 'orologio RTC SPI (DS3234)'},
    "force_sensor": {"fr": 'capteur de force (FSR)',
                 "en": 'force sensor (FSR)',
                 "es": 'sensor de fuerza (FSR)',
                 "it": 'sensore di forza (FSR)'},
    "ftdi_basic": {"fr": 'adaptateur USB-série (FTDI)',
                 "en": 'USB-serial adapter (FTDI)',
                 "es": 'adaptador USB-serie (FTDI)',
                 "it": 'adattatore USB-seriale (FTDI)'},
    "grove_oled_128x96": {"fr": 'écran OLED Grove 128x96',
                 "en": 'Grove OLED display 128x96',
                 "es": 'pantalla OLED Grove 128x96',
                 "it": 'display OLED Grove 128x96'},
    "hc05":     {"fr": 'module Bluetooth (HC-05)',
                 "en": 'Bluetooth module (HC-05)',
                 "es": 'módulo Bluetooth (HC-05)',
                 "it": 'modulo Bluetooth (HC-05)'},
    "hmc6352":  {"fr": 'boussole numérique (HMC6352)',
                 "en": 'digital compass (HMC6352)',
                 "es": 'brújula digital (HMC6352)',
                 "it": 'bussola digitale (HMC6352)'},
    "itg3200":  {"fr": 'gyroscope 3 axes (ITG-3200)',
                 "en": '3-axis gyroscope (ITG-3200)',
                 "es": 'giroscopio 3 ejes (ITG-3200)',
                 "it": 'giroscopio 3 assi (ITG-3200)'},
    "joystick": {"fr": 'joystick analogique',
                 "en": 'analog joystick',
                 "es": 'joystick analógico',
                 "it": 'joystick analogico'},
    "l3g4200d": {"fr": 'gyroscope 3 axes (L3G4200D)',
                 "en": '3-axis gyroscope (L3G4200D)',
                 "es": 'giroscopio 3 ejes (L3G4200D)',
                 "it": 'giroscopio 3 assi (L3G4200D)'},
    "light_sensor": {"fr": 'capteur de luminosité',
                 "en": 'light sensor',
                 "es": 'sensor de luz',
                 "it": 'sensore di luce'},
    "load_cell": {"fr": 'jauge de contrainte (load cell)',
                 "en": 'load cell',
                 "es": 'célula de carga',
                 "it": 'cella di carico'},
    "lsm303":   {"fr": 'boussole/accéléromètre (LSM303)',
                 "en": 'compass/accelerometer (LSM303)',
                 "es": 'brújula/acelerómetro (LSM303)',
                 "it": 'bussola/accelerometro (LSM303)'},
    "mag3110":  {"fr": 'magnétomètre (MAG3110)',
                 "en": 'magnetometer (MAG3110)',
                 "es": 'magnetómetro (MAG3110)',
                 "it": 'magnetometro (MAG3110)'},
    "max1704x": {"fr": 'jauge de batterie (MAX1704X)',
                 "en": 'battery gauge (MAX1704X)',
                 "es": 'medidor de batería (MAX1704X)',
                 "it": 'indicatore di batteria (MAX1704X)'},
    "mcp41xxx": {"fr": 'potentiomètre numérique (MCP41xxx)',
                 "en": 'digital potentiometer (MCP41xxx)',
                 "es": 'potenciómetro digital (MCP41xxx)',
                 "it": 'potenziometro digitale (MCP41xxx)'},
    "mcp42xxx": {"fr": 'potentiomètre numérique double (MCP42xxx)',
                 "en": 'dual digital potentiometer (MCP42xxx)',
                 "es": 'potenciómetro digital doble (MCP42xxx)',
                 "it": 'doppio potenziometro digitale (MCP42xxx)'},
    "mma8452q": {"fr": 'accéléromètre 3 axes (MMA8452Q)',
                 "en": '3-axis accelerometer (MMA8452Q)',
                 "es": 'acelerómetro 3 ejes (MMA8452Q)',
                 "it": 'accelerometro 3 assi (MMA8452Q)'},
    "mpl3115a2": {"fr": "capteur d'altitude/pression (MPL3115A2)",
                 "en": 'altitude/pressure sensor (MPL3115A2)',
                 "es": 'sensor de altitud/presión (MPL3115A2)',
                 "it": 'sensore di altitudine/pressione (MPL3115A2)'},
    "mpr121":   {"fr": 'capteur tactile capacitif (MPR121)',
                 "en": 'capacitive touch sensor (MPR121)',
                 "es": 'sensor táctil capacitivo (MPR121)',
                 "it": 'sensore touch capacitivo (MPR121)'},
    "reed_switch": {"fr": 'interrupteur ILS (reed)',
                 "en": 'reed switch',
                 "es": 'interruptor de láminas (reed)',
                 "it": 'interruttore reed'},
    "sht15":    {"fr": "capteur d'humidité (SHT15)",
                 "en": 'humidity sensor (SHT15)',
                 "es": 'sensor de humedad (SHT15)',
                 "it": 'sensore di umidità (SHT15)'},
    "sht25":    {"fr": "capteur d'humidité (SHT25)",
                 "en": 'humidity sensor (SHT25)',
                 "es": 'sensor de humedad (SHT25)',
                 "it": 'sensore di umidità (SHT25)'},
    "slide_switch": {"fr": 'interrupteur à glissière',
                 "en": 'slide switch',
                 "es": 'interruptor deslizante',
                 "it": 'interruttore a slitta'},
    "slider":   {"fr": 'potentiomètre à glissière',
                 "en": 'slide potentiometer',
                 "es": 'potenciómetro deslizante',
                 "it": 'potenziometro a slitta'},
    "soil_moisture": {"fr": "capteur d'humidité du sol",
                 "en": 'soil moisture sensor',
                 "es": 'sensor de humedad del suelo',
                 "it": 'sensore di umidità del suolo'},
    "solenoid": {"fr": 'électrovanne/solénoïde',
                 "en": 'solenoid',
                 "es": 'solenoide',
                 "it": 'solenoide'},
    "speaker":  {"fr": 'haut-parleur',
                 "en": 'speaker',
                 "es": 'altavoz',
                 "it": 'altoparlante'},
    "thermal_printer": {"fr": 'imprimante thermique',
                 "en": 'thermal printer',
                 "es": 'impresora térmica',
                 "it": 'stampante termica'},
    "tilt_switch": {"fr": "interrupteur d'inclinaison",
                 "en": 'tilt switch',
                 "es": 'interruptor de inclinación',
                 "it": 'interruttore di inclinazione'},
    "tmp102":   {"fr": 'capteur de température (TMP102)',
                 "en": 'temperature sensor (TMP102)',
                 "es": 'sensor de temperatura (TMP102)',
                 "it": 'sensore di temperatura (TMP102)'},
    "toggle_switch": {"fr": 'interrupteur à bascule',
                 "en": 'toggle switch',
                 "es": 'interruptor basculante',
                 "it": 'interruttore a levetta'},
    "us100":    {"fr": 'capteur de distance ultrason (US-100)',
                 "en": 'ultrasonic distance sensor (US-100)',
                 "es": 'sensor de distancia ultrasónico (US-100)',
                 "it": 'sensore di distanza a ultrasuoni (US-100)'},
    "vcnl4000": {"fr": 'capteur de proximité (VCNL4000)',
                 "en": 'proximity sensor (VCNL4000)',
                 "es": 'sensor de proximidad (VCNL4000)',
                 "it": 'sensore di prossimità (VCNL4000)'},
    # ── Pilote "identite elargie" du 2026-08-19 (TODO #57, sous-chantier B) ──
    "esp8266":          {"fr": 'module WiFi (ESP8266)',
                 "en": 'WiFi module (ESP8266)',
                 "es": 'módulo WiFi (ESP8266)',
                 "it": 'modulo WiFi (ESP8266)'},
    # 2026-08-26 : le type existait et etait emis, mais n'avait aucun libelle —
    # l'utilisateur voyait « wiz820io » brut. Debusque par
    # `test_no_detected_type_is_nameless` une fois les alias d'en-tetes en
    # place, qui ont fait remonter le type sous son vrai nom.
    "wiz820io":         {"fr": 'module Ethernet (WIZ820io)',
                 "en": 'Ethernet module (WIZ820io)',
                 "es": 'módulo Ethernet (WIZ820io)',
                 "it": 'modulo Ethernet (WIZ820io)'},
    "sim800l":          {"fr": 'module GSM (SIM800L)',
                 "en": 'GSM module (SIM800L)',
                 "es": 'módulo GSM (SIM800L)',
                 "it": 'modulo GSM (SIM800L)'},
    "mq2":              {"fr": 'capteur de gaz (MQ-2)',
                 "en": 'gas sensor (MQ-2)',
                 "es": 'sensor de gas (MQ-2)',
                 "it": 'sensore di gas (MQ-2)'},
    "water_flow_sensor": {"fr": 'débitmètre à eau (YF-S201)',
                 "en": 'water flow sensor (YF-S201)',
                 "es": 'sensor de flujo de agua (YF-S201)',
                 "it": "sensore di flusso d'acqua (YF-S201)"},
    "drv8825":          {"fr": 'driver de moteur pas à pas (DRV8825)',
                 "en": 'stepper motor driver (DRV8825)',
                 "es": 'controlador de motor paso a paso (DRV8825)',
                 "it": 'driver per motore passo passo (DRV8825)'},
    "flame_sensor":     {"fr": 'capteur de flamme',
                 "en": 'flame sensor',
                 "es": 'sensor de llama',
                 "it": 'sensore di fiamma'},
    "rain_sensor":      {"fr": 'capteur de pluie',
                 "en": 'rain sensor',
                 "es": 'sensor de lluvia',
                 "it": 'sensore di pioggia'},
    "sound_detector":   {"fr": 'détecteur de son',
                 "en": 'sound detector',
                 "es": 'detector de sonido',
                 "it": 'rilevatore di suono'},
    # ── Lot #2 "identite elargie" du 2026-08-19 (TODO #57, sous-chantier B) ──
    "tmp006":   {"fr": 'capteur infrarouge sans contact (TMP006)',
                 "en": 'contactless infrared sensor (TMP006)',
                 "es": 'sensor infrarrojo sin contacto (TMP006)',
                 "it": 'sensore infrarosso senza contatto (TMP006)'},
    "tmp007":   {"fr": 'capteur infrarouge sans contact (TMP007)',
                 "en": 'contactless infrared sensor (TMP007)',
                 "es": 'sensor infrarrojo sin contacto (TMP007)',
                 "it": 'sensore infrarosso senza contatto (TMP007)'},
    "si1145":   {"fr": "capteur d'indice UV (SI1145)",
                 "en": 'UV index sensor (SI1145)',
                 "es": 'sensor de índice UV (SI1145)',
                 "it": 'sensore di indice UV (SI1145)'},
    "adt7410":  {"fr": 'capteur de température de précision (ADT7410)',
                 "en": 'precision temperature sensor (ADT7410)',
                 "es": 'sensor de temperatura de precisión (ADT7410)',
                 "it": 'sensore di temperatura di precisione (ADT7410)'},
    "ds3502":   {"fr": 'potentiomètre numérique (DS3502)',
                 "en": 'digital potentiometer (DS3502)',
                 "es": 'potenciómetro digital (DS3502)',
                 "it": 'potenziometro digitale (DS3502)'},
    "fram":     {"fr": 'mémoire FRAM I2C',
                 "en": 'I2C FRAM memory',
                 "es": 'memoria FRAM I2C',
                 "it": 'memoria FRAM I2C'},
    "mprls":    {"fr": 'capteur de pression (MPRLS)',
                 "en": 'pressure sensor (MPRLS)',
                 "es": 'sensor de presión (MPRLS)',
                 "it": 'sensore di pressione (MPRLS)'},
    "hdc1008":  {"fr": "capteur de température et d'humidité (HDC1008)",
                 "en": 'temperature and humidity sensor (HDC1008)',
                 "es": 'sensor de temperatura y humedad (HDC1008)',
                 "it": 'sensore di temperatura e umidità (HDC1008)'},
    "adxl335":  {"fr": 'accéléromètre analogique 3 axes (ADXL335)',
                 "en": 'analog 3-axis accelerometer (ADXL335)',
                 "es": 'acelerómetro analógico de 3 ejes (ADXL335)',
                 "it": 'accelerometro analogico a 3 assi (ADXL335)'},
    "bluefruit_le": {"fr": 'module Bluetooth Low Energy (Bluefruit LE)',
                 "en": 'Bluetooth Low Energy module (Bluefruit LE)',
                 "es": 'módulo Bluetooth Low Energy (Bluefruit LE)',
                 "it": 'modulo Bluetooth Low Energy (Bluefruit LE)'},
    "spi_flash": {"fr": 'mémoire flash SPI',
                 "en": 'SPI flash memory',
                 "es": 'memoria flash SPI',
                 "it": 'memoria flash SPI'},
    "dotstar":  {"fr": 'bande de LEDs adressables (DotStar)',
                 "en": 'addressable LED strip (DotStar)',
                 "es": 'tira de LED direccionable (DotStar)',
                 "it": 'striscia LED indirizzabile (DotStar)'},
    "tsl2561":  {"fr": 'capteur de luminosité de précision (TSL2561)',
                 "en": 'precision light sensor (TSL2561)',
                 "es": 'sensor de luz de precisión (TSL2561)',
                 "it": 'sensore di luce di precisione (TSL2561)'},
    "sharp_memory_display": {"fr": 'écran mémoire réflectif (SHARP)',
                 "en": 'reflective memory display (SHARP)',
                 "es": 'pantalla de memoria reflectiva (SHARP)',
                 "it": 'display a memoria riflettente (SHARP)'},
    "winc1500": {"fr": 'module WiFi SPI (WINC1500)',
                 "en": 'SPI WiFi module (WINC1500)',
                 "es": 'módulo WiFi SPI (WINC1500)',
                 "it": 'modulo WiFi SPI (WINC1500)'},
    "tmp36":    {"fr": 'capteur de température analogique (TMP36)',
                 "en": 'analog temperature sensor (TMP36)',
                 "es": 'sensor de temperatura analógico (TMP36)',
                 "it": 'sensore di temperatura analogico (TMP36)'},
    "flex_sensor": {"fr": 'capteur de flexion',
                 "en": 'flex sensor',
                 "es": 'sensor de flexión',
                 "it": 'sensore di flessione'},
    "si4713":   {"fr": 'émetteur FM stéréo (SI4713)',
                 "en": 'stereo FM transmitter (SI4713)',
                 "es": 'transmisor FM estéreo (SI4713)',
                 "it": 'trasmettitore FM stereo (SI4713)'},
    "ads7830":  {"fr": 'convertisseur analogique-numérique 8 voies (ADS7830)',
                 "en": '8-channel analog-to-digital converter (ADS7830)',
                 "es": 'convertidor analógico-digital de 8 canales (ADS7830)',
                 "it": 'convertitore analogico-digitale a 8 canali (ADS7830)'},
    "trellis":  {"fr": 'grille de boutons rétroéclairés (Trellis)',
                 "en": 'backlit button grid (Trellis)',
                 "es": 'matriz de botones retroiluminados (Trellis)',
                 "it": 'griglia di pulsanti retroilluminati (Trellis)'},
    "touch_sensor": {"fr": 'capteur tactile capacitif',
                 "en": 'capacitive touch sensor',
                 "es": 'sensor táctil capacitivo',
                 "it": 'sensore tattile capacitivo'},
    "ir_reflective_sensor": {"fr": 'capteur réflectif infrarouge (QRE1113)',
                 "en": 'infrared reflective sensor (QRE1113)',
                 "es": 'sensor reflectivo infrarrojo (QRE1113)',
                 "it": 'sensore riflettente infrarosso (QRE1113)'},
    "mmc5603":  {"fr": 'magnétomètre I2C (MMC5603)',
                 "en": 'I2C magnetometer (MMC5603)',
                 "es": 'magnetómetro I2C (MMC5603)',
                 "it": 'magnetometro I2C (MMC5603)'},
    "hdc3021":  {"fr": "capteur de température et d'humidité de précision (HDC3021)",
                 "en": 'precision temperature and humidity sensor (HDC3021)',
                 "es": 'sensor de temperatura y humedad de precisión (HDC3021)',
                 "it": 'sensore di temperatura e umidità di precisione (HDC3021)'},
    "ina228":   {"fr": 'moniteur de puissance de précision (INA228)',
                 "en": 'precision power monitor (INA228)',
                 "es": 'monitor de potencia de precisión (INA228)',
                 "it": 'monitor di potenza di precisione (INA228)'},
    "opt4048":  {"fr": 'capteur de couleur de précision (OPT4048)',
                 "en": 'precision color sensor (OPT4048)',
                 "es": 'sensor de color de precisión (OPT4048)',
                 "it": 'sensore di colore di precisione (OPT4048)'},
    "ina169":   {"fr": 'capteur de courant analogique (INA169)',
                 "en": 'analog current sensor (INA169)',
                 "es": 'sensor de corriente analógico (INA169)',
                 "it": 'sensore di corrente analogico (INA169)'},
    "guva_s12sd": {"fr": 'capteur UV analogique (GUVA-S12SD)',
                 "en": 'analog UV sensor (GUVA-S12SD)',
                 "es": 'sensor UV analógico (GUVA-S12SD)',
                 "it": 'sensore UV analogico (GUVA-S12SD)'},
    "stspin220": {"fr": 'driver de moteur pas à pas silencieux (STSPIN220)',
                 "en": 'silent stepper motor driver (STSPIN220)',
                 "es": 'controlador de motor paso a paso silencioso (STSPIN220)',
                 "it": 'driver per motore passo passo silenzioso (STSPIN220)'},
    "tmc2209":  {"fr": 'driver de moteur pas à pas silencieux (TMC2209)',
                 "en": 'silent stepper motor driver (TMC2209)',
                 "es": 'controlador de motor paso a paso silencioso (TMC2209)',
                 "it": 'driver per motore passo passo silenzioso (TMC2209)'},
    "i2c_multiplexer": {"fr": 'multiplexeur I2C 8 canaux (TCA9548A)',
                 "en": '8-channel I2C multiplexer (TCA9548A)',
                 "es": 'multiplexor I2C de 8 canales (TCA9548A)',
                 "it": 'multiplexer I2C a 8 canali (TCA9548A)'},
    "lps28":    {"fr": 'capteur de pression (LPS28)',
                 "en": 'pressure sensor (LPS28)',
                 "es": 'sensor de presión (LPS28)',
                 "it": 'sensore di pressione (LPS28)'},
    "eink_display": {"fr": "écran à encre électronique (e-ink)",
                 "en": 'electronic ink display (e-ink)',
                 "es": 'pantalla de tinta electrónica (e-ink)',
                 "it": 'display a inchiostro elettronico (e-ink)'},
    "nau7802":  {"fr": 'ADC 24 bits pour cellule de charge (NAU7802)',
                 "en": '24-bit load cell ADC (NAU7802)',
                 "es": 'ADC de 24 bits para célula de carga (NAU7802)',
                 "it": 'ADC a 24 bit per cella di carico (NAU7802)'},
    "sen5x":    {"fr": "capteur environnemental multi-paramètres (SEN54/55)",
                 "en": 'multi-parameter environmental sensor (SEN54/55)',
                 "es": 'sensor ambiental multiparamétrico (SEN54/55)',
                 "it": 'sensore ambientale multiparametrico (SEN54/55)'},
    "gc9a01":   {"fr": 'écran TFT rond (GC9A01)',
                 "en": 'round TFT display (GC9A01)',
                 "es": 'pantalla TFT redonda (GC9A01)',
                 "it": 'display TFT rotondo (GC9A01)'},
    "mcp9600":  {"fr": "amplificateur de thermocouple I2C (MCP9600)",
                 "en": "I2C thermocouple amplifier (MCP9600)",
                 "es": "amplificador de termopar I2C (MCP9600)",
                 "it": "amplificatore di termocoppia I2C (MCP9600)"},
    "max17043": {"fr": "jauge de batterie LiPo (MAX17043)",
                 "en": "LiPo battery fuel gauge (MAX17043)",
                 "es": "medidor de batería LiPo (MAX17043)",
                 "it": "indicatore di carica LiPo (MAX17043)"},
    "amg8833":  {"fr": "caméra thermique 8x8 (AMG8833)",
                 "en": "8x8 thermal camera (AMG8833)",
                 "es": "cámara térmica 8x8 (AMG8833)",
                 "it": "termocamera 8x8 (AMG8833)"},
    "pm25":     {"fr": "capteur de particules fines PM2.5 (PMSA003I)",
                 "en": "PM2.5 particulate sensor (PMSA003I)",
                 "es": "sensor de partículas PM2.5 (PMSA003I)",
                 "it": "sensore di particolato PM2.5 (PMSA003I)"},
    "st7735":         {"fr": "écran TFT couleur (ST7735)",
                       "en": "color TFT display (ST7735)",
                       "es": "pantalla TFT color (ST7735)",
                       "it": "display TFT a colori (ST7735)"},
    "st7789":         {"fr": "écran TFT couleur (ST7789)",
                       "en": "color TFT display (ST7789)",
                       "es": "pantalla TFT color (ST7789)",
                       "it": "display TFT a colori (ST7789)"},
    "max31855":       {"fr": "thermocouple SPI (MAX31855)",
                       "en": "thermocouple amplifier (MAX31855)",
                       "es": "termopar SPI (MAX31855)",
                       "it": "termocoppia SPI (MAX31855)"},
    "hx711":          {"fr": "cellule de charge HX711 (balance)",
                       "en": "load cell amplifier (HX711)",
                       "es": "célula de carga HX711 (báscula)",
                       "it": "cella di carico HX711 (bilancia)"},
    "dfplayer":       {"fr": "module MP3 (DFPlayer Mini)",
                       "en": "MP3 player module (DFPlayer Mini)",
                       "es": "módulo MP3 (DFPlayer Mini)",
                       "it": "modulo MP3 (DFPlayer Mini)"},
    "sr74hc595":      {"fr": "registre à décalage (74HC595)",
                       "en": "shift register (74HC595)",
                       "es": "registro de desplazamiento (74HC595)",
                       "it": "registro a scorrimento (74HC595)"},
    "lcd_i2c":        {"fr": "écran LCD I²C",             "en": "I²C LCD screen",
                       "es": "pantalla LCD I²C",          "it": "schermo LCD I²C"},
    "oled_ssd1306":   {"fr": "écran OLED SSD1306",        "en": "SSD1306 OLED screen",
                       "es": "pantalla OLED SSD1306",     "it": "schermo OLED SSD1306"},
    "module_generic": {"fr": "module",                    "en": "module",
                       "es": "módulo",                    "it": "modulo"},
    "ina219":         {"fr": "capteur de courant INA219",  "en": "INA219 current sensor",
                       "es": "sensor de corriente INA219",  "it": "sensore di corrente INA219"},
    "ldr":            {"fr": "photorésistance (LDR)",      "en": "LDR (photoresistor)",
                       "es": "fotorresistencia (LDR)",     "it": "fotoresistenza (LDR)"},
    "ky018":          {"fr": "photorésistance KY-018",     "en": "KY-018 photoresistor",
                       "es": "fotorresistencia KY-018",    "it": "fotoresistenza KY-018"},
    "thermistor":     {"fr": "thermistance",               "en": "thermistor",
                       "es": "termistor",                  "it": "termistore"},
    "microphone":     {"fr": "capteur de son",             "en": "sound sensor",
                       "es": "sensor de sonido",           "it": "sensore di suono"},
    "relay":          {"fr": "relais",                     "en": "relay",
                       "es": "relé",                       "it": "relè"},
    "pir":            {"fr": "détecteur de mouvement (PIR)","en": "PIR motion sensor",
                       "es": "sensor de movimiento (PIR)", "it": "sensore di movimento (PIR)"},
    # Motors / drivers
    "dc_motor":       {"fr": "moteur DC",                 "en": "DC motor",
                       "es": "motor DC",                  "it": "motore DC"},
    "stepper_motor":  {"fr": "moteur pas-à-pas 28BYJ-48", "en": "28BYJ-48 stepper motor",
                       "es": "motor paso a paso 28BYJ-48","it": "motore passo-passo 28BYJ-48"},
    "nema17":         {"fr": "moteur NEMA17",             "en": "NEMA17 motor",
                       "es": "motor NEMA17",              "it": "motore NEMA17"},
    "l298n":          {"fr": "driver L298N",              "en": "L298N driver",
                       "es": "controlador L298N",         "it": "driver L298N"},
    "l293d":          {"fr": "driver L293D",              "en": "L293D driver",
                       "es": "controlador L293D",         "it": "driver L293D"},
    "l293d_module":   {"fr": "driver L293D (module)",     "en": "L293D module driver",
                       "es": "módulo controlador L293D",  "it": "driver L293D (modulo)"},
    "tb6612fng":      {"fr": "driver TB6612FNG",          "en": "TB6612FNG driver",
                       "es": "controlador TB6612FNG",     "it": "driver TB6612FNG"},
    "drv8833":        {"fr": "driver DRV8833",            "en": "DRV8833 driver",
                       "es": "controlador DRV8833",       "it": "driver DRV8833"},
    "a4988":          {"fr": "driver A4988",              "en": "A4988 driver",
                       "es": "controlador A4988",         "it": "driver A4988"},
    "uln2003":        {"fr": "driver ULN2003",            "en": "ULN2003 driver",
                       "es": "controlador ULN2003",       "it": "driver ULN2003"},
    "battery_external": {"fr": "batterie externe",        "en": "external battery",
                         "es": "batería externa",         "it": "batteria esterna"},
    # Sensors / modules without a dedicated asset (generic rendering)
    "ds18b20":        {"fr": "capteur DS18B20",           "en": "DS18B20 sensor",
                       "es": "sensor DS18B20",            "it": "sensore DS18B20"},
    "bme280":         {"fr": "capteur BME280/VMA335",     "en": "BME280/VMA335 sensor",
                       "es": "sensor BME280/VMA335",      "it": "sensore BME280/VMA335"},
    "mpu6050":        {"fr": "capteur MPU6050",           "en": "MPU6050 sensor",
                       "es": "sensor MPU6050",            "it": "sensore MPU6050"},
    "ds1307":         {"fr": "horloge RTC DS1307",        "en": "DS1307 RTC clock",
                       "es": "reloj RTC DS1307",          "it": "orologio RTC DS1307"},
    "ds3231":         {"fr": "horloge RTC DS3231",        "en": "DS3231 RTC clock",
                       "es": "reloj RTC DS3231",          "it": "orologio RTC DS3231"},
    "ccs811":         {"fr": "capteur qualité air CCS811","en": "CCS811 air quality sensor",
                       "es": "sensor de calidad CCS811",  "it": "sensore qualità aria CCS811"},
    "mfrc522":        {"fr": "lecteur RFID MFRC522",      "en": "MFRC522 RFID reader",
                       "es": "lector RFID MFRC522",       "it": "lettore RFID MFRC522"},
    "ili9341":        {"fr": "écran TFT ILI9341",         "en": "ILI9341 TFT screen",
                       "es": "pantalla TFT ILI9341",      "it": "schermo TFT ILI9341"},
    "neopixel":       {"fr": "bande LED WS2812 (NeoPixel)", "en": "WS2812 LED strip (NeoPixel)",
                       "es": "tira LED WS2812 (NeoPixel)",  "it": "striscia LED WS2812 (NeoPixel)"},
    "encoder":        {"fr": "encodeur rotatif",          "en": "rotary encoder",
                       "es": "codificador rotativo",      "it": "encoder rotativo"},
    "keypad":         {"fr": "clavier matriciel",         "en": "matrix keypad",
                       "es": "teclado matricial",         "it": "tastiera a matrice"},
    "ir_receiver":    {"fr": "récepteur infrarouge",      "en": "IR receiver",
                       "es": "receptor infrarrojo",       "it": "ricevitore IR"},
    "gps":            {"fr": "module GPS",                "en": "GPS module",
                       "es": "módulo GPS",                "it": "modulo GPS"},
    "uart_module":    {"fr": "module UART",               "en": "UART module",
                       "es": "módulo UART",               "it": "modulo UART"},
    # TODO #69 (2026-08-27) : le lot d'identites du balayage des serigraphies.
    "mq131":            {"fr": "capteur d'ozone MQ-131", "en": "MQ-131 ozone sensor",
                      "es": "sensor de ozono MQ-131", "it": "sensore di ozono MQ-131"},
    "mq136":            {"fr": "capteur de gaz MQ-136", "en": "MQ-136 gas sensor",
                      "es": "sensor de gas MQ-136", "it": "sensore di gas MQ-136"},
    "mq137":            {"fr": "capteur de gaz MQ-137", "en": "MQ-137 gas sensor",
                      "es": "sensor de gas MQ-137", "it": "sensore di gas MQ-137"},
    "mq138":            {"fr": "capteur de gaz MQ-138", "en": "MQ-138 gas sensor",
                      "es": "sensor de gas MQ-138", "it": "sensore di gas MQ-138"},
    "mq214":            {"fr": "capteur de gaz MQ-214", "en": "MQ-214 gas sensor",
                      "es": "sensor de gas MQ-214", "it": "sensore di gas MQ-214"},
    "mq216":            {"fr": "capteur de gaz MQ-216", "en": "MQ-216 gas sensor",
                      "es": "sensor de gas MQ-216", "it": "sensore di gas MQ-216"},
    "mq303a":           {"fr": "capteur de gaz MQ-303A", "en": "MQ-303A gas sensor",
                      "es": "sensor de gas MQ-303A", "it": "sensore di gas MQ-303A"},
    "mq306a":           {"fr": "capteur de gaz MQ-306A", "en": "MQ-306A gas sensor",
                      "es": "sensor de gas MQ-306A", "it": "sensore di gas MQ-306A"},
    "mq307a":           {"fr": "capteur de gaz MQ-307A", "en": "MQ-307A gas sensor",
                      "es": "sensor de gas MQ-307A", "it": "sensore di gas MQ-307A"},
    "mq309a":           {"fr": "capteur de gaz MQ-309A", "en": "MQ-309A gas sensor",
                      "es": "sensor de gas MQ-309A", "it": "sensore di gas MQ-309A"},
    "mhz14a":           {"fr": "capteur CO₂ MH-Z14A", "en": "MH-Z14A CO₂ sensor",
                      "es": "sensor de CO₂ MH-Z14A", "it": "sensore di CO₂ MH-Z14A"},
    "mhz1311a":         {"fr": "capteur CO₂ MH-Z1311A", "en": "MH-Z1311A CO₂ sensor",
                      "es": "sensor de CO₂ MH-Z1311A", "it": "sensore di CO₂ MH-Z1311A"},
    "rcwl0516":         {"fr": "détecteur de mouvement radar RCWL-0516", "en": "RCWL-0516 radar motion sensor",
                      "es": "sensor de movimiento radar RCWL-0516", "it": "sensore di movimento radar RCWL-0516"},
    "rcwl1005":         {"fr": "télémètre ultrason I2C RCWL-1005", "en": "RCWL-1005 I2C ultrasonic sensor",
                      "es": "sensor ultrasónico I2C RCWL-1005", "it": "sensore a ultrasuoni I2C RCWL-1005"},
    "rcwl1605":         {"fr": "télémètre ultrason I2C RCWL-1605", "en": "RCWL-1605 I2C ultrasonic sensor",
                      "es": "sensor ultrasónico I2C RCWL-1605", "it": "sensore a ultrasuoni I2C RCWL-1605"},
    "jsn_sr04t":        {"fr": "télémètre ultrason étanche JSN-SR04T", "en": "JSN-SR04T waterproof ultrasonic sensor",
                      "es": "sensor ultrasónico impermeable JSN-SR04T", "it": "sensore a ultrasuoni impermeabile JSN-SR04T"},
    "mhz19":          {"fr": "capteur CO₂ MH-Z19",        "en": "MH-Z19 CO₂ sensor",
                       "es": "sensor CO₂ MH-Z19",         "it": "sensore CO₂ MH-Z19"},
    "lora_sx1276":    {"fr": "module LoRa SX1276",        "en": "LoRa SX1276 module",
                       "es": "módulo LoRa SX1276",        "it": "modulo LoRa SX1276"},
    "mq135":          {"fr": "capteur de gaz MQ-135",     "en": "MQ-135 gas sensor",
                       "es": "sensor de gas MQ-135",      "it": "sensore di gas MQ-135"},
    # Registry components with wiring="known"/"unknown"/"none" but no entry
    # here yet (measured 2026-07-31): `_label` falls back to the raw id, so
    # the "Composants" tab printed slugs like "sd_card" verbatim. Beginner-
    # facing names, not library names -- for the chips with no common
    # nickname (INA226, INA3221, MPU9250) the reference itself IS the
    # readable name, kept uppercase.
    "mpu9250":            {"fr": "centrale inertielle 9 axes (MPU9250)",
                           "en": "9-axis IMU (MPU9250)",
                           "es": "IMU de 9 ejes (MPU9250)",
                           "it": "IMU a 9 assi (MPU9250)"},
    "ina226":             {"fr": "capteur de courant INA226",
                           "en": "INA226 current sensor",
                           "es": "sensor de corriente INA226",
                           "it": "sensore di corrente INA226"},
    "ina3221":            {"fr": "capteur de courant 3 voies INA3221",
                           "en": "3-channel current sensor (INA3221)",
                           "es": "sensor de corriente de 3 canales INA3221",
                           "it": "sensore di corrente a 3 canali INA3221"},
    # NOT re-added here: `rotary_encoder`, `lora` and `rtc`. The first pass gave
    # them labels, creating a SECOND spelling for components this table already
    # named (`encoder`, `lora_sx1276`, `ds3231`/`ds1307`) -- "encodeur rotatif"
    # appeared twice under two ids. `markers` emits the latter, and those
    # identifiers are written into saved projects: they are the durable ones,
    # so the registry adopted them rather than the other way round.
    "sd_card":            {"fr": "module carte SD",        "en": "SD card module",
                           "es": "módulo de tarjeta SD",    "it": "modulo scheda SD"},
    "motor_shield_v2":    {"fr": "shield moteur (Adafruit Motor Shield v2)",
                           "en": "motor shield (Adafruit Motor Shield v2)",
                           "es": "shield de motores (Adafruit Motor Shield v2)",
                           "it": "shield motori (Adafruit Motor Shield v2)"},
    "grove_motor_driver": {"fr": "driver moteur I2C (Grove)",
                           "en": "I2C motor driver (Grove)",
                           "es": "controlador de motor I2C (Grove)",
                           "it": "driver motore I2C (Grove)"},
    "eeprom":             {"fr": "mémoire EEPROM",         "en": "EEPROM memory",
                           "es": "memoria EEPROM",          "it": "memoria EEPROM"},
}

_ROLE_LABEL: dict[str, dict[str, str]] = {
    "series":   {"fr": "en série",      "en": "in series",
                 "es": "en serie",      "it": "in serie"},
    "pullup":   {"fr": "en pull-up",    "en": "as a pull-up",
                 "es": "como pull-up",  "it": "come pull-up"},
    "pulldown": {"fr": "en pull-down",  "en": "as a pull-down",
                 "es": "como pull-down","it": "come pull-down"},
    "limit":    {"fr": "de limitation", "en": "limiting",
                 "es": "limitadora",    "it": "limitatrice"},
}

_SECTION_TITLES: dict[str, dict[str, str]] = {
    "warnings":    {"fr": "Avertissements",  "en": "Warnings",
                    "es": "Advertencias",    "it": "Avvisi"},
    "components":  {"fr": "Composants",      "en": "Components",
                    "es": "Componentes",     "it": "Componenti"},
    "feature":     {"fr": "Fonctionnalité",  "en": "Feature",
                    "es": "Funcionalidad",   "it": "Funzionalità"},
    "skipped_motors": {
        "fr": "Moteurs détectés mais non câblés",
        "en": "Detected motors not wired",
        "es": "Motores detectados pero no cableados",
        "it": "Motori rilevati ma non cablati",
    },
    "skipped_motors_explainer": {
        "fr": "PromptuinoUI se limite à 2 moteurs DC dans le schéma. "
              "Les moteurs ci-dessous sont bien reconnus dans ton code "
              "mais ne sont pas câblés sur le diagramme. Pour les câbler "
              "à la place des actuels, ouvre « Modifier les choix » et "
              "décoche/recoche les moteurs voulus.",
        "en": "PromptuinoUI is limited to 2 DC motors in the diagram. "
              "The motors below are recognized in your code but not "
              "wired on the diagram. To wire them instead of the "
              "current ones, open “Edit choices” and uncheck/recheck "
              "the desired motors.",
        "es": "PromptuinoUI se limita a 2 motores DC en el esquema. "
              "Los motores siguientes están reconocidos en tu código "
              "pero no se cablean en el diagrama. Para cablearlos en "
              "lugar de los actuales, abre «Editar opciones» y "
              "desmarca/marca los motores deseados.",
        "it": "PromptuinoUI è limitato a 2 motori DC nello schema. "
              "I motori sottostanti sono riconosciuti nel tuo codice "
              "ma non sono cablati sul diagramma. Per cablarli al posto "
              "di quelli attuali, apri «Modifica scelte» e "
              "deseleziona/seleziona i motori desiderati.",
    },
    "no_components": {
        "fr": "_Aucun composant à câbler pour ce code._",
        "en": "_No components to wire for this code._",
        "es": "_No hay componentes que cablear para este código._",
        "it": "_Nessun componente da cablare per questo codice._",
    },
}

# Pedagogical justifications — displayed in `detailed` mode.
_EXPLANATIONS: dict[str, dict[str, str]] = {
    "led_series": {
        "fr": "La LED ne supporte pas la tension d'alimentation directe : "
              "cette résistance limite le courant à environ 15 mA, dans la "
              "zone nominale de fonctionnement.",
        "en": "An LED can't handle the supply voltage directly: this resistor "
              "limits current to about 15 mA, within nominal operating range.",
        "es": "El LED no soporta la tensión de alimentación directa: esta "
              "resistencia limita la corriente a unos 15 mA, dentro del rango "
              "nominal de funcionamiento.",
        "it": "Il LED non sopporta la tensione di alimentazione diretta: "
              "questa resistenza limita la corrente a circa 15 mA, nel range "
              "nominale di funzionamento.",
    },
    "button_pullup": {
        "fr": "Cette résistance de pull-up empêche la pin de **flotter** "
              "(état indéterminé) lorsque le bouton n'est pas pressé : elle "
              "force la pin à l'état haut au repos.",
        "en": "This pull-up resistor prevents the pin from **floating** "
              "(undefined state) when the button is not pressed: it pulls "
              "the pin to high level at rest.",
        "es": "Esta resistencia de pull-up evita que el pin **flote** "
              "(estado indeterminado) cuando el botón no está pulsado: "
              "fuerza el pin al estado alto en reposo.",
        "it": "Questa resistenza di pull-up impedisce che il pin **fluttui** "
              "(stato indeterminato) quando il pulsante non è premuto: "
              "forza il pin allo stato alto a riposo.",
    },
    "button_pulldown": {
        "fr": "Cette résistance de pull-down maintient la pin à l'état bas "
              "lorsque le bouton n'est pas pressé.",
        "en": "This pull-down resistor keeps the pin at low level when the "
              "button is not pressed.",
        "es": "Esta resistencia de pull-down mantiene el pin en estado bajo "
              "cuando el botón no está pulsado.",
        "it": "Questa resistenza di pull-down mantiene il pin allo stato "
              "basso quando il pulsante non è premuto.",
    },
    "led_anode": {
        "fr": "L'**anode** (broche longue) reçoit le courant ; la "
              "**cathode** (broche courte, côté méplat) est reliée à GND.",
        "en": "The **anode** (long lead) receives current; the **cathode** "
              "(short lead, flat side) connects to GND.",
        "es": "El **ánodo** (terminal largo) recibe la corriente; el "
              "**cátodo** (terminal corto, lado plano) se conecta a GND.",
        "it": "L'**anodo** (terminale lungo) riceve la corrente; il "
              "**catodo** (terminale corto, lato piatto) si collega a GND.",
    },
    "button": {
        "fr": "Le bouton-poussoir ferme le circuit quand il est appuyé. "
              "Les deux pattes du même côté sont déjà reliées en interne.",
        "en": "The push-button closes the circuit when pressed. Pins on the "
              "same side are already connected internally.",
        "es": "El pulsador cierra el circuito al ser presionado. Los pines "
              "del mismo lado ya están conectados internamente.",
        "it": "Il pulsante chiude il circuito quando premuto. I pin sullo "
              "stesso lato sono già collegati internamente.",
    },
    "i2c": {
        "fr": "Communication I²C : SDA = données, SCL = horloge. Sur Uno, "
              "SDA = A4 et SCL = A5 (les pull-ups sont déjà sur le module).",
        "en": "I²C communication: SDA = data, SCL = clock. On Uno, SDA = A4 "
              "and SCL = A5 (pull-ups are typically on the module itself).",
        "es": "Comunicación I²C: SDA = datos, SCL = reloj. En el Uno, "
              "SDA = A4 y SCL = A5 (las pull-ups están típicamente en el módulo).",
        "it": "Comunicazione I²C: SDA = dati, SCL = clock. Su Uno, "
              "SDA = A4 e SCL = A5 (le pull-up sono tipicamente sul modulo).",
    },
    "module_3_pins": {
        "fr": "Module 3 broches : VCC = alimentation, GND = masse, "
              "DATA = signal numérique vers le micro-contrôleur.",
        "en": "3-pin module: VCC = power, GND = ground, DATA = digital signal "
              "to the microcontroller.",
        "es": "Módulo de 3 pines: VCC = alimentación, GND = masa, "
              "DATA = señal digital al microcontrolador.",
        "it": "Modulo a 3 pin: VCC = alimentazione, GND = massa, "
              "DATA = segnale digitale al microcontrollore.",
    },
    "hcsr04": {
        "fr": "Le capteur ultrason émet une impulsion sur **TRIG** et "
              "mesure le temps de retour de l'écho sur **ECHO**.",
        "en": "The ultrasonic sensor sends a pulse on **TRIG** and measures "
              "the echo return time on **ECHO**.",
        "es": "El sensor ultrasónico emite un pulso en **TRIG** y mide el "
              "tiempo de retorno del eco en **ECHO**.",
        "it": "Il sensore a ultrasuoni emette un impulso su **TRIG** e "
              "misura il tempo di ritorno dell'eco su **ECHO**.",
    },
    "servo": {
        "fr": "Le servomoteur attend une impulsion PWM périodique sur "
              "**SIG** : la largeur d'impulsion détermine la position.",
        "en": "A servo motor expects a periodic PWM pulse on **SIG**: the "
              "pulse width determines the angle.",
        "es": "Un servomotor espera un pulso PWM periódico en **SIG**: "
              "el ancho de pulso determina el ángulo.",
        "it": "Un servomotore richiede un impulso PWM periodico su **SIG**: "
              "la larghezza dell'impulso determina l'angolo.",
    },
}


# ─── Warning templates (by code, by language) ───────────────────────
# Each template can use the params emitted by inference/markers via
# {placeholder}. See Netlist.add_warning(params=...).
_WARNING_TEMPLATES: dict[str, dict[str, str]] = {
    "led_series_resistor": {
        "fr": "Résistance de limitation {value}Ω ajoutée automatiquement "
              "pour la LED {led_ref}.",
        "en": "Current-limiting resistor {value}Ω automatically added for "
              "LED {led_ref}.",
        "es": "Resistencia limitadora {value}Ω añadida automáticamente "
              "para el LED {led_ref}.",
        "it": "Resistenza limitatrice {value}Ω aggiunta automaticamente "
              "per il LED {led_ref}.",
    },
    "button_external_pullup": {
        "fr": "Pull-up externe {value}Ω ajoutée pour le bouton {button_ref}.",
        "en": "External pull-up {value}Ω added for button {button_ref}.",
        "es": "Pull-up externa {value}Ω añadida para el botón {button_ref}.",
        "it": "Pull-up esterna {value}Ω aggiunta per il pulsante {button_ref}.",
    },
    # Ces trois-là n'avaient AUCUN gabarit et retombaient donc sur leur
    # `message` de secours, écrit en français — dans les 4 langues. Ce sont
    # pourtant trois des composants les plus courants d'un kit débutant :
    # tout sketch DHT, DS18B20 ou buzzer en déclenche un.
    "dht_data_pullup": {
        "fr": "Pull-up {value}Ω ajoutée sur DATA du {dht_ref}.",
        "en": "Pull-up {value}Ω added on the DATA line of {dht_ref}.",
        "es": "Pull-up {value}Ω añadida en DATA del {dht_ref}.",
        "it": "Pull-up {value}Ω aggiunta su DATA del {dht_ref}.",
    },
    "ds18b20_data_pullup": {
        "fr": "Pull-up {value}Ω ajoutée sur DATA du {sensor_ref}.",
        "en": "Pull-up {value}Ω added on the DATA line of {sensor_ref}.",
        "es": "Pull-up {value}Ω añadida en DATA del {sensor_ref}.",
        "it": "Pull-up {value}Ω aggiunta su DATA del {sensor_ref}.",
    },
    "buzzer_series_resistor": {
        "fr": "Résistance série {value}Ω ajoutée pour le buzzer {buzzer_ref}.",
        "en": "Series resistor {value}Ω added for buzzer {buzzer_ref}.",
        "es": "Resistencia en serie {value}Ω añadida para el zumbador "
              "{buzzer_ref}.",
        "it": "Resistenza in serie {value}Ω aggiunta per il buzzer "
              "{buzzer_ref}.",
    },
    "pin_double_use": {
        "fr": "Pin {pin} utilisée par plusieurs composants : {refs_csv}.",
        "en": "Pin {pin} used by multiple components: {refs_csv}.",
        "es": "Pin {pin} usado por varios componentes: {refs_csv}.",
        "it": "Pin {pin} utilizzato da più componenti: {refs_csv}.",
    },
    # La parenthese « (les marqueurs IA n'ont pas ete fournis) » a ete retiree
    # le 2026-08-10 : elle expliquait un detail d'IMPLEMENTATION (le detecteur
    # ne s'appuie plus sur des balises emises par le modele depuis
    # WIRING_DETECTOR_MODE = "python") a quelqu'un qui veut juste brancher son
    # montage. Ce qui reste est ce qui le concerne : le cablage est deduit,
    # donc il merite un coup d'oeil.
    # Le message DIT desormais que le resultat peut etre faux, et ou aller si
    # c'est le cas. « Deduit du code » seul est un constat neutre dont un
    # debutant ne tire rien ; le wiring etant experimental par construction,
    # c'est la porte de sortie qui manquait.
    "wiring_inferred": {
        "fr": "Le câblage a été déduit du code et peut être inexact. Tu peux "
              "demander de l'aide dans le chat.",
        "en": "Wiring was inferred from the code and may be inaccurate. You "
              "can ask for help in the chat.",
        "es": "El cableado se ha deducido del código y puede ser inexacto. "
              "Puedes pedir ayuda en el chat.",
        "it": "Il cablaggio è stato dedotto dal codice e potrebbe non essere "
              "esatto. Puoi chiedere aiuto nella chat.",
    },
    "unwired_unknown_component": {
        "fr": "Composant « {name} » détecté mais son câblage n'a pas pu être "
              "déduit (type non reconnu).",
        "en": "Component “{name}” detected but its wiring could not "
              "be inferred (unrecognized type).",
        "es": "Componente «{name}» detectado pero no se pudo deducir su "
              "cableado (tipo no reconocido).",
        "it": "Componente «{name}» rilevato ma non è stato possibile dedurre "
              "il suo cablaggio (tipo non riconosciuto).",
    },
    "unwired_unknown_component_pins": {
        "fr": "Composant « {name} » détecté mais son câblage n'a pas pu être "
              "déduit (type non reconnu). Broches vues dans le code : {pins} — "
              "à relier en te reportant à sa documentation.",
        "en": "Component “{name}” detected but its wiring could not be inferred "
              "(unrecognized type). Pins seen in the code: {pins} — wire them "
              "using its documentation.",
        "es": "Componente «{name}» detectado pero no se pudo deducir su "
              "cableado (tipo no reconocido). Pines vistos en el código: "
              "{pins} — conéctalos consultando su documentación.",
        "it": "Componente «{name}» rilevato ma non è stato possibile dedurre il "
              "suo cablaggio (tipo non riconosciuto). Pin visti nel codice: "
              "{pins} — collegali consultando la sua documentazione.",
    },
    "declared_unconnected_pins": {
        "fr": "« {name} » : tu as laissé ces broches non connectées : {pins}. "
              "Le schéma les dessine sans fil, c'est voulu.",
        "en": "“{name}”: you left these pins unconnected: {pins}. The schematic "
              "draws them without a wire, as intended.",
        "es": "«{name}»: dejaste estos pines sin conectar: {pins}. El esquema "
              "los dibuja sin cable, es intencionado.",
        "it": "«{name}»: hai lasciato questi pin non collegati: {pins}. Lo "
              "schema li disegna senza filo, è voluto.",
    },
    # ⚠️ Ce message dit le FAIT, jamais l'usage. `_constructor_pins_for`
    # retient tout litteral 0..13 de n'importe quel argument, donc
    # `MonEcran lcd(16, 2)` fait sortir « D2 » : ecrire « le code UTILISE D2 »
    # serait alors faux et permanent. On rapporte ce qui est verifiable (des
    # valeurs sont passees au constructeur, la fiche ne les cable pas) et on
    # laisse explicitement la sortie « ignore si ce ne sont pas des broches ».
    # Raisonnement complet dans ui/wiring/declared_apply.py.
    "declared_pins_diverge_from_code": {
        "fr": "Le code passe {pins} au constructeur de ce composant, et la "
              "fiche « {name} » ne les câble pas. Harmonise, ou ignore si ce "
              "ne sont pas des broches.",
        "en": "The code passes {pins} to this component’s constructor, and "
              "the “{name}” card does not wire them. Reconcile, or ignore "
              "if these are not pins.",
        "es": "El código pasa {pins} al constructor de este componente, y la "
              "ficha «{name}» no los cablea. Armoniza, o ignora si no son "
              "pines.",
        "it": "Il codice passa {pins} al costruttore di questo componente, e "
              "la scheda «{name}» non li collega. Armonizza, o ignora se non "
              "sono pin.",
    },
    # ⚠️ Ce message nomme la ref adverse TELLE QUELLE : si le net Arduino est
    # porte par la resistance serie d'une LED, c'est la resistance qui est
    # nommee — exact, a defaut d'etre elegant (remonter le bridge est
    # differe). Les partages legitimes ne l'atteignent jamais : rails, nets a
    # alias I2C et labels de bus partage sont exclus a la source.
    # Raisonnement complet dans ui/wiring/declared_apply.py.
    "declared_pin_already_claimed": {
        "fr": "La fiche « {name} » câble {net}, déjà utilisée par un autre "
              "composant du schéma ({ref}).",
        "en": "The “{name}” card wires {net}, already used by another "
              "component of the diagram ({ref}).",
        "es": "La ficha «{name}» cablea {net}, ya usada por otro componente "
              "del esquema ({ref}).",
        "it": "La scheda «{name}» collega {net}, già usato da un altro "
              "componente dello schema ({ref}).",
    },
    # Le type deduit POSSEDE une reference (« RCWL-0516 ») et le prompt ne
    # l'a pas donnee : c'est la DESCRIPTION qui a gagne, donc l'app a choisi
    # un numero de piece que personne n'a ecrit. Meme discipline que ses
    # voisins : dire la devinette, et ou la corriger.
    "presumed_from_description": {
        "fr": "**{name}** a été déduit de ta **description**, pas d'une "
              "référence exacte. Le schéma a choisi cette pièce parce que ce "
              "que tu as écrit lui ressemble — vérifie que c'est bien la "
              "tienne, et corrige-la avec l'engrenage sinon.",
        "en": "**{name}** was inferred from your **description**, not from an "
              "exact reference. The schematic picked this part because what "
              "you wrote resembles it — check that it is really yours, and "
              "use the gear icon to fix it otherwise.",
        "es": "**{name}** se dedujo de tu **descripción**, no de una "
              "referencia exacta. El esquema eligió esta pieza porque lo que "
              "escribiste se le parece — comprueba que es la tuya y corrígela "
              "con el engranaje si no.",
        "it": "**{name}** è stato dedotto dalla tua **descrizione**, non da un "
              "riferimento esatto. Lo schema ha scelto questo componente "
              "perché quello che hai scritto gli somiglia — verifica che sia "
              "il tuo e correggilo con l'ingranaggio altrimenti.",
    },
    "presumed_analog_component": {
        "fr": "Composant **présumé** sur {pin} : ton code lit une valeur "
              "analogique, mais rien n'indique ce qui est branché. Le schéma "
              "dessine un potentiomètre 10 kΩ **par défaut**, pas parce qu'il "
              "l'a reconnu. Si c'est autre chose, corrige-le avec l'engrenage.",
        "en": "**Presumed** component on {pin}: your sketch reads an analog "
              "value, but nothing says what is wired there. The schematic "
              "draws a 10 kΩ potentiometer **by default**, not because it "
              "recognised one. Use the gear icon to fix it if it is something "
              "else.",
        "es": "Componente **supuesto** en {pin}: tu código lee un valor "
              "analógico, pero nada indica qué hay conectado. El esquema "
              "dibuja un potenciómetro de 10 kΩ **por defecto**, no porque lo "
              "haya reconocido. Corrígelo con el engranaje si es otra cosa.",
        "it": "Componente **presunto** su {pin}: il tuo codice legge un valore "
              "analogico, ma nulla dice cosa sia collegato. Lo schema disegna "
              "un potenziometro da 10 kΩ **per impostazione predefinita**, non "
              "perché lo abbia riconosciuto. Correggilo con l'ingranaggio se è "
              "altro.",
    },
    "presumed_i2c_wiring": {
        "fr": "Câblage I2C **présumé** pour « {name} » : le code utilise le bus "
              "I2C mais ne dit pas comment ce composant s'y branche. Vérifie "
              "VCC/GND/SDA/SCL sur sa documentation ; corrige-le avec "
              "l'engrenage si ce n'est pas le bon composant.",
        "en": "**Presumed** I2C wiring for “{name}”: the sketch uses the I2C "
              "bus but does not say how this component connects to it. Check "
              "VCC/GND/SDA/SCL against its documentation; use the gear icon to "
              "fix it if this is not the right component.",
        "es": "Cableado I2C **supuesto** para «{name}»: el código usa el bus "
              "I2C pero no indica cómo se conecta este componente. Comprueba "
              "VCC/GND/SDA/SCL en su documentación; corrígelo con el engranaje "
              "si no es el componente correcto.",
        "it": "Cablaggio I2C **presunto** per «{name}»: il codice usa il bus "
              "I2C ma non dice come questo componente vi si collega. Verifica "
              "VCC/GND/SDA/SCL sulla sua documentazione; correggilo con "
              "l'ingranaggio se non è il componente giusto.",
    },
    "shield_not_drawable": {
        "fr": "**{name} détecté.** Un shield se monte **directement sur les "
              "broches de la carte** : il n'y a aucun fil à dessiner entre les "
              "deux. Branche tes moteurs sur les bornes du shield (M1 à M4) et "
              "son alimentation sur son bornier dédié, en te reportant à sa "
              "documentation.",
        "en": "**{name} detected.** A shield plugs **straight onto the board's "
              "headers**: there is no wire to draw between the two. Connect "
              "your motors to the shield's terminals (M1 to M4) and its power "
              "to its own screw terminal, following its documentation.",
        "es": "**{name} detectado.** Un shield se monta **directamente sobre "
              "los pines de la placa**: no hay ningún cable que dibujar entre "
              "ambos. Conecta tus motores a los bornes del shield (M1 a M4) y "
              "su alimentación a su propio borne, según su documentación.",
        "it": "**{name} rilevato.** Uno shield si monta **direttamente sui pin "
              "della scheda**: non c'è alcun filo da disegnare tra i due. "
              "Collega i motori ai morsetti dello shield (da M1 a M4) e "
              "l'alimentazione al suo morsetto dedicato, seguendo la sua "
              "documentazione.",
    },
    "nothing_detected": {
        "fr": "**Aucun composant n'a pu être déduit de ce code**, alors qu'il "
              "utilise « {header} ». Le schéma est vide parce que la lecture a "
              "échoué, pas parce qu'il n'y a rien à brancher. Reporte-toi à la "
              "documentation de ton composant, ou demande de l'aide dans le chat.",
        "en": "**No component could be inferred from this code**, although it "
              "uses “{header}”. The diagram is empty because the reading "
              "failed, not because there is nothing to wire. Check your "
              "component's documentation, or ask for help in the chat.",
        "es": "**No se ha podido deducir ningún componente de este código**, "
              "aunque usa «{header}». El esquema está vacío porque la lectura "
              "falló, no porque no haya nada que conectar. Consulta la "
              "documentación de tu componente o pide ayuda en el chat.",
        "it": "**Nessun componente è stato dedotto da questo codice**, anche se "
              "usa «{header}». Lo schema è vuoto perché la lettura è fallita, "
              "non perché non ci sia nulla da collegare. Consulta la "
              "documentazione del tuo componente o chiedi aiuto in chat.",
    },
    "undrawable_component": {
        "fr": "Composant « {name} » ({pins} broches) détecté dans le code mais "
              "**absent du schéma** : aucun dessin disponible pour ce nombre "
              "de broches. Câble-le en te reportant à sa documentation.",
        "en": "Component “{name}” ({pins} pins) detected in the code but "
              "**missing from the diagram**: no drawing available for that pin "
              "count. Wire it using its documentation.",
        "es": "Componente «{name}» ({pins} pines) detectado en el código pero "
              "**ausente del esquema**: no hay dibujo disponible para ese "
              "número de pines. Cablealo consultando su documentación.",
        "it": "Componente «{name}» ({pins} pin) rilevato nel codice ma "
              "**assente dallo schema**: nessun disegno disponibile per questo "
              "numero di pin. Collegalo consultando la sua documentazione.",
    },
    "unwired_component_pins": {
        "fr": "Broches à câbler toi-même selon ton montage : {pins}. "
              "Le logiciel ne peut pas deviner ce qu'elles pilotent.",
        "en": "Pins to wire yourself depending on your build: {pins}. "
              "The software cannot guess what they drive.",
        "es": "Pines que debes cablear según tu montaje: {pins}. "
              "El software no puede adivinar qué controlan.",
        "it": "Pin da collegare secondo il tuo montaggio: {pins}. "
              "Il software non può indovinare cosa pilotano.",
    },
    "too_many_dc_motors": {
        "fr": "{count} moteurs DC détectés. PromptuinoUI se limite à "
              "**2 moteurs DC maximum** (tous les drivers catalogués "
              "L298N / L293D / TB6612FNG / DRV8833 sont des dual H-bridges, "
              "1 chip = 2 moteurs). Pour piloter plus de moteurs, utilisez "
              "un shield dédié ou parallélisez plusieurs moteurs sur les "
              "mêmes sorties driver.",
        "en": "{count} DC motors detected. PromptuinoUI supports up to "
              "**2 DC motors maximum** (all catalogued drivers L298N / "
              "L293D / TB6612FNG / DRV8833 are dual H-bridges, 1 chip = "
              "2 motors). For more motors, use a dedicated shield or "
              "parallel several motors on the same driver outputs.",
        "es": "{count} motores DC detectados. PromptuinoUI se limita a "
              "**2 motores DC como máximo** (todos los drivers catalogados "
              "L298N / L293D / TB6612FNG / DRV8833 son puentes en H "
              "duales, 1 chip = 2 motores). Para más motores, utilice un "
              "shield dedicado o paralelice varios motores en las mismas "
              "salidas del driver.",
        "it": "{count} motori DC rilevati. PromptuinoUI è limitato a "
              "**2 motori DC al massimo** (tutti i driver catalogati "
              "L298N / L293D / TB6612FNG / DRV8833 sono ponti H duali, "
              "1 chip = 2 motori). Per più motori, utilizzare uno shield "
              "dedicato o parallelizzare più motori sulle stesse uscite "
              "del driver.",
    },
}


# ─── Public API ───────────────────────────────────────────────────────
def render_instructions(netlist: Netlist, mode: str = "simple",
                        lang: str = "fr") -> str:
    """Returns a markdown describing the wiring.

    Args:
        netlist : enriched netlist (cf. wiring_pipeline).
        mode    : "simple" or "detailed".
        lang    : "fr", "en", "es" or "it". Any other value falls back
                  to "fr".
    """
    if lang not in _LANGS:
        lang = "fr"
    if mode not in ("simple", "detailed"):
        mode = "simple"

    if not netlist.components:
        return _SECTION_TITLES["no_components"][lang]

    parts: list[str] = []

    # Grouping by feature.
    groups: dict[str, list[Component]] = {}
    order: list[str] = []
    for c in netlist.components:
        key = c.fn_id or ""
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(c)

    for key in order:
        title = _group_title(key, lang)
        parts.append(f"## {title}\n")
        for i, comp in enumerate(groups[key], start=1):
            parts.append(_render_step(i, comp, netlist, mode, lang))
        parts.append("")

    if netlist.warnings:
        parts.append(f"## {_SECTION_TITLES['warnings'][lang]}\n")
        for w in netlist.warnings:
            # `info` porte le meme ⚠️ que `warning` (decision utilisateur
            # 2026-08-10). Tout ce qui atterrit dans cette section demande un
            # coup d'oeil — les filets d'honnetete du detecteur y sont tous en
            # `info`, alors qu'ils disent « l'app a devine ici ». Un ℹ️ les
            # faisait passer pour de la decoration, et il ne correspondait a
            # rien a l'ecran : la PASTILLE posee sur le composant, elle, est un
            # symbole d'attention. Deux glyphes pour le meme fait, c'etait le
            # schema qui se contredisait lui-meme.
            icon = {
                SEVERITY_ERROR:   "❌",
                SEVERITY_WARNING: "⚠️",
                SEVERITY_INFO:    "⚠️",
            }.get(w.severity, "•")
            parts.append(f"- {icon} {_render_warning_message(w, lang)}")

    # Dedicated section for the motors marked _skip_wiring=True (= recognized
    # in the code but deliberately not wired, typically when the
    # count exceeds the editorial limit of 2 DC motors). The info is
    # stored by `inference._apply_motor_drivers_and_battery` in
    # `netlist.metadata["_skipped_motors"]`.
    skipped = netlist.metadata.get("_skipped_motors") or []
    if skipped:
        parts.append(f"\n## {_SECTION_TITLES['skipped_motors'][lang]}\n")
        parts.append(_SECTION_TITLES['skipped_motors_explainer'][lang])
        parts.append("")
        for m in skipped:
            ctrl = m.get("control_pin", "?")
            dirs = m.get("aux_dir_pins") or []
            dirs_txt = ", ".join(dirs) if dirs else "—"
            parts.append(f"- **{m['ref']}** : broche PWM `{ctrl}`, "
                          f"broches direction `{dirs_txt}`")

    return "\n".join(parts).strip() + "\n"


# ─── Internals ───────────────────────────────────────────────────────────
def _group_title(fn_id: str, lang: str) -> str:
    if not fn_id:
        return _SECTION_TITLES["components"][lang]
    n = fn_id.split("-", 1)[-1] if "-" in fn_id else fn_id
    return f"{_SECTION_TITLES['feature'][lang]} {n}"


# Localized names of the LED colours. Keys MUST match `_LED_COLOR_KEYWORDS`
# in markers.py -- that map is what writes `attributes["color"]`, and it only
# ever writes one of these six. An unknown value falls through to the raw
# stored string rather than being dropped: better an untranslated word than a
# silently missing one.
_LED_COLOR_LABEL: dict[str, dict[str, str]] = {
    "red":    {"fr": "rouge",  "en": "red",    "es": "roja",     "it": "rosso"},
    "green":  {"fr": "verte",  "en": "green",  "es": "verde",    "it": "verde"},
    "blue":   {"fr": "bleue",  "en": "blue",   "es": "azul",     "it": "blu"},
    "yellow": {"fr": "jaune",  "en": "yellow", "es": "amarilla", "it": "giallo"},
    "white":  {"fr": "blanche", "en": "white", "es": "blanca",   "it": "bianco"},
    "orange": {"fr": "orange", "en": "orange", "es": "naranja",  "it": "arancione"},
}


def _led_color(comp, lang: str) -> str:
    """Colour word for this LED in `lang`, or "" when it has none."""
    raw = (comp.attributes.get("color") or "").strip().lower()
    if not raw:
        return ""
    entry = _LED_COLOR_LABEL.get(raw)
    if entry is None:
        return raw
    return entry.get(lang) or entry.get("fr") or raw


def _label(comp_type: str, lang: str) -> str:
    from ..declared_components import TYPE_PREFIX
    if comp_type.startswith(TYPE_PREFIX):
        from ..declared_components import find_by_type
        decl = find_by_type(comp_type)
        if decl is not None:
            return decl.name
    entry = _TYPE_LABEL.get(comp_type, {})
    return entry.get(lang) or entry.get("fr") or comp_type


def _role(role: str, lang: str) -> str:
    entry = _ROLE_LABEL.get(role.lower(), {})
    return entry.get(lang) or ""


# Warnings dont un parametre porte un ID de type et doit s'afficher traduit.
# Volontairement une table et non une regle sur le nom du parametre : la
# plupart des `{name}` du fichier portent deja un texte humain (le nom d'une
# bibliotheque, celui d'une fiche declaree), et les traduire les casserait.
_WARNING_PARAMS_TO_LABEL = {"presumed_from_description": "name"}


def _render_warning_message(w, lang: str) -> str:
    """Localizes a warning via its code + params.

    If the code is unknown, falls back to the raw `message` (FR debug).
    """
    template = _WARNING_TEMPLATES.get(w.code, {}).get(lang)
    if not template:
        # Fallback: raw FR message (the Warning's `message` field).
        return getattr(w, "message", "") or w.code
    params = dict(w.params or {})
    # `markers` ne connait pas la langue : il pose l'ID du type et c'est ICI
    # qu'il devient un nom lisible. Sans ca l'aveu disait « rcwl0516 » a
    # l'utilisateur, c'est-a-dire un slug interne pour parler d'un composant
    # dont on lui demande justement de verifier l'identite.
    if w.code in _WARNING_PARAMS_TO_LABEL:
        cle = _WARNING_PARAMS_TO_LABEL[w.code]
        if params.get(cle):
            params[cle] = _label(str(params[cle]), lang)
    try:
        return template.format(**params)
    except KeyError:
        return getattr(w, "message", "") or w.code


def _render_step(idx: int, comp: Component, netlist: Netlist,
                  mode: str, lang: str) -> str:
    base = _render_step_simple(idx, comp, netlist, lang)
    if mode == "simple":
        return base
    explanation = _explanation_for(comp, lang)
    if not explanation:
        return base
    return f"{base}\n   _{explanation}_"


# ─── Humanization of internal "NET_*" nets ─────────────────────────────
# The inference rules create bridge nets between two components
# (e.g. LED.A ↔ R.B for the series R of a LED). Displayed as-is, these
# "NET_A"/"NET_B" lose a beginner. We replace them with a reference
# to the companion component ("cote R1" in FR), or with the Arduino pin
# located at the end of the bridge chain if it can be resolved.

def _humanize_net(net: str, netlist: Netlist | None,
                   exclude_ref: str, lang: str) -> str:
    """For `NET_*` nets, returns a user-friendly phrase ("cote R1")
    or the real Arduino pin at the end of the bridge (D6, 5V, ...). For all
    other nets, returns the net as-is.
    """
    if not net.startswith("NET_") or netlist is None:
        return net
    # 1st attempt: follow the chain of 2-pin bridges (series R/pullup, jumper)
    # up to an Arduino pin/rail.
    end_pin = _resolve_bridge_end(net, netlist, exclude_ref)
    if end_pin is not None:
        return end_pin
    # 2nd attempt: name the companion component by its type + ref
    # + the specific pin it shares on this bridge. The ref disambiguates the
    # multi-instance cases (e.g.: 2 DC motors -> "OUT1 on DC motor M1 side"
    # vs "OUT1 on DC motor M2 side"), at the cost of a bit more verbosity
    # in the mono-instance case.
    for c in netlist.components:
        if c.ref == exclude_ref:
            continue
        for p in c.pins:
            if p.net != net:
                continue
            type_label = _label(c.type, lang)
            if lang == "en":
                return f"{p.name} on the {type_label} {c.ref}"
            if lang == "es":
                return f"{p.name} lado del {type_label} {c.ref}"
            if lang == "it":
                return f"{p.name} lato del {type_label} {c.ref}"
            return f"{p.name} côté {type_label} {c.ref}"
    return net


def _resolve_bridge_end(net: str, netlist: Netlist,
                         source_ref: str) -> str | None:
    """Follows the chain of NET_* bridges through the 2-pin components
    (series R/pullup, jumper) until landing on a non-`NET_*` pin
    (= Arduino pin, rail, battery). Returns that net, or None if the
    chain does not resolve (multi-pin component or more than 5 hops).

    Restriction to 2-pins: for a component with N>2 pins, there is no
    "naturally opposite" pin on the bridge -- we return None to
    let the caller use the "cote <ref>" fallback.
    """
    visited_refs = {source_ref}
    current_net = net
    for _ in range(5):
        bridge_comp = None
        for c in netlist.components:
            if c.ref in visited_refs:
                continue
            if len(c.pins) != 2:
                continue   # only use the 2-pins as bridges
            if any(p.net == current_net for p in c.pins):
                bridge_comp = c
                break
        if bridge_comp is None:
            return None
        # Opposite pin in this 2-pin.
        other = next(p for p in bridge_comp.pins if p.net != current_net)
        if not other.net.startswith("NET_"):
            return other.net
        visited_refs.add(bridge_comp.ref)
        current_net = other.net
    return None


_AND_WORD = {"fr": " et ", "en": " and ", "es": " y ", "it": " e "}
_OR_WORD = {"fr": "ou", "en": "or", "es": "o", "it": "o"}

# An I2C bus pin has TWO holes on an Uno: the dedicated SDA/SCL header and
# A4/A5 -- same net, different places on the board. The netlist names the net
# A4/A5, but the router hands each consumer a distinct physical hole and takes
# the dedicated header first (`_I2C_PHYSICAL_PINS_FOR_BUS`, routing/router.py),
# so the schematic showed a wire landing on "SDA" while the instructions said
# "A4" (QA 2026-08-08). Naming BOTH is true whichever hole the router picked,
# and teaches a beginner that the two are the same pin.
#
# SOURCE UNIQUE de la correspondance bus I2C <-> net nommé par `markers`.
# Deux endroits en dépendent (les instructions ci-dessous et le formulaire de
# déclaration, `declare_component_dialog`) : la définir deux fois les ferait
# diverger le jour où une carte change.
I2C_BUS_NET = {"SDA": "A4", "SCL": "A5"}

# Keyed by (component pin name, net): only a pin the component itself calls
# SDA/SCL gets the alias. An analog input wired to A4 stays "A4".
_I2C_NET_ALIAS = {(bus, net): bus for bus, net in I2C_BUS_NET.items()}


def i2c_alias_for_net(net: str) -> str | None:
    """Bus name of a board net that also carries I2C ("A4" -> "SDA"), or None.

    Unconditional, unlike `_I2C_NET_ALIAS`: the question here is "what else is
    this hole called on the board?", not "what is this component's pin doing?"
    """
    up = (net or "").strip().upper()
    return next((bus for bus, n in I2C_BUS_NET.items() if n == up), None)


def _board_pin_label(pin, hn, lang: str) -> str:
    """Board hole(s) to name for `pin`, humanised, markdown included."""
    net = hn(pin.net)
    alias = _I2C_NET_ALIAS.get(((pin.name or "").upper(),
                                (pin.net or "").upper()))
    if not alias or alias == net:
        return f"**{net}**"
    return f"**{alias}** ({_OR_WORD[lang]} **{net}**)"


# Definite articles for the types whose gender/elision is not "le" in
# FR (masculine default) -- same idea for ES (el) and IT (il). For the
# other types, the function falls back to each language's masculine default.
_TYPE_ARTICLE: dict[str, dict[str, str]] = {
    "battery_external": {"fr": "la", "es": "la", "it": "la"},
    "ds1307":           {"fr": "l'", "es": "el", "it": "l'"},
    "ds3231":           {"fr": "l'", "es": "el", "it": "l'"},
    "neopixel":         {"fr": "la", "es": "la", "it": "la"},
    "ili9341":          {"fr": "l'", "es": "la", "it": "lo"},
    "encoder":          {"fr": "l'", "es": "el", "it": "l'"},
}


def _article(comp_type: str, lang: str) -> str:
    """Definite article in FR/ES/IT (always 'the' in EN, handled by
    template). Default: le/el/il (masculine)."""
    entry = _TYPE_ARTICLE.get(comp_type, {})
    if lang in entry:
        return entry[lang]
    return {"fr": "le", "es": "el", "it": "il"}.get(lang, "")


def _render_step_simple(idx: int, comp: Component,
                         netlist: Netlist | None, lang: str) -> str:
    label = _label(comp.type, lang)

    def hn(net: str) -> str:
        return _humanize_net(net, netlist, comp.ref, lang)

    if comp.type == "resistor":
        value = comp.attributes.get("value") or "?"
        role  = _role(comp.attributes.get("role") or "", lang)
        nets_str = _AND_WORD[lang].join(hn(p.net) for p in comp.pins) or "?"
        suffix = f" ({role})" if role else ""
        if lang == "en":
            return (f"{idx}. Place a {label} **{comp.ref}** of **{value}Ω**"
                    f"{suffix} between **{nets_str}**.")
        if lang == "es":
            return (f"{idx}. Coloca una {label} **{comp.ref}** de **{value}Ω**"
                    f"{suffix} entre **{nets_str}**.")
        if lang == "it":
            return (f"{idx}. Posiziona una {label} **{comp.ref}** da **{value}Ω**"
                    f"{suffix} tra **{nets_str}**.")
        return (f"{idx}. Place une {label} **{comp.ref}** de **{value}Ω**"
                f"{suffix} entre **{nets_str}**.")

    if comp.type == "led":
        # Localized colour word, empty when the LED has no colour -- which is
        # the NORMAL case: only the user's prompt can name one (cf. the
        # `color` annotation in markers). Before 2026-07-30 every LED was
        # forced to "red", so a French instruction read "LED red D1": wrong
        # colour AND wrong language.
        color = _led_color(comp, lang)
        anode = hn(next((p.net for p in comp.pins if p.name == "A"), "?"))
        cath  = hn(next((p.net for p in comp.pins if p.name == "K"), "?"))
        if lang == "en":
            # Adjective BEFORE the noun in English, after it elsewhere.
            prefix = f"{color} " if color else ""
            return (f"{idx}. Wire the **{prefix}LED {comp.ref}**: "
                    f"anode (long leg) → **{anode}**, "
                    f"cathode (short leg, flat side) → **{cath}**.")
        suffix = f" {color}" if color else ""
        if lang == "es":
            return (f"{idx}. Conecta el **LED{suffix} {comp.ref}**: "
                    f"ánodo (pata larga) → **{anode}**, "
                    f"cátodo (pata corta, lado plano) → **{cath}**.")
        if lang == "it":
            return (f"{idx}. Collega il **LED{suffix} {comp.ref}**: "
                    f"anodo (gamba lunga) → **{anode}**, "
                    f"catodo (gamba corta, lato piatto) → **{cath}**.")
        return (f"{idx}. Branche la **LED{suffix} {comp.ref}** : "
                f"anode (patte longue) → **{anode}**, "
                f"cathode (patte courte, côté plat) → **{cath}**.")

    if comp.type == "button":
        a = hn(next((p.net for p in comp.pins if p.name == "A"), "?"))
        b = hn(next((p.net for p in comp.pins if p.name == "B"), "?"))
        if lang == "en":
            return (f"{idx}. Wire the **{label} {comp.ref}** between "
                    f"**{a}** and **{b}**.")
        if lang == "es":
            return (f"{idx}. Conecta el **{label} {comp.ref}** entre "
                    f"**{a}** y **{b}**.")
        if lang == "it":
            return (f"{idx}. Collega il **{label} {comp.ref}** tra "
                    f"**{a}** e **{b}**.")
        return (f"{idx}. Branche le **{label} {comp.ref}** entre "
                f"**{a}** et **{b}**.")

    # General case: pins as bullets. FR/ES/IT article from _TYPE_ARTICLE
    # (masculine default) with FR elision ("l'encodeur") without a space after.
    art = _article(comp.type, lang)
    sep = "" if art.endswith("'") else " "
    if lang == "en":
        head = f"{idx}. Wire the **{label} {comp.ref}**:"
    elif lang == "es":
        head = f"{idx}. Conecta {art}{sep}**{label} {comp.ref}**:"
    elif lang == "it":
        head = f"{idx}. Collega {art}{sep}**{label} {comp.ref}**:"
    else:
        head = f"{idx}. Branche {art}{sep}**{label} {comp.ref}** :"
    bullets = [f"   - **{p.name}** → {_board_pin_label(p, hn, lang)}"
               for p in comp.pins]
    return "\n".join([head, *bullets])


def _explanation_for(comp: Component, lang: str) -> str:
    """Returns the pedagogical justification for this component, or ""."""
    role = (comp.attributes.get("role") or "").lower()

    if comp.type == "resistor":
        if role == "series":
            return _EXPLANATIONS["led_series"][lang]
        if role == "pullup":
            return _EXPLANATIONS["button_pullup"][lang]
        if role == "pulldown":
            return _EXPLANATIONS["button_pulldown"][lang]
        return ""

    if comp.type == "led":
        return _EXPLANATIONS["led_anode"][lang]
    if comp.type == "button":
        return _EXPLANATIONS["button"][lang]
    if comp.type in ("dht22", "dht11"):
        return _EXPLANATIONS["module_3_pins"][lang]
    if comp.type == "hcsr04":
        return _EXPLANATIONS["hcsr04"][lang]
    if comp.type == "servo":
        return _EXPLANATIONS["servo"][lang]
    if comp.type in ("lcd_i2c", "oled_ssd1306"):
        return _EXPLANATIONS["i2c"][lang]
    return ""

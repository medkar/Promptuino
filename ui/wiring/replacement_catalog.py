"""Curated catalog of components proposable for replacement (SP3).

Source: scrape of Fritzing core. Tier-1 (bus/ultrasonic, high confidence) +
Tier-2 (bare pin single_output/analog_in/digital_in, aggressive dedup of
mechanical duplicates + correction of the scrape's input/output cross-talk). Curated
manually (DROP junk/dev-kits, MERGE multi-view duplicates, SKIP collisions
already present in CATEGORY_OF_TYPE). See
docs/superpowers/specs/2026-06-15-component-replace-sp3-design.md.

Additive layer: imports NOTHING from categories.py (categories as literals to
break the import cycle ; a drift test locks the consistency). Feeds
CATEGORY_OF_TYPE (proposal) and the label resolution of the dropdown/tiles.

display_name = cleaned-up Fritzing title + short FR descriptor. The other
three languages live in `_OTHER_LANGS` (TODO #124, 2026-11-07): the table was
long documented as "language-neutral, proper nouns", but 48 of its 60 labels
carry a French descriptor (« (baromètre) », « Haut-parleur »), so English,
Spanish and Italian users read French in the picker and on the cards.
"""
from __future__ import annotations

# (type_id, category, display_name). category = literal, validated by
# test_catalog_categories_match_constants against the categories.py constants.
REPLACEMENT_CATALOG: list[tuple[str, str, str]] = [
    # --- I2C (26) ---
    ("adxl345", "i2c", "ADXL345 (accéléromètre)"),
    ("mma8452q", "i2c", "MMA8452Q (accéléromètre)"),
    ("sensor_stick_9dof", "i2c", "Sensor Stick 9DOF"),
    ("mpl3115a2", "i2c", "MPL3115A2 (altimètre/baromètre)"),
    ("bmp085", "i2c", "BMP085 (baromètre)"),
    ("bmp180", "i2c", "BMP180 (baromètre)"),
    ("adjd_s311", "i2c", "ADJD-S311 (capteur de couleur)"),
    ("hmc6352", "i2c", "HMC6352 (boussole)"),
    ("hmc5883", "i2c", "HMC5883L (magnétomètre)"),
    ("tmp102", "i2c", "TMP102 (température)"),
    ("ds1307", "i2c", "DS1307 (horloge RTC)"),
    ("ds3231", "i2c", "DS3231 (horloge RTC précise)"),
    ("grove_3axis_accel", "i2c", "Grove accéléromètre 3 axes"),
    ("grove_oled_128x96", "i2c", "Grove OLED 128×96"),
    ("sht15", "i2c", "SHT15 (température/humidité)"),
    ("sht25", "i2c", "SHT25 (température/humidité)"),
    ("imu_6dof", "i2c", "IMU 6DOF (combo)"),
    ("itg3200", "i2c", "ITG-3200 (gyroscope)"),
    ("l3g4200d", "i2c", "L3G4200D (gyroscope)"),
    ("lsm303", "i2c", "LSM303 (boussole/accéléromètre)"),
    ("mag3110", "i2c", "MAG3110 (magnétomètre)"),
    ("max1704x", "i2c", "MAX1704x (jauge batterie LiPo)"),
    ("mlx90614", "i2c", "MLX90614 (thermomètre IR)"),
    ("mpu9250", "i2c", "MPU-9250 (IMU 9 axes)"),
    ("pcf8574", "i2c", "PCF8574 (expandeur E/S)"),
    ("vcnl4000", "i2c", "VCNL4000 (proximité/lumière)"),
    ("mpr121", "i2c", "MPR121 (contrôleur tactile capacitif)"),  # Tier-2: recat from digital_in (true I2C)
    # --- SPI (8) ---
    ("ds3234", "spi", "DS3234 (horloge RTC SPI)"),
    ("led_matrix_rgb_spi", "spi", "Matrice LED RGB (série)"),
    ("max6675", "spi", "MAX6675 (thermocouple type K)"),
    ("mcp41xxx", "spi", "MCP41xxx (potentiomètre numérique)"),
    ("mcp42xxx", "spi", "MCP42xxx (double potentiomètre numérique)"),
    ("microsd_card_module", "spi", "Module carte microSD"),
    ("nrf24l01", "spi", "nRF24L01 (radio 2.4 GHz)"),
    ("wiz820io", "spi", "WIZ820io (Ethernet)"),
    # --- UART (6) ---
    ("hc05", "uart", "HC-05 (Bluetooth)"),
    ("gps_em406", "uart", "GPS EM-406"),
    ("ftdi_basic", "uart", "FTDI Basic (USB-série)"),
    ("openlog", "uart", "OpenLog (enregistreur série)"),
    ("atlas_ph", "uart", "Circuit pH (Atlas)"),
    ("thermal_printer", "uart", "Imprimante thermique"),
    # --- ULTRASONIC (1) ---
    ("us100", "ultrasonic", "US-100 (capteur ultrason)"),
    # =================================================================
    # TIER-2 — bare pin (aggressive dedup: 256 scrape entries → distinct).
    # Wiring keep-pins safe (intra-category replacement keeps signal+GND).
    # =================================================================
    # --- SINGLE_OUTPUT (3) ---
    ("rgb_led", "single_output", "LED RGB"),
    ("speaker", "single_output", "Haut-parleur"),
    ("passive_buzzer", "single_output", "Buzzer passif"),
    # ⛔ Le solenoide (300 mA a 1 A) n'est PAS ici : decision de l'auteur
    # (CLAUDE.md). Pair d'echange d'une LED, il aurait ete cable en direct sur
    # la broche, sans transistor ni diode de roue libre.
    # --- ANALOG_IN (8) ---
    ("light_sensor", "analog_in", "Capteur de lumière (TEMT6000)"),
    ("soil_moisture", "analog_in", "Capteur d'humidité du sol"),
    ("load_cell", "analog_in", "Cellule de charge (jauge)"),
    ("joystick", "analog_in", "Joystick analogique"),
    ("acs712", "analog_in", "Capteur de courant ACS712"),
    ("force_sensor", "analog_in", "Capteur de force (FSR)"),
    ("slider", "analog_in", "Potentiomètre à glissière"),
    # --- DIGITAL_IN (7) ---
    ("toggle_switch", "digital_in", "Interrupteur à bascule"),
    ("slide_switch", "digital_in", "Interrupteur à glissière"),
    ("tilt_switch", "digital_in", "Capteur d'inclinaison (tilt)"),
    ("reed_switch", "digital_in", "Interrupteur reed (magnétique)"),
    ("dip_switch", "digital_in", "Interrupteur DIP"),
    ("buttonpad", "digital_in", "Pavé de boutons"),
    ("touch_sensor", "digital_in", "Capteur tactile capacitif"),
    # TODO #98 (2026-09-08) : passe de `analog_in` a `digital_in`. Il
    # etait range parmi les analogiques a une epoque ou AUCUN de ces
    # types n'etait emis par `markers.py` -- la categorie satisfaisait
    # un garde-fou, elle ne decrivait pas un usage. Il est emis depuis
    # ce ticket, et il l'est en tout-ou-rien (A3144, KY-003).
    ("hall_sensor", "digital_in", "Capteur à effet Hall"),
]

_LABEL_BY_TYPE: dict[str, str] = {t: lbl for t, _c, lbl in REPLACEMENT_CATALOG}

# type_id -> (en, es, it). The French label stays in REPLACEMENT_CATALOG.
# `test_every_catalog_entry_is_translated` reddens if an entry is missing.
_OTHER_LANGS: dict[str, tuple[str, str, str]] = {
    "adxl345": ("ADXL345 (accelerometer)", "ADXL345 (acelerómetro)", "ADXL345 (accelerometro)"),
    "mma8452q": ("MMA8452Q (accelerometer)", "MMA8452Q (acelerómetro)", "MMA8452Q (accelerometro)"),
    "sensor_stick_9dof": ("Sensor Stick 9DOF", "Sensor Stick 9DOF", "Sensor Stick 9DOF"),
    "mpl3115a2": ("MPL3115A2 (altimeter/barometer)", "MPL3115A2 (altímetro/barómetro)", "MPL3115A2 (altimetro/barometro)"),
    "bmp085": ("BMP085 (barometer)", "BMP085 (barómetro)", "BMP085 (barometro)"),
    "bmp180": ("BMP180 (barometer)", "BMP180 (barómetro)", "BMP180 (barometro)"),
    "adjd_s311": ("ADJD-S311 (colour sensor)", "ADJD-S311 (sensor de color)", "ADJD-S311 (sensore di colore)"),
    "hmc6352": ("HMC6352 (compass)", "HMC6352 (brújula)", "HMC6352 (bussola)"),
    "hmc5883": ("HMC5883L (magnetometer)", "HMC5883L (magnetómetro)", "HMC5883L (magnetometro)"),
    "tmp102": ("TMP102 (temperature)", "TMP102 (temperatura)", "TMP102 (temperatura)"),
    "ds1307": ("DS1307 (RTC clock)", "DS1307 (reloj RTC)", "DS1307 (orologio RTC)"),
    "ds3231": ("DS3231 (precise RTC clock)", "DS3231 (reloj RTC preciso)", "DS3231 (orologio RTC preciso)"),
    "grove_3axis_accel": ("Grove 3-axis accelerometer", "Grove acelerómetro de 3 ejes", "Grove accelerometro a 3 assi"),
    "grove_oled_128x96": ("Grove OLED 128×96", "Grove OLED 128×96", "Grove OLED 128×96"),
    "sht15": ("SHT15 (temperature/humidity)", "SHT15 (temperatura/humedad)", "SHT15 (temperatura/umidità)"),
    "sht25": ("SHT25 (temperature/humidity)", "SHT25 (temperatura/humedad)", "SHT25 (temperatura/umidità)"),
    "imu_6dof": ("IMU 6DOF (combo)", "IMU 6DOF (combo)", "IMU 6DOF (combo)"),
    "itg3200": ("ITG-3200 (gyroscope)", "ITG-3200 (giroscopio)", "ITG-3200 (giroscopio)"),
    "l3g4200d": ("L3G4200D (gyroscope)", "L3G4200D (giroscopio)", "L3G4200D (giroscopio)"),
    "lsm303": ("LSM303 (compass/accelerometer)", "LSM303 (brújula/acelerómetro)", "LSM303 (bussola/accelerometro)"),
    "mag3110": ("MAG3110 (magnetometer)", "MAG3110 (magnetómetro)", "MAG3110 (magnetometro)"),
    "max1704x": ("MAX1704x (LiPo fuel gauge)", "MAX1704x (indicador de batería LiPo)", "MAX1704x (indicatore batteria LiPo)"),
    "mlx90614": ("MLX90614 (IR thermometer)", "MLX90614 (termómetro IR)", "MLX90614 (termometro IR)"),
    "mpu9250": ("MPU-9250 (9-axis IMU)", "MPU-9250 (IMU de 9 ejes)", "MPU-9250 (IMU a 9 assi)"),
    "pcf8574": ("PCF8574 (I/O expander)", "PCF8574 (expansor de E/S)", "PCF8574 (espansore I/O)"),
    "vcnl4000": ("VCNL4000 (proximity/light)", "VCNL4000 (proximidad/luz)", "VCNL4000 (prossimità/luce)"),
    "mpr121": ("MPR121 (capacitive touch controller)", "MPR121 (controlador táctil capacitivo)", "MPR121 (controller touch capacitivo)"),
    "ds3234": ("DS3234 (SPI RTC clock)", "DS3234 (reloj RTC SPI)", "DS3234 (orologio RTC SPI)"),
    "led_matrix_rgb_spi": ("RGB LED matrix (serial)", "Matriz LED RGB (serie)", "Matrice LED RGB (seriale)"),
    "max6675": ("MAX6675 (type K thermocouple)", "MAX6675 (termopar tipo K)", "MAX6675 (termocoppia tipo K)"),
    "mcp41xxx": ("MCP41xxx (digital potentiometer)", "MCP41xxx (potenciómetro digital)", "MCP41xxx (potenziometro digitale)"),
    "mcp42xxx": ("MCP42xxx (dual digital potentiometer)", "MCP42xxx (potenciómetro digital doble)", "MCP42xxx (doppio potenziometro digitale)"),
    "microsd_card_module": ("microSD card module", "Módulo de tarjeta microSD", "Modulo scheda microSD"),
    "nrf24l01": ("nRF24L01 (2.4 GHz radio)", "nRF24L01 (radio 2,4 GHz)", "nRF24L01 (radio 2,4 GHz)"),
    "wiz820io": ("WIZ820io (Ethernet)", "WIZ820io (Ethernet)", "WIZ820io (Ethernet)"),
    "hc05": ("HC-05 (Bluetooth)", "HC-05 (Bluetooth)", "HC-05 (Bluetooth)"),
    "gps_em406": ("GPS EM-406", "GPS EM-406", "GPS EM-406"),
    "ftdi_basic": ("FTDI Basic (USB-serial)", "FTDI Basic (USB-serie)", "FTDI Basic (USB-seriale)"),
    "openlog": ("OpenLog (serial logger)", "OpenLog (registrador serie)", "OpenLog (registratore seriale)"),
    "atlas_ph": ("pH circuit (Atlas)", "Circuito de pH (Atlas)", "Circuito pH (Atlas)"),
    "thermal_printer": ("Thermal printer", "Impresora térmica", "Stampante termica"),
    "us100": ("US-100 (ultrasonic sensor)", "US-100 (sensor ultrasónico)", "US-100 (sensore a ultrasuoni)"),
    "rgb_led": ("RGB LED", "LED RGB", "LED RGB"),
    "speaker": ("Speaker", "Altavoz", "Altoparlante"),
    "passive_buzzer": ("Passive buzzer", "Zumbador pasivo", "Buzzer passivo"),
    "light_sensor": ("Light sensor (TEMT6000)", "Sensor de luz (TEMT6000)", "Sensore di luce (TEMT6000)"),
    "soil_moisture": ("Soil moisture sensor", "Sensor de humedad del suelo", "Sensore di umidità del terreno"),
    "load_cell": ("Load cell (strain gauge)", "Celda de carga (galga)", "Cella di carico (estensimetro)"),
    "joystick": ("Analog joystick", "Joystick analógico", "Joystick analogico"),
    "acs712": ("ACS712 current sensor", "Sensor de corriente ACS712", "Sensore di corrente ACS712"),
    "force_sensor": ("Force sensor (FSR)", "Sensor de fuerza (FSR)", "Sensore di forza (FSR)"),
    "slider": ("Slide potentiometer", "Potenciómetro deslizante", "Potenziometro a slitta"),
    "toggle_switch": ("Toggle switch", "Interruptor de palanca", "Interruttore a levetta"),
    "slide_switch": ("Slide switch", "Interruptor deslizante", "Interruttore a slitta"),
    "tilt_switch": ("Tilt sensor", "Sensor de inclinación (tilt)", "Sensore di inclinazione (tilt)"),
    "reed_switch": ("Reed switch (magnetic)", "Interruptor reed (magnético)", "Interruttore reed (magnetico)"),
    "dip_switch": ("DIP switch", "Interruptor DIP", "Interruttore DIP"),
    "buttonpad": ("Button pad", "Teclado de botones", "Tastierino a pulsanti"),
    "touch_sensor": ("Capacitive touch sensor", "Sensor táctil capacitivo", "Sensore touch capacitivo"),
    "hall_sensor": ("Hall effect sensor", "Sensor de efecto Hall", "Sensore a effetto Hall"),
}
_LANG_INDEX = {"en": 0, "es": 1, "it": 2}


def merge_into(category_map: dict[str, str]) -> None:
    """Writes each curated entry into category_map (type_id -> category).
    Idempotent. Does NOT overwrite an existing key carrying a different
    category (the known collisions are already SKIP from the table ; this guard
    covers a future drift)."""
    for type_id, category, _label in REPLACEMENT_CATALOG:
        existing = category_map.get(type_id)
        if existing is not None and existing != category:
            continue  # never reclassify an already-mapped type
        category_map[type_id] = category


def label_of(type_id: str, lang: str) -> str | None:
    """Curated human label of a type in `lang` (fr/en/es/it), or None if the
    type is absent from the table.

    `lang` is REQUIRED on purpose: with a default, every caller that forgot it
    showed French in the other three languages -- which is exactly how this
    table stayed French for months. The module stays free of lang_manager:
    the caller knows its language. An unknown code falls back to French.
    """
    fr = _LABEL_BY_TYPE.get(type_id)
    if fr is None:
        return None
    idx = _LANG_INDEX.get(lang)
    if idx is None:
        return fr
    return _OTHER_LANGS.get(type_id, (fr, fr, fr))[idx]

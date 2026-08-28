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

display_name = cleaned-up Fritzing title + short FR descriptor ; proper nouns →
identical FR/EN/ES/IT (no per-language translation).
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
    # --- SINGLE_OUTPUT (4) ---
    ("rgb_led", "single_output", "LED RGB"),
    ("speaker", "single_output", "Haut-parleur"),
    ("passive_buzzer", "single_output", "Buzzer passif"),
    ("solenoid", "single_output", "Solénoïde"),
    # --- ANALOG_IN (8) ---
    ("light_sensor", "analog_in", "Capteur de lumière (TEMT6000)"),
    ("soil_moisture", "analog_in", "Capteur d'humidité du sol"),
    ("hall_sensor", "analog_in", "Capteur à effet Hall"),
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
]

_LABEL_BY_TYPE: dict[str, str] = {t: lbl for t, _c, lbl in REPLACEMENT_CATALOG}


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


def label_of(type_id: str) -> str | None:
    """Curated human label of a type, or None if absent from the table."""
    return _LABEL_BY_TYPE.get(type_id)

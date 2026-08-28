"""One identity per component.

A component did not exist as an object anywhere in this app. It was rebuilt on
the fly by four independent join mechanisms that did not know each other, and
that already disagreed (see the spec). This module is the missing object: the
curated set of components the app knows, each pointing at the corpus documents
that describe it.

Pure module: no Qt, and no import of `ui.wiring` -- the wiring catalog holds the
DRAWING (svg, pin labels the router consumes); this registry holds what the
component IS. Without that split the inventory would have to import the wiring
layout package just to learn what a DHT11 is.

The registry is READ-ONLY curated data, hence a Python module rather than JSON:
no parsing, no schema version, no corruption path. Per-user data lives
elsewhere -- declared components in `components.json`, and later the inventory
selection (#8) and the preferred-library override (#39), both keyed by
component id.
"""
from __future__ import annotations

from dataclasses import dataclass

# Closed vocabulary. The corpus `category` field was the seed but NOT the
# source: it carries 16 values including both "Sensor" and "Sensors", plus
# three motor variants. Inheriting that would engrave the mess. The corpus
# keeps its own categories untouched (the chat's BM25 index reads them).
#
# The first pass DID inherit it 1:1 anyway (`Signal Input/Output` -> input,
# `Device Control` -> output, `Display` -> display), which is how a DAC ended
# up under "input" and four displays under two different functions. Curated by
# hand on 2026-07-31; the rule that settles it is WHAT THE COMPONENT DOES, not
# which corpus drawer it was filed in. No test can check that -- a guard
# validates membership in this vocabulary, never the fairness of an
# assignment. So it is written down here instead:
#   - a part that SHOWS something is `display`, whatever the driver chip
#     (TM1637, MAX7219 and HT16K33 all drive digits or a LED matrix);
#   - a DAC OUTPUTS an analog voltage, an ADC READS one -- they are not the
#     same function even though the corpus files both under Signal I/O;
#   - anything whose job is to drive a motor is `motor_driver`, servos and
#     haptic motors included;
#   - a servo IS a motor. A teacher grouping their kit by function looks for
#     it under "motors", not next to the LED (arbitration 2026-07-31).
# Deliberately left half-true: the bidirectional I/O expanders (MCP23017,
# PCF8574) sit in `output`. The vocabulary is closed and short on purpose;
# adding a tenth value for two parts would make everything else pay. Revisit
# if the case multiplies.
FUNCTIONS = (
    "sensor",         # measures the world: temperature, distance, light, gas...
    "display",        # shows something: OLED, LCD, 7-segment, LED matrix
    "input",          # the user acts on it: button, potentiometer, keypad
    "output",         # the app acts on the world: LED, buzzer, relay
    "motor",          # a motor itself, servos included
    "motor_driver",   # what drives a motor
    "communication",  # radio, RFID, IR, GPS, serial bridges
    "storage",        # SD card, EEPROM
    "timing",         # real-time clocks
)

# How the component is physically mounted.
MOUNTINGS = ("breadboard", "off_board", "on_mcu")

# How the component is DRAWN. THREE values, and above all not two: the silent
# absence used to conflate two very different situations, and `resolve_generic`
# draws a rectangle without saying so.
#   known   -- a dedicated footprint in the catalog: the drawing looks like the
#              real part
#   unknown -- drawn by `resolve_generic` as a plain rectangle. The PINOUT is
#              not unknown: `markers.py` wires a DS18B20 correctly, 4.7k
#              pull-up included -- only the drawing is generic. Said out loud,
#              not endured (TODO #41 fills these in).
#   none    -- nothing to wire, by construction (EEPROM: real memory, a real
#              library, but integrated on the board).
WIRING_STATES = ("known", "unknown", "none")

# Catalog types that are structure or a detector fallback, not components
# anyone looks up. The ONLY types allowed to have no registry entry.
NON_COMPONENT_CATALOG_TYPES = frozenset(
    {"resistor", "battery_external", "module_generic"})

# Same idea for the types the WIRING names without them being in the catalog:
# named in `instructions._TYPE_LABEL` yet not components a user could own.
#   uart_module -- the generic fallback for an unidentified serial device, the
#                  `module_generic` of the UART path.
#
# ⚠️ `hw-612` was HERE until 2026-08-18, on the grounds that a module is "one
# box merging several chips, each of which has its own entry". That reasoning
# was wrong at its root: a user OWNS a HW-612 -- one board, one object, one
# component -- and exempting it is what kept the three modules out of the
# "Composants" tab and out of reach of every guard protecting components. The
# proof arrived on its own: GY-80 and GY-85 were added with no human label and
# nothing went red, because the label guard checks against the registry.
#
# Modules are now ordinary components carrying a `contains`. This exemption
# must never take one back: it would silently restore the blind spot.
NON_COMPONENT_WIRING_TYPES = frozenset({"uart_module"})

# Corpus documents that describe NO component -- pure software or a protocol.
# Declared once so the drift guard stays actionable rather than noisy.
#
# The classification is not mechanical, as the EEPROM proved: real memory, a
# real library, but integrated on the board -- a component with nothing to
# wire, not a software entry. What follows has no hardware behind it at all.
#
# `onewire` is NOT here: it is the bus library the DS18B20 needs, listed in
# its own `documents` (task 2) -- exempting it here as well would contradict
# `test_software_only_documents_are_really_software`, which requires an
# exempted document to be referenced by no component.
SOFTWARE_ONLY_DOCUMENTS: frozenset[str] = frozenset({
    "arduinojson",      # JSON serialisation
    "accelstepper",     # drives a stepper -- the component is the motor
    "ntpclient",        # network time
    "pubsubclient",     # MQTT client
    "softwareserial",   # a capability of the board, not a part
})


@dataclass(frozen=True)
class Component:
    id: str                                  # catalog type id where one exists
    function: str                            # one of FUNCTIONS
    mounting: str                            # one of MOUNTINGS
    wiring: str                              # one of WIRING_STATES
    documents: tuple[str, ...] = ()          # corpus ids, ORDERED
    # fr/en/es/it search terms. TWO readers, and the difference matters:
    #   - `component_index.py` -- the "Composants" tab search box. Every
    #     component's keywords are read here.
    #   - `hardware_modules.detect_module` -- ONLY for a component that is
    #     also declared in `hardware_modules.MODULES` (hw-612, gy-80, gy-85).
    #     Those keywords are the silkscreened aliases that let a prompt name
    #     the board.
    # For every OTHER component, these keywords do NOT take part in
    # generation-time prompt matching: `ui/rag.py` recognizes a named chip
    # through `assets/rag/corpus.json` (`prompt_names_a_chip`) or through the
    # live `registry_lookup.lookup_component` search, neither of which reads
    # this field. Written down 2026-08-20 because the bare label "prompt
    # matching" invited exactly the wrong assumption for a full session.
    keywords: tuple[str, ...] = ()
    # Library facts for components with NO corpus document (the corpus must
    # not grow for them -- embeddings are aligned by position). Three states:
    #   lib_name set        -> "known": the verified Arduino library
    #   lib_to_determine    -> "unknown": probably needs one, not verified
    #   neither (default)   -> "none": no library to install (bare pin part)
    lib_name: str = ""
    lib_to_determine: bool = False
    # French one-liner for the card when no corpus document describes it.
    description: str = ""
    # Components carried BY this one -- a breakout board and the chips soldered
    # on it (GY-80 = ADXL345 + L3G4200D + HMC5883L + BMP085). Empty for every
    # ordinary part.
    #
    # Composition is IDENTITY, not drawing: "a GY-80 is a board carrying these
    # four chips" says what the object IS, so it belongs here rather than in
    # the wiring catalog. `ui/hardware_modules.py` READS this instead of
    # re-declaring it -- two lists would drift, and the drift would only show
    # up at generation time.
    #
    # For the user a module is ONE component (they own one board); for the app
    # it is several. Before 2026-08-18 modules lived outside the registry
    # entirely, so they had no identity: absent from the "Composants" tab, and
    # outside the reach of every guard that protects components -- GY-80 and
    # GY-85 were added with no human label and nothing caught it.
    contains: tuple[str, ...] = ()

    @property
    def default_document(self) -> str:
        """The document whose library is used unless told otherwise.

        The ORDER of `documents` carries the default. #39 ("choose your own
        library") will become a per-user preference overriding this order --
        not a schema change.
        """
        return self.documents[0] if self.documents else ""


REGISTRY: tuple[Component, ...] = (
    # -- 65 catalog types (68 minus the 3 non-components): wiring known --
    Component(id="a4988", function="motor_driver", mounting="breadboard", wiring="known", documents=(),
              description="Driver de moteur pas à pas A4988, piloté par deux broches STEP et DIR.",
              keywords=('a4988', 'driver a4988', 'driver pas a pas', 'stepper driver', 'step dir', 'controlador paso a paso', 'driver passo passo')),
    Component(id="ads1115", function="input", mounting="breadboard", wiring="known", documents=('ads1115',), keywords=('ads1115', 'ads1015', 'convertisseur analogique numerique', 'adc i2c', 'analog to digital', 'conversor adc', 'convertitore adc')),
    Component(id="adxl345", function="sensor", mounting="breadboard", wiring="known", documents=('adxl345',), keywords=('adxl345', 'accelerometre 3 axes', "capteur d'acceleration", '3 axis accelerometer', 'acelerometro 3 ejes', 'accelerometro 3 assi')),
    Component(id="aht20", function="sensor", mounting="breadboard", wiring="known", documents=('aht20',), keywords=('aht20', 'aht10', 'temperature humidite', 'temperature humidity', 'sensor temperatura humedad', 'sensore temperatura umidita')),
    Component(id="amg8833", function="sensor", mounting="breadboard", wiring="known", documents=('amg8833',), keywords=('amg8833', 'camera thermique', 'imagerie thermique', 'matrice infrarouge 8x8', '8x8 thermal camera infrared', 'camara termica', 'termocamera')),
    Component(id="apds9960", function="sensor", mounting="breadboard", wiring="known", documents=('apds9960',), keywords=('apds9960', 'capteur de geste', 'gestes de la main', 'proximite', 'gesture sensor', 'hand gesture', 'sensor de gestos', 'sensore di gesti')),
    Component(id="as5600", function="sensor", mounting="breadboard", wiring="known", documents=('as5600',), keywords=('as5600', 'capteur de position magnetique', 'encodeur magnetique rotatif', 'angle de rotation', 'magnetic rotary position sensor', 'sensor de posicion magnetica', 'sensore di posizione magnetica')),
    Component(id="bh1750", function="sensor", mounting="breadboard", wiring="known", documents=('bh1750',), keywords=('bh1750', 'luxmetre', 'lux', 'light sensor i2c', 'luxometro', 'capteur de lumiere i2c', 'sensore di luce')),
    Component(id="bmp280", function="sensor", mounting="breadboard", wiring="known", documents=('bmp280',), keywords=('bmp280', 'capteur de pression', 'pression barometrique', 'altitude', 'barometric pressure', 'pressure sensor', 'sensor de presion', 'sensore di pressione')),
    Component(id="bno055", function="sensor", mounting="breadboard", wiring="known", documents=('bno055',), keywords=('bno055', 'centrale inertielle 9 axes', 'orientation absolue', 'fusion de capteurs imu', '9 dof absolute orientation imu', 'unidad inercial 9 ejes', 'sensore di orientamento 9 assi')),
    Component(id="button", function="input", mounting="breadboard", wiring="known", documents=('onebutton',), keywords=('button', 'push button', 'click', 'double click', 'long press', 'debounce', 'switch', 'input', 'GPIO', 'callback', 'event', 'OneButton')),
    Component(id="buzzer", function="output", mounting="breadboard", wiring="known", documents=('buzzer',), keywords=('buzzer', 'piezo', 'bip', 'biper', 'melodie', 'tone', 'son simple', 'beep', 'zumbador', 'cicalino', 'alarme sonore')),
    Component(id="dc_motor", function="motor", mounting="off_board", wiring="known", documents=('dc_motor',), keywords=('dc motor', 'moteur dc', 'brushed motor', 'motor', 'moteur', 'dc')),
    Component(id="dfplayer", function="output", mounting="breadboard", wiring="known", documents=('dfplayer',), keywords=('dfplayer', 'dfplayer mini', 'module mp3', 'lecteur mp3', 'mp3 player', 'reproductor mp3', 'lettore mp3', 'carte sd audio')),
    Component(id="dht11", function="sensor", mounting="breadboard", wiring="known", documents=('dht-sensor-library',), keywords=('DHT11', 'DHT22', 'DHT21', 'AM2302', 'AM2301', 'DHT temperature humidity', 'DHT22 sensor', 'humidity sensor DHT', 'weather station DHT', 'climate sensor', 'ambient temperature humidity', 'indoor environment DHT')),
    Component(id="dht22", function="sensor", mounting="breadboard", wiring="known", documents=('dht-sensor-library',), keywords=('DHT11', 'DHT22', 'DHT21', 'AM2302', 'AM2301', 'DHT temperature humidity', 'DHT22 sensor', 'humidity sensor DHT', 'weather station DHT', 'climate sensor', 'ambient temperature humidity', 'indoor environment DHT')),
    Component(id="drv2605", function="motor_driver", mounting="breadboard", wiring="known", documents=('drv2605',), keywords=('drv2605', 'moteur de vibration', 'retour haptique', 'vibration haptique', 'haptic motor driver', 'driver de vibracion haptica', 'driver motore aptico')),
    Component(id="drv8833", function="motor_driver", mounting="breadboard", wiring="known", documents=('drv8833',), keywords=('DRV8833', 'DRV8833 IC', 'DRV8833 chip', 'DRV8833 module', 'TI DRV8833', 'Texas Instruments DRV8833', 'avec DRV8833', 'con DRV8833', 'using DRV8833', 'avec un DRV8833', 'con un DRV8833', 'with a DRV8833', 'pilote moteur DRV8833', 'controla motor DRV8833', 'pilota motore DRV8833', 'AIN1 BIN1 DRV8833', 'nSLEEP DRV8833', 'MOSFET H-bridge DRV8833', 'drive two DC motors with a DRV8833', 'drive 2 DC motors with a DRV8833', 'two DC motors DRV8833', 'dual motor DRV8833')),
    Component(id="fingerprint", function="input", mounting="breadboard", wiring="known", documents=('fingerprint',), keywords=('empreinte digitale', "capteur d'empreinte", 'lecteur biometrique', 'fingerprint sensor', 'biometric reader', 'sensor de huella dactilar', 'sensore di impronte digitali')),
    Component(id="hcsr04", function="sensor", mounting="breadboard", wiring="known", documents=('newping',), keywords=('ultrasonic', 'distance', 'HC-SR04', 'SRF05', 'ping', 'echo', 'rangefinder', 'obstacle', 'proximity', 'trigger', 'echo pin', 'level', 'tank')),
    Component(id="hmc5883l", function="sensor", mounting="breadboard", wiring="known", documents=('hmc5883l',), keywords=('hmc5883l', 'magnetometre', 'boussole numerique', 'champ magnetique', 'digital compass magnetometer', 'brujula magnetometro', 'bussola magnetometro')),
    Component(id="ht16k33", function="display", mounting="breadboard", wiring="known", documents=('ht16k33',), keywords=('matrice led i2c', 'backpack', 'ht16k33', 'matrice 8x8 i2c', 'i2c led matrix', 'matriz led i2c')),
    Component(id="hx711", function="sensor", mounting="breadboard", wiring="known", documents=('hx711',), keywords=('hx711', 'cellule de charge', 'load cell', 'balance', 'peser', 'capteur de poids', 'celula de carga', 'cella di carico')),
    Component(id="ina260", function="sensor", mounting="breadboard", wiring="known", documents=('ina260',), keywords=('ina260', 'mesure de courant et tension', 'wattmetre', 'consommation electrique', 'power monitor voltage current', 'sensor de corriente y voltaje', 'sensore corrente tensione')),
    Component(id="l293d", function="motor_driver", mounting="breadboard", wiring="known", documents=('l293d',), keywords=('L293D', 'L293D IC', 'L293D chip', 'L293D module', 'avec L293D', 'con L293D', 'using L293D', 'avec un L293D', 'con un L293D', 'with an L293D', 'pilote moteur L293D', 'controla motor L293D', 'pilota motore L293D', 'shield motor v1 L293D', '16-pin DIP H-bridge L293D', 'flyback diode L293D')),
    Component(id="l293d_module", function="motor_driver", mounting="off_board", wiring="known", documents=(),
              description="Carte à double pont en H L293D, pour deux moteurs à courant continu.",
              keywords=('l293d', 'module l293d', 'double pont en h', 'pont en h', 'h bridge module', 'modulo puente h', 'doppio ponte h')),
    Component(id="l298n", function="motor_driver", mounting="off_board", wiring="known", documents=('l298n',), keywords=('L298N', 'motor driver', 'H-bridge', 'DC motor', 'moteur DC', 'motor DC', 'motore DC', 'robot 2 moteurs', 'robotics kit', 'kit robotique', 'PWM motor', 'controle direction moteur', 'carte L298N', 'modulo L298N', 'pilote moteur', 'starter robot', 'robot educatif', 'kit robot', 'kit de robotica', 'L298N module', 'L298N driver', 'L298N green PCB', 'avec L298N', 'con L298N', 'using L298N')),
    Component(id="lcd_i2c", function="display", mounting="breadboard", wiring="known", documents=('liquidcrystal-i2c',), keywords=('LCD', 'LCD I2C', 'LCD screen', 'character LCD', 'character display', 'alphanumeric LCD', 'ecran LCD', 'afficher sur ecran LCD', 'afficher texte ecran LCD', 'afficher du texte sur LCD', 'pantalla LCD', 'mostrar en pantalla LCD', 'mostrar texto pantalla LCD', 'mostrar texto en LCD', 'schermo LCD', 'mostrare su schermo LCD', 'mostrare testo schermo LCD', 'mostrare testo su LCD', 'show text on LCD screen', 'display text on LCD screen', '16x2 LCD', '20x4 LCD', 'I2C', 'HD44780', 'PCF8574', 'backlight', 'menu', 'readout')),
    Component(id="led", function="output", mounting="breadboard", wiring="known", documents=(),
              description="Diode électroluminescente, allumée par une simple sortie numérique.",
              keywords=('led', 'diode electroluminescente', 'allumer une led', 'turn on an led', 'encender un led', 'accendere un led')),
    Component(id="led_matrix", function="display", mounting="breadboard", wiring="known", documents=('led_matrix',), keywords=('led matrix', 'matrice led', 'afficheur matrice', 'dot matrix', 'matriz led', 'matrice a led', 'max7219', '8x8 led', 'afficheur 8x8')),
    Component(id="max17043", function="sensor", mounting="breadboard", wiring="known", documents=('max17043',), keywords=('max17043', 'max17048', 'jauge de batterie lipo', 'niveau de charge batterie', 'lipo battery fuel gauge', 'medidor de bateria lipo', 'indicatore di carica batteria lipo')),
    Component(id="max30102", function="sensor", mounting="breadboard", wiring="known", documents=('max30102',), keywords=('max30102', 'max30105', 'frequence cardiaque', 'heart rate', 'spo2', 'oximetre', 'pulsioximetro', 'battito cardiaco')),
    Component(id="max31855", function="sensor", mounting="breadboard", wiring="known", documents=('max31855',), keywords=('max31855', 'thermocouple', 'type k', 'capteur de temperature thermocouple', 'termopar', 'termocoppia')),
    Component(id="max6675", function="sensor", mounting="breadboard", wiring="known", documents=('max6675',), keywords=('max6675', 'thermocouple type k', 'sonde de temperature k', 'type k thermocouple', 'high temperature sensor', 'termopar tipo k', 'termocoppia tipo k')),
    Component(id="mcp23017", function="output", mounting="breadboard", wiring="known", documents=('mcp23017',), keywords=('mcp23017', 'expandeur 16 broches', 'expandeur entrees sorties i2c', '16 bit io expander', 'i2c gpio expander', 'expansor de e/s 16 bits', 'espansore io 16 bit')),
    Component(id="mcp4725", function="output", mounting="breadboard", wiring="known", documents=('mcp4725',), keywords=('mcp4725', 'convertisseur numerique analogique', 'dac i2c', 'sortie analogique', 'digital to analog converter dac', 'convertidor digital analogico', 'convertitore digitale analogico')),
    Component(id="mcp9600", function="sensor", mounting="breadboard", wiring="known", documents=('mcp9600',), keywords=('mcp9600', 'amplificateur de thermocouple', 'thermocouple i2c', 'i2c thermocouple amplifier', 'amplificador de termopar i2c', 'amplificatore di termocoppia i2c')),
    Component(id="mcp9808", function="sensor", mounting="breadboard", wiring="known", documents=('mcp9808',), keywords=('mcp9808', 'capteur de temperature precis', 'temperature haute precision', 'precision temperature sensor', 'sensor de temperatura preciso', 'sensore di temperatura preciso')),
    Component(id="mlx90614", function="sensor", mounting="breadboard", wiring="known", documents=('mlx90614',), keywords=('mlx90614', 'thermometre infrarouge', 'temperature sans contact', 'non-contact temperature', 'infrared thermometer', 'termometro infrarrojo', 'termometro a infrarossi')),
    Component(id="nema17", function="motor", mounting="off_board", wiring="known", documents=('nema17',), keywords=('nema17', 'nema 17', 'stepper', 'bipolar', 'moteur pas-a-pas', 'a4988', 'drv8825')),
    Component(id="nrf24l01", function="communication", mounting="breadboard", wiring="known", documents=('nrf24l01',), keywords=('nrf24l01', 'nrf24', 'module radio 2.4ghz', 'emetteur recepteur sans fil', '2.4ghz wireless transceiver', 'radio module', 'modulo de radio inalambrico', 'modulo radio senza fili')),
    Component(id="oled_ssd1306", function="display", mounting="breadboard", wiring="known", documents=('adafruit-ssd1306',), keywords=('OLED', 'OLED screen', 'OLED display', 'SSD1306', 'show text on OLED', 'display text on OLED', 'afficher texte ecran OLED', 'mostrar texto OLED', 'mostrare testo OLED', 'monochrome OLED', 'I2C OLED 0x3C', 'SPI OLED', '128x64 OLED', '128x32 OLED', 'Adafruit GFX', 'pixels graphics', 'OLED menu UI', 'draw shapes on OLED', 'draw circle on OLED', 'draw icon on OLED', 'draw smiley on OLED', 'smiley face on OLED', 'emoji on OLED', 'dessiner sur ecran OLED', 'afficher smiley sur ecran', 'afficher icone sur ecran OLED', 'dibujar smiley en pantalla OLED', 'disegnare smiley su schermo OLED', 'draw bitmap OLED', 'OLED graphics primitives')),
    Component(id="pca9685", function="motor_driver", mounting="breadboard", wiring="known", documents=('pca9685',), keywords=('pca9685', 'driver servo', '16 servos', 'pwm driver', 'controleur de servos', 'driver pwm i2c', 'driver servo i2c')),
    Component(id="pcd8544", function="display", mounting="breadboard", wiring="known", documents=('pcd8544',), keywords=('nokia 5110', 'ecran lcd nokia', 'pcd8544', 'lcd 84x48', 'nokia 5110 lcd display', 'pantalla lcd nokia 5110', 'display lcd nokia 5110')),
    Component(id="pcf8574", function="output", mounting="breadboard", wiring="known", documents=('pcf8574',), keywords=('pcf8574', "expandeur d'entrees sorties", 'expandeur de broches i2c', 'io expander', 'i2c gpio expander', 'expansor de e/s', 'espansore di io')),
    Component(id="pm25", function="sensor", mounting="breadboard", wiring="known", documents=('pm25',), keywords=('pm25', 'pmsa003i', 'capteur de particules fines', "qualite de l'air particules", 'pm2.5 dust air quality', 'sensor de particulas finas', 'sensore di particolato fine')),
    Component(id="pn532", function="communication", mounting="breadboard", wiring="known", documents=('pn532',), keywords=('pn532', 'lecteur nfc', 'rfid 13.56', 'badge nfc', 'nfc reader', 'lector nfc', 'lettore nfc')),
    Component(id="potentiometer", function="input", mounting="breadboard", wiring="known", documents=(),
              description="Potentiomètre rotatif, lu en analogique comme une position.",
              keywords=('potentiometre', 'potentiometer', 'potenciometro', 'potenziometro', 'bouton rotatif', 'reglage analogique')),
    Component(id="scd30", function="sensor", mounting="breadboard", wiring="known", documents=('scd30',), keywords=('scd30', 'capteur de co2', 'dioxyde de carbone', 'co2 ndir', 'carbon dioxide sensor', 'sensor de co2', 'sensore di co2')),
    Component(id="servo", function="motor", mounting="breadboard", wiring="known", documents=('servo',), keywords=('servo', 'motor', 'angle', 'position', 'PWM', 'robotics', 'robot arm', 'pan', 'tilt', 'RC', 'actuator', 'steering', 'rotation')),
    Component(id="sgp30", function="sensor", mounting="breadboard", wiring="known", documents=('sgp30',), keywords=('sgp30', "qualite de l'air", 'composes organiques volatils', 'cov', 'air quality voc', 'calidad del aire', "qualita dell'aria")),
    Component(id="sh1106", function="display", mounting="breadboard", wiring="known", documents=('sh1106',), keywords=('sh1106', 'sh1107', 'ecran oled', 'oled display', 'pantalla oled', 'display oled', 'schermo oled')),
    Component(id="si7021", function="sensor", mounting="breadboard", wiring="known", documents=('si7021',), keywords=('si7021', 'capteur temperature humidite', 'humidite relative', 'temperature humidity sensor', 'sensor de temperatura humedad', 'sensore temperatura umidita')),
    Component(id="sr74hc595", function="output", mounting="breadboard", wiring="known", documents=('sr74hc595',), keywords=('registre a decalage', 'shift register', '74hc595', 'expansion sorties', 'registro de desplazamiento', 'shift register 74hc595')),
    Component(id="ssd1351", function="display", mounting="breadboard", wiring="known", documents=('ssd1351',), keywords=('ssd1351', 'ecran oled couleur', 'oled rgb spi', 'afficheur oled couleur', 'color oled display spi', 'pantalla oled a color', 'display oled a colori')),
    Component(id="st7735", function="display", mounting="breadboard", wiring="known", documents=('st7735',), keywords=('st7735', 'ecran tft', 'tft display', 'ecran couleur', 'pantalla tft', 'display tft', 'ecran spi')),
    Component(id="st7789", function="display", mounting="breadboard", wiring="known", documents=('st7789',), keywords=('st7789', 'ecran tft', 'tft display', 'ecran couleur 240', 'pantalla tft', 'display tft')),
    Component(id="stepper_motor", function="motor", mounting="off_board", wiring="known", documents=('stepper_28byj48', 'stepper'), keywords=('28byj-48', '28byj', 'stepper', 'moteur pas-a-pas', 'uln2003', 'unipolar')),
    Component(id="tb6612fng", function="motor_driver", mounting="breadboard", wiring="known", documents=('sparkfun-tb6612',), keywords=('TB6612FNG', 'TB6612', 'motor driver', 'H-bridge', 'DC motor', 'moteur DC', 'motor DC', 'motore DC', 'controle moteur', 'control motor', 'pilotage moteur', 'robot 2 moteurs', 'PWM speed', 'vitesse moteur', 'balancing robot', 'line follower', 'robot ligne', 'robot suiveur', 'robot equilibrio')),
    Component(id="tcs34725", function="sensor", mounting="breadboard", wiring="known", documents=('adafruit-tcs34725',), keywords=('TCS34725', 'color sensor', 'RGB', 'color', 'lux', 'ambient light', 'color temperature', 'I2C', 'color matching', 'color sorting', 'AMS')),
    Component(id="tm1637", function="display", mounting="breadboard", wiring="known", documents=('tm1637',), keywords=('7 segments', 'afficheur 7 segments', '7-segment', '4 digits', 'tm1637', 'display 7 segmentos', 'display 4 cifre')),
    Component(id="tm1638", function="display", mounting="breadboard", wiring="known", documents=('tm1638',), keywords=('tm1638', 'afficheur et boutons', 'module led and key', 'afficheur 7 segments avec boutons', 'led and key display buttons module', 'modulo de visualizacion y botones', 'modulo display e pulsanti')),
    Component(id="uln2003", function="motor_driver", mounting="off_board", wiring="known", documents=(),
              description="Carte de commande ULN2003, pour moteur pas à pas 28BYJ-48.",
              keywords=('uln2003', 'carte uln2003', 'driver 28byj-48', 'uln2003 driver board', 'placa uln2003', 'scheda uln2003')),
    Component(id="veml6075", function="sensor", mounting="breadboard", wiring="known", documents=('veml6075',), keywords=('veml6075', 'capteur uv', 'indice uv', 'rayonnement ultraviolet', 'uv index sensor', 'sensor uv ultravioleta', 'sensore uv ultravioletto')),
    Component(id="vl53l0x", function="sensor", mounting="breadboard", wiring="known", documents=('vl53l0x',), keywords=('vl53l0x', 'distance laser', 'time of flight', 'tof', 'capteur de distance laser', 'sensor distancia laser', 'sensore distanza')),

    # -- real components with no dedicated footprint yet: drawn generic --
    Component(id="bme280", function="sensor", mounting="breadboard", wiring="known", documents=('adafruit-bme280',), keywords=('BME280', 'BME280 sensor', 'BME280 pressure temperature humidity', 'Bosch BME280', 'barometric pressure sensor BME280', 'BME280 pressure', 'BME280 temperature', 'capteur BME280 pression et temperature', 'lire BME280 pression temperature', 'BME280 presion y temperatura', 'leer BME280 presion temperatura', 'sensor BME280 presion', 'BME280 pressione e temperatura', 'leggere BME280 pressione temperatura', 'sensore BME280 pressione', 'altitude altimeter BME280', 'weather station BME280', 'I2C 0x76 BME280', 'atmospheric environmental sensor', 'VMA335', 'VMA335 BME280 module', 'Velleman VMA335', 'capteur VMA335')),
    Component(id="ds18b20", function="sensor", mounting="breadboard", wiring="known", documents=('dallas-temperature', 'onewire'), keywords=('DS18B20', 'DS18S20', 'DS1822', 'DS18B20 probe', 'DS18B20 sonde', 'DS18B20 sonda', '1-Wire DS18B20', 'OneWire DS18B20', 'lire la temperature avec une sonde DS18B20', 'read temperature with a DS18B20 probe', 'leer temperatura con sonda DS18B20', 'leggere temperatura con sonda DS18B20', 'Dallas Maxim', 'DS18B20 waterproof probe', 'stainless steel DS18B20', 'digital thermometer DS18B20', 'aquarium DS18B20')),
    Component(id="mpu6050", function="sensor", mounting="breadboard", wiring="known", documents=('adafruit-mpu6050',), keywords=('MPU6050', 'IMU', 'accelerometer', 'gyroscope', 'gyro', 'tilt', 'orientation', 'motion', 'vibration', 'balance', 'drone', 'gesture', '6-axis', 'InvenSense')),
    Component(id="mpu9250", function="sensor", mounting="breadboard", wiring="unknown", documents=('mpu9250',), keywords=('mpu9250', 'mpu-9250', 'mpu 9250', 'centrale inertielle 9 axes', 'accelerometre gyroscope magnetometre', 'imu 9 axes', '9 dof', '9 axis imu accel gyro magnetometer', 'boussole', 'compass', 'cap magnetique', 'magnetic heading', 'ak8963', 'unidad inercial 9 ejes', 'sensore inerziale 9 assi')),
    Component(id="ccs811", function="sensor", mounting="breadboard", wiring="unknown", documents=('adafruit-ccs811',), keywords=('CCS811', 'Adafruit CCS811', 'CCS811 module', 'CCS811 chip', 'CCS811 I2C', 'eCO2 TVOC CCS811', 'eCO2', 'TVOC', 'eCO2 ppm', 'TVOC ppb', 'avec CCS811', 'con CCS811', 'using CCS811', 'avec un CCS811', 'con un CCS811', 'CO2 interieur CCS811', 'CO2 interior CCS811', 'CO2 interno CCS811', 'composes organiques volatiles', 'compuestos organicos volatiles', 'composti organici volatili', 'MOX gas sensor', 'indoor air quality CCS811')),
    Component(id="ina219", function="sensor", mounting="breadboard", wiring="unknown", documents=('adafruit-ina219',), keywords=('INA219', 'INA219 current sensor', 'capteur de courant INA219', 'mesurer courant tension INA219', 'intensite consommation INA219', 'sensor de corriente INA219', 'medir corriente tension INA219', 'sensore di corrente INA219', 'misurare corrente tensione INA219', 'high side current sensor', 'I2C 0x40 power monitor', 'battery current monitor', 'shunt 0.1 ohm INA219', 'power meter')),
    Component(id="ina226", function="sensor", mounting="breadboard", wiring="unknown", documents=('ina226-we',), keywords=('INA226', 'INA226 current sensor', 'capteur de courant INA226', 'mesurer courant tension INA226', 'intensite consommation INA226', 'sensor de corriente INA226', 'medir corriente tension INA226', 'sensore di corrente INA226', 'high precision current sensor', 'bidirectional power monitor', 'I2C 0x40 power monitor', 'battery monitor', 'misurare corrente tensione INA226')),
    Component(id="ina3221", function="sensor", mounting="breadboard", wiring="unknown", documents=('adafruit-ina3221',), keywords=('INA3221', 'INA3221 current sensor', 'capteur de courant INA3221', 'mesurer courant tension 3 canaux INA3221', 'trois canaux intensite INA3221', 'sensor de corriente INA3221 3 canales', 'medir corriente tension INA3221', 'sensore di corrente INA3221 3 canali', 'three channel current sensor', 'multi rail power monitor', 'I2C 0x40 INA3221', '3 channel voltage current monitor', 'misurare corrente tensione INA3221')),
    Component(id="ldr", function="sensor", mounting="breadboard", wiring="known", documents=('ldr',), keywords=('ldr', 'photoresistance', 'photoresistor', 'capteur de lumiere', 'capteur de luminosite', 'luminosite', 'lumiere', 'light sensor', 'ambient light', 'light level', 'fotorresistencia', 'sensor de luz', 'fotoresistore', 'sensore di luce')),
    Component(id="mq135", function="sensor", mounting="breadboard", wiring="unknown", documents=('mq135',), keywords=('MQ-135', 'MQ135', 'air quality sensor', 'gas sensor', "qualite de l'air", 'qualite air MQ-135', 'calidad del aire', 'calidad aire MQ-135', "qualita dell'aria", 'qualita aria MQ-135', 'CO2 estimate', 'ammonia NH3', 'smoke sensor', 'VOC sensor', 'indoor air monitoring', 'Rs R0 ratio', 'analog gas sensor', 'capteur de gaz', 'sensor de gas', 'sensore di gas', 'fumee detection', 'deteccion humo', 'rilevazione fumo')),
    Component(id="mhz19", function="sensor", mounting="breadboard", wiring="unknown", documents=('mhz19',), keywords=('MH-Z19', 'MHZ19', 'MH-Z19B', 'MH-Z19C', 'MH-Z19D', 'MH-Z19E', 'MHZ19B', 'MHZ19C', 'MHZ19D', 'MHZ19E', 'MH-Z19 sensor', 'MH-Z19 module', 'capteur MH-Z19', 'sensor MH-Z19', 'sensore MH-Z19', 'NDIR CO2 MH-Z19', 'CO2 NDIR MH-Z19', 'avec MH-Z19', 'con MH-Z19', 'using MH-Z19', 'lire MH-Z19', 'leer MH-Z19', 'leggere MH-Z19', 'UART CO2 MH-Z19', 'serial CO2 MH-Z19')),
    Component(id="pir", function="sensor", mounting="breadboard", wiring="known", documents=('pir-motion-sensor',), keywords=('PIR', 'motion sensor', 'movement sensor', 'HC-SR501', 'HC-SR505', 'détecter mouvement', 'capteur de mouvement', 'detector de movimiento', 'sensore di movimento', 'presence detection', 'détection de présence', 'alarm trigger', 'interrupt motion', 'rilevatore di movimento', 'alarma de movimiento')),
    Component(id="ili9341", function="display", mounting="breadboard", wiring="known", documents=('adafruit-ili9341',), keywords=('ILI9341', 'TFT', 'TFT display', 'color screen', 'ecran TFT', 'pantalla TFT', 'schermo TFT', '240x320', 'Adafruit GFX', 'color graphics', 'graphiques couleur', 'afficher couleur', 'RGB565', 'color display', '2.4 inch', '2.8 inch', 'afficher image', 'bitmap couleur', 'ecran TFT couleur', 'pantalla a color', 'schermo a colori')),
    Component(id="neopixel", function="display", mounting="breadboard", wiring="known", documents=('adafruit-neopixel',), keywords=('NeoPixel', 'WS2812', 'WS2812B', 'WS2811', 'SK6812', 'LED', 'RGB', 'RGBW', 'addressable', 'strip', 'ring', 'matrix', 'color', 'lighting', 'pixel')),
    Component(id="keypad", function="input", mounting="breadboard", wiring="unknown", documents=('keypad',), keywords=('keypad', 'matrix keypad', 'clavier matriciel', 'teclado matricial', 'tastiera matrice', '4x4', '3x4', 'PIN code', 'door code', 'code numerique', 'menu navigation', 'lire touche', 'leer tecla', 'leggere tasto', 'input matrix', 'clavier 4x4', 'tastiera 4x4', 'teclado 4x4', 'boutons matriciels')),
    Component(id="encoder", function="input", mounting="breadboard", wiring="known", documents=('encoder',), keywords=('encoder', 'encodeur rotatif', 'rotary', 'quadrature', 'knob', 'position', 'pulse', 'interrupt', 'shaft', 'wheel', 'step', 'incremental', 'Stoffregen', 'menu')),
    Component(id="ir_receiver", function="communication", mounting="breadboard", wiring="known", documents=('irremote',), keywords=('IR', 'infrared', 'remote', 'NEC', 'Sony', 'RC5', 'RC6', 'Samsung', 'Panasonic', 'TV', 'AC', 'air conditioner', 'receiver', 'transmitter', 'decode', 'TSOP', 'remote control signal', 'IR remote', 'telecommande infrarouge', 'mando a distancia infrarrojo', 'telecomando a infrarossi', 'recevoir infrarouge', 'receive IR signal', 'recibir senal infrarroja', 'ricevere segnale infrarosso')),
    Component(id="gps", function="communication", mounting="breadboard", wiring="unknown", documents=('tinygps-plus',), keywords=('GPS', 'NMEA', 'TinyGPS', 'TinyGPS++', 'TinyGPSPlus', 'NEO-6M', 'NEO-M8N', 'latitude', 'longitude', 'GPS module', 'module GPS', 'modulo GPS', 'lecture GPS', 'leer GPS', 'leggere GPS', 'geolocalisation', 'geolocation', 'position', 'tracker GPS', 'satellites', 'coordonnees GPS', 'coordenadas GPS')),
    Component(id="lora_sx1276", function="communication", mounting="breadboard", wiring="unknown", documents=('lora',), keywords=('LoRa', 'LoRa packet', 'LoRa transceiver', 'SX1276', 'SX1278', 'SX1262', 'Semtech LoRa', 'long range radio', 'longue portee radio', 'largo alcance radio', 'lungo raggio radio', '433 MHz', '868 MHz', '915 MHz', 'sub GHz wireless', 'sub-GHz', 'ISM band', 'low power radio', 'telemetrie longue portee', 'telemetria larga distancia', 'telemetria lungo raggio', 'remote IoT', 'rural IoT', 'GPS tracker LoRa', 'envoyer paquet LoRa', 'enviar paquete LoRa', 'inviare pacchetto LoRa', 'send LoRa packet')),
    Component(id="mfrc522", function="communication", mounting="breadboard", wiring="known", documents=('mfrc522',), keywords=('RFID', 'NFC', 'MFRC522', 'RC522', 'card reader', 'lecteur RFID', 'lector RFID', 'lettore RFID', 'UID', 'MIFARE', 'tag NFC', 'lire badge', 'leer tarjeta', 'leggere tessera', 'access control', "controle d'acces", '13.56 MHz', 'control de acceso', 'controllo accessi')),
    # `lib_name` set although a document backs this entry: the `sd` document
    # carries `arduino_lib_name: null`, so the card said "no library to
    # install" for a component whose sketch cannot compile without
    # `#include <SD.h>`. The corpus is frozen (embeddings aligned by
    # position), so the registry is the only place that can say it -- and
    # `_library_state` gives a set registry field precedence for exactly this
    # reason. Without it this card would contradict `microsd_card_module`,
    # which is the SAME part and does say "SD".
    Component(id="sd_card", function="storage", mounting="breadboard", wiring="unknown", documents=('sd',), lib_name="SD", keywords=('SD card', 'microSD', 'FAT', 'FAT32', 'file', 'filesystem', 'logger', 'datalog', 'CSV', 'SPI', 'storage', 'save', 'read file', 'write file')),
    # Two chips, one library (RTClib) -- the same N<->N as DHT11/DHT22, and the
    # identifiers `markers` actually emits (`_RTC_DS3231_RE` / `_RTC_DS1307_RE`).
    Component(id="ds3231", function="timing", mounting="breadboard", wiring="known", documents=('rtclib',), keywords=('DS3231', 'RTC', 'horloge temps reel', 'real time clock', 'reloj en tiempo real', 'orologio in tempo reale', 'time', 'date', 'calendar', 'alarm', 'I2C', 'battery backup', 'timestamp', 'compense en temperature')),
    Component(id="ds1307", function="timing", mounting="breadboard", wiring="known", documents=('rtclib',), keywords=('DS1307', 'RTC', 'horloge temps reel', 'real time clock', 'reloj en tiempo real', 'orologio in tempo reale', 'time', 'date', 'calendar', 'I2C', 'battery backup', 'timestamp')),
    Component(id="motor_shield_v2", function="motor_driver", mounting="off_board", wiring="unknown", documents=('adafruit-motorshield-v2',), keywords=('motor shield', 'DC motor', 'stepper motor', 'Adafruit', 'I2C', 'robot', 'rover', 'wheel', 'drive', 'PWM', 'FORWARD', 'BACKWARD', 'stacking')),
    Component(id="grove_motor_driver", function="motor_driver", mounting="off_board", wiring="unknown", documents=('grove-i2c-motor-driver',), keywords=('grove i2c motor driver', 'grove motor', 'seeed motor driver', 'i2c motor driver', 'i2c motor', 'moteur i2c', 'moteur en i2c', 'driver moteur i2c', 'moteur dc i2c', 'motor i2c', 'motore i2c', 'L298 i2c', 'grove base shield motor', '0x0F')),

    # -- types `markers` emits with no corpus document at all --
    # Produced at RUNTIME by the bare-pin subtype cascade (`_BARE_PIN_TYPES`,
    # `_relay`/`_ky018`/`_thermistor`/`_microphone` lexicons in markers.py):
    # the user writes "allume un relais", the app wires a relay and names it in
    # the instructions. Missing here until 2026-07-31, so the "Composants" tab
    # answered nothing for a component it can perfectly well build -- the exact
    # gap the drift guard cannot see, since it only walks corpus -> registry.
    # `documents=()` is the honest value, like the bare LED: no library, no
    # corpus entry, a component all the same.
    Component(id="relay", function="output", mounting="breadboard", wiring="known", documents=(),
              description="Relais électromécanique, pour commuter un circuit séparé.",
              keywords=('relais', 'relai', 'relay', 'rele', 'module relais', 'relay module', 'commander une lampe', 'switch 220v', 'modulo rele', 'modulo di rele')),
    Component(id="thermistor", function="sensor", mounting="breadboard", wiring="known", documents=(),
              description="Thermistance CTN, dont la résistance varie avec la température.",
              keywords=('thermistance', 'thermistor', 'ntc', 'lm35', 'capteur de temperature analogique', 'analog temperature sensor', 'termistor', 'sensor de temperatura', 'termistore', 'sensore di temperatura')),
    Component(id="microphone", function="sensor", mounting="breadboard", wiring="known", documents=(),
              description="Microphone à électret, sortie analogique du niveau sonore.",
              keywords=('microphone', 'capteur de son', 'capteur sonore', 'sound sensor', 'audio sensor', 'detecter un bruit', 'clap', 'microfono', 'sensor de sonido', 'sensore sonoro')),
    Component(id="ky018", function="sensor", mounting="breadboard", wiring="unknown", documents=(),
              description="Module photorésistance KY-018, sortie analogique de luminosité.",
              keywords=('ky-018', 'ky018', 'photoresistance ky-018', 'module photoresistance', 'photoresistor module', 'modulo fotorresistencia', 'modulo fotoresistenza')),

    # -- Lot A (2026-08-12): replacement candidates, bare pin --
    # The types the ambiguity modal proposes as replacements
    # (replacement_catalog, categories single_output / analog_in / digital_in)
    # that had no card at all: their card would have been empty. No library
    # to install (user decision 2026-08-12) -- neither lib_name nor
    # lib_to_determine, the default "none" state is the right one. The
    # displayed name comes from replacement_catalog.label_of (never from
    # _TYPE_LABEL).
    Component(id="acs712", function="sensor", mounting="breadboard",
              wiring="known",
              description="Capteur de courant à effet Hall, sortie analogique proportionnelle.",
              keywords=("acs712", "capteur de courant", "current sensor",
                        "sensor de corriente", "sensore di corrente")),
    Component(id="buttonpad", function="input", mounting="breadboard",
              wiring="unknown",
              description="Pavé de boutons-poussoirs en matrice.",
              keywords=("buttonpad", "pave de boutons", "button pad",
                        "matriz de botones", "matrice di pulsanti")),
    Component(id="dip_switch", function="input", mounting="breadboard",
              wiring="unknown",
              description="Bloc de micro-interrupteurs DIP à positions maintenues.",
              keywords=("dip switch", "interrupteur dip", "micro-interrupteur",
                        "interruptor dip", "interruttore dip")),
    Component(id="force_sensor", function="sensor", mounting="breadboard",
              wiring="known",
              description="Capteur de force résistif (FSR), lu en analogique.",
              keywords=("fsr", "capteur de force", "force sensor",
                        "sensor de fuerza", "sensore di forza")),
    Component(id="hall_sensor", function="sensor", mounting="breadboard",
              wiring="unknown",
              description="Capteur à effet Hall, détecte un champ magnétique.",
              keywords=("hall", "effet hall", "hall sensor",
                        "sensor hall", "sensore hall")),
    Component(id="joystick", function="input", mounting="breadboard",
              wiring="known",
              description="Joystick analogique 2 axes avec bouton.",
              # `ky-023` : serigraphie du module de kit, affirmee par la
              # bibliotheque « Joystick-KY023 » de l'index Arduino. Le joystick
              # n'a AUCUN document corpus, donc cet alias ne sert qu'a la
              # recherche de l'onglet et du picker -- pas a la generation.
              keywords=("joystick", "manette", "joystick analogico",
                        "palanca", "ky-023", "ky023", "ky 023")),
    Component(id="light_sensor", function="sensor", mounting="breadboard",
              wiring="known",
              description="Capteur de lumière analogique (TEMT6000 ou équivalent).",
              keywords=("temt6000", "capteur de lumiere", "light sensor",
                        "sensor de luz", "sensore di luce")),
    Component(id="load_cell", function="sensor", mounting="breadboard",
              wiring="known",
              description="Cellule de charge (jauge de contrainte) pour peser.",
              keywords=("load cell", "cellule de charge", "jauge",
                        "celula de carga", "cella di carico")),
    Component(id="passive_buzzer", function="output", mounting="breadboard",
              wiring="unknown",
              description="Buzzer passif : la fréquence vient du code (tone).",
              keywords=("buzzer passif", "passive buzzer", "zumbador pasivo",
                        "cicalino passivo")),
    Component(id="reed_switch", function="sensor", mounting="breadboard",
              wiring="known",
              description="Interrupteur reed, fermé par un aimant.",
              keywords=("reed", "interrupteur reed", "reed switch",
                        "interruptor reed", "interruttore reed")),
    Component(id="rgb_led", function="output", mounting="breadboard",
              wiring="unknown",
              description="LED RGB à 4 broches (une par couleur + commun).",
              keywords=("led rgb", "rgb led", "led tricolore", "led rvb")),
    Component(id="slide_switch", function="input", mounting="breadboard",
              wiring="known",
              description="Interrupteur à glissière à deux positions.",
              keywords=("slide switch", "interrupteur a glissiere",
                        "interruptor deslizante",
                        "interruttore a scorrimento")),
    Component(id="slider", function="input", mounting="breadboard",
              wiring="known",
              description="Potentiomètre à glissière, lu en analogique.",
              keywords=("slider", "potentiometre a glissiere",
                        "slide potentiometer", "potenciometro deslizante")),
    Component(id="soil_moisture", function="sensor", mounting="breadboard",
              wiring="known",
              description="Capteur d'humidité du sol, sortie analogique.",
              keywords=("humidite du sol", "soil moisture",
                        "humedad del suelo", "umidita del suolo")),
    Component(id="solenoid", function="output", mounting="breadboard",
              wiring="known",
              description="Solénoïde (électroaimant), piloté via transistor.",
              keywords=("solenoide", "solenoid", "electroaimant",
                        "electroiman")),
    Component(id="speaker", function="output", mounting="breadboard",
              wiring="known",
              description="Petit haut-parleur piloté par une broche.",
              keywords=("haut-parleur", "speaker", "altavoz",
                        "altoparlante")),
    Component(id="tilt_switch", function="sensor", mounting="breadboard",
              wiring="known",
              description="Interrupteur d'inclinaison à bille.",
              keywords=("tilt", "inclinaison", "tilt switch",
                        "interruptor de inclinacion",
                        "interruttore di inclinazione")),
    Component(id="toggle_switch", function="input", mounting="breadboard",
              wiring="known",
              description="Interrupteur à bascule à deux positions.",
              keywords=("toggle", "interrupteur a levier", "toggle switch",
                        "interruptor de palanca", "interruttore a leva")),
    Component(id="touch_sensor", function="input", mounting="breadboard",
              wiring="known",
              # Brochage Fritzing reel (AT42QT1010, 2026-08-19) : la fiche
              # ajoutee au catalogue en meme temps que le lot #2 ci-dessous.
              description="Capteur tactile capacitif (TTP223 ou équivalent).",
              keywords=("ttp223", "capteur tactile", "touch sensor",
                        "sensor tactil", "sensore tattile")),

    # -- Lot A (2026-08-12): replacement candidates, bus (I2C / SPI / UART /
    # ultrasonic) --
    # Same gap as the bare-pin block above, on the other half of
    # `replacement_catalog`. These DO generally need a library, so the default
    # "none" state would lie the way it lied for a BMP180 before task 1. Each
    # library below was checked, one by one, against the LOCAL arduino-cli
    # index (9825 entries, 2026-08-12), applying the plan's rule in order:
    #   (a) the proposed name exists VERBATIM in the index -> lib_name
    #   (b) the part speaks a bare protocol (text serial, raw SPI transfer)
    #       and needs no library at all -> neither field, i.e. "none"
    #   (c) anything else -> lib_to_determine, an honest shippable state
    # A near-miss is NOT a match: `SparkFun ITG-3200` is absent and only
    # `DFRobot_ITG3200` exists (another vendor, another breakout), so itg3200
    # stays (c) rather than silently borrowing a library written for a
    # different board -- the exact substitution the unknown-part pipeline
    # exists to prevent. Two exceptions, both index-verified: the proposal
    # `SparkFun MMA8452Q Accelerometer Breakout` is registered WITHOUT the
    # trailing " Breakout", and hmc6352 was expected to have no maintained
    # library yet the index carries one named exactly `HMC6352`.
    # `gps_em406` and `hmc5883` carry NEITHER description nor lib_name: they
    # reference an existing corpus document, which supplies both (the
    # dht11/dht22 pattern -- a document serves N components).
    # (c) NO OCCURRENCE AT ALL in the index -- adjd_s311, l3g4200d, mag3110,
    # vcnl4000. Worth re-checking one day: nothing is wrong with the part, a
    # library may simply get published. This is the only one of the three (c)
    # groups where waiting can change the answer.
    Component(id="adjd_s311", function="sensor", mounting="breadboard",
              wiring="known", lib_to_determine=True,
              description="Capteur de couleur I²C ADJD-S311, mesure les composantes rouge, verte et bleue.",
              keywords=("adjd-s311", "adjd s311", "capteur de couleur",
                        "color sensor", "sensor de color",
                        "sensore di colore")),
    # Rule (b): the Atlas Scientific pH circuit is driven by ASCII commands on
    # a serial line -- no library, and the index has none for it.
    Component(id="atlas_ph", function="sensor", mounting="breadboard",
              wiring="unknown",
              description="Circuit de mesure de pH Atlas Scientific, piloté par des commandes texte en série.",
              keywords=("atlas ph", "circuit ph", "sonde ph", "ph sensor",
                        "sensor de ph", "sensore di ph")),
    # One library for both barometers: its own index entry says
    # "BMP085/BMP180 Library". Their descriptions say the SAME thing on
    # purpose -- both chips measure pressure, temperature and derive altitude,
    # and wording them differently ("pression et température" vs "pression et
    # altitude") suggested a spec difference that does not exist. The BMP180
    # is simply the smaller, later revision, which is a real difference and
    # the one worth printing.
    Component(id="bmp085", function="sensor", mounting="breadboard",
              wiring="known", documents=('bmp085',), lib_name="Adafruit BMP085 Library",
              description="Baromètre I²C BMP085, mesure pression, température et altitude.",
              keywords=("bmp085", "barometre", "capteur de pression",
                        "barometric pressure", "sensor de presion",
                        "sensore di pressione")),
    Component(id="bmp180", function="sensor", mounting="breadboard",
              wiring="known", documents=('bmp180',), lib_name="Adafruit BMP085 Library",
              description="Baromètre I²C BMP180, mesure pression, température et altitude. Version compacte du BMP085.",
              keywords=("bmp180", "barometre", "capteur de pression",
                        "barometric pressure altitude", "presion y altitud",
                        "pressione e altitudine")),
    # (c) ONLY ANOTHER VENDOR'S LIBRARY for the same chip -- ds3234
    # (`Soldered DS3234 RTC`) and itg3200 (`DFRobot_ITG3200`). Refused on
    # purpose: a library written for another vendor's breakout is the silent
    # substitution the unknown-part pipeline exists to prevent. Nothing to
    # re-check here -- the answer will not improve by waiting, it needs a
    # human to decide the swap is safe.
    Component(id="ds3234", function="timing", mounting="breadboard",
              wiring="known", lib_to_determine=True,
              description="Horloge temps réel DS3234 en SPI, avec pile de sauvegarde.",
              keywords=("ds3234", "horloge temps reel spi", "rtc spi",
                        "real time clock spi", "reloj en tiempo real spi",
                        "orologio in tempo reale spi")),
    # Rule (b): a USB-to-serial bridge. Nothing to drive from the sketch.
    Component(id="ftdi_basic", function="communication", mounting="breadboard",
              wiring="known",
              description="Adaptateur FTDI Basic, pont USB vers série pour programmer ou dialoguer avec la carte.",
              keywords=("ftdi", "ftdi basic", "pont usb serie",
                        "usb to serial", "usb a serie", "usb seriale")),
    # The corpus already describes TinyGPS++ for the `gps` component; an EM-406
    # is one more NMEA receiver on the same library.
    Component(id="gps_em406", function="communication", mounting="breadboard",
              wiring="unknown", documents=('tinygps-plus',),
              keywords=("em406", "gps em-406", "module gps", "gps module",
                        "modulo gps")),
    # (c) THE CHIP VARIES WITH THE MODULE VERSION -- grove_3axis_accel,
    # grove_oled_128x96, imu_6dof, led_matrix_rgb_spi, sensor_stick_9dof.
    # Not generically resolvable: the same product name shipped with
    # different silicon over the years, so naming ONE library would be right
    # for one revision and wrong for the next. The user's own board settles
    # it, which is what the "choose the library" flow (#39) is for.
    Component(id="grove_3axis_accel", function="sensor", mounting="breadboard",
              wiring="unknown", lib_to_determine=True,
              description="Accéléromètre 3 axes au format Grove, en I²C.",
              keywords=("grove accelerometre", "grove accelerometer",
                        "accelerometre 3 axes grove", "acelerometro grove",
                        "accelerometro grove")),
    # (c) chip varies with the version -- see the grove_3axis_accel group
    # comment above (SSD1327 or another driver depending on the revision).
    Component(id="grove_oled_128x96", function="display",
              mounting="breadboard", wiring="known", lib_to_determine=True,
              description="Écran OLED Grove 128×96, en I²C.",
              keywords=("grove oled", "ecran oled grove",
                        "grove oled display", "pantalla oled grove",
                        "schermo oled grove")),
    # Rule (b): a transparent serial bridge. The description used to lead with
    # the AT commands, which is what a beginner needs LEAST -- in a sketch you
    # just read and write the serial port; AT is only for configuring the
    # module once.
    Component(id="hc05", function="communication", mounting="breadboard",
              wiring="known",
              description="Module Bluetooth HC-05 : liaison série sans fil ; se configure par commandes AT.",
              keywords=("hc-05", "hc05", "bluetooth", "module bluetooth",
                        "modulo bluetooth")),
    # Same physical chip as `hmc5883l`: two wiring ids, one component, so one
    # document rather than a second description to keep in sync.
    Component(id="hmc5883", function="sensor", mounting="breadboard",
              wiring="known", documents=('hmc5883l',),
              keywords=("hmc5883", "hmc5883l", "magnetometre",
                        "boussole numerique", "digital compass", "brujula",
                        "bussola")),
    Component(id="hmc6352", function="sensor", mounting="breadboard",
              wiring="known", documents=('hmc6352',), lib_name="HMC6352",
              description="Boussole numérique I²C HMC6352, donne un cap en degrés.",
              keywords=("hmc6352", "boussole numerique", "digital compass",
                        "brujula digital", "bussola digitale")),
    # (c) chip varies with the version -- see the grove_3axis_accel group
    # comment above ("6DOF combo" names a shape, not a part number).
    Component(id="imu_6dof", function="sensor", mounting="breadboard",
              wiring="unknown", lib_to_determine=True,
              description="Centrale inertielle 6 axes : accéléromètre et gyroscope réunis.",
              keywords=("imu 6dof", "6 dof", "centrale inertielle 6 axes",
                        "6 axis imu", "unidad inercial 6 ejes",
                        "sensore inerziale 6 assi")),
    # ✅ 2026-08-26 (#54) : le refus (c) « autre vendeur seulement » est LEVE,
    # et il l'est sur le CODE, pas sur une opinion. Le constructeur de
    # `DFRobot_ITG3200` est `(TwoWire *pWire = &Wire, uint8_t I2C_addr = 0x68)` :
    # l'adresse est un PARAMETRE, et son defaut 0x68 est l'adresse standard de
    # l'ITG-3200 (AD0 au niveau bas), pas une adresse propre a la carte DFRobot.
    # C'est donc un pilote de PUCE, pas de carte -- la substitution silencieuse
    # que le refus visait n'existe pas ici. Verifie en lisant l'en-tete installe.
    Component(id="itg3200", function="sensor", mounting="breadboard",
              wiring="known", documents=('itg3200',),
              lib_name="DFRobot_ITG3200",
              description="Gyroscope 3 axes I²C ITG-3200, mesure les vitesses de rotation.",
              keywords=("itg3200", "itg-3200", "gyroscope",
                        "gyroscope 3 axes", "giroscopio",
                        "giroscopio 3 assi")),
    # ✅ 2026-08-26 (#54) : « aucune occurrence dans l'index » etait vrai au
    # 2026-08-12 et ne l'est plus — le groupe (c) disait lui-meme que c'est le
    # seul des trois ou attendre peut changer la reponse. `L3G` (Pololu) existe,
    # et c'est bien CETTE puce : son en-tete declare
    # `enum deviceType { device_4200D, device_D20, device_D20H, device_auto }`
    # et son exemple appelle `gyro.init()` en autodetection.
    # ⛔ NE PAS lui substituer `Adafruit L3GD20 U`, qui parait proche : son
    # `begin()` refuse tout WHO_AM_I autre que 0xD4 (L3GD20) ou 0xD7 (L3GD20H),
    # or un L3G4200D repond 0xD3. Verifie dans le .cpp installe.
    Component(id="l3g4200d", function="sensor", mounting="breadboard",
              wiring="known", documents=('l3g4200d',), lib_name="L3G",
              description="Gyroscope 3 axes I²C L3G4200D, mesure les vitesses de rotation.",
              keywords=("l3g4200d", "gyroscope", "gyroscope 3 axes",
                        "giroscopio", "giroscopio 3 assi")),
    # (c) chip varies with the version -- see the grove_3axis_accel group
    # comment above. Filed under SPI by `replacement_catalog`, so a swap
    # routes MOSI/SCK/CS: the description must not say "one data wire", which
    # described a WS2812-style backpack and contradicted its own wiring.
    Component(id="led_matrix_rgb_spi", function="display",
              mounting="breadboard", wiring="unknown", lib_to_determine=True,
              description="Matrice de LED RGB à backpack série, pilotée en SPI.",
              keywords=("matrice led rgb", "rgb led matrix", "matriz led rgb",
                        "matrice led rgb spi")),
    Component(id="lsm303", function="sensor", mounting="breadboard",
              wiring="known", documents=('lsm303',), lib_name="Adafruit LSM303DLHC",
              description="Boussole et accéléromètre I²C LSM303, orientation et inclinaison.",
              keywords=("lsm303", "boussole accelerometre",
                        "compass accelerometer", "brujula acelerometro",
                        "bussola accelerometro")),
    # (c) no occurrence at all -- see the adjd_s311 group comment above.
    Component(id="mag3110", function="sensor", mounting="breadboard",
              wiring="known", lib_to_determine=True,
              description="Magnétomètre 3 axes I²C MAG3110, mesure le champ magnétique.",
              keywords=("mag3110", "magnetometre", "magnetometer",
                        "magnetometro", "champ magnetique")),
    Component(id="max1704x", function="sensor", mounting="breadboard",
              wiring="known", documents=('max17043',), lib_name="Adafruit MAX1704X",
              description="Jauge de batterie LiPo I²C MAX1704x, donne l'état de charge.",
              keywords=("max1704x", "jauge de batterie lipo",
                        "lipo fuel gauge", "medidor de bateria lipo",
                        "indicatore di carica batteria")),
    # Rule (b) for both digital pots: a single raw SPI transfer sets the
    # wiper. A third-party wrapper exists in the index but is not needed.
    Component(id="mcp41xxx", function="output", mounting="breadboard",
              wiring="known",
              description="Potentiomètre numérique MCP41xxx, réglé par un simple transfert SPI.",
              keywords=("mcp41xxx", "mcp41010", "potentiometre numerique",
                        "digital potentiometer", "potenciometro digital",
                        "potenziometro digitale")),
    Component(id="mcp42xxx", function="output", mounting="breadboard",
              wiring="known",
              description="Double potentiomètre numérique MCP42xxx, réglé par un simple transfert SPI.",
              keywords=("mcp42xxx", "mcp42010",
                        "double potentiometre numerique",
                        "dual digital potentiometer",
                        "potenciometro digital doble",
                        "doppio potenziometro digitale")),
    Component(id="microsd_card_module", function="storage",
              mounting="breadboard", wiring="unknown", documents=('sd',), lib_name="SD",
              description="Module de carte microSD en SPI, pour enregistrer des fichiers.",
              keywords=("microsd", "carte microsd", "module carte sd",
                        "microsd card module", "tarjeta microsd",
                        "scheda microsd")),
    Component(id="mma8452q", function="sensor", mounting="breadboard",
              wiring="known", documents=('mma8452q',), lib_name="SparkFun MMA8452Q Accelerometer",
              description="Accéléromètre 3 axes I²C MMA8452Q, échelles 2, 4 ou 8 g.",
              keywords=("mma8452q", "accelerometre 3 axes",
                        "3 axis accelerometer", "acelerometro 3 ejes",
                        "accelerometro 3 assi")),
    Component(id="mpl3115a2", function="sensor", mounting="breadboard",
              wiring="known", documents=('mpl3115a2',), lib_name="Adafruit MPL3115A2 Library",
              description="Altimètre et baromètre I²C MPL3115A2, pression et altitude.",
              keywords=("mpl3115a2", "altimetre", "barometre",
                        "altimeter barometer", "altimetro barometro")),
    Component(id="mpr121", function="input", mounting="breadboard",
              wiring="known", documents=('mpr121',), lib_name="Adafruit MPR121",
              description="Contrôleur tactile capacitif I²C MPR121, jusqu'à 12 électrodes.",
              keywords=("mpr121", "tactile capacitif", "capacitive touch",
                        "touch controller", "tactil capacitivo",
                        "tattile capacitivo")),
    # Rule (b): everything the sketch prints on the serial line is written to
    # the card. The `SparkFun Qwiic OpenLog` of the index is the I2C variant,
    # a different product.
    Component(id="openlog", function="storage", mounting="breadboard",
              wiring="unknown",
              description="Enregistreur OpenLog : tout ce qui part en série est écrit sur la carte SD.",
              keywords=("openlog", "enregistreur serie", "serial logger",
                        "datalogger serie", "registrador serie",
                        "registratore seriale")),
    # (c) chip varies with the version -- see the grove_3axis_accel group
    # comment above (the SparkFun combo was retired and re-silicon'd twice).
    Component(id="sensor_stick_9dof", function="sensor",
              mounting="breadboard", wiring="unknown", lib_to_determine=True,
              description="Barrette 9 axes : accéléromètre, gyroscope et magnétomètre réunis.",
              keywords=("sensor stick", "9dof", "9 dof",
                        "centrale inertielle 9 axes", "9 axis imu",
                        "unidad inercial 9 ejes", "sensore inerziale 9 assi")),
    # `SHT1x` is absent from the index; the only near name is an ESP-only
    # fork (architectures esp8266/esp32), useless on an Arduino board.
    Component(id="sht15", function="sensor", mounting="breadboard",
              wiring="known", lib_to_determine=True,
              description="Capteur de température et d'humidité SHT15, sur deux fils dédiés.",
              keywords=("sht15", "sht1x", "temperature humidite",
                        "temperature humidity", "temperatura humedad",
                        "temperatura umidita")),
    # `arduino-sht` lists SHT2x among its supported sensors.
    Component(id="sht25", function="sensor", mounting="breadboard",
              wiring="known", documents=('sht25',), lib_name="arduino-sht",
              description="Capteur de température et d'humidité I²C SHT25.",
              keywords=("sht25", "sht2x", "temperature humidite",
                        "temperature humidity", "temperatura humedad",
                        "temperatura umidita")),
    Component(id="thermal_printer", function="output", mounting="breadboard",
              wiring="known", documents=('thermal_printer',), lib_name="Adafruit Thermal Printer Library",
              description="Imprimante thermique série, imprime du texte sur du papier thermique.",
              keywords=("imprimante thermique", "thermal printer",
                        "impresora termica", "stampante termica", "ticket")),
    Component(id="tmp102", function="sensor", mounting="breadboard",
              wiring="known", documents=('tmp102',), lib_name="SparkFun TMP102 Breakout",
              description="Capteur de température I²C TMP102.",
              keywords=("tmp102", "capteur de temperature",
                        "temperature sensor", "sensor de temperatura",
                        "sensore di temperatura")),
    # Rule (b): trigger/echo like an HC-SR04, or plain serial -- both without
    # a library, and the index has none for it.
    Component(id="us100", function="sensor", mounting="breadboard",
              wiring="known",
              description="Capteur de distance à ultrasons US-100, en trigger/echo ou en série.",
              keywords=("us-100", "us100", "capteur ultrason",
                        "ultrasonic sensor", "sensor ultrasonico",
                        "sensore a ultrasuoni")),
    # (c) no occurrence at all -- see the adjd_s311 group comment above.
    Component(id="vcnl4000", function="sensor", mounting="breadboard",
              wiring="known", lib_to_determine=True,
              description="Capteur de proximité et de lumière ambiante I²C VCNL4000.",
              keywords=("vcnl4000", "capteur de proximite",
                        "proximity sensor", "sensor de proximidad",
                        "sensore di prossimita")),
    Component(id="wiz820io", function="communication", mounting="breadboard",
              wiring="unknown", documents=('wiz820io',), lib_name="Ethernet",
              description="Module Ethernet WIZ820io, connexion réseau filaire en SPI.",
              keywords=("wiz820io", "ethernet", "reseau filaire",
                        "wired network", "red ethernet", "rete ethernet")),

    # -- real memory, a real library, integrated on the board: nothing to wire --
    Component(id="eeprom", function="storage", mounting="on_mcu", wiring="none", documents=('eeprom',), keywords=('EEPROM', 'non-volatile', 'persistent', 'memory', 'save', 'calibration', 'settings', 'configuration', 'preferences', 'flash', 'AVR', 'built-in')),

    # ── Cartes multi-puces (2026-08-18) ───────────────────────────────────────
    # Un module est UN composant pour l'utilisateur et PLUSIEURS pour l'app.
    # `contains` porte la composition ; `ui/hardware_modules.py` lit ces
    # entrées (mots-clés de détection ET puces) au lieu de les redéclarer.
    #
    # `wiring="unknown"` est exact et non un aveu d'échec : la boîte fusionnée
    # est bien dessinée, mais par `resolve_generic` (4 broches I2C), sans entrée
    # dédiée au catalogue — c'est précisément ce que cet état veut dire.
    # `documents=()` l'est aussi : la carte n'a pas de bibliothèque à elle, ce
    # sont ses PUCES qui en ont une, et `module_forced_libs` va les y chercher.
    Component(id="hw-612", function="sensor", mounting="breadboard", wiring="unknown",
              description="Carte 10-DOF HW-612 : accéléromètre, gyroscope, magnétomètre et baromètre sur un seul module I2C.",
              contains=('mpu9250', 'bmp280'),
              # ⚠️ `gy-87` et `gy-86` ont ete RETIRES d'ici le 2026-08-26 (TODO #57).
              # Ils y etaient faux : cette carte porte un MPU9250 + BMP280, alors
              # que le GY-87 porte MPU6050 + HMC5883L + BMP180 et le GY-86
              # MPU6050 + HMC5883L + MS5611. Un utilisateur qui lisait « GY-87 »
              # sur sa carte se voyait forcer les bibliotheques de DEUX puces
              # qu'elle n'a pas -- l'app affirmait, avec autorite, le mauvais
              # composant. Les deux ont desormais leur propre module.
              # `gy-91` RESTE : cette carte-la est bien un MPU9250 + BMP280.
              keywords=('hw-612', 'hw612', 'hw 612',
                        'gy-91', 'gy91', 'gy 91', '10 dof', '10-dof', '10dof',
                        'imu 10 dof', '10 axis imu', '10 ejes', '10 assi')),
    Component(id="gy-80", function="sensor", mounting="breadboard", wiring="unknown",
              description="Carte 10-DOF GY-80 : accéléromètre, gyroscope, magnétomètre et baromètre sur un seul module I2C.",
              contains=('adxl345', 'l3g4200d', 'hmc5883l', 'bmp085'),
              keywords=('gy-80', 'gy80', 'gy 80')),
    Component(id="gy-85", function="sensor", mounting="breadboard", wiring="unknown",
              description="Carte 9-DOF GY-85 : accéléromètre, gyroscope et magnétomètre sur un seul module I2C.",
              contains=('adxl345', 'itg3200', 'hmc5883l'),
              keywords=('gy-85', 'gy85', 'gy 85')),

    # ── Ajoutés le 2026-08-26 (TODO #57) — correction d'un alias FAUX ─────────
    # Ces deux cartes étaient aliasées sur `hw-612` (cf. le commentaire là-haut).
    # Sources : la composition de chacune est affirmée par les revendeurs et,
    # pour le GY-87, par la bibliothèque « HW290 » de l'index Arduino elle-même
    # (« HW290 10DOF sensor board (MPU6050 + BMP180 + HP5883) »).
    #
    # `hw-290` est un alias du GY-87 et non un module à part : c'est LA MÊME
    # CARTE, sérigraphiée différemment selon le revendeur — le cas d'usage qui
    # a motivé ce chantier.
    Component(id="gy-87", function="sensor", mounting="breadboard", wiring="unknown",
              description="Carte 10-DOF GY-87 (aussi vendue HW-290) : accéléromètre, gyroscope, magnétomètre et baromètre sur un seul module I2C.",
              contains=('mpu6050', 'hmc5883l', 'bmp180'),
              keywords=('gy-87', 'gy87', 'gy 87', 'hw-290', 'hw290', 'hw 290')),
    # Le GY-86 se distingue du GY-87 par son BAROMÈTRE : un MS5611, plus précis,
    # et surtout une bibliothèque différente. C'est exactement le genre d'écart
    # qu'un alias approximatif efface.
    Component(id="gy-86", function="sensor", mounting="breadboard", wiring="unknown",
              description="Carte 10-DOF GY-86 : accéléromètre, gyroscope, magnétomètre et baromètre MS5611 sur un seul module I2C.",
              contains=('mpu6050', 'hmc5883l', 'ms5611'),
              keywords=('gy-86', 'gy86', 'gy 86')),
    # Le baromètre du GY-86, qui n'avait aucune identité. Bibliothèque VÉRIFIÉE
    # par le vrai `registry_lookup.lookup_component` (statut `found`, « MS5611 »
    # de Rob Tillaart, 19 versions) — jamais supposée. C'est cette même fiche
    # d'index qui donne son alias de carte : « Experimental, GY-63, GY63 ».
    Component(id="ms5611", function="sensor", mounting="breadboard", wiring="unknown",
              lib_name="MS5611",
              description="Baromètre MS5611 haute résolution (pression et température), porté par les cartes GY-63 et GY-86.",
              keywords=('ms5611', 'gy-63', 'gy63', 'gy 63', 'baromètre haute résolution',
                        'high resolution barometer', 'barometro alta resolucion',
                        'barometro alta risoluzione')),

    # ── Pilote « identité élargie » du 2026-08-19 (TODO #57, sous-chantier B) ──
    # Contrairement aux lots précédents (brochage pour une identité déjà
    # connue), ces 8 composants n'existaient PAS du tout au registre. Fritzing
    # s'est révélé pauvre sur les modules récents (recherche documentée dans
    # TODO #57) : ce lot vient d'ailleurs — connaissance du domaine, chaque
    # bibliothèque VÉRIFIÉE via le vrai `registry_lookup.lookup_component`
    # (le même mécanisme qu'utilise l'app en production), jamais devinée.
    #
    # `wiring="unknown"` pour la plupart : le brochage n'a pas été sourcé dans
    # ce lot, c'est un état honnête et déjà légitime au registre (72 autres
    # composants y vivent). Exception : `drv8825`, dont le brochage EST connu
    # (fiche Fritzing du breakout, cohérente avec le driver frère `a4988`).
    #
    # Deux résultats de recherche REJETÉS plutôt qu'adoptés : la requête
    # « sound sensor » a remonté « Arduino Learning Board » (un paquet
    # générique sans rapport, faux positif lexical) et « rain sensor » a
    # remonté « DFRobot_RainfallSensor » (probablement le pluviomètre à
    # augets DFRobot, pas la carte comparateur à 2 € que les débutants
    # câblent). Les deux sont classés `none` par ANALOGIE avec les modules
    # comparateur déjà au registre (`pir`, `ldr`, `force_sensor`,
    # `soil_moisture` : lecture directe, aucune bibliothèque) — pas par
    # défaut faute de résultat, par jugement de domaine explicite.
    Component(id="esp8266", function="communication", mounting="breadboard", wiring="unknown", documents=('esp8266',),
              description="Module WiFi ESP8266 (ESP-01), piloté par commandes AT sur liaison série.",
              lib_name="Adafruit ESP8266",
              keywords=('esp8266', 'esp-01', 'esp01', 'module wifi esp8266', 'wifi module esp8266',
                        'modulo wifi esp8266', 'modulo esp-01')),
    Component(id="sim800l", function="communication", mounting="breadboard", wiring="unknown", documents=('sim800l',),
              description="Module GSM/GPRS SIM800L : appels, SMS et données via une carte SIM.",
              lib_name="Sim800L Library",
              keywords=('sim800l', 'module gsm sim800l', 'module sms', 'gsm module', 'sms module',
                        'modulo gsm sim800l', 'modulo sms')),
    Component(id="mq2", function="sensor", mounting="breadboard", wiring="unknown", documents=('mq2',),
              description="Capteur de gaz MQ-2 (fumée, GPL, propane), sortie analogique.",
              lib_name="MQ2_LPG",
              keywords=('mq-2', 'mq2', 'capteur de gaz mq-2', 'detecteur de fumee', 'capteur de gpl',
                        'mq-2 gas sensor', 'smoke detector mq-2', 'sensor de gas mq-2', 'detector de humo',
                        'sensore di gas mq-2', 'rilevatore di fumo')),
    Component(id="water_flow_sensor", function="sensor", mounting="breadboard", wiring="unknown", documents=('water_flow_sensor',),
              description="Débitmètre à effet Hall (type YF-S201), impulsions comptées sur une broche numérique.",
              lib_name="YF-S201 Water Flow",
              keywords=('yf-s201', 'debitmetre a eau', 'capteur de debit', 'water flow sensor', 'flow meter',
                        'sensor de flujo de agua', 'caudalimetro', "sensore di flusso d'acqua", 'flussometro')),
    Component(id="drv8825", function="motor_driver", mounting="breadboard", wiring="known", documents=('drv8825',),
              description="Driver de moteur pas à pas DRV8825 (STEP/DIR, comme l'A4988, courant plus élevé).",
              lib_name="DRV8825",
              keywords=('drv8825', 'driver pas a pas drv8825', 'driver moteur pas a pas',
                        'drv8825 stepper driver', 'controlador paso a paso drv8825',
                        'driver passo passo drv8825')),
    Component(id="flame_sensor", function="sensor", mounting="breadboard", wiring="unknown",
              description="Capteur de flamme infrarouge, sortie numérique et/ou analogique — pas de bibliothèque, lecture directe.",
              keywords=('capteur de flamme', 'detecteur de flamme', "detecteur d'incendie", 'flame sensor',
                        'fire sensor', 'sensor de llama', 'sensor de fuego', 'sensore di fiamma')),
    Component(id="rain_sensor", function="sensor", mounting="breadboard", wiring="unknown",
              description="Capteur de pluie résistif (plaque + comparateur), sortie numérique et/ou analogique — pas de bibliothèque, lecture directe.",
              keywords=('capteur de pluie', 'detecteur de pluie', 'rain sensor', 'rain detector',
                        'sensor de lluvia', 'sensore di pioggia')),
    Component(id="sound_detector", function="sensor", mounting="breadboard", wiring="unknown",
              description="Module détecteur de son (micro + comparateur, type KY-038), sortie numérique et/ou analogique — pas de bibliothèque, lecture directe.",
              keywords=('module detecteur de son', 'capteur sonore module', 'ky-038', 'sound detector module',
                        'sound sensor module ky-038', 'modulo detector de sonido', 'modulo rilevatore di suono')),

    # ── Lot #2 « identité élargie » du 2026-08-19 (TODO #57, sous-chantier B) ──
    # Contrairement au lot pilote ci-dessus, ces 20 identités viennent bien de
    # Fritzing (recherche par CONTENU dans `contrib/`, pas par nom de fichier —
    # 79 % des fichiers de ce dossier ont un nom de fichier opaque, seul le vrai
    # nom vit dans `<title>`). Chaque bibliothèque est VÉRIFIÉE via le vrai
    # `registry_lookup.lookup_component` ; chaque brochage vient d'une fiche
    # `.fzp` réelle (dédoublonnage double-rangée géré par l'outil d'import).
    # `wiring="known"` partout où le nombre de broches est dessinable par
    # `resolve_generic` (2-8 en rangée simple, ou pair en DIP). À cette
    # époque, `sharp_memory_display` (9) et `winc1500` (13) n'entraient dans
    # aucune de ces plages et étaient donc `"unknown"`. Depuis, TODO #58
    # (2026-08-20) a étendu la rangée simple aux impairs 9/11/13 et leur a
    # donné une entrée catalogue : les deux sont maintenant `"known"`
    # (cf. plus bas dans ce fichier).
    # Écartés à la vérification : `sen6x`/EEPROM I2C externe/émetteur IR (pas
    # de bibliothèque propre trouvée) et `pcf8523` (bibliothèque personnelle
    # de 2014, même profil que `RFM69` déjà écarté au lot précédent).
    Component(id="tmp006", function="sensor", mounting="breadboard", wiring="known", documents=('tmp006',),
              description="Capteur infrarouge de température sans contact TMP006 (thermopile).",
              lib_name="Adafruit TMP006",
              keywords=('tmp006', 'capteur infrarouge sans contact', 'thermometre sans contact',
                        'thermopile', 'contactless infrared temperature sensor', 'non-contact thermometer',
                        'sensor infrarrojo sin contacto', 'termometro senza contatto')),
    Component(id="tmp007", function="sensor", mounting="breadboard", wiring="known", documents=('tmp007',),
              description="Capteur infrarouge de température sans contact TMP007 (thermopile, successeur du TMP006).",
              lib_name="Adafruit TMP007 Library",
              keywords=('tmp007', 'capteur infrarouge sans contact', 'thermometre sans contact',
                        'thermopile', 'contactless infrared temperature sensor', 'non-contact thermometer',
                        'sensor infrarrojo sin contacto', 'termometro senza contatto')),
    Component(id="si1145", function="sensor", mounting="breadboard", wiring="known", documents=('si1145',),
              description="Capteur d'indice UV, lumière infrarouge et visible SI1145.",
              lib_name="Adafruit SI1145 Library",
              keywords=('si1145', 'indice uv', 'capteur uv infrarouge visible', 'uv index sensor',
                        'infrared visible light sensor', 'sensor de indice uv', 'sensore di indice uv')),
    Component(id="adt7410", function="sensor", mounting="breadboard", wiring="known", documents=('adt7410',),
              description="Capteur de température I2C haute précision ADT7410.",
              lib_name="Adafruit ADT7410 Library",
              keywords=('adt7410', 'capteur de temperature precision', 'high precision temperature sensor',
                        'sensor de temperatura de precision', 'sensore di temperatura di precisione')),
    Component(id="ds3502", function="output", mounting="breadboard", wiring="known", documents=('ds3502',),
              description="Potentiomètre numérique I2C DS3502, résistance pilotée par code.",
              lib_name="Adafruit DS3502",
              keywords=('ds3502', 'potentiometre numerique', 'resistance pilotee par i2c',
                        'digital potentiometer', 'i2c controlled resistance', 'potenciometro digital',
                        'potenziometro digitale')),
    Component(id="fram", function="storage", mounting="breadboard", wiring="known", documents=('fram',),
              description="Mémoire FRAM I2C non volatile, lecture/écriture rapide et illimitée.",
              lib_name="Adafruit FRAM I2C",
              keywords=('fram', 'memoire fram', 'memoire non volatile i2c', 'non-volatile memory',
                        'fast rewrite memory', 'memoria fram', 'memoria no volatil', 'memoria non volatile')),
    Component(id="mprls", function="sensor", mounting="breadboard", wiring="known", documents=('mprls',),
              description="Capteur de pression MPRLS (pompes, manchons, niveaux de liquide), interface I2C.",
              lib_name="Adafruit MPRLS Library",
              keywords=('mprls', 'capteur de pression', 'pression pour pompe', 'ported pressure sensor',
                        'pump pressure sensor', 'sensor de presion', 'sensore di pressione')),
    Component(id="hdc1008", function="sensor", mounting="breadboard", wiring="known", documents=('hdc1008',),
              description="Capteur de température et d'humidité I2C HDC1008.",
              lib_name="Adafruit HDC1000 Library",
              keywords=('hdc1008', 'hdc1000', 'temperature et humidite', 'temperature humidity sensor',
                        'sensor de temperatura y humedad', 'sensore di temperatura e umidita')),
    Component(id="adxl335", function="sensor", mounting="breadboard", wiring="known", documents=('adxl335',),
              description="Accéléromètre analogique 3 axes ADXL335.",
              lib_name="Accelerometer ADXL335",
              keywords=('adxl335', 'accelerometre analogique 3 axes', 'analog 3 axis accelerometer',
                        'acelerometro analogico 3 ejes', 'accelerometro analogico 3 assi')),
    Component(id="bluefruit_le", function="communication", mounting="breadboard", wiring="known", documents=('bluefruit_le',),
              description="Module Bluetooth Low Energy Bluefruit LE (UART ou SPI).",
              lib_name="Adafruit BluefruitLE nRF51",
              keywords=('bluefruit le', 'bluetooth low energy', 'module bluetooth ble', 'ble module',
                        'modulo bluetooth', 'modulo bluetooth ble')),
    Component(id="spi_flash", function="storage", mounting="breadboard", wiring="known", documents=('spi_flash',),
              description="Mémoire flash SPI externe (stockage de fichiers, capteurs, journaux).",
              lib_name="Adafruit SPIFlash",
              keywords=('spi flash', 'memoire flash spi', 'external flash memory', 'memoria flash spi',
                        'memoria flash esterna')),
    Component(id="dotstar", function="display", mounting="breadboard", wiring="known", documents=('dotstar',),
              description="Bande de LEDs adressables DotStar (APA102), pilotée par SPI (données + horloge).",
              lib_name="Adafruit DotStar",
              keywords=('dotstar', 'apa102', 'bande led adressable spi', 'addressable led strip spi',
                        'led strip apa102', 'tira led direccionable', 'striscia led indirizzabile')),
    Component(id="tsl2561", function="sensor", mounting="breadboard", wiring="known", documents=('tsl2561',),
              description="Capteur de luminosité I2C haute précision TSL2561.",
              lib_name="Adafruit TSL2561",
              keywords=('tsl2561', 'capteur de luminosite precis', 'luxmetre precis', 'precision light sensor',
                        'lux sensor', 'sensor de luz', 'sensore di luce')),
    Component(id="sharp_memory_display", function="display", mounting="breadboard", wiring="known", documents=('sharp_memory_display',),
              description="Écran mémoire réflectif SHARP (faible consommation, type liseuse).",
              lib_name="Adafruit SHARP Memory Display",
              keywords=('sharp memory display', 'ecran memoire reflectif', 'low power reflective display',
                        'memory lcd', 'pantalla de memoria', 'display a memoria')),
    Component(id="winc1500", function="communication", mounting="breadboard", wiring="known", documents=('winc1500',),
              description="Module WiFi WINC1500, interface SPI.",
              lib_name="WiFi101",
              keywords=('winc1500', 'module wifi spi', 'wifi module spi', 'modulo wifi spi')),
    Component(id="tmp36", function="sensor", mounting="breadboard", wiring="known",
              description="Capteur de température analogique TMP36, tension proportionnelle à la température.",
              keywords=('tmp36', 'capteur de temperature analogique', 'analog temperature sensor',
                        'sensor de temperatura analogico', 'sensore di temperatura analogico')),
    Component(id="flex_sensor", function="sensor", mounting="breadboard", wiring="known",
              description="Capteur de flexion (résistance variable selon la courbure).",
              keywords=('flex sensor', 'capteur de flexion', 'capteur de courbure', 'bend sensor',
                        'sensor de flexion', 'sensore di flessione')),
    Component(id="si4713", function="communication", mounting="breadboard", wiring="known", documents=('si4713',),
              description="Émetteur FM stéréo Si4713, piloté en I2C.",
              lib_name="Adafruit Si4713 Library",
              keywords=('si4713', 'emetteur fm', 'stereo fm transmitter', 'transmisor fm',
                        'trasmettitore fm')),
    Component(id="ads7830", function="sensor", mounting="breadboard", wiring="known", documents=('ads7830',),
              description="Convertisseur analogique-numérique I2C 8 voies ADS7830.",
              lib_name="Adafruit ADS7830",
              keywords=('ads7830', 'convertisseur analogique numerique 8 voies', '8 channel adc',
                        'conversor adc 8 canales', 'convertitore adc 8 canali')),
    Component(id="trellis", function="input", mounting="breadboard", wiring="known", documents=('trellis',),
              description="Grille de boutons rétroéclairés 4x4 Trellis, pilotée en I2C.",
              lib_name="Adafruit Trellis Library",
              keywords=('trellis', 'clavier lumineux 4x4', 'grille de boutons retroeclaires',
                        'backlit button grid', 'illuminated keypad 4x4', 'teclado retroiluminado',
                        'tastiera retroilluminata')),
    # Trouvé dans core/ (pas contrib/) en poursuivant le lot #2 : la quasi-
    # totalité de core/ recoupe déjà le registre ou vise des puces gyro/accel
    # obsolètes (2008-2012, supplantées par mpu6050/bno055 déjà au registre) —
    # celui-ci est le seul candidat clairement neuf et non redondant trouvé.
    Component(id="ir_reflective_sensor", function="sensor", mounting="breadboard", wiring="known",
              description="Capteur réflectif infrarouge (émetteur IR + phototransistor), détecte une surface proche ou une ligne au sol — type QRE1113/QRD1114.",
              keywords=('qre1113', 'qrd1114', 'capteur reflectif infrarouge', 'detecteur de ligne',
                        'capteur suiveur de ligne', 'infrared reflective sensor', 'line follower sensor',
                        'ir reflective sensor', 'sensor reflectivo infrarrojo', 'sensor seguidor de linea',
                        'sensore riflettente infrarosso', 'sensore segui linea')),

    # ── Lot #4 (2026-08-19) — poursuite systématique de `contrib/` (317 titres
    # distincts passés en revue un par un, pas seulement les familles les plus
    # visibles) : successeurs modernes de puces déjà au registre (MMC5603 vs
    # hmc5883l, INA228 vs ina219/226/3221), deux drivers pas-à-pas silencieux,
    # un multiplexeur I2C, deux capteurs analogiques sans bibliothèque.
    # `ir_transmitter` volontairement ÉCARTÉ : `ir_receiver` référence déjà
    # IRremote, qui gère l'émission ET la réception — un second id serait un
    # quasi-doublon, pas une identité neuve.
    Component(id="mmc5603", function="sensor", mounting="breadboard", wiring="known", documents=('mmc5603',),
              description="Magnétomètre 3 axes I2C MMC5603 (boussole numérique).",
              lib_name="Adafruit MMC56x3",
              keywords=('mmc5603', 'magnetometre 3 axes', 'boussole numerique', 'triple axis magnetometer',
                        'digital compass', 'magnetometro 3 ejes', 'brujula digital', 'magnetometro 3 assi',
                        'bussola digitale')),
    Component(id="hdc3021", function="sensor", mounting="breadboard", wiring="known", documents=('hdc3021',),
              description="Capteur de température et d'humidité I2C haute précision HDC3021.",
              lib_name="Adafruit HDC302x",
              keywords=('hdc3021', 'temperature et humidite precision', 'high precision temperature humidity sensor',
                        'sensor de temperatura y humedad de precision', 'sensore di temperatura e umidita di precisione')),
    Component(id="ina228", function="sensor", mounting="breadboard", wiring="known", documents=('ina228',),
              description="Moniteur de puissance I2C INA228 (courant, tension, puissance), haute précision 20 bits.",
              lib_name="Adafruit INA228 Library",
              keywords=('ina228', 'moniteur de puissance precis', 'capteur de courant haute precision',
                        'high precision power monitor', '20-bit current sensor', 'monitor de potencia',
                        'monitor di potenza')),
    Component(id="opt4048", function="sensor", mounting="breadboard", wiring="known", documents=('opt4048',),
              description="Capteur de couleur XYZ I2C OPT4048, haute précision colorimétrique.",
              lib_name="Adafruit OPT4048",
              keywords=('opt4048', 'capteur de couleur precis', 'xyz color sensor', 'precision color sensor',
                        'sensor de color preciso', 'sensore di colore preciso')),
    Component(id="ina169", function="sensor", mounting="breadboard", wiring="known",
              description="Capteur de courant analogique INA169, sortie tension proportionnelle au courant.",
              keywords=('ina169', 'capteur de courant analogique', 'analog current sensor',
                        'sensor de corriente analogico', 'sensore di corrente analogico')),
    Component(id="guva_s12sd", function="sensor", mounting="breadboard", wiring="known",
              description="Capteur UV analogique GUVA-S12SD.",
              keywords=('guva-s12sd', 'guva s12sd', 'capteur uv analogique', 'analog uv sensor',
                        'sensor uv analogico', 'sensore uv analogico')),
    Component(id="stspin220", function="motor_driver", mounting="breadboard", wiring="known", documents=('stspin220',),
              description="Driver de moteur pas-à-pas STSPIN220, fonctionnement silencieux (micro-pas).",
              lib_name="Adafruit STSPIN",
              keywords=('stspin220', 'driver pas a pas silencieux', 'silent stepper driver',
                        'controlador paso a paso silencioso', 'driver passo passo silenzioso')),
    Component(id="tmc2209", function="motor_driver", mounting="breadboard", wiring="known", documents=('tmc2209',),
              description="Driver de moteur pas-à-pas TMC2209, fonctionnement silencieux (StealthChop), pilotable en UART.",
              lib_name="TMC2209",
              keywords=('tmc2209', 'driver pas a pas silencieux', 'stealthchop', 'silent stepper driver uart',
                        'controlador paso a paso silencioso', 'driver passo passo silenzioso')),
    Component(id="i2c_multiplexer", function="output", mounting="breadboard", wiring="known", documents=('i2c_multiplexer',),
              description="Multiplexeur I2C 8 canaux (famille PCA9548/TCA9548A), pour combiner plusieurs capteurs de même adresse.",
              lib_name="TCA9548A",
              keywords=('pca9548', 'tca9548a', 'multiplexeur i2c', 'meme adresse i2c', 'i2c multiplexer',
                        'same i2c address', 'multiplexor i2c', 'misma direccion i2c', 'multiplexer i2c',
                        'stesso indirizzo i2c')),
    Component(id="lps28", function="sensor", mounting="breadboard", wiring="known", documents=('lps28',),
              description="Capteur de pression I2C LPS28.",
              lib_name="Adafruit LPS28",
              keywords=('lps28', 'capteur de pression', 'pressure sensor', 'sensor de presion',
                        'sensore di pressione')),

    # ── Lot #5 (2026-08-19) — audit systématique des 317 titres de `contrib/`
    # ligne par ligne (le lot #4 avait encore des trous). Un premier passage
    # automatique de vérification s'est révélé FAUX (le mot « adafruit », déjà
    # keyword de `motor_shield_v2` depuis avant ce chantier, matchait quasiment
    # tous les titres par accident) : refait avec un filtre plus strict, 80
    # titres non appariés sur 317, dont 4 se sont avérés être de vraies
    # identités neuves après vérification une par une (le reste = variantes
    # déjà couvertes, infrastructure, ou cartes de développement).
    Component(id="eink_display", function="display", mounting="breadboard", wiring="known", documents=('eink_display',),
              description="Écran à encre électronique (e-paper), très faible consommation.",
              lib_name="Adafruit EPD",
              keywords=('eink', 'e-ink', 'encre electronique', 'ecran e-paper', 'e-paper display',
                        'electronic ink screen', 'pantalla de tinta electronica', 'display a inchiostro elettronico')),
    Component(id="nau7802", function="sensor", mounting="breadboard", wiring="known", documents=('nau7802',),
              description="Convertisseur ADC 24 bits I2C NAU7802 pour cellule de charge (alternative au HX711).",
              lib_name="Adafruit NAU7802 Library",
              keywords=('nau7802', 'cellule de charge i2c', '24-bit load cell adc', 'celula de carga i2c',
                        'cella di carico i2c')),
    Component(id="sen5x", function="sensor", mounting="breadboard", wiring="known", documents=('sen5x',),
              description="Capteur environnemental multi-paramètres Sensirion SEN54/SEN55 (particules fines, VOC, NOx, température, humidité).",
              lib_name="Sensirion I2C SEN5X",
              keywords=('sen54', 'sen55', 'capteur qualite de l\'air multi-parametres', 'particules fines voc',
                        'multi-parameter air quality sensor', 'sensor de calidad del aire',
                        'sensore di qualita dell\'aria')),
    Component(id="gc9a01", function="display", mounting="breadboard", wiring="known", documents=('gc9a01',),
              description="Écran TFT rond IPS 240x240, contrôleur GC9A01.",
              lib_name="Adafruit GC9A01A",
              keywords=('gc9a01', 'ecran tft rond', 'round tft display', 'pantalla tft redonda',
                        'display tft rotondo')),

    # ── TODO #69 (2026-08-27) : le lot d'identites revele par le balayage
    # des serigraphies du #57. Ce ne sont PAS des alias : ce sont des pieces
    # que le registre ne connaissait pas.
    #
    # ⛔ CHAQUE bibliotheque est VERIFIEE dans l'index Arduino, jamais
    # supposee -- meme contrat que le #57, et la mesure du jour montre
    # pourquoi : `lookup_component('hc12')` rend « libasm », un assembleur
    # pour CPU retro, parce que le HC12 de Motorola en est un. Le module
    # radio HC-12 n'a donc AUCUNE entree ici : aucune bibliotheque de l'index
    # ne le vise. Idem pour AJ-SR04M et les RCWL-16xx introuvables.
    #
    # ⚠️ LE GAZ MESURE N'EST PAS AFFIRME pour les MQ autres que le MQ-131.
    # Les fiches de bibliotheque enumerent les references SANS dire ce que
    # chacune detecte, et l'inventer serait exactement la supposition que ce
    # contrat interdit. Le renseigner demande une datasheet, pas une
    # deduction.
    # Source : lib dediee « MQ131 gas sensor » (Olivier Staquet) : « measuring ozone (O3) concentration with sensor MQ131 ».
    Component(id="mq131", function="sensor", mounting="breadboard",
              wiring="unknown", documents=('mq131',),
              description="Capteur de gaz MQ-131 : mesure la concentration d'ozone (O₃), sortie analogique.",
              keywords=('MQ-131', 'MQ131', "capteur d'ozone", 'ozone sensor', 'sensor de ozono', 'sensore di ozono', 'O3', 'capteur de gaz MQ-131', 'gas sensor MQ-131')),
    # Source : MQSpaceData enumere MQ-136 dans son paragraphe.
    Component(id="mq136", function="sensor", mounting="breadboard",
              wiring="unknown", documents=('mq136',),
              description="Capteur de gaz MQ-136 (famille MQ, sortie analogique).",
              keywords=('MQ-136', 'MQ136', 'capteur de gaz MQ-136', 'gas sensor MQ-136', 'sensor de gas MQ-136', 'sensore di gas MQ-136')),
    # Source : MQSpaceData enumere MQ-137 ; la lib dediee « MQ137 » vise ESP8266.
    Component(id="mq137", function="sensor", mounting="breadboard",
              wiring="unknown", documents=('mq137',),
              description="Capteur de gaz MQ-137 (famille MQ, sortie analogique).",
              keywords=('MQ-137', 'MQ137', 'capteur de gaz MQ-137', 'gas sensor MQ-137', 'sensor de gas MQ-137', 'sensore di gas MQ-137')),
    # Source : MQSpaceData enumere MQ-138.
    Component(id="mq138", function="sensor", mounting="breadboard",
              wiring="unknown", documents=('mq138',),
              description="Capteur de gaz MQ-138 (famille MQ, sortie analogique).",
              keywords=('MQ-138', 'MQ138', 'capteur de gaz MQ-138', 'gas sensor MQ-138', 'sensor de gas MQ-138', 'sensore di gas MQ-138')),
    # Source : MQSpaceData enumere MQ-214.
    Component(id="mq214", function="sensor", mounting="breadboard",
              wiring="unknown", documents=('mq214',),
              description="Capteur de gaz MQ-214 (famille MQ, sortie analogique).",
              keywords=('MQ-214', 'MQ214', 'capteur de gaz MQ-214', 'gas sensor MQ-214', 'sensor de gas MQ-214', 'sensore di gas MQ-214')),
    # Source : MQSpaceData enumere MQ-216.
    Component(id="mq216", function="sensor", mounting="breadboard",
              wiring="unknown", documents=('mq216',),
              description="Capteur de gaz MQ-216 (famille MQ, sortie analogique).",
              keywords=('MQ-216', 'MQ216', 'capteur de gaz MQ-216', 'gas sensor MQ-216', 'sensor de gas MQ-216', 'sensore di gas MQ-216')),
    # Source : MQUnifiedsensor (Miguel Califa) enumere MQ303A.
    Component(id="mq303a", function="sensor", mounting="breadboard",
              wiring="unknown", documents=('mq303a',),
              description="Capteur de gaz MQ-303A (famille MQ, sortie analogique).",
              keywords=('MQ-303A', 'MQ303A', 'capteur de gaz MQ-303A', 'gas sensor MQ-303A', 'sensor de gas MQ-303A', 'sensore di gas MQ-303A')),
    # Source : MQSpaceData enumere MQ306A.
    Component(id="mq306a", function="sensor", mounting="breadboard",
              wiring="unknown", documents=('mq306a',),
              description="Capteur de gaz MQ-306A (famille MQ, sortie analogique).",
              keywords=('MQ-306A', 'MQ306A', 'capteur de gaz MQ-306A', 'gas sensor MQ-306A', 'sensor de gas MQ-306A', 'sensore di gas MQ-306A')),
    # Source : MQSpaceData enumere MQ307A.
    Component(id="mq307a", function="sensor", mounting="breadboard",
              wiring="unknown", documents=('mq307a',),
              description="Capteur de gaz MQ-307A (famille MQ, sortie analogique).",
              keywords=('MQ-307A', 'MQ307A', 'capteur de gaz MQ-307A', 'gas sensor MQ-307A', 'sensor de gas MQ-307A', 'sensore di gas MQ-307A')),
    # Source : MQUnifiedsensor enumere MQ309A.
    Component(id="mq309a", function="sensor", mounting="breadboard",
              wiring="unknown", documents=('mq309a',),
              description="Capteur de gaz MQ-309A (famille MQ, sortie analogique).",
              keywords=('MQ-309A', 'MQ309A', 'capteur de gaz MQ-309A', 'gas sensor MQ-309A', 'sensor de gas MQ-309A', 'sensore di gas MQ-309A')),

    # Les variantes MH-Z19B/C/D/E ne sont PAS ici : ce sont des mots-cles de
    # `mhz19` (le registre n'a pas de notion de variante, et le precedent
    # existait deja pour B et C). MH-Z14A et MH-Z1311A, eux, sont des pieces
    # distinctes avec leur propre bibliotheque.
    # Source : « MH-Z CO2 Sensors » (Tobias Schurg et al.) nomme MH-Z14A dans sa phrase.
    Component(id="mhz14a", function="sensor", mounting="breadboard",
              wiring="unknown", documents=('mhz14a',),
              description="Capteur de CO₂ NDIR MH-Z14A (liaison série UART ou sortie PWM).",
              keywords=('MH-Z14A', 'MHZ14A', 'MH-Z14', 'capteur CO2 MH-Z14A', 'CO2 sensor MH-Z14A', 'sensor de CO2 MH-Z14A', 'sensore di CO2 MH-Z14A', 'NDIR CO2')),
    # Source : MHZCO2 enumere MHZ1311A.
    Component(id="mhz1311a", function="sensor", mounting="breadboard",
              wiring="unknown", documents=('mhz1311a',),
              description="Capteur de CO₂ NDIR MH-Z1311A (liaison série UART ou sortie PWM).",
              keywords=('MH-Z1311A', 'MHZ1311A', 'capteur CO2 MH-Z1311A', 'CO2 sensor MH-Z1311A', 'sensor de CO2 MH-Z1311A', 'sensore di CO2 MH-Z1311A', 'NDIR CO2')),

    # ⚠️ Le RCWL-0516 est un RADAR, les RCWL-1x05 des ultrasons I2C : meme
    # prefixe, trois composants differents, et surtout PAS le cablage du
    # HC-SR04 (declenchement par impulsion). D'ou trois entrees separees.
    # Source : lib dediee « RCWL0516 » (Dean Gienger) : « control an RCWL-0516 motion detection radar sensor ».
    Component(id="rcwl0516", function="sensor", mounting="breadboard",
              wiring="unknown", documents=('rcwl0516',),
              description="Détecteur de mouvement RCWL-0516 : radar Doppler micro-ondes, traverse les cloisons fines.",
              keywords=('RCWL-0516', 'RCWL0516', 'radar doppler', 'capteur de mouvement radar', 'microwave motion sensor', 'sensor de movimiento radar', 'sensore di movimento radar', 'detection de presence radar')),
    # Source : « RCWL_1X05 » (juh) nomme RCWL-1005 dans sa phrase.
    Component(id="rcwl1005", function="sensor", mounting="breadboard",
              wiring="unknown", documents=('rcwl1005',),
              description="Télémètre à ultrasons RCWL-1005 en mode I2C (puce RCWL-9600).",
              keywords=('RCWL-1005', 'RCWL1005', 'RCWL-9600', 'RCWL-9623', 'RCWL-9624', 'ultrason I2C', 'I2C ultrasonic distance', 'distancia ultrasonica I2C', 'distanza a ultrasuoni I2C', 'telemetre ultrason I2C')),
    # Source : « RCWL_1X05 » (juh) nomme RCWL-1605 dans sa phrase.
    Component(id="rcwl1605", function="sensor", mounting="breadboard",
              wiring="unknown", documents=('rcwl1605',),
              description="Télémètre à ultrasons RCWL-1605 en mode I2C (puce RCWL-9600).",
              keywords=('RCWL-1605', 'RCWL1605', 'RCWL-9600', 'ultrason I2C', 'I2C ultrasonic distance', 'distancia ultrasonica I2C', 'distanza a ultrasuoni I2C', 'telemetre ultrason I2C')),
    # Source : lib « jsnsr04t » : « The boards JSN-SR-04T provides distance measured by ultrasonic transducter ».
    Component(id="jsn_sr04t", function="sensor", mounting="breadboard",
              wiring="unknown", documents=('jsn_sr04t',),
              description="Télémètre à ultrasons étanche JSN-SR04T, sonde déportée pour l'extérieur ou un réservoir.",
              keywords=('JSN-SR04T', 'JSNSR04T', 'ultrason etanche', 'waterproof ultrasonic', 'ultrasonido impermeable', 'ultrasuoni impermeabile', 'capteur de distance etanche', "niveau d'eau reservoir")),
)


def registry() -> tuple[Component, ...]:
    return REGISTRY


def by_id(cid: str,
          items: tuple[Component, ...] | None = None) -> Component | None:
    pool = registry() if items is None else items
    return next((c for c in pool if c.id == cid), None)


def components_for_document(
        doc_id: str,
        items: tuple[Component, ...] | None = None) -> tuple[Component, ...]:
    """Every component this document describes.

    The reverse of `documents`, derived by scanning: at ~85 entries a separate
    reverse table would be a second thing to keep in sync for no gain.
    """
    pool = registry() if items is None else items
    return tuple(c for c in pool if doc_id in c.documents)

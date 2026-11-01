"""Un composant SANS bibliotheque ne doit pas s'en faire injecter une.

Contexte du defaut d'origine (QA AJ4.1, 2026-09-07). Le prompt « lis une
thermistance sur A0 » rendait un schema de DS18B20 -- correctement cable, mais
pour le mauvais composant. Le cablage n'y etait pour rien : il etait fidele au
code, et le code parlait a un DS18B20 parce que le RAG avait injecte
`DallasTemperature` (score 0.543, au-dessus du plancher de 0.50). Une
thermistance se lit avec `analogRead` et un pont diviseur ; elle n'a AUCUNE
bibliotheque.

Autres degats mesures le meme jour, tous du bruit passant le plancher :
  « lis un capteur TMP36 sur A0 »      -> MFRC522 (un lecteur RFID) a 0.519
  « lis un capteur de force FSR »      -> Encoder a 0.527

Le mecanisme qui empeche ca existait deja et fonctionnait -- `_prompt_is_basic_component`,
la « garde composant de base » -- mais son lexique s'arretait a la LED, au
bouton, au buzzer, au potentiometre et a la resistance. Les composants ajoutes
par le #94 n'y etaient pas.

⚠️ Le banc `bench_rag.py` ne bouge PAS sur cette correction : ses 164 prompts
ne couvrent pas cette classe de composants. C'est une limite de la batterie,
pas une preuve d'innocuite -- d'ou ce fichier.

Run : python scripts/test_basic_component_no_lib.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.rag import _BASIC_NO_LIB_KEYWORDS, _prompt_is_basic_component

# Composants sans bibliotheque : le prompt les nomme, rien ne doit etre injecte.
_SANS_LIB = [
    "lis une thermistance sur A0",
    "affiche la temperature avec une thermistance",
    "read a thermistor on A0",
    "lis un capteur TMP36 sur A0",
    "lis un capteur de force FSR sur A0",
    "a force sensor on A0",
    "un capteur de flexion sur A0",
    "lis l'humidite du sol sur A0",
    "a soil moisture sensor on A0",
    "un interrupteur reed sur la broche 4",
    "a reed switch on pin 4",
    "un capteur d'inclinaison sur la broche 4",
    "un interrupteur a bascule sur la broche 4",
    "un capteur tactile sur la broche 4",
    # 2e lot (2026-09-07) : le reste des composants a broche nue. Les trois
    # premiers recevaient du bruit mesure ; les suivants etaient muets par
    # CHANCE (rien ne passait le plancher) et le sont desormais par REGLE.
    "un detecteur de son sur A0",
    "un capteur de flamme sur A0",
    "un capteur de courant analogique sur A0",
    "un capteur de courant ACS712 sur A0",
    "un capteur UV sur A0",
    "un capteur reflectif infrarouge sur A0",
    "une photoresistance KY-018 sur A0",
    "pilote un relais sur la broche 7",
    "un haut-parleur sur la broche 7",
    "un joystick sur A0 et A1",
    "un capteur de pluie sur A0",
    "un capteur a effet hall sur la broche 4",
    "un solenoide sur la broche 7",
]

# Prompts qui ont BESOIN d'une bibliotheque et doivent continuer d'en recevoir.
# C'est la moitie qui compte : sans eux, vider la table ferait passer le test.
_AVEC_LIB = [
    "lis un capteur de temperature sur A0",     # generique -> DS18B20/DHT/...
    "affiche la temperature avec un DS18B20",
    "capteur de temperature et d'humidite DHT22",
    "un capteur de force avec un HX711",        # puce nommee -> echappatoire
    "affiche l'heure avec un module RTC DS1307",
    "un ecran OLED SSD1306",
    # ⛔ Le piege du 2e lot : un ACS712 se lit avec analogRead, mais un INA219
    # est en I2C et a bien une bibliotheque. Le mot « capteur de courant » NU
    # casserait celui-ci pour reparer celui-la.
    "un capteur de courant INA219",
    "un lecteur RFID MFRC522",
    "joue un mp3 avec un DFPlayer",
    "un accelerometre MPU6050",
    "mesure la distance avec un HC-SR04",
]


def test_a_library_less_component_gets_no_library():
    """Le defaut d'origine, et ses voisins mesures le meme jour.

    La garde repond AVANT tout retrieval, donc ce test ne charge pas le modele
    d'embeddings -- il est vrai meme sans ONNX.
    """
    for prompt in _SANS_LIB:
        assert _injection_supprimee(prompt), (
            f"{prompt!r} designe un composant sans bibliotheque, la garde "
            f"« composant de base » aurait du le reconnaitre")


def _injection_supprimee(prompt: str) -> bool:
    """La condition REELLE, celle qu'applique `_build_lib_context`.

    La garde ne decide pas seule : nommer une puce la desactive. L'echappatoire
    vit dans l'appelant et vaut pour TOUTES les entrees de la table, ce qui
    evite d'ecrire un `override` par mot.
    """
    from ui.rag import prompt_names_a_chip
    return _prompt_is_basic_component(prompt) and not prompt_names_a_chip(prompt)


def test_a_component_that_needs_a_library_still_gets_one():
    """La moitie qui compte : la garde ne doit pas affamer les autres.

    ⛔ En particulier « capteur de temperature » GENERIQUE. Mettre le mot
    « temperature » dans la table corrigerait la thermistance en cassant ce
    cas-la : un prompt generique de temperature a besoin d'une lib (DS18B20,
    DHT...), et la garde le priverait de tout contexte.
    """
    for prompt in _AVEC_LIB:
        assert not _injection_supprimee(prompt), (
            f"{prompt!r} a besoin d'une bibliotheque, l'injection ne doit PAS "
            f"etre supprimee")


def test_naming_a_chip_reopens_the_gate():
    """L'echappatoire, enoncee plutot que deduite.

    « un capteur de force avec un HX711 » declenche BIEN la garde -- le mot
    « capteur de force » est dans la table -- mais la puce nommee la desactive,
    et la bibliotheque du HX711 est injectee. Sans ce test, quelqu'un pourrait
    « corriger » la table en retirant « capteur de force », et rouvrirait le
    defaut d'origine pour rien.
    """
    prompt = "un capteur de force avec un HX711"
    assert _prompt_is_basic_component(prompt), (
        "le mot generique matche bien : c'est voulu")
    assert not _injection_supprimee(prompt), (
        "mais la puce nommee doit rouvrir la porte")


def test_the_generic_words_stay_out_of_the_table():
    """Enonce comme une regle, pas seulement verifie par ses consequences.

    Un mot generique ici priverait de contexte toute une famille. Le test
    ci-dessus l'attrape par ricochet ; celui-ci le dit, pour que le message
    d'echec designe la cause.
    """
    interdits = {
        "temperature", "température", "capteur de temperature",
        "capteur de température", "temperature sensor",
        "humidite", "humidité", "humidity",
        "pression", "pressure", "presion",
        "interrupteur", "switch", "interruptor", "interruttore",
        "capteur", "sensor", "sensore",
        "capteur de courant", "current sensor", "sensor de corriente",
        "lumiere", "lumière", "light", "luminosite", "luminosité",
    }
    presents = sorted(k for k in _BASIC_NO_LIB_KEYWORDS if k.lower() in interdits)
    assert not presents, (
        f"Ces mots sont trop generiques pour la garde « composant de base » : "
        f"{presents}. Ils priveraient de bibliotheque des prompts qui en ont "
        f"besoin.")


def test_the_copied_words_still_exist_in_their_markers_lexicon():
    """Garde de DERIVE : `rag.py` recopie des mots de `ui/wiring/markers.py`.

    La copie est assumee -- `rag.py` ne doit pas dependre du paquet cablage --
    mais elle doit rester vraie. Si un lexique de `markers` est reecrit et
    qu'un mot disparait, la garde « composant de base » continuerait de
    reconnaitre un mot que le detecteur ne connait plus : le prompt
    n'injecterait aucune lib ET ne dessinerait pas le bon composant.
    """
    import ui.wiring.markers as M

    attendus = {
        "thermistance": M._TEMP_SENSOR_KEYWORDS,
        "thermistor": M._TEMP_SENSOR_KEYWORDS,
        "termistor": M._TEMP_SENSOR_KEYWORDS,
        "termistore": M._TEMP_SENSOR_KEYWORDS,
        "ntc": M._TEMP_SENSOR_KEYWORDS,
        "tmp36": M._TMP36_KEYWORDS,
        "fsr": M._FORCE_SENSOR_KEYWORDS,
        "capteur de force": M._FORCE_SENSOR_KEYWORDS,
        "force sensor": M._FORCE_SENSOR_KEYWORDS,
        "capteur de flexion": M._FLEX_SENSOR_KEYWORDS,
        "flex sensor": M._FLEX_SENSOR_KEYWORDS,
        "soil moisture": M._SOIL_MOISTURE_KEYWORDS,
        "humidité du sol": M._SOIL_MOISTURE_KEYWORDS,
        "interrupteur reed": M._REED_SWITCH_KEYWORDS,
        "reed switch": M._REED_SWITCH_KEYWORDS,
        "capteur d'inclinaison": M._TILT_SWITCH_KEYWORDS,
        "tilt switch": M._TILT_SWITCH_KEYWORDS,
        "slide switch": M._SLIDE_SWITCH_KEYWORDS,
        "toggle switch": M._TOGGLE_SWITCH_KEYWORDS,
        "capteur tactile": M._TOUCH_SENSOR_KEYWORDS,
        "touch sensor": M._TOUCH_SENSOR_KEYWORDS,
        # 2e lot : ceux qui ont un lexique cote detecteur.
        "détecteur de son": M._SOUND_SENSOR_KEYWORDS,
        "sound detector": M._SOUND_SENSOR_KEYWORDS,
        "microphone": M._SOUND_SENSOR_KEYWORDS,
        "ky-018": M._KY018_KEYWORDS,
        "ky018": M._KY018_KEYWORDS,
        "relais": M._RELAY_KEYWORDS,
        "haut-parleur": M._SPEAKER_KEYWORDS,
        "speaker": M._SPEAKER_KEYWORDS,
        "joystick": M._JOYSTICK_KEYWORDS,
        # 3e lot (2026-09-09) : le suiveur de ligne du #98.
        "suiveur de ligne": M._IR_REFLECTIVE_KEYWORDS,
        "capteur de ligne": M._IR_REFLECTIVE_KEYWORDS,
        "detecteur de ligne": M._IR_REFLECTIVE_KEYWORDS,
        "line follower": M._IR_REFLECTIVE_KEYWORDS,
        "line sensor": M._IR_REFLECTIVE_KEYWORDS,
        "line tracking sensor": M._IR_REFLECTIVE_KEYWORDS,
        "sensor seguidor de linea": M._IR_REFLECTIVE_KEYWORDS,
        "sensore segui linea": M._IR_REFLECTIVE_KEYWORDS,
        "tcrt5000": M._IR_REFLECTIVE_KEYWORDS,
        "qre1113": M._IR_REFLECTIVE_KEYWORDS,
    }
    for mot, lexique in attendus.items():
        assert mot in _BASIC_NO_LIB_KEYWORDS, (
            f"{mot!r} a disparu de la table de rag.py")
        assert mot in lexique, (
            f"{mot!r} n'existe plus dans son lexique de markers.py : les deux "
            f"tables ont derive")


def test_the_line_follower_gets_no_library_in_any_wording():
    """⛔ Le trou laisse par le #98, trouve sur une question de l'utilisateur
    (« tu as bien rajoute ces capteurs dans le RAG ? ») le 2026-09-09.

    Le lot 3 du #98 avait ajoute ces expressions au lexique de `markers` pour
    DESSINER le composant, sans les recopier dans la table ci-dessus. Mesure
    avant correctif : SEPT formulations sur onze injectaient une bibliotheque
    sans le moindre rapport --
        « un capteur suiveur de ligne sur A0 » -> DS3502 (potentiometre
          numerique I2C) + deux capteurs de CO2, 2127 caracteres ;
        « un TCRT5000 sur A0 »                 -> TCA9548A (multiplexeur
          I2C), 5597 caracteres.
    C'est exactement le defaut que le #97 existe pour supprimer, re-ouvert
    par une moitie de checklist.

    ⚠️ On balaie TOUTES les formulations, pas une par langue : c'est
    precisement parce que quatre d'entre elles passaient par chance que le
    trou n'a saute aux yeux de personne.
    """
    formulations = [
        "un capteur suiveur de ligne sur A0",
        "un detecteur de ligne sur A0",
        "un capteur de ligne sur A0",
        "a line follower sensor on A0",
        "a line sensor on A0",
        "a line tracking sensor on A0",
        "un sensor seguidor de linea en A0",
        "un sensore segui linea su A0",
        "un TCRT5000 sur A0",
        "un capteur QRE1113 sur A0",
        "un capteur reflectif infrarouge sur A0",
    ]
    fautifs = [p for p in formulations if not _prompt_is_basic_component(p)]
    assert not fautifs, (
        f"{len(fautifs)} formulation(s) echappent a la garde : {fautifs}")


TESTS = [
    test_the_line_follower_gets_no_library_in_any_wording,
    test_a_library_less_component_gets_no_library,
    test_a_component_that_needs_a_library_still_gets_one,
    test_naming_a_chip_reopens_the_gate,
    test_the_generic_words_stay_out_of_the_table,
    test_the_copied_words_still_exist_in_their_markers_lexicon,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"OK   {t.__name__}")
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)

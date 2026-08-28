"""Catalog of the choices offered by the visual ambiguity modal in
beginner mode (cf docs/PROMPTUINO_FEATURES_SPEC.md Feature 2,
step 3).

For each option offered in the visual modal, we associate:
- An `option_id` identifier (= target type of the component after the choice)
- An SVG asset (file or inline content) for the illustrative icon
- A natural-language label (FR/EN/ES/IT)
- Examples / synonyms in parentheses (FR/EN/ES/IT)

Expanded catalog (Priority 1, 2026-06-02): the modal offers a choice
PER ambiguous output among 4 components (LED, buzzer, servo, DC motor) via
`GENERIC_OUTPUT_OPTIONS`. Open architecture: adding relay/vibrator/
electromagnet later = one `VisualOption` entry + one transformation
in `ambiguity_dialog._DEFAULT_TRANSFORMS`. Analog sensors
(LDR, thermistor, microphone) stay out of the catalog as long as their
rendering types do not exist.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# Project root directory (needed to resolve relative SVG paths
# from this module).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


# Iconic red LED SVG with light halo. Inline rather than an external
# asset because (1) we have no dedicated LED SVG in the catalog, (2) pure
# icon: it is NOT the LED rendering used on the schematic (that one will be
# the generic `horizontal/2pins.svg`), it is just for the modal.
LED_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg"
  viewBox="0 0 120 120" width="120" height="120">
  <!-- Halo de lumiere autour de la LED -->
  <circle cx="60" cy="48" r="42" fill="#fef3c7" opacity="0.6"/>
  <circle cx="60" cy="48" r="32" fill="#fde68a" opacity="0.8"/>
  <!-- Corps de la LED (dome rouge translucide) -->
  <ellipse cx="60" cy="50" rx="22" ry="26" fill="#dc2626"
           stroke="#7f1d1d" stroke-width="1.5"/>
  <!-- Reflet brillant sur le dome -->
  <ellipse cx="52" cy="42" rx="6" ry="10" fill="#fca5a5"
           opacity="0.7"/>
  <!-- Base/cathode -->
  <rect x="42" y="72" width="36" height="6" fill="#9ca3af"
        stroke="#4b5563" stroke-width="1"/>
  <!-- 2 pattes -->
  <line x1="52" y1="78" x2="52" y2="110" stroke="#6b7280"
        stroke-width="2.5" stroke-linecap="round"/>
  <line x1="68" y1="78" x2="68" y2="115" stroke="#6b7280"
        stroke-width="2.5" stroke-linecap="round"/>
</svg>"""


# Iconic buzzer SVG (black cylinder + hole + waves). Pure modal icon.
BUZZER_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg"
  viewBox="0 0 120 120" width="120" height="120">
  <ellipse cx="60" cy="40" rx="34" ry="13" fill="#374151"/>
  <rect x="26" y="40" width="68" height="40" fill="#4b5563"/>
  <ellipse cx="60" cy="80" rx="34" ry="13" fill="#6b7280"/>
  <circle cx="60" cy="40" r="5" fill="#111827"/>
  <line x1="52" y1="92" x2="52" y2="112" stroke="#6b7280"
        stroke-width="2.5" stroke-linecap="round"/>
  <line x1="68" y1="92" x2="68" y2="112" stroke="#6b7280"
        stroke-width="2.5" stroke-linecap="round"/>
  <path d="M96 34 q10 26 0 52" stroke="#f59e0b" stroke-width="3"
        fill="none" stroke-linecap="round"/>
  <path d="M104 26 q16 34 0 68" stroke="#fbbf24" stroke-width="3"
        fill="none" stroke-linecap="round"/>
</svg>"""


# Iconic servomotor SVG (blue housing + horn). Pure modal icon.
SERVO_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg"
  viewBox="0 0 120 120" width="120" height="120">
  <rect x="30" y="44" width="60" height="52" rx="4" fill="#2563eb"
        stroke="#1e40af" stroke-width="1.5"/>
  <rect x="52" y="28" width="16" height="18" fill="#1e40af"/>
  <rect x="36" y="20" width="48" height="7" rx="3" fill="#cbd5e1"
        stroke="#94a3b8" stroke-width="1"/>
  <circle cx="60" cy="23" r="4" fill="#64748b"/>
  <!-- 3 fils servo, convention standard : GND (brun) / VCC (rouge) / Signal (orange) -->
  <line x1="50" y1="96" x2="50" y2="112" stroke="#a16207"
        stroke-width="2.5" stroke-linecap="round"/>
  <line x1="60" y1="96" x2="60" y2="112" stroke="#dc2626"
        stroke-width="2.5" stroke-linecap="round"/>
  <line x1="70" y1="96" x2="70" y2="112" stroke="#ea580c"
        stroke-width="2.5" stroke-linecap="round"/>
</svg>"""


@dataclass
class VisualOption:
    """A choice presented in the visual modal.

    `option_id` : target type (e.g. "dc_motor", "led"). Used for the
        post-click dispatch in `studio_view._resolve_wiring_netlist`.
    `svg_path` : absolute path to the SVG file, or None if the icon
        is provided inline via `svg_inline`.
    `svg_inline` : raw SVG content (str). Ignored if `svg_path` is
        non-null.
    `labels` : dict `lang -> main label` (FR/EN/ES/IT).
    `examples` : dict `lang -> examples/synonyms` (FR/EN/ES/IT).
    `placeholder` : True if the option is generated dynamically without a
        dedicated SVG asset (component in the same category but absent from
        the rich catalog). The tile then shows a generic rendering.
    """
    option_id: str
    svg_path: Path | None
    svg_inline: str | None
    labels: dict[str, str]
    examples: dict[str, str]
    placeholder: bool = False


# Expanded catalog (Priority 1): 4 outputs offered per ambiguous output.
# Order = display order of the tiles in each section.
GENERIC_OUTPUT_OPTIONS: list[VisualOption] = [
    VisualOption(
        option_id="led",
        svg_path=None,
        svg_inline=LED_ICON_SVG,
        labels={"fr": "Voyant (LED)", "en": "Indicator (LED)",
                "es": "Indicador (LED)", "it": "Spia (LED)"},
        examples={"fr": "LED, lampe", "en": "LED, lamp",
                  "es": "LED, lámpara", "it": "LED, lampada"},
    ),
    VisualOption(
        option_id="buzzer",
        svg_path=None,
        svg_inline=BUZZER_ICON_SVG,
        labels={"fr": "Buzzer", "en": "Buzzer",
                "es": "Zumbador", "it": "Cicalino"},
        examples={"fr": "bip, alarme", "en": "beep, alarm",
                  "es": "pitido, alarma", "it": "bip, allarme"},
    ),
    VisualOption(
        option_id="servo",
        svg_path=None,
        svg_inline=SERVO_ICON_SVG,
        labels={"fr": "Servomoteur", "en": "Servo",
                "es": "Servo", "it": "Servo"},
        examples={"fr": "bras, angle", "en": "arm, angle",
                  "es": "brazo, ángulo", "it": "braccio, angolo"},
    ),
    VisualOption(
        option_id="dc_motor",
        svg_path=(_PROJECT_ROOT / "assets" / "wiring" / "components"
                  / "external" / "dc_motor.svg"),
        svg_inline=None,
        labels={"fr": "Moteur", "en": "Motor",
                "es": "Motor", "it": "Motore"},
        examples={"fr": "ventilateur, hélice", "en": "fan, propeller",
                  "es": "ventilador, hélice", "it": "ventilatore, elica"},
    ),
]


# H-bridge drivers offered AFTER confirming "Oui c'est un moteur" in
# beginner mode. Image tiles: dedicated SVG for L298N and L293D module; for
# the others (L293D chip, TB6612FNG, DRV8833) we reuse the generic DIP SVG
# placed on the BB, until better assets are available (Fritzing).
# The order = display order; L298N first = pre-selected default.
_EXTERNAL_DIR = _PROJECT_ROOT / "assets" / "wiring" / "components" / "external"
_DIP_GENERIC_SVG = (_PROJECT_ROOT / "assets" / "wiring" / "components"
                    / "dip" / "16pins.svg")

DRIVER_OPTIONS: list[VisualOption] = [
    VisualOption(
        option_id="l298n",
        svg_path=_EXTERNAL_DIR / "l298n.svg",
        svg_inline=None,
        labels={"fr": "L298N", "en": "L298N", "es": "L298N", "it": "L298N"},
        examples={"fr": "le plus courant", "en": "most common",
                  "es": "el más común", "it": "il più comune"},
    ),
    VisualOption(
        option_id="l293d_module",
        svg_path=_EXTERNAL_DIR / "l293d_module.svg",
        svg_inline=None,
        labels={"fr": "L293D (module)", "en": "L293D (module)",
                "es": "L293D (módulo)", "it": "L293D (modulo)"},
        examples={"fr": "carte breakout", "en": "breakout board",
                  "es": "placa breakout", "it": "scheda breakout"},
    ),
    VisualOption(
        option_id="l293d",
        svg_path=_DIP_GENERIC_SVG,
        svg_inline=None,
        labels={"fr": "L293D (puce)", "en": "L293D (chip)",
                "es": "L293D (chip)", "it": "L293D (chip)"},
        examples={"fr": "circuit intégré", "en": "bare IC",
                  "es": "circuito integrado", "it": "circuito integrato"},
    ),
    VisualOption(
        option_id="tb6612fng",
        svg_path=_DIP_GENERIC_SVG,
        svg_inline=None,
        labels={"fr": "TB6612FNG", "en": "TB6612FNG",
                "es": "TB6612FNG", "it": "TB6612FNG"},
        examples={"fr": "", "en": "", "es": "", "it": ""},
    ),
    VisualOption(
        option_id="drv8833",
        svg_path=_DIP_GENERIC_SVG,
        svg_inline=None,
        labels={"fr": "DRV8833", "en": "DRV8833",
                "es": "DRV8833", "it": "DRV8833"},
        examples={"fr": "", "en": "", "es": "", "it": ""},
    ),
]


# Labels of the modal itself (title, subtitle, buttons), not
# specific to a scenario. Multilang FR/EN/ES/IT.
DIALOG_LABELS: dict[str, dict[str, str]] = {
    "title": {
        "fr": "Que veux-tu brancher sur chaque sortie ?",
        "en": "What do you want to connect on each output?",
        "es": "¿Qué quieres conectar en cada salida?",
        "it": "Cosa vuoi collegare su ogni uscita?",
    },
    "title_single": {
        "fr": "Que veux-tu brancher sur cette sortie ?",
        "en": "What do you want to connect to this output?",
        "es": "¿Qué quieres conectar en esta salida?",
        "it": "Cosa vuoi collegare a questa uscita?",
    },
    "subtitle": {
        "fr": "Clique l'image qui correspond, pour chaque sortie.",
        "en": "Click the matching image, for each output.",
        "es": "Haz clic en la imagen correspondiente, para cada salida.",
        "it": "Fai clic sull'immagine corrispondente, per ogni uscita.",
    },
    "subtitle_single": {
        "fr": "Clique l'image qui correspond.",
        "en": "Click the matching image.",
        "es": "Haz clic en la imagen que corresponde.",
        "it": "Clicca l'immagine corrispondente.",
    },
    "cancel": {
        "fr": "Annuler",
        "en": "Cancel",
        "es": "Cancelar",
        "it": "Annulla",
    },
    "validate": {
        "fr": "Valider", "en": "Confirm", "es": "Validar", "it": "Conferma",
    },
    "output_on_pin": {
        "fr": "Sortie sur la broche {pin}",
        "en": "Output on pin {pin}",
        "es": "Salida en el pin {pin}",
        "it": "Uscita sul pin {pin}",
    },
    "motor_question": {
        "fr": "Ces broches forment peut-être un moteur ({pin}). Est-ce un moteur ?",
        "en": "These pins might be a motor ({pin}). Is it a motor?",
        "es": "Estos pines podrían ser un motor ({pin}). ¿Es un motor?",
        "it": "Questi pin potrebbero essere un motore ({pin}). È un motore?",
    },
    "motor_yes": {
        "fr": "Oui, c'est un moteur",
        "en": "Yes, it's a motor",
        "es": "Sí, es un motor",
        "it": "Sì, è un motore",
    },
    "motor_no": {
        "fr": "Non, ce sont des sorties séparées",
        "en": "No, these are separate outputs",
        "es": "No, son salidas separadas",
        "it": "No, sono uscite separate",
    },
    "driver_question": {
        "fr": "Quel module pilote ce moteur ?",
        "en": "Which module drives this motor?",
        "es": "¿Qué módulo controla este motor?",
        "it": "Quale modulo pilota questo motore?",
    },
    # Consolidated section: >=2 grouped motors, 1 checkbox per motor + 1 SINGLE
    # shared driver (aligns beginner mode with advanced mode).
    "motors_consolidated_question": {
        "fr": "J'ai détecté {n} moteurs. Décoche une ligne si ce n'est pas un moteur :",
        "en": "I detected {n} motors. Uncheck a row if it isn't a motor:",
        "es": "Detecté {n} motores. Desmarca una fila si no es un motor:",
        "it": "Ho rilevato {n} motori. Deseleziona una riga se non è un motore:",
    },
    "motor_row": {
        "fr": "Moteur {n} — broches {pwm}, {dirs}",
        "en": "Motor {n} — pins {pwm}, {dirs}",
        "es": "Motor {n} — pines {pwm}, {dirs}",
        "it": "Motore {n} — pin {pwm}, {dirs}",
    },
    "driver_question_shared": {
        "fr": "Quel module pilote ces moteurs ?",
        "en": "Which module drives these motors?",
        "es": "¿Qué módulo controla estos motores?",
        "it": "Quale modulo pilota questi motori?",
    },
    "regroup_banner": {
        "fr": "Ces broches formaient peut-être un moteur.",
        "en": "These pins might have formed a motor.",
        "es": "Estos pines podrían haber formado un motor.",
        "it": "Questi pin potrebbero aver formato un motore.",
    },
    "regroup_button": {
        "fr": "Re-grouper en moteur",
        "en": "Re-group as a motor",
        "es": "Reagrupar como motor",
        "it": "Raggruppa come motore",
    },
    "declare_tile": {
        "fr": "Créer un composant",
        "en": "Create a component",
        "es": "Crear un componente",
        "it": "Crea un componente",
    },
    "custom_badge": {
        # "it": "perso" read as the Italian for "lost" -- not a cognate of
        # French "perso" (informal for "personnel"). Fixed 2026-07-30.
        "fr": "perso", "en": "custom", "es": "propio", "it": "personale",
    },
    # ⚠️ `edit_declared_tip` SUPPRIMÉE le 2026-08-13. Elle légendait le crayon
    # unique de la liste déroulante du mode avancé, qui n'existe plus : chaque
    # card porte le sien, et sa légende vient de `Strings`
    # (`components_custom_badge_tip` / `components_adopt_tip`), c'est-à-dire de
    # la MÊME source que la fiche de l'onglet « Composants ». Ne pas la
    # réintroduire pour un futur crayon : deux tables pour la même phrase, dans
    # deux écrans qui promettent d'être équivalents, c'est la divergence que ce
    # dict existe pour empêcher.
    "custom_badge_tip": {
        "fr": "Composant que tu as décrit toi-même",
        "en": "A component you described yourself",
        "es": "Componente que describiste tú mismo",
        "it": "Componente che hai descritto tu",
    },
    # Advanced (text) ambiguity modal -- AmbiguityDialog in ambiguity_dialog.py.
    # Added 2026-08-11: these strings were hardcoded French, bypassing i18n
    # entirely. Kept in this SAME dict (not a separate one in
    # ambiguity_dialog.py) for the reason stated above: single source, so the
    # beginner tiles and the advanced text modal never drift apart again.
    "adv_window_title": {
        "fr": "Précise ce que tu utilises",
        "en": "Specify what you're using",
        "es": "Especifica qué estás usando",
        "it": "Specifica cosa stai usando",
    },
    "adv_intro": {
        "fr": "Pour générer le schéma de câblage, j'ai besoin de précisions "
              "sur certains composants que je n'ai pas pu identifier avec "
              "certitude. Choisis le composant qui correspond à ce que tu "
              "veux brancher :",
        "en": "To generate the wiring diagram, I need clarification on some "
              "components I couldn't identify with certainty. Choose the "
              "component that matches what you want to connect:",
        "es": "Para generar el esquema de cableado, necesito precisar "
              "algunos componentes que no pude identificar con certeza. "
              "Elige el componente que corresponde a lo que quieres "
              "conectar:",
        "it": "Per generare lo schema di cablaggio, ho bisogno di "
              "chiarimenti su alcuni componenti che non sono riuscito a "
              "identificare con certezza. Scegli il componente che "
              "corrisponde a ciò che vuoi collegare:",
    },
    "motors_limit_warning": {
        "fr": "⚠️ <b>{n} moteurs DC détectés.</b> Promptuino se limite à "
              "<b>{limit} moteurs DC</b> maximum (tous les drivers "
              "catalogués sont des dual H-bridges, 1 chip = 2 moteurs). Les "
              "{limit} premiers sont pré-cochés ; tu peux en décocher pour "
              "en choisir d'autres. Les broches non retenues deviendront "
              "des sorties à reclasser individuellement plus bas dans "
              "cette modale.",
        "en": "⚠️ <b>{n} DC motors detected.</b> Promptuino limits you to "
              "<b>{limit} DC motors</b> maximum (every cataloged driver is "
              "a dual H-bridge, 1 chip = 2 motors). The first {limit} are "
              "pre-checked; you can uncheck some to pick different ones. "
              "Pins that aren't kept become individual outputs to "
              "reclassify further down in this dialog.",
        "es": "⚠️ <b>Se detectaron {n} motores DC.</b> Promptuino limita "
              "a <b>{limit} motores DC</b> como máximo (todos los drivers "
              "del catálogo son puente H dual, 1 chip = 2 motores). Los "
              "primeros {limit} están premarcados; puedes desmarcarlos "
              "para elegir otros. Los pines no conservados pasarán a ser "
              "salidas individuales para reclasificar más abajo en esta "
              "ventana.",
        "it": "⚠️ <b>Rilevati {n} motori DC.</b> Promptuino limita a "
              "<b>{limit} motori DC</b> al massimo (tutti i driver a "
              "catalogo sono ponti H doppi, 1 chip = 2 motori). I primi "
              "{limit} sono preselezionati; puoi deselezionarne alcuni per "
              "sceglierne altri. I pin non mantenuti diventeranno uscite "
              "singole da riclassificare più in basso in questa finestra.",
    },
    "pin_digital": {
        "fr": "Broche numérique {n}", "en": "Digital pin {n}",
        "es": "Pin digital {n}", "it": "Pin digitale {n}",
    },
    "pin_analog": {
        "fr": "Broche analogique {net}", "en": "Analog pin {net}",
        "es": "Pin analógico {net}", "it": "Pin analogico {net}",
    },
    "pin_generic": {
        "fr": "Broche {net}", "en": "Pin {net}",
        "es": "Pin {net}", "it": "Pin {net}",
    },
    "prompt_excerpt": {
        "fr": "<i>Dans ton prompt :</i> « {excerpt} »",
        "en": "<i>In your prompt:</i> “{excerpt}”",
        "es": "<i>En tu prompt:</i> «{excerpt}»",
        "it": "<i>Nel tuo prompt:</i> «{excerpt}»",
    },
    "prompt_excerpt_missing": {
        "fr": "<i>Pas de mention explicite dans ton prompt — le composant "
              "a été détecté à partir du code.</i>",
        "en": "<i>No explicit mention in your prompt — the component was "
              "detected from the code.</i>",
        "es": "<i>Sin mención explícita en tu prompt — el componente se "
              "detectó a partir del código.</i>",
        "it": "<i>Nessuna menzione esplicita nel tuo prompt — il "
              "componente è stato rilevato dal codice.</i>",
    },
    "motor_yes_dc": {
        "fr": "Oui, c'est un moteur DC",
        "en": "Yes, it's a DC motor",
        "es": "Sí, es un motor DC",
        "it": "Sì, è un motore DC",
    },
    "components_separate": {
        "fr": "Non, ce sont des composants séparés",
        "en": "No, these are separate components",
        "es": "No, son componentes separados",
        "it": "No, sono componenti separati",
    },
    "motors_detected_title": {
        "fr": "{k} moteurs DC détectés", "en": "{k} DC motors detected",
        "es": "{k} motores DC detectados", "it": "{k} motori DC rilevati",
    },
    "motors_groups_desc": {
        "fr": "<i>J'ai détecté plusieurs groupes de broches OUTPUT qui "
              "forment des moteurs DC :</i>",
        "en": "<i>I detected several groups of OUTPUT pins that form DC "
              "motors:</i>",
        "es": "<i>Detecté varios grupos de pines OUTPUT que forman "
              "motores DC:</i>",
        "it": "<i>Ho rilevato diversi gruppi di pin OUTPUT che formano "
              "motori DC:</i>",
    },
    "assumed_motor_label": {
        "fr": "<b>Moteur supposé {i}</b> — broches {pwm} (PWM), {dirs}",
        "en": "<b>Assumed motor {i}</b> — pins {pwm} (PWM), {dirs}",
        "es": "<b>Motor supuesto {i}</b> — pines {pwm} (PWM), {dirs}",
        "it": "<b>Motore presunto {i}</b> — pin {pwm} (PWM), {dirs}",
    },
    "motor_confirm_checkbox": {
        "fr": "C'est bien un moteur",
        "en": "This is really a motor",
        "es": "Esto es realmente un motor",
        "it": "Questo è davvero un motore",
    },
    "motor_confirm_tooltip": {
        "fr": "Décoche si ces broches ne forment pas vraiment un moteur DC "
              "(faux positif du détecteur). Les pins seront alors "
              "ambiguës individuelles à reclasser dans la section "
              "classique plus bas.",
        "en": "Uncheck if these pins don't actually form a DC motor "
              "(detector false positive). The pins will then become "
              "individual ambiguous outputs to reclassify in the classic "
              "section below.",
        "es": "Desmarca si estos pines no forman realmente un motor DC "
              "(falso positivo del detector). Los pines pasarán a ser "
              "salidas ambiguas individuales para reclasificar en la "
              "sección clásica más abajo.",
        "it": "Deseleziona se questi pin non formano davvero un motore DC "
              "(falso positivo del rilevatore). I pin diventeranno uscite "
              "ambigue singole da riclassificare nella sezione classica "
              "più in basso.",
    },
    "wire_motor_checkbox": {
        "fr": "Câbler le moteur", "en": "Wire the motor",
        "es": "Cablear el motor", "it": "Cablare il motore",
    },
    "motors_limit_toast": {
        "fr": "Maximum {limit} moteurs DC. Décoche d'abord un moteur pour "
              "en choisir un autre.",
        "en": "Maximum {limit} DC motors. Uncheck a motor first to choose "
              "a different one.",
        "es": "Máximo {limit} motores DC. Primero desmarca un motor para "
              "elegir otro.",
        "it": "Massimo {limit} motori DC. Deseleziona prima un motore per "
              "sceglierne un altro.",
    },
    "driver_label_l293d_module": {
        "fr": "L293D (module breakout)", "en": "L293D (breakout module)",
        "es": "L293D (módulo breakout)", "it": "L293D (modulo breakout)",
    },
    "driver_label_l293d_dip": {
        "fr": "L293D (DIP nu)", "en": "L293D (bare DIP)",
        "es": "L293D (DIP sin montar)", "it": "L293D (DIP nudo)",
    },
    "grouped_outputs_title": {
        "fr": "Plusieurs sorties OUTPUT — broches {pwm} (PWM), {dirs}",
        "en": "Several OUTPUT pins — pins {pwm} (PWM), {dirs}",
        "es": "Varias salidas OUTPUT — pines {pwm} (PWM), {dirs}",
        "it": "Diverse uscite OUTPUT — pin {pwm} (PWM), {dirs}",
    },
    "grouped_excerpt_found": {
        "fr": "<i>Dans ton prompt :</i> « {excerpt} » — ces 3 sorties "
              "forment probablement un moteur DC.",
        "en": "<i>In your prompt:</i> “{excerpt}” — these 3 outputs "
              "probably form a DC motor.",
        "es": "<i>En tu prompt:</i> «{excerpt}» — estas 3 salidas "
              "probablemente forman un motor DC.",
        "it": "<i>Nel tuo prompt:</i> «{excerpt}» — queste 3 uscite "
              "formano probabilmente un motore DC.",
    },
    "grouped_excerpt_missing": {
        "fr": "<i>Ces broches semblent former un seul montage</i> : la "
              "broche {pwm} en PWM (vitesse) et les autres en sens. C'est "
              "typiquement un moteur DC avec driver H-bridge.",
        "en": "<i>These pins seem to form a single assembly</i>: pin "
              "{pwm} as PWM (speed), the others for direction. This is "
              "typically a DC motor with an H-bridge driver.",
        "es": "<i>Estos pines parecen formar un solo montaje</i>: el pin "
              "{pwm} en PWM (velocidad) y los demás en dirección. Esto es "
              "típicamente un motor DC con driver puente H.",
        "it": "<i>Questi pin sembrano formare un unico montaggio</i>: il "
              "pin {pwm} come PWM (velocità), gli altri per il senso. Si "
              "tratta tipicamente di un motore DC con driver a ponte H.",
    },
}


def build_options_for_type(type_id: str, lang: str = "fr",
                           component=None) -> list["VisualOption"]:
    """Visual options for the manual editing of a component. SINGLE SOURCE:
    derives from full_candidate_choices (functional family / electrical
    category + the cross-category promotions), so the beginner tiles match the
    advanced modal EXACTLY (same candidate set, only the rendering differs).
    Rich VisualOption reused when available, placeholder otherwise. [] if not
    replaceable (unknown type, NON_REPLACEABLE infrastructure).

    `component`: the real netlist component when the caller has it. Without it
    we rebuild a bare one from the type alone, which loses the attributes — and
    an unrecognised component would then look non-replaceable and offer nothing.
    """
    from .replacement_ui import full_candidate_choices
    from .netlist import Component
    from .declare_component_dialog import DECLARE_OPTION_ID

    target = component if component is not None else Component(
        ref="_", type=type_id, fn_id="", pins=[])
    choices = full_candidate_choices(target, lang)
    rich = {o.option_id: o for o in GENERIC_OUTPUT_OPTIONS}
    out: list[VisualOption] = []
    for t, label in choices:
        if t in rich:
            out.append(rich[t])
        else:
            out.append(VisualOption(
                option_id=t, svg_path=None, svg_inline=None,
                labels={lang: label}, examples={}, placeholder=True))
    if out:
        out.append(VisualOption(
            option_id=DECLARE_OPTION_ID, svg_path=None, svg_inline=None,
            labels={lang: dialog_label("declare_tile", lang)},
            examples={}, placeholder=True))
    return out


def label_for(option: VisualOption, lang: str) -> str:
    """Return the option's label in the desired language (FR fallback)."""
    return option.labels.get(lang) or option.labels["fr"]


def examples_for(option: VisualOption, lang: str) -> str:
    """Return the option's examples in the desired language (FR fallback)."""
    return option.examples.get(lang) or option.examples["fr"]


def dialog_label(key: str, lang: str) -> str:
    """Return a modal label (title/subtitle/button) in the
    desired language (FR fallback if the language is missing)."""
    entry = DIALOG_LABELS.get(key, {})
    return entry.get(lang) or entry.get("fr") or key

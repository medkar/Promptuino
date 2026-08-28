"""
Internationalization system.
To add a language: add an entry in TRANSLATIONS and LANGUAGE_NAMES.
"""
from dataclasses import dataclass
from PyQt6.QtCore import QObject, pyqtSignal


@dataclass
class Strings:
    # ── Navigation ────────────────────────────────────────────
    nav_carte:        str
    nav_ia:           str
    nav_studio:       str
    chat_title:               str
    chat_placeholder:         str
    chat_send_button:         str
    chat_stop_button:         str
    chat_new_conversation:    str
    chat_thinking:            str
    chat_no_backend:          str
    chat_attach_tooltip:      str
    chat_attachment_too_large: str
    chat_model_label_tooltip: str
    chat_no_model_label:      str
    chat_open_in_studio:      str
    chat_answer_anyway:       str
    chat_backend_timeout:     str
    chat_stream_soft_warn:    str
    chat_stream_hard_warn:    str
    chat_help_tooltip:        str
    chat_help_menu_code:      str
    # Code editor context menu (right-click) — Qt does not translate these
    # standard labels without a translator loaded: we provide them via i18n.
    ctx_menu_undo:            str
    ctx_menu_redo:            str
    ctx_menu_cut:             str
    ctx_menu_copy:            str
    ctx_menu_paste:           str
    ctx_menu_delete:          str
    ctx_menu_select_all:      str
    chat_help_error_button:   str
    registry_ask_chat:        str
    chat_help_prefix_unknown: str
    chat_help_prefix_motor:   str
    chat_help_prefix_technique: str
    chat_help_prefix_code:    str
    chat_help_prefix_selection: str
    chat_help_prefix_wrong_component: str
    chat_correction_to_studio: str
    chat_correction_redirect: str
    chat_correction_studio_offer: str
    chat_help_prefix_error:   str
    nudge_beginner_to_intermediate:  str
    nudge_intermediate_to_advanced:  str
    nav_tableau:      str

    # ── Mode selector ─────────────────────────────────────────
    mode_beginner:     str
    mode_intermediate: str
    mode_advanced:     str

    # ── Studio view ───────────────────────────────────────────
    studio_prompt_label:       str
    studio_prompt_placeholder: str
    prompt_tips:               tuple  # rotating tips (prompt placeholder + chat)
    studio_code_label:         str
    studio_generate:           str
    studio_generating:         str
    studio_gen_slow_soft:      str
    studio_gen_slow_hard:      str
    studio_generate_send:      str
    studio_upload_only:        str
    studio_err_no_prompt:      str
    clarify_title:             str
    clarify_intro:             str
    clarify_step:              str   # multi-family indicator « {n}/{total} »
    clarify_dont_care:         str
    clarify_other_label:       str
    clarify_other_apply:       str
    studio_err_no_backend:     str
    studio_compile_upload:     str
    studio_window_ai:          str
    studio_window_stable:      str
    studio_transfer_to_stable: str
    studio_transfer_overwrite_msg: str
    studio_console_src_ai:     str
    studio_console_src_stable: str
    studio_compile_upload_stable: str
    studio_mode_locked_busy:   str
    studio_compiling:          str
    studio_uploading:          str
    studio_upload_success:     str
    studio_upload_failed:      str
    studio_verifying:          str
    studio_recombine:          str
    studio_recombine_failed:   str
    studio_verify_ok:          str
    studio_verify_repaired_ok: str
    studio_repair_insufficient: str
    studio_verify_failed:      str
    feature_tools_delete_tip:   str
    feature_tools_regen_tip:    str
    feature_select_delete_title: str
    feature_select_regen_title: str
    feature_select_delete_confirm: str
    feature_select_regen_confirm: str
    feature_delete_dirty_warn:  str
    feature_deleted_msg:        str
    studio_program_ready:      str   # with description: « Code ready: {} »
    studio_program_ready_plain: str  # without description (fallback): « Code ready »
    studio_no_code_generated:  str
    studio_output_label:       str
    studio_err_no_code:        str
    studio_err_no_board:       str
    studio_err_no_fqbn:        str
    studio_err_no_port:        str
    studio_err_no_cli:         str
    studio_unverified_no_cli:  str
    studio_unverified_no_board: str
    studio_fixing:             str
    studio_lib_installing:         str
    studio_core_installing:        str
    studio_err_missing_lib:        str
    studio_err_core_install:       str
    studio_err_upload_port_busy:   str
    studio_err_upload_port:        str
    studio_err_upload_no_response: str
    studio_err_upload_timeout:     str
    studio_explaining:             str
    studio_fix_attempt:            str
    studio_repairing:              str
    studio_repair_summary:         str
    studio_cancel:                 str
    studio_instructions_title:     str

    # ── AI context file ───────────────────────────────────────
    studio_context_badge:          str  # "Contexte : {name} ({chars} car.)"
    studio_context_remove:         str  # tooltip of the × button
    studio_context_add_hint:       str  # badge label when empty
    studio_context_add_tooltip:    str  # tooltip of the + button
    studio_attach:                 str  # + Attach button (prompt field overlay)
    studio_context_picker_title:   str  # QFileDialog title
    studio_context_picker_filter:  str  # QFileDialog filter
    studio_context_invalid_ext:    str  # "Unsupported format (.md/.txt only)"
    studio_context_read_error:     str  # "Cannot read this file"
    studio_context_need_project:   str  # "Create or open a project first"

    # ── Onboarding tutorial (coachmark) ───────────────────────
    tutorial_next:                 str  # « Next » button
    tutorial_back:                 str  # « Back » button
    tutorial_skip:                 str  # « Skip » button
    tutorial_finish:               str  # « Done » button (last step)
    mn_review_tutorial:            str  # Help » Replay tutorial menu action
    tuto_beg_studio:               str
    tuto_beg_projets:              str
    tuto_beg_carte:                str
    tuto_beg_ia:                   str
    tuto_beg_mode:                 str
    tuto_beg_theme:                str
    tuto_beg_prompt:               str
    tuto_beg_actions:              str
    tuto_beg_journal:              str
    tuto_beg_chat:                 str
    tuto_int_generate:             str
    tuto_int_editor:               str
    tuto_int_compile:              str
    tuto_int_tools:                str
    tuto_int_features:             str
    tuto_adv_editor:               str
    tuto_adv_stable:               str
    tuto_adv_transfer:             str
    tuto_adv_comments:             str
    tuto_adv_serial:               str

    # ── Topbar ────────────────────────────────────────────────
    topbar_collapse:  str
    topbar_expand:    str
    topbar_settings:  str

    # ── Theme toggle ──────────────────────────────────────────
    theme_light:      str
    theme_dark:       str

    # ── Board view — auto section ──────────────────────────────
    board_auto_title:    str
    board_auto_subtitle: str
    board_connected:     str
    board_disconnected:  str

    # ── Board view — manual section ───────────────────────────
    board_manual_title:      str
    board_manual_subtitle:   str
    board_env:               str
    board_model:             str
    board_model_placeholder: str
    board_port:              str
    board_port_placeholder:  str
    board_validate:          str
    board_manual_confirmed:  str

    # ── Status bar ────────────────────────────────────────────
    status_ia:        str
    status_board:     str
    status_no_board:  str

    # ── AI Model view ─────────────────────────────────────────
    ia_claude_subtitle:      str
    ia_claude_available:     str
    ia_claude_unavailable:   str
    ia_gemini_subtitle:      str
    ia_anthropic_subtitle:   str
    ia_api_key_label:        str
    ia_api_key_placeholder:  str
    ia_save_key:             str
    ia_activate:             str
    ia_active:               str
    ia_key_saved:            str
    ia_ollama_subtitle:         str
    ia_ollama_running:          str
    ia_ollama_not_running:      str
    ia_ollama_model_missing:    str
    ia_ollama_model_label:      str
    ia_ollama_model_placeholder: str
    ia_ollama_ctx_label:        str
    ia_ollama_ctx_help:         str

    # ── Serial Monitor ────────────────────────────────────────
    serial_title:            str
    serial_baud:             str
    serial_autoscroll:       str
    serial_send:             str
    serial_send_placeholder: str
    serial_connect:          str
    serial_disconnect:       str
    serial_console_header:   str

    # ── Read-only popup (intermediate mode) ───────────────────
    readonly_popup_ok:  str
    readonly_popup_switch: str

    # ── Overwrite popup + Iterate button ──────────────────────
    studio_overwrite_msg:    str
    studio_beginner_overwrite_msg: str
    studio_overwrite_accept: str
    studio_overwrite_cancel: str
    studio_overwrite_switch: str
    studio_iterate:          str
    studio_iterating:        str

    # ── Settings window ───────────────────────────────────────
    settings_title:   str
    settings_language: str
    settings_theme:   str
    settings_storage:              str
    settings_storage_title:        str
    settings_storage_description:  str
    settings_storage_current:      str
    settings_storage_default_suffix: str
    settings_storage_change:       str
    settings_storage_reset:        str
    settings_storage_picker_title: str
    settings_storage_warning:      str

    # ── First-launch wizard ───────────────────────────────────
    welcome_title:       str
    welcome_heading:     str
    welcome_description: str
    welcome_folder_label: str
    welcome_browse:      str
    welcome_confirm:     str
    welcome_hint:        str

    # ── Menu bar ──────────────────────────────────────────────
    menu_file:        str

    # ── Generation modal ──────────────────────────────────────
    gen_modal_title:           str
    gen_modal_regenerate:      str
    gen_modal_regenerate_desc: str
    gen_modal_add:             str
    gen_modal_add_desc:        str
    gen_modal_correct:         str
    gen_modal_correct_desc:    str
    gen_modal_target:          str
    gen_modal_target_all:      str
    gen_modal_validate:        str
    gen_modal_cancel:          str
    modify_guidance_title:     str
    modify_guidance_body:      str
    modify_guidance_ok:        str

    # ── Generation orchestrator (Task 11) ─────────────────────
    studio_err_parse_failed:        str
    studio_inline_overwrite_title:  str
    studio_inline_overwrite_body:   str
    studio_merge_features_title:    str
    studio_merge_features_body:     str

    # ── Component replacement (SP2 Task 11) ───────────────────
    component_replace_dropdown:          str
    component_replace_divergence_title:  str
    component_replace_divergence_message: str
    component_replace_continue:          str


TRANSLATIONS: dict[str, Strings] = {
    "fr": Strings(
        nav_carte        = "Carte",
        nav_ia           = "Modèle IA",
        nav_studio       = "Studio",
        nav_tableau      = "Tableau de bord",
        topbar_collapse  = "Réduire la navigation",
        topbar_expand    = "Afficher la navigation",
        topbar_settings  = "Paramètres",
        theme_light      = "Mode clair",
        theme_dark       = "Mode sombre",
        status_ia        = "Modèle IA :",
        status_board     = "Carte :",
        status_no_board  = "Aucune carte",
        board_auto_title    = "Détection automatique",
        board_auto_subtitle = "Branchez votre carte USB, elle sera reconnue automatiquement.",
        board_connected     = "Connectée",
        board_disconnected  = "Carte déconnectée",
        board_manual_title      = "Sélection manuelle",
        board_manual_subtitle   = "Votre carte n'a pas été reconnue ? Sélectionnez-la ci-dessous.",
        board_env               = "Environnement",
        board_model             = "Modèle",
        board_model_placeholder = "Sélectionner un modèle",
        board_port              = "Port série",
        board_port_placeholder  = "Sélectionner un port",
        board_validate          = "Valider",
        board_manual_confirmed  = "Configurée manuellement",
        ia_claude_subtitle     = "Utilise le CLI claude installé sur votre machine. Aucune clé API requise.",
        ia_claude_available    = "Disponible",
        ia_claude_unavailable  = "Non disponible — installez Claude Code",
        ia_gemini_subtitle     = "Utilise l'API Google Generative AI — modèle gemini-1.5-flash.",
        ia_anthropic_subtitle  = "Utilise l'API Anthropic (pay-per-use) — modèle claude-sonnet-4-6.",
        ia_api_key_label       = "Clé API",
        ia_api_key_placeholder = "Entrez votre clé API...",
        ia_save_key            = "Enregistrer",
        ia_activate            = "Activer ce modèle",
        ia_active              = "Actif",
        ia_key_saved           = "Clé enregistrée",
        ia_ollama_subtitle          = "Utilise le serveur Ollama local. Aucune clé API requise.",
        ia_ollama_running           = "Serveur actif — modèle disponible",
        ia_ollama_not_running       = "Ollama non lancé — exécutez : ollama serve",
        ia_ollama_model_missing     = "Modèle non téléchargé — exécutez : ollama pull",
        ia_ollama_model_label       = "Modèle",
        ia_ollama_model_placeholder = "ex. gemma4:e2b",
        ia_ollama_ctx_label         = "Taille de contexte",
        ia_ollama_ctx_help          = "Contexte utilisé pour le chat avec un modèle local. Si le modèle est très lent, réduisez cette valeur.",
        settings_title   = "Paramètres",
        settings_language = "Langue",
        settings_theme    = "Thème",
        settings_storage              = "Stockage",
        settings_storage_title        = "Dossier des projets et librairies",
        settings_storage_description  = "Choisissez où seront enregistrés vos projets ainsi que les librairies téléchargées par l'outil.",
        settings_storage_current      = "Dossier actuel",
        settings_storage_default_suffix = " (par défaut)",
        settings_storage_change       = "Modifier…",
        settings_storage_reset        = "Réinitialiser",
        settings_storage_picker_title = "Choisir le dossier de stockage",
        settings_storage_warning      = "Les projets et librairies déjà présents dans l'ancien dossier ne sont pas déplacés automatiquement — vous pouvez les copier manuellement si besoin.",
        welcome_title        = "Bienvenue dans Promptuino",
        welcome_heading      = "Où souhaitez-vous enregistrer vos projets ?",
        welcome_description  = "Promptuino va créer un dossier pour stocker vos projets ainsi que les librairies téléchargées par l'outil. Vous pourrez modifier cet emplacement plus tard dans les Paramètres.",
        welcome_folder_label = "Dossier choisi",
        welcome_browse       = "Parcourir…",
        welcome_confirm      = "Continuer",
        welcome_hint         = "Astuce : conservez le dossier par défaut si vous n'avez pas de préférence.",
        mode_beginner     = "Débutant",
        mode_intermediate = "Intermédiaire",
        mode_advanced     = "Avancé",
        studio_prompt_label       = "Générer une fonctionnalité",
        studio_prompt_placeholder = "Décrivez ce que vous souhaitez programmer… Ex : allumer une LED rouge quand la température dépasse 30°C",
        prompt_tips = (
            "Ex. : fais clignoter une LED sur D13",
            "Astuce : décris une seule fonctionnalité à la fois",
            "Ex. : mesure la température avec un DHT22",
            "Astuce : nomme ton composant — « DHT22 » plutôt que « capteur »",
            "Ex. : allume une LED quand on appuie sur le bouton D2",
            "Astuce : précise la broche et la carte si besoin",
            "Astuce : insère un fichier texte avec les branchements de ton montage pour ne pas les retaper",
            "Astuce : chaque génération crée un code différent — plutôt que tout corriger pour le faire marcher, essaie de régénérer",
            "Info : la qualité du code dépend du modèle d'IA utilisé",
            "Ex. : fais tourner un servomoteur de 0 à 180°",
            "Ex. : mesure une distance avec un capteur HC-SR04",
            "Ex. : affiche un message sur un écran OLED SSD1306",
            "Ex. : joue une mélodie sur un buzzer",
            "Ex. : contrôle un moteur avec un driver L298N",
            "Astuce : utilise « Voir le schéma » pour vérifier ton câblage avant d'uploader",
            "Astuce : si le code ne compile pas, l'outil Réparer peut corriger les erreurs",
            "Astuce : passe en mode Avancé pour voir et éditer le code à la main",
            "Astuce : en mode Avancé, le code s'ouvre en 2 fenêtres — celui généré par l'IA et ton code stable, que l'IA ne modifie jamais. Pratique pour tester des choses sans casser du code fonctionnel",
            "Astuce : précise une valeur si besoin — « clignote toutes les 200 ms »",
        ),
        studio_code_label         = "Code généré",
        studio_generate           = "Générer",
        studio_generating         = "Génération en cours…",
        studio_gen_slow_soft      = "C'est plus long que d'habitude. La génération continue — tu peux attendre, ou cliquer sur « Annuler ».",
        studio_gen_slow_hard      = "Toujours en cours. Une demande complexe peut prendre plusieurs minutes sur un modèle local. Rien n'est perdu : elle ira jusqu'au bout si tu la laisses faire.",
        studio_generate_send      = "Générer et uploader",
        studio_upload_only        = "Uploader",
        studio_err_no_prompt      = "Veuillez entrer un prompt.",
        clarify_title             = "Préciser le composant",
        clarify_intro             = "Plusieurs composants correspondent. Lequel utilises-tu ?",
        clarify_step              = "Précision {n}/{total}",
        clarify_dont_care         = "Choisis pour moi (au plus probable)",
        clarify_other_label       = "Autre / je précise…",
        clarify_other_apply       = "Appliquer",
        studio_err_no_backend     = "Aucun modèle IA disponible. Configurez-en un dans l'onglet Modèle IA.",
        studio_compile_upload     = "Uploader",
        studio_window_ai          = "Code généré (IA)",
        studio_window_stable      = "Code stable",
        studio_transfer_to_stable = "Transférer vers stable ▶",
        studio_transfer_overwrite_msg = "Écraser le code stable actuel par le code IA ?",
        studio_console_src_ai     = "Fenêtre IA",
        studio_console_src_stable = "Fenêtre stable",
        studio_compile_upload_stable = "Uploader",
        studio_mode_locked_busy   = "Termine l'opération en cours avant de changer de mode.",
        studio_compiling          = "Compilation…",
        studio_uploading          = "Upload…",
        studio_upload_success     = "Uploadé avec succès",
        studio_upload_failed      = "Upload échoué — la carte n'a PAS été reprogrammée",
        studio_verifying          = "Vérification de la compilation…",
        studio_recombine          = "Fonctionnalités liées détectées — régénération de l'ensemble…",
        studio_recombine_failed   = "Le code ne compile pas (fonctionnalités liées) — simplifie ton prompt ou réessaie",
        studio_verify_ok          = "Le code compile ✓",
        studio_verify_repaired_ok = "Réparé ✓ — le code compile maintenant",
        studio_repair_insufficient = "La réparation n'a pas suffi : les fonctionnalités semblent liées.",
        studio_verify_failed      = "Le code ne compile pas après réparation — code restauré ; demande de l'aide au chat ci-dessous",
        feature_tools_delete_tip   = "Supprimer une fonctionnalité",
        feature_tools_regen_tip    = "Régénérer une fonctionnalité",
        feature_select_delete_title = "Supprimer une ou plusieurs fonctionnalités",
        feature_select_regen_title = "Régénérer une ou plusieurs fonctionnalités",
        feature_select_delete_confirm = "Supprimer",
        feature_select_regen_confirm = "Régénérer",
        feature_delete_dirty_warn  = "Le code a été modifié à la main : ces retouches seront perdues. Continuer ?",
        feature_deleted_msg        = "Fonctionnalité(s) supprimée(s).",
        studio_program_ready      = "Code prêt : {}",
        studio_program_ready_plain = "Code prêt",
        studio_no_code_generated  = "Aucun code généré",
        studio_output_label       = "Journal",
        studio_err_no_code        = "Aucun code à compiler.",
        studio_err_no_board       = "Aucune carte sélectionnée. Vérifiez que votre carte est bien connectée.",
        studio_err_no_fqbn        = "Carte non supportée par arduino-cli.",
        studio_err_no_port        = "Aucun port série détecté. Vérifiez que votre carte est bien connectée.",
        studio_err_no_cli         = "arduino-cli est introuvable. Il est normalement installé avec Promptuino : réinstalle l'application.",
        studio_unverified_no_cli  = "non vérifié : arduino-cli introuvable, réinstalle Promptuino",
        studio_unverified_no_board = "non vérifié : aucune carte sélectionnée",
        studio_fixing             = "Correction IA en cours…",
        studio_lib_installing         = "Installation des librairies…",
        studio_core_installing        = "Installation du composant carte…",
        studio_err_missing_lib        = "Librairie introuvable :",
        studio_err_core_install       = "Impossible d'installer le composant pour cette carte :",
        studio_err_upload_port_busy   = "Le port série est occupé par une autre application. Fermez le Moniteur Série avant d'uploader.",
        studio_err_upload_port        = "Port série introuvable. Vérifiez le branchement USB.",
        studio_err_upload_no_response = "La carte ne répond pas. Rebranchez-la ou appuyez sur Reset.",
        studio_err_upload_timeout     = "Délai dépassé lors de l'upload. Vérifiez la connexion.",
        studio_explaining             = "Analyse de l'erreur par l'IA…",
        studio_fix_attempt            = "Erreur compilation — Réparation IA",
        studio_repairing              = "Réparation approfondie par l'IA…",
        studio_repair_summary         = "Réparations appliquées :",
        studio_cancel                 = "Annuler",
        studio_instructions_title     = "Instructions de branchement",
        studio_context_badge          = "Contexte : {name} ({chars} car.)",
        studio_context_remove         = "Retirer le contexte",
        studio_context_add_hint       = "Ajouter un fichier de contexte (.md ou .txt)",
        studio_context_add_tooltip    = "Ajouter un contexte",
        studio_attach                 = "+ Joindre",
        studio_context_picker_title   = "Choisir un fichier de contexte",
        studio_context_picker_filter  = "Fichiers texte (*.md *.txt *.ino *.cpp *.c *.h *.csv *.log)",
        studio_context_invalid_ext    = "Format non supporté — fichier texte attendu (.md, .txt, .ino, .cpp, .c, .h, .csv, .log).",
        studio_context_read_error     = "Impossible de lire ce fichier.",
        studio_context_need_project   = "Créez ou ouvrez un projet avant d'ajouter un contexte.",
        tutorial_next                 = "Suivant",
        tutorial_back                 = "Précédent",
        tutorial_skip                 = "Passer",
        tutorial_finish               = "Terminer",
        mn_review_tutorial            = "Revoir le tutoriel",
        tuto_beg_studio               = "Studio : c'est ici que tu décris et génères ton programme, puis l'envoies à la carte.",
        tuto_beg_projets              = "Projets : retrouve, ouvre et organise tes programmes sauvegardés.",
        tuto_beg_carte                = "Carte : ta carte est reconnue automatiquement ; sinon, tu peux choisir manuellement le modèle de ta carte.",
        tuto_beg_ia                   = "Modèle IA : choisis ici quelle IA fait tourner le logiciel — en local via Ollama, ou dans le cloud via l'API de ton choix.",
        tuto_beg_mode                 = "Choisis ton niveau : Débutant, Intermédiaire ou Avancé. Plus de contrôles apparaissent à mesure.",
        tuto_beg_theme                = "Bascule entre le thème clair et le thème sombre.",
        tuto_beg_prompt               = "Décris ici, en français, ce que tu veux faire (ex. « fais clignoter une LED »).",
        tuto_beg_actions              = "Génère le code et envoie-le à ta carte, ou ouvre le schéma de câblage.",
        tuto_beg_journal              = "Suis ici ce qui se passe : génération, compilation, envoi à la carte, et les erreurs éventuelles.",
        tuto_beg_chat                 = "Pose tes questions à l'assistant : il connaît ton projet.",
        tuto_int_generate             = "Ce bouton génère du code : créer une nouvelle fonctionnalité, en ajouter une, ou modifier une fonctionnalité existante.",
        tuto_int_editor               = "Le code généré s'affiche ici — et tu peux l'éditer directement à la main.",
        tuto_int_compile              = "Compile, envoie à la carte et ouvre le schéma de câblage.",
        tuto_int_tools                = "Les outils IA : explique, commente ou répare le code généré.",
        tuto_int_features             = "Chaque fonctionnalité générée est listée ici : coche-la pour surligner ses lignes, ou régénère / supprime-la.",
        tuto_adv_editor               = "En mode Avancé, ton code s'ouvre en 2 fenêtres. Ici, le code généré par l'IA.",
        tuto_adv_stable               = "Ta fenêtre de code stable : tu l'édites à la main, l'IA n'y touche jamais. Parfait pour garder du code qui marche.",
        tuto_adv_transfer             = "Transfère les fonctionnalités entre les deux fenêtres (glisser-déposer), pour mettre ton code au propre à l'abri de l'IA.",
        tuto_adv_comments             = "Règle le niveau de commentaires ajoutés au code généré.",
        tuto_adv_serial               = "Active l'inclusion du moniteur série (Serial) dans le code.",
        serial_title            = "Moniteur Série",
        serial_baud             = "Baud",
        serial_autoscroll       = "Défilement auto",
        serial_send             = "Envoyer",
        serial_send_placeholder = "Envoyer un message…",
        serial_connect          = "Connecter",
        serial_disconnect       = "Déconnecter",
        serial_console_header   = "Sortie console :",
        readonly_popup_ok  = "OK",
        readonly_popup_switch = "Passer en Avancé",
        studio_overwrite_msg    = "Cette action va remplacer le code existant.\nÊtes-vous sûr ?",
        studio_beginner_overwrite_msg = "Cette action va remplacer le code existant.<br><br><b>Pour ajouter une fonctionnalité sans écraser, passez en mode intermédiaire</b>",
        studio_overwrite_accept = "Remplacer",
        studio_overwrite_cancel = "Annuler",
        studio_overwrite_switch = "Passer en Intermédiaire",
        studio_iterate          = "Ajout fonctionnalité",
        studio_iterating        = "Ajout d'une fonctionnalité en cours…",
        menu_file        = "Fichier",
        chat_title              = "Assistant IA",
        chat_placeholder        = "Pose ta question...",
        chat_send_button        = "Envoyer",
        chat_stop_button        = "Arrêter",
        chat_new_conversation   = "Nouvelle conversation",
        chat_thinking           = "Réflexion en cours…",
        chat_no_backend         = "Active un modèle dans l'onglet Modèle IA.",
        chat_attach_tooltip       = "Joindre un document",
        chat_attachment_too_large = "Document tronqué à 100 Ko pour le contexte.",
        chat_model_label_tooltip  = "Modèle actif — cliquer pour changer",
        chat_no_model_label       = "Aucun modèle",
        chat_open_in_studio     = "Ouvrir dans Studio",
        chat_answer_anyway      = "Répondre quand même",
        chat_backend_timeout    = (
            "Le modèle ne répond pas — vérifie ta connexion ou la clé "
            "API."
        ),
        chat_stream_soft_warn   = (
            "*⏳ Le modèle prend plus de temps que d'habitude. "
            "Tu peux attendre ou cliquer Stop.*"
        ),
        chat_stream_hard_warn   = (
            "*⏳ Ça fait 3 minutes sans réponse, le modèle est "
            "probablement bloqué. Tu devrais cliquer Stop.*"
        ),
        chat_help_tooltip       = "Demander à l'assistant",
        chat_help_menu_code     = "Demander à l'assistant",
        ctx_menu_undo           = "Annuler",
        ctx_menu_redo           = "Rétablir",
        ctx_menu_cut            = "Couper",
        ctx_menu_copy           = "Copier",
        ctx_menu_paste          = "Coller",
        ctx_menu_delete         = "Supprimer",
        ctx_menu_select_all     = "Tout sélectionner",
        chat_help_error_button  = "Demander de l'aide sur cette erreur",
        registry_ask_chat      = "Demander de l'aide dans le chat",
        chat_help_prefix_unknown = (
            "Mon programme utilise des composants que l'application ne "
            "connaît pas : {parts}. Comment m'y prendre ?"),
        chat_help_prefix_motor = (
            "Mes broches {pins} forment peut-être un seul moteur, ou bien "
            "ce sont des sorties séparées (LED, buzzer, servo…). Aide-moi "
            "à comprendre la différence et à choisir."
        ),
        chat_help_prefix_technique = (
            "Sur la broche {pin}, le détecteur hésite entre {candidates}. "
            "Peux-tu m'expliquer la différence dans ce contexte ?"
        ),
        chat_help_prefix_code   = (
            "Explique-moi ce que fait la fonction `{function}`."
        ),
        chat_help_prefix_selection = (
            "Explique-moi ce que font ces lignes."
        ),
        chat_help_prefix_wrong_component = "Composant {ref} ({type}) : ",
        chat_correction_to_studio  = "Corriger dans Studio",
        chat_correction_redirect   = (
            "On dirait que c'est plutôt un {name}. Tu peux corriger ça dans "
            "le Studio — ton prompt sera pré-rempli."
        ),
        chat_correction_studio_offer = (
            "Tu veux appliquer un changement à ton code ? Tu peux le faire "
            "dans le Studio."
        ),
        chat_help_prefix_error  = (
            "J'ai cette erreur de compilation, peux-tu m'aider à la "
            "comprendre ?"
        ),
        nudge_beginner_to_intermediate = "<b>Astuce</b> : En mode <b>intermédiaire</b>, tu vois le code, tu peux ajouter ou modifier une fonctionnalité — et même l'éditer toi-même.",
        nudge_intermediate_to_advanced = "<b>Astuce</b> : En mode <b>avancé</b>, ton code s'ouvre en 2 fenêtres — celui généré par l'IA et ton code stable, que l'IA ne modifie jamais. Idéal pour tester des idées sans casser ce qui marche déjà.",
        gen_modal_title           = "Que veux-tu faire ?",
        gen_modal_regenerate      = "Régénérer",
        gen_modal_regenerate_desc = "Repartir de zéro avec cette description",
        gen_modal_add             = "Ajouter une fonctionnalité",
        gen_modal_add_desc        = "Garder l'existant, ajouter ce comportement",
        gen_modal_correct         = "Modifier",
        gen_modal_correct_desc    = "Modifier une fonctionnalité existante",
        gen_modal_target          = "Fonctionnalité(s) à modifier :",
        gen_modal_target_all      = "Tout sélectionner",
        gen_modal_validate        = "Valider",
        gen_modal_cancel          = "Annuler",
        modify_guidance_title     = "Modifier dans le Studio",
        modify_guidance_body      = "Les fonctionnalités ne sont pas modifiables en mode débutant, tu vas passer en mode intermédiaire.\n\nPour appliquer la modification, clique sur « Générer » puis « Modifier ».",
        modify_guidance_ok        = "Compris",
        studio_err_parse_failed        = "La génération n'a pas pu être interprétée. Réessaie.",
        studio_inline_overwrite_title  = "Modifications manuelles",
        studio_inline_overwrite_body   = "Tu as modifié le code à la main. Cette action va régénérer et écraser ces modifications. Continuer ?",
        studio_merge_features_title    = "Fusion des fonctionnalités",
        studio_merge_features_body     = "Les {n} fonctionnalités sélectionnées vont être fusionnées en une seule. Continuer ?",
        component_replace_dropdown          = "Remplacer par :",
        component_replace_divergence_title  = "Code ≠ schéma",
        component_replace_divergence_message = "Le code dit « {old} », le schéma affichera « {new} ». Continuer ?",
        component_replace_continue          = "Continuer",
    ),
    "en": Strings(
        nav_carte        = "Board",
        nav_ia           = "AI Model",
        nav_studio       = "Studio",
        nav_tableau      = "Dashboard",
        topbar_collapse  = "Collapse navigation",
        topbar_expand    = "Show navigation",
        topbar_settings  = "Settings",
        theme_light      = "Light mode",
        theme_dark       = "Dark mode",
        status_ia        = "AI Model:",
        status_board     = "Board:",
        status_no_board  = "No board",
        board_auto_title    = "Auto-detection",
        board_auto_subtitle = "Plug in your USB board, it will be detected automatically.",
        board_connected     = "Connected",
        board_disconnected  = "Board disconnected",
        board_manual_title      = "Manual selection",
        board_manual_subtitle   = "Board not detected? Select it manually below.",
        board_env               = "Environment",
        board_model             = "Model",
        board_model_placeholder = "Select a model",
        board_port              = "Serial port",
        board_port_placeholder  = "Select a port",
        board_validate          = "Validate",
        board_manual_confirmed  = "Configured manually",
        ia_claude_subtitle     = "Uses the claude CLI installed on your machine. No API key required.",
        ia_claude_available    = "Available",
        ia_claude_unavailable  = "Not available — install Claude Code",
        ia_gemini_subtitle     = "Uses the Google Generative AI API — model gemini-1.5-flash.",
        ia_anthropic_subtitle  = "Uses the Anthropic API (pay-per-use) — model claude-sonnet-4-6.",
        ia_api_key_label       = "API Key",
        ia_api_key_placeholder = "Enter your API key...",
        ia_save_key            = "Save",
        ia_activate            = "Activate this model",
        ia_active              = "Active",
        ia_key_saved           = "Key saved",
        ia_ollama_subtitle          = "Uses the local Ollama server. No API key required.",
        ia_ollama_running           = "Server active — model available",
        ia_ollama_not_running       = "Ollama not running — run: ollama serve",
        ia_ollama_model_missing     = "Model not downloaded — run: ollama pull",
        ia_ollama_model_label       = "Model",
        ia_ollama_model_placeholder = "e.g. gemma4:e2b",
        ia_ollama_ctx_label         = "Context size",
        ia_ollama_ctx_help          = "Context used when chatting with a local model. If the model is very slow, reduce this value.",
        settings_title   = "Settings",
        settings_language = "Language",
        settings_theme    = "Theme",
        settings_storage              = "Storage",
        settings_storage_title        = "Projects and libraries folder",
        settings_storage_description  = "Choose where your projects and the libraries downloaded by the tool will be saved.",
        settings_storage_current      = "Current folder",
        settings_storage_default_suffix = " (default)",
        settings_storage_change       = "Change…",
        settings_storage_reset        = "Reset",
        settings_storage_picker_title = "Choose the storage folder",
        settings_storage_warning      = "Projects and libraries already present in the previous folder are not moved automatically — you can copy them manually if needed.",
        welcome_title        = "Welcome to Promptuino",
        welcome_heading      = "Where would you like to save your projects?",
        welcome_description  = "Promptuino will create a folder to store your projects and the libraries downloaded by the tool. You can change this location later in Settings.",
        welcome_folder_label = "Chosen folder",
        welcome_browse       = "Browse…",
        welcome_confirm      = "Continue",
        welcome_hint         = "Tip: keep the default folder if you have no preference.",
        mode_beginner     = "Beginner",
        mode_intermediate = "Intermediate",
        mode_advanced     = "Advanced",
        studio_prompt_label       = "Generate a feature",
        studio_prompt_placeholder = "Describe what you want to program… E.g. turn on a red LED when temperature exceeds 30°C",
        prompt_tips = (
            "E.g. blink an LED on D13",
            "Tip: describe one feature at a time",
            "E.g. measure the temperature with a DHT22",
            "Tip: name your component — \"DHT22\" rather than \"a sensor\"",
            "E.g. light an LED when button D2 is pressed",
            "Tip: mention the pin and the board if needed",
            "Tip: attach a text file with your wiring so you don't retype it",
            "Tip: each generation produces different code — rather than fixing everything, try regenerating",
            "Note: code quality depends on the AI model used",
            "E.g. sweep a servo from 0 to 180°",
            "E.g. measure a distance with an HC-SR04 sensor",
            "E.g. show a message on an SSD1306 OLED screen",
            "E.g. play a melody on a buzzer",
            "E.g. control a motor with an L298N driver",
            "Tip: use \"View diagram\" to check your wiring before uploading",
            "Tip: if the code doesn't compile, the Repair tool can fix errors",
            "Tip: switch to Advanced mode to see and edit the code by hand",
            "Tip: in Advanced mode the code opens as 2 windows — the AI-generated one and your stable code, which the AI never changes. Handy for trying things out without breaking working code",
            "Tip: give a value when needed — \"blink every 200 ms\"",
        ),
        studio_code_label         = "Generated code",
        studio_generate           = "Generate",
        studio_generating         = "Generating…",
        studio_gen_slow_soft      = "This is taking longer than usual. Generation is still running — you can wait, or click « Cancel ».",
        studio_gen_slow_hard      = "Still running. A complex request can take several minutes on a local model. Nothing is lost: it will finish if you let it.",
        studio_generate_send      = "Generate & Upload",
        studio_upload_only        = "Upload",
        studio_err_no_prompt      = "Please enter a prompt.",
        clarify_title             = "Specify the component",
        clarify_intro             = "Several components match. Which one are you using?",
        clarify_step              = "Clarification {n}/{total}",
        clarify_dont_care         = "Choose for me (most likely)",
        clarify_other_label       = "Other / let me specify…",
        clarify_other_apply       = "Apply",
        studio_err_no_backend     = "No AI model available. Configure one in the AI Model tab.",
        studio_compile_upload     = "Upload",
        studio_window_ai          = "Generated code (AI)",
        studio_window_stable      = "Stable code",
        studio_transfer_to_stable = "Transfer to stable ▶",
        studio_transfer_overwrite_msg = "Overwrite the current stable code with the AI code?",
        studio_console_src_ai     = "AI window",
        studio_console_src_stable = "Stable window",
        studio_compile_upload_stable = "Upload",
        studio_mode_locked_busy   = "Finish the current operation before switching mode.",
        studio_compiling          = "Compiling…",
        studio_uploading          = "Uploading…",
        studio_upload_success     = "Uploaded successfully",
        studio_upload_failed      = "Upload failed — the board was NOT reprogrammed",
        studio_verifying          = "Verifying compilation…",
        studio_recombine          = "Linked features detected — regenerating as one…",
        studio_recombine_failed   = "The code does not compile (linked features) — simplify your prompt or try again",
        studio_verify_ok          = "Code compiles ✓",
        studio_verify_repaired_ok = "Repaired ✓ — the code compiles now",
        studio_repair_insufficient = "The repair was not enough: the features appear linked.",
        studio_verify_failed      = "The code does not compile after repair — restored; ask for help in the chat below",
        feature_tools_delete_tip   = "Delete a feature",
        feature_tools_regen_tip    = "Regenerate a feature",
        feature_select_delete_title = "Delete one or more features",
        feature_select_regen_title = "Regenerate one or more features",
        feature_select_delete_confirm = "Delete",
        feature_select_regen_confirm = "Regenerate",
        feature_delete_dirty_warn  = "The code was edited by hand: those edits will be lost. Continue?",
        feature_deleted_msg        = "Feature(s) deleted.",
        studio_program_ready      = "Code ready: {}",
        studio_program_ready_plain = "Code ready",
        studio_no_code_generated  = "No code generated",
        studio_output_label       = "Log",
        studio_err_no_code        = "No code to compile.",
        studio_err_no_board       = "No board selected. Check that your board is properly connected.",
        studio_err_no_fqbn        = "Board not supported by arduino-cli.",
        studio_err_no_port        = "No serial port detected. Check that your board is properly connected.",
        studio_err_no_cli         = "arduino-cli not found. It normally ships with Promptuino: reinstall the application.",
        studio_unverified_no_cli  = "not verified: arduino-cli not found, reinstall Promptuino",
        studio_unverified_no_board = "not verified: no board selected",
        studio_fixing             = "AI correction in progress…",
        studio_lib_installing         = "Installing libraries…",
        studio_core_installing        = "Installing board core…",
        studio_err_missing_lib        = "Missing library:",
        studio_err_core_install       = "Failed to install the core for this board:",
        studio_err_upload_port_busy   = "The serial port is busy. Close the Serial Monitor before uploading.",
        studio_err_upload_port        = "Serial port not found. Check the USB connection.",
        studio_err_upload_no_response = "Board not responding. Replug it or press Reset.",
        studio_err_upload_timeout     = "Upload timed out. Check the connection.",
        studio_explaining             = "AI is analysing the error…",
        studio_fix_attempt            = "Compile error — AI repair",
        studio_repairing              = "AI deep repair in progress…",
        studio_repair_summary         = "Applied repairs:",
        studio_cancel                 = "Cancel",
        studio_instructions_title     = "Wiring instructions",
        studio_context_badge          = "Context: {name} ({chars} chars)",
        studio_context_remove         = "Remove context",
        studio_context_add_hint       = "Add a context file (.md or .txt)",
        studio_context_add_tooltip    = "Add context",
        studio_attach                 = "+ Attach",
        studio_context_picker_title   = "Choose a context file",
        studio_context_picker_filter  = "Text files (*.md *.txt *.ino *.cpp *.c *.h *.csv *.log)",
        studio_context_invalid_ext    = "Unsupported format — a text file is expected (.md, .txt, .ino, .cpp, .c, .h, .csv, .log).",
        studio_context_read_error     = "Can't read this file.",
        studio_context_need_project   = "Create or open a project before adding context.",
        tutorial_next                 = "Next",
        tutorial_back                 = "Back",
        tutorial_skip                 = "Skip",
        tutorial_finish               = "Done",
        mn_review_tutorial            = "Replay tutorial",
        tuto_beg_studio               = "Studio: this is where you describe and generate your program, then send it to the board.",
        tuto_beg_projets              = "Projects: find, open and organize your saved programs.",
        tuto_beg_carte                = "Board: your board is detected automatically; if not, you can pick your board model manually.",
        tuto_beg_ia                   = "AI model: choose here which AI powers the app — locally via Ollama, or in the cloud via the API of your choice.",
        tuto_beg_mode                 = "Pick your level: Beginner, Intermediate or Advanced. More controls appear as you go.",
        tuto_beg_theme                = "Switch between light and dark theme.",
        tuto_beg_prompt               = "Describe here, in plain words, what you want to do (e.g. \"blink an LED\").",
        tuto_beg_actions              = "Generate the code and send it to your board, or open the wiring diagram.",
        tuto_beg_journal              = "Follow what happens here: generation, compilation, upload to the board, and any errors.",
        tuto_beg_chat                 = "Ask the assistant your questions — it knows your project.",
        tuto_int_generate             = "This button generates code: create a new feature, add one, or modify an existing feature.",
        tuto_int_editor               = "The generated code shows here — and you can edit it directly by hand.",
        tuto_int_compile              = "Compile, upload to the board and open the wiring diagram.",
        tuto_int_tools                = "The AI tools: explain, comment or repair the generated code.",
        tuto_int_features             = "Each generated feature is listed here: tick it to highlight its lines, or regenerate / delete it.",
        tuto_adv_editor               = "In Advanced mode your code opens as 2 windows. Here, the AI-generated code.",
        tuto_adv_stable               = "Your stable code window: you edit it by hand, the AI never touches it. Perfect to keep working code.",
        tuto_adv_transfer             = "Transfer features between the two windows (drag & drop), to tidy up your code safe from the AI.",
        tuto_adv_comments             = "Set how many comments are added to the generated code.",
        tuto_adv_serial               = "Toggle including the serial monitor (Serial) in the code.",
        serial_title            = "Serial Monitor",
        serial_baud             = "Baud",
        serial_autoscroll       = "Auto-scroll",
        serial_send             = "Send",
        serial_send_placeholder = "Send a message…",
        serial_connect          = "Connect",
        serial_disconnect       = "Disconnect",
        serial_console_header   = "Console output:",
        readonly_popup_ok  = "OK",
        readonly_popup_switch = "Switch to Advanced",
        studio_overwrite_msg    = "This will replace the existing code.\nAre you sure?",
        studio_beginner_overwrite_msg = "This will replace the existing code.<br><br><b>To add a feature without overwriting, switch to Intermediate mode</b>",
        studio_overwrite_accept = "Replace",
        studio_overwrite_cancel = "Cancel",
        studio_overwrite_switch = "Switch to Intermediate",
        studio_iterate          = "Add a feature",
        studio_iterating        = "Adding a feature…",
        menu_file        = "File",
        chat_title              = "AI Assistant",
        chat_placeholder        = "Ask a question...",
        chat_send_button        = "Send",
        chat_stop_button        = "Stop",
        chat_new_conversation   = "New conversation",
        chat_thinking           = "Thinking…",
        chat_no_backend         = "Activate a model in the AI Model tab.",
        chat_attach_tooltip       = "Attach a document",
        chat_attachment_too_large = "Document truncated to 100 KB for context.",
        chat_model_label_tooltip  = "Active model — click to change",
        chat_no_model_label       = "No model",
        chat_open_in_studio     = "Open in Studio",
        chat_answer_anyway      = "Answer anyway",
        chat_backend_timeout    = (
            "The model is not responding — check your connection or "
            "API key."
        ),
        chat_stream_soft_warn   = (
            "*⏳ The model is taking longer than usual. "
            "You can wait or click Stop.*"
        ),
        chat_stream_hard_warn   = (
            "*⏳ It's been 3 minutes without a response. The model is "
            "probably stuck. You should click Stop.*"
        ),
        chat_help_tooltip       = "Ask the assistant",
        chat_help_menu_code     = "Ask the assistant",
        ctx_menu_undo           = "Undo",
        ctx_menu_redo           = "Redo",
        ctx_menu_cut            = "Cut",
        ctx_menu_copy           = "Copy",
        ctx_menu_paste          = "Paste",
        ctx_menu_delete         = "Delete",
        ctx_menu_select_all     = "Select All",
        chat_help_error_button  = "Ask for help on this error",
        registry_ask_chat      = "Ask for help in the chat",
        chat_help_prefix_unknown = (
            "My program uses components the app does not know: {parts}. "
            "How should I go about it?"),
        chat_help_prefix_motor = (
            "My pins {pins} might form a single motor, or they could be "
            "separate outputs (LED, buzzer, servo…). Help me understand "
            "the difference and choose."
        ),
        chat_help_prefix_technique = (
            "On pin {pin}, the detector is hesitating between {candidates}. "
            "Can you explain the difference in this context?"
        ),
        chat_help_prefix_code   = (
            "Explain what the function `{function}` does."
        ),
        chat_help_prefix_selection = (
            "Explain what these lines do."
        ),
        chat_help_prefix_wrong_component = "Component {ref} ({type}): ",
        chat_correction_to_studio  = "Fix in Studio",
        chat_correction_redirect   = (
            "It looks like it's actually a {name}. You can fix this in the "
            "Studio — your prompt will be pre-filled."
        ),
        chat_correction_studio_offer = (
            "Want to apply a change to your code? You can do it in the Studio."
        ),
        chat_help_prefix_error  = (
            "I have this compilation error, can you help me understand "
            "it?"
        ),
        nudge_beginner_to_intermediate = "<b>Tip</b>: In <b>Intermediate</b> mode you see the code, you can add or modify a feature — and even edit it yourself.",
        nudge_intermediate_to_advanced = "<b>Tip</b>: In <b>Advanced</b> mode your code opens as 2 windows — the AI-generated one and your stable code, which the AI never changes. Ideal for trying ideas out without breaking what already works.",
        gen_modal_title           = "What do you want to do?",
        gen_modal_regenerate      = "Regenerate",
        gen_modal_regenerate_desc = "Start over from this description",
        gen_modal_add             = "Add a feature",
        gen_modal_add_desc        = "Keep the existing code, add this behavior",
        gen_modal_correct         = "Modify",
        gen_modal_correct_desc    = "Modify an existing feature",
        gen_modal_target          = "Feature(s) to modify:",
        gen_modal_target_all      = "Select all",
        gen_modal_validate        = "Confirm",
        gen_modal_cancel          = "Cancel",
        modify_guidance_title     = "Modify in the Studio",
        modify_guidance_body      = "Features can't be edited in Beginner mode, so you'll switch to Intermediate mode.\n\nTo apply the change, click « Generate » then « Modify ».",
        modify_guidance_ok        = "Got it",
        studio_err_parse_failed        = "The generated code could not be interpreted. Try again.",
        studio_inline_overwrite_title  = "Manual changes",
        studio_inline_overwrite_body   = "You edited the code by hand. This action will regenerate and overwrite those changes. Continue?",
        studio_merge_features_title    = "Merge features",
        studio_merge_features_body     = "The {n} selected features will be merged into a single one. Continue?",
        component_replace_dropdown          = "Replace with:",
        component_replace_divergence_title  = "Code ≠ diagram",
        component_replace_divergence_message = "The code says \"{old}\", the diagram will show \"{new}\". Continue?",
        component_replace_continue          = "Continue",
    ),
    "es": Strings(
        nav_carte        = "Placa",
        nav_ia           = "Modelo IA",
        nav_studio       = "Studio",
        nav_tableau      = "Panel",
        topbar_collapse  = "Colapsar navegación",
        topbar_expand    = "Mostrar navegación",
        topbar_settings  = "Configuración",
        theme_light      = "Modo claro",
        theme_dark       = "Modo oscuro",
        status_ia        = "Modelo IA:",
        status_board     = "Placa:",
        status_no_board  = "Sin placa",
        board_auto_title    = "Detección automática",
        board_auto_subtitle = "Conecta tu placa USB, será reconocida automáticamente.",
        board_connected     = "Conectada",
        board_disconnected  = "Placa desconectada",
        board_manual_title      = "Selección manual",
        board_manual_subtitle   = "¿Placa no detectada? Selecciónala manualmente.",
        board_env               = "Entorno",
        board_model             = "Modelo",
        board_model_placeholder = "Seleccionar un modelo",
        board_port              = "Puerto serie",
        board_port_placeholder  = "Seleccionar un puerto",
        board_validate          = "Validar",
        board_manual_confirmed  = "Configurada manualmente",
        ia_claude_subtitle     = "Usa el CLI claude instalado en tu máquina. No requiere clave API.",
        ia_claude_available    = "Disponible",
        ia_claude_unavailable  = "No disponible — instala Claude Code",
        ia_gemini_subtitle     = "Usa la API Google Generative AI — modelo gemini-1.5-flash.",
        ia_anthropic_subtitle  = "Usa la API Anthropic (pago por uso) — modelo claude-sonnet-4-6.",
        ia_api_key_label       = "Clave API",
        ia_api_key_placeholder = "Introduce tu clave API...",
        ia_save_key            = "Guardar",
        ia_activate            = "Activar este modelo",
        ia_active              = "Activo",
        ia_key_saved           = "Clave guardada",
        ia_ollama_subtitle          = "Usa el servidor Ollama local. No requiere clave API.",
        ia_ollama_running           = "Servidor activo — modelo disponible",
        ia_ollama_not_running       = "Ollama no está en ejecución — ejecuta: ollama serve",
        ia_ollama_model_missing     = "Modelo no descargado — ejecuta: ollama pull",
        ia_ollama_model_label       = "Modelo",
        ia_ollama_model_placeholder = "ej. gemma4:e2b",
        ia_ollama_ctx_label         = "Tamaño de contexto",
        ia_ollama_ctx_help          = "Contexto utilizado al chatear con un modelo local. Si el modelo es muy lento, reduce este valor.",
        settings_title   = "Configuración",
        settings_language = "Idioma",
        settings_theme    = "Tema",
        settings_storage              = "Almacenamiento",
        settings_storage_title        = "Carpeta de proyectos y librerías",
        settings_storage_description  = "Elige dónde se guardarán tus proyectos y las librerías descargadas por la herramienta.",
        settings_storage_current      = "Carpeta actual",
        settings_storage_default_suffix = " (predeterminada)",
        settings_storage_change       = "Cambiar…",
        settings_storage_reset        = "Restablecer",
        settings_storage_picker_title = "Elegir la carpeta de almacenamiento",
        settings_storage_warning      = "Los proyectos y librerías ya presentes en la carpeta anterior no se trasladan automáticamente — puedes copiarlos manualmente si es necesario.",
        welcome_title        = "Bienvenido a Promptuino",
        welcome_heading      = "¿Dónde quieres guardar tus proyectos?",
        welcome_description  = "Promptuino creará una carpeta para almacenar tus proyectos y las librerías descargadas por la herramienta. Podrás cambiar esta ubicación más tarde en los Ajustes.",
        welcome_folder_label = "Carpeta elegida",
        welcome_browse       = "Explorar…",
        welcome_confirm      = "Continuar",
        welcome_hint         = "Consejo: conserva la carpeta predeterminada si no tienes preferencia.",
        mode_beginner     = "Principiante",
        mode_intermediate = "Intermedio",
        mode_advanced     = "Avanzado",
        studio_prompt_label       = "Generar una función",
        studio_prompt_placeholder = "Describe lo que quieres programar… Ej. encender un LED rojo cuando la temperatura supere los 30°C",
        prompt_tips = (
            "Ej.: parpadea un LED en D13",
            "Consejo: describe una sola funcionalidad a la vez",
            "Ej.: mide la temperatura con un DHT22",
            "Consejo: nombra tu componente — «DHT22» en vez de «un sensor»",
            "Ej.: enciende un LED al pulsar el botón D2",
            "Consejo: indica el pin y la placa si hace falta",
            "Consejo: adjunta un archivo de texto con tu cableado para no volver a escribirlo",
            "Consejo: cada generación produce un código distinto — en vez de corregirlo todo, prueba a regenerar",
            "Info: la calidad del código depende del modelo de IA utilizado",
            "Ej.: mueve un servo de 0 a 180°",
            "Ej.: mide una distancia con un sensor HC-SR04",
            "Ej.: muestra un mensaje en una pantalla OLED SSD1306",
            "Ej.: reproduce una melodía en un zumbador",
            "Ej.: controla un motor con un driver L298N",
            "Consejo: usa «Ver el esquema» para revisar el cableado antes de subir",
            "Consejo: si el código no compila, la herramienta Reparar puede corregir errores",
            "Consejo: cambia a modo Avanzado para ver y editar el código a mano",
            "Consejo: en modo Avanzado el código se abre en 2 ventanas — el generado por la IA y tu código estable, que la IA nunca modifica. Práctico para probar cosas sin romper código que funciona",
            "Consejo: indica un valor si hace falta — «parpadea cada 200 ms»",
        ),
        studio_code_label         = "Código generado",
        studio_generate           = "Generar",
        studio_generating         = "Generando…",
        studio_gen_slow_soft      = "Está tardando más de lo habitual. La generación continúa — puedes esperar o pulsar « Cancelar ».",
        studio_gen_slow_hard      = "Sigue en curso. Una petición compleja puede tardar varios minutos en un modelo local. No se pierde nada: terminará si la dejas.",
        studio_generate_send      = "Generar y subir",
        studio_upload_only        = "Subir",
        studio_err_no_prompt      = "Por favor, introduce un prompt.",
        clarify_title             = "Especificar el componente",
        clarify_intro             = "Varios componentes coinciden. ¿Cuál usas?",
        clarify_step              = "Aclaración {n}/{total}",
        clarify_dont_care         = "Elige por mí (el más probable)",
        clarify_other_label       = "Otro / especificar…",
        clarify_other_apply       = "Aplicar",
        studio_err_no_backend     = "Ningún modelo IA disponible. Configura uno en la pestaña Modelo IA.",
        studio_compile_upload     = "Subir",
        studio_window_ai          = "Código generado (IA)",
        studio_window_stable      = "Código estable",
        studio_transfer_to_stable = "Transferir a estable ▶",
        studio_transfer_overwrite_msg = "¿Sobrescribir el código estable actual con el código de la IA?",
        studio_console_src_ai     = "Ventana IA",
        studio_console_src_stable = "Ventana estable",
        studio_compile_upload_stable = "Subir",
        studio_mode_locked_busy   = "Termina la operación en curso antes de cambiar de modo.",
        studio_compiling          = "Compilando…",
        studio_uploading          = "Subiendo…",
        studio_upload_success     = "Subido con éxito",
        studio_upload_failed      = "Subida fallida — la placa NO fue reprogramada",
        studio_verifying          = "Verificando la compilación…",
        studio_recombine          = "Funcionalidades vinculadas detectadas — regenerando todo…",
        studio_recombine_failed   = "El código no compila (funcionalidades vinculadas) — simplifica tu prompt o reinténtalo",
        studio_verify_ok          = "El código compila ✓",
        studio_verify_repaired_ok = "Reparado ✓ — el código ya compila",
        studio_repair_insufficient = "La reparación no bastó: las funcionalidades parecen vinculadas.",
        studio_verify_failed      = "El código no compila tras la reparación — restaurado; pide ayuda en el chat de abajo",
        feature_tools_delete_tip   = "Eliminar una funcionalidad",
        feature_tools_regen_tip    = "Regenerar una funcionalidad",
        feature_select_delete_title = "Eliminar una o varias funcionalidades",
        feature_select_regen_title = "Regenerar una o varias funcionalidades",
        feature_select_delete_confirm = "Eliminar",
        feature_select_regen_confirm = "Regenerar",
        feature_delete_dirty_warn  = "El código se editó a mano: esos cambios se perderán. ¿Continuar?",
        feature_deleted_msg        = "Funcionalidad(es) eliminada(s).",
        studio_program_ready      = "Código listo: {}",
        studio_program_ready_plain = "Código listo",
        studio_no_code_generated  = "Ningún código generado",
        studio_output_label       = "Registro",
        studio_err_no_code        = "No hay código para compilar.",
        studio_err_no_board       = "Ninguna placa seleccionada. Comprueba que tu placa esté bien conectada.",
        studio_err_no_fqbn        = "Placa no compatible con arduino-cli.",
        studio_err_no_port        = "No se detectó ningún puerto serie. Comprueba que tu placa esté bien conectada.",
        studio_err_no_cli         = "arduino-cli no se encuentra. Normalmente se instala con Promptuino: reinstala la aplicación.",
        studio_unverified_no_cli  = "sin verificar: arduino-cli no encontrado, reinstala Promptuino",
        studio_unverified_no_board = "sin verificar: ninguna placa seleccionada",
        studio_fixing             = "Corrección IA en curso…",
        studio_lib_installing         = "Instalando librerías…",
        studio_core_installing        = "Instalando núcleo de la placa…",
        studio_err_missing_lib        = "Librería no encontrada:",
        studio_err_core_install       = "No se pudo instalar el núcleo para esta placa:",
        studio_err_upload_port_busy   = "El puerto serie está ocupado. Cierra el Monitor Serie antes de cargar.",
        studio_err_upload_port        = "Puerto serie no encontrado. Comprueba la conexión USB.",
        studio_err_upload_no_response = "La placa no responde. Vuelve a conectarla o pulsa Reset.",
        studio_err_upload_timeout     = "Tiempo de espera agotado. Comprueba la conexión.",
        studio_explaining             = "La IA está analizando el error…",
        studio_fix_attempt            = "Error de compilación — Reparación IA",
        studio_repairing              = "Reparación profunda por IA…",
        studio_repair_summary         = "Reparaciones aplicadas:",
        studio_cancel                 = "Cancelar",
        studio_instructions_title     = "Instrucciones de conexión",
        studio_context_badge          = "Contexto: {name} ({chars} car.)",
        studio_context_remove         = "Quitar contexto",
        studio_context_add_hint       = "Añadir un archivo de contexto (.md o .txt)",
        studio_context_add_tooltip    = "Añadir contexto",
        studio_attach                 = "+ Adjuntar",
        studio_context_picker_title   = "Elegir un archivo de contexto",
        studio_context_picker_filter  = "Archivos de texto (*.md *.txt *.ino *.cpp *.c *.h *.csv *.log)",
        studio_context_invalid_ext    = "Formato no admitido — se espera un archivo de texto (.md, .txt, .ino, .cpp, .c, .h, .csv, .log).",
        studio_context_read_error     = "No se puede leer este archivo.",
        studio_context_need_project   = "Crea o abre un proyecto antes de añadir contexto.",
        tutorial_next                 = "Siguiente",
        tutorial_back                 = "Atrás",
        tutorial_skip                 = "Saltar",
        tutorial_finish               = "Listo",
        mn_review_tutorial            = "Repetir el tutorial",
        tuto_beg_studio               = "Studio: aquí describes y generas tu programa, y luego lo envías a la placa.",
        tuto_beg_projets              = "Proyectos: encuentra, abre y organiza tus programas guardados.",
        tuto_beg_carte                = "Placa: tu placa se detecta automáticamente; si no, puedes elegir el modelo manualmente.",
        tuto_beg_ia                   = "Modelo de IA: elige aquí qué IA hace funcionar la app — en local con Ollama, o en la nube con la API que prefieras.",
        tuto_beg_mode                 = "Elige tu nivel: Principiante, Intermedio o Avanzado. Aparecen más controles según avanzas.",
        tuto_beg_theme                = "Cambia entre tema claro y oscuro.",
        tuto_beg_prompt               = "Describe aquí, en lenguaje natural, lo que quieres hacer (p. ej. «parpadear un LED»).",
        tuto_beg_actions              = "Genera el código y envíalo a tu placa, o abre el esquema de cableado.",
        tuto_beg_journal              = "Sigue aquí lo que ocurre: generación, compilación, envío a la placa, y los posibles errores.",
        tuto_beg_chat                 = "Haz tus preguntas al asistente: conoce tu proyecto.",
        tuto_int_generate             = "Este botón genera código: crear una nueva funcionalidad, añadir una, o modificar una existente.",
        tuto_int_editor               = "El código generado aparece aquí — y puedes editarlo directamente a mano.",
        tuto_int_compile              = "Compila, envía a la placa y abre el esquema de cableado.",
        tuto_int_tools                = "Las herramientas de IA: explica, comenta o repara el código generado.",
        tuto_int_features             = "Cada función generada aparece aquí: márcala para resaltar sus líneas, o regenérala / elimínala.",
        tuto_adv_editor               = "En modo Avanzado tu código se abre en 2 ventanas. Aquí, el código generado por la IA.",
        tuto_adv_stable               = "Tu ventana de código estable: la editas a mano, la IA nunca la toca. Perfecta para guardar código que funciona.",
        tuto_adv_transfer             = "Transfiere funciones entre las dos ventanas (arrastrar y soltar), para ordenar tu código a salvo de la IA.",
        tuto_adv_comments             = "Ajusta cuántos comentarios se añaden al código generado.",
        tuto_adv_serial               = "Activa la inclusión del monitor serie (Serial) en el código.",
        serial_title            = "Monitor Serie",
        serial_baud             = "Baud",
        serial_autoscroll       = "Desplazamiento auto",
        serial_send             = "Enviar",
        serial_send_placeholder = "Enviar un mensaje…",
        serial_connect          = "Conectar",
        serial_disconnect       = "Desconectar",
        serial_console_header   = "Salida de consola:",
        readonly_popup_ok  = "OK",
        readonly_popup_switch = "Cambiar a Avanzado",
        studio_overwrite_msg    = "Esta acción reemplazará el código existente.\n¿Estás seguro?",
        studio_beginner_overwrite_msg = "Esta acción reemplazará el código existente.<br><br><b>Para añadir una función sin sobrescribir, cambia al modo Intermedio</b>",
        studio_overwrite_accept = "Reemplazar",
        studio_overwrite_cancel = "Cancelar",
        studio_overwrite_switch = "Cambiar a Intermedio",
        studio_iterate          = "Añadir función",
        studio_iterating        = "Añadiendo una funcionalidad…",
        menu_file        = "Archivo",
        chat_title              = "Asistente IA",
        chat_placeholder        = "Haz una pregunta...",
        chat_send_button        = "Enviar",
        chat_stop_button        = "Detener",
        chat_new_conversation   = "Nueva conversación",
        chat_thinking           = "Reflexión en curso…",
        chat_no_backend         = "Activa un modelo en la pestaña Modelo IA.",
        chat_attach_tooltip       = "Adjuntar un documento",
        chat_attachment_too_large = "Documento truncado a 100 KB para el contexto.",
        chat_model_label_tooltip  = "Modelo activo — clic para cambiar",
        chat_no_model_label       = "Sin modelo",
        chat_open_in_studio     = "Abrir en Studio",
        chat_answer_anyway      = "Responder de todos modos",
        chat_backend_timeout    = (
            "El modelo no responde — comprueba tu conexión o la "
            "clave API."
        ),
        chat_stream_soft_warn   = (
            "*⏳ El modelo está tardando más de lo habitual. "
            "Puedes esperar o hacer clic en Detener.*"
        ),
        chat_stream_hard_warn   = (
            "*⏳ Hace 3 minutos sin respuesta, el modelo "
            "probablemente esté bloqueado. Deberías hacer clic en "
            "Detener.*"
        ),
        chat_help_tooltip       = "Preguntar al asistente",
        chat_help_menu_code     = "Preguntar al asistente",
        ctx_menu_undo           = "Deshacer",
        ctx_menu_redo           = "Rehacer",
        ctx_menu_cut            = "Cortar",
        ctx_menu_copy           = "Copiar",
        ctx_menu_paste          = "Pegar",
        ctx_menu_delete         = "Eliminar",
        ctx_menu_select_all     = "Seleccionar todo",
        chat_help_error_button  = "Pedir ayuda con este error",
        registry_ask_chat      = "Pedir ayuda en el chat",
        chat_help_prefix_unknown = (
            "Mi programa usa componentes que la aplicación no conoce: "
            "{parts}. ¿Cómo debo proceder?"),
        chat_help_prefix_motor = (
            "Mis pines {pins} podrían formar un solo motor, o ser salidas "
            "separadas (LED, zumbador, servo…). Ayúdame a entender la "
            "diferencia y a elegir."
        ),
        chat_help_prefix_technique = (
            "En el pin {pin}, el detector duda entre {candidates}. "
            "¿Puedes explicarme la diferencia en este contexto?"
        ),
        chat_help_prefix_code   = (
            "Explícame qué hace la función `{function}`."
        ),
        chat_help_prefix_selection = (
            "Explícame qué hacen estas líneas."
        ),
        chat_help_prefix_wrong_component = "Componente {ref} ({type}): ",
        chat_correction_to_studio  = "Corregir en Studio",
        chat_correction_redirect   = (
            "Parece que en realidad es un {name}. Puedes corregirlo en el "
            "Studio — tu prompt se rellenará."
        ),
        chat_correction_studio_offer = (
            "¿Quieres aplicar un cambio a tu código? Puedes hacerlo en el "
            "Studio."
        ),
        chat_help_prefix_error  = (
            "Tengo este error de compilación, ¿puedes ayudarme a "
            "entenderlo?"
        ),
        nudge_beginner_to_intermediate = "<b>Consejo</b>: En modo <b>Intermedio</b> ves el código, puedes añadir o modificar una función — e incluso editarlo tú mismo.",
        nudge_intermediate_to_advanced = "<b>Consejo</b>: En modo <b>Avanzado</b> tu código se abre en 2 ventanas — el generado por la IA y tu código estable, que la IA nunca modifica. Ideal para probar ideas sin romper lo que ya funciona.",
        gen_modal_title           = "¿Qué quieres hacer?",
        gen_modal_regenerate      = "Regenerar",
        gen_modal_regenerate_desc = "Empezar de cero con esta descripción",
        gen_modal_add             = "Añadir una función",
        gen_modal_add_desc        = "Mantener lo existente, añadir este comportamiento",
        gen_modal_correct         = "Modificar",
        gen_modal_correct_desc    = "Modificar una función existente",
        gen_modal_target          = "Función(es) a modificar:",
        gen_modal_target_all      = "Seleccionar todo",
        gen_modal_validate        = "Validar",
        gen_modal_cancel          = "Cancelar",
        modify_guidance_title     = "Modificar en el Studio",
        modify_guidance_body      = "Las funciones no se pueden modificar en modo Principiante, vas a cambiar al modo Intermedio.\n\nPara aplicar el cambio, haz clic en « Generar » y luego « Modificar ».",
        modify_guidance_ok        = "Entendido",
        studio_err_parse_failed        = "No se pudo interpretar el código generado. Inténtalo de nuevo.",
        studio_inline_overwrite_title  = "Cambios manuales",
        studio_inline_overwrite_body   = "Has editado el código a mano. Esta acción regenerará y sobrescribirá esos cambios. ¿Continuar?",
        studio_merge_features_title    = "Fusionar funcionalidades",
        studio_merge_features_body     = "Las {n} funcionalidades seleccionadas se fusionarán en una sola. ¿Continuar?",
        component_replace_dropdown          = "Reemplazar por:",
        component_replace_divergence_title  = "Código ≠ esquema",
        component_replace_divergence_message = "El código dice «{old}», el esquema mostrará «{new}». ¿Continuar?",
        component_replace_continue          = "Continuar",
    ),
    "it": Strings(
        nav_carte        = "Scheda",
        nav_ia           = "Modello IA",
        nav_studio       = "Studio",
        nav_tableau      = "Dashboard",
        topbar_collapse  = "Comprimi navigazione",
        topbar_expand    = "Mostra navigazione",
        topbar_settings  = "Impostazioni",
        theme_light      = "Modalità chiara",
        theme_dark       = "Modalità scura",
        status_ia        = "Modello IA:",
        status_board     = "Scheda:",
        status_no_board  = "Nessuna scheda",
        board_auto_title    = "Rilevamento automatico",
        board_auto_subtitle = "Collega la tua scheda USB, verrà riconosciuta automaticamente.",
        board_connected     = "Connessa",
        board_disconnected  = "Scheda disconnessa",
        board_manual_title      = "Selezione manuale",
        board_manual_subtitle   = "Scheda non rilevata? Selezionala manualmente.",
        board_env               = "Ambiente",
        board_model             = "Modello",
        board_model_placeholder = "Seleziona un modello",
        board_port              = "Porta seriale",
        board_port_placeholder  = "Seleziona una porta",
        board_validate          = "Valida",
        board_manual_confirmed  = "Configurata manualmente",
        ia_claude_subtitle     = "Usa il CLI claude installato sulla tua macchina. Nessuna chiave API richiesta.",
        ia_claude_available    = "Disponibile",
        ia_claude_unavailable  = "Non disponibile — installa Claude Code",
        ia_gemini_subtitle     = "Usa l'API Google Generative AI — modello gemini-1.5-flash.",
        ia_anthropic_subtitle  = "Usa l'API Anthropic (pay-per-use) — modello claude-sonnet-4-6.",
        ia_api_key_label       = "Chiave API",
        ia_api_key_placeholder = "Inserisci la tua chiave API...",
        ia_save_key            = "Salva",
        ia_activate            = "Attiva questo modello",
        ia_active              = "Attivo",
        ia_key_saved           = "Chiave salvata",
        ia_ollama_subtitle          = "Usa il server Ollama locale. Nessuna chiave API richiesta.",
        ia_ollama_running           = "Server attivo — modello disponibile",
        ia_ollama_not_running       = "Ollama non avviato — esegui: ollama serve",
        ia_ollama_model_missing     = "Modello non scaricato — esegui: ollama pull",
        ia_ollama_model_label       = "Modello",
        ia_ollama_model_placeholder = "es. gemma4:e2b",
        ia_ollama_ctx_label         = "Dimensione del contesto",
        ia_ollama_ctx_help          = "Contesto usato per la chat con un modello locale. Se il modello è molto lento, riduci questo valore.",
        settings_title   = "Impostazioni",
        settings_language = "Lingua",
        settings_theme    = "Tema",
        settings_storage              = "Archiviazione",
        settings_storage_title        = "Cartella dei progetti e delle librerie",
        settings_storage_description  = "Scegli dove salvare i tuoi progetti e le librerie scaricate dallo strumento.",
        settings_storage_current      = "Cartella attuale",
        settings_storage_default_suffix = " (predefinita)",
        settings_storage_change       = "Cambia…",
        settings_storage_reset        = "Ripristina",
        settings_storage_picker_title = "Scegli la cartella di archiviazione",
        settings_storage_warning      = "I progetti e le librerie già presenti nella cartella precedente non vengono spostati automaticamente — puoi copiarli manualmente se necessario.",
        welcome_title        = "Benvenuto in Promptuino",
        welcome_heading      = "Dove vuoi salvare i tuoi progetti?",
        welcome_description  = "Promptuino creerà una cartella per salvare i tuoi progetti e le librerie scaricate dallo strumento. Potrai modificare questa posizione più tardi nelle Impostazioni.",
        welcome_folder_label = "Cartella scelta",
        welcome_browse       = "Sfoglia…",
        welcome_confirm      = "Continua",
        welcome_hint         = "Suggerimento: mantieni la cartella predefinita se non hai preferenze.",
        mode_beginner     = "Principiante",
        mode_intermediate = "Intermedio",
        mode_advanced     = "Avanzato",
        studio_prompt_label       = "Genera una funzionalità",
        studio_prompt_placeholder = "Descrivi cosa vuoi programmare… Es. accendere un LED rosso quando la temperatura supera i 30°C",
        prompt_tips = (
            "Es.: fai lampeggiare un LED su D13",
            "Consiglio: descrivi una sola funzionalità alla volta",
            "Es.: misura la temperatura con un DHT22",
            "Consiglio: nomina il componente — «DHT22» invece di «un sensore»",
            "Es.: accendi un LED quando premi il pulsante D2",
            "Consiglio: indica il pin e la scheda se serve",
            "Consiglio: allega un file di testo con i collegamenti del montaggio per non riscriverli",
            "Consiglio: ogni generazione produce codice diverso — invece di correggere tutto, prova a rigenerare",
            "Info: la qualità del codice dipende dal modello di IA utilizzato",
            "Es.: muovi un servo da 0 a 180°",
            "Es.: misura una distanza con un sensore HC-SR04",
            "Es.: mostra un messaggio su uno schermo OLED SSD1306",
            "Es.: riproduci una melodia su un buzzer",
            "Es.: controlla un motore con un driver L298N",
            "Consiglio: usa «Vedi lo schema» per controllare il cablaggio prima di caricare",
            "Consiglio: se il codice non compila, lo strumento Ripara può correggere gli errori",
            "Consiglio: passa alla modalità Avanzata per vedere e modificare il codice a mano",
            "Consiglio: in modalità Avanzata il codice si apre in 2 finestre — quello generato dall'IA e il tuo codice stabile, che l'IA non modifica mai. Comodo per provare cose senza rompere codice funzionante",
            "Consiglio: indica un valore se serve — «lampeggia ogni 200 ms»",
        ),
        studio_code_label         = "Codice generato",
        studio_generate           = "Genera",
        studio_generating         = "Generazione in corso…",
        studio_gen_slow_soft      = "Sta impiegando più del solito. La generazione continua — puoi aspettare o fare clic su « Annulla ».",
        studio_gen_slow_hard      = "Ancora in corso. Una richiesta complessa può richiedere diversi minuti su un modello locale. Non si perde nulla: arriverà in fondo se la lasci lavorare.",
        studio_generate_send      = "Genera e carica",
        studio_upload_only        = "Carica",
        studio_err_no_prompt      = "Inserisci un prompt.",
        clarify_title             = "Specifica il componente",
        clarify_intro             = "Più componenti corrispondono. Quale usi?",
        clarify_step              = "Chiarimento {n}/{total}",
        clarify_dont_care         = "Scegli per me (il più probabile)",
        clarify_other_label       = "Altro / specifico io…",
        clarify_other_apply       = "Applica",
        studio_err_no_backend     = "Nessun modello IA disponibile. Configurane uno nella scheda Modello IA.",
        studio_compile_upload     = "Carica",
        studio_window_ai          = "Codice generato (IA)",
        studio_window_stable      = "Codice stabile",
        studio_transfer_to_stable = "Trasferisci su stabile ▶",
        studio_transfer_overwrite_msg = "Sovrascrivere il codice stabile attuale con il codice IA?",
        studio_console_src_ai     = "Finestra IA",
        studio_console_src_stable = "Finestra stabile",
        studio_compile_upload_stable = "Carica",
        studio_mode_locked_busy   = "Termina l'operazione in corso prima di cambiare modalità.",
        studio_compiling          = "Compilazione…",
        studio_uploading          = "Caricamento…",
        studio_upload_success     = "Caricato con successo",
        studio_upload_failed      = "Caricamento fallito — la scheda NON è stata riprogrammata",
        studio_verifying          = "Verifica della compilazione…",
        studio_recombine          = "Funzionalità collegate rilevate — rigenerazione unica…",
        studio_recombine_failed   = "Il codice non compila (funzionalità collegate) — semplifica il prompt o riprova",
        studio_verify_ok          = "Il codice compila ✓",
        studio_verify_repaired_ok = "Riparato ✓ — il codice ora compila",
        studio_repair_insufficient = "La riparazione non è bastata: le funzionalità sembrano collegate.",
        studio_verify_failed      = "Il codice non compila dopo la riparazione — ripristinato; chiedi aiuto nella chat qui sotto",
        feature_tools_delete_tip   = "Elimina una funzionalità",
        feature_tools_regen_tip    = "Rigenera una funzionalità",
        feature_select_delete_title = "Elimina una o più funzionalità",
        feature_select_regen_title = "Rigenera una o più funzionalità",
        feature_select_delete_confirm = "Elimina",
        feature_select_regen_confirm = "Rigenera",
        feature_delete_dirty_warn  = "Il codice è stato modificato a mano: quelle modifiche andranno perse. Continuare?",
        feature_deleted_msg        = "Funzionalità eliminata/e.",
        studio_program_ready      = "Codice pronto: {}",
        studio_program_ready_plain = "Codice pronto",
        studio_no_code_generated  = "Nessun codice generato",
        studio_output_label       = "Registro",
        studio_err_no_code        = "Nessun codice da compilare.",
        studio_err_no_board       = "Nessuna scheda selezionata. Verifica che la tua scheda sia ben collegata.",
        studio_err_no_fqbn        = "Scheda non supportata da arduino-cli.",
        studio_err_no_port        = "Nessuna porta seriale rilevata. Verifica che la tua scheda sia ben collegata.",
        studio_err_no_cli         = "arduino-cli non trovato. Di norma viene installato con Promptuino: reinstalla l'applicazione.",
        studio_unverified_no_cli  = "non verificato: arduino-cli non trovato, reinstalla Promptuino",
        studio_unverified_no_board = "non verificato: nessuna scheda selezionata",
        studio_fixing             = "Correzione IA in corso…",
        studio_lib_installing         = "Installazione librerie…",
        studio_core_installing        = "Installazione del core della scheda…",
        studio_err_missing_lib        = "Libreria non trovata:",
        studio_err_core_install       = "Impossibile installare il core per questa scheda:",
        studio_err_upload_port_busy   = "La porta seriale è occupata. Chiudi il Monitor Seriale prima di caricare.",
        studio_err_upload_port        = "Porta seriale non trovata. Verificare il collegamento USB.",
        studio_err_upload_no_response = "La scheda non risponde. Ricollegarla o premere Reset.",
        studio_err_upload_timeout     = "Timeout durante il caricamento. Verificare la connessione.",
        studio_explaining             = "L'IA sta analizzando l'errore…",
        studio_fix_attempt            = "Errore di compilazione — Riparazione IA",
        studio_repairing              = "Riparazione profonda IA in corso…",
        studio_repair_summary         = "Riparazioni applicate:",
        studio_cancel                 = "Annulla",
        studio_instructions_title     = "Istruzioni di collegamento",
        studio_context_badge          = "Contesto: {name} ({chars} car.)",
        studio_context_remove         = "Rimuovi contesto",
        studio_context_add_hint       = "Aggiungi un file di contesto (.md o .txt)",
        studio_context_add_tooltip    = "Aggiungi contesto",
        studio_attach                 = "+ Allega",
        studio_context_picker_title   = "Scegli un file di contesto",
        studio_context_picker_filter  = "File di testo (*.md *.txt *.ino *.cpp *.c *.h *.csv *.log)",
        studio_context_invalid_ext    = "Formato non supportato — è atteso un file di testo (.md, .txt, .ino, .cpp, .c, .h, .csv, .log).",
        studio_context_read_error     = "Impossibile leggere questo file.",
        studio_context_need_project   = "Crea o apri un progetto prima di aggiungere un contesto.",
        tutorial_next                 = "Avanti",
        tutorial_back                 = "Indietro",
        tutorial_skip                 = "Salta",
        tutorial_finish               = "Fine",
        mn_review_tutorial            = "Rivedi il tutorial",
        tuto_beg_studio               = "Studio: qui descrivi e generi il tuo programma, poi lo invii alla scheda.",
        tuto_beg_projets              = "Progetti: trova, apri e organizza i tuoi programmi salvati.",
        tuto_beg_carte                = "Scheda: la tua scheda è riconosciuta automaticamente; altrimenti puoi scegliere il modello manualmente.",
        tuto_beg_ia                   = "Modello IA: scegli qui quale IA fa funzionare l'app — in locale con Ollama, o nel cloud con l'API che preferisci.",
        tuto_beg_mode                 = "Scegli il tuo livello: Principiante, Intermedio o Avanzato. Più controlli compaiono via via.",
        tuto_beg_theme                = "Passa dal tema chiaro a quello scuro.",
        tuto_beg_prompt               = "Descrivi qui, in linguaggio naturale, cosa vuoi fare (es. «far lampeggiare un LED»).",
        tuto_beg_actions              = "Genera il codice e invialo alla scheda, oppure apri lo schema di cablaggio.",
        tuto_beg_journal              = "Segui qui cosa succede: generazione, compilazione, invio alla scheda, ed eventuali errori.",
        tuto_beg_chat                 = "Fai le tue domande all'assistente: conosce il tuo progetto.",
        tuto_int_generate             = "Questo pulsante genera codice: creare una nuova funzionalità, aggiungerne una, o modificarne una esistente.",
        tuto_int_editor               = "Il codice generato appare qui — e puoi modificarlo direttamente a mano.",
        tuto_int_compile              = "Compila, invia alla scheda e apri lo schema di cablaggio.",
        tuto_int_tools                = "Gli strumenti IA: spiega, commenta o ripara il codice generato.",
        tuto_int_features             = "Ogni funzione generata è elencata qui: spuntala per evidenziarne le righe, oppure rigenerala / eliminala.",
        tuto_adv_editor               = "In modalità Avanzata il tuo codice si apre in 2 finestre. Qui, il codice generato dall'IA.",
        tuto_adv_stable               = "La tua finestra di codice stabile: la modifichi a mano, l'IA non la tocca mai. Perfetta per conservare codice funzionante.",
        tuto_adv_transfer             = "Trasferisci le funzioni tra le due finestre (trascina e rilascia), per sistemare il codice al riparo dall'IA.",
        tuto_adv_comments             = "Regola quanti commenti vengono aggiunti al codice generato.",
        tuto_adv_serial               = "Attiva l'inclusione del monitor seriale (Serial) nel codice.",
        serial_title            = "Monitor Seriale",
        serial_baud             = "Baud",
        serial_autoscroll       = "Scorrimento auto",
        serial_send             = "Invia",
        serial_send_placeholder = "Invia un messaggio…",
        serial_connect          = "Connetti",
        serial_disconnect       = "Disconnetti",
        serial_console_header   = "Uscita console:",
        readonly_popup_ok  = "OK",
        readonly_popup_switch = "Passa ad Avanzato",
        studio_overwrite_msg    = "Questa azione sostituirà il codice esistente.\nSei sicuro?",
        studio_beginner_overwrite_msg = "Questa azione sostituirà il codice esistente.<br><br><b>Per aggiungere una funzione senza sovrascrivere, passa alla modalità Intermedio</b>",
        studio_overwrite_accept = "Sostituisci",
        studio_overwrite_cancel = "Annulla",
        studio_overwrite_switch = "Passa a Intermedio",
        studio_iterate          = "Aggiungi funzione",
        studio_iterating        = "Aggiunta di una funzionalità in corso…",
        menu_file        = "File",
        chat_title              = "Assistente IA",
        chat_placeholder        = "Fai una domanda...",
        chat_send_button        = "Invia",
        chat_stop_button        = "Ferma",
        chat_new_conversation   = "Nuova conversazione",
        chat_thinking           = "Riflessione in corso…",
        chat_no_backend         = "Attiva un modello nella scheda Modello IA.",
        chat_attach_tooltip       = "Allega un documento",
        chat_attachment_too_large = "Documento troncato a 100 KB per il contesto.",
        chat_model_label_tooltip  = "Modello attivo — clicca per cambiare",
        chat_no_model_label       = "Nessun modello",
        chat_open_in_studio     = "Apri in Studio",
        chat_answer_anyway      = "Rispondi comunque",
        chat_backend_timeout    = (
            "Il modello non risponde — controlla la connessione o "
            "la chiave API."
        ),
        chat_stream_soft_warn   = (
            "*⏳ Il modello sta impiegando più del solito. "
            "Puoi aspettare o cliccare Ferma.*"
        ),
        chat_stream_hard_warn   = (
            "*⏳ Sono passati 3 minuti senza risposta, il modello è "
            "probabilmente bloccato. Dovresti cliccare Ferma.*"
        ),
        chat_help_tooltip       = "Chiedi all'assistente",
        chat_help_menu_code     = "Chiedi all'assistente",
        ctx_menu_undo           = "Annulla",
        ctx_menu_redo           = "Ripeti",
        ctx_menu_cut            = "Taglia",
        ctx_menu_copy           = "Copia",
        ctx_menu_paste          = "Incolla",
        ctx_menu_delete         = "Elimina",
        ctx_menu_select_all     = "Seleziona tutto",
        chat_help_error_button  = "Chiedi aiuto su questo errore",
        registry_ask_chat      = "Chiedere aiuto nella chat",
        chat_help_prefix_unknown = (
            "Il mio programma usa componenti che l'applicazione non "
            "conosce: {parts}. Come devo procedere?"),
        chat_help_prefix_motor = (
            "I miei pin {pins} potrebbero formare un solo motore, oppure "
            "essere uscite separate (LED, buzzer, servo…). Aiutami a "
            "capire la differenza e a scegliere."
        ),
        chat_help_prefix_technique = (
            "Sul pin {pin}, il rilevatore esita tra {candidates}. "
            "Puoi spiegarmi la differenza in questo contesto?"
        ),
        chat_help_prefix_code   = (
            "Spiegami cosa fa la funzione `{function}`."
        ),
        chat_help_prefix_selection = (
            "Spiegami cosa fanno queste righe."
        ),
        chat_help_prefix_wrong_component = "Componente {ref} ({type}): ",
        chat_correction_to_studio  = "Correggi in Studio",
        chat_correction_redirect   = (
            "Sembra che sia in realtà un {name}. Puoi correggerlo nello "
            "Studio — il tuo prompt sarà precompilato."
        ),
        chat_correction_studio_offer = (
            "Vuoi applicare una modifica al tuo codice? Puoi farlo nello "
            "Studio."
        ),
        chat_help_prefix_error  = (
            "Ho questo errore di compilazione, puoi aiutarmi a "
            "capirlo?"
        ),
        nudge_beginner_to_intermediate = "<b>Suggerimento</b>: In modalità <b>Intermedio</b> vedi il codice, puoi aggiungere o modificare una funzione — e anche modificarlo tu stesso.",
        nudge_intermediate_to_advanced = "<b>Suggerimento</b>: In modalità <b>Avanzata</b> il tuo codice si apre in 2 finestre — quello generato dall'IA e il tuo codice stabile, che l'IA non modifica mai. Ideale per provare idee senza rompere ciò che già funziona.",
        gen_modal_title           = "Cosa vuoi fare?",
        gen_modal_regenerate      = "Rigenera",
        gen_modal_regenerate_desc = "Ricominciare da questa descrizione",
        gen_modal_add             = "Aggiungi una funzione",
        gen_modal_add_desc        = "Mantieni l'esistente, aggiungi questo comportamento",
        gen_modal_correct         = "Modifica",
        gen_modal_correct_desc    = "Modifica una funzione esistente",
        gen_modal_target          = "Funzione/i da modificare:",
        gen_modal_target_all      = "Seleziona tutto",
        gen_modal_validate        = "Conferma",
        gen_modal_cancel          = "Annulla",
        modify_guidance_title     = "Modifica nello Studio",
        modify_guidance_body      = "Le funzioni non sono modificabili in modalità Principiante, passerai alla modalità Intermedio.\n\nPer applicare la modifica, clicca su « Genera » poi « Modifica ».",
        modify_guidance_ok        = "Ho capito",
        studio_err_parse_failed        = "Impossibile interpretare il codice generato. Riprova.",
        studio_inline_overwrite_title  = "Modifiche manuali",
        studio_inline_overwrite_body   = "Hai modificato il codice a mano. Questa azione rigenererà e sovrascriverà tali modifiche. Continuare?",
        studio_merge_features_title    = "Unione funzionalità",
        studio_merge_features_body     = "Le {n} funzionalità selezionate saranno unite in una sola. Continuare?",
        component_replace_dropdown          = "Sostituisci con:",
        component_replace_divergence_title  = "Codice ≠ schema",
        component_replace_divergence_message = "Il codice dice «{old}», lo schema mostrerà «{new}». Continuare?",
        component_replace_continue          = "Continua",
    ),
}

# Language names displayed in their own language
LANGUAGE_NAMES: dict[str, str] = {
    "fr": "Français",
    "en": "English",
    "es": "Español",
    "it": "Italiano",
}


class LanguageManager(QObject):
    """Emits a signal when the language changes. Instantiated once at the bottom."""

    changed = pyqtSignal(object)   # emits the new Strings

    def __init__(self):
        super().__init__(None)
        self._lang    = "fr"
        self._current = TRANSLATIONS["fr"]

    @property
    def current(self) -> Strings:
        return self._current

    @property
    def lang(self) -> str:
        return self._lang

    def set_language(self, lang_code: str):
        if lang_code == self._lang or lang_code not in TRANSLATIONS:
            return
        self._lang    = lang_code
        self._current = TRANSLATIONS[lang_code]
        self.changed.emit(self._current)


# ── Editor templates (intermediate/advanced mode) per language ───────────────
# Comments condensed to one line per block: we keep the pedagogical role
# but drastically reduce the vertical space between sections.
EDITOR_TEMPLATES: dict[str, str] = {
    "fr": """\
/* Librairies externes (#include) et variables globales partagées entre les fonctions. */

void setup() {
  /* Configuration initiale : broches, communication série, capteurs — tout ce qui doit être initialisé au démarrage. */
}

void loop() {
  /* Logique principale du programme, exécutée en boucle indéfiniment. */
}
""",
    "en": """\
/* External libraries (#include) and global variables shared between functions. */

void setup() {
  /* Initial setup: pins, serial communication, sensors — everything that must be initialised at startup. */
}

void loop() {
  /* Main program logic, executed repeatedly. */
}
""",
    "es": """\
/* Bibliotecas externas (#include) y variables globales compartidas entre funciones. */

void setup() {
  /* Configuración inicial: pines, comunicación serie, sensores — todo lo que debe inicializarse al arrancar. */
}

void loop() {
  /* Lógica principal del programa, ejecutada en bucle indefinidamente. */
}
""",
    "it": """\
/* Librerie esterne (#include) e variabili globali condivise tra le funzioni. */

void setup() {
  /* Configurazione iniziale: pin, comunicazione seriale, sensori — tutto ciò che deve essere inizializzato all'avvio. */
}

void loop() {
  /* Logica principale del programma, eseguita in loop indefinitamente. */
}
""",
}

# Old verbose versions: we keep them only so that
# is_known_template() can recognize the content of a project saved
# with the old template and replace it cleanly on a mode change.
#
# ⚠️ CE QUI EST ÉCRIT ICI NE SE CORRIGE PAS. `is_known_template` compare des
# chaînes EXACTES : ces textes sont la trace de ce que les versions passées
# ont réellement écrit dans les projets, pas de la prose à entretenir. Y
# appliquer une reformulation (ex. « bibliothèque » → « librairie », 2026-08-08)
# rendrait méconnaissables les projets déjà enregistrés — leur éditeur vide
# passerait pour du vrai code, donc bouton Schéma actif sur un sketch vide.
# Toute reformulation du gabarit COURANT s'ajoute ici, elle ne s'y substitue
# jamais.
_LEGACY_EDITOR_TEMPLATES: dict[str, str] = {
    "fr": """\
/*
 * C'est ici que sont incluses les bibliothèques externes (#include)
 * et que sont déclarées les variables globales partagées entre les fonctions.
 */

void setup() {
  /*
   * Cette fonction s'exécute une seule fois au démarrage de la carte.
   * C'est ici que sont configurées les broches, la communication série,
   * les capteurs et tout ce qui doit être initialisé avant le programme principal.
   */
}

void loop() {
  /*
   * Cette fonction s'exécute en boucle indéfiniment après setup().
   * C'est ici que se trouve la logique principale du programme.
   */
}
""",
    "en": """\
/*
 * This is where external libraries are included (#include)
 * and where global variables shared between functions are declared.
 */

void setup() {
  /*
   * This function runs once when the board starts up.
   * This is where pins, serial communication, sensors,
   * and anything that must be initialised before the main program are configured.
   */
}

void loop() {
  /*
   * This function runs repeatedly after setup() finishes.
   * This is where the main logic of the program lives.
   */
}
""",
    "es": """\
/*
 * Aquí es donde se incluyen las bibliotecas externas (#include)
 * y se declaran las variables globales compartidas entre las funciones.
 */

void setup() {
  /*
   * Esta función se ejecuta una sola vez al arrancar la placa.
   * Aquí es donde se configuran los pines, la comunicación serie,
   * los sensores y todo lo que deba inicializarse antes del programa principal.
   */
}

void loop() {
  /*
   * Esta función se ejecuta en bucle indefinidamente después de setup().
   * Aquí es donde se encuentra la lógica principal del programa.
   */
}
""",
    "it": """\
/*
 * Qui è dove si includono le librerie esterne (#include)
 * e si dichiarano le variabili globali condivise tra le funzioni.
 */

void setup() {
  /*
   * Questa funzione viene eseguita una sola volta all'avvio della scheda.
   * Qui è dove si configurano i pin, la comunicazione seriale,
   * i sensori e tutto ciò che deve essere inizializzato prima del programma principale.
   */
}

void loop() {
  /*
   * Questa funzione viene eseguita in loop indefinitamente dopo setup().
   * Qui è dove si trova la logica principale del programma.
   */
}
""",
}

# Language names for the instructions sent to the AI
AI_LANG_NAMES: dict[str, str] = {
    "fr": "French",
    "en": "English",
    "es": "Spanish",
    "it": "Italian",
}


# Product decision: same pedagogical comments in all modes.
# The starting template is therefore identical regardless of the mode (the mode
# is only a display layer). No per-mode variant.
def _lm_editor_template(self) -> str:
    return EDITOR_TEMPLATES.get(self._lang, EDITOR_TEMPLATES["fr"])


def _lm_ai_lang_name(self) -> str:
    return AI_LANG_NAMES.get(self._lang, "English")


# Gabarit courant AVANT le renommage « bibliothèque » → « librairie »
# (2026-08-08). Un projet enregistré entre-temps contient encore ce texte :
# sans cette entrée il cesserait d'être reconnu comme vide, et le bouton
# « Voir le schéma » — qui suit le CODE depuis la QA E1 — s'activerait sur un
# éditeur qui ne contient rien.
_PRE_2026_08_08_FR_TEMPLATE = """\
/* Bibliothèques externes (#include) et variables globales partagées entre les fonctions. */

void setup() {
  /* Configuration initiale : broches, communication série, capteurs — tout ce qui doit être initialisé au démarrage. */
}

void loop() {
  /* Logique principale du programme, exécutée en boucle indéfiniment. */
}
"""


def _lm_is_known_template(self, text: str) -> bool:
    return (
        text in EDITOR_TEMPLATES.values()
        or text in _LEGACY_EDITOR_TEMPLATES.values()
        or text == _PRE_2026_08_08_FR_TEMPLATE
    )


LanguageManager.editor_template = _lm_editor_template
LanguageManager.ai_lang_name = _lm_ai_lang_name
LanguageManager.is_known_template = _lm_is_known_template


# ── Additional strings (Projects) — injected via setattr to avoid ────────────
#    editing each Strings(...) above. As many keys as upcoming phases.
_EXTRA_STRINGS: dict[str, dict[str, str]] = {
    "fr": {
        "settings_privacy":               "Confidentialité",
        "settings_privacy_desc":          "Promptuino ne collecte aucune statistique et n'envoie rien sur Internet. Tes projets, tes prompts et ton code restent sur ta machine. Si l'application plante, un rapport est écrit dans ton dossier Promptuino — à toi seul de décider de le partager.",
        "tip_toggle_sidebar":             "Afficher ou masquer la navigation",
        "tip_toggle_chat":                "Afficher ou masquer l'assistant",
        "tip_card_functions":             "Voir les fonctionnalités du projet",
        "tip_refresh_ports":              "Rechercher à nouveau les ports",
        "btn_validate":                   "Valider",
        "btn_cancel":                     "Annuler",
        "btn_understood":                 "J'ai compris",
        "btn_yes":                        "Oui",
        "btn_no":                         "Non",
        "nav_projets":                 "Projets",
        "chip_swap_regen_title":       "Mettre le code à jour ?",
        "chip_swap_regen_body":        "Tu as choisi un <b>{new}</b>, mais le <b>code décrit encore un {old}</b>.<br><br>Régénérer le code de cette fonctionnalité avec {new} ? Le schéma va se fermer et la génération se lancer.",
        "chip_swap_regen_yes":         "Régénérer",
        "chip_swap_regen_no":          "Garder tel quel",
        "registry_lib_found":          "Composant {part} : librairie « {lib} » trouvée au registre Arduino et utilisée pour la génération.",
        "registry_lib_not_found":      "Composant « {part} » inconnu : code généré sans référence, le code risque de ne pas être fonctionnel. Joindre une documentation (.md/.txt) peut aider.",
        "registry_install_failed":     "Composant « {part} » : la librairie « {lib} » existe bien au registre Arduino, mais elle n'a pas pu être téléchargée. Vérifie ta connexion internet, puis relance la génération.",
        "registry_change_lib":         "Changer de librairie",
        "rag_guess_by_resemblance":    "Aucun composant reconnu dans ta demande — une bibliothèque a été proposée au modèle <b>par ressemblance</b>. Donne la référence exacte de ton composant (ex. « BMP280 ») pour un résultat sûr.",
        "lib_choice_title":            "Choisir la librairie",
        "lib_choice_body":             "Pour <b>{part}</b>, l'app utilise « <b>{lib}</b> ». Choisis celle qui correspond au matériel que tu as.",
        "lib_choice_search_placeholder": "Nom de la librairie…",
        "lib_choice_search_empty":     "Aucune bibliothèque ne correspond à « {q} ».",
        "lib_choice_search_unavailable": "Recherche indisponible : arduino-cli est absent. Les librairies déjà trouvées restent proposées.",
        "lib_choice_ok":               "Utiliser cette librairie",
        "lib_choice_cancel":           "Annuler",
        "lib_choice_let_app_decide":   "Laisser l'app décider",
        "lib_choice_let_app_decide_hint": "Efface ton choix ; l'app cherchera à nouveau à la prochaine génération.",
        "lib_choice_no_library":      "Aucune bibliothèque n’est nécessaire",
        "lib_choice_no_library_hint": "Ce composant se pilote directement, sans #include. L’app cessera d’en chercher une.",
        "lib_choice_loading":          "Chargement du catalogue Arduino…",
        "lib_choice_count":            "{n} bibliothèques trouvées",
        "lib_choice_count_one":        "1 bibliothèque trouvée",
        "lib_choice_count_capped":     "{total} bibliothèques correspondent — les {shown} premières sont affichées, précise ta recherche.",
        "lib_choice_badge_in_use":     "en usage",
        "lib_choice_badge_retired":    "abandonnée",
        "lib_choice_badge_incompatible": "incompatible avec ta carte",
        "lib_choice_meta_all_boards":  "Compatible toutes cartes",
        "lib_choice_meta_requires":    "nécessite {deps}",
        "registry_pref_not_found":     "Ta librairie « {pref} » pour {part} est introuvable au registre Arduino : « {lib} » a été utilisée à la place.",
        "lib_swap_regen_title":        "Mettre le code à jour ?",
        "lib_swap_regen_body":         "Tu as choisi la librairie <b>{new}</b>, mais le <b>code utilise encore {old}</b>.<br><br>Régénérer le code concerné ? Le schéma ne bouge pas : c'est la même puce, seules les instructions changent.",
        "lib_swap_regen_body_cleared": "Tu as effacé ta préférence, mais le <b>code utilise encore {old}</b>.<br><br>Régénérer le code de cette fonctionnalité pour laisser l'app choisir à nouveau ? Le schéma va se fermer et la génération se lancer.",
        "lib_swap_regen_yes":          "Régénérer",
        "lib_swap_regen_no":           "Garder tel quel",
        "lib_swap_unchecked":          "Librairie changée pour {part} : {new}. Impossible de vérifier si le code utilise encore l'ancienne librairie — pense à régénérer la fonctionnalité concernée si besoin.",
        "motor_mismatch_title":        "Code et schéma à harmoniser",
        "motor_mismatch_body":         "Ton code utilise un pattern moteur (<code>setMotor(...)</code>), mais tu n'as choisi aucun moteur pour le schéma.<br><br>Le câblage sera correct mais le <b>code reste celui d'un moteur</b>.<br><br>Pour les rendre cohérents, regénère ton code avec une description plus précise.",
        "projects_title":              "Mes projets",
        "projects_filter_all":         "Tous",
        "projects_new":                "Nouveau projet",
        "projects_new_dialog_title":   "Nouveau projet",
        "projects_new_dialog_prompt":  "Nom du projet :",
        "projects_new_type_label":     "Type de carte :",
        "projects_create":             "Créer",
        "projects_cancel":             "Annuler",
        "projects_empty":              "Aucun projet pour l'instant",
        "projects_empty_hint":         "Cliquez sur « Nouveau projet » pour commencer.",
        "projects_open":               "Ouvrir",
        "projects_open_folder":        "Ouvrir le dossier",
        "projects_last_modified":      "Modifié",
        "projects_board_unknown":      "Carte non définie",
        "projects_invalid_name":       "Nom invalide. Utilisez lettres, chiffres, tirets ou espaces.",
        "projects_name_exists":        "Un projet portant ce nom existe déjà.",
        "projects_actions_tooltip":    "Plus d'actions",
        "projects_rename":             "Renommer",
        "projects_duplicate":          "Dupliquer",
        "projects_delete":             "Supprimer",
        "projects_delete_confirm_title":  "Supprimer le projet",
        "projects_delete_confirm_msg":    "Supprimer définitivement le projet « {name} » ?\nCette action est irréversible.",
        "projects_rename_dialog_title":   "Renommer le projet",
        "projects_rename_prompt":         "Nouveau nom :",
        "projects_selection_one":         "1 projet sélectionné",
        "projects_selection_many":        "{n} projets sélectionnés",
        "projects_deselect_all":          "Tout désélectionner",
        "projects_delete_selection":      "Supprimer la sélection",
        "projects_delete_bulk_title":     "Supprimer les projets",
        "projects_delete_bulk_msg":       "Supprimer définitivement {n} projets ?\nCette action est irréversible.",
        "studio_comments_label":       "Commentaires code généré :",
        "studio_comments_none":        "Aucun",
        "studio_comments_minimal":     "Minimal",
        "studio_comments_standard":    "Standard",
        "studio_comments_detailed":    "Détaillé",
        "studio_serial_monitor_chk":   "Moniteur série",
        "studio_save":                 "Enregistrer",
        "studio_save_as":              "Enregistrer sous…",
        "studio_saved":                "Enregistré",
        "studio_untitled":             "Sans-titre",
        "studio_unsaved_title":        "Modifications non enregistrées",
        "studio_unsaved_msg":          "Voulez-vous enregistrer les modifications de « {name} » ?",
        "studio_unsaved_save":         "Enregistrer",
        "studio_unsaved_discard":      "Ignorer",
        "studio_unsaved_cancel":       "Annuler",
        "studio_functions_title":       "Fonctionnalités",
        "studio_functions_empty":       "Aucune fonctionnalité pour l'instant.",
        "studio_functions_empty_hint":  "Cliquez sur « Ajouter une fonctionnalité » pour commencer.",
        "studio_functions_collapse":    "Réduire le panneau",
        "studio_functions_expand":      "Afficher le panneau",
        "studio_ai_tools_title":        "Outils IA",
        "studio_ai_tools_label":        "Outils",
        "studio_action_regen":          "Régénérer",
        "studio_action_schema":         "Voir le schéma",
        "studio_lines_word":            "lignes",
        "studio_tools_panel_title":     "Outils",
        "studio_schema_title":          "Schéma",
        "studio_tool_explain_lines":    "Expliquer les lignes sélectionnées",
        "studio_tool_coming_soon":      "Cet outil sera bientôt disponible.",
        "studio_explain_title":         "Expliquer le code",
        "studio_explain_code_label":    "Code",
        "studio_explain_result_label":  "Explication",
        "studio_explain_btn":           "Expliquer",
        "studio_explain_close":         "Fermer",
        "studio_explain_loading":       "Analyse en cours…",
        "studio_explain_hint_select":   "Sélectionnez les lignes à expliquer puis cliquez sur « Expliquer ».",
        "studio_explain_no_backend":    "Aucun backend IA disponible.",
        "studio_tool_lint":             "Détecter les antipatterns",
        "studio_lint_title":            "Inspection du code",
        "studio_lint_result_label":     "Avertissements",
        "studio_lint_loading":          "Inspection en cours…",
        "studio_lint_rerun_btn":        "Relancer l'inspection",
        "studio_tool_add_comments":     "Ajouter des commentaires pédagogiques",
        "studio_addcmt_title":          "Ajouter des commentaires",
        "studio_addcmt_original":       "Code actuel",
        "studio_addcmt_commented":      "Code commenté",
        "studio_addcmt_loading":        "Génération en cours…",
        "studio_addcmt_apply":          "Appliquer",
        "studio_addcmt_rerun":          "Régénérer",
        "studio_addcmt_confirm_title":  "Remplacer le code",
        "studio_addcmt_confirm_msg":    "Le code actuel va être remplacé par la version commentée. Le surlignage par fonction sera perdu (les fonctions restent dans le panneau).\n\nContinuer ?",
        "studio_show_comments":         "Commentaires",
        "studio_addcmt_error":          "Échec de la génération des commentaires : {msg}",
        "studio_addcmt_loading":        "Génération de commentaires…",
        "studio_tool_repair":           "Analyser / Réparer le code",
        "studio_tool_format":           "Formater le code",
        "studio_format_brace_added":    "Une accolade fermante manquante a été ajoutée, et le code a été reformaté.",
        "studio_format_unbalanced":     "Déséquilibre d'accolades détecté, mais impossible de le localiser automatiquement (indentation insuffisante). Lance une compilation pour un diagnostic complet.",
        "studio_repair_error":          "Échec de l'analyse : {msg}",
        "studio_repair_dialog_title":   "Analyser / Réparer le code",
        "studio_repair_original_label": "Code original",
        "studio_repair_code_label":     "Code proposé (modifications surlignées)",
        "studio_repair_summary_label":  "Analyse",
        "studio_repair_apply":          "Appliquer",
        "studio_repair_no_summary":     "L'IA n'a pas fourni d'explication.",
        "studio_repairs_link":          "🔧 {n} correction(s) automatique(s) — voir le détail",
        "studio_repair_history_title":  "Corrections automatiques",
        "studio_tool_wiring_diagram":   "Schéma de câblage",
        "studio_bottom_collapse":       "Réduire le journal et le moniteur",
        "studio_bottom_expand":         "Afficher le journal et le moniteur",
        "studio_bottom_collapsed_title": "Journal et moniteur série",
        "studio_function_name_fmt":      "Fonctionnalité {n}",
        "studio_function_no_prompt":     "(pas de description)",
        "studio_function_err_no_markers":  "La réponse de l'IA ne contient pas les marqueurs de nouvelle fonctionnalité.",
        "studio_function_err_missing_fid": "Le marqueur {fid} est absent de la réponse de l'IA.",
        "studio_function_err_contract_broken": "Régénération refusée pour « {name} » : le contrat d'exports n'est plus respecté ({details}). Les autres fonctionnalités dépendent de ces variables — réessayez en précisant de conserver les mêmes noms.",
        "studio_function_delete_tip":    "Supprimer",
        "studio_function_regen_tip":     "Modifier / Régénérer",
        "studio_function_delete_title":  "Supprimer une fonctionnalité",
        "studio_function_delete_single": "Supprimer « {name} » ?\nLe code correspondant sera retiré de l'éditeur.",
        "studio_function_delete_cascade":"Supprimer « {name} » entraînera aussi la suppression de {n} fonctionnalité(s) qui en dépendent :\n\n{names}\n\nContinuer ?",
        "studio_function_rename_tip":    "Double-cliquez pour renommer",
        "studio_function_delete_confirm":"Supprimer",
        "studio_function_regen_title":   "Régénérer « {name} »",
        "studio_function_regen_prompt":  "Nouvelle description :",
        "studio_function_regen_confirm": "Régénérer",
        "studio_function_regenerating":  "Régénération en cours…",
        "studio_function_undo":          "Annuler",
        "studio_function_undo_tip":      "Annuler la dernière opération sur une fonctionnalité (Ctrl+Z)",
        "studio_functions_actions_tooltip": "Actions",
        "studio_functions_action_rename":   "Renommer",
        "studio_functions_action_merge":    "Fusionner…",
        "studio_functions_merge_confirm":   "Fusionner ({n})",
        "studio_functions_merge_cancel":    "Annuler",
        "studio_functions_merge_title":     "Fusionner les fonctionnalités",
        "studio_functions_merge_msg":       "Fusionner les {n} fonctionnalités sélectionnées en une seule ?\n\nL'identifiant et la couleur de la première sont conservés, les prompts sont concaténés, les exports et les lignes sont réunis.",
        "studio_repair_merge_ask_title":    "Fusionner les fonctionnalités ?",
        "studio_repair_merge_ask_msg":      "La réparation a absorbé le code des fonctionnalités suivantes dans « {target} » :\n\n{lost}\n\nVoulez-vous officialiser cette fusion (prompts concaténés, exports et historique regroupés) ? Si vous refusez, ces fonctionnalités resteront dans le panneau mais sans surlignage dans l'éditeur.",
        "studio_function_delete_warning":"Cette action retirera le code de la fonctionnalité de l'éditeur.",
        "studio_function_regen_placeholder": "Décris la nouvelle version de la fonctionnalité…",
        "menu_card":                   "Carte",
        "menu_view":                   "Affichage",
        "menu_help":                   "Aide",
        "mn_new_project":              "Nouveau projet",
        "mn_open_project":             "Ouvrir un projet",
        "mn_save":                     "Enregistrer",
        "mn_quit":                     "Quitter",
        "menu_edit":                   "Édition",
        "mn_undo":                     "Annuler",
        "mn_redo":                     "Rétablir",
        "mn_copy_code":                "Copier le code",
        "mn_clear_prompt":             "Effacer le prompt",
        "topbar_undo_tip":             "Annuler (Ctrl+Z)",
        "topbar_redo_tip":             "Rétablir (Ctrl+Y)",
        "feature_chips_delete_confirm": "Supprimer {n} fonctionnalité(s) ? Le code correspondant sera retiré de l'éditeur.",
        "feature_dropdown_label":      "Fonctionnalités",
        "feature_action_regen":        "Régénérer",
        "feature_action_delete":       "Supprimer",
        "studio_manual_feature_label": "Éditions manuelles",
        "ctx_menu_assign_feature":     "Attribuer à…",
        "feature_transfer_title":      "Transférer des fonctionnalités",
        "feature_transfer_apply":      "Appliquer",
        "feature_transfer_all":        "Tout transférer →",
        "feature_transfer_all_back":   "← Tout transférer",
        "feature_transfer_recap_title": "Récapitulatif",
        "feature_transfer_confirm":    "Confirmer",
        "feature_transfer_recap_transfers": "{n} transfert(s)",
        "feature_transfer_recap_deletes":   "{n} suppression(s)",
        "feature_transfer_recap_reorder":   "ordre modifié",
        "feature_transfer_dirty_warn": "{win} : le code a été retouché à la main, ces retouches seront perdues.",
        "feature_transfer_deleted_dep_warn": "{label} utilisera une variable supprimée",
        "feature_transfer_restore":    "Restaurer",
        "studio_reconstruct_title":    "Reconstruire depuis les fonctionnalités ?",
        "studio_reconstruct_msg":      "La réparation a échoué et le code est structurellement cassé. Reconstruire un code propre à partir de vos fonctionnalités ? Vos retouches manuelles seront perdues.",
        "studio_reconstruct_ok":       "Reconstruire",
        "studio_reconstruct_done":     "Code reconstruit depuis les fonctionnalités.",
        "studio_behavior_lint_title":  "Analyse comportementale",
        "studio_behavior_lint_none":   "Aucun piège statique détecté.",
        "studio_behavior_evidence_joined": "Sortie série jointe à la revue.",
        "studio_cascade_fixes_header": "**Corrections de compilation :**",
        "studio_cascade_fixes_generic": "- {n} correction(s) de compilation (voir le détail dans le journal).",
        "studio_cascade_line_removed": "- Ligne {n} : `{code}` retirée",
        "studio_cascade_line_added":   "- Ligne {n} : `{code}` ajoutée",
        "studio_cascade_line_changed": "- Ligne {n} : `{old}` → `{new}`",
        "feature_link_uses":           "Utilise {name} de {label}",
        "feature_link_provides":       "Fournit {name} à {label}",
        "studio_transfer_to_ai":       "◀ Transférer vers la fenêtre IA",
        "mn_goto_board":               "Sélectionner carte/port…",
        "mn_theme_toggle":             "Basculer thème clair/sombre",
        "mn_language":                 "Langue",
        "mn_toggle_sidebar":           "Masquer la navigation",
        "mn_fullscreen":               "Plein écran",
        "mn_open_workspace":           "Ouvrir le dossier des projets",
        "mn_about":                    "À propos",
        "mn_about_msg":                "Génère du code Arduino à partir d'une description en langage naturel — un outil éducatif open source pour débuter en programmation embarquée.",
        "about_developer":             "Développeur",
        "about_credits_title":         "Logiciels et ressources libres",
        "about_credits_intro":         "Promptuino s'appuie sur ces projets open source :",
        "about_source":                "Code source",
        "about_support":               "Soutenir le projet",
        # « Coulisses du prompt » (#42). Anciennement « Mode débug — afficher le
        # prompt IA », dans le menu Aide : ce n'est pas un outil de débogage,
        # c'est un aperçu pédagogique de ce que l'app fabrique à partir de ce
        # que l'utilisateur écrit. Le mot « débug » le faisait passer pour une
        # rustine réservée aux développeurs.
        "prompt_too_long":             "Ton projet est devenu grand : la demande envoyée au modèle occupe {percent} % de ce qu'il peut lire ({tokens} sur {window}). Il risque d'oublier le début du code et de réécrire ce qui existe déjà. Génère fonctionnalité par fonctionnalité, ou passe sur un modèle en ligne.",
        "crash_recovered":             "Une erreur inattendue a interrompu l'opération en cours. L'application continue de fonctionner — tu peux réessayer. Le détail a été enregistré.",
        "settings_backstage":          "Coulisses du prompt",
        "backstage_enable":            "Voir le prompt avant de l'envoyer",
        "backstage_desc":              "Avant chaque génération, une fenêtre montre ce que l'app envoie réellement à l'IA : les règles qu'elle ajoute d'elle-même, et ton message. Tu peux modifier ton message puis envoyer, ou annuler.",
        "backstage_title":             "Coulisses du prompt",
        "backstage_system":            "Ce que l'app ajoute d'elle-même (non modifiable)",
        "backstage_user":              "Ton message (modifiable avant l'envoi)",
        "backstage_chars":             "{n} caractères",
        "backstage_send":              "Envoyer",
        "backstage_edited":            "Prompt modifié à la main pour cette génération : le bouton ↻ repartira du projet, pas de ce texte.",
        "nav_bibliotheque":               "Librairies",
        "library_title":                  "Librairies",
        "library_search_placeholder":     "Rechercher une librairie à installer…",
        "library_installed_section":      "Librairies installées",
        "library_installed_count":        "{n} installée(s)",
        "library_installed_empty":        "Aucune librairie installée pour {platform}.",
        "library_installed_empty_hint":   "Tapez le nom d'une librairie ci-dessus pour en installer une.",
        "library_search_section":         "Résultats de recherche",
        "library_search_no_results":      "Aucune librairie trouvée pour « {query} ».",
        "library_searching":              "Recherche en cours…",
        "library_loading":                "Chargement…",
        "library_install":                "Installer",
        "library_installing":             "Installation…",
        "library_installed_badge":        "Installée",
        "library_uninstall":              "Supprimer",
        "library_uninstalling":           "Suppression…",
        "library_delete_confirm_title":   "Supprimer la librairie",
        "library_delete_confirm_msg":     "Supprimer définitivement « {name} » ?\nLe dossier sera effacé du disque.",
        "library_install_error_title":    "Échec de l'installation",
        "library_install_error_msg":      "Impossible d'installer « {name} » :\n{error}",
        "library_uninstall_error_title":  "Échec de la suppression",
        "library_uninstall_error_msg":    "Impossible de supprimer « {name} » :\n{error}",
        "library_no_cli":                 "arduino-cli est introuvable — installez-le et redémarrez l'application.",
        "library_platform_label":         "Plateforme :",
        "library_platform_arduino":       "Arduino",
        "library_platform_esp32":         "ESP32",
        "board_coming_soon":              "Bientôt disponible",
        "library_by":                     "par {author}",
        "library_version_prefix":         "v",
        "library_open_folder":            "Ouvrir le dossier",
        "library_more_actions":           "Plus d'actions",
        "ia_err_auth":         "Clé API invalide ou absente pour ce fournisseur.",
        "ia_err_notfound":     "Modèle ou URL introuvable — vérifie le modèle et l'URL de base.",
        "ia_err_quota":        "Quota ou débit dépassé — réessaie plus tard.",
        "ia_err_provider":     "Erreur côté fournisseur — réessaie plus tard.",
        "ia_err_network":      "Fournisseur injoignable — vérifie ta connexion et l'URL de base.",
        "ia_err_bad_response": "Réponse illisible du fournisseur.",
        "ia_cloud_provider_title":    "Cloud (clé perso)",
        "ia_cloud_provider_subtitle": "Utilise ta propre clé API chez un fournisseur compatible OpenAI.",
        "ia_provider_label":   "Fournisseur",
        "ia_model_label":      "Modèle",
        "ia_model_placeholder": "Laisser vide pour le modèle par défaut",
        "ia_base_url_label":   "URL de base",
        "ia_get_key_link":     "Obtenir une clé",
        "ia_model_disclaimer": "Certains modèles offrent un palier d'API gratuit — vérifie sur le site du fournisseur.",
        "ia_models_loading":       "Chargement des modèles…",
        "ia_models_none":          "Aucun modèle récupéré — saisis-le manuellement.",
        "ia_models_unsupported":   "Ce fournisseur n'expose pas la liste — saisis le modèle à la main.",
        # ── Components tab ──
        "nav_composants":                  "Composants",
        "components_search_placeholder":   "Rechercher un composant…",
        "components_filter_all":           "Tous",
        "components_filter_declared":      "Perso",
        "components_filter_with_library":  "Avec librairie",
        "components_filter_drawable":      "Dessinables",
        "components_declare_button":       "Créer un composant",
        "components_lib_unknown":          "lib à déterminer",
        "components_wiring_unknown":       "dessin générique",
        "components_wiring_none":          "rien à brancher",
        "components_library_none":         "aucune librairie à installer",
        "components_custom_badge_tip":     "Composant que tu as décrit toi-même",
        "components_adopt_tip":            "Librairie devinée par l'app — clique pour la corriger et décrire ce composant",
        "components_empty":                "Aucun composant ne correspond.",
        "components_pin_count":            "{n} broches",
        "components_change_lib":           "Changer de librairie",
        # ── Picker de la modale d'ambiguite ──
        # Les compteurs sont formules « libellé : {n} » plutôt que « {n}
        # composants » : le picker affiche régulièrement UN seul résultat
        # (« bmp180 ») et « 1 composants » serait faux dans les quatre
        # langues. Une clé singulière de plus par compteur (le motif de
        # `lib_choice_count_one`) coûterait huit clés pour un problème que la
        # formulation supprime.
        "picker_search_placeholder":       "Chercher un composant…",
        "picker_count_category":           "Composants proposés pour cette broche : {n}",
        "picker_count_all":                "Recherche dans toute la bibliothèque : {n}",
        "picker_count_capped":             "{total} composants correspondent — les {shown} premiers sont affichés, précise ta recherche.",
        "picker_group_requalify":          "— ou requalifier en —",
        "picker_group_yours":              "— tes composants —",
        "registry_module_lib_found":      "Module {alias} : reconnu comme {part}, librairie « {lib} » trouvée au registre Arduino et utilisée pour la génération.",
        "registry_module_lib_not_found":  "Module {alias} : reconnu comme {part}, mais aucune librairie trouvée au registre Arduino. Le code risque de ne pas être fonctionnel. Joindre une documentation (.md/.txt) peut aider.",
        "registry_module_install_failed": "Module {alias} : reconnu comme {part}, la librairie « {lib} » existe bien au registre Arduino, mais elle n'a pas pu être téléchargée. Vérifie ta connexion internet, puis relance la génération.",
        "registry_module_lib_unavailable": "Module {alias} : reconnu comme {part}, mais le registre Arduino n'a pas pu être interrogé (aucune carte sélectionnée, ou arduino-cli indisponible). Sélectionne ta carte, puis relance la génération.",
    },
    "en": {
        "settings_privacy":               "Privacy",
        "settings_privacy_desc":          "Promptuino collects no statistics and sends nothing over the Internet. Your projects, prompts and code stay on your machine. If the application crashes, a report is written to your Promptuino folder — sharing it is entirely up to you.",
        "tip_toggle_sidebar":             "Show or hide the navigation",
        "tip_toggle_chat":                "Show or hide the assistant",
        "tip_card_functions":             "See the project's features",
        "tip_refresh_ports":              "Scan for ports again",
        "btn_validate":                   "Confirm",
        "btn_cancel":                     "Cancel",
        "btn_understood":                 "Got it",
        "btn_yes":                        "Yes",
        "btn_no":                         "No",
        "nav_projets":                 "Projects",
        "chip_swap_regen_title":       "Update the code?",
        "chip_swap_regen_body":        "You picked a <b>{new}</b>, but the <b>code still describes a {old}</b>.<br><br>Regenerate this feature's code with the {new}? The diagram will close and generation will start.",
        "chip_swap_regen_yes":         "Regenerate",
        "chip_swap_regen_no":          "Keep as is",
        "registry_lib_found":          "Component {part}: library “{lib}” found in the Arduino registry and used for generation.",
        "registry_lib_not_found":      "Component “{part}” unknown: code generated without a reference, it may well not work. Attaching a documentation file (.md/.txt) may help.",
        "registry_install_failed":     "Component “{part}”: the “{lib}” library does exist in the Arduino registry, but it could not be downloaded. Check your internet connection, then generate again.",
        "registry_change_lib":         "Change library",
        "rag_guess_by_resemblance":    "No component recognised in your request — a library was offered to the model <b>by resemblance</b>. Give your component's exact reference (e.g. “BMP280”) for a reliable result.",
        "lib_choice_title":            "Choose the library",
        "lib_choice_body":             "For <b>{part}</b>, the app uses “<b>{lib}</b>”. Pick the one matching the hardware you own.",
        "lib_choice_search_placeholder": "Library name…",
        "lib_choice_search_empty":     "No library matches “{q}”.",
        "lib_choice_search_unavailable": "Search unavailable: arduino-cli is missing. The libraries already found are still offered.",
        "lib_choice_ok":               "Use this library",
        "lib_choice_cancel":           "Cancel",
        "lib_choice_let_app_decide":   "Let the app decide",
        "lib_choice_let_app_decide_hint": "Clears your choice; the app will search again at the next generation.",
        "lib_choice_no_library":      "No library is needed",
        "lib_choice_no_library_hint": "This component is driven directly, with no #include. The app will stop searching for one.",
        "lib_choice_loading":          "Loading the Arduino catalogue…",
        "lib_choice_count":            "{n} libraries found",
        "lib_choice_count_one":        "1 library found",
        "lib_choice_count_capped":     "{total} libraries match — the first {shown} are shown, narrow your search.",
        "lib_choice_badge_in_use":     "in use",
        "lib_choice_badge_retired":    "retired",
        "lib_choice_badge_incompatible": "not compatible with your board",
        "lib_choice_meta_all_boards":  "Works on every board",
        "lib_choice_meta_requires":    "requires {deps}",
        "registry_pref_not_found":     "Your library “{pref}” for {part} is not in the Arduino registry: “{lib}” was used instead.",
        "lib_swap_regen_title":        "Update the code?",
        "lib_swap_regen_body":         "You picked the <b>{new}</b> library, but the <b>code still uses {old}</b>.<br><br>Regenerate the affected code? The diagram does not move: same chip, only the instructions change.",
        "lib_swap_regen_body_cleared": "You cleared your choice, but the <b>code still uses {old}</b>.<br><br>Regenerate this feature's code so the app can search again? The diagram will close and generation will start.",
        "lib_swap_regen_yes":          "Regenerate",
        "lib_swap_regen_no":           "Keep as is",
        "lib_swap_unchecked":          "Library changed for {part}: now {new}. Could not check whether the existing code still uses the old one — consider regenerating the affected feature manually.",
        "motor_mismatch_title":        "Code and schematic to reconcile",
        "motor_mismatch_body":         "Your code uses a motor pattern (<code>setMotor(...)</code>), but you didn't pick any motor for the schematic.<br><br>The wiring will be correct, but the <b>code still drives a motor</b>.<br><br>To make them consistent, regenerate your code with a more precise description.",
        "projects_title":              "My projects",
        "projects_filter_all":         "All",
        "projects_new":                "New project",
        "projects_new_dialog_title":   "New project",
        "projects_new_dialog_prompt":  "Project name:",
        "projects_new_type_label":     "Board type:",
        "projects_create":             "Create",
        "projects_cancel":             "Cancel",
        "projects_empty":              "No projects yet",
        "projects_empty_hint":         "Click \"New project\" to get started.",
        "projects_open":               "Open",
        "projects_open_folder":        "Open folder",
        "projects_last_modified":      "Modified",
        "projects_board_unknown":      "Board not set",
        "projects_invalid_name":       "Invalid name. Use letters, digits, dashes or spaces.",
        "projects_name_exists":        "A project with that name already exists.",
        "projects_actions_tooltip":    "More actions",
        "projects_rename":             "Rename",
        "projects_duplicate":          "Duplicate",
        "projects_delete":             "Delete",
        "projects_delete_confirm_title":  "Delete project",
        "projects_delete_confirm_msg":    "Permanently delete project \"{name}\"?\nThis cannot be undone.",
        "projects_rename_dialog_title":   "Rename project",
        "projects_rename_prompt":         "New name:",
        "projects_selection_one":         "1 project selected",
        "projects_selection_many":        "{n} projects selected",
        "projects_deselect_all":          "Clear selection",
        "projects_delete_selection":      "Delete selection",
        "projects_delete_bulk_title":     "Delete projects",
        "projects_delete_bulk_msg":       "Permanently delete {n} projects?\nThis cannot be undone.",
        "studio_comments_label":       "Generated code comments:",
        "studio_comments_none":        "None",
        "studio_comments_minimal":     "Minimal",
        "studio_comments_standard":    "Standard",
        "studio_comments_detailed":    "Detailed",
        "studio_serial_monitor_chk":   "Serial monitor",
        "studio_save":                 "Save",
        "studio_save_as":              "Save as…",
        "studio_saved":                "Saved",
        "studio_untitled":             "Untitled",
        "studio_unsaved_title":        "Unsaved changes",
        "studio_unsaved_msg":          "Save changes to \"{name}\"?",
        "studio_unsaved_save":         "Save",
        "studio_unsaved_discard":      "Discard",
        "studio_unsaved_cancel":       "Cancel",
        "studio_functions_title":       "Features",
        "studio_functions_empty":       "No features yet.",
        "studio_functions_empty_hint":  "Click \"Add a feature\" to get started.",
        "studio_functions_collapse":    "Collapse panel",
        "studio_functions_expand":      "Expand panel",
        "studio_ai_tools_title":        "AI tools",
        "studio_ai_tools_label":        "Tools",
        "studio_action_regen":          "Regenerate",
        "studio_action_schema":         "View schematic",
        "studio_lines_word":            "lines",
        "studio_tools_panel_title":     "Tools",
        "studio_schema_title":          "Schematic",
        "studio_tool_explain_lines":    "Explain selected lines",
        "studio_tool_coming_soon":      "This tool will be available soon.",
        "studio_explain_title":         "Explain the code",
        "studio_explain_code_label":    "Code",
        "studio_explain_result_label":  "Explanation",
        "studio_explain_btn":           "Explain",
        "studio_explain_close":         "Close",
        "studio_explain_loading":       "Analysing…",
        "studio_explain_hint_select":   "Select the lines to explain, then click \"Explain\".",
        "studio_explain_no_backend":    "No AI backend available.",
        "studio_tool_lint":             "Detect antipatterns",
        "studio_lint_title":            "Code audit",
        "studio_lint_result_label":     "Warnings",
        "studio_lint_loading":          "Auditing…",
        "studio_lint_rerun_btn":        "Re-run audit",
        "studio_tool_add_comments":     "Add pedagogical comments",
        "studio_addcmt_title":          "Add comments",
        "studio_addcmt_original":       "Current code",
        "studio_addcmt_commented":      "Commented code",
        "studio_addcmt_loading":        "Generating…",
        "studio_addcmt_apply":          "Apply",
        "studio_addcmt_rerun":          "Regenerate",
        "studio_addcmt_confirm_title":  "Replace code",
        "studio_addcmt_confirm_msg":    "The current code will be replaced by the commented version. Function highlights will be lost (functions remain in the panel).\n\nContinue?",
        "studio_show_comments":         "Comments",
        "studio_addcmt_error":          "Failed to generate comments: {msg}",
        "studio_addcmt_loading":        "Generating comments…",
        "studio_tool_repair":           "Analyze / Repair the code",
        "studio_tool_format":           "Format the code",
        "studio_format_brace_added":    "A missing closing brace was added, and the code was reformatted.",
        "studio_format_unbalanced":     "Brace imbalance detected, but it could not be located automatically (not enough indentation). Run a compile for a full diagnosis.",
        "studio_repair_error":          "Analysis failed: {msg}",
        "studio_repair_dialog_title":   "Analyze / Repair the code",
        "studio_repair_original_label": "Original code",
        "studio_repair_code_label":     "Proposed code (changed lines highlighted)",
        "studio_repair_summary_label":  "Analysis",
        "studio_repair_apply":          "Apply",
        "studio_repair_no_summary":     "The AI didn't provide an explanation.",
        "studio_repairs_link":          "🔧 {n} automatic fix(es) — see details",
        "studio_repair_history_title":  "Automatic fixes",
        "studio_tool_wiring_diagram":   "Wiring diagram",
        "studio_bottom_collapse":       "Collapse log and monitor",
        "studio_bottom_expand":         "Expand log and monitor",
        "studio_bottom_collapsed_title": "Log and serial monitor",
        "studio_function_name_fmt":      "Feature {n}",
        "studio_function_no_prompt":     "(no description)",
        "studio_function_err_no_markers":  "The AI response contains no new-feature markers.",
        "studio_function_err_missing_fid": "Marker {fid} is missing from the AI response.",
        "studio_function_err_contract_broken": "Regeneration rejected for \"{name}\": the exports contract is broken ({details}). Other features depend on these variables — try again asking to keep the same names.",
        "studio_function_delete_tip":    "Delete",
        "studio_function_regen_tip":     "Edit / Regenerate",
        "studio_function_delete_title":  "Delete a feature",
        "studio_function_delete_single": "Delete \"{name}\"?\nIts code will be removed from the editor.",
        "studio_function_delete_cascade":"Deleting \"{name}\" will also delete {n} feature(s) that depend on it:\n\n{names}\n\nContinue?",
        "studio_function_rename_tip":    "Double-click to rename",
        "studio_function_delete_confirm":"Delete",
        "studio_function_regen_title":   "Regenerate \"{name}\"",
        "studio_function_regen_prompt":  "New description:",
        "studio_function_regen_confirm": "Regenerate",
        "studio_function_regenerating":  "Regenerating…",
        "studio_function_undo":          "Undo",
        "studio_function_undo_tip":      "Undo the last feature operation (Ctrl+Z)",
        "studio_functions_actions_tooltip": "Actions",
        "studio_functions_action_rename":   "Rename",
        "studio_functions_action_merge":    "Merge…",
        "studio_functions_merge_confirm":   "Merge ({n})",
        "studio_functions_merge_cancel":    "Cancel",
        "studio_functions_merge_title":     "Merge features",
        "studio_functions_merge_msg":       "Merge the {n} selected features into a single one?\n\nId and colour of the first are kept, prompts are concatenated, exports and lines are unified.",
        "studio_repair_merge_ask_title":    "Merge features?",
        "studio_repair_merge_ask_msg":      "The repair absorbed the code of these features into \"{target}\":\n\n{lost}\n\nFormalise the merge (prompts concatenated, exports and history unified)? If you decline, these features remain in the panel but without editor highlighting.",
        "studio_function_delete_warning":"This will remove the feature's code from the editor.",
        "studio_function_regen_placeholder": "Describe the new version of the feature…",
        "menu_card":                   "Board",
        "menu_view":                   "View",
        "menu_help":                   "Help",
        "mn_new_project":              "New project",
        "mn_open_project":             "Open a project",
        "mn_save":                     "Save",
        "mn_quit":                     "Quit",
        "menu_edit":                   "Edit",
        "mn_undo":                     "Undo",
        "mn_redo":                     "Redo",
        "mn_copy_code":                "Copy code",
        "mn_clear_prompt":             "Clear prompt",
        "topbar_undo_tip":             "Undo (Ctrl+Z)",
        "topbar_redo_tip":             "Redo (Ctrl+Y)",
        "feature_chips_delete_confirm": "Delete {n} feature(s)? The corresponding code will be removed from the editor.",
        "feature_dropdown_label":      "Features",
        "feature_action_regen":        "Regenerate",
        "feature_action_delete":       "Delete",
        "studio_manual_feature_label": "Manual edits",
        "ctx_menu_assign_feature":     "Assign to…",
        "feature_transfer_title":      "Transfer features",
        "feature_transfer_apply":      "Apply",
        "feature_transfer_all":        "Transfer all →",
        "feature_transfer_all_back":   "← Transfer all",
        "feature_transfer_recap_title": "Summary",
        "feature_transfer_confirm":    "Confirm",
        "feature_transfer_recap_transfers": "{n} transfer(s)",
        "feature_transfer_recap_deletes":   "{n} deletion(s)",
        "feature_transfer_recap_reorder":   "order changed",
        "feature_transfer_dirty_warn": "{win}: the code was edited by hand, those edits will be lost.",
        "feature_transfer_deleted_dep_warn": "{label} will use a deleted variable",
        "feature_transfer_restore":    "Restore",
        "studio_reconstruct_title":    "Rebuild from features?",
        "studio_reconstruct_msg":      "The repair failed and the code is structurally broken. Rebuild clean code from your features? Your manual edits will be lost.",
        "studio_reconstruct_ok":       "Rebuild",
        "studio_reconstruct_done":     "Code rebuilt from features.",
        "studio_behavior_lint_title":  "Behavioral check",
        "studio_behavior_lint_none":   "No static pitfall detected.",
        "studio_behavior_evidence_joined": "Serial output attached to the review.",
        "studio_cascade_fixes_header": "**Compile fixes:**",
        "studio_cascade_fixes_generic": "- {n} compile fix(es) (see the details in the journal).",
        "studio_cascade_line_removed": "- Line {n}: `{code}` removed",
        "studio_cascade_line_added":   "- Line {n}: `{code}` added",
        "studio_cascade_line_changed": "- Line {n}: `{old}` → `{new}`",
        "feature_link_uses":           "Uses {name} from {label}",
        "feature_link_provides":       "Provides {name} to {label}",
        "studio_transfer_to_ai":       "◀ Transfer to the AI window",
        "mn_goto_board":               "Select board/port…",
        "mn_theme_toggle":             "Toggle light/dark theme",
        "mn_language":                 "Language",
        "mn_toggle_sidebar":           "Hide navigation",
        "mn_fullscreen":               "Full screen",
        "mn_open_workspace":           "Open projects folder",
        "mn_about":                    "About",
        "mn_about_msg":                "Generates Arduino code from a plain-language description — an open-source educational tool to get started with embedded programming.",
        "about_developer":             "Developer",
        "about_credits_title":         "Open-source software & assets",
        "about_credits_intro":         "Promptuino is built on these open-source projects:",
        "about_source":                "Source code",
        "about_support":               "Support the project",
        "prompt_too_long":             "Your project has grown: the request sent to the model takes up {percent}% of what it can read ({tokens} of {window}). It may forget the start of your code and rewrite what is already there. Generate one feature at a time, or switch to an online model.",
        "crash_recovered":             "An unexpected error interrupted the current operation. The application is still running — you can try again. The details have been saved.",
        "settings_backstage":          "Behind the prompt",
        "backstage_enable":            "Show the prompt before sending it",
        "backstage_desc":              "Before each generation, a window shows what the app really sends to the AI: the rules it adds on its own, and your message. You can edit your message and send, or cancel.",
        "backstage_title":             "Behind the prompt",
        "backstage_system":            "What the app adds on its own (read-only)",
        "backstage_user":              "Your message (editable before sending)",
        "backstage_chars":             "{n} characters",
        "backstage_send":              "Send",
        "backstage_edited":            "Prompt edited by hand for this generation: the ↻ button will start from the project, not from this text.",
        "nav_bibliotheque":               "Libraries",
        "library_title":                  "Libraries",
        "library_search_placeholder":     "Search for a library to install…",
        "library_installed_section":      "Installed libraries",
        "library_installed_count":        "{n} installed",
        "library_installed_empty":        "No libraries installed for {platform}.",
        "library_installed_empty_hint":   "Type a library name above to install one.",
        "library_search_section":         "Search results",
        "library_search_no_results":      "No library found for \u201c{query}\u201d.",
        "library_searching":              "Searching…",
        "library_loading":                "Loading…",
        "library_install":                "Install",
        "library_installing":             "Installing…",
        "library_installed_badge":        "Installed",
        "library_uninstall":              "Remove",
        "library_uninstalling":           "Removing…",
        "library_delete_confirm_title":   "Remove library",
        "library_delete_confirm_msg":     "Permanently remove \u201c{name}\u201d?\nThe folder will be deleted from disk.",
        "library_install_error_title":    "Install failed",
        "library_install_error_msg":      "Could not install \u201c{name}\u201d:\n{error}",
        "library_uninstall_error_title":  "Remove failed",
        "library_uninstall_error_msg":    "Could not remove \u201c{name}\u201d:\n{error}",
        "library_no_cli":                 "arduino-cli not found — install it and restart the application.",
        "library_platform_label":         "Platform:",
        "library_platform_arduino":       "Arduino",
        "library_platform_esp32":         "ESP32",
        "board_coming_soon":              "Coming soon",
        "library_by":                     "by {author}",
        "library_version_prefix":         "v",
        "library_open_folder":            "Open folder",
        "library_more_actions":           "More actions",
        "ia_err_auth":         "Invalid or missing API key for this provider.",
        "ia_err_notfound":     "Model or URL not found — check the model and base URL.",
        "ia_err_quota":        "Quota or rate limit exceeded — try again later.",
        "ia_err_provider":     "Provider error — try again later.",
        "ia_err_network":      "Provider unreachable — check your connection and the base URL.",
        "ia_err_bad_response": "Unreadable response from the provider.",
        "ia_cloud_provider_title":    "Cloud (your key)",
        "ia_cloud_provider_subtitle": "Use your own API key with an OpenAI-compatible provider.",
        "ia_provider_label":   "Provider",
        "ia_model_label":      "Model",
        "ia_model_placeholder": "Leave empty for the default model",
        "ia_base_url_label":   "Base URL",
        "ia_get_key_link":     "Get a key",
        "ia_model_disclaimer": "Some models offer a free API tier — check the provider's website.",
        "ia_models_loading":       "Loading models…",
        "ia_models_none":          "No models fetched — type it manually.",
        "ia_models_unsupported":   "This provider doesn't expose a model list — type the model manually.",
        # ── Components tab ──
        "nav_composants":                  "Components",
        "components_search_placeholder":   "Search a component…",
        "components_filter_all":           "All",
        "components_filter_declared":      "Custom",
        "components_filter_with_library":  "With a library",
        "components_filter_drawable":      "Drawable",
        "components_declare_button":       "Create a component",
        "components_lib_unknown":          "library to determine",
        "components_wiring_unknown":       "generic drawing",
        "components_wiring_none":          "nothing to wire",
        "components_library_none":         "no library to install",
        "components_custom_badge_tip":     "A component you described yourself",
        "components_adopt_tip":            "Library guessed by the app — click to correct it and describe this component",
        "components_empty":                "No component matches.",
        "components_pin_count":            "{n} pins",
        "components_change_lib":           "Change library",
        # ── Ambiguity modal picker ──
        "picker_search_placeholder":       "Search a component…",
        "picker_count_category":           "Components offered for this pin: {n}",
        "picker_count_all":                "Searching the whole library: {n}",
        "picker_count_capped":             "{total} components match — the first {shown} are shown, refine your search.",
        "picker_group_requalify":          "— or make it a —",
        "picker_group_yours":              "— your components —",
        "registry_module_lib_found":      "Module {alias}: recognised as {part}, library “{lib}” found in the Arduino registry and used for generation.",
        "registry_module_lib_not_found":  "Module {alias}: recognised as {part}, but no library was found in the Arduino registry. The code may well not work. Attaching a documentation file (.md/.txt) may help.",
        "registry_module_install_failed": "Module {alias}: recognised as {part}, the “{lib}” library does exist in the Arduino registry, but it could not be downloaded. Check your internet connection, then generate again.",
        "registry_module_lib_unavailable": "Module {alias}: recognised as {part}, but the Arduino registry could not be searched (no board selected, or arduino-cli unavailable). Select your board, then generate again.",
    },
    "es": {
        "settings_privacy":               "Privacidad",
        "settings_privacy_desc":          "Promptuino no recopila ninguna estadística y no envía nada por Internet. Tus proyectos, tus prompts y tu código se quedan en tu máquina. Si la aplicación falla, se escribe un informe en tu carpeta Promptuino — compartirlo depende solo de ti.",
        "tip_toggle_sidebar":             "Mostrar u ocultar la navegación",
        "tip_toggle_chat":                "Mostrar u ocultar el asistente",
        "tip_card_functions":             "Ver las funcionalidades del proyecto",
        "tip_refresh_ports":              "Buscar los puertos de nuevo",
        "btn_validate":                   "Validar",
        "btn_cancel":                     "Cancelar",
        "btn_understood":                 "Entendido",
        "btn_yes":                        "Sí",
        "btn_no":                         "No",
        "nav_projets":                 "Proyectos",
        "chip_swap_regen_title":       "¿Actualizar el código?",
        "chip_swap_regen_body":        "Has elegido un <b>{new}</b>, pero el <b>código aún describe un {old}</b>.<br><br>¿Regenerar el código de esta funcionalidad con el {new}? El esquema se cerrará y la generación comenzará.",
        "chip_swap_regen_yes":         "Regenerar",
        "chip_swap_regen_no":          "Dejar como está",
        "registry_lib_found":          "Componente {part}: librería «{lib}» encontrada en el registro de Arduino y usada para la generación.",
        "registry_lib_not_found":      "Componente «{part}» desconocido: código generado sin referencia, puede que no funcione. Adjuntar una documentación (.md/.txt) puede ayudar.",
        "registry_install_failed":     "Componente «{part}»: la librería «{lib}» sí existe en el registro de Arduino, pero no se pudo descargar. Comprueba tu conexión a internet y vuelve a generar.",
        "registry_change_lib":         "Cambiar de librería",
        "rag_guess_by_resemblance":    "Ningún componente reconocido en tu petición — se propuso una biblioteca al modelo <b>por parecido</b>. Indica la referencia exacta de tu componente (p. ej. «BMP280») para un resultado fiable.",
        "lib_choice_title":            "Elegir la librería",
        "lib_choice_body":             "Para <b>{part}</b>, la app usa «<b>{lib}</b>». Elige la que corresponde al material que tienes.",
        "lib_choice_search_placeholder": "Nombre de la librería…",
        "lib_choice_search_empty":     "Ninguna biblioteca coincide con «{q}».",
        "lib_choice_search_unavailable": "Búsqueda no disponible: falta arduino-cli. Las librerías ya encontradas siguen ofreciéndose.",
        "lib_choice_ok":               "Usar esta librería",
        "lib_choice_cancel":           "Cancelar",
        "lib_choice_let_app_decide":   "Dejar que la app decida",
        "lib_choice_let_app_decide_hint": "Borra tu elección; la app buscará de nuevo en la próxima generación.",
        "lib_choice_no_library":      "No hace falta ninguna biblioteca",
        "lib_choice_no_library_hint": "Este componente se controla directamente, sin #include. La app dejará de buscar una.",
        "lib_choice_loading":          "Cargando el catálogo de Arduino…",
        "lib_choice_count":            "{n} bibliotecas encontradas",
        "lib_choice_count_one":        "1 biblioteca encontrada",
        "lib_choice_count_capped":     "{total} bibliotecas coinciden — se muestran las {shown} primeras, precisa tu búsqueda.",
        "lib_choice_badge_in_use":     "en uso",
        "lib_choice_badge_retired":    "retirada",
        "lib_choice_badge_incompatible": "incompatible con tu placa",
        "lib_choice_meta_all_boards":  "Compatible con todas las placas",
        "lib_choice_meta_requires":    "necesita {deps}",
        "registry_pref_not_found":     "Tu librería «{pref}» para {part} no está en el registro de Arduino: se usó «{lib}» en su lugar.",
        "lib_swap_regen_title":        "¿Actualizar el código?",
        "lib_swap_regen_body":         "Elegiste la librería <b>{new}</b>, pero el <b>código todavía usa {old}</b>.<br><br>¿Regenerar el código afectado? El esquema no cambia: es el mismo chip, solo cambian las instrucciones.",
        "lib_swap_regen_body_cleared": "Borraste tu elección, pero el <b>código todavía usa {old}</b>.<br><br>¿Regenerar el código de esta funcionalidad para que la app busque de nuevo? El esquema se cerrará y la generación comenzará.",
        "lib_swap_regen_yes":          "Regenerar",
        "lib_swap_regen_no":           "Dejarlo así",
        "lib_swap_unchecked":          "Librería de {part} cambiada a {new}. No se pudo comprobar si el código existente todavía usa la anterior — considera regenerar la funcionalidad afectada manualmente.",
        "motor_mismatch_title":        "Código y esquema por armonizar",
        "motor_mismatch_body":         "Tu código usa un patrón de motor (<code>setMotor(...)</code>), pero no elegiste ningún motor para el esquema.<br><br>El cableado será correcto, pero el <b>código sigue siendo el de un motor</b>.<br><br>Para hacerlos coherentes, regenera tu código con una descripción más precisa.",
        "projects_title":              "Mis proyectos",
        "projects_filter_all":         "Todos",
        "projects_new":                "Nuevo proyecto",
        "projects_new_dialog_title":   "Nuevo proyecto",
        "projects_new_dialog_prompt":  "Nombre del proyecto:",
        "projects_new_type_label":     "Tipo de placa:",
        "projects_create":             "Crear",
        "projects_cancel":             "Cancelar",
        "projects_empty":              "Aún no hay proyectos",
        "projects_empty_hint":         "Pulsa «Nuevo proyecto» para empezar.",
        "projects_open":               "Abrir",
        "projects_open_folder":        "Abrir carpeta",
        "projects_last_modified":      "Modificado",
        "projects_board_unknown":      "Placa no definida",
        "projects_invalid_name":       "Nombre no válido. Usa letras, números, guiones o espacios.",
        "projects_name_exists":        "Ya existe un proyecto con ese nombre.",
        "projects_actions_tooltip":    "Más acciones",
        "projects_rename":             "Renombrar",
        "projects_duplicate":          "Duplicar",
        "projects_delete":             "Eliminar",
        "projects_delete_confirm_title":  "Eliminar proyecto",
        "projects_delete_confirm_msg":    "¿Eliminar definitivamente el proyecto «{name}»?\nEsta acción no se puede deshacer.",
        "projects_rename_dialog_title":   "Renombrar proyecto",
        "projects_rename_prompt":         "Nuevo nombre:",
        "projects_selection_one":         "1 proyecto seleccionado",
        "projects_selection_many":        "{n} proyectos seleccionados",
        "projects_deselect_all":          "Deseleccionar todo",
        "projects_delete_selection":      "Eliminar selección",
        "projects_delete_bulk_title":     "Eliminar proyectos",
        "projects_delete_bulk_msg":       "¿Eliminar definitivamente {n} proyectos?\nEsta acción no se puede deshacer.",
        "studio_comments_label":       "Comentarios del código generado:",
        "studio_comments_none":        "Ninguno",
        "studio_comments_minimal":     "Mínimo",
        "studio_comments_standard":    "Estándar",
        "studio_comments_detailed":    "Detallado",
        "studio_serial_monitor_chk":   "Monitor serie",
        "studio_save":                 "Guardar",
        "studio_save_as":              "Guardar como…",
        "studio_saved":                "Guardado",
        "studio_untitled":             "Sin título",
        "studio_unsaved_title":        "Cambios sin guardar",
        "studio_unsaved_msg":          "¿Guardar los cambios de «{name}»?",
        "studio_unsaved_save":         "Guardar",
        "studio_unsaved_discard":      "Descartar",
        "studio_unsaved_cancel":       "Cancelar",
        "studio_functions_title":       "Funcionalidades",
        "studio_functions_empty":       "Aún no hay funcionalidades.",
        "studio_functions_empty_hint":  "Pulsa «Añadir una funcionalidad» para empezar.",
        "studio_functions_collapse":    "Replegar el panel",
        "studio_functions_expand":      "Mostrar el panel",
        "studio_ai_tools_title":        "Herramientas IA",
        "studio_ai_tools_label":        "Herramientas",
        "studio_action_regen":          "Regenerar",
        "studio_action_schema":         "Ver el esquema",
        "studio_lines_word":            "líneas",
        "studio_tools_panel_title":     "Herramientas",
        "studio_schema_title":          "Esquema",
        "studio_tool_explain_lines":    "Explicar las líneas seleccionadas",
        "studio_tool_coming_soon":      "Esta herramienta estará disponible próximamente.",
        "studio_explain_title":         "Explicar el código",
        "studio_explain_code_label":    "Código",
        "studio_explain_result_label":  "Explicación",
        "studio_explain_btn":           "Explicar",
        "studio_explain_close":         "Cerrar",
        "studio_explain_loading":       "Analizando…",
        "studio_explain_hint_select":   "Selecciona las líneas a explicar y pulsa «Explicar».",
        "studio_explain_no_backend":    "No hay backend de IA disponible.",
        "studio_tool_lint":             "Detectar antipatrones",
        "studio_lint_title":            "Auditoría del código",
        "studio_lint_result_label":     "Avisos",
        "studio_lint_loading":          "Auditando…",
        "studio_lint_rerun_btn":        "Reanalizar",
        "studio_tool_add_comments":     "Añadir comentarios pedagógicos",
        "studio_addcmt_title":          "Añadir comentarios",
        "studio_addcmt_original":       "Código actual",
        "studio_addcmt_commented":      "Código comentado",
        "studio_addcmt_loading":        "Generando…",
        "studio_addcmt_apply":          "Aplicar",
        "studio_addcmt_rerun":          "Regenerar",
        "studio_addcmt_confirm_title":  "Reemplazar código",
        "studio_addcmt_confirm_msg":    "El código actual será reemplazado por la versión comentada. Se perderá el resaltado por función (las funciones permanecen en el panel).\n\n¿Continuar?",
        "studio_show_comments":         "Comentarios",
        "studio_addcmt_error":          "Error al generar comentarios: {msg}",
        "studio_addcmt_loading":        "Generando comentarios…",
        "studio_tool_repair":           "Analizar / Reparar el código",
        "studio_tool_format":           "Formatear el código",
        "studio_format_brace_added":    "Se añadió una llave de cierre que faltaba y se reformateó el código.",
        "studio_format_unbalanced":     "Desequilibrio de llaves detectado, pero no se pudo localizar automáticamente (indentación insuficiente). Ejecuta una compilación para un diagnóstico completo.",
        "studio_repair_error":          "Error en el análisis: {msg}",
        "studio_repair_dialog_title":   "Analizar / Reparar el código",
        "studio_repair_original_label": "Código original",
        "studio_repair_code_label":     "Código propuesto (cambios resaltados)",
        "studio_repair_summary_label":  "Análisis",
        "studio_repair_apply":          "Aplicar",
        "studio_repair_no_summary":     "La IA no proporcionó una explicación.",
        "studio_repairs_link":          "🔧 {n} corrección(es) automática(s) — ver detalle",
        "studio_repair_history_title":  "Correcciones automáticas",
        "studio_tool_wiring_diagram":   "Esquema de cableado",
        "studio_bottom_collapse":       "Replegar el registro y el monitor",
        "studio_bottom_expand":         "Mostrar el registro y el monitor",
        "studio_bottom_collapsed_title": "Registro y monitor serie",
        "studio_function_name_fmt":      "Funcionalidad {n}",
        "studio_function_no_prompt":     "(sin descripción)",
        "studio_function_err_no_markers":  "La respuesta de la IA no contiene marcadores de nueva funcionalidad.",
        "studio_function_err_missing_fid": "Falta el marcador {fid} en la respuesta de la IA.",
        "studio_function_err_contract_broken": "Regeneración rechazada para «{name}»: el contrato de exports ya no se respeta ({details}). Otras funcionalidades dependen de estas variables — inténtalo de nuevo pidiendo conservar los mismos nombres.",
        "studio_function_delete_tip":    "Eliminar",
        "studio_function_regen_tip":     "Modificar / Regenerar",
        "studio_function_delete_title":  "Eliminar una funcionalidad",
        "studio_function_delete_single": "¿Eliminar «{name}»?\nSu código será retirado del editor.",
        "studio_function_delete_cascade":"Eliminar «{name}» también eliminará {n} funcionalidad(es) que dependen de ella:\n\n{names}\n\n¿Continuar?",
        "studio_function_rename_tip":    "Haz doble clic para renombrar",
        "studio_function_delete_confirm":"Eliminar",
        "studio_function_regen_title":   "Regenerar «{name}»",
        "studio_function_regen_prompt":  "Nueva descripción:",
        "studio_function_regen_confirm": "Regenerar",
        "studio_function_regenerating":  "Regenerando…",
        "studio_function_undo":          "Deshacer",
        "studio_function_undo_tip":      "Deshacer la última operación de funcionalidad (Ctrl+Z)",
        "studio_functions_actions_tooltip": "Acciones",
        "studio_functions_action_rename":   "Renombrar",
        "studio_functions_action_merge":    "Fusionar…",
        "studio_functions_merge_confirm":   "Fusionar ({n})",
        "studio_functions_merge_cancel":    "Cancelar",
        "studio_functions_merge_title":     "Fusionar funcionalidades",
        "studio_functions_merge_msg":       "¿Fusionar las {n} funcionalidades seleccionadas en una sola?\n\nSe conservan el identificador y el color de la primera, los prompts se concatenan, los exports y líneas se unen.",
        "studio_repair_merge_ask_title":    "¿Fusionar las funcionalidades?",
        "studio_repair_merge_ask_msg":      "La reparación absorbió el código de estas funcionalidades en «{target}»:\n\n{lost}\n\n¿Oficializar la fusión (prompts concatenados, exports e historial unificados)? Si rechazas, estas funcionalidades permanecen en el panel pero sin resaltado.",
        "studio_function_delete_warning":"Esta acción retirará el código de la funcionalidad del editor.",
        "studio_function_regen_placeholder": "Describe la nueva versión de la funcionalidad…",
        "menu_card":                   "Placa",
        "menu_view":                   "Vista",
        "menu_help":                   "Ayuda",
        "mn_new_project":              "Nuevo proyecto",
        "mn_open_project":             "Abrir un proyecto",
        "mn_save":                     "Guardar",
        "mn_quit":                     "Salir",
        "menu_edit":                   "Edición",
        "mn_undo":                     "Deshacer",
        "mn_redo":                     "Rehacer",
        "mn_copy_code":                "Copiar el código",
        "mn_clear_prompt":             "Borrar el prompt",
        "topbar_undo_tip":             "Deshacer (Ctrl+Z)",
        "topbar_redo_tip":             "Rehacer (Ctrl+Y)",
        "feature_chips_delete_confirm": "¿Eliminar {n} funcionalidad(es)? El código correspondiente se quitará del editor.",
        "feature_dropdown_label":      "Funcionalidades",
        "feature_action_regen":        "Regenerar",
        "feature_action_delete":       "Eliminar",
        "studio_manual_feature_label": "Ediciones manuales",
        "ctx_menu_assign_feature":     "Asignar a…",
        "feature_transfer_title":      "Transferir funcionalidades",
        "feature_transfer_apply":      "Aplicar",
        "feature_transfer_all":        "Transferir todo →",
        "feature_transfer_all_back":   "← Transferir todo",
        "feature_transfer_recap_title": "Resumen",
        "feature_transfer_confirm":    "Confirmar",
        "feature_transfer_recap_transfers": "{n} transferencia(s)",
        "feature_transfer_recap_deletes":   "{n} eliminación(es)",
        "feature_transfer_recap_reorder":   "orden modificado",
        "feature_transfer_dirty_warn": "{win}: el código se editó a mano, esos cambios se perderán.",
        "feature_transfer_deleted_dep_warn": "{label} usará una variable eliminada",
        "feature_transfer_restore":    "Restaurar",
        "studio_reconstruct_title":    "¿Reconstruir desde las funcionalidades?",
        "studio_reconstruct_msg":      "La reparación falló y el código está roto estructuralmente. ¿Reconstruir un código limpio desde tus funcionalidades? Se perderán tus cambios manuales.",
        "studio_reconstruct_ok":       "Reconstruir",
        "studio_reconstruct_done":     "Código reconstruido desde las funcionalidades.",
        "studio_behavior_lint_title":  "Análisis de comportamiento",
        "studio_behavior_lint_none":   "Ningún error estático detectado.",
        "studio_behavior_evidence_joined": "Salida serie adjuntada a la revisión.",
        "studio_cascade_fixes_header": "**Correcciones de compilación:**",
        "studio_cascade_fixes_generic": "- {n} corrección(es) de compilación (ver el detalle en el registro).",
        "studio_cascade_line_removed": "- Línea {n}: `{code}` eliminada",
        "studio_cascade_line_added":   "- Línea {n}: `{code}` añadida",
        "studio_cascade_line_changed": "- Línea {n}: `{old}` → `{new}`",
        "feature_link_uses":           "Usa {name} de {label}",
        "feature_link_provides":       "Proporciona {name} a {label}",
        "studio_transfer_to_ai":       "◀ Transferir a la ventana IA",
        "mn_goto_board":               "Seleccionar placa/puerto…",
        "mn_theme_toggle":             "Cambiar tema claro/oscuro",
        "mn_language":                 "Idioma",
        "mn_toggle_sidebar":           "Ocultar navegación",
        "mn_fullscreen":               "Pantalla completa",
        "mn_open_workspace":           "Abrir la carpeta de proyectos",
        "mn_about":                    "Acerca de",
        "mn_about_msg":                "Genera código Arduino a partir de una descripción en lenguaje natural — una herramienta educativa de código abierto para iniciarse en la programación embebida.",
        "about_developer":             "Desarrollador",
        "about_credits_title":         "Software y recursos libres",
        "about_credits_intro":         "Promptuino se basa en estos proyectos de código abierto:",
        "about_source":                "Código fuente",
        "about_support":               "Apoyar el proyecto",
        "prompt_too_long":             "Tu proyecto ha crecido: la petición enviada al modelo ocupa el {percent} % de lo que puede leer ({tokens} de {window}). Puede olvidar el principio del código y reescribir lo que ya existe. Genera funcionalidad por funcionalidad, o cambia a un modelo en línea.",
        "crash_recovered":             "Un error inesperado ha interrumpido la operación en curso. La aplicación sigue funcionando — puedes volver a intentarlo. El detalle se ha guardado.",
        "settings_backstage":          "Entre bastidores del prompt",
        "backstage_enable":            "Ver el prompt antes de enviarlo",
        "backstage_desc":              "Antes de cada generación, una ventana muestra lo que la app envía realmente a la IA: las reglas que añade por su cuenta y tu mensaje. Puedes modificar tu mensaje y enviar, o cancelar.",
        "backstage_title":             "Entre bastidores del prompt",
        "backstage_system":            "Lo que la app añade por su cuenta (solo lectura)",
        "backstage_user":              "Tu mensaje (modificable antes de enviar)",
        "backstage_chars":             "{n} caracteres",
        "backstage_send":              "Enviar",
        "backstage_edited":            "Prompt modificado a mano para esta generación: el botón ↻ partirá del proyecto, no de este texto.",
        "nav_bibliotheque":               "Librerías",
        "library_title":                  "Librerías",
        "library_search_placeholder":     "Buscar una librería para instalar…",
        "library_installed_section":      "Librerías instaladas",
        "library_installed_count":        "{n} instalada(s)",
        "library_installed_empty":        "No hay librerías instaladas para {platform}.",
        "library_installed_empty_hint":   "Escribe el nombre de una librería arriba para instalarla.",
        "library_search_section":         "Resultados de búsqueda",
        "library_search_no_results":      "No se encontró ninguna librería para «{query}».",
        "library_searching":              "Buscando…",
        "library_loading":                "Cargando…",
        "library_install":                "Instalar",
        "library_installing":             "Instalando…",
        "library_installed_badge":        "Instalada",
        "library_uninstall":              "Eliminar",
        "library_uninstalling":           "Eliminando…",
        "library_delete_confirm_title":   "Eliminar librería",
        "library_delete_confirm_msg":     "¿Eliminar definitivamente «{name}»?\nLa carpeta se borrará del disco.",
        "library_install_error_title":    "Error al instalar",
        "library_install_error_msg":      "No se pudo instalar «{name}»:\n{error}",
        "library_uninstall_error_title":  "Error al eliminar",
        "library_uninstall_error_msg":    "No se pudo eliminar «{name}»:\n{error}",
        "library_no_cli":                 "arduino-cli no está disponible — instálalo y reinicia la aplicación.",
        "library_platform_label":         "Plataforma:",
        "library_platform_arduino":       "Arduino",
        "library_platform_esp32":         "ESP32",
        "board_coming_soon":              "Próximamente",
        "library_by":                     "por {author}",
        "library_version_prefix":         "v",
        "library_open_folder":            "Abrir carpeta",
        "library_more_actions":           "Más acciones",
        "ia_err_auth":         "Clave API inválida o ausente para este proveedor.",
        "ia_err_notfound":     "Modelo o URL no encontrado — comprueba el modelo y la URL base.",
        "ia_err_quota":        "Cuota o límite de uso superado — inténtalo más tarde.",
        "ia_err_provider":     "Error del proveedor — inténtalo más tarde.",
        "ia_err_network":      "Proveedor inaccesible — comprueba tu conexión y la URL base.",
        "ia_err_bad_response": "Respuesta ilegible del proveedor.",
        "ia_cloud_provider_title":    "Nube (tu clave)",
        "ia_cloud_provider_subtitle": "Usa tu propia clave API con un proveedor compatible con OpenAI.",
        "ia_provider_label":   "Proveedor",
        "ia_model_label":      "Modelo",
        "ia_model_placeholder": "Dejar vacío para el modelo por defecto",
        "ia_base_url_label":   "URL base",
        "ia_get_key_link":     "Obtener una clave",
        "ia_model_disclaimer": "Algunos modelos ofrecen un nivel de API gratuito — comprueba el sitio del proveedor.",
        "ia_models_loading":       "Cargando modelos…",
        "ia_models_none":          "No se obtuvieron modelos — escríbelo manualmente.",
        "ia_models_unsupported":   "Este proveedor no expone la lista — escribe el modelo manualmente.",
        # ── Components tab ──
        "nav_composants":                  "Componentes",
        "components_search_placeholder":   "Buscar un componente…",
        "components_filter_all":           "Todos",
        "components_filter_declared":      "Propios",
        "components_filter_with_library":  "Con librería",
        "components_filter_drawable":      "Dibujables",
        "components_declare_button":       "Crear un componente",
        "components_lib_unknown":          "librería por determinar",
        "components_wiring_unknown":       "dibujo genérico",
        "components_wiring_none":          "nada que conectar",
        "components_library_none":         "sin librería que instalar",
        "components_custom_badge_tip":     "Componente que describiste tú mismo",
        "components_adopt_tip":            "Librería adivinada por la app — haz clic para corregirla y describir este componente",
        "components_empty":                "Ningún componente coincide.",
        "components_pin_count":            "{n} pines",
        "components_change_lib":           "Cambiar de librería",
        # ── Selector de la modal de ambigüedad ──
        "picker_search_placeholder":       "Buscar un componente…",
        "picker_count_category":           "Componentes propuestos para este pin: {n}",
        "picker_count_all":                "Búsqueda en toda la biblioteca: {n}",
        "picker_count_capped":             "{total} componentes coinciden — se muestran los {shown} primeros, precisa tu búsqueda.",
        "picker_group_requalify":          "— o reclasificar como —",
        "picker_group_yours":              "— tus componentes —",
        "registry_module_lib_found":      "Módulo {alias}: reconocido como {part}, librería «{lib}» encontrada en el registro de Arduino y usada para la generación.",
        "registry_module_lib_not_found":  "Módulo {alias}: reconocido como {part}, pero no se encontró ninguna librería en el registro de Arduino. Puede que el código no funcione. Adjuntar una documentación (.md/.txt) puede ayudar.",
        "registry_module_install_failed": "Módulo {alias}: reconocido como {part}, la librería «{lib}» sí existe en el registro de Arduino, pero no se pudo descargar. Comprueba tu conexión a internet y vuelve a generar.",
        "registry_module_lib_unavailable": "Módulo {alias}: reconocido como {part}, pero no se pudo consultar el registro de Arduino (ninguna placa seleccionada, o arduino-cli no disponible). Selecciona tu placa y vuelve a generar.",
    },
    "it": {
        "settings_privacy":               "Riservatezza",
        "settings_privacy_desc":          "Promptuino non raccoglie alcuna statistica e non invia nulla su Internet. I tuoi progetti, i tuoi prompt e il tuo codice restano sulla tua macchina. Se l'applicazione va in crash, un rapporto viene scritto nella tua cartella Promptuino — condividerlo dipende solo da te.",
        "tip_toggle_sidebar":             "Mostra o nascondi la navigazione",
        "tip_toggle_chat":                "Mostra o nascondi l'assistente",
        "tip_card_functions":             "Vedi le funzionalità del progetto",
        "tip_refresh_ports":              "Cerca di nuovo le porte",
        "btn_validate":                   "Conferma",
        "btn_cancel":                     "Annulla",
        "btn_understood":                 "Ho capito",
        "btn_yes":                        "Sì",
        "btn_no":                         "No",
        "nav_projets":                 "Progetti",
        "chip_swap_regen_title":       "Aggiornare il codice?",
        "chip_swap_regen_body":        "Hai scelto un <b>{new}</b>, ma il <b>codice descrive ancora un {old}</b>.<br><br>Rigenerare il codice di questa funzionalità con il {new}? Lo schema si chiuderà e la generazione partirà.",
        "chip_swap_regen_yes":         "Rigenera",
        "chip_swap_regen_no":          "Lascia così",
        "registry_lib_found":          "Componente {part}: libreria «{lib}» trovata nel registro Arduino e usata per la generazione.",
        "registry_lib_not_found":      "Componente «{part}» sconosciuto: codice generato senza riferimento, potrebbe non funzionare. Allegare una documentazione (.md/.txt) può aiutare.",
        "registry_install_failed":     "Componente «{part}»: la libreria «{lib}» esiste nel registro Arduino, ma non è stato possibile scaricarla. Controlla la connessione a internet, poi rigenera.",
        "registry_change_lib":         "Cambia libreria",
        "rag_guess_by_resemblance":    "Nessun componente riconosciuto nella tua richiesta — una libreria è stata proposta al modello <b>per somiglianza</b>. Indica il riferimento esatto del tuo componente (es. «BMP280») per un risultato affidabile.",
        "lib_choice_title":            "Scegliere la libreria",
        "lib_choice_body":             "Per <b>{part}</b>, l'app usa «<b>{lib}</b>». Scegli quella che corrisponde al materiale che hai.",
        "lib_choice_search_placeholder": "Nome della libreria…",
        "lib_choice_search_empty":     "Nessuna libreria corrisponde a «{q}».",
        "lib_choice_search_unavailable": "Ricerca non disponibile: manca arduino-cli. Le librerie già trovate restano proposte.",
        "lib_choice_ok":               "Usa questa libreria",
        "lib_choice_cancel":           "Annulla",
        "lib_choice_let_app_decide":   "Lascia decidere all'app",
        "lib_choice_let_app_decide_hint": "Cancella la tua scelta; l'app cercherà di nuovo alla prossima generazione.",
        "lib_choice_no_library":      "Non serve alcuna libreria",
        "lib_choice_no_library_hint": "Questo componente si pilota direttamente, senza #include. L’app smetterà di cercarne una.",
        "lib_choice_loading":          "Caricamento del catalogo Arduino…",
        "lib_choice_count":            "{n} librerie trovate",
        "lib_choice_count_one":        "1 libreria trovata",
        "lib_choice_count_capped":     "{total} librerie corrispondono — sono mostrate le prime {shown}, affina la ricerca.",
        "lib_choice_badge_in_use":     "in uso",
        "lib_choice_badge_retired":    "ritirata",
        "lib_choice_badge_incompatible": "non compatibile con la tua scheda",
        "lib_choice_meta_all_boards":  "Compatibile con tutte le schede",
        "lib_choice_meta_requires":    "richiede {deps}",
        "registry_pref_not_found":     "La tua libreria «{pref}» per {part} non è nel registro Arduino: è stata usata «{lib}».",
        "lib_swap_regen_title":        "Aggiornare il codice?",
        "lib_swap_regen_body":         "Hai scelto la libreria <b>{new}</b>, ma il <b>codice usa ancora {old}</b>.<br><br>Rigenerare il codice interessato? Lo schema non cambia: è lo stesso chip, cambiano solo le istruzioni.",
        "lib_swap_regen_body_cleared": "Hai cancellato la tua scelta, ma il <b>codice usa ancora {old}</b>.<br><br>Rigenerare il codice di questa funzionalità per lasciare che l'app cerchi di nuovo? Lo schema si chiuderà e la generazione partirà.",
        "lib_swap_regen_yes":          "Rigenera",
        "lib_swap_regen_no":           "Lascia com'è",
        "lib_swap_unchecked":          "Libreria di {part} cambiata in {new}. Impossibile verificare se il codice esistente usa ancora quella precedente — valuta di rigenerare manualmente la funzionalità interessata.",
        "motor_mismatch_title":        "Codice e schema da armonizzare",
        "motor_mismatch_body":         "Il tuo codice usa un pattern per motore (<code>setMotor(...)</code>), ma non hai scelto alcun motore per lo schema.<br><br>Il cablaggio sarà corretto, ma il <b>codice resta quello di un motore</b>.<br><br>Per renderli coerenti, rigenera il codice con una descrizione più precisa.",
        "projects_title":              "I miei progetti",
        "projects_filter_all":         "Tutti",
        "projects_new":                "Nuovo progetto",
        "projects_new_dialog_title":   "Nuovo progetto",
        "projects_new_dialog_prompt":  "Nome del progetto:",
        "projects_new_type_label":     "Tipo di scheda:",
        "projects_create":             "Crea",
        "projects_cancel":             "Annulla",
        "projects_empty":              "Nessun progetto per ora",
        "projects_empty_hint":         "Clicca su «Nuovo progetto» per iniziare.",
        "projects_open":               "Apri",
        "projects_open_folder":        "Apri cartella",
        "projects_last_modified":      "Modificato",
        "projects_board_unknown":      "Scheda non definita",
        "projects_invalid_name":       "Nome non valido. Usa lettere, numeri, trattini o spazi.",
        "projects_name_exists":        "Esiste già un progetto con questo nome.",
        "projects_actions_tooltip":    "Altre azioni",
        "projects_rename":             "Rinomina",
        "projects_duplicate":          "Duplica",
        "projects_delete":             "Elimina",
        "projects_delete_confirm_title":  "Elimina progetto",
        "projects_delete_confirm_msg":    "Eliminare definitivamente il progetto «{name}»?\nQuesta azione è irreversibile.",
        "projects_rename_dialog_title":   "Rinomina progetto",
        "projects_rename_prompt":         "Nuovo nome:",
        "projects_selection_one":         "1 progetto selezionato",
        "projects_selection_many":        "{n} progetti selezionati",
        "projects_deselect_all":          "Deseleziona tutto",
        "projects_delete_selection":      "Elimina selezione",
        "projects_delete_bulk_title":     "Elimina progetti",
        "projects_delete_bulk_msg":       "Eliminare definitivamente {n} progetti?\nQuesta azione è irreversibile.",
        "studio_comments_label":       "Commenti del codice generato:",
        "studio_comments_none":        "Nessuno",
        "studio_comments_minimal":     "Minimo",
        "studio_comments_standard":    "Standard",
        "studio_comments_detailed":    "Dettagliato",
        "studio_serial_monitor_chk":   "Monitor seriale",
        "studio_save":                 "Salva",
        "studio_save_as":              "Salva con nome…",
        "studio_saved":                "Salvato",
        "studio_untitled":             "Senza titolo",
        "studio_unsaved_title":        "Modifiche non salvate",
        "studio_unsaved_msg":          "Salvare le modifiche a «{name}»?",
        "studio_unsaved_save":         "Salva",
        "studio_unsaved_discard":      "Ignora",
        "studio_unsaved_cancel":       "Annulla",
        "studio_functions_title":       "Funzionalità",
        "studio_functions_empty":       "Nessuna funzionalità per ora.",
        "studio_functions_empty_hint":  "Clicca su «Aggiungi una funzionalità» per iniziare.",
        "studio_functions_collapse":    "Riduci il pannello",
        "studio_functions_expand":      "Mostra il pannello",
        "studio_ai_tools_title":        "Strumenti IA",
        "studio_ai_tools_label":        "Strumenti",
        "studio_action_regen":          "Rigenera",
        "studio_action_schema":         "Vedi lo schema",
        "studio_lines_word":            "righe",
        "studio_tools_panel_title":     "Strumenti",
        "studio_schema_title":          "Schema",
        "studio_tool_explain_lines":    "Spiega le righe selezionate",
        "studio_tool_coming_soon":      "Questo strumento sarà presto disponibile.",
        "studio_explain_title":         "Spiega il codice",
        "studio_explain_code_label":    "Codice",
        "studio_explain_result_label":  "Spiegazione",
        "studio_explain_btn":           "Spiega",
        "studio_explain_close":         "Chiudi",
        "studio_explain_loading":       "Analisi in corso…",
        "studio_explain_hint_select":   "Seleziona le righe da spiegare poi clicca «Spiega».",
        "studio_explain_no_backend":    "Nessun backend IA disponibile.",
        "studio_tool_lint":             "Rileva antipattern",
        "studio_lint_title":            "Audit del codice",
        "studio_lint_result_label":     "Avvisi",
        "studio_lint_loading":          "Analisi in corso…",
        "studio_lint_rerun_btn":        "Rilancia l'audit",
        "studio_tool_add_comments":     "Aggiungi commenti pedagogici",
        "studio_addcmt_title":          "Aggiungi commenti",
        "studio_addcmt_original":       "Codice attuale",
        "studio_addcmt_commented":      "Codice commentato",
        "studio_addcmt_loading":        "Generazione in corso…",
        "studio_addcmt_apply":          "Applica",
        "studio_addcmt_rerun":          "Rigenera",
        "studio_addcmt_confirm_title":  "Sostituisci il codice",
        "studio_addcmt_confirm_msg":    "Il codice attuale verrà sostituito con la versione commentata. L'evidenziazione per funzione andrà persa (le funzioni restano nel pannello).\n\nContinuare?",
        "studio_show_comments":         "Commenti",
        "studio_addcmt_error":          "Errore generazione commenti: {msg}",
        "studio_addcmt_loading":        "Generazione commenti…",
        "studio_tool_repair":           "Analizza / Ripara il codice",
        "studio_tool_format":           "Formatta il codice",
        "studio_format_brace_added":    "È stata aggiunta una parentesi graffa di chiusura mancante e il codice è stato riformattato.",
        "studio_format_unbalanced":     "Squilibrio di parentesi graffe rilevato, ma impossibile localizzarlo automaticamente (indentazione insufficiente). Avvia una compilazione per una diagnosi completa.",
        "studio_repair_error":          "Analisi fallita: {msg}",
        "studio_repair_dialog_title":   "Analizza / Ripara il codice",
        "studio_repair_original_label": "Codice originale",
        "studio_repair_code_label":     "Codice proposto (modifiche evidenziate)",
        "studio_repair_summary_label":  "Analisi",
        "studio_repair_apply":          "Applica",
        "studio_repair_no_summary":     "L'IA non ha fornito una spiegazione.",
        "studio_repairs_link":          "🔧 {n} correzione/i automatica/he — vedi dettaglio",
        "studio_repair_history_title":  "Correzioni automatiche",
        "studio_tool_wiring_diagram":   "Schema di cablaggio",
        "studio_bottom_collapse":       "Riduci il registro e il monitor",
        "studio_bottom_expand":         "Mostra il registro e il monitor",
        "studio_bottom_collapsed_title": "Registro e monitor seriale",
        "studio_function_name_fmt":      "Funzionalità {n}",
        "studio_function_no_prompt":     "(nessuna descrizione)",
        "studio_function_err_no_markers":  "La risposta dell'IA non contiene marcatori di nuova funzionalità.",
        "studio_function_err_missing_fid": "Il marcatore {fid} è assente dalla risposta dell'IA.",
        "studio_function_err_contract_broken": "Rigenerazione rifiutata per «{name}»: il contratto di exports non è più rispettato ({details}). Altre funzionalità dipendono da queste variabili — riprova chiedendo di mantenere gli stessi nomi.",
        "studio_function_delete_tip":    "Elimina",
        "studio_function_regen_tip":     "Modifica / Rigenera",
        "studio_function_delete_title":  "Elimina una funzionalità",
        "studio_function_delete_single": "Eliminare «{name}»?\nIl suo codice verrà rimosso dall'editor.",
        "studio_function_delete_cascade":"Eliminare «{name}» eliminerà anche {n} funzionalità che ne dipendono:\n\n{names}\n\nContinuare?",
        "studio_function_rename_tip":    "Fai doppio clic per rinominare",
        "studio_function_delete_confirm":"Elimina",
        "studio_function_regen_title":   "Rigenera «{name}»",
        "studio_function_regen_prompt":  "Nuova descrizione:",
        "studio_function_regen_confirm": "Rigenera",
        "studio_function_regenerating":  "Rigenerazione in corso…",
        "studio_function_undo":          "Annulla",
        "studio_function_undo_tip":      "Annulla l'ultima operazione sulla funzionalità (Ctrl+Z)",
        "studio_functions_actions_tooltip": "Azioni",
        "studio_functions_action_rename":   "Rinomina",
        "studio_functions_action_merge":    "Unisci…",
        "studio_functions_merge_confirm":   "Unisci ({n})",
        "studio_functions_merge_cancel":    "Annulla",
        "studio_functions_merge_title":     "Unisci le funzionalità",
        "studio_functions_merge_msg":       "Unire le {n} funzionalità selezionate in una sola?\n\nId e colore della prima vengono mantenuti, i prompt concatenati, gli export e le righe uniti.",
        "studio_repair_merge_ask_title":    "Unire le funzionalità?",
        "studio_repair_merge_ask_msg":      "La riparazione ha assorbito il codice di queste funzionalità in «{target}»:\n\n{lost}\n\nUfficializzare la fusione (prompt concatenati, export e cronologia unificati)? Se rifiuti, queste funzionalità restano nel pannello ma senza evidenziazione.",
        "studio_function_delete_warning":"Questa azione rimuoverà il codice della funzionalità dall'editor.",
        "studio_function_regen_placeholder": "Descrivi la nuova versione della funzionalità…",
        "menu_card":                   "Scheda",
        "menu_view":                   "Visualizza",
        "menu_help":                   "Aiuto",
        "mn_new_project":              "Nuovo progetto",
        "mn_open_project":             "Apri un progetto",
        "mn_save":                     "Salva",
        "mn_quit":                     "Esci",
        "menu_edit":                   "Modifica",
        "mn_undo":                     "Annulla",
        "mn_redo":                     "Ripristina",
        "mn_copy_code":                "Copia il codice",
        "mn_clear_prompt":             "Cancella il prompt",
        "topbar_undo_tip":             "Annulla (Ctrl+Z)",
        "topbar_redo_tip":             "Ripristina (Ctrl+Y)",
        "feature_chips_delete_confirm": "Eliminare {n} funzionalità? Il codice corrispondente sarà rimosso dall'editor.",
        "feature_dropdown_label":      "Funzionalità",
        "feature_action_regen":        "Rigenera",
        "feature_action_delete":       "Elimina",
        "studio_manual_feature_label": "Modifiche manuali",
        "ctx_menu_assign_feature":     "Assegna a…",
        "feature_transfer_title":      "Trasferisci funzionalità",
        "feature_transfer_apply":      "Applica",
        "feature_transfer_all":        "Trasferisci tutto →",
        "feature_transfer_all_back":   "← Trasferisci tutto",
        "feature_transfer_recap_title": "Riepilogo",
        "feature_transfer_confirm":    "Conferma",
        "feature_transfer_recap_transfers": "{n} trasferimento/i",
        "feature_transfer_recap_deletes":   "{n} eliminazione/i",
        "feature_transfer_recap_reorder":   "ordine modificato",
        "feature_transfer_dirty_warn": "{win}: il codice è stato modificato a mano, quelle modifiche andranno perse.",
        "feature_transfer_deleted_dep_warn": "{label} userà una variabile eliminata",
        "feature_transfer_restore":    "Ripristina",
        "studio_reconstruct_title":    "Ricostruire dalle funzionalità?",
        "studio_reconstruct_msg":      "La riparazione è fallita e il codice è strutturalmente rotto. Ricostruire un codice pulito dalle funzionalità? Le modifiche manuali andranno perse.",
        "studio_reconstruct_ok":       "Ricostruire",
        "studio_reconstruct_done":     "Codice ricostruito dalle funzionalità.",
        "studio_behavior_lint_title":  "Analisi comportamentale",
        "studio_behavior_lint_none":   "Nessuna trappola statica rilevata.",
        "studio_behavior_evidence_joined": "Output seriale allegato alla revisione.",
        "studio_cascade_fixes_header": "**Correzioni di compilazione:**",
        "studio_cascade_fixes_generic": "- {n} correzione/i di compilazione (vedi il dettaglio nel registro).",
        "studio_cascade_line_removed": "- Riga {n}: `{code}` rimossa",
        "studio_cascade_line_added":   "- Riga {n}: `{code}` aggiunta",
        "studio_cascade_line_changed": "- Riga {n}: `{old}` → `{new}`",
        "feature_link_uses":           "Usa {name} di {label}",
        "feature_link_provides":       "Fornisce {name} a {label}",
        "studio_transfer_to_ai":       "◀ Trasferisci nella finestra IA",
        "mn_goto_board":               "Seleziona scheda/porta…",
        "mn_theme_toggle":             "Cambia tema chiaro/scuro",
        "mn_language":                 "Lingua",
        "mn_toggle_sidebar":           "Nascondi la navigazione",
        "mn_fullscreen":               "Schermo intero",
        "mn_open_workspace":           "Apri la cartella dei progetti",
        "mn_about":                    "Informazioni",
        "mn_about_msg":                "Genera codice Arduino da una descrizione in linguaggio naturale — uno strumento educativo open source per iniziare con la programmazione embedded.",
        "about_developer":             "Sviluppatore",
        "about_credits_title":         "Software e risorse open source",
        "about_credits_intro":         "Promptuino si basa su questi progetti open source:",
        "about_source":                "Codice sorgente",
        "about_support":               "Sostieni il progetto",
        "prompt_too_long":             "Il tuo progetto è cresciuto: la richiesta inviata al modello occupa il {percent} % di ciò che può leggere ({tokens} su {window}). Potrebbe dimenticare l'inizio del codice e riscrivere ciò che esiste già. Genera una funzionalità alla volta, oppure passa a un modello online.",
        "crash_recovered":             "Un errore imprevisto ha interrotto l'operazione in corso. L'applicazione continua a funzionare — puoi riprovare. Il dettaglio è stato registrato.",
        "settings_backstage":          "Dietro le quinte del prompt",
        "backstage_enable":            "Vedere il prompt prima di inviarlo",
        "backstage_desc":              "Prima di ogni generazione, una finestra mostra ciò che l'app invia davvero all'IA: le regole che aggiunge da sé e il tuo messaggio. Puoi modificare il tuo messaggio e inviare, oppure annullare.",
        "backstage_title":             "Dietro le quinte del prompt",
        "backstage_system":            "Ciò che l'app aggiunge da sé (sola lettura)",
        "backstage_user":              "Il tuo messaggio (modificabile prima dell'invio)",
        "backstage_chars":             "{n} caratteri",
        "backstage_send":              "Invia",
        "backstage_edited":            "Prompt modificato a mano per questa generazione: il pulsante ↻ ripartirà dal progetto, non da questo testo.",
        "nav_bibliotheque":               "Librerie",
        "library_title":                  "Librerie",
        "library_search_placeholder":     "Cerca una libreria da installare…",
        "library_installed_section":      "Librerie installate",
        "library_installed_count":        "{n} installata/e",
        "library_installed_empty":        "Nessuna libreria installata per {platform}.",
        "library_installed_empty_hint":   "Digita il nome di una libreria sopra per installarla.",
        "library_search_section":         "Risultati della ricerca",
        "library_search_no_results":      "Nessuna libreria trovata per «{query}».",
        "library_searching":              "Ricerca in corso…",
        "library_loading":                "Caricamento…",
        "library_install":                "Installa",
        "library_installing":             "Installazione…",
        "library_installed_badge":        "Installata",
        "library_uninstall":              "Rimuovi",
        "library_uninstalling":           "Rimozione…",
        "library_delete_confirm_title":   "Rimuovi libreria",
        "library_delete_confirm_msg":     "Rimuovere definitivamente «{name}»?\nLa cartella sarà eliminata dal disco.",
        "library_install_error_title":    "Installazione fallita",
        "library_install_error_msg":      "Impossibile installare «{name}»:\n{error}",
        "library_uninstall_error_title":  "Rimozione fallita",
        "library_uninstall_error_msg":    "Impossibile rimuovere «{name}»:\n{error}",
        "library_no_cli":                 "arduino-cli non trovato — installalo e riavvia l'applicazione.",
        "library_platform_label":         "Piattaforma:",
        "library_platform_arduino":       "Arduino",
        "library_platform_esp32":         "ESP32",
        "board_coming_soon":              "Prossimamente",
        "library_by":                     "di {author}",
        "library_version_prefix":         "v",
        "library_open_folder":            "Apri cartella",
        "library_more_actions":           "Altre azioni",
        "ia_err_auth":         "Chiave API non valida o assente per questo provider.",
        "ia_err_notfound":     "Modello o URL non trovato — controlla il modello e l'URL di base.",
        "ia_err_quota":        "Quota o limite di frequenza superato — riprova più tardi.",
        "ia_err_provider":     "Errore del provider — riprova più tardi.",
        "ia_err_network":      "Provider irraggiungibile — controlla la connessione e l'URL di base.",
        "ia_err_bad_response": "Risposta illeggibile dal provider.",
        "ia_cloud_provider_title":    "Cloud (la tua chiave)",
        "ia_cloud_provider_subtitle": "Usa la tua chiave API con un provider compatibile con OpenAI.",
        "ia_provider_label":   "Provider",
        "ia_model_label":      "Modello",
        "ia_model_placeholder": "Lascia vuoto per il modello predefinito",
        "ia_base_url_label":   "URL di base",
        "ia_get_key_link":     "Ottieni una chiave",
        "ia_model_disclaimer": "Alcuni modelli offrono un piano API gratuito — controlla il sito del provider.",
        "ia_models_loading":       "Caricamento modelli…",
        "ia_models_none":          "Nessun modello recuperato — inseriscilo manualmente.",
        "ia_models_unsupported":   "Questo provider non espone l'elenco — inserisci il modello manualmente.",
        # ── Components tab ──
        "nav_composants":                  "Componenti",
        "components_search_placeholder":   "Cerca un componente…",
        "components_filter_all":           "Tutti",
        "components_filter_declared":      "Personali",
        "components_filter_with_library":  "Con libreria",
        "components_filter_drawable":      "Disegnabili",
        "components_declare_button":       "Crea un componente",
        "components_lib_unknown":          "libreria da determinare",
        "components_wiring_unknown":       "disegno generico",
        "components_wiring_none":          "niente da collegare",
        "components_library_none":         "nessuna libreria da installare",
        "components_custom_badge_tip":     "Componente che hai descritto tu",
        "components_adopt_tip":            "Libreria indovinata dall'app — clicca per correggerla e descrivere questo componente",
        "components_empty":                "Nessun componente corrisponde.",
        "components_pin_count":            "{n} pin",
        "components_change_lib":           "Cambia libreria",
        # ── Selettore della modale di ambiguità ──
        "picker_search_placeholder":       "Cerca un componente…",
        "picker_count_category":           "Componenti proposti per questo pin: {n}",
        "picker_count_all":                "Ricerca in tutta la libreria: {n}",
        "picker_count_capped":             "{total} componenti corrispondono — sono mostrati i primi {shown}, precisa la ricerca.",
        "picker_group_requalify":          "— o riqualifica come —",
        "picker_group_yours":              "— i tuoi componenti —",
        "registry_module_lib_found":      "Modulo {alias}: riconosciuto come {part}, libreria «{lib}» trovata nel registro Arduino e usata per la generazione.",
        "registry_module_lib_not_found":  "Modulo {alias}: riconosciuto come {part}, ma nessuna libreria trovata nel registro Arduino. Il codice potrebbe non funzionare. Allegare una documentazione (.md/.txt) può aiutare.",
        "registry_module_install_failed": "Modulo {alias}: riconosciuto come {part}, la libreria «{lib}» esiste nel registro Arduino, ma non è stato possibile scaricarla. Controlla la connessione a internet, poi rigenera.",
        "registry_module_lib_unavailable": "Modulo {alias}: riconosciuto come {part}, ma non è stato possibile interrogare il registro Arduino (nessuna scheda selezionata, o arduino-cli non disponibile). Seleziona la tua scheda, poi rigenera.",
    },
}
for _code, _kvs in _EXTRA_STRINGS.items():
    _s = TRANSLATIONS.get(_code)
    if _s is not None:
        for _k, _v in _kvs.items():
            setattr(_s, _k, _v)


# Global instance — import from the other modules
lang_manager = LanguageManager()


def localize_button_box(box, *, ok: str | None = None,
                        cancel: str | None = None) -> None:
    """Give a QDialogButtonBox's STANDARD buttons the app's own wording.

    Qt ships its own translations for Ok/Cancel/Yes/No and picks them from the
    SYSTEM locale, which has nothing to do with the language chosen in the app.
    Left alone, they came out in English -- « OK » / « Cancel » in the middle of
    a French dialog. Written by hand in French, they came out in French inside
    an English one: the wiring dialog did exactly that, in eleven places.

    So the wording comes from `lang_manager` like every other label, and it is
    re-applied on every language change: call this again from the dialog's
    `apply_lang`, since switching the language must not leave a stale button.

    `ok` / `cancel` override the default wording for the dialogs whose action
    is not a plain validation (« J'ai compris » on an informational one).
    """
    from PyQt6.QtWidgets import QDialogButtonBox
    s = lang_manager.current
    sb = QDialogButtonBox.StandardButton
    for std, text in ((sb.Ok, ok if ok is not None else s.btn_validate),
                      (sb.Cancel, cancel if cancel is not None else s.btn_cancel)):
        btn = box.button(std)
        if btn is not None:
            btn.setText(text)

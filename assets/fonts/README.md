# Polices embarquées (optionnel)

Dépose ici les fichiers `.ttf` / `.otf` à embarquer. Au démarrage,
`ui/fonts.py::setup_fonts()` charge **automatiquement** tout fichier présent
dans ce dossier — aucun autre changement de code requis.

Politique (spec Phase 2 §5/§6) : **fallback système prioritaire**. Sans ces
fichiers, l'app utilise les polices système :

- **UI** : Geist → *Segoe UI Variable Display* → *Segoe UI*
- **Mono** : JetBrains Mono → *Cascadia Mono* → *Cascadia Code* → *Consolas*

## Quelles polices

- **Geist** (UI) — https://github.com/vercel/geist-font
  Fichiers utiles : `Geist-Regular.ttf`, `Geist-Medium.ttf`,
  `Geist-SemiBold.ttf`, `Geist-Bold.ttf` (la famille doit s'appeler `Geist`).
- **JetBrains Mono** (code) — https://www.jetbrains.com/lp/mono/
  Fichiers utiles : `JetBrainsMono-Regular.ttf`, `JetBrainsMono-Bold.ttf`
  (famille `JetBrains Mono`).

## Vérifier que c'est pris en compte

Au lancement, la police UI bascule sur Geist et le code sur JetBrains Mono.
Si rien ne change, vérifie que le **nom de famille** interne du `.ttf`
correspond bien (`Geist`, `JetBrains Mono`) — c'est ce nom, pas le nom de
fichier, que Qt utilise.

> Ce dossier est volontairement vide par défaut (les `.ttf` ne sont pas
> versionnés). À chacun d'y déposer ses polices.

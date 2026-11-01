"""Pick the Arduino library to use for a component the app had to guess.

Opened from TWO places (the banner announcing the guess, and the component
card in the "Composants" tab) so the same decision is reachable both while it
is fresh and long after. Both pass the alternatives they already hold -- the
registry search already found them, `registry_lookup` already persists them;
this dialog only had to be written.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from .i18n import lang_manager
from .library_index import (
    LibraryRecord, filter_libraries, index, is_loaded, is_retired, set_index,
    supports_arch,
)
from .registry_lookup import norm_lib_name
from .theme import card_qss, theme_manager


def choices_for(current_lib: str, alternatives: list[str]) -> list[str]:
    """Libraries to offer, the retained one FIRST and never duplicated.

    Pure and Qt-free so the ordering rule is testable on its own. The registry
    returns the winner inside `alternatives` too, and those names round-trip
    through JSON and a cache -- hence the dedup through the project's own
    library-name key, which also collapses internal whitespace: two radios for
    the same library would be a defect the user cannot explain.
    """
    out: list[str] = []
    seen: set[str] = set()
    for name in [current_lib, *alternatives]:
        clean = (name or "").strip()
        if not clean:
            continue
        key = norm_lib_name(clean)
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
    return out


class _Badge(QLabel):
    """Pastille de la card. QLabel avec un fond dessine par QSS local : ce
    n'est pas un controle standard, la garde de theme.py ne le vise pas, et il
    ne porte aucune QPalette donc aucun conflit."""

    def __init__(self, text: str, *, warn: bool = False, parent=None):
        super().__init__(text, parent)
        c = theme_manager.current
        color = c.signal_warn if warn else c.signal_ok
        self.setStyleSheet(
            f"QLabel {{ color: {color}; border: 1px solid {color};"
            f" border-radius: 8px; padding: 1px 7px; font-size: 8pt;"
            f" background: transparent; }}")


class _LibraryCard(QFrame):
    """Une bibliotheque, affichee et selectionnable. Remplace la QRadioButton.

    Emet `picked` quand l'utilisateur la choisit (clic ou Espace). La modale
    tient l'exclusivite : une card ne sait pas qui sont ses soeurs.
    """

    picked = pyqtSignal(object)      # emet le LibraryRecord

    def __init__(self, record: LibraryRecord, *, arch: str,
                 in_use: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("libCard")
        self.record = record
        self._selected = False
        # Le clavier que la QRadioButton donnait gratuitement.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Minimum)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel(record.name)
        title.setWordWrap(True)
        head.addWidget(title, 1)
        for text, warn in self._badges(arch, in_use):
            head.addWidget(_Badge(text, warn=warn))
        lay.addLayout(head)

        meta_bits = [b for b in (record.author, record.version, record.category)
                     if b]
        if meta_bits:
            sub = QLabel(" · ".join(meta_bits))
            sub.setWordWrap(True)
            lay.addWidget(sub)

        # `sentence` et `paragraph` sont souvent identiques, mais pas
        # toujours : le schema du registre permet une entree dont `sentence`
        # est vide et `paragraph` renseigne. Ne rien afficher dans ce cas
        # serait une perte gratuite d'un texte deja charge en memoire ;
        # `sentence` reste prioritaire quand les deux existent, c'est la
        # forme courte prevue pour cet usage.
        desc_text = record.sentence or record.paragraph
        if desc_text:
            desc = QLabel(desc_text)
            desc.setWordWrap(True)
            lay.addWidget(desc)

        foot = self._footer(arch)
        if foot:
            lbl = QLabel(" · ".join(foot))
            lbl.setWordWrap(True)
            lay.addWidget(lbl)

        self._apply_theme()

    def _badges(self, arch: str, in_use: bool) -> list[tuple[str, bool]]:
        s = lang_manager.current
        out: list[tuple[str, bool]] = []
        if in_use:
            out.append((s.lib_choice_badge_in_use, False))
        if is_retired(self.record):
            out.append((s.lib_choice_badge_retired, True))
        # Aucune revendication de compatibilite sans carte connue.
        if arch and not supports_arch(self.record, arch):
            out.append((s.lib_choice_badge_incompatible, True))
        return out

    def _footer(self, arch: str) -> list[str]:
        s = lang_manager.current
        bits: list[str] = []
        if arch and "*" in self.record.architectures:
            bits.append(s.lib_choice_meta_all_boards)
        if self.record.dependencies:
            bits.append(s.lib_choice_meta_requires.format(
                deps=", ".join(self.record.dependencies)))
        return bits

    # -- selection ------------------------------------------------------
    def is_selected(self) -> bool:
        return self._selected

    def set_selected(self, value: bool) -> None:
        self._selected = bool(value)
        self._apply_theme()

    def _apply_theme(self) -> None:
        self.setStyleSheet(card_qss(theme_manager.current,
                                    selected=self._selected))

    # -- entrees --------------------------------------------------------
    def mousePressEvent(self, ev):
        self.setFocus()
        self.picked.emit(self.record)
        super().mousePressEvent(ev)

    def keyPressEvent(self, ev):
        # Espace SEUL selectionne. Entree est reserve : aucun bouton de cette
        # modale n'est `default`, et valider reste un clic explicite (piege
        # documente sur les modales du cablage).
        if ev.key() == Qt.Key.Key_Space:
            self.picked.emit(self.record)
            ev.accept()
            return
        super().keyPressEvent(ev)


_MAX_CARDS = 60
"""Nombre de cards construites au maximum.

Le filtre rend TOUS les correspondants ; c'est l'affichage qui plafonne, parce
que « a » correspond a 9 824 bibliotheques et que construire 9 824 widgets
gelerait la fenetre. Le compte entier est ANNONCE (`lib_choice_count_capped`) :
un plafond muet se lirait « voila tout ce qui existe ».

60 est un point de depart. Le critere a tenir est un re-filtre complet sous
50 ms ; si 60 cards coutent plus sur une machine lente, baisser ce nombre.
"""


class _IndexLoader(QThread):
    """Charge l'index Arduino hors du fil d'interface (1,55 s mesurees).

    Jamais `terminate()` : le fil lance un sous-processus, et l'interrompre
    plante l'app (0xC0000409, deja paye). La modale se contente d'ignorer le
    signal si elle est fermee entre-temps.
    """

    done = pyqtSignal(list)

    def __init__(self, config_file: str | None, parent=None):
        super().__init__(parent)
        self._config_file = config_file

    def run(self):
        from .registry_lookup import fetch_library_index
        from .library_index import parse_index
        self.done.emit(parse_index(fetch_library_index(self._config_file)))


class LibChoiceDialog(QDialog):
    """Cards de bibliotheques, recherche au-dessus, filtre en memoire.

    Apres `exec()` :
      - `chosen_lib` porte le nom choisi, ou "" si l'utilisateur a annule ou
        n'a rien change ;
      - `clear_requested` est vrai si « Laisser l'app decider » etait
        selectionne (branche a la tache suivante). Sans ce drapeau, « efface mon
        choix » et « j'ai annule » rendraient la meme valeur.
      - `no_library_requested` est vrai si « Aucune bibliotheque » etait
        selectionne (TODO #51).

    ⛔ TROIS SORTIES, ET AUCUNE N'EST REDUCTIBLE AUX AUTRES. « Aucune » est
    une AFFIRMATION de l'utilisateur -- ce composant se pilote sans
    bibliotheque -- la ou « Laisser l'app decider » rend la main a la
    devinette et ou annuler ne change rien. Cette card s'est longtemps
    appelee « Laisser l'app decider » FAUTE DE POUVOIR representer
    l'affirmation dans les magasins ; elle existe depuis que
    `component_libs` a son 3e etat.

    Pas de parametre `lang` : les libelles viennent du i18n GLOBAL, donc la
    modale parle toujours la langue en vigueur.
    """

    def __init__(self, parent=None, *, token: str, current_lib: str,
                 alternatives: list[str], config_file: str | None = None,
                 arch: str = "", current_no_lib: bool = False):
        super().__init__(parent)
        self._token = token
        self._current = (current_lib or "").strip()
        self._config_file = config_file
        self._arch = (arch or "").strip()
        self._short = choices_for(self._current, alternatives)
        self._cards: list[_LibraryCard] = []
        self._picked: str = self._current
        self.chosen_lib: str = ""
        self.clear_requested: bool = False
        self.no_library_requested: bool = False
        self._clear_selected = False
        # Pre-selectionnee quand l'affirmation est DEJA enregistree : rouvrir
        # la modale doit montrer l'etat courant, pas repartir de zero -- c'est
        # ce que fait deja le badge « en usage » pour une lib nommee.
        self._none_selected = bool(current_no_lib)
        self._alive = True
        self._loader: _IndexLoader | None = None
        self.setMinimumWidth(520)
        self._build()
        self._start_loading()
        theme_manager.changed.connect(self._apply_theme)
        self._apply_theme()
        self._refresh()

    # -- construction ---------------------------------------------------
    def _build(self) -> None:
        s = lang_manager.current
        self.setWindowTitle(s.lib_choice_title)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        self._lbl_body = QLabel(s.lib_choice_body.format(
            part=self._token.upper(), lib=self._current or "—"))
        self._lbl_body.setTextFormat(Qt.TextFormat.RichText)
        self._lbl_body.setWordWrap(True)
        root.addWidget(self._lbl_body)

        self._search = QLineEdit(self._token)
        self._search.setPlaceholderText(s.lib_choice_search_placeholder)
        # Le ✕ vient du controle standard : rien a dessiner, rien a styler.
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(lambda _t: self._refresh())
        root.addWidget(self._search)

        self._lbl_count = QLabel("")
        self._lbl_count.setWordWrap(True)
        root.addWidget(self._lbl_count)

        # Epinglee HORS du bloc defilant : elle doit rester atteignable meme
        # sous 174 resultats. `arch=""` volontairement : ce n'est pas une vraie
        # bibliotheque, elle ne revendique aucune compatibilite.
        #
        # `record.name` est ici un LIBELLE TRADUIT (« Laisser l'app decider »
        # / "Let the app decide" / ...), pas le nom d'une bibliotheque -- ce
        # `LibraryRecord` est un habillage pour reutiliser `_LibraryCard`, pas
        # une entree du registre. Rien ne le compare aujourd'hui a un vrai nom
        # (self._card_clear vit hors de self._cards, cf. _refresh), mais un
        # futur code qui itererait `self._cards + [self._card_clear]` en
        # comparant des `.record.name` tomberait sur ce libelle localise, pas
        # sur un nom de lib -- a garder hors de tout classement/dedup de libs.
        self._card_clear = _LibraryCard(
            LibraryRecord(name=s.lib_choice_let_app_decide,
                          sentence=s.lib_choice_let_app_decide_hint),
            arch="", parent=self)
        self._card_clear.picked.connect(lambda _r: self._on_clear_picked())
        root.addWidget(self._card_clear)

        # La 3e sortie (TODO #51). Meme habillage `LibraryRecord` que sa
        # voisine, meme raison de vivre hors du bloc defilant : elle doit
        # rester atteignable sous n'importe quel nombre de resultats.
        self._card_none = _LibraryCard(
            LibraryRecord(name=s.lib_choice_no_library,
                          sentence=s.lib_choice_no_library_hint),
            arch="", parent=self)
        self._card_none.picked.connect(lambda _r: self._on_none_picked())
        self._card_none.set_selected(self._none_selected)
        root.addWidget(self._card_none)

        self._list_host = QWidget()
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(8, 8, 8, 8)
        self._list_layout.setSpacing(6)
        self._lbl_empty = QLabel("")
        self._lbl_empty.setWordWrap(True)
        self._lbl_empty.setVisible(False)
        self._list_layout.addWidget(self._lbl_empty)
        self._list_layout.addStretch(1)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setWidget(self._list_host)
        self._scroll.setMinimumHeight(260)
        root.addWidget(self._scroll, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch(1)
        self._btn_cancel = QPushButton(s.lib_choice_cancel)
        self._btn_ok = QPushButton(s.lib_choice_ok)
        self._btn_ok.setProperty("variant", "primary")
        for b in (self._btn_cancel, self._btn_ok):
            b.setAutoDefault(False)
            b.setDefault(False)
        self._btn_cancel.clicked.connect(self.reject)
        self._btn_ok.clicked.connect(self._on_ok)
        actions.addWidget(self._btn_cancel)
        actions.addWidget(self._btn_ok)
        root.addLayout(actions)

        if self._config_file is None:
            self._search.setEnabled(False)

    # -- chargement -----------------------------------------------------
    def _start_loading(self) -> None:
        if is_loaded() or self._config_file is None:
            return
        self._loader = _IndexLoader(self._config_file, self)
        self._loader.done.connect(self._on_index_loaded)
        self._loader.start()

    def _on_index_loaded(self, records: list) -> None:
        # La modale a pu se fermer pendant les 1,55 s : le fil finit tout seul
        # (jamais terminate()), on ignore simplement son resultat.
        if not self._alive:
            return
        set_index(records)
        self._refresh()

    def done(self, result: int) -> None:
        # LE chemin de fermeture reel : `accept()` (bouton OK) ET `reject()`
        # (bouton Annuler, Echap -- QDialog.keyPressEvent gere Echap en
        # appelant reject() par defaut, notre propre keyPressEvent ne
        # l'intercepte pas) appellent tous les deux `done()`. Verifie a la
        # main (2026-08-12) : ni accept() ni reject() ne passent par
        # `closeEvent` en PyQt6, seul le bouton natif « X » de la fenetre le
        # fait -- un `_alive` pose uniquement dans `closeEvent` ne protegeait
        # donc AUCUN des trois chemins de fermeture normaux de cette modale.
        self._alive = False
        super().done(result)

    def closeEvent(self, ev):
        # Filet en plus, pas le chemin principal : couvre le bouton natif
        # « X » sur les rares plateformes ou il ne route pas par `done()`.
        self._alive = False
        super().closeEvent(ev)

    # -- affichage ------------------------------------------------------
    def _records_to_show(self) -> tuple[list, int]:
        """(enregistrements affichables, total avant plafonnement)."""
        query = self._search.text().strip()
        if not query or not is_loaded():
            by_key = {norm_lib_name(r.name): r for r in index()}
            recs = [by_key.get(norm_lib_name(n)) or LibraryRecord(name=n)
                    for n in self._short]
            return recs, len(recs)
        matches = filter_libraries(index(), query)
        total = len(matches)
        capped = matches[:_MAX_CARDS]
        # La lib en usage passe en tete quand elle est dans le lot affiche,
        # meme resultat que la liste courte (elle y est deja premiere) --
        # sans ca, le depart-egalite de `filter_libraries` (auteur puis
        # longueur de nom) peut la releguer derriere une alternative plus
        # courte, alors que c'est elle que le badge « en usage » et le corps
        # de la modale mettent en avant. Trouve le 2026-08-12 : "Adafruit
        # AS7341" (15 caracteres) passait apres "DFRobot_AS7341" (14) sur la
        # seule requete "as7341", qui matche les deux a egalite de rang.
        #
        # Applique APRES le plafond, jamais avant : `norm_lib_name` n'est pas
        # mis en cache (contrairement a `norm_token` de library_index), et
        # balayer les 9 824 correspondants de la requete "a" pour n'en
        # epingler qu'un seul a double le temps d'un re-filtre (15 -> 42 ms,
        # mesure le 2026-08-12). Sur le lot deja plafonne (<= _MAX_CARDS), le
        # cout est negligeable. Limite assumee : si la lib en usage est
        # classee au-dela du plafond, elle n'apparait pas du tout -- deja
        # vrai avant cet epinglage, et un cas marginal (une lib normalement
        # bien classee pour son propre nom).
        if self._current:
            key = norm_lib_name(self._current)
            capped = ([r for r in capped if norm_lib_name(r.name) == key]
                      + [r for r in capped if norm_lib_name(r.name) != key])
        return capped, total

    def _refresh(self) -> None:
        s = lang_manager.current
        for card in self._cards:
            self._list_layout.removeWidget(card)
            # setParent(None) AVANT deleteLater : un widget retire du layout
            # mais toujours enfant reste VISIBLE et se peint (defaut paye le
            # 2026-08-12 sur le formulaire de declaration).
            card.setParent(None)
            card.deleteLater()
        self._cards = []

        recs, total = self._records_to_show()

        # Si la selection courante a disparu du lot affiche (une recherche
        # affinee peut l'exclure), aucune card ne la montre plus selectionnee
        # -- mais sans ce retour en arriere, `_on_ok` validerait quand meme
        # une bibliotheque INVISIBLE : l'utilisateur croit n'avoir rien
        # choisi et une preference s'ecrit. C'est la regle que l'ancien code
        # a QRadioButton portait dans `_clear_search_radios` (retire par la
        # Task 8) : quand la recherche efface le lot qui contenait le radio
        # coche, on re-coche la bibliotheque EN USAGE plutot que de laisser
        # une pastille arbitraire cochee ou de fabriquer un choix. Meme
        # raisonnement ici, applique aux cards : retombe sur `_current`,
        # jamais sur une alternative arbitraire. Et le meme cas limite :
        # quand `_current` est lui-meme vide, il n'y a pas d'incumbent sur
        # lequel retomber, donc `_picked` redevient "" -- que `_on_ok` rend
        # deja comme "l'utilisateur n'a rien decide", l'issue sure plutot
        # qu'un trou.
        # La card epinglee (« Laisser l'app decider ») n'est PAS dans `recs` --
        # elle vit hors du bloc defilant, cf. `_build`. Sans ce garde-fou, le
        # retour en arriere ci-dessous la traiterait comme une selection
        # devenue invisible et la remplacerait par `_current` : la card de la
        # bibliotheque en usage se peindrait selectionnee alors que la card
        # epinglee, elle, resterait selectionnee aussi (`_on_clear_picked` ne
        # touche pas a `self._cards`, qui n'existent pas encore ici) -- DEUX
        # cards selectionnees a la fois, ce qu'aucun bouton radio n'aurait
        # jamais permis.
        # `_none_selected` a exactement le meme statut que `_clear_selected`
        # ici : sa card vit hors de `recs`, donc la traiter comme « selection
        # devenue invisible » repeindrait DEUX cards selectionnees.
        if not self._clear_selected and not self._none_selected:
            visible_keys = {norm_lib_name(r.name) for r in recs}
            if norm_lib_name(self._picked) not in visible_keys:
                self._picked = self._current

        for i, rec in enumerate(recs):
            card = _LibraryCard(
                rec, arch=self._arch,
                in_use=norm_lib_name(rec.name) == norm_lib_name(self._current),
                parent=self._list_host)
            card.set_selected(
                not self._clear_selected and not self._none_selected
                and norm_lib_name(rec.name) == norm_lib_name(self._picked))
            card.picked.connect(self._on_card_picked)
            self._list_layout.insertWidget(i, card)
            self._cards.append(card)

        query = self._search.text().strip()
        if self._config_file is None:
            self._lbl_count.setText("")
            self._lbl_empty.setText(s.lib_choice_search_unavailable)
            self._lbl_empty.setVisible(True)
        elif not is_loaded():
            self._lbl_count.setText(s.lib_choice_loading)
            self._lbl_empty.setVisible(False)
        elif not query:
            self._lbl_count.setText("")
            self._lbl_empty.setVisible(False)
        elif not recs:
            self._lbl_count.setText("")
            self._lbl_empty.setText(s.lib_choice_search_empty.format(q=query))
            self._lbl_empty.setVisible(True)
        else:
            self._lbl_empty.setVisible(False)
            if total > len(recs):
                self._lbl_count.setText(s.lib_choice_count_capped.format(
                    total=total, shown=len(recs)))
            elif total == 1:
                self._lbl_count.setText(s.lib_choice_count_one)
            else:
                self._lbl_count.setText(s.lib_choice_count.format(n=total))

    def _on_card_picked(self, record) -> None:
        self._clear_selected = False
        self._none_selected = False
        self._card_clear.set_selected(False)
        self._card_none.set_selected(False)
        self._picked = record.name
        for card in self._cards:
            card.set_selected(card.record.name == record.name)

    def _on_clear_picked(self) -> None:
        self._clear_selected = True
        self._none_selected = False
        self._picked = ""
        self._card_clear.set_selected(True)
        self._card_none.set_selected(False)
        for card in self._cards:
            card.set_selected(False)

    def _on_none_picked(self) -> None:
        self._none_selected = True
        self._clear_selected = False
        self._picked = ""
        self._card_none.set_selected(True)
        self._card_clear.set_selected(False)
        for card in self._cards:
            card.set_selected(False)

    # -- clavier --------------------------------------------------------
    def keyPressEvent(self, ev):
        """↓ / ↑ deplacent le focus dans la liste, y compris depuis le champ
        de recherche (une QLineEdit d'une seule ligne n'utilise pas ces
        touches, donc elles remontent jusqu'ici)."""
        if ev.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self._cards:
            focused = [i for i, c in enumerate(self._cards) if c.hasFocus()]
            step = 1 if ev.key() == Qt.Key.Key_Down else -1
            nxt = (focused[0] + step) if focused else 0
            nxt = max(0, min(len(self._cards) - 1, nxt))
            self._cards[nxt].setFocus()
            self._scroll.ensureWidgetVisible(self._cards[nxt])
            ev.accept()
            return
        super().keyPressEvent(ev)

    # -- validation -----------------------------------------------------
    def _on_ok(self) -> None:
        if self._none_selected:
            # ⛔ Rendu AVANT `_clear_selected`, et les deux drapeaux sont
            # mutuellement exclusifs par construction (chaque handler eteint
            # l'autre). L'ordre n'est donc pas une precedence deguisee : c'est
            # une garde, pour qu'un futur chemin qui oublierait d'eteindre
            # l'autre drapeau echoue du cote sur -- affirmer ce que
            # l'utilisateur vient de cocher, plutot que l'effacer.
            self.no_library_requested = True
            self.chosen_lib = ""
            self.accept()
            return
        if self._clear_selected:
            # « Efface mon choix » et « j'ai annule » rendraient tous deux
            # chosen_lib == "" : c'est ce drapeau qui les distingue.
            self.clear_requested = True
            self.chosen_lib = ""
            self.accept()
            return
        picked = (self._picked or "").strip()
        self.chosen_lib = (
            "" if norm_lib_name(picked) == norm_lib_name(self._current)
            else picked)
        self.accept()

    def _apply_theme(self, *_) -> None:
        c = theme_manager.current
        p = self.palette()
        p.setColor(QPalette.ColorRole.Window, QColor(c.main_bg))
        self.setPalette(p)
        self.setAutoFillBackground(True)
        label_style = f"color: {c.text_primary}; background: transparent;"
        self._lbl_body.setStyleSheet(label_style)
        self._lbl_count.setStyleSheet(
            f"color: {c.text_secondary}; background: transparent;")
        self._lbl_empty.setStyleSheet(
            f"color: {c.text_secondary}; background: transparent;")
        self._list_host.setStyleSheet("background: transparent;")
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }")
        self._card_clear._apply_theme()
        self._card_none._apply_theme()
        for card in self._cards:
            card._apply_theme()

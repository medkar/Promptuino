"""Code IMBRIQUE entre deux fonctionnalites : l'ajout qui doit REAGIR a l'etat
d'une fonctionnalite existante (2026-08-31).

Mesure d'origine, chaine reelle de l'app (banc + arduino-cli) : quand la
nouvelle fonctionnalite doit se greffer sur la logique d'une autre, le modele
n'obeit PAS a la consigne << ne produis que les ajouts >> -- il relit l'entree
lui-meme et reemet la structure de controle avec ses lignes dedans. Mesure :
4 generations sur 4 (gemma4:e2b, conditions de l'app).

Deux defauts en decoulaient, tous deux verifies avant correction :

1. RECOLLE QUI INVERSE LA SEMANTIQUE. La deduplication supprimait le run
   `} else {` + son corps -- equilibre (net 0) donc juge supprimable -- et la
   ligne neuve qui suivait etait REPARENTEE du `else` vers le `if` : le
   `noTone()` atterrissait juste apres le `tone()`. Ca compile, la note ne
   joue jamais. Corruption silencieuse.
   -> Garde : on ne supprime qu'un run qui COMMENCE a la profondeur 0 du bloc
   emis (un enonce complet), jamais un fragment d'une structure englobante.

2. REDECLARATION QUI NE COMPILE PAS. Le modele redeclare la variable d'etat
   qu'il relit (`int etatBouton = ...`), et la regle << une ligne dupliquee
   ISOLEE est gardee >> (qui protege un `delay(1000);` partage) la laissait
   passer : deux declarations du meme nom dans le meme bloc,
   `redeclaration of 'int etatBouton'` a l'arduino-cli.
   -> Une declaration dupliquee est supprimee independamment des runs (elle
   ne porte aucune accolade, donc ne reparente rien). Sa suppression fait
   consommer celle du fournisseur : composition par etat partage.

3. Consequence de (2) : le consommateur depend desormais d'une LOCALE du
   fournisseur. `feature_links` ne connaissait que les globales -> aucun lien
   dessine, pas de solidarite de glisser, et rien n'empechait de remonter le
   consommateur au-dessus de son fournisseur (ne compile plus). Les locales
   de corps (profondeur 0) sont donc des `providers`.

⚠️ Les regles sont STRUCTURELLES (profondeur d'accolades, redeclaration dans
un meme bloc) : aucun composant, aucun mot-cle metier. Les cas ci-dessous
balayent exprès des familles differentes (bouton/buzzer, capteur analogique,
millis + for/switch, objet de bibliotheque).
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.generation.assembler import (  # noqa: E402
    _code_sig, _declares_local, _subtract_existing, assemble,
    clean_feature_contributions,
)
from ui.generation.feature_links import feature_deps, providers  # noqa: E402
from ui.generation.feature_model import Feature  # noqa: E402


def _sigs(lines):
    return {s for ln in lines if (s := _code_sig(ln))}


# ── 1. le predicat de declaration, forme GENERALE ────────────────────────

def test_the_declaration_predicate_is_a_shape_not_a_list():
    """Ni liste de composants, ni liste de types : deux identifiants separes
    par un espace, suivis de = ; [ ou (. Les mots de controle sont exclus,
    sinon `else if (x) {` passerait pour une declaration."""
    for line in ("int etat = digitalRead(2);", "float t = capteur.lire();",
                 "unsigned long debut = millis();", "Servo monServo;",
                 "DHT capteur(2, DHT11);", "static int compteur = 0;",
                 "const byte n = 4;", "String msg = \"x\";", "char buf[32];",
                 "uint8_t v = 0;", "int *p = &x;", "  long long gros = 1;"):
        assert _declares_local(line), line
    for line in ("delay(1000);", "digitalWrite(LED_BUILTIN, HIGH);",
                 "if (etat == LOW) {", "} else {", "else if (x > 3) {",
                 "for (int i = 0; i < 5; i++) {", "while (Serial.available()) {",
                 "switch (mode) {", "case 2:", "tone(PIN, 440);",
                 "Serial.println(v);", "capteur.read();", "return;",
                 "monServo.write(90);", "}", "x = y + 1;", "break;"):
        assert not _declares_local(line), line


# ── 2. la garde d'imbrication (reparentage) ──────────────────────────────

def test_a_nested_fragment_is_never_dropped():
    """Le defaut 1. Ici la structure de controle est un `if/else` sur un
    capteur analogique -- autre famille que celle du banc, meme mecanique."""
    existing = ["float mesure = analogRead(A0);", "if (mesure > 500) {",
                "  digitalWrite(7, HIGH);", "} else {",
                "  digitalWrite(7, LOW);", "}"]
    emitted = ["float mesure = analogRead(A0);", "if (mesure > 500) {",
               "  digitalWrite(7, HIGH);", "  tone(8, 440);", "} else {",
               "  digitalWrite(7, LOW);", "  noTone(8);", "}"]
    kept = _subtract_existing(emitted, _sigs(existing))
    texte = "\n".join(kept)
    # La ligne neuve du `else` doit RESTER dans le `else`.
    i_else, i_no = texte.index("} else {"), texte.index("noTone(8)")
    assert i_else < i_no, texte
    # ... et celle du `if` rester avant le `else`.
    assert texte.index("tone(8, 440)") < i_else, texte


def test_a_complete_top_level_block_is_still_deduplicated():
    """Non-regression du cas COURANT : le modele reemet le bloc entier d'une
    fonctionnalite PUIS ajoute le sien. Ce run-la commence a la profondeur 0
    et doit toujours disparaitre -- sinon la garde ferait doublonner tout."""
    existing = ["if (mode == 1) {", "  Serial.println(1);", "}"]
    emitted = existing + ["digitalWrite(5, HIGH);", "delay(20);"]
    assert _subtract_existing(emitted, _sigs(existing)) == [
        "digitalWrite(5, HIGH);", "delay(20);"]


def test_an_isolated_shared_call_is_still_kept():
    """L'autre non-regression : un `delay(1000);` legitimement partage par
    deux fonctionnalites n'est PAS une declaration -- il reste."""
    existing = ["delay(1000);"]
    assert _subtract_existing(["digitalWrite(3, HIGH);", "delay(1000);"],
                              _sigs(existing)) == ["digitalWrite(3, HIGH);",
                                                   "delay(1000);"]


# ── 3. la redeclaration ──────────────────────────────────────────────────

def test_a_duplicated_declaration_glued_to_its_structure_is_dropped():
    """Le defaut 2, et la raison de la passe SEPAREE : le modele colle la
    declaration a la structure qui la suit, donc le run
    [decl, `if (...) {`] est desequilibre (+1) et n'est jamais supprimable
    comme un tout -- la redeclaration survivait."""
    existing = ["unsigned long debut = millis();", "if (debut > 100) {",
                "  Serial.println(debut);", "}"]
    emitted = ["unsigned long debut = millis();", "if (debut > 100) {",
               "  digitalWrite(6, HIGH);", "}"]
    kept = _subtract_existing(emitted, _sigs(existing))
    assert not any(_declares_local(ln) for ln in kept), kept
    assert kept[0].strip().startswith("if"), kept


def test_a_library_object_redeclaration_is_dropped_too():
    """Meme regle pour un objet de bibliotheque declare dans un corps --
    la forme, pas une liste de types connus."""
    existing = ["Servo monServo;", "monServo.attach(9);"]
    kept = _subtract_existing(["Servo monServo;", "monServo.write(180);"],
                              _sigs(existing))
    assert kept == ["monServo.write(180);"], kept


def test_the_assembled_sketch_no_longer_redeclares():
    """Bout en bout, au niveau ou l'app le fait (clean + assemble)."""
    a = Feature(id="fn-1", prompt="a",
                loop_lines=["int lecture = analogRead(A0);",
                            "Serial.println(lecture);"])
    b = Feature(id="fn-2", prompt="b",
                loop_lines=["int lecture = analogRead(A0);",
                            "if (lecture > 800) {", "  digitalWrite(4, HIGH);",
                            "}"])
    code = assemble([a, clean_feature_contributions(b, [a])])
    assert code.count("int lecture") == 1, code


# ── 4. le graphe suit la dependance creee ────────────────────────────────

def test_a_body_local_is_a_provider():
    f = Feature(id="fn-1", prompt="a",
                loop_lines=["unsigned long horodatage = millis();",
                            "Serial.println(horodatage);"])
    assert "horodatage" in providers(f), providers(f)


def test_a_declaration_nested_in_a_block_provides_nothing():
    """Portee : une declaration dans un `if` du fournisseur n'est visible de
    personne -- meme regle de profondeur que la garde d'imbrication."""
    f = Feature(id="fn-1", prompt="a",
                loop_lines=["if (x > 1) {", "  int cache = 42;", "}"])
    assert "cache" not in providers(f), providers(f)


def test_the_consumer_depends_on_the_provider_of_the_local():
    """Sans ce lien : aucun trait dessine, pas de solidarite de glisser, et
    rien n'empeche de remonter le consommateur au-dessus de son fournisseur
    -- ce qui ne compile plus."""
    a = Feature(id="fn-1", prompt="a",
                loop_lines=["int lecture = analogRead(A0);",
                            "Serial.println(lecture);"])
    b = Feature(id="fn-2", prompt="b",
                loop_lines=["if (lecture > 800) {", "  digitalWrite(4, HIGH);",
                            "}"])
    deps = feature_deps([a, b])
    assert deps["fn-2"] == {"fn-1"}, deps
    assert deps["fn-1"] == set(), deps


TESTS = [
    test_the_declaration_predicate_is_a_shape_not_a_list,
    test_a_nested_fragment_is_never_dropped,
    test_a_complete_top_level_block_is_still_deduplicated,
    test_an_isolated_shared_call_is_still_kept,
    test_a_duplicated_declaration_glued_to_its_structure_is_dropped,
    test_a_library_object_redeclaration_is_dropped_too,
    test_the_assembled_sketch_no_longer_redeclares,
    test_a_body_local_is_a_provider,
    test_a_declaration_nested_in_a_block_provides_nothing,
    test_the_consumer_depends_on_the_provider_of_the_local,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()

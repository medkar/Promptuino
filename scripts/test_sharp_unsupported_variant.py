"""Une variante que la bibliotheque ne couvre pas (2026-09-09).

Spec : docs/superpowers/specs/2026-09-09-variante-sharp-non-supportee-design.md

Contexte. La bibliotheque `SharpIR` ne convertit que TROIS modeles, et
l'utilisateur peut en tenir un quatrieme dans la main -- il cite lui-meme le
GP2Y0A51SK (2-15 cm) parmi les trois qu'on trouve en pratique. Recouvrement
avec la bibliotheque : deux sur trois.

⛔ ET `getDistance()` EST UN `switch` SANS `default`, sur une variable NON
INITIALISEE (lu dans `SharpIR.cpp` v2.0.1). Un modele hors des trois ne
produit donc pas une erreur : il produit une VALEUR INDETERMINEE, en silence.
C'est exactement la panne muette que ce projet existe pour supprimer.

Choix produit (utilisateur, 2026-09-09) : ne rien imposer plutot qu'imposer
une constante voisine. « Un super modele pourra peut-etre ecrire du code
fonctionnel quand meme et un petit modele ne pourra probablement pas, mais au
moins l'utilisateur est averti que son code risque d'etre faux. »

Run : python scripts/test_sharp_unsupported_variant.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import io
import json
import contextlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)
# Widgets retenus : un widget sans parent ramasse par le GC tue le process.
_VIVANTS: list = []

from ui import rag
from ui.i18n import lang_manager


def _contexte(prompt: str) -> str:
    """Contexte RAG, sans les diagnostics `[RAG] …` sur la sortie."""
    with contextlib.redirect_stdout(io.StringIO()):
        ctx, _ = rag._build_lib_context(prompt)
    return ctx or ""


def test_the_three_supported_models_come_from_the_header():
    """⛔ La liste est LUE, pas supposee -- c'est ce qui rend la regle
    categorielle plutot qu'un jugement.

    ⚠️ DEUX bibliotheques depuis le 2026-09-09, et la question n'est plus
    « que gere SharpIR ? » mais « que l'app sait-elle piloter ? » :
        SharpIR.h v2.0.1        : GP2Y0A41SK0F, GP2Y0A21YK0F, GP2Y0A02YK0F
        SharpDistSensor.h v1.6  : GP2Y0A51SK0F, GP2Y0A41SK0F, GP2Y0A21F,
                                  GP2Y0A60SZLF, GP2Y0A710K0F
    L'union fait SIX modeles, et les six ont un type depuis le 2026-09-09. Les deux listes sont LUES dans
    les en-tetes, pas supposees.

    ⛔ Ma mesure du 2026-09-09 -- « aucune bibliotheque ne gere le A51, index
    entier balaye, zero » -- etait FAUSSE : j'avais balaye les METADONNEES du
    registre, alors que la liste des modeles vit dans l'EN-TETE des sources.
    """
    assert rag._SUPPORTED_SHARP_MODELS == frozenset(
        {"21", "41", "02", "51", "60", "710"})
    corpus = json.loads((ROOT / "assets" / "rag" / "corpus.json")
                        .read_text(encoding="utf-8"))
    e = next(x for x in corpus if x["id"] == "sharpir")
    sigs = " ".join(e["api_signatures"]["SharpIR"])
    # Le corpus et la regle doivent nommer les MEMES trois modeles : si l'un
    # bouge sans l'autre, on injecterait une constante qu'on declare
    # non supportee, ou l'inverse.
    for n in ("41", "21", "02"):
        assert f"GP2Y0A{n}" in sigs, n
    assert "GP2Y0A700" not in sigs


def test_only_an_unsupported_named_model_triggers():
    """Les trois branches de la regle, dans l'ordre ou elles se decident."""
    # (a) hors des trois -> variante
    # ⚠️ Le GP2Y0A700K0F (1-5,5 m) remplace ici le A51, qui est SUPPORTE
    # depuis l'ajout de `SharpDistSensor` : aucune des deux bibliotheques du
    # corpus ne porte sa courbe.
    # ⚠️ Le GP2Y0A700K0F (1-5,5 m) : un modele REEL que NI l'une NI l'autre
    # bibliotheque ne porte. Le A710, lui, est desormais supporte -- ne pas
    # les confondre, leurs numeros ne different que d'un chiffre.
    for p in ("un capteur de distance GP2Y0A700K0F sur A0",
              "un capteur 2Y0A700 sur A0"):
        assert rag.unsupported_sharp_model(p) == "GP2Y0A700", p
    # (b) dans les trois -> rien
    for p in ("un capteur GP2Y0A21YK0F sur A0", "un capteur 2Y0A41 sur A0",
              "un capteur GP2Y0A02 sur A0", "un capteur 2Y0A21 F 7X sur A0",
              "un capteur GP2Y0A51SK0F sur A0",
              "un capteur GP2Y0A60SZLF sur A0",
              "un capteur GP2Y0A710K0F sur A0"):
        assert rag.unsupported_sharp_model(p) == "", p
    # (c) aucun modele nomme -> rien, et c'est VOULU : l'exemple officiel
    #     montre les trois constantes et rend le choix visible dans le code.
    #     Supprimer l'injection ici punirait le cas courant.
    for p in ("un telemetre infrarouge sur A0", "an IR distance sensor on A0",
              "fais clignoter une led"):
        assert rag.unsupported_sharp_model(p) == "", p


def test_the_library_is_suppressed_and_the_directive_takes_its_place():
    """⛔ Le coeur. Mesure du 2026-09-09 AVANT correctif complet : filtrer
    `sharpir` ne suffisait pas -- le retrieval remontait alors un ALTIMETRE
    (MPL3115A2) et la consigne ne partait jamais, donc on avait remplace une
    mauvaise bibliotheque par une autre, en silence. La consigne s'ajoute
    desormais a TOUT ce qui reste, et en dernier.
    """
    for p in ("un capteur de distance GP2Y0A700K0F sur A0",
              "un capteur 2Y0A700 sur A0"):
        ctx = _contexte(p)
        assert "Unsupported sensor variant" in ctx, p
        assert "GP2Y0A700" in ctx, p
        # La bibliotheque elle-meme ne doit PAS etre presentee comme a suivre.
        assert "Headers: `SharpIR.h`" not in ctx, p
    # Le modele supporte, lui, la recoit toujours.
    ctx = _contexte("un capteur de distance GP2Y0A21YK0F sur A0")
    assert "SharpIR.h" in ctx
    assert "Unsupported sensor variant" not in ctx


def test_the_directive_invents_no_coefficient():
    """⚠️ Elle dit la FORME de la solution, jamais un chiffre.

    On ne connait pas la courbe de ce modele. Donner une formule qui aurait
    l'air juste serait exactement le defaut qu'on corrige -- et c'est le
    reflexe qu'un modele de langage a naturellement.
    """
    d = rag._unsupported_sharp_directive("GP2Y0A700")
    assert "analogRead" in d and "calibrat" in d.lower()
    assert "NON-LINEAR" in d
    assert "do NOT invent conversion" in d.lower().replace("do not", "do NOT")
    # Aucune constante de conversion : les seuls chiffres tolerés sont les
    # noms de modele eux-memes.
    import re
    nombres = re.findall(r"\b\d+(?:\.\d+)?\b", d.replace("GP2Y0A", " "))
    assert not [n for n in nombres if n not in {"41", "21", "02", "51", "700", "60", "710", "5", "2"}], (
        f"des coefficients ont ete inventes : {nombres}")


def test_the_banner_does_not_borrow_the_lying_message():
    """⛔ « Aucun composant reconnu » serait FAUX ici : l'app a parfaitement
    reconnu le composant, c'est la BIBLIOTHEQUE qui ne couvre pas ce modele.

    Meme discipline que le cas « composant declare », laisse muet plutot que
    d'emprunter un message qui mentirait.
    """
    from ui.studio_view import StudioView
    v = StudioView()
    _VIVANTS.append(v)
    for lg in ("fr", "en", "es", "it"):
        lang_manager.set_language(lg)
        s = lang_manager.current
        v._sharp_variant = "GP2Y0A700"
        v._last_resemblance = False
        v._maybe_resemblance_banner(action="ADD", from_scratch=True,
                                    has_targets=False)
        texte = v._registry_banner._lbl.text()
        assert not v._registry_banner.isHidden(), lg
        assert "GP2Y0A700" in texte, (lg, texte)
        assert s.rag_guess_by_resemblance[:25] not in texte, (
            f"[{lg}] la banniere emprunte « aucun composant reconnu », "
            f"qui serait faux ici")
        assert v._registry_banner._btn2.text() == s.registry_ask_chat, lg
    lang_manager.set_language("fr")
    # Modele supporte : aucune banniere.
    v._sharp_variant = ""
    v._registry_banner.setVisible(False)
    v._maybe_resemblance_banner(action="ADD", from_scratch=True,
                                has_targets=False)
    assert v._registry_banner.isHidden()


def test_the_button_carries_its_own_explanation():
    """⛔ MESURE QUI A INVALIDE UNE PARTIE DU PLAN (2026-09-09).

    Le plan disait : « la question envoyee au chat doit etre FIXE, et ses
    mots dans les `aliases`, pour que la recuperation BM25 soit
    deterministe ». Mesure : elle ne l'est pas, et ne peut pas l'etre.
    L'entree corpus `sharpir` decrit LE MEME capteur, avec un document bien
    plus court -- or BM25 normalise par la longueur. Sur la question FR
    complete, `sharpir` sort a 30,9 et l'entree piege n'est meme pas dans les
    six premieres. Et `_SLM_TOP_K` vaut **1** : avec un modele local, une
    seule entree est recuperee.

    Le bouton n'en a pas besoin. `chat_help_requested` porte un
    `system_extras` qui va DIRECTEMENT au modele : l'explication est livree
    par construction, sans rien parier sur un classement. C'est cette
    garantie-la qu'on verrouille.
    """
    from ui.studio_view import StudioView
    v = StudioView()
    _VIVANTS.append(v)
    recu: list = []
    v.chat_help_requested.connect(lambda p_, e_: recu.append((p_, e_)))
    for lg in ("fr", "en", "es", "it"):
        lang_manager.set_language(lg)
        recu.clear()
        v._sharp_variant = "GP2Y0A700"
        v._on_banner_help_requested()
        assert recu, lg
        question, extras = recu[-1]
        assert "GP2Y0A700" in question, (lg, question)
        # Les faits qui comptent voyagent avec le bouton, pas par le hasard.
        for attendu in ("GP2Y0A41SK0F", "GP2Y0A21YK0F", "GP2Y0A02YK0F",
                        "SANS default", "serigraphie", "code de DATE"):
            assert attendu in extras, (lg, attendu)
        assert "N'invente AUCUN coefficient" in extras, lg
    lang_manager.set_language("fr")


def test_the_trap_entry_is_reachable_when_asked_spontaneously():
    """L'entree `hardware_trap` sert l'utilisateur qui pose la question
    LUI-MEME -- « que veut dire 2Y0A21 F 7X sur mon capteur ? ». C'est la
    qu'elle gagne, et c'est mesure : rang 1, donc atteinte meme avec un
    modele local (`_SLM_TOP_K = 1`).

    ⚠️ On n'exige PAS le rang 1 sur les formulations ou l'entree corpus
    `sharpir` decrit legitimement le meme capteur : lui disputer la place
    serait chasser un classement, pas corriger un defaut.
    """
    from ui.chat.chat_rag import (CorpusIndex, load_default_corpus,
                                  load_concepts)
    index = CorpusIndex.from_entries(load_default_corpus() + load_concepts())
    for q in ("que veut dire 2Y0A21 F 7X sur mon capteur ?",
              "what does 2Y0A21 F 81 mean on my sensor?"):
        ids = [h.entry.get("id") for h in index.query(q, top_k=1)]
        assert ids == ["sharp-gp2y0a-variantes"], (q, ids)
    # Et dans les trois premieres sur les formulations plus vagues.
    for q in ("comment lire la serigraphie de mon capteur Sharp ?",
              "mon capteur Sharp GP2Y0A51 n'est pas supporte"):
        ids = [h.entry.get("id") for h in index.query(q, top_k=3)]
        assert "sharp-gp2y0a-variantes" in ids, (q, ids)


def test_the_trap_entry_says_what_the_user_must_do():
    """Les faits actionnables, pas seulement le constat."""
    entries = json.loads((ROOT / "assets" / "rag" / "concepts.json")
                         .read_text(encoding="utf-8"))
    e = next(x for x in entries if x["id"] == "sharp-gp2y0a-variantes")
    assert e["category"] == "hardware_trap"
    # Le routage du chat est STRUCTUREL : une entree compte comme concept
    # parce qu'elle PORTE `summary` ou `facts`, jamais par sa categorie.
    from ui.chat.chat_prompts import _is_concept_entry
    assert _is_concept_entry(e)
    faits = " ".join(e["facts"])
    # ⚠️ La regle de lecture est « 2 OU 3 chiffres » depuis le 2026-09-09 :
    # le GP2Y0A710 en a trois, et la version a deux le tronquait en `2Y0A71`.
    assert "2Y0A" in faits and "TWO OR THREE DIGITS" in faits, "la regle de lecture"
    assert "no default" in faits.lower()
    # Les DEUX bibliotheques, et qui couvre quoi -- c'est le piege desormais.
    assert "SharpIR" in faits and "SharpDistSensor" in faits
    assert "2Y0A710" in faits and "2Y0A60" in faits
    assert "date" in faits.lower(), "le decodage du code de date"
    # Les deux ecritures sont des alias : le hit ne depend pas de la langue.
    alias = {a.lower() for a in e["aliases"]}
    assert {"gp2y0a51", "2y0a51", "gp2y0a21", "2y0a21"} <= alias


def test_the_two_sharp_patterns_agree():
    """`rag.py` recopie le motif de `markers.py` -- la copie est ASSUMEE
    (`rag` ne doit pas dependre du paquet cablage) mais elle doit rester
    vraie. Deux motifs qui divergent, c'est un composant dessine et une
    bibliotheque supprimee sur des criteres differents."""
    from ui.wiring.markers import _SHARP_MODEL_RE as motif_cablage
    assert rag._SHARP_MODEL_RE.pattern == motif_cablage.pattern


TESTS = [
    test_the_three_supported_models_come_from_the_header,
    test_only_an_unsupported_named_model_triggers,
    test_the_library_is_suppressed_and_the_directive_takes_its_place,
    test_the_directive_invents_no_coefficient,
    test_the_banner_does_not_borrow_the_lying_message,
    test_the_button_carries_its_own_explanation,
    test_the_trap_entry_is_reachable_when_asked_spontaneously,
    test_the_trap_entry_says_what_the_user_must_do,
    test_the_two_sharp_patterns_agree,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"OK   {t.__name__}", flush=True)
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}", flush=True)
    print(f"\n{passed}/{len(TESTS)} tests passed", flush=True)
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)

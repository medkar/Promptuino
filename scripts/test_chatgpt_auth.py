"""Connexion << Sign in with ChatGPT >> -- module pur (TODO #122).

Aucun reseau vers OpenAI, aucun VRAI trousseau : le point de jeton et le
trousseau sont des bouchons. Le retour local, lui, est REEL (un serveur sur
127.0.0.1) : c'est la piece qu'un bouchon ne prouverait pas, et le << faux
navigateur >> des tests l'appelle comme le ferait le vrai.

Les noms de parametres, URL et portees sont ceux de la doc officielle
(developers.openai.com/siwc/token-sharing-open-source/sign-in, lue le
2026-11-06) : un test qui les verrouille rougira si quelqu'un les << corrige >>
de memoire.

Run: python scripts/test_chatgpt_auth.py
"""
from __future__ import annotations

import base64
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui.chatgpt_auth as auth  # noqa: E402

PAGE = "<p>Connexion reussie, revenez dans Promptuino.</p>"


def _jwt(claims: dict) -> str:
    def b64(o):
        return base64.urlsafe_b64encode(json.dumps(o).encode()).rstrip(b"=").decode()
    return f"{b64({'alg': 'RS256'})}.{b64(claims)}.signature-non-verifiee"


class _Coffre:
    """Le trousseau, en memoire."""

    def __init__(self, contenu=None):
        self.contenu = contenu

    def lire(self):
        return self.contenu

    def ecrire(self, texte):
        self.contenu = texte

    def effacer(self):
        self.contenu = None


class _PointDeJeton:
    """Le point de jeton d'OpenAI, en bouchon. `reponse(form)` decide."""

    def __init__(self, reponse):
        self.reponse = reponse
        self.formulaires = []

    def __call__(self, url, formulaire, timeout):
        assert url == auth.TOKEN_URL, url
        self.formulaires.append(dict(formulaire))
        return self.reponse(formulaire)


def _navigateur(params_retour=None, *, garder_nonce=True, attente=0.05):
    """Un faux navigateur : lit l'URL d'autorisation, puis APPELLE le vrai
    retour local avec ce qu'aurait renvoye OpenAI."""
    vu = {}

    def ouvrir(url):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        vu.update(q)
        retour = {"code": "code-123", "state": q["state"],
                  "client_id": "client-attribue-1"}
        retour.update(params_retour or {})
        retour = {k: v for k, v in retour.items() if v is not None}

        def appeler():
            time.sleep(attente)
            cible = q["redirect_uri"] + "?" + urllib.parse.urlencode(retour)
            with urllib.request.urlopen(cible, timeout=5) as r:
                vu["page_statut"] = r.status
                vu["page"] = r.read().decode("utf-8")
        # Le fil est GARDE : `connecter` rend la main des que le serveur a
        # repondu, sans attendre que ce faux navigateur ait fini de LIRE la
        # reponse. Un test qui affirme sur `page_statut` doit donc joindre ce
        # fil -- cf. `_attendre_la_page`.
        fil = threading.Thread(target=appeler, daemon=True)
        vu["_fil"] = fil
        fil.start()
    return ouvrir, vu


def _attendre_la_page(vu, delai=5):
    """Attend que le faux navigateur ait lu la page de retour.

    ⛔ Sans ca, affirmer sur `vu["page_statut"]` est une COURSE, et elle
    tombait : mesuree le 2026-11-09 sur 40 connexions reussies, le statut
    etait 200 trente-neuf fois et **absent** une fois, **jamais mauvais** --
    donc le defaut etait dans le test, pas dans l'application. Au hasard du
    cadencement, la suite entiere rougissait environ une fois sur douze, ce
    qui est bien pire qu'un echec franc : elle a ete declaree verte deux fois
    de suite juste avant, par chance.
    """
    fil = vu.get("_fil")
    if fil is not None:
        fil.join(delai)


def _jetons(vu, *, scope=None, email="eleve@example.com", nonce=None):
    def reponse(form):
        return 200, {
            "access_token": "acces-1", "refresh_token": "renouv-1",
            "id_token": _jwt({"email": email, "nonce": nonce or vu.get("nonce"),
                              "iss": "https://auth.openai.com"}),
            "token_type": "Bearer", "expires_in": 3600,
            "scope": scope or ("chatgpt.tokens.use.direct email offline_access "
                               "openid profile resource.invoke"),
        }
    return reponse


def _session(coffre=None, point=None, horloge=None):
    return auth.Session(coffre=coffre or _Coffre(),
                        poster=point or (lambda u, f, t: (500, {})),
                        horloge=horloge or time.time)


# ── PKCE et URL d'autorisation ────────────────────────────────────────────

def test_pkce_matches_the_rfc_7636_vector():
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    v, c = auth.pkce(verifier)
    assert v == verifier
    assert c == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM", c
    v2, c2 = auth.pkce()
    assert 43 <= len(v2) <= 128 and v2 != v


def test_the_first_authorization_registers_the_client():
    url = auth.url_autorisation(
        client_id=None, host_id="urn:uuid:h", redirect_uri="http://127.0.0.1:5555/auth/callback",
        challenge="c", state="s", nonce="n", id_token_hint=None, login_hint=None)
    base, q = url.split("?", 1)
    q = dict(urllib.parse.parse_qsl(q))
    assert base == "https://auth.openai.com/api/accounts/authorize", base
    assert q["client_id"] == "dynamic_agent_client"
    assert q["agent_name_hint"] == "Promptuino"
    assert q["ext_agent_host_id"] == "urn:uuid:h"
    assert q["response_type"] == "code"
    assert q["scope"] == ("openid profile email offline_access "
                          "resource.invoke chatgpt.tokens.use.direct"), q["scope"]
    assert q["resource"] == "https://api.openai.com/v1"
    assert q["code_challenge_method"] == "S256" and q["code_challenge"] == "c"
    assert q["state"] == "s" and q["nonce"] == "n"
    assert "id_token_hint" not in q and "login_hint" not in q


def test_a_reauthorization_reuses_the_client_and_names_the_account():
    url = auth.url_autorisation(
        client_id="client-attribue-1", host_id="urn:uuid:h",
        redirect_uri="http://127.0.0.1:5555/auth/callback", challenge="c",
        state="s", nonce="n", id_token_hint="ancien.jeton.id", login_hint="eleve@example.com")
    q = dict(urllib.parse.parse_qsl(url.split("?", 1)[1]))
    assert q["client_id"] == "client-attribue-1"
    assert "agent_name_hint" not in q, "seulement a l'enregistrement"
    assert q["id_token_hint"] == "ancien.jeton.id"
    assert q["login_hint"] == "eleve@example.com"


# ── le parcours complet, retour local REEL ───────────────────────────────

def test_a_full_sign_in_saves_the_account_and_the_issued_client():
    ouvrir, vu = _navigateur()
    point = _PointDeJeton(lambda f: _jetons(vu)(f))
    coffre = _Coffre()
    r = _session(coffre, point).connecter(ouvrir, page_html=PAGE, delai=10)
    assert r["ok"], r
    assert r["email"] == "eleve@example.com" and r["forfait"] is True, r
    # le retour local : 127.0.0.1, jamais localhost ; le chemin documente
    assert vu["redirect_uri"].startswith("http://127.0.0.1:"), vu["redirect_uri"]
    assert vu["redirect_uri"].endswith("/auth/callback"), vu["redirect_uri"]
    _attendre_la_page(vu)
    assert vu.get("page_statut") == 200, vu.get("page_statut")
    assert "Promptuino" in vu.get("page", ""), vu.get("page", "")[:200]
    # l'echange
    f = point.formulaires[0]
    assert f["grant_type"] == "authorization_code" and f["code"] == "code-123"
    assert f["client_id"] == "client-attribue-1", "l'identifiant ATTRIBUE, pas le dynamique"
    assert f["redirect_uri"] == vu["redirect_uri"]
    assert f["resource"] == "https://api.openai.com/v1"
    assert auth.pkce(f["code_verifier"])[1] == vu["code_challenge"]
    # le coffre
    rec = json.loads(coffre.contenu)
    assert rec["client_id"] == "client-attribue-1"
    assert rec["refresh_token"] == "renouv-1" and rec["access_token"] == "acces-1"
    assert rec["host_id"].startswith("urn:uuid:")


def test_a_wrong_state_is_refused_and_nothing_is_saved():
    ouvrir, vu = _navigateur({"state": "etat-forge"})
    coffre = _Coffre()
    r = _session(coffre, _PointDeJeton(lambda f: (200, {}))).connecter(ouvrir, page_html=PAGE, delai=10)
    assert not r["ok"] and r["erreur"] == "etat", r
    assert coffre.contenu is None or "access_token" not in coffre.contenu


def test_a_refusal_by_the_user_is_reported():
    ouvrir, vu = _navigateur({"code": None, "error": "access_denied"})
    r = _session().connecter(ouvrir, page_html=PAGE, delai=10)
    assert not r["ok"] and r["erreur"] == "refus", r


def test_a_wrong_nonce_is_refused():
    ouvrir, vu = _navigateur()
    point = _PointDeJeton(lambda f: _jetons(vu, nonce="autre-nonce")(f))
    r = _session(point=point).connecter(ouvrir, page_html=PAGE, delai=10)
    assert not r["ok"] and r["erreur"] == "nonce", r


def test_signed_in_without_plan_usage_is_said_so():
    ouvrir, vu = _navigateur()
    point = _PointDeJeton(lambda f: _jetons(vu, scope="openid profile email offline_access")(f))
    r = _session(point=point).connecter(ouvrir, page_html=PAGE, delai=10)
    assert r["ok"] and r["forfait"] is False, r


def test_a_failed_exchange_carries_the_reason():
    ouvrir, vu = _navigateur()
    point = _PointDeJeton(lambda f: (400, {"error": "invalid_grant",
                                           "error_description": "code expired"}))
    r = _session(point=point).connecter(ouvrir, page_html=PAGE, delai=10)
    assert not r["ok"] and r["erreur"] == "echange" and "code expired" in r["message"], r


def test_cancelling_stops_the_wait():
    debut = time.time()
    r = _session().connecter(lambda url: None, page_html=PAGE, delai=30,
                             annule=lambda: time.time() - debut > 0.3)
    assert not r["ok"] and r["erreur"] == "annule", r
    assert time.time() - debut < 5


def test_a_reconnection_keeps_the_client_when_the_callback_omits_it():
    coffre = _Coffre(json.dumps({"host_id": "urn:uuid:h", "client_id": "client-attribue-1",
                                 "email": "eleve@example.com"}))
    ouvrir, vu = _navigateur({"client_id": None})
    point = _PointDeJeton(lambda f: _jetons(vu)(f))
    r = _session(coffre, point).connecter(ouvrir, page_html=PAGE, delai=10)
    assert r["ok"], r
    assert vu["client_id"] == "client-attribue-1" and "agent_name_hint" not in vu
    assert vu["ext_agent_host_id"] == "urn:uuid:h", "l'identifiant de machine est STABLE"
    assert point.formulaires[0]["client_id"] == "client-attribue-1"


# ── le jeton et son renouvellement ───────────────────────────────────────

def _enregistrement(expire_dans, maintenant=1_000_000.0):
    return json.dumps({"host_id": "urn:uuid:h", "client_id": "client-attribue-1",
                       "email": "eleve@example.com", "id_token": "id",
                       "access_token": "acces-1", "refresh_token": "renouv-1",
                       "expires_at": maintenant + expire_dans,
                       "scopes": ["chatgpt.tokens.use.direct"]})


def test_a_valid_token_is_returned_without_network():
    point = _PointDeJeton(lambda f: (500, {}))
    s = _session(_Coffre(_enregistrement(3000)), point, horloge=lambda: 1_000_000.0)
    assert s.jeton() == "acces-1" and point.formulaires == []


def test_an_expiring_token_is_renewed_and_the_new_refresh_token_kept():
    point = _PointDeJeton(lambda f: (200, {"access_token": "acces-2", "refresh_token": "renouv-2",
                                           "expires_in": 3600, "scope": "chatgpt.tokens.use.direct"}))
    coffre = _Coffre(_enregistrement(30))
    s = _session(coffre, point, horloge=lambda: 1_000_000.0)
    assert s.jeton() == "acces-2"
    f = point.formulaires[0]
    assert f["grant_type"] == "refresh_token" and f["refresh_token"] == "renouv-1"
    assert f["client_id"] == "client-attribue-1"
    rec = json.loads(coffre.contenu)
    assert rec["refresh_token"] == "renouv-2", "le jeton de renouvellement TOURNE"
    assert rec["expires_at"] == 1_000_000.0 + 3600


def test_a_network_failure_during_renewal_keeps_the_credentials():
    """<< Don't erase credentials because of a temporary network failure >>."""
    coffre = _Coffre(_enregistrement(30))
    s = _session(coffre, _PointDeJeton(lambda f: (None, {})), horloge=lambda: 1_000_000.0)
    assert s.jeton() is None
    assert json.loads(coffre.contenu)["refresh_token"] == "renouv-1"


def test_a_refused_renewal_signs_out_but_keeps_the_registration():
    coffre = _Coffre(_enregistrement(30))
    s = _session(coffre, _PointDeJeton(lambda f: (400, {"error": "invalid_grant"})),
                 horloge=lambda: 1_000_000.0)
    assert s.jeton() is None
    rec = json.loads(coffre.contenu)
    assert "refresh_token" not in rec and "access_token" not in rec
    assert rec["client_id"] == "client-attribue-1" and rec["host_id"] == "urn:uuid:h"
    assert s.compte() is None


def test_signing_out_keeps_the_registration_only():
    coffre = _Coffre(_enregistrement(3000))
    s = _session(coffre)
    assert s.compte() == {"email": "eleve@example.com", "forfait": True}
    s.deconnecter()
    rec = json.loads(coffre.contenu)
    assert set(rec) == {"host_id", "client_id"}, rec
    assert s.compte() is None


def test_a_corrupted_record_reads_as_signed_out():
    s = _session(_Coffre("{pas du json"))
    assert s.compte() is None and s.jeton() is None


# ── Le trousseau Windows et sa limite (audit du 2026-11-06) ──────────────
# Mesure sur cette machine : le Gestionnaire d'identifiants refuse une entree
# de plus de 1 280 caracteres (CredWrite, erreur 1783). Un enregistrement
# avec les trois jetons d'OpenAI la depasse : sans decoupage, la connexion
# etait perdue aussitot ecrite, et l'ecran disait « non connecte ».

class _TrousseauLimite:
    """Un faux module `keyring` qui refuse, comme Windows, au-dela de 1 280."""
    LIMITE = 1280

    def __init__(self, refuse_tout=False):
        self.entrees, self.refuse_tout = {}, refuse_tout

    def set_password(self, service, nom, texte):
        if self.refuse_tout or len(texte) > self.LIMITE:
            raise OSError(1783, "CredWrite")
        self.entrees[(service, nom)] = texte

    def get_password(self, service, nom):
        return self.entrees.get((service, nom))

    def delete_password(self, service, nom):
        if (service, nom) not in self.entrees:
            raise KeyError(nom)
        del self.entrees[(service, nom)]


def _coffre_reel(kr):
    c = auth._CoffreTrousseau()
    c._kr = kr
    return c


def test_a_record_larger_than_the_windows_limit_survives():
    kr = _TrousseauLimite()
    c = _coffre_reel(kr)
    gros = json.dumps({"access_token": "a" * 2500, "id_token": "b" * 1800,
                       "refresh_token": "c" * 300})
    c.ecrire(gros)
    assert c.lire() == gros
    assert all(len(v) <= kr.LIMITE for v in kr.entrees.values())
    assert c._memoire is None, "rien ne doit rester en memoire seule"


def test_a_smaller_record_leaves_no_stale_part_behind():
    kr = _TrousseauLimite()
    c = _coffre_reel(kr)
    c.ecrire("x" * 6000)
    c.ecrire('{"host_id": "h"}')
    assert c.lire() == '{"host_id": "h"}'
    assert len(kr.entrees) == 1, kr.entrees.keys()


def test_erasing_removes_every_part():
    kr = _TrousseauLimite()
    c = _coffre_reel(kr)
    c.ecrire("y" * 6000)
    c.effacer()
    assert kr.entrees == {} and c.lire() is None


def test_a_refused_write_still_works_for_the_session():
    """Le repli en memoire n'etait jamais RELU quand `keyring` existait."""
    c = _coffre_reel(_TrousseauLimite(refuse_tout=True))
    c.ecrire('{"access_token": "t"}')
    assert c.lire() == '{"access_token": "t"}'


def test_the_uninstall_purge_knows_every_part():
    noms = auth.noms_dans_le_trousseau()
    assert auth.TROUSSEAU_NOM in noms and len(noms) > 5, noms


TESTS = [
    test_a_record_larger_than_the_windows_limit_survives,
    test_a_smaller_record_leaves_no_stale_part_behind,
    test_erasing_removes_every_part,
    test_a_refused_write_still_works_for_the_session,
    test_the_uninstall_purge_knows_every_part,
    test_pkce_matches_the_rfc_7636_vector,
    test_the_first_authorization_registers_the_client,
    test_a_reauthorization_reuses_the_client_and_names_the_account,
    test_a_full_sign_in_saves_the_account_and_the_issued_client,
    test_a_wrong_state_is_refused_and_nothing_is_saved,
    test_a_refusal_by_the_user_is_reported,
    test_a_wrong_nonce_is_refused,
    test_signed_in_without_plan_usage_is_said_so,
    test_a_failed_exchange_carries_the_reason,
    test_cancelling_stops_the_wait,
    test_a_reconnection_keeps_the_client_when_the_callback_omits_it,
    test_a_valid_token_is_returned_without_network,
    test_an_expiring_token_is_renewed_and_the_new_refresh_token_kept,
    test_a_network_failure_during_renewal_keeps_the_credentials,
    test_a_refused_renewal_signs_out_but_keeps_the_registration,
    test_signing_out_keeps_the_registration_only,
    test_a_corrupted_record_reads_as_signed_out,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()

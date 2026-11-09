"""Connexion << Sign in with ChatGPT >> — logique pure, sans Qt (TODO #122).

L'utilisateur se connecte avec son compte ChatGPT et Promptuino utilise SON
forfait, sans cle d'API. OpenAI l'autorise explicitement pour les projets open
source qui tournent en local (cookbook officiel, lancement du 2026-09-29) --
l'inverse exact du backend retire au #118.

Tout ce qui suit vient de la doc officielle, lue le 2026-11-06
(developers.openai.com/siwc/token-sharing-open-source, pages `sign-in` et
`token-reference`) :

- PKCE S256, `state`, `nonce` ; retour local sur **127.0.0.1** (⛔ jamais
  `localhost`), chemin FIXE `/auth/callback`, seul le port varie.
- Enregistrement DYNAMIQUE : premiere connexion avec
  `client_id=dynamic_agent_client` et `agent_name_hint` ; l'identifiant
  ATTRIBUE arrive sur le retour local, et peut manquer a la reconnexion.
- `ext_agent_host_id` : stable par machine, choisi AVANT la premiere
  connexion.
- Jeton d'acces 1 h ; jeton de renouvellement 30 jours, REMPLACE a chaque
  renouvellement.
- ⚠️ Le renouvellement n'est documente que par `grant_type=refresh_token` :
  on envoie la forme OAuth standard (`refresh_token`, `client_id`). A
  confirmer a l'essai reel avec un compte.

Le jeton d'identite n'est lu que pour l'e-mail et le `nonce`, SANS verifier sa
signature : OpenID Connect l'admet quand le jeton vient directement du point de
jeton en TLS (Core 3.1.3.7), et il ne sert qu'a AFFICHER le compte.

Un seul enregistrement JSON dans le trousseau (`promptuino` / `chatgpt_auth`),
jamais sur disque en clair. Point de jeton, trousseau et horloge sont
injectables : les tests ne touchent ni OpenAI ni le vrai trousseau.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

AUTHORIZE_URL = "https://auth.openai.com/api/accounts/authorize"
TOKEN_URL = "https://auth.openai.com/api/accounts/oauth/token"
RESOURCE = "https://api.openai.com/v1"
SCOPES = ("openid profile email offline_access "
          "resource.invoke chatgpt.tokens.use.direct")
SCOPE_FORFAIT = "chatgpt.tokens.use.direct"
CLIENT_DYNAMIQUE = "dynamic_agent_client"
NOM_APP = "Promptuino"
CHEMIN_RETOUR = "/auth/callback"
PAGE_USAGE = "https://chatgpt.com/settings/usage"

_TROUSSEAU_SERVICE = "promptuino"
TROUSSEAU_NOM = "chatgpt_auth"
_MARGE_RENOUVELLEMENT = 60      # secondes : renouveler avant l'expiration
_TIMEOUT = 20


# ─── PKCE, URL ───────────────────────────────────────────────────────────

def _b64url(octets: bytes) -> str:
    return base64.urlsafe_b64encode(octets).rstrip(b"=").decode("ascii")


def pkce(verifier: "str | None" = None) -> "tuple[str, str]":
    """(verifier, challenge S256). Verifie contre le vecteur de la RFC 7636."""
    verifier = verifier or _b64url(secrets.token_bytes(48))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def url_autorisation(*, client_id: "str | None", host_id: str,
                     redirect_uri: str, challenge: str, state: str, nonce: str,
                     id_token_hint: "str | None", login_hint: "str | None") -> str:
    """`client_id` None = premiere connexion : enregistrement dynamique, et
    alors SEULEMENT `agent_name_hint` (« include it only on initial
    dynamic-registration requests »)."""
    params = {"client_id": client_id or CLIENT_DYNAMIQUE}
    if not client_id:
        params["agent_name_hint"] = NOM_APP
    params.update({
        "ext_agent_host_id": host_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "resource": RESOURCE,
        "state": state,
        "nonce": nonce,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    })
    if id_token_hint:
        params["id_token_hint"] = id_token_hint
    if login_hint:
        params["login_hint"] = login_hint
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def _decoder_jwt(jeton: str) -> dict:
    """La charge utile d'un JWT, SANS verification de signature (voir l'en-tete)."""
    try:
        charge = jeton.split(".")[1]
        charge += "=" * (-len(charge) % 4)
        valeur = json.loads(base64.urlsafe_b64decode(charge.encode("ascii")))
        return valeur if isinstance(valeur, dict) else {}
    except Exception:
        return {}


# ─── Le retour local ─────────────────────────────────────────────────────

class RetourLocal:
    """Un serveur HTTP sur 127.0.0.1, port choisi par le systeme, qui attend
    UNE requete sur `/auth/callback` et sert `page_html` en reponse."""

    def __init__(self, page_html: str):
        self._recu: dict = {}
        self._evenement = threading.Event()
        recu, evenement = self._recu, self._evenement
        page = page_html.encode("utf-8")

        class _Gestion(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                parties = urllib.parse.urlsplit(self.path)
                if parties.path != CHEMIN_RETOUR or evenement.is_set():
                    self.send_response(404)
                    self.end_headers()
                    return
                recu.update(dict(urllib.parse.parse_qsl(parties.query)))
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)
                evenement.set()

            def log_message(self, *a):   # pas de journal sur la console
                pass

        self._serveur = http.server.HTTPServer(("127.0.0.1", 0), _Gestion)
        self.port = self._serveur.server_address[1]
        self.redirect_uri = f"http://127.0.0.1:{self.port}{CHEMIN_RETOUR}"
        self._fil = threading.Thread(target=self._serveur.serve_forever,
                                     kwargs={"poll_interval": 0.1}, daemon=True)
        self._fil.start()

    def attendre(self, delai: float, annule) -> "dict | None":
        """Les parametres du retour ; None si delai ecoule ou annulation."""
        fin = time.time() + delai
        while time.time() < fin:
            if self._evenement.wait(0.1):
                return dict(self._recu)
            if annule():
                return None
        return None

    def fermer(self):
        try:
            self._serveur.shutdown()
            self._serveur.server_close()
        except Exception:
            pass


# ─── Transports par defaut ───────────────────────────────────────────────

def _poster_urllib(url: str, formulaire: dict, timeout: int) -> "tuple[int | None, dict]":
    """POST en formulaire ; (statut, JSON), statut None = injoignable."""
    data = urllib.parse.urlencode(formulaire).encode("ascii")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"})
    try:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, _json(r.read())
        except urllib.error.HTTPError as e:
            return e.code, _json(e.read())
    except Exception:
        return None, {}


def _json(octets: bytes) -> dict:
    try:
        v = json.loads(octets.decode("utf-8", errors="replace") or "{}")
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


# Le Gestionnaire d'identifiants de Windows refuse une entree de plus de 1 280
# caracteres (mesure le 2026-11-06 : CredWrite, erreur 1783). L'enregistrement
# avec les trois jetons d'OpenAI la depasse largement : il est donc DECOUPE en
# morceaux `chatgpt_auth.1`, `chatgpt_auth.2`..., l'entree principale ne
# portant plus que leur nombre. Sans ca, la connexion etait perdue aussitot
# ecrite et l'ecran disait « non connecte » sans erreur (audit du 2026-11-06).
_TAILLE_MORCEAU = 1000
_MAX_MORCEAUX = 20
_MARQUE_MORCEAUX = "__morceaux__:"


def _nom_morceau(i: int) -> str:
    return f"{TROUSSEAU_NOM}.{i}"


def noms_dans_le_trousseau() -> list:
    """Toutes les entrees que la connexion peut occuper -- la purge de la
    desinstallation doit les effacer toutes."""
    return [TROUSSEAU_NOM] + [_nom_morceau(i) for i in range(1, _MAX_MORCEAUX + 1)]


class _CoffreTrousseau:
    """L'enregistrement dans le trousseau du systeme ; en memoire si `keyring`
    manque OU refuse l'ecriture (la connexion vaut alors pour la session)."""

    def __init__(self):
        self._memoire: "str | None" = None
        try:
            import keyring
            self._kr = keyring
        except Exception:
            self._kr = None

    def lire(self) -> "str | None":
        # Le repli en memoire passe en premier : il n'existe que si le
        # trousseau a refuse l'ecriture, et il n'etait jamais relu.
        if self._memoire is not None or self._kr is None:
            return self._memoire
        try:
            tete = self._kr.get_password(_TROUSSEAU_SERVICE, TROUSSEAU_NOM)
            if tete is None or not tete.startswith(_MARQUE_MORCEAUX):
                return tete
            n = int(tete[len(_MARQUE_MORCEAUX):])
            morceaux = [self._kr.get_password(_TROUSSEAU_SERVICE, _nom_morceau(i))
                        for i in range(1, n + 1)]
            return None if any(m is None for m in morceaux) else "".join(morceaux)
        except Exception:
            return None

    def _effacer_morceaux(self, a_partir_de: int) -> None:
        for i in range(a_partir_de, _MAX_MORCEAUX + 1):
            try:
                self._kr.delete_password(_TROUSSEAU_SERVICE, _nom_morceau(i))
            except Exception:
                pass

    def ecrire(self, texte: str) -> None:
        if self._kr is None:
            self._memoire = texte
            return
        morceaux = [texte[i:i + _TAILLE_MORCEAU]
                    for i in range(0, len(texte), _TAILLE_MORCEAU)] or [""]
        try:
            if len(morceaux) == 1:
                self._kr.set_password(_TROUSSEAU_SERVICE, TROUSSEAU_NOM, texte)
                self._effacer_morceaux(1)
            else:
                if len(morceaux) > _MAX_MORCEAUX:
                    raise ValueError("enregistrement trop grand")
                for i, m in enumerate(morceaux, 1):
                    self._kr.set_password(_TROUSSEAU_SERVICE, _nom_morceau(i), m)
                self._kr.set_password(_TROUSSEAU_SERVICE, TROUSSEAU_NOM,
                                      f"{_MARQUE_MORCEAUX}{len(morceaux)}")
                self._effacer_morceaux(len(morceaux) + 1)
            self._memoire = None
        except Exception:
            self._memoire = texte

    def effacer(self) -> None:
        self._memoire = None
        if self._kr is not None:
            try:
                self._kr.delete_password(_TROUSSEAU_SERVICE, TROUSSEAU_NOM)
            except Exception:
                pass
            self._effacer_morceaux(1)


# ─── La session ──────────────────────────────────────────────────────────

_CLES_ENREGISTREMENT = ("host_id", "client_id")
_CLES_JETONS = ("email", "id_token", "access_token", "refresh_token",
                "expires_at", "scopes")


class Session:
    """L'etat de connexion d'une machine. `session` (en bas) est l'instance
    partagee par l'app ; les tests en construisent une avec des bouchons."""

    def __init__(self, coffre=None, poster=None, horloge=time.time):
        self._coffre = coffre or _CoffreTrousseau()
        self._poster = poster or _poster_urllib
        self._horloge = horloge
        self._verrou = threading.Lock()
        # Vrai quand le DERNIER `jeton()` a rendu None faute de joindre le
        # serveur (panne reseau, 5xx) -- les identifiants sont alors gardes.
        # Sans ca l'appelant ne distingue pas « deconnecte » de « injoignable ».
        self.panne_reseau = False

    # -- enregistrement --
    def _lire(self) -> dict:
        texte = self._coffre.lire()
        if not texte:
            return {}
        try:
            rec = json.loads(texte)
        except Exception:
            return {}
        return rec if isinstance(rec, dict) else {}

    def _ecrire(self, rec: dict) -> None:
        self._coffre.ecrire(json.dumps(rec))

    def _garder_enregistrement_seul(self, rec: dict) -> None:
        self._ecrire({k: rec[k] for k in _CLES_ENREGISTREMENT if rec.get(k)})

    # -- lecture sans reseau --
    def compte(self) -> "dict | None":
        """`{"email", "forfait"}` si connecte, sinon None. Aucun reseau."""
        rec = self._lire()
        if not rec.get("refresh_token") and not rec.get("access_token"):
            return None
        return {"email": rec.get("email") or "",
                "forfait": SCOPE_FORFAIT in (rec.get("scopes") or [])}

    # -- connexion --
    def connecter(self, ouvrir, *, page_html: str, annule=lambda: False,
                  delai: float = 300) -> dict:
        """Tout le parcours. `ouvrir(url)` ouvre le navigateur.

        Rend `{"ok": True, "email", "forfait"}` ou `{"ok": False, "erreur",
        "message"}`, erreur parmi `annule`, `delai`, `refus`, `etat`,
        `echange`, `nonce`.
        """
        rec = self._lire()
        host_id = rec.get("host_id") or f"urn:uuid:{uuid.uuid4()}"
        client_id = rec.get("client_id")
        verifier, challenge = pkce()
        state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        retour = RetourLocal(page_html)
        try:
            ouvrir(url_autorisation(
                client_id=client_id, host_id=host_id,
                redirect_uri=retour.redirect_uri, challenge=challenge,
                state=state, nonce=nonce,
                id_token_hint=rec.get("id_token"), login_hint=rec.get("email")))
            recu = retour.attendre(delai, annule)
        finally:
            retour.fermer()
        if recu is None:
            return {"ok": False, "erreur": "annule" if annule() else "delai", "message": ""}
        if recu.get("error"):
            return {"ok": False, "erreur": "refus",
                    "message": recu.get("error_description") or recu["error"]}
        if recu.get("state") != state:
            return {"ok": False, "erreur": "etat", "message": ""}
        client_id = recu.get("client_id") or client_id
        # L'identifiant attribue est garde AVANT l'echange (comme le SDK
        # officiel) : un echange rate ne doit pas faire perdre l'enregistrement.
        self._ecrire({**rec, "host_id": host_id, "client_id": client_id})
        statut, rep = self._poster(TOKEN_URL, {
            "grant_type": "authorization_code",
            "code": recu.get("code") or "",
            "client_id": client_id or "",
            "code_verifier": verifier,
            "redirect_uri": retour.redirect_uri,
            "resource": RESOURCE,
        }, _TIMEOUT)
        if statut != 200 or not rep.get("access_token"):
            return {"ok": False, "erreur": "echange",
                    "message": str(rep.get("error_description") or rep.get("error") or "")}
        identite = _decoder_jwt(rep.get("id_token") or "")
        if identite.get("nonce") != nonce:
            return {"ok": False, "erreur": "nonce", "message": ""}
        scopes = str(rep.get("scope") or "").split()
        self._ecrire({
            "host_id": host_id, "client_id": client_id,
            "email": str(identite.get("email") or ""),
            "id_token": rep.get("id_token") or "",
            "access_token": rep["access_token"],
            "refresh_token": rep.get("refresh_token") or "",
            "expires_at": self._horloge() + float(rep.get("expires_in") or 3600),
            "scopes": scopes,
        })
        return {"ok": True, "email": str(identite.get("email") or ""),
                "forfait": SCOPE_FORFAIT in scopes}

    # -- jeton --
    def jeton(self, *, forcer: bool = False) -> "str | None":
        """Un jeton d'acces valide, renouvele au besoin ; None sinon.

        ⛔ Une panne RESEAU pendant le renouvellement garde les identifiants
        (« Don't erase credentials because of a temporary network or
        infrastructure failure ») ; seul un REFUS du serveur deconnecte.
        `forcer` sert apres un 401 : le jeton a pu etre revoque avant terme.
        """
        with self._verrou:
            self.panne_reseau = False
            rec = self._lire()
            acces = rec.get("access_token")
            if not acces and not rec.get("refresh_token"):
                return None
            if (acces and not forcer
                    and float(rec.get("expires_at") or 0) - _MARGE_RENOUVELLEMENT > self._horloge()):
                return acces
            if not rec.get("refresh_token"):
                return None
            statut, rep = self._poster(TOKEN_URL, {
                "grant_type": "refresh_token",
                "refresh_token": rec["refresh_token"],
                "client_id": rec.get("client_id") or "",
            }, _TIMEOUT)
            # 408 (delai) et 429 (limitation de debit) sont PASSAGERS comme un
            # 5xx : les traiter en refus deconnectait l'utilisateur pour rien
            # (audit 2026-11-06).
            if statut is None or statut >= 500 or statut in (408, 429):
                self.panne_reseau = True
                return None
            if statut != 200 or not rep.get("access_token"):
                self._garder_enregistrement_seul(rec)
                return None
            rec["access_token"] = rep["access_token"]
            if rep.get("refresh_token"):
                rec["refresh_token"] = rep["refresh_token"]     # il tourne
            rec["expires_at"] = self._horloge() + float(rep.get("expires_in") or 3600)
            if rep.get("scope"):
                rec["scopes"] = str(rep["scope"]).split()
            if rep.get("id_token"):
                rec["id_token"] = rep["id_token"]
            self._ecrire(rec)
            return rec["access_token"]

    def deconnecter(self) -> None:
        """Efface les jetons ; garde l'enregistrement du client et de la
        machine (« The runtime keeps the registration through logout »)."""
        with self._verrou:
            self._garder_enregistrement_seul(self._lire())


session = Session()

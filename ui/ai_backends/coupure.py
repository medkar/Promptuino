"""Une requete urllib qu'un autre fil peut couper, MEME avant les en-tetes.

Pourquoi ce module : sans flux, Ollama et LM Studio n'envoient RIEN -- pas
meme les en-tetes -- avant d'avoir fini de generer. `urlopen` reste donc
bloque pendant toute la generation, et une annulation qui fermait la REPONSE
n'avait rien a fermer : mesure le 2026-11-07 sur les vrais serveurs, Annuler
laissait LM Studio generer plus de 60 s et Ollama finir sa reponse.

Ici on garde la SOCKET des sa connexion, et `couper()` la ferme
(`shutdown`), ce qui debloque un `recv` en cours sur toutes les plateformes ;
le serveur voit le client partir et arrete de generer. On reste sur urllib
(proxys, HTTPS) : seule la classe de connexion change.
"""
from __future__ import annotations

import http.client
import socket
import threading
import urllib.request


class Coupure:
    """Ouvre des requetes et peut couper celle en cours.

    `couper()` vise la requete EN VOL ; une requete ouverte apres repart
    normalement (meme semantique que l'ancienne fermeture de reponse).

    `unique=True` (annuler un chargement, 2026-11-07) : la coupure est
    DEFINITIVE -- une requete qui s'ouvre apres `couper()` est coupee des sa
    connexion. Sans ca, annuler pendant que l'app libere les autres modeles
    (avant que la requete de chargement soit partie) ne coupait rien, et le
    modele se chargeait quand meme. Pas pour le moteur, qui reutilise sa
    coupure d'une generation a l'autre."""

    def __init__(self, *, unique: bool = False):
        self._lock = threading.Lock()
        self._sock = None
        self._unique = unique
        self.annulee = False

    def _retenir(self, sock) -> None:
        with self._lock:
            self._sock = sock
            tardive = self._unique and self.annulee and sock is not None
        if tardive:
            self._fermer(sock)

    def couper(self) -> None:
        with self._lock:
            self.annulee = True
            s = self._sock
        if s is None:
            return
        self._fermer(s)

    @staticmethod
    def _fermer(s) -> None:
        try:
            s.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            s.close()
        except OSError:
            pass

    def urlopen(self, req, timeout=None):
        coupure = self

        class _Http(http.client.HTTPConnection):
            def connect(self):
                super().connect()
                coupure._retenir(self.sock)

        class _Https(http.client.HTTPSConnection):
            def connect(self):
                super().connect()
                coupure._retenir(self.sock)

        class _HttpHandler(urllib.request.HTTPHandler):
            def http_open(self, r):
                return self.do_open(_Http, r)

        class _HttpsHandler(urllib.request.HTTPSHandler):
            def https_open(self, r):
                return self.do_open(_Https, r, context=self._context)

        opener = urllib.request.build_opener(_HttpHandler, _HttpsHandler)
        return _Reponse(opener.open(req, timeout=timeout), self)


class _Reponse:
    """Enveloppe de contexte : oublie la socket a la fermeture, pour qu'un
    `couper()` tardif ne vise jamais une connexion terminee."""

    def __init__(self, r, coupure: Coupure):
        self._r = r
        self._c = coupure

    def __getattr__(self, nom):
        return getattr(self._r, nom)

    def __iter__(self):
        return iter(self._r)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            self._r.close()
        finally:
            self._c._retenir(None)
        return False

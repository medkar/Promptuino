"""Annuler une generation coupe la requete AVANT que le serveur ait repondu.

Defaut mesure le 2026-11-07 sur les vrais serveurs : sans flux, Ollama et LM
Studio n'envoient rien -- pas meme les en-tetes -- avant d'avoir fini.
L'annulation fermait la REPONSE, qui n'existait pas encore : LM Studio a
continue de generer plus de 60 s apres « Annuler », Ollama a fini la sienne.

Ici un serveur local retient ses en-tetes 20 s, comme eux. Le test exige que
le fil qui attend soit libere en moins de 3 s ET que le serveur voie le
client partir (c'est ce qui fait arreter la generation cote serveur).
Aucun vrai serveur n'est appele.
"""
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.ai_backends import ollama_backend as ob  # noqa: E402
from ui.ai_backends import openai_compat as oc  # noqa: E402
from ui.ai_backends.coupure import Coupure  # noqa: E402

RETENUE = 20.0


class _Lent(BaseHTTPRequestHandler):
    vu_partir = None  # threading.Event, pose par le serveur

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        # Rien n'est envoye pendant la « generation » ; on guette le depart
        # du client en lisant la socket (recv rend b"" quand il ferme).
        self.connection.settimeout(0.2)
        fin = time.time() + RETENUE
        while time.time() < fin:
            try:
                if self.connection.recv(1) == b"":
                    _Lent.vu_partir.set()
                    return
            except TimeoutError:
                continue
            except OSError:
                _Lent.vu_partir.set()
                return
        body = b'{"response": "trop tard", "done": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _serveur():
    _Lent.vu_partir = threading.Event()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Lent)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _attendre_puis_annuler(appel, annuler):
    issue = {}

    def fil():
        try:
            issue["r"] = appel()
        except Exception as e:  # la coupure leve : c'est attendu
            issue["exc"] = type(e).__name__

    t = threading.Thread(target=fil, daemon=True)
    t.start()
    time.sleep(0.5)
    t0 = time.time()
    annuler()
    t.join(5)
    return t.is_alive(), time.time() - t0, issue


def test_coupure_frees_a_request_still_waiting_for_headers():
    srv, base = _serveur()
    try:
        import urllib.request
        c = Coupure()
        req = urllib.request.Request(base + "/x", data=b"{}")
        vivant, delai, issue = _attendre_puis_annuler(
            lambda: c.urlopen(req, timeout=None).read(), c.couper)
        assert not vivant, "le fil attend toujours les en-tetes"
        assert delai < 3, f"libere en {delai:.1f} s"
        assert "r" not in issue, issue
        assert _Lent.vu_partir.wait(3), "le serveur n'a pas vu le client partir"
    finally:
        srv.shutdown()


def test_ollama_generation_cancel_cuts_before_headers():
    srv, base = _serveur()
    ancien = ob._BASE_URL
    ob._BASE_URL = base
    try:
        be = ob.OllamaBackend("modele-de-test")
        vivant, delai, issue = _attendre_puis_annuler(
            lambda: ob._post("/api/generate", {"prompt": "x"}, timeout=None,
                             register=be._register_inflight,
                             coupure=be._coupure),
            be.cancel)
        assert not vivant and delai < 3, (vivant, delai)
        assert "r" not in issue, issue
        assert _Lent.vu_partir.wait(3)
    finally:
        ob._BASE_URL = ancien
        srv.shutdown()


def test_openai_compat_cancel_cuts_before_headers():
    srv, base = _serveur()
    try:
        tr = oc._UrllibTransport()
        vivant, delai, issue = _attendre_puis_annuler(
            lambda: tr.post_json(base + "/v1/chat/completions", {}, {}, None),
            tr.close_inflight)
        assert not vivant and delai < 3, (vivant, delai)
        assert "r" not in issue, issue
        assert _Lent.vu_partir.wait(3)
    finally:
        srv.shutdown()


def test_a_request_after_a_cancel_goes_through():
    """Couper vise la requete EN VOL : la suivante repart normalement."""
    from http.server import BaseHTTPRequestHandler as B

    class _Rapide(B):
        def log_message(self, *a):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            body = b'{"ok": 1}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Rapide)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        tr = oc._UrllibTransport()
        tr.close_inflight()  # rien en vol : sans effet
        url = f"http://127.0.0.1:{srv.server_address[1]}/v1"
        assert tr.post_json(url, {}, {}, 5) == {"ok": 1}
        assert tr.post_json(url, {}, {}, 5) == {"ok": 1}
    finally:
        srv.shutdown()


TESTS = [
    test_coupure_frees_a_request_still_waiting_for_headers,
    test_ollama_generation_cancel_cuts_before_headers,
    test_openai_compat_cancel_cuts_before_headers,
    test_a_request_after_a_cancel_goes_through,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {e!r}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} OK")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()

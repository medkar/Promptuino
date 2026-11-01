"""CompileUploadWorker(verify_only=True) : compile SANS upload, backend=None
(donc sans réparation IA) -> teste les deux issues compile OK / KO.
Skip si arduino-cli absent (intégration légère)."""
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import QCoreApplication, QEventLoop
_app = QCoreApplication.instance() or QCoreApplication([])
from ui import arduino_cli

_GOOD = "void setup(){} void loop(){}\n"
_BAD  = "void setup(){} void loop(){ int x = ; }\n"   # erreur de syntaxe

def _run(code):
    w = arduino_cli.CompileUploadWorker(code, "arduino:avr:uno", verify_only=True)
    res = {}
    loop = QEventLoop()
    w.done.connect(lambda ok, err: (res.update(ok=ok, err=err), loop.quit()))
    w.start(); loop.exec()
    return res

def test_good_compiles():
    if not arduino_cli.is_available():
        print("SKIP (arduino-cli absent)"); return
    r = _run(_GOOD)
    assert r["ok"] is True, r

def test_bad_fails():
    if not arduino_cli.is_available():
        print("SKIP (arduino-cli absent)"); return
    r = _run(_BAD)
    assert r["ok"] is False and r["err"], r

TESTS = [test_good_compiles, test_bad_fails]
def main():
    f = 0
    for t in TESTS:
        try: t(); print("OK  ", t.__name__)
        except AssertionError as e: f += 1; print("FAIL", t.__name__, e)
    print(f"\n{len(TESTS)-f}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(1 if f else 0)
if __name__ == "__main__": main()

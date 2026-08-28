"""Tests: dupliquer un projet en fait une COPIE EXACTE (fonctionnalités, chat,
résolutions de câblage, actions implicites, fichier de contexte, .ino)."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.project_manager import Project, ProjectType, project_manager
from ui.generation.feature_model import Feature, FeatureFunction


def _make_source(root: Path) -> Project:
    """Create a fully-populated project on disk under `root`."""
    proj_dir = root / "MyProj"
    proj_dir.mkdir(parents=True)
    (proj_dir / "MyProj.ino").write_text("void setup(){}\nvoid loop(){}\n",
                                         encoding="utf-8")
    (proj_dir / "notes.md").write_text("# pins\nD13 = LED\n", encoding="utf-8")
    proj = Project(
        path=proj_dir, name="MyProj", type=ProjectType.ARDUINO,
        mode="intermediate", board_env="arduino:avr:uno", board_model="Uno",
        last_prompt="fais clignoter une LED", ai_backend="ollama",
        comment_verbosity=3, serial_monitor=False,
        context_file_path="notes.md",
        functions=[],
        features=[
            Feature(id="f1", prompt="led qui clignote", summary="Clignote",
                    setup_lines=["pinMode(13, OUTPUT);"],
                    functions=[FeatureFunction(name="blink", code="void blink(){}")]),
            Feature(id="f2", prompt="un buzzer", summary="Bip",
                    setup_lines=["pinMode(8, OUTPUT);"]),
        ],
        chat_history=[
            {"role": "user", "content": "comment ça marche ?", "ts": "2026-07-01T10:00:00"},
            {"role": "assistant", "content": "voilà…", "ts": "2026-07-01T10:00:05"},
        ],
        wiring_resolutions={"f1|D13": "led", "f2|D8": "buzzer"},
        wiring_implicit_actions={"f1|D13|led_series_r": "220",
                                 "f2|D8|buzzer_series_r": "none"},
    )
    # Write the source meta too (duplicate reads the in-memory object, but a
    # real project always has its meta on disk).
    proj.meta_path.write_text(json.dumps(proj.to_dict(), indent=2, ensure_ascii=False),
                              encoding="utf-8")
    return proj


def test_duplicate_copies_everything():
    with tempfile.TemporaryDirectory() as td:
        src = _make_source(Path(td))
        dup = project_manager.duplicate(src)

        # Identity is fresh, content is identical.
        assert dup.name == "MyProj (copie)"
        assert dup.path == src.path.parent / "MyProj (copie)"
        assert dup.mode == "intermediate"
        assert dup.board_env == "arduino:avr:uno"
        assert dup.last_prompt == "fais clignoter une LED"
        assert dup.ai_backend == "ollama"
        assert dup.comment_verbosity == 3
        assert dup.serial_monitor is False
        assert dup.context_file_path == "notes.md"

        # The things that used to be dropped on duplicate:
        assert [f.id for f in dup.features] == ["f1", "f2"], "features lost!"
        assert dup.features[0].functions[0].name == "blink"
        assert dup.chat_history == src.chat_history, "chat history lost!"
        assert dup.wiring_resolutions == src.wiring_resolutions, "wiring resolutions lost!"
        assert dup.wiring_implicit_actions == src.wiring_implicit_actions, \
            "implicit actions lost!"

        # Files copied + renamed on disk.
        assert (dup.path / "MyProj (copie).ino").exists(), ".ino not renamed"
        assert (dup.path / "notes.md").read_text(encoding="utf-8").startswith("# pins")
        assert not list(dup.path.glob("MyProj.promptuino.json")), \
            "old-named meta should be gone"

        # And it all survives a reload from the freshly written meta.
        meta = json.loads(dup.meta_path.read_text(encoding="utf-8"))
        reloaded = Project.from_dict(meta, dup.path, ProjectType.ARDUINO)
        assert [f.id for f in reloaded.features] == ["f1", "f2"]
        assert reloaded.chat_history == src.chat_history
        assert reloaded.wiring_resolutions == src.wiring_resolutions
        assert reloaded.wiring_implicit_actions == src.wiring_implicit_actions


def test_duplicate_is_independent_copy():
    # Mutating the duplicate must not touch the source (deep copy via to/from_dict).
    with tempfile.TemporaryDirectory() as td:
        src = _make_source(Path(td))
        dup = project_manager.duplicate(src)
        dup.features[0].prompt = "MODIFIED"
        dup.chat_history.append({"role": "user", "content": "x", "ts": "t"})
        assert src.features[0].prompt == "led qui clignote"
        assert len(src.chat_history) == 2


TESTS = [test_duplicate_copies_everything, test_duplicate_is_independent_copy]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

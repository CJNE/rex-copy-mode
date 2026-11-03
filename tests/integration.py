"""Real Rex/Neovim integration tests. Python is a TEST DRIVER ONLY, not part of the viewer.
Run: python3 tests/integration.py [--live] [--stress]
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
REX = "rex"
PREFIX = "rex-copy-mode-"

def integration(action=None):
    def rex(*args):
        return subprocess.check_output([REX, *args], timeout=35).decode()
    def rex_json(*args):
        return json.loads(rex(*args))
    before = set(Path(tempfile.gettempdir()).glob(PREFIX + "*"))
    created = rex_json("new", "scrollback-integration-test", "--shell=none", "--json", "--", sys.executable, "-c",
                       "import time; print('\\033]2;SCROLLBACK_TITLE_50% Åäö\\007', end=''); print('\\n'.join('SCROLLBACK_TEST_LINE_%03d' % i for i in range(99))); print('\\033[1;3;4;38;2;255;100;10mSCROLLBACK_TEST_LINE_099 Åäö\\033[0m', flush=True); time.sleep(120)")
    session = created["session_id"]
    source = created["initial_windows"][0]["block_ids"][0]
    try:
        time.sleep(0.5)
        original_lines = rex("capture", "-s", session, "-b", source).splitlines()
        started = time.perf_counter()
        invocation = ["do", "-s", session, "-b", source, str(action or ROOT / "tests/fixture.lua")]
        if action != "copy_mode":
            invocation += ["--action", "copy_mode"]
        result = rex_json(*invocation, "--json")
        block = result["block_ids"][0]
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            screen = rex("capture", "-s", session, "-b", block, "--trim")
            if "SCROLLBACK_TEST_LINE_099" in screen:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("Neovim viewer did not display the captured fixture")
        startup = time.perf_counter() - started
        state = rex_json("session", "inspect", session, "--json")
        assert len(state["windows"]) == 1, "floating viewer must not create a tab"
        window = state["windows"][0]
        assert window["focused_block_id"] == block, "viewer must have keyboard focus"
        floating = [layer for layer in window["layers"] if layer["kind"] == "floating"]
        assert len(floating) == 1 and floating[0]["layer_id"] == result["layer_id"]
        assert floating[0]["bounds"] == [0, 0, 1, 1]
        expected_title = "(copy-mode) SCROLLBACK_TITLE_50% Åäö"
        assert floating[0]["blocks"][0]["label"] == expected_title
        actual_title = rex_json("block", "call", "-s", session, "-b", block, "title")["title"]
        assert actual_title == expected_title, (actual_title, expected_title)
        assert "Rex scrollback" not in screen, "statusline must not consume a row"
        viewer_lines = rex("capture", "-s", session, "-b", block).splitlines()
        assert original_lines[-len(viewer_lines):] == viewer_lines, "visible rows must stay aligned"
        styled = rex("capture", "-s", session, "-b", block, "--format=vt", "--trim")
        for style in ["\x1b[3m", "\x1b[1m", "\x1b[4m", "\x1b[38;2;255;100;10m"]:
            assert style in styled, "missing rendered style: %r" % style
        assert "Åäö" in styled
        snapshots = set(Path(tempfile.gettempdir()).glob(PREFIX + "*")) - before
        assert len(snapshots) == 1, "expected one private capture"
        snapshot = next(iter(snapshots))
        text = (snapshot / "capture.vt").read_text()
        assert "SCROLLBACK_TEST_LINE_000" in text and "SCROLLBACK_TEST_LINE_099" in text
        rex("send", "-s", session, "-b", block, ':lua vim.fn.writefile({vim.json.encode({loadplugins=vim.o.loadplugins,laststatus=vim.o.laststatus,cmdheight=vim.o.cmdheight,showmode=vim.o.showmode})}, (vim.g.rex_copy_mode_directory .. "/capture.vt") .. ".options")')
        rex("send-key", "-s", session, "-b", block, "enter")
        deadline = time.monotonic() + 5
        options_file = snapshot / "capture.vt.options"
        while not options_file.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        assert json.loads(options_file.read_text()) == {
            "loadplugins": False, "laststatus": 0, "cmdheight": 0, "showmode": False}
        # Yank a visual selection into a NAMED register: test copying rendered
        # text without changing the user's system clipboard.
        rex("send", "-s", session, "-b", block, ':normal! ggV"ay')
        rex("send-key", "-s", session, "-b", block, "enter")
        rex("send", "-s", session, "-b", block, ':lua vim.fn.writefile(vim.fn.getreg("a", 1, true), (vim.g.rex_copy_mode_directory .. "/capture.vt") .. ".yank")')
        rex("send-key", "-s", session, "-b", block, "enter")
        deadline = time.monotonic() + 5
        copied_file = snapshot / "capture.vt.yank"
        while not copied_file.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        copied = copied_file.read_text()
        assert "SCROLLBACK_TEST_LINE_000" in copied and "\x1b" not in copied
        rex("send", "-s", session, "-b", block, ":q")
        rex("send-key", "-s", session, "-b", block, "enter")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = rex_json("session", "inspect", session, "--json")
            if (len(state["windows"]) == 1
                    and len(state["windows"][0]["layers"]) == 1
                    and state["windows"][0]["focused_block_id"] == source):
                assert state["windows"][0]["layers"][0]["kind"] == "tiled"
                assert state["windows"][0]["focused_block_id"] == source
                assert state["active_window_id"] == state["windows"][0]["window_id"]
                assert not snapshot.exists(), "snapshot leaked after quitting"
                break
            time.sleep(0.2)
        else:
            raise AssertionError("Floating viewer did not close and return to the source")
        assert rex_json("block", "call", "-s", session, "-b", source, "title")["title"] == "SCROLLBACK_TITLE_50% Åäö"
        print("PASS: integration: title, clean config, alignment, styles, yank, focus, cleanup; ready %.1f ms" % (startup * 1000))
        return startup
    finally:
        rex("kill", session)


def large_capture():
    def rex(*args):
        return subprocess.check_output([REX, *args], timeout=35).decode()
    def rex_json(*args):
        return json.loads(rex(*args))
    before = set(Path(tempfile.gettempdir()).glob(PREFIX + "*"))
    created = rex_json("new", "scrollback-large-test", "--shell=none", "--json", "--", sys.executable, "-c",
                       "import time; print('\\n'.join('LARGE_%05d '%i + 'x'*60 for i in range(30000)), flush=True); time.sleep(120)")
    session = created["session_id"]
    source = created["initial_windows"][0]["block_ids"][0]
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if "LARGE_29999" in rex("capture", "-s", session, "-b", source, "--trim"):
                break
            time.sleep(0.1)
        else:
            raise AssertionError("Large source fixture did not render")
        result = rex_json("do", "-s", session, "-b", source, str(ROOT / "tests/fixture.lua"), "--action", "copy_mode", "--json")
        block = result["block_ids"][0]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if "LARGE_29999" in rex("capture", "-s", session, "-b", block, "--trim"):
                break
            time.sleep(0.1)
        else:
            raise AssertionError("Large viewer fixture did not render")
        snapshots = set(Path(tempfile.gettempdir()).glob(PREFIX + "*")) - before
        assert len(snapshots) == 1
        snapshot = snapshots.pop()
        data = (snapshot / "capture.vt").read_bytes()
        assert len(data) > 983040 and b"LARGE_00000" in data and b"LARGE_29999" in data
        assert snapshot.stat().st_mode & 0o777 == 0o700
        assert (snapshot / "capture.vt").stat().st_mode & 0o777 == 0o600
        rex("send", "-s", session, "-b", block, ":normal! gg")
        rex("send-key", "-s", session, "-b", block, "enter")
        deadline = time.monotonic() + 5
        while "LARGE_00000" not in rex("capture", "-s", session, "-b", block, "--trim"):
            assert time.monotonic() < deadline, "Older lines must remain navigable"
            time.sleep(0.1)
        rex("send", "-s", session, "-b", block, ":q")
        rex("send-key", "-s", session, "-b", block, "enter")
        deadline = time.monotonic() + 5
        while snapshot.exists():
            assert time.monotonic() < deadline, "Large snapshot must be cleaned up"
            time.sleep(0.1)
        print("PASS: native paginated capture, %d bytes / 30,000 lines; first/last lines navigable and private files removed" % len(data))
    finally:
        rex("kill", session)


if __name__ == "__main__":
    integration()
    if "--live" in sys.argv:
        integration("copy_mode")  # Invoke the loaded server action, not just a script.
    if "--stress" in sys.argv:
        large_capture()

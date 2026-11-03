"""Real visual-mode Enter tests with a FAKE clipboard: user's clipboard is untouched.
Run: python3 tests/copy_enter.py
"""
import json
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def rex(*args):
    return subprocess.check_output(["rex", *args], timeout=20).decode()


def rex_json(*args):
    return json.loads(rex(*args))


created = rex_json("new", "copy-mode-enter-test", "--shell=none", "--json", "--",
                   "/bin/sh", "-c", "printf 'ROW_ALPHA\\nROW_BRAVO\\nROW_CHARLIE\\n'; sleep 120")
session = created["session_id"]
source = created["initial_windows"][0]["block_ids"][0]
try:
    with tempfile.TemporaryDirectory(prefix="rex-copy-tests-") as temporary:
        directory = Path(temporary)
        for name, selection, expected, regtype in [
                ("character", "gg0v4l", ["ROW_A"], "v"),
                ("line", "ggVj", ["ROW_ALPHA", "ROW_BRAVO", ""], "V"),
                ("block", None, ["ROW_A", "ROW_B", ""], "b")]:
            result = rex_json("do", "-s", session, "-b", source, str(ROOT / "tests/fixture.lua"), "--action", "copy_mode", "--json")
            viewer = result["block_ids"][0]
            deadline = time.monotonic() + 5
            while "ROW_CHARLIE" not in rex("capture", "-s", session, "-b", viewer, "--trim"):
                assert time.monotonic() < deadline, "viewer did not render"
                time.sleep(0.05)
            copied = directory / (name + ".json")
            ready = directory / (name + ".ready")
            provider = directory / (name + "-provider.lua")
            provider.write_text('''
local function copy(lines, regtype)
  vim.fn.writefile({vim.json.encode({lines=lines,regtype=regtype})}, %s)
end
local function paste() return {{}, "v"} end
vim.g.clipboard = {name="copy-mode-test", copy={["+"]=copy,["*"]=copy}, paste={["+"]=paste,["*"]=paste}, cache_enabled=0}
vim.fn["provider#clipboard#Executable"]()
vim.fn.writefile({"ready"}, %s)
''' % (json.dumps(str(copied)), json.dumps(str(ready))))
            rex("send", "-s", session, "-b", viewer, ":lua dofile(" + json.dumps(str(provider)) + ")")
            rex("send-key", "-s", session, "-b", viewer, "enter")
            deadline = time.monotonic() + 5
            while not ready.exists():
                assert time.monotonic() < deadline, "fake clipboard provider did not initialize"
                time.sleep(0.05)
            # Normal-mode Enter must not copy or close the overlay.
            rex("send-key", "-s", session, "-b", viewer, "enter")
            time.sleep(0.05)
            state = rex_json("session", "inspect", session, "--json")
            assert any(layer["layer_id"] == result["layer_id"] for layer in state["windows"][0]["layers"])
            assert not copied.exists()
            if selection:
                rex("send", "-s", session, "-b", viewer, selection)
            else:
                rex("send", "-s", session, "-b", viewer, "gg0")
                rex("send-key", "-s", session, "-b", viewer, "ctrl+v")
                rex("send", "-s", session, "-b", viewer, "j4l")
            rex("send-key", "-s", session, "-b", viewer, "enter")
            deadline = time.monotonic() + 5
            while not copied.exists():
                assert time.monotonic() < deadline, "visual Enter did not copy"
                time.sleep(0.05)
            data = json.loads(copied.read_text())
            assert data["lines"] == expected, (name, data, expected)
            assert data["regtype"] == regtype, (name, data["regtype"], regtype)
            deadline = time.monotonic() + 5
            while True:
                state = rex_json("session", "inspect", session, "--json")
                window = state["windows"][0]
                notices = [layer for layer in window["layers"] if any(
                    block.get("label") == "Copied to clipboard" for block in layer.get("blocks", []))]
                if notices and len(window["layers"]) == 2:
                    assert window["focused_block_id"] == source, "notice must not take keyboard focus"
                    x, y, width, height = notices[0]["bounds"]
                    assert height <= 0.12 and abs(y + height - 1) < 1e-6
                    assert abs(x + width / 2 - 0.5) < 1e-6, "notice must be bottom-centered"
                    break
                assert time.monotonic() < deadline, "bottom copy notice did not appear after viewer closed"
                time.sleep(0.02)
            deadline = time.monotonic() + 5
            while True:
                state = rex_json("session", "inspect", session, "--json")
                window = state["windows"][0]
                if len(window["layers"]) == 1:
                    assert window["focused_block_id"] == source
                    break
                assert time.monotonic() < deadline, "visual Enter did not close/restore source"
                time.sleep(0.05)
            print("PASS: %s selection + Enter copies/quits; bottom notice keeps focus and auto-closes; normal Enter unchanged" % name)
finally:
    rex("kill", session)

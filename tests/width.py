"""Wide scrollback regression; uses only a disposable, unselected Rex session.
Run: python3 tests/width.py
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def rex(*args):
    return subprocess.check_output(["rex", *args], timeout=20).decode()


def rex_json(*args):
    return json.loads(rex(*args))


def wait_for(check, message):
    deadline = time.monotonic() + 10
    while not check():
        assert time.monotonic() < deadline, message
        time.sleep(0.05)


with tempfile.TemporaryDirectory(prefix="rex-width-test-") as temporary:
    directory = Path(temporary)
    ready = directory / "ready"
    output = directory / "buffer.json"
    expected = ["ROW%03d_" % i + "x" * 173 for i in range(100)]
    fixture = (
        "import pathlib,time; "
        "ready=pathlib.Path(%r)\n" % str(ready)
        + "while not ready.exists(): time.sleep(0.05)\n"
        + "print('\\n'.join('ROW%03d_'%i+'x'*173 for i in range(100)), flush=True)\n"
        + "time.sleep(120)"
    )
    created = rex_json("api", "call", "session.create", json.dumps({
        "label": "copy-mode-width-test",
        "initial_windows": [{"layout": {"block": {
            "flavor": "com.superlogical.terminal.shell",
            "options": {"shell": "none", "command": [sys.executable, "-c", fixture],
                        "size": {"columns": 220, "rows": 40}},
        }}}],
    }))
    session = created["session_id"]
    source = created["initial_windows"][0]["block_ids"][0]
    try:
        wait_for(lambda: rex_json("block", "call", "-s", session, "-b", source, "size")["columns"] == 220,
                 "source did not start at the requested width")
        ready.touch()
        wait_for(lambda: expected[-1] in rex("capture", "-s", session, "-b", source, "--trim"),
                 "wide source fixture did not render")
        result = rex_json("do", "-s", session, "-b", source, str(ROOT / "tests/fixture.lua"),
                          "--action", "copy_mode", "--json")
        viewer = result["block_ids"][0]
        wait_for(lambda: "ROW099_" in rex("capture", "-s", session, "-b", viewer, "--trim"),
                 "viewer did not render")
        # Inspect actual buffer rows, including history, not just the visible screen.
        # No yank or clipboard provider is involved.
        rex("send", "-s", session, "-b", viewer,
            ':lua vim.fn.writefile({vim.json.encode({columns=vim.o.columns,'
            'lines=vim.api.nvim_buf_get_lines(0,0,-1,false)})},' + json.dumps(str(output)) + ')')
        rex("send-key", "-s", session, "-b", viewer, "enter")
        wait_for(output.exists, "viewer did not write buffer inspection")
        data = json.loads(output.read_text())
        assert data["columns"] == 220, data["columns"]
        rows = [line for line in data["lines"] if line.startswith("ROW")]
        assert rows == expected, "wide lines were split in Neovim's scrollback"
        rex("send", "-s", session, "-b", viewer, ":qa!")
        rex("send-key", "-s", session, "-b", viewer, "enter")
        wait_for(lambda: len(rex_json("session", "inspect", session, "--json")["windows"][0]["layers"]) == 1,
                 "viewer did not close")
        print("PASS: 220-column overlay preserves all 100 wide scrollback lines")
    finally:
        rex("kill", session)

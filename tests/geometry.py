"""Real Rex geometry tests; creates and destroys only its own test session.
Run: python3 tests/geometry.py
"""
import json
import math
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = "import time; print('GEOMETRY_TEST_SOURCE', flush=True); time.sleep(120)"


def rex(*args):
    return subprocess.check_output(["rex", *args], timeout=35).decode()


def rex_json(*args):
    return json.loads(rex(*args))


def fixture():
    return {"block": {"flavor": "com.superlogical.terminal.shell", "options": {
        "shell": "none", "command": [sys.executable, "-c", FIXTURE]}}}


created = rex_json("new", "scrollback-geometry-test", "--shell=none", "--json", "--",
                   sys.executable, "-c", FIXTURE)
session = created["session_id"]
source = created["initial_windows"][0]["block_ids"][0]


def api(method, **args):
    return rex_json("api", "call", method, json.dumps(dict(session_id=session, **args)))


def check(name, block, expected_bounds, expect_zoom=False):
    time.sleep(0.2)
    baseline = rex_json("session", "inspect", session, "--json")
    layer_count = len(baseline["windows"][0]["layers"])
    result = rex_json("do", "-s", session, "-b", block, str(ROOT / "tests/fixture.lua"), "--action", "copy_mode", "--json")
    viewer = result["block_ids"][0]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        screen = rex("capture", "-s", session, "-b", viewer, "--trim")
        if "GEOMETRY_TEST_SOURCE" in screen:
            break
        time.sleep(0.1)
    else:
        raise AssertionError(name + ": viewer did not render")
    state = rex_json("session", "inspect", session, "--json")
    assert len(state["windows"]) == 1, "viewer must not create a tab"
    window = state["windows"][0]
    assert window["focused_block_id"] == viewer, "viewer must receive focus"
    layer = next(layer for layer in window["layers"] if layer["layer_id"] == result["layer_id"])
    assert all(math.isclose(actual, expected, abs_tol=1e-10) for actual, expected in zip(layer["bounds"], expected_bounds)), (name, layer["bounds"], expected_bounds)
    rex("send", "-s", session, "-b", viewer, ":q")
    rex("send-key", "-s", session, "-b", viewer, "enter")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        window = rex_json("session", "inspect", session, "--json")["windows"][0]
        if len(window["layers"]) == layer_count and window["focused_block_id"] == block:
            assert (window.get("zoomed_block_id") == block) == expect_zoom, "source zoom must be restored"
            break
        time.sleep(0.1)
    else:
        raise AssertionError(name + ": viewer did not close/restore source")
    print("PASS: %s -> %s, source focus/zoom restored" % (name, expected_bounds))


try:
    check("full-window pane", source, [0, 0, 1, 1])
    right = api("session.new_split", anchor_id=source, direction="horizontal", side="after",
                ratio=0.4, layout=fixture(), focus=True)["block_ids"][0]
    check("right split", right, [0.4, 0, 0.6, 1])
    bottom = api("session.new_split", anchor_id=right, direction="vertical", side="after",
                 ratio=0.3, layout=fixture(), focus=True)["block_ids"][0]
    check("nested bottom-right split", bottom, [0.4, 0.3, 0.6, 0.7])
    rex("zoom", "-s", session, bottom, "--on")
    check("zoomed split", bottom, [0, 0, 1, 1], expect_zoom=True)
    rex("zoom", "-s", session, bottom, "--off")
    floating = api("session.new_layer", bounds=[0.2, 0.1, 0.6, 0.8], focus=True,
                   layout={"split": {"direction": "horizontal", "ratio": 0.25,
                                     "before": fixture(), "after": fixture()}})
    check("split inside an existing floating layer", floating["block_ids"][1], [0.35, 0.1, 0.45, 0.8])
finally:
    rex("kill", session)

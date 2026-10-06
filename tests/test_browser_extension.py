"""Static checks for the browser extension, plus its Node unit tests when Node is available."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "browser_extension"
NODE = shutil.which("node")
UNSAFE_JS = re.compile(r"\.(inner|outer)HTML\b|insertAdjacentHTML|document\.write|\beval\(|new Function")


def _manifest() -> dict:
    return json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))


def test_manifest_is_mv3_with_minimal_permissions():
    m = _manifest()
    assert m["manifest_version"] == 3
    assert set(m["permissions"]) == {"activeTab", "scripting", "storage"}  # no tabs/cookies/webRequest/history
    assert m["host_permissions"] == ["http://127.0.0.1/*"]                 # local receiver only
    for forbidden in ("content_scripts", "background", "externally_connectable", "web_accessible_resources"):
        assert forbidden not in m, forbidden  # nothing runs automatically on any site
    assert "<all_urls>" not in json.dumps(m)


def test_unsafe_js_pattern_detects_what_it_should():
    assert UNSAFE_JS.search("el.innerHTML = x") and UNSAFE_JS.search("eval(code)")
    assert not UNSAFE_JS.search("// shown via form values, never innerHTML")


def test_referenced_files_exist_and_no_remote_code():
    m = _manifest()
    for name in (m["action"]["default_popup"], m["options_page"]):
        assert (EXT / name).is_file()
    for html in EXT.glob("*.html"):
        text = html.read_text(encoding="utf-8")
        assert "https://" not in text and "http://" not in text  # no remote scripts or styles
        assert "<script>" not in text  # MV3 forbids inline scripts; all JS is in files
    for js in EXT.glob("*.js"):
        text = js.read_text(encoding="utf-8")
        assert not UNSAFE_JS.search(text), f"{js.name} must not render page content as HTML or evaluate code"
        assert "https://" not in text, f"{js.name} must not contact remote servers"


def test_popup_sends_only_to_localhost():
    text = (EXT / "popup.js").read_text(encoding="utf-8")
    urls = [line for line in text.splitlines() if "fetch(" in line]
    assert urls and all("127.0.0.1" in u for u in urls)


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_extension_scripts_parse():
    for js in sorted(EXT.glob("*.js")):
        result = subprocess.run([NODE, "--check", str(js)], capture_output=True, text=True)
        assert result.returncode == 0, f"{js.name}: {result.stderr}"


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_capture_logic_node_tests():
    files = [str(f) for f in sorted((ROOT / "tests" / "js").glob("*.test.js"))]
    result = subprocess.run([NODE, "--test", *files], capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stdout + result.stderr

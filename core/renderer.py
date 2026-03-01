"""
core/renderer.py
════════════════════════════════════════════════════════════════
Loads the HTML template, injects data as JSON, and renders it
as a full-viewport Streamlit component.

All pages (P1–P5) call render_dashboard(active_page).
Only P6 (Holdings Editor) is a native Streamlit page.
════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import json
import pathlib
import streamlit as st
import streamlit.components.v1 as components

# Path to the HTML template — relative to this file
_TEMPLATE = pathlib.Path(__file__).parent.parent / "assets" / "dashboard.html"

# Viewport height minus Streamlit's thin topbar (≈ 0 when chrome is hidden)
_HEIGHT = 950


def _inject(html: str, key: str, value) -> str:
    """Replace __KEY__ placeholder with JSON-serialised value."""
    return html.replace(f"__{key}__", json.dumps(value, default=str))


def render_dashboard(
    active_page: str,
    meta: dict,
    runs: list,
    nifty: list,
    snapshot: list,
    signals: list,
) -> None:
    """
    Inject all data into the HTML template and embed as component.

    Args:
        active_page: one of 'overview','market','portfolio','signals','harvest'
        meta:     get_harvest_meta() result
        runs:     get_run_history() result
        nifty:    get_nifty_series() result  (sampled to ≤742 pts)
        snapshot: get_snapshot() result
        signals:  get_signals(snapshot) result
    """
    html = _TEMPLATE.read_text(encoding="utf-8")

    # Data injection
    html = _inject(html, "META",     meta)
    html = _inject(html, "RUNS",     runs)
    html = _inject(html, "NIFTY",    nifty)
    html = _inject(html, "SNAPSHOT", snapshot)
    html = _inject(html, "SIGNALS",  signals)

    # Tell the JS which page to activate on load
    # We append a tiny inline script after the closing </script> tag
    activate_script = f"""
<script>
// Auto-navigate to the correct page on load
document.addEventListener('DOMContentLoaded', function() {{
  go('{active_page}');
}});
</script>
"""
    html = html.replace("</body>", activate_script + "</body>")

    components.html(html, height=_HEIGHT, scrolling=False)

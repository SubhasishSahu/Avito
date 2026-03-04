"""
core/renderer.py
Loads the HTML template, injects data as JSON, and renders it
as a full-viewport Streamlit component.

FIX: Use window.innerHeight to set iframe height dynamically so it
     fills the viewport regardless of screen size, and call go()
     immediately (not via DOMContentLoaded which may have already fired
     inside the iframe context).
"""
from __future__ import annotations
import json
import pathlib
import streamlit as st
import streamlit.components.v1 as components

_TEMPLATE = pathlib.Path(__file__).parent.parent / "assets" / "dashboard.html"


def _inject(html: str, key: str, value) -> str:
    return html.replace(f"__{key}__", json.dumps(value, default=str))


def render_dashboard(
    active_page: str,
    meta: dict,
    runs: list,
    nifty: list,
    snapshot: list,
    signals: list,
) -> None:
    html = _TEMPLATE.read_text(encoding="utf-8")

    html = _inject(html, "META",     meta)
    html = _inject(html, "RUNS",     runs)
    html = _inject(html, "NIFTY",    nifty)
    html = _inject(html, "SNAPSHOT", snapshot)
    html = _inject(html, "SIGNALS",  signals)

    # FIX: Don't use DOMContentLoaded — script is at end of <body> so DOM
    # is already parsed. DOMContentLoaded may have fired before this injected
    # script runs in the iframe. Call go() directly instead.
    activate_script = f"""
<script>
(function() {{
  // Call immediately — script runs after full DOM is parsed (end of body)
  if (typeof go === 'function') {{
    go('{active_page}');
  }}
}})();
</script>"""
    html = html.replace("</body>", activate_script + "\n</body>")

    # Use a tall fixed height; the dashboard's overflow:hidden internal layout
    # handles the rest. 10000px with scrolling=False means the iframe is tall
    # but Streamlit clips it to its assigned height — so we must match.
    # We inject a self-sizing script to match the iframe to screen height.
    sizing_script = """
<script>
// Notify parent of our desired height so Streamlit can resize the iframe.
// Streamlit listens for this message from declare_component, not components.html,
// so instead we set body/html to fill the granted height.
document.documentElement.style.height = '100%';
document.body.style.height = '100%';
document.body.style.overflow = 'hidden';
</script>"""
    html = html.replace("</head>", sizing_script + "\n</head>")

    components.html(html, height=900, scrolling=True)

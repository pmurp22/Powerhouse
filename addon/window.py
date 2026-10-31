"""The Powerhouse game window: a plain Qt window holding one Anki web view."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Optional

from aqt.qt import QDialog, Qt, QVBoxLayout
from aqt.utils import restoreGeom, saveGeom
from aqt.webview import AnkiWebView

if TYPE_CHECKING:
    from .main import Powerhouse

GEOM_KEY = "powerhouse_window"


class GameWindow(QDialog):
    def __init__(self, controller: "Powerhouse") -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.controller = controller
        self.setWindowTitle("Powerhouse")
        self.setMinimumSize(760, 560)
        self.resize(1180, 780)
        restoreGeom(self, GEOM_KEY)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.web = AnkiWebView(self, title="powerhouse")
        self.web.set_bridge_command(self._on_bridge, self)
        layout.addWidget(self.web)
        self._loaded = False
        self._closed = False
        self.load()

    def load(self) -> None:
        base = self.controller.web_base
        self.web.stdHtml(
            '<div id="app" class="app"></div>',
            css=[f"{base}/game.css"],
            js=[f"{base}/mito.js", f"{base}/game.js"],
            context=self,
            default_css=False,
        )
        static = json.dumps(self.controller.static_payload())
        snapshot = json.dumps(self.controller.snapshot())
        settings = json.dumps(self.controller.client_settings())
        self.web.eval(f"PH.init({static}, {snapshot}, {settings});")
        self._loaded = True

    def push(self, snapshot: dict[str, Any], events: Optional[list[dict[str, Any]]] = None,
             settings: Optional[dict[str, Any]] = None) -> None:
        if not self._loaded:
            return
        args = [json.dumps(snapshot), json.dumps(events or [])]
        if settings is not None:
            args.append(json.dumps(settings))
        self.web.eval(f"window.PH && PH.update({', '.join(args)});")

    def _on_bridge(self, cmd: str) -> Any:
        # Normally our webview_did_receive_js_message hook answers first.
        if cmd.startswith("powerhouse:"):
            return self.controller.handle_command(cmd[len("powerhouse:"):], self)
        return None

    # Every way of closing (the X button, Esc, close() from code) ends up in
    # QDialog.done(), so clean up there and let Qt finish closing normally.
    def done(self, result: int) -> None:
        if not self._closed:
            self._closed = True
            try:
                saveGeom(self, GEOM_KEY)
                self.web.cleanup()
            except Exception:
                pass
            self.controller.window_closed(self)
        super().done(result)

"""Explicit cursor insertion when a target does not expose accessibility."""
from dataclasses import dataclass


@dataclass
class ManualTarget:
    desktop: object
    window: int
    source: object = None
    original: str = ""
    manual: bool = True

    def validate(self):
        if self.window <= 1 or not self.desktop.window_exists(self.window):
            raise RuntimeError("The original window is no longer available. Your draft is still here.")

    def focus(self):
        self.validate()

    def focused(self):
        return self.desktop.focused_window() == self.window

    def select_contents(self):
        # No field identity or range is available: preserve the original cursor
        # and selection. Never guess with Ctrl+A or read via simulated copying.
        pass

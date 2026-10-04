# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bounded history model; persistence is handled by storage.py."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    text: str
    html: str | None = None


class History:
    def __init__(self, limit=9, max_characters=100_000):
        self.limit = limit
        self.max_characters = max_characters
        self.entries = []

    def add(self, text, html=None):
        if self.limit == 0 or not text or len(text) > self.max_characters:
            return False
        if html and len(html) > self.max_characters * 10:
            html = None
        entry = Entry(text, html)
        self.entries = [old for old in self.entries if old.text != text]
        self.entries.insert(0, entry)
        del self.entries[self.limit:]
        return True

# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Private, atomic configuration and history storage."""
from dataclasses import asdict
from copy import deepcopy
import yaml
import json
import os
from pathlib import Path
import tempfile
import time

from .history import History
from .shortcuts import DEFAULT_BINDINGS, normalize_bindings
from .completion import DEFAULT_COMPLETION
from .quick_insert import DEFAULT_QUICK_INSERT, normalize_quick_insert

DEFAULT_CONFIG = {"recent_entries_limit": 50, "clipboard_entries_limit": 50,
                  "spellcheck_language": "en_AU", "editor_font_size": 16,
                  "autocorrect": True, "grammar_check": True,
                  "automatic_popup": True, "completion": DEFAULT_COMPLETION,
                  "window_width_percent": 60, "window_height_percent": 66.67,
                  "indent_width": 4,
                  "keybindings": DEFAULT_BINDINGS, "quick_insert": DEFAULT_QUICK_INSERT}


def atomic_text(path, text):
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class ConfigLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        mapping = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in mapping:
                raise ValueError(f"Configuration keys must be unique strings: {key!r}")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


class ConfigDumper(yaml.SafeDumper):
    pass


def _represent_text(dumper, value):
    return dumper.represent_scalar('tag:yaml.org,2002:str', value,
                                   style='|' if '\n' in value else None)


ConfigDumper.add_representer(str, _represent_text)


def atomic_json(path, data):
    atomic_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def atomic_yaml(path, data):
    atomic_text(path, yaml.dump(data, Dumper=ConfigDumper, allow_unicode=True, sort_keys=False))


class Store:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "universal-input"
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.directory.chmod(0o700)
        self.config_path = self.directory / "config.yaml"
        self.history_path = self.directory / "history.json"
        legacy_path = self.directory / "config.json"
        create = not self.config_path.exists()
        source_path = legacy_path if create and legacy_path.exists() else self.config_path
        try:
            if create and not legacy_path.exists():
                self.config = deepcopy(DEFAULT_CONFIG)
            elif source_path == legacy_path:
                self.config = json.loads(legacy_path.read_text(encoding="utf-8"))
            else:
                self.config = yaml.load(self.config_path.read_text(encoding="utf-8"), Loader=ConfigLoader)
            if not isinstance(self.config, dict):
                raise ValueError("expected a mapping")
            if "quick_insert" in self.config and not isinstance(self.config["quick_insert"], list):
                raise ValueError("quick_insert must be a list")
            self.quick_insert = normalize_quick_insert(self.config.get("quick_insert"))
            self.config.setdefault("quick_insert", self.quick_insert)
            if source_path == legacy_path:
                old_bindings = self.config.get("keybindings", {})
                if isinstance(old_bindings, dict):
                    for item in self.quick_insert:
                        if item["id"] in old_bindings:
                            item["shortcut"] = old_bindings.pop(item["id"])
                    self.config["quick_insert"] = self.quick_insert
            for key in ("recent_entries_limit", "clipboard_entries_limit"):
                default = DEFAULT_CONFIG[key]
                value = self.config.setdefault(key, default)
                if type(value) is not int or not 0 <= value <= 500:
                    raise ValueError(f"{key} must be an integer from 0 to 500")
            configured = self.config.setdefault("keybindings", {})
            for key in ("autocorrect", "grammar_check", "automatic_popup"):
                if type(self.config.setdefault(key, DEFAULT_CONFIG[key])) is not bool:
                    raise ValueError(f"{key} must be true or false")
            completion = self.config.setdefault("completion", {})
            if not isinstance(completion, dict):
                raise ValueError("completion must be an object")
            for key, default in DEFAULT_COMPLETION.items():
                completion.setdefault(key, default)
            if type(completion["enabled"]) is not bool:
                raise ValueError("completion.enabled must be true or false")
            for key, low, high in (("debounce_ms", 0, 2000), ("context_tokens", 32, 512),
                                   ("max_tokens", 4, 32), ("threads", 1, 8)):
                if type(completion[key]) is not int or not low <= completion[key] <= high:
                    raise ValueError(f"completion.{key} must be an integer from {low} to {high}")
            for key in ("python_path", "model_path"):
                if not isinstance(completion[key], str):
                    raise ValueError(f"completion.{key} must be a path string")
            if not isinstance(configured, dict):
                raise ValueError("keybindings must be an object")
            self.keybindings = normalize_bindings(configured, self.quick_insert)
            indent = self.config.setdefault("indent_width", 4)
            if type(indent) is not int or not 1 <= indent <= 16:
                raise ValueError("indent_width must be an integer from 1 to 16 spaces")
            for key in ("window_width_percent", "window_height_percent"):
                value = self.config.setdefault(key, DEFAULT_CONFIG[key])
                if type(value) not in (int, float) or not 20 <= value <= 100:
                    raise ValueError(f"{key} must be a number from 20 to 100")
            size = self.config.setdefault("editor_font_size", 16)
            if type(size) is not int or not 10 <= size <= 48:
                raise ValueError("editor_font_size must be an integer from 10 to 48 (pixels)")
            language = self.config.setdefault("spellcheck_language", "en_AU")
            if not isinstance(language, str) or not language:
                raise ValueError("spellcheck_language must be a dictionary language such as en_AU")
            # Materialize omitted defaults, retaining all user overrides.
            for action, value in DEFAULT_BINDINGS.items():
                configured.setdefault(action, value)
            if create:
                atomic_yaml(self.config_path, self.config)
            self.config_path.chmod(0o600)
        except (ValueError, OSError, yaml.YAMLError) as exc:
            raise RuntimeError(f"Invalid configuration at {source_path}: {exc}") from exc
        self.entries = History(self.config["recent_entries_limit"])
        self.clipboard = History(self.config["clipboard_entries_limit"])
        self.warning = None
        self.load()

    def load(self):
        if not self.history_path.exists():
            return
        self.history_path.chmod(0o600)
        try:
            data = json.loads(self.history_path.read_text())
            if not isinstance(data, dict) or data.get("version") != 1:
                raise ValueError("unsupported history format")
            # Validate both lists before changing either in-memory history.
            for key in ("recent_entries", "clipboard_entries"):
                rows = data.get(key, [])
                if not isinstance(rows, list) or any(
                    not isinstance(row, dict) or not isinstance(row.get("text"), str)
                    or (row.get("html") is not None and not isinstance(row["html"], str))
                    for row in rows
                ):
                    raise ValueError("invalid history entry")
            for key, history in (("recent_entries", self.entries), ("clipboard_entries", self.clipboard)):
                for row in reversed(data.get(key, [])[:history.limit]):
                    history.add(row["text"], row.get("html"))
        except ValueError:
            backup = self.history_path.with_name(f"history.invalid-{time.time_ns()}.json")
            self.history_path.rename(backup)
            self.warning = f"Unreadable history preserved at {backup}. Starting a new history."
        self.save()  # Enforce reduced limits on disk as well as in memory.

    def save(self):
        atomic_json(self.history_path, {
            "version": 1,
            "recent_entries": [asdict(entry) for entry in self.entries.entries],
            "clipboard_entries": [asdict(entry) for entry in self.clipboard.entries],
        })

    def save_font_size(self, size):
        # Patch only this scalar, preserving comments and edits made while running.
        source = self.config_path.read_text(encoding="utf-8")
        try:
            data = yaml.load(source, Loader=ConfigLoader)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("Configuration must be a mapping")
        # Anchors/aliases can share scalar nodes and source locations. Expand
        # them on save rather than rewriting another setting or dangling an alias.
        if any(isinstance(token, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken))
               for token in yaml.scan(source)):
            data["editor_font_size"] = size
            atomic_yaml(self.config_path, data)
            self.config["editor_font_size"] = size
            return
        node = yaml.compose(source, Loader=ConfigLoader)
        for key, value in node.value:
            if key.value == "editor_font_size":
                source = source[:value.start_mark.index] + str(size) + source[value.end_mark.index:]
                break
        else:
            # Flow mappings need structural serialization when adding a key.
            if node.flow_style:
                data["editor_font_size"] = size
                atomic_yaml(self.config_path, data)
                self.config["editor_font_size"] = size
                return
            end = node.end_mark.index
            source = source[:end].rstrip() + f"\neditor_font_size: {size}\n" + source[end:]
        atomic_text(self.config_path, source)
        self.config["editor_font_size"] = size

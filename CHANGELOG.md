# Changelog

Project changes are recorded here. Unreleased entries describe changes on `main`
that have not been assigned a new release version.

## Unreleased

### Added

- [PR #7](https://github.com/muntedcrocodile/universal_input/pull/7): Define the quick-insert toolbar and hotkeys through an ordered `quick_insert`
  list: custom labels, aliases, hidden buttons, Markdown/plain insertion, cursor
  offsets or selected placeholders, and inline text, UTF-8 file, or asynchronous
  command sources. Table recipes retain the grid and custom-size picker. Commands
  have time/output limits and discard results when their destination changes.

### Fixed

- Repair the local configuration's conflicting history shortcuts by restoring
  `history_left` / `history_right` to `Ctrl+Shift+Left` / `Ctrl+Shift+Right`,
  allowing startup while retaining `Ctrl+Alt+Left` / `Ctrl+Alt+Right` for spelling.
- Make the configurable quick-insert toolbar's scroll area and contents transparent
  so buttons and shortcut labels follow the dark theme instead of sitting on white.
- Keep table insertion guides visible during delayed syntax-highlighting refreshes
  so moving onto an add-row button is not interrupted.

### Changed

- Change default history shortcuts to `Ctrl+R` for Recents and `Ctrl+P` for
  Clipboard, freeing `Ctrl+Shift+Left` / `Ctrl+Shift+Right` for word selection.
  Update the local running configuration, example config, README, usage guide,
  and desktop checks. Other existing configurations retain saved bindings; set
  `keybindings.history_left` / `history_right` to the new shortcuts or remove
  those overrides to adopt the defaults.
- Move settings to `config.yaml` using PyYAML (`python3-yaml` in the dependency
  installer). Automatically migrate existing JSON settings and quick-insert
  shortcuts while retaining the original JSON; YAML takes precedence. Preserve
  YAML comments on startup and normal font-size saves. History remains JSON.
- [PR #7](https://github.com/muntedcrocodile/universal_input/pull/7): Expand the
  README with text/file/command and table recipes, cursor and shortcut options,
  and PyYAML installation/update instructions.
- Replace the example config with YAML and document recipe configuration,
  migration, command execution, and cursor behavior. Add migration and insertion
  regression tests for both editor modes and command failures/cancellation.

## 1.1.0 — 2026-10-09

### Added

- [PR #1](https://github.com/muntedcrocodile/universal_input/pull/1): Offline,
  inline word predictions. Tap Tab to accept grey preview text as one undoable
  edit; unaccepted predictions stay out of copied text, history, and exports.
  Tab+Arrow navigation remains available. The optional installer provides a
  local CPU runtime and checksum-verified model; editing still works without it.
  Set `automatic_popup` to `false` for manual opening through Ctrl+Space or the
  tray. The default remains `true`.
- [PR #3](https://github.com/muntedcrocodile/universal_input/pull/3): A Template
  toolbar button inserts an editable Markdown example document in either mode,
  with single-step undo. Rendered fenced code now has language-aware syntax
  colours, and blockquotes have continuous bars, including nested quotes.
- [PR #4](https://github.com/muntedcrocodile/universal_input/pull/4): Local English
  autocorrect for curated typos, contractions, and sentence capitalisation, plus
  basic grammar suggestions for repeated words, subject/verb agreement, and
  selected a/an mistakes. `autocorrect` and `grammar_check` are independently
  configurable and enabled by default. These are limited offline rules.
  Autocorrect supports undo, does not rewrite loaded or pasted text, and excludes
  code, URLs, and email addresses. Selected personal dictionary words can be
  removed through the context menu; removal persists across restarts.
- [PR #6](https://github.com/muntedcrocodile/universal_input/pull/6): Table →
  Custom size, also accessible with C in the picker grid. Enter rows including
  the header, then columns, with limits of 1,000 rows, 100 columns, and 10,000
  cells total. Escape cancels; insertion preserves the destination selection,
  selects the first header, and supports single-step undo in both modes.

### Fixed

- [PR #2](https://github.com/muntedcrocodile/universal_input/pull/2): Capture
  existing browser textbox content when accessibility exposes nested-object
  placeholders, using Select All/Copy while restoring the clipboard. Wait for
  the opening shortcut's trigger key to be released before issuing editing
  commands, preventing blank captures for default and custom shortcuts.
- [PR #3](https://github.com/muntedcrocodile/universal_input/pull/3): Preserve
  cursor position, selection direction, and cursor visibility when switching
  between Raw and Rendered, with exact restoration on an unchanged round trip.
- [PR #5](https://github.com/muntedcrocodile/universal_input/pull/5): Save and
  dismiss the editor when native X11 focus moves elsewhere, allowing transient
  focus changes and editor popups. Cancel pending insertion safely and retain
  resumable drafts for accessible fields. Preserve authored Markdown paragraph
  and hard-line breaks instead of exporting visual wrapping as new line breaks.
  Request accessibility support at startup and explain Copy fallback failures
  without logging field contents.

### Development and documentation

- Bump the package version from 1.0.0 to 1.1.0 for this minor source release.
- Integrate PRs #1–#6 with their shared editor, settings, and documentation
  changes resolved together. Keep prediction tests independent of autocorrect
  and wait for window activation before testing mode shortcuts on X11.
- Add this changelog and a README link. Require future changes to update it in
  `AGENTS.md`, alongside the existing service restart and active-status check.

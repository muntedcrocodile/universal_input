# Universal Input

A floating, keyboard-driven editor for text fields on your Linux desktop.
Write in Markdown or an editable rendered view, reuse recent drafts and clipboard
entries, and send the result back when you are ready. **The original field stays
unchanged until you press Ctrl+Enter.**

![Rendered editor with task items, an editable code-language header, and separate Recents and Clipboard lists](docs/images/rendered.png)

Built for **Linux/X11**, including an individual **Qubes OS Qube**. This is an early
release, tested on Debian 13. Field detection depends on accessibility support;
**Ctrl+Space** provides a manual fallback. Wayland and cross-Qube editing are not
supported yet.

See the [changelog](CHANGELOG.md) for features, fixes, and update notes.

## Try it

Run these commands inside the desktop session where you want to edit text. On
Qubes OS, install in the application Qube, **not dom0**.

```sh
git clone https://github.com/muntedcrocodile/universal_input.git
cd universal_input
./scripts/install-deps
./scripts/run --demo
```

The dependency installer uses Debian's `apt` and asks for `sudo`. It installs Python,
PyQt6, AT-SPI, Xlib, Pygments, Enchant, PyYAML (`python3-yaml`), and the Australian
English spelling dictionary.
Python 3.11 or later is required. In a template-based Qube, install dependencies in
its TemplateVM so they survive a Qube restart; keep this checkout in the AppVM's home
directory. Other distributions need the equivalent packages.

Demo mode uses sample-free, in-memory drafts. It does not monitor applications,
read the system clipboard, or save history. Close it with **Ctrl+Escape**.
Then start desktop integration:

```sh
./scripts/run
```

## Start automatically

Quit any manually started instance using its tray menu, then run:

```sh
./scripts/install-service
./scripts/install-desktop
```

This installs and enables a **systemd user service**, starts it now, and adds a
login hook to supply the X11 display environment. The second command adds an
application-menu launcher. No root service or lingering user session is needed.
The service template is in [packaging/systemd](packaging/systemd/universal-input.service.in).

```sh
systemctl --user status universal-input
systemctl --user restart universal-input
journalctl --user -u universal-input -n 50
```

The service restarts after an unexpected failure; choosing **Quit** stops it until
you start it again or log in again. The checkout must stay at its installed path.
After moving it, rerun `./scripts/install-service`. To update:

```sh
git pull --ff-only
./scripts/install-deps
./scripts/install-service
```

To turn automatic startup off and stop the app:

```sh
systemctl --user disable --now universal-input
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/universal-input.desktop"
```

## From a field to a finished draft

1. **Select a text field.** Accessible fields open automatically when `automatic_popup` is enabled. Otherwise, press
   **Ctrl+Space**; the fallback uses Select All and Copy to load the field.
2. **Write in the floating editor.** Switch between **Raw** and **Rendered** with
   **Ctrl+M**. Your draft is separate from the original field.
3. **Press Ctrl+Enter to insert.** The app replaces the field's contents. The
   clipboard offers Markdown to plain editors and HTML to rich editors; the
   destination chooses which format to accept.

**Ctrl+Escape**, or two quick **Escape** presses, saves the draft to Recents and
closes without changing the field. One Escape dismisses an open popup.
The editor also saves and closes when you switch focus to another window, leaving
focus where you moved it. Its own controls and menus keep the editor open. Reopening
the same accessible, unchanged field restores its draft during the current session.
The tray menu can pause automatic opening, clear histories, or quit.

## One place to write

- **Raw and Rendered views.** Syntax-highlighted Markdown source, editable formatted
  text, fenced code with language headers, tasks, links, quotes, and tables.
- **Keyboard navigation.** Hold Tab and press Left/Right to select useful parts:
  a code block's language and body, a link's label and URL, tasks, or table cells.
- **Line tools.** A muted line-number gutter, Ctrl+L to select a whole line, Ctrl+G
  to jump to a line, and Ctrl+[ / Ctrl+] to indent selected blocks.
- **Local writing assistance.** Common typos and missing apostrophes correct as
  you type, including `dont` → `don't` and `ill go` → `I'll go`. Ctrl+Alt+Left/Right
  selects spelling and grammar issues; arrows and Enter choose a correction.
  Alt+A adds unrecognised words to your persistent personal dictionary.
- **Two history lists.** Ctrl+R highlights Recents; Ctrl+P highlights Clipboard.
  Alt+1–9 inserts an item; Alt+I accepts any retained item's number.
  Ctrl+Shift+Left/Right extends the text selection by one word.
- **A floating workspace.** Frameless and translucent, with monospace editing and
  neutral dark colours accented in `#007e00`. Drag the toolbar to move it; use the
  bottom-right grip to resize. It bypasses tiling window management, including i3.

### Write source or edit the result

Raw view uses Pygments highlighting for Markdown and recognised code languages.
The toolbar shows the configured shortcuts; inserted templates select their first
useful placeholder so you can type immediately.

![Raw Markdown editor with syntax highlighting, line numbers, and quick-insert shortcuts](docs/images/raw.png)

### Correct words without leaving the draft

Suggestions keep typing focus in the editor. Escape dismisses the popup and leaves
the word selected; personal dictionary entries persist across sessions.
Select a personal dictionary word and right-click to remove it from the dictionary.
Spelling uses red underlines; grammar uses blue. The built-in English grammar
rules cover repeated words, common pronoun/verb agreement errors, and selected
`a`/`an` mistakes, plus lowercase sentence starts. They run offline and are not a
comprehensive grammar analysis.

Autocorrect runs when you type a space or punctuation, with **Ctrl+Z** to undo the
correction. It waits for a following verb before changing `ill` to `I'll`, so
“feel ill” and “ill health” stay intact. Loaded and pasted drafts receive
suggestions without being rewritten. Code, URLs and email addresses are excluded.
Sentence starts after `.`, `?`, and `!` are capitalised as you finish the word,
with exceptions for common abbreviations and decimals.

![Spelling suggestions for a selected word, with numbered choices and an Add to dictionary shortcut](docs/images/spelling.png)

### Insert and grow tables

Choose a size from the Table grid. In Rendered view, hover over a cell to reveal
**+** controls for adding rows and columns. These changes support undo.
For larger tables, choose **Custom size…** (or press **C** in the grid). The entry
popup asks for rows, including the header, then columns.

![In-window grid picker for inserting a Markdown table](docs/images/table-picker.png)

## Settings and shortcuts

Settings live in `~/.config/universal-input/config.yaml`, or
`$XDG_CONFIG_HOME/universal-input/config.yaml`. Defaults are created on the first
normal launch. [config.example.yaml](config.example.yaml) lists every setting and
binding. Existing `config.json` settings migrate automatically on first launch;
the original JSON is retained and YAML takes precedence afterwards.

| Setting | Default |
| --- | --- |
| Recent drafts / clipboard entries retained | 50 each; configurable from 0 to 500 |
| Window width / height | 60% / 66.67% of the available screen |
| Editor font size | 16 px; Ctrl+Shift+Plus/Minus saves changes immediately |
| Indentation | 4 spaces |
| Spelling dictionary | `en_AU` |
| Automatic popup | `automatic_popup: true`; set to `false` for manual opening with Ctrl+Space or the tray |
| Inline word predictions | Enabled when the optional local model is installed; tap Tab to accept grey text |
| Autocorrect / basic grammar checking | Both enabled; set `autocorrect` / `grammar_check` to `false` to disable independently |
| App keybindings | Configurable, with aliases or disabled bindings |
| Quick inserts | Ordered YAML recipes with custom labels, hotkeys, text/file/command sources, and cursor placement |

Existing configurations retain their saved shortcuts. To use the new history
shortcuts, set `history_left: Ctrl+R` and `history_right: Ctrl+P` under
`keybindings` (or remove those two overrides to use the defaults).

Restart the service after editing the config file. The **[usage guide](docs/usage.md)**
contains the complete shortcut table, configuration examples, navigation details,
and transfer behaviour.

### Configure quick inserts

The `quick_insert` list controls the toolbar order, labels, and hotkeys. Each recipe
inserts inline `text`, the contents of a UTF-8 `file`, or a `command`'s stdout. For
example, this configuration provides a meeting template, a signature, today's date,
and the existing table picker:

```yaml
quick_insert:
  - id: meeting
    label: Meeting
    shortcut: Ctrl+Alt+M
    text: |-
      ## Meeting title

      - [ ] First task
    select: Meeting title
    padding: true

  - id: signature
    label: Signature
    shortcut: Ctrl+Alt+S
    file: snippets/signature.txt
    format: plain
    cursor: end

  - id: date
    label: Date
    shortcut: Ctrl+Alt+D
    command: [date, '+%Y-%m-%d']
    format: plain

  - id: table
    label: Table ▾
    shortcut: Ctrl+Alt+T
    action: table
```

A configured list replaces the default recipes; retain any defaults you want from
[config.example.yaml](config.example.yaml). Omit `quick_insert` to use all defaults,
or set it to `[]` to remove them. Create the signature file relative to the config
directory (here, `~/.config/universal-input/snippets/signature.txt`). Files are read
on each activation; commands run only when their action is activated.

Markdown is the default format; `format: plain` inserts literal text. Use `select`
to highlight a placeholder, or `cursor` for `start`, `end`, or a zero-based character
offset. Set `toolbar: false` for a hotkey-only recipe, and use a list under `shortcut`
for aliases. Each insertion replaces the current selection and supports one-step
undo. Table recipes retain the interactive size picker.

Commands run asynchronously in the config directory using the service environment.
Argument lists run directly; strings run through `/bin/sh -c`. The default timeout
is 10 seconds, and file/command output is limited to 1 MiB. Restart the service after
editing the YAML. See the [quick-insert reference](docs/usage.md#configurable-quick-inserts)
for all fields, command limits, and cursor behavior in Raw and Rendered views.

## Local word predictions

Install the optional CPU runtime and the 101 MB quantized
[SmolLM2-135M base model](https://huggingface.co/ggml-org/SmolLM2-135M-GGUF):

```sh
sudo apt-get install --no-install-recommends build-essential python3-venv cmake
./scripts/install-completion
./scripts/start-service --restart
```

The installer builds a pinned llama.cpp Python runtime in a separate environment,
downloads and verifies the model once, and stores both under
`~/.local/share/universal-input/` (or `$XDG_DATA_HOME/universal-input/`).
Predictions then run entirely offline in a persistent CPU worker. No text leaves
the machine, and inference never blocks typing.

Grey inline text completes the current word or suggests one next word. Generation
can use multiple model tokens and stops when whitespace is reached.
Tap **Tab** to accept; **Escape** dismisses it. Holding **Tab+Left/Right** still
navigates Markdown parts. Predictions appear only at line endings or immediately
before a space, with no selection. They never enter history or pasted content until
accepted, and are shortened or hidden if the visible line has insufficient room.

The `completion` settings control the short context (128 tokens), debounce (100 ms),
generation limit (12 tokens), CPU threads (2), and optional model/runtime paths.
Set `completion.enabled` to `false` to unload the worker after restarting.
See [config.example.yaml](config.example.yaml). A missing runtime leaves ordinary
editing available; the model is primarily intended for short English continuations.

## Data and compatibility

Draft history, clipboard history, and the personal dictionary stay on this machine.
There is no cloud service, account, telemetry, or network spellchecker. History is
**unencrypted local data** with owner-only file permissions. Password fields are
excluded from automatic opening, but explicitly copied text can enter clipboard
history. Set a history limit to `0` to disable that list, or clear both lists from
the tray menu. Active drafts are saved on close/insert, not continuously against a
crash.

Automatic detection needs editable AT-SPI objects. Some browser, Electron,
terminal, remote-desktop, or custom controls do not expose usable fields. The
Ctrl+Space fallback requires ordinary Ctrl+A/C/V behaviour and cannot verify the
identity or contents of a particular field. If copy fails, the editor opens blank
and reports that insertion uses the current selection.

Complex existing rich documents are not imported losslessly. Editing in Rendered
view can normalize Markdown syntax; switching views resets undo history. A
single-line target cannot accept a multiline document. Review an unverified
insertion before retrying. More details are in the
[integration limits](docs/usage.md#current-integration-limits).

In Qubes OS, the app only sees its own Qube. No dom0 policy changes are made; Qubes
may retain its trusted VM-colour border. Transparency depends on the compositor.

## Development

```sh
sudo apt-get install --no-install-recommends python3-pytest xvfb xauth dbus-daemon
./scripts/test -q
```

Tests use an isolated Xvfb display, D-Bus session, and disposable target app. They
cover capture, explicit insertion, clipboard restoration, draft recovery, editing,
formatting, spelling, navigation, and configuration without pasting into your apps.

To regenerate the screenshots using only synthetic sample text:

```sh
xvfb-run -a -s '-screen 0 1800x1200x24' ./scripts/screenshots
```

The UI lives in `editor.py`, `design.py`, and the editing helpers; `app.py`
coordinates capture and insertion. `accessibility.py` and `x11.py` provide desktop
integration; `storage.py` owns configuration and persistence.
[Report a bug or suggest a change](https://github.com/muntedcrocodile/universal_input/issues).

## License

Copyright © 2026 muntedcrocodile. Licensed under the
**GNU Affero General Public License, version 3 or later (AGPL-3.0-or-later)**.
See [LICENSE](LICENSE) for the full terms. Dependencies retain their own licenses.

The palette draws from [VS Code Dark](https://github.com/microsoft/vscode/blob/main/extensions/theme-defaults/themes/dark_vs.json)
and [Dark+](https://github.com/microsoft/vscode/blob/main/extensions/theme-defaults/themes/dark_plus.json),
with green replacing blue accents. The UI uses Lato and Nimbus Mono PS when
available, with system font fallbacks.

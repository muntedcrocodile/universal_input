# Universal Input

A floating, keyboard-driven draft editor for **Linux/X11 applications in this Qube**.
Selecting an accessible text field opens its complete contents in a centered window,
approximately half the screen width and one third its height. The translucent, frameless window can be moved by dragging its command bar
and resized from its bottom-right grip. Nothing is written back until **Ctrl+Enter**.
**Escape** closes immediately and saves the draft to Recents, without a prompt.

The editor uses X11 `override_redirect`, so i3 does not tile, reparent, or decorate
it. Dragging and resizing are handled by the app. No i3 rule is required with the
standard Qubes GUI settings; Qubes can still draw its trusted VM-colour border.
A dom0 policy that explicitly disables override-redirect windows can override this
request. This app does not change dom0 policy.

The interface uses a dark translucent panel with **#007e00** highlights, Lato controls,
Bitstream Charter rendered prose, and Nimbus Mono PS raw text. Font fallbacks apply
where those fonts are unavailable. Transparency depends on the desktop compositor.

![Universal Input preview](docs/ui-preview.png)

## Run

On Debian 13 (the dependencies are already installed in this development Qube):

```sh
./scripts/install-deps
./scripts/run
```

Use `./scripts/run --demo` to try the editor without monitoring applications or writing
history. `./scripts/install-desktop` adds an application-menu launcher. To also start
at login, run `./scripts/install-desktop --autostart`.

The tray menu can pause automatic opening, clear history, or quit. After cancelling
or inserting, the original field is suppressed until focus moves elsewhere; use
**Ctrl+Space** to reopen it immediately. Only one desktop instance runs at a time.

## Editing and inserting

The **top-left dropdown** selects the draft view independently of the target:

- **Raw** shows and edits literal Markdown source.
- **Markdown rendered** shows an editable formatted document, including tables.

Switching views without making edits preserves the raw source exactly. Editing the
rendered document uses Qt's Markdown serializer when returning to Raw or inserting;
spacing and Markdown syntax may be normalized. Switching views resets Qt's undo stack.

At insertion, the clipboard temporarily offers **HTML to rich editors** and **Markdown
to plain editors**. The receiving application chooses the format it supports. The app
selects the original field's complete contents through accessibility and pastes once,
then checks the resulting text. It never simulates Enter into the target. The previous
clipboard is restored if another application has not replaced it in the meantime.
A changed, closed, inaccessible, or incorrectly focused target leaves the draft open.

| Shortcut | Action |
| --- | --- |
| Ctrl+Enter | Replace the entire original field |
| Esc | Save the draft to Recents and close without changing the field |
| Ctrl+Space | Open the current field, or a blank draft for insertion at the original cursor |
| Ctrl+1 / Ctrl+2 | Raw / Markdown rendered |
| Ctrl+Shift+M | Toggle draft view |
| Ctrl+B / Ctrl+I | Toggle bold / italic |
| Ctrl+U | Underline in rendered mode; `__bold__` in Raw (Markdown has no standard underline) |
| Ctrl+Shift+X | Strikethrough |
| Ctrl+\` | Inline code |
| Ctrl+Left / Ctrl+Right | Highlight recent-entry / clipboard history |
| Alt+1 … Alt+9 | Insert that numbered item from the highlighted history |
| Ctrl+Alt+T | Open the table size grid |
| Ctrl+Z / Ctrl+Y | Undo / redo within the current view |

The top toolbar inserts **tables, fenced code, task lists, quotes, links, and dividers**.
The Table dropdown opens a 10-column × 8-row grid inside the editor. Hover over cells
to preview the dimensions, then click to insert; arrow keys and Enter also work.
The first row is the header. Click elsewhere to dismiss the picker, or press Escape
to save and close the entire draft. Larger tables can be expanded using the row/column
controls. The picker uses no modal dialog or separate native window.
In rendered mode, hover over a
cell to show green row/column insertion guides. Click the **+** on the right to insert
a row below that cell, or the **+** above to insert a column to its right. Hover near
the first row's top edge or first column's left edge to insert before them. Row/column
changes are undoable and survive conversion back to Markdown.

## Persistent history and configuration

The two lists below the editor contain closed or successfully inserted drafts (left) and copied
text (right). Click an item or use the history shortcuts to insert at the draft cursor,
replacing any selected draft text. History insertion does not touch the target field.

Files live in **`~/.config/universal-input/`**, or
`$XDG_CONFIG_HOME/universal-input/` when set:

- `config.json`: retained entry counts, loaded at startup.
- `history.json`: both histories, newest first, including rich clipboard data when available.

Default `config.json`:

```json
{
  "recent_entries_limit": 50,
  "clipboard_entries_limit": 50
}
```

Set either limit to an integer from **0 to 500**; zero disables that history. Restart
the app after changing configuration. Reduced limits trim the saved history on the
next launch. The first nine items have Alt+number shortcuts; the rest can be scrolled
and clicked. Repeated text moves to the top instead of creating duplicates.

History is saved atomically, with owner-only directory/file permissions (`0700`/`0600`).
It is local, unencrypted JSON. Empty entries and text over 100,000 characters are not
retained. Password fields are excluded from automatic editing, but text explicitly
copied to the system clipboard is eligible for clipboard history. Use **Clear history**
in the tray menu to remove both saved lists. Malformed history files are preserved as
`history.invalid-<timestamp>.json`; invalid configuration is reported without overwriting it.
Closing with Escape, the Close button, or Quit saves the current draft to Recents.
During the same session, reopening the same accessible field restores its saved draft,
view mode, and cursor if the underlying field is unchanged. If the field has changed,
its current contents are loaded instead; the old draft remains in Recents. Field-to-draft
associations are memory-only (up to 50 fields); Recents persist across restarts.
If history retention is disabled or the draft exceeds the size limit, it remains eligible
for same-session field restoration but is not persisted in Recents. Active drafts are not
continuously saved against a crash.

## Current integration limits

- X11 and applications exposing editable **AT-SPI accessibility** objects are required.
  This is not yet a hook into every possible custom-drawn input widget. Some browser,
  Electron, terminal, remote-desktop, and sandboxed controls do not expose usable fields.
  **Ctrl+Space** also works without accessibility: it opens a blank draft and pastes
  at the original cursor/selection. In this fallback, existing text cannot be loaded,
  insertion cannot be verified, and automatic same-field draft restoration is unavailable.
  The original window is checked before pasting; no select-all command is sent.
- Only this Qube is supported. There is no dom0 integration or cross-Qube transport.
  A future design can reuse the editor with a target adapter per Qube; it would need
  an explicit transport and focus-routing design.
- AT-SPI imports all exposed text and basic bold/italic/underline/strike attributes.
  Existing complex rich documents (links, embedded media, table structure, application-
  specific styling) are not faithfully reconstructed by this first adapter. New tables
  created in the draft export as Markdown and HTML.
- Paste-format selection is controlled by the destination application. Apps that strip
  HTML, normalize text, reject accessibility selection, or do not implement normal
  Ctrl+V may need a dedicated adapter. Verification checks text, not rich-style fidelity.
  On an unverified transfer, inspect the original field before retrying.
- A single-line target cannot hold a multiline document. App-side normalization is
  reported as an unverified insertion rather than silently accepting different content.
- The editor handles up to one million source characters. It does not capture keystrokes
  typed into the original field during the short interval before a focus event is received.

## Development

```sh
sudo apt-get install --no-install-recommends python3-pytest xvfb xauth dbus-daemon
./scripts/test -q
```

Desktop integration tests use an isolated Xvfb display, D-Bus session, and disposable
Qt target application; they never paste into the user's applications. The tests cover
focus detection, field loading, draft isolation, cancellation, password/read-only
exclusion, hotkeys, rich/Markdown transfer, clipboard restoration, external edits,
clearing a field, persistent history retention, Escape draft recovery, view conversion,
and table row/column insertion.

`editor.py`/`design.py` own the UI; `tables.py` owns hover controls; `history.py`/`storage.py` own
retention; `accessibility.py` and `x11.py` provide the Linux adapter; `app.py` coordinates
capture and explicit insertion. No web service is used.

References: [AT-SPI](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/),
[Qt text editing](https://doc.qt.io/qt-6/qtextedit.html),
[Qt clipboard MIME data](https://doc.qt.io/qt-6/qmimedata.html).

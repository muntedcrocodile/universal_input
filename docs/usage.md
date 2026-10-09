# Using Universal Input

[Back to the README](../README.md)

## Editing and inserting

Set `"automatic_popup": false` in `config.json` to open only with **Ctrl+Space**
or the tray menu. The default is `true`; restarting applies a change. Focus
tracking continues in manual mode so Ctrl+Space can find the selected field.

The **top-left dropdown** selects the draft view independently of the target:

- **Raw** shows and edits literal Markdown source with Pygments syntax highlighting, including recognised fenced code languages.
- **Rendered** shows an editable formatted document, including tables.

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
| Esc | Dismiss suggestions or the table picker; keep the selected word |
| Ctrl+Esc / double Esc | Save the draft to Recents and close without changing the field |
| Ctrl+Space | Open the current field; use Select All and Copy if accessibility is unavailable |
| Ctrl+1 / Ctrl+2 | Raw / Rendered |
| Ctrl+M | Toggle Raw / Rendered (Ctrl+Shift+M also works) |
| Ctrl+B / Ctrl+I | Toggle bold / italic |
| Ctrl+U | Underline in rendered mode; `__bold__` in Raw (Markdown has no standard underline) |
| Ctrl+Shift+X | Strikethrough |
| Ctrl+\` | Inline code |
| Ctrl+Alt+Left / Ctrl+Alt+Right | Select the previous / next spelling or grammar issue |
| Ctrl+Left / Ctrl+Right | Move the cursor one word at a time |
| Ctrl+Shift+Left / Ctrl+Shift+Right | Highlight Recents / Clipboard history |
| Alt+1 … Alt+9 | Choose a spelling popup item, or insert that numbered history item when no popup is open |
| Alt+Enter | Reopen suggestions for a selected spelling or grammar issue |
| Alt+A | Add the selected misspelled word to the personal dictionary |
| Ctrl+Shift+Plus / Ctrl+Shift+Minus | Increase / decrease editor font size; saved immediately |
| Ctrl+Alt+T | Open the table size grid |
| Ctrl+Alt+C / Ctrl+Alt+L | Code block / task list |
| Ctrl+Alt+Q / Ctrl+Alt+K / Ctrl+Alt+D | Quote / link / divider |
| Hold Tab + Left / Right | Select the previous / next editable Markdown part |
| Ctrl+[ / Ctrl+] | Dedent / indent the current line or every selected line |
| Ctrl+L | Select the whole logical line, including its newline; repeat to extend to the next line |
| Ctrl+G | Enter a line number, then press Enter to jump there |
| Alt+I | Enter an item number from the highlighted Recents / Clipboard list, then press Enter to insert |
| Ctrl+Z / Ctrl+Y | Undo / redo within the current view |

The editor gutter uses muted, right-aligned line numbers with a brighter current line.
Wrapped text keeps one number. Raw mode counts source lines; Rendered counts text
paragraphs and code lines (table cells are separate paragraphs). Ctrl+G uses the
current view's numbering. Escape dismisses either numeric popup without editing.
Alt+I supports the entire retained history, including entries above 9, and inserts
at the saved cursor or replaces the saved selection. Its list is captured when the
popup opens so a new clipboard item cannot change the numbered choice mid-entry.
Configure these shortcuts with `select_line`, `goto_line`, and `insert_history_number`.

The top toolbar inserts **tables, fenced code, task lists, quotes, links, and dividers**.
Templates insert at the current cursor and select their useful placeholder, such as
the code language, first task, link label, or first table header. Typing replaces it immediately.
The mode selector and toolbar buttons show their configured shortcuts.
The **Template** button inserts a complete sample document at the cursor in either
mode and selects its title for editing. It includes headings, text formatting,
nested lists, tasks, links, quotes, tables, dividers, image syntax, and code blocks
in several languages. Edit the bundled [Markdown template](../universal_input/templates/markdown.md)
to customise it. The insertion can be undone in one step.
The Table dropdown opens a 10-column × 8-row grid inside the editor. Hover over cells
to preview the dimensions, then click to insert; arrow keys and Enter also work.
The first row is the header. Click elsewhere or press Escape to dismiss the picker.
Press Ctrl+Escape or double Escape to save and close the entire draft. Larger tables can be expanded using the row/column
controls. The picker uses no modal dialog or separate native window.
Rendered tables have faint, roughly 10% opacity cell borders. Hover over a
cell to show green row/column insertion guides. Click the **+** on the right to insert
a row below that cell, or the **+** above to insert a column to its right. Hover near
the first row's top edge or first column's left edge to insert before them. Row/column
changes are undoable and survive conversion back to Markdown.

## Tab navigation, indentation, and the last line

**Hold Tab and press Left/Right** to move between editable parts. Tapping Tab accepts
a visible grey word prediction on release; otherwise it inserts nothing and does
not move keyboard focus. Releasing Tab restores ordinary arrow-key
navigation. The selection wraps at the first/last part of the document.

With the [optional local model installed](../README.md#local-word-predictions),
pausing briefly while typing offers the rest of a word or one next word.
Generation continues across model tokens until whitespace completes that word;
an unfinished word at the token limit is not shown.
Only the last 128 tokens are used by default. Suggestions are allowed at the end
of a line or immediately before an existing space, never inside an existing word
or while text is selected. Typing, moving the cursor, changing mode, selecting
text, or leaving the editor clears the old suggestion. Escape dismisses it.
Suggestions are paint-only: copying, saving, word counts, and insertion ignore
them until Tab accepts. Acceptance is one undo step. Tab navigation chords and
Shift+Tab/Ctrl+Tab never accept. Suggestions fit the visible line and leave room
for existing text after the cursor.

The `completion` object in `config.json` supports `enabled`, `debounce_ms` (0–2000),
`context_tokens` (32–512), `max_tokens` (4–32), and `threads` (1–8).
Empty `python_path` and `model_path` use the installer's standard locations;
otherwise supply the interpreter with `llama_cpp` installed and a local GGUF model.
Restart after editing these settings. Installation requires internet access once;
prediction uses a private local subprocess with no network API or prompt logging.

- Code blocks: language first, then the whole code body.
- Task/list items: the complete item text, leaving its marker intact.
- Links: label text, then destination URL.
- Tables: individual cells, including empty cells.
- Quotes, headings, and other text blocks: their text.

In Rendered mode, each code block has its own bordered container and a persistent,
editable language header. The language stop selects that header field; the next stop
selects the code body. Link URL stops open a small in-window field.
Changes apply to the draft immediately; Tab+Left/Right continues navigating,
Enter moves to the next part, and Escape returns to the document. Raw mode selects
the corresponding source directly. Code insertion starts at the language stop in both
modes. Typing replaces the selected part. Code headers and their layout spacing are
editor controls and are excluded from submitted Markdown, text, and HTML.

**Ctrl+]** indents the current line or every line touched by a selection; **Ctrl+[**
removes up to one indentation level. A selected block stays selected for repeated
indent/dedent, and each operation is one undo step. `indent_width` in `config.json`
sets the number of spaces (default **4**, allowed **1–16**). No tab characters are
inserted. An existing leading tab from pasted text can be removed by dedenting.

The editor keeps one extra trailing newline so there is always an empty final line
available for writing. That editor-added newline is excluded from the Markdown,
plain text, and HTML sent to the target or saved in history. Existing source newlines
are preserved in Raw mode; Rendered mode retains the documented Markdown serialization
behaviour.

## Spelling, autocorrect, grammar and font size

Local Enchant/Hunspell checking underlines misspelled prose in red in both views. Code,
URLs, email addresses, and Markdown link destinations are skipped. Select an
underlined word (double-click, or Ctrl+Alt+Left/Right) to open its suggestions. Use the
arrow keys and Enter, click an item, or use its displayed Alt+number shortcut.
Press **Alt+A**, or choose the final “Add to dictionary” item, to save a personal word
for future sessions. This action has its own shortcut instead of an Alt+number slot.
To remove a saved word, select it and right-click, then choose **Remove from personal
dictionary**. This option appears only for personal entries. Removal is saved
immediately and spelling is checked again; words in the main dictionary remain valid.
Typing replaces the selected misspelling immediately; the popup keeps keyboard focus
in the editor. **Escape** dismisses suggestions and leaves the word selected.
**Ctrl+Escape**, or two Escape presses within 400 milliseconds, saves and closes the
whole editor. Typing or clicking between Escape presses resets that double-press sequence.

English writing rules also recognise missing apostrophes that a dictionary alone
can miss. For example, `ill go` suggests `I'll go`, while “feel ill”, “ill health”,
and “ill will” are left alone. Ambiguous words such as `well`, `were`, `cant`, and
`wont` are not automatically changed.

**Autocorrect** fixes a curated set of common typos and contractions when you
finish a word with a space, punctuation, or Enter. Examples include `teh` → `the`,
`dont` → `don't`, `im` → `I'm`, and lowercase `i` → `I`. `ill` needs a following
recognised verb: type `ill go ` to get `I'll go `. **Ctrl+Z** immediately restores
the original spelling, retaining the space or punctuation; keep typing to leave
it as written. Corrections preserve formatting and work in both views. Opening,
pasting, inserting history, and switching views never trigger autocorrect.
Set `"autocorrect": false` in the config to disable it while keeping suggestions.

Autocorrect also capitalises the first word after a full stop, question mark, or
exclamation mark once you finish typing that word. Common titles and abbreviations
(`Dr.`, `e.g.`), decimals, and ellipses are excluded. Loaded text gets a suggestion
instead of being rewritten. The first word in a field is left alone because a
field may contain a sentence fragment.

**Grammar** suggestions use blue underlines and the same navigation and correction
popup as spelling. They explain repeated words (`the the`), common pronoun/verb
agreement errors (`They is` → `They are`), and selected article mistakes (`a apple`
→ `an apple`), plus lowercase sentence starts. Apart from sentence capitalisation,
grammar corrections require your choice. Grammar and built-in contraction suggestions do not offer “Add to
dictionary”. Set `"grammar_check": false` to disable grammar suggestions separately.
These are limited, local English rules, not a complete grammar or style checker;
they may miss errors or offer an unsuitable suggestion. Both writing features
apply only to English dictionaries; other languages retain dictionary spelling.

The default language is Australian English (`en_AU`). Set `spellcheck_language` to
another installed Enchant dictionary if needed. Install its corresponding Hunspell
language package first. No text is sent to a server. Spelling/grammar underlines and Raw
syntax colours are display-only and are not inserted into the target.

Ctrl+Shift+Plus and Ctrl+Shift+Minus change the editor's base font size by one pixel,
from 10 to 48. The size applies in both views and saves immediately in `config.json`;
reopening the draft or restarting the app restores it. Shifted `=` / `_` spellings
are included as shortcut aliases for keyboard layouts that need them.

## Persistent history and configuration

The two lists below the editor contain closed or successfully inserted drafts (left) and copied
text (right). Click an item or use the history shortcuts to insert at the draft cursor,
replacing any selected draft text. History insertion does not touch the target field.

Files live in **`~/.config/universal-input/`**, or
`$XDG_CONFIG_HOME/universal-input/` when set:

- `config.json`: retained entry counts, all application keybindings, spelling language, autocorrect, grammar checking, and editor font size.
- `history.json`: both histories, newest first, including rich clipboard data when available.
- `personal-dictionary.txt`: your added words, one per line. Clearing history keeps this dictionary.

The app fills in all default settings and keybindings on startup. See
[`config.example.json`](../config.example.json) for the complete defaults. For example,
these overrides change the mode shortcut and disable bold:

```json
{
  "recent_entries_limit": 50,
  "clipboard_entries_limit": 50,
  "spellcheck_language": "en_AU",
  "autocorrect": true,
  "grammar_check": true,
  "editor_font_size": 16,
  "indent_width": 4,
  "window_width_percent": 60,
  "window_height_percent": 66.67,
  "keybindings": {
    "toggle_mode": "F6",
    "bold": ""
  }
}
```

Use a Qt shortcut string (`"Ctrl+Alt+T"`), a list of aliases (`["F6", "Ctrl+M"]`),
or `""` / `[]` to disable a binding. Missing actions inherit their defaults.
The special `Tab+Left` / `Tab+Right` chords are supported for editor actions; the
`previous_part` and `next_part` actions can also use ordinary Qt shortcuts. Tab itself
is reserved for completion acceptance and navigation.
Unknown actions, invalid shortcuts, and shortcuts assigned to multiple actions
produce a configuration error. The `open` action controls the global shortcut;
`choice_1` through `choice_9` are shared by history and spelling suggestions.
The `close`, `dismiss_popup`, and `add_to_dictionary` actions control Ctrl+Escape,
Escape, and Alt+A respectively. Double-pressing the configured `dismiss_popup` key
closes the editor as well.
Standard text editing and widget navigation (typing, selection, arrows, undo/redo)
continue to use Qt's usual keys. Shortcut hints follow your configuration.

`window_width_percent` and `window_height_percent` set the centered window size as
percentages of the available screen (20–100). The minimum size needed to fit controls
still applies. These settings are loaded at startup and applied when a draft opens.

Set either limit to an integer from **0 to 500**; zero disables that history. Restart
the app after changing configuration. Reduced limits trim the saved history on the
next launch. The first nine items have Alt+number shortcuts; use Alt+I to insert any retained item by number, or scroll and click it. Repeated text moves to the top instead of creating duplicates.

History is saved atomically, with owner-only directory/file permissions (`0700`/`0600`).
It is local, unencrypted JSON. Empty entries and text over 100,000 characters are not
retained. Password fields are excluded from automatic editing, but text explicitly
copied to the system clipboard is eligible for clipboard history. Use **Clear history**
in the tray menu to remove both saved lists. Malformed history files are preserved as
`history.invalid-<timestamp>.json`; invalid configuration is reported without overwriting it.
Closing with Ctrl+Escape, double Escape, the Close button, or Quit saves the current draft to Recents.
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
  **Ctrl+Space** also works without accessibility: it sends Ctrl+A then Ctrl+C to
  load existing text, restoring the previous clipboard afterwards. At insertion it
  selects all again and replaces that field. If copying fails (including some empty
  fields), it opens a blank draft and reports that insertion uses the current selection.
  Browser fields that expose nested paragraphs as accessibility placeholders also
  use this copy fallback, including when opened automatically.
  This fallback requires ordinary editing shortcuts; the original window is checked,
  but same-field identity, changes made while drafting, and insertion success cannot
  be verified. Automatic same-field draft restoration is unavailable in this fallback.
- In Qubes OS, only the Qube running the app is supported. There is no dom0 integration or cross-Qube transport.
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

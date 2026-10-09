# Markdown template

A sample document to edit, copy, and explore in Raw or Rendered mode.

## Headings

Use headings to give a document structure.

### Heading level 3

#### Heading level 4

##### Heading level 5

###### Heading level 6

## Text formatting

Write **bold**, *italic*, ***bold italic***, and ~~strikethrough~~ text.
Use `inline code` for names such as `result` or `config.yaml`.

Separate paragraphs with a blank line. Unicode works too: café, 日本語, and 🦎.

This line ends with two spaces for a hard line break.  
This continues on the next line in the same paragraph.

Escape punctuation to show literal markers: \*asterisks\*, \_underscores\_, and \[brackets\].

## Lists

### Unordered list

- First item
- Second item
  - Nested item
  - Another nested item
- Third item

### Ordered list

1. Gather the requirements.
2. Write a first draft.
   1. Add examples.
   2. Review the details.
3. Share the finished document.

### Task list

- [x] Create the document
- [ ] Replace the example content
- [ ] Review and share

## Links

An [inline link](https://example.com), a [link with a title](https://example.com "Example website"),
and an automatic link: <https://example.com>.

Use a [reference link][example] when several places share the same destination.

[example]: https://example.com "Example website"

## Quotes

> A short quotation or an important note.
>
> Quotes can contain **formatting** and multiple paragraphs.
>
> > A nested quotation.

## Tables

| Feature | Example | Status |
| --- | --- | --- |
| Formatting | **Bold** and *italic* | Ready |
| Inline code | `print("hello")` | Ready |
| Links | [Example](https://example.com) | Ready |

### Column alignment

| Left aligned | Centred | Right aligned |
| :--- | :---: | ---: |
| Apples | Fruit | 3 |
| Carrots | Vegetable | 12 |
| Bread | Bakery | 1 |

## Code blocks

### Python

```python
def greet(name):
    return f"Hello, {name}!"

print(greet("world"))
```

### JavaScript

```javascript
const names = ["Ada", "Grace", "Linus"];
const greetings = names.map(name => `Hello, ${name}!`);
console.log(greetings.join("\n"));
```

### Bash

```bash
name="world"
printf 'Hello, %s!\n' "$name"
```

### JSON

```json
{
  "title": "Example document",
  "published": false,
  "tags": ["markdown", "template"],
  "version": 1
}
```

### SQL

```sql
SELECT name, COUNT(*) AS total
FROM examples
WHERE active = TRUE
GROUP BY name
ORDER BY total DESC;
```

### HTML

```html
<article>
  <h1>Hello, world!</h1>
  <p>A small example with <strong>bold text</strong>.</p>
</article>
```

### CSS

```css
.example {
  color: #007e00;
  padding: 1rem;
  border: 1px solid currentColor;
}
```

### Plain text

```text
No language-specific syntax is needed here.
    Indentation and spacing are preserved.
```

## Images

Replace the example path with your image's path or URL. The syntax is shown as
code so this template does not display a missing image.

```markdown
![A description of the image](path/to/image.png "Optional image title")
```

## Dividers

Use a horizontal rule to separate sections.

---

End of template. Replace these examples with your own content.

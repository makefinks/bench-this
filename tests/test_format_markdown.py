from scripts.format_markdown import format_markdown


def test_wraps_plain_and_list_prose_at_100_columns() -> None:
    plain = "word " * 30
    item = "- " + "detail " * 25

    formatted = format_markdown(plain.rstrip() + "\n" + item.rstrip() + "\n")

    assert max(map(len, formatted.splitlines())) <= 100
    assert formatted.splitlines()[-1].startswith("  ")


def test_preserves_frontmatter_fences_table_like_lines_and_indented_code() -> None:
    text = """---
description: this intentionally remains a single YAML scalar even when it is much longer than one hundred characters because frontmatter is data
---

```python
value = "this code line intentionally remains longer than one hundred characters and must not be modified by the prose formatter"
```

| column | another column with content that remains structurally intact |
    indented_code = "unchanged"
"""

    assert format_markdown(text) == text


def test_aligns_complete_tables_without_constraining_them_to_prose_width() -> None:
    text = """| Name|Description|
|---|---|
|short|much longer cell|
"""
    expected = """| Name  | Description      |
| ----- | ---------------- |
| short | much longer cell |
"""

    formatted = format_markdown(text, width=10)

    assert formatted == expected
    assert max(map(len, formatted.splitlines())) > 10
    assert format_markdown(formatted, width=10) == formatted


def test_preserves_table_alignment_markers_and_escaped_pipes() -> None:
    text = """| left | right | center |
| :--- | ---: | :---: |
| a \\| b | c | d |
"""
    expected = """| left   | right | center |
| :----- | ----: | :----: |
| a \\| b | c     | d      |
"""

    assert format_markdown(text) == expected


def test_preserves_markdown_hard_break() -> None:
    text = ("A long sentence with a deliberate hard break " + "word " * 20).rstrip() + "  \n"

    formatted = format_markdown(text)

    assert formatted.endswith("  \n")
    assert max(map(len, formatted.splitlines())) <= 100

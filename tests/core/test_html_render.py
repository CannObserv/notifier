"""Tests for src/core/notifications/html_render.py.

Pure-function tests — no Apprise, no I/O. Asserts cover:
- diff-fence styling produces the expected colored <span> structure;
- non-diff fences fall through to standard <pre><code>;
- HTML escaping survives XSS payloads inside diff lines;
- multiple diff fences in one body each get styled independently;
- plain Markdown outside fences renders correctly;
- _classify_diff_line is exhaustive over the prefixes we care about.
"""

from src.core.notifications.html_render import (
    _classify_diff_line,
    markdown_to_email_html,
)

# --- diff fence rendering ---------------------------------------------------


def test_diff_fence_added_line_gets_green_background():
    html = markdown_to_email_html("```diff\n+ added line\n```\n")
    assert "background:#e6ffec" in html
    assert "+ added line" in html


def test_diff_fence_removed_line_gets_red_background():
    html = markdown_to_email_html("```diff\n- removed line\n```\n")
    assert "background:#ffebe9" in html
    assert "- removed line" in html


def test_diff_fence_hunk_header_gets_meta_color():
    html = markdown_to_email_html("```diff\n@@ -1,3 +1,3 @@\n```\n")
    assert "color:#57606a" in html
    assert "@@ -1,3 +1,3 @@" in html


def test_diff_fence_context_line_renders_uncolored_block():
    html = markdown_to_email_html("```diff\n context unchanged\n```\n")
    # Context lines are wrapped in display:block but carry no background.
    assert "display:block" in html
    assert "background:#e6ffec" not in html
    assert "background:#ffebe9" not in html


def test_diff_fence_renders_pre_wrapper_with_monospace_styling():
    html = markdown_to_email_html("```diff\n+ x\n```\n")
    assert "<pre" in html
    assert "white-space:pre" in html
    assert "monospace" in html


def test_diff_fence_with_mixed_lines_styles_each_correctly():
    body = "```diff\n@@ -1,2 +1,2 @@\n- old\n+ new\n  same\n```\n"
    html = markdown_to_email_html(body)
    assert "background:#e6ffec" in html  # added
    assert "background:#ffebe9" in html  # removed
    assert "color:#57606a" in html  # meta
    # All four diff lines are present in order.
    add_pos = html.find("+ new")
    del_pos = html.find("- old")
    meta_pos = html.find("@@ -1,2 +1,2 @@")
    ctx_pos = html.find("same")
    assert -1 < meta_pos < del_pos < add_pos < ctx_pos


def test_diff_fence_escapes_html_inside_diff_lines():
    body = '```diff\n+ <script>alert("xss")</script>\n```\n'
    html = markdown_to_email_html(body)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_multiple_diff_fences_each_get_styled():
    body = "```diff\n+ first\n```\n\nbetween\n\n```diff\n- second\n```\n"
    html = markdown_to_email_html(body)
    assert html.count("background:#e6ffec") >= 1
    assert html.count("background:#ffebe9") >= 1
    assert "+ first" in html
    assert "- second" in html


# --- non-diff fences --------------------------------------------------------


def test_non_diff_fence_renders_as_standard_pre_code():
    html = markdown_to_email_html("```python\nprint('hi')\n```\n")
    # Standard mistune output for a fenced code block: <pre><code class="language-...">.
    assert "<pre>" in html
    assert "<code" in html
    # No diff-fence styling.
    assert "background:#e6ffec" not in html
    assert "background:#ffebe9" not in html


def test_unfenced_code_block_renders_as_standard_pre_code():
    html = markdown_to_email_html("```\nplain code\n```\n")
    assert "<pre>" in html
    assert "<code" in html
    assert "background:#e6ffec" not in html


# --- markdown outside fences ------------------------------------------------


def test_heading_outside_diff_fence_renders_as_h1():
    html = markdown_to_email_html("# Header\n\n```diff\n+ x\n```\n")
    assert "<h1>" in html
    assert "Header" in html


def test_bold_text_outside_diff_fence_renders_as_strong():
    html = markdown_to_email_html("This is **important** text.\n")
    assert "<strong>" in html
    assert "important" in html


def test_paragraph_outside_diff_fence_renders_as_p():
    html = markdown_to_email_html("Just a paragraph.\n")
    assert "<p>" in html
    assert "Just a paragraph." in html


# --- _classify_diff_line ----------------------------------------------------


def test_classify_added_line():
    assert _classify_diff_line("+ added") == "add"


def test_classify_removed_line():
    assert _classify_diff_line("- removed") == "del"


def test_classify_hunk_header():
    assert _classify_diff_line("@@ -1,3 +1,3 @@") == "meta"


def test_classify_file_marker_plus():
    assert _classify_diff_line("+++ b/file.py") == "meta"


def test_classify_file_marker_minus():
    assert _classify_diff_line("--- a/file.py") == "meta"


def test_classify_context_line():
    assert _classify_diff_line(" context") == "ctx"


def test_classify_empty_line_is_context():
    assert _classify_diff_line("") == "ctx"

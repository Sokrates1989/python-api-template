"""
Markdown formatting utilities for notification content.

Converts between HTML-style tags and Telegram MarkdownV2 format.
Supports: bold, italic, underline, code, preformatted blocks.
"""
from __future__ import annotations

import html
import re


def html_to_telegram_markdown(text: str) -> str:
    """
    Convert HTML-style tags to Telegram MarkdownV2 format.

    Telegram MarkdownV2 syntax:
    - *bold text*
    - _italic text_
    - __underlined text__
    - `inline fixed-width code`
    - ```preformatted code block```

    Also escapes special characters that must be escaped in Telegram MarkdownV2:
    _ * [ ] ( ) ~ ` > # + - = | { } . ! \

    Args:
        text (str): Input text with HTML tags (<b>, <i>, <u>, <code>, <pre>).

    Returns:
        str: Text formatted for Telegram MarkdownV2 parse mode.

    Example:
        >>> html_to_telegram_markdown("<b>bold</b> and <i>italic</i>")
        '*bold* and _italic_'
    """
    if not text:
        return ""

    # First, handle <pre> blocks (preserve content, escape inside)
    def escape_for_telegram(match: re.Match) -> str:
        """Escape special chars inside pre blocks."""
        content = match.group(1)
        return _escape_telegram_special_chars(content)

    # Extract and temporarily replace <pre> blocks
    pre_blocks: list[str] = []

    def store_pre_block(match: re.Match) -> str:
        """Store pre block and return placeholder."""
        content = match.group(1)
        escaped_content = _escape_telegram_special_chars(content)
        placeholder = f"\x00PRE{len(pre_blocks)}\x00"
        pre_blocks.append(f"```{escaped_content}```")
        return placeholder

    # Handle <pre>code</pre> and <pre><code>...</code></pre>
    result = re.sub(r"<pre>(.*?)</pre>", store_pre_block, text, flags=re.DOTALL)
    result = re.sub(
        r"<pre>\s*<code[^>]*>(.*?)</code>\s*</pre>",
        store_pre_block,
        result,
        flags=re.DOTALL,
    )

    # Handle inline <code>
    result = re.sub(
        r"<code[^>]*>(.*?)</code>",
        lambda m: f"`{_escape_telegram_special_chars(m.group(1))}`",
        result,
    )

    # Handle HTML tags — store formatted spans as placeholders so the
    # final _escape_telegram_special_chars pass does not re-escape the
    # MarkdownV2 marker characters (* and _) we just introduced.
    fmt_spans: list[str] = []

    def _store_fmt(marker_open: str, marker_close: str, content: str) -> str:
        """Escape content, wrap in MarkdownV2 markers, store as placeholder."""
        escaped_content = _escape_telegram_special_chars(content)
        placeholder = f"\x00FMT{len(fmt_spans)}\x00"
        fmt_spans.append(f"{marker_open}{escaped_content}{marker_close}")
        return placeholder

    result = re.sub(r"<b>(.*?)</b>", lambda m: _store_fmt("*", "*", m.group(1)), result)
    result = re.sub(r"<strong>(.*?)</strong>", lambda m: _store_fmt("*", "*", m.group(1)), result)
    result = re.sub(r"<i>(.*?)</i>", lambda m: _store_fmt("_", "_", m.group(1)), result)
    result = re.sub(r"<em>(.*?)</em>", lambda m: _store_fmt("_", "_", m.group(1)), result)
    result = re.sub(r"<u>(.*?)</u>", lambda m: _store_fmt("__", "__", m.group(1)), result)
    result = re.sub(r"<ins>(.*?)</ins>", lambda m: _store_fmt("__", "__", m.group(1)), result)

    # Restore pre blocks
    for i, block in enumerate(pre_blocks):
        result = result.replace(f"\x00PRE{i}\x00", block)

    # Escape remaining plain text (markers are still placeholders here).
    result = _escape_telegram_special_chars(result)

    # Restore formatted spans after escaping so their markers are untouched.
    for i, span in enumerate(fmt_spans):
        result = result.replace(f"\x00FMT{i}\x00", span)

    return result


def _escape_telegram_special_chars(text: str) -> str:
    """
    Escape characters that are special in Telegram MarkdownV2.

    Must escape: _ * [ ] ( ) ~ ` > # + - = | { } . !
    Note: Also escapes backslash itself to prevent escape sequence issues.

    Args:
        text (str): Text to escape.

    Returns:
        str: Escaped text safe for Telegram MarkdownV2.
    """
    # Characters that must be escaped in Telegram MarkdownV2, including backslash
    # Order matters: escape backslash first to avoid double-escaping
    result = text
    result = result.replace("\\", "\\\\")  # Escape backslashes first
    
    # Then escape other special characters
    special_chars = r"_[]()~`>#+=|{}.!-*"
    for char in special_chars:
        if char == "-":
            # Hyphen needs special handling as it can indicate range
            result = result.replace(char, "\\-")
        else:
            result = result.replace(char, f"\\{char}")
    
    return result


def telegram_markdown_to_html(text: str) -> str:
    """
    Convert Telegram MarkdownV2 format to HTML tags.

    Args:
        text (str): Input with Telegram markdown (*bold*, _italic_, etc.).

    Returns:
        str: HTML-formatted text.

    Example:
        >>> telegram_markdown_to_html("*bold* and _italic_")
        '<b>bold</b> and <i>italic</i>'
    """
    if not text:
        return ""

    result = text

    # Code blocks (must be first to avoid conflicts)
    result = re.sub(r"```(.*?)```", r"<pre>\1</pre>", result, flags=re.DOTALL)

    # Inline code
    result = re.sub(r"`([^`]+)`", r"<code>\1</code>", result)

    # Bold
    result = re.sub(r"\*([^*]+)\*", r"<b>\1</b>", result)

    # Italic (single underscore)
    result = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"<i>\1</i>", result)

    # Underline (double underscore)
    result = re.sub(r"__([^_]+)__", r"<u>\1</u>", result)

    # Strikethrough
    result = re.sub(r"~([^~]+)~", r"<s>\1</s>", result)

    return result


def format_telegram_message(
    title: str | None,
    message: str,
    app: str | None = None,
) -> str:
    """
    Format a notification for Telegram with optional title and app label.

    Output structure (all parts present):
        *__<UPPERCASE_TITLE>__*

        <message>

        _From: <app>_

    The "From:" prefix makes the italic footer self-explanatory in chat so
    readers immediately understand what the last line means. When multiple
    apps share the same Telegram chat this prevents ambiguity.

    Args:
        title (str | None): Optional title (will be uppercased, underlined, and bolded).
        message (str): Required message content.
        app (str | None): Application identifier appended as italic footer (e.g. "file-backup").
            Omitted when None or empty.

    Returns:
        str: Formatted message for Telegram MarkdownV2.

    Example:
        >>> format_telegram_message("Alert", "Something happened", "file-backup")
        '*__ALERT__*\\n\\nSomething happened\\n\\n_From: file\\-backup_'
    """
    # Convert HTML in message to Telegram markdown.
    telegram_message = html_to_telegram_markdown(message)

    # Build app footer as italic "From: <app>" line so the label is self-explanatory.
    app_footer = ""
    if app:
        escaped_app = _escape_telegram_special_chars(app)
        app_footer = f"\n\n_From: {escaped_app}_"

    if title:
        # Convert HTML in title, uppercase, underline, and bold.
        telegram_title = html_to_telegram_markdown(title)
        plain_title = telegram_title.replace("*", "").replace("_", "")
        formatted_title = f"*__{plain_title.upper()}__*"
        return f"{formatted_title}\n\n{telegram_message}{app_footer}"

    return f"{telegram_message}{app_footer}"


def format_email_content(
    title: str | None,
    message: str,
    app: str | None = None,
) -> tuple[str, str]:
    """
    Format notification content for email delivery.

    Args:
        title (str | None): Optional title (becomes email subject if provided).
        message (str): Message content (may contain HTML or markdown).
        app (str | None): App identifier for internal reference (not in message body).

    Returns:
        tuple[str, str]: (subject, html_body) where subject is derived from title
            or a default, and html_body is HTML-formatted content.

    Example:
        >>> format_email_content("Backup Done", "Job completed", "myapp")
        ('Backup Done', '<html>...</html>')
    """
    # Determine subject
    if title:
        subject = title
    else:
        # Use first line of message or default
        first_line = message.split("\n")[0][:50]
        subject = first_line if first_line else "Notification"

    # Convert any Telegram markdown to HTML
    html_message = telegram_markdown_to_html(message)

    # Build HTML body
    html_parts = ["<html><body>"]

    if title:
        # Title as header
        html_title = html.escape(title)
        html_parts.append(f"<h2>{html_title}</h2>")

    # Message content
    html_parts.append(f"<div>{html_message}</div>")

    # Footer with app reference (for internal tracking)
    if app:
        html_parts.append(f"<hr><p><small>From: {html.escape(app)}</small></p>")

    html_parts.append("</body></html>")

    html_body = "\n".join(html_parts)

    return subject, html_body

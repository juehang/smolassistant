"""
HTML sanitizer for Telegram messages.

This module provides functionality to ensure text only contains HTML tags allowed by Telegram
and properly escapes other special characters.
"""

import html
import re


def sanitize_telegram_html(text):
    """
    Sanitize a message to ensure it only contains HTML tags allowed by Telegram
    and properly escapes other special characters.
    
    Args:
        text: The text message to sanitize
        
    Returns:
        Sanitized text that can be safely sent to Telegram with HTML parsing mode
    """
    if not text:
        return text
    
    # Replace <br> tags with newlines first
    text = re.sub(r"<br\s*/?>|<\s*/\s*br>", "\n", text, flags=re.IGNORECASE)
    
    # Define patterns for allowed tags
    allowed_patterns = [
        # Simple tags
        r"<b>.*?</b>",
        r"<strong>.*?</strong>",
        r"<i>.*?</i>",
        r"<em>.*?</em>",
        r"<u>.*?</u>",
        r"<ins>.*?</ins>",
        r"<s>.*?</s>",
        r"<strike>.*?</strike>",
        r"<del>.*?</del>",
        r"<span class=\"tg-spoiler\">.*?</span>",
        r"<tg-spoiler>.*?</tg-spoiler>",
        r"<code>.*?</code>",
        r"<pre>.*?</pre>",
        r"<blockquote>.*?</blockquote>",
        r"<blockquote expandable>.*?</blockquote>",
        
        # Complex tags
        r"<a href=\"(?:http[s]?://[^\"]+|tg://[^\"]+)\">.*?</a>",
        r"<pre><code class=\"language-[a-zA-Z0-9]+\">.*?</code></pre>",
        r"<tg-emoji emoji-id=\"[0-9]+\">.*?</tg-emoji>",
    ]
    
    # Combine all patterns into a single pattern
    allowed_tags_pattern = "|".join(allowed_patterns)
    
    # Split the text into allowed tags and non-tag text
    parts = []
    last_end = 0
    
    for match in re.finditer(allowed_tags_pattern, text, re.DOTALL):
        start, end = match.span()
        
        # Add text before the tag (escaped)
        if start > last_end:
            parts.append(html.escape(text[last_end:start]))
        
        # Add the tag (unescaped)
        parts.append(match.group(0))
        
        last_end = end
    
    # Add any remaining text
    if last_end < len(text):
        parts.append(html.escape(text[last_end:]))
    
    # Join parts together
    sanitized_text = "".join(parts)
    
    # Replace HTML entities (except &lt;, &gt;, &amp;, &quot;)
    # with their corresponding characters
    def replace_entity(match):
        entity = match.group(1)
        if entity in ["lt", "gt", "amp", "quot"]:
            return f"&{entity};"
        return html.unescape(f"&{entity};")
    
    sanitized_text = re.sub(r"&([a-zA-Z0-9]+);", replace_entity, sanitized_text)
    
    return sanitized_text

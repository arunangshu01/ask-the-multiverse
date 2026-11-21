"""Small, dependency-free wikitext helpers: infobox parameter parsing with
brace/bracket depth tracking, link extraction and conversion to plain text."""

from __future__ import annotations

import html
import re

# Templates whose visible text is a page link: {{cl|Target|Label}} etc.
LINK_TEMPLATES = {"a", "apn", "c", "cl", "sl", "sld", "ml", "el", "vl", "g", "tv", "m", "n", "ll",
                  "gl", "glossary", "vg", "sll", "cld", "sldl", "mcu", "mc", "nl", "fc"}
# Templates that link to another wiki: {{Wc|wiki|Target|Label}}, {{DC|Target}}, {{WP|Target}},
# {{Wikipedia|Target|Label}}, {{Image Wiki|Target|Label}}, {{Star Wars|Target|Label}}.
EXTERNAL_TEMPLATES = {"wc": "wiki", "dc": "dc", "wp": "wikipedia", "w": "wiki", "wikipedia": "wikipedia",
                      "image wiki": "image", "star wars": "starwars", "imagewiki": "image"}
# Text-only label templates (no page link): {{Power|Energy Conversion}}, {{Ability|Target|Label}}.
LABEL_TEMPLATES = {"power", "ability", "speaker"}
# Appearance qualifiers keep their inner link text: {{Mentioned|[[X]]}}.
WRAPPER_TEMPLATES = {"mentioned", "recaponly", "flashback", "flashbackonly", "voiceonly", "1st",
                     "apn", "a", "minor", "visiononly", "picture", "imageonly", "corpse", "illusion",
                     "dream", "ghost", "death", "possessed", "impersonated", "decoy", "cameo",
                     "fictional", "unnamed", "1stchrono", "revisited", "photo"}

_REF = re.compile(r"<ref[^>/]*/>|<ref[^>]*>.*?</ref>", re.S | re.I)
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_BR = re.compile(r"<br\s*/?>", re.I)


def find_template(text: str, name_pattern: str) -> tuple[str, str] | None:
    """Return (template name, body) for the first `{{<name>...}}` matching the
    regex, with the body extended to the matching closing braces."""
    m = re.search(r"\{\{\s*(" + name_pattern + r")\s*(?=[|}\n])", text)
    if not m:
        return None
    depth = 1
    for tok in _BRACES.finditer(text, m.end()):
        depth += 1 if tok.group() == "{{" else -1
        if depth == 0:
            return m.group(1).strip(), text[m.end():tok.start()]
    return m.group(1).strip(), text[m.end():]


_BRACES = re.compile(r"\{\{|\}\}")
_PROTECTED = re.compile(r"<(gallery|nowiki|pre|math|tabber)\b[^>]*>.*?</\1\s*>", re.S | re.I)
_SPLIT_TOKENS = re.compile(r"<(?:gallery|nowiki|pre|math|tabber)\b|\{\{|\}\}|\[\[|\]\]|\|", re.I)


def split_top(body: str, sep: str = "|") -> list[str]:
    """Split on `|` only at depth 0 of {{ }} and [[ ]], never inside
    <gallery>, <nowiki>, <pre>, <math> or <tabber> blocks."""
    assert sep == "|"
    parts, start, depth_t, depth_l, pos = [], 0, 0, 0, 0
    while True:
        tok = _SPLIT_TOKENS.search(body, pos)
        if not tok:
            break
        t, pos = tok.group(), tok.end()
        if t.startswith("<"):
            block = _PROTECTED.match(body, tok.start())
            if block:
                pos = block.end()
        elif t == "{{":
            depth_t += 1
        elif t == "}}":
            depth_t = max(0, depth_t - 1)
        elif t == "[[":
            depth_l += 1
        elif t == "]]":
            depth_l = max(0, depth_l - 1)
        elif depth_t == 0 and depth_l == 0:
            parts.append(body[start:tok.start()])
            start = pos
    parts.append(body[start:])
    return parts


def params(body: str) -> dict[str, str]:
    """Named parameters of a template body (first occurrence wins, values stripped)."""
    out: dict[str, str] = {}
    for part in split_top(body)[1:]:
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        key = key.strip()
        if key and key not in out:
            out[key] = value.strip()
    return out


def infobox(text: str) -> tuple[str | None, dict[str, str]]:
    """Template name (e.g. 'Reality Template') and parameters of the page's
    'Marvel Database:* Template' infobox."""
    found = find_template(text, r"Marvel Database\s*:\s*[^|}\n]*?Template")
    if not found:
        return None, {}
    name, body = found
    return re.sub(r"^Marvel Database\s*:\s*", "", name).strip(), params(body)


def _template_name_args(inner: str) -> tuple[str, list[str]]:
    parts = split_top(inner)
    return parts[0].strip(), [p.strip() for p in parts[1:]]


def links(text: str) -> list[dict]:
    """Ordered link targets in wikitext: [[Target|label]], link templates and
    external-wiki templates. Each item: {target, label, external}."""
    out: list[dict] = []
    text = _COMMENT.sub("", _REF.sub("", text or ""))
    i = 0
    while i < len(text):
        if text.startswith("[[", i):
            end = _match(text, i, "[[", "]]")
            inner = text[i + 2:end]
            target, _, label = inner.partition("|")
            target = target.strip().lstrip(":")
            if target and not re.match(r"(?i)(file|image|category|media)\s*:", target):
                out.append({"target": _norm(target), "label": plain(label) if label else target,
                            "external": None})
            i = end + 2
        elif text.startswith("{{", i):
            end = _match(text, i, "{{", "}}")
            name, args = _template_name_args(text[i + 2:end])
            low = name.lower()
            positional = [a for a in args if "=" not in a.split("|")[0] or a.startswith("[[")]
            if low in EXTERNAL_TEMPLATES and positional:
                if low in ("wc", "w") and len(positional) >= 2:
                    out.append({"target": positional[1].strip(), "label": plain(positional[-1]),
                                "external": positional[0].strip().lower()})
                else:
                    out.append({"target": positional[0].strip(), "label": plain(positional[-1]),
                                "external": EXTERNAL_TEMPLATES[low]})
            elif low in LINK_TEMPLATES and positional and "[[" not in positional[0]:
                out.append({"target": _norm(positional[0]),
                            "label": plain(positional[1] if len(positional) > 1 else positional[0]),
                            "external": None})
            else:
                out.extend(links(text[i + 2 + len(name):end]))
            i = end + 2
        else:
            nxt = _NEXT_MARKUP.search(text, i + 1)
            i = nxt.start() if nxt else len(text)
    return out


def first_link(text: str) -> dict | None:
    found = links(text)
    if found:
        return found[0]
    bare = plain(text)
    return {"target": _norm(bare), "label": bare, "external": None} if bare else None


_NEXT_MARKUP = re.compile(r"\[\[|\{\{")
_NEXT_PLAIN = re.compile(r"\[\[|\{\{|\[http")
_PAIR = {"[[": re.compile(r"\[\[|\]\]"), "{{": re.compile(r"\{\{|\}\}")}


def _match(text: str, start: int, open_: str, close: str) -> int:
    """Index of the `close` that balances the `open_` at `start` (len(text) if unbalanced)."""
    depth = 0
    for tok in _PAIR[open_].finditer(text, start):
        depth += 1 if tok.group() == open_ else -1
        if depth == 0:
            return tok.start()
    return len(text)


def _norm(title: str) -> str:
    title = html.unescape(title).replace("_", " ").split("#", 1)[0]
    title = re.sub(r"\s+", " ", title).strip()
    return title[:1].upper() + title[1:] if title else title


def plain(text: str) -> str:
    """Readable plain text: links become their labels, link templates their
    label, every other template, reference, comment and tag is removed."""
    if not text:
        return ""
    text = _COMMENT.sub("", _REF.sub("", text))
    text = _BR.sub(" ", text)
    out, i = [], 0
    while i < len(text):
        if text.startswith("[[", i):
            end = _match(text, i, "[[", "]]")
            inner = text[i + 2:end]
            target, _, label = inner.partition("|")
            # [[:Category:X|label]] (leading colon) is a visible link; [[Category:X]] only categorises.
            if target.lstrip().startswith(":") or not re.match(r"(?i)\s*(file|image|category|media)\s*:", target):
                out.append(plain(label) if label else target.lstrip(" :").split("#")[0])
            i = end + 2
        elif text.startswith("{{", i):
            end = _match(text, i, "{{", "}}")
            name, args = _template_name_args(text[i + 2:end])
            low = name.lower()
            positional = [a for a in args if "=" not in a or a.startswith("[[")]
            if (low in LINK_TEMPLATES or low in EXTERNAL_TEMPLATES or low in LABEL_TEMPLATES) and positional:
                out.append(plain(positional[-1]))
            elif low in WRAPPER_TEMPLATES and positional:
                out.append(plain(positional[0]))
            i = end + 2
        elif text.startswith("[http", i):
            end = text.find("]", i)
            end = len(text) if end < 0 else end
            _, _, label = text[i + 1:end].partition(" ")
            out.append(label)
            i = end + 1
        else:
            nxt = _NEXT_PLAIN.search(text, i + 1)
            end = nxt.start() if nxt else len(text)
            out.append(text[i:end]); i = end
    s = "".join(out)
    s = _TAG.sub("", s)
    s = re.sub(r"'{2,}", "", s)
    s = html.unescape(s).replace("\u00a0", " ")
    s = re.sub(r"__[A-Z]+__", "", s)
    s = re.sub(r"\(\s*\)", "", s)
    return re.sub(r"\s+", " ", s).strip(" |;,")


def list_items(text: str) -> list[str]:
    """Plain-text values of a field written as a bullet list or ;/<br>-separated."""
    text = _BR.sub("\n", text or "")
    raw = re.split(r"\n\s*\*+|^\s*\*+|\n|;", text)
    return [v for v in (plain(r) for r in raw) if v]


def shorten(text: str, limit: int = 600) -> tuple[str, bool]:
    """Cut at a sentence boundary under `limit`; returns (text, was_shortened)."""
    text = text.strip()
    if len(text) <= limit:
        return text, False
    cut = text[:limit]
    stop = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[:stop + 1] if stop > limit * 0.4 else cut.rsplit(" ", 1)[0] + " ...").strip(), True


def first_paragraph(text: str) -> str:
    """First non-empty prose paragraph (skips headings, lists, tables, templates-only lines)."""
    for para in re.split(r"\n\s*\n", _COMMENT.sub("", text or "")):
        lines = [ln for ln in para.splitlines()
                 if ln.strip() and not re.match(r"\s*(=|\{\||\||!|\*|#|:)", ln)]
        candidate = plain("\n".join(lines))
        if len(candidate) > 20:
            return candidate
    return ""

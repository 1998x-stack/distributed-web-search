"""Robots meta/X-Robots-Tag indexing and outgoing link directives."""
import re


def robots_directives(response) -> set[str]:
    directives = set()
    values = [v.decode("utf-8", errors="ignore") for v in
              response.headers.getlist(b"X-Robots-Tag")]
    for tag in response.css("meta[name][content]"):
        name = (tag.attrib.get("name") or "").lower().strip()
        if name in ("robots", "googlebot", "distributedwebsearchbot"):
            values.append(tag.attrib.get("content", ""))
    for value in values:
        parts = set(re.findall(r"[a-zA-Z]+", value.lower()))
        if "none" in parts:
            directives.update(("noindex", "nofollow"))
        if "noindex" in parts:
            directives.add("noindex")
        if "nofollow" in parts:
            directives.add("nofollow")
    return directives

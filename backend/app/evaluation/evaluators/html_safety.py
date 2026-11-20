"""Conservative HTML fragment policy scanner, not an HTML sanitizer."""

from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

BLOCKED_TAGS = frozenset(
    {
        "script",
        "iframe",
        "object",
        "embed",
        "base",
        "form",
        "input",
        "button",
        "textarea",
        "select",
        "meta",
        "link",
        "svg",
        "math",
        "style",
        "template",
    }
)
URL_ATTRIBUTES = frozenset({"href", "src", "action", "formaction", "poster", "xlink:href"})
SAFE_SCHEMES = frozenset({"http", "https", "mailto", "tel"})


class _Scanner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.violations = []

    def handle_starttag(self, tag, attrs):
        if tag in BLOCKED_TAGS:
            self.violations.append(f"Blocked element: {tag}")
        for name, value in attrs:
            if name is None:
                continue
            if name.lower().startswith("on") or name.lower() in {"style", "srcdoc"}:
                self.violations.append(f"Blocked attribute: {name}")
            if name.lower() in URL_ATTRIBUTES:
                normalized = "".join(unquote(value or "").split()).lower()
                scheme = urlsplit(normalized).scheme
                if scheme and scheme not in SAFE_SCHEMES:
                    self.violations.append(f"Unsafe URL scheme in {name}")
                if normalized.startswith("//"):
                    self.violations.append(f"Protocol relative URL in {name}")

    handle_startendtag = handle_starttag

    def handle_entityref(self, name):
        pass


def evaluate(criterion_id: str, response: str, parameters: dict):
    if criterion_id != "html_safety":
        raise ValueError("Unknown HTML safety criterion")
    if not isinstance(response, str):
        raise ValueError("Response must be text")
    if len(response) > 100_000:
        raise ValueError("HTML exceeds scan limit")
    scanner = _Scanner()
    scanner.feed(response)
    scanner.close()
    passed = not scanner.violations
    detail = "; ".join(scanner.violations[:5]) if not passed else "No blocked HTML patterns found"
    return passed, float(passed), detail

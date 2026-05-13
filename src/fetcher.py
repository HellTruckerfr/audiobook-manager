import re
import urllib.request
import urllib.error


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _decode(raw: bytes) -> str:
    """Amazon.fr déclare UTF-8 mais sert souvent du latin-1/windows-1252.
    On essaie UTF-8 strict en premier, on bascule sur windows-1252 sinon."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("windows-1252", errors="replace")


def _fetch_raw(asin: str, region: str) -> str | None:
    url = f"https://www.amazon.{region}/dp/{asin}"
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return _decode(resp.read())
    except (urllib.error.URLError, OSError):
        return None


_STRIP_PATTERNS = [
    # ">> Ce livre audio ... disponible en téléchargement."
    re.compile(r">>?\s*Ce livre audio[^.]*disponible en téléchargement\.?", re.IGNORECASE),
    # "Illustration de couverture : © 2011 HBO ..." (mention légale sur la cover)
    re.compile(r"Illustration de couverture\s*:.*", re.IGNORECASE | re.DOTALL),
]


def _extract_description(html: str) -> str | None:
    m = re.search(r'class="a-expander-content[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
    if m:
        text = re.sub(r"<[^>]+>", "", m.group(1))
        text = re.sub(r"\s+", " ", text).strip()
        for pat in _STRIP_PATTERNS:
            text = pat.sub("", text).strip()
        if len(text) > 30:
            return text
    return None


def _extract_copyright(html: str) -> str | None:
    # Structure Amazon : <... copyright" class="a-section ...">©2016 Albin Michel...</div>
    m = re.search(r'copyright"[^>]*class="[^"]*"[^>]*>([^<]{5,150})', html)
    if not m:
        # Fallback : balise <div id="..."> précédée de copyright
        m = re.search(r'copyright["\s][^>]*>([©(P)\d][^<]{4,120})', html, re.IGNORECASE)
    if m:
        val = m.group(1).strip()
        if val:
            return val
    return None


def fetch_amazon_description(asin: str, region: str = "fr") -> str | None:
    html = _fetch_raw(asin, region)
    return _extract_description(html) if html else None


def fetch_amazon_copyright(asin: str, region: str = "fr") -> str | None:
    html = _fetch_raw(asin, region)
    return _extract_copyright(html) if html else None


def fetch_amazon_meta(asin: str, region: str = "fr") -> dict:
    """Récupère description ET copyright en une seule requête HTTP.

    Retourne {'description': str|None, 'copyright': str|None}.
    """
    html = _fetch_raw(asin, region)
    if not html:
        return {"description": None, "copyright": None}
    return {
        "description": _extract_description(html),
        "copyright":   _extract_copyright(html),
    }

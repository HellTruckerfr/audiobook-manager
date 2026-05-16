import re
import http.client
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
    except (urllib.error.URLError, OSError, http.client.IncompleteRead):
        return None


_STRIP_PATTERNS = [
    # ">> Ce livre audio ... disponible en téléchargement."
    re.compile(r">>?\s*Ce livre audio[^.]*disponible en téléchargement\.?", re.IGNORECASE),
    # "Illustration de couverture : © 2011 HBO ..." (mention légale sur la cover)
    re.compile(r"Illustration de couverture\s*:.*", re.IGNORECASE | re.DOTALL),
    # "Lorsque vous achetez ce titre, le fichier PDF ..."
    re.compile(r"Lorsque vous achetez ce titre[^.]*\.", re.IGNORECASE),
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


def _extract_cover_url(html: str) -> str | None:
    m = re.search(
        r'(https://m\.media-amazon\.com/images/I/([A-Za-z0-9+%.]+)\._SL\d+_\.jpg)',
        html,
    )
    if m:
        return f"https://m.media-amazon.com/images/I/{m.group(2)}._SL500_.jpg"
    return None


def _extract_title(html: str) -> str | None:
    m = re.search(r'id="productTitle"[^>]*>\s*([^<]{3,200}?)\s*<', html)
    return m.group(1).strip() if m else None


def _extract_contributors(html: str) -> dict:
    """Extrait auteur, narrateur et editeur depuis le byline Amazon.
    Structure Audible : <span class="author"><a>Nom</a>...(Role)</span>"""
    result: dict = {"author": None, "narrator": None, "publisher": None}
    byline_m = re.search(r'id="bylineInfo"[^>]*>(.*?)(?=<div)', html, re.DOTALL)
    section = byline_m.group(1) if byline_m else html[:30000]

    for span_m in re.finditer(
        r'class="author[^"]*"[^>]*>(.*?)</span>\s*</span>', section, re.DOTALL
    ):
        span_html = span_m.group(1)
        name_m = re.search(r'<a[^>]*>([^<]{2,80})</a>', span_html)
        role_m = re.search(r'\(([^)]{2,40})\)', span_html)
        if not name_m or not role_m:
            continue
        name = name_m.group(1).strip()
        role = role_m.group(1).strip().lower()
        if "auteur" in role and not result["author"]:
            result["author"] = name
        elif "narrateur" in role and not result["narrator"]:
            result["narrator"] = name
        elif ("editeur" in role or "\xe9diteur" in role) and not result["publisher"]:
            result["publisher"] = name
    return result


def _extract_year(html: str) -> str | None:
    # JSON-LD structuré (le plus fiable sur les pages Audible)
    m = re.search(r'"datePublished"\s*:\s*"(\d{4})', html)
    if m:
        return m.group(1)
    # Bullets de details Amazon — Amazon insere des chars invisibles U+200E/F
    # autour des deux-points ; on les supprime avant le match
    _INVIS = re.compile(r"[‎‏‪‫‬‭‮]")
    clean = _INVIS.sub("", html)
    for label in ("Date d'\xe9coute", "Date de publication", "Publication date"):
        pat = rf'{re.escape(label)}\s*:?\s*</span>\s*<span[^>]*>\s*([^<]{{4,60}}?)\s*</span>'
        m = re.search(pat, clean, re.IGNORECASE)
        if m:
            yr = re.search(r'\b(19|20)\d{2}\b', m.group(1))
            if yr:
                return yr.group(0)
    # Fallback : année extraite du copyright  ex. "©2022 Audiolib"
    copy = _extract_copyright(html)
    if copy:
        yr = re.search(r'\b(19|20)\d{2}\b', copy)
        if yr:
            return yr.group(0)
    return None


def fetch_amazon_meta(asin: str, region: str = "fr") -> dict:
    """Récupère toutes les métadonnées disponibles en une seule requête HTTP."""
    html = _fetch_raw(asin, region)
    if not html:
        return {}
    contributors = _extract_contributors(html)
    return {
        "title":       _extract_title(html),
        "author":      contributors["author"],
        "narrator":    contributors["narrator"],
        "publisher":   contributors["publisher"],
        "year":        _extract_year(html),
        "description": _extract_description(html),
        "copyright":   _extract_copyright(html),
        "cover_url":   _extract_cover_url(html),
    }

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


def fetch_amazon_description(asin: str, region: str = "fr") -> str | None:
    """Récupère le résumé d'un livre depuis Amazon via son ASIN.

    Retourne le texte brut ou None si introuvable / erreur réseau.
    """
    url = f"https://www.amazon.{region}/dp/{asin}"
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError):
        return None

    # Description dans le bloc « a-expander-content » (synopsis produit)
    m = re.search(r'class="a-expander-content[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
    if m:
        text = re.sub(r"<[^>]+>", "", m.group(1))
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 30:
            return text

    return None


def fetch_amazon_copyright(asin: str, region: str = "fr") -> str | None:
    """Récupère le copyright d'un livre depuis Amazon (éditeur + année).

    Retourne une chaîne comme '© 2020 Audible Studios' ou None.
    """
    url = f"https://www.amazon.{region}/dp/{asin}"
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError):
        return None

    # Chercher la ligne « Copyright » dans les détails du produit
    m = re.search(
        r"Copyright[^<]*</[^>]+>[^<]*<[^>]+>([^<]{5,120})</",
        html, re.IGNORECASE
    )
    if m:
        val = m.group(1).strip()
        if val:
            return val

    return None


def fetch_amazon_meta(asin: str, region: str = "fr") -> dict:
    """Récupère description ET copyright en une seule requête HTTP.

    Retourne {'description': str|None, 'copyright': str|None}.
    """
    url = f"https://www.amazon.{region}/dp/{asin}"
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError):
        return {"description": None, "copyright": None}

    # Description
    description = None
    m = re.search(r'class="a-expander-content[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
    if m:
        text = re.sub(r"<[^>]+>", "", m.group(1))
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 30:
            description = text

    # Copyright
    copyright_val = None
    mc = re.search(
        r"Copyright[^<]*</[^>]+>[^<]*<[^>]+>([^<]{5,120})</",
        html, re.IGNORECASE,
    )
    if mc:
        val = mc.group(1).strip()
        if val:
            copyright_val = val

    return {"description": description, "copyright": copyright_val}

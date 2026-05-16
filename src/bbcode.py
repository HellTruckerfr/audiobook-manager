import re
from .models import BookEntry, AudioInfo


def _fr_ordinal(n: int) -> str:
    return "1er" if n == 1 else f"{n}ème"


def _codec_display(codec: str) -> str:
    c = codec.lower()
    if c in ("aac", "aac_mf", "libfdk_aac"):
        return "AAC LC"
    if c == "mp3":
        return "MP3"
    return codec.upper()


def _bitrate_display(info: AudioInfo) -> str:
    return f"{info.bitrate_kbps}kbps"


def _size_display(info: AudioInfo) -> str:
    return f"{info.size_mb / 1024:.2f} GiB"


def _title_lines(cfg, fmt_label: str = "M4B") -> list:
    """Retourne 1 ou 2 lignes de titre selon la présence d'une série."""
    author = cfg.author or "?"
    title  = cfg.title or "?"
    year_str = f" ({cfg.year})" if cfg.year else ""
    line1 = f"{author} - {title} - {fmt_label}{year_str}"
    lines = [f"[size=6][color=#eab308][b]{line1}[/b][/color][/size]"]
    if cfg.series:
        bracket = f"[{cfg.volume}]" if cfg.volume else "[Intégrale]"
        lines.append(f"[size=6][color=#eab308][b]{cfg.series} {bracket}[/b][/color][/size]")
    if cfg.parent_series:
        try:
            n = int(cfg.universe_order)
            prefix = f" {_fr_ordinal(n)} volume de l'univers"
        except (ValueError, TypeError, AttributeError):
            prefix = " Fait partie de l'univers"
        lines.append(f"[size=4][color=#eab308][i]{prefix} : {cfg.parent_series}[/i][/color][/size]")
    return lines


def generate_prez(book: BookEntry, rating: str = "", fmt: str = "m4b",
                  audio_info: "AudioInfo | None" = None) -> str:
    cfg = book.config
    fmt_label = "M4B" if fmt == "m4b" else "MP3"
    info: AudioInfo | None = audio_info if audio_info is not None else (
        book.output_m4b_info if fmt == "m4b" else book.output_mp3_info
    )

    lines = ["[center]"]

    if cfg.cover_url:
        lines.append(f"[img]{cfg.cover_url}[/img]")

    lines += _title_lines(cfg, fmt_label)
    lines.append("")

    if rating:
        lines.append(f"[b]Note :[/b] {rating}/10")

    if cfg.genre and cfg.description:
        lines.append(f"[b]Genre :[/b] {cfg.genre}[quote]{cfg.description}[/quote]")
    elif cfg.genre:
        lines.append(f"[b]Genre :[/b] {cfg.genre}")
    elif cfg.description:
        lines.append(f"[quote]{cfg.description}[/quote]")

    lines += ["[color=#eab308][b]--- DÉTAILS ---[/b][/color]", ""]
    lines.append(f"[b]Auteur :[/b] {cfg.author}")
    if cfg.narrator:
        lines.append(f"[b]Lu par :[/b] {cfg.narrator}")
    if cfg.publisher:
        lines.append(f"[b]Éditeur :[/b] {cfg.publisher}")
    lines.append(f"[b]Format :[/b] {fmt_label}")

    if info:
        if fmt == "m4b":
            lines.append(f"[b]Codec audio :[/b] {_codec_display(info.codec)}")
        lines.append(f"[b]Bitrate :[/b] {_bitrate_display(info)}")
        lines.append(f"[b]Taille :[/b] {_size_display(info)}")

    lines += ["", "[/center]"]
    return "\n".join(lines)


# ── BBCode → HTML (preview basique) ──────────────────────────────────────────

_HTML_CSS = """
body {
    background: #1e1e1e; color: #ddd;
    font-family: "Segoe UI", sans-serif; font-size: 10pt;
    padding: 24px; margin: 0;
}
blockquote {
    background: #252525; border-left: 3px solid #eab308;
    padding: 10px 16px; margin: 8px 0; color: #bbb; font-style: italic;
    border-radius: 0 4px 4px 0;
}
img { border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,.6);
      max-width: 500px; height: auto; margin-bottom: 12px; }
"""

_CONVERSIONS = [
    (re.compile(r'\[b\](.*?)\[/b\]',           re.DOTALL), r'<b>\1</b>'),
    (re.compile(r'\[i\](.*?)\[/i\]',           re.DOTALL), r'<i>\1</i>'),
    (re.compile(r'\[color=([^\]]+)\](.*?)\[/color\]', re.DOTALL),
     r'<span style="color:\1">\2</span>'),
    (re.compile(r'\[size=(\d+)\](.*?)\[/size\]', re.DOTALL),
     lambda m: f'<span style="font-size:{int(m.group(1)) * 4}px">{m.group(2)}</span>'),
    (re.compile(r'\[img\](.*?)\[/img\]',        re.DOTALL),
     r'<img src="\1">'),
    (re.compile(r'\[quote\](.*?)\[/quote\]',    re.DOTALL),
     r'<blockquote>\1</blockquote>'),
    (re.compile(r'\[center\](.*?)\[/center\]',  re.DOTALL),
     r'<div style="text-align:center">\1</div>'),
]


def bbcode_to_html(bbcode: str) -> str:
    t = bbcode
    for pattern, repl in _CONVERSIONS:
        t = pattern.sub(repl, t)
    t = t.replace('\n', '<br>\n')
    return (
        f'<!DOCTYPE html><html><head><meta charset="utf-8">'
        f'<style>{_HTML_CSS}</style></head><body>{t}</body></html>'
    )


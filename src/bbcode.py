from .models import BookEntry, AudioInfo


def _codec_display(codec: str) -> str:
    c = codec.lower()
    if c in ("aac", "aac_mf", "libfdk_aac"):
        return "AAC LC"
    if c == "mp3":
        return "MP3"
    return codec.upper()


def _bitrate_display(info: AudioInfo) -> str:
    if info.vbr:
        return f"Variable ~{info.bitrate_kbps}kbps"
    return f"Constant {info.bitrate_kbps}kbps"


def _size_display(info: AudioInfo) -> str:
    return f"{info.size_mb / 1024:.2f} GiB"


def _title_line(cfg) -> str:
    author = cfg.author or "?"
    if cfg.series:
        bracket = f"[{cfg.volume}]" if cfg.volume else "[Intégrale]"
        title_part = f"{cfg.series} {bracket}"
    else:
        title_part = cfg.title or "?"
    year_str = f" ({cfg.year})" if cfg.year else ""
    return f"{author} - {title_part} - M4B{year_str}"


def generate_prez(book: BookEntry, tracker_name: str = "La Cale",
                  rating: str = "") -> str:
    cfg = book.config
    lines = ["[center]"]

    if cfg.cover_url:
        lines += [f"[img]{cfg.cover_url}[/img]", ""]

    lines += [
        f"[size=6][color=#eab308][b]{_title_line(cfg)}[/b][/color][/size]",
        "",
    ]

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
        lines.append(f"[b]Narrateur :[/b] {cfg.narrator}")
    if cfg.publisher:
        lines.append(f"[b]Éditeur :[/b] {cfg.publisher}")
    lines.append("[b]Format :[/b] Audiobook")
    lines.append("[b]Format du conteneur :[/b] M4B")

    info: AudioInfo | None = book.output_m4b_info
    if info:
        lines.append(f"[b]Codec audio :[/b] {_codec_display(info.codec)}")
        lines.append(f"[b]Bitrate :[/b] {_bitrate_display(info)}")
        lines.append(f"[b]Taille :[/b] {_size_display(info)}")

    lines += ["", f"[i]Généré par {tracker_name}[/i][/center]"]
    return "\n".join(lines)

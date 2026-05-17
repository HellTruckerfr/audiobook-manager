"""Scene-release NFO generation (HellTrucker format)."""
import os
import re
import subprocess
import unicodedata
from typing import List, Optional, Tuple

_CODEC_LABEL = {"aac": "AAC LC", "mp3": "MP3", "opus": "Opus", "flac": "FLAC"}

from .models import BookEntry, AudioInfo


_SEP_LEN = 90

_FIGLET_LINES = [
    '██╗  ██╗███████╗██╗     ██╗  ████████╗██████╗ ██╗   ██╗ ██████╗██╗  ██╗███████╗██████╗ ',
    '██║  ██║██╔════╝██║     ██║  ╚══██╔══╝██╔══██╗██║   ██║██╔════╝██║ ██╔╝██╔════╝██╔══██╗',
    '███████║█████╗  ██║     ██║     ██║   ██████╔╝██║   ██║██║     █████╔╝ █████╗  ██████╔╝',
    '██╔══██║██╔══╝  ██║     ██║     ██║   ██╔══██╗██║   ██║██║     ██╔═██╗ ██╔══╝  ██╔══██╗',
    '██║  ██║███████╗███████╗███████╗██║   ██║  ██║╚██████╔╝╚██████╗██║  ██╗███████╗██║  ██║',
    '╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝╚═╝   ╚═╝  ╚═╝ ╚═════╝  ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝',
]

_HEADER_CACHE: Optional[Tuple[str, int]] = None


def _vol_number(volume: str) -> int:
    m = re.search(r'\d+', volume)
    return int(m.group(0)) if m else 0


def _fmt_duration(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sr = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{sr:02d}"
    return f"{m:02d}:{sr:02d}"


def _field(label: str, value: str) -> str:
    dots = max(1, 34 - len(label))
    return f"{label} {'.' * dots} : {value}"


def _get_header() -> Tuple[str, int]:
    global _HEADER_CACHE
    if _HEADER_CACHE is not None:
        return _HEADER_CACHE

    subtitle = '-= NFO par HellTrucker =-'
    inner_w = max(max(len(l) for l in _FIGLET_LINES + [subtitle]), 55)

    rows = ['╔' + '═' * (inner_w + 2) + '╗']
    rows.append('║ ' + ' ' * inner_w + ' ║')
    for ln in _FIGLET_LINES:
        rows.append('║ ' + ln.ljust(inner_w) + ' ║')
    rows.append('║ ' + ' ' * inner_w + ' ║')
    rows.append('║ ' + subtitle.center(inner_w) + ' ║')
    rows.append('║ ' + ' ' * inner_w + ' ║')
    rows.append('╚' + '═' * (inner_w + 2) + '╝')

    header_text = '\n'.join(rows)
    box_w = inner_w + 4
    _HEADER_CACHE = (header_text, box_w)
    return _HEADER_CACHE


_MI_DLL_PATHS = [
    r'C:\Program Files\MediaInfo\MediaInfo.dll',
    r'C:\Program Files (x86)\MediaInfo\MediaInfo.dll',
]
_MI_LANG_DIR = r'C:\Program Files\MediaInfo\Plugin\Language'


def _load_lang_csv(lang_code: str) -> str:
    """Charge le fichier CSV de langue MediaInfo, retourne '' si introuvable."""
    path = os.path.join(_MI_LANG_DIR, f'{lang_code}.csv')
    if not os.path.isfile(path):
        # Essai avec le code court (ex: 'fr' depuis 'FR')
        path = os.path.join(_MI_LANG_DIR, f'{lang_code.lower()}.csv')
    if os.path.isfile(path):
        try:
            with open(path, encoding='utf-8') as f:
                return f.read()
        except Exception:
            pass
    return ''


def _get_mediainfo(file_path: str, language: str = 'fr') -> Optional[str]:
    """Retourne le texte brut MediaInfo localisé, sans aucun filtrage."""
    if not file_path or not os.path.isfile(file_path):
        return None

    lang_csv = _load_lang_csv(language)

    # Appel direct via ctypes pour pouvoir passer l'option Language
    try:
        import ctypes
        lib = None
        for dll_path in _MI_DLL_PATHS:
            try:
                lib = ctypes.CDLL(dll_path)
                break
            except OSError:
                continue

        if lib is not None:
            lib.MediaInfo_New.restype = ctypes.c_void_p
            lib.MediaInfo_Option.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p]
            lib.MediaInfo_Option.restype = ctypes.c_wchar_p
            lib.MediaInfo_Open.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
            lib.MediaInfo_Open.restype = ctypes.c_size_t
            lib.MediaInfo_Inform.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
            lib.MediaInfo_Inform.restype = ctypes.c_wchar_p
            lib.MediaInfo_Close.argtypes = [ctypes.c_void_p]
            lib.MediaInfo_Close.restype = None
            lib.MediaInfo_Delete.argtypes = [ctypes.c_void_p]
            lib.MediaInfo_Delete.restype = None

            handle = lib.MediaInfo_New()
            try:
                lib.MediaInfo_Option(handle, 'CharSet', 'UTF-8')
                if lang_csv:
                    lib.MediaInfo_Option(handle, 'Language', lang_csv)
                if lib.MediaInfo_Open(handle, file_path) != 0:
                    result = lib.MediaInfo_Inform(handle, 0)
                    if result and result.strip():
                        return result.strip()
            finally:
                lib.MediaInfo_Close(handle)
                lib.MediaInfo_Delete(handle)
    except Exception:
        pass

    # Fallback sans langue via pymediainfo
    try:
        from pymediainfo import MediaInfo as _MI
        result = _MI.parse(file_path, output='')
        if isinstance(result, str) and result.strip():
            return result.strip()
    except Exception:
        pass

    # Fallback : ffprobe minimal si pymediainfo indisponible
    try:
        import json
        r = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json',
             '-show_format', '-show_streams', file_path],
            capture_output=True, text=True, timeout=30, encoding='utf-8',
        )
        if r.returncode != 0:
            return None
        data = json.loads(r.stdout)
    except Exception:
        return None

    fmt   = data.get('format', {})
    audio = next((s for s in data.get('streams', [])
                  if s.get('codec_type') == 'audio'), None)
    if not audio:
        return None

    try:
        dur_s = float(fmt.get('duration', 0))
        h, rem = divmod(int(dur_s), 3600)
        mn, sc = divmod(rem, 60)
        dur_str = f"{h} h {mn:02d} min {sc:02d} s" if h else f"{mn} min {sc:02d} s"
    except Exception:
        dur_str = "?"
    try:
        size_str = f"{os.path.getsize(file_path) / (1024*1024):.1f} MiB"
    except Exception:
        size_str = "?"
    try:
        br_str = f"{int(fmt.get('bit_rate', 0)) // 1000} kb/s"
    except Exception:
        br_str = "?"
    stream_br = audio.get('bit_rate')
    br_mode = 'Variable' if (not stream_br or str(stream_br) in ('N/A', '0', '')) else 'Constant'
    codec = audio.get('codec_long_name') or audio.get('codec_name', '?')
    try:
        sr_str = f"{int(audio.get('sample_rate', 0)) / 1000:.1f} kHz"
    except Exception:
        sr_str = "?"
    ch = audio.get('channels', '?')
    ch_layout = audio.get('channel_layout', '')

    def _row(label: str, value: str) -> str:
        return f"{label:<40}: {value}"

    return '\n'.join([
        'General',
        _row('Complete name', os.path.basename(file_path)),
        _row('Format', fmt.get('format_long_name') or fmt.get('format_name', '?')),
        _row('File size', size_str),
        _row('Duration', dur_str),
        _row('Overall bit rate', br_str),
        '',
        'Audio',
        _row('Format', codec),
        _row('Bit rate mode', br_mode),
        _row('Bit rate', br_str),
        _row('Channel(s)', f"{ch} ({ch_layout})" if ch_layout else str(ch)),
        _row('Sampling rate', sr_str),
    ])


def _clean_mediainfo(text: str, file_path: str) -> str:
    """Collapse blank lines (keep 1 only between sections) and shorten file path."""
    basename = os.path.basename(file_path)
    text = text.replace(file_path, basename)
    text = text.replace(file_path.replace('\\', '/'), basename)

    # splitlines() strips \r so CRLF doesn't produce ghost blank lines when
    # the NFO is re-joined with \n and written in text mode on Windows.
    def _sanitize(line: str) -> str:
        line = line.replace('\x00', '')
        line = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f�]', '', line)
        # Tronquer les chaînes version (ex: "LAME3.10") quand du garbage binaire suit
        if ' : ' in line:
            label, _, value = line.partition(' : ')
            m = re.match(r'^([A-Za-z][A-Za-z0-9_.]*\d)', value)
            if m and m.end() < len(value) and ord(value[m.end()]) > 0x7E:
                value = m.group(1)
            line = label + ' : ' + value
        return line.rstrip()

    lines = [_sanitize(l) for l in text.splitlines()]
    lines = [l for l in lines if l.strip()]
    result: List[str] = []
    for line in lines:
        stripped = line.strip()
        is_section = (
            stripped
            and ':' not in stripped
            and not line[0].isspace()
            and not re.match(r'^\d{2}:\d{2}:\d{2}', stripped)
        )
        if is_section and result:
            result.append('')
        result.append(line)
    return '\n'.join(result)


def _mediainfo_block(file_path: str, sep_len: int, language: str = 'fr') -> str:
    """Return a MediaInfo section to append to an NFO, or empty string."""
    mi = _get_mediainfo(file_path, language=language)
    if not mi:
        return ""
    mi = _clean_mediainfo(mi, file_path)
    sep = '-' * sep_len
    return f"\n{sep}\n{'MediaInfo'.center(sep_len)}\n{sep}\n\n{mi}\n"


def _bit_mode(info: Optional[AudioInfo]) -> str:
    if info is None or info.vbr is None:
        return 'Constant'
    return 'Variable' if info.vbr else 'Constant'


def generate_m4b_nfo(book: BookEntry, fmt: str = "M4B",
                     mp3_dir: Optional[str] = None) -> str:
    header, box_w = _get_header()
    sep_len = max(_SEP_LEN, box_w)
    sep = '-' * sep_len

    cfg = book.config
    info: Optional[AudioInfo] = book.output_m4b_info or book.selected_source

    bitrate_kbps = info.bitrate_kbps if (info and info.bitrate_kbps) else int(
        (cfg.bitrate or '128k').rstrip('k') or 128)
    sample_rate_hz = info.sample_rate_hz if (info and info.sample_rate_hz) else int(
        cfg.sample_rate or 44100)
    channels = info.channels if (info and info.channels) else 2
    # size_mb is stored in MiB (bytes / 1024²) despite the field name
    size_mib = info.size_mb if (info and info.size_mb) else 0.0

    chapters = book.chapters
    total_dur_s = (sum(ch.duration_s for ch in chapters)
                   if chapters else (info.duration_s if info else 0.0))

    channels_label = 'Stéréo' if channels >= 2 else 'Mono'
    sr_label = f'{sample_rate_hz / 1000:.2f} kHz'
    title_str = cfg.title or book.detected_title

    out: List[str] = [header, '']
    out.append(sep)
    out.append(title_str.center(sep_len))
    out.append(sep)
    out.append('')

    out.append(_field('Auteur', cfg.author or book.detected_author or 'Inconnu'))
    out.append(_field('Narrateur', cfg.narrator or cfg.author or book.detected_author or 'Inconnu'))
    out.append(_field('Titre du livre', title_str))
    if cfg.series:
        series_str = cfg.series
        m = re.search(r'\d+', cfg.volume) if cfg.volume else None
        if m:
            series_str += f' - Tome {int(m.group()):02d}'
        out.append(_field('Série', series_str))
    if cfg.year:
        out.append(_field('Année', cfg.year))
    out.append(_field('Genre', cfg.genre or 'Audiobook'))
    if cfg.asin:
        out.append(_field('ASIN', cfg.asin))
    out.append('')

    if fmt == "MP3":
        codec_label = "MP3"
    else:
        raw_codec = (info.codec or "aac").lower() if info else "aac"
        codec_label = _CODEC_LABEL.get(raw_codec, raw_codec.upper())
    out.append(_field('Codec', codec_label))
    out.append(_field('Débit moyen', f'{bitrate_kbps} kb/s'))
    out.append(_field('Mode de débit', _bit_mode(info)))
    out.append(_field('Canaux', f'{channels_label} / {sr_label}'))
    out.append(_field('Qualité', 'Lossy'))
    out.append('')
    has_cover = bool(cfg.cover_path and os.path.exists(cfg.cover_path))
    out.append(_field('Pochette', 'Oui' if has_cover else 'Non'))
    out.append('')

    # Pour MP3 : lister les fichiers pistes ; pour M4B : lister les chapitres
    mp3_files: List[str] = []
    if fmt == "MP3" and mp3_dir and os.path.isdir(mp3_dir):
        mp3_files = sorted(f for f in os.listdir(mp3_dir) if f.lower().endswith(".mp3"))

    total_size_mb: float  # will be in MB at the end
    if mp3_files:
        out.append(sep)
        out.append(f'Pistes ({len(mp3_files)})'.center(sep_len))
        out.append(sep)
        total_size_mb = 0.0
        for i, fname in enumerate(mp3_files, 1):
            fpath = os.path.join(mp3_dir, fname)  # type: ignore[arg-type]
            fsize_mib = os.path.getsize(fpath) / (1024 * 1024) if os.path.exists(fpath) else 0.0
            total_size_mb += fsize_mib * 1.048576  # MiB → MB
            ch = chapters[i - 1] if chapters and i - 1 < len(chapters) else None
            dur_str = _fmt_duration(ch.duration_s) if ch else ""
            stem = unicodedata.normalize('NFC', os.path.splitext(fname)[0])[:53]
            out.append(
                f'{i:02d}. {stem:<53} [{bitrate_kbps} kb/s]  [{fsize_mib:6.2f} MiB]  [{dur_str}]'
            )
    else:
        n_ch = len(chapters)
        out.append(sep)
        out.append(f'Chapitres ({n_ch if n_ch else 1})'.center(sep_len))
        out.append(sep)
        if chapters:
            for ch in chapters:
                est_mib = (bitrate_kbps * 1000 / 8 * ch.duration_s) / (1024 * 1024) if ch.duration_s else 0.0
                ch_title = unicodedata.normalize('NFC', ch.title or f'Chapitre {ch.index:02d}')[:53]
                out.append(
                    f'{ch.index:02d}. {ch_title:<53} [{bitrate_kbps} kb/s]  [{est_mib:6.2f} MiB]  [{_fmt_duration(ch.duration_s)}]'
                )
        else:
            out.append(
                f'00. {title_str:<52} [{bitrate_kbps} kb/s]  [{size_mib:6.2f} MiB]  [{_fmt_duration(total_dur_s)}]'
            )
        total_size_mb = size_mib * 1.048576  # MiB → MB

    out.append('')
    out.append('')
    out.append(_field('Durée totale', _fmt_duration(total_dur_s)))
    out.append(_field('Taille totale', f'{total_size_mb:.2f} MB'))
    out.append('')

    return '\n'.join(out)


def write_m4b_nfo(book: BookEntry, m4b_dest_path: str) -> str:
    """Write the NFO alongside the M4B release, with MediaInfo appended."""
    nfo_path = os.path.splitext(m4b_dest_path)[0] + '.nfo'
    _, box_w = _get_header()
    sep_len = max(_SEP_LEN, box_w)
    lang = (book.config.language or 'fr').lower()
    content = generate_m4b_nfo(book, fmt="M4B")
    content += _mediainfo_block(m4b_dest_path, sep_len, language=lang)
    with open(nfo_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return nfo_path


def write_mp3_nfo(book: BookEntry, nfo_path: str, mp3_dir: str) -> str:
    """Write the NFO for an MP3 release, with MediaInfo from the first track."""
    _, box_w = _get_header()
    sep_len = max(_SEP_LEN, box_w)
    lang = (book.config.language or 'fr').lower()
    content = generate_m4b_nfo(book, fmt="MP3", mp3_dir=mp3_dir)
    try:
        mp3_files = sorted(f for f in os.listdir(mp3_dir) if f.lower().endswith('.mp3'))
        first_mp3 = os.path.join(mp3_dir, mp3_files[0]) if mp3_files else ""
        content += _mediainfo_block(first_mp3, sep_len, language=lang)
    except Exception:
        pass
    with open(nfo_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return nfo_path


def generate_series_nfo(books: List[BookEntry], series_release_name: str) -> str:
    """NFO de série : infos audio depuis le premier tome + liste des tomes."""
    header, box_w = _get_header()
    sep_len = max(_SEP_LEN, box_w)
    sep = '-' * sep_len

    first = books[0]
    cfg = first.config
    series_name = cfg.series or ""
    author = cfg.author or first.detected_author or "Inconnu"
    info: Optional[AudioInfo] = first.output_m4b_info or first.selected_source

    album_title = (info.tag_album if (info and info.tag_album) else series_name)

    out: List[str] = [header, '']
    out.append(sep)
    out.append(album_title.center(sep_len))
    out.append(sep)
    out.append('')

    out.append(_field('Auteur', author))
    if cfg.narrator:
        out.append(_field('Narrateur', cfg.narrator))
    out.append(_field('Série', series_name))
    out.append(_field('Genre', cfg.genre or 'Audiobook'))
    out.append('')

    if info:
        bitrate_kbps = info.bitrate_kbps or int((cfg.bitrate or '128k').rstrip('k') or 128)
        sample_rate_hz = info.sample_rate_hz or int(cfg.sample_rate or 44100)
        channels = info.channels or 2
        channels_label = 'Stéréo' if channels >= 2 else 'Mono'
        sr_label = f'{sample_rate_hz / 1000:.2f} kHz'
        raw_codec = (info.codec or "aac").lower()
        codec_label = _CODEC_LABEL.get(raw_codec, raw_codec.upper())
        out.append(_field('Codec', codec_label))
        out.append(_field('Débit moyen', f'{bitrate_kbps} kb/s'))
        out.append(_field('Mode de débit', _bit_mode(info)))
        out.append(_field('Canaux', f'{channels_label} / {sr_label}'))
        out.append(_field('Qualité', 'Lossy'))
        out.append('')

    has_cover = bool(cfg.cover_path and os.path.exists(cfg.cover_path))
    out.append(_field('Pochette', 'Oui' if has_cover else 'Non'))
    out.append('')

    sorted_books = sorted(books, key=lambda b: _vol_number(b.config.volume) if b.config.volume else 0)

    out.append(sep)
    out.append(f'Tomes ({len(sorted_books)})'.center(sep_len))
    out.append(sep)

    total_dur = 0.0
    total_size_mib = 0.0

    for book in sorted_books:
        bcfg = book.config
        binfo = book.output_m4b_info or book.selected_source
        vol_num = _vol_number(bcfg.volume) if bcfg.volume else 0
        title = (bcfg.title or book.detected_title or "")[:52]
        dur_s = binfo.duration_s if binfo else 0.0
        size_mib = binfo.size_mb if binfo else 0.0  # stored as MiB
        total_dur += dur_s
        total_size_mib += size_mib
        out.append(
            f'T{vol_num:02d}. {title:<52} [{size_mib:6.2f} MiB]  [{_fmt_duration(dur_s)}]'
        )

    out.append('')
    out.append(_field('Durée totale', _fmt_duration(total_dur)))
    out.append(_field('Taille totale', f'{total_size_mib * 1.048576:.2f} MB'))
    out.append('')

    return '\n'.join(out)


def write_series_nfo(books: List[BookEntry], series_folder: str,
                     series_release_name: str) -> str:
    """Write the series-level NFO with MediaInfo from the first book's M4B."""
    nfo_path = os.path.join(series_folder, series_release_name + '.nfo')
    _, box_w = _get_header()
    sep_len = max(_SEP_LEN, box_w)
    content = generate_series_nfo(books, series_release_name)
    first_m4b = books[0].output_m4b_path if books else ""
    lang = (books[0].config.language or 'fr').lower() if books else 'fr'
    content += _mediainfo_block(first_m4b, sep_len, language=lang)
    with open(nfo_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return nfo_path

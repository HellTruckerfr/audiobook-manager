import os
import re
import sys
import subprocess
import threading
import tempfile
from typing import Callable, List, Optional

# Priorité basse pour les process ffmpeg parallèles (Windows only)
_BELOW_NORMAL = 0x00004000 if sys.platform == "win32" else 0

from .models import BookEntry, Chapter, AudioInfo
from .config_manager import ConfigManager


_CHAPTER_WORD = {
    "FR": "Chapitre", "EN": "Chapter", "ES": "Capítulo",
    "DE": "Kapitel",  "IT": "Capitolo", "PT": "Capítulo",
    "NL": "Hoofdstuk", "RU": "Глава",
}

_CHAPTER_PATTERN = re.compile(r'^chapter\s+(\d+)$', re.IGNORECASE)


def _localize_chapter(title: str, lang: str) -> str:
    m = _CHAPTER_PATTERN.match(title.strip())
    if not m:
        return title
    word = _CHAPTER_WORD.get(lang.upper(), "Chapter")
    return f"{word} {m.group(1)}"


def _duration_to_ms(seconds: float) -> int:
    return int(seconds * 1000)


def _write_ffmeta(path: str, config, chapters: List[Chapter]):
    utf8 = "utf-8"
    lines = [";FFMETADATA1\n"]

    # Convention M4B audiobook :
    #   artist       = auteur    (©ART  → "Auteurs" Windows)
    #   album_artist = narrateur (aART  → "Interprète de l'album" Windows)
    #   performer    = narrateur (©prf  → "Interprètes ayant participé" Windows)
    lines.append(f"title={config.title}\n")
    if config.series and config.volume:
        album = f"{config.series} - T{_vol_number(config.volume):02d} - {config.title}"
    elif config.series:
        album = f"{config.series} - {config.title}"
    else:
        album = config.title
    lines.append(f"album={album}\n")
    lines.append(f"artist={config.author}\n")
    narrator = config.narrator or config.author
    lines.append(f"album_artist={narrator}\n")
    if config.narrator:
        lines.append(f"performer={config.narrator}\n")
    if config.series:
        lines.append(f"grouping={config.series}\n")
    if config.volume:
        lines.append(f"track={_vol_number(config.volume)}\n")
    lines.append(f"genre={config.genre}\n")
    if config.year:
        lines.append(f"date={config.year}\n")
    if config.publisher:
        lines.append(f"publisher={config.publisher}\n")
    if config.asin:
        lines.append(f"ASIN={config.asin}\n")
    if config.encoded_by:
        lines.append(f"encoded_by={config.encoded_by}\n")
    if config.copyright:
        lines.append(f"copyright={config.copyright}\n")
    if config.description:
        lines.append(f"comment={config.description}\n")

    lang = (config.language or "FR").upper()
    cum_ms = 0
    for ch in chapters:
        dur_ms = _duration_to_ms(ch.duration_s)
        lines.append("\n[CHAPTER]\n")
        lines.append("TIMEBASE=1/1000\n")
        lines.append(f"START={cum_ms}\n")
        lines.append(f"END={cum_ms + dur_ms}\n")
        lines.append(f"title={_localize_chapter(ch.title, lang)}\n")
        cum_ms += dur_ms

    with open(path, "w", encoding=utf8, newline="\n") as f:
        f.writelines(lines)


def _write_ffmeta_tags(path: str, config) -> None:
    """Tags globaux uniquement (pas de chapitres) — pour update_metadata."""
    lines = [";FFMETADATA1\n"]
    lines.append(f"title={config.title}\n")
    if config.series and config.volume:
        album = f"{config.series} - T{_vol_number(config.volume):02d} - {config.title}"
    elif config.series:
        album = f"{config.series} - {config.title}"
    else:
        album = config.title
    lines.append(f"album={album}\n")
    lines.append(f"artist={config.author}\n")
    narrator = config.narrator or config.author
    lines.append(f"album_artist={narrator}\n")
    if config.narrator:
        lines.append(f"performer={config.narrator}\n")
    if config.series:
        lines.append(f"grouping={config.series}\n")
    if config.volume:
        lines.append(f"track={_vol_number(config.volume)}\n")
    lines.append(f"genre={config.genre}\n")
    if config.year:
        lines.append(f"date={config.year}\n")
    if config.publisher:
        lines.append(f"publisher={config.publisher}\n")
    if config.asin:
        lines.append(f"ASIN={config.asin}\n")
    if config.encoded_by:
        lines.append(f"encoded_by={config.encoded_by}\n")
    if config.copyright:
        lines.append(f"copyright={config.copyright}\n")
    if config.description:
        lines.append(f"comment={config.description}\n")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(lines)


def _write_concat(path: str, files: List[str]):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("ffconcat version 1.0\n")
        for fp in files:
            # Slashes forward + échappement des apostrophes pour le format ffconcat
            fwd = fp.replace("\\", "/").replace("'", "\\'")
            f.write(f"file '{fwd}'\n")


def _make_watermark_filter(logo_path: str, font_path: str) -> str:
    font_path_fwd = font_path.replace("\\", "/").replace(":", "\\:")
    return (
        # Logo : redimensionné, canal alpha du PNG préservé tel quel
        "[1:v]scale=160:-1,format=rgba[logo];"
        "[0:v]format=rgba[bg];"
        "[bg][logo]overlay=x=W-w-10:y=H-h-30[wm];"
        "[wm]drawtext="
        f"fontfile='{font_path_fwd}':"
        "text='by HellTrucker':"
        "fontsize=12:fontcolor=white@0.75:"
        "borderw=1:bordercolor=black@0.75:"
        "x=W-tw-10:y=H-18[out]"
    )


def _extract_cover(source_path: str, out_path: str) -> bool:
    try:
        r = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-i", source_path,
             "-an", "-vframes", "1", "-y", out_path],
            capture_output=True, timeout=30
        )
        return r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 100
    except Exception:
        return False


def _apply_watermark(cover_path: str, logo_path: str, font_path: str, out_path: str) -> bool:
    filt = _make_watermark_filter(logo_path, font_path)
    try:
        r = subprocess.run(
            ["ffmpeg", "-loglevel", "error",
             "-i", cover_path, "-i", logo_path,
             "-filter_complex", filt,
             "-map", "[out]", "-frames:v", "1", "-q:v", "2", "-y", out_path],
            capture_output=True, timeout=30
        )
        return r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 100
    except Exception:
        return False


_aac_encoder_cache: Optional[str] = None


def _best_aac_encoder() -> str:
    """Retourne le meilleur encodeur AAC disponible (libfdk_aac > aac_mf > aac)."""
    global _aac_encoder_cache
    if _aac_encoder_cache is not None:
        return _aac_encoder_cache
    try:
        r = subprocess.run(
            ["ffmpeg", "-encoders"], capture_output=True, text=True, timeout=10
        )
        out = r.stdout
        if "libfdk_aac" in out:
            _aac_encoder_cache = "libfdk_aac"
        elif "aac_mf" in out:
            _aac_encoder_cache = "aac_mf"
        else:
            _aac_encoder_cache = "aac"
    except Exception:
        _aac_encoder_cache = "aac"
    return _aac_encoder_cache


_PROGRESS_PREFIXES = frozenset([
    "frame=", "fps=", "stream_", "bitrate=", "total_size=",
    "out_time_us=", "out_time_ms=", "dup_frames=", "drop_frames=",
    "speed=", "progress=",
])


def _parse_progress(line: str, total_duration_s: float) -> Optional[float]:
    """Parse une ligne ffmpeg (-progress pipe:2) et retourne 0-1."""
    # Format -progress pipe:2 : out_time=HH:MM:SS.ffffff
    m = re.match(r"out_time=(\d+):(\d+):(\d+\.\d+)", line.strip())
    if m and total_duration_s > 0:
        h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        return min((h * 3600 + mn * 60 + s) / total_duration_s, 1.0)
    return None


class Converter:
    def __init__(self, config_manager: ConfigManager):
        self.cfg = config_manager
        self._cancel_flag = threading.Event()

    def cancel(self):
        self._cancel_flag.set()

    def reset_cancel(self):
        self._cancel_flag.clear()

    def convert(
        self,
        book: BookEntry,
        output_path: str,
        progress_cb: Callable[[float, str], None],
        done_cb: Callable[[bool, str], None],
        log_cb: Optional[Callable[[str, str], None]] = None,
    ):
        """Run M4B conversion in a background thread."""
        self.reset_cancel()
        threading.Thread(
            target=self._run,
            args=(book, output_path, progress_cb, done_cb, log_cb),
            daemon=True,
        ).start()

    def update_metadata(self, book, progress_cb, done_cb, log_cb=None):
        """Réécrit les tags d'un M4B existant sans ré-encodage audio."""
        threading.Thread(
            target=self._run_update_metadata,
            args=(book, progress_cb, done_cb, log_cb),
            daemon=True,
        ).start()

    def _run_update_metadata(self, book, progress_cb, done_cb, log_cb=None):
        import tempfile, shutil

        def log(msg, level="info"):
            if log_cb:
                log_cb(msg, level)

        m4b_path = book.output_m4b_path
        if not m4b_path or not os.path.isfile(m4b_path):
            done_cb(False, "Fichier M4B introuvable")
            return

        log(f"🏷  Tags : {book.display_title}", "start")
        progress_cb(0.1, "Écriture des tags…")

        with tempfile.TemporaryDirectory() as tmp:
            meta_path = os.path.join(tmp, "meta.txt")
            tmp_out   = os.path.join(tmp, "output.m4b")

            _write_ffmeta_tags(meta_path, book.config)

            # Chapitres et audio conservés depuis le M4B original ; tags remplacés
            args = [
                "ffmpeg", "-loglevel", "error",
                "-i", self._p(m4b_path),
                "-i", self._p(meta_path),
                "-map_metadata", "1",
                "-map_chapters", "0",
                "-c", "copy",
                "-y", self._p(tmp_out),
            ]

            progress_cb(0.5, "Application des tags…")
            try:
                r = subprocess.run(
                    args, capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    timeout=300, creationflags=_BELOW_NORMAL,
                )
            except subprocess.TimeoutExpired:
                log("✗  Timeout", "error")
                done_cb(False, "Timeout")
                return

            if r.returncode != 0 or not os.path.isfile(tmp_out) or os.path.getsize(tmp_out) < 1024:
                err = " | ".join(l for l in (r.stderr or "").splitlines() if l.strip())[:200]
                log(f"✗  {err or 'Erreur ffmpeg'}", "error")
                done_cb(False, err or "Erreur ffmpeg")
                return

            progress_cb(0.9, "Remplacement du fichier…")
            try:
                shutil.move(tmp_out, m4b_path)
            except Exception as e:
                log(f"✗  Remplacement impossible : {e}", "error")
                done_cb(False, str(e))
                return

        log("✓  Tags mis à jour", "ok")
        progress_cb(1.0, "Terminé")
        done_cb(True, m4b_path)

    def convert_to_mp3(
        self,
        book: BookEntry,
        output_dir: str,
        progress_cb: Callable[[float, str], None],
        done_cb: Callable[[bool, str], None],
        log_cb: Optional[Callable[[str, str], None]] = None,
    ):
        """Split M4B → dossier de MP3 (un fichier par chapitre), en background."""
        self.reset_cancel()
        threading.Thread(
            target=self._run_mp3,
            args=(book, output_dir, progress_cb, done_cb, log_cb),
            daemon=True,
        ).start()

    def _run_mp3(self, book, output_dir, progress_cb, done_cb, log_cb):
        import concurrent.futures
        import tempfile

        def log(msg, level="info"):
            if log_cb:
                log_cb(msg, level)

        m4b_path = book.output_m4b_path
        if not m4b_path or not os.path.isfile(m4b_path):
            done_cb(False, "Fichier M4B de sortie introuvable — convertir en M4B d'abord")
            return

        chapters = _get_m4b_chapters(m4b_path)
        if not chapters:
            # Pas de chapitres embarqués → exporter le fichier entier comme un seul MP3
            title = book.config.title or book.detected_title or "Track"
            chapters = [{"index": 1, "title": title, "start": 0.0, "end": None}]

        n   = len(chapters)
        pad = len(str(n))
        cfg = book.config
        bitrate = cfg.bitrate or "128k"

        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            done_cb(False, f"Impossible de créer le dossier : {e}")
            return

        log(f"▶  MP3 : {book.display_title}", "start")
        log(f"   Source    : {m4b_path}", "detail")
        log(f"   Sortie    : {output_dir}", "detail")
        log(f"   Chapitres : {n}  ·  Bitrate : {bitrate}", "detail")

        progress_cb(0.0, "Démarrage…")

        lock      = threading.Lock()
        completed = [0]
        err_msgs: list = []

        book_title  = cfg.title or book.detected_title
        book_author = cfg.author or book.detected_author
        narrator    = cfg.narrator or book_author

        total_dur_mp3 = sum(
            (ch["end"] - ch["start"]) if ch.get("end") else 0
            for ch in chapters
        ) or 3600
        _per_ch_timeout = max(300, int(total_dur_mp3 / max(n, 1) * 2) + 60)

        # Cover : depuis l'éditeur en priorité, watermark si activé, sinon extrait du M4B
        _fd, _cover_raw = tempfile.mkstemp(suffix=".jpg")
        os.close(_fd)
        _fd, _cover_wm = tempfile.mkstemp(suffix=".jpg")
        os.close(_fd)
        cover_path: str | None = None

        _raw = cfg.cover_path if (cfg.cover_path and os.path.isfile(cfg.cover_path)) else None
        if not _raw and _extract_cover(m4b_path, _cover_raw):
            _raw = _cover_raw
        if _raw:
            if cfg.watermark and self.cfg.app_config.logo_path:
                if _apply_watermark(_raw, self.cfg.app_config.logo_path,
                                    self.cfg.app_config.font_path, _cover_wm):
                    cover_path = _cover_wm
                else:
                    cover_path = _raw
            else:
                cover_path = _raw

        def encode_chapter(i: int, ch: dict):
            if self._cancel_flag.is_set():
                return False
            safe = _clean_filename(ch["title"]) or f"Chapitre {ch['index']}"
            out_file = os.path.join(output_dir, f"{i + 1:0{pad}d} - {safe}.mp3")

            args = ["ffmpeg", "-threads", "1", "-loglevel", "error",
                    "-ss", str(ch["start"]),
                    "-i", self._p(m4b_path)]
            if cover_path:
                args += ["-i", self._p(cover_path)]
            if ch["end"] is not None:
                args += ["-t", str(ch["end"] - ch["start"])]
            args += ["-map", "0:a"]
            if cover_path:
                args += ["-map", "1:v", "-c:v", "copy"]
            else:
                args += ["-vn"]
            args += [
                "-c:a", "libmp3lame", "-threads", "1", "-b:a", bitrate, "-write_xing", "0",
                "-id3v2_version", "3",
                "-metadata", f"title={ch['title']}",
                "-metadata", f"album={book_title}",
                "-metadata", f"artist={book_author}",
                "-metadata", f"album_artist={narrator}",
                "-metadata", f"track={i + 1}/{n}",
                "-metadata", f"genre={cfg.genre or 'Audiobook'}",
            ]
            if cfg.year:
                args += ["-metadata", f"date={cfg.year}"]
            if cfg.publisher:
                args += ["-metadata", f"publisher={cfg.publisher}"]
            args += ["-y", self._p(out_file)]

            timed_out = False
            r = None
            try:
                r = subprocess.run(args, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace",
                                   timeout=_per_ch_timeout,
                                   creationflags=_BELOW_NORMAL)
            except subprocess.TimeoutExpired:
                timed_out = True
            success = (not timed_out and r is not None
                       and r.returncode == 0
                       and os.path.isfile(out_file)
                       and os.path.getsize(out_file) > 512)

            with lock:
                if success:
                    completed[0] += 1
                    progress_cb(-1.0, f"{completed[0]}/{n} encodés")
                else:
                    if timed_out:
                        msg = f"timeout ({_per_ch_timeout}s)"
                    else:
                        lines = [l for l in (r.stderr or "").splitlines() if l.strip()]
                        msg = " | ".join(lines[:2]) if lines else f"exit {r.returncode}"
                    err_msgs.append(f"[ch{i + 1}] {msg}")
                    if log_cb:
                        log_cb(f"   ffmpeg: [ch {i + 1}] {msg}", "error")
            return success

        workers = min(max((os.cpu_count() or 4) // 2, 4), n)
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            fut_map = {ex.submit(encode_chapter, i, ch): i
                       for i, ch in enumerate(chapters)}
            for fut in concurrent.futures.as_completed(fut_map):
                results.append(fut.result())
                if self._cancel_flag.is_set():
                    break

        for _tmp in (_cover_raw, _cover_wm):
            try:
                os.unlink(_tmp)
            except OSError:
                pass

        if self._cancel_flag.is_set():
            log("   Annulé par l'utilisateur", "info")
            done_cb(False, "Annulé")
            return

        if any(not r for r in results):
            err = "; ".join(err_msgs[:3]) if err_msgs else "Encodage MP3 échoué"
            log(f"✗  {err}", "error")
            done_cb(False, err)
            return

        total_mb = sum(
            os.path.getsize(os.path.join(output_dir, f))
            for f in os.listdir(output_dir)
            if f.endswith(".mp3")
        ) / 1024 / 1024
        log(f"✓  {n} fichier{'s' if n != 1 else ''} MP3 — {total_mb:.1f} MB", "ok")
        done_cb(True, output_dir)

    def _run(self, book, output_path, progress_cb, done_cb, log_cb):
        def log(msg, level="info"):
            if log_cb:
                log_cb(msg, level)

        tmp = tempfile.mkdtemp(prefix="abm_")
        try:
            src = book.selected_source
            if not src:
                done_cb(False, "Aucune source sélectionnée")
                return

            config = book.config
            chapters = book.chapters
            total_duration = sum(ch.duration_s for ch in chapters)

            log(f"▶  {book.display_title}", "start")
            log(f"   Auteur  : {book.display_author}", "detail")
            log(f"   Source  : {src.path}", "detail")
            log(f"   Sortie  : {output_path}", "detail")
            log(f"   Durée   : {_fmt_dur(total_duration)}  "
                f"({len(chapters)} chapitre{'s' if len(chapters) != 1 else ''})", "detail")

            # Cover
            cover_path = config.cover_path or None
            raw_cover = os.path.join(tmp, "cover_raw.jpg")
            wm_cover = os.path.join(tmp, "cover_wm.jpg")

            if not cover_path:
                sample = src.path if os.path.isfile(src.path) else _first_audio(src.path)
                if sample and _extract_cover(sample, raw_cover):
                    cover_path = raw_cover

            if cover_path and config.watermark and self.cfg.app_config.logo_path:
                if _apply_watermark(
                    cover_path,
                    self.cfg.app_config.logo_path,
                    self.cfg.app_config.font_path,
                    wm_cover,
                ):
                    cover_path = wm_cover

            progress_cb(0.05, "Métadonnées...")

            meta_path = os.path.join(tmp, "meta.txt")
            _write_ffmeta(meta_path, config, chapters)

            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            if os.path.isfile(src.path) and src.path.lower().endswith(".m4b"):
                # Copie directe uniquement si la source est déjà à la qualité cible
                target_br = int(re.sub(r'[^0-9]', '', config.bitrate or '128') or 128)
                target_sr = int(config.sample_rate or 44100)
                quality_ok = (
                    src.bitrate_kbps > 0
                    and abs(src.bitrate_kbps - target_br) <= 10
                    and (src.sample_rate_hz == 0 or src.sample_rate_hz == target_sr)
                )
                if quality_ok:
                    log("   Mode    : copie M4B directe", "detail")
                    ok = self._copy_m4b(
                        src.path, meta_path, cover_path, output_path,
                        total_duration, progress_cb,
                        lang=_iso_lang(config.language), log_cb=log_cb
                    )
                else:
                    log(f"   Mode    : ré-encodage M4B ({src.bitrate_kbps}k → {config.bitrate})", "detail")
                    ok = self._reencode_m4b(
                        src.path, meta_path, cover_path, output_path,
                        config, total_duration, tmp, progress_cb,
                        lang=_iso_lang(config.language), log_cb=log_cb
                    )
            else:
                ok = self._encode_mp3s(
                    src, chapters, meta_path, cover_path, output_path,
                    config, total_duration, tmp, progress_cb, log_cb
                )

            if self._cancel_flag.is_set():
                log("   Annulé par l'utilisateur", "info")
                done_cb(False, "Annulé")
            elif ok:
                size_mb = os.path.getsize(output_path) / 1024 / 1024 if os.path.exists(output_path) else 0
                log(f"✓  Terminé — {size_mb:.1f} MB", "ok")
                done_cb(True, output_path)
            else:
                err = getattr(self, "_last_ffmpeg_error", "") or "Erreur ffmpeg"
                log(f"✗  Erreur ffmpeg : {err}", "error")
                done_cb(False, err)

        except Exception as e:
            log(f"✗  Exception : {e}", "error")
            done_cb(False, str(e))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    @staticmethod
    def _p(path: str) -> str:
        """Normalise un chemin pour ffmpeg (forward slashes)."""
        return path.replace("\\", "/")

    def _copy_m4b(self, src, meta, cover, out, total_dur, progress_cb, lang="fra", log_cb=None):
        p = self._p
        args = [
            "ffmpeg", "-loglevel", "error", "-progress", "pipe:2",
            "-i", p(src),
            "-i", p(meta),
        ]
        if cover and os.path.exists(cover):
            args += ["-i", p(cover)]

        args += ["-map", "0:a", "-map_metadata", "1", "-map_chapters", "1",
                 "-metadata:s:a:0", f"language={lang}", "-sn"]

        if cover and os.path.exists(cover):
            args += ["-map", "2:0", "-c:v", "copy", "-disposition:v:0", "attached_pic"]

        args += ["-c:a", "copy", "-y", p(out)]
        return self._run_ffmpeg(args, total_dur, progress_cb, log_cb)

    def _reencode_m4b(self, src, meta, cover, out, config, total_dur, tmp,
                      progress_cb, lang="fra", log_cb=None):
        """Ré-encode un M4B en parallèle par chapitre, puis concat + métadonnées."""
        import concurrent.futures

        p = self._p
        preferred_enc = _best_aac_encoder()
        chapters = _get_m4b_chapters(src)

        if not chapters:
            # Pas de chapitres → passe unique
            args = ["ffmpeg", "-loglevel", "error", "-progress", "pipe:2",
                    "-i", p(src), "-i", p(meta)]
            if cover and os.path.exists(cover):
                args += ["-i", p(cover)]
            args += ["-map", "0:a", "-map_metadata", "1", "-map_chapters", "1",
                     "-metadata:s:a:0", f"language={lang}", "-sn"]
            if cover and os.path.exists(cover):
                args += ["-map", "2:0", "-c:v", "copy", "-disposition:v:0", "attached_pic"]
            args += ["-c:a", preferred_enc, "-b:a", config.bitrate,
                     "-ac", "2", "-ar", config.sample_rate, "-y", p(out)]
            return self._run_ffmpeg(args, total_dur, progress_cb, log_cb)

        n = len(chapters)
        cpu = os.cpu_count() or 4
        workers = min(max(cpu // 2, 4), n)
        if log_cb:
            log_cb(f"   Workers : {workers} processus parallèles ({n} chapitres)", "detail")

        lock = threading.Lock()
        completed = [0]
        err_msgs: list = []
        _per_ch_timeout = max(300, int(total_dur / max(n, 1) * 2) + 60)

        def encode_chapter(i: int, ch: dict):
            if self._cancel_flag.is_set():
                return None
            part = os.path.join(tmp, f"part_{i:04d}.mp4")
            duration = (ch["end"] - ch["start"]) if ch["end"] is not None else None
            args = ["ffmpeg", "-threads", "1", "-loglevel", "warning",
                    "-ss", str(ch["start"]), "-i", p(src)]
            if duration is not None:
                args += ["-t", str(duration)]
            args += ["-map", "0:a:0",
                     "-c:a", preferred_enc, "-b:a", config.bitrate,
                     "-ac", "2", "-ar", config.sample_rate,
                     "-threads", "1", "-y", p(part)]
            timed_out = False
            r = None
            try:
                r = subprocess.run(args, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace",
                                   timeout=_per_ch_timeout,
                                   creationflags=_BELOW_NORMAL)
            except subprocess.TimeoutExpired:
                timed_out = True
            ok = (not timed_out and r is not None
                  and r.returncode == 0 and os.path.isfile(part) and os.path.getsize(part) > 512)
            with lock:
                if ok:
                    completed[0] += 1
                    progress_cb(-1.0, f"{completed[0]}/{n} encodés")
                else:
                    if timed_out:
                        msg = f"timeout ({_per_ch_timeout}s)"
                    else:
                        lines = [l for l in (r.stderr or "").splitlines() if l.strip()]
                        msg = " | ".join(lines[:2]) if lines else f"exit {r.returncode}"
                    err_msgs.append(f"[ch{i + 1}] {msg}")
                    if log_cb:
                        log_cb(f"   ffmpeg: [ch {i + 1}] {msg}", "error")
            return part if ok else None

        results = [None] * n
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            fut_map = {ex.submit(encode_chapter, i, ch): i
                       for i, ch in enumerate(chapters)}
            for fut in concurrent.futures.as_completed(fut_map):
                results[fut_map[fut]] = fut.result()
                if self._cancel_flag.is_set():
                    break

        if self._cancel_flag.is_set():
            return False
        if any(r is None for r in results):
            self._last_ffmpeg_error = "; ".join(err_msgs[:3]) if err_msgs else "Ré-encodage M4B échoué"
            return False

        # Concat + métadonnées (stream copy depuis les intermédiaires déjà encodés)
        concat_list = os.path.join(tmp, "concat_reencode.txt")
        _write_concat(concat_list, results)

        args = ["ffmpeg", "-loglevel", "error", "-progress", "pipe:2",
                "-f", "concat", "-safe", "0", "-i", p(concat_list),
                "-i", p(meta)]
        cover_idx = -1
        if cover and os.path.exists(cover):
            args += ["-i", p(cover)]
            cover_idx = 2
        args += ["-map", "0:a", "-map_metadata", "1", "-map_chapters", "1",
                 "-metadata:s:a:0", f"language={lang}",
                 "-sn", "-c:a", "copy"]
        if cover_idx >= 0:
            args += ["-map", f"{cover_idx}:0", "-c:v", "copy",
                     "-disposition:v:0", "attached_pic"]
        args += ["-y", p(out)]

        def concat_progress(raw: float, label: str):
            progress_cb(0.88 + raw * 0.12, label)

        return self._run_ffmpeg(args, total_dur, concat_progress, log_cb)

    def _encode_mp3s(self, src, chapters, meta, cover, out, config, total_dur, tmp, progress_cb, log_cb=None):
        p          = self._p
        folder     = src.path
        audio_exts = {".mp3", ".m4b", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
        aac_exts   = {".m4b", ".m4a", ".aac"}

        files = sorted([
            os.path.join(folder, f) for f in os.listdir(folder)
            if os.path.splitext(f)[1].lower() in audio_exts
        ])
        if not files:
            return False

        n         = len(files)
        target_br = int(re.sub(r'[^0-9]', '', config.bitrate or '128') or 128)
        target_sr = int(config.sample_rate or 44100)
        copy_aac  = (
            src.bitrate_kbps > 0
            and abs(src.bitrate_kbps - target_br) <= 10
            and (src.sample_rate_hz == 0 or src.sample_rate_hz == target_sr)
        )
        can_copy = (
            n == 1
            and os.path.splitext(files[0])[1].lower() in aac_exts
            and copy_aac
        )

        if n > 1:
            if log_cb:
                log_cb(f"   Mode    : encodage parallèle {_best_aac_encoder()} @ {config.bitrate} ({n} fichiers)", "detail")
            return self._encode_parallel(
                files, meta, cover, out, config, total_dur, tmp, progress_cb, log_cb, copy_aac
            )

        # Fichier unique
        args = ["ffmpeg", "-loglevel", "error", "-progress", "pipe:2",
                "-i", p(files[0]), "-i", p(meta)]
        cover_idx = -1
        if cover and os.path.exists(cover):
            args += ["-i", p(cover)]
            cover_idx = 2
        args += ["-map", "0:a", "-map_metadata", "1", "-map_chapters", "1",
                 "-metadata:s:a:0", f"language={_iso_lang(config.language)}", "-sn"]
        if cover_idx >= 0:
            args += ["-map", f"{cover_idx}:0", "-c:v", "copy",
                     "-disposition:v:0", "attached_pic"]
        args += ["-c:a", "copy"] if can_copy else [
            "-c:a", _best_aac_encoder(), "-b:a", config.bitrate,
            "-ac", "2", "-ar", config.sample_rate,
        ]
        if log_cb:
            _enc = "copie directe" if can_copy else f"encodage {_best_aac_encoder()} @ {config.bitrate}"
            log_cb(f"   Mode    : {_enc} (1 fichier)", "detail")
        args += ["-y", p(out)]
        return self._run_ffmpeg(args, total_dur, progress_cb, log_cb)

    def _encode_parallel(self, files, meta, cover, out, config, total_dur, tmp, progress_cb, log_cb=None, copy_aac=True):
        import concurrent.futures
        n    = len(files)
        p    = self._p
        lock = threading.Lock()
        completed  = [0]
        err_msgs: list = []
        aac_exts = {".m4b", ".m4a", ".aac"}

        cpu = os.cpu_count() or 4
        workers = min(max(cpu // 2, 4), n)
        if log_cb:
            log_cb(f"   Workers : {workers} processus parallèles", "detail")

        preferred_enc = _best_aac_encoder()
        # Timeout par fichier : 2× la durée max d'un chapitre à 1× vitesse, au moins 5 min
        _per_file_timeout = max(300, int(total_dur / max(n, 1) * 2) + 60)

        def encode_one(i: int, src_file: str):
            if self._cancel_flag.is_set():
                return None
            # .mp4 intermédiaire : muxer plus permissif que ipod (.m4a)
            part = os.path.join(tmp, f"part_{i:04d}.mp4")
            ext  = os.path.splitext(src_file)[1].lower()

            if ext in aac_exts and copy_aac:
                candidates = [["-map", "0:a:0", "-c:a", "copy"]]
            else:
                base_enc = ["-map", "0:a:0",
                            "-c:a", preferred_enc, "-b:a", config.bitrate,
                            "-ac", "2", "-ar", config.sample_rate]
                candidates = [base_enc]
                if preferred_enc != "aac":
                    candidates.append(["-map", "0:a:0",
                                       "-c:a", "aac", "-b:a", config.bitrate,
                                       "-ac", "2", "-ar", config.sample_rate])

            r = None
            timed_out = False
            for idx_c, enc_args in enumerate(candidates):
                try:
                    r = subprocess.run(
                        ["ffmpeg", "-threads", "1", "-loglevel", "warning",
                         "-i", p(src_file)] + enc_args + ["-threads", "1", "-y", p(part)],
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                        timeout=_per_file_timeout, creationflags=_BELOW_NORMAL,
                    )
                except subprocess.TimeoutExpired:
                    timed_out = True
                    r = None
                    break
                ok = r.returncode == 0 and os.path.isfile(part) and os.path.getsize(part) > 512
                if ok:
                    if idx_c > 0 and log_cb:
                        log_cb(f"   fallback aac sur partie {i}", "detail")
                    break

            with lock:
                success = (not timed_out and r is not None and r.returncode == 0
                           and os.path.isfile(part) and os.path.getsize(part) > 512)
                if success:
                    completed[0] += 1
                    # -1.0 = phase parallèle, barre indéterminée dans l'UI
                    progress_cb(-1.0, f"{completed[0]}/{n} encodés")
                else:
                    fname = os.path.basename(src_file)
                    if timed_out:
                        msg = f"timeout ({_per_file_timeout}s) — {fname}"
                    else:
                        lines = (r.stderr if r else "").strip().splitlines()
                        meaningful = [l for l in lines if l.strip() and "Nothing was written" not in l]
                        detail = " | ".join(meaningful[:2]) if meaningful else \
                                 (lines[-1] if lines else f"exit {r.returncode if r else '?'}")
                        msg = f"{fname} — {detail}"
                    err_msgs.append(f"[{i}] {msg}")
                    if log_cb:
                        log_cb(f"   ffmpeg: [partie {i}] {msg}", "error")
            return part if success else None

        results = [None] * n
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            fut_map = {ex.submit(encode_one, i, f): i for i, f in enumerate(files)}
            for fut in concurrent.futures.as_completed(fut_map):
                results[fut_map[fut]] = fut.result()
                if self._cancel_flag.is_set():
                    break

        if self._cancel_flag.is_set():
            return False
        if any(r is None for r in results):
            self._last_ffmpeg_error = "; ".join(err_msgs[:3]) if err_msgs else "Encodage parallèle échoué"
            return False

        # Phase concat : stream copy + metadata (88 % → 100 %)
        concat_list = os.path.join(tmp, "concat.txt")
        _write_concat(concat_list, results)

        args = ["ffmpeg", "-loglevel", "error", "-progress", "pipe:2",
                "-f", "concat", "-safe", "0", "-i", p(concat_list),
                "-i", p(meta)]
        cover_idx = -1
        if cover and os.path.exists(cover):
            args += ["-i", p(cover)]
            cover_idx = 2
        args += ["-map", "0:a", "-map_metadata", "1", "-map_chapters", "1",
                 "-metadata:s:a:0", f"language={_iso_lang(config.language)}",
                 "-sn", "-c:a", "copy"]
        if cover_idx >= 0:
            args += ["-map", f"{cover_idx}:0", "-c:v", "copy",
                     "-disposition:v:0", "attached_pic"]
        args += ["-y", p(out)]

        def concat_progress(raw: float, label: str):
            progress_cb(0.88 + raw * 0.12, label)

        return self._run_ffmpeg(args, total_dur, concat_progress, log_cb, pct_start=0.0, pct_end=1.0)

    def _run_ffmpeg(self, args, total_dur, progress_cb, log_cb=None,
                    pct_start: float = 0.05, pct_end: float = 1.0) -> bool:
        self._last_ffmpeg_error = ""
        error_lines: list = []
        span = pct_end - pct_start
        try:
            proc = subprocess.Popen(
                args,
                stderr=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            for line in proc.stderr:
                if self._cancel_flag.is_set():
                    proc.terminate()
                    return False
                stripped = line.strip()
                prog = _parse_progress(stripped, total_dur)
                if prog is not None:
                    progress_cb(pct_start + prog * span, f"{int(prog * 100)}%")
                elif any(stripped.startswith(pfx) for pfx in _PROGRESS_PREFIXES):
                    pass
                elif stripped:
                    error_lines.append(stripped)
                    if log_cb:
                        log_cb(f"   ffmpeg: {stripped}", "ffmpeg")
            proc.wait()
            if proc.returncode != 0:
                self._last_ffmpeg_error = " | ".join(error_lines[-3:]) if error_lines else f"exit {proc.returncode}"
            return proc.returncode == 0
        except Exception as e:
            self._last_ffmpeg_error = str(e)
            return False


_LANG_ISO = {
    "FR": "fra", "EN": "eng", "ES": "spa", "DE": "deu",
    "IT": "ita", "PT": "por", "NL": "nld", "JA": "jpn", "RU": "rus",
}


def _iso_lang(code: str) -> str:
    return _LANG_ISO.get((code or "FR").upper(), "fra")


def _first_audio(folder: str) -> Optional[str]:
    exts = {".mp3", ".m4b", ".m4a", ".aac", ".flac"}
    for fn in sorted(os.listdir(folder)):
        if os.path.splitext(fn)[1].lower() in exts:
            return os.path.join(folder, fn)
    return None


def _fmt_dur(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def _clean_filename(s: str) -> str:
    """Supprime les caractères interdits dans les noms de fichiers Windows."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s).strip(" .")


def _get_m4b_chapters(m4b_path: str) -> list:
    """Retourne [{index, title, start, end}] depuis les chapitres embarqués du M4B."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_chapters", m4b_path],
            capture_output=True, text=True, timeout=30, encoding="utf-8"
        )
        if r.returncode != 0:
            return []
        import json
        data = json.loads(r.stdout)
        chapters = []
        for ch in data.get("chapters", []):
            tags = {k.lower(): v for k, v in (ch.get("tags") or {}).items()}
            title = tags.get("title", f"Chapitre {len(chapters) + 1}")
            try:
                start = float(ch.get("start_time", 0))
                end   = float(ch.get("end_time", 0)) or None
            except (ValueError, TypeError):
                start, end = 0.0, None
            chapters.append({
                "index": len(chapters) + 1,
                "title": title,
                "start": start,
                "end":   end,
            })
        return chapters
    except Exception:
        return []


def build_mp3_output_dir(book: "BookEntry", output_mp3: str) -> str:
    """Retourne le dossier de sortie MP3 :
    output_mp3 / Auteur / [Série /] <stem du fichier .m4b source> /
    """
    cfg    = book.config
    author = _clean_filename((cfg.author or book.detected_author).split(",")[0].strip())
    series = _clean_filename(cfg.series or book.detected_series or "")

    # Nom du dossier = stem du fichier .m4b de sortie
    m4b_path = book.output_m4b_path
    if m4b_path:
        folder_name = _clean_filename(os.path.splitext(os.path.basename(m4b_path))[0])
    else:
        folder_name = _clean_filename(cfg.title or book.detected_title)

    parts = [output_mp3, author]
    if series:
        parts.append(series)
    parts.append(folder_name)
    return os.path.join(*parts)


def _vol_number(volume: str) -> int:
    """Extrait le premier entier du champ volume (ex: 'Volume 6' → 6, '6' → 6)."""
    m = re.search(r'\d+', volume)
    return int(m.group(0)) if m else 0


def _dot(s: str) -> str:
    """Remplace les espaces par des points et écrase les points multiples."""
    return re.sub(r'\.{2,}', '.', s.replace(" ", ".")).strip(".")


def build_output_subdir(book: BookEntry, style: str = "perso") -> str:
    """
    Retourne le sous-dossier relatif à l'auteur.
    Perso : 'The Expanse' (serie subfolder)
    Scène : '' (serie dans le nom de fichier)
    """
    if style == "scene":
        return ""
    series = book.display_series
    return _clean_filename(series) if series else ""


def build_output_filename(book: BookEntry, style: str = "perso") -> str:
    """Retourne le nom de fichier M4B seul (sans chemin ni sous-dossier)."""
    cfg   = book.config
    title = _clean_filename(cfg.title or book.detected_title)

    if style == "scene":
        series  = _clean_filename(cfg.series or book.detected_series)
        author_raw = cfg.author or book.detected_author or ""
        author  = _clean_filename(author_raw.split(",")[0].strip())
        lang    = cfg.language or "FR"
        bitrate = cfg.bitrate.upper()
        tag     = cfg.encoded_by or "HellTrucker"
        parts   = []
        if series:
            parts.append(_dot(series))
        if cfg.volume:
            parts.append(f"T{_vol_number(cfg.volume):02d}")
        parts.append(_dot(title))
        parts.append(_dot(author))
        parts.append(lang)
        parts.append(f"[AAC.{bitrate}]")
        return ".".join(parts) + f"-{tag}.m4b"

    # Style perso
    if cfg.volume:
        num  = _vol_number(cfg.volume)
        return f"T {num:02d} - {title}.m4b"
    return f"{title}.m4b"

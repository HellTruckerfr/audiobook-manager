import os
import re
import json
import subprocess
import unicodedata
from typing import List, Dict, Optional, Callable, Tuple

from .models import AudioInfo, BookEntry, BookConfig, Chapter
from .config_manager import ConfigManager, FolderConfig

AUDIO_EXTS = {".mp3", ".m4b", ".m4a", ".aac", ".flac", ".ogg", ".opus"}


def _fingerprint(path: str) -> str:
    """Cheap filesystem fingerprint — no ffprobe, used to detect changes."""
    try:
        if os.path.isfile(path):
            st = os.stat(path)
            return f"f:{st.st_size}:{int(st.st_mtime)}"
        if os.path.isdir(path):
            files = sorted(
                f for f in os.listdir(path)
                if os.path.splitext(f)[1].lower() in AUDIO_EXTS
            )
            if not files:
                return "d:empty"
            total = sum(os.path.getsize(os.path.join(path, f)) for f in files)
            mtime = max(int(os.stat(os.path.join(path, f)).st_mtime) for f in files)
            return f"d:{len(files)}:{total}:{mtime}"
    except OSError:
        pass
    return ""


def _run_ffprobe(path: str) -> Optional[dict]:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", "-show_chapters", path],
            capture_output=True, text=True, timeout=30, encoding="utf-8"
        )
        if r.returncode == 0:
            return json.loads(r.stdout)
    except Exception:
        pass
    return None


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _title_key(title: str) -> str:
    """
    Normalize a title for cross-source matching.

    Handles variants like:
      "T1 - Rendez-vous avec Rama"
      "Rendez-vous avec Rama: Le cycle de Rama 1"
      "Rendez_vous_avec_Rama_Le_cycle_de_Rama_1"
    → all produce the same key.
    """
    t = _strip_accents(title.lower())
    t = t.replace("_", " ")

    # 1. Strip leading volume prefix BEFORE dash-replacement:
    #    "T1 - ", "T 1 - ", "Tome 2 - ", "Vol. 3 - "
    t = re.sub(
        r"^(?:t|tome|vol\.?|volume|livre|book)\s*\d+\s*[-–\s]+",
        "", t)
    # bare numeric prefix: "01 - ", "1. "
    t = re.sub(r"^\d+\s*[-–.]\s+", "", t)

    t = t.replace("-", " ")

    # 2. Strip series subtitle after ":" ("....: Le cycle de Rama 1")
    t = re.sub(r"\s*:.*$", "", t)

    # 3. Strip trailing French series indicator (" le cycle de X N")
    t = re.sub(r"\s+le\s+cycle\s+de\s+.*$", "", t)

    # 4. Strip parenthetical qualifiers: "(French Edition)", "(Unabridged)", etc.
    t = re.sub(r"\s*\(.*?\)", "", t)

    # 5. Remove articles
    for art in ("le ", "la ", "les ", "l'", "l ", "un ", "une ", "des ",
                "the ", "a ", "an "):
        if t.startswith(art):
            t = t[len(art):]
            break

    # 6. Keep only letters and digits
    t = re.sub(r"[^a-z0-9]", "", t)
    return t


def _strip_author_prefix(name: str) -> str:
    """
    Remove 'Author - ' or 'Author, Coauthor - ' prefix from folder/file names.
    Pattern: anything followed by ' - ' where the prefix contains no digits.
    """
    # Match "Author Name - Title" or "Author, Co - Title"
    m = re.match(r"^[^0-9\[\(]+\s+-\s+(.+)$", name)
    if m:
        return m.group(1).strip()
    return name


def _detect_chapter_title(filename: str) -> str:
    name = os.path.splitext(filename)[0]
    m = re.match(r"^\d+[\s.\-_]+(.+)$", name)
    if m:
        return m.group(1).strip()
    return name


def _detect_track_index(filename: str) -> int:
    m = re.match(r"^(\d+)", os.path.splitext(filename)[0])
    return int(m.group(1)) if m else 0


def _clean_author(artist: str, performer: str) -> Tuple[str, str]:
    """
    Separate author from narrator.
    If both artist and performer are set → artist=author, performer=narrator.
    If only artist → artist is likely the author (we can't know for sure).
    Returns (author, narrator).
    """
    if performer and performer != artist:
        return artist, performer
    # If performer == artist, the author likely set both to themselves (no narrator)
    return artist, performer


def _analyze_folder_source(folder_path: str, folder_label: str) -> Optional[AudioInfo]:
    files = sorted([
        f for f in os.listdir(folder_path)
        if os.path.splitext(f)[1].lower() in AUDIO_EXTS
    ])
    if not files:
        return None

    sample_path = os.path.join(folder_path, files[0])
    data = _run_ffprobe(sample_path)
    if not data:
        return None

    fmt = data.get("format", {})
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    audio_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None
    )
    if not audio_stream:
        return None

    codec = audio_stream.get("codec_name", "?")
    try:
        bitrate_kbps = int(int(fmt.get("bit_rate", 0)) / 1000)
    except (ValueError, TypeError):
        bitrate_kbps = 0
    if bitrate_kbps == 0:
        try:
            bitrate_kbps = int(int(audio_stream.get("bit_rate", 0)) / 1000)
        except (ValueError, TypeError):
            pass

    try:
        sample_rate_hz = int(audio_stream.get("sample_rate", 0))
    except (ValueError, TypeError):
        sample_rate_hz = 0

    channels = audio_stream.get("channels", 0)

    total_size = 0
    total_duration = 0.0
    for fn in files:
        fp = os.path.join(folder_path, fn)
        total_size += os.path.getsize(fp)
        try:
            r2 = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", fp],
                capture_output=True, text=True, timeout=10
            )
            total_duration += float(r2.stdout.strip())
        except Exception:
            pass

    artist = tags.get("artist", tags.get("album_artist", ""))
    performer = tags.get("performer", "")

    return AudioInfo(
        path=folder_path,
        folder_label=folder_label,
        codec=codec,
        bitrate_kbps=bitrate_kbps,
        sample_rate_hz=sample_rate_hz,
        channels=channels,
        duration_s=total_duration,
        size_mb=round(total_size / (1024 * 1024), 1),
        file_count=len(files),
        tag_album=tags.get("album", ""),
        tag_artist=artist,
        tag_performer=performer,
        tag_asin=tags.get("asin", ""),
    )


def _analyze_m4b_source(file_path: str, folder_label: str) -> Optional[AudioInfo]:
    data = _run_ffprobe(file_path)
    if not data:
        return None

    fmt = data.get("format", {})
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    audio_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None
    )
    if not audio_stream:
        return None

    codec = audio_stream.get("codec_name", "?")
    try:
        bitrate_kbps = int(int(fmt.get("bit_rate", 0)) / 1000)
    except (ValueError, TypeError):
        bitrate_kbps = 0

    try:
        sample_rate_hz = int(audio_stream.get("sample_rate", 0))
    except (ValueError, TypeError):
        sample_rate_hz = 0

    channels = audio_stream.get("channels", 0)
    try:
        duration_s = float(fmt.get("duration", 0))
    except (ValueError, TypeError):
        duration_s = 0.0

    size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 1)
    artist = tags.get("artist", tags.get("album_artist", ""))
    performer = tags.get("performer", "")

    return AudioInfo(
        path=file_path,
        folder_label=folder_label,
        codec=codec,
        bitrate_kbps=bitrate_kbps,
        sample_rate_hz=sample_rate_hz,
        channels=channels,
        duration_s=duration_s,
        size_mb=size_mb,
        file_count=1,
        tag_title=tags.get("title", ""),
        tag_album=tags.get("album", ""),
        tag_artist=artist,
        tag_performer=performer,
        tag_asin=tags.get("asin", ""),
    )


def _get_chapters_from_folder(folder_path: str, config: BookConfig) -> List[Chapter]:
    files = sorted([
        f for f in os.listdir(folder_path)
        if os.path.splitext(f)[1].lower() in AUDIO_EXTS
    ])
    chapters = []
    for fn in files:
        fp = os.path.join(folder_path, fn)
        idx = _detect_track_index(fn) or (len(chapters) + 1)
        detected = _detect_chapter_title(fn)
        custom = config.chapter_custom_titles.get(idx, "")
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", fp],
                capture_output=True, text=True, timeout=10
            )
            dur = float(r.stdout.strip())
        except Exception:
            dur = 0.0
        chapters.append(Chapter(
            index=idx,
            source_path=fp,
            detected_title=detected,
            custom_title=custom,
            duration_s=dur,
        ))
    return chapters


def _get_chapters_from_m4b(file_path: str, config: BookConfig) -> List[Chapter]:
    data = _run_ffprobe(file_path)
    if not data:
        return []
    chapters = []
    for ch in data.get("chapters", []):
        idx = ch.get("id", 0) + 1
        tags = {k.lower(): v for k, v in (ch.get("tags") or {}).items()}
        detected = tags.get("title", f"Chapitre {idx}")
        custom = config.chapter_custom_titles.get(idx, "")
        try:
            dur = float(ch.get("end_time", 0)) - float(ch.get("start_time", 0))
        except (ValueError, TypeError):
            dur = 0.0
        chapters.append(Chapter(
            index=idx,
            source_path=file_path,
            detected_title=detected,
            custom_title=custom,
            duration_s=dur,
        ))
    return chapters


class Scanner:
    def __init__(self, config_manager: ConfigManager):
        self.cfg = config_manager

    # ── Chargement instantané depuis le dernier scan sauvegardé ────────

    def _label_for_path(self, path: str) -> str:
        """Retourne le label du dossier source configuré qui contient `path`,
        ou 'M4B' si aucun ne correspond."""
        norm = os.path.normcase(os.path.abspath(path))
        for folder in self.cfg.app_config.source_folders:
            norm_folder = os.path.normcase(os.path.abspath(folder.path))
            if norm.startswith(norm_folder + os.sep) or norm == norm_folder:
                return folder.label
        # Essayer aussi avec output_m4b (le dossier de sortie est souvent aussi une source)
        out_dir = self.cfg.app_config.output_m4b
        if out_dir:
            norm_out = os.path.normcase(os.path.abspath(out_dir))
            if norm.startswith(norm_out + os.sep) or norm == norm_out:
                return out_dir  # fallback : utilise le chemin brut comme label
        return "M4B"

    def _enrich_synthetic_source(self, src: "AudioInfo") -> Tuple["AudioInfo", bool]:
        """Pour une source avec bitrate_kbps=0 et fichier existant, lit les vraies
        métadonnées (cache d'abord, ffprobe ensuite).
        Retourne (source_enrichie, cache_mis_à_jour)."""
        if src.bitrate_kbps != 0 or not os.path.isfile(src.path):
            return src, False
        fp = _fingerprint(src.path)
        cached = self.cfg.get_cached_source(src.path, fp)
        if cached:
            real = AudioInfo.from_dict(cached)
            real.folder_label = src.folder_label
            return real, False
        real = _analyze_m4b_source(src.path, src.folder_label)
        if real:
            self.cfg.set_source_cache(src.path, fp, real.to_dict())
            return real, True
        return src, False

    def _build_mp3_output_index(self) -> dict:
        """Index {nom_dossier_feuille → chemin_absolu} des dossiers MP3 de sortie.
        Le nom du dossier feuille est le stem du M4B source."""
        output_mp3 = self.cfg.app_config.output_mp3
        if not output_mp3 or not os.path.isdir(output_mp3):
            return {}
        index = {}
        for dirpath, _, filenames in os.walk(output_mp3):
            if any(f.lower().endswith(".mp3") for f in filenames):
                index[os.path.basename(dirpath)] = dirpath
        return index

    def _enrich_output_info(self, book: "BookEntry", mp3_index: dict) -> bool:
        """Remplit output_m4b_info et output_mp3_info depuis cache ou ffprobe.
        Retourne True si le cache a été mis à jour."""
        dirty = False

        if book.output_m4b_path and os.path.isfile(book.output_m4b_path):
            fp = _fingerprint(book.output_m4b_path)
            cached = self.cfg.get_cached_source(book.output_m4b_path, fp)
            if cached:
                book.output_m4b_info = AudioInfo.from_dict(cached)
            else:
                info = _analyze_m4b_source(book.output_m4b_path, "output_m4b")
                if info:
                    self.cfg.set_source_cache(book.output_m4b_path, fp, info.to_dict())
                    book.output_m4b_info = info
                    dirty = True

        if book.output_m4b_path and mp3_index:
            stem = os.path.splitext(os.path.basename(book.output_m4b_path))[0]
            mp3_dir = mp3_index.get(stem)
            if mp3_dir and os.path.isdir(mp3_dir):
                book.output_mp3_dir = mp3_dir
                fp = _fingerprint(mp3_dir)
                cached = self.cfg.get_cached_source(mp3_dir, fp)
                if cached:
                    book.output_mp3_info = AudioInfo.from_dict(cached)
                else:
                    mp3_files = sorted(
                        f for f in os.listdir(mp3_dir) if f.lower().endswith(".mp3"))
                    if mp3_files:
                        info = _analyze_m4b_source(
                            os.path.join(mp3_dir, mp3_files[0]), "output_mp3")
                        if info:
                            self.cfg.set_source_cache(mp3_dir, fp, info.to_dict())
                            book.output_mp3_info = info
                            dirty = True
        return dirty

    def load_last_books(self) -> List[BookEntry]:
        """Reconstruit la bibliothèque depuis last_library.json.
        Pour les sources synthétiques (bitrate=0), tente d'enrichir depuis le cache
        ou via un ffprobe ponctuel."""
        from .models import AudioInfo, Chapter
        snapshots = self.cfg.load_last_scan()
        books = []
        seen_ids: set = set()
        cache_dirty = False

        for snap in snapshots:
            book_id = snap["id"]
            seen_ids.add(book_id)
            # library.json (mis à jour à chaque sauvegarde) prime sur le snapshot
            config  = (self.cfg.get_saved_config(book_id)
                       or BookConfig.from_dict(snap.get("config", {})))
            out_path = (self.cfg.get_saved_output_path(book_id)
                        or snap.get("output_m4b_path", ""))
            sources = [AudioInfo.from_dict(s) for s in snap.get("sources", [])]
            # Recalculer le label des sources synthétiques mal étiquetées
            known_labels = {f.label for f in self.cfg.app_config.source_folders}
            for s in sources:
                if s.folder_label not in known_labels:
                    s.folder_label = self._label_for_path(s.path)
            # Enrichir les sources sans bitrate avec les vraies métadonnées
            enriched = []
            for s in sources:
                real, updated = self._enrich_synthetic_source(s)
                enriched.append(real)
                if updated:
                    cache_dirty = True
            sources = enriched

            # Chapitres depuis le cache : essaye d'abord la source sélectionnée,
            # puis toutes les autres par ordre de qualité décroissante.
            chapters: List[Chapter] = []
            if sources:
                ordered = []
                preferred_label = config.selected_source_label
                if preferred_label:
                    ordered.extend(s for s in sources
                                   if s.folder_label == preferred_label)
                ordered.extend(sorted(
                    [s for s in sources if s not in ordered],
                    key=lambda s: s.quality_score, reverse=True))
                for src in ordered:
                    fp = _fingerprint(src.path)
                    cached = self.cfg.get_cached_chapters(src.path, fp)
                    if cached:
                        chapters = [Chapter.from_cached(c, config) for c in cached]
                        break

            # Statut de sortie : revérifier que le fichier existe encore
            status = "done" if out_path and os.path.exists(out_path) else "pending"

            # Si le snapshot n'a pas de sources mais que le fichier de sortie existe,
            # on crée une source synthétique pour que le livre survive au filtre
            # `kept_previous` lors du prochain scan incrémental.
            if not sources and out_path and os.path.isfile(out_path):
                try:
                    size_mb = round(os.path.getsize(out_path) / (1024 * 1024), 1)
                except OSError:
                    size_mb = 0.0
                synth = AudioInfo(
                    path=out_path, folder_label=self._label_for_path(out_path),
                    codec="aac", bitrate_kbps=0, sample_rate_hz=0, channels=2,
                    duration_s=0.0, size_mb=size_mb, file_count=1,
                )
                real, updated = self._enrich_synthetic_source(synth)
                if updated:
                    cache_dirty = True
                sources = [real]

            books.append(BookEntry(
                id=snap["id"],
                detected_author=snap.get("detected_author", ""),
                detected_series=snap.get("detected_series", ""),
                detected_title=snap.get("detected_title", ""),
                sources=sources,
                chapters=chapters,
                config=config,
                output_m4b_path=out_path,
                status=status,
                merged_from=snap.get("merged_from", []),
            ))

        # Récupérer les livres orphelins : présents dans library.json mais absents
        # de last_library.json (sources perdues ou jamais scannées). On les restitue
        # en utilisant le fichier de sortie comme source synthétique afin qu'ils
        # apparaissent dans la bibliothèque et survivent aux scans suivants.
        for book_id, book_dict in self.cfg._library.items():
            if book_id in seen_ids:
                continue
            out_path = book_dict.get("output_m4b_path", "")
            if not out_path or not os.path.isfile(out_path):
                continue
            config = BookConfig.from_dict(book_dict.get("config", {}))
            try:
                size_mb = round(os.path.getsize(out_path) / (1024 * 1024), 1)
            except OSError:
                size_mb = 0.0
            synth = AudioInfo(
                path=out_path,
                folder_label=self._label_for_path(out_path),
                codec="aac",
                bitrate_kbps=0,
                sample_rate_hz=0,
                channels=2,
                duration_s=0.0,
                size_mb=size_mb,
                file_count=1,
            )
            source, updated = self._enrich_synthetic_source(synth)
            if updated:
                cache_dirty = True
            books.append(BookEntry(
                id=book_id,
                detected_author=book_dict.get("detected_author", ""),
                detected_series=book_dict.get("detected_series", ""),
                detected_title=book_dict.get("detected_title", ""),
                sources=[source],
                chapters=[],
                config=config,
                output_m4b_path=out_path,
                status="done",
                merged_from=book_dict.get("merged_from", []),
            ))

        mp3_index = self._build_mp3_output_index()
        for book in books:
            if self._enrich_output_info(book, mp3_index):
                cache_dirty = True

        if cache_dirty:
            self.cfg.save_scan_cache()

        return books

    # ── Comptage rapide (sans ffprobe) ──────────────────────────────────

    def _quick_count_sources(self, skip_set: set) -> int:
        """Compte les sources audio sans appeler ffprobe — utilisé pour la barre de progression."""
        count = 0
        for folder in self.cfg.app_config.source_folders:
            if not os.path.isdir(folder.path):
                continue
            if folder.structured:
                try:
                    for author_name in os.listdir(folder.path):
                        author_path = os.path.join(folder.path, author_name)
                        if not os.path.isdir(author_path) or author_name.startswith("."):
                            continue
                        for sub in os.listdir(author_path):
                            sub_path = os.path.join(author_path, sub)
                            norm = os.path.normcase(os.path.abspath(sub_path))
                            if os.path.isdir(sub_path) and norm not in skip_set:
                                count += 1
                except OSError:
                    pass
            else:
                for dirpath, _, filenames in os.walk(folder.path):
                    norm = os.path.normcase(os.path.abspath(dirpath))
                    if norm in skip_set:
                        continue
                    audio = [f for f in filenames
                             if os.path.splitext(f)[1].lower() in AUDIO_EXTS]
                    m4b = [f for f in audio if f.lower().endswith(".m4b")]
                    if m4b:
                        count += len(m4b)
                    elif audio:
                        count += 1
        return max(count, 1)

    # ── Scan (incrémental par défaut, complet si `incremental=False`) ───

    def scan_all(self, progress_cb: Optional[Callable] = None,
                 incremental: bool = True) -> List[BookEntry]:
        """progress_cb(current: int, total: int, msg: str) — appelé à chaque source analysée."""
        ignored = self.cfg.get_ignore_paths()

        if incremental:
            previous_books = self.load_last_books()
        else:
            previous_books = []

        # Paths déjà couverts par les livres existants — on les saute pendant le scan
        # et on réutilise leurs entrées telles quelles.
        known_paths = set()
        for b in previous_books:
            for s in b.sources:
                if os.path.exists(s.path):
                    known_paths.add(os.path.normcase(os.path.abspath(s.path)))

        # Filtrer les anciens livres : retirer uniquement les sources dont le fichier
        # n'existe plus sur disque. On ne filtre PAS sur `ignored` ici — quand le
        # dossier source et le dossier de sortie sont identiques, le chemin de sortie
        # se retrouverait dans `ignored` et ferait disparaître les livres existants.
        kept_previous: List[BookEntry] = []
        for b in previous_books:
            b.sources = [s for s in b.sources if os.path.exists(s.path)]
            if b.sources:
                kept_previous.append(b)

        raw: List[Tuple[str, str, str, AudioInfo]] = []
        path_fps: Dict[str, str] = {}

        skip_set = known_paths | ignored

        _total   = self._quick_count_sources(skip_set)
        _counter = [0]

        def _prog(msg: str):
            if progress_cb:
                progress_cb(_counter[0], _total, msg)

        def _tick(msg: str):
            _counter[0] += 1
            _prog(msg)

        for folder in self.cfg.app_config.source_folders:
            if not os.path.isdir(folder.path):
                continue
            _prog(f"Scan : {folder.label}")

            if folder.structured:
                raw.extend(self._scan_structured(
                    folder, _tick, path_fps, skip_set))
            else:
                raw.extend(self._scan_unstructured(
                    folder, _tick, path_fps, skip_set))

        # Conserver dans le cache les paths utilisés par les livres déjà connus
        # (sinon `cleanup_cache` les supprimerait).
        active_paths = set(path_fps.keys())
        for b in kept_previous:
            for s in b.sources:
                active_paths.add(s.path)
        self.cfg.cleanup_cache(active_paths)

        # Construire un mapping path → book_id à partir de l'historique enregistré.
        # Cela respecte les fusions manuelles : si l'utilisateur a fusionné une source
        # dans un autre livre, son path doit retourner à ce livre, pas à une nouvelle
        # entrée groupée par title_key.
        path_overrides = self._build_path_overrides()

        # Regrouper par clé de titre — sauf si le path a un override de fusion connu.
        groups: Dict[str, dict] = {}
        for title, author, narrator, audio in raw:
            norm = os.path.normcase(os.path.abspath(audio.path))
            key = path_overrides.get(norm)
            if not key:
                key = _title_key(title) or _title_key(audio.tag_album or "unknown")
            if key not in groups:
                groups[key] = {"title": title, "author": author,
                               "narrator": narrator, "sources": []}
            else:
                if len(title) > len(groups[key]["title"]):
                    groups[key]["title"] = title
                if not groups[key]["author"] and author:
                    groups[key]["author"] = author
                if not groups[key]["narrator"] and narrator:
                    groups[key]["narrator"] = narrator
            groups[key]["sources"].append(audio)

        books = []
        for key, g in groups.items():
            book_id      = key
            saved_config = self.cfg.get_saved_config(book_id)
            saved_output = self.cfg.get_saved_output_path(book_id)
            config       = saved_config or BookConfig(
                title=g["title"], author=g["author"], narrator=g["narrator"])

            best    = max(g["sources"], key=lambda s: s.quality_score)
            best_fp = path_fps.get(best.path) or _fingerprint(best.path)

            # Chapitres depuis cache ou ffprobe
            cached_chs = self.cfg.get_cached_chapters(best.path, best_fp)
            if cached_chs is not None:
                chapters = [Chapter.from_cached(c, config) for c in cached_chs]
            else:
                _prog(f"Chapitres : {g['title'][:40]}")
                if os.path.isfile(best.path):
                    chapters = _get_chapters_from_m4b(best.path, config)
                else:
                    chapters = _get_chapters_from_folder(best.path, config)
                self.cfg.set_chapters_cache(best.path, best_fp,
                                            [c.to_dict() for c in chapters])

            book = BookEntry(
                id=book_id,
                detected_author=g["author"],
                detected_series="",
                detected_title=g["title"],
                sources=g["sources"],
                chapters=chapters,
                config=config,
                output_m4b_path=saved_output,
                status="done" if saved_output and os.path.exists(saved_output) else "pending",
            )
            books.append(book)

        # En mode incrémental, fusionner avec les livres déjà connus (qu'on n'a
        # pas re-scannés). Si un nouveau book partage le même id (= title_key)
        # qu'un ancien, on additionne ses sources à l'ancien.
        if kept_previous:
            prev_by_id = {b.id: b for b in kept_previous}
            merged: List[BookEntry] = list(kept_previous)
            for nb in books:
                existing = prev_by_id.get(nb.id)
                if existing is None:
                    merged.append(nb)
                else:
                    existing_paths = {s.path for s in existing.sources}
                    for s in nb.sources:
                        if s.path not in existing_paths:
                            existing.sources.append(s)
                    if not existing.chapters and nb.chapters:
                        existing.chapters = nb.chapters
            books = merged

        books = sorted(books, key=lambda b: _strip_accents(b.display_title.lower()))

        # Enrichir les infos de sortie M4B + MP3
        mp3_index = self._build_mp3_output_index()
        for book in books:
            self._enrich_output_info(book, mp3_index)

        # Persister le cache mis à jour + snapshot de la bibliothèque
        self.cfg.save_scan_cache()
        self.cfg.save_last_scan([_book_snapshot(b) for b in books])

        return books

    # ── Mapping de fusion : path → book_id ─────────────────────────────

    def _build_path_overrides(self) -> Dict[str, str]:
        """Construit un dict `path_normalisé → target_book_id` depuis l'historique :
        `library.json[*].merged_from[*].source_paths` et `last_library.json[*].sources[*].path`.
        Permet au scan de respecter les fusions manuelles et de réattacher chaque
        source à son livre, indépendamment de son title_key automatique."""
        overrides: Dict[str, str] = {}
        # 1. last_library : paths primaires de chaque book actuel
        for snap in self.cfg.load_last_scan() or []:
            target = snap.get("id")
            if not target:
                continue
            for s in snap.get("sources", []):
                p = s.get("path", "")
                if p:
                    overrides[os.path.normcase(os.path.abspath(p))] = target
        # 2. library.json : paths historiques de fusions manuelles
        for book_data in self.cfg._library.values():
            target = book_data.get("id")
            if not target:
                continue
            for snap in (book_data.get("merged_from") or []):
                for p in snap.get("source_paths", []):
                    if p:
                        overrides[os.path.normcase(os.path.abspath(p))] = target
        return overrides

    def load_chapters(self, book: BookEntry) -> List[Chapter]:
        src = book.selected_source
        if not src:
            return []
        if os.path.isfile(src.path):
            return _get_chapters_from_m4b(src.path, book.config)
        return _get_chapters_from_folder(src.path, book.config)

    # ── Helpers internes ───────────────────────────────────────────────

    def _get_source_info(self, path: str, label: str,
                         fp: str, progress_cb, display_name: str) -> Optional[AudioInfo]:
        """Retourne AudioInfo depuis le cache si possible, sinon lance ffprobe."""
        cached = self.cfg.get_cached_source(path, fp)
        if cached:
            info = AudioInfo.from_dict(cached)
            info.folder_label = label  # le label peut avoir changé
            return info

        if progress_cb:
            progress_cb(f"Analyse : {display_name[:50]}")
        if os.path.isfile(path):
            info = _analyze_m4b_source(path, label)
        else:
            info = _analyze_folder_source(path, label)
        if info:
            self.cfg.set_source_cache(path, fp, info.to_dict())
        return info

    # ------------------------------------------------------------------

    def _scan_structured(self, folder: FolderConfig, progress_cb,
                         path_fps: dict, skip_set: set) -> List[Tuple]:
        results = []
        root = folder.path

        def _is_skipped(p: str) -> bool:
            return os.path.normcase(os.path.abspath(p)) in skip_set

        for author_name in sorted(os.listdir(root)):
            author_path = os.path.join(root, author_name)
            if not os.path.isdir(author_path) or author_name.startswith("."):
                continue

            for sub in sorted(os.listdir(author_path)):
                sub_path = os.path.join(author_path, sub)
                if not os.path.isdir(sub_path):
                    continue
                if _is_skipped(sub_path):
                    continue

                audio_files = [
                    f for f in os.listdir(sub_path)
                    if os.path.splitext(f)[1].lower() in AUDIO_EXTS
                    and not _is_skipped(os.path.join(sub_path, f))
                ]
                sub_subdirs = [
                    d for d in os.listdir(sub_path)
                    if os.path.isdir(os.path.join(sub_path, d))
                    and not _is_skipped(os.path.join(sub_path, d))
                ]

                if audio_files:
                    fp = _fingerprint(sub_path)
                    path_fps[sub_path] = fp
                    info = self._get_source_info(
                        sub_path, folder.label, fp, progress_cb,
                        f"{author_name} / {sub}")
                    if info:
                        title = _strip_author_prefix(sub) or info.tag_album or sub
                        author, narrator = _clean_author(info.tag_artist, info.tag_performer)
                        if not author:
                            author = author_name
                        results.append((title, author, narrator, info))

                elif sub_subdirs:
                    for vol in sorted(sub_subdirs):
                        vol_path = os.path.join(sub_path, vol)
                        if _is_skipped(vol_path):
                            continue
                        vol_files = [
                            f for f in os.listdir(vol_path)
                            if os.path.splitext(f)[1].lower() in AUDIO_EXTS
                            and not _is_skipped(os.path.join(vol_path, f))
                        ]
                        if vol_files:
                            fp = _fingerprint(vol_path)
                            path_fps[vol_path] = fp
                            info = self._get_source_info(
                                vol_path, folder.label, fp, progress_cb,
                                f"{author_name} / {sub} / {vol}")
                            if info:
                                title = _strip_author_prefix(vol) or info.tag_album or vol
                                author, narrator = _clean_author(info.tag_artist, info.tag_performer)
                                if not author:
                                    author = author_name
                                results.append((title, author, narrator, info))

        return results

    def _scan_unstructured(self, folder: FolderConfig, progress_cb,
                           path_fps: dict, skip_set: set) -> List[Tuple]:
        results = []
        root = folder.path

        def _is_skipped(p: str) -> bool:
            return os.path.normcase(os.path.abspath(p)) in skip_set

        for dirpath, dirnames, filenames in os.walk(root):
            # Skip les sous-dossiers déjà connus (pas de descente inutile)
            dirnames[:] = [d for d in sorted(dirnames)
                           if not d.startswith(".")
                           and not _is_skipped(os.path.join(dirpath, d))]

            if _is_skipped(dirpath):
                continue

            audio_files = [
                f for f in filenames
                if os.path.splitext(f)[1].lower() in AUDIO_EXTS
                and not _is_skipped(os.path.join(dirpath, f))
            ]
            m4b_files = [f for f in audio_files if f.lower().endswith(".m4b")]

            if m4b_files:
                for fn in m4b_files:
                    file_path = os.path.join(dirpath, fn)
                    fp = _fingerprint(file_path)
                    path_fps[file_path] = fp
                    info = self._get_source_info(
                        file_path, folder.label, fp, progress_cb, fn)
                    if info:
                        title = (_m4b_best_title(info.tag_title, info.tag_album)
                                 or os.path.splitext(fn)[0])
                        author, narrator = _clean_author(info.tag_artist, info.tag_performer)
                        if not author:
                            author = _infer_author(dirpath, root)
                        results.append((title, author, narrator, info))

            elif audio_files:
                fp = _fingerprint(dirpath)
                path_fps[dirpath] = fp
                info = self._get_source_info(
                    dirpath, folder.label, fp, progress_cb,
                    os.path.basename(dirpath))
                if info:
                    folder_name = os.path.basename(dirpath)
                    title = _strip_author_prefix(folder_name) or info.tag_album or folder_name
                    author, narrator = _clean_author(info.tag_artist, info.tag_performer)
                    if not author:
                        author = _infer_author(dirpath, root)
                    results.append((title, author, narrator, info))

        return results


def _m4b_best_title(tag_title: str, tag_album: str) -> str:
    """
    Pour un M4B individuel, préfère tag_title quand il est plus spécifique
    que tag_album (cas typique : album = nom de série, title = nom du tome).
    """
    if not tag_title:
        return tag_album
    if not tag_album:
        return tag_title
    # Si title et album sont identiques, l'un ou l'autre convient
    if _title_key(tag_title) == _title_key(tag_album):
        return tag_title
    # Si album est un sous-texte de title → title est plus précis
    # Sinon préférer title (plus spécifique en général)
    return tag_title


def _infer_author(path: str, root: str) -> str:
    rel = os.path.relpath(path, root)
    parts = rel.split(os.sep)
    return parts[0] if len(parts) > 1 else ""


def _book_snapshot(book: "BookEntry") -> dict:
    """Sérialise un BookEntry pour last_library.json (sources incluses, pas les chapitres)."""
    return {
        "id":               book.id,
        "detected_author":  book.detected_author,
        "detected_series":  book.detected_series,
        "detected_title":   book.detected_title,
        "output_m4b_path":  book.output_m4b_path,
        "status":           book.status,
        "config":           book.config.to_dict(),
        "sources":          [s.to_dict() for s in book.sources],
        "merged_from":      book.merged_from,
    }

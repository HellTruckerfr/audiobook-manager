import json
import os
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from .models import BookEntry, BookConfig

CONFIG_FILE      = "config.json"
LIBRARY_FILE     = "library.json"
SCAN_CACHE_FILE  = "scan_cache.json"
LAST_SCAN_FILE   = "last_library.json"


@dataclass
class FolderConfig:
    label: str
    path: str
    structured: bool = False
    mp3_only: bool = False   # si True, ignoré comme source pour l'encodage M4B


DEFAULT_METADATA_REQUIRED = ["title", "author", "narrator", "year", "asin", "cover_path"]

# Template dossier : {author_raw} = auteur brut, {series_release} = nom calculé du dossier série,
# {book_release} = nom calculé du dossier livre. Les segments vides sont supprimés.
DEFAULT_SCENE_COPY_DIR_TEMPLATE = "{author_raw}/{series_raw}/{tag_album}"

# Template fichier : contrôle le nom de release (dossier livre ET nom de fichier).
# Le même template est appliqué deux fois : une fois pour le dossier série (volume/title vides,
# integrale="Integrale"), une fois pour le livre (valeurs réelles).
DEFAULT_SCENE_COPY_FILE_TEMPLATE = (
    "{author}.{series}.{volume}.{integrale}.{title}.{year}.{lang}.{format}.{bitrate}.{codec}-{group}"
)


@dataclass
class AppConfig:
    source_folders: List[FolderConfig] = field(default_factory=list)
    output_m4b: str = ""
    output_mp3: str = ""
    logo_path: str = ""
    font_path: str = "C:/Windows/Fonts/arialbd.ttf"
    watermark_text: str = ""
    naming_style: str = "perso"   # "perso" | "scene"
    metadata_required_fields: List[str] = field(
        default_factory=lambda: list(DEFAULT_METADATA_REQUIRED))
    scene_copy_dest_m4b: str = ""
    scene_copy_dest_mp3: str = ""
    scene_copy_dir_template: str = DEFAULT_SCENE_COPY_DIR_TEMPLATE
    scene_copy_file_template: str = DEFAULT_SCENE_COPY_FILE_TEMPLATE
    scene_copy_include_codec: bool = True
    scene_copy_include_bitrate: bool = True
    scene_copy_group: str = "HellTrucker"
    scan_ignore_paths: List[str] = field(default_factory=list)
    ui_prefs: dict = field(default_factory=dict)


def _sort_key(s: str) -> str:
    """Clé de tri naturel : insensible à la casse/accents, nombres triés numériquement."""
    normalized = "".join(
        c for c in unicodedata.normalize("NFD", s.casefold())
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r'\d+', lambda m: m.group().zfill(10), normalized)


class ConfigManager:
    def __init__(self, base_dir: str):
        self.base_dir       = base_dir
        self.config_path    = os.path.join(base_dir, CONFIG_FILE)
        self.library_path   = os.path.join(base_dir, LIBRARY_FILE)
        self.cache_path     = os.path.join(base_dir, SCAN_CACHE_FILE)
        self.last_scan_path = os.path.join(base_dir, LAST_SCAN_FILE)
        self.app_config     = AppConfig()
        self._library: Dict[str, dict]    = {}
        self._scan_cache: Dict[str, dict] = {}

    def load(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.app_config = AppConfig(
                source_folders=[
                    FolderConfig(
                        label=fd["label"],
                        path=fd["path"],
                        structured=fd.get("structured", False),
                        mp3_only=fd.get("mp3_only", False),
                    )
                    for fd in data.get("source_folders", [])
                ],
                output_m4b=data.get("output_m4b", ""),
                output_mp3=data.get("output_mp3", ""),
                logo_path=data.get("logo_path", ""),
                font_path=data.get("font_path", "C:/Windows/Fonts/arialbd.ttf"),
                watermark_text=data.get("watermark_text", ""),
                naming_style=data.get("naming_style", "perso"),
                metadata_required_fields=data.get(
                    "metadata_required_fields", list(DEFAULT_METADATA_REQUIRED)),
                scene_copy_dest_m4b=data.get("scene_copy_dest_m4b",
                                            data.get("scene_copy_dest", "")),
                scene_copy_dest_mp3=data.get("scene_copy_dest_mp3", ""),
                scene_copy_dir_template=data.get(
                    "scene_copy_dir_template", DEFAULT_SCENE_COPY_DIR_TEMPLATE),
                scene_copy_file_template=data.get(
                    "scene_copy_file_template", DEFAULT_SCENE_COPY_FILE_TEMPLATE),
                scene_copy_include_codec=data.get("scene_copy_include_codec", True),
                scene_copy_include_bitrate=data.get("scene_copy_include_bitrate", True),
                scene_copy_group=data.get("scene_copy_group", "HellTrucker"),
                scan_ignore_paths=data.get("scan_ignore_paths", []),
                ui_prefs=data.get("ui", {}),
            )
        if os.path.exists(self.library_path):
            with open(self.library_path, "r", encoding="utf-8") as f:
                self._library = json.load(f)
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self._scan_cache = json.load(f)
            except Exception:
                self._scan_cache = {}

    def save_config(self):
        data = {
            "source_folders": [
                {"label": f.label, "path": f.path,
                 "structured": f.structured, "mp3_only": f.mp3_only}
                for f in self.app_config.source_folders
            ],
            "output_m4b": self.app_config.output_m4b,
            "output_mp3": self.app_config.output_mp3,
            "logo_path": self.app_config.logo_path,
            "font_path": self.app_config.font_path,
            "watermark_text": self.app_config.watermark_text,
            "naming_style": self.app_config.naming_style,
            "metadata_required_fields": self.app_config.metadata_required_fields,
            "scene_copy_dest_m4b": self.app_config.scene_copy_dest_m4b,
            "scene_copy_dest_mp3": self.app_config.scene_copy_dest_mp3,
            "scene_copy_dir_template": self.app_config.scene_copy_dir_template,
            "scene_copy_file_template": self.app_config.scene_copy_file_template,
            "scene_copy_include_codec": self.app_config.scene_copy_include_codec,
            "scene_copy_include_bitrate": self.app_config.scene_copy_include_bitrate,
            "scene_copy_group": self.app_config.scene_copy_group,
            "scan_ignore_paths": self.app_config.scan_ignore_paths,
            "ui": self.app_config.ui_prefs,
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_col_widths(self, key: str) -> list:
        return self.app_config.ui_prefs.get(key, [])

    def set_col_widths(self, key: str, widths: list):
        self.app_config.ui_prefs[key] = widths

    def save_book(self, book: BookEntry):
        self._library[book.id] = book.to_dict()
        self._save_library()

    def delete_book(self, book_id: str):
        if book_id in self._library:
            del self._library[book_id]
            self._save_library()

    def get_saved_config(self, book_id: str) -> Optional[BookConfig]:
        if book_id in self._library:
            return BookConfig.from_dict(self._library[book_id].get("config", {}))
        return None

    def get_saved_output_path(self, book_id: str) -> str:
        if book_id in self._library:
            return self._library[book_id].get("output_m4b_path", "")
        return ""

    def get_ignore_paths(self) -> set:
        """Ensemble normalisé des chemins à exclure du scan : sorties de conversion +
        liste manuelle (`scan_ignore_paths`)."""
        out = set()
        for entry in self._library.values():
            p = entry.get("output_m4b_path", "")
            if p:
                out.add(os.path.normcase(os.path.abspath(p)))
        for p in self.app_config.scan_ignore_paths:
            if p:
                out.add(os.path.normcase(os.path.abspath(p)))
        return out

    def add_ignore_paths(self, paths):
        """Ajoute des chemins à `scan_ignore_paths` sans doublon (préserve la casse
        d'origine pour l'affichage)."""
        existing_norm = {os.path.normcase(os.path.abspath(p))
                         for p in self.app_config.scan_ignore_paths}
        added = False
        for p in paths:
            if not p:
                continue
            norm = os.path.normcase(os.path.abspath(p))
            if norm in existing_norm:
                continue
            self.app_config.scan_ignore_paths.append(p)
            existing_norm.add(norm)
            added = True
        if added:
            self.save_config()
        return added

    def get_referential(self, field: str) -> list:
        values = set()
        for book_dict in self._library.values():
            val = book_dict.get("config", {}).get(field, "").strip()
            if val:
                values.add(val)
        return sorted(values, key=_sort_key)

    def rename_referential_value(self, field: str, old: str, new: str) -> int:
        count = 0
        for book_dict in self._library.values():
            cfg = book_dict.get("config", {})
            if cfg.get(field) == old:
                cfg[field] = new
                count += 1
        if count:
            self._save_library()
        return count

    def _save_library(self):
        with open(self.library_path, "w", encoding="utf-8") as f:
            json.dump(self._library, f, ensure_ascii=False, indent=2)

    # ── Scan cache (AudioInfo + chapters par chemin source) ───────────

    def get_cached_source(self, path: str, fp: str) -> Optional[dict]:
        entry = self._scan_cache.get(path)
        if entry and entry.get("fp") == fp:
            return entry.get("audio")
        return None

    def get_cached_chapters(self, path: str, fp: str) -> Optional[list]:
        entry = self._scan_cache.get(path)
        if entry and entry.get("fp") == fp:
            return entry.get("chapters")
        return None

    def set_source_cache(self, path: str, fp: str, audio_dict: dict):
        existing = self._scan_cache.get(path, {})
        if existing.get("fp") == fp:
            self._scan_cache[path] = {**existing, "audio": audio_dict}
        else:
            self._scan_cache[path] = {"fp": fp, "audio": audio_dict}

    def set_chapters_cache(self, path: str, fp: str, chapters: list):
        existing = self._scan_cache.get(path, {})
        if existing.get("fp") == fp:
            self._scan_cache[path] = {**existing, "chapters": chapters}
        else:
            self._scan_cache[path] = {"fp": fp, "chapters": chapters}

    def save_scan_cache(self):
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(self._scan_cache, f, ensure_ascii=False, indent=2)

    def cleanup_cache(self, active_paths: set):
        stale = [p for p in list(self._scan_cache) if p not in active_paths]
        for p in stale:
            del self._scan_cache[p]

    # ── Backup / Restauration ─────────────────────────────────────────

    def backup(self, dest_zip: str):
        """Crée un ZIP contenant config.json + library.json."""
        with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for path, name in [
                (self.config_path,  CONFIG_FILE),
                (self.library_path, LIBRARY_FILE),
            ]:
                if os.path.exists(path):
                    zf.write(path, name)

    def restore(self, zip_path: str):
        """Extrait config.json + library.json depuis un ZIP, puis recharge."""
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            for name in [CONFIG_FILE, LIBRARY_FILE]:
                if name in names:
                    zf.extract(name, self.base_dir)
        self.load()

    def reset_scan_cache(self):
        """Vide uniquement le cache de fingerprints/ffprobe.
        `last_library.json` et `library.json` sont préservés pour ne pas perdre
        les fusions manuelles et les méta saisies par l'utilisateur."""
        self._scan_cache = {}
        if os.path.exists(self.cache_path):
            os.remove(self.cache_path)

    # ── Dernière bibliothèque connue ──────────────────────────────────

    def save_last_scan(self, snapshots: list):
        with open(self.last_scan_path, "w", encoding="utf-8") as f:
            json.dump(snapshots, f, ensure_ascii=False, indent=2)

    def load_last_scan(self) -> list:
        if os.path.exists(self.last_scan_path):
            try:
                with open(self.last_scan_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

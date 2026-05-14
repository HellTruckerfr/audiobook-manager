from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class AudioInfo:
    path: str
    folder_label: str
    codec: str
    bitrate_kbps: int
    sample_rate_hz: int
    channels: int
    duration_s: float
    size_mb: float        # stored as MiB (bytes / 1024²) despite the name
    file_count: int = 1
    tag_title: str = ""
    tag_album: str = ""
    tag_artist: str = ""
    tag_performer: str = ""
    tag_asin: str = ""
    vbr: Optional[bool] = None   # True=VBR, False=CBR, None=unknown

    @property
    def channels_label(self) -> str:
        return "Stéréo" if self.channels >= 2 else "Mono"

    @property
    def sample_rate_khz(self) -> str:
        return f"{self.sample_rate_hz // 1000}kHz" if self.sample_rate_hz else "?"

    @property
    def quality_score(self) -> int:
        return self.bitrate_kbps * (2 if self.channels >= 2 else 1)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "folder_label": self.folder_label,
            "codec": self.codec,
            "bitrate_kbps": self.bitrate_kbps,
            "sample_rate_hz": self.sample_rate_hz,
            "channels": self.channels,
            "duration_s": self.duration_s,
            "size_mb": self.size_mb,
            "file_count": self.file_count,
            "tag_title": self.tag_title,
            "tag_album": self.tag_album,
            "tag_artist": self.tag_artist,
            "tag_performer": self.tag_performer,
            "tag_asin": self.tag_asin,
            "vbr": self.vbr,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AudioInfo":
        return cls(
            path=d["path"],
            folder_label=d.get("folder_label", ""),
            codec=d.get("codec", "?"),
            bitrate_kbps=d.get("bitrate_kbps", 0),
            sample_rate_hz=d.get("sample_rate_hz", 0),
            channels=d.get("channels", 0),
            duration_s=d.get("duration_s", 0.0),
            size_mb=d.get("size_mb", 0.0),
            file_count=d.get("file_count", 1),
            tag_title=d.get("tag_title", ""),
            tag_album=d.get("tag_album", ""),
            tag_artist=d.get("tag_artist", ""),
            tag_performer=d.get("tag_performer", ""),
            tag_asin=d.get("tag_asin", ""),
            vbr=d.get("vbr"),
        )


@dataclass
class Chapter:
    index: int
    source_path: str
    detected_title: str
    custom_title: str = ""
    duration_s: float = 0.0

    @property
    def title(self) -> str:
        return self.custom_title if self.custom_title else self.detected_title

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "source_path": self.source_path,
            "detected_title": self.detected_title,
            "duration_s": self.duration_s,
        }

    @classmethod
    def from_cached(cls, d: dict, config: "BookConfig") -> "Chapter":
        idx = d["index"]
        return cls(
            index=idx,
            source_path=d.get("source_path", ""),
            detected_title=d.get("detected_title", ""),
            custom_title=config.chapter_custom_titles.get(idx, ""),
            duration_s=d.get("duration_s", 0.0),
        )


@dataclass
class BookConfig:
    title: str = ""
    author: str = ""
    series: str = ""
    volume: str = ""
    narrator: str = ""
    genre: str = "Audiobook"
    year: str = ""
    language: str = "FR"
    asin: str = ""
    publisher: str = ""
    bitrate: str = "128k"
    sample_rate: str = "44100"
    watermark: bool = True
    cover_path: str = ""
    description: str = ""
    copyright: str = ""
    selected_source_label: str = ""
    ignore_metadata_check: bool = False
    title_source: str = "detected"   # "detected" | "normalized" | "custom"
    chapter_custom_titles: Dict[int, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "author": self.author,
            "series": self.series,
            "volume": self.volume,
            "narrator": self.narrator,
            "genre": self.genre,
            "year": self.year,
            "language": self.language,
            "asin": self.asin,
            "publisher": self.publisher,
            "bitrate": self.bitrate,
            "sample_rate": self.sample_rate,
            "watermark": self.watermark,
            "cover_path": self.cover_path,
            "description": self.description,
            "copyright": self.copyright,
            "selected_source_label": self.selected_source_label,
            "ignore_metadata_check": self.ignore_metadata_check,
            "title_source": self.title_source,
            "chapter_custom_titles": {str(k): v for k, v in self.chapter_custom_titles.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BookConfig":
        titles = {int(k): v for k, v in d.get("chapter_custom_titles", {}).items()}
        return cls(
            title=d.get("title", ""),
            author=d.get("author", ""),
            series=d.get("series", ""),
            volume=d.get("volume", ""),
            narrator=d.get("narrator", ""),
            genre=d.get("genre", "Audiobook"),
            year=d.get("year", ""),
            language=d.get("language", "FR"),
            asin=d.get("asin", ""),
            publisher=d.get("publisher", ""),
            bitrate=d.get("bitrate", "128k"),
            sample_rate=d.get("sample_rate", "44100"),
            watermark=d.get("watermark", False),
            cover_path=d.get("cover_path", ""),
            description=d.get("description", ""),
            copyright=d.get("copyright", ""),
            selected_source_label=d.get("selected_source_label", ""),
            ignore_metadata_check=d.get("ignore_metadata_check", False),
            title_source=d.get("title_source", "detected"),
            chapter_custom_titles=titles,
        )


@dataclass
class BookEntry:
    id: str
    detected_author: str
    detected_series: str
    detected_title: str
    sources: List[AudioInfo]
    chapters: List[Chapter]
    config: BookConfig
    output_m4b_path: str = ""
    status: str = "pending"
    merged_from: List[dict] = field(default_factory=list)
    # Transient — peuplé au scan/load, non persisté
    output_m4b_info: Optional["AudioInfo"] = field(default=None)
    output_mp3_dir: str = field(default="")
    output_mp3_info: Optional["AudioInfo"] = field(default=None)

    @property
    def display_title(self) -> str:
        return self.config.title or self.detected_title

    @property
    def display_author(self) -> str:
        return self.config.author or self.detected_author

    @property
    def display_series(self) -> str:
        return self.config.series or self.detected_series

    def is_metadata_complete(self, required_fields: List[str]) -> bool:
        """True si tous les champs requis sont renseignés OU si le livre est marqué « ignorer »."""
        if self.config.ignore_metadata_check:
            return True
        for f in required_fields:
            val = getattr(self.config, f, None)
            if isinstance(val, str):
                if not val.strip():
                    return False
            elif not val:
                return False
        return True

    @property
    def selected_source(self) -> Optional[AudioInfo]:
        sel = self.config.selected_source_label
        if sel:
            # Essai par path (format actuel), puis fallback label (ancien format)
            for s in self.sources:
                if s.path == sel:
                    return s
            for s in self.sources:
                if s.folder_label == sel:
                    return s
        if self.sources:
            return max(self.sources, key=lambda s: s.quality_score)
        return None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "detected_author": self.detected_author,
            "detected_series": self.detected_series,
            "detected_title": self.detected_title,
            "output_m4b_path": self.output_m4b_path,
            "status": self.status,
            "config": self.config.to_dict(),
            "merged_from": self.merged_from,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BookEntry":
        return cls(
            id=d["id"],
            detected_author=d.get("detected_author", ""),
            detected_series=d.get("detected_series", ""),
            detected_title=d.get("detected_title", ""),
            sources=[],
            chapters=[],
            config=BookConfig.from_dict(d.get("config", {})),
            output_m4b_path=d.get("output_m4b_path", ""),
            status=d.get("status", "pending"),
            merged_from=d.get("merged_from", []),
        )


@dataclass
class ConversionJob:
    book: BookEntry
    status: str = "queued"
    progress: float = 0.0
    message: str = ""
    output_path: str = ""
    job_type: str = "m4b"   # "m4b" | "mp3"

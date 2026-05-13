# Audiobook Manager

> Outil personnel de gestion, taggage et conversion d'audiobooks vers M4B/MP3  
> Personal tool for managing, tagging and converting audiobooks to M4B/MP3

---

## 🇫🇷 Français

### Description

Application de bureau (Windows) développée avec PyQt6 pour gérer une bibliothèque d'audiobooks.  
Elle scanne les dossiers sources, détecte les métadonnées, et permet de convertir vers **M4B** (avec chapitres, cover et tags complets) ou d'exporter en **MP3** (un fichier par chapitre).

### Fonctionnalités

- **Bibliothèque** — scan automatique des dossiers sources, détection codec/bitrate, affichage des sorties M4B et MP3
- **Éditeur** — édition complète des métadonnées : titre, auteur, narrateur, série, langue, couverture, chapitres
- **Conversion M4B** — copie directe (si déjà AAC 128k), ré-encodage ou concaténation parallèle de MP3/M4B sources
- **Export MP3** — découpage par chapitre, encodage LAME 128k, cover embarquée, tags ID3 complets
- **Watermark** — logo + texte incrustés sur la couverture via FFmpeg
- **File de conversion** — traitement séquentiel avec barre de progression et console de log
- **Convention scène** — nommage `Auteur.Titre.FRENCH.M4B.AAC.128kbps-HellTrucker`
- **Copie scène** — panneau dédié pour préparer le release final

### Prérequis

- Windows 10/11
- [FFmpeg](https://ffmpeg.org/download.html) (gyan.dev build recommandé pour `libfdk_aac`)
- Python 3.11+ et `pip install -r requirements.txt` (si exécution depuis les sources)

### Installation depuis les sources

```bash
git clone https://github.com/Helltrucker/audiobook-manager.git
cd audiobook-manager
pip install -r requirements.txt
python main.py
```

### Build exécutable autonome

FFmpeg doit être installé. Mettre à jour les chemins dans `audiobook_manager.spec` si nécessaire, puis :

```bash
pyinstaller audiobook_manager.spec
```

L'exécutable se trouve dans `dist/AudiobookManager/AudiobookManager.exe`.

### Structure du projet

```
audiobook-manager/
├── main.py                  # Point d'entrée
├── requirements.txt
├── audiobook_manager.spec   # Build PyInstaller
└── src/
    ├── models.py            # BookEntry, BookConfig, Chapter…
    ├── config_manager.py    # Persistance config.json / library.json
    ├── scanner.py           # Scan dossiers sources + ffprobe
    ├── converter.py         # Conversion M4B, export MP3, watermark
    ├── windows_utils.py
    └── gui/
        ├── app.py           # Fenêtre principale + navigation
        ├── library_panel.py # Page Bibliothèque
        ├── editor_panel.py  # Page Éditeur
        ├── queue_panel.py   # Page File de conversion
        ├── console_panel.py # Page Console
        ├── scene_copy_panel.py
        ├── settings_dialog.py
        ├── tag_import_dialog.py
        ├── referential_panel.py
        └── theme.py
```

---

## 🇬🇧 English

### Description

A Windows desktop application built with PyQt6 for managing an audiobook library.  
It scans source folders, detects metadata, and converts to **M4B** (with chapters, cover art and full tags) or exports as **MP3** (one file per chapter).

### Features

- **Library** — automatic folder scan, codec/bitrate detection, M4B and MP3 output status
- **Editor** — full metadata editing: title, author, narrator, series, language, cover, chapters
- **M4B conversion** — direct copy (if already AAC 128k), re-encode, or parallel MP3/M4B concatenation
- **MP3 export** — chapter splitting, LAME 128k encoding, embedded cover art, full ID3 tags
- **Watermark** — logo + text overlay on cover art via FFmpeg
- **Conversion queue** — sequential processing with progress bar and log console
- **Scene naming** — `Author.Title.FRENCH.M4B.AAC.128kbps-HellTrucker` convention
- **Scene copy** — dedicated panel to prepare the final release

### Requirements

- Windows 10/11
- [FFmpeg](https://ffmpeg.org/download.html) (gyan.dev full build recommended for `libfdk_aac`)
- Python 3.11+ and `pip install -r requirements.txt` (source run only)

### Run from source

```bash
git clone https://github.com/Helltrucker/audiobook-manager.git
cd audiobook-manager
pip install -r requirements.txt
python main.py
```

### Build standalone executable

Update the FFmpeg paths in `audiobook_manager.spec` if needed, then:

```bash
pyinstaller audiobook_manager.spec
```

The executable will be at `dist/AudiobookManager/AudiobookManager.exe`.

---

## License

Personal project — no redistribution intended.

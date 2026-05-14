# Audiobook Manager

> Outil personnel de gestion, taggage et conversion d'audiobooks vers M4B/MP3  
> Personal tool for managing, tagging and converting audiobooks to M4B/MP3

---

## 🇫🇷 Français

### Description

Application de bureau (Windows) développée avec PyQt6 pour gérer une bibliothèque d'audiobooks.  
Elle scanne les dossiers sources, détecte les métadonnées, et permet de convertir vers **M4B** (avec chapitres, cover et tags complets) ou d'exporter en **MP3** (un fichier par chapitre).

### Fonctionnalités

- **Sidebar rétractable** — navigation par icônes PNG, sections nommées (Édition / Scène / Outils), mode compact 52px ou étendu 200px
- **Bibliothèque** — scan automatique des dossiers sources, détection codec/bitrate, affichage des sorties M4B et MP3, sélection multiple via checkbox d'en-tête
- **Éditeur** — édition complète des métadonnées : titre, auteur, narrateur, série, langue, couverture (recadrée 1:1), chapitres, description Amazon ; navigation Livre précédent/suivant
- **Conversion M4B** — copie directe (si déjà AAC 128k), ré-encodage ou concaténation parallèle de MP3/M4B sources
- **Export MP3** — découpage par chapitre, encodage LAME 128k, cover embarquée, tags ID3 complets
- **Watermark** — logo + texte incrustés sur la couverture via FFmpeg
- **File de conversion** — traitement séquentiel avec barre de progression, sélection via checkbox d'en-tête, tri par colonnes
- **Convention scène** — nommage `Auteur.Titre.FRENCH.M4B.AAC.128kbps-HellTrucker`
- **Copie scène** — panneau dédié pour préparer le release final ; nommage intelligent (suppression `{title}` quand tous les tomes portent le nom de la série), génération automatique de fichiers NFO M4B et MP3
- **Présentation** — aperçu BBCode avec preview de la fiche de release (format M4B unifié)
- **Référentiel** — base d'auteurs et de séries
- **Console** — deux onglets : *Conversions* (log de conversion) et *Journal* (événements copie scène)

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
├── assets/
│   └── icons/               # Icônes PNG de la sidebar
└── src/
    ├── models.py            # BookEntry, BookConfig, Chapter…
    ├── config_manager.py    # Persistance config.json / library.json
    ├── scanner.py           # Scan dossiers sources + ffprobe
    ├── converter.py         # Conversion M4B, export MP3, watermark
    ├── bbcode.py            # Génération BBCode pour fiches de release
    ├── nfo.py               # Génération fichiers NFO
    ├── windows_utils.py
    └── gui/
        ├── app.py               # Fenêtre principale + sidebar rétractable
        ├── library_panel.py     # Page Bibliothèque
        ├── editor_panel.py      # Page Éditeur
        ├── queue_panel.py       # Page File de conversion
        ├── scene_copy_panel.py  # Page Copie scène
        ├── prez_panel.py        # Page Présentation BBCode
        ├── console_panel.py     # Console (Conversions + Journal)
        ├── referential_panel.py # Page Référentiel
        ├── settings_dialog.py
        ├── tag_import_dialog.py
        └── theme.py
```

---

## 🇬🇧 English

### Description

A Windows desktop application built with PyQt6 for managing an audiobook library.  
It scans source folders, detects metadata, and converts to **M4B** (with chapters, cover art and full tags) or exports as **MP3** (one file per chapter).

### Features

- **Collapsible sidebar** — PNG icon navigation, named sections (Edition / Scene / Tools), compact 52px or expanded 200px mode
- **Library** — automatic folder scan, codec/bitrate detection, M4B and MP3 output status, multi-select via header checkbox
- **Editor** — full metadata editing: title, author, narrator, series, language, cover art (1:1 crop), chapters, Amazon description; previous/next book navigation
- **M4B conversion** — direct copy (if already AAC 128k), re-encode, or parallel MP3/M4B concatenation
- **MP3 export** — chapter splitting, LAME 128k encoding, embedded cover art, full ID3 tags
- **Watermark** — logo + text overlay on cover art via FFmpeg
- **Conversion queue** — sequential processing with progress bar, header checkbox selection, column sorting
- **Scene naming** — `Author.Title.FRENCH.M4B.AAC.128kbps-HellTrucker` convention
- **Scene copy** — dedicated panel for final release prep; smart naming (drops `{title}` when all volumes share the series name), automatic NFO file generation for M4B and MP3
- **Presentation** — BBCode preview for release sheets (unified M4B format line)
- **Referential** — author and series database
- **Console** — two tabs: *Conversions* (conversion log) and *Journal* (scene copy events)

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

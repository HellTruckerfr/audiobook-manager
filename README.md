# Audiobook Manager

> Outil personnel de gestion, taggage et conversion d'audiobooks vers M4B/MP3  
> Personal tool for managing, tagging and converting audiobooks to M4B/MP3

---

## 🇫🇷 Français

### Description

Application de bureau (Windows) développée avec PyQt6 pour gérer une bibliothèque d'audiobooks.  
Elle scanne les dossiers sources, détecte les métadonnées, et permet de convertir vers **M4B** (avec chapitres, cover et tags complets) ou d'exporter en **MP3** (un fichier par chapitre).

### Fonctionnalités

- **Splash screen** — écran de chargement intégré à la fenêtre principale au démarrage
- **Sidebar rétractable** — navigation par icônes ICO multi-résolution, sections nommées (Édition / Scène / Outils), mode compact 52px ou étendu 200px
- **Bibliothèque** — scan automatique des dossiers sources, détection codec/bitrate, tri par colonnes (titre, auteur, état…), sélection multiple via checkbox d'en-tête, barre de recherche et filtre « Cacher complets » en ligne 2
- **Vue catalogue** — 3 niveaux (Auteurs → Séries/standalone → Volumes), cartes avec couverture, zoom +/−, fill-width dynamique
- **Éditeur** — édition complète des métadonnées : titre, auteur, narrateur, série, langue, couverture (recadrée 1:1), chapitres, description Amazon ; navigation Livre précédent/suivant
- **Conversion M4B** — copie directe (si déjà AAC 128k), ré-encodage ou concaténation parallèle de MP3/M4B sources
- **Export MP3** — découpage par chapitre, encodage LAME 128k, cover embarquée, tags ID3 complets
- **Watermark** — logo + texte incrustés sur la couverture via FFmpeg
- **File de conversion** — traitement séquentiel avec barre de progression, sélection via checkbox d'en-tête, tri par colonnes
- **Convention scène** — nommage `Auteur.Titre.FRENCH.M4B.AAC.128kbps-{Groupe}` (groupe configurable dans les Paramètres)
- **Copie scène** — panneau dédié pour préparer le release final ; nommage intelligent (suppression `{title}` quand tous les tomes portent le nom de la série), génération automatique de fichiers NFO M4B et MP3
- **Présentation** — aperçu BBCode avec preview de la fiche de release (format M4B unifié)
- **Référentiel** — base d'auteurs, séries, narrateurs et éditeurs avec renommage en masse
- **Console** — deux onglets : *Conversions* (log de conversion) et *Journal* (événements copie scène)
- **Paramètres** — backup/restauration de la config et bibliothèque (ZIP horodaté)

### Prérequis

- Windows 10/11
- [FFmpeg](https://ffmpeg.org/download.html) (gyan.dev full build recommandé pour `libfdk_aac`)
- Python 3.11+ et `pip install -r requirements.txt` (si exécution depuis les sources)

### Installation depuis les sources

```bash
git clone https://github.com/HellTruckerfr/audiobook-manager.git
cd audiobook-manager
pip install -r requirements.txt
python main.py
```

### Build exécutable

Deux distributions disponibles :

#### Portable (`.exe` autonome)

Un seul fichier `.exe`, aucune installation requise.

```bash
python -m PyInstaller audiobook_manager_onefile.spec -y
```

Sortie : `dist/AudiobookManager-portable.exe`

#### Installeur Windows

Installe dans `Program Files`, raccourci menu Démarrer, désinstalleur reconnu par Windows.  
Nécessite [Inno Setup](https://jrsoftware.org/isinfo.php).

```bash
python -m PyInstaller audiobook_manager.spec -y
iscc audiobook_manager_setup.iss
```

Sortie : `dist/AudiobookManager-Setup.exe`

> FFmpeg est bundlé dans les deux distributions — aucune dépendance pour l'utilisateur final.  
> Le chemin FFmpeg dans le `.spec` (`FFMPEG_BIN`) doit pointer vers un build **full** de gyan.dev (nécessaire pour `libfdk_aac`).

### Structure du projet

```
audiobook-manager/
├── main.py                       # Point d'entrée
├── requirements.txt
├── audiobook_manager.spec        # Build PyInstaller (dossier — base installeur)
├── audiobook_manager_onefile.spec # Build PyInstaller (fichier unique portable)
├── audiobook_manager_setup.iss   # Script Inno Setup (installeur Windows)
├── assets/
│   └── icons/                   # Icônes ICO multi-résolution (16/32/48/64/128px)
└── src/
    ├── models.py                 # BookEntry, BookConfig, Chapter…
    ├── config_manager.py         # Persistance config.json / library.json
    ├── scanner.py                # Scan dossiers sources + ffprobe
    ├── converter.py              # Conversion M4B, export MP3, watermark
    ├── bbcode.py                 # Génération BBCode pour fiches de release
    ├── nfo.py                    # Génération fichiers NFO
    ├── windows_utils.py
    └── gui/
        ├── app.py                # Fenêtre principale + sidebar + splash screen
        ├── icon_utils.py         # Chargement et cache des icônes ICO
        ├── library_panel.py      # Page Bibliothèque + vue Catalogue
        ├── editor_panel.py       # Page Éditeur
        ├── queue_panel.py        # Page File de conversion
        ├── scene_copy_panel.py   # Page Copie scène
        ├── prez_panel.py         # Page Présentation BBCode
        ├── console_panel.py      # Console (Conversions + Journal)
        ├── referential_panel.py  # Page Référentiel
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

- **Splash screen** — integrated loading screen shown in the main window on startup
- **Collapsible sidebar** — multi-resolution ICO icon navigation, named sections (Edition / Scene / Tools), compact 52px or expanded 200px mode
- **Library** — automatic folder scan, codec/bitrate detection, column sorting (title, author, status…), multi-select via header checkbox, search bar and "Hide completed" filter on row 2
- **Catalogue view** — 3 levels (Authors → Series/standalone → Volumes), cover art cards, zoom +/−, dynamic fill-width
- **Editor** — full metadata editing: title, author, narrator, series, language, cover art (1:1 crop), chapters, Amazon description; previous/next book navigation
- **M4B conversion** — direct copy (if already AAC 128k), re-encode, or parallel MP3/M4B concatenation
- **MP3 export** — chapter splitting, LAME 128k encoding, embedded cover art, full ID3 tags
- **Watermark** — logo + text overlay on cover art via FFmpeg
- **Conversion queue** — sequential processing with progress bar, header checkbox selection, column sorting
- **Scene naming** — `Author.Title.FRENCH.M4B.AAC.128kbps-{Group}` convention (group configurable in Settings)
- **Scene copy** — dedicated panel for final release prep; smart naming (drops `{title}` when all volumes share the series name), automatic NFO file generation for M4B and MP3
- **Presentation** — BBCode preview for release sheets (unified M4B format line)
- **Referential** — author, series, narrator and publisher database with bulk rename
- **Console** — two tabs: *Conversions* (conversion log) and *Journal* (scene copy events)
- **Settings** — backup/restore config and library (timestamped ZIP)

### Requirements

- Windows 10/11
- [FFmpeg](https://ffmpeg.org/download.html) (gyan.dev full build recommended for `libfdk_aac`)
- Python 3.11+ and `pip install -r requirements.txt` (source run only)

### Run from source

```bash
git clone https://github.com/HellTruckerfr/audiobook-manager.git
cd audiobook-manager
pip install -r requirements.txt
python main.py
```

### Build executable

Two distributions available:

#### Portable (single `.exe`)

One self-contained file, no installation required.

```bash
python -m PyInstaller audiobook_manager_onefile.spec -y
```

Output: `dist/AudiobookManager-portable.exe`

#### Windows Installer

Installs to `Program Files`, Start Menu shortcut, uninstaller registered with Windows.  
Requires [Inno Setup](https://jrsoftware.org/isinfo.php).

```bash
python -m PyInstaller audiobook_manager.spec -y
iscc audiobook_manager_setup.iss
```

Output: `dist/AudiobookManager-Setup.exe`

> FFmpeg is bundled in both distributions — no dependencies for the end user.  
> The FFmpeg path in the `.spec` (`FFMPEG_BIN`) must point to a gyan.dev **full** build (required for `libfdk_aac`).

---

## License

Personal project — no redistribution intended.

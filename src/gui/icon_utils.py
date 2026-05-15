"""
Chargement d'icônes ICO depuis assets/icons/.
Les fichiers ICO embarquent plusieurs résolutions (16/32/48/64) avec padding
uniforme, donc aucun trim runtime nécessaire.
"""
import os
import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QSize

if hasattr(sys, '_MEIPASS'):
    _ICONS_DIR = os.path.join(sys._MEIPASS, 'assets', 'icons')
else:
    _ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               '..', '..', 'assets', 'icons')

EMOJI_ICON: dict[str, str] = {
    "💾": "Sauvegarder.ico",
    "⚡": "Conversion.ico",
    "⬇": "importation.ico",
    "📥": "fetch.ico",
    "📤": "upload.ico",
    "📂": "folder.ico",
    "📦": "exportation.ico",
    "🎵": "Mp3.ico",
    "🏷": "Tags.ico",
    "▶": "Lancer.ico",
    "◀": "Précédent.ico",
    "↺": "Réinitialiser.ico",
    "↻": "Update.ico",
    "✕": "Annuler.ico",
    "🗑": "Vider.ico",
    "⛓": "Fusionner.ico",
    "✂": "Défusionner.ico",
    "✎": "Modifier.ico",
    "✓": "OK.ico",
    "✗": "Erreur.ico",
    "○": "En-attente.ico",
    "⟳": "En-cours.ico",
    "⚠": "Avertissement.ico",
    "▾": "Menu-déroulant.ico",
    "⊞": "Vue-catalogue.ico",
    "♪": "notes.ico",
    "…": "folder.ico",
}

_cache: dict[str, QIcon] = {}


def get_icon(filename: str) -> QIcon:
    """Charge et retourne un QIcon depuis assets/icons/."""
    if filename in _cache:
        return _cache[filename]
    path = os.path.join(_ICONS_DIR, filename)
    icon = QIcon(path) if os.path.exists(path) else QIcon()
    _cache[filename] = icon
    return icon


def icon_for(emoji: str) -> QIcon:
    """Retourne le QIcon correspondant à un emoji (via EMOJI_ICON)."""
    fname = EMOJI_ICON.get(emoji, "")
    return get_icon(fname) if fname else QIcon()

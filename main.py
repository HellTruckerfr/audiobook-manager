import sys
import os

# When running as a PyInstaller bundle, add bundled ffmpeg/ffprobe to PATH
# and resolve base_dir to the folder containing the exe (not the temp _MEIPASS)
if hasattr(sys, '_MEIPASS'):
    _bin = os.path.join(sys._MEIPASS, 'bin')
    os.environ['PATH'] = _bin + os.pathsep + os.environ.get('PATH', '')
    _exe_dir = os.path.dirname(sys.executable)
    # Si le dossier de l'exe n'est pas accessible en écriture (ex. Program Files),
    # on stocke la config dans %APPDATA%\AudiobookManager
    _test = os.path.join(_exe_dir, '.write_test')
    try:
        with open(_test, 'w') as _f:
            _f.write('')
        os.remove(_test)
        _base_dir = _exe_dir
    except OSError:
        _base_dir = os.path.join(os.environ.get('APPDATA', _exe_dir), 'AudiobookManager')
        os.makedirs(_base_dir, exist_ok=True)
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    _base_dir = os.path.dirname(os.path.abspath(__file__))

from src.gui.app import AudiobookManagerApp


def main():
    app = AudiobookManagerApp(_base_dir)
    app.run()


if __name__ == "__main__":
    main()

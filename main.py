import sys
import os

# When running as a PyInstaller bundle, add bundled ffmpeg/ffprobe to PATH
# and resolve base_dir to the folder containing the exe (not the temp _MEIPASS)
if hasattr(sys, '_MEIPASS'):
    _bin = os.path.join(sys._MEIPASS, 'bin')
    os.environ['PATH'] = _bin + os.pathsep + os.environ.get('PATH', '')
    _base_dir = os.path.dirname(sys.executable)
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    _base_dir = os.path.dirname(os.path.abspath(__file__))

from src.gui.app import AudiobookManagerApp


def main():
    app = AudiobookManagerApp(_base_dir)
    app.run()


if __name__ == "__main__":
    main()

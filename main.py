import time
import sys
from pathlib import Path
from datetime import date
import re
ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]|\r')
class Tee:
    def __init__(self, stream, file):
        self.stream = stream
        self.file = file

    def write(self, data):
        self.stream.write(data)
        self.file.write(ANSI.sub('', data))
        self.file.flush()          

    def flush(self):
        self.stream.flush()
        self.file.flush()

    def isatty(self):
        return self.stream.isatty()

    def fileno(self):
        return self.stream.fileno()
def start_logging(log_dir=Path("data","logs")):
    Path(log_dir).mkdir(exist_ok=True)
    name = date.today().isoformat() + ".log"
    f = open(Path(log_dir) / name, "a", encoding="utf-8", buffering=1)
    sys.stdout = Tee(sys.__stdout__, f)
    sys.stderr = Tee(sys.__stderr__, f)  
    return f
log_file = start_logging()
t=time.time()
print('Starting...')
PYDEVD_DISABLE_FILE_VALIDATION=1
def load(msg):
    sys.stdout.write(f'\r\033[K{msg}')
    sys.stdout.flush()





print(f'------------------ loading 3rd party libs:  ----------------------')
print('', end='')

load('importing IPython'); from IPython.terminal.embed import InteractiveShellEmbed
load('importing QApplication'); from PySide6.QtWidgets import QApplication
from PySide6.QtCore import qInstallMessageHandler

def qt_handler(mode, context, message):
    print(f"[Qt] {message}")

qInstallMessageHandler(qt_handler)

from Python.app.ui.main_window import MainWindow


if __name__ == "__main__":
    print(f'Launching app. Startup time: {time.time()-t:.3f} s')
    app = QApplication(sys.argv)
    app.setStyle("Oxygen")
    window = MainWindow()
    window.show()
    
    shell = InteractiveShellEmbed(banner1="",banner2="",display_banner = False)
    shell.enable_gui('qt')  
    shell(local_ns={"app": app, "main": window})
    

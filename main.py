import time
import sys

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
    

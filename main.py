import time
t=time.time()
print('Starting...',time.time()-t)
import sys
PYDEVD_DISABLE_FILE_VALIDATION=1
from IPython.terminal.embed import InteractiveShellEmbed
print('InteractiveShellEmbed...',time.time()-t)
from PySide6.QtWidgets import QApplication
print('QApplication...',time.time()-t)
from Python.app.ui.main_window import MainWindow
print('MainWindow...',time.time()-t)


if __name__ == "__main__":
    print(f'Launching app. Startup time: {time.time()-t:.3f} s')
    app = QApplication(sys.argv)
    app.setStyle("Oxygen")
    window = MainWindow()
    window.show()
    
    shell = InteractiveShellEmbed(banner1="",banner2="",display_banner = False)
    shell.enable_gui('qt')  
    shell(local_ns={"app": app, "main": window})
    

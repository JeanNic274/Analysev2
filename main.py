import time
t=time.time()
print('Starting...')
import sys
from PySide6.QtWidgets import QApplication
from Python.app.ui.main_window import MainWindow

if __name__ == "__main__":
    print(f'Launching app. Startup time: {time.time()-t:.3f} s')
    app = QApplication(sys.argv)
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec())

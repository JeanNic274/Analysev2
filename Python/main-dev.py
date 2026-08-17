import sys
from pwreloader import ReloaderWindow, start_reloaders
from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow

if __name__ == '__main__':
    print('Starting app in dev mode.')
    start_reloaders([ReloaderWindow(MainWindow,10,check_sub_modules=True, reload_sub_modules=True)])
    print('Closing app.')
    # app = QApplication(sys.argv)
    # window = MainWindow()
    # window.showMaximized()
    # sys.exit(app.exec())
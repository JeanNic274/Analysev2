import sys
from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow

if __name__ == "__main__":
    print('Starting app.')
    app = QApplication(sys.argv)
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec())
    print('Closing app.')

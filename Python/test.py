import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout
from app.ui.sidebar import Sidebar
from app.Plotting.line import SpectrumPlot
from app.Processing.data_import import Data_Set_Import


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spectrum Viewer")
        self.resize(1200, 800)

        self.selected_files = []
        self.datasets = {}

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self.sidebar = Sidebar(self)

        # for testing, create spectrum directly
        self.plot_area = type('obj', (object,), {})()  # dummy object
        self.spectrum = SpectrumPlot(self)
        self.plot_area.spectrum = self.spectrum

        layout.addWidget(self.sidebar)
        layout.addWidget(self.spectrum)

    def add(self, filepath, dataset):
        self.spectrum.add(filepath, dataset)

    def remove(self, filepath, dataset):
        self.spectrum.remove(filepath)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
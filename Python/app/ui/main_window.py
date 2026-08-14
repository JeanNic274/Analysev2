from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout
from app.ui.sidebar import Sidebar
from app.ui.toolbar import Toolbar
from app.ui.plot_area import PlotArea


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("My App")
        self.resize(1200, 800)

        self.selected_files = []
        self.datasets = {}
        self.fit_results = {}

        central = QWidget()
        self.setCentralWidget(central)
        self.layout = QHBoxLayout(central)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.sidebar = Sidebar(self)
        self.plot_area = PlotArea(self)  # add when ready
        self.toolbar = Toolbar(self)  # add when ready

        self.layout.addWidget(self.sidebar)
        self.layout.addWidget(self.plot_area)
        self.layout.addWidget(self.toolbar)
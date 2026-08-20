import time
t=time.time()
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout
print('---------------- imported QtWidgets',time.time()-t,' --------------------')
t=time.time()
from app.ui.sidebar import Sidebar
print('---------------- imported sidebar',time.time()-t,' --------------------')
t=time.time()
from app.ui.toolbar import Toolbar
print('---------------- imported toolbar',time.time()-t,' --------------------')
from app.ui.plot_area import PlotArea
print('---------------- imported PlotArea',time.time()-t,' --------------------')

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PL ViewerV2")
        # self.resize(1200, 800)

        self.selected_files = []
        self.datasets = {}
        self.fit_results = {}

        central = QWidget()
        self.setCentralWidget(central)
        self.layout = QHBoxLayout(central)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.sidebar = Sidebar(self)
        self.plot_area = PlotArea(self)  
        self.toolbar = Toolbar(self)  

        self.layout.addWidget(self.sidebar)
        self.layout.addWidget(self.plot_area)
        self.layout.addWidget(self.toolbar)#
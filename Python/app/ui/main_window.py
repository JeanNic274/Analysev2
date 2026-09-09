import time
t=time.time()
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout
print(f'---------------- imported QtWidgets:{time.time()-t:.8f} --------------------')
t=time.time()
from app.ui.sidebar import Sidebar
print(f'---------------- imported sidebar:  {time.time()-t:.8f} --------------------')
t=time.time()
from app.ui.toolbar import Toolbar
print(f'---------------- imported toolbar:  {time.time()-t:.8f} --------------------')
from app.ui.plot_area import PlotArea
print(f'---------------- imported PlotArea: {time.time()-t:.8f} --------------------')

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PL ViewerV2")
        # self.resize(1200, 800)

        self.save_folder = r"C:\Users\jnich\OneDrive - USherbrooke\Uni\PhD\Data\img\26_08_13-i"

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
        self.layout.addWidget(self.toolbar)
                
    def closeEvent(self, event):
        print(f'Closing app. Runtime: {time.time()-t:.3f} s')
        event.accept()
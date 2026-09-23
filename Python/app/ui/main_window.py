import time
t=time.time()
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QStackedWidget, QPushButton, QApplication, QSplitter
from PySide6.QtGui import QGuiApplication, Qt
print(f'---------------- imported Pyside6:  {time.time()-t:.8f} --------------------')
t=time.time()
from app.ui.sidebar import SidebarView, SidebarMeasure
print(f'---------------- imported sidebar:  {time.time()-t:.8f} --------------------')
t=time.time()
from app.ui.toolbar import Toolbar
print(f'---------------- imported toolbar:  {time.time()-t:.8f} --------------------')
from app.ui.plot_area import PlotAreas
print(f'---------------- imported PlotArea: {time.time()-t:.8f} --------------------')
t=time.time()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PL ViewerV2")
        # self.resize(1200, 800)

        self.save_folder = r"C:\Users\jnich\OneDrive - USherbrooke\Uni\PhD\Data\img\26_08_13-i"

        self.selected_files = {}
        self.datasets = {}
        self.fit_results = {}

        self.measurement_mode_on = False
        self.spectrometer_graph = None
        
        self.graph_windows = {}

        central = QWidget()
        self.setCentralWidget(central)
        self.main_layout = QHBoxLayout(central)
        self.layout = QSplitter(Qt.Horizontal)
        # self.layout.setContentsMargins(0, 0, 0, 0)

        self.sidebar = QStackedWidget()
        # if QGuiApplication.primaryScreen().size().toTuple()[0] >1500:
        #     self.sidebar.setFixedWidth(300)
        #     # print("SB size: 300")
        # else:
        #     # print("SB size: 225")
        #     self.sidebar.setFixedWidth(225)
        self.sidebar_view = SidebarView(self)
        self.sidebar_measure = SidebarMeasure(self)
        
        self.sidebar.addWidget(self.sidebar_view)  # index 0
        self.sidebar.addWidget(self.sidebar_measure) 
        
        self.plot_areas = PlotAreas(self)  
        self.toolbar = Toolbar(self)  

        self.plot_area = self.plot_areas.currentWidget()
        self.plot_area_index = str(self.plot_areas.currentIndex())

        self.layout.addWidget(self.sidebar)
        self.layout.addWidget(self.plot_areas)
        self.layout.addWidget(self.toolbar)
        self.layout.setSizes([250, 800,200])  # pixel widths, sidebar, plot area, toolbar
        self.main_layout.addWidget(self.layout)
                
    def closeEvent(self, event):
        print(f'Closing app. Runtime: {time.time()-t:.3f} s')
        QApplication.closeAllWindows()
        event.accept()
        
    def start_measurement_mode(self):
        print("_MMode WIP")
        # ------------ imports for measurement mode ------------
        from app.ui.graphs import SpectrometerGraph
        
        if not self.measurement_mode_on:
            btn_meas = QPushButton("Lab Scan")
            btn_meas.clicked.connect(self.swap_sidebars)
            self.sidebar_view.top_layout.addWidget(btn_meas)
            self.measurement_mode_on = True
            
            self.sidebar.setCurrentIndex(1) 
            
        # ----- Spectrometer 
        if self.spectrometer_graph is None:
            self.spectrometer_graph = SpectrometerGraph(self,480,1)
            self.spectrometer_graph.show()



    
    def swap_sidebars(self):
        self.sidebar.setCurrentIndex((self.sidebar.currentIndex()+1)%2) 
            
            
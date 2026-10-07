import time
t=time.time()

import numpy
import lmfit
import matplotlib

from pathlib import Path
import os, signal

from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QStackedWidget, QPushButton, QApplication, QSplitter, QVBoxLayout, QDockWidget
from PySide6.QtGui import QGuiApplication, Qt
from PySide6.QtCore import QSettings, QObject, Signal
print(f'---------------- imported libraries:  {time.time()-t:.8f} --------------------')
t=time.time()
from Python.app.ui.sidebar import SidebarView, SidebarMeasure
print(f'---------------- imported sidebar:  {time.time()-t:.8f} --------------------')
t=time.time()
from Python.app.ui.toolbar import Toolbar
print(f'---------------- imported toolbar:  {time.time()-t:.8f} --------------------')
from Python.app.ui.plot_area import PlotAreas
print(f'---------------- imported PlotArea: {time.time()-t:.8f} --------------------')
from Python.app.Measurements.Fake_instruments import *
from Python.app.ui.graphs import SpectrometerGraph

t=time.time()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PL ViewerV2")
        # self.resize(1200, 800)
        
        self.settings = QSettings("JN","AnalyseV2-MainWindow")
        self.save_folder=Path(self.settings.value("save_folder",r"C:"))

        self.selected_files = {}
        self.datasets = {}
        self.fit_results = {}

        self.measurement_mode_on = False
        # Device graphs
        self.graph_spectrometer = None
        self.graph_rate_graph = None
        self.graphs_scan=[]
        
        #Devices
        self.device_spectrometer = None
        self.device_MH150 = None
        self.device_laser = None
        self.device_nanopositionner = None
        self.device_ESP300 = None
        self.graph_windows = {}

        central = QWidget()
        self.setCentralWidget(central)
        self.main_layout = QHBoxLayout(central)
        self.layout = QSplitter(Qt.Horizontal)

        self.dock_sidebar = DockedSidebar(self)
        self.sidebar = QStackedWidget()
        
        self.sidebar_view = SidebarView(self)
        self.sidebar_measure = SidebarMeasure(self)
        
        self.sidebar.addWidget(self.sidebar_view)  # index 0
        self.sidebar.addWidget(self.sidebar_measure) 
        
        self.dock_sidebar.setWidget(self.sidebar)
        
        self.plot_areas = PlotAreas(self)  
        self.toolbar = Toolbar(self)  

        self.plot_area = self.plot_areas.currentWidget()
        self.plot_area_index = str(self.plot_areas.currentIndex())

        self.addDockWidget(Qt.LeftDockWidgetArea,self.dock_sidebar)
        self.layout.addWidget(self.plot_areas)
        self.layout.addWidget(self.toolbar)
        # self.layout.setSizes([150, 800,100])  # default pixel widths, sidebar, plot area, toolbar
        self.main_layout.addWidget(self.layout)
        self._restore_geometry()

    def _restore_geometry(self):
        geometry = self.settings.value("window_geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1200, 800)
            
        splitter_size = self.settings.value("splitter_sizes")
        if splitter_size is not None:
            self.layout.restoreState(self.settings.value("splitter_sizes"))


    def closeEvent(self, event):
        print(f'Closing Python.app. Runtime: {time.time()-t:.3f} s')
        self.settings.setValue("window_geometry", self.saveGeometry())
        self.settings.setValue("splitter_sizes", self.layout.saveState())
        QApplication.closeAllWindows()
        super().closeEvent(event)
        os.kill(os.getpid(), signal.SIGINT)
        
    def start_measurement_mode(self):
        # ------------ imports for measurement mode ------------
        
        if not self.measurement_mode_on:
            btn_meas = QPushButton("Lab Scan")
            btn_meas.clicked.connect(self.swap_sidebars)
            self.sidebar_view.top_layout.addWidget(btn_meas)
            self.measurement_mode_on = True
            
            self.sidebar.setCurrentIndex(1) 
            
        # ----- Spectrometer 
        # if self.graph_spectrometer is None:
        #     self.graph_spectrometer = SpectrometerGraph(self)
        #     self.graph_spectrometer.show()
            
        if self.device_spectrometer == None:
            self.device_spectrometer = Fake_spectrometer()
            
        # ----- MultiHarp
        if self.device_MH150 == None:
            self.device_MH150 = Fake_MH150()
            
        # ----- Laser
        if self.device_laser == None:
            self.device_laser = Fake_laser()
            
        # ----- Fake_NanoPositionner
        if self.device_nanopositionner == None:
            self.device_nanopositionner = Fake_NanoPositionner()
            
        # ----- Fake_ESP300
        if self.device_ESP300 == None:
            self.device_ESP300 = Fake_ESP300()



    def swap_sidebars(self):
        self.sidebar.setCurrentIndex((self.sidebar.currentIndex()+1)%2) 
            
    
    
class DockedSidebar(QDockWidget):
    def __init__(self,main_window):
        super().__init__('Sidebar')
        self.main = main_window
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        # self.btn_dock_toggle = QPushButton()
        # self.btn_dock_toggle.clicked.connect(self._toggle_dock)
        
        # self.setTitleBarWidget(self.btn_dock_toggle)
        
    def _toggle_dock(self):
        if self.isFloating():
            self.setFloating(False)
        else:
            self.setFloating(True)
            
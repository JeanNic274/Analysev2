# import numpy as np
from sys import float_info
import os

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QSizePolicy, QInputDialog
from PySide6.QtCore import QSize, QSettings

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from matplotlib import ticker

from app.Plotting.utils import *
from app.Processing.data_import import Data_Set_Import
from app.Processing.io import prevent_overwrite_file, save_figure_export, save_fit
from app.ui.DialogWindow import FitManager

plt.rcParams.update({
    "font.size": 16,
    "legend.fontsize": 11,
})

class BasePlot(QWidget):
    def __init__(self, main_window, buttons = [],xlim = None,yaxis = None, xaxis = None, title = "",ylab = "", xlab = ""):
        super().__init__()
        self.main = main_window


        self.buttons = buttons

        self.vlines = []
        self.hlines = []


        self.title = title
        self.xlim = xlim
        self.ylim = None
        self.xlab = xlab
        self.ylab = ylab
        self.xaxis = xaxis
        self.yaxis = yaxis


        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setSizePolicy(sizePolicy)

        self._build()

    def _build(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # -----------------
        # Left: button panel
        # -----------------
        button_layout = QVBoxLayout()
        button_layout.setContentsMargins(4, 4, 4, 4)
        button_layout.setSpacing(5)
        if True:
            btn_get_info = QPushButton("Get Info")
            btn_get_info.setFixedWidth(100)
            btn_get_info.clicked.connect(self._get_info)
            button_layout.addWidget(btn_get_info)
        if 'axvline' in self.buttons:
            btn_axvline = QPushButton("Ax V Line")
            btn_axvline.clicked.connect(self.axvline)
            button_layout.addWidget(btn_axvline)
        if 'axhline' in self.buttons:
            btn_axhline = QPushButton("Ax H Line")
            btn_axhline.clicked.connect(self.axhline)
            button_layout.addWidget(btn_axhline)

        button_layout.addStretch()

        # -----------------
        # Middle: matplotlib
        # -----------------
        graph_layout = QVBoxLayout()

        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.canvas.mpl_connect("button_press_event",self._on_plot_double_click)
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.ax = self.figure.add_subplot(111)
        self.ax.margins(0,0.01)
    
        self.gen_axis() 
        
        self.figure.set_layout_engine('tight')
        
        #--------------------------------------------------------#
        
        graph_layout.addWidget(self.toolbar)
        graph_layout.addWidget(self.canvas)

        main_layout.addLayout(button_layout)
        main_layout.addLayout(graph_layout, 1)
            
    def _get_info(self):
        text, ok = QInputDialog.getText(self,"Info", "Enter attribute name")
        if not ok:
            return
        obj = self
        for attr in text.split("."):
            obj = getattr(obj, attr)
        print(attr,obj)
        

    def axhline(self):
        text, ok = QInputDialog.getText(self,"AxHLine", "Enter y coordinates separated by commas:")

        if not ok:
            return

        # Remove existing lines
        for line in self.hlines:
            line.remove()

        self.hlines.clear()

        if not text.strip():
            self._refresh()
            return

        try:
            y_values = [
                float(y.strip())
                for y in text.split(',')
                if y.strip()
            ]
        except ValueError:
            return
        for y in y_values:
            self.hlines.append(self.ax.axhline(y,color='k',alpha=0.7,zorder=-10))
        self._refresh()     
         
    def axvline(self):
        text, ok = QInputDialog.getText(self,"AxVLine", "Enter x coordinates separated by commas:")

        if not ok:
            return

        # Remove existing lines
        for line in self.vlines:
            line.remove()

        self.vlines.clear()

        if not text.strip():
            self._refresh()
            return

        try:
            x_values = [
                float(x.strip())
                for x in text.split(',')
                if x.strip()
            ]
        except ValueError:
            return
        for x in x_values:
            self.vlines.append(self.ax.axvline(x,color='k',alpha=0.7,zorder=-10))
        self._refresh()      

    def _on_plot_double_click(self, event):
        if event.dblclick and event.inaxes == self.ax:
            text, ok = QInputDialog.getText(self,"Add Text","Enter text:")

            if not ok or not text:
                return
            self.toggles['annotations'].append([event.xdata,event.ydata,text])
            self.ax.text(event.xdata,event.ydata,text)
            self.canvas.draw_idle()
            

    def _refresh(self):
        self.ax.relim()
        # if not self.xlim:
        #     self.ax.autoscale(enable=True, axis='x')
        # if not self.ylim:
        #     self.ax.autoscale(enable=True, axis='y')
        self.ax.autoscale_view()
        self.canvas.draw()
        self.canvas.flush_events()

  
    def update_data(self,data):
        self.line.set_ydata(data[self.yaxis])
        self.line.set_xdata(data[self.xaxis])
        
    def gen_axis(self):
        self.ax.set_ylabel(self.ylab)
        self.ax.set_xlabel(self.xlab)
        self.line = self.ax.plot([self.xlim[0],self.xlim[1]],[-1,-1],color='k')
        self.ax.set_ylim(0,10)
        self._refresh()
        
        
            


class SpectrometerGraph(QWidget):
    def __init__(self,main_window, wavelength = None, grating = None):
        super().__init__()
        self.main = main_window
        self.setWindowTitle('Spectrometer')
        self.settings = {"wavelength":wavelength, 'grating': grating}
        
        self.settings_path = os.path.join('data','settings', "settingsFileSpectrometerGraph.ini")
        
        if os.path.exists(self.settings_path):
            settings_obj = QSettings(self.settings_path, QSettings.IniFormat)
            self.restoreGeometry(settings_obj.value("windowGeometry"))
            
        self.launch()


        
    def launch(self): 
        layout = QVBoxLayout(self)
        
        buttons = [ 'axvline', 'axhline']
        yaxis = 'count'
        xlim = (420,550)
        xlab,ylab = ('Wavelength (nm)', 'Counts')
        self.graph = BasePlot(self,buttons = buttons, yaxis = yaxis, xlim = xlim, ylab = ylab, xlab = xlab)
        
        
        self.graph._refresh()
        
        layout.addWidget(self.graph)
        
    
    def closeEvent(self, event):
        settings_obj = QSettings(self.settings_path, QSettings.IniFormat)
        settings_obj.setValue("windowGeometry", self.saveGeometry())
        self.main.spectrometer_graph = None
        event.accept()
        
        

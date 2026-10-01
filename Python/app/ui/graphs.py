# import numpy as np
from sys import float_info
import os
import time

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QSizePolicy, QInputDialog, QLabel, QFrame
from PySide6.QtCore import QSize, QSettings

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from matplotlib import ticker

from Python.app.Plotting.utils import *
from Python.app.Processing.data_import import Data_Set_Import
from Python.app.Processing.io import prevent_overwrite_file, save_figure_export, save_fit
from Python.app.ui.DialogWindow import FitManager
from Python.app.Plotting.map import MultiSlider, build_colormap_from_handles

plt.rcParams.update({
    "font.size": 16,
    "legend.fontsize": 11,
})

class BasePlot(QWidget):
    def __init__(self, main_window, buttons = [],xlim = None,yaxis = None, xaxis = None, title = "",ylab = "", xlab = "",n_lines = 1):
        super().__init__()
        self.main = main_window

        self.start_time = time.time()
        self.paused = False
        self.pause_started_at = None
        self.total_paused_duration = 0.0
        
        self.buttons = buttons

        self.vlines = []
        self.hlines = []

        self.color = ['red','blue','orange']
        self.title = title
        self.xlim = xlim
        self.ylim = None
        self.xlab = xlab
        self.ylab = ylab
        self.xaxis = xaxis
        self.yaxis = yaxis
        self.n_lines = n_lines
        

        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setSizePolicy(sizePolicy)

        self._build()

    def _build(self):
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # -----------------
        # Left: button panel
        # -----------------
        self.button_layout = QVBoxLayout()
        self.button_layout.setContentsMargins(5, 10, 5, 10)
        self.button_layout.setSpacing(5)
        if True:
            btn_get_info = QPushButton("Get Info")
            btn_get_info.setMinimumWidth(100)
            btn_get_info.clicked.connect(self._get_info)
            self.button_layout.addWidget(btn_get_info)
        if 'axvline' in self.buttons:
            btn_axvline = QPushButton("Ax V Line")
            btn_axvline.clicked.connect(self.axvline)
            self.button_layout.addWidget(btn_axvline)
        if 'axhline' in self.buttons:
            btn_axhline = QPushButton("Ax H Line")
            btn_axhline.clicked.connect(self.axhline)
            self.button_layout.addWidget(btn_axhline)
        if 'clear' in self.buttons:
            btn_clear = QPushButton("Clear")
            btn_clear.clicked.connect(self.clear_plot)
            self.button_layout.addWidget(btn_clear)

        self.button_layout.addStretch()

        # -----------------
        # Middle: matplotlib
        # -----------------
        graph_layout = QVBoxLayout()
        with plt.style.context('dark_background'):
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

        self.main_layout.addLayout(self.button_layout)
        self.main_layout.addLayout(graph_layout, 1)
            
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
            self.hlines.append(self.ax.axhline(y,color='yellow',alpha=0.7,zorder=-10))
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
            self.vlines.append(self.ax.axvline(x,color='yellow',alpha=0.7,zorder=-10))
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
        self.ax.autoscale(enable=True, axis='x')
        # if not self.ylim:
        self.ax.autoscale(enable=True, axis='y')
        self.ax.autoscale_view()
        self.canvas.draw()
        self.canvas.flush_events()

  
    def add_data(self,ydatas=[]):
        t = time.time() - self.start_time - self.total_paused_duration
        for line,ydata in zip(self.lines,ydatas):
            line.set_data(np.append(line.get_xdata(),t),np.append(line.get_ydata(),ydata))
        self._refresh()
        
    def update_data(self,xdatas=None,ydatas=None):
        if ydatas is not None:
            for line,ydata in zip(self.lines,ydatas):
                line.set_ydata(ydata)
        if xdatas is not None:
            for line,xdata in zip(self.lines,xdatas):
                line.set_xdata(xdata)
        self._refresh()
        
    def gen_axis(self):
        self.lines = []
        self.ax.set_ylabel(self.ylab)
        self.ax.set_xlabel(self.xlab)
        self.ax.set_ylim(0,10)
        for idx,_ in enumerate(range(self.n_lines)):
            line, = self.ax.plot([],[],color=self.color[idx])
            self.lines.append(line)
            
    def clear_plot(self):
        for line in self.lines:
            line.set_data([],[])
        self._refresh()
        
    def pause(self):
        if not self.paused:
            self.paused = True
            self.pause_started_at = time.time()

    def resume(self):
        if self.paused:
            self.paused = False
            self.total_paused_duration += time.time() - self.pause_started_at
            self.pause_started_at = None
        
        


class BaseMap(QWidget):
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

        self.data_min = np.inf
        self.data_max = -np.inf

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

        graph_layout = QVBoxLayout()
        with plt.style.context('dark_background'):
            self.figure = Figure()
            self.canvas = FigureCanvas(self.figure)
            self.canvas.mpl_connect("button_press_event",self._on_plot_double_click)
            self.toolbar = NavigationToolbar(self.canvas, self)
            self.ax = self.figure.add_subplot(111)
            self.ax.margins(0,0.01)
    
            self.gen_axis() 
        
            self.figure.set_layout_engine('tight')
            self._bg = self.canvas.copy_from_bbox(self.ax.bbox) 
            
            
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
            self.hlines.append(self.ax.axhline(y,color='yellow',alpha=0.7,zorder=-10))
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
            self.vlines.append(self.ax.axvline(x,color='yellow',alpha=0.7,zorder=-10))
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
        self.ax.autoscale_view()
        self.canvas.draw()
        self.canvas.flush_events()

  
    def update_data(self, data,new_value):
        self.image.set_data(data)

        if new_value is not None and not np.isnan(new_value):
            if self.data_min is None or new_value < self.data_min:
                self.data_min = new_value
                self.image.set_clim(vmin=self.data_min, vmax=self.data_max)
            if self.data_max is None or new_value > self.data_max:
                self.data_max = new_value
                self.image.set_clim(vmin=self.data_min, vmax=self.data_max)
        self.canvas.draw_idle()
                
    def _apply_shared_clim(self):
        for mesh in self.lines.values():
            mesh.set_clim(vmin=self.minimum, vmax=self.maximum)
        self.canvas.draw_idle()
        

    def slider_changed(self,values_dict):
        if len(values_dict) < 2:
            return  # need at least 2 stops for a valid gradient

        sorted_items = sorted(values_dict.items(), key=lambda kv: kv[1])
        handle_min = sorted_items[0][1]
        handle_max = sorted_items[-1][1]

        cmap, vmin, vmax = build_colormap_from_handles(
            values_dict,
            vmin=handle_min,
            vmax=handle_max
        )

        for mesh in self.lines.values():
            mesh.set_cmap(cmap)
            mesh.set_clim(vmin=vmin, vmax=vmax)

        if self.colorbar is not None and self.lines:
            self.colorbar.update_normal(next(iter(self.lines.values())))

        self.canvas.draw_idle()
        

            


class SpectrometerGraph(QWidget):
    def __init__(self,main_window):
        super().__init__()
        self.main = main_window
        self.setWindowTitle('Spectrometer')
        
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
        
    def update_val(self,val):
        self.graph.update_data(xdatas=[val[0]],ydatas=[val[1]])
        
    def closeEvent(self, event):
        settings_obj = QSettings(self.settings_path, QSettings.IniFormat)
        settings_obj.setValue("windowGeometry", self.saveGeometry())
        self.main.graph_spectrometer = None
        event.accept()
        
        
        
class RateGraph(QWidget):
    def __init__(self,main_window):
        super().__init__()
        self.main = main_window
        self.setWindowTitle('Rate Graph')
        
        self.settings_path = os.path.join('data','settings', "settingsFileRateGraph.ini")
        
        self.values = {'Ch1. Count: ':0,'Ch1. Max: ':0,'Ch2. Count: ':0,'Ch2. Max: ':0,'Delta: ':0}
        self.added_widgets = {}
        
        
        if os.path.exists(self.settings_path):
            settings_obj = QSettings(self.settings_path, QSettings.IniFormat)
            self.restoreGeometry(settings_obj.value("windowGeometry"))
            
        self.launch()

    def launch(self): 
        layout = QVBoxLayout(self)
        
        buttons = [ 'axvline', 'axhline', 'clear']
        yaxis = 'count'
        xlim = (420,550)
        xlab,ylab = ('Time (s)', 'Counts')
        self.graph = BasePlot(self,buttons = buttons, yaxis = yaxis, xlim = xlim, ylab = ylab, xlab = xlab,n_lines = 3)
        
        self.graph.lines[0].set_label('Ch. 1')
        self.graph.lines[1].set_label('Ch. 2')
        self.graph.lines[2].set_label('Total')
        self.graph.ax.legend(loc= 'upper left')
        
        font = QtGui.QFont()
        font.setPointSize(14)
        skip=True
        for k,v in self.values.items():
            label = QLabel(k+f" {v}")
            label.setFrameShape(QFrame.StyledPanel)
            label.setFixedHeight(35)
            label.setFont(font)
            self.graph.button_layout.addWidget(label)
            self.added_widgets[k] = label
            if not skip:
                line =  QFrame()
                line.setFrameShape(QFrame.HLine)
                # line.setFrameShadow(QFrame.Sunken)
                line.setStyleSheet(" border: 5px solid white ")
                self.graph.button_layout.addWidget(line)
                skip=True
            else:
                skip=False
            
        
        self.label_ratio = QLabel('Ratio: '+f" {0}")
        self.label_ratio.setFrameShape(QFrame.StyledPanel)
        self.label_ratio.setFixedWidth(180)
        self.label_ratio.setFixedHeight(35)
        self.label_ratio.setFont(font)
        self.graph.button_layout.addWidget(self.label_ratio)
        
        self.graph._refresh()
        
        layout.addWidget(self.graph)
        
    def _update(self):
        for k,v in self.values.items():
            self.added_widgets[k].setText(k+f" {v:,}")
        self.label_ratio.setText('Ratio: '+f"{self.values['Ch1. Count: ']/self.values['Ch2. Count: ']:.3g}")
                
        
        
    def add_data(self,value):
        self.values['Ch1. Max: '] = max(value[0],self.values['Ch1. Max: '])
        self.values['Ch2. Max: '] = max(value[1],self.values['Ch2. Max: '])
        self.values['Ch1. Count: '] = value[0]
        self.values['Ch2. Count: '] = value[1]
        self.values['Delta: '] = value[1]-value[0]
        self.graph.add_data(ydatas = value)
        self._update()
        
    def closeEvent(self, event):
        settings_obj = QSettings(self.settings_path, QSettings.IniFormat)
        settings_obj.setValue("windowGeometry", self.saveGeometry())
        self.main.graph_rate_graph = None
        self.main.UI_MH150.btn_rate_graph.setChecked(False)
        event.accept()
        
        
class ScanPlot(BaseMap):
    def __init__(self,main_window):
        self.buttons = [ 'axvline', 'axhline', 'clear']
        self.x_lab = "x (μm)"
        self.y_lab = "y (μm)"
        self.z_lab = "Counts/s"
        
        super().__init__(main_window)
        
        self.xaxis = 'x'
        self.yaxis = 'y'
        self.zaxis = 'count'


    def gen_axis(self):
        self.image = self.ax.imshow([[1,1],[1,1]], cmap='viridis', origin='lower')
        self.ax.set_aspect('equal')
        self.ax.set_ylabel(self.y_lab)
        self.ax.set_xlabel(self.x_lab)
        # self.ax.xaxis.set_major_locator(plt.MaxNLocator(9))
        # self.ax.yaxis.set_major_locator(plt.MaxNLocator(9))


import numpy as np
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton
from PySide6.QtCore import QSize
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from app.Plotting.utils import *

class SpectrumPlot(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.lines = {} 
        self.original_y = {}
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

        btn_normalize = QPushButton("Normalize")
        btn_normalize.setFixedWidth(100)
        btn_normalize.clicked.connect(self.normalize)
        btn2 = QPushButton("Button 2")
        btn3 = QPushButton("Button 3")

        button_layout.addWidget(btn_normalize)
        button_layout.addWidget(btn2)
        button_layout.addWidget(btn3)
        button_layout.addStretch()

        # -----------------
        # Right: matplotlib
        # -----------------
        graph_layout = QVBoxLayout()

        self.figure = Figure(figsize=(8, 4))
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.ax = self.figure.add_subplot(111)

        self.ax.set_xlabel("Wavelength (nm)")
        self.ax.set_ylabel("Intensity (a.u.)")
        self.ax.set_title("Spectrum")

        graph_layout.addWidget(self.toolbar)
        graph_layout.addWidget(self.canvas)

        # Add both sides
        main_layout.addLayout(button_layout)
        main_layout.addLayout(graph_layout, 1)
        
    def add(self, filepath, dataset):
        xaxis='nm'
        yaxis='count_cor'
        label = filepath.replace("\\", "/").split("/")[-1]
        line, = self.ax.plot(dataset.data[xaxis], dataset.data[yaxis], label=label)
        self.lines[filepath] = line
        self.original_y[filepath] = dataset.data[yaxis].copy()
        self._refresh()

    def remove(self, filepath):
        if filepath in self.lines:
            self.lines[filepath].remove()
            del self.lines[filepath]
        self._refresh()

    def normalize(self):
        normalize_lines(self.lines,self.original_y)
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw()

    def _refresh(self):
        if self.lines:
            self.ax.legend()
        else:
            self.ax.legend().remove() if self.ax.get_legend() else None
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw()
        
        
        
        
        
        
        
        
        
        
        

class TRPLPlot(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.lines = {}   # { filepath: Line2D }
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.figure = Figure(figsize=(8, 4))
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.ax = self.figure.add_subplot(111)

        self.ax.set_xlabel("Wavelength (nm)")
        self.ax.set_ylabel("Intensity (a.u.)")
        self.ax.set_title("Spectrum")

        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

    def add(self, filepath, dataset):
        xaxis='ns'
        yaxis='count'
        label = filepath.replace("\\", "/").split("/")[-1]
        line, = self.ax.plot(dataset.data[xaxis], dataset.data[yaxis], label=label)
        self.lines[filepath] = line
        self._refresh()

    def remove(self, filepath):
        if filepath in self.lines:
            self.lines[filepath].remove()
            del self.lines[filepath]
        self._refresh()

    def toggle_log(self):
        current = self.ax.get_yscale()
        self.ax.set_yscale("linear" if current == "log" else "log")
        self.canvas.draw()

    def normalize(self):
        for filepath, line in self.lines.items():
            y = line.get_ydata()
            if y.max() != 0:
                line.set_ydata(y / y.max())
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw()

    def _refresh(self):
        if self.lines:
            self.ax.legend()
        else:
            self.ax.legend().remove() if self.ax.get_legend() else None
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw()
        
        
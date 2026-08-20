

import numpy as np
from sys import float_info


from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QSizePolicy, QInputDialog
from PySide6.QtCore import QSize

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from matplotlib import ticker

from app.Plotting.utils import *

plt.rcParams.update({
    "font.size": 16,
    "legend.fontsize": 11,
})

class SpectrumPlot(QWidget):
    def __init__(self, main_window):
        self.xaxis='nm'
        self.xaxisev='ev'
        self.yaxis='count_cor'
        self.x_lab="Wavelength (nm)"
        self.y_lab="Counts/s"
        self.xlim=None
        self.ylim=None
        self.title=0
        self.groups={str(i): [] for i in range(5)}
        self.datasets={}
        self.vlines=[]
        self.hlines=[]
        self.colors = plt.rcParams['axes.prop_cycle'].by_key()['color']
        self.available_colors = list(self.colors)
        self.used_colors = {}
        super().__init__()
        self.main = main_window
        self.lines = {} 
        self.original_d = {}
        self.aspect_ratio = 0.7  # height / width
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setSizePolicy(sizePolicy)
        self._build()
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = event.size().width()
        h = int(w * self.aspect_ratio)
        if w>1000:
            right_margin = int(w*0.15)
        else:
            right_margin = 0
        self.layout().setContentsMargins(int(0.3*right_margin), 0, right_margin, 0)
        usable_w = w - right_margin
        h = int(usable_w * self.aspect_ratio)
        if h > 0 and self.height() != h:
            self.setFixedHeight(h)
            
    # def sizeHint(self):
    #     return QSize(800,600)
    # def heightForWidth(self, width):
    #     return width * 0.75
    
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
        btn_ev_nm_swap = QPushButton("eV/nm")
        btn_ev_nm_swap.clicked.connect(self.ev_nm_swap)
        btn_title = QPushButton("Set Title")
        btn_title.clicked.connect(self.set_title)
        btn_xlim = QPushButton("Set x lim")
        btn_xlim.clicked.connect(self.set_xlim)
        btn_ylim = QPushButton("Set y lim")
        btn_ylim.clicked.connect(self.set_ylim)
        btn_axvline = QPushButton("Ax V Line")
        btn_axvline.clicked.connect(self.axvline)
        btn_axhline = QPushButton("Ax H Line")
        btn_axhline.clicked.connect(self.axhline)


        button_layout.addWidget(btn_normalize)
        button_layout.addWidget(btn_ev_nm_swap)
        button_layout.addWidget(btn_title)
        button_layout.addWidget(btn_xlim)
        button_layout.addWidget(btn_ylim)
        button_layout.addWidget(btn_axvline)
        button_layout.addWidget(btn_axhline)
        button_layout.addStretch()

        # -----------------
        # Middle: matplotlib
        # -----------------
        graph_layout = QVBoxLayout()

        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.ax = self.figure.add_subplot(111)
        self.ax.margins(0,0.01)
    
        self.gen_axis() 
        
        self.figure.set_layout_engine('tight')
        
        
        # -----------------
        # Right: margin
        # -----------------
        # margin_layout = QVBoxLayout()
        # margin_layout.setContentsMargins(4, 4, 4, 4)
        # margin_layout.setSpacing(5)
        # margin_layout.addStretch(100)
        
        #--------------------------------------------------------#
        
        graph_layout.addWidget(self.toolbar)
        graph_layout.addWidget(self.canvas)

        # Add layouts
        main_layout.addLayout(button_layout)
        main_layout.addLayout(graph_layout, 1)
        # main_layout.addLayout(margin_layout)
        
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

    def normalize(self):
        normalize_lines(self.lines,self.original_d,xlim=self.xlim,xaxis=self.xaxis,yaxis=self.yaxis)
        self._refresh()
        
    def set_title(self):
        title, ok = QInputDialog.getText(self, 'Title', 'Enter title, if multiple attributes, separate with a comma.')
        if title and ok:
            set_fig_title(self.figure,title,[*self.datasets.values()][0])
            self._refresh()
               
    def set_xlim(self):
        self.xlim, ok = QInputDialog.getText(self, 'Set x axis limits', 'Enter x axis limits, seperated by comma. \nLeave a side empty for no change.')
        if self.xlim and ok:
            set_ax_lim(self.ax,self.xlim,x=True)
        self._refresh()         
        self.xlim=self.ax.get_xlim()   
         
    def set_ylim(self):
        self.ylim, ok = QInputDialog.getText(self, 'Set y axis limits', 'Enter y axis limits, seperated by comma. \nLeave a side empty for no change.')
        if self.ylim and ok:
            set_ax_lim(self.ax,self.ylim,y=True)
        self._refresh() 
        self.ylim=self.ax.get_ylim() 
        
    def y_offset(self):
        return

    def _refresh(self):
        if self.lines:
            self.ax.legend()
        else:
            self.ax.legend().remove() if self.ax.get_legend() else None
        self.ax.relim()
        if not self.xlim:
            self.ax.autoscale(enable=True, axis='x')
        if not self.ylim:
            self.ax.autoscale(enable=True, axis='y')
        self.ax.autoscale_view()
        self.canvas.draw()
        self.canvas.flush_events()
        
    def nm_to_ev(self,wl):
        """Converts wavelength in nm to eV and inverse.

        Args:
            wl (_type_): Wavelength in nm (eV).

        Returns:
            _type_: Wavelength in eV (nm).
        """
        
        ev = 1239.8 / (wl+float_info.epsilon)    
        return ev
        
    def ev_nm_swap(self):
        print('swaping')
        
        evnm_swap(self.lines)
        
        if self.xaxis=='ev':
                self.xaxis='nm'
        elif self.xaxis=='nm':
                self.xaxis='ev'
                
        self.swap_axis()
            
        self._refresh()
    
    def gen_axis(self):     
        if self.xaxis=='nm':
                self.ax_ev = self.ax.secondary_xaxis('top', functions=(self.nm_to_ev, self.nm_to_ev))
                self.ax_ev.set_xlabel("Energy (eV)")
                self.ax.set_xlabel("Wavelength (nm)")
                self.ax_ev.invert_xaxis()
                # wl_ticks = ax.get_xticks()
                # wl_ticks = preventDivisionByZero(wl_ticks)
                # E_ticks = nm_to_ev(wl_ticks)
                # ax_ev.set_xticks(E_ticks)
                self.ax.xaxis.set_minor_locator(ticker.MultipleLocator(5))
                self.ax_ev.xaxis.set_minor_locator(ticker.MultipleLocator(0.02))
                # ax_ev.xaxis.set_major_formatter(FormatStrFormatter('%.2f'))

        if self.xaxis=='ev':
                self.ax_ev = self.ax.secondary_xaxis('top', functions=(self.nm_to_ev, self.nm_to_ev))
                self.ax.set_xlabel("Energy (eV)")
                self.ax_ev.set_xlabel("Wavelength (nm)")
                self.ax_ev.invert_xaxis()
                self.ax_ev.xaxis.set_minor_locator(ticker.MultipleLocator(5))
                self.ax.xaxis.set_minor_locator(ticker.MultipleLocator(0.02))
    
    def swap_axis(self):     
        if self.xaxis=='nm':
                self.ax_ev.set_xlabel("Energy (eV)")
                self.ax.set_xlabel("Wavelength (nm)")
                self.ax_ev.invert_xaxis()
                self.ax.xaxis.set_minor_locator(ticker.MultipleLocator(5))
                self.ax_ev.xaxis.set_minor_locator(ticker.MultipleLocator(0.02))

        if self.xaxis=='ev':
                self.ax.set_xlabel("Energy (eV)")
                self.ax_ev.set_xlabel("Wavelength (nm)")
                self.ax_ev.invert_xaxis()
                self.ax_ev.xaxis.set_minor_locator(ticker.MultipleLocator(5))
                self.ax.xaxis.set_minor_locator(ticker.MultipleLocator(0.02))
        
    def add(self, filepath, dataset):
        if not self.available_colors:
            # Reuse colors after cycle
            self.available_colors = list(self.colors)
            
        color = self.available_colors.pop(0)
        self.datasets[filepath]=dataset
        label = filepath.replace("\\", "/").split("/")[-1]
        label = dataset.number +', ' + dataset.name
        line, = self.ax.plot(dataset.data[self.xaxis], dataset.data[self.yaxis],color=color, label=label)
        self.lines[filepath] = line
        self.used_colors[filepath] = color
        self.original_d[filepath] = dataset.data.copy()
        self._refresh()
        print(self.groups)

    def remove(self, filepath):
        if filepath not in self.lines:
            return

        self.lines[filepath].remove()

        color = self.used_colors.pop(filepath)
        self.available_colors.insert(0, color)

        del self.lines[filepath]
        self._refresh()
    
        
    def update_groups(self):
        # Remove existing plotted group lines
        for line in self.lines.values():
            line.remove()

        self.lines.clear()

        # Plot each non-empty group
        for group_id, filepaths in self.groups.items():

            if not filepaths:
                continue

            datasets = []

            for filepath in filepaths:
                if filepath in self.main.datasets:
                    datasets.append(self.main.datasets[filepath].data)

            if not datasets:
                continue

            # Merge the files in this group
            merged = merge_spectra(
                datasets,
                # axis=col_merged['spectrum']
            )

            if merged is None:
                continue

            # Choose the y column you want
            x = merged[self.xaxis]
            y = merged[self.yaxis]

            line, = self.ax.plot(
                x,
                y,
                label=str(group_id)
            )

            self.lines[group_id] = line

        self._refresh()
        
        
        
        
    
        
        
        

class TRPLPlot(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.lines = {}   # { filepath: Line2D }
        sizePolicy = QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        sizePolicy.setHeightForWidth(True)
        self.setSizePolicy(sizePolicy)
        self._build()
        
    def sizeHint(self):
        return QSize(1200,800)
    def heightForWidth(self, width):
        return width * 0.75

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
        
        
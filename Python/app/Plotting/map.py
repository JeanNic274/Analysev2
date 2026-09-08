import numpy as np
import matplotlib
matplotlib.use("QtAgg")  # PySide6 works with the QtAgg backend

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.colors as mcolors
from matplotlib.patches import Circle

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QSizePolicy, QInputDialog, QLabel
from PySide6.QtCore import QSize

from app.Plotting.utils import *
from app.Processing.data_import import Data_Set_Import
import app.Plotting.cmaps

class BaseMap(QWidget):
    def __init__(self, main_window):
        super().__init__()

        self.main = main_window

        self.lines = {}
        self.datasets = {}
        self.original_d = {}

        self.cbars = {}          # NEW: one InteractiveColorbar per filepath
        self.active_cbar = None  

        self.vlines = []
        self.hlines = []
        self.annotations = []

        self.xaxis = None
        self.yaxis = None
        self.zaxis = None
        self.xlim = None
        self.ylim = None


        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setSizePolicy(sizePolicy)
        self.aspect_ratio = 0.7

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
        # self.buttons = ['normalize', 'ev_swap', 'set_title', 'set_xlim', 'set_ylim', 'axvline', 'axhline', 'set y axis', 'set y_offset']
        if 'normalize' in self.buttons:
            btn_normalize = QPushButton("Normalize")
            btn_normalize.setFixedWidth(100)
            btn_normalize.clicked.connect(self.normalize)
            button_layout.addWidget(btn_normalize)
        if 'set_title' in self.buttons:
            btn_title = QPushButton("Set Title")
            btn_title.clicked.connect(self.set_title)
            button_layout.addWidget(btn_title)
        if 'set_xlim' in self.buttons:
            btn_xlim = QPushButton("Set x lim")
            btn_xlim.clicked.connect(self.set_xlim)
            button_layout.addWidget(btn_xlim)
        if 'set_ylim' in self.buttons:
            btn_ylim = QPushButton("Set y lim")
            btn_ylim.clicked.connect(self.set_ylim)
            button_layout.addWidget(btn_ylim)
        if 'axvline' in self.buttons:
            btn_axvline = QPushButton("Ax V Line")
            btn_axvline.clicked.connect(self.axvline)
            button_layout.addWidget(btn_axvline)
        if 'axhline' in self.buttons:
            btn_axhline = QPushButton("Ax H Line")
            btn_axhline.clicked.connect(self.axhline)
            button_layout.addWidget(btn_axhline)
        if 'set y axis' in self.buttons:
            btn_yaxis_select = QPushButton("Set y axis")
            btn_yaxis_select.clicked.connect(self.yaxis_select)
            button_layout.addWidget(btn_yaxis_select)
        if 'cmap' in self.buttons:
            btn_cmap = QPushButton("cmap")
            btn_cmap.clicked.connect(self.cmap_change)
            button_layout.addWidget(btn_cmap)

        button_layout.addStretch()

        graph_layout = QVBoxLayout()

        self.fig = Figure()
        self.canvas = FigureCanvas(self.fig)
        self.canvas.mpl_connect("button_press_event", self._on_plot_double_click)

        self.canvas.mpl_connect("button_press_event", self._on_cbar_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_cbar_motion)
        self.canvas.mpl_connect("button_release_event", self._on_cbar_release)

        self.toolbar = NavigationToolbar(self.canvas, self)

        gs = self.fig.add_gridspec(1, 42, wspace=0,hspace=0)
        self.ax = self.fig.add_subplot(gs[0, :34])
        self.ax_strip = self.fig.add_subplot(gs[0, 35:38])
        self.ax.margins(0,0.05)
    
        self.gen_axis() 
        
        
        graph_layout.addWidget(self.toolbar)
        graph_layout.addWidget(self.canvas)

        # Add layouts
        main_layout.addLayout(button_layout)
        main_layout.addLayout(graph_layout, 1)
        # main_layout.addLayout(margin_layout)
        
        
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


    def _on_cbar_press(self, event):
        if self.active_cbar is not None:
            self.active_cbar.on_press(event)

    def _on_cbar_motion(self, event):
        if self.active_cbar is not None:
            self.active_cbar.on_motion(event)
            self.canvas.draw_idle()

    def _on_cbar_release(self, event):
        if self.active_cbar is not None:
            self.active_cbar.on_release(event)

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
            self.hlines.append(self.ax.axhline(y,color='k',alpha=0.7,zorder=10))
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
            self.vlines.append(self.ax.axvline(x,color='k',alpha=0.7,zorder=10))
        self._refresh()      

    def normalize(self):
        self.toggles['normalize']=(self.toggles['normalize']+1)%2
        print('WIP _normalize')
        self._refresh()
        
    def set_title(self):
        title, ok = QInputDialog.getText(self, 'Title', 'Enter title, if multiple attributes, separate with a comma.')
        if title and ok:
            set_fig_title(self.fig,title,[*self.datasets.values()][0])
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


    def yaxis_select(self):
        yaxis, ok = QInputDialog.getText(self, 'Set y axis', 'Enter y axis name.')
        if yaxis and ok:
            self.yaxis = yaxis
        self._refresh() 
        
    def cmap_change(self):
        cmap, ok = QInputDialog.getText(self, 'Set cmap', 'Enter colormap name (ex: viridis, gist_rainbow_r, turbo, jet, CustomLC).')
        if cmap and ok:
            for filepath in self.datasets:
                self.datasets[filepath].cmap = cmap
        self._refresh_cmap() 

    def _on_plot_double_click(self, event):
        if event.dblclick and event.inaxes == self.ax:
            text, ok = QInputDialog.getText(self,"Add Text","Enter text:")

            if not ok or not text:
                return
            self.toggles['annotations'].append([event.xdata,event.ydata,text])
            self.ax.text(event.xdata,event.ydata,text)
            self.canvas.draw_idle()


    def _refresh(self):
        if not self.xlim:
            self.ax.autoscale(enable=True, axis='x')
        if not self.ylim:
            self.ax.autoscale(enable=True, axis='y')
        self.ax.autoscale_view()
        self.canvas.draw()
        self.canvas.flush_events()
        
    def _refresh_cmap(self):
        filepath = list(self.lines.keys())[-1]
        dataset = self.datasets[filepath]
        self.remove(filepath,refresh=False)
        self.add(filepath,dataset)
        self._refresh()
        

    def add(self, filepath, dataset, plot_now = True):
        self.datasets[filepath]=dataset
        
        if plot_now:
            xu = np.unique(dataset.data[self.xaxis])
            yu = np.unique(dataset.data[self.yaxis])

            grid = np.zeros((len(yu), len(xu)))
            xi = np.searchsorted(xu, dataset.data[self.xaxis])
            yi = np.searchsorted(yu, dataset.data[self.yaxis])
            grid[yi, xi] = dataset.data[self.zaxis]
            pcolormesh = self.ax.pcolormesh(xu,yu,grid, cmap=dataset.cmap,antialiased=False,edgecolor='none', linewidth=0)
            self.lines[filepath] = pcolormesh
            self.original_d[filepath] = dataset.data.copy()
            cbar = InteractiveColorbar(
                self.ax_strip, pcolormesh, dataset.data[self.zaxis],
                dataset.cmap, label=self.z_lab
            )
            self.cbars[filepath] = cbar
            self.active_cbar = cbar
            
            self._refresh()

    def remove(self, filepath, refresh=True):
        if filepath not in self.lines:
            return

        self.lines[filepath].remove()
        del self.lines[filepath]

        if filepath in self.cbars:
            if self.active_cbar is self.cbars[filepath]:
                self.active_cbar = None
            del self.cbars[filepath]

        if refresh:
            self._refresh()
            
    def remove_all(self):
        for filepath in self.lines.copy():
            self.main.plot_area.remove(filepath,self.datasets[filepath],refresh=False)
        self._refresh()
        
    def refresh_curves(self):
        for key, data in self.datasets.items():
            self.remove(key)
            self.add(key,data)
            
    def _refresh_full(self):
        self.refresh_curves()
        self._refresh_cmap()
        self._refresh()
        
    


class MapPlot(BaseMap):
    def __init__(self,main_window):
        self.buttons = ['normalize', 'set_title', 'set_xlim', 'set_ylim', 'axvline', 'axhline', 'set y axis', 'cmap']
        self.x_lab = "x (μm)"
        self.y_lab = "y (μm)"
        self.z_lab = "Counts/s"
        
        super().__init__(main_window)
        
        self.xaxis = 'x'
        self.yaxis = 'y'
        self.zaxis = 'count'

        self.toggles = {'normalize':0,'annotations':[],'circles':[]}

    def gen_axis(self):
        self.ax.set_aspect('equal')
        self.ax.set_ylabel(self.y_lab)
        self.ax.set_xlabel(self.x_lab)
        self.ax.xaxis.set_major_locator(plt.MaxNLocator(5))
        self.ax.yaxis.set_major_locator(plt.MaxNLocator(5))




class PiecewiseNorm(mcolors.Normalize):
    def __init__(self, stops, frac):
        self.stops = np.asarray(stops, dtype=float)
        self.frac = np.asarray(frac, dtype=float)
        super().__init__(vmin=self.stops[0], vmax=self.stops[-1], clip=True)

    def __call__(self, value, clip=None):
        data = np.ma.getdata(value) if np.ma.is_masked(value) else np.asarray(value)
        result = np.interp(data, self.stops, self.frac)
        return np.ma.masked_array(result)

    def inverse(self, value):
        return np.interp(value, self.frac, self.stops)

class InteractiveColorbar:
    def __init__(self, ax_strip, mappable, data, cmap, label=""):
        self.ax = ax_strip
        self.mappable = mappable
        if isinstance(cmap,str):
            self.cmap = matplotlib.colormaps[cmap] 
        else:
            self.cmap = cmap

        finite = data[np.isfinite(data)]
        self.vmin = float(finite.min()) if finite.size else 0.0
        self.vmax = float(finite.max()) if finite.size else 1.0
        if self.vmin == self.vmax:
            self.vmax = self.vmin + 1.0

        self.stops = [self.vmin, (self.vmin + self.vmax) / 2, self.vmax]
        self.frac = [0.0, 0.5, 1.0]
        self.norm = PiecewiseNorm(self.stops, self.frac)
        self.mappable.set_norm(self.norm)

        self.ax.clear()
        self.ax.set_ylim(self.vmin, self.vmax)   # value axis is now Y
        self.ax.set_xlim(0, 1)
        self.ax.set_xticks([])
        self.ax.yaxis.tick_right()
        self.ax.yaxis.set_label_position("right")
        self.ax.set_ylabel(label)

        self.strip_img = self.ax.imshow(
            self._strip_gradient(),
            aspect="auto",
            extent=[0, 1, self.vmin, self.vmax],
            origin="lower",
        )

        self.labels = ["low", "mid", "high"]
        self.markers = []
        self.value_texts = []
        for s, lbl in zip(self.stops, self.labels):
            c = Circle((0.5, s),radius=(self.vmax - self.vmin) * 0.015,color="k",zorder=5,picker=True,)
            
            self.ax.add_patch(c)
            self.markers.append(c)
            # self.ax.annotate(lbl, (1.5, s), ha="left", va="center",
            #                   fontsize=7, annotation_clip=False)
            t = self.ax.text(-0.6, s, "", ha="right", va="center")
            # t = self.ax.text(-0.6, s, f"{s:.2f}", ha="right", va="center", fontsize=7)
            self.value_texts.append(t)

        self._dragging_index = None

    def _strip_gradient(self):
        vals = np.linspace(self.vmin, self.vmax, 256)
        t = np.interp(vals, self.stops, self.frac)
        return self.cmap(t).reshape(-1, 1, 4)   # column instead of row

    def redraw(self):
        order = np.argsort(self.stops)
        self.norm.stops = np.asarray([self.stops[i] for i in order], dtype=float)
        self.norm.frac = np.asarray([self.frac[i] for i in order], dtype=float)

        self.mappable.set_norm(self.norm)
        self.strip_img.set_data(self._strip_gradient())

        for i, m in enumerate(self.markers):
            m.center = (0.5, self.stops[i])
            self.value_texts[i].set_position((-0.6, self.stops[i]))

    def on_press(self, event):
        if event.inaxes != self.ax:
            return
        for i, m in enumerate(self.markers):
            contains, _ = m.contains(event)
            if contains:
                self._dragging_index = i
                return

    def on_motion(self, event):
        i = self._dragging_index
        if i is None or event.inaxes != self.ax or event.ydata is None:
            return
        self.stops[i] = float(np.clip(event.ydata, self.vmin, self.vmax))  # ydata now
        self.redraw()

    def on_release(self, event):
        self._dragging_index = None

    def reset_stops(self):
        self.stops = [self.vmin, (self.vmin + self.vmax) / 2, self.vmax]
        self.frac = [0.0, 0.5, 1.0]
        self.redraw()
# import numpy as np
from sys import float_info


from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QSizePolicy, QInputDialog
from PySide6.QtCore import QSize

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from matplotlib import ticker

from app.Plotting.utils import *
from app.Processing.data_import import Data_Set_Import
from app.Processing.io import prevent_overwrite_file

plt.rcParams.update({
    "font.size": 16,
    "legend.fontsize": 11,
})

class BasePlot(QWidget):
    def __init__(self, main_window):
        super().__init__()

        self.main = main_window
        self.EXPORT_STYLE = {"width": 6.4,"height": 4.8,"dpi": 200,"font_size": 10,"legend_font_size": 9,}
        self.save_name = "temp"

        self.lines = {}
        self.datasets = {}
        self.original_d = {}

        self.vlines = []
        self.hlines = []

        self.colors = plt.rcParams['axes.prop_cycle'].by_key()['color']
        self.available_colors = list(self.colors)
        self.used_colors = {}

        self.title = ""
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
        if 'save' in self.buttons:
            btn_save = QPushButton("Save Graph")
            btn_save.setFixedWidth(100)
            btn_save.clicked.connect(self.save_graph)
            button_layout.addWidget(btn_save)
        if True:
            btn_legend = QPushButton("Legend")
            btn_legend.setFixedWidth(100)
            btn_legend.clicked.connect(self.legend_toggle)
            button_layout.addWidget(btn_legend)
        if 'normalize' in self.buttons:
            btn_normalize = QPushButton("Normalize")
            btn_normalize.setFixedWidth(100)
            btn_normalize.clicked.connect(self.normalize)
            button_layout.addWidget(btn_normalize)
        if 'ev_swap' in self.buttons:
            btn_ev_nm_swap = QPushButton("eV/nm")
            btn_ev_nm_swap.clicked.connect(self.ev_nm_swap)
            button_layout.addWidget(btn_ev_nm_swap)
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
        if 'set y_offset' in self.buttons:
            btn_y_offset = QPushButton("Set y offset")
            btn_y_offset.clicked.connect(self.set_y_offset)
            button_layout.addWidget(btn_y_offset)

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
        self.toggles['normalize']=(self.toggles['normalize']+1)%2
        normalize_lines(self.lines,self.original_d,xlim=self.xlim,xaxis=self.xaxis,yaxis=self.yaxis,toggle=self.toggles['normalize'])
        self._refresh()
        
    def set_title(self):
        title, ok = QInputDialog.getText(self, 'Title', 'Enter title, if multiple attributes, separate with a comma.')
        if title and ok:
            self.title = title
            set_fig_title(self.figure,self.title,[*self.datasets.values()][0])
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
        
    def set_y_offset(self):
        yoffset, ok = QInputDialog.getText(self, 'Set y axis offset', 'Enter value.')
        if yoffset == "":
            yoffset = 0
        if ok:
            self.toggles['yoffset'] = yoffset
            offset_lines(self,yoffset=self.toggles['yoffset'],xaxis=self.xaxis,yaxis=self.yaxis)
        self._refresh()

    def yaxis_select(self):
        yaxis, ok = QInputDialog.getText(self, 'Set y axis', 'Enter y axis name.')
        if yaxis and ok:
            self.yaxis = yaxis
        self._refresh() 
        
    def legend_toggle(self):
        if self.toggles['legend']:
            self.toggles['legend']=0
            self.ax.get_legend().remove()
        else:
            self.toggles['legend']=1
            self.ax.legend()
        self._refresh() 

    def _on_plot_double_click(self, event):
        if event.dblclick and event.inaxes == self.ax:
            text, ok = QInputDialog.getText(self,"Add Text","Enter text:")

            if not ok or not text:
                return
            self.toggles['annotations'].append([event.xdata,event.ydata,text])
            self.ax.text(event.xdata,event.ydata,text)
            self.canvas.draw_idle()
            
    def save_graph(self):
        filename, ok = QInputDialog.getText(self, 'Export graph', 'Enter file name.',text=self.save_name)
        if not ok:
            return
        prevent_overwrite_file(filename+'.png')
        save_figure_export(
            self.figure,
            filename,
            **self.EXPORT_STYLE
        )

    def _refresh(self):
        if self.lines:
            if self.toggles['legend']:
                self.ax.legend()
        else:
            self.ax.get_legend().remove() if self.ax.get_legend() else None
        self.ax.relim()
        if not self.xlim:
            self.ax.autoscale(enable=True, axis='x')
        if not self.ylim:
            self.ax.autoscale(enable=True, axis='y')
        self.ax.autoscale_view()
        self.canvas.draw()
        self.canvas.flush_events()

  
    def add(self, filepath, dataset, plot_now = True):
        if not self.available_colors:
            # Reuse colors after cycle
            self.available_colors = list(self.colors)
        
        color=self._get_color(filepath)
        # color = self.available_colors.pop(0)
        self.datasets[filepath]=dataset
        if plot_now:
            label = fetch_label(dataset,toggles=self.labels)
            norm_factor=1
            if self.toggles['normalize']:
                if self.xlim:
                    norm_factor =  dataset.data[self.yaxis][((dataset.data[self.xaxis] >= self.xlim[0]) &(dataset.data[self.xaxis] <= self.xlim[1]))].max()
                else:
                    norm_factor=dataset.data[self.yaxis].max()
            line, = self.ax.plot(dataset.data[self.xaxis]+dataset.x_offset, dataset.data[self.yaxis]/norm_factor, color=color, label=label)
            self.lines[filepath] = line
            # self.used_colors[filepath] = color
            self.original_d[filepath] = dataset.data.copy()
            self._refresh()

    def remove(self, filepath,refresh=True):
        if filepath not in self.lines:
            return

        self.lines[filepath].remove()

        color = self.used_colors.pop(filepath,None)
        self.available_colors.insert(0, color)

        del self.lines[filepath]
        if refresh:
            self._refresh()
            
    def remove_all(self):
        for filepath in self.lines.copy():
            self.main.plot_area.remove(filepath,self.datasets[filepath],refresh=False)
        self._refresh()
    
    def _get_color(self, key):
        if key not in self.used_colors:
            self.used_colors[key] = self.available_colors.pop(0)
        return self.used_colors[key]

    def refresh_labels(self):
        for key, line in self.lines.items():
            dataset = self.datasets.get(key)

            if dataset is None:
                continue

            line.set_label(
                fetch_label(dataset,toggles=self.labels)
            )

        self.ax.legend()
        self.canvas.draw_idle()
        
    def refresh_curves(self):
        for key, data in self.datasets.items():
            self.remove(key)
            self.add(key,data)
            
    def _refresh_full(self):
        self.refresh_curves()
        self._refresh()
        
    



class SpectrumPlot(BasePlot):
    def __init__(self, main_window):
        self.buttons = ['save','normalize', 'ev_swap', 'set_title', 'set_xlim', 'set_ylim', 'axvline', 'axhline', 'set y axis', 'set y_offset']
        self.xaxis = 'nm'
        self.yaxis = 'count_cor'
        super().__init__(main_window)


        self.x_lab = "Wavelength (nm)"
        self.y_lab = "Counts/s"

        self.labels = {'number': 1,'name': 1,'power': 0,'pos': 0,'posf': 0,'filter': 0,}
        self.groups = {str(i): [] for i in range(5)}
        self.toggles = {'normalize':0,'annotations':[],'yoffset':0,'legend':1}
        
            

        
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
        print('Swaping axis')
        
        evnm_swap(self.lines)
        
        if self.xaxis=='ev':
                self.xaxis='nm'
        elif self.xaxis=='nm':
                self.xaxis='ev'
                
        self.swap_axis()
            
        self._refresh()
    
    def gen_axis(self):   
        self.ax.set_ylabel('Counts/s')  
        if self.xaxis=='nm':
                self.ax_ev = self.ax.secondary_xaxis('top', functions=(self.nm_to_ev, self.nm_to_ev))

        if self.xaxis=='ev':
                self.ax_ev = self.ax.secondary_xaxis('top', functions=(self.nm_to_ev, self.nm_to_ev))
        self.swap_axis()
    
    def swap_axis(self):     
        if self.xaxis=='nm':
                self.ax_ev.set_xlabel("Energy (eV)")
                self.ax.set_xlabel("Wavelength (nm)")
                self.ax_ev.invert_xaxis()
                self.ax.xaxis.set_minor_locator(ticker.MultipleLocator(5))
                self.ax.xaxis.set_major_locator(plt.MaxNLocator(7))
                self.ax_ev.xaxis.set_minor_locator(ticker.MultipleLocator(0.02))
                self.ax_ev.xaxis.set_major_locator(plt.MaxNLocator(7))

        if self.xaxis=='ev':
                self.ax.set_xlabel("Energy (eV)")
                self.ax_ev.set_xlabel("Wavelength (nm)")
                self.ax_ev.invert_xaxis()
                self.ax_ev.xaxis.set_minor_locator(ticker.MultipleLocator(5))
                self.ax_ev.xaxis.set_major_locator(plt.MaxNLocator(7))
                self.ax.xaxis.set_minor_locator(ticker.MultipleLocator(0.02))
                self.ax.xaxis.set_major_locator(plt.MaxNLocator(7))
                
        
    def update_groups(self):
        for group_id, filepaths in reversed(self.groups.items()):
            if group_id in self.lines:
                self.remove(group_id,refresh=False)

            for filepath in reversed(filepaths):
                if filepath in self.main.datasets:
                    self.main.plot_area.remove(filepath,self.datasets[filepath],refresh=False,keep=True)
        for group_id, filepaths in self.groups.items():
            if not filepaths:
                continue

            datasets = []

            for filepath in reversed(filepaths):
                if filepath in self.main.datasets:
                    datasets.append(self.main.datasets[filepath])
                    self.main.datasets[filepath].number = str(int(group_id)+1)

            if not datasets:
                continue

            merged = merge_spectra(datasets)
            if merged is None:
                continue
            
            self.datasets[group_id] = Data_Set_Import(attrs=datasets[-1].attrs,dataset=merged,name=datasets[-1].name)
            self.datasets[group_id].number = group_id
            self.original_d[group_id] = self.datasets[group_id].data.copy()
            color=self._get_color(group_id)

            label = fetch_label(datasets[0],toggles=self.labels)
            line, = self.ax.plot(
                merged[self.xaxis],
                merged[self.yaxis],
                color=color,
                label=label,
            )

            self.lines[group_id] = line
        self._refresh()
    
    
        
        
        
    
        
        
    

class TRPLPlot(BasePlot):
    def __init__(self, main_window):
        self.buttons = ['save','normalize', 'set_title', 'set_xlim', 'set_ylim', 'axvline', 'axhline', 'set y axis']
        self.x_lab = "Time (ns)"
        self.y_lab = "Counts/s"
        self.xaxis = 'ns'
        self.yaxis = 'count'
        super().__init__(main_window)



        self.labels = {'number': 1,'name': 1,'power': 0,'pos': 0,'posf': 0,'filter': 0,}
        self.groups = {str(i): [] for i in range(5)}
        self.toggles = {'normalize':0,'annotations':[],'yoffset':0,'legend':1}
        
    def gen_axis(self):
        self.ax.set_yscale('log')
        self.ax.set_ylabel(self.y_lab)
        self.ax.set_xlabel(self.x_lab)
        
     

    
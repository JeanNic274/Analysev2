import numpy as np
import matplotlib
matplotlib.use("QtAgg")  # PySide6 works with the QtAgg backend

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from mpl_toolkits.axes_grid1 import make_axes_locatable
from matplotlib.figure import Figure
import matplotlib.colors as mcolors
from matplotlib.patches import Circle

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QSizePolicy, QInputDialog, QLabel, QColorDialog
from PySide6.QtCore import QSize, Qt, Signal, QRectF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QLinearGradient


from app.Plotting.utils import *
from app.Processing.data_import import Data_Set_Import
from app.Processing.io import prevent_overwrite_file, save_figure_export
import app.Plotting.cmaps

class BaseMap(QWidget):
    def __init__(self, main_window):
        super().__init__()

        self.main = main_window
        
        self.save_params = {'save_name':'temp','extension':'.png','transp':True}
        self.EXPORT_STYLE = {"width": 6.4,"height": 4.8,"dpi": 200,"font_size": 10,"legend_font_size": 9,}

        self.lines = {}
        self.datasets = {}
        self.original_d = {}

        self.colorbar = None
        self.maximum = None
        self.minimum = None
        
        
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

        button_layout = QVBoxLayout()
        button_layout.setContentsMargins(4, 4, 4, 4)
        button_layout.setSpacing(5)
        # self.buttons = ['normalize', 'ev_swap', 'set_title', 'set_xlim', 'set_ylim', 'axvline', 'axhline', 'set y axis', 'set y_offset']
        if True:
            btn_save = QPushButton("Save Graph")
            btn_save.setFixedWidth(100)
            btn_save.clicked.connect(self.save_graph)
            button_layout.addWidget(btn_save)
            btn_get_info = QPushButton("Get Info")
            btn_get_info.setFixedWidth(100)
            btn_get_info.clicked.connect(self._get_info)
            button_layout.addWidget(btn_get_info)
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
        # if 'cmap' in self.buttons:
        #     btn_cmap = QPushButton("cmap")
        #     btn_cmap.clicked.connect(self.cmap_change)
        #     button_layout.addWidget(btn_cmap)

        button_layout.addStretch()

        graph_layout = QVBoxLayout()

        self.fig = Figure()
        self.canvas = FigureCanvas(self.fig)
        self.canvas.mpl_connect("button_press_event", self._on_plot_double_click)

        self.toolbar = NavigationToolbar(self.canvas, self)

        self.ax = self.fig.add_subplot()
    
        self.gen_axis() 
        
        
        graph_layout.addWidget(self.toolbar)
        graph_layout.addWidget(self.canvas)

        # Add layouts
        main_layout.addLayout(button_layout)
        main_layout.addLayout(graph_layout, 1)
        
        self.slider_layout = QVBoxLayout()
        self.slider_layout.setContentsMargins(0,2,0,2)
        self.slider = MultiSlider()


        self.slider.valuesChanged.connect(self.slider_changed)

        self.slider_layout.addWidget(self.slider)
        main_layout.addLayout(self.slider_layout)
        # main_layout.addLayout(margin_layout)
        
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = event.size().width()
        h = int(w * self.aspect_ratio)
        if w>1000:
            right_margin = int(w*0.1)
        else:
            right_margin = 0
        self.layout().setContentsMargins(int(0.3*right_margin), 0, right_margin, 0)
        usable_w = w - right_margin
        h = int(usable_w * self.aspect_ratio)
        if h > 0 and self.height() != h:
            self.setFixedHeight(h)

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
        
    # def cmap_change(self):
    #     cmap, ok = QInputDialog.getText(self, 'Set cmap', 'Enter colormap name (ex: viridis, gist_rainbow_r, turbo, jet, CustomLC).')
    #     if cmap and ok:
    #         for filepath in self.datasets:
    #             self.datasets[filepath].cmap = cmap
    #     self._refresh_cmap() 
    
    
    def save_graph(self,skip_name=False):
        if not skip_name:
            filename, ok = QInputDialog.getText(self, 'Export graph', 'Enter file name.',text=self.save_params['save_name'])
            if not ok:
                return
            self.save_params['save_name'] = filename
            
        save_path = self.main.save_folder+"\\"+self.save_params['save_name']+self.save_params['extension']
        prevent_overwrite_file(save_path)
        save_figure_export(
            self.fig,
            save_path,
            self.save_params['transp'],
            **self.EXPORT_STYLE
        )



    def _on_plot_double_click(self, event):
        if event.dblclick and event.inaxes == self.ax:
            text, ok = QInputDialog.getText(self,"Add Text","Enter text:")

            if not ok or not text:
                return
            self.toggles['annotations'].append([event.xdata,event.ydata,text])
            self.ax.text(event.xdata,event.ydata,text)
            self.canvas.draw_idle()


    def _refresh(self):
        self.slider.setRange(self.minimum, self.maximum)
        self._apply_shared_clim()
        if self.lines:
            xs_min, xs_max, ys_min, ys_max = [], [], [], []
            for mesh in self.lines.values():
                coords = mesh.get_coordinates()  # shape (ny, nx, 2) — x,y grid corners
                xs_min.append(np.nanmin(coords[..., 0]))
                xs_max.append(np.nanmax(coords[..., 0]))
                ys_min.append(np.nanmin(coords[..., 1]))
                ys_max.append(np.nanmax(coords[..., 1]))

            self.ax.set_xlim(min(xs_min), max(xs_max))
            self.ax.set_ylim(min(ys_min), max(ys_max))
        else:
            self.ax.autoscale(enable=True, axis='both')

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
            self.original_d[filepath] = dataset.data.copy()
            xu = np.unique(dataset.data[self.xaxis])
            yu = np.unique(dataset.data[self.yaxis])

            grid = np.zeros((len(yu), len(xu)))
            xi = np.searchsorted(xu, dataset.data[self.xaxis])
            yi = np.searchsorted(yu, dataset.data[self.yaxis])
            grid[yi, xi] = dataset.data[self.zaxis]
            pcolormesh = self.ax.pcolormesh(
                xu, yu, grid,
                cmap=dataset.cmap,
                antialiased=False,
                edgecolor='none',
                linewidth=0
            )
            self.lines[filepath] = pcolormesh

            
            self._update_global_range(dataset)
            
            if self.colorbar is None:
                divider = make_axes_locatable(self.ax)
                cax = divider.append_axes("right", size="5%", pad=0.05)
                self.colorbar = self.fig.colorbar(pcolormesh, cax=cax)
                self.slider.setRange(self.minimum, self.maximum)
                self._apply_shared_clim()
            else:
                self.colorbar.update_normal(pcolormesh)
                
            self.slider.setValues({
                '#440154': self.minimum,
                '#21918c': self.minimum+0.5*(self.maximum-self.minimum),
                '#FDE725': self.maximum,
                
            })


            
            
            
            self._refresh()
            

    def _update_global_range(self, dataset):
        data_min = dataset.data[self.zaxis].min()
        data_max = dataset.data[self.zaxis].max()

        self.minimum = data_min if self.minimum is None else min(self.minimum, data_min)
        self.maximum = data_max if self.maximum is None else max(self.maximum, data_max)

    def _apply_shared_clim(self):
        for mesh in self.lines.values():
            mesh.set_clim(vmin=self.minimum, vmax=self.maximum)
        self.canvas.draw_idle()



    def remove(self, filepath, refresh=True):
        if filepath not in self.lines:
            return

        self.lines[filepath].remove()
        del self.lines[filepath]
        del self.datasets[filepath]
        if refresh:
            if self.datasets:
                self.minimum = min(d.data[self.zaxis].min() for d in self.datasets.values())
                self.maximum = max(d.data[self.zaxis].max() for d in self.datasets.values())
                self._apply_shared_clim()
                self._refresh()
            
    def remove_all(self,all_lines=False):
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





def build_colormap_from_handles(values_dict, vmin=None, vmax=None):
    sorted_items = sorted(values_dict.items(), key=lambda kv: kv[1])
    colors = [c for c, _ in sorted_items]
    positions = [p for _, p in sorted_items]

    lo = vmin if vmin is not None else positions[0]
    hi = vmax if vmax is not None else positions[-1]
    span = hi - lo
    if span == 0:
        span = 1e-9  # avoid div by zero

    stops = [(p - lo) / span for p in positions]
    stops[0], stops[-1] = 0.0, 1.0  

    normalized_colors = []
    for c in colors:
        if isinstance(c, str):
            normalized_colors.append(c)  # hex string, e.g. "#440154"
        else:
            # assume (r,g,b,a) in 0-255, convert to 0-1 floats
            normalized_colors.append(tuple(v / 255 for v in c))

    cmap = mcolors.LinearSegmentedColormap.from_list(
        "custom_slider_cmap",
        list(zip(stops, normalized_colors))
    )
    return cmap, lo, hi   
        
        
        

class MultiSlider(QWidget):
    valuesChanged = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._minimum = 0.0
        self._maximum = 100.0
        self._values = {}

        self._handle_radius = 7
        self._track_height = 4
        self._dragging = None
        
        self._show_labels = True
        self._label_gap = 6        # px between handle edge and text
        self._label_decimals = 0

        self.setMinimumHeight(30)
        self.setMinimumWidth(30)

        self.setSizePolicy(
            QSizePolicy.Fixed,
            QSizePolicy.Expanding
        )

        self.setMouseTracking(True)
    def sizeHint(self):
        return QSize(30 + self._label_width(), 200)

    def minimumSizeHint(self):
        return QSize(30 + self._label_width(), 60)
    
    
    def _v_margin(self):
        return self.height() * 0.15

    def _track_bounds(self):
        margin = self._v_margin()
        top = margin + self._handle_radius
        bottom = self.height() - margin - self._handle_radius
        return top, bottom
    
    def _format_value(self, value):
        return f"{value:.{self._label_decimals}f}"
    
    def _label_width(self):
        if not self._show_labels or not self._values:
            return 0
        fm = self.fontMetrics()
        widest = max(fm.horizontalAdvance(self._format_value(v)) for k,v in self._values.items()) 
        return self._label_gap + widest

    def _center_x(self):
        # centre the track within the space left of the label column
        usable = self.width() - self._label_width()
        return usable / 2
    
    def setRange(self, minimum, maximum):
        if maximum <= minimum:
            raise ValueError("maximum must be greater than minimum")

        self._minimum = minimum # 0.267004, 0.004874, 0.329415 
        self._maximum = maximum # 0.993248, 0.906157, 0.143936

        for k,v in self._values.items():
            self._values[k] = max(minimum, min(maximum, v))
            


        self.update()
        self.valuesChanged.emit(self.values())

    def setValues(self, values):
        for k,v in values.items():
            values[k] = max(self._minimum, min(self._maximum, float(v)))

        self._values = values
        self.update()
        self.valuesChanged.emit(self.values())

    def values(self):
        return self._values.copy()

    def addValue(self, value,color):
        value = max(self._minimum, min(self._maximum, float(value)))

        self._values[color]= value
        # self._values.sort()

        self.update()
        self.valuesChanged.emit(self.values())

    def removeValue(self, index):
        if index in self._values:
            self._values.pop(index)

            self.update()
            self.valuesChanged.emit(self.values())


    def _value_to_y(self, value):
        top, bottom = self._track_bounds()
        span = self._maximum - self._minimum
        if span == 0:
            return bottom
        frac = (value - self._minimum) / span
        return bottom - frac * (bottom - top)

    def _y_to_value(self, y):
        top, bottom = self._track_bounds()
        usable = bottom - top
        if usable <= 0:
            return self._minimum
        frac = (bottom - y) / usable
        frac = max(0.0, min(1.0, frac))
        return self._minimum + frac * (self._maximum - self._minimum)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        center_x = self._center_x()
        top, bottom = self._track_bounds()

        track_rect = QRectF(
            center_x - self._track_height / 2,
            top,
            self._track_height,
            bottom - top
        )

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(Qt.gray))
        painter.drawRoundedRect(
            track_rect,
            self._track_height / 2,
            self._track_height / 2
        )

        if len(self._values) >= 2:
            sorted_items = sorted(self._values.items(), key=lambda item: item[1])

            for i in range(len(sorted_items) - 1):
                color1, val1 = sorted_items[i]
                color2, val2 = sorted_items[i + 1]

                y1 = self._value_to_y(val1)
                y2 = self._value_to_y(val2)
                y_top, y_bottom = min(y1, y2), max(y1, y2)

                gradient = QLinearGradient(0, y_top, 0, y_bottom)
                # y1/y2 might be inverted relative to value order (since y grows downward
                # while value grows upward) so anchor stops by actual pixel position
                if y1 <= y2:
                    gradient.setColorAt(0, QColor(color1))
                    gradient.setColorAt(1, QColor(color2))
                else:
                    gradient.setColorAt(0, QColor(color2))
                    gradient.setColorAt(1, QColor(color1))

                painter.setBrush(QBrush(gradient))
                painter.setPen(Qt.NoPen)
                painter.drawRect(QRectF(
                    center_x - self._track_height / 2,
                    y_top,
                    self._track_height,
                    y_bottom - y_top
                ))

        painter.setFont(self.font())
        fm = painter.fontMetrics()

        for k,value in self._values.items():
            y = self._value_to_y(value)

            painter.setBrush(QBrush(Qt.white))
            painter.setPen(QPen(Qt.black, 1))
            painter.drawEllipse(QRectF(
                center_x - self._handle_radius,
                y - self._handle_radius,
                self._handle_radius * 2,
                self._handle_radius * 2
            ))

            if self._show_labels:
                text = self._format_value(value)
                text_w = fm.horizontalAdvance(text)
                text_h = fm.height()

                text_x = center_x + self._handle_radius + self._label_gap
                text_rect = QRectF(
                    text_x,
                    y - text_h / 2,
                    text_w,
                    text_h
                )

                painter.setPen(QPen(Qt.white))
                painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, text)

    def mousePressEvent(self, event):

        y = event.position().y()

        # Right click -> remove handle
        if event.button() == Qt.RightButton:

            index = self._handle_at(y)

            if index is not None:
                self.removeValue(index)

            return
        
        # Left click
        if event.button() == Qt.LeftButton:
            index = self._handle_at(y)

            if index is not None:
                self._dragging = index
                return

    def mouseDoubleClickEvent(self, event): #add handle

        y = event.position().y()
        color = QColorDialog.getColor()
        if color.isValid(): 
            color = color.name()
            value = self._y_to_value(y)
            self.addValue(value,color)


    def mouseMoveEvent(self, event):

        if self._dragging is None:
            return

        y = event.position().y()
        value = self._y_to_value(y)

        index = self._dragging

        # Don't allow handles to cross
        # if index > 0:
        #     value = max(value, self._values[index - 1])

        # if index < len(self._values) - 1:
        #     value = min(value, self._values[index + 1])

        self._values[index] = value

        self.update()
        self.valuesChanged.emit(self.values())

    def mouseReleaseEvent(self, event):

        if event.button() == Qt.LeftButton:
            self._dragging = None


    def _handle_at(self, y):

        tolerance = self._handle_radius + 5

        closest = None
        closest_distance = float("inf")

        for k,value in self._values.items():

            handle_y = self._value_to_y(value)
            distance = abs(y - handle_y)

            if distance <= tolerance and distance < closest_distance:
                closest = k
                closest_distance = distance

        return closest
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
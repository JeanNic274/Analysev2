from PySide6.QtWidgets import  QWidget, QVBoxLayout, QScrollArea, QLabel, QSizePolicy, QLayout
from PySide6.QtCore import Qt

from app.Plotting.line import SpectrumPlot, TRPLPlot, LinePlot, FocusPlot
from app.Plotting.map import MapPlot
from app.Processing.misc import curve_number

class PlotArea(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        
        
        self.spectrum   = None
        self.trpl       = None
        self.maps       = None
        self.lineplot   = None
        self.focus      = None
        
        self.manager = curve_number()
        
        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Preferred
        )
        self._build()

    def _build(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # Scroll area
        self.scroll = ScrollArea()
        self.scroll.setWidgetResizable(True)
        # self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Widget inside the scroll area
        self.container = QWidget()

        # Layout containing the plots
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(10)
        self.layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.container)
        self.container.setMinimumWidth(400)
        outer_layout.addWidget(self.scroll)

    def _get_or_create(self, plot_type,names = None):
        if plot_type == 'spectrum':
            if self.spectrum is None:
                self.spectrum = SpectrumPlot(self.main)
                self.spectrum.setObjectName("Spectrum")
                self.layout.addWidget(self.spectrum)
            
        elif plot_type == 'trpl':
            if self.trpl is None:
                self.trpl = TRPLPlot(self.main)
                self.trpl.setObjectName("TRPL")
                self.layout.addWidget(self.trpl)
            
        elif plot_type == 'maps':
            if self.maps is None:
                self.maps = MapPlot(self.main)
                self.maps.setObjectName("Map")
                self.layout.addWidget(self.maps)
            
        elif plot_type == 'focus':
            if self.focus is None:
                self.focus = FocusPlot(self.main)
                self.focus.setObjectName("Focus")
                self.layout.addWidget(self.focus)
            
            
        elif self.lineplot is None:
            self.lineplot = LinePlot(self.main,names)
            self.lineplot.setObjectName("Line")
            self.layout.addWidget(self.lineplot)
        self.layout.addStretch()
        
        
    def add(self, filepath, dataset,plot_now= True):
        self._get_or_create(dataset.measure_type,names = dataset.data.dtype.names)

        if dataset.measure_type == 'spectrum':
            self.spectrum.add(filepath, dataset, plot_now)
        elif dataset.measure_type == 'trpl':
            self.trpl.add(filepath, dataset, plot_now)
        elif dataset.measure_type == 'maps':
            self.maps.add(filepath, dataset, plot_now)
        elif dataset.measure_type == 'focus':
            self.focus.add(filepath, dataset, plot_now)
        else:
            self.lineplot.add(filepath, dataset, plot_now)

    def remove(self, filepath, dataset,refresh=True,keep=False):
        if dataset.measure_type == 'spectrum' and self.spectrum:
            self.spectrum.remove(filepath,refresh=refresh)
            if not self.spectrum.lines and not keep:  # destroy if empty
                self.layout.removeWidget(self.spectrum)
                self.spectrum.deleteLater()
                self.spectrum = None

        elif dataset.measure_type == 'trpl' and self.trpl:
            self.trpl.remove(filepath,refresh=refresh)
            if not self.trpl.lines:
                self.layout.removeWidget(self.trpl)
                self.trpl.deleteLater()
                self.trpl = None

        elif dataset.measure_type == 'maps' and self.maps:
            self.maps.remove(filepath,refresh=refresh)
            if not self.maps.lines:
                self.layout.removeWidget(self.maps)
                self.maps.deleteLater()
                self.maps = None
                
        elif dataset.measure_type == 'focus' and self.focus:
            self.focus.remove(filepath,refresh=refresh)
            if not self.focus.lines:
                self.layout.removeWidget(self.focus)
                self.focus.deleteLater()
                self.focus = None
                
        elif dataset.measure_type == 'line' and self.lineplot:
            self.lineplot.remove(filepath,refresh=refresh)
            if not self.lineplot.lines:
                self.layout.removeWidget(self.lineplot)
                self.lineplot.deleteLater()
                self.lineplot = None
        self.manager.remove(dataset)
                
    def remove_all(self):
        if self.spectrum:
            self.spectrum.remove_all(all_lines=True)
        if self.trpl:
            self.trpl.remove_all(all_lines=True)
        if self.maps:
            self.maps.remove_all(all_lines=True)
        if self.focus:
            self.focus.remove_all(all_lines=True)
        if self.lineplot:
            self.lineplot.remove_all(all_lines=True)
        self.clearLayout(self.layout)   
                 
    def clearLayout(self, layout):
        if isinstance(layout, QLayout):
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                else:
                    self.clearLayout(item.layout())


class ScrollArea(QScrollArea):
    def wheelEvent(self, event):
        bar = self.verticalScrollBar()

        delta = event.angleDelta().y()

        bar.setValue(bar.value() - delta)

        event.accept()
from PySide6.QtWidgets import  QWidget, QVBoxLayout, QScrollArea, QLabel, QSizePolicy
from PySide6.QtCore import Qt

from app.Plotting.line import SpectrumPlot, TRPLPlot
from app.Plotting.map import MapPlot


class PlotArea(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.spectrum = None
        self.trpl = None
        self.map = None
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

    def _get_or_create(self, plot_type):
        if plot_type == 'spectrum' and self.spectrum is None:
            self.spectrum = SpectrumPlot(self.main)
            self.layout.addWidget(self.spectrum)
            
        elif plot_type == 'trpl' and self.trpl is None:
            self.trpl = TRPLPlot(self.main)
            self.layout.addWidget(self.trpl)
            
        elif plot_type == 'maps' and self.map is None:
            self.map = MapPlot(self.main)
            self.layout.addWidget(self.map)
        self.layout.addStretch()
        
    def add(self, filepath, dataset):
        self._get_or_create(dataset.measure_type)

        if dataset.measure_type == 'spectrum':
            self.spectrum.add(filepath, dataset)
        elif dataset.measure_type == 'trpl':
            self.trpl.add(filepath, dataset)
        elif dataset.measure_type == 'maps':
            self.map.add(filepath, dataset)

    def remove(self, filepath, dataset,refresh=True,keep=False):
        if dataset.measure_type == 'spectrum' and self.spectrum:
            self.spectrum.remove(filepath,refresh=refresh)
            if not self.spectrum.lines and not keep:  # destroy if empty
                self.layout.removeWidget(self.spectrum)
                self.spectrum.deleteLater()
                self.spectrum = None

        elif dataset.measure_type == 'trpl' and self.trpl:
            self.trpl.remove(filepath)
            if not self.trpl.lines:
                self.layout.removeWidget(self.trpl)
                self.trpl.deleteLater()
                self.trpl = None

        elif dataset.measure_type == 'map' and self.map:
            self.map.remove(filepath)
            if not self.map.lines:
                self.layout.removeWidget(self.map)
                self.map.deleteLater()
                self.map = None
    def remove_all(self):
        if self.spectrum:
            self.spectrum.remove_all()
        if self.trpl:
            self.trpl.remove_all
        # self.maps.remove_all


class ScrollArea(QScrollArea):
    def wheelEvent(self, event):
        bar = self.verticalScrollBar()

        delta = event.angleDelta().y()

        bar.setValue(bar.value() - delta)

        event.accept()
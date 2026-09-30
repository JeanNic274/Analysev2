# import time
# t=time.time()
import itertools

import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QAbstractItemView,
    QLabel, QLineEdit, QTreeWidget, QTreeWidgetItem, QSizePolicy, QFileSystemModel, QFrame, QMessageBox
)
# print('imported QTWidget', time.time()-t)
# t=time.time()
from PySide6.QtCore import Qt, QDir, QSortFilterProxyModel, QSettings, QThread, QObject, Signal
from PySide6.QtGui import QBrush
# print('imported QtCore', time.time()-t)
# t=time.time()
from pathlib import Path
import subprocess
# print('imported re', time.time()-t)
# t=time.time()
# from config import DEFAULT_FOLDER, WHITELIST_EXTENSIONS
# print('imported config', time.time()-t)
# t=time.time()
from Python.app.Processing.data_import import Data_Set_Import
# print('imported Data_Set_Import', time.time()-t)
# t=time.time()
from Python.app.Processing.misc import  browse
# print('imported time.time()-t)

from pyHegel.pyHegel import commands
from Python.config import DEFAULT_FOLDER


class SidebarView(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.settings = QSettings("JN","AnalyseV2-Sidebar")
        self.path=Path(self.settings.value("last_folder",DEFAULT_FOLDER))
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setAlignment(Qt.AlignTop)

        # path input
        self.top_layout = QHBoxLayout()
        
        self.path_input = QLineEdit()
        self.path_input.setStyleSheet('font-size: 10pt;')
        self.path_input.setPlaceholderText("Enter path...")
        self.path_input.returnPressed.connect(self._set_path)
        self.top_layout.addWidget(QLabel("Browse Files"))
        
        
        
        layout.addLayout(self.top_layout)
        
        layout_top = QHBoxLayout()
        btn_refresh = QPushButton("⟳")
        btn_refresh.setFixedWidth(30)
        btn_refresh.clicked.connect(self.refresh_tree)
        layout_top.addWidget(btn_refresh)#
        layout_top.addWidget(self.path_input)#
        layout.addLayout(layout_top)
        
        layout_btn = QHBoxLayout()
        
        btn_return = QPushButton("  📁 ..")
        btn_return.setStyleSheet("text-align: left")
        btn_return.clicked.connect(self.return_folder)
        
        btn_meas = QPushButton("Open meas.txt")
        btn_meas.clicked.connect(self._open_meas)

        layout_btn.addWidget(btn_return)
        layout_btn.addWidget(btn_meas)
        layout.addLayout(layout_btn)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.NoSelection)
        self.tree.setStyleSheet("""font-size: 10pt;""")
        self.populate_tree(self.path)
        
        self.tree.itemClicked.connect(self._item_clicked)
        
        
        
        layout.addWidget(self.tree)

        # selected files label
        layout.addWidget(QLabel("Selected Files"))
        self.selected_label = QLabel("No files selected")
        self.selected_label.setWordWrap(True)
        self.selected_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(self.selected_label)

        # plot + clear buttons
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)

        clear_btn = QPushButton("✕")
        clear_btn.setFixedWidth(30)
        clear_btn.clicked.connect(self._clear_selection)

        btn_layout.addWidget(clear_btn)
        layout.addWidget(btn_row)
    
    def return_folder(self):
        self.populate_tree("")
    
    def refresh_tree(self):
        self.populate_tree(self.path)
    
    def populate_tree(self,path):
        if path:
            self.path=Path(path)
        else:
            self.path= self.path.parent
        files = browse(self.path)
        self.tree.clear()
        for file in files:
            item = QTreeWidgetItem([file['name']])
            item.setData(0,Qt.UserRole,file['path'])
            item.setData(0,Qt.UserRole+1,file['is_dir'])
            
            self.tree.addTopLevelItem(item)
            
    def _set_path(self):
        path = self.path_input.text()
        if QDir(path).exists():
            self.populate_tree(path)
            
    def _item_clicked(self, item):
        
        path = str(item.data(0, Qt.UserRole))
        is_dir = item.data(0, Qt.UserRole + 1)
        if is_dir:
            self.populate_tree(path)
            self.settings.setValue("last_folder", str(path))
        else:
            if path in self.main.selected_files[self.main.plot_area_index]:
                self.main.selected_files[self.main.plot_area_index].remove(path)
                dataset = self.main.datasets.pop(path)
                self.main.plot_area.remove(path, dataset)
                item.setData(0, Qt.UserRole + 2, False)
                item.setBackground(0, QBrush())
            else:
                dataset = Data_Set_Import(path)
                self.main.selected_files[self.main.plot_area_index].append(path)
                self.main.datasets[path] = dataset
                self.main.plot_area.manager.add(dataset)
                self.main.plot_area.add(path, dataset)
                item.setData(0, Qt.UserRole + 2, True)
                item.setBackground(0, QBrush(Qt.blue))
            self._update_label()
        
    def _clear_selection(self):
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            item.setData(0, Qt.UserRole + 2, False)
            item.setBackground(0, QBrush())
        self.main.plot_area.remove_all()
        self.main.selected_files[self.main.plot_area_index] = []
        self.tree.clearSelection()
        self._update_label()
        for filepath in self.main.selected_files[self.main.plot_area_index].copy():
            self.remove(filepath)

    def _open_meas(self):
        path_meas = self.path.joinpath(str(self.path.name)+" measurements.txt")
        if not path_meas.exists():
            print('File not found at: ',path_meas)
            return
        print('Opening: ',path_meas)
        pid = subprocess.Popen(['notepad.exe', str(path_meas)]).pid

    def _update_label(self):
        files = self.main.selected_files[self.main.plot_area_index]
        if not files:
            self.selected_label.setText("No files selected")
            self.selected_label.setStyleSheet("color: #aaa; font-size: 11px;")
        else:
            names = [f.replace("\\", "/").split("/")[-1] for f in files]
            self.selected_label.setText(
                f"{len(names)} selected:\n" + "\n".join(names)
            )
            self.selected_label.setStyleSheet("font-size: 11px;")
            
            
            
class SidebarMeasure(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        
        self.FAKE = True
        
        self._build()

    def _build(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.setAlignment(Qt.AlignTop)

        btn_view_sidebar = QPushButton("File Browser")
        # btn_view_sidebar.setFixedWidth(30)
        btn_view_sidebar.clicked.connect(self.main.swap_sidebars)
        self.layout.addWidget(btn_view_sidebar)
        
        self.UI_spectrometer = UI_SpectroMeter(self)
        self.add_device_ui(self.UI_spectrometer)
        
        
        
    def add_device_ui(self,dev_ui):
        self.layout.addWidget(dev_ui)
        
        
        
class UI_SpectroMeter(QFrame):
    def __init__(self,main_window):
        super().__init__()
        self.main = main_window
        # self.setFrameShape(QFrame.Box)       # or StyledPanel, Panel, etc.
        # self.setFrameShadow(QFrame.Raised)
        self.setFrameShape(QFrame.StyledPanel)
        
        
        self.val = None
        self._build()
        
        
        
        
    def _build(self):
        
        # self.setStyleSheet("border: 1px solid red; margin: 1px; padding: 1px;")
        
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(5)
        self.layout.setContentsMargins(5, 1, 5, 1)
        
        self.layout.addWidget(QLabel('Spectrometer'))
        
        btn_measure = QPushButton('Measure')        
        if self.main.FAKE:
            btn_measure.clicked.connect(self.start_measure)
        
        layer1 = QHBoxLayout()
        
        layer1.addWidget(btn_measure)
        
        self.layout.addLayout(layer1)
        


    def start_measure(self):
        self._thread = QThread()
        self._worker = MeasureWorker(self.main.main.device_spectrometer)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_measure_done)
        self._worker.error.connect(self._on_measure_error)

        # cleanup when done
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def _on_measure_done(self, val):
        self.val = val
        self.main.main.graph_spectrometer.update_val(self.val)

    def _on_measure_error(self, message):
        QMessageBox.critical(self, "Measurement error", message)
        
        
class UI_Scan(QFrame):
    def __init__(self,main_window):
        super().__init__()
        self.main = main_window
        
        self.setFrameShape(QFrame.StyledPanel)
        
        self.val = None
        self._build()
        
    def _build(self):
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(5)
        self.layout.setContentsMargins(5, 1, 5, 1)
        
        self.layout.addWidget(QLabel('Scan'))
        
        btn_measure = QPushButton('Start')        
        if self.main.FAKE:
            btn_measure.clicked.connect(self.start_measure)
        
        layer1 = QHBoxLayout()
        
        layer1.addWidget(btn_measure)
        
        self.layout.addLayout(layer1)

    def start_scan(self, axes):
        device = self.main.main.device_spectrometer

        def move_fn(coords):
            self.main.main.stage.move_to(coords)

        def measure_fn():
            return sn.getCountRates()

        self._scan_thread = QThread()
        self._scan_worker = ScanWorker(axes, move_fn, measure_fn)
        self._scan_worker.moveToThread(self._scan_thread)

        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.point_measured.connect(self._on_point_measured)
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)

        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.finished.connect(self._scan_worker.deleteLater)
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)

        self._scan_thread.start()

    def _on_point_measured(self, coords, value):
        self.main.main.graph_spectrometer.update_val(value, coords) # runs on main thread

    def _on_scan_progress(self, current, total):
        self.progress_bar.setValue(int(current / total * 100))

    def _on_scan_finished(self):
        self.status_label.setText("Scan complete")

    def _on_scan_error(self, message):
        QMessageBox.critical(self, "Scan error", message)

    def stop_scan(self):
        if hasattr(self, '_scan_worker'):
            self._scan_worker.request_stop()
        
        
        
        
        
        
        
class MeasureWorker(QObject):
    finished = Signal(object)  
    error = Signal(str)

    def __init__(self, device):
        super().__init__()
        self.device = device

    def run(self):
        try:
            val = commands.get(self.device)
            self.finished.emit(val)
        except Exception as e:
            self.error.emit(str(e))
            
            
            
            
            
            
class ScanWorker(QObject):
    point_measured = Signal(dict, object)   # (coords_dict, measured_value) - emitted after each point
    finished = Signal()
    error = Signal(str)
    progress = Signal(int, int)             # (current_index, total_points)

    def __init__(self, axes, move_fn, measure_fn):
        """
        axes: dict like {'x': [-10, 10, 1], 'y': [0, 5, 1]}
              meaning start, stop, step (inclusive)
        move_fn: callable(coords_dict) -> moves the instrument to that position
        measure_fn: callable() -> returns a measurement value
        """
        super().__init__()
        self.axes = axes
        self.move_fn = move_fn
        self.measure_fn = measure_fn
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def _build_grid(self):
        axis_names = list(self.axes.keys())
        axis_ranges = []
        for name in axis_names:
            start, stop, step = self.axes[name]
            # include stop point, guard against float drift
            values = np.arange(start, stop + step / 2, step)
            axis_ranges.append(values)

        combos = itertools.product(*axis_ranges)
        return axis_names, list(combos)

    def run(self):
        try:
            axis_names, combos = self._build_grid()
            total = len(combos)

            for i, combo in enumerate(combos):
                if self._stop_requested:
                    break

                coords = dict(zip(axis_names, combo))

                self.move_fn(coords)
                value = self.measure_fn()

                self.point_measured.emit(coords, value)
                self.progress.emit(i + 1, total)

            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))
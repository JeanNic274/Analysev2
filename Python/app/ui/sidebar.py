import itertools

import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QAbstractItemView,
    QLabel, QLineEdit, QTreeWidget, QTreeWidgetItem, QSizePolicy, QFileSystemModel, QFrame, QMessageBox, QCheckBox, QTableWidgetItem, QTableWidget, QAbstractScrollArea, QHeaderView, QScrollArea, QTextEdit
)
# print('imported QTWidget', time.time()-t)
# t=time.time()
from PySide6.QtCore import Qt, QDir, QSortFilterProxyModel, QSettings, QThread, QObject, Signal
from PySide6.QtGui import QBrush, QPalette, QColor, QColorConstants
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
from Python.app.ui.graphs import *
from Python.app.Measurements.devices import Scanner

from pyHegel.pyHegel import commands as cmds
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
        
        self.path_input = RevertableLineEdit()
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
            
            
            
class SidebarMeasure(QScrollArea):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        
        self.FAKE = True
        self._build()

    def _build(self):
        
        self.setStyleSheet(
            """
            QScrollArea { background-color: #121212 } 
            """
        )
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.setAlignment(Qt.AlignTop)

        btn_view_sidebar = QPushButton("File Browser")
        btn_view_sidebar.clicked.connect(self.main.swap_sidebars)
        self.layout.addWidget(btn_view_sidebar)
        
        self.UI_MH150 = UI_MH150(self)
        self.add_device_ui(self.UI_MH150)
        
        self.UI_Scan = UI_Scan(self)
        self.add_device_ui(self.UI_Scan)
        
        self.UI_spectrometer = UI_SpectroMeter(self)
        self.add_device_ui(self.UI_spectrometer)
        
        self.UI_NanoPos = UI_NanoPos(self)
        self.add_device_ui(self.UI_NanoPos)
        
        self.UI_Laser = UI_Laser(self)
        self.add_device_ui(self.UI_Laser)
        
        self.layout.addStretch()
        
    def add_device_ui(self,dev_ui):
        self.layout.addWidget(dev_ui)
        

#************************ UI Widgets for instruments/commands ************************#


class UI_MH150(QFrame):    
    def __init__(self,main_window):
        super().__init__()
        self.main = main_window
        # self.setFrameShape(QFrame.Box)       # or StyledPanel, Panel, etc.
        # self.setFrameShadow(QFrame.Raised)
        self.setFrameShape(QFrame.StyledPanel)
        self.update_graph = True
        
        self.val = None
        self._build()
        
        
        
        
    def _build(self):
        
        # self.setStyleSheet("border: 1px solid red; margin: 1px; padding: 1px;")
        
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(5)
        self.layout.setContentsMargins(5, 1, 5, 1)
        
        self.layout.addWidget(QLabel('MultiHarp150'))
        
        layer1 = QHBoxLayout()
        
        self.btn_read_cont = QCheckBox('Read Cont.')        
        self.btn_read_cont.toggled.connect(self.on_continuous_toggled)
        self.btn_rate_graph = QCheckBox('Rate Graph')        
        self.btn_rate_graph.toggled.connect(self.rate_graph_toggle)
        
        
        layer1.addWidget(self.btn_read_cont)
        layer1.addWidget(self.btn_rate_graph)
        
        layer2 = QHBoxLayout()
        
        self.label_counts1 = QLabel("Ch1: -")
        self.label_counts2 = QLabel("Ch2: -")
        self.label_countst = QLabel("Total: -")
        layer2.addWidget(self.label_counts1)
        layer2.addWidget(self.label_counts2)
        layer2.addWidget(self.label_countst)
        
        self.layout.addLayout(layer1)
        self.layout.addLayout(layer2)
        

    def on_continuous_toggled(self, checked):
        if checked:
            self._start_continuous_read()
            if self.main.main.graph_rate_graph:
                self.main.main.graph_rate_graph.graph.resume()
        else:
            self._stop_continuous_read()
            if self.main.main.graph_rate_graph:
                self.main.main.graph_rate_graph.graph.pause()
                
    def rate_graph_toggle(self,checked):
        if checked:
            self.main.main.graph_rate_graph = RateGraph(self.main)
            self.main.main.graph_rate_graph.show()
        else:
            if self.main.main.graph_rate_graph:
                self.main.main.graph_rate_graph.close()
                self.main.main.graph_rate_graph = None
            
    def _start_continuous_read(self):
        device = self.main.main.device_MH150
        
        if hasattr(self, '_cont_thread') and self._cont_thread is not None and self._cont_thread.isRunning():
            return
        
        def measure_fn(): 
            return device.getCountRates()

        self._cont_thread = QThread()
        self._cont_worker = ContinuousReadWorker(measure_fn, interval_ms=500)
        self._cont_worker.moveToThread(self._cont_thread)

        self._cont_thread.started.connect(self._cont_worker.run)
        self._cont_worker.reading.connect(self._on_continuous_reading)
        self._cont_worker.error.connect(self._on_continuous_error)

        self._cont_worker.finished.connect(self._cont_thread.quit)
        self._cont_worker.finished.connect(self._cont_worker.deleteLater)
        self._cont_thread.finished.connect(self._cont_thread.deleteLater)

        self._cont_thread.finished.connect(self._clear_cont_refs)
        self._cont_thread.start()

    def _stop_continuous_read(self):
        if hasattr(self, '_cont_worker'):
            self._cont_worker.stop()
        

    def _on_continuous_reading(self, value):
        self.val = value+ (value[0]+value[1],)
        self.label_countst.setText(f"Total: {self.val[2]}")
        self.label_counts1.setText(f"Ch1: {self.val[0]}")
        self.label_counts2.setText(f"Ch2: {self.val[1]}")
        if self.btn_rate_graph.isChecked():
            # if self.update_graph: # if 500 ms is too fast can update every 2 points
            self.main.main.graph_rate_graph.add_data(self.val)
            #     self.update_graph = False
            # else:
            #     self.update_graph = True

    def _on_continuous_error(self, message):
        QMessageBox.critical(self, "Measurement error", message)
        self.btn_read_cont.setChecked(False)
    def _clear_cont_refs(self):
        self._cont_thread = None
        self._cont_worker = None

        
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
        self._worker = MeasureWorker(self.main.main.device_spectrometer.readval)
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
        
        self.params_enabled = {}
        self.setFrameShape(QFrame.StyledPanel)
        
        self.val = None
        self._build()
        
    def _build(self):
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(5)
        self.layout.setContentsMargins(5, 1, 5, 1)
        
        self.layout.addWidget(QLabel('Scan'))
        
        self.btn_measure = QPushButton('Start')        
        self.btn_measure.setCheckable(True)
        
        self.btn_measure.toggled.connect(self.start_scan)
        
        layer1 = QHBoxLayout()
        
        layer1.addWidget(self.btn_measure)
        
        layer1.addStretch()
        layer1.addWidget(QLabel('Detection: '))
        
        self.qbox_scan_det = MyQComboBox()        
        self.qbox_scan_det.addItems(['MH150','DAQ','Spec'])
        layer1.addWidget(self.qbox_scan_det)
        
        layer2 = QHBoxLayout()
        
        layer2.addWidget(QLabel('Scan Parameters: '))
        
        layer3 = QHBoxLayout()
        
        self.scan_parameters = QTableWidget()
        layer3.addWidget(self.scan_parameters)
        self.scan_parameters.setMinimumHeight(1)
        self.scan_parameters.setStyleSheet("""
            QTableWidget::item {
                padding-left: 5px;
                padding-right: 5px;
                padding-top: 1px;
                padding-bottom: 1px;
            }
        """)
        self.scan_parameters.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.scan_parameters.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scan_parameters.setDragEnabled(1)
        self.scan_parameters.setAcceptDrops(1)
        self.scan_parameters.setDefaultDropAction(Qt.DropAction.CopyAction)
        
        self.scan_parameters.setColumnCount(4)
        self.scan_parameters.setHorizontalHeaderLabels(('Start','Stop','Step',''))
        
        self.scan_parameters.setRowCount(3)
        scan_params = ('x','y','z')
        self.scan_parameters.setVerticalHeaderLabels(scan_params)
        for i in range(self.scan_parameters.columnCount()-1):
            self.scan_parameters.horizontalHeader().setSectionResizeMode(i,QHeaderView.Stretch)
            
        self.scan_parameters.setColumnWidth(3,10)
        self.scan_parameters.horizontalHeader().setSectionResizeMode(3,QHeaderView.Fixed)
        
        for i, param in enumerate(scan_params):
            self.params_enabled[param] = QTableWidgetItem()
            self.params_enabled[param].setTextAlignment(4)
            self.params_enabled[param].setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            self.scan_parameters.setItem(i,3,self.params_enabled[param])
            start_item = QTableWidgetItem()
            stop_item = QTableWidgetItem()
            step_item = QTableWidgetItem()
        # default scan param for dev
            start_item.setText("0")
            stop_item.setText("10")
            step_item.setText("1")
            self.scan_parameters.setItem(i,0,start_item)
            self.scan_parameters.setItem(i,1,stop_item)
            self.scan_parameters.setItem(i,2,step_item)
            
        # default enabled:
        self.params_enabled[scan_params[0]].setCheckState(Qt.Checked)
        self.params_enabled[scan_params[1]].setCheckState(Qt.Checked)
        self.params_enabled[scan_params[2]].setCheckState(Qt.Unchecked)
        
        resize_table_to_contents(self.scan_parameters)
        
        self.layout.addLayout(layer1)
        self.layout.addLayout(layer2)
        self.layout.addLayout(layer3)
        
        
    
    def get_scan_parameters(self):
        result = {}
        last_col = self.scan_parameters.columnCount() - 1

        for row in range(self.scan_parameters.rowCount()):
            header_item = self.scan_parameters.verticalHeaderItem(row)
            key = header_item.text() if header_item else str(row)

            checkbox_item = self.scan_parameters.item(row, last_col)
            is_checked = checkbox_item.checkState() == Qt.Checked if checkbox_item else False

            if not is_checked:
                continue  # skip if not checked

            values = []
            for col in range(last_col):  
                item = self.scan_parameters.item(row, col)
                try:
                    values.append(float(item.text()))
                except (ValueError, AttributeError):
                    QMessageBox.critical(self, f"Error Scan Parameters",f"Bad input at: {(row, col)}")
                    return None
                
            if values[0]==values[1]:
                QMessageBox.critical(self, f"Error Scan Parameters",f"Stop cannot be the same as Start")
                return None
                
            if values[0]>values[1]:
                values[0], values[1] = values[1], values[0]
                
                
            result[key] = values

        return result
    
    
    def start_scan(self, checked = False):
        if not checked:
            if hasattr(self, '_scan_worker'):
                self._scan_worker.request_stop()
            return
        self.btn_measure.setText('Abort')
        
        axes = self.get_scan_parameters()
        
        if axes == None:
            return
        
        # axes={'x':[0,10,1],'y':[10,15,1]}
        device = None
        if self.qbox_scan_det.currentText() == "MH150":
            device = self.main.main.device_MH150
        elif self.qbox_scan_det.currentText() == "DAQ":
            device = self.main.main.device_DAQ
        elif self.qbox_scan_det.currentText() == "Spec":
            device = self.main.main.device_spectrometer
        
        self.main.main.scanner = Scanner(axes,[self.qbox_scan_det.currentText(),device])
        
        move_fns = self.main.main.scanner.move_fns()
        measure_fn = self.main.main.scanner.meas_fns()
        
        missing = set(axes.keys()) - set(move_fns.keys()) # Check all scan axis ok
        if missing:
            raise ValueError(f"Missing move function for axes: {missing}")

        # def measure_fn():
        #     return device.getCountRates()
        
        if len(axes) == 1:
            graph = ScanPlot1D(self,axes)
        else:
            graph = ScanPlot2D(self,axes)
        graph.show()
        self.main.main.graphs_scan.append(graph)
        
        self._scan_thread = QThread()
        self._scan_worker = ScanWorker(axes, move_fns, measure_fn)
        self._scan_worker.moveToThread(self._scan_thread)

        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.point_measured.connect(self._on_point_measured)
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)

        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.finished.connect(self._scan_worker.deleteLater)
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)
        self._scan_thread.finished.connect(self._clear_scan_refs)

        self._scan_thread.start()

    def _on_point_measured(self, idx, coords, value):
        self.main.main.graphs_scan[-1].update_data(self._scan_worker.data, new_value = value,coords=coords)

    def _on_scan_progress(self, current, total):
        # self.progress_bar.setValue(int(current / total * 100))
        pass

    def _on_scan_finished(self):
        # self.status_label.setText("Scan complete")
        print()
        print("Scan complete")
        self.btn_measure.blockSignals(True)
        self.btn_measure.setChecked(False)
        self.btn_measure.setText('Start')
        self.btn_measure.blockSignals(False)
        self.main.main.scanner = None

    def _on_scan_error(self, message):
        QMessageBox.critical(self, "Scan error", message)
        
    def _clear_scan_refs(self):
        self._scan_thread = None
        self._scan_worker = None

    def stop_scan(self):
        if hasattr(self, '_scan_worker'):
            self._scan_worker.request_stop()
                
        
class UI_Laser(QFrame):
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
        
        self.layout.addWidget(QLabel('Laser'))
        
        layer1 = QHBoxLayout()
        
        layer1.addWidget(QLabel('Power: '))
        self.qtext_laser_power = RevertableLineEdit()       
        self.qtext_laser_power.editingFinished.connect(self._set_laser)
        self.qtext_laser_power.setFixedWidth(50)
        layer1.addWidget(self.qtext_laser_power)
        layer1.addWidget(QLabel('%'))
        
        layer1.addStretch()
        
        self.btn_softlock = QPushButton('SoftLock')        
        self.btn_softlock.setCheckable(True)
        self.btn_softlock.toggled.connect(self._set_laser)
        
        
        layer1.addWidget(self.btn_softlock)
        
        layer2 = QHBoxLayout()
        
        layer2.addWidget(QLabel('Mode: '))
        
        self.qbox_laser_mode = MyQComboBox()        
        self.qbox_laser_mode.addItems(['cw','pulse','burst'])
        self.qbox_laser_mode.currentTextChanged.connect(self._set_laser)
        layer2.addWidget(self.qbox_laser_mode)
        
        layer2.addStretch()
        
        layer2.addWidget(QLabel('Freq: '))
        self.qtext_laser_freq = RevertableLineEdit()       
        self.qtext_laser_freq.editingFinished.connect(self._set_laser)
        self.qtext_laser_freq.setFixedWidth(50)
        # self.qtext_laser_freq.document().contentsChanged.connect(self._set_laser)
        layer2.addWidget(self.qtext_laser_freq)
        
        
        layer2.addWidget(QLabel('kHz'))
        
        self.layout.addLayout(layer1)
        self.layout.addLayout(layer2)
        
    def _set_laser(self):
        self._thread = QThread()
        self._worker = CommWorker(self.main.main.device_laser,self.set_laser)
        self._worker.moveToThread(self._thread)

        self._worker.kwargs = {
                                  "power"     : self.qtext_laser_power.text(),
                                  "softlock"  : self.btn_softlock.isChecked(),
                                  "mode"      : self.qbox_laser_mode.currentText(), 
                                  "freq"      : self.qtext_laser_freq.text()
                                  }

        self._thread.started.connect(self._worker.run)
        self._worker.error.connect(self._on_measure_error)
        self._worker.value_error.connect(self._on_value_error)

        # cleanup when done
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def _on_value_error(self, messages):
        for value in messages:
            QMessageBox.warning(self, f"Invalid numeric value", f"Invalid numeric value for {value}")

    def _on_measure_error(self, message):
        QMessageBox.critical(self, "Comm. error", message)
        
    def set_laser(self,device = None, power = None,  mode = None, softlock = None, freq = None):
        invalid_parameters = []
        if device is None:
            # laser = instruments.picoQuant.PicoQuant_Taiko_PDL_M1()
            raise ValueError()
        
        if power is not None:
            print(f"\nSetting CW power to {power}%...")
            try:
                pwr = int(float(power) * 10)
                cmds.set(device.cw_power_permille, pwr)
                print(f"CW power is now: {power}%")
            except ValueError:
                invalid_parameters.append(power)
                
        if softlock is not None:
            cmds.set(device.softlock_en, softlock)
            if softlock:
                print(f"Laser softlock state : {cmds.get(device.softlock_en)}.")
        if freq is not None and freq != "":
            try:
                frq = int(float(freq) * 1000)
                cmds.set(device.freq, frq)
                print(f"Frequency is now: {freq} kHz")
            except ValueError:
                invalid_parameters.append(freq)
        if mode is not None:
            cmds.set(device.laser_mode, mode)    
        return invalid_parameters
      
        
class UI_NanoPos(QFrame):
    def __init__(self,main_window):
        super().__init__()
        self.main = main_window
        
        self.setFrameShape(QFrame.StyledPanel)
        
        self.toggles_btns = {}
        self.cont_labels = {}
        
        self._cont_thread = {}
        self._cont_worker = {}
        
        self.val = None
        self._build()
        
    def _build(self):
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(5)
        self.layout.setContentsMargins(5, 1, 5, 1)
        
        self.layout.addWidget(QLabel('Position'))
        
        axis = {'0':'x','1':'y','2':'z'}
        
        for ax,v in axis.items():
        
            layer = QHBoxLayout()
            
            # layer.addWidget(QLabel(v))
            
            btn_toggle = QPushButton(v)        
            btn_toggle.setFixedWidth(25)       
            btn_toggle.setCheckable(True)
            btn_toggle.toggled.connect(self._set_pos) #TODO: toggle piezo
            
            
            layer.addWidget(btn_toggle)
            self.toggles_btns[ax] = btn_toggle
            
            
            layer.addWidget(QLabel('goto: '))
            goto = RevertableLineEdit()       
            goto.editingFinished.connect(
                lambda ax=ax,pos_btn=goto:
                    self._set_pos(ax,pos_btn)
            )
            goto.validator()
            goto.setFixedWidth(50)
            layer.addWidget(goto)
            layer.addStretch()
            
            btn_read_cont = QPushButton('Read')        
            btn_read_cont.setCheckable(True)
            btn_read_cont.setFixedWidth(40)
            btn_read_cont.clicked.connect(lambda checked=btn_read_cont.isChecked(), ax=ax:self.on_continuous_toggled(checked,ax))
                
            layer.addWidget(btn_read_cont)
            label_read_cont = QLabel("-")
            label_read_cont.setFixedWidth(50)
            layer.addWidget(label_read_cont)
            self.cont_labels[ax] = label_read_cont
            
            self.layout.addLayout(layer)
        
    def _set_pos(self,ax,pos_btn):
        text = pos_btn.text()
        try:
            pos = int(float(text) * 1000)
        except ValueError:
            QMessageBox.warning(self, "Invalid input", f"'{text}' is not a valid number.")
            return
        # if self.qtext_laser_freq.text().isdigit():
        #     freq = float(self.qtext_laser_freq.text())
        # else:
        #     freq = None
        
        # self._thread = QThread()
        # self._worker = CommWorker()
        # self._worker.moveToThread(self._thread)

        # self._thread.started.connect(self._worker.run)
        # self._worker.error.connect(self._on_measure_error)

        # # cleanup when done
        # self._worker.finished.connect(self._thread.quit)
        # self._worker.finished.connect(self._worker.deleteLater)
        # self._thread.finished.connect(self._thread.deleteLater)

        # self._thread.start()

    def on_continuous_toggled(self, checked,ax):
        if checked:
            self._start_continuous_read(ax)
        else:
            self._stop_continuous_read(ax)
                
    def _start_continuous_read(self,ax):
        device = self.main.main.device_nanopositionner
        
        if ax in self._cont_thread and self._cont_thread[ax] is not None and self._cont_thread[ax].isRunning():
            return
        
        def measure_fn(): 
            return device.move.getPosition(ax)/1000
        
        self._cont_thread[ax] = QThread()
        self._cont_worker[ax] = ContinuousReadWorker(measure_fn, interval_ms=500)
        self._cont_worker[ax].moveToThread(self._cont_thread[ax])

        self._cont_thread[ax].started.connect(self._cont_worker[ax].run)
        self._cont_worker[ax].reading.connect(lambda value, ax=ax:self._on_continuous_reading(value,ax))
        self._cont_worker[ax].error.connect(lambda message, ax=ax:self._on_continuous_error(message,ax))

        self._cont_worker[ax].finished.connect(self._cont_thread[ax].quit)
        self._cont_worker[ax].finished.connect(self._cont_worker[ax].deleteLater)
        self._cont_thread[ax].finished.connect(self._cont_thread[ax].deleteLater)

        self._cont_thread[ax].finished.connect(lambda ax=ax:self._clear_cont_refs(ax))
        self._cont_thread[ax].start()

    def _stop_continuous_read(self,ax):
        worker = self._cont_worker.get(ax)
        if worker is not None:
            worker.stop()
        
    def _on_continuous_reading(self, value,ax):
        self.cont_labels[ax].setText(f"{value:.3f}")

    def _on_continuous_error(self, message,ax):
        QMessageBox.critical(self, "NanoPositionner measurement error", message)
        self.toggles_btns[ax].setChecked(False)
        
    def _clear_cont_refs(self,ax):
        self._cont_thread[ax] = None
        self._cont_worker[ax] = None


#************************ Workers for non main-thread operations ************************#
        
class CommWorker(QObject):
    finished = Signal(object)  
    error = Signal(str)
    value_error = Signal(list)
    
    def __init__(self, device, set_fn):
        super().__init__()
        self.device = device
        self.set_fn = set_fn
        self.kwargs = {}

    def run(self):
        try:
            val = self.set_fn(device = self.device, **self.kwargs)
            if val:
                self.value_error.emit(val)
            self.finished.emit(1)
        except Exception as e:
            self.error.emit(str(e))
            
        
        
class MeasureWorker(QObject):
    finished = Signal(object)  
    error = Signal(str)

    def __init__(self, device):
        super().__init__()
        self.device = device

    def run(self):
        try:
            val = cmds.get(self.device)
            self.finished.emit(val)
        except Exception as e:
            self.error.emit(str(e))
            
            
class ContinuousReadWorker(QObject):
    reading = Signal(object)   
    error = Signal(str)
    finished = Signal()

    def __init__(self, measure_fn, interval_ms=500, graph = None):
        super().__init__()
        self.measure_fn = measure_fn
        self.interval_ms = interval_ms
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        try:
            while self._running:
                value = self.measure_fn()
                self.reading.emit(value)

                # sleep in small chunks so stop() is noticed quickly
                # rather than blocking a full interval after stop() is called
                slept = 0
                chunk = 100  # ms
                while slept < self.interval_ms and self._running:
                    QThread.msleep(chunk)
                    slept += chunk
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()        
            
            
class ScanWorker(QObject): 
    point_measured = Signal(tuple, dict, object)
    finished = Signal()
    error = Signal(str)
    progress = Signal(int, int)

    def __init__(self, axes, move_fns, measure_fn):
        """
        axes: dict like {'x': [-10, 10, 1], 'y': [0, 5, 1]}
        move_fns: dict like {'x': move_x_fn, 'y': move_y_fn}
                  each move_fns[name](value) moves just that axis
        measure_fn: callable() -> value
        """
        super().__init__()
        self.axes = axes
        self.move_fns = move_fns
        self.measure_fn = measure_fn
        self._stop_requested = False

        self.axis_names = list(reversed(axes.keys()))
        self.axis_values = []
        for name in self.axis_names:
            start, stop, step = axes[name]
            start, stop, step = 1000*int(start), 1000*int(stop), 1000*int(step)
            values = np.arange(start, stop + step / 2, step, dtype= int)
            self.axis_values.append(values)

        self.shape = tuple(len(v) for v in self.axis_values)
        self.data = np.full(self.shape, np.nan)

    def request_stop(self):
        self._stop_requested = True

    def run(self):
        try:
            index_ranges = [range(len(v)) for v in self.axis_values]
            combos = list(itertools.product(*index_ranges))
            total = len(combos)

            last_coords = {name: None for name in self.axis_names}

            for i, idx in enumerate(combos):
            # for i, rev_idx in enumerate(combos):
                if self._stop_requested:
                    break

                # idx = rev_idx[::-1]
                coords = {
                    name: self.axis_values[a][idx[a]]
                    for a, name in enumerate(self.axis_names)
                }

                # only move relevant axes
                for name in self.axis_names:
                    if coords[name] != last_coords[name]:
                        self.move_fns[name](coords[name])
                        last_coords[name] = coords[name]

                value = self.measure_fn()
                values = (value) + (np.sum(value),)
                self.data[idx] = values[-1]
                self.point_measured.emit(idx, coords, values)
                self.progress.emit(i + 1, total)

            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))






def resize_table_to_contents(table):
    header_height = table.horizontalHeader().height()
    rows_height = sum(table.rowHeight(r) for r in range(table.rowCount()))
    frame = table.frameWidth() * 2
    total_height = header_height + rows_height + frame
    table.setFixedHeight(total_height)
    
    
    
class RevertableLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._previous_text = self.text()
        self.editingFinished.connect(self._store_previous_text)

    def focusInEvent(self, event):
        self._previous_text = self.text()
        super().focusInEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.blockSignals(True)
            self.setText(self._previous_text)
            self.clearFocus() 
            self.blockSignals(False)
            return
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            self.clearFocus() 
            return
        super().keyPressEvent(event)

    def _store_previous_text(self):
        self._previous_text = self.text()
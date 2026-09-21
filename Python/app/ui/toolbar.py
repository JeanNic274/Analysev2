from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QTreeView, QSizePolicy, QFileSystemModel, QInputDialog
)
from PySide6.QtCore import Qt, QDir, QSortFilterProxyModel
from app.ui.DialogWindow import SpectrumFileManager, TRPLFileManager, Experiment_Picker, SaveManager
from app.Processing.misc import meastxt
from app.Processing.io import save_exp, load_exp

class Toolbar(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        # self.setFixedWidth(200)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setAlignment(Qt.AlignTop)

       
        btn_row = QWidget()
        btn_layout = QVBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)

        btn_save_mng = QPushButton("Save Manager")
        btn_save_mng.setFixedWidth(150)
        btn_save_mng.clicked.connect(self._open_save_mng)

        btn_sfile_mng = QPushButton("Spectrum File Manager")
        btn_sfile_mng.setFixedWidth(150)
        btn_sfile_mng.clicked.connect(self._open_sfile_mng)

        btn_tfile_mng = QPushButton("TRPL File Manager")
        btn_tfile_mng.setFixedWidth(150)
        btn_tfile_mng.clicked.connect(self._open_tfile_mng)

        btn_save_exp = QPushButton("Save Exp")
        btn_save_exp.setFixedWidth(150)
        btn_save_exp.clicked.connect(self._save_exp)

        btn_load_exp = QPushButton("Load Exp")
        btn_load_exp.setFixedWidth(150)
        btn_load_exp.clicked.connect(self._load_exp)


        btn_newtab = QPushButton("New Tab")
        btn_newtab.setFixedWidth(150)
        btn_newtab.clicked.connect(self._addTab)
        
        btn_meastxt = QPushButton("Meas.txt")
        btn_meastxt.setFixedWidth(150)
        btn_meastxt.clicked.connect(self._meastxt)

        btn_reset = QPushButton("Reset")
        btn_reset.setFixedWidth(150)
        btn_reset.clicked.connect(self._reset)

        btn_layout.addWidget(btn_save_mng)
        btn_layout.addWidget(btn_sfile_mng)
        btn_layout.addWidget(btn_tfile_mng)
        btn_layout.addWidget(btn_save_exp)
        btn_layout.addWidget(btn_load_exp)
        btn_layout.addWidget(btn_newtab)
        btn_layout.addWidget(btn_meastxt)
        btn_layout.addWidget(btn_reset)
        layout.addWidget(btn_row)
        layout.addStretch()
        
        self.btn_live_mode = QPushButton("Measurement Mode")
        self.btn_live_mode.setFixedWidth(150)
        
        self.btn_live_mode.setStyleSheet("QPushButton { background-color: red }"
                      "QPushButton:pressed { background-color: green }"
        )
        
        self.btn_live_mode.clicked.connect(self._start_measurement_mode)
        
        layout.addWidget(self.btn_live_mode)
        
    def _start_measurement_mode(self):
        self.btn_live_mode.setDown(True)
        self.main.start_measurement_mode()        
        
    def _open_save_mng(self):
        dialog = SaveManager(self.main)
        dialog.exec()

    def _open_sfile_mng(self):
        if self.main.plot_area.spectrum is None:
            print('No spectrum curves')
            return
        dialog = SpectrumFileManager(self.main)
        dialog.exec()
        
    def _open_tfile_mng(self):
        if self.main.plot_area.trpl is None:
            print('No trpl curves')
            return
        dialog = TRPLFileManager(self.main)
        dialog.exec()
        
    def _save_exp(self):
        filename, ok = QInputDialog.getText(self,"Save Experiment", "Enter file name:")
        if ok:
            save_exp(self.main.plot_area,filename)
        else:
            print('Enter valid name')
        
        
    def _load_exp(self):
        dialog = Experiment_Picker(self.main)
        dialog.exec()
        filepath = dialog.path
        if filepath:
            load_exp(self.main.plot_area,self.main.plot_area_index, filepath)
        
    def _addTab(self):
        self.main.plot_areas.add()    
    
    def _reset(self):
        print("_reset")

    def _meastxt(self):
        meastxt(self.main.sidebar.path)









            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
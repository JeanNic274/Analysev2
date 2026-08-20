from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QTreeView, QSizePolicy, QFileSystemModel
)
from PySide6.QtCore import Qt, QDir, QSortFilterProxyModel
from app.ui.DialogWindow import SpectrumFileManager

class Toolbar(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.setFixedWidth(200)
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

        btn_file_mng = QPushButton("File Manager")
        btn_file_mng.setFixedWidth(150)
        btn_file_mng.clicked.connect(self._open_file_mng)

        btn_save_exp = QPushButton("Save Exp")
        btn_save_exp.setFixedWidth(150)
        btn_save_exp.clicked.connect(self._save_exp)

        btn_load_exp = QPushButton("Load Exp")
        btn_load_exp.setFixedWidth(150)
        btn_load_exp.clicked.connect(self._load_exp)

        btn_reset = QPushButton("Reset")
        btn_reset.setFixedWidth(150)
        btn_reset.clicked.connect(self._reset)

        btn_meastxt = QPushButton("Meas.txt")
        btn_meastxt.setFixedWidth(150)
        btn_meastxt.clicked.connect(self._meastxt)


        btn_layout.addWidget(btn_save_mng)
        btn_layout.addWidget(btn_file_mng)
        btn_layout.addWidget(btn_save_exp)
        btn_layout.addWidget(btn_load_exp)
        btn_layout.addWidget(btn_reset)
        btn_layout.addWidget(btn_meastxt)
        layout.addWidget(btn_row)
        
        
        
        
    def _open_save_mng(self):
        print("_open_save_mng")

    def _open_file_mng(self):
        print("_open_file_mng")
        dialog = SpectrumFileManager(self.main)

        dialog.exec()
        
    def _save_exp(self):
        print("_save_exp")

    def _load_exp(self):
        print("_load_exp")
        
    def _reset(self):
        print("_reset")

    def _meastxt(self):
        print("_meastxt")









            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
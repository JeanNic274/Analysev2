# import time
# t=time.time()
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QAbstractItemView,
    QLabel, QLineEdit, QTreeWidget, QTreeWidgetItem, QSizePolicy, QFileSystemModel,
)
# print('imported QTWidget', time.time()-t)
# t=time.time()
from PySide6.QtCore import Qt, QDir, QSortFilterProxyModel, QSettings
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
from app.Processing.data_import import Data_Set_Import
# print('imported Data_Set_Import', time.time()-t)
# t=time.time()
from app.Processing.misc import  browse
# print('imported time.time()-t)
from config import DEFAULT_FOLDER


class SidebarView(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.settings = QSettings("JN","AnalyseV2")
        self.path=Path(self.settings.value("last_folder",DEFAULT_FOLDER))
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setAlignment(Qt.AlignTop)

        # path input
        self.path_input = QLineEdit()
        self.path_input.setStyleSheet('font-size: 10pt;')
        self.path_input.setPlaceholderText("Enter path...")
        self.path_input.returnPressed.connect(self._set_path)
        self.top_layout = QHBoxLayout()
        self.top_layout.addWidget(QLabel("Browse Files"))
        layout.addLayout(self.top_layout)
        layout.addWidget(self.path_input)
        
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
        subprocess.run(['notepad.exe', str(path_meas)])

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
        
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setAlignment(Qt.AlignTop)

        btn_view_sidebar = QPushButton("File Browser")
        # btn_view_sidebar.setFixedWidth(30)
        btn_view_sidebar.clicked.connect(self.main.swap_sidebars)
        layout.addWidget(btn_view_sidebar)
        
        

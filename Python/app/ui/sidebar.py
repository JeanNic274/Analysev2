# import time
# t=time.time()
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QTreeView, QSizePolicy, QFileSystemModel
)
# print('imported QTWidget', time.time()-t)
# t=time.time()
from PySide6.QtCore import Qt, QDir, QSortFilterProxyModel
# print('imported QtCore', time.time()-t)
# t=time.time()
import re
# print('imported re', time.time()-t)

# t=time.time()
from config import DEFAULT_FOLDER, WHITELIST_EXTENSIONS
# print('imported config', time.time()-t)
# t=time.time()
from app.Processing.data_import import Data_Set_Import
# print('imported Data_Set_Import', time.time()-t)
# t=time.time()
from app.Processing.misc import reset_idx
# print('imported reset_idx', time.time()-t)

class Sidebar(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.setFixedWidth(250)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setAlignment(Qt.AlignTop)

        # path input
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Enter path...")
        self.path_input.returnPressed.connect(self._set_path)
        layout.addWidget(QLabel("Browse Files"))
        layout.addWidget(self.path_input)
        
        # file tree
        self.fs_model = QFileSystemModel()
        self.fs_model.setRootPath(DEFAULT_FOLDER)
        self.fs_model.setNameFilters(WHITELIST_EXTENSIONS)
        self.fs_model.setNameFilterDisables(False)
        
        # custom sort
        self.proxy_model = CustomSortModel()
        self.proxy_model.setSourceModel(self.fs_model)
        
        self.tree = QTreeView()
        self.tree.setModel(self.proxy_model)
        # self.tree.setRootIndex(self.fs_model.index(DEFAULT_FOLDER))
        self.tree.setRootIndex(self.proxy_model.mapFromSource(
            self.fs_model.index(DEFAULT_FOLDER)
        ))
        self.tree.setSelectionMode(QTreeView.MultiSelection)
        self.tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tree.clicked.connect(self._on_file_clicked)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.AscendingOrder)

        # hide size, type, date columns
        self.tree.hideColumn(1)
        self.tree.hideColumn(2)
        self.tree.hideColumn(3)

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
        
    def _set_path(self):
        path = self.path_input.text()
        if QDir(path).exists():
            self.fs_model.setRootPath(path)
            self.tree.setRootIndex(self.proxy_model.mapFromSource(
                self.fs_model.index(path)
            ))
    def _on_file_clicked(self, index):
        source_index = self.proxy_model.mapToSource(index)
        if self.fs_model.isDir(source_index):
            if self.tree.isExpanded(index):
                self.tree.collapse(index)
            else:
                self.tree.expand(index)
            return

        path = self.fs_model.filePath(source_index)

        if path in self.main.selected_files:
            self.main.selected_files.remove(path)
            dataset = self.main.datasets.pop(path)
            self.main.plot_area.remove(path, dataset)
        else:
            dataset = Data_Set_Import(path)
            self.main.selected_files.append(path)
            self.main.datasets[path] = dataset
            self.main.plot_area.add(path, dataset)
        self._update_label()
        
    def _clear_selection(self):
        self.main.plot_area.remove_all()
        self.main.selected_files = []
        self.tree.clearSelection()
        self._update_label()
        for filepath in self.main.selected_files.copy():
            self.remove(filepath)
        reset_idx()

    # def _on_plot(self):
    #     self.main.plot_area.plot(self.main.selected_files)

    def _update_label(self):
        files = self.main.selected_files
        if not files:
            self.selected_label.setText("No files selected")
            self.selected_label.setStyleSheet("color: #aaa; font-size: 11px;")
        else:
            names = [f.replace("\\", "/").split("/")[-1] for f in files]
            self.selected_label.setText(
                f"{len(names)} selected:\n" + "\n".join(names)
            )
            self.selected_label.setStyleSheet("font-size: 11px;")
            
            
            

class CustomSortModel(QSortFilterProxyModel):
    def _natural_key(self, name):
        # split "..._0_10.txt" into ["..._", 0, "_", 10, ".txt"]
        parts = re.split(r'(\d+)', name.lower())
        return [int(p) if p.isdigit() else p for p in parts]
    def lessThan(self, left, right):
        model = self.sourceModel()

        left_is_dir = model.isDir(left)
        right_is_dir = model.isDir(right)

        if left_is_dir and right_is_dir:
            left_name = model.fileName(left)
            right_name = model.fileName(right)
            return self._natural_key(left_name) > self._natural_key(right_name)  # descending

        if not left_is_dir and not right_is_dir:
            left_name = model.fileName(left)
            right_name = model.fileName(right)
            return self._natural_key(left_name) < self._natural_key(right_name)  # ascending

        return left_is_dir
import os

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QInputDialog,
    QListWidgetItem,
)
from PySide6.QtCore import Qt


class SpectrumFileManager(QDialog):

    def __init__(self, main_window):
        super().__init__(main_window)

        self.main = main_window

        self.setWindowTitle("Spectrum File Manager")
        self.resize(700, 500)

        self._build()
        self._refresh()


    def _build(self):

        layout = QVBoxLayout(self)

        # -------------------------
        # Groups
        # -------------------------

        self.groups = QListWidget()

        # -------------------------
        # Files
        # -------------------------

        self.files = QListWidget()

        # Allow multiple file selection
        self.files.setSelectionMode(
            QListWidget.MultiSelection
        )

        # -------------------------
        # Buttons
        # -------------------------

        btn_new = QPushButton("New Group")
        btn_add = QPushButton("Add Selected Files")
        btn_remove = QPushButton("Remove Files")
        btn_reset = QPushButton("Reset Groups")

        btn_new.clicked.connect(self._new_group)
        btn_add.clicked.connect(self._add_files)
        btn_remove.clicked.connect(self._remove_files)
        btn_reset.clicked.connect(self._reset)

        # -------------------------
        # Layout
        # -------------------------

        group_layout = QVBoxLayout()
        group_layout.addWidget(self.groups)
        group_layout.addWidget(btn_new)
        group_layout.addWidget(btn_reset)

        file_layout = QVBoxLayout()
        file_layout.addWidget(self.files)
        file_layout.addWidget(btn_add)
        file_layout.addWidget(btn_remove)

        lists = QHBoxLayout()
        lists.addLayout(group_layout)
        lists.addLayout(file_layout)

        layout.addLayout(lists)

    def _reset(self):
        self.main.plot_area.spectrum.groups = {str(i): [] for i in range(5)}
    
    
    def _refresh(self):
        self.groups.clear()
        self.files.clear()
        for group_name in self.main.plot_area.spectrum.groups:
            self.groups.addItem(group_name)

        for filepath, dataset in self.main.datasets.items():
            if getattr(dataset, "measure_type", None) == "spectrum":
                item=QListWidgetItem(os.path.basename(filepath)[:-4])
                item.setData(Qt.UserRole,filepath)
                self.files.addItem(item)

    def _new_group(self):
        group_id = 0

        while str(group_id) in self.main.plot_area.spectrum.groups:
            group_id += 1

        self.main.plot_area.spectrum.groups[str(group_id)] = []

        self._refresh()
        
    def _add_files(self):
        group_item = self.groups.currentItem()
        if group_item is None:
            return

        group_name = group_item.text()
        selected = self.files.selectedItems()

        for item in selected:
            filepath = item.data(Qt.UserRole)
            if filepath not in self.main.plot_area.spectrum.groups[group_name]:
                self.main.plot_area.spectrum.groups[group_name].append(filepath)
        self._refresh()
        self.main.plot_area.spectrum.update_groups()
        
    def _remove_files(self):
        group_item = self.groups.currentItem()

        if group_item is None:
            return

        group_name = group_item.text()
        selected = self.files.selectedItems()

        for item in selected:
            filepath = item.text()
            if filepath in self.main.plot_area.spectrum.groups[group_name]:
                self.main.plot_area.spectrum.groups[group_name].remove(filepath)
                
    def closeEvent(self, event):
        self.main.plot_area.spectrum.update_groups()
        event.accept()




























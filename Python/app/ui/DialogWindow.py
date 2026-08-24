import os

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QCheckBox,
    QInputDialog,
    QListWidgetItem,
    QLineEdit,
    QWidget,
    QLabel,
)
from PySide6.QtCore import Qt


class SpectrumFileManager(QDialog):

    def __init__(self, main_window):
        self.force_refresh=0
        super().__init__(main_window)

        self.main = main_window

        self.setWindowTitle("Spectrum File Manager")
        self.resize(700, 500)



        self._build()
        self._refresh()


    def _build(self):

        layout = QVBoxLayout(self)

        # Groups
        self.groups = QListWidget()

        # Files
        self.files = QListWidget()
        
        self.files.setSelectionMode(# Allow multiple file selection
            QListWidget.MultiSelection
        )

        # Buttons
        btn_new = QPushButton("New Group")
        btn_add = QPushButton("Add Selected Files")
        btn_remove = QPushButton("Remove Files")
        btn_reset = QPushButton("Reset Groups")

        btn_new.clicked.connect(self._new_group)
        btn_add.clicked.connect(self._add_files)
        btn_remove.clicked.connect(self._remove_files)
        btn_reset.clicked.connect(self._reset)

        # Check Boxes
        check_number = QCheckBox('Number')
        check_number.setChecked(1)
        check_name = QCheckBox('Name')
        check_name.setChecked(1)
        check_power = QCheckBox('Power')
        check_pos = QCheckBox('Position (x,y)')
        check_posf = QCheckBox('Position (x,y,z)')
        check_filter = QCheckBox('Filter')
        
        # Layouts
        group_layout = QVBoxLayout()
        group_layout.addWidget(self.groups)
        group_layout.addWidget(btn_new)
        group_layout.addWidget(btn_reset)

        file_layout = QVBoxLayout()
        file_layout.addWidget(self.files)
        file_layout.addWidget(btn_add)
        file_layout.addWidget(btn_remove)
        
        check_layout = QHBoxLayout()
        check_layout.addWidget(check_number)
        check_layout.addWidget(check_name)
        check_layout.addWidget(check_power)
        check_layout.addWidget(check_pos)
        check_layout.addWidget(check_posf)
        check_layout.addWidget(check_filter)

        lists = QHBoxLayout()
        lists.addLayout(group_layout)
        lists.addLayout(file_layout)
        
        # Title
        qlab1 = QLabel('Curves label:')
        qlab1.setStyleSheet('font-size: 16pt;')
        # Title
        qlab2 = QLabel('Merge spectra:')
        qlab2.setStyleSheet('font-size: 12pt;')
        
        layout.addWidget(qlab1)
        layout.addLayout(check_layout)
        layout.addWidget(qlab2)
        layout.addLayout(lists)

    def _reset(self):
        self.force_refresh = 1
        self.main.plot_area.spectrum.groups = {str(i): [] for i in range(5)}
    
    
    def _refresh(self):
        self.groups.clear()
        self.files.clear()
        for group_name in self.main.plot_area.spectrum.groups:
            self.groups.addItem(group_name)

        for filepath, dataset in self.main.datasets.items():
            if getattr(dataset, "measure_type", None) != "spectrum":
                continue
            
            item=QListWidgetItem(os.path.basename(filepath)[:-4])
            item.setData(Qt.UserRole,filepath)

            # Widget containing filename + text box
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(2, 2, 2, 2)

            # Filename
            filename = QLabel(os.path.basename(filepath)[:-4])

            # Custom text
            edit = QLineEdit()

            edit.setPlaceholderText("Custom Labels")

            edit.setText(
                self.main.plot_area.spectrum.datasets[filepath].text
            )

            # Save text when edited
            edit.editingFinished.connect(
                lambda filepath=filepath, edit=edit:
                    self._custom_text_changed(filepath, edit)
            )

            layout.addWidget(filename)
            layout.addWidget(edit)

            # Put widget inside QListWidget item
            self.files.addItem(item)
            self.files.setItemWidget(item, widget)

            # Give the item enough height
            item.setSizeHint(widget.sizeHint())
    def _custom_text_changed(self, filepath, edit):
        self.main.plot_area.spectrum.datasets[filepath].text = edit.text()+", "

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
        self.force_refresh = 1
        self._refresh()
        # self.main.plot_area.spectrum.update_groups()
        
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
        if self.force_refresh:
            self.main.plot_area.spectrum.update_groups()
            self.force_refresh = 0
        self.main.plot_area.spectrum.refresh_labels()
        event.accept()




























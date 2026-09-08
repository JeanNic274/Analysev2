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
        for attribute, var in [('Number','number'),('Name','name'),('Power',"power"), ('Position (x,y)',"pos"),('Positition (x,y,z)','posf'), ('Filter',"filter")]:
            checkbox = QCheckBox(attribute)

            checkbox.toggled.connect(
                lambda checked, attr=var:
                    self._checkbox_attribute_label_change(attr, checked)
            )
            if self.main.plot_area.spectrum.labels[var]:
                checkbox.setChecked(1)
            check_layout.addWidget(checkbox)


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
        
    def _checkbox_attribute_label_change(self,var,checked):
        self.main.plot_area.spectrum.labels[var] = checked

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
        if edit != "":
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



class TRPLFileManager(QDialog):

    def __init__(self, main_window):
        self.force_refresh=0
        super().__init__(main_window)

        self.main = main_window

        self.setWindowTitle("TRPL File Manager")
        self.resize(700, 500)



        self._build()
        self._refresh()


    def _build(self):

        layout = QVBoxLayout(self)

        # Files
        self.files = QListWidget()

        # Layouts
        file_layout = QVBoxLayout()
        file_layout.addWidget(self.files)
        
        check_layout = QHBoxLayout()
        for attribute, var in [('Number','number'),('Name','name'),('Power',"power"), ('Position (x,y)',"pos"),('Positition (x,y,z)','posf'), ('Filter',"filter")]:
            checkbox = QCheckBox(attribute)

            checkbox.toggled.connect(
                lambda checked, attr=var:
                    self._checkbox_attribute_label_change(attr, checked)
            )
            if self.main.plot_area.trpl.labels[var]:
                checkbox.setChecked(1)
            check_layout.addWidget(checkbox)


        lists = QHBoxLayout()
        lists.addLayout(file_layout)
        
        # Title
        qlab1 = QLabel('Curves label:')
        qlab1.setStyleSheet('font-size: 16pt;')
        # Title
        qlab2 = QLabel('Set zero (x offset in ns):')
        qlab2.setStyleSheet('font-size: 12pt;')
        
        layout.addWidget(qlab1)
        layout.addLayout(check_layout)
        layout.addWidget(qlab2)
        layout.addLayout(lists)
        
    def _checkbox_attribute_label_change(self,var,checked):
        self.main.plot_area.trpl.labels[var] = checked

    def _reset(self):
        print('WIP')
    
    def _refresh(self):
        self.files.clear()

        for filepath, dataset in self.main.datasets.items():
            if getattr(dataset, "measure_type", None) != "trpl":
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
                self.main.plot_area.trpl.datasets[filepath].text
            )

            # Save text when edited
            edit.editingFinished.connect(
                lambda filepath=filepath, edit=edit:
                    self._custom_text_changed(filepath, edit)
            )
            x_off = QLineEdit()
            x_off.setFixedWidth(50)
            x_off.setPlaceholderText("x")
            x_off.setText(
                str(self.main.plot_area.trpl.datasets[filepath].x_offset)
            )

            x_off.editingFinished.connect(
                lambda filepath=filepath, edit=x_off:
                    self._custom_number_changed(filepath, edit)
            )

            layout.addWidget(filename)
            layout.addWidget(x_off)
            layout.addWidget(edit)

            # Put widget inside QListWidget item
            self.files.addItem(item)
            self.files.setItemWidget(item, widget)

            # Give the item enough height
            item.setSizeHint(widget.sizeHint())
    def _custom_text_changed(self, filepath, edit):
        if edit != "":
            self.main.plot_area.trpl.datasets[filepath].text = edit.text()+", "
    def _custom_number_changed(self, filepath, edit):
        if edit != "":
            self.main.plot_area.trpl.datasets[filepath].x_offset = float(edit.text())
            self.main.plot_area.trpl.refresh_curves()
        
    def closeEvent(self, event):
        if self.force_refresh:
            # self.main.plot_area.trpl.refresh()
            # self.force_refresh = 0
            print('refresh curve WIP')
        self.main.plot_area.trpl.refresh_labels()
        event.accept()


class Experiment_Picker(QDialog):
    
    def __init__(self, main_window):
        self.path=""
        super().__init__(main_window)

        self.main = main_window

        self.setWindowTitle("Experiment Picker")
        self.resize(400, 500)

        self._build()
        self._refresh()


    def _build(self):

        layout = QVBoxLayout(self)

        # Files
        self.files = QListWidget()
        self.files.itemSelectionChanged.connect(self._on_change)
        
        # Title
        qlab1 = QLabel('Curves label:')
        qlab1.setStyleSheet('font-size: 12pt;')
        
        layout.addWidget(qlab1)
        layout.addWidget(self.files)


    def _refresh(self):
        self.files.clear()

        for filepath in os.listdir(os.path.join('data','experiments')):
            
            item=QListWidgetItem(os.path.basename(filepath))
            item.setData(Qt.UserRole,filepath)

            # Widget containing filename + text box
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(2, 2, 2, 2)

            # Filename
            filename = QLabel(os.path.basename(filepath))

       
            layout.addWidget(filename)

            # Put widget inside QListWidget item
            self.files.addItem(item)
            self.files.setItemWidget(item, widget)

            # Give the item enough height
            item.setSizeHint(widget.sizeHint())
            
    def _on_change(self):
        self.path = self.files.selectedItems()[0].data(Qt.UserRole)
        self.accept()






















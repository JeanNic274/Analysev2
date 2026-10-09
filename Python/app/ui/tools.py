from PySide6.QtWidgets import (
    QLineEdit, QWidget, QSpinBox, QVBoxLayout, QLabel, QComboBox
)
from PySide6.QtCore import Qt


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
        
        


class LabeledLineEdit(QWidget):
    def __init__(self, title="", parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.label = QLabel(title)
        self.label.setStyleSheet("font: 8pt;")
        self.line_edit = RevertableLineEdit()

        layout.addWidget(self.label)
        layout.addWidget(self.line_edit)
        self.text = self.line_edit.text
        
class NoScrollSpinBox(QSpinBox):
    def __init__(self):
        super().__init__()
        self.setKeyboardTracking(False)
    def wheelEvent(self, event):
        event.ignore()
        
        

class MyQComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()

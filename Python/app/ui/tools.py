from PySide6.QtWidgets import (
    QLineEdit, QWidget, QSpinBox, QVBoxLayout, QLabel, QComboBox, QHBoxLayout, QFrame, QApplication
)
from PySide6.QtCore import Qt, QSettings, QMimeData
from PySide6.QtGui import QDrag

def resize_table_to_contents(table):
    header_height = table.horizontalHeader().height()
    rows_height = sum(table.rowHeight(r) for r in range(table.rowCount()))
    frame = table.frameWidth() * 2
    total_height = header_height + rows_height + frame
    table.setFixedHeight(total_height)
    

class DraggableFrame(QFrame):
    def __init__(self, key, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._drag_start_pos = None
        self.key = key

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_pos is None:
            return super().mouseMoveEvent(event)

        if (event.position().toPoint() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return super().mouseMoveEvent(event)

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setData("application/x-frame-id", str(id(self)).encode())
        drag.setMimeData(mime_data)

        pixmap = self.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.position().toPoint())

        drag.exec(Qt.MoveAction)
        self._drag_start_pos = None
    
    
class ReorderableContainer(QWidget):
    def __init__(self, settings_key="frame_order"):
        super().__init__()
        self.setAcceptDrops(True)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setSpacing(10)
        self.settings_key = settings_key
        self.settings = QSettings("JN", "AnalyseV2-Sidebar")
        
    def add_frame(self, frame: DraggableFrame):
        self.layout_.addWidget(frame)

    def current_order(self):
        order = []
        for i in range(self.layout_.count()):
            w = self.layout_.itemAt(i).widget()
            if w is not None:
                order.append(w.key)
        return order

    def save_order(self):
        self.settings.setValue(self.settings_key, self.current_order())

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-frame-id"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        frame_id = int(bytes(event.mimeData().data("application/x-frame-id")).decode())
        dragged_widget = self._find_widget_by_id(frame_id)
        if dragged_widget is None:
            return

        drop_y = event.position().toPoint().y()
        target_index = self._index_for_y(drop_y, exclude=dragged_widget)

        current_index = self.layout_.indexOf(dragged_widget)
        self.layout_.removeWidget(dragged_widget)

        # adjust target index if removing shifted things
        if current_index < target_index:
            target_index -= 1

        self.layout_.insertWidget(target_index, dragged_widget)
        event.acceptProposedAction()
        self.save_order()

    def _find_widget_by_id(self, widget_id):
        for i in range(self.layout_.count()):
            w = self.layout_.itemAt(i).widget()
            if w is not None and id(w) == widget_id:
                return w
        return None

    def _index_for_y(self, y, exclude=None):
        for i in range(self.layout_.count()):
            w = self.layout_.itemAt(i).widget()
            if w is exclude or w is None:
                continue
            if y < w.geometry().center().y():
                return i
        return self.layout_.count()

    def restore_order(self):
        saved_order = self.settings.value(self.settings_key)
        if not saved_order:
            return  

        widgets_by_key = {}
        for i in range(self.layout_.count()):
            w = self.layout_.itemAt(i).widget()
            if w is not None:
                widgets_by_key[w.key] = w

        for w in widgets_by_key.values():
            self.layout_.removeWidget(w)

        for key in saved_order:
            if key in widgets_by_key:
                self.layout_.addWidget(widgets_by_key.pop(key))

        # if not in saved order
        for w in widgets_by_key.values():
            self.layout_.addWidget(w)
    
    
    
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
    def __init__(self, title="", parent=None, horizontal = False):
        super().__init__(parent)

        if horizontal:
            layout = QHBoxLayout(self)
        else:
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

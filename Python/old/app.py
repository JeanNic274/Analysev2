import sys
import numpy as np
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QListWidget, QSizePolicy
)
from PySide6.QtWidgets import (
    QTreeView, QLineEdit, QFileSystemModel
)
from PySide6.QtCore import QDir, Qt
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("My App")
        self.resize(1200, 800)

        # central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # --- LEFT SIDEBAR ---
        main_layout.addWidget(self.build_sidebar())

        # --- MIDDLE PLOT AREA ---
        plot_area = QWidget()
        plot_layout = QVBoxLayout(plot_area)
        plot_layout.setContentsMargins(0, 0, 0, 0)

        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.toolbar = NavigationToolbar(self.canvas, self)

        plot_layout.addWidget(self.toolbar)
        plot_layout.addWidget(self.canvas)

        # --- RIGHT TOOLBAR ---
        right_toolbar = QWidget()
        right_toolbar.setFixedWidth(150)
        right_layout = QVBoxLayout(right_toolbar)
        right_layout.setAlignment(Qt.AlignTop)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save)
        log_btn = QPushButton("Toggle Log")
        log_btn.clicked.connect(self.toggle_log)

        right_layout.addWidget(save_btn)
        right_layout.addWidget(log_btn)

        # assemble
        main_layout.addWidget(plot_area)
        main_layout.addWidget(right_toolbar)

        self.log = False

    def build_sidebar(self):
        sidebar = QWidget()
        sidebar.setFixedWidth(250)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(4, 4, 4, 4)
        sidebar_layout.setAlignment(Qt.AlignTop)

        # path input
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Enter path...")
        self.path_input.returnPressed.connect(self.set_path)
        sidebar_layout.addWidget(self.path_input)

        # file tree
        self.fs_model = QFileSystemModel()
        self.fs_model.setRootPath(QDir.homePath())
        self.fs_model.setNameFilters(["*.txt", "*.csv"])  # filter file types
        self.fs_model.setNameFilterDisables(False)  # hide non-matching files

        self.tree = QTreeView()
        self.tree.setModel(self.fs_model)
        self.tree.setRootIndex(self.fs_model.index(QDir.homePath()))
        self.tree.setSelectionMode(QTreeView.MultiSelection)
        self.tree.clicked.connect(self.on_file_clicked)

        # hide size, type, date columns — keep only name
        self.tree.hideColumn(1)
        self.tree.hideColumn(2)
        self.tree.hideColumn(3)

        sidebar_layout.addWidget(self.tree)

        # selected files label
        self.selected_label = QLabel("No files selected")
        self.selected_label.setWordWrap(True)
        sidebar_layout.addWidget(self.selected_label)

        # plot button
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)

        plot_btn = QPushButton("Plot")
        plot_btn.clicked.connect(self.plot)

        clear_btn = QPushButton("✕")
        clear_btn.setFixedWidth(30)
        clear_btn.clicked.connect(self.clear_selection)

        btn_layout.addWidget(plot_btn)
        btn_layout.addWidget(clear_btn)
        sidebar_layout.addWidget(btn_row)

        return sidebar

    def set_path(self):
        path = self.path_input.text()
        if QDir(path).exists():
            self.tree.setRootIndex(self.fs_model.index(path))
            self.fs_model.setRootPath(path)

    def on_file_clicked(self, index):
        path = self.fs_model.filePath(index)
        if self.fs_model.isDir(index):
            return  # ignore folders
        if path in self.selected_files:
            self.selected_files.remove(path)
        else:
            self.selected_files.append(path)
        self.update_selected_label()

    def clear_selection(self):
        self.selected_files = []
        self.tree.clearSelection()
        self.update_selected_label()

    def update_selected_label(self):
        if not self.selected_files:
            self.selected_label.setText("No files selected")
        else:
            names = [f.split("/")[-1] for f in self.selected_files]
            self.selected_label.setText(f"{len(names)} selected:\n" + "\n".join(names))


    def plot(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        x = np.linspace(0, 10, 100)
        ax.plot(x, np.sin(x))
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        self.canvas.draw()

    def toggle_log(self):
        self.log = not self.log
        for ax in self.figure.axes:
            ax.set_yscale("log" if self.log else "linear")
        self.canvas.draw()

    def save(self):
        self.figure.savefig("plot.png", dpi=150, bbox_inches="tight")
        print("Saved to plot.png")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
import numpy as np
import matplotlib
matplotlib.use("QtAgg")  # PySide6 works with the QtAgg backend

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import matplotlib.colors as mcolors
from matplotlib.patches import Circle

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
)



class MapPlot():
    def __init__(self,pat):
        super().__init__()

        np.random.seed(0)
        x = np.linspace(-3, 3, 200)
        y = np.linspace(-3, 3, 200)
        X, Y = np.meshgrid(x, y)
        data = (np.sin(X**2 + Y) * np.cos(Y**2 + X)) * 50 + 50

        self.plot_widget = DraggableColormapWidget(data, cmap_name="coolwarm")

        central = QWidget()
        outer_layout = QVBoxLayout(central)
        outer_layout.addWidget(self.plot_widget)

        controls = QHBoxLayout()
        info = QLabel("Drag the black dots on the strip to move each color's breakpoint.")
        reset_btn = QPushButton("Reset stops")
        reset_btn.clicked.connect(self.plot_widget.reset_stops)
        controls.addWidget(info)
        controls.addStretch()
        controls.addWidget(reset_btn)
        outer_layout.addLayout(controls)

        # self.setCentralWidget(central)
        # self.resize(650, 750)



class PiecewiseNorm(mcolors.Normalize):
    def __init__(self, stops, frac):
        self.stops = np.asarray(stops, dtype=float)
        self.frac = np.asarray(frac, dtype=float)
        super().__init__(vmin=self.stops[0], vmax=self.stops[-1], clip=True)

    def __call__(self, value, clip=None):
        data = np.ma.getdata(value) if np.ma.is_masked(value) else np.asarray(value)
        result = np.interp(data, self.stops, self.frac)
        return np.ma.masked_array(result)

    def inverse(self, value):
        return np.interp(value, self.frac, self.stops)


class DraggableColormapWidget(QWidget):
    def __init__(self, data, cmap_name="coolwarm", parent=None):
        super().__init__(parent)

        self.data = data
        self.cmap = matplotlib.colormaps[cmap_name]
        self.vmin, self.vmax = float(data.min()), float(data.max())

        self.stops = [self.vmin, (self.vmin + self.vmax) / 2, self.vmax]
        self.frac = [0.0, 0.5, 1.0]
        self.norm = PiecewiseNorm(self.stops, self.frac)

        # --- Matplotlib figure with two axes (image + strip) ---
        self.fig = Figure(figsize=(6, 6.5))
        self.canvas = FigureCanvasQTAgg(self.fig)

        self.ax_img = self.fig.add_axes([0.1, 0.28, 0.8, 0.65])
        self.ax_strip = self.fig.add_axes([0.1, 0.08, 0.8, 0.1])

        self.im = self.ax_img.imshow(
            self.data, cmap=self.cmap, norm=self.norm, origin="lower"
        )
        self.fig.colorbar(self.im, ax=self.ax_img, fraction=0.046, pad=0.04)
        self.ax_img.set_title("Drag markers below to move color stops")

        self.ax_strip.set_xlim(self.vmin, self.vmax)
        self.ax_strip.set_ylim(0, 1)
        self.ax_strip.set_yticks([])
        self.ax_strip.set_xlabel("data value")

        self.strip_img = self.ax_strip.imshow(
            self._strip_gradient(),
            aspect="auto",
            extent=[self.vmin, self.vmax, 0, 1],
            origin="lower",
        )

        self.labels = ["low", "mid", "high"]
        self.markers = []
        self.value_texts = []
        for s, lbl in zip(self.stops, self.labels):
            c = Circle(
                (s, 0.5),
                radius=(self.vmax - self.vmin) * 0.015,
                color="black",
                zorder=5,
                picker=True,
            )
            self.ax_strip.add_patch(c)
            self.markers.append(c)
            self.ax_strip.annotate(lbl, (s, 1.2), ha="center", fontsize=8, annotation_clip=False)
            t = self.ax_strip.text(s, -0.6, f"{s:.1f}", ha="center", fontsize=8)
            self.value_texts.append(t)

        self._dragging_index = None
        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_release_event", self._on_release)

        # --- Layout ---
        layout = QVBoxLayout(self)
        layout.addWidget(self.canvas)

    # -- helpers -----------------------------------------------------
    def _strip_gradient(self):
        vals = np.linspace(self.vmin, self.vmax, 256)
        t = np.interp(vals, self.stops, self.frac)
        return self.cmap(t).reshape(1, -1, 4)

    def _redraw(self):
        order = np.argsort(self.stops)
        sorted_stops = [self.stops[i] for i in order]
        sorted_frac = [self.frac[i] for i in order]

        self.norm.stops = np.asarray(sorted_stops, dtype=float)
        self.norm.frac = np.asarray(sorted_frac, dtype=float)

        self.im.set_norm(self.norm)
        self.strip_img.set_data(self._strip_gradient())

        for i, m in enumerate(self.markers):
            m.center = (self.stops[i], 0.5)
            self.value_texts[i].set_position((self.stops[i], -0.6))
            self.value_texts[i].set_text(f"{self.stops[i]:.1f}")

        self.canvas.draw_idle()

    # -- mouse events --------------------------------------------------
    def _on_press(self, event):
        if event.inaxes != self.ax_strip:
            return
        for i, m in enumerate(self.markers):
            contains, _ = m.contains(event)
            if contains:
                self._dragging_index = i
                return

    def _on_motion(self, event):
        i = self._dragging_index
        if i is None or event.inaxes != self.ax_strip or event.xdata is None:
            return
        self.stops[i] = float(np.clip(event.xdata, self.vmin, self.vmax))
        self._redraw()

    def _on_release(self, event):
        self._dragging_index = None

    def reset_stops(self):
        self.stops = [self.vmin, (self.vmin + self.vmax) / 2, self.vmax]
        self.frac = [0.0, 0.5, 1.0]
        self._redraw()

from datetime import timezone
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton,
    QColorDialog, QLineEdit, QLabel,
)
from PySide6.QtGui import QColor
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from matplotlib.dates import AutoDateLocator, ConciseDateFormatter


class PlotDetailWindow(QDialog):
    def __init__(self, time_data, param_data, param_name, param_label, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'{param_label} vs Time')
        self.resize(900, 600)
        self.time_data, self.param_data = time_data, param_data
        self.param_name, self.param_label = param_name, param_label
        self.show_markers = False
        self.plot_color = '#2E86AB'
        self.custom_title = f'{param_label} vs Time'
        self.show_title = True
        layout = QVBoxLayout(self)
        self.figure = Figure(figsize=(10, 6), layout='constrained')
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        layout.addWidget(self.toolbar)
        controls = QHBoxLayout()
        self.marker_checkbox = QCheckBox('Show Markers')
        self.marker_checkbox.toggled.connect(self._toggle_markers)
        controls.addWidget(self.marker_checkbox)
        self.color_button = QPushButton('Select Color')
        self.color_button.clicked.connect(self._select_color)
        controls.addWidget(self.color_button)
        controls.addWidget(QLabel('Title:'))
        self.title_input = QLineEdit(self.custom_title)
        self.title_input.setMaximumWidth(250)
        self.title_input.textChanged.connect(self._update_title)
        controls.addWidget(self.title_input)
        self.title_checkbox = QCheckBox('Show Title')
        self.title_checkbox.setChecked(True)
        self.title_checkbox.toggled.connect(self._toggle_title)
        controls.addWidget(self.title_checkbox)
        controls.addStretch()
        layout.addLayout(controls)
        layout.addWidget(self.canvas)
        self.ax = self.figure.add_subplot(111)
        self.line, = self.ax.plot(time_data, param_data, linewidth=1.5, color=self.plot_color,
                                 markersize=4, markeredgecolor='white', markeredgewidth=0.5)
        self.ax.set_xlabel('Time (UTC)')
        self.ax.set_ylabel(param_label)
        locator = AutoDateLocator(minticks=3, maxticks=10, tz=timezone.utc)
        self.ax.xaxis.set_major_locator(locator)
        self.ax.xaxis.set_major_formatter(ConciseDateFormatter(locator, tz=timezone.utc))
        self.ax.grid(True, alpha=0.3, linestyle='--')
        self._plot_data()

    def _toggle_markers(self, checked):
        self.show_markers = bool(checked)
        self._plot_data()

    def _select_color(self):
        color = QColorDialog.getColor(QColor(self.plot_color), self, 'Select Plot Color')
        if color.isValid():
            self.plot_color = color.name()
            self._plot_data()

    def _update_title(self, text):
        self.custom_title = text
        self._plot_data()

    def _toggle_title(self, checked):
        self.show_title = bool(checked)
        self._plot_data()

    def _plot_data(self):
        self.line.set_color(self.plot_color)
        self.line.set_markerfacecolor(self.plot_color)
        self.line.set_marker('o' if self.show_markers else '')
        self.ax.set_title(self.custom_title if self.show_title else '', fontweight='bold')
        self.canvas.draw_idle()

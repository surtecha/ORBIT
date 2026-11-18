from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QGridLayout, QScrollArea
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from ui.dialogs.plot_detail_window import PlotDetailWindow
from ui.tabs.tabular_tab import COLUMN_HEADERS


class PlotWidget(QScrollArea):
    def __init__(self, dataframe):
        super().__init__()
        frame = dataframe.sort_values('time', kind='stable').reset_index(drop=True)
        self.setWidgetResizable(True)
        content = QWidget()
        layout = QGridLayout(content)
        layout.setSpacing(10)
        self.previews = []
        for index, parameter in enumerate(column for column in frame if column != 'time'):
            preview = _create_preview_plot(frame['time'], frame[parameter], parameter,
                                           COLUMN_HEADERS.get(parameter, parameter))
            self.previews.append(preview)
            layout.addWidget(preview, index // 3, index % 3)
        self.setWidget(content)

    def cleanup(self):
        for preview in self.previews:
            preview.canvas.mpl_disconnect(preview.connection)
            preview.canvas.figure.clear()
        self.previews.clear()
        for dialog in self.findChildren(PlotDetailWindow):
            dialog.reject()


def create_plot_widget(dataframe):
    return PlotWidget(dataframe)


def _create_preview_plot(time_data, param_data, param_name, param_label):
    container = QWidget()
    container.setMinimumSize(300, 200)
    container.setCursor(Qt.CursorShape.PointingHandCursor)
    layout = QGridLayout(container)
    layout.setContentsMargins(5, 5, 5, 5)
    figure = Figure(figsize=(3, 2), layout='constrained')
    canvas = FigureCanvas(figure)
    canvas.setCursor(Qt.CursorShape.PointingHandCursor)
    ax = figure.add_subplot(111)
    ax.plot(time_data, param_data, linewidth=1, color='#2E86AB')
    ax.set_title(param_label, fontsize=9, fontweight='bold')
    ax.tick_params(axis='x', labelbottom=False, length=0)
    ax.tick_params(axis='y', labelsize=7)
    ax.grid(True, alpha=0.2, linestyle='--')
    layout.addWidget(canvas)

    def on_click(event):
        if event.button == 1:
            _open_detail_window(time_data, param_data, param_name, param_label, container)

    container.canvas = canvas
    container.connection = canvas.mpl_connect('button_press_event', on_click)
    canvas.draw_idle()
    return container


def _open_detail_window(time_data, param_data, param_name, param_label, parent):
    dialog = PlotDetailWindow(time_data, param_data, param_name, param_label, parent)
    try:
        dialog.exec()
    finally:
        dialog.deleteLater()

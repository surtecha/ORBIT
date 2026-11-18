from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QMenu, QScrollArea, QFrame
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QFont, QPalette


class Sidebar(QWidget):
    rename_requested = Signal(str)
    duplicate_requested = Signal(str)
    table_requested = Signal(str)
    plot_requested = Signal(str)
    propagate_requested = Signal(str)
    ground_trace_requested = Signal(str)
    delete_requested = Signal(str)
    export_csv_requested = Signal(str)
    export_tle_requested = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.setFixedWidth(250)
        layout = QVBoxLayout(self)
        header = QLabel('Objects')
        header.setFont(QFont('Arial', 14, QFont.Weight.Bold))
        layout.addWidget(header)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        self.items_layout = QVBoxLayout(content)
        self.items_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(5)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        self.satellite_labels = {}
        self.selected_id = None

    def add_satellite_item(self, satellite_id, display_name):
        if satellite_id in self.satellite_labels:
            self.update_satellite_name(satellite_id, display_name)
            return
        label = QLabel(str(display_name))
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setToolTip(str(display_name))
        label.setFont(QFont('Arial', 13))
        label.setCursor(Qt.CursorShape.PointingHandCursor)
        label.setStyleSheet('padding: 8px; border-radius: 3px;')
        label.mousePressEvent = lambda event: self._select_satellite(satellite_id)
        label.mouseDoubleClickEvent = lambda event: self.table_requested.emit(satellite_id) if event.button() == Qt.MouseButton.LeftButton else None
        label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        label.customContextMenuRequested.connect(lambda point: self._show_context_menu(satellite_id))
        self.items_layout.addWidget(label)
        self.satellite_labels[satellite_id] = label

    def _select_satellite(self, satellite_id):
        if satellite_id not in self.satellite_labels:
            return
        if self.selected_id in self.satellite_labels:
            self.satellite_labels[self.selected_id].setStyleSheet('padding: 8px; border-radius: 3px;')
        self.selected_id = satellite_id
        palette = self.palette()
        background = palette.color(QPalette.ColorRole.Highlight).name()
        foreground = palette.color(QPalette.ColorRole.HighlightedText).name()
        self.satellite_labels[satellite_id].setStyleSheet(
            f'padding: 8px; border-radius: 3px; background-color: {background}; color: {foreground};')

    def update_satellite_name(self, satellite_id, new_name):
        label = self.satellite_labels.get(satellite_id)
        if label is not None:
            label.setText(new_name)
            label.setToolTip(new_name)

    def remove_satellite_item(self, satellite_id):
        label = self.satellite_labels.pop(satellite_id, None)
        if label is not None:
            self.items_layout.removeWidget(label)
            label.deleteLater()
        if self.selected_id == satellite_id:
            self.selected_id = None

    def get_satellite_name(self, satellite_id):
        label = self.satellite_labels.get(satellite_id)
        return label.text() if label is not None else ''

    def _show_context_menu(self, satellite_id):
        self._select_satellite(satellite_id)
        menu = QMenu(self)
        actions = {}
        for label, signal in (('Table', self.table_requested), ('Plot', self.plot_requested),
                              ('Propagate', self.propagate_requested), ('Ground Trace', self.ground_trace_requested)):
            actions[menu.addAction(label)] = lambda selected=signal: selected.emit(satellite_id)
        menu.addSeparator()
        actions[menu.addAction('Rename')] = lambda: self.rename_requested.emit(satellite_id)
        menu.addSeparator()
        actions[menu.addAction('Export as CSV')] = lambda: self.export_csv_requested.emit(satellite_id)
        submenu = menu.addMenu('Export as TLE')
        for extension in ('.tle', '.txt'):
            actions[submenu.addAction(f'Export as {extension}')] = lambda suffix=extension: self.export_tle_requested.emit(satellite_id, suffix)
        menu.addSeparator()
        delete_action = menu.addAction('Delete')
        font = delete_action.font()
        font.setBold(True)
        delete_action.setFont(font)
        actions[delete_action] = lambda: self.delete_requested.emit(satellite_id)
        action = menu.exec(QCursor.pos())
        if action in actions:
            actions[action]()
        menu.deleteLater()

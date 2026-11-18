import numbers
import numpy as np
import pandas as pd
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QTableView, QHeaderView, QApplication
from backend.controllers.propagator_controller import format_utc_time


COLUMN_HEADERS = {
    'time': 'Epoch (UTC)', 'a': 'Semi Major Axis (km)', 'apogee': 'Apogee (km)',
    'perigee': 'Perigee (km)', 'e': 'Eccentricity', 'i': 'Inclination (deg)',
    'raan': 'RAAN (deg)', 'aop': 'Arg of Perigee (deg)', 'ma': 'Mean Anomaly (deg)',
    'bstar': 'B-Star', 'mean_motion': 'Mean Motion (rev/day)',
    'mean_motion_derivative': 'Mean Motion Deriv (rev/day²)', 'revolution_number': 'Revolution Number',
}


class SatelliteTableModel(QAbstractTableModel):
    def __init__(self, dataframe, parent=None):
        super().__init__(parent)
        self.dataframe = dataframe.copy().reset_index(drop=True)
        if 'time' in self.dataframe:
            self.dataframe['time'] = pd.to_datetime(self.dataframe['time'], utc=True)
        self.columns = list(self.dataframe.columns)
        self._order = np.arange(len(self.dataframe))

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._order)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._order) or not 0 <= index.column() < len(self.columns):
            return None
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter
        if role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return None
        value = self.dataframe.iat[int(self._order[index.row()]), index.column()]
        if pd.isna(value):
            return ''
        column = self.columns[index.column()]
        if column == 'time':
            return format_utc_time(value)
        if isinstance(value, numbers.Integral):
            return str(int(value))
        if isinstance(value, numbers.Real):
            if role == Qt.ItemDataRole.ToolTipRole:
                return repr(float(value))
            return format(float(value), '.12g')
        return str(value)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return COLUMN_HEADERS.get(self.columns[section], self.columns[section])
        return str(section + 1)

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        if not 0 <= column < len(self.columns):
            return
        ascending = order == Qt.SortOrder.AscendingOrder
        series = self.dataframe.iloc[self._order, column]
        sorted_indices = series.sort_values(ascending=ascending, kind='stable', na_position='last').index
        self.beginResetModel()
        self._order = sorted_indices.to_numpy()
        self.endResetModel()


class SatelliteTableView(QTableView):
    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            indexes = self.selectedIndexes()
            if indexes:
                cells = {(index.row(), index.column()): str(index.data() or '') for index in indexes}
                rows, columns = zip(*cells)
                text = '\n'.join('\t'.join(cells.get((row, column), '') for column in range(min(columns), max(columns) + 1))
                                 for row in range(min(rows), max(rows) + 1))
                QApplication.clipboard().setText(text)
            event.accept()
        else:
            super().keyPressEvent(event)


def create_tabular_widget(dataframe):
    table = SatelliteTableView()
    model = SatelliteTableModel(dataframe, table)
    table.setModel(model)
    table.setAlternatingRowColors(True)
    table.setSortingEnabled(True)
    if 'time' in model.columns:
        table.sortByColumn(model.columns.index('time'), Qt.SortOrder.AscendingOrder)
    header = table.horizontalHeader()
    header.setResizeContentsPrecision(200)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    table.resizeColumnsToContents()
    return table

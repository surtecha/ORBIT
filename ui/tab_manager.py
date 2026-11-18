from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from ui.tabs.tabular_tab import create_tabular_widget
from ui.tabs.plot_tab import create_plot_widget


class TabManager(QWidget):
    TAB_ICONS = {'Tabular': '🗒️', 'Plotting': '📈', 'Propagation': '🌏', 'Ground Trace': '🛰️'}

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._close_tab)
        self.tab_widget.currentChanged.connect(self._on_current_changed)
        layout.addWidget(self.tab_widget)
        self.tabs = {}

    def _create_tab(self, satellite_id, name, kind, factory, *args):
        key = f'{satellite_id}-{kind}'
        if key in self.tabs:
            self.tab_widget.setCurrentWidget(self.tabs[key]['widget'])
            return
        widget = factory(*args)
        self.tabs[key] = {'widget': widget, 'satellite_id': satellite_id, 'type': kind}
        self.tab_widget.addTab(widget, f'{self.TAB_ICONS[kind]} {name}')
        self.tab_widget.setCurrentWidget(widget)

    def create_tabular_tab(self, satellite_id, name, dataframe):
        self._create_tab(satellite_id, name, 'Tabular', create_tabular_widget, dataframe)

    def create_plot_tab(self, satellite_id, name, dataframe):
        self._create_tab(satellite_id, name, 'Plotting', create_plot_widget, dataframe)

    def create_propagator_tab(self, satellite_id, name, propagation_data, propagator_controller):
        from ui.tabs.propagator_tab import create_propagator_widget
        self._create_tab(satellite_id, name, 'Propagation', create_propagator_widget, propagation_data, propagator_controller)

    def create_ground_trace_tab(self, satellite_id, name, ground_trace_data, ground_trace_controller):
        from ui.tabs.ground_trace_tab import create_ground_trace_widget
        self._create_tab(satellite_id, name, 'Ground Trace', create_ground_trace_widget, ground_trace_data, ground_trace_controller)

    def _close_tab(self, index):
        widget = self.tab_widget.widget(index)
        if widget is None:
            return
        key = next((key for key, entry in self.tabs.items() if entry['widget'] is widget), None)
        if key is not None:
            del self.tabs[key]
        if hasattr(widget, 'cleanup'):
            widget.cleanup()
        self.tab_widget.removeTab(index)
        widget.close()
        widget.deleteLater()

    def close_tabs_for_satellite(self, satellite_id):
        for entry in list(self.tabs.values()):
            if entry['satellite_id'] == satellite_id:
                self._close_tab(self.tab_widget.indexOf(entry['widget']))

    def close_all(self):
        while self.tab_widget.count():
            self._close_tab(0)

    def update_tab_names(self, satellite_id, new_name):
        for entry in self.tabs.values():
            if entry['satellite_id'] == satellite_id:
                widget = entry['widget']
                index = self.tab_widget.indexOf(widget)
                self.tab_widget.setTabText(index, f"{self.TAB_ICONS[entry['type']]} {new_name}")
                if hasattr(widget, 'set_satellite_name'):
                    widget.set_satellite_name(new_name)

    def _on_current_changed(self, index):
        current = self.tab_widget.widget(index)
        for entry in self.tabs.values():
            widget = entry['widget']
            if widget is not current and hasattr(widget, 'pause'):
                widget.pause()

from PyQt6.QtWidgets import QScrollArea, QWidget, QVBoxLayout


class PlotScrollArea(QScrollArea):
    def __init__(self):
        super().__init__()

        self.setWidgetResizable(True)

        self.container = QWidget()
        self.vbox = QVBoxLayout(self.container)
        self.vbox.addStretch()

        self.setWidget(self.container)

    def clear_plots(self):
        while self.vbox.count() > 1:  # keep stretch
            item = self.vbox.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def add_plot(self, plot_widget):
        self.vbox.insertWidget(self.vbox.count() - 1, plot_widget)

    def move_widget_up(self, widget):
        idx = self.vbox.indexOf(widget)
        if idx > 0:
            self.vbox.removeWidget(widget)
            self.vbox.insertWidget(idx - 1, widget)

    def move_widget_down(self, widget):
        idx = self.vbox.indexOf(widget)
        if idx < self.vbox.count() - 2:  # last is stretch
            self.vbox.removeWidget(widget)
            self.vbox.insertWidget(idx + 1, widget)

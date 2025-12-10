from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton
from PyQt6.QtCore import pyqtSignal
import pyqtgraph as pg

class PlotRowWidget(QWidget):
    moved_up = pyqtSignal(object)
    moved_down = pyqtSignal(object)

    def __init__(self, signal_name, parent=None):
        super().__init__(parent)
        self.signal_name = signal_name
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        # ---- Arrow buttons ----
        btn_layout = QVBoxLayout()
        self.up_btn = QPushButton("▲")
        self.down_btn = QPushButton("▼")

        self.up_btn.clicked.connect(lambda: self.moved_up.emit(self))
        self.down_btn.clicked.connect(lambda: self.moved_down.emit(self))

        btn_layout.addWidget(self.up_btn)
        btn_layout.addWidget(self.down_btn)
        btn_layout.addStretch()

        # ---- PyQtGraph Plot ----
        self.plot_widget = pg.PlotWidget()
        self.plot_item = self.plot_widget.plot([], [])
        self.plot_widget.setLabel('left', signal_name)
        self.plot_widget.setLabel('bottom', 'Time', units='s')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)

        layout.addLayout(btn_layout)
        layout.addWidget(self.plot_widget)

    def plot(self, time, values):
        self.plot_item.setData(time, values)  # fast!

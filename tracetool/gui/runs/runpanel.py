from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
)


class RunSelectorPanel(QWidget):
    run_changed = pyqtSignal(int)  # emits new run index

    def __init__(self, runs):
        super().__init__()
        self.runs = runs
        self.index = 0

        layout = QVBoxLayout(self)

        # ---- Run dropdown ----
        self.dropdown = QComboBox()
        for i, run in enumerate(runs):
            self.dropdown.addItem(f"Run {i+1}")
        self.dropdown.currentIndexChanged.connect(self.on_select)

        # ---- Prev/Next ----
        btn_layout = QHBoxLayout()
        self.prev_btn = QPushButton("Previous run")
        self.next_btn = QPushButton("Next run")
        self.prev_btn.clicked.connect(self.prev_run)
        self.next_btn.clicked.connect(self.next_run)
        btn_layout.addWidget(self.prev_btn)
        btn_layout.addWidget(self.next_btn)

        # ---- Metadata table ----
        self.meta = QTableWidget()
        self.meta.setColumnCount(2)
        self.meta.setHorizontalHeaderLabels(["Field", "Value"])
        self.meta.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(self.dropdown)
        layout.addLayout(btn_layout)
        layout.addWidget(self.meta)

        self.refresh_metadata(0)

    def on_select(self, idx):
        self.index = idx
        self.refresh_metadata(idx)
        self.run_changed.emit(idx)

    def prev_run(self):
        if self.index > 0:
            self.dropdown.setCurrentIndex(self.index - 1)

    def next_run(self):
        if self.index < len(self.runs) - 1:
            self.dropdown.setCurrentIndex(self.index + 1)

    def refresh_metadata(self, idx):
        run = self.runs[idx].metadata
        self.meta.setRowCount(len(run))
        for row, (k, v) in enumerate(run.items()):
            self.meta.setItem(row, 0, QTableWidgetItem(k))
            self.meta.setItem(row, 1, QTableWidgetItem(str(v)))

# plot_window.py
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QScrollArea,
)
from PyQt6.QtCore import pyqtSignal
import pyqtgraph as pg


class PlotRow(QWidget):
    moved_up = pyqtSignal(object)
    moved_down = pyqtSignal(object)

    def __init__(self, signal_name):
        super().__init__()
        self.signal_name = signal_name

        layout = QHBoxLayout(self)

        # arrows
        arrow_col = QVBoxLayout()
        btn_up = QPushButton("▲")
        btn_down = QPushButton("▼")
        btn_up.clicked.connect(lambda: self.moved_up.emit(self))
        btn_down.clicked.connect(lambda: self.moved_down.emit(self))
        arrow_col.addWidget(btn_up)
        arrow_col.addWidget(btn_down)
        arrow_col.addStretch()

        # plot
        self.plot_widget = pg.PlotWidget()
        self.plot_item = self.plot_widget.plot([], [])
        self.plot_widget.setLabel("left", signal_name)
        self.plot_widget.showGrid(x=True, y=True)

        layout.addLayout(arrow_col)
        layout.addWidget(self.plot_widget)

    def update_data(self, t, y):
        self.plot_item.setData(t, y)


class PlotWindow(QWidget):
    """A self-contained plot viewer with:
    - run selector
    - scrollable plots
    - reorder arrows
    """

    def __init__(self, run_objects, selected_cols):
        super().__init__()
        self.runs = run_objects
        self.selected_cols = selected_cols
        self.plot_widgets = []

        main_layout = QVBoxLayout(self)

        # ----------------------------
        # Run selector UI
        # ----------------------------
        run_row = QHBoxLayout()
        self.run_label = QLabel(f"Run: 1 / {len(self.runs)}")

        btn_prev = QPushButton("Prev")
        btn_next = QPushButton("Next")
        self.run_dropdown = QComboBox()

        for i, r in enumerate(self.runs):
            r_meta = r.metadata
            r_parts = [f"{key.capitalize()}: {value}" for key, value in r_meta.items()]
            r_string = " | ".join(r_parts)
            self.run_dropdown.addItem(r_string, i)

        btn_prev.clicked.connect(self.prev_run)
        btn_next.clicked.connect(self.next_run)
        self.run_dropdown.currentIndexChanged.connect(self.update_plots)

        run_row.addWidget(btn_prev)
        run_row.addWidget(btn_next)
        run_row.addWidget(self.run_dropdown)
        run_row.addWidget(self.run_label)
        main_layout.addLayout(run_row)

        # ----------------------------
        # Scrollable plot area
        # ----------------------------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        scroll.setWidget(self.scroll_widget)

        main_layout.addWidget(scroll)

        # Build plot widgets
        self.build_plot_list()
        self.update_plots(0)

    # ----------------------------------
    # Build plot list
    # ----------------------------------
    def build_plot_list(self):
        for w in self.plot_widgets:
            w.deleteLater()
        self.plot_widgets = []

        for modality, cols in self.selected_cols.items():
            for col in cols:
                w = PlotRow(f"{modality}: {col}")
                w.moved_up.connect(self.move_up)
                w.moved_down.connect(self.move_down)
                self.scroll_layout.addWidget(w)
                self.plot_widgets.append(w)

        self.scroll_layout.addStretch()
        self.relink_x_axes()

    # ----------------------------------
    # Ordering
    # ----------------------------------

    def move_up(self, widget):
        i = self.scroll_layout.indexOf(widget)
        if i > 0:
            self.scroll_layout.removeWidget(widget)
            self.scroll_layout.insertWidget(i - 1, widget)

            # reorder internal list too
            j = self.plot_widgets.index(widget)
            self.plot_widgets.insert(j-1, self.plot_widgets.pop(j))

            # NEW
            self.relink_x_axes()

    def move_down(self, widget):
        i = self.scroll_layout.indexOf(widget)
        if i < self.scroll_layout.count() - 2:
            self.scroll_layout.removeWidget(widget)
            self.scroll_layout.insertWidget(i + 1, widget)

            j = self.plot_widgets.index(widget)
            self.plot_widgets.insert(j+1, self.plot_widgets.pop(j))

            # NEW
            self.relink_x_axes()


    # ----------------------------------
    # Run navigation
    # ----------------------------------
    def prev_run(self):
        idx = self.run_dropdown.currentIndex()
        if idx > 0:
            self.run_dropdown.setCurrentIndex(idx - 1)

    def next_run(self):
        idx = self.run_dropdown.currentIndex()
        if idx < len(self.runs) - 1:
            self.run_dropdown.setCurrentIndex(idx + 1)

    # ----------------------------------
    # Plot updating
    # ----------------------------------
    def update_plots(self, idx):
        run = self.runs[idx]
        self.run_label.setText(f"Run: {idx+1} / {len(self.runs)}")

        # Walk through selected columns & plot widgets together
        k = 0
        for modality, cols in self.selected_cols.items():
            for col in cols:
                time, y = run.get_signal(modality, col)  # your run API
                self.plot_widgets[k].update_data(time, y)
                k += 1

        self.relink_x_axes()

    
    # ----------------------------------
    # X-axis linking for zoom/pan sync
    # ----------------------------------
    def relink_x_axes(self):
        if not self.plot_widgets:
            return

        master = self.plot_widgets[0].plot_widget

        for w in self.plot_widgets[1:]:
            w.plot_widget.setXLink(master)


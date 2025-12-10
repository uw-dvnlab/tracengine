# main_gui.py
import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QToolBar,
    QFileDialog,
    QDialog,
    QVBoxLayout,
    QCheckBox,
    QPushButton,
    QLabel,
    QScrollArea,
    QWidget,
)
from PyQt6.QtGui import QAction
from tracetool.data.loader import load_session, get_modality_columns
from plot_window import PlotWindow  # add this


class ColumnSelectorDialog(QDialog):
    def __init__(self, run_objects):
        super().__init__()
        self.setWindowTitle("Select Signals to Plot")
        self.run_objects = run_objects
        self.selected_columns = {}

        layout = QVBoxLayout()

        # Scroll area for many modalities
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # Assume single run for now (can extend later)
        run = run_objects[0]
        modality_dict = get_modality_columns(run)

        self.checkboxes = {}

        for modality, columns in modality_dict.items():
            scroll_layout.addWidget(QLabel(f"<b>{modality}</b>"))
            for col in columns:
                cb = QCheckBox(col)
                scroll_layout.addWidget(cb)
                self.checkboxes[(modality, col)] = cb

        scroll.setWidgetResizable(True)
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        # OK button
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.on_ok)
        layout.addWidget(ok_btn)

        self.setLayout(layout)

    def on_ok(self):
        selections = {}
        for (mod, col), cb in self.checkboxes.items():
            if cb.isChecked():
                selections.setdefault(mod, []).append(col)
        print("Selected columns:", selections)
        self.selected_columns = selections
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Multimodal Annotator")
        self.resize(600, 400)

        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)

        load_action = QAction("Load Session", self)
        load_action.triggered.connect(self.load_session)
        toolbar.addAction(load_action)

        self.run_objects = []

    # def load_session(self):
    #     folder = QFileDialog.getExistingDirectory(self, "Select Session Folder")
    #     if folder:
    #         session_path = Path(folder)
    #         self.run_objects = load_session(session_path)

    #         if not self.run_objects:
    #             print("No runs found!")
    #             return

    #         dlg = ColumnSelectorDialog(self.run_objects)
    #         dlg.exec()
    def load_session(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Session Folder")
        if folder:
            session_path = Path(folder)
            self.run_objects = load_session(session_path)

            if not self.run_objects:
                print("No runs found!")
                return

            dlg = ColumnSelectorDialog(self.run_objects)
            if dlg.exec():
                selected = dlg.selected_columns

                # -----------------------------
                # Create the PyQtGraph plot UI
                # -----------------------------
                self.plot_window = PlotWindow(self.run_objects, selected)
                self.setCentralWidget(self.plot_window)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

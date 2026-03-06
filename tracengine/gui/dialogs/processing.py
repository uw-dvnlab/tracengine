from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QPushButton,
    QStackedWidget,
    QWidget,
    QFormLayout,
    QCheckBox,
)

from tracengine.processing.registry import get_all_processors


class DerivativeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compute Derivative")
        self.setFixedWidth(300)

        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.spin_order = QSpinBox()
        self.spin_order.setRange(1, 3)
        self.spin_order.setValue(1)
        form.addRow("Order (1=Vel, 2=Acc):", self.spin_order)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_apply = QPushButton("Apply")
        btn_apply.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_apply)

        layout.addLayout(btn_layout)

    def get_params(self):
        return {"order": self.spin_order.value()}


class FilterDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Apply Filter")
        self.setFixedWidth(350)

        layout = QVBoxLayout(self)

        # Load processors
        self.processors = get_all_processors()
        self.processor_widgets = {}  # {proc_name: {param_name: widget}}

        # Filter Type Selector
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Filter Type:"))
        self.combo_type = QComboBox()

        for proc in self.processors:
            display_name = getattr(proc, "description", proc.name)
            self.combo_type.addItem(display_name, proc.name)

        self.combo_type.currentIndexChanged.connect(self._on_type_changed)
        type_layout.addWidget(self.combo_type)

        layout.addLayout(type_layout)

        # Stacked Widget for Parameters
        self.stack = QStackedWidget()

        for proc in self.processors:
            page = QWidget()
            form = QFormLayout(page)

            param_widgets = {}
            params = proc.get_parameters()

            for p in params:
                p_name = p["name"]
                p_label = p.get("label", p_name)
                p_type = p.get("type", "str")
                p_default = p.get("default")

                widget = None

                if p_type == "int":
                    widget = QSpinBox()
                    if "min" in p:
                        widget.setMinimum(p["min"])
                    if "max" in p:
                        widget.setMaximum(p["max"])
                    if "step" in p:
                        widget.setSingleStep(p["step"])
                    if p_default is not None:
                        widget.setValue(p_default)
                    if "suffix" in p:
                        widget.setSuffix(p["suffix"])

                elif p_type == "float":
                    widget = QDoubleSpinBox()
                    if "min" in p:
                        widget.setMinimum(p["min"])
                    if "max" in p:
                        widget.setMaximum(p["max"])
                    if "step" in p:
                        widget.setSingleStep(p["step"])
                    if p_default is not None:
                        widget.setValue(p_default)
                    if "suffix" in p:
                        widget.setSuffix(p["suffix"])
                    widget.setDecimals(2)  # Default reasonable decimals

                elif p_type == "bool":
                    widget = QCheckBox()
                    if p_default is not None:
                        widget.setChecked(p_default)

                if widget:
                    form.addRow(f"{p_label}:", widget)
                    param_widgets[p_name] = widget

            self.processor_widgets[proc.name] = param_widgets
            self.stack.addWidget(page)

        layout.addWidget(self.stack)

        # Common settings
        self.chk_interpolate = QCheckBox("Interpolate Missing Values")
        layout.addWidget(self.chk_interpolate)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_apply = QPushButton("Apply")
        btn_apply.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_apply)

        layout.addLayout(btn_layout)

        # Trigger initial selection
        if self.processors:
            self._on_type_changed(0)

    def _on_type_changed(self, idx):
        self.stack.setCurrentIndex(idx)

    def get_params(self):
        idx = self.combo_type.currentIndex()
        if idx < 0:
            return {}

        proc_name = self.combo_type.currentData()

        params = {"filter_type": proc_name}

        # Get processor specific params
        widgets = self.processor_widgets.get(proc_name, {})
        for p_name, widget in widgets.items():
            val = None
            if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                val = widget.value()
            elif isinstance(widget, QCheckBox):
                val = widget.isChecked()

            if val is not None:
                params[p_name] = val

        # add interpolate missing values flag
        params["interpolate_missing"] = self.chk_interpolate.isChecked()

        return params


class AverageChannelsDialog(QDialog):
    """Dialog for creating an averaged channel from multiple selected channels."""

    def __init__(self, channel_names: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Average Channels")
        self.setFixedWidth(350)

        layout = QVBoxLayout(self)

        # Show what will be averaged
        layout.addWidget(QLabel("<b>Averaging channels:</b>"))
        for name in channel_names:
            layout.addWidget(QLabel(f"  • {name}"))

        layout.addSpacing(10)

        # Output name
        form = QFormLayout()
        from PyQt6.QtWidgets import QLineEdit

        self.txt_name = QLineEdit()
        # Suggest a default name
        if channel_names:
            # Try to extract common prefix
            parts = [n.split(":")[-1] for n in channel_names]
            self.txt_name.setText("average_" + "_".join(parts[:2]))
        form.addRow("Output Name:", self.txt_name)
        layout.addLayout(form)

        # Interpolate option
        self.chk_interpolate = QCheckBox("Interpolate Missing Values")
        self.chk_interpolate.setChecked(True)
        layout.addWidget(self.chk_interpolate)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_apply = QPushButton("Create")
        btn_apply.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_apply)

        layout.addLayout(btn_layout)

    def get_params(self):
        return {
            "output_name": self.txt_name.text().strip(),
            "interpolate_missing": self.chk_interpolate.isChecked(),
        }


class ResampleDialog(QDialog):
    """Dialog for resampling an entire signal group to a target frequency."""

    def __init__(self, current_hz: float | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Resample Signal Group")
        self.setFixedWidth(320)

        layout = QVBoxLayout(self)

        if current_hz:
            layout.addWidget(QLabel(f"Current rate: ~{current_hz:.1f} Hz"))
            layout.addSpacing(4)

        form = QFormLayout()

        self.spin_target = QSpinBox()
        self.spin_target.setRange(1, 10000)
        self.spin_target.setValue(int(current_hz) if current_hz else 100)
        self.spin_target.setSuffix(" Hz")
        form.addRow("Target Rate:", self.spin_target)

        layout.addLayout(form)

        # Reset option
        self.chk_reset = QCheckBox("Reset to original rate first")
        self.chk_reset.setChecked(True)
        self.chk_reset.setToolTip(
            "Reload original data from disk before resampling.\n"
            "Uncheck to resample the already-resampled data."
        )
        layout.addWidget(self.chk_reset)

        self._reset_only = False

        btn_layout = QHBoxLayout()
        btn_reset = QPushButton("Reset to Raw")
        btn_reset.setToolTip("Clear all resampling and restore original data")
        btn_reset.clicked.connect(self._on_reset_only)
        btn_apply = QPushButton("Apply")
        btn_apply.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(btn_reset)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_apply)

        layout.addLayout(btn_layout)

    def _on_reset_only(self):
        self._reset_only = True
        self.accept()

    def get_params(self):
        return {
            "target_hz": self.spin_target.value(),
            "reset_first": self.chk_reset.isChecked(),
            "reset_only": self._reset_only,
        }

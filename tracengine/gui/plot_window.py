from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QScrollArea,
    QMessageBox,
    QFrame,
    QSplitter,
)
from PyQt6.QtCore import pyqtSignal, Qt
import pyqtgraph as pg
import numpy as np

# Imports from our new modules
from tracengine.gui.plot.plotrow import PlotRow, PlotControlPanel
from tracengine.gui.plot.plotrow_unified import PlotRowWidget
from tracengine.gui.plot.channel_browser import ChannelBrowser
from tracengine.gui.dialogs import (
    DerivativeDialog,
    FilterDialog,
    AverageChannelsDialog,
    ResampleDialog,
)
from tracengine.processing.channel_utils import (
    create_derived_channel,
    create_averaged_channel,
    resample_signal_group,
    reset_signal_group_resample,
)

from tracengine.data.descriptors import Event


class ScaledAxis(pg.AxisItem):
    """
    Custom axis that maps normalized [0,1] values back to original range.
    """

    def __init__(self, orientation="left", **kwargs):
        super().__init__(orientation, **kwargs)
        self.min_val = 0.0
        self.max_val = 1.0

    def update_range(self, min_val, max_val):
        self.min_val = min_val
        self.max_val = max_val
        self.picture = None
        self.update()

    def tickStrings(self, values, scale, spacing):
        span = self.max_val - self.min_val
        if span == 0:
            span = 1.0
        strings = []
        for v in values:
            real_val = self.min_val + (v * span)
            strings.append(f"{real_val:.2f}")
        return strings


class ClickableLinearRegionItem(pg.LinearRegionItem):
    sigClicked = pyqtSignal(object)  # emits self

    def mouseClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.sigClicked.emit(self)
            ev.accept()
        else:
            super().mouseClickEvent(ev)


class ClickableInfiniteLine(pg.InfiniteLine):
    sigClicked = pyqtSignal(object)  # emits self

    def mouseClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.sigClicked.emit(self)
            ev.accept()
        else:
            super().mouseClickEvent(ev)


class CombinedPlotRow(QWidget):
    moved_up = pyqtSignal(object)
    moved_down = pyqtSignal(object)

    def __init__(self, row1, row2):
        super().__init__()
        self.row1_info = (row1.modality, row1.channel, row1.signal_name)
        self.row2_info = (row2.modality, row2.channel, row2.signal_name)

        self.signal_name = f"{row1.signal_name} & {row2.signal_name}"

        # Main Layout (Vertical: Title then Content)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.setMinimumHeight(200)

        # Title Label
        self.lbl_title = QLabel(self.signal_name)
        self.lbl_title.setStyleSheet(
            "font-weight: bold; background-color: #444; color: #EEE; padding: 2px;"
        )
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.lbl_title)

        # Content Layout
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Control Panel (Reused from plotrow, ensuring uniform width)
        self.controls = PlotControlPanel()
        self.controls.moved_up.connect(lambda: self.moved_up.emit(self))
        self.controls.moved_down.connect(lambda: self.moved_down.emit(self))
        # Disable processing for combined rows for now (or implement later)
        self.controls.btn_proc.setEnabled(False)
        self.controls.btn_proc.setToolTip("Processing available for single plots only")

        # Expose check box
        self.chk_select = self.controls.chk_select
        self.chk_select.setEnabled(False)

        # Configurable axes for combined plot
        self.ax_left = ScaledAxis(orientation="left")
        self.ax_right = ScaledAxis(orientation="right")

        # Plot Widget
        self.plot_widget = pg.PlotWidget(
            axisItems={"left": self.ax_left, "right": self.ax_right}
        )
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.showAxis("right")

        self.plot_widget.setLabel("left", row1.signal_name, color="cyan")
        self.plot_widget.setLabel("right", row2.signal_name, color="magenta")

        self.curve1 = self.plot_widget.plot(pen=pg.mkPen(color="cyan", width=2))
        self.curve2 = self.plot_widget.plot(pen=pg.mkPen(color="magenta", width=2))

        content_layout.addWidget(self.controls)
        content_layout.addWidget(self.plot_widget)

        main_layout.addWidget(content_widget)

    def update_from_run(self, run):
        t1, y1 = run.get_signal(self.row1_info[0], self.row1_info[1])
        t2, y2 = run.get_signal(self.row2_info[0], self.row2_info[1])

        def normalize(arr):
            mn, mx = np.nanmin(arr), np.nanmax(arr)
            span = mx - mn
            if span == 0:
                span = 1.0
            return (arr - mn) / span, mn, mx

        if len(y1) > 0 and len(y2) > 0:
            y1_norm, min1, max1 = normalize(y1)
            y2_norm, min2, max2 = normalize(y2)

            self.ax_left.update_range(min1, max1)
            self.ax_right.update_range(min2, max2)

            self.curve1.setData(t1, y1_norm)
            self.curve2.setData(t2, y2_norm)

    def set_processing(self, *args):
        pass  # Not supported yet for combined


class SignalProcessingToolbar(QFrame):
    derivative_requested = pyqtSignal()
    filter_requested = pyqtSignal()
    average_requested = pyqtSignal()
    resample_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedHeight(36)  # Compact height

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        lbl = QLabel("<b>Signal Processing:</b>")
        layout.addWidget(lbl)

        btn_deriv = QPushButton("Compute Derivative...")
        btn_deriv.clicked.connect(self.derivative_requested.emit)
        layout.addWidget(btn_deriv)

        btn_filter = QPushButton("Apply Filter...")
        btn_filter.clicked.connect(self.filter_requested.emit)
        layout.addWidget(btn_filter)

        btn_average = QPushButton("Average Channels...")
        btn_average.clicked.connect(self.average_requested.emit)
        layout.addWidget(btn_average)

        btn_resample = QPushButton("Resample Group...")
        btn_resample.clicked.connect(self.resample_requested.emit)
        layout.addWidget(btn_resample)

        layout.addStretch()


class PlotWindow(QWidget):
    run_changed = pyqtSignal(object)
    event_selected_on_plot = pyqtSignal(object)  # event object
    event_modified = pyqtSignal(object)  # event object
    event_removed = pyqtSignal(object)  # event object
    manual_annotation_completed = pyqtSignal(list)  # list[Event]
    channel_provenance_changed = pyqtSignal(object)  # RunData - NEW

    def __init__(self, run_objects, selected_channels, session_path=None):
        super().__init__()
        self.runs = run_objects
        # Sort runs by metadata for consistent order
        self.runs.sort(key=lambda r: tuple(v for k, v in sorted(r.metadata.items())))

        self.selected_channels = selected_channels
        self.session_path = session_path  # For reloading original data
        self.plot_widgets = []
        self.current_run_idx = 0
        self.event_items = {}  # group_name -> { event_obj_id: [items_on_plots] }
        self.item_to_event = {}  # item -> event object
        self.highlighted_event_id = None

        # State for manual annotation
        self.annotation_mode = None  # "timepoint" or "interval"
        self.current_annotation_items = []  # list of temporary items
        self.annotation_start_x = None

        # focus
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Track signal handlers
        self.active_handlers = {}  # widget -> handler callable

        main_layout = QVBoxLayout(self)

        # ----------------------------
        # Run selector UI (compact)
        # ----------------------------
        run_widget = QWidget()
        run_widget.setFixedHeight(32)
        run_row = QHBoxLayout(run_widget)
        run_row.setContentsMargins(4, 2, 4, 2)
        self.run_label = QLabel(f"Run: 1 / {len(self.runs)}")

        btn_prev = QPushButton("Prev")
        btn_next = QPushButton("Next")
        self.run_dropdown = QComboBox()

        for i, r in enumerate(self.runs):
            r_meta = r.metadata
            # Sort metadata keys for display consistency
            r_parts = [
                f"{key.capitalize()}: {value}" for key, value in sorted(r_meta.items())
            ]
            r_string = " | ".join(r_parts)
            self.run_dropdown.addItem(r_string, i)

        btn_prev.clicked.connect(self.prev_run)
        btn_next.clicked.connect(self.next_run)
        self.run_dropdown.currentIndexChanged.connect(self.update_run)

        run_row.addWidget(btn_prev)
        run_row.addWidget(btn_next)
        run_row.addWidget(self.run_dropdown)
        run_row.addWidget(self.run_label)
        run_row.addStretch()
        main_layout.addWidget(run_widget)

        # ----------------------------
        # Signal Processing Toolbar
        # ----------------------------
        self.proc_toolbar = SignalProcessingToolbar()
        self.proc_toolbar.derivative_requested.connect(self.open_derivative_dialog)
        self.proc_toolbar.filter_requested.connect(self.open_filter_dialog)
        self.proc_toolbar.average_requested.connect(self.open_average_dialog)
        self.proc_toolbar.resample_requested.connect(self.open_resample_dialog)
        main_layout.addWidget(self.proc_toolbar)

        # ----------------------------
        # Control Row (Manage Plots)
        # ----------------------------
        control_row = QHBoxLayout()
        btn_combine = QPushButton("Combine Selected")
        btn_combine.clicked.connect(self.combine_selected_plots)
        btn_split = QPushButton("Split Selected")
        btn_split.clicked.connect(self.split_selected_plot)
        control_row.addWidget(btn_combine)
        control_row.addWidget(btn_split)
        control_row.addStretch()
        main_layout.addLayout(control_row)

        # ----------------------------
        # Main content area with sidebar
        # ----------------------------
        content_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Channel browser sidebar (left)
        self.channel_browser = ChannelBrowser()
        self.channel_browser.new_row_requested.connect(self._on_new_row_requested)
        self.channel_browser.add_to_row_requested.connect(self._on_add_to_row_requested)
        content_splitter.addWidget(self.channel_browser)

        # ----------------------------
        # Scrollable plot area (right)
        # ----------------------------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        scroll.setWidget(self.scroll_widget)

        content_splitter.addWidget(scroll)
        content_splitter.setSizes([220, 800])  # Initial widths

        main_layout.addWidget(content_splitter)

        # Build plot widgets
        self.build_plot_list()
        self.update_run(0)

    # ----------------------------------
    # Build plot list
    # ----------------------------------
    def build_plot_list(self):
        for w in self.plot_widgets:
            w.deleteLater()
        self.plot_widgets = []

        for modality, channels in self.selected_channels.items():
            for channel in channels:
                w = PlotRow(f"{modality}: {channel}", modality, channel)
                w.moved_up.connect(self.move_up)
                w.moved_down.connect(self.move_down)
                # Connect background click for deselect
                # use lambda to capture
                w.plot_widget.scene().sigMouseClicked.connect(
                    lambda ev, widget=w: self.on_background_clicked(ev, widget)
                )
                self.scroll_layout.addWidget(w)
                self.plot_widgets.append(w)

        self.scroll_layout.addStretch()
        self.relink_x_axes()

    # ----------------------------------
    # Run Nav
    # ----------------------------------
    def prev_run(self):
        idx = self.run_dropdown.currentIndex()
        if idx > 0:
            self.run_dropdown.setCurrentIndex(idx - 1)

    def next_run(self):
        idx = self.run_dropdown.currentIndex()
        if idx < len(self.runs) - 1:
            self.run_dropdown.setCurrentIndex(idx + 1)

    def update_run(self, idx):
        self.clear_all_events()  # Clear previous run's events

        run = self.runs[idx]
        self.current_run_idx = idx
        self.run_label.setText(f"Run: {idx + 1} / {len(self.runs)}")
        self.run_changed.emit(run)

        for w in self.plot_widgets:
            w.update_from_run(run)

        # Update channel browser
        self.channel_browser.load_from_run(run)
        self._update_row_dropdown()

        self.relink_x_axes()
        print({k: v.data.columns for k, v in run.raw_signals.items()})

    def clear_all_events(self):
        """Remove all event items from plots and clear state."""
        for group_map in self.event_items.values():
            for items in group_map.values():
                for item in items:
                    if item.scene():
                        item.scene().removeItem(item)
                    if item in self.item_to_event:
                        del self.item_to_event[item]
        self.event_items.clear()
        self.highlighted_event_id = None

    # ----------------------------------
    # Signal Processing Actions
    # ----------------------------------
    def get_selected_rows(self):
        return [
            w
            for w in self.plot_widgets
            if hasattr(w, "chk_select") and w.chk_select.isChecked()
        ]

    def open_derivative_dialog(self):
        selected = self.get_selected_rows()
        if not selected:
            QMessageBox.information(
                self, "Info", "Select at least one signal plot first."
            )
            return

        dlg = DerivativeDialog(self)
        if dlg.exec():
            params = dlg.get_params()
            self.apply_derivative(selected, params["order"])

    def apply_derivative(self, rows, order):
        """Apply derivative and persist as derived channel."""
        created_channels = set()  # Use set to avoid duplicates across runs

        for row in rows:
            # Extract source channel info from either row type
            source_channels = self._get_row_channels(row)
            if not source_channels:
                continue

            for modality, channel_name in source_channels:
                # Create derived channel for ALL runs
                for run in self.runs:
                    try:
                        channel = create_derived_channel(
                            run=run,
                            group_name=modality,
                            source_channel=channel_name,
                            operation="derivative",
                            params={"order": order},
                        )
                        if channel:
                            created_channels.add(f"{modality}:{channel.name}")
                    except KeyError:
                        continue

        # Create new plot rows for derived channels (one per unique channel)
        for channel_id in created_channels:
            self._on_new_row_requested([channel_id])

        # Refresh channel browser to show new channels
        if self.runs:
            self.channel_browser.load_from_run(self.runs[self.current_run_idx])
            self._update_row_dropdown()

        # Emit signal to trigger provenance save for ALL runs (since we computed for all)
        for run in self.runs:
            self.channel_provenance_changed.emit(run)

    def open_filter_dialog(self):
        selected = self.get_selected_rows()
        if not selected:
            QMessageBox.information(
                self, "Info", "Select at least one signal plot first."
            )
            return

        dlg = FilterDialog(self)
        if dlg.exec():
            params = dlg.get_params()
            self.apply_filter(selected, params)

    def apply_filter(self, rows, params):
        """Apply filter and persist as derived channel."""
        filter_type = params.get("filter_type", "butter")
        filter_params = {k: v for k, v in params.items() if k != "filter_type"}
        created_channels = set()  # Use set to avoid duplicates across runs

        for row in rows:
            # Extract source channel info from either row type
            source_channels = self._get_row_channels(row)
            if not source_channels:
                continue

            for modality, channel_name in source_channels:
                # Create derived channel for ALL runs
                for run in self.runs:
                    try:
                        channel = create_derived_channel(
                            run=run,
                            group_name=modality,
                            source_channel=channel_name,
                            operation=filter_type,
                            params=filter_params,
                        )
                        if channel:
                            created_channels.add(f"{modality}:{channel.name}")
                    except KeyError:
                        continue

        # Create new plot rows for derived channels (one per unique channel)
        for channel_id in created_channels:
            self._on_new_row_requested([channel_id])

        # Refresh channel browser to show new channels
        if self.runs:
            self.channel_browser.load_from_run(self.runs[self.current_run_idx])
            self._update_row_dropdown()

        # Emit signal to trigger provenance save for ALL runs (since we computed for all)
        for run in self.runs:
            self.channel_provenance_changed.emit(run)

    def open_average_dialog(self):
        """Open dialog to create an averaged channel from selected plots."""
        selected = self.get_selected_rows()
        if len(selected) < 2:
            QMessageBox.information(
                self, "Info", "Select at least two signal plots to average."
            )
            return

        # Collect all channel IDs from selected rows
        all_channels = []
        for row in selected:
            source_channels = self._get_row_channels(row)
            for modality, channel_name in source_channels:
                all_channels.append((modality, channel_name))

        if len(all_channels) < 2:
            QMessageBox.warning(self, "Warning", "Need at least 2 channels to average.")
            return

        # Format for display
        channel_names = [f"{m}:{c}" for m, c in all_channels]

        dlg = AverageChannelsDialog(channel_names, self)
        if dlg.exec():
            params = dlg.get_params()
            output_name = params.get("output_name", "averaged")
            interpolate = params.get("interpolate_missing", True)

            if not output_name:
                QMessageBox.warning(self, "Warning", "Please enter an output name.")
                return

            # Use first channel's modality as target
            target_group = all_channels[0][0]

            # Create averaged channel for all runs
            created_channels = set()
            for run in self.runs:
                try:
                    channel = create_averaged_channel(
                        run=run,
                        source_channels=all_channels,
                        target_group=target_group,
                        output_name=output_name,
                        interpolate_missing=interpolate,
                    )
                    created_channels.add(f"{target_group}:{channel.name}")
                except (KeyError, ValueError) as e:
                    print(f"Failed to create average for run: {e}")
                    continue

            # Create new plot row for averaged channel
            for channel_id in created_channels:
                self._on_new_row_requested([channel_id])

            # Refresh channel browser
            if self.runs:
                self.channel_browser.load_from_run(self.runs[self.current_run_idx])
                self._update_row_dropdown()

            # Emit provenance changed for all runs
            for run in self.runs:
                self.channel_provenance_changed.emit(run)

            QMessageBox.information(
                self, "Success", f"Created averaged channel: {output_name}"
            )

    def open_resample_dialog(self):
        """Open dialog to resample a signal group."""
        selected = self.get_selected_rows()
        if not selected:
            QMessageBox.information(
                self, "Info", "Select at least one signal plot first."
            )
            return

        # Get the modality from the first selected row to show current Hz
        source_channels = self._get_row_channels(selected[0])
        current_hz = None
        if source_channels and self.runs:
            modality = source_channels[0][0]
            run = self.runs[self.current_run_idx]
            if modality in run.signals:
                current_hz = run.signals[modality].sampling_rate

        dlg = ResampleDialog(current_hz=current_hz, parent=self)
        if dlg.exec():
            params = dlg.get_params()
            if params["reset_only"]:
                self._reset_resample(selected)
            else:
                self.apply_resample(
                    selected,
                    params["target_hz"],
                    reset_first=params["reset_first"],
                )

    def apply_resample(self, rows, target_hz, reset_first=False):
        """Resample selected signal groups to target Hz."""
        resampled_groups = set()

        # Determine data directory for reset
        data_dir = None
        if reset_first and self.session_path:
            from pathlib import Path

            data_dir = Path(self.session_path) / "processed"

        for row in rows:
            source_channels = self._get_row_channels(row)
            if not source_channels:
                continue

            for modality, _ in source_channels:
                if modality in resampled_groups:
                    continue  # Don't resample same group twice

                for run in self.runs:
                    try:
                        # Reset to original data first if requested
                        if reset_first and data_dir and data_dir.exists():
                            try:
                                reset_signal_group_resample(run, modality, data_dir)
                            except (FileNotFoundError, KeyError) as e:
                                print(f"Reset skipped for {modality}: {e}")

                        resample_signal_group(
                            run=run,
                            group_name=modality,
                            target_hz=target_hz,
                        )
                    except (KeyError, ValueError) as e:
                        print(f"Failed to resample {modality} for run: {e}")
                        continue

                resampled_groups.add(modality)

        # Refresh all plots since data changed in-place
        if self.runs:
            self.update_run(self.current_run_idx)

        # Emit provenance changed for all runs
        for run in self.runs:
            self.channel_provenance_changed.emit(run)

        if resampled_groups:
            groups_str = ", ".join(sorted(resampled_groups))
            QMessageBox.information(
                self,
                "Success",
                f"Resampled {groups_str} to {target_hz} Hz",
            )

    def _reset_resample(self, rows):
        """Reset selected signal groups to original (raw) data from disk."""
        if not self.session_path:
            QMessageBox.warning(self, "Error", "No session path available for reset.")
            return

        from pathlib import Path

        data_dir = Path(self.session_path) / "processed"
        if not data_dir.exists():
            QMessageBox.warning(self, "Error", f"Data directory not found: {data_dir}")
            return

        reset_groups = set()
        for row in rows:
            source_channels = self._get_row_channels(row)
            if not source_channels:
                continue
            for modality, _ in source_channels:
                if modality in reset_groups:
                    continue
                for run in self.runs:
                    try:
                        reset_signal_group_resample(run, modality, data_dir)
                    except (FileNotFoundError, KeyError) as e:
                        print(f"Reset failed for {modality}: {e}")
                        continue
                reset_groups.add(modality)

        if self.runs:
            self.update_run(self.current_run_idx)

        for run in self.runs:
            self.channel_provenance_changed.emit(run)

        if reset_groups:
            groups_str = ", ".join(sorted(reset_groups))
            QMessageBox.information(
                self, "Success", f"Reset {groups_str} to raw sample rate"
            )

    def _get_row_channels(self, row) -> list[tuple[str, str]]:
        """
        Extract (modality, channel_name) tuples from a row.
        Works with both legacy PlotRow and new PlotRowWidget.
        """
        result = []

        if isinstance(row, PlotRowWidget):
            # New unified row - get all channel IDs
            for channel_id in row.get_channel_ids():
                if ":" in channel_id:
                    modality, name = channel_id.split(":", 1)
                    result.append((modality, name))
        elif hasattr(row, "modality") and hasattr(row, "channel"):
            # Legacy PlotRow / DerivedPlotRow
            result.append((row.modality, row.channel))

        return result

    # ----------------------------------
    # Ordering & Combining
    # ----------------------------------
    def move_up(self, widget):
        i = self.scroll_layout.indexOf(widget)
        if i > 0:
            self.scroll_layout.removeWidget(widget)
            self.scroll_layout.insertWidget(i - 1, widget)
            j = self.plot_widgets.index(widget)
            self.plot_widgets.insert(j - 1, self.plot_widgets.pop(j))
            self.relink_x_axes()

    def move_down(self, widget):
        i = self.scroll_layout.indexOf(widget)
        if i < self.scroll_layout.count() - 2:
            self.scroll_layout.removeWidget(widget)
            self.scroll_layout.insertWidget(i + 1, widget)
            j = self.plot_widgets.index(widget)
            self.plot_widgets.insert(j + 1, self.plot_widgets.pop(j))
            self.relink_x_axes()

    def combine_selected_plots(self):
        """Combine selected plot rows into a single multi-channel row."""
        selected = self.get_selected_rows()
        if len(selected) < 2:
            QMessageBox.warning(
                self, "Selection Error", "Please select at least 2 plots to combine."
            )
            return

        # Collect all channel IDs from selected rows
        all_channels = []
        for row in selected:
            if isinstance(row, PlotRowWidget):
                all_channels.extend(row.get_channel_ids())
            elif hasattr(row, "modality") and hasattr(row, "channel"):
                # Legacy PlotRow/DerivedPlotRow
                channel_id = f"{row.modality}:{row.channel}"
                all_channels.append(channel_id)

        if not all_channels:
            return

        # Create new combined row
        new_row = PlotRowWidget(all_channels)
        new_row.moved_up.connect(self.move_up)
        new_row.moved_down.connect(self.move_down)
        new_row.close_requested.connect(self._on_row_close_requested)
        new_row.split_requested.connect(self._on_row_split_requested)

        if self.runs:
            new_row.update_from_run(self.runs[self.current_run_idx])

        # Add new row at position of first selected
        first_idx = min(self.scroll_layout.indexOf(r) for r in selected)
        self.scroll_layout.insertWidget(first_idx, new_row)
        self.plot_widgets.insert(first_idx, new_row)

        # Remove original rows
        for row in selected:
            row.chk_select.setChecked(False)
            self.scroll_layout.removeWidget(row)
            self.plot_widgets.remove(row)
            row.deleteLater()

        self._update_row_dropdown()
        self.relink_x_axes()

        # Sync existing visible annotations to the new combined row
        self._sync_visibility_to_row(new_row)

    def split_selected_plot(self):
        """Split a selected multi-channel row into individual rows."""
        selected = self.get_selected_rows()
        if len(selected) != 1:
            QMessageBox.warning(
                self,
                "Selection Error",
                "Please select exactly 1 multi-channel plot to split.",
            )
            return

        row = selected[0]
        if not isinstance(row, PlotRowWidget):
            QMessageBox.warning(
                self, "Split Error", "Only unified plot rows can be split."
            )
            return

        channel_ids = row.get_channel_ids()
        if len(channel_ids) <= 1:
            QMessageBox.information(
                self, "Info", "This row has only one channel, nothing to split."
            )
            return

        self._on_row_split_requested(row)

    def relink_x_axes(self):
        if not self.plot_widgets:
            return
        master = None
        # Find first PlotRow or CombinedPlotRow that has a plot_widget
        for w in self.plot_widgets:
            if hasattr(w, "plot_widget"):
                master = w.plot_widget
                break
        if not master:
            return

        for w in self.plot_widgets:
            if w.plot_widget != master:
                w.plot_widget.setXLink(master)

    # ----------------------------------
    # Channel Browser Handlers
    # ----------------------------------
    def _on_new_row_requested(self, channel_ids: list[str]):
        """Create a new plot row with the given channels."""
        new_row = PlotRowWidget(channel_ids)
        new_row.moved_up.connect(self.move_up)
        new_row.moved_down.connect(self.move_down)
        new_row.close_requested.connect(self._on_row_close_requested)
        new_row.split_requested.connect(self._on_row_split_requested)

        if self.runs:
            new_row.update_from_run(self.runs[self.current_run_idx])

        # Add at end (before stretch)
        self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, new_row)
        self.plot_widgets.append(new_row)

        # Sync existing visible annotations to this new row
        self._sync_visibility_to_row(new_row)

        self._update_row_dropdown()
        self.relink_x_axes()

    def _on_add_to_row_requested(self, channel_ids: list[str], row_index: int):
        """Add channels to an existing plot row."""
        if row_index < 0 or row_index >= len(self.plot_widgets):
            return

        row = self.plot_widgets[row_index]

        if isinstance(row, PlotRowWidget):
            for ch in channel_ids:
                row.add_channel(ch)
            if self.runs:
                row.update_from_run(self.runs[self.current_run_idx])
        else:
            # Legacy row - can't add to it, create a combined one instead
            legacy_channel = f"{row.modality}:{row.channel}"
            all_channels = [legacy_channel] + channel_ids
            self._on_new_row_requested(all_channels)

        self._update_row_dropdown()

    def _on_row_close_requested(self, row):
        """Handle row close button."""
        if row in self.plot_widgets:
            self.scroll_layout.removeWidget(row)
            self.plot_widgets.remove(row)
            row.deleteLater()
            self._update_row_dropdown()
            self.relink_x_axes()

    def _on_row_split_requested(self, row):
        """Split a multi-channel row into individual rows."""
        if not isinstance(row, PlotRowWidget):
            return

        channel_ids = row.get_channel_ids()
        if len(channel_ids) <= 1:
            return

        # Get position
        idx = self.scroll_layout.indexOf(row)

        # Remove the combined row
        self.scroll_layout.removeWidget(row)
        if row in self.plot_widgets:
            self.plot_widgets.remove(row)

        # Create individual rows
        for i, ch in enumerate(channel_ids):
            new_row = PlotRowWidget([ch])
            new_row.moved_up.connect(self.move_up)
            new_row.moved_down.connect(self.move_down)
            new_row.close_requested.connect(self._on_row_close_requested)
            new_row.split_requested.connect(self._on_row_split_requested)

            if self.runs:
                new_row.update_from_run(self.runs[self.current_run_idx])

            self.scroll_layout.insertWidget(idx + i, new_row)
            self.plot_widgets.insert(idx + i, new_row)

            # Sync existing visible annotations to this new row
            self._sync_visibility_to_row(new_row)

        row.deleteLater()
        self._update_row_dropdown()
        self.relink_x_axes()

    def _sync_visibility_to_row(self, plot_row):
        """
        Sync existing visible annotations to a newly created plot row.
        Iterates over self.event_items to find what should be visible.
        """
        if not hasattr(plot_row, "plot_widget"):
            return

        for group_name, group_map in self.event_items.items():
            for event_id, items in group_map.items():
                # Get the event object from the first item in the group list
                if not items:
                    continue
                event = self.item_to_event.get(items[0])
                if not event:
                    continue

                # Create visual item for this row
                if event.offset is not None:
                    # Interval
                    brush = pg.mkBrush(255, 255, 0, 40)
                    item = ClickableLinearRegionItem(
                        [event.onset, event.offset], movable=False, brush=brush
                    )
                else:
                    # Point
                    pen = pg.mkPen("y", width=1, style=Qt.PenStyle.DashLine)
                    item = ClickableInfiniteLine(
                        event.onset, angle=90, pen=pen, movable=False
                    )

                item.sigClicked.connect(self.on_item_clicked)
                plot_row.plot_widget.addItem(item)

                # Register the new item
                items.append(item)
                self.item_to_event[item] = event

                # Apply style
                self._update_item_style(
                    item, event, active=(event_id == self.highlighted_event_id)
                )

    def _update_row_dropdown(self):
        """Update the channel browser's row dropdown."""
        row_names = []
        for w in self.plot_widgets:
            if isinstance(w, PlotRowWidget):
                channels = w.get_channel_ids()
                if len(channels) == 1:
                    row_names.append(channels[0].split(":")[-1])
                else:
                    row_names.append(f"{len(channels)} channels")
            elif hasattr(w, "signal_name"):
                row_names.append(w.signal_name)
            else:
                row_names.append("(unknown)")
        self.channel_browser.update_row_list(row_names)

    # ----------------------------------
    # Event Visualization
    # ----------------------------------
    def update_event_visibility(self, group_name, events, visible):
        # 1. Clear existing items for this group
        if group_name in self.event_items:
            for event_id, items in self.event_items[group_name].items():
                for item in items:
                    if item in self.item_to_event:
                        del self.item_to_event[item]
                    try:
                        if item.scene():
                            item.scene().removeItem(item)
                    except RuntimeError:
                        # C++ object already deleted
                        pass
            del self.event_items[group_name]

        if not visible or not events:
            return

        # 2. Add new items
        group_map = {}

        for event in events:
            items = []
            for plot_row in self.plot_widgets:
                if not hasattr(plot_row, "plot_widget"):
                    continue

                # Check timestamps (assuming float seconds relative to start)
                if event.offset is not None:
                    # Interval
                    brush = pg.mkBrush(255, 255, 0, 40)  # Yellow, transparent
                    item = ClickableLinearRegionItem(
                        [event.onset, event.offset], movable=False, brush=brush
                    )
                else:
                    # Point
                    pen = pg.mkPen("y", width=1, style=Qt.PenStyle.DashLine)
                    item = ClickableInfiniteLine(
                        event.onset, angle=90, pen=pen, movable=False
                    )

                item.sigClicked.connect(self.on_item_clicked)
                plot_row.plot_widget.addItem(item)
                items.append(item)
                self.item_to_event[item] = event

            group_map[id(event)] = items

        self.event_items[group_name] = group_map

        # Apply initial style for all new items
        for event_id, items in group_map.items():
            # Get event object (we can get it from first item)
            if not items:
                continue
            event = self.item_to_event[items[0]]

            for item in items:
                self._update_item_style(item, event, active=False)

        # Re-apply highlight if needed
        if self.highlighted_event_id in group_map:
            self._apply_visual_highlight(self.highlighted_event_id)

    def on_item_clicked(self, item):
        if item in self.item_to_event:
            event = self.item_to_event[item]
            self.highlight_event(event)  # local highlight
            self.event_selected_on_plot.emit(event)  # sync to panel

            # Ensure window has focus for keys
            self.setFocus()

    def start_annotation_mode(self, mode):
        # Ensure we don't stack connections
        self.stop_annotation_mode(save=False)

        self.annotation_mode = mode
        self.current_annotation_items = []
        self.annotation_start_x = None

        # visual cue?
        QMessageBox.information(
            self,
            "Annotation Mode",
            f"Mode: {mode}\n\n- Left Click to add.\n- Drag for interval.\n- Press ENTER to finish.\n- Press ESC to cancel.",
        )

        # We need to hook into mouse events of the plot widgets
        self.active_handlers = {}
        for w in self.plot_widgets:
            if hasattr(w, "plot_widget"):
                # Define handler for this widget
                # We need a default arg to capture 'w'
                def make_handler(widget):
                    return lambda ev: self.on_scene_clicked(ev, widget)

                handler = make_handler(w)
                w.plot_widget.scene().sigMouseClicked.connect(handler)
                self.active_handlers[w] = handler

    def stop_annotation_mode(self, save=False):
        # Clean up handlers
        if hasattr(self, "active_handlers"):
            for w, handler in self.active_handlers.items():
                try:
                    if hasattr(w, "plot_widget"):
                        w.plot_widget.scene().sigMouseClicked.disconnect(handler)
                except Exception:
                    pass
            self.active_handlers = {}

        # Clear items
        for start, end, items in self.current_annotation_items:
            for item in items:
                if item.scene():
                    item.scene().removeItem(item)
        self.current_annotation_items = []

        self.annotation_mode = None

        if save:
            # We need to reconstruct events from the items we created
            # But actually, I implemented on_scene_clicked to create items AND events immediately?
            # No, better to create temporary events list.
            pass

    def on_scene_clicked(self, ev, plot_row=None):
        if not self.annotation_mode:
            return
        if ev.button() != Qt.MouseButton.LeftButton:
            return

        # If plot_row is None (old style call? shouldn't happen with lambda fix), fail safe
        if plot_row is None:
            # Try fallback to first widget?
            if not self.plot_widgets:
                return
            plot_row = self.plot_widgets[0]

        if not hasattr(plot_row, "plot_widget"):
            return
        pw_widget = plot_row.plot_widget
        vb = pw_widget.plotItem.vb

        scene_pos = ev.scenePos()
        if pw_widget.sceneBoundingRect().contains(scene_pos):
            # Map
            mouse_point = vb.mapSceneToView(scene_pos)
            x_val = mouse_point.x()

            if self.annotation_mode == "timepoint":
                self.add_manual_event(x_val, None)
            elif self.annotation_mode == "interval":
                if self.annotation_start_x is None:
                    self.annotation_start_x = x_val
                    # Show visual cursor at start
                    # Remove old cursor if any
                    if hasattr(self, "cursor_line") and self.cursor_line:
                        if self.cursor_line.scene():
                            self.cursor_line.scene().removeItem(self.cursor_line)

                    pen = pg.mkPen(
                        (0, 255, 0, 150), width=1, style=Qt.PenStyle.DashLine
                    )
                    self.cursor_line = pg.InfiniteLine(
                        pos=x_val, angle=90, pen=pen, movable=False
                    )
                    pw_widget.addItem(self.cursor_line)

                else:
                    start = min(self.annotation_start_x, x_val)
                    end = max(self.annotation_start_x, x_val)
                    self.add_manual_event(start, end)
                    self.annotation_start_x = None
                    # Remove cursor
                    if hasattr(self, "cursor_line") and self.cursor_line:
                        if self.cursor_line.scene():
                            self.cursor_line.scene().removeItem(self.cursor_line)
                        self.cursor_line = None

    def add_manual_event(self, start, end):
        # Create visual item
        temp_items = []

        for w in self.plot_widgets:
            if not hasattr(w, "plot_widget"):
                continue

            if end is not None:
                item = pg.LinearRegionItem([start, end], movable=True)
                brush = pg.mkBrush(0, 255, 0, 50)  # Green for new
                item.setBrush(brush)
            else:
                item = pg.InfiniteLine(start, angle=90, movable=True)
                pen = pg.mkPen("g", width=2, style=Qt.PenStyle.SolidLine)
                item.setPen(pen)

            w.plot_widget.addItem(item)
            temp_items.append(item)

        # Store as touple (start, end, [items])
        self.current_annotation_items.append((start, end, temp_items))

    def finish_annotation(self):
        events = []
        for i, (start, end, items) in enumerate(self.current_annotation_items):
            # Check current position of items (in case user moved them)
            # Use first item as reference
            ref_item = items[0]
            if isinstance(ref_item, pg.LinearRegionItem):
                s, e = ref_item.getRegion()
                ev = Event(
                    annotator="ManualInterval",
                    name=f"Manual I{i}",
                    event_type="interval",
                    onset=s,
                    offset=e,
                    confidence=1.0,
                    metadata={},
                )
            else:
                s = ref_item.value()
                ev = Event(
                    annotator="ManualTimepoint",
                    name=f"Manual T{i}",
                    event_type="timepoint",
                    onset=s,
                    offset=None,
                    confidence=1.0,
                    metadata={},
                )
            events.append(ev)

        self.manual_annotation_completed.emit(events)
        self.stop_annotation_mode()

    def keyPressEvent(self, ev):
        if self.annotation_mode:
            if ev.key() == Qt.Key.Key_Return or ev.key() == Qt.Key.Key_Enter:
                self.finish_annotation()
                return
            elif ev.key() == Qt.Key.Key_Escape:
                self.stop_annotation_mode()
                return

        if self.highlighted_event_id is not None:
            # Find the event object
            target_event = None
            # Expensive search but safe
            for group_map in self.event_items.values():
                if self.highlighted_event_id in group_map:
                    # Just grab first item to find event
                    items = group_map[self.highlighted_event_id]
                    if items:
                        target_event = self.item_to_event.get(items[0])
                    break

            if target_event:
                if ev.text() == "0":
                    target_event.confidence = 0.0
                    self.event_modified.emit(target_event)
                elif ev.text() == "1":
                    target_event.confidence = 1.0
                    self.event_modified.emit(target_event)
                elif ev.key() == Qt.Key.Key_Delete or ev.key() == Qt.Key.Key_Backspace:
                    self.remove_highlighted_event()
                    return

        super().keyPressEvent(ev)

    def remove_highlighted_event(self):
        if self.highlighted_event_id is None:
            return

        # Find event object and group
        target_event = None
        target_group = None

        for group_name, group_map in self.event_items.items():
            if self.highlighted_event_id in group_map:
                target_group = group_name
                items = group_map[self.highlighted_event_id]
                if items:
                    target_event = self.item_to_event.get(items[0])
                break

        if target_event and target_group:
            self.event_removed.emit(target_event)

            # DIRECTLY Remove items from scene
            if (
                target_group in self.event_items
                and self.highlighted_event_id in self.event_items[target_group]
            ):
                items = self.event_items[target_group][self.highlighted_event_id]
                for item in items:
                    if item.scene():
                        item.scene().removeItem(item)
                    if item in self.item_to_event:
                        del self.item_to_event[item]

                # Cleanup registry
                del self.event_items[target_group][self.highlighted_event_id]

            self.highlighted_event_id = None

    def on_background_clicked(self, ev, widget):
        if self.annotation_mode:
            return  # Handled by annotation handler
        if ev.isAccepted():
            return  # Handled by item

        # If we are here, background was clicked
        if ev.button() == Qt.MouseButton.LeftButton:
            self.highlight_event(None)  # Deselect all

    def highlight_event(self, event):
        new_id = id(event) if event is not None else None

        # Un-highlight old
        if self.highlighted_event_id is not None:
            self._apply_visual_highlight(self.highlighted_event_id, active=False)

        self.highlighted_event_id = new_id

        if new_id is not None:
            self._apply_visual_highlight(new_id, active=True)

            # Auto-zoom? maybe not, might be annoying.
            # But maybe scroll to it if not visible?

    def _update_item_style(self, item, event, active=False):
        is_rejected = event.confidence == 0.0

        if isinstance(item, pg.LinearRegionItem):
            # Base color: Red if active, Yellow if inactive
            base_color = [255, 0, 0, 100] if active else [255, 255, 0, 40]
            if is_rejected:
                # Dim significantly or hide, make redish
                base_color[0] = 255
                base_color[1] = 0
                base_color[2] = 0
                base_color[3] = (
                    50 if not active else 100
                )  # Invisible if not active, faint if active

            item.setBrush(pg.mkBrush(base_color))

        elif isinstance(item, pg.InfiniteLine):
            color = "r" if active else "y"
            width = 3 if active else 1
            style = Qt.PenStyle.SolidLine

            if is_rejected:
                # Make it grey or very faint?
                color = (255, 0, 0, 255)  # Faint grey
                style = Qt.PenStyle.DashLine

            item.setPen(pg.mkPen(color, width=width, style=style))

    def _apply_visual_highlight(self, event_id, active=True):
        # Find the items
        for group, group_map in self.event_items.items():
            if event_id in group_map:
                items = group_map[event_id]
                for item in items:
                    event = self.item_to_event.get(item)
                    if not event:
                        continue
                    self._update_item_style(item, event, active=active)

        # Force update
        for w in self.plot_widgets:
            if hasattr(w, "plot_widget"):
                # Force viewport update for immediate repaint
                w.plot_widget.viewport().update()

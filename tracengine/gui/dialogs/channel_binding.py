"""
Channel Binding Dialog

UI for mapping plugin ChannelSpecs to actual channels in the data.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QGroupBox,
    QScrollArea,
    QWidget,
    QFrame,
    QMessageBox,
)
from PyQt6.QtCore import pyqtSignal

from tracengine.data.descriptors import RunData, ChannelSpec, EventSpec


class ChannelBindingDialog(QDialog):
    """
    Dialog for configuring plugin channel and event bindings.

    Features:
    - Dropdown for each required_channel with available channels
    - Dropdown for each required_event with available annotation groups
    - Preview of current bindings
    - Save to RunConfig option
    """

    bindings_saved = pyqtSignal(dict)  # Emitted when bindings are saved

    def __init__(
        self,
        run: RunData,
        required_channels: dict[str, ChannelSpec] | None = None,
        required_events: dict[str, EventSpec] | None = None,
        plugin_name: str = "Plugin",
        parent=None,
    ):
        super().__init__(parent)
        self.run = run
        self.required_channels = required_channels or {}
        self.required_events = required_events or {}
        self.plugin_name = plugin_name

        self.setWindowTitle(f"Configure: {plugin_name}")
        self.setMinimumWidth(450)

        self._channel_combos: dict[str, QComboBox] = {}
        self._event_combos: dict[str, QComboBox] = {}

        self._setup_ui()
        self._populate_combos()
        self._load_existing_bindings()

    def _setup_ui(self):
        """Create the dialog UI."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel(f"<b>Configure bindings for {self.plugin_name}</b>")
        layout.addWidget(header)

        # Scroll area for bindings
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # Channel bindings section
        if self.required_channels:
            channel_group = QGroupBox("Required Channels")
            channel_form = QFormLayout()

            for role, spec in self.required_channels.items():
                combo = QComboBox()
                combo.setMinimumWidth(250)
                self._channel_combos[role] = combo

                # Label with semantic role info
                label = f"{role}"
                if spec.semantic_role:
                    label += f" ({spec.semantic_role})"
                channel_form.addRow(label + ":", combo)

            channel_group.setLayout(channel_form)
            scroll_layout.addWidget(channel_group)

        # Event bindings section
        if self.required_events:
            event_group = QGroupBox("Required Events")
            event_form = QFormLayout()

            for role, spec in self.required_events.items():
                combo = QComboBox()
                combo.setMinimumWidth(250)
                self._event_combos[role] = combo

                label = f"{role} ({spec.event_type}, {spec.kind})"
                if spec.optional:
                    label += " — optional"
                event_form.addRow(label + ":", combo)

            event_group.setLayout(event_form)
            scroll_layout.addWidget(event_group)

        # No requirements message
        if not self.required_channels and not self.required_events:
            no_req = QLabel("This plugin has no channel or event requirements.")
            no_req.setStyleSheet("color: gray; font-style: italic;")
            scroll_layout.addWidget(no_req)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # Info label
        info = QLabel("<small>Bindings will be saved to the run configuration.</small>")
        info.setStyleSheet("color: gray;")
        layout.addWidget(info)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = QPushButton("Save Bindings")
        btn_save.clicked.connect(self._on_save)
        btn_save.setDefault(True)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

    def _populate_combos(self):
        """Populate dropdown options from run data."""
        # Build list of all available channels
        all_channels = []
        for group_name, signal_group in self.run.signals.items():
            for channel_name in signal_group.list_channels():
                channel_id = f"{group_name}:{channel_name}"
                display = f"{group_name} → {channel_name}"
                all_channels.append((channel_id, display))

        # Sort alphabetically by display name
        all_channels.sort(key=lambda x: x[1].lower())

        # Populate channel combos
        for role, combo in self._channel_combos.items():
            combo.addItem("-- Select Channel --", None)
            for channel_id, display in all_channels:
                combo.addItem(display, channel_id)

        # Build list of available annotation groups
        all_events = []
        for group_name, events in self.run.annotations.items():
            if events:
                event_type = events[0].event_type
                count = len(events)
                display = f"{group_name} ({event_type}, {count} events)"
                all_events.append((group_name, display))

        # Populate event combos
        for role, combo in self._event_combos.items():
            if self.required_events[role].optional:
                combo.addItem("-- None --", "")
            else:
                combo.addItem("-- Select Event Group --", None)
            for group_name, display in all_events:
                combo.addItem(display, group_name)

    def _load_existing_bindings(self):
        """Load existing bindings from RunConfig if available.

        Note: With instance-scoped bindings, we don't auto-load because
        we don't know which instance the user is configuring. The caller
        (plugin_runner) should pass instance_name if pre-loading is needed.
        """
        # Disabled - caller handles instance-specific bindings
        pass

    def _on_save(self):
        """Validate and save bindings."""
        # Validate all required channels are selected
        channel_bindings = {}
        for role, combo in self._channel_combos.items():
            channel_id = combo.currentData()
            if channel_id is None:
                QMessageBox.warning(
                    self,
                    "Missing Binding",
                    f"Please select a channel for: {role}",
                )
                return

            spec = self.required_channels.get(role)
            if spec:
                # Store using semantic_role as key
                channel_bindings[spec.semantic_role] = channel_id

        # Validate all required events are selected
        event_bindings = {}
        for role, combo in self._event_combos.items():
            group_name = combo.currentData()
            if group_name is None:
                QMessageBox.warning(
                    self,
                    "Missing Binding",
                    f"Please select an event group for: {role}",
                )
                return
            event_bindings[role] = group_name

        # Note: We no longer update RunConfig here directly.
        # The caller (plugin_runner) handles storing under instance name.

        # Emit signal with all bindings
        all_bindings = {
            "channels": channel_bindings,
            "events": event_bindings,
        }
        self.bindings_saved.emit(all_bindings)

        self.accept()

    def get_bindings(self) -> dict:
        """
        Get the current bindings.

        Returns:
            Dict with 'channels' and 'events' keys
        """
        channel_bindings = {}
        for role, combo in self._channel_combos.items():
            channel_id = combo.currentData()
            if channel_id:
                spec = self.required_channels.get(role)
                if spec:
                    channel_bindings[spec.semantic_role] = channel_id

        event_bindings = {}
        for role, combo in self._event_combos.items():
            group_name = combo.currentData()
            if group_name is not None:
                event_bindings[role] = group_name

        return {
            "channels": channel_bindings,
            "events": event_bindings,
        }

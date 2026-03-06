# main_gui.py
import sys
import json
from pathlib import Path
from datetime import datetime
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
    QMenuBar,
    QMenu,
    QMessageBox,
)
from PyQt6.QtGui import QAction
from tracengine.data.loader import (
    load_session,
    load_session_from_project,
    get_modality_channels,
)
from tracengine.project import load_project
from tracengine.project.structure import PROJECT_MANIFEST
from tracengine.gui.plot_window import PlotWindow
from tracengine.gui.panels.events_panel import EventsPanel
from tracengine.gui.dialogs.plugin_runner import PluginRunnerDialog
from tracengine.gui.dialogs.channel_binding import ChannelBindingDialog
from PyQt6.QtWidgets import QSplitter
from PyQt6.QtCore import Qt


class ChannelSelectorDialog(QDialog):
    def __init__(self, run_objects):
        super().__init__()
        self.setWindowTitle("Select Signals to Plot")
        self.run_objects = run_objects
        self.selected_channels = {}

        layout = QVBoxLayout()

        # Scroll area for many modalities
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # Assume single run for now (can extend later)
        run = run_objects[0]
        modality_dict = get_modality_channels(run)

        self.checkboxes = {}

        for modality, channels in modality_dict.items():
            scroll_layout.addWidget(QLabel(f"<b>{modality}</b>"))
            for channel in channels:
                cb = QCheckBox(channel)
                scroll_layout.addWidget(cb)
                self.checkboxes[(modality, channel)] = cb

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
        for (mod, channel), cb in self.checkboxes.items():
            if cb.isChecked():
                selections.setdefault(mod, []).append(channel)
        print("Selected channels:", selections)
        self.selected_channels = selections
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, initial_session_path: str | Path | None = None):
        super().__init__()
        self.setWindowTitle("TRACE")
        self.resize(600, 400)

        # Create menu bar
        self._create_menu_bar()

        # Create toolbar
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)

        load_action = QAction("Load Session", self)
        load_action.triggered.connect(self.load_session)
        toolbar.addAction(load_action)

        self.run_objects = []
        self.current_run = None
        self.project_config = None  # Will be set if loading from project

        # Auto-load session if provided
        if initial_session_path:
            self._auto_load_session(Path(initial_session_path))

    def _get_derived_path(self) -> Path:
        """Get the path for derived outputs (annotations, configs, provenance).

        When loading from a project, use the project's derived folder.
        Otherwise, fall back to session_path/derived for legacy sessions.
        """
        if self.project_config is not None:
            return self.project_config.paths.derived
        elif hasattr(self, "session_path") and self.session_path:
            return self.session_path / "derived"
        return None

    def _create_menu_bar(self):
        """Create the application menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        load_action = QAction("Load Session...", self)
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self.load_session)
        file_menu.addAction(load_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Analysis menu
        analysis_menu = menubar.addMenu("Analysis")

        run_annotator_action = QAction("Run Annotator...", self)
        run_annotator_action.triggered.connect(self._on_run_annotator)
        analysis_menu.addAction(run_annotator_action)

        run_compute_action = QAction("Run Compute...", self)
        run_compute_action.triggered.connect(self._on_run_compute)
        analysis_menu.addAction(run_compute_action)

        analysis_menu.addSeparator()

        configure_bindings_action = QAction("Configure Bindings...", self)
        configure_bindings_action.triggered.connect(self._on_configure_bindings)
        analysis_menu.addAction(configure_bindings_action)

        # Help menu
        help_menu = menubar.addMenu("Help")

        about_action = QAction("Version && License Info...", self)
        about_action.setMenuRole(
            QAction.MenuRole.NoRole
        )  # Prevent macOS from moving it
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _on_about(self):
        """Show the About dialog with version, license, and citation info."""
        from importlib.metadata import version, PackageNotFoundError

        try:
            pkg_version = version("tracengine")
        except PackageNotFoundError:
            pkg_version = "dev"

        about_text = f"""
<h2>TRACE</h2>
<p><b>Time-series Research, Annotation, and Computation Engine</b></p>
<p><b>Version:</b> {pkg_version}</p>
<hr>
<p><b>Author:</b> Abdullah Zafar</p>
<p><b>Email:</b> abdullah.zafar@umontreal.ca</p>
<p><b>ORCID:</b> <a href="https://orcid.org/0000-0002-7872-7715">0000-0002-7872-7715</a></p>
<hr>
<p><b>License:</b> BSD 3-Clause</p>
<p><b>Repository:</b> <a href="https://github.com/uw-dvnlab/tracengine">github.com/uw-dvnlab/tracengine</a></p>
<hr>
<p><i>If you use this software in your research, please cite it as below.</i></p>
<a href="https://doi.org/10.5281/zenodo.18245732">10.5281/zenodo.18245732</a>
"""
        msg = QMessageBox(self)
        msg.setWindowTitle("About TRACE")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(about_text)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.exec()

    def _on_run_annotator(self):
        """Open annotator runner dialog."""
        if not self.run_objects:
            QMessageBox.warning(self, "No Data", "Please load a session first.")
            return

        run = self._get_current_run()
        all_runs = self._get_all_runs()
        dialog = PluginRunnerDialog(
            run, plugin_type="annotator", all_runs=all_runs, parent=self
        )
        dialog.plugin_completed.connect(self._on_plugin_completed)
        dialog.bindings_changed.connect(self._on_bindings_changed)
        dialog.exec()

    def _on_run_compute(self):
        """Open compute runner dialog."""
        if not self.run_objects:
            QMessageBox.warning(self, "No Data", "Please load a session first.")
            return

        run = self._get_current_run()
        all_runs = self._get_all_runs()

        # Determine project directory
        project_dir = None
        if self.project_config:
            project_dir = self.project_config.root
        elif hasattr(self, "session_path") and self.session_path:
            project_dir = self.session_path

        dialog = PluginRunnerDialog(
            run,
            plugin_type="compute",
            all_runs=all_runs,
            project_dir=project_dir,
            parent=self,
        )
        dialog.plugin_completed.connect(self._on_plugin_completed)
        dialog.bindings_changed.connect(self._on_bindings_changed)
        dialog.exec()

    def _on_configure_bindings(self):
        """Open standalone channel binding dialog."""
        if not self.run_objects:
            QMessageBox.warning(self, "No Data", "Please load a session first.")
            return

        run = self._get_current_run()
        dialog = ChannelBindingDialog(
            run=run,
            required_channels={},  # Show all channels
            plugin_name="Run Configuration",
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Save the updated config
            self.save_run_config(run)

    def _on_plugin_completed(self, plugin_name, result):
        """Handle plugin completion - refresh UI."""
        run = self._get_current_run()

        # Refresh events panel if annotator
        if hasattr(self, "events_panel"):
            self.events_panel.set_run(run)

        # Save annotations/config
        self.save_annotations(run)

    def _get_current_run(self):
        """Get the currently active run."""
        if hasattr(self, "plot_window") and self.plot_window:
            return self.plot_window.runs[self.plot_window.current_run_idx]
        elif self.run_objects:
            return self.run_objects[0]
        return None

    def _get_all_runs(self):
        """Get all runs in the current session."""
        if hasattr(self, "plot_window") and self.plot_window:
            return self.plot_window.runs
        return self.run_objects

    def _on_bindings_changed(self):
        """Handle bindings changed signal - save configs for all runs."""
        for run in self._get_all_runs():
            self.save_run_config(run)

    def save_run_config(self, run_data):
        """Save run configuration to derived directory."""
        derived_dir = self._get_derived_path()
        if not derived_dir:
            return

        if not run_data.run_config:
            return

        from tracengine.data.loader import save_run_config

        derived_dir.mkdir(parents=True, exist_ok=True)
        run_id = (
            run_data.subject,
            run_data.session,
            run_data.metadata.get("task", "unknown"),
            run_data.metadata.get("condition", "unknown"),
            run_data.run,
        )

        save_run_config(derived_dir, run_id, run_data.run_config)
        print(f"Saved run config for run {run_data.run}")

    def start_manual_annotation(self, annotator_name, mode):
        # We need to store annotator name to pass back later?
        # Actually simplest is just to store it temporarily or pass it through if possible.
        # But PlotWindow doesn't know about annotator names.
        # Let's store it in MainWindow state
        self.pending_manual_annotator = annotator_name
        self.plot_window.start_annotation_mode(mode)

    def finish_manual_annotation(self, events):
        if hasattr(self, "pending_manual_annotator") and self.pending_manual_annotator:
            self.events_panel.finalize_manual_annotation(
                self.pending_manual_annotator, events
            )
            self.pending_manual_annotator = None

    def _auto_load_session(self, folder_path: Path):
        """Auto-load a session from a given path (called from CLI)."""
        self._load_session_from_path(folder_path)

    def load_session(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Project or Session Folder"
        )
        if folder:
            self._load_session_from_path(Path(folder))

    def _load_session_from_path(self, folder_path: Path):
        """Load session from a given path (shared by auto-load and manual load)."""
        manifest_path = folder_path / PROJECT_MANIFEST

        # Check if this is a project folder (has trace-project.yaml)
        if manifest_path.exists():
            self.project_config = load_project(folder_path)
            self.session_path = self.project_config.get_data_path()
            self.run_objects = load_session_from_project(self.project_config)

            # Discover and register custom plugins from project
            self._discover_project_plugins(self.project_config)
        else:
            # Legacy: treat as raw session folder
            self.project_config = None
            self.session_path = folder_path
            self.run_objects = load_session(self.session_path)

        if not self.run_objects:
            print("No runs found!")
            return

        # Skip channel selector - start with empty plot area
        # User will add channels via the channel browser
        selected = {}  # Empty - no initial plots

        # -----------------------------
        # Create the PyQtGraph plot UI
        # -----------------------------
        self.plot_window = PlotWindow(
            self.run_objects, selected, session_path=self.session_path
        )

        # Create Events Panel
        self.events_panel = EventsPanel()

        # Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.plot_window)
        splitter.addWidget(self.events_panel)
        splitter.setStretchFactor(0, 4)  # Plot gets more space
        splitter.setStretchFactor(1, 1)  # Events smaller

        self.setCentralWidget(splitter)

        # Connect signals
        self.plot_window.run_changed.connect(self.events_panel.set_run)
        self.events_panel.event_visibility_toggled.connect(
            self.plot_window.update_event_visibility
        )
        self.events_panel.event_selected.connect(self.plot_window.highlight_event)
        self.plot_window.event_selected_on_plot.connect(self.events_panel.select_event)
        self.plot_window.event_modified.connect(self.events_panel.update_event_display)
        self.plot_window.event_removed.connect(self.events_panel.remove_event)

        # Persistence
        self.events_panel.annotations_changed.connect(self.save_annotations)
        self.plot_window.channel_provenance_changed.connect(
            self.save_channel_provenance
        )

        # Manual Annotation Connections
        # (Signal removed from EventsPanel, this logic waits for new trigger mechanism)
        # self.events_panel.request_manual_annotation.connect(self.start_manual_annotation)
        self.plot_window.manual_annotation_completed.connect(
            self.finish_manual_annotation
        )

        # Initialize panel with current run (first run)
        if self.run_objects:
            self.events_panel.set_run(self.run_objects[0])

    def save_annotations(self, run_data):
        if not hasattr(self, "session_path") or not self.session_path:
            return

        # Construct filename
        # sub-{sub}_ses-{ses}_task-{task}_condition-{cond}_run-{run}_annotations.json
        sub = run_data.subject
        ses = run_data.session
        run_num = run_data.run
        # task and condition are in metadata
        task = run_data.metadata.get("task", "unknown")
        cond = run_data.metadata.get("condition", "unknown")

        fname = f"sub-{sub}_ses-{ses}_task-{task}_condition-{cond}_run-{run_num}_annotations.json"

        derived_dir = self._get_derived_path()
        if not derived_dir:
            return
        derived_dir.mkdir(parents=True, exist_ok=True)

        out_path = derived_dir / fname

        # Prepare data
        annotations_dict = {}
        for group, events in run_data.annotations.items():
            ev_list = []
            for ev in events:
                ev_data = {
                    "name": ev.name,
                    "onset": ev.onset,
                    "offset": ev.offset,
                    "confidence": ev.confidence,
                    "metadata": ev.metadata,
                }
                ev_list.append(ev_data)
            annotations_dict[group] = ev_list

        data = {
            "run_start_utc": run_data.start_time.isoformat(),
            "annotations": annotations_dict,
        }

        try:
            with open(out_path, "w") as f:
                json.dump(data, f, indent=2)
            print(f"Saved annotations to {out_path}")
        except Exception as e:
            print(f"Failed to save annotations: {e}")

    def save_channel_provenance(self, run_data):
        """Save channel provenance when derived channels are created."""
        if not hasattr(self, "session_path") or not self.session_path:
            return

        if not run_data.channel_provenance:
            return

        sub = run_data.subject
        ses = run_data.session
        run_num = run_data.run
        task = run_data.metadata.get("task", "unknown")
        cond = run_data.metadata.get("condition", "unknown")

        fname = f"sub-{sub}_ses-{ses}_task-{task}_condition-{cond}_run-{run_num}_channels.json"

        derived_dir = self._get_derived_path()
        if not derived_dir:
            return
        derived_dir.mkdir(parents=True, exist_ok=True)

        out_path = derived_dir / fname

        # Prepare data
        data = {}
        for channel_id, prov in run_data.channel_provenance.items():
            data[channel_id] = {
                "parents": prov.parents,
                "operation": prov.operation,
                "parameters": prov.parameters,
                "timestamp": prov.timestamp.isoformat(),
            }

        try:
            with open(out_path, "w") as f:
                json.dump(data, f, indent=2)
            print(f"Saved channel provenance to {out_path}")
        except Exception as e:
            print(f"Failed to save channel provenance: {e}")

    def _discover_project_plugins(self, project_config):
        """Discover and register custom plugins from project's plugins folder."""
        from tracengine.registry.discovery import discover_annotators, discover_compute
        from tracengine.annotate import get_registry as get_annotator_registry
        from tracengine.compute import get_registry as get_compute_registry

        plugins_path = project_config.paths.plugins

        # Discover annotators
        annotator_registry = get_annotator_registry()
        annotators = discover_annotators(plugins_path)
        for name, cls in annotators.items():
            annotator_registry.register(cls)
            print(f"Registered custom annotator: {name}")

        # Discover compute modules
        compute_registry = get_compute_registry()
        computes = discover_compute(plugins_path)
        for name, cls in computes.items():
            compute_registry.register(cls)
            print(f"Registered custom compute: {name}")


def run_trace_tool(session_path: str | Path | None = None):
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("TRACE")
    app.setApplicationDisplayName("TRACE")
    win = MainWindow(initial_session_path=session_path)
    win.show()
    sys.exit(app.exec())

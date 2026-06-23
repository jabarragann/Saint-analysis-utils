import argparse
import os
import shlex
import shutil
import signal
import sys
from pathlib import Path

import yaml
from PyQt5.QtCore import QProcess, QTimer
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class PathField(QWidget):
    def __init__(self, label, select_directory=True, save_file=False, parent=None):
        super().__init__(parent)
        self.select_directory = select_directory
        self.save_file = save_file

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel(label)
        self.label.setMinimumWidth(140)

        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText(label)

        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self._browse)

        layout.addWidget(self.label)
        layout.addWidget(self.line_edit)
        layout.addWidget(self.browse_button)

    def _browse(self):
        if self.save_file:
            path, _ = QFileDialog.getSaveFileName(self, "Select Output File")
        elif self.select_directory:
            path = QFileDialog.getExistingDirectory(self, "Select Directory")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if path:
            self.line_edit.setText(path)

    def text(self):
        return self.line_edit.text()


class ProcessRunnerPanel(QGroupBox):
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.process = None
        self._current_label = ""
        self._current_button = None

    def _run_command(self, label, program, args, cwd, button):
        if self.process is not None and self.process.state() != QProcess.NotRunning:
            print(f"[{label}] Another process is already running.")
            return

        print(f"[{label}] Running command:")
        print(shlex.join([program, *args]))

        self._current_label = label
        self._current_button = button
        self.process = QProcess(self)
        if cwd:
            self.process.setWorkingDirectory(cwd)
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_process_finished)
        button.setEnabled(False)
        self.process.start(program, args)

    def _on_stdout(self):
        data = bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        sys.stdout.write(data)
        sys.stdout.flush()

    def _on_stderr(self):
        data = bytes(self.process.readAllStandardError()).decode(errors="replace")
        sys.stderr.write(data)
        sys.stderr.flush()

    def _on_process_finished(self, exit_code, _exit_status):
        print(f"[{self._current_label} finished with exit code {exit_code}]")
        if self._current_button is not None:
            self._current_button.setEnabled(True)


class ExperimentSetupPanel(ProcessRunnerPanel):
    def __init__(self, config, parent=None):
        super().__init__("Experiment Setup", parent)

        scripts = config.get("script_paths", {}) or {}
        self.nrrd_to_adf_script = scripts.get("nrrd_to_adf_script", "")
        self.create_saint_config_script = scripts.get("create_saint_config_script", "")
        self.update_seg_nrrd_script = scripts.get("update_seg_nrrd_script", "")
        self.saint_config = config.get("saint_config", {}) or {}

        layout = QVBoxLayout(self)

        self.output_dir_field = PathField("experiment output", select_directory=True)
        self.segmentation_field = PathField(".seg.nrrd path", select_directory=False)
        self.fiducials_field = PathField("fiducials.json path", select_directory=False)

        self.output_dir_field.line_edit.setText(config.get("output_dir", ""))
        self.segmentation_field.line_edit.setText(config.get("segmentation_path", ""))
        self.fiducials_field.line_edit.setText(config.get("fiducials_path", ""))

        self.phantom_subdir = config.get("output_dir_structure", {}).get("phantom_dir", "")
        self.config_subdir = config.get("output_dir_structure", {}).get("config_dir", "")
        self.input_backup_subdir = config.get("output_dir_structure", {}).get("input_backup_dir", "")
        self.ros_bag_subdir = config.get("output_dir_structure", {}).get("ros_bag_dir", "")
        self.copy_input_files = bool(config.get("copy_input_files", False))

        self.create_phantom_button = QPushButton("Create Phantom")
        self.create_phantom_button.clicked.connect(self._on_create_phantom)

        self.create_config_button = QPushButton("Create Config")
        self.create_config_button.clicked.connect(self._on_create_config)

        button_row = QHBoxLayout()
        button_row.addWidget(self.create_phantom_button)
        button_row.addWidget(self.create_config_button)

        layout.addWidget(self.output_dir_field)
        layout.addWidget(self.segmentation_field)
        layout.addWidget(self.fiducials_field)
        layout.addLayout(button_row)

    def get_output_dir(self):
        return Path(self.output_dir_field.text())

    def get_config_dir(self):
        return self.get_output_dir() / self.config_subdir

    def get_phantom_dir(self):
        return self.get_output_dir() / self.phantom_subdir

    def get_input_backup_dir(self):
        return self.get_output_dir() / self.input_backup_subdir

    def get_ros_bag_dir(self):
        return self.get_output_dir() / self.ros_bag_subdir

    def _backup_input_files(self, nrrd_file, fiducial_filepath):
        backup_dir = self.get_input_backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)
        for src in (nrrd_file, fiducial_filepath):
            src_path = Path(src)
            if not src_path.is_file():
                print(f"[Create Phantom] Skipping backup, file not found: {src_path}")
                continue
            dst = backup_dir / src_path.name
            if dst.exists() and src_path.resolve() == dst.resolve():
                print(f"[Create Phantom] Skipping backup, file already in backup dir: {src_path}")
                continue
            print(f"[Create Phantom] Copying {src_path} -> {dst}")
            shutil.copy2(src_path, dst)

    def _on_create_phantom(self):
        nrrd_file = self.segmentation_field.text()
        fiducial_filepath = self.fiducials_field.text()
        adf_filepath = str(self.get_phantom_dir() / f"{Path(nrrd_file).stem}.yaml")
        slices_path = str(self.get_phantom_dir() / "slices")

        if self.copy_input_files:
            self._backup_input_files(nrrd_file, fiducial_filepath)

        args = [
            self.nrrd_to_adf_script,
            "--nrrd_file", nrrd_file,
            "--adf_filepath", adf_filepath,
            "-p", "slices00",
            "-s", "True",
            "--slices_path", slices_path,
            "--fiducial_filepath", fiducial_filepath,
            "-v", "mastoidectomy_volume",
        ]
        self._run_command(
            label="Create Phantom",
            program=sys.executable,
            args=args,
            cwd=str(Path(self.nrrd_to_adf_script).parent),
            button=self.create_phantom_button,
        )

    def _on_create_config(self):
        nrrd_file = self.segmentation_field.text()
        phantom_path = str(self.get_phantom_dir() / f"{Path(nrrd_file).stem}.yaml")
        script = self.create_saint_config_script
        saint_root = self.saint_config.get("saint_root", "")
        drill_size = self.saint_config.get("drill_size", "")
        drill_marker_namespace = self.saint_config.get("drill_marker_namespace", "")
        pointer_marker_namespace = self.saint_config.get("pointer_marker_namespace", "")
        drill_tool_tip = self.saint_config.get("drill_tool_tip", "drill_tip")
        pointer_tool_tip = self.saint_config.get("pointer_tool_tip", "pointer_tip")

        args = [
            script,
            "--saint-root", str(saint_root),
            "--drill-size", str(drill_size),
            "--phantom-path", phantom_path,
            "--drill-marker-namespace", str(drill_marker_namespace),
            "--pointer-marker-namespace", str(pointer_marker_namespace),
            "--drill-tool-tip", str(drill_tool_tip),
            "--pointer-tool-tip", str(pointer_tool_tip),
            "--output-dir", str(self.get_config_dir()),
        ]
        self._run_command(
            label="Create Config",
            program=sys.executable,
            args=args,
            cwd=str(Path(script).parent) if script else None,
            button=self.create_config_button,
        )


class UpdateSegmentationPanel(ProcessRunnerPanel):
    """Regenerate a .seg.nrrd from a folder of (possibly edited) PNG slices.

    Runs update_seg_nrrd_data_from_pngs.py, reusing the backed-up input
    segmentation for its header/colors. The slices folder defaults to the
    experiment's config/resources dir (where SAINT writes the PNGs) and the
    output field is pre-filled with output_dir/ambf_models/ so the user only
    has to append a file name.
    """

    SLICES_PREFIX = "plane00"

    def __init__(self, experiment_panel, parent=None):
        super().__init__("Update Segmentation from PNGs", parent)
        self.experiment_panel = experiment_panel
        self.update_seg_nrrd_script = experiment_panel.update_seg_nrrd_script

        layout = QVBoxLayout(self)

        self.slices_field = PathField("PNG slices folder", select_directory=True)
        self.output_field = PathField("output .seg.nrrd", select_directory=False, save_file=True)

        self.slices_field.line_edit.setText(str(experiment_panel.get_config_dir() / "resources"))
        # Pre-fill the output with the ambf_models dir (trailing separator) so it
        # is clearly incomplete until the user appends a file name.
        default_out = str(experiment_panel.get_output_dir() / "ambf_models") + os.sep
        self.output_field.line_edit.setText(default_out)
        self.output_field.line_edit.setPlaceholderText("append a .seg.nrrd file name (not a directory)")

        self.update_button = QPushButton("Update Segmentation")
        self.update_button.clicked.connect(self._on_run)

        layout.addWidget(self.slices_field)
        layout.addWidget(self.output_field)
        layout.addWidget(self.update_button)

    def _input_nrrd(self):
        # -n is the segmentation selected for the phantom, taken from the
        # backed-up copy in the input_backup dir.
        seg_name = Path(self.experiment_panel.segmentation_field.text()).name
        return self.experiment_panel.get_input_backup_dir() / seg_name

    def _on_run(self):
        script = self.update_seg_nrrd_script
        if not script:
            print("[Update Segmentation] No update_seg_nrrd_script configured.")
            return

        nrrd_file = self._input_nrrd()
        if not nrrd_file.is_file():
            print(f"[Update Segmentation] Input .seg.nrrd not found in backup dir: {nrrd_file}")
            return

        slices_path = Path(self.slices_field.text())
        if not slices_path.is_dir():
            print(f"[Update Segmentation] Slices folder does not exist: {slices_path}")
            return

        output_text = self.output_field.text().strip()
        if not output_text:
            print("[Update Segmentation] No output file specified.")
            return
        output_file = Path(output_text)
        if output_text.endswith(("/", os.sep)) or not output_file.name or output_file.is_dir():
            print(f"[Update Segmentation] Output must be a file name, not a directory: {output_text}")
            return
        output_file.parent.mkdir(parents=True, exist_ok=True)

        args = [
            script,
            "-n", str(nrrd_file),
            "-s", str(slices_path),
            "-p", self.SLICES_PREFIX,
            "-o", str(output_file),
        ]
        self._run_command(
            label="Update Segmentation",
            program=sys.executable,
            args=args,
            cwd=str(Path(script).parent),
            button=self.update_button,
        )


class RunRegistrationPanel(ProcessRunnerPanel):
    TF_LIST_OPTIONS = ["tf_config_drill.yaml", "tf_config_pointer.yaml"]

    def __init__(self, experiment_panel, parent=None):
        super().__init__("Run Registration", parent)
        self.experiment_panel = experiment_panel

        layout = QVBoxLayout(self)

        tf_row = QHBoxLayout()
        tf_label = QLabel("--tf_list")
        tf_label.setMinimumWidth(140)
        self.tf_list_combo = QComboBox()
        self.tf_list_combo.addItems(self.TF_LIST_OPTIONS)
        self.tf_list_combo.currentTextChanged.connect(self._on_tf_list_changed)
        tf_row.addWidget(tf_label)
        tf_row.addWidget(self.tf_list_combo)
        layout.addLayout(tf_row)

        self.command_edit = QTextEdit()
        self.command_edit.setLineWrapMode(QTextEdit.WidgetWidth)
        self.command_edit.setPlainText(self._build_command(self.tf_list_combo.currentText()))
        layout.addWidget(self.command_edit)

        self.run_button = QPushButton("Run Registration")
        self.run_button.clicked.connect(self._on_run)
        layout.addWidget(self.run_button)

    @staticmethod
    def _registration_config_for(tf_list):
        # The drill/pointer tf and registration configs share a naming scheme,
        # so the matching registration file is derived from the selected tf file.
        return tf_list.replace("tf_config", "registration_config")

    def _build_command(self, tf_list):
        program = "ambf_simulator"
        args = [
            "--launch_file", "launch_registration.yaml",
            "-l", "0,1",
            "--registration_config", self._registration_config_for(tf_list),
            "--tf_list", tf_list,
        ]
        return shlex.join([program, *args])

    def _set_arg(self, tokens, flag, value):
        # Update an existing flag's value in place, or append it if absent.
        if flag in tokens:
            idx = tokens.index(flag)
            if idx + 1 < len(tokens):
                tokens[idx + 1] = value
            else:
                tokens.append(value)
        else:
            tokens += [flag, value]
        return tokens

    def _on_tf_list_changed(self, tf_list):
        # Replace the --tf_list and matching --registration_config arguments in
        # the command shown, preserving any other manual edits the user made.
        current = self.command_edit.toPlainText().strip()
        if not current:
            self.command_edit.setPlainText(self._build_command(tf_list))
            return
        tokens = shlex.split(current)
        self._set_arg(tokens, "--tf_list", tf_list)
        self._set_arg(tokens, "--registration_config", self._registration_config_for(tf_list))
        self.command_edit.setPlainText(shlex.join(tokens))

    def _on_run(self):
        config_dir = self.experiment_panel.get_config_dir()
        if not config_dir.is_dir():
            print(f"[Run Registration] Config dir does not exist: {config_dir}")
            return

        command = self.command_edit.toPlainText().strip()
        if not command:
            print("[Run Registration] No command to run.")
            return

        tokens = shlex.split(command)
        program, args = tokens[0], tokens[1:]
        self._run_command(
            label="Run Registration",
            program=program,
            args=args,
            cwd=str(config_dir),
            button=self.run_button,
        )


class RunSaintPanel(ProcessRunnerPanel):
    def __init__(self, experiment_panel, parent=None):
        super().__init__("Run SAINT", parent)
        self.experiment_panel = experiment_panel

        layout = QVBoxLayout(self)
        self.run_button = QPushButton("Run SAINT")
        self.run_button.clicked.connect(self._on_run)
        layout.addWidget(self.run_button)

    def _on_run(self):
        config_dir = self.experiment_panel.get_config_dir()
        if not config_dir.is_dir():
            print(f"[Run SAINT] Config dir does not exist: {config_dir}")
            return

        args = [
            "--launch_file", "launch.yaml",
            "-l", "6,10,14",
            "--mute", "true",
            "--nt", "1",
            "--tf_list", "tf_config_drill.yaml",
        ]
        self._run_command(
            label="Run SAINT",
            program="ambf_simulator",
            args=args,
            cwd=str(config_dir),
            button=self.run_button,
        )


class DataRecordingPanel(ProcessRunnerPanel):
    def __init__(self, experiment_panel, parent=None):
        super().__init__("Data Recording", parent)
        self.experiment_panel = experiment_panel

        layout = QVBoxLayout(self)
        self.record_button = QPushButton("Record Data")
        self.record_button.clicked.connect(self._on_click)
        layout.addWidget(self.record_button)

    def _is_running(self):
        return self.process is not None and self.process.state() != QProcess.NotRunning

    def _on_click(self):
        if self._is_running():
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        bag_dir = self.experiment_panel.get_ros_bag_dir()
        bag_dir.mkdir(parents=True, exist_ok=True)

        program = "ros2"
        args = ["bag", "record", "/ambf/env/World/State"]

        print("[Data Recording] Running command:")
        print(shlex.join([program, *args]))

        self._current_label = "Data Recording"
        self._current_button = self.record_button
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(bag_dir))
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_recording_finished)
        self.process.start(program, args)
        self.record_button.setText("Stop Recording")
        self.record_button.setStyleSheet("background-color: #2ecc71; color: white;")

    def _stop_recording(self):
        pid = int(self.process.processId())
        if pid <= 0:
            print("[Data Recording] No PID available; cannot send SIGINT.")
            return
        print(f"[Data Recording] Sending SIGINT to PID {pid}")
        try:
            os.kill(pid, signal.SIGINT)
        except ProcessLookupError:
            print(f"[Data Recording] Process {pid} not found.")

    def _on_recording_finished(self, exit_code, _exit_status):
        print(f"[Data Recording finished with exit code {exit_code}]")
        self.record_button.setText("Record Data")
        self.record_button.setStyleSheet("")
        self.record_button.setEnabled(True)


class MainWindow(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.setWindowTitle("SAINT GUI")

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        experiment_panel = ExperimentSetupPanel(config)
        layout.addWidget(experiment_panel)
        layout.addWidget(RunRegistrationPanel(experiment_panel))
        layout.addWidget(RunSaintPanel(experiment_panel))
        layout.addWidget(DataRecordingPanel(experiment_panel))
        layout.addWidget(UpdateSegmentationPanel(experiment_panel))
        layout.addStretch()


def load_config(config_path):
    path = Path(config_path).expanduser().resolve()
    with path.open("r") as f:
        return yaml.safe_load(f) or {}


def main():
    parser = argparse.ArgumentParser(description="SAINT GUI")
    parser.add_argument("config", default="config/config.yaml", type=str, help="Path to YAML config file")
    args = parser.parse_args()

    config = load_config(args.config)

    app = QApplication(sys.argv)

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    # Keep the Python interpreter ticking so SIGINT can be delivered to the handler.
    timer = QTimer()
    timer.start(200)
    timer.timeout.connect(lambda: None)

    window = MainWindow(config)
    window.resize(600, 200)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

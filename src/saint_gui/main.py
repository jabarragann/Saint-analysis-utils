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
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class PathField(QWidget):
    def __init__(self, label, select_directory=True, parent=None):
        super().__init__(parent)
        self.select_directory = select_directory

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
        if self.select_directory:
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
        marker_namespace = self.saint_config.get("marker_namespace", "")

        args = [
            script,
            "--saint-root", str(saint_root),
            "--drill-size", str(drill_size),
            "--phantom-path", phantom_path,
            "--marker-namespace", str(marker_namespace),
            "--output-dir", str(self.get_config_dir()),
        ]
        self._run_command(
            label="Create Config",
            program=sys.executable,
            args=args,
            cwd=str(Path(script).parent) if script else None,
            button=self.create_config_button,
        )


class RunRegistrationPanel(ProcessRunnerPanel):
    def __init__(self, experiment_panel, parent=None):
        super().__init__("Run Registration", parent)
        self.experiment_panel = experiment_panel

        layout = QVBoxLayout(self)
        self.run_button = QPushButton("Run Registration")
        self.run_button.clicked.connect(self._on_run)
        layout.addWidget(self.run_button)

    def _on_run(self):
        config_dir = self.experiment_panel.get_config_dir()
        if not config_dir.is_dir():
            print(f"[Run Registration] Config dir does not exist: {config_dir}")
            return

        args = [
            "--launch_file", "launch_registration.yaml",
            "-l", "0,1",
            "--registration_config", "registration_config.yaml",
            "--tf_list", "tf_config.yaml",
        ]
        self._run_command(
            label="Run Registration",
            program="ambf_simulator",
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
            "--tf_list", "tf_config.yaml",
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

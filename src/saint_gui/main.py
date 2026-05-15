import argparse
import shlex
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


class ExperimentSetupPanel(QGroupBox):
    def __init__(self, config, parent=None):
        super().__init__("Experiment Setup", parent)

        self.nrrd_to_adf_script = config.get("nrrd_to_adf_script", "")
        self.saint_config = config.get("saint_config", {}) or {}
        self.process = None
        self._current_label = ""
        self._current_button = None

        layout = QVBoxLayout(self)

        self.output_dir_field = PathField("experiment output", select_directory=True)
        self.segmentation_field = PathField(".seg.nrrd path", select_directory=False)
        self.fiducials_field = PathField("fiducials.json path", select_directory=False)

        self.output_dir_field.line_edit.setText(config.get("output_dir", ""))
        self.segmentation_field.line_edit.setText(config.get("segmentation_path", ""))
        self.fiducials_field.line_edit.setText(config.get("fiducials_path", ""))

        self.phantom_subdir = config.get("output_dir_structure", {}).get("phantom_dir", "")
        self.config_subdir = config.get("output_dir_structure", {}).get("config_dir", "")

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

    def _on_create_phantom(self):
        output_dir = Path(self.output_dir_field.text())
        nrrd_file = self.segmentation_field.text()
        fiducial_filepath = self.fiducials_field.text()
        adf_filepath = str(output_dir / self.phantom_subdir / f"{Path(nrrd_file).stem}.yaml")
        slices_path = str(output_dir / self.phantom_subdir / "slices")

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
            args=args,
            cwd=str(Path(self.nrrd_to_adf_script).parent),
            button=self.create_phantom_button,
        )

    def _on_create_config(self):
        output_dir = Path(self.output_dir_field.text()) 
        nrrd_file = self.segmentation_field.text()
        phantom_path = str(output_dir / self.phantom_subdir / f"{Path(nrrd_file).stem}.yaml")
        script = self.saint_config.get("create_saint_config_script", "")
        saint_root = self.saint_config.get("saint_root", "")
        drill_size = self.saint_config.get("drill_size", "")
        marker_namespace = self.saint_config.get("marker_namespace", "")

        output_config_dir = output_dir / self.config_subdir

        args = [
            script,
            "--saint-root", str(saint_root),
            "--drill-size", str(drill_size),
            "--phantom-path", phantom_path,
            "--marker-namespace", str(marker_namespace),
            "--output-dir", str(output_config_dir),
        ]
        self._run_command(
            label="Create Config",
            args=args,
            cwd=str(Path(script).parent) if script else None,
            button=self.create_config_button,
        )

    def _run_command(self, label, args, cwd, button):
        if self.process is not None and self.process.state() != QProcess.NotRunning:
            print(f"[{label}] Another process is already running.")
            return

        program = sys.executable
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


class MainWindow(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.setWindowTitle("SAINT GUI")

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.addWidget(ExperimentSetupPanel(config))
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

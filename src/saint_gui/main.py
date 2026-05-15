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

        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText(label)

        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self._browse)

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
        self.process = None

        layout = QVBoxLayout(self)

        self.output_dir_field = PathField("Experiment output dir", select_directory=True)
        self.segmentation_field = PathField("Segmentation path", select_directory=False)
        self.fiducials_field = PathField("Fiducials path", select_directory=False)

        self.output_dir_field.line_edit.setText(config.get("output_dir", ""))
        self.segmentation_field.line_edit.setText(config.get("segmentation_path", ""))
        self.fiducials_field.line_edit.setText(config.get("fiducials_path", ""))

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
        if self.process is not None and self.process.state() != QProcess.NotRunning:
            print("Create Phantom is already running.")
            return

        output_dir = Path(self.output_dir_field.text())
        nrrd_file = self.segmentation_field.text()
        fiducial_filepath = self.fiducials_field.text()
        adf_filepath = str(output_dir / f"{Path(nrrd_file).stem}.yaml")
        slices_path = str(output_dir / "slices")

        program = sys.executable
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
        print("[Create Phantom] Running command:")
        print(shlex.join([program, *args]))

        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(Path(self.nrrd_to_adf_script).parent))
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_process_finished)
        self.create_phantom_button.setEnabled(False)
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
        print(f"[Create Phantom finished with exit code {exit_code}]")
        self.create_phantom_button.setEnabled(True)

    def _on_create_config(self):
        print("Create Config")
        print("Experiment output dir:", self.output_dir_field.text())
        print("Segmentation path:", self.segmentation_field.text())
        print("Fiducials path:", self.fiducials_field.text())


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

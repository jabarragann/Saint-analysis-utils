#!/usr/bin/env python
"""Generate SAINT config files from templates in data/sample_configs.

Reads the four template YAMLs, substitutes <SAINT_ROOT>, <DRILL_SIZE>, and
<PHANTOM_PATH> markers, and writes the resulting files to the output dir.
For registration_config.yaml, additionally fills in `object name` and
`name of points` from the bodies declared in the phantom YAML.
"""

from argparse import ArgumentParser
from pathlib import Path
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SCRIPT_DIR  / "config_templates"

TEMPLATE_FILES = [
    "launch.yaml",
    "launch_registration.yaml",
    "registration_config.yaml",
    "tf_config.yaml",
]

ANATOMICAL_ORIGIN_SUFFIX = "_Anatomical_Origin"


def substitute_markers(text: str, saint_root: str, drill_size: str, phantom_path: str, marker_namespace: str) -> str:
    return (
        text.replace("<SAINT_ROOT>", saint_root)
            .replace("<DRILL_SIZE>", drill_size)
            .replace("<PHANTOM_PATH>", phantom_path)
            .replace("<MARKER_NAMESPACE>", marker_namespace)
    )


def parse_phantom_bodies(phantom_path: Path):
    """Return (anatomical_origin_name, [fiducial_names]) from the phantom YAML."""
    with open(phantom_path, "r") as f:
        phantom = yaml.safe_load(f)

    body_entries = phantom.get("bodies", [])
    body_names = [b[len("BODY "):] if b.startswith("BODY ") else b for b in body_entries]

    anatomical_origin = None
    fiducials = []
    for name in body_names:
        if name.endswith(ANATOMICAL_ORIGIN_SUFFIX):
            anatomical_origin = name
        else:
            fiducials.append(name)

    if anatomical_origin is None:
        raise ValueError(
            f"No body with suffix '{ANATOMICAL_ORIGIN_SUFFIX}' found in {phantom_path}"
        )

    return anatomical_origin, fiducials


def generate_launch(output_dir: Path, saint_root: str, drill_size: str, phantom_path: str, marker_namespace: str) -> None:
    src = TEMPLATE_DIR / "launch.yaml"
    text = substitute_markers(src.read_text(), saint_root, drill_size, phantom_path, marker_namespace)
    (output_dir / "launch.yaml").write_text(text)


def generate_launch_registration(output_dir: Path, saint_root: str, drill_size: str, phantom_path: str, marker_namespace: str) -> None:
    src = TEMPLATE_DIR / "launch_registration.yaml"
    text = substitute_markers(src.read_text(), saint_root, drill_size, phantom_path, marker_namespace)
    (output_dir / "launch_registration.yaml").write_text(text)


def generate_tf_config(output_dir: Path, saint_root: str, drill_size: str, phantom_path: str, marker_namespace: str) -> None:
    src = TEMPLATE_DIR / "tf_config.yaml"
    text = substitute_markers(src.read_text(), saint_root, drill_size, phantom_path, marker_namespace)
    (output_dir / "tf_config.yaml").write_text(text)


def generate_registration_config(output_dir: Path, saint_root: str, drill_size: str, phantom_path: str, marker_namespace: str) -> None:
    src = TEMPLATE_DIR / "registration_config.yaml"
    text = substitute_markers(src.read_text(), saint_root, drill_size, phantom_path, marker_namespace)

    config = yaml.safe_load(text)

    anatomical_origin, fiducials = parse_phantom_bodies(Path(phantom_path))
    config["pointer"]["object name"] = anatomical_origin
    config["pointer"]["name of points"] = fiducials

    with open(output_dir / "registration_config.yaml", "w") as f:
        yaml.safe_dump(config, f, sort_keys=False)


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--saint-root", required=True, help="Value to substitute for <SAINT_ROOT>")
    parser.add_argument("--drill-size", required=True, help="Value to substitute for <DRILL_SIZE>")
    parser.add_argument("--phantom-path", required=True, help="Path to phantom YAML (substituted for <PHANTOM_PATH>)")
    parser.add_argument("--marker-namespace", required=True, help="ROS topic namespace (substituted for <MARKER_NAMESPACE>), e.g. /atracsys/drill_marker")
    parser.add_argument("--output-dir", required=True, help="Directory to write generated config files")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    phantom_path = str(Path(args.phantom_path).resolve())

    generate_launch(output_dir, args.saint_root, args.drill_size, phantom_path, args.marker_namespace)
    generate_launch_registration(output_dir, args.saint_root, args.drill_size, phantom_path, args.marker_namespace)
    generate_tf_config(output_dir, args.saint_root, args.drill_size, phantom_path, args.marker_namespace)
    generate_registration_config(output_dir, args.saint_root, args.drill_size, phantom_path, args.marker_namespace)

    print(f"Wrote {len(TEMPLATE_FILES)} config files to {output_dir}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""Generate SAINT config files from templates in config_templates.

Substitutes <SAINT_ROOT>, <DRILL_SIZE>, <PHANTOM_PATH>, and <MARKER_NAMESPACE>
markers and writes the resulting files to the output dir.

The drill and pointer tools each get their own tf and registration configs:
  - tf_config_drill.yaml / tf_config_pointer.yaml come from separate templates.
  - registration_config_drill.yaml / registration_config_pointer.yaml come from
    the same registration_config.yaml template and differ only in the substituted
    <MARKER_NAMESPACE>.
For the registration configs, `object name` and `name of points` are additionally
filled in from the bodies declared in the phantom YAML.
"""

from argparse import ArgumentParser
from pathlib import Path
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SCRIPT_DIR  / "config_templates"

ANATOMICAL_ORIGIN_SUFFIX = "_Anatomical_Origin"


def substitute_markers(text: str, saint_root: str, drill_size: str, phantom_path: str, marker_namespace: str, ambf_tool_tip: str = "") -> str:
    return (
        text.replace("<SAINT_ROOT>", saint_root)
            .replace("<DRILL_SIZE>", drill_size)
            .replace("<PHANTOM_PATH>", phantom_path)
            .replace("<MARKER_NAMESPACE>", marker_namespace)
            .replace("<AMBF_TOOL_TIP>", ambf_tool_tip)
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


def generate_tf_config(output_dir: Path, template_name: str, output_name: str, saint_root: str, drill_size: str, phantom_path: str, marker_namespace: str) -> None:
    src = TEMPLATE_DIR / template_name
    text = substitute_markers(src.read_text(), saint_root, drill_size, phantom_path, marker_namespace)
    (output_dir / output_name).write_text(text)


def generate_registration_config(output_dir: Path, output_name: str, saint_root: str, drill_size: str, phantom_path: str, marker_namespace: str, ambf_tool_tip: str) -> None:
    src = TEMPLATE_DIR / "registration_config.yaml"
    text = substitute_markers(src.read_text(), saint_root, drill_size, phantom_path, marker_namespace, ambf_tool_tip)

    config = yaml.safe_load(text)

    anatomical_origin, fiducials = parse_phantom_bodies(Path(phantom_path))
    config["pointer"]["object name"] = anatomical_origin
    config["pointer"]["name of points"] = fiducials

    with open(output_dir / output_name, "w") as f:
        yaml.safe_dump(config, f, sort_keys=False)


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--saint-root", required=True, help="Value to substitute for <SAINT_ROOT>")
    parser.add_argument("--drill-size", required=True, help="Value to substitute for <DRILL_SIZE>")
    parser.add_argument("--phantom-path", required=True, help="Path to phantom YAML (substituted for <PHANTOM_PATH>)")
    parser.add_argument("--drill-marker-namespace", required=True, help="ROS topic namespace for the drill marker (substituted for <MARKER_NAMESPACE> in the drill configs), e.g. /atracsys/drill_marker")
    parser.add_argument("--pointer-marker-namespace", required=True, help="ROS topic namespace for the pointer tool (substituted for <MARKER_NAMESPACE> in the pointer configs), e.g. /atracsys/pointer_tool")
    parser.add_argument("--drill-tool-tip", default="drill_tip", help="AMBF tooltip body name for the drill registration (substituted for <AMBF_TOOL_TIP>)")
    parser.add_argument("--pointer-tool-tip", default="pointer_tip", help="AMBF tooltip body name for the pointer registration (substituted for <AMBF_TOOL_TIP>)")
    parser.add_argument("--output-dir", required=True, help="Directory to write generated config files")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    phantom_path = str(Path(args.phantom_path).resolve())

    # The launch files don't reference <MARKER_NAMESPACE>; the drill namespace is
    # passed only to satisfy the substitution helper's signature.
    generate_launch(output_dir, args.saint_root, args.drill_size, phantom_path, args.drill_marker_namespace)
    generate_launch_registration(output_dir, args.saint_root, args.drill_size, phantom_path, args.drill_marker_namespace)

    generate_tf_config(output_dir, "tf_config_drill.yaml", "tf_config_drill.yaml", args.saint_root, args.drill_size, phantom_path, args.drill_marker_namespace)
    generate_tf_config(output_dir, "tf_config_pointer.yaml", "tf_config_pointer.yaml", args.saint_root, args.drill_size, phantom_path, args.pointer_marker_namespace)

    generate_registration_config(output_dir, "registration_config_drill.yaml", args.saint_root, args.drill_size, phantom_path, args.drill_marker_namespace, args.drill_tool_tip)
    generate_registration_config(output_dir, "registration_config_pointer.yaml", args.saint_root, args.drill_size, phantom_path, args.pointer_marker_namespace, args.pointer_tool_tip)

    print(f"Wrote config files to {output_dir}")


if __name__ == "__main__":
    main()

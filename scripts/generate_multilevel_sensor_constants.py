#!/usr/bin/env python3
"""Script to generate Multilevel Sensor CC constants."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
import json
import pathlib
import re
import subprocess
import sys

import requests
from slugify import slugify

GITHUB_PROJECT = "zwave-js/node-zwave-js"
BRANCH_NAME = "master"
SENSOR_TYPES_FILE_PATH = "packages/config/config/sensorTypes.json"
DEFAULT_SCALES_FILE_PATH = "packages/config/config/scales.json"

CONST_FILE_PATH = (
    pathlib.Path(__file__).parent.parent
    / "zwave_js_server/const/command_class/multilevel_sensor.py"
)


def remove_comments(text: str) -> str:
    """Remove comments from a JSON string."""
    return "\n".join(
        line for line in text.split("\n") if not line.strip().startswith("//")
    )


def remove_parenthesis(text: str) -> str:
    """Remove text in parenthesis from a string."""
    return re.sub(r"\([^)]*\)", "", text)


def enum_name_format(name: str, should_remove_parenthesis: bool) -> str:
    """Convert sensor/scale name to enum format."""
    if should_remove_parenthesis:
        name = remove_parenthesis(name)
    return slugify(name, separator="_").upper()


def normalize_name(name: str) -> str:
    """Convert a sensor/scale name into a normalized name."""
    return enum_name_format(name, True).replace("_", " ").title()


def format_for_class_name(name: str) -> str:
    """Convert sensor/scale name to class name format."""
    return f"{normalize_name(name).replace(' ', '')}Scale"


def normalize_scale_definition(scale_definitions: dict[str, dict]) -> dict[str, int]:
    """Convert a scales definition dictionary into a normalized dictionary."""
    scale_def_ = {}
    for scale_id, scale_props in scale_definitions.items():
        _scale_id = int(scale_id, 16)
        scale_name_ = enum_name_format(scale_props["label"], True)
        scale_def_[scale_name_] = _scale_id

    return dict(sorted(scale_def_.items(), key=lambda kv: kv[0]))


sensor_types = json.loads(
    remove_comments(
        requests.get(
            (
                f"https://raw.githubusercontent.com/{GITHUB_PROJECT}/{BRANCH_NAME}/"
                f"{SENSOR_TYPES_FILE_PATH}"
            ),
            timeout=10,
        ).text
    )
)
default_scales = json.loads(
    remove_comments(
        requests.get(
            (
                f"https://raw.githubusercontent.com/{GITHUB_PROJECT}/{BRANCH_NAME}/"
                f"{DEFAULT_SCALES_FILE_PATH}"
            ),
            timeout=10,
        ).text
    )
)

scales = {
    normalize_name(scale_name): normalize_scale_definition(scale_def)
    for scale_name, scale_def in default_scales.items()
}

sensors = {}
for sensor_id, sensor_props in sensor_types.items():
    sensor_id = int(sensor_id, 16)
    scale_def = sensor_props["scales"]
    remove_parenthesis_ = True
    if sensor_id in (87, 88):
        remove_parenthesis_ = False
    sensor_name = enum_name_format(sensor_props["label"], remove_parenthesis_)
    sensors[sensor_name] = {"id": sensor_id, "label": sensor_props["label"]}
    if isinstance(scale_def, str):
        sensors[sensor_name]["scale"] = normalize_name(
            scale_def.replace("$SCALES:", "")
        )
    else:
        scales[sensor_name] = normalize_scale_definition(scale_def)
        sensors[sensor_name]["scale"] = normalize_name(sensor_name)

scales = dict(sorted(scales.items(), key=lambda kv: kv[0]))
sensors = dict(sorted(sensors.items(), key=lambda kv: kv[0]))


def generate_int_enum_class_definition(
    class_name: str,
    enum_map: Mapping[str, int | str | dict],
    enum_ref_url: str | None = None,
    get_id_func: Callable | None = None,
    docstring_info: str = "",
    base_class: str = "IntEnum",
) -> list[str]:
    """Generate an IntEnum class definition as an array of lines of string."""
    class_def: list[str] = []
    class_def.append(f"class {class_name}({base_class}):")
    docstring = (
        f'"""Enum for known {docstring_info} multilevel sensor types."""'.replace(
            "  ", " "
        )
    )
    class_def.append(f"    {docstring}")
    if enum_ref_url:
        class_def.append(f"    # {enum_ref_url}")
    for enum_name, enum_id in enum_map.items():
        if get_id_func:
            enum_id = get_id_func(enum_id)
        class_def.append(f"    {enum_name} = {enum_id}")
    return class_def


def generate_int_enum_base_class(class_name: str, docstring: str) -> list[str]:
    """Generate an IntEnum base class definition."""
    class_def: list[str] = []
    class_def.append(f"class {class_name}(IntEnum):")
    class_def.append(f"\t{docstring}")
    return class_def


SENSOR_TYPE_URL = (
    f"https://github.com/{GITHUB_PROJECT}/blob/{BRANCH_NAME}/{SENSOR_TYPES_FILE_PATH}"
)

lines = [
    '"""Constants for the Multilevel Sensor CC."""',
    "",
    "# ----------------------------------------------------------------------------------- #",
    "# **BEGINNING OF AUTOGENERATED CONTENT** (TO ADD ADDITIONAL MANUAL CONTENT, LOOK FOR  #",
    '# THE "END OF AUTOGENERATED CONTENT" COMMENT BLOCK AND ADD YOUR CODE BELOW IT)        #',
    "# ----------------------------------------------------------------------------------- #",
    "",
    "from __future__ import annotations",
    "",
    "from enum import IntEnum",
    'CC_SPECIFIC_SCALE = "scale"',
    'CC_SPECIFIC_SENSOR_TYPE = "sensorType"',
    "",
]

lines.extend(
    [f"{sensor}_PROPERTY = \"{data['label']}\"" for sensor, data in sensors.items()]
)

lines.extend(
    generate_int_enum_class_definition(
        "MultilevelSensorType",
        sensors,
        SENSOR_TYPE_URL,
        get_id_func=lambda x: x["id"],
    )
)

lines.extend(
    generate_int_enum_base_class(
        "MultilevelSensorScaleType",
        docstring='"""Common base class for multilevel sensor scale enums."""',
    )
)

_unit_name_to_enum_map = defaultdict(list)
for scale_name, scale_dict in scales.items():
    lines.extend(
        generate_int_enum_class_definition(
            format_for_class_name(scale_name),
            scale_dict,
            SENSOR_TYPE_URL,
            docstring_info=f"scales for {scale_name}",
            base_class="MultilevelSensorScaleType",
        )
    )
    for unit_name in scale_dict.keys():
        _unit_name_to_enum_map[unit_name].append(
            f"{format_for_class_name(scale_name)}.{unit_name}"
        )
unit_name_to_enum_map = dict(
    sorted(_unit_name_to_enum_map.items(), key=lambda kv: kv[0])
)
for unit_name, enum_list in unit_name_to_enum_map.items():
    unit_name_to_enum_map[unit_name] = sorted(enum_list)


multilevel_sensor_type_to_scale_map_line = (
    "MULTILEVEL_SENSOR_TYPE_TO_SCALE_MAP: dict[MultilevelSensorType, "
    "type[MultilevelSensorScaleType]] = {"
)
for sensor_name, sensor_def in sensors.items():
    multilevel_sensor_type_to_scale_map_line += (
        f"    MultilevelSensorType.{sensor_name}: "
        f"{format_for_class_name(sensor_def['scale'])},"
    )
multilevel_sensor_type_to_scale_map_line += "}"
lines.append(multilevel_sensor_type_to_scale_map_line)
lines.append("")

for unit_name, unit_enums in unit_name_to_enum_map.items():
    lines.append(
        f"UNIT_{unit_name}: list[MultilevelSensorScaleType] = [{','.join(sorted(unit_enums))}]"
    )

lines.extend(
    [
        "",
        "# ----------------------------------------------------------------------------------- #",
        "# **END OF AUTOGENERATED CONTENT** (DO NOT EDIT/REMOVE THIS COMMENT BLOCK AND DO NOT  #",
        "# EDIT ANYTHING ABOVE IT. IF A NEW IMPORT IS NEEDED, UPDATE THE LINES AROUND 135      #",
        "# IN scripts/generate_multilevel_sensor_constants.py THEN RE-RUN THE SCRIPT. ALL      #",
        "# LINES WRITTEN BELOW THIS BLOCK WILL BE PRESERVED AS LONG AS THIS BLOCK REMAINS)     #",
        "# ----------------------------------------------------------------------------------- #",
        "",
    ]
)

existing_const_file = CONST_FILE_PATH.read_text(encoding="utf-8").splitlines()

manually_written_code_start_idx = (
    next(
        i
        for i, line in enumerate(existing_const_file)
        if "**END OF AUTOGENERATED CONTENT**" in line
    )
    + 6
)
if len(existing_const_file) > manually_written_code_start_idx:
    lines.extend(
        [
            line.strip("\n")
            for line in existing_const_file[manually_written_code_start_idx:]
        ]
    )

CONST_FILE_PATH.write_text("\n".join(lines), encoding="utf-8")

if subprocess.run(["which", "black"], capture_output=True, check=True).stdout:
    subprocess.run(
        ["black", CONST_FILE_PATH],
        check=True,
    )
else:
    print("Could not run black on new file, please run it to properly format it.")

if subprocess.run(["which", "git"], capture_output=True, check=True).stdout:
    if (
        subprocess.run(
            ["git", "diff", "--stat"],
            check=True,
        ).stdout
        is not None
    ):
        print("Repo is dirty and needs to be committed!")
        sys.exit(1)
else:
    print(
        "Could not run `git diff --stat` on repo, please run it to determine whether "
        "constants have changed."
    )

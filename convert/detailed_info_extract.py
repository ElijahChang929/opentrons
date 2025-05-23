# import importlib.util
# import os
# import sys
# from pathlib import Path
# from opentrons.simulate import simulate, format_runlog

# script_dir = Path(__file__).resolve().parent
# os.chdir(script_dir)


# for file in Path("protocols").glob("*.py"):
#     runlog, bundled = simulate(
#         protocol_file=open(f"protocols/{file.name}", "r"),
#     )

#     # write the runlog to a file
#     with open(f"protocols/log/{file.name}.log", "w") as f:
#         f.write(format_runlog(runlog))


import importlib.util
import os
import sys
from pathlib import Path
from opentrons.simulate import simulate, format_runlog
import builtins

def get_values(*names):

    import inspect
    import json
    import os

    # 尝试从全局变量拿真实 py 文件路径
    caller_globals = inspect.stack()[1].frame.f_globals
    caller_file = caller_globals.get("__protocol_file__")
    if not caller_file:
        raise RuntimeError("Cannot locate the original protocol file path (__protocol_file__ not set).")

    # 获取同级目录下的 field.json
    json_path = os.path.join(os.path.dirname(caller_file), "fields.json")
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"JSON config not found: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    fields = config
    values = []
    for name in names:
        value = None
        for field in fields:
            if field.get("name") == name:
                if "default" in field:
                    value = field["default"]
                elif "options" in field and field["options"]:
                    value = field["options"][0]["value"]
                break
        if value is None:
            raise ValueError(f"Field '{name}' not found or missing default/options in {json_path}")
        values.append(value)
    return tuple(values)

builtins.get_values = get_values

log_dir = Path("protocols/test/log")
os.makedirs(log_dir, exist_ok=True)



for file in Path("protocols/test").rglob("*.py"):
    print(f"Simulating: {file}")

    # 获取该 py 文件同级的 labware 目录
    labware_dir = (file.parent / "labware").resolve()  # use absolute path
    if labware_dir.exists() and labware_dir.is_dir():
        # 支持多个路径，用冒号:分隔（mac/linux），分号;分隔（windows），这里假设mac/linux
        prev_path = os.environ.get("OT_CUSTOM_LABWARE_PATH", "")
        # 保证不会重复加
        sep = ";" if os.name == "nt" else ":"
        labware_paths = [str(labware_dir)]
        if prev_path:
        # split existing path by sep, avoid duplicates, keep absolute paths
            labware_paths.extend([p for p in prev_path.split(sep) if p and p not in labware_paths])
        os.environ["OT_CUSTOM_LABWARE_PATH"] = sep.join(labware_paths)
    else:
        # 如果没有自定义labware目录，保留原本
        pass
    print("OT_CUSTOM_LABWARE_PATH = ", os.environ.get("OT_CUSTOM_LABWARE_PATH"))
    print("labware_dir exists: ", labware_dir.exists())
    print("all labware files: ", list(labware_dir.glob("**/*.json")))

    runlog, bundled = simulate(
        protocol_file=open(file, "r"),
    )

    rel_path = file.relative_to("protocols/test").with_suffix(".py.log")
    log_path = log_dir / rel_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w") as f:
        f.write(format_runlog(runlog))
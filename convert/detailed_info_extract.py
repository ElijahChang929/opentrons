import importlib.util
import os
import sys

from pathlib import Path
from opentrons.simulate import simulate, format_runlog

# 设置当前工作目录为脚本所在目录
script_dir = Path(__file__).resolve().parent
os.chdir(script_dir)

# 遍历original目录下的所有.py文件

for file in Path("protocols").glob("*.py"):
    runlog, bundled = simulate(
        protocol_file=open(f"protocols/{file.name}", "r"),
    )

    # write the runlog to a file
    with open(f"protocols/log/{file.name}.log", "w") as f:
        f.write(format_runlog(runlog))

#print(format_runlog(runlog))
# PYTHONPATH="../opentrons/api/src" python test_new.py
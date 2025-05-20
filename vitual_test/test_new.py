import importlib.util
import os
import sys

from pathlib import Path
from opentrons.simulate import simulate, format_runlog

# 现在可以使用自定义模块
runlog, bundled = simulate(
    protocol_file=open("sci-lucif-assay4.py", "r"),
   # propagate_logs=True,
   # log_level="debug"
)
#print(format_runlog(runlog))
# PYTHONPATH="../opentrons/api/src" python test_new.py
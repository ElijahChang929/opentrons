import sys
import importlib.util
import os

# 指定模块文件的完整路径
module_path = '/Users/guangxinzhang/Documents/Deep Potential/opentrons/api/src/opentrons/simulate.py'

# 以下是直接导入模块文件的方法
spec = importlib.util.spec_from_file_location('custom_simulate', module_path)
custom_simulate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(custom_simulate)

# 现在可以使用自定义模块
runlog, bundled = custom_simulate.simulate(
    protocol_file=open("sci-lucif-assay4.py", "r"),
    propagate_logs=True,
    log_level="debug"
)


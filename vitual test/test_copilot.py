from pathlib import Path
from opentrons.simulate import simulate
runlog, bundled = simulate(Path("sci-lucif-assay4.py").open()) 
#engine = bundled.engine  # >=v8.0 里可直接拿到
#print(engine.state_view.liquids.get_all())   # 打印所有井的液体状态


print(bundled)
Move function is in types.py (under opentrons/)

Air_gap, move_to, asp , dis, mix are in instrument_context.py

bottom and top is in labware.py


现在需要做的：

1. 检查别的protocol，看看是不是要调整逻辑

    a. move_to 位置应该更灵活，bottom 也可以
    b. move_to 可以是 center

2. 检查输出，看看有没有错

3. 大批量运行
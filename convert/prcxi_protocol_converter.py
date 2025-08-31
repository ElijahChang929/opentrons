from pprint import pprint
import json
import time
from platform import node
import pandas as pd
from collections import defaultdict
import networkx as nx
import re
from typing import List, Dict, Optional, Union, Sequence, Literal, Any
import networkx as nx
import os
from pathlib import Path
import inspect
_LABWARE_CACHE: Dict[tuple, Any] = {}
from typing import List, Dict, Any
import pprint as pp
from pylabrobot.resources.opentrons.tube_racks import *
from pylabrobot.resources.opentrons.tip_racks import *
from pylabrobot.resources.opentrons.reservoirs import *
import pylabrobot.resources.opentrons.reservoirs as reservoirs
from pylabrobot.resources.opentrons.plates import *
import pylabrobot.resources.opentrons.plates as plates
from pylabrobot.resources.opentrons.module import *
import pylabrobot.resources.opentrons.tip_racks as tip_racks_mod
import pylabrobot.resources.opentrons.tube_racks as tube_racks_mod

_DEF_WELL_COUNTS = (384, 96, 48, 24)

def _parse_well_count(name: str) -> int | None:
    s = name.lower()
    for k in _DEF_WELL_COUNTS:
        # 匹配独立数字（避免把 96 匹配到 196 等）
        if re.search(rf'(^|[^0-9]){k}([^0-9]|$)', s):
            return k
    return None

def _parse_capacity_ul(name: str) -> float | None:
    s = name.lower()
    m = re.search(r'(\d+(?:\.\d+)?)(\s*(?:u?l|[µμ]l|ml))', s, re.IGNORECASE)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2).strip().lower()
    if unit == 'ml':
        return val * 1000.0
    # 兼容 'ul' / 'u l' / 'µl' / 'μl'
    return val

def match_labware_class(class_name: str):
    """超简匹配：
    - 先看目标名里是否包含 well/pcr；若都不含，直接放弃匹配；
    - 提取孔数（仅 24/48/96/384），容量（若有）；
    - 在已导入的 plates 类（globals 里名称包含 'plate' 或 'wellplate' 或 'pcr'）中找同孔数；
    - 如有容量要求，挑 capacity >= 需求 且差值最小的；否则返回第一个同孔数候选。
    返回 (cls 或 None, 说明字符串)
    """
    name_l = class_name.lower()
    # Special case: trash – pick the largest reservoir available
    if 'trash' in name_l or 'reservoir' in name_l or 'waste' in name_l:

        trash_candidates = []  # (factory_fn, name, cap)
        for nm, obj in inspect.getmembers(reservoirs, inspect.isfunction):
            # 解析容量，选容量最大的
            cap = _parse_capacity_ul(nm) or 0.0
            trash_candidates.append((obj, nm, cap))
        if trash_candidates:
            trash_candidates.sort(key=lambda x: x[2], reverse=True)
            cls, nm, cap = trash_candidates[0]
            return cls, f"trash matched by max capacity: picked {nm} ({cap}uL)"
        return None, "no reservoir functions found for trash"
    
        # Tip racks: choose by tip volume (closest >= target if available)
    if 'tip' in name_l:
        import inspect
        target_cap = _parse_capacity_ul(class_name)  # may be None
        cands = []  # (factory_fn, name, cap)
        for nm, obj in inspect.getmembers(tip_racks_mod, inspect.isfunction):
            cap = _parse_capacity_ul(nm)
            cands.append((obj, nm, cap))
        if not cands:
            return None, 'no tip_rack factories found'
        if target_cap is not None:
            feasible = [(fn, nm, cap) for fn, nm, cap in cands if cap is not None and cap >= target_cap]
            if feasible:
                feasible.sort(key=lambda x: x[2] - target_cap)
                fn, nm, cap = feasible[0]
                return fn, f"tip rack by min over-cap: target={target_cap}uL, picked {nm} ({cap}uL)"
            # fallback: pick closest absolute difference if none are >=
            with_caps = [(fn, nm, cap) for fn, nm, cap in cands if cap is not None]
            if with_caps:
                with_caps.sort(key=lambda x: abs(x[2] - target_cap))
                fn, nm, cap = with_caps[0]
                return fn, f"tip rack by nearest: target={target_cap}uL, picked {nm} ({cap}uL)"
        # if no target cap or no caps in names, return first candidate
        fn, nm, cap = cands[0]
        return fn, f"tip rack fallback: chose {nm} (cap={cap})"

    # Tube racks (non-tip racks): try to match by capacity if present, else fallback
    if 'rack' in name_l and 'tip' not in name_l:
        import inspect
        target_cap = _parse_capacity_ul(class_name)  # may be None
        cands = []  # (factory_fn, name, cap)
        for nm, obj in inspect.getmembers(tube_racks_mod, inspect.isfunction):
            cap = _parse_capacity_ul(nm)
            cands.append((obj, nm, cap))
        if not cands:
            return None, 'no tube_rack factories found'
        if target_cap is not None:
            feasible = [(fn, nm, cap) for fn, nm, cap in cands if cap is not None and cap >= target_cap]
            if feasible:
                feasible.sort(key=lambda x: x[2] - target_cap)
                fn, nm, cap = feasible[0]
                return fn, f"tube rack by min over-cap: target={target_cap}uL, picked {nm} ({cap}uL)"
            with_caps = [(fn, nm, cap) for fn, nm, cap in cands if cap is not None]
            if with_caps:
                with_caps.sort(key=lambda x: abs(x[2] - target_cap))
                fn, nm, cap = with_caps[0]
                return fn, f"tube rack by nearest: target={target_cap}uL, picked {nm} ({cap}uL)"
        fn, nm, cap = cands[0]
        return fn, f"tube rack fallback: chose {nm} (cap={cap})"


    has_plate_keyword = ('well' in name_l) or ('pcr' in name_l)
    if not has_plate_keyword:
        return None, "skip: not a plate-like name (no 'well'/'pcr')"

    target_wells = _parse_well_count(class_name)
    if target_wells is None:
        return None, "skip: no 24/48/96/384 well count in name"

    target_cap = _parse_capacity_ul(class_name)


    candidates = []  # (factory_fn, name, wells, cap)
    for nm, obj in inspect.getmembers(plates, inspect.isfunction):
        nm_l = nm.lower()
        if not (('plate' in nm_l) or ('wellplate' in nm_l) or ('pcr' in nm_l) or ('well' in nm_l)):
            continue
        wells = _parse_well_count(nm)
        if wells != target_wells:
            continue
        cap = _parse_capacity_ul(nm)
        candidates.append((obj, nm, wells, cap))
    
    if not candidates:
        return None, f"no class with {target_wells}-well in imported plates"

    # 如果没有容量要求，返回第一个候选
    if target_cap is None:
        cls, nm, _, cap = candidates[0]
        return cls, f"matched by wells={target_wells} (no target cap); chose {nm} (cap={cap})"

    # 有容量要求：选择 cap>=target_cap 且 (cap-target_cap) 最小；若都无 cap 或 cap 小于需求，则退而选任一候选
    feasible = [(cls, nm, cap) for cls, nm, _, cap in candidates if (cap is not None and cap >= target_cap)]
    if feasible:
        feasible.sort(key=lambda x: x[2] - target_cap)
        cls, nm, cap = feasible[0]
        return cls, f"matched by wells={target_wells} and min over-cap: target={target_cap}uL, picked {nm} ({cap}uL)"

    # 没有容量信息或都不足，兜底：返回任一候选
    cls, nm, _, cap = candidates[0]
    return cls, f"fallback by wells={target_wells}; no feasible cap>=target ({target_cap}uL); chose {nm} (cap={cap})"

def build_heater_shaker_dict(step_lines: List[str]) -> Dict:
    """
    Extracts key parameters for a Heater‑Shaker phase:
    target_temperature, shake_speed, duration, wait flag, deactivate flags
    """
    data = {
        "template": "heater_shaker",
        "target_temperature": None,
        "wait_for_temp": False,
        "shake_speed": None,
        "duration_minutes": None,
        "deactivate_heater": False,
        "deactivate_shaker": False
    }
    for line in step_lines:
        if line.startswith("Setting Target Temperature of Heater-Shaker"):
            data["target_temperature"] = extract_float_after_keyword(line, "to")
        elif line.startswith("Waiting for Heater-Shaker"):
            data["wait_for_temp"] = True
        elif line.startswith("Setting Heater-Shaker to Shake at"):
            m = re.search(r'Shake at ([\d.]+) RPM', line)
            if m:
                data["shake_speed"] = float(m.group(1))
        elif line.startswith("Delaying"):
            dm = re.search(r'Delaying for (\d+) minutes', line)
            if dm:
                data["duration_minutes"] = int(dm.group(1))
        elif line.startswith("Deactivating Heater"):
            data["deactivate_heater"] = True
        elif line.startswith("Deactivating Shaker"):
            data["deactivate_shaker"] = True
    return data




def is_full_row(wells: List[str]) -> bool:
    """Returns True if all wells in a row (e.g., A1 to A12) are included"""
    if len(wells) < 12:
        return False
    row = wells[0][0]
    indices = sorted([int(w[1:]) for w in wells if w[0] == row])
    return indices == list(range(1, 13))



# def _scan_phase_markers(step_lines: List[str]) -> Tuple[Optional[int], Optional[int], List[int], Optional[Dict]]:
#     """
#     返回：
#       aspirate_index, dispense_index, mixing_indices, tip_rack_info
#     """
#     aspirate_index = None
#     dispense_index = None
#     mixing_indices: List[int] = []
#     tip_rack_info: Optional[Dict] = None

#     for i, line in enumerate(step_lines):
#         if line.startswith(" "):   # 忽略缩进行
#             continue
#         s = line.strip()
#         if s.startswith("Aspirating") and "from" in s and aspirate_index is None:
#             aspirate_index = i
#         elif s.startswith("Dispensing") and "into" in s and dispense_index is None:
#             dispense_index = i
#         elif s.startswith("Mixing"):
#             mixing_indices.append(i)
#         elif s.startswith("Picking up tip"):
#             m = re.search(r'from ([A-H]\d+) of (.*?) on (\d+)', s)
#             if m:
#                 tip_rack_info = {
#                     "well": m.group(1),
#                     "type": m.group(2).strip(),
#                     "slot": int(m.group(3))
#                 }
#     return aspirate_index, dispense_index, mixing_indices, tip_rack_info

# ---------- 2) 根据位置判断 mixing 阶段 ----------
# def _infer_mix_stage(asp_idx: Optional[int], disp_idx: Optional[int], mixing_indices: List[int]) -> str:
#     """
#     返回 'none' / 'before' / 'after' / 'both'
#     """
#     stage = "none"
#     for idx in mixing_indices:
#         if asp_idx is not None and idx < asp_idx:
#             stage = "before" if stage == "none" else "both"
#         elif disp_idx is not None and idx > disp_idx:
#             stage = "after" if stage == "none" else "both"
#     return stage

# ---------- 3) 第二遍：解析液体学操作 ----------
def _parse_liquid_ops(step_lines: List[str]) -> List[Dict]:
    """
    返回按原始顺序的动作列表；将连续的 Heater-Shaker 行聚合为一条:
      {"action":"heater_shaker",
       "target_temperature":float|None,
       "wait_for_temp":bool,
       "shake_speed":float|None,
       "duration_minutes":int|None,
       "deactivate_heater":bool,
       "deactivate_shaker":bool}
    其它动作同之前：aspirate/dispense/pick_tip/drop_tip/air_gap/blow_out/touch_tip/delay/magnet/temperature/raw
    """
    import re
    from typing import Optional, Dict, Union, List

    def f_after(s: str, kw: str) -> Optional[float]:
        m = re.search(rf'{re.escape(kw)}\s+([\d.]+)', s)
        return float(m.group(1)) if m else None

    def parse_container(line: str, mode_kw: str) -> Optional[Dict[str, Union[str, int]]]:
        m = re.search(
            rf'{re.escape(mode_kw)}\s+[\d.]*\s*u?L?.*?(?:from|into|at)\s+([A-H]\d+)\s+of\s+(.*?)\s+on\s+(\d+)',
            line
        )
        if not m:
            return None
        return {"well": m.group(1), "labware": m.group(2).strip(), "slot": int(m.group(3))}

    actions: List[Dict] = []
    # —— Heater-Shaker 聚合状态（遇到非 HS 行时 flush）——
    hs = None  # dict | None

    def flush_hs():
        nonlocal hs, actions
        if hs is not None:
            actions.append(hs)
            hs = None

    for raw in step_lines:
        s = raw.strip()
        if not s:
            continue

        # ===== Heater-Shaker 聚合 =====
        if s.startswith("Setting Target Temperature of Heater-Shaker") \
           or s.startswith("Waiting for Heater-Shaker") \
           or s.startswith("Setting Heater-Shaker to Shake at") \
           or s.startswith("Delaying") \
           or s.startswith("Deactivating Heater") \
           or s.startswith("Deactivating Shaker"):

            if hs is None:
                hs = {
                    "action": "heater_shaker",
                    "target_temperature": None,
                    "wait_for_temp": False,
                    "shake_speed": None,
                    "duration_minutes": None,
                    "deactivate_heater": False,
                    "deactivate_shaker": False
                }

            if s.startswith("Setting Target Temperature of Heater-Shaker"):
                # “… to XX”
                hs["target_temperature"] = f_after(s, "to")

            elif s.startswith("Waiting for Heater-Shaker"):
                hs["wait_for_temp"] = True

            elif s.startswith("Setting Heater-Shaker to Shake at"):
                m = re.search(r'Shake at\s+([\d.]+)\s*RPM', s)
                if m:
                    hs["shake_speed"] = float(m.group(1))

            elif s.startswith("Delaying"):
                m = re.search(r'Delaying for\s+(\d+)\s+minutes', s)
                if m:
                    hs["duration_minutes"] = int(m.group(1))

            elif s.startswith("Deactivating Heater"):
                hs["deactivate_heater"] = True

            elif s.startswith("Deactivating Shaker"):
                hs["deactivate_shaker"] = True

            # 注意：是“聚合”而不是立即落表，所以 continue
            continue

        # 走到这里说明当前行**不是** Heater-Shaker，先把上一个 hs flush 掉
        flush_hs()

        # ===== 常规液体学 / 其它模块 =====
        matched = False

        if s.startswith("Aspirating") and "from" in s:
            vol = f_after(s, "Aspirating")
            src = parse_container(s, "Aspirating")
            rate = f_after(s, "at")
            actions.append({"action": "aspirate",
                            "vol": vol if vol is not None else 0.0,
                            "source": src, "flow_rate": rate})
            matched = True

        elif s.startswith("Dispensing") and "into" in s:
            vol = f_after(s, "Dispensing")
            tgt = parse_container(s, "Dispensing")
            rate = f_after(s, "at")
            actions.append({"action": "dispense",
                            "vol": vol if vol is not None else 0.0,
                            "target": tgt, "flow_rate": rate})
            matched = True

        elif s.startswith("Picking up tip"):
            m = re.search(r'from ([A-H]\d+) of (.*?) on (\d+)', s)
            tip = {"well": m.group(1), "type": m.group(2).strip(), "slot": int(m.group(3))} if m else None
            actions.append({"action": "pick_tip", "tip_rack": tip})
            matched = True

        elif s.startswith("Dropping tip"):
            m = re.search(r'into ([A-H]\d+) of (.*?) on (\d+)', s)
            loc = {"well": m.group(1), "labware": m.group(2).strip(), "slot": int(m.group(3))} if m else None
            actions.append({"action": "drop_tip", "location": loc})
            matched = True

        elif s.startswith("Air gap"):
            m = re.search(r'Air gap(?:\s+with)?\s+([\d.]+)\s*u?L', s, re.IGNORECASE)
            vol = float(m.group(1)) if m else f_after(s, "Aspirating")
            actions.append({"action": "air_gap", "vol": vol})
            matched = True

        elif s.startswith("Blowing out"):
            m = re.search(r'Blowing out at\s+([A-H]\d+)\s+of\s+(.*?)\s+on\s+(\d+)', s)
            at = {"well": m.group(1), "labware": m.group(2).strip(), "slot": int(m.group(3))} if m else None
            actions.append({"action": "blow_out", "at": at})
            matched = True

        elif "Touching tip" in s:
            actions.append({"action": "touch_tip"})
            matched = True

        elif s.startswith("Delaying"):
            # 注意：此 delay 是**非** Heater-Shaker 的普通延时（因为前面已经 flush 了 hs）
            m = re.search(r'Delaying for\s+(\d+)\s+minutes(?:\s+and\s+([\d.]+)\s*seconds)?', s)
            minutes = int(m.group(1)) if m else None
            seconds = float(m.group(2)) if (m and m.group(2)) else None
            actions.append({"action": "delay", "minutes": minutes, "seconds": seconds})
            matched = True

        elif s.startswith("Engaging Magnetic Module"):
            actions.append({"action": "magnet", "state": "engage"})
            matched = True
        elif s.startswith("Disengaging Magnetic Module"):
            actions.append({"action": "magnet", "state": "disengage"})
            matched = True

        elif s.startswith("Setting Temperature Module temperature"):
            temp = f_after(s, "to")
            actions.append({"action": "temperature", "target": temp})
            matched = True
        elif s.startswith("Deactivating Temperature Module"):
            actions.append({"action": "temperature", "state": "off"})
            matched = True

        if not matched:
            actions.append({"action": "raw", "text": s})

    # 文件结尾如果还有挂着的 HS，别忘了收尾
    flush_hs()
    return actions
# # ---------- 4) 解析模块相关标志 ----------
# def _parse_module_flags(step_lines: List[str]):
#     """
#     返回：
#       temperature_target, temperature_deactivate,
#       magnetic_engage, magnetic_delay_minutes, magnetic_disengage
#     """
#     temperature_target = None
#     temperature_deactivate = False
#     magnetic_engage = False
#     magnetic_delay_minutes = None
#     magnetic_disengage = False

#     for line in step_lines:
#         if line.startswith(" "):
#             continue
#         s = line.strip()

#         if s.startswith("Setting Temperature Module temperature"):
#             temperature_target = extract_float_after_keyword(s, "to")
#         elif s.startswith("Deactivating Temperature Module"):
#             temperature_deactivate = True
#         elif s.startswith("Engaging Magnetic Module"):
#             magnetic_engage = True
#         elif s.startswith("Disengaging Magnetic Module"):
#             magnetic_disengage = True
#         elif s.startswith("Delaying") and magnetic_engage and not magnetic_disengage:
#             m = re.search(r'Delaying for (\d+) minutes', s)
#             if m:
#                 magnetic_delay_minutes = int(m.group(1))

#     return (temperature_target, temperature_deactivate,
#             magnetic_engage, magnetic_delay_minutes, magnetic_disengage)

# # ---------- 5) 是否 96 孔整行（多道） ----------
# def _compute_is_96_well(sources: List[Dict], targets: List[Dict]) -> bool:
#     source_wells = [s['well'] for s in sources]
#     target_wells = [t['well'] for t in targets]
#     return is_full_row(source_wells) and is_full_row(target_wells)

# # ---------- 6) 组装基础字段 ----------
# def _build_basic_info(sources, targets, tip_rack_info,
#                       asp_vols, asp_flow_rate, dis_vols, dis_flow_rate,
#                       blow_out_air_volume, is_96_well, mix_stage,
#                       mix_times, mix_vol, mix_rate, delays) -> Dict:
#     return {
#         "sources": sources,
#         "targets": targets,
#         "tip_racks": [tip_rack_info] if tip_rack_info else [],
#         "use_channels": None,
#         "asp_vols": asp_vols,
#         "asp_flow_rates": [asp_flow_rate] if asp_flow_rate else None,
#         "disp_vols": dis_vols,
#         "dis_flow_rates": [dis_flow_rate] if dis_flow_rate else None,
#         "offsets": None,
#         "touch_tip": any(["Touching tip" in str(x) for x in []]),  # 由上层填充；这里保持接口
#         "liquid_height": None,
#         "blow_out_air_volume": [blow_out_air_volume] if blow_out_air_volume else [0.0],
#         "is_96_well": is_96_well,
#         "mix_stage": mix_stage,
#         "mix_times": mix_times,
#         "mix_vol": mix_vol,
#         "mix_rate": mix_rate,
#         "mix_liquid_height": None,
#         "delays": delays
#     }

# ---------- 7) 主函数：只做编排 ----------
# def build_transfer_liquid_dict_complete(step_lines: List[str]) -> Dict:
#     # 第一遍：标记关键位置 & tip rack
#     # asp_idx, disp_idx, mixing_indices, tip_rack_info = _scan_phase_markers(step_lines)

#     # # pp.pprint({
#     # #     "asp_idx": asp_idx,
#     # #     "disp_idx": disp_idx,
#     # #     "mixing_indices": mixing_indices,
#     # #     "tip_rack_info": tip_rack_info
#     # # })

#     # mix_stage = _infer_mix_stage(asp_idx, disp_idx, mixing_indices)
    
#     # 第二遍：解析液体操作
#     (asp_vols, dis_vols, sources, targets, asp_flow_rate, dis_flow_rate,
#      blow_out_air_volume, mix_times, mix_vol, mix_rate, touch_tip, delays) = _parse_liquid_ops(step_lines)

#     # 模块标志
#     (temperature_target, temperature_deactivate,
#      magnetic_engage, magnetic_delay_minutes, magnetic_disengage) = _parse_module_flags(step_lines)

#     # 96 孔整行判定
#     is_96_well = _compute_is_96_well(sources, targets)

#     # 组装基础信息
#     basic_info = {
#         **_build_basic_info(sources, targets, tip_rack_info,
#                             asp_vols, asp_flow_rate, dis_vols, dis_flow_rate,
#                             blow_out_air_volume, is_96_well, mix_stage,
#                             mix_times, mix_vol, mix_rate, delays),
#         "touch_tip": touch_tip,  # 回填
#     }

#     # 模板分支
#     if magnetic_engage or magnetic_disengage:
#         return {
#             "template": "transfer_with_magnetic",
#             **basic_info,
#             "magnetic_engage": magnetic_engage,
#             "magnetic_delay_minutes": magnetic_delay_minutes,
#             "magnetic_disengage": magnetic_disengage
#         }
#     elif temperature_target is not None:
#         return {
#             "template": "transfer_with_temperature",
#             **basic_info,
#             "temperature_target": temperature_target,
#             "temperature_deactivate": temperature_deactivate
#         }
#     else:
#         return {"template": "transfer", **basic_info}



def collapse_mixes(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    把单个 phase 里连续的同孔 Aspirate→Dispense 对折叠为一条 mix：
      输出的 mix 结构：
        {
          "action": "mix",
          "well": str, "labware": str, "slot": int,
          "times": int,              # 成功折叠的 AD 对数
          "volume": float,           # 采用第一对的体积
          "speed": (asp_rate, dis_rate)  # 采用第一对的吸/放速率
        }
    其余动作保持原顺序。
    """
    out = []
    i, n = 0, len(actions)

    # 碰到这些动作就认为中断混匀序列
    breakers = {"pick_tip", "drop_tip", "touch_tip", "blow_out", "delay",
                "magnet", "temperature", "heater_shaker", "raw"}

    def same_container(a, b) -> bool:
        return bool(a and b and
                    a.get("well") == b.get("well") and
                    a.get("slot") == b.get("slot"))

    while i < n:
        # 尝试从 i 开始识别一段 aspirate->dispense（在位）
        if i + 1 < n:
            a0, d0 = actions[i], actions[i + 1]
            if (a0.get("action") == "aspirate"
                and d0.get("action") == "dispense"
                and same_container(a0.get("source"), d0.get("target"))):

                base_src   = a0.get("source")
                base_vol   = a0.get("vol")
                asp_rate0  = a0.get("flow_rate")
                dis_rate0  = d0.get("flow_rate")
                times = 1
                j = i + 2

                # 吃后续最大连续块：严格 AD 成对、同孔、体积一致、不中断
                while j + 1 < n:
                    x, y = actions[j], actions[j + 1]
                    if x.get("action") in breakers or y.get("action") in breakers:
                        break
                    if not (x.get("action") == "aspirate" and y.get("action") == "dispense"):
                        break
                    if not same_container(x.get("source"), y.get("target")):
                        break
                    # 体积不一致就停（如需速率也一致，可再加判断）
                    if x.get("vol") != base_vol:
                        break
                    times += 1
                    j += 2

                # times>=2 才折叠为 mix；只有一对就原样保留更直观
                if times >= 2:
                    out.append({
                        "action": "mix",
                        "well":   base_src.get("well"),
                        "labware":base_src.get("labware"),
                        "slot":   base_src.get("slot"),
                        "times":  times,
                        "volume": base_vol,
                        "speed":  (asp_rate0, dis_rate0)
                    })
                    i = j
                    continue
                else:
                    out.append(a0); out.append(d0)
                    i += 2
                    continue

        # 不是 mix 起点，原样输出一条
        out.append(actions[i])

        i += 1

    return out

def extract_asp_params(line):
# 例子：Aspirating 30.0 uL from A2 of reagent stock on 3 at 940.0 uL/sec
    m = re.match(r"Aspirating ([\d.]+) uL from ([A-H]\d+) of (.+) on (\d+) at ([\d.]+) uL/sec", line)
    if m:
        # 只返回体积和其它参数
        return {
            "vol": float(m.group(1)),
            "well": m.group(2),
            "labware": m.group(3).strip(),
            "slot": int(m.group(4)),
            "flow": float(m.group(5)),
        }
    return None


# ---------------------- Log parsing helpers (factored) ----------------------
_MODULE_START_PATTERNS = [
    r"Setting Target Temperature of Heater-Shaker",
    r"Engaging Magnetic Module",
    r"Deactivating Temperature Module",
    r"Disengaging Magnetic Module",
    r"Setting Temperature Module",
    r"Incubating"
]
_PREPOSITIONS = [' from ', ' to ', ' on ', ' of ', ' into ']

def _read_log_text(filename: str) -> str:
    """Return log text: prefer `text` arg, else read from `filename`."""
    with open(filename, "r", encoding="utf-8") as f:
        return f.read()

def _preprocess_text(raw: str) -> list[str]:
    """Normalize indentation-after-newline and split into non-empty lines."""
    text_ = re.sub(r'\n[ \t]+', '\n', raw)
    text_ = re.sub(r'\u00b5', 'u', text_)
    return [ln for ln in text_.strip().split('\n')]

def _filter_step_lines(lines: list[str]) -> list[str]:
    """Drop headers/noise and keep candidate step lines."""
    excluded_prefixes = [
        "Distributing",
        "Transferring",
        "/Users",
        "Congratulations!",
        "Caught exception:",
        "Deck calibration",
        "WARNING",
        "Protocol complete",
        "Seal and shake",
        "Pausing robot operation",
        "TRANSFERRING",
        "Centrifuge",
        "Removing",
        "Logs",
        "ERROR",
        "Moving to",
        "Returning tip",
        "Mixing",
        "Touching tip",
        "Transfer",
        "Protocol",
        "Air gap",
        "========",
        "~~","--",
        "THIS",
        "protocol",
        "There"
              ]
    steps = []
    for line in lines:
        if not line.strip():
            continue
        if line.startswith("        "):   # deep‑indented subline
            continue
        if line.endswith(":"):            # section headers
            continue
        if any(line.startswith(p) for p in excluded_prefixes):
            continue
        # cosmetic: show semicolon-separated subphrases on next visual line
        steps.append(line.replace(";", "\n        ").strip())
    return steps



def _group_phases(steps: list[dict], module_start_regex: re.Pattern) -> list[list[str]]:
    """Group raw lines into phases separated by module ops and 'new aspirate/tip' starts."""
    grouped_phases: list[list[str]] = []
    current_phase: list[str] = []
    aspirating_seen = False
    last_sentence = ""

    for step in steps:

        if module_start_regex.search(step):
            if current_phase:
                grouped_phases.append(current_phase)
                current_phase = []
                aspirating_seen = False

        # new liquid series if a 'standalone' Aspirating or a 'Picking up tip'
        starts_with_asp = step.startswith("Aspirating")
        #guard_prev = all(x not in last_sentence for x in ("Air gap","Transferring", "Picking up tip", "Aspirating"))
        guard_prev = all(x not in last_sentence for x in (
    "Moving to",  "Picking up tip",
    "Aspirating", "Dispensing"
))
        is_tip_pick = "Picking up tip" in step

        if is_tip_pick:
            if current_phase:
                grouped_phases.append(current_phase)
                current_phase = []
            aspirating_seen = True  # 新系列开始
        elif starts_with_asp and guard_prev:
            if aspirating_seen:
                grouped_phases.append(current_phase)
                current_phase = []
            aspirating_seen = True

        last_sentence = step
        current_phase.append(step)

    if current_phase:
        grouped_phases.append(current_phase)
    return grouped_phases

# def _merge_mixing_phases(grouped_phases: list[list[str]]) -> list[list[str]]:
#     belong_to_mixing = []
#     for i, phase in enumerate(grouped_phases):
#         if phase and "Mixing" in phase[-1]:
#             m = re.search(r"Mixing\s+(\d+)\s+times", phase[-1])
#             if not m:
#                 continue
#             mix_count = int(m.group(1))
#             max_take = min(mix_count, len(grouped_phases) - i - 1)
#             for j in range(1, max_take + 1):
#                 nxt = grouped_phases[i + j]
#                 head = nxt[0] if nxt else ""
#                 # --- 关键防护：遇到换枪就别合并 ---
#                 if head.startswith("Picking up tip") or any("Dropping tip" in ln for ln in nxt):
#                     break
#                 grouped_phases[i].extend(nxt)
#                 belong_to_mixing.append(i + j)
#     return [p for k, p in enumerate(grouped_phases) if k not in set(belong_to_mixing)]

def _merge_air_gaps_in_phase(phase: list[str]) -> None:
    """Within a single phase, merge 'Air gap' surrounded aspirates for same container."""
    to_remove = set()
    for idx, line in enumerate(phase):
        if not line.startswith("Air gap"):
            continue
        # search upward
        asp_up = asp_up_idx = None
        for i in range(idx - 1, -1, -1):
            if phase[i].startswith("Aspirating"):
                asp_up_idx = i
                asp_up = extract_asp_params(phase[i])
                break
        # search downward
        asp_down = asp_down_idx = None
        for i in range(idx + 1, len(phase)):
            if phase[i].startswith("Aspirating"):
                asp_down_idx = i
                asp_down = extract_asp_params(phase[i])
                break
        if asp_up and asp_down:
            if all(asp_up[k] == asp_down[k] for k in ("well", "labware", "slot")):
                new_vol = asp_up["vol"] + asp_down["vol"]
                phase[asp_up_idx] = re.sub(r"Aspirating ([\d.]+) uL",
                                           f"Aspirating {new_vol} uL",
                                           phase[asp_up_idx])
                to_remove.add(asp_down_idx)
    for i in sorted(to_remove, reverse=True):
        del phase[i]

def _merge_consecutive_ops_in_phase(phase: list[str]) -> None:
    """Merge consecutive Aspirating/Dispensing lines by summing volumes."""
    to_remove = set()
    idx = 0
    while idx < len(phase) - 1:
        cur, nxt = phase[idx], phase[idx + 1]
        if cur.startswith("Aspirating") and nxt.startswith("Aspirating"):
            v = float(re.search(r"Aspirating ([\d.]+)", cur).group(1))
            v2 = float(re.search(r"Aspirating ([\d.]+)", nxt).group(1))
            phase[idx] = re.sub(r"Aspirating [\d.]+", f"Aspirating {v + v2}", cur)
            to_remove.add(idx + 1)
            idx += 1
        elif cur.startswith("Dispensing") and nxt.startswith("Dispensing"):
            v = float(re.search(r"Dispensing ([\d.]+)", cur).group(1))
            v2 = float(re.search(r"Dispensing ([\d.]+)", nxt).group(1))
            phase[idx] = re.sub(r"Dispensing [\d.]+", f"Dispensing {v + v2}", cur)
            to_remove.add(idx + 1)
            idx += 1
        else:
            idx += 1
    for i in sorted(to_remove, reverse=True):
        del phase[i]
# ---------------------------------------------------------------------------



def coalesce_transfer_phases(phases):
    """把相邻路由一致的液体移动 phase 合并；纯 mix 的 phase 若与上下相邻路由槽位重合，也并入对应块。"""

    def _phase_route(phase_actions):
        """返回 (src_slot, dst_slot) 或 None。要求 aspirate/dispense 各自的槽位唯一。"""
        src_slots = {
            a["source"]["slot"]
            for a in phase_actions
            if a.get("action") == "aspirate" and a.get("source") and "slot" in a["source"]
        }
        dst_slots = {
            a["target"]["slot"]
            for a in phase_actions
            if a.get("action") == "dispense" and a.get("target") and "slot" in a["target"]
        }
        if src_slots and dst_slots and len(src_slots) == 1 and len(dst_slots) == 1:
            return (next(iter(src_slots)), next(iter(dst_slots)))
        return None

    def _mix_slots(phase_actions):
        """收集本 phase 中 mix 涉及的槽位集合（若有）。"""
        return {
            a.get("slot")
            for a in phase_actions
            if a.get("action") == "mix" and isinstance(a.get("slot"), int)
        }

    high_level = []
    cur = None  # 正在合并的 transfer_liquid 块：{"template":"transfer_liquid","route_key":(s,d),"route":{...},"actions":[...]}
    pending_mix = []  # 暂存需要并入“下一段路由”的 mix-only actions

    i = 0
    while i < len(phases):
        actions = phases[i]
        route = _phase_route(actions)

        # 在处理当前段前，若有挂起的 pending_mix 且“当前段是路由段”，且槽位重合，则把 pending_mix 先并入
        if pending_mix and route is not None:
            s, d = route
            mix_slots = {a.get("slot") for a in pending_mix if a.get("action") == "mix"}
            if (s in mix_slots) or (d in mix_slots):
                # 若当前已有合并块且路由匹配，就把 pending_mix 追加到当前块；
                # 否则开新块并把 pending_mix 放前面
                if cur is not None and cur.get("template") == "transfer_liquid" and cur.get("route_key") == route:
                    cur["actions"].extend(pending_mix)
                else:
                    if cur is not None:
                        high_level.append(cur)
                    cur = {
                        "template": "transfer_liquid",
                        "route_key": route,
                        "route": {"source_slot": s, "target_slot": d},
                        "actions": list(pending_mix),  # 先塞 pending_mix
                    }
                pending_mix = []  # 清空

        if route is None:
            # 非路由段：优先尝试作为 mix-only 并入上下
            mix_slots = _mix_slots(actions)

            if mix_slots:
                # 1) 先尝试并到“当前已开的路由块”
                if cur is not None and cur.get("template") == "transfer_liquid":
                    s, d = cur["route_key"]
                    if (s in mix_slots) or (d in mix_slots):
                        cur["actions"].extend(actions)
                        i += 1
                        continue

                # 2) 向前看下一段
                next_route = _phase_route(phases[i + 1]) if (i + 1 < len(phases)) else None
                if next_route is not None:
                    s2, d2 = next_route
                    if (s2 in mix_slots) or (d2 in mix_slots):
                        # 先挂起，等下一段路由时并入
                        pending_mix.extend(actions)
                        i += 1
                        continue

            # 3) 上下都并不进去，则当作 other_devices 落地
            if cur is not None:
                high_level.append(cur)
                cur = None
            high_level.append({"template": "other_devices", "actions": actions})
            i += 1
            continue

        # 路由段：常规合并
        if cur is not None and cur.get("template") == "transfer_liquid" and cur.get("route_key") == route:
            cur["actions"].extend(actions)
        else:
            if cur is not None:
                high_level.append(cur)
            s, d = route
            cur = {
                "template": "transfer_liquid",
                "route": {"source_slot": s, "target_slot": d},
                "actions": list(actions),
            }
        i += 1

    # 循环结束：如果还挂着 pending_mix，尽量塞到当前块；否则单独落地
    if pending_mix:
        if cur is not None and cur.get("template") == "transfer_liquid":
            cur["actions"].extend(pending_mix)
        else:
            high_level.append({"template": "other_devices", "actions": pending_mix})

    if cur is not None:
        high_level.append(cur)

    return high_level

def process_liquid_handler_log(filename: str = "test.log", name: str = "") -> List[Dict]:
    """
    Parse an Opentrons liquid‑handler log into structured phases and summarize them.
    Steps:
      1) read + preprocess
      2) filter candidate lines
      3) tokenize (debug) and group into phases
      4) merge mixing/air‑gap/consecutive ops
      5) build structured dicts and merge adjacent compatible blocks
    """
   
    raw = _read_log_text(filename)
    lines = _preprocess_text(raw)
    steps = _filter_step_lines(lines)
    
    # debug tokenization (kept for visibility)
    module_start_regex = re.compile("|".join(_MODULE_START_PATTERNS))
    grouped_phases = _group_phases(steps, module_start_regex)
    #grouped_phases = _merge_mixing_phases(grouped_phases)
    # with open(f"test_tmp/cleaned_phases_{name}.txt", "w") as f:
    #     for phase in grouped_phases:
    #         for line in phase:
    #             f.write(line + "\n")
    #         f.write("\n" + "="*40 + "\n")  # 每个 phase 之间加分隔线


    phases = []
    for phase_lines in grouped_phases:
        phases.append(collapse_mixes(_parse_liquid_ops(phase_lines)))

    # 相邻同路由的“移动液体”phase 合并；其余落 other_devices
    high_level_steps = coalesce_transfer_phases(phases)

    # 如果还想保留原始 phases，可同时写两个文件；否则直接覆盖原输出
    with open(f"test_tmp/outputs_{name}.json", "w") as f:
        json.dump(high_level_steps, f, indent=4)

    # final_outputs = collapse_mixes(outputs)


    return #final_outputs

def extract_labware_info_from_json(json_data: dict) -> list:
    """
    从 Opentrons JSON 配置中提取板位信息，转换为结构化格式。
    """
    labware_list = json_data.get("labware", [])
    if len(labware_list) > 6:
        raise ValueError("Labware list exceeds 6 items, which is not supported by the PRCXI.")
    import re

    output = []
    replace_map = {}
    # 直接把标号强行转换为1-6
    container_char = ['wellplate', 'well', 'pcr']
    for i, lw in enumerate(labware_list):

        class_name = lw.get("type")
        # replace '.' in class_name as 'point'
        class_name = re.sub(r'\.', 'point', class_name)
        #print(class_name)
        # 判断 class_name 是否包含 container_char 的任一关键词
        if any(c in class_name.lower() for c in container_char):
            liquid_vol = 200.0
            # 用正则匹配体积：例如 12.5ul / 0.5ml
            match = re.search(r'(\d+)\.(\d+)([mu]l)', class_name, re.IGNORECASE)
            if match:
                num1, num2, unit = match.groups()
                value = float(f"{num1}.{num2}")
                # 单位换算：统一转成 µL
                if unit.lower() == "ml":
                    liquid_vol = value * 1000.0
                elif unit.lower() == "ul":
                    liquid_vol = value
            else:
                # 没匹配到小数，尝试匹配整数
                match_int = re.search(r'(\d+)([mu]l)', class_name, re.IGNORECASE)
                if match_int:
                    num, unit = match_int.groups()
                    value = float(num)
                    if unit.lower() == "ml":
                        liquid_vol = value * 1000.0
                    elif unit.lower() == "ul":
                        liquid_vol = value
            #print(class_name, liquid_vol)

        prcxi_id = lw.get("name")
        new_id = re.sub(r'on \d+', f'on {i+1}', prcxi_id)
        new_id = re.sub(r' ', '_', new_id)
        replace_map[lw.get("slot")] = i+1
        output.append({
            "id": new_id,
            "parent": "deck",
            "slot_on_deck": i+1,
            "class_name": class_name,
            "liquid_type": [],
            "liquid_volume": [liquid_vol],
            "liquid_input_wells": []    
        })


    return output, replace_map
import re, inspect

def expend_labware_info(class_name: str, name: str = "labware", slot: int = 1):
    """
    传入：class_name（字符串），可选 name（将作为资源名；会清洗为[a-zA-Z0-9_]），slot（整数）
    返回：实例对象 或 None
    """
    if not isinstance(class_name, str) or not class_name:
        #print(f"[WARN] expend_labware_info: invalid class_name={class_name!r}")
        return None

    safe_name = f"{sanitize_name(name or 'labware')}_on_{slot}"

    try:
        cls = globals().get(class_name)
        if cls is None:
            cand, reason = match_labware_class(class_name)
            if cand is None:
                print(f"[WARN] No match for '{class_name}': {reason}")
                return None
            #print(f"[INFO] Matched '{class_name}' -> '{getattr(cand,'__name__',str(cand))}' ({reason})")
            cls = cand

        # 尝试实例化：优先带 name；如果签名里没有 name 就无参
        if isinstance(cls, type):
            try:
                inst = cls(name=safe_name)
            except TypeError:
                inst = cls()
        elif callable(cls):
            sig = inspect.signature(cls)
            if "name" in sig.parameters:
                inst = cls(name=safe_name)
            else:
                inst = cls()
        else:
            #print(f"[WARN] Candidate not callable/type: {cls}")
            return None

        #print(f"[OK] Instantiated {getattr(cls,'__name__',str(cls))} as name='{safe_name}'")
        #pprint(inst.serialize())
        return inst

    except Exception as e:
        #print(f"[ERROR] expend_labware_info('{class_name}', name='{safe_name}') -> {e}")
        return None
    
def sanitize_name(name: str) -> str:
    name = (name
            .replace("µL", "ul").replace("μL", "ul")
            .replace("µl", "ul").replace("μl", "ul")
            .replace("uL", "ul").replace("UL", "ul"))
    name = re.sub(r"[^0-9a-zA-Z_]", "_", name)
    return name


def refine_wells(labware_info: List[Dict[str, Any]], liquid_info: List[Dict[str, Any]], protocol_steps: List[Dict[str, Any]]):
    # 给labware_info添加液体信息
    for labware in labware_info:
        for liquid_key, liquid_val in liquid_info.items():
            if labware["slot_on_deck"] == int(liquid_val["slot"]):
                clean_key = re.sub(r'[^0-9a-zA-Z_]', '_', liquid_key)
                labware["liquid_type"].append(clean_key)
                labware["liquid_input_wells"].append(liquid_val["well"])
        labware["liquid_volume"] = labware["liquid_volume"] * len(labware["liquid_input_wells"])
        #
        # print(labware)
    # 收集 protocol 里将会用到的唯一 (class_name, slot) 组合
    unique_pairs = set()
    for step in protocol_steps:
        for term in ("tip_racks", "sources", "targets"):
            for it in step.get(term, []) or []:
                cls_name = it.get("labware") or it.get("type")
                slot = it.get("slot")
                if cls_name and slot is not None:
                    unique_pairs.add((cls_name, slot))

    # 只对每个唯一 (class_name, slot) 实例化一次，并缓存
    for cls_name, slot in sorted(unique_pairs, key=lambda x: (x[0], x[1])):
        key = (cls_name, slot)
        if key in _LABWARE_CACHE:
            continue
        inst = expend_labware_info(cls_name, name=cls_name, slot=slot)
        _LABWARE_CACHE[key] = inst
        

    # —— 新增：把 step 里的 wells 改成带前缀的完整路径 ——
    for step in protocol_steps:
        for term in ("tip_racks", "sources", "targets"):
            items = step.get(term, []) or []
            for it in items:
                cls_name = it.get("labware") or it.get("type")
                slot = it.get("slot")
                if cls_name and slot is not None:
                    inst = _LABWARE_CACHE.get((cls_name, slot))
                    if inst is not None:
                        dev_name = getattr(inst, "name", None) or sanitize_name(f"{cls_name}_on_{slot}")
                        orig_well = it.get("well")
                        if orig_well:
                            it["well"] = f"/PRCXI9300/deck/{dev_name}/{inst._ordering.get(orig_well)}"
            step[term] = items

    return labware_info
        

def _clean_micro_symbol(obj):
    if isinstance(obj, str):
        return obj.replace("\u00b5", "u").replace("µ", "u").replace("μ", "u")
    elif isinstance(obj, dict):
        return {k: _clean_micro_symbol(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_micro_symbol(v) for v in obj]
    else:
        return obj

def build_protocol_graph(labware_info: List[Dict[str, Any]], protocol_steps: List[Dict[str, Any]]) -> nx.DiGraph:
    """
    构建包含物料创建和步骤节点的 protocol graph。
    每个节点代表一个操作或物料；每条边表示数据/物料流动。
    """
    G = nx.DiGraph()
    slot_last_writer = {}  # 记录每个 slot 上次的输出节点（transfer/heater_shaker）

    labware_ids = {lw["id"] for lw in labware_info}
    # Step 1: 添加物料创建节点
    for labware in labware_info:
        node_id = labware["id"]
        G.add_node(node_id, template="create_resource", **labware)
        slot = labware["slot_on_deck"]
        slot_last_writer[slot] = node_id
    #print(json.dumps(protocol_steps,indent=4))
    # Step 2: 添加 protocol 步骤节点及边
    for i, step in enumerate(protocol_steps):
        node_id = f"step_{i+1}"
        G.add_node(node_id, **step)

        if step["template"].startswith("transfer"):
            for port_type, port_name in [("sources", "sources"), ("targets", "targets"), ("tip_racks", "tip_racks")]:
                items = step.get(port_type, [])
               
                item = items[0] 
                slot = item.get("slot")
                if slot is not None:
                    prev_node = slot_last_writer.get(slot)
                    if prev_node:
                        source_port = "labware" if prev_node in labware_ids else f"{port_name}_out"
                        G.add_edge(prev_node, node_id, source_port=source_port, target_port=port_name)
                    if port_type != "tip_racks":
                        slot_last_writer[slot] = node_id
                G.nodes[node_id][port_type] = step[port_type] = [item["well"] for item in items]

        elif step["template"] == "heater_shaker":
            slot = step.get("targets", [{}])[0].get("slot", None)
            if slot is not None:
                prev_node = slot_last_writer.get(slot)
                if prev_node:
                    G.add_edge(prev_node, node_id, source_port="plate", target_port="plate")
                slot_last_writer[slot] = node_id

    return G




def build_ordered_action_dict(detail_action):
    ordered_action_dict = {}
    move_to_list = []
    prev_main_idx = -1
    last_order = 0
    # helper -------------------------------------------------------
    def collect_sub(prev_idx: int, cur_idx: int):
        """Collect sub‑events between two indices, exclusive of cur_idx."""
        buckets = defaultdict(list)
        for k in range(prev_idx + 1, cur_idx):
            sub = detail_action[k]
            buckets[sub["event"]].append(sub)
        return buckets
    # --------------------------------------------------------------
    for i, evt in enumerate(detail_action):
        evt_type = evt.get("event")

        # --------------------------------------------------- MAIN ACTIONS
        if evt_type in {"aspirate", "dispense"}:
            order = evt["order"]
            buckets = collect_sub(prev_main_idx, i)
            # promote move_to to before_move_to list with empty sub‑lists
            before_move_to = []
            for mt in buckets.pop("move_to", []):
                mt.update({"top": [], "bottom": [], "center": [], "move": []})
                before_move_to.append(mt)

            # merge tops/bottoms/move/center into their buckets (defaultdict handles missing)
            ordered_action_dict[order] = {
                "type": evt_type,
                "order": order,
                "main_event": evt,
                "top": buckets["top"],
                "bottom": buckets["bottom"],
                "move": buckets["move"],
                "center": buckets["center"],
                "before_move_to": before_move_to,
                "mix_after": []
            }
            prev_main_idx = i
            last_order = order

        # --------------------------------------------------- MIX ACTION
        elif evt_type == "mix":
            if last_order in ordered_action_dict:
                buckets = collect_sub(prev_main_idx, i)
                ordered_action_dict[last_order]["mix_after"].append({
                    "mix": evt,
                    "top": buckets["top"],
                    "bottom": buckets["bottom"],
                    "move": buckets["move"],
                    "center": buckets["center"]
                })

    for od in ordered_action_dict.values():
        for field in ["top", "bottom", "move","center"]:
            if field in od:
                items_to_remove = []
                for evt in od[field]:
                    for mt in od["before_move_to"]:
                        if "line" in mt and "line" in evt and mt["line"] == evt["line"]:
                            if field not in mt:
                                mt[field] = []
                            mt[field].append(evt)
                            items_to_remove.append(evt)
                            break  # 每个evt最多归一次
                for evt in items_to_remove:
                    od[field].remove(evt)

    return ordered_action_dict

def add_detail_info(protocol_steps: List[Dict], detail_info: str) -> List[Dict]:

    detail_action = json.load(open(detail_info, "r"))['event_logs']
    set_liquid = json.load(open(detail_info, "r"))['liquid_locations']
    # 1. 把aspirate和dispense设置为主动作，来规划顺序
    counter = 1
    for item in detail_action:
        if item.get("event") in {"aspirate", "dispense"}:
            item["order"] = counter
            counter += 1
    # 2. 生成有序的动作细节字典
    ordered_action_dict = build_ordered_action_dict(detail_action)

    # with open(f"protocol_steps.json", "w") as f:
    #     json.dump(protocol_steps, f, indent=4)
   
   # 3. 在每个 phase 中添加详细的动作信息
    current_order = 1  # order编号从1开始
    for phase_idx, phase in enumerate(protocol_steps):
        # 1. 统计主动作个数
        asp_vals = phase.get("asp_vols")
        disp_vals = phase.get("disp_vols")
        asp_count = len(asp_vals) if isinstance(asp_vals, list) else (1 if asp_vals is not None else 0)
        disp_count = len(disp_vals) if isinstance(disp_vals, list) else (1 if disp_vals is not None else 0)
        num_main = asp_count + disp_count
        # 2. 把本 phase 需要的主动作依次弹出（保证顺序）
        detailed_event_list = []
        for _ in range(num_main):
            if current_order in ordered_action_dict:
                detailed_event_list.append(ordered_action_dict[current_order])
            current_order += 1
        # 3. 通用方式提取 top / bottom / move / center 等标量
        FIELD_KEY = {
    "top":      ("z",      lambda lst: lst and lst[0] and "z" in lst[0] and lst[0]["z"] or None),
    "bottom":   ("z",      lambda lst: lst and lst[0] and "z" in lst[0] and lst[0]["z"] or None),
    "move":     ("offset", lambda lst: lst and lst[0] and "offset" in lst[0] and lst[0]["offset"] or None),
    "center":   (None,     lambda lst: bool(lst) and lst[0] is not None)
}
        scalar_lists = {fld: [] for fld in FIELD_KEY}
        move_to_detail = []
        mix_detail = []

        for ev in detailed_event_list:
            # ---- 主动作的参数 ----
            for fld, (key, fun) in FIELD_KEY.items():
                val = fun(ev.get(fld, []))
                scalar_lists[fld].append(val)
            # ---- before_move_to（每个move_to元素下直接带四个list）----
            # phase["move_to"]: 每个主动作一项
            if ev.get("before_move_to"):
                agg = {fld: [] for fld in FIELD_KEY}
                for mt in ev["before_move_to"]:
                    for fld, (key, fun) in FIELD_KEY.items():
                        agg[fld].append(fun(mt.get(fld, [])))
                move_to_detail.append(agg)
            else:
                move_to_detail.append({fld: [] for fld in FIELD_KEY})
            if ev.get("mix_after"):
                agg = {fld: [] for fld in FIELD_KEY}
                for mix_blk in ev["mix_after"]:
                    for fld, (key, fun) in FIELD_KEY.items():
                        agg[fld].append(fun(mix_blk.get(fld, [])))
                mix_detail.append(agg)
            else:
                mix_detail.append({fld: [] for fld in FIELD_KEY})
        for fld in FIELD_KEY:
            phase[fld] = scalar_lists[fld]
        phase["move_to"] = move_to_detail
        phase["mix_detail"] = mix_detail
        
    # with open(f"detailed_action.json", "w") as f:
    #     json.dump(protocol_steps, f, indent=4)

    return protocol_steps, set_liquid

def fix_special_cases(protocol_steps: List[Dict]) -> List[Dict]:
    """
    处理一些protocol的特殊情况，比如：
    1. 有些protocol的aspirate和dispense没有对应的tip_rack
    """
    for step in protocol_steps:
        if step["template"] == "transfer":
            if not step.get("tip_racks"):
                # 让这个步骤的tip_racks为上一个步骤的tip_racks
                if protocol_steps.index(step) > 0:
                    prev_step = protocol_steps[protocol_steps.index(step) - 1]
                    step["tip_racks"] = prev_step.get("tip_racks", [])
    return protocol_steps


def fix_positions(protocol_steps: List[Dict], replace_map: Dict[int, int]) -> List[Dict]:
    """
    根据 replace_map 修复 protocol_steps 中各 labware 的 slot。
    若某个 slot 没有映射，只记录警告并继续执行。
    """
    for step_idx, step in enumerate(protocol_steps):
        for field in ("targets", "sources", "tip_racks"):
            for item_idx, single_slot in enumerate(step.get(field, [])):
                old_slot = single_slot.get("slot")
                try:
                    single_slot["slot"] = replace_map[str(old_slot)]
                    #print(f"[INFO] step {step_idx}, {field}[{item_idx}] slot {old_slot} replaced with {single_slot['slot']}")
                except KeyError:
                    pass
                    # 通用警告，不输出具体 labware 名称等敏感信息
                    #print(f"[WARN] step {step_idx}, {field}[{item_idx}] 无映射，保留原 slot")
                    # pass      
    return protocol_steps


def parse_protocol(name: str):
    logfile = f"/Users/guangxinzhang/Documents/Deep_Potential/opentrons/convert/protocols/log/{name}.log"
    infofile = f"/Users/guangxinzhang/Documents/Deep_Potential/Protocols/protoBuilds/{name}/{name}.ot2.apiv2.py.json"
    detail_steps = f"/Users/guangxinzhang/Documents/Deep_Potential/opentrons/convert/protocols/detailed_action_json/{name}.json"

    # first check if the files exist
    if not os.path.exists(infofile):
        proto_dir = f"/Users/guangxinzhang/Documents/Deep_Potential/Protocols/protoBuilds/{name}/"
        candidates = [
            os.path.join(proto_dir, f)
            for f in os.listdir(proto_dir)
            if f.endswith(".json") and f not in ("metadata.json", "README.json")
        ]
        if candidates:
            infofile = candidates[0]
        else:
            raise FileNotFoundError(f"No protocol json found in {proto_dir}, except metadata.json/README.json")

    protocol_steps = process_liquid_handler_log(logfile, name)
    # enriched_steps, liquid_info = add_detail_info(protocol_steps, detail_steps)
    # with open(infofile, "r") as f:
    #     labware_data = json.load(f)
    # labware_info, replace_map = extract_labware_info_from_json(labware_data)
    # enriched_steps = fix_special_cases(enriched_steps)
    # enriched_steps = fix_positions(enriched_steps, replace_map)
    # # with open(f'/Users/guangxinzhang/Documents/Deep_Potential/opentrons/convert/protocols/prcxi_enriched_steps/{name}.json', 'w') as f:
    # #     json.dump(enriched_steps, f, indent=4)
    # #print(json.dumps(enriched_steps, indent=4))
    # labware_info = refine_wells(labware_info, liquid_info, enriched_steps)
    # protocol_graph = build_protocol_graph(labware_info, enriched_steps)
    # data = nx.node_link_data(protocol_graph)
    # # Dumb but effective: clean micro symbols at the serialized string level
    # json_str = json.dumps(data, indent=4, ensure_ascii=False)
    # json_str = (json_str
    #             .replace("\\u00b5", "u")
    #             .replace("µ", "u")
    #             .replace("μ", "u"))
    # with open(f"/Users/guangxinzhang/Documents/Deep_Potential/opentrons/convert/protocols/PRCXI_graph/{name}.graph.json", "w", encoding="utf-8") as f:
    #     f.write(json_str)

if __name__ == "__main__":
    # 测试代码
    file_dir = "/Users/guangxinzhang/Documents/Deep_Potential/opentrons/convert/protocols/original"
    error_log = Path("protocols/log/error_converting.txt")
    protocol_names = [d for d in os.listdir(file_dir) if os.path.isdir(os.path.join(file_dir, d))]
    for name in protocol_names:

        try:
            parse_protocol(name)
        except Exception as e:
            with open(error_log, "a") as f:
                f.write(f"Error processing {name}: {str(e)}\n")
            #print(f"Error processing {name}: {str(e)}")

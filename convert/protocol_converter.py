import json
import pandas as pd

import re
from typing import List, Dict, Optional, Union, Sequence, Literal
# ---------- Heater‑Shaker phase parser ----------
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
# -----------------------------------------------



def extract_float_after_keyword(text: str, keyword: str) -> Optional[float]:
    match = re.search(fr'{keyword} ([\d.]+)', text)
    return float(match.group(1)) if match else None

def extract_container_from_line(line: str, keyword: str) -> Optional[Dict[str, Union[str, int, float]]]:
    # 匹配 from 模式
    match = re.search(fr'{keyword} [\d.]+ uL .*?from ([A-H]\d+) of (.*?) on (\d+).*?at ([\d.]+) uL/sec', line)
    if not match:
        # 匹配 into 模式
        match = re.search(fr'{keyword} [\d.]+ uL .*?into ([A-H]\d+) of (.*?) on (\d+).*?at ([\d.]+) uL/sec', line)
    if match:
        return {
            "well": match.group(1),
            "labware": match.group(2).strip(),
            "slot": int(match.group(3))
        }
    return None

def is_full_row(wells: List[str]) -> bool:
    """Returns True if all wells in a row (e.g., A1 to A12) are included"""
    if len(wells) < 12:
        return False
    row = wells[0][0]
    indices = sorted([int(w[1:]) for w in wells if w[0] == row])
    return indices == list(range(1, 13))

def build_transfer_liquid_dict_complete(step_lines: List[str]) -> Dict:
    asp_vols = []
    dis_vols = []
    sources = []
    targets = []
    tip_rack_info = None
    asp_flow_rate = None
    dis_flow_rate = None
    blow_out_air_volume = 0.0
    mix_times = 0
    mix_vol = None
    mix_rate = None
    touch_tip = False
    delays = None

    # --- module flags that accompany liquid handling ---
    temperature_target = None
    temperature_deactivate = False
    magnetic_engage = False
    magnetic_delay_minutes = None
    magnetic_disengage = False
    # ---------------------------------------------------

    aspirate_index = None
    dispense_index = None
    mixing_indices = []

    # First pass: gather line indices for logic
    for i, line in enumerate(step_lines):
        if line.startswith(" "):  # ignore indented substeps
            continue
        stripped = line.strip()
        if stripped.startswith("Aspirating") and "from" in stripped and aspirate_index is None:
            aspirate_index = i
        elif stripped.startswith("Dispensing") and "into" in stripped and dispense_index is None:
            dispense_index = i
        elif stripped.startswith("Mixing"):
            mixing_indices.append(i)
        elif stripped.startswith("Picking up tip"):
            tip_match = re.search(r'from ([A-H]\d+) of (.*?) on (\d+)', stripped)
            if tip_match:
                tip_rack_info = {
                    "well": tip_match.group(1),
                    "type": tip_match.group(2).strip(),
                    "slot": int(tip_match.group(3))
                }

    # Determine mix_stage
    mix_stage = "none"
    for idx in mixing_indices:
        if aspirate_index is not None and idx < aspirate_index:
            mix_stage = "before" if mix_stage == "none" else "both"
        elif dispense_index is not None and idx > dispense_index:
            mix_stage = "after" if mix_stage == "none" else "both"

    # Second pass: parse actual values
    for i, line in enumerate(step_lines):
        if line.startswith(" "):  # ignore indented substeps
            continue
        stripped = line.strip()

        if stripped.startswith("Aspirating") and "from" in stripped:
            asp_vols = extract_float_after_keyword(stripped, "Aspirating")
            source = extract_container_from_line(stripped, "Aspirating")
            if source:
                sources.append(source)
            asp_flow_rate = extract_float_after_keyword(stripped, "at")
        elif stripped.startswith("Dispensing") and "into" in stripped:
            dis_vols = extract_float_after_keyword(stripped, "Dispensing")
            target = extract_container_from_line(stripped, "Dispensing")
            if target:
                targets.append(target)
            dis_flow_rate = extract_float_after_keyword(stripped, "at")
        
        elif stripped.startswith("Transferring"):
            asp_vols = extract_float_after_keyword(stripped, "Aspirating")
            dis_vols = extract_float_after_keyword(stripped, "Dispensing")
            source = extract_container_from_line(stripped, "Aspirating")
            if source:
                sources.append(source)
            target = extract_container_from_line(stripped, "Dispensing")
            if target:
                targets.append(target)    
                # 新增：分别提取Aspirating和Dispensing的流速
            asp_match = re.search(r"Aspirating.*?at ([\d.]+)", stripped)
            dis_match = re.search(r"Dispensing.*?at ([\d.]+)", stripped)
            asp_flow_rate = float(asp_match.group(1)) if asp_match else None
            dis_flow_rate = float(dis_match.group(1)) if dis_match else None

        # Temperature Module commands
        elif stripped.startswith("Setting Temperature Module temperature"):
            temperature_target = extract_float_after_keyword(stripped, "to")
        elif stripped.startswith("Deactivating Temperature Module"):
            temperature_deactivate = True

        # Magnetic Module commands
        elif stripped.startswith("Engaging Magnetic Module"):
            magnetic_engage = True
        elif stripped.startswith("Disengaging Magnetic Module"):
            magnetic_disengage = True
        elif stripped.startswith("Delaying") and magnetic_engage and not magnetic_disengage:
            delay_match2 = re.search(r'Delaying for (\d+) minutes', stripped)
            if delay_match2:
                magnetic_delay_minutes = int(delay_match2.group(1))

        elif stripped.startswith("Air gap"):
            blow_out_air_volume = extract_float_after_keyword(stripped, "Aspirating")
        elif stripped.startswith("Mixing"):
            mix_match = re.search(r'Mixing (\d+) times.*?(\d+\.?\d*)', stripped)
            if mix_match:
                mix_times = [int(mix_match.group(1))]
                mix_vol = float(mix_match.group(2))
                mix_rate = extract_float_after_keyword(stripped, "at")
        elif "Touching tip" in stripped:
            touch_tip = True
        elif stripped.startswith("Delaying"):
            delay_match = re.search(r'Delaying for \d+ minutes and ([\d.]+)', stripped)
            if delay_match:
                delays = [int(float(delay_match.group(1)))]

    # Determine 96-well multichannel use
    source_wells = [s['well'] for s in sources]
    target_wells = [t['well'] for t in targets]
    is_96_well = is_full_row(source_wells) and is_full_row(target_wells)

    basic_info = {
        "sources": sources,
        "targets": targets,
        "tip_racks": [tip_rack_info] if tip_rack_info else [],
        "use_channels": None,
        "asp_vols": asp_vols,
        "asp_flow_rates": [asp_flow_rate] if asp_flow_rate else None,
        "disp_vols": dis_vols,
        "dis_flow_rates": [dis_flow_rate] if dis_flow_rate else None,
        "offsets": None,
        "touch_tip": touch_tip,
        "liquid_height": None,
        "blow_out_air_volume": [blow_out_air_volume] if blow_out_air_volume else [0.0],
        "is_96_well": is_96_well,
        "mix_stage": mix_stage,
        "mix_times": mix_times,
        "mix_vol": mix_vol,
        "mix_rate": mix_rate,
        "mix_liquid_height": None,
        "delays": delays
    }

    if magnetic_engage or magnetic_disengage:
        template = "transfer_with_magnetic"
        return {
            "template": template,
            **basic_info,
            "magnetic_engage": magnetic_engage,
            "magnetic_delay_minutes": magnetic_delay_minutes,
            "magnetic_disengage": magnetic_disengage
        }
    elif temperature_target is not None:
        template = "transfer_with_temperature"
        return {
            "template": template,
            **basic_info,
            "temperature_target": temperature_target,
            "temperature_deactivate": temperature_deactivate
        }
    else:
        template = "transfer"
        return {"template": template, **basic_info}


def merge_same_slot_phases(param_dicts: List[Dict]) -> List[Dict]:
    merged = []
    last_key = None
    last_block = None

    for d in param_dicts:
        if not d.get("sources") or not d.get("targets"):
            merged.append(d)
            last_key = None
            last_block = None
            continue

        key = (
            d["template"],
            d["sources"][0]["slot"],
            d["targets"][0]["slot"],
            d.get("mix_stage"),
            d.get("is_96_well"),
            d.get("touch_tip"),
            d.get("blow_out_air_volume", [0])[0]
        )

        if last_key == key and last_block:
            for field in ['asp_vols', 'disp_vols', 'sources', 'targets',
                          'tip_racks', 'asp_flow_rates', 'dis_flow_rates',
                          'blow_out_air_volume', 'delays']:
                if field in d:
                    if not isinstance(last_block[field], list):
                        last_block[field] = [last_block[field]]
                    last_block[field].extend(d[field] if isinstance(d[field], list) else [d[field]])
        else:
            merged.append(d)
            last_key = key
            last_block = d

    return merged


def process_liquid_handler_log(filename: str = "test.log", text: str = "") -> List[Dict]:
    """
    Process the liquid handler log text and return a list of dictionaries
    containing the parsed information.
    """
    if not text:
        text = open(filename, "r", encoding="utf-8").read()

    # Define regex patterns for module start commands

    MODULE_START_PATTERNS = [
        r"Setting Target Temperature of Heater-Shaker",
        r"Engaging Magnetic Module"
    ]

    # Compile once for quick matching of Heater‑Shaker commands
    module_start_regex = re.compile("|".join(MODULE_START_PATTERNS))

    # Input: Multiline protocol text
    # with open("/mnt/data/opentrons_protocol.txt", "r", encoding="utf-8") as file:
    #     lines = file.readlines()
    text_ = text.replace("\n        ", ";")
    text_ = text_.replace("\n\t", ";")
    lines = text_.strip().split('\n')

    excluded_patterns = [
        "/Users",
        "Congratulations!",
        "Caught exception:",
        "Deck calibration",
        "WARNING",
        "Protocol complete",
        "Seal and shake",
        "Pausing robot operation",
        "TRANSFERRING",
        "Centrifuge"
    ]
    steps = [line.replace(";", "\n        ").strip() for line in lines if line.strip() and
             not line.startswith("        ") and not line.startswith("~~") and
             not "--" in line and not line.endswith(":") and
             not sum([line.startswith(patt) for patt in excluded_patterns])]

    # Define prepositions to split on
    PREPOSITIONS = [' from ', ' to ', ' on ', ' of ', ' into ']

    # Structure for collecting parsed results
    parsed_steps = []

    # Parse each line
    for line in steps:
        tokens = [line]
        for prep in PREPOSITIONS:
            new_tokens = []
            for token in tokens:
                new_tokens.extend(token.split(prep))
            tokens = new_tokens
        parsed_steps.append({
            "raw": line,
            "tokens": [t.strip() for t in tokens if t.strip()]
        })

    # -------- Build phases: split on Heater‑Shaker OR liquid‑logic breaks --------
    grouped_phases = []
    current_phase = []
    aspirating_seen = False
    last = ""

    for step in parsed_steps:
        line_raw = step["raw"]

        # ① 如果遇到 Heater‑Shaker 指令，立即结束当前 phase
        if module_start_regex.search(line_raw):
            if current_phase:
                grouped_phases.append(current_phase)
                current_phase = []
                aspirating_seen = False    # reset for next liquid series

        # ② 维持原有移液逻辑的切割
        if (line_raw.startswith("Aspirating") and not ("Picking up tip" in last) and not ("Moving to" in last) and not ("Transferring" in last)) \
            or ("Picking up tip" in line_raw) \
            or ("Moving to" in line_raw and not ("Picking up tip" in last)):
            if aspirating_seen:
                grouped_phases.append(current_phase)
                current_phase = []
            aspirating_seen = True

        last = line_raw
        current_phase.append(line_raw)

    # 别忘了收集最后一个 phase
    if current_phase:
        grouped_phases.append(current_phase)

    #print(grouped_phases)
     # -------- Build dicts for each phase (liquid vs HS) --------
    outputs = []
    for phase_lines in grouped_phases:
        if any("Heater-Shaker" in l for l in phase_lines):
            outputs.append(build_heater_shaker_dict(phase_lines))
        else:
            outputs.append(build_transfer_liquid_dict_complete(phase_lines))
    # -----------------------------------------------------------

    final_outputs = merge_same_slot_phases(outputs)

    # ------------- Output the final DataFrame -------------
    #print(final_outputs)
    json.dump(final_outputs, open(f"{filename}.json", "w"), indent=4)
    #ddf = pd.DataFrame({"Phase {}".format(i + 1): phase for i, phase in enumerate(final_outputs)})

    return final_outputs


def extract_labware_info_from_json(json_data: dict) -> list:
    """
    从 Opentrons JSON 配置中提取板位信息，转换为结构化格式。
    """
    labware_list = json_data.get("labware", [])

    output = []
    for i, lw in enumerate(labware_list):
        output.append({
            "id": lw.get("name"),
            "parent": "deck",
            "slot_on_deck": int(lw.get("slot")),
            "class_name": lw.get("type"),
            "liquid_type": [],      # 默认填写
            "liquid_volume": [],                # 默认每个液体体积
            "liquid_input_wells": []                # 默认输入孔位索引
        })

    return output


# Re-import necessary libraries after kernel reset
from typing import List, Dict, Any
import networkx as nx
import json

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

def add_detail_info(protocol_steps: List[Dict], detail_info: str) -> List[Dict]:
    import json
    from collections import defaultdict

    detail_action = json.load(open(detail_info, "r"))['event_logs']
    set_liquid = json.load(open(detail_info, "r"))['liquid_locations']

    # Step 1: 对 detail_action 建立按顺序的指针（滑动窗口）
    action_ptr = 0
    total_actions = len(detail_action)
    enriched_phases = []

    for phase_idx, phase in enumerate(protocol_steps):


        asp_info = []
        disp_info = []
        # 假设 asp_vols 和 disp_vols 为序列
        asp_count = len(phase.get("asp_vols", [])) 
        disp_count = len(phase.get("disp_vols", [])) 

        

    #     # 辅助函数：在 action_ptr 后依次找到下一个目标 event
    #     def next_event(event_type, start_ptr):
    #         for i in range(start_ptr, total_actions):
    #             if detail_action[i]["event"] == event_type:
    #                 return i, detail_action[i]
    #         return None, None

    #     # 辅助函数：对于每个asp/disp，查找其附近相关的bottom/top/move_to
    #     def find_related_events(start, stop):
    #         related = {"bottom": [], "top": [], "move_to": []}
    #         for i in range(start, stop):
    #             evt = detail_action[i]
    #             if evt["event"] in related:
    #                 related[evt["event"]].append(evt)
    #         return related

        # 逐个找aspirate及其附属动作
        asp_results = []
        for a in range(asp_count):
            idx, asp_evt = next_event("aspirate", action_ptr)
            if asp_evt is None:
                asp_results.append({"aspirate": None, "bottom": [], "top": [], "move_to": []})
                continue
            # 寻找在这次aspirate前面最近的bottom/top/move_to
            related = find_related_events(action_ptr, idx)
            asp_results.append({
                "aspirate": asp_evt,
                "bottom": related["bottom"] if related["bottom"] else [],
                "top": related["top"] if related["top"] else [],
                "move_to": related["move_to"] if related["move_to"] else []
            })
            action_ptr = idx + 1  # 推进指针

    #     # 逐个找dispense及其附属动作
    #     disp_results = []
    #     for d in range(disp_count):
    #         idx, disp_evt = next_event("dispense", action_ptr)
    #         if disp_evt is None:
    #             disp_results.append({"dispense": None, "bottom": [], "top": [], "move_to": []})
    #             continue
    #         related = find_related_events(action_ptr, idx)
    #         disp_results.append({
    #             "dispense": disp_evt,
    #             "bottom": related["bottom"] if related["bottom"] else [],
    #             "top": related["top"] if related["top"] else [],
    #             "move_to": related["move_to"] if related["move_to"] else []
    #         })
    #         action_ptr = idx + 1

    #     # 添加到 phase 结构
    #     phase_with_details = dict(phase)  # 拷贝一份
    #     phase_with_details["aspirate_details"] = asp_results
    #     phase_with_details["dispense_details"] = disp_results
    #     enriched_phases.append(phase_with_details)
    # print( "enriched_phases", enriched_phases)
    return enriched_phases


def parse_protocol(name: str):
    logfile = f"/Users/guangxinzhang/Documents/Deep Potential/opentrons/convert/protocols/log/{name}.py.log"
    infofile = f"/Users/guangxinzhang/Documents/Deep Potential/Protocols/protoBuilds/{name}/{name}.ot2.apiv2.py.json"
    detail_steps = f"/Users/guangxinzhang/Documents/Deep Potential/opentrons/convert/protocols/detailed_action_json/{name}.json"
    protocol_steps = process_liquid_handler_log(logfile)
    enriched_steps = add_detail_info(protocol_steps, detail_steps)
    # with open(infofile, "r") as f:
    #     labware_data = json.load(f)
    # labware_info = extract_labware_info_from_json(labware_data)
    # protocol_graph = build_protocol_graph(labware_info, protocol_steps)
    # data = nx.node_link_data(protocol_graph)
    # with open(f"/Users/guangxinzhang/Documents/Deep Potential/opentrons/convert/protocols/graph/{name}.graph.json", "w") as f:
    #     json.dump(data, f, indent=4)


if __name__ == "__main__":
    # 测试代码
    # process_liquid_handler_log("/Users/chang/Design_projects/LabOS/opentrons/Protocols/success/sci-lucif-assay4.ot2.apiv2.log")
    # process_liquid_handler_log(text=text__)
    parse_protocol("sci-lucif-assay4")

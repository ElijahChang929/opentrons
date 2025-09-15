import builtins
builtins.event_logs = []
__protocol_file__ = r"/Users/guangxinzhang/Documents/Deep_Potential/opentrons/convert/new_test/protocols/original/3fb582/3fb582.ot2.apiv2.py"

metadata = {
    'protocolName': 'PCR setup using a CSV file',
    'author': 'Opentrons <protocols@opentrons.com>',
    'source': 'Protocol Library',
    'apiLevel': '2.2'
}

# c = """Reagent,Source Slot,Source Well,Target Slot,Target Well,Volume
# Water,2,A1,9,A1,10
# Primer 1,2,A2,9,A1,5
# PCR Mix,2,A3,9,A1,10
# DNA 1,2,A4,9,A1,1
# """


def run(ctx):

    c = get_values(  # noqa: F821
            'csv_input')[0]

    csv_data = [r.split(',') for r in c.strip().splitlines() if r][1:]
    steps = {"Water": [], "PCR": [], "Primer": [], "DNA": []}
    for line in csv_data:
        for k, v in steps.items():
            if k in line[0]:
                steps[k].append(line)

    tube_racks = [
        ctx.load_labware(
            "opentrons_24_tuberack_eppendorf_1.5ml_safelock_snapcap",
            x) for x in [
            "2",
            "5",
            "8",
            "11"]]
    tube_rack_slot = {
        str(i): tube_rack for i,
        tube_rack in zip(range(2, 12, 3), tube_racks)}

    p20s = ctx.load_instrument(
        "p20_single_gen2",
        "right",
        tip_racks=[
            ctx.load_labware(
                "opentrons_96_filtertiprack_20ul",
                x) for x in [
                "1",
                "4",
                "7",
                "10",
                "3"]])

    destination_plate_96 = ctx.load_labware(
        "nest_96_wellplate_100ul_pcr_full_skirt", "6")
    destination_plate_384 = ctx.load_labware(
        "corning_384_wellplate_112ul_flat", "9")
    destination_slot = {"6": destination_plate_96, "9": destination_plate_384}

    p20s.pick_up_tip()
    for r, ss, source_well, ts, target_well, volume in steps["Water"]:
        p20s.transfer(
            float(volume),
            tube_rack_slot[ss].wells_by_name()[source_well],
            destination_slot[ts].wells_by_name()[target_well],
            new_tip='never')
    p20s.drop_tip()

    p20s.pick_up_tip()
    for r, ss, source_well, ts, target_well, volume in steps["PCR"]:
        p20s.transfer(
            float(volume),
            tube_rack_slot[ss].wells_by_name()[source_well],
            destination_slot[ts].wells_by_name()[target_well].top(),
            new_tip='never')
    p20s.drop_tip()

    for step in [steps["Primer"], steps["DNA"]]:
        for r, ss, source_well, ts, target_well, volume in step:
            p20s.transfer(
                float(volume),
                tube_rack_slot[ss].wells_by_name()[source_well],
                destination_slot[ts].wells_by_name()[target_well],
                new_tip='always')

    from opentrons.protocol_api.labware import Well, Labware
    from collections.abc import Sequence, Mapping
    import re
    import json
    import os
    import builtins

    # 复制一份当前局部变量的快照，避免后面被我们修改/覆盖
    _all_vars = dict(locals())

    # ----------------------------
    # 工具函数
    # ----------------------------
    # 允许普通空格 / 不换行空格 / 窄不换行空格；兼容 "on 3" 与 "on slot 3"
    _SLOT_PAT = re.compile(r'on[\s\u00A0\u202F]*(?:slot[\s\u00A0\u202F]*)?(\d+)', re.IGNORECASE)
    _WELL_PAT = re.compile(r'\b([A-H]\d{1,2})\b', re.IGNORECASE)

    def _normalize_spaces(text: str) -> str:
        return text.replace("\u00A0", " ").replace("\u202F", " ")

    def _parse_well_and_last_slot(text: str):
        if not text:
            return None, None
        norm = _normalize_spaces(text)
        m_well = _WELL_PAT.search(norm)
        well = m_well.group(1) if m_well else None

        slots = _SLOT_PAT.findall(norm)
        if slots:
            try:
                slot = int(slots[-1])
            except Exception:
                slot = None
        else:
            m_last = re.search(r'on.*?(\d+)\s*$', norm, re.IGNORECASE)
            slot = int(m_last.group(1)) if m_last else None
        return well, slot

    def _safe_get(obj, name, default=None):
        try:
            return getattr(obj, name)
        except Exception:
            return default

    def _walk_parents_for_slot(obj):
        seen = set()
        cur = obj
        while cur and id(cur) not in seen:
            seen.add(id(cur))
            disp = _safe_get(cur, "display_name")
            if disp:
                _, slot = _parse_well_and_last_slot(disp)
                if slot is not None:
                    return slot
            cur = _safe_get(cur, "parent")
        return None

    def _extract_from_well(w: Well):
        well_name = _safe_get(w, "well_name")
        if not well_name or not isinstance(well_name, str):
            disp = _safe_get(w, "display_name") or ""
            well_name, _ = _parse_well_and_last_slot(disp)

        disp = _safe_get(w, "display_name") or ""
        _, slot_num = _parse_well_and_last_slot(disp)
        if slot_num is None:
            slot_num = _walk_parents_for_slot(w)

        return well_name, slot_num

    def _iter_wells(obj):
        if isinstance(obj, Well):
            yield obj
            return
        if isinstance(obj, Mapping):
            for v in obj.values():
                yield from _iter_wells(v)
            return
        if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
            for it in obj:
                yield from _iter_wells(it)

    def _iter_named_entries(name, obj):
        if isinstance(obj, Well):
            yield (name, obj)
            return
        if isinstance(obj, Mapping):
            for k, v in obj.items():
                subkey = f"{name}[{k}]"
                for kk, ww in _iter_named_entries(subkey, v):
                    yield (kk, ww)
            return
        if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
            for i, it in enumerate(obj):
                subkey = f"{name}[{i}]"
                for kk, ww in _iter_named_entries(subkey, it):
                    yield (kk, ww)

    # ----------------------------
    # 收集逻辑
    # ----------------------------
    processed = set()
    liquid_locations = {}

    _exclude_prefixes = {
        "_parse_well_and_last_slot", "_safe_get", "_walk_parents_for_slot", "_extract_from_well",
        "_iter_wells", "_iter_named_entries", "_all_vars",
        "processed", "liquid_locations", "_SLOT_PAT", "_WELL_PAT",
        "re", "json", "os", "builtins", "Well", "Labware", "Sequence", "Mapping",
        "FOLDERNAME", "__protocol_file__"
    }

    for var_name, var_val in list(_all_vars.items()):
        if any(var_name.startswith(p) for p in _exclude_prefixes):
            continue

        for key, w in _iter_named_entries(var_name, var_val):
            if not isinstance(w, Well):
                continue
            if w in processed:
                continue
            processed.add(w)

            well_name, slot_num = _extract_from_well(w)
            if well_name is None or slot_num is None:
                disp = _safe_get(w, "display_name", "")
                print(f"[WARN] Unparsed: {key} -> well={well_name!r}, slot={slot_num!r}, disp={disp!r}")

            liquid_locations[key] = {
                "well": well_name or "unknown",
                "slot": slot_num if slot_num is not None else "unknown"
            }

    # ----------------------------
    # 写 JSON（确保目录存在）
    # ----------------------------
    folder = f"protocols/detailed_action_json"
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception:
        pass

    event_logs = getattr(builtins, "event_logs", [])

    try:
        _pf = globals().get("__protocol_file__")
        _foldername = os.path.basename(os.path.dirname(_pf)) if _pf else "unknown"
    except Exception:
        # 打印这个错误
   
        _foldername = "unknown"

    filename = f"{folder}/{_foldername}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump({
            "event_logs": event_logs,
            "liquid_locations": liquid_locations
        }, f, indent=2, ensure_ascii=False, default=str)
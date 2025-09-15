import builtins
builtins.event_logs = []
__protocol_file__ = r"/Users/guangxinzhang/Documents/Deep_Potential/opentrons/convert/new_test/protocols/original/4a0be6/4a0be6.ot2.apiv2.py"

import math
from opentrons.protocol_api.labware import Well

from opentrons import APIVersion

metadata = {
    'protocolName': 'Tube Filling',
    'author': 'Opentrons <protocols@opentrons.com>',
    'source': 'Custom Protocol Request',
    'apiLevel': '2.13'
}


def run(protocol):
    [transferVol, tubeRacks, tubeType, numRacks, srcType, srcVol,
     pipType, pipMnt, startTip, dispMode, touchTip] = get_values(  # noqa: F821
     'transferVol', 'tubeRacks', 'tubeType', 'numRacks', 'srcType', 'srcVol',
     'pipType', 'pipMnt', 'startTip', 'dispMode', 'touchTip')

    # Load labware and pipettes

    tipNum = pipType.split('_')[0][1:]
    tipNum = '300' if tipNum == '50' else tipNum
    tipType = f'opentrons_96_tiprack_{tipNum}ul'
    tips = [protocol.load_labware(tipType, '11')]
    pip = protocol.load_instrument(pipType, pipMnt, tip_racks=tips)

    firstTip = startTip[0].upper()+str(int(startTip[1:]))
    pip.starting_tip = tips[0][firstTip]

    srcLabware = protocol.load_labware(srcType, '1')

    destRacks = [
        protocol.load_labware(tubeRacks+tubeType, slot) for slot in range(
            2, 2+numRacks)]

    # Functions and Class creation
    if not protocol.is_simulating:
        class WellH(Well):
            def __init__(self, well, height=0, min_height=5, comp_coeff=1.15,
                         current_volume=0):
                # Change one is that we deprecated well._impl
                super().__init__(well.parent, well._core, APIVersion(2, 13))
                self.well = well
                self.height = height
                self.min_height = min_height
                self.comp_coeff = comp_coeff
                self.radius = self.diameter / 2
                self.current_volume = current_volume

            def height_dec(self, vol):
                dh = (vol / (math.pi * (self.radius ** 2))) * self.comp_coeff
                if self.height - dh > self.min_height:
                    self.height = self.height - dh
                else:
                    self.height = self.min_height
                if self.current_volume - vol > 0:
                    self.current_volume = self.current_volume - vol
                else:
                    self.current_volume = 0
                return (self.well.bottom(self.height))

            def height_inc(self, vol):
                dh = (vol / (math.pi * (self.radius ** 2))) * self.comp_coeff
                if self.height + dh < self.depth:
                    self.height = self.height + dh
                else:
                    self.height = self.depth
                self.current_volume += vol
                return (self.well.bottom(self.height + 20))

        def yield_groups(list, num):
            """
            yield lists based on number of items
            """
            for i in range(0, len(list), num):
                yield list[i:i+num]

        # get number of distributes pipette can handle
        distribute_num = pip.max_volume // transferVol
        if distribute_num < 1:
            # if transfer volume is greater than pipette max volume,
            # use Transfer mode
            dispMode = 'Transfer'

        # create source location with WellH
        source = WellH(
            srcLabware.wells()[0], min_height=3, current_volume=srcVol*1000)

        # Protocol: Tube filling
        pip.pick_up_tip()
        all_wells = [well for tuberack in destRacks
                     for well in tuberack.wells()]
        if dispMode == 'Transfer':
            for dest in all_wells:
                pip.transfer(
                    transferVol, source.height_dec(transferVol), dest,
                    touch_tip=touchTip, new_tip='never')
        else:
            well_groups = list(yield_groups(all_wells, int(distribute_num)))
            for wells in well_groups:
                pip.distribute(
                    transferVol, source.height_dec(transferVol), wells,
                    blow_out=source, touch_tip=touchTip, new_tip='never')
        pip.drop_tip()

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

    print(list(_all_vars.items()))

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
        _foldername = "unknown"

    filename = f"{folder}/{_foldername}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump({
            "event_logs": event_logs,
            "liquid_locations": liquid_locations
        }, f, indent=2, ensure_ascii=False, default=str)
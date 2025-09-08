import os
import ast

INJECT_CODE = '''
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
_SLOT_PAT = re.compile(r'on[\\s\\u00A0\\u202F]*(?:slot[\\s\\u00A0\\u202F]*)?(\\d+)', re.IGNORECASE)
_WELL_PAT = re.compile(r'\\b([A-H]\\d{1,2})\\b', re.IGNORECASE)

def _normalize_spaces(text: str) -> str:
    return text.replace("\\u00A0", " ").replace("\\u202F", " ")

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
        m_last = re.search(r'on.*?(\\d+)\\s*$', norm, re.IGNORECASE)
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
    _foldername = "unknown"

filename = f"{folder}/{_foldername}.json"
with open(filename, "w", encoding="utf-8") as f:
    json.dump({
        "event_logs": event_logs,
        "liquid_locations": liquid_locations
    }, f, indent=2, ensure_ascii=False, default=str)
'''

def insert_code_in_run(py_path, foldername):
    with open(py_path, 'r', encoding='utf-8') as f:
        code = f.read()

    lines = code.splitlines()

    # -------- Preprocess: remove backslash line continuations --------
    processed_lines = []
    idx = 0
    while idx < len(lines):
        current = lines[idx]
        if current.rstrip().endswith('\\'):
            stripped = current.rstrip()[:-1]
            if idx + 1 < len(lines):
                next_line = lines[idx + 1]
                merged = stripped + ' ' + next_line.lstrip()
                processed_lines.append(merged)
                idx += 2
                continue
        processed_lines.append(current)
        idx += 1
    lines = processed_lines

    need_eventlog = not any("builtins.event_logs" in ln for ln in lines)

    from pathlib import Path
    abs_path = str(Path(py_path).resolve())

    eventlog_init = [
        "import builtins",
        "builtins.event_logs = []",
        f"__protocol_file__ = r\"{abs_path}\""
    ]
    if need_eventlog:
        insert_pos = 0
        if lines and lines[0].startswith("#!"):
            insert_pos = 1
        if len(lines) > insert_pos and "coding" in lines[insert_pos]:
            insert_pos += 1
        lines = lines[:insert_pos] + eventlog_init + [""] + lines[insert_pos:]

    # ！！！这里改成真正的换行
    tree = ast.parse('\n'.join(lines))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run":
            start = node.body[-1].end_lineno
            break
    else:
        print(f"run() not found in {py_path}")
        return

    for i, line in enumerate(lines):
        if line.strip().startswith('def run'):
            run_indent = len(line) - len(line.lstrip())
            break
    else:
        run_indent = 0

    indent = ' ' * (run_indent + 4)
    folder_code = INJECT_CODE
    inject_lines = [(indent + l if l.strip() else l) for l in folder_code.splitlines()]

    inject_at = start
    new_lines = lines[:inject_at] + inject_lines + lines[inject_at:]
    # ！！！这里也改成真正的换行
    with open(py_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines))
    print(f"Injected into {py_path}")

def main():
    base = 'protocols/original/'
    for root, dirs, files in os.walk(base):
        foldername = os.path.basename(root)
        for file in files:
            if file.endswith('.py'):
                py_path = os.path.join(root, file)
                insert_code_in_run(py_path, foldername)

if __name__ == "__main__":
    main()
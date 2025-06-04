import json
import pandas as pd
from collections import defaultdict
import networkx as nx
import re
from typing import List, Dict, Optional, Union, Sequence, Literal, Any
import networkx as nx
import os
from pathlib import Path


def refactor_data(data):
    """
    Refactor the workflow data to change the structure of transfer operations.

    Args:
        data (list): Original workflow data (list of steps).

    Returns:
        list: Refactored workflow data.
    """
    refactored_data = []

    #print(data)
    for step in data.get('steps', []):
        if step.get('operation') == 'transfer':
            refactored_data.append({
                'template': 'transfer',
                'sources': step.get('parameters', []).get('source', []),
                'targets': step.get('parameters', []).get('target', []),
                'volume': step.get('parameters', {}).get('volume', None),
                'tip_racks': step.get('parameters', {}).get('tip_rack', []),
                'technique': 'MC P300 High',
            })
        elif step.get('operation') == 'incubation':
            refactored_data.append({
                'template': 'incubation',
                'time': step.get('parameters', {}).get('time', None),
            })
        elif step.get('operation') == 'move_labware':
            refactored_data.append({
                'template': 'move_labware',
                'sources': step.get('parameters', {}).get('source', None),
                'targets': step.get('parameters', {}).get('target', None),
            })
        elif step.get('operation') == 'oscillation':
            refactored_data.append({
                'template': 'oscillation',
                'rpm': step.get('parameters', {}).get('rpm', None),
                'time': step.get('parameters', {}).get('time', None),
            })
        else:
            refactored_data.append(step)

    return refactored_data

def build_protocol_graph(labware_with_liquid: List[Dict[str, Any]], protocol_steps: List[Dict[str, Any]]) -> nx.DiGraph:
    """
    构建包含物料创建和步骤节点的 protocol graph。
    每个节点代表一个操作或物料；每条边表示数据/物料流动。
    """

    G = nx.DiGraph()
    slot_last_writer = {}  # 记录每个 slot 上次的输出节点（transfer/heater_shaker）
    labware_ids = {lw["id"] for lw in labware_with_liquid}

    # Step 1: 添加物料创建节点
    for labware in labware_with_liquid:
        node_id = labware["id"]
        G.add_node(node_id, template="create_resource", **labware)
        slot = labware["slot_on_deck"]
        slot_last_writer[slot] = node_id

    for i, step in enumerate(protocol_steps):
        node_id = f"step_{i+1}"
        G.add_node(node_id, **step)
        if step["template"].startswith("transfer"):
            for port_type, port_name in [("sources", "sources"), ("targets", "targets")]:
                slot = step.get(port_type, [])
                if slot is not None:
                    prev_node = slot_last_writer.get(slot)
                    if prev_node:
                        source_port = "labware" if prev_node in labware_ids else f"{port_name}_out"
                        #print(prev_node)
                        G.add_edge(prev_node, node_id, source_port=source_port, target_port=port_name)
                        slot_last_writer[slot] = node_id

            tip_rack_location = 'TL1'
            port_name = "tip_rack"
            rack_id = "Tip Rack BC230 TL2"

            if prev_node:
                source_port = "labware" if prev_node in labware_ids else f"{port_name}_out"
                G.add_edge(rack_id, node_id, source_port=source_port, target_port=port_name)

        elif step["template"] == "move_labware":
            for port_type, port_name in [("sources", "sources"), ("targets", "targets")]:
                slot = step.get(port_type, [])
                if slot is not None:
                    prev_node = slot_last_writer.get(slot)
                    if prev_node:
                        source_port = "labware" if prev_node in labware_ids else f"{port_name}_out"
                        G.add_edge(prev_node, node_id, source_port=source_port, target_port=port_name)
                    slot_last_writer[slot] = node_id

        elif step["template"] == "oscillation" or step["template"] == "incubation":
            # pre_node_id = f"step_{i}"
            # slot = G.nodes[pre_node_id]['targets']
            G.add_edge(node_id, node_id, source_port="plate", target_port="plate")
            # print(pre_node_id,node_id)
            # slot_last_writer[slot] = node_id
    return G

def parse_protocol_biomek(labware_with_liquid, steps_info):

    labware_with_liquid = json.loads(labware_with_liquid)
    steps_info = json.loads(steps_info)

    steps_info = refactor_data(steps_info)
    protocol_graph = build_protocol_graph(labware_with_liquid,steps_info)
    data = nx.node_link_data(protocol_graph)
    work_flow = json.dumps(data, indent=4)
    print(work_flow)

if __name__ == "__main__":

    labware_with_liquid = '''
[    {
        "id": "stock plate on P1",
        "parent": "deck",
        "slot_on_deck": "P1",
        "class_name": "nest_12_reservoir_15ml",
        "liquid_type": [
            "master_mix"
        ],
        "liquid_volume": [10000],
        "liquid_input_wells": [
            "A1"
        ]
    },
    {
        "id": "Tip Rack BC230 TL2",
        "parent": "deck",
        "slot_on_deck": "TL2",
        "class_name": "BC230",
        "liquid_type": [],
        "liquid_volume": [],
        "liquid_input_wells": [
        ]
    },
        {
        "id": "Tip Rack BC230 on TL3",
        "parent": "deck",
        "slot_on_deck": "TL3",
        "class_name": "BC230",
        "liquid_type": [],
        "liquid_volume": [],
        "liquid_input_wells": [
        ]
    },
        {
        "id": "Tip Rack BC230 on TL4",
        "parent": "deck",
        "slot_on_deck": "TL4",
        "class_name": "BC230",
        "liquid_type": [],
        "liquid_volume": [],
        "liquid_input_wells": [
        ]
    },
        {
        "id": "Tip Rack BC230 on TL5",
        "parent": "deck",
        "slot_on_deck": "TL5",
        "class_name": "BC230",
        "liquid_type": [],
        "liquid_volume": [],
        "liquid_input_wells": [
        ]
    },
            {
        "id": "Tip Rack BC230 on P5",
        "parent": "deck",
        "slot_on_deck": "P5",
        "class_name": "BC230",
        "liquid_type": [],
        "liquid_volume": [],
        "liquid_input_wells": [
        ]
    },
                {
        "id": "Tip Rack BC230 on P6",
        "parent": "deck",
        "slot_on_deck": "P6",
        "class_name": "BC230",
        "liquid_type": [],
        "liquid_volume": [],
        "liquid_input_wells": [
        ]
    },
                    {
        "id": "Tip Rack BC230 on P7",
        "parent": "deck",
        "slot_on_deck": "P7",
        "class_name": "BC230",
        "liquid_type": [],
        "liquid_volume": [],
        "liquid_input_wells": [
        ]
    },
    {
        "id": "Tip Rack BC230 on P8",
        "parent": "deck",
        "slot_on_deck": "P8",
        "class_name": "BC230",
        "liquid_type": [],
        "liquid_volume": [],
        "liquid_input_wells": [
        ]
    },
        {
        "id": "Tip Rack BC230 P16",
        "parent": "deck",
        "slot_on_deck": "P16",
        "class_name": "BC230",
        "liquid_type": [],
        "liquid_volume": [],
        "liquid_input_wells": [
        ]
    },
    {
        "id": "stock plate on 4",
        "parent": "deck",
        "slot_on_deck": "P2",
        "class_name": "nest_12_reservoir_15ml",
        "liquid_type": [
            "bind beads"
        ],
        "liquid_volume": [10000],
        "liquid_input_wells": [
            "A1"
        ]
    },
        {
        "id": "stock plate on P2",
        "parent": "deck",
        "slot_on_deck": "P2",
        "class_name": "nest_12_reservoir_15ml",
        "liquid_type": [
            "bind beads"
        ],
        "liquid_volume": [10000],
        "liquid_input_wells": [
            "A1"
        ]
    },
        {
        "id": "stock plate on P3",
        "parent": "deck",
        "slot_on_deck": "P3",
        "class_name": "nest_12_reservoir_15ml",
        "liquid_type": [
            "ethyl alcohol"
        ],
        "liquid_volume": [10000],
        "liquid_input_wells": [
            "A1"
        ]
    },

        {
        "id": "oscillation",
        "parent": "deck",
        "slot_on_deck": "Orbital1",
        "class_name": "Orbital",
        "liquid_type": [],
        "liquid_volume": [],
        "liquid_input_wells": [
        ]
    },
        {
        "id": "working plate on P11",
        "parent": "deck",
        "slot_on_deck": "P11",
        "class_name": "NEST 2ml Deep Well Plate",
        "liquid_type": [
        ],
        "liquid_volume": [],
        "liquid_input_wells": [
        ]
    },
            {
        "id": "magnetics module on P12",
        "parent": "deck",
        "slot_on_deck": "P12",
        "class_name": "magnetics module",
        "liquid_type": [],
        "liquid_volume": [],
        "liquid_input_wells": [
        ]
    },
                {
        "id": "working plate on P13",
        "parent": "deck",
        "slot_on_deck": "P13",
        "class_name": "NEST 2ml Deep Well Plate",
        "liquid_type": [
        ],
        "liquid_volume": [],
        "liquid_input_wells": [
        ]
    },
        {
        "id": "waste on P22",
        "parent": "deck",
        "slot_on_deck": "P22",
        "class_name": "nest_1_reservoir_195ml",
        "liquid_type": [
        ],
        "liquid_volume": [],
        "liquid_input_wells": [
        ]
    }
]

'''

    steps_info = ''' 
{
  "steps": [
    {
      "step_number": 1,
      "operation": "transfer",
      "description": "转移PCR产物或酶促反应液至0.05ml 96孔板中",
      "parameters": {
        "source": "P1",
        "target": "P11",
        "tip_rack": "BC230",
        "volume": 50
      }
    },
    {
      "step_number": 2,
      "operation": "transfer",
      "description": "加入2倍体积Bind Beads BC至产物中",
      "parameters": {
        "source": "P2",
        "target": "P11",
        "tip_rack": "BC230",
        "volume": 100
      }
    },
    {
      "step_number": 3,
      "operation": "move_labware",
      "description": "移动P11至Orbital1用于振荡混匀",
      "parameters": {
        "source": "P11",
        "target": "Orbital1"
      }
    },
    {
      "step_number": 4,
      "operation": "oscillation",
      "description": "在Orbital1上振荡混匀Bind Beads BC与PCR产物（700-900rpm，300秒）",
      "parameters": {
        "rpm": 800,
        "time": 300
      }
    },
    {
      "step_number": 5,
      "operation": "move_labware",
      "description": "移动混匀后的板回P11",
      "parameters": {
        "source": "Orbital1",
        "target": "P11"
      }
    },
    {
      "step_number": 6,
      "operation": "move_labware",
      "description": "将P11移动到磁力架（P12）吸附3分钟",
      "parameters": {
        "source": "P11",
        "target": "P12"
      }
    },
    {
      "step_number": 7,
      "operation": "incubation",
      "description": "磁力架上室温静置3分钟完成吸附",
      "parameters": {
        "time": 180
      }
    },
    {
      "step_number": 8,
      "operation": "transfer",
      "description": "去除上清液至废液槽",
      "parameters": {
        "source": "P12",
        "target": "P22",
        "tip_rack": "BC230",
        "volume": 150
      }
    },
    {
      "step_number": 9,
      "operation": "transfer",
      "description": "加入300-500μl 75%乙醇清洗",
      "parameters": {
        "source": "P3",
        "target": "P12",
        "tip_rack": "BC230",
        "volume": 400
      }
    },
    {
      "step_number": 10,
      "operation": "move_labware",
      "description": "移动清洗板到Orbital1进行振荡",
      "parameters": {
        "source": "P12",
        "target": "Orbital1"
      }
    },
    {
      "step_number": 11,
      "operation": "oscillation",
      "description": "乙醇清洗液振荡混匀（700-900rpm, 45秒）",
      "parameters": {
        "rpm": 800,
        "time": 45
      }
    },
    {
      "step_number": 12,
      "operation": "move_labware",
      "description": "振荡后将板移回磁力架P12吸附",
      "parameters": {
        "source": "Orbital1",
        "target": "P12"
      }
    },
    {
      "step_number": 13,
      "operation": "incubation",
      "description": "吸附3分钟",
      "parameters": {
        "time": 180
      }
    },
    {
      "step_number": 14,
      "operation": "transfer",
      "description": "去除乙醇上清液至废液槽",
      "parameters": {
        "source": "P12",
        "target": "P22",
        "tip_rack": "BC230",
        "volume": 400
      }
    },
    {
      "step_number": 15,
      "operation": "transfer",
      "description": "第二次加入300-500μl 75%乙醇清洗",
      "parameters": {
        "source": "P3",
        "target": "P12",
        "tip_rack": "BC230",
        "volume": 400
      }
    },
    {
      "step_number": 16,
      "operation": "move_labware",
      "description": "再次移动清洗板到Orbital1振荡",
      "parameters": {
        "source": "P12",
        "target": "Orbital1"
      }
    },
    {
      "step_number": 17,
      "operation": "oscillation",
      "description": "再次乙醇清洗液振荡混匀（700-900rpm, 45秒）",
      "parameters": {
        "rpm": 800,
        "time": 45
      }
    },
    {
      "step_number": 18,
      "operation": "move_labware",
      "description": "振荡后板送回磁力架P12吸附",
      "parameters": {
        "source": "Orbital1",
        "target": "P12"
      }
    },
    {
      "step_number": 19,
      "operation": "incubation",
      "description": "再次吸附3分钟",
      "parameters": {
        "time": 180
      }
    },
    {
      "step_number": 20,
      "operation": "transfer",
      "description": "去除乙醇上清液至废液槽",
      "parameters": {
        "source": "P12",
        "target": "P22",
        "tip_rack": "BC230",
        "volume": 400
      }
    },
    {
      "step_number": 21,
      "operation": "incubation",
      "description": "空气干燥15分钟",
      "parameters": {
        "time": 900
      }
    },
    {
      "step_number": 22,
      "operation": "transfer",
      "description": "加30-50μl Elution Buffer洗脱",
      "parameters": {
        "source": "P4",
        "target": "P12",
        "tip_rack": "BC230",
        "volume": 40
      }
    },
    {
      "step_number": 23,
      "operation": "move_labware",
      "description": "移动到Orbital1振荡混匀（60秒）",
      "parameters": {
        "source": "P12",
        "target": "Orbital1"
      }
    },
    {
      "step_number": 24,
      "operation": "oscillation",
      "description": "Elution Buffer振荡混匀（700-900rpm, 60秒）",
      "parameters": {
        "rpm": 800,
        "time": 60
      }
    },
    {
      "step_number": 25,
      "operation": "move_labware",
      "description": "振荡后送回磁力架P12",
      "parameters": {
        "source": "Orbital1",
        "target": "P12"
      }
    },
    {
      "step_number": 26,
      "operation": "incubation",
      "description": "室温静置3分钟（洗脱反应）",
      "parameters": {
        "time": 180
      }
    },
    {
      "step_number": 27,
      "operation": "transfer",
      "description": "将上清液（DNA）转移到新板（P13）",
      "parameters": {
        "source": "P12",
        "target": "P13",
        "tip_rack": "BC230",
        "volume": 40
      }
    }
  ]
}
'''

    parse_protocol_biomek(labware_with_liquid, steps_info)
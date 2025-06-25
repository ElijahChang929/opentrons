import json
import os

file_dir = "/Users/guangxinzhang/Documents/Deep_Potential/opentrons/convert/protocols/detailed_action_json/"
enriched_steps_dir = "/Users/guangxinzhang/Documents/Deep_Potential/opentrons/convert/protocols/enriched_steps/"

protocol_names = [file_dir + d for d in os.listdir(file_dir)]

liquid_information = []

for detail_infor in protocol_names:
    try:
        with open(detail_infor, "r", encoding="utf-8") as f:
            data = json.load(f)
        liquid_infor = data['liquid_locations']
        liquid_information.append(liquid_infor)
    except Exception as e:
        print(e)

liquid_types = []
for i, liquid_infor in enumerate(liquid_information):
    liquid_type = list(liquid_infor.keys())
    # remove the [number] structure at the end of the string
    liquid_type = set([liquid.split('[')[0] for liquid in liquid_type])
    liquid_types.extend(liquid_type)


# count the number of each liquid type
liquid_types_count = {}
for liquid in liquid_types:
    if liquid not in liquid_types_count:
        liquid_types_count[liquid] = 1
    else:
        liquid_types_count[liquid] += 1

# sort the liquid types by count
liquid_types_count = dict(sorted(liquid_types_count.items(), key=lambda item: item[1], reverse=True))

# with open('liquid_types_count.json', 'w', encoding='utf-8') as f:
#     json.dump(liquid_types_count, f, indent=4, ensure_ascii=False)

liquid_to_check = ['beads','water','ethanol','pbs']

def gather_location(liquid_type, key_location, path_enriched_steps):

    with open(path_enriched_steps, "r", encoding="utf-8") as f:
        enriched_steps = json.load(f)

    asp_infor = {
        'top':[],
        'bottom':[],
        'move':[],
        'center':[],
        'move_to':[],
        'mix_detail':[],
    }
    dis_infor = {
        'top':[],
        'bottom':[],
        'move':[],
        'center':[],
        'move_to':[],
        'mix_detail':[],
    }

    for step in enriched_steps:

        for step_number, i in enumerate(step['sources']):

            if i['well'] == key_location[liquid_type]['well'] and i['slot'] == key_location[liquid_type]['slot']:
                #print("DEBUG", i['slot'], type(i['slot']),
      #key_location[liquid_type]['slot'], type(key_location[liquid_type]['slot']))
                # 对于吸和放，其实都要考察。序号上： 放 = 吸 + 1
                asp_infor['top'].append(step['top'][step_number])
                asp_infor['bottom'].append(step['bottom'][step_number])
                asp_infor['move'].append(step['move'][step_number])
                asp_infor['center'].append(step['center'][step_number])
                asp_infor['move_to'].append(step['move_to'][step_number])
                asp_infor['mix_detail'].append(step['mix_detail'][step_number])

                dis_infor['top'].append(step['top'][step_number+1])
                dis_infor['bottom'].append(step['bottom'][step_number+1])
                dis_infor['move'].append(step['move'][step_number+1])
                dis_infor['center'].append(step['center'][step_number+1])
                dis_infor['move_to'].append(step['move_to'][step_number+1])
                dis_infor['mix_detail'].append(step['mix_detail'][step_number+1])

    #print(asp_infor)
    return asp_infor, dis_infor

def visit_protocols(liquid_to_check, path_detail_infor, path_enriched_steps):

    liquid_transfer_properties = {

        key: {'aspirate':{
                'top':[],
                'bottom':[],
                'move':[],
                'center':[],
                'move_to':[],
                'mix_detail':[],
        },
              'dispense':{
                'top':[],
                'bottom':[],
                'move':[],
                'center':[],
                'move_to':[],
                'mix_detail':[],
              }
         } for key in liquid_to_check
    }

    protocol = [path_detail_infor+d for d in os.listdir(path_detail_infor)]

    for p in protocol:
        try:
            with open(p, "r", encoding="utf-8") as f:
                labware_data = json.load(f)
            liquid_infor = labware_data['liquid_locations']
            for key in list(liquid_infor.keys()):
                key_location = {}
                for liquid_type in liquid_to_check:
                    if liquid_type in key:
                        key_location[liquid_type] = liquid_infor[key]
                        if key_location[liquid_type]['slot'] in ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12']:
                            key_location[liquid_type]['slot'] = int(key_location[liquid_type]['slot'])
                            enriched_steps = os.path.join(path_enriched_steps, os.path.basename(p))
                            asp_infor, dis_infor = gather_location(liquid_type, key_location, enriched_steps)
                            for key in liquid_transfer_properties[liquid_type]['aspirate'].keys():
                                liquid_transfer_properties[liquid_type]['aspirate'][key].extend(asp_infor[key])
                            for key in liquid_transfer_properties[liquid_type]['dispense'].keys():
                                liquid_transfer_properties[liquid_type]['dispense'][key].extend(dis_infor[key])
        except Exception as e:
            print(e)

    return liquid_transfer_properties

liquid_transfer_properties = visit_protocols(liquid_to_check, file_dir, enriched_steps_dir)

with open('liquid_transfer_properties.json', 'w', encoding='utf-8') as f:
    json.dump(liquid_transfer_properties, f, indent=4, ensure_ascii=False)


# 靠壁其实意味着要和具体的板子相适应

# 高度也是

# 根据经验来编辑更为通用的Technique？

# 水/PBS

# 乙醇等

# beads等

# 可选择mix or not就行

# 默认mix
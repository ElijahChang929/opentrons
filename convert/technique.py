import json
import os

file_dir = "/Users/guangxinzhang/Documents/Deep Potential/opentrons/convert/protocols/detailed_action_json/"
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

print(liquid_types_count)

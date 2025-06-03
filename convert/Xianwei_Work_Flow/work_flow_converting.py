
import os
import sys
import json
import re
import pandas as pd

def convert_workflow_to_json(workflow_path):
    """
    Convert a workflow file to JSON format.
    
    Args:
        workflow_path (str): Path to the workflow file.
    
    Returns:
        dict: Parsed workflow data.
    """
    if not os.path.exists(workflow_path):
        raise FileNotFoundError(f"Workflow file not found: {workflow_path}")

    with open(workflow_path, 'r') as file:
        content = file.read()

    # Extract the JSON part from the content
    json_match = re.search(r'(\{.*\})', content, re.DOTALL)
    if not json_match:
        raise ValueError("No valid JSON found in the workflow file.")

    json_data = json.loads(json_match.group(1))
    
    return json_data

data = convert_workflow_to_json('0530.txt')


# 重构data，对于operation是transfer的信息，变成最外层是现在的step_number，里面的sources内容是继承data的source，targets 内容是继承data的target。别的不变

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

refactored_data = refactor_data(data)

print("Refactored Data:")
print(json.dumps(refactored_data, indent=4))
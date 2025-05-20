metadata = {
    "apiLevel": "2.10",
    "protocolName": "Simple Transfer"
}

def run(ctx):
    tiprack = ctx.load_labware("opentrons_96_tiprack_300ul", "1")
    pipette = ctx.load_instrument("p300_single", "right", tip_racks=[tiprack])
    plate = ctx.load_labware("corning_96_wellplate_360ul_flat", "2")
    pipette.pick_up_tip()
    pipette.aspirate(50, plate["A1"])
    pipette.dispense(50, plate["B1"])
    pipette.drop_tip()
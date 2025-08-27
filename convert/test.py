
from pylabrobot.resources.opentrons.tube_racks import *
from pylabrobot.resources.opentrons.tip_racks import *
from pylabrobot.resources.opentrons.reservoirs import *
from pylabrobot.resources.opentrons.plates import *
from pylabrobot.resources.opentrons.plate_adapters import *
from pylabrobot.resources.opentrons.module import *
from pylabrobot.resources.opentrons.deck import *


a = locals()["opentrons_24_tuberack_eppendorf_1point5ml_safelock_snapcap"](name="suibian")
from pprint import pprint
pprint(list(a._ordering.keys()))
pprint(a)


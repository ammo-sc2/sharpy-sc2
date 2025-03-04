from sc2 import UnitTypeId, AbilityId, Set
from sc2.unit import Unit
from .act_base import ActBase


class MorphBuilding(ActBase):
    def __init__(self, building_type: UnitTypeId, ability_type: AbilityId, result_type: UnitTypeId, target_count: int):
        super().__init__()
        self.target_count = target_count
        self.result_type = result_type
        self.ability_type = ability_type
        self.building_type = building_type

    async def execute(self) -> bool:
        target_count = self.cache.own(self.result_type).amount
        start_buildings = self.cache.own(self.building_type).ready.sorted_by_distance_to(
            self.zone_manager.own_main_zone.center_location
        )

        ignore_tags: Set[int] = set()
        for target in start_buildings:  # type: Unit
            if target.orders and target.orders[0].ability.id == self.ability_type:
                target_count += 1
                ignore_tags.add((target.tag))

        if target_count >= self.target_count:
            return True

        for target in start_buildings:
            if target.is_ready and target.tag not in ignore_tags:
                if self.knowledge.can_afford(self.ability_type):
                    target(self.ability_type, subtract_cost=True)
                else:
                    self.knowledge.reserve_costs(self.ability_type)

                target_count += 1

                if target_count >= self.target_count:
                    return True
        if start_buildings:
            return False
        return True

from typing import Optional, List

from sc2 import Race, UnitTypeId, AbilityId
from sc2.ids.upgrade_id import UpgradeId
from sc2.position import Point2
from sc2.unit import Unit
from sharpy.general.extended_power import ExtendedPower
from sharpy.interfaces import IGameAnalyzer, IZoneManager
from sharpy.interfaces.combat_manager import MoveType

from sharpy.knowledges import Knowledge, KnowledgeBot
from sharpy.combat import GenericMicro, Action, MicroRules
from sharpy.managers.core.roles import UnitTask
from sharpy.managers.extensions import BuildDetector
from sharpy.plans.zerg import *


class MicroTunnelRoaches(GenericMicro):
    """
    Annoying micro for Roaches that uses burrow and tunnel.
    """

    def unit_solve_combat(self, unit: Unit, current_command: Action) -> Action:

        burrow_ready = self.cd_manager.is_ready(unit.tag, AbilityId.BURROWDOWN_ROACH)
        unburrow_ready = self.cd_manager.is_ready(unit.tag, AbilityId.BURROWUP_ROACH)

        if self.knowledge.ai.enemy_race == Race.Zerg:
            self.burrow_up_percentage = 0.75
            self.burrow_down_percentage = 0.25
        if self.knowledge.ai.enemy_race == Race.Protoss:
            self.burrow_up_percentage = 0.9
            self.burrow_down_percentage = 0.25
        if self.knowledge.ai.enemy_race == Race.Terran:
            self.burrow_up_percentage = 0.9
            self.burrow_down_percentage = 0.4

        detectors = self.ai.all_enemy_units.of_type(
            [
                UnitTypeId.OBSERVER,
                UnitTypeId.OBSERVERSIEGEMODE,
                UnitTypeId.OVERSEER,
                UnitTypeId.RAVEN,
                UnitTypeId.MISSILETURRET,
                UnitTypeId.SPORECRAWLER,
                UnitTypeId.PHOTONCANNON
            ]
        )

        enemies = self.cache.enemy_in_range(unit.position, 10).filter(
            lambda u: u.type_id not in self.unit_values.combat_ignore
        )
        relevant_enemies_power = ExtendedPower(self.knowledge.unit_values)
        relevant_enemies_power.add_units(enemies)
        relevant_friendlies_power = ExtendedPower(self.knowledge.unit_values)
        relevant_friendlies_power.add_units(self.cache.own_in_range(unit.position, 10).not_structure)

        if detectors.exists:
            close = detectors.closest_to(unit)
            dd = close.distance_to(unit)

            if close is not None and dd <= 11 \
                    and unit.is_burrowed \
                    and unburrow_ready:
                return Action(None, False, AbilityId.BURROWUP_ROACH)

            if relevant_enemies_power.power > (relevant_friendlies_power.power * 1.5) \
                    and unit.is_burrowed \
                    and close is not None and dd > 11:
                return self.stay_safe(unit, current_command)

            if relevant_enemies_power.power > (relevant_friendlies_power.power * 1.5) \
                    and not unit.is_burrowed \
                    and burrow_ready \
                    and close is not None and dd > 11:
                return Action(None, False, AbilityId.BURROWDOWN_ROACH)

            if unit.health_percentage < self.burrow_up_percentage \
                    and unit.is_burrowed \
                    and close is not None and dd > 11 \
                    and TechReady(UpgradeId.TUNNELINGCLAWS):
                return self.stay_safe(unit, current_command)

            if unit.health_percentage < self.burrow_down_percentage \
                    and not unit.is_burrowed \
                    and burrow_ready \
                    and close is not None and dd > 11:
                return Action(None, False, AbilityId.BURROWDOWN_ROACH)

        else:
            if relevant_enemies_power.power > (relevant_friendlies_power.power * 1.5) \
                    and unit.is_burrowed \
                    and TechReady(UpgradeId.TUNNELINGCLAWS):
                return self.stay_safe(unit, current_command)

            if relevant_enemies_power.power > (relevant_friendlies_power.power * 1.5) \
                    and not unit.is_burrowed \
                    and burrow_ready:
                return Action(None, False, AbilityId.BURROWDOWN_ROACH)

            if unit.health_percentage < self.burrow_up_percentage \
                    and unit.is_burrowed \
                    and TechReady(UpgradeId.TUNNELINGCLAWS):
                return self.stay_safe(unit, current_command)

            if unit.health_percentage < self.burrow_down_percentage \
                    and not unit.is_burrowed \
                    and burrow_ready:
                return Action(None, False, AbilityId.BURROWDOWN_ROACH)

        return super().unit_solve_combat(unit, current_command)

    def stay_safe(self, unit: Unit, current_command: Action) -> Action:
        """Partial retreat, micro back."""
        pos = self.pather.find_weak_influence_ground(unit.position, 6)
        return Action(pos, False)


class NewMicroMethods:
    @staticmethod
    def handle_groups(combat: "GroupCombatManager", target: Point2, move_type=MoveType.Harass):
        total_power = ExtendedPower(combat.unit_values)

        for group in combat.own_groups:
            total_power.add_power(group.power)

        for group in combat.own_groups:
            # Skip all regroup logic
            if move_type == MoveType.PanicRetreat:
                combat.move_to(group, target, move_type)
            else:
                combat.attack_to(group, target, move_type)
            continue


class RoachHarassTunnel(ActBase):
    def __init__(self):
        self.micro = MicroRules()
        self.micro.load_default_methods()
        self.micro.handle_groups_func = NewMicroMethods.handle_groups
        self.micro.generic_micro = MicroTunnelRoaches()
        super().__init__()

    async def start(self, knowledge: "Knowledge"):
        await super().start(knowledge)
        await self.micro.start(knowledge)

    async def execute(self) -> bool:

        target = await self.select_harass_target()

        for harasser in self.cache.own(UnitTypeId.ROACH):
            self.combat.add_unit(harasser)
            self.roles.set_task(UnitTask.Reserved, harasser)

        base_ramp = self.zone_manager.expansion_zones[-1].ramp
        pos: Point2 = base_ramp.top_center

        ramp_defenders = self.ai.all_enemy_units.of_type(
            [
                UnitTypeId.SIEGETANK,
                UnitTypeId.SIEGETANKSIEGED,
                UnitTypeId.BUNKER,
                UnitTypeId.PHOTONCANNON,
                UnitTypeId.SHIELDBATTERY,
                UnitTypeId.SPINECRAWLER,
            ]
        )
        if ramp_defenders.exists:
            close = ramp_defenders.closest_to(pos)
            d = close.distance_to(pos)

            if not (close is not None and d < 6):
                self.combat.execute(target, MoveType.Harass, rules=self.micro)

        else:
            self.combat.execute(target, MoveType.Harass, rules=self.micro)

        return True

    async def select_harass_target(self) -> Optional[Point2]:
        our_main = self.zone_manager.expansion_zones[0].center_location
        proxy_buildings = self.ai.enemy_structures.closer_than(70, our_main)

        if proxy_buildings.exists:
            return proxy_buildings.closest_to(our_main).position

        # Select expansion to attack.
        # Enemy main zone should the last element in expansion_zones.
        enemy_zones = list(filter(lambda z: z.is_enemys, self.zone_manager.expansion_zones))

        best_zone = None
        best_score = 100000
        start_position = our_main

        for zone in enemy_zones:  # type: Zone
            not_like_points = zone.center_location.distance_to(start_position)
            not_like_points += zone.enemy_static_power.power * 5
            if not_like_points < best_score:
                best_zone = zone
                best_score = not_like_points

        if best_zone is not None:
            return best_zone.behind_mineral_position_center

        if self.ai.enemy_structures.exists:
            return self.ai.enemy_structures.closest_to(our_main).position

        return None


class HydraOnly(BuildOrder):
    def __init__(self):
        self.hydras = ZergUnit(UnitTypeId.HYDRALISK, priority=True)
        self.queens = Step(Minerals(200), ZergUnit(UnitTypeId.QUEEN, 12))
        super().__init__(self.hydras, self.queens)

    async def execute(self) -> bool:
        return await super().execute()


class HydraRoach(BuildOrder):
    def __init__(self):
        self.hydras = ZergUnit(UnitTypeId.HYDRALISK, priority=True)
        self.roaches = ZergUnit(UnitTypeId.ROACH, priority=True)
        super().__init__(self.hydras, self.roaches)

    async def execute(self) -> bool:
        self.hydras.to_count = self.get_count(UnitTypeId.ROACH) / 2
        return await super().execute()


class RoachOnly(BuildOrder):
    def __init__(self):
        self.roaches = ZergUnit(UnitTypeId.ROACH, priority=True)
        super().__init__(self.roaches)

    async def execute(self) -> bool:
        return await super().execute()


class RoachTunnelBuild(BuildOrder):
    def __init__(self):

        opener = [
            Step(Supply(14), ActBuilding(UnitTypeId.SPAWNINGPOOL, 1)),
            Step(Supply(14), BuildGas(1)),
            AutoOverLord(),
            Step(UnitExists(UnitTypeId.SPAWNINGPOOL),
                 PositionBuilding(UnitTypeId.ROACHWARREN, DefensePosition.BehindMineralLineCenter, 0)),
            Step(UnitReady(UnitTypeId.LAIR), MorphOverseer(1)),
        ]

        counter_workerrush = [
            Step(
                None,
                ActBuilding(UnitTypeId.SPAWNINGPOOL, 1),
                skip_until=lambda k: self.build_detector.rush_build == 15
            ),
            Step(
                None,
                ZergUnit(UnitTypeId.ZERGLING, 6),
                skip_until=lambda k: self.build_detector.rush_build == 15
            )
        ]

        hydra_trigger = [
            Step(
                Any(
                    [
                        EnemyUnitExists(UnitTypeId.BANSHEE, 1),
                        EnemyUnitExists(UnitTypeId.BATTLECRUISER, 1),
                        EnemyUnitExists(UnitTypeId.RAVEN, 2),
                        EnemyUnitExists(UnitTypeId.LIBERATOR, 2),
                        EnemyUnitExists(UnitTypeId.MEDIVAC, 4),
                        EnemyUnitExists(UnitTypeId.FUSIONCORE, 1),
                        EnemyUnitExists(UnitTypeId.PHOENIX, 1),
                        EnemyUnitExists(UnitTypeId.CARRIER, 1),
                        EnemyUnitExists(UnitTypeId.VOIDRAY, 1),
                        EnemyUnitExists(UnitTypeId.WARPPRISM, 1),
                        EnemyUnitExists(UnitTypeId.STARGATE, 1),
                        EnemyUnitExists(UnitTypeId.TEMPEST, 1),
                        EnemyUnitExists(UnitTypeId.ORACLE, 2),
                        EnemyUnitExists(UnitTypeId.MUTALISK, 1),
                        EnemyUnitExists(UnitTypeId.BROODLORD, 1),
                        EnemyUnitExists(UnitTypeId.CORRUPTOR, 1),
                        EnemyUnitExists(UnitTypeId.VIPER, 1),
                        EnemyUnitExists(UnitTypeId.SPIRE, 1),
                        Time(10 * 60)
                    ]
                ),
                None,
            ),
            Step(None, PositionBuilding(UnitTypeId.HYDRALISKDEN, DefensePosition.BehindMineralLineLeft, 0)),
        ]

        gas = [
            Step(Supply(40), BuildGas(2)),
            Step(Supply(52), BuildGas(3)),
            Step(None, BuildGas(4), skip=Gas(100), skip_until=Supply(40, supply_type=SupplyType.Workers)),
            Step(None, BuildGas(5), skip=Gas(300), skip_until=Supply(45, supply_type=SupplyType.Workers)),
            Step(None, BuildGas(6), skip=Gas(300), skip_until=Supply(50, supply_type=SupplyType.Workers)),
            Step(None, BuildGas(7), skip=Gas(300), skip_until=Supply(55, supply_type=SupplyType.Workers)),
            Step(None, BuildGas(8), skip=Gas(300), skip_until=Supply(60, supply_type=SupplyType.Workers)),
            Step(None, BuildGas(10), skip=Gas(300), skip_until=Supply(70, supply_type=SupplyType.Workers)),
        ]

        tech = [
            Step(Supply(44), MorphLair(), skip=UnitExists(UnitTypeId.HIVE, 1)),
            Step(Supply(78), ActBuilding(UnitTypeId.EVOLUTIONCHAMBER, 1)),
            Step(Supply(96), ActBuilding(UnitTypeId.EVOLUTIONCHAMBER, 2)),
            Step(Supply(200), MorphHive(), skip=UnitExists(UnitTypeId.HIVE, 1)),
        ]

        workers = [
            ZergUnit(UnitTypeId.DRONE, 16),
            Step(
                All(
                    UnitExists(UnitTypeId.ROACHWARREN, 1, include_killed=True),
                    UnitExists(UnitTypeId.QUEEN, 1, include_killed=True)
                ),
                ZergUnit(UnitTypeId.DRONE, 20),
            ),
            Step(
                UnitExists(UnitTypeId.ROACH, 2, include_killed=True),
                ZergUnit(UnitTypeId.DRONE, 24),
                skip_until=All(
                    lambda k: self.game_analyzer.army_can_survive == True,  # Army Predict Even or better
                ),
            ),
            Step(
                UnitExists(UnitTypeId.ROACH, 6, include_killed=True),
                ZergUnit(UnitTypeId.DRONE, 30),
                skip_until=All(
                    lambda k: self.game_analyzer.army_can_survive == True,  # Army Predict Even or better
                ),
            ),
            Step(
                UnitExists(UnitTypeId.ROACH, 12, include_killed=True),
                ZergUnit(UnitTypeId.DRONE, 50),
                skip_until=All(
                    lambda k: self.game_analyzer.army_can_survive == True,  # Army Predict Even or better
                ),
            ),
            Step(
                Supply(50, supply_type=SupplyType.Combat),
                ZergUnit(UnitTypeId.DRONE, 90),
                skip_until=lambda k: self.game_analyzer.army_can_survive == True  # Army Predict Even or better
            ),
        ]

        expansions = [
            Step(UnitExists(UnitTypeId.ROACH, 2, include_killed=True), Expand(2)),
            Step(Supply(40, supply_type=SupplyType.Workers), Expand(3)),
            Step(Supply(60, supply_type=SupplyType.Workers), Expand(4)),
        ]

        queens = [
            Step(UnitExists(UnitTypeId.SPAWNINGPOOL), ZergUnit(UnitTypeId.QUEEN, 1, priority=True)),
            Step(Supply(30), ZergUnit(UnitTypeId.QUEEN, 2, priority=True)),
            Step(Supply(45), ZergUnit(UnitTypeId.QUEEN, 3)),
        ]

        counter_spores = [
            Step(
                Any(
                    [
                        EnemyUnitExists(UnitTypeId.BANSHEE),
                        EnemyUnitExists(UnitTypeId.BATTLECRUISER),
                        EnemyUnitExists(UnitTypeId.ORACLE),
                    ]
                ),
                None,
            ),
            Step(None, DefensiveBuilding(UnitTypeId.SPORECRAWLER, DefensePosition.Entrance, 2)),
            Step(None, DefensiveBuilding(UnitTypeId.SPORECRAWLER, DefensePosition.CenterMineralLine, None)),
        ]

        units = [
            Step(None, HydraOnly(),
                 skip_until=lambda k: self.game_analyzer.enemy_air > 2 and UnitReady(UnitTypeId.HYDRALISKDEN)),
            # almost all air or all air
            Step(None, HydraRoach(), skip_until=UnitReady(UnitTypeId.HYDRALISKDEN)),
            Step(None, RoachOnly(), skip_until=UnitReady(UnitTypeId.ROACHWARREN)),
        ]

        upgrades = [
            Step(UnitReady(UnitTypeId.ROACHWARREN), Tech(UpgradeId.BURROW)),
            Step(All(UnitReady(UnitTypeId.ROACHWARREN), UnitReady(UnitTypeId.LAIR)), Tech(UpgradeId.TUNNELINGCLAWS)),
            Step(All(UnitReady(UnitTypeId.ROACHWARREN), UnitReady(UnitTypeId.LAIR)),
                 Tech(UpgradeId.GLIALRECONSTITUTION)),
            Step(None, Tech(UpgradeId.OVERLORDSPEED)),
            Step(UnitReady(UnitTypeId.EVOLUTIONCHAMBER), Tech(UpgradeId.ZERGMISSILEWEAPONSLEVEL1)),
            Step(UnitReady(UnitTypeId.EVOLUTIONCHAMBER), Tech(UpgradeId.ZERGGROUNDARMORSLEVEL1)),
            Step(UnitReady(UnitTypeId.EVOLUTIONCHAMBER), Tech(UpgradeId.ZERGMISSILEWEAPONSLEVEL2)),
            Step(UnitReady(UnitTypeId.EVOLUTIONCHAMBER), Tech(UpgradeId.ZERGGROUNDARMORSLEVEL2)),
            Step(UnitReady(UnitTypeId.EVOLUTIONCHAMBER), Tech(UpgradeId.ZERGMISSILEWEAPONSLEVEL3)),
            Step(UnitReady(UnitTypeId.EVOLUTIONCHAMBER), Tech(UpgradeId.ZERGGROUNDARMORSLEVEL3)),
        ]

        use_money = [
            Step(UnitExists(UnitTypeId.ROACH, 2, include_killed=True), None),
            Step(Minerals(450), Expand(6)),
            Step(Minerals(800), Expand(99)),
        ]

        scout_overlords = [
            Step(
                UnitExists(UnitTypeId.OVERLORD, 1, include_killed=True),
                OverlordScout(ScoutLocation.scout_enemy_natural_ol_spot())
            ),
        ]

        attack = [
            Step(TechReady(UpgradeId.BURROW, 0.5),
                 RoachHarassTunnel(),
                 skip=Any(
                     UnitReady(UnitTypeId.HYDRALISKDEN),
                 ),
                 ),

            Step(None, PlanZoneAttackAllIn(10), skip_until=Supply(100, supply_type=SupplyType.Combat)),
            Step(None, PlanZoneAttack(30)),
        ]

        tactics = [
            DistributeWorkers(),
            SpeedMining(),
            PlanZoneGather(),
            PlanZoneDefense(),
            PlanCancelBuilding(),
            Step(None, SpreadCreepV2(), skip_until=lambda k: self.knowledge.ai.enemy_race != Race.Zerg),
            InjectLarva(),
            PlanFinishEnemy()
        ]

        super().__init__(
            [
                counter_workerrush,
                opener,
                counter_spores,
                hydra_trigger,
                gas,
                workers,
                expansions,
                queens,
                tech,
                upgrades,
                units,
                use_money,
                attack,
                scout_overlords,
                tactics,
            ]
        )

    async def start(self, knowledge: "Knowledge"):
        await super().start(knowledge)
        self.zone_manager = knowledge.get_required_manager(IZoneManager)
        self.build_detector = knowledge.get_required_manager(BuildDetector)
        self.game_analyzer = knowledge.get_required_manager(IGameAnalyzer)


class RoachTunnelBot(KnowledgeBot):
    """
    Dummy bot that harasses with burrowed roaches, made for ZvZ
    """

    def __init__(self):
        super().__init__("CMTunnel")

    def configure_managers(self) -> Optional[List["ManagerBase"]]:
        return [BuildDetector()]

    async def create_plan(self) -> BuildOrder:
        return BuildOrder(
            CounterTerranTie([RoachTunnelBuild()]),
        )


class LadderBot(RoachTunnelBot):
    @property
    def my_race(self):
        return Race.Zerg

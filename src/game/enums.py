from enum import Enum

class RestType(Enum):
    SHORT = "short"
    LONG = "long"

class StatusEffectType(Enum):
    ATKMOD = "attack_modifier"
    ACMOD = "ac_modifier"
    DOT = "DoT"
    HOT = "HoT"
    CONTROL = "control"
    IMMUNITY = "immunity"
    RESISTANCE = "resistance"
    VULNERABLE = "vulnerable" 

class DamageType(Enum):
    ACID = "acid"
    BLUDGEONING = "bludgeoning"
    COLD = "cold"
    FIRE = "fire"
    FORCE = "force"
    LIGHTNING = "lightning"
    NECROTIC = "necrotic"
    PIERCING = "piercing"
    POISON = "poison"
    PSYCHIC = "psychic"
    RADIANT = "radiant"
    SLASHING = "slashing"
    THUNDER = "thunder"

class ControlType(Enum):
    STUNNED = "stunned"
    ASLEEP = "asleep"
    RESTRAINED = "restrained"
    SILENCED = "silenced"

class AttackType(Enum):
    MELEE = "melee"
    RANGED = "ranged"
    UNARMED = "unarmed"
    AOE_MELEE = "aoe_melee"
    AOE_RANGED = "aoe_ranged"
    AOE_UNARMED = "aoe_unarmed"

class SpellType(Enum):
    ATTACK = "attack"
    HEAL = "heal"
    BUFF = "buff"
    DEBUFF = "debuff"
    CONTROL = "control"
    CLEANSE = "cleanse"
    AOE_ATTACK = "aoe_attack"
    AOE_HEAL = "aoe_heal"
    AOE_BUFF = "aoe_buff"
    AOE_DEBUFF = "aoe_debuff"
    AOE_CONTROL = "aoe_control"
    AOE_CLEANSE = "aoe_cleanse"

class WeaponProficiency(Enum):
    SIMPLE= "simple"
    MARTIAL = "martial"
    EXOTIC = "exotic"
    ARCANE = "arcane"
    DIVINE = "divine"
    TECH = "tech"

class WeaponHandling(Enum):
    ONE_HANDED = "one_handed"
    TWO_HANDED = "two_handed"
    VERSATILE = "versatile"

class WeaponWeightClass(Enum):
    LIGHT = "light"
    HEAVY = "heavy"

class WeaponDelivery(Enum):
    MELEE = "melee"
    RANGED = "ranged"
    VERSATILE = "versatile"

class WeaponMagicType(Enum):
    MUNDANE = "mundane"
    ENCHANTED = "enchanted"
    FOCUS = "focus"
    AUGMENT = "augment"
from . import base as _base
_globals = {k: v for k, v in vars(_base).items() if not k.startswith('__')}
globals().update(_globals)
def plan_coin_spending(skills, plan, coin_balance):
    if coin_balance < 0:
        raise ValueError("Coin balance cannot be negative.")
    skill_lookup = {skill_key(skill["name"]): skill for skill in skills}
    remaining = coin_balance
    purchases = []
    next_purchase = None
    for action in plan["actions"]:
        skill = skill_lookup[skill_key(action["skill"])]
        costs = skill["versions"]["Current"]
        current_level = action["current_level"]
        funded_level = current_level
        action_cost = 0
        for level_index in range(current_level, action["target_level"]):
            cost = costs[level_index]["cost"]
            if cost > remaining:
                next_purchase = {
                    "skill": action["skill"],
                    "current_level": funded_level,
                    "target_level": funded_level + 1,
                    "cost": cost,
                }
                break
            remaining -= cost
            action_cost += cost
            funded_level = level_index + 1
        if funded_level > current_level:
            purchases.append({
                "skill": action["skill"],
                "current_level": current_level,
                "target_level": funded_level,
                "cost": action_cost,
            })
        if next_purchase:
            break
    return {
        "purchases": purchases,
        "next_purchase": next_purchase,
        "spent": coin_balance - remaining,
        "unspent": remaining,
    }


def format_skill_plan(plan, skills, coin_balance=None):
    if coin_balance is None:
        lines = ["**Next upgrades (Current):**"] if plan["actions"] else ["**All route goals reached.**"]
        for index, action in enumerate(plan["actions"][:5], 1):
            lines.append(
                f"{index}. {action['skill']}: {action['current_level']} â†’ {action['target_level']} "
                f"({action['cost']:,} Coins)"
            )
        if len(plan["actions"]) > 5:
            lines.append(f"â€¦and {len(plan['actions']) - 5} more steps.")
    else:
        spending = plan_coin_spending(skills, plan, coin_balance)
        lines = [f"**Recommended spending for {coin_balance:,} Coins:**"]
        if spending["purchases"]:
            lines.extend(
                f"{index}. {item['skill']}: {item['current_level']} â†’ {item['target_level']} "
                f"({item['cost']:,} Coins)"
                for index, item in enumerate(spending["purchases"], 1)
            )
        elif spending["next_purchase"]:
            lines.append("Save your coins for the next planned upgrade.")
        if spending["next_purchase"]:
            item = spending["next_purchase"]
            lines.append(
                f"Save {spending['unspent']:,} toward {item['skill']} level {item['target_level']} "
                f"({item['cost']:,} Coins needed)."
            )
        elif spending["unspent"]:
            lines.append(f"Route complete; {spending['unspent']:,} Coins remain unspent.")
        lines.append(f"**Spent:** {spending['spent']:,} Coins")
    lines.append(f"**Coins to finish the route:** {plan['total_cost']:,}")
    return "\n".join(lines)


def _skill_tree(options):
    return {key: int(options.get(key) or 0) for key in SKILL_TREE_KEYS}


def _pack_state(page_index, include_changes, include_description, skill_tree, history_group=0):
    values = [page_index, int(include_changes), int(include_description)]
    values.extend(int((skill_tree or {}).get(key, 0)) for key in SKILL_TREE_KEYS)
    values.append(int(history_group))
    return ",".join(str(value) for value in values)


def _unpack_state(state):
    """state: [page, include_changes, include_description, *skill tree values]"""
    include_changes = bool(state[1]) if len(state) > 1 else False
    include_description = bool(state[2]) if len(state) > 2 else False
    skill_tree = {
        key: state[3 + index] if len(state) > 3 + index else 0
        for index, key in enumerate(SKILL_TREE_KEYS)
    }
    return include_changes, include_description, skill_tree


def _history_group(state):
    return int(state[3 + len(SKILL_TREE_KEYS)]) if len(state) > 3 + len(SKILL_TREE_KEYS) else 0




SENSITIVE = ['send', 'delete', 'pay', 'purchase', 'checkout']

def requires_confirmation(step_name: str) -> bool:
    low = step_name.lower()
    return any(s in low for s in SENSITIVE)

def guard_step(step) -> str:
    if step.safety_level == 'BLOCKED':
        return 'blocked'
    if step.safety_level == 'CONFIRM' or requires_confirmation(step.name):
        return 'confirm'
    return 'allow'

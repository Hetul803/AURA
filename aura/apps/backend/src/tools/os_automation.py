import platform

def open_app(name: str) -> dict:
    system = platform.system().lower()
    if system not in ['darwin', 'windows']:
        return {'ok': False, 'reason': 'unsupported_os'}
    return {'ok': True, 'action': f'open_app:{name}', 'system': system}

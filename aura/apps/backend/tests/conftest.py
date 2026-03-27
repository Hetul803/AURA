import os


def pytest_configure(config):
    os.environ.setdefault('AURA_FORCE_FIXTURES', '1')

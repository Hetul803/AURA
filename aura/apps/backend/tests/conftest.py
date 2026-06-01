import os


def pytest_configure(config):
    os.environ.setdefault('AEGISURE_FORCE_FIXTURES', '1')
    os.environ.setdefault('AEGISURE_LEGACY_COMPAT', '1')

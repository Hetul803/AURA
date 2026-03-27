from .db import init_db

def run_migrations() -> None:
    init_db()

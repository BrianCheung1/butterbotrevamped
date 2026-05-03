import sqlite3
from functools import wraps

from logger import setup_logger

logger = setup_logger("DatabaseErrorHandler")


def db_error_handler(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)

        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower():
                logger.error(
                    f"Database locked in {func.__qualname__}: {e}",
                    exc_info=True,
                )
            else:
                logger.error(
                    f"Database operational error in {func.__qualname__}: {e}",
                    exc_info=True,
                )
            raise

        except Exception as e:
            logger.error(
                f"Unexpected error in {func.__qualname__}: {e}",
                exc_info=True,
            )
            raise

    return wrapper

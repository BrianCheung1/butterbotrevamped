from functools import wraps

from logger import setup_logger

logger = setup_logger("DatabaseErrorHandler")


def db_error_handler(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Database error in {func.__name__}: {e}", exc_info=True)
            raise

    return wrapper

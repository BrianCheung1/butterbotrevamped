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
            # Check if the error is related to a locked database
            if "database is locked" in str(e).lower():
                logger.error(
                    f"Database is locked during {func.__name__} execution: {e}",
                    exc_info=True,
                )
                # Optionally, send a user-friendly message to the user
                await args[0].response.send_message(
                    "The database is currently locked. Please try again later.",
                    ephemeral=True,
                )
            else:
                # Handle other OperationalErrors (not a lock)
                logger.error(f"Database error in {func.__name__}: {e}", exc_info=True)
                raise
        except Exception as e:
            # Log any other general errors
            logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
            raise

    return wrapper

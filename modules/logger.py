import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Create a logger for user-assistant communication
comm_logger = logging.getLogger('communication')
comm_logger.setLevel(logging.INFO)
comm_logger.propagate = False

# Create a logger for debug messages
debug_logger = logging.getLogger('debug')
debug_logger.setLevel(logging.DEBUG)
debug_logger.propagate = False

COMM_LOG_PATH = Path("communication.log")
DEBUG_LOG_PATH = Path("debug.log")
DEFAULT_MAX_LOG_BYTES = 2 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 5

def setup_loggers(
    clear_communication_log: bool = True,
    max_bytes: int = DEFAULT_MAX_LOG_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
):
    """
    Set up the loggers for the application.
    This should be called once at the start of the application.
    """
    # Clear and close existing handlers to avoid duplicate logs and file descriptor leaks
    if comm_logger.hasHandlers():
        for handler in list(comm_logger.handlers):
            handler.close()
            comm_logger.removeHandler(handler)
    if debug_logger.hasHandlers():
        for handler in list(debug_logger.handlers):
            handler.close()
            debug_logger.removeHandler(handler)

    if clear_communication_log:
        COMM_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        COMM_LOG_PATH.write_text("", encoding="utf-8")

    # Communication Log Handler with rotation
    comm_handler = RotatingFileHandler(
        COMM_LOG_PATH,
        mode='a',
        encoding="utf-8",
        maxBytes=max_bytes,
        backupCount=backup_count,
    )
    # The formatter for the communication log will be very simple, just the message.
    comm_formatter = logging.Formatter('%(asctime)s - %(message)s')
    comm_handler.setFormatter(comm_formatter)
    comm_logger.addHandler(comm_handler)

    # Debug Log Handler with rotation
    debug_handler = RotatingFileHandler(
        DEBUG_LOG_PATH,
        mode='a',
        encoding="utf-8",
        maxBytes=max_bytes,
        backupCount=backup_count,
    )
    debug_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    debug_handler.setFormatter(debug_formatter)
    debug_logger.addHandler(debug_handler)

def get_comm_logger():
    """Returns the communication logger instance."""
    return comm_logger

def get_debug_logger():
    """Returns the debug logger instance."""
    return debug_logger

def get_log_files(include_rotated: bool = True) -> list[Path]:
    """Return current log files and, optionally, rotated ones."""
    files = [COMM_LOG_PATH, DEBUG_LOG_PATH]
    if include_rotated:
        files.extend(sorted(Path(".").glob("communication.log.*")))
        files.extend(sorted(Path(".").glob("debug.log.*")))
    return [p for p in files if p.exists() and p.is_file()]

def log_debug(message, *args, **kwargs):
    """Convenience function to log a debug message."""
    debug_logger.debug(message, *args, **kwargs)

def log_info(message, *args, **kwargs):
    """Convenience function to log an info message."""
    debug_logger.info(message, *args, **kwargs)

def log_warning(message, *args, **kwargs):
    """Convenience function to log a warning message."""
    debug_logger.warning(message, *args, **kwargs)

def log_error(message, *args, **kwargs):
    """Convenience function to log an error message."""
    debug_logger.error(message, *args, **kwargs)

# Initial setup when module is loaded.
setup_loggers()

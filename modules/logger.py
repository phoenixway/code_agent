import logging
import os

# Create a logger for user-assistant communication
comm_logger = logging.getLogger('communication')
comm_logger.setLevel(logging.INFO)

# Create a logger for debug messages
debug_logger = logging.getLogger('debug')
debug_logger.setLevel(logging.DEBUG)

def setup_loggers(clear_communication_log=True):
    """
    Set up the loggers for the application.
    This should be called once at the start of the application.
    """
    # Clear existing handlers to avoid duplicate logs
    if comm_logger.hasHandlers():
        comm_logger.handlers.clear()
    if debug_logger.hasHandlers():
        debug_logger.handlers.clear()

    # Communication Log Handler
    comm_mode = 'w' if clear_communication_log else 'a'
    comm_handler = logging.FileHandler("communication.log", mode=comm_mode, encoding="utf-8")
    # The formatter for the communication log will be very simple, just the message.
    comm_formatter = logging.Formatter('%(message)s')
    comm_handler.setFormatter(comm_formatter)
    comm_logger.addHandler(comm_handler)

    # Debug Log Handler
    debug_handler = logging.FileHandler("debug.log", mode='w', encoding="utf-8")
    debug_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    debug_handler.setFormatter(debug_formatter)
    debug_logger.addHandler(debug_handler)

def get_comm_logger():
    """Returns the communication logger instance."""
    return comm_logger

def get_debug_logger():
    """Returns the debug logger instance."""
    return debug_logger

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

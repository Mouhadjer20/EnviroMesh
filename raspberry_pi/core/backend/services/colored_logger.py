"""EnviroMesh — Colored Logging Formatter and Setup.

Provides high-visibility ANSI colored output for log messages across all layers:
- DEBUG:    Cyan
- INFO:     Bright Green
- WARNING:  Bright Yellow (with message highlight)
- ERROR:    Bright Red (with message highlight)
- CRITICAL: Bold White on Red Background
"""

import logging
import os
import sys


class ColoredFormatter(logging.Formatter):
    """Logging Formatter that adds ANSI colors to log levels, logger names, and messages."""

    # ANSI Colors
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GRAY = "\033[90m"
    PURPLE = "\033[95m"

    COLORS = {
        "DEBUG": "\033[96m",       # Bright Cyan
        "INFO": "\033[92m",        # Bright Green
        "WARNING": "\033[93m",     # Bright Yellow
        "ERROR": "\033[91m",       # Bright Red
        "CRITICAL": "\033[97;41m", # Bold White on Red
    }

    def __init__(self, fmt: str = None, datefmt: str = "%Y-%m-%d %H:%M:%S", use_colors: bool = None):
        super().__init__(fmt=fmt, datefmt=datefmt)
        if use_colors is None:
            # Auto-detect TTY or forced color env var
            self.use_colors = sys.stdout.isatty() or os.getenv("FORCE_COLOR", "1") == "1"
        else:
            self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        if not self.use_colors:
            return super().format(record)

        color = self.COLORS.get(record.levelname, self.RESET)
        # Highlight messages for WARNING, ERROR, and CRITICAL
        msg_color = color if record.levelno >= logging.WARNING else self.RESET

        log_fmt = (
            f"{self.GRAY}%(asctime)s{self.RESET} "
            f"[{color}{self.BOLD}%(levelname)-7s{self.RESET}] "
            f"{self.PURPLE}%(name)s{self.RESET}: "
            f"{msg_color}%(message)s{self.RESET}"
        )

        formatter = logging.Formatter(log_fmt, datefmt=self.datefmt)
        return formatter.format(record)


def setup_colored_logging(level: int = logging.INFO, name: str = None) -> logging.Logger:
    """Configure the root logger with the ColoredFormatter and return the requested logger.

    Args:
        level: Minimum log level (default: logging.INFO)
        name: Name of the logger to return (default: root logger)

    Returns:
        Configured logging.Logger instance
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers if setup is called multiple times
    for existing_handler in list(root.handlers):
        root.removeHandler(existing_handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColoredFormatter())
    root.addHandler(handler)

    # Re-apply colored formatter to uvicorn loggers if present
    for uvicorn_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        u_logger = logging.getLogger(uvicorn_name)
        u_logger.handlers = [handler]
        u_logger.propagate = False

    return logging.getLogger(name) if name else root

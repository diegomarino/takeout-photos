"""
Logging configuration for the takeout_photos pipeline.

Provides centralized logging setup with file and console handlers.
"""

from __future__ import annotations

import logging
from datetime import datetime

from takeout_photos.core.config import Config


def setup_logging(config: Config) -> tuple[logging.Logger, str]:
    """
    Configure logging to both file and console.

    Creates a timestamped log file in the logs/ directory and configures
    console output. Log level is DEBUG if verbose mode is enabled, otherwise INFO.

    Args:
        config: Pipeline configuration containing logs_dir and verbose settings

    Returns:
        Tuple of (logger, run_timestamp) where run_timestamp is "YYYYMMDD_HHMMSS"

    Side effects:
        - Creates logs_dir if it doesn't exist
        - Creates timestamped log file
        - Configures root logger with file and console handlers

    Example:
        >>> from takeout_photos.core.config import Config
        >>> from takeout_photos.utils.logging_setup import setup_logging
        >>> config = Config(workdir="/path/to/work", verbose=True)
        >>> log, timestamp = setup_logging(config)
        >>> log.info("Pipeline started")
    """
    assert config.logs_dir is not None
    config.logs_dir.mkdir(parents=True, exist_ok=True)

    # Generate timestamp once for all log files in this run
    run_timestamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    log_file = config.logs_dir / f"{run_timestamp}_run.log"

    handlers: list[logging.Handler] = [
        logging.FileHandler(log_file),
        logging.StreamHandler(),
    ]

    logging.basicConfig(
        level=logging.DEBUG if config.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )

    return logging.getLogger(__name__), run_timestamp

__author__ = 'Brian Bason'

from logging import StreamHandler, Formatter
import logging


# create the default handler
default_handler = StreamHandler()
default_handler.setFormatter(
    fmt=Formatter(
        fmt="%(asctime)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
)

# create the handler for the container console
container_console_handler = StreamHandler()
container_console_handler.setFormatter(
    fmt=Formatter(
        fmt="%(message)s",
    )
)

# set the root logger
root_logger = logging.getLogger()
root_logger.addHandler(default_handler)
root_logger.setLevel(logging.WARN)

# set the logger for the builder
docker_build_logger = logging.getLogger("docker_build")
docker_build_logger.setLevel(logging.INFO)

# set the logger for the container console output
container_console_logger = logging.getLogger("container_console")
container_console_logger.setLevel(logging.INFO)
container_console_logger.addHandler(container_console_handler)
container_console_logger.propagate = 0

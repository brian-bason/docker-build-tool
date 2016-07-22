__author__ = 'Brian Bason'

from logging import StreamHandler, Formatter
import logging


# create the default handler
handler = StreamHandler()
handler.setFormatter(
    fmt=Formatter(
        fmt="%(asctime)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
)

# set the root logger
root_logger = logging.getLogger()
root_logger.addHandler(handler)
root_logger.setLevel(logging.WARN)

# set the logger for the builder
docker_build_logger = logging.getLogger("docker_build")
docker_build_logger.setLevel(logging.INFO)
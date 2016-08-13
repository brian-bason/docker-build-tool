"""
Defines the different enumerations that are required by the Docker Build tool
"""

import types

from enum import Enum
from docker_build.util import convert_to_list


class Configuration(Enum):
    """
    Details of a configuration used to set a Docker image
    """
    CMD = ("Cmd", [types.ListType, types.StringType, types.NoneType])
    ENTRYPOINT = ("Entrypoint", [types.ListType, types.StringType, types.NoneType])
    ENV = ("Env", [types.DictType], convert_to_list)
    EXPOSE = ("ExposedPorts", [types.DictType])
    LABELS = ("Labels", [types.DictType])
    ONBUILD = ("OnBuild", [types.ListType])
    USER = ("User", [types.StringType])
    VOLUMES = ("Volumes", [types.ListType])
    WORKDIR = ("WorkingDir", [types.StringType])
    STOPSIGNAL = ("StopSignal", [types.StringType])

    def __init__(self, docker_command, supported_types, conversion_fn=None):
        self.docker_command = docker_command
        self.supported_types = supported_types
        self.conversion_fn = conversion_fn

    def validate_value(self, value):
        if type(value) not in self.supported_types:
            raise TypeError(
                "Configuration {!r} value is not valid, type should be one of {!r}".format(
                    self.name,
                    self.supported_types
                )
            )

    def convert_value(self, value):
        return self.conversion_fn(value) if self.conversion_fn else value

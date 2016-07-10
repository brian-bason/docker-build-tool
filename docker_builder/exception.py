"""
The exceptions that can be raised by the build tool
"""


class DockerBuilderException(Exception):
    """
    Base Class for the Docker Builder
    """
    pass


class DockerBuilderConfigFileNotFound(DockerBuilderException):
    """
    Raised if the Docker Builder configuration file is not found
    """
    pass


class InvalidDockerBuilderConfigFile(DockerBuilderException):
    """
    Raised if the given Docker Builder configuration file is invalid
    """
    pass


class DockerBuilderFileNotFound(DockerBuilderException):
    """
    Raised if the Docker Builder file is not found
    """
    pass


class InvalidDockerBuilderFile(DockerBuilderException):
    """
    Raised if the given Docker Builder file is invalid
    """
    pass


class InvalidDockerBuildOptionValue(InvalidDockerBuilderFile):
    """
    Raised if the given Docker Build file contains an invalid option value
    """
    pass


class MissingDockerBuilderArgument(DockerBuilderException):
    """
    Raised if a build argument is not optional and is not passed to the build tool
    """
    pass


class CommandExecutionError(DockerBuilderException):
    """
    Raised if the execution of a command in a Docker Container failed due to some error
    """
    pass

"""
The exceptions that can be raised by the build tool
"""


class DockerBuildException(Exception):
    """
    Base Class for the Docker Build
    """
    pass


class DockerBuildConfigFileNotFound(DockerBuildException):
    """
    Raised if the Docker Build configuration file is not found
    """
    pass


class InvalidDockerBuildConfigFile(DockerBuildException):
    """
    Raised if the given Docker Build configuration file is invalid
    """
    pass


class DockerBuildFileNotFound(DockerBuildException):
    """
    Raised if the Docker Build file is not found
    """
    pass


class InvalidDockerBuildFile(DockerBuildException):
    """
    Raised if the given Docker Build file is invalid
    """
    pass


class InvalidDockerBuildOptionValue(InvalidDockerBuildFile):
    """
    Raised if the given Docker Build file contains an invalid option value
    """
    pass


class MissingDockerBuildArgument(DockerBuildException):
    """
    Raised if a build argument is not optional and is not passed to the build tool
    """
    pass


class InvalidDockerBuildArgumentValue(DockerBuildException):
    """
    Raised if an invalid value was specified for a build argument
    """
    pass


class CommandExecutionError(DockerBuildException):
    """
    Raised if the execution of a command in a Docker Container failed due to some error
    """
    pass


class DockerImageNotFound(DockerBuildException):
    """
    Raised if the Docker Image to be used as the base image for a build could not be found locally
    and on the remote Docker Registry
    """
    pass

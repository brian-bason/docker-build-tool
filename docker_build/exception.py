"""
The exceptions that can be raised by the build tool
"""


class DockerBuildException(Exception):
    """
    The base class for any application exception raised in the application
    """
    pass


class DockerBuildIOError(IOError):
    """
    The base class for any IO error raised in the application
    """
    pass


class InvalidDockerBuildOptionValue(DockerBuildException):
    """
    Raised if the given Docker build file contains an invalid option value
    """
    pass


class CommandExecutionError(DockerBuildException):
    """
    Raised if the execution of a command in a Docker container failed due to some error
    """
    pass


class DockerImageNotFound(DockerBuildException):
    """
    Raised if the Docker image to be used as the base image for a build could not be found locally
    and on the remote Docker registry
    """
    pass


class SourcePathNotFound(DockerBuildIOError):
    """
    Raised if the given source for a copy operation to a Docker container is not found
    """
    pass

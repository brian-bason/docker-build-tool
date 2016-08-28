"""
The exceptions that can be raised by the build tool
"""


class DockerBuildException(Exception):
    """
    Base Class for the Docker Build
    """
    pass


class InvalidDockerBuildOptionValue(DockerBuildException):
    """
    Raised if the given Docker Build file contains an invalid option value
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

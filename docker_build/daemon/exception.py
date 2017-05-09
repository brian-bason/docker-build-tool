"""
The exceptions that can be raised due to errors with the daemon
"""
from docker_build.exception import \
    DockerBuildIOError, \
    DockerBuildException


class DockerDaemonConnectionException(DockerBuildIOError):
    """
    The exception that should be raised if the connection to the docker daemon could not be 
    established
    """
    pass


class DockerDaemonRequestException(DockerBuildException):
    """
    The exception that should be raised if a request to the docker daemon fails to complete
    """
    pass

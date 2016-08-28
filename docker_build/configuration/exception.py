from docker_build.exception import DockerBuildException


class InvalidMainConfigurations(DockerBuildException):
    """
    Raised if the given main configurations are invalid
    """
    pass


class InvalidBuildConfigurations(DockerBuildException):
    """
    Raised if the given build configurations are invalid
    """
    pass


class MissingArgument(DockerBuildException):
    """
    Raised if an argument is required and is not passed to the build tool
    """
    pass


class InvalidArgumentValue(DockerBuildException):
    """
    Raised if an invalid value was specified for an argument
    """
    pass
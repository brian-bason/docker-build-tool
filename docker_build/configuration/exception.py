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


class InvalidArgumentMapping(DockerBuildException):
    """
    Raised if an invalid mapping for an argument is defined
    """
    pass


class InvalidArgumentReference(DockerBuildException):
    """
    Raised if an invalid reference is made to an argument in a build file
    """
    pass


class InvalidFunctionReference(DockerBuildException):
    """
    Raised if an invalid reference is made to a function in a build file
    """
    pass


class FunctionExecutionError(DockerBuildException):
    """
    Raised if an error is encountered when a build in function is executed
    """
    pass

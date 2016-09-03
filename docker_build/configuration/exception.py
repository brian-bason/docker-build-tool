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


class InvalidVariableReference(DockerBuildException):
    """
    Raised if an invalid reference is made to a variable in a build file
    """
    def __init__(self, message, variable_name):
        super(InvalidVariableReference, self).__init__(message)
        self._variable_name = variable_name

    @property
    def variable_name(self):
        return self._variable_name


class InvalidFunctionReference(DockerBuildException):
    """
    Raised if an invalid reference is made to a function in a build file
    """
    def __init__(self, message, function_name):
        super(InvalidFunctionReference, self).__init__(message)
        self._function_name = function_name

    @property
    def function_name(self):
        return self._function_name


class FunctionExecutionError(DockerBuildException):
    """
    Raised if an error is encountered when a build in function is executed
    """
    def __init__(self, message, function_name, cause):
        super(FunctionExecutionError, self).__init__(message)
        self._function_name = function_name
        self._cause = cause

    @property
    def function_name(self):
        return self._function_name

    @property
    def cause(self):
        return self._cause
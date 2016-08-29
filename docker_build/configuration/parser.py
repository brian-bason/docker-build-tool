import re

from string import Formatter
from exception import \
    InvalidArgumentReference, \
    InvalidFunctionReference, \
    FunctionExecutionError


# the list of functions that can be used in the configuration
Functions = {
    "lower": lambda value: str(value).lower(),
    "upper": lambda value: str(value).upper(),
    "capitalise": lambda value: str(value).capitalize()
}


class ConfigurationParser():

    def __init__(self):
        self._parser = Formatter()

    @staticmethod
    def parse(configurations, build_arguments=None):
        """
        Parses the given configuration to evaluate all the found arguments and functions. All the
        found arguments will be replaced with the value of that argument. All functions will be
        evaluated and the result to the evaluation will be used to replace the referenced function

        :param configurations: The configuration that is to be parsed
        :param build_arguments: The list of known build arguments

        :return: The parsed configuration with all the arguments and functions evaluated

        :type configurations: str
        :type build_arguments: dict

        :rtype: str
        """
        if not configurations:
            raise ValueError("Configurations must be specified and cannot be None")

        parser = Formatter()
        arguments = build_arguments or {}
        parsed_configuration = []

        # start formatting the configuration. For the scope of the first version of the parser the
        # format
        for literal_text, expression, format_spec, conv_spec in parser.parse(configurations):

            # no need to do anything to the literal text, copy as is
            parsed_configuration.append(literal_text)

            # if any expression is specified try to evaluate it
            if expression:
                # append to the resulting configuration to be concatenated at the end
                parsed_configuration.append(
                    ConfigurationParser._evaluate_expression(
                        parser, expression, arguments, format_spec, conv_spec
                    )
                )

        # concatenate the parsed configuration and return, all done
        return "".join(parsed_configuration)

    @staticmethod
    def _evaluate_expression(parser, expression, arguments, format_spec=None, conv_spec=None):
        """
        Evaluates the expression that was given. The expression can be either an argument or a
        function. The expression is evaluated and the value of which returned.

        :param expression: The expression that is to be evaluated
        :param arguments: The list of arguments that is being used for the build process
        :param format_spec: The format spec that should be used on the result of the evaluated
            expression. Optional
        :param conv_spec: The conversion spec that should be used on the result of the evaluated
            expression. Optional

        :return: The result of the expression

        :type expression: str
        :type arguments: dict
        :type format_spec: str
        :type conv_spec: str

        :rtype: str
        """

        function_details = re.match("^([a-zA-Z0-9_-]+)\((.+)\)", expression)

        if function_details:
            # execute the function
            value = ConfigurationParser._execute_function(
                name=function_details.groups()[0],
                parameters=function_details.groups()[1],
                arguments=arguments
            )
        else:
            try:
                # parse the argument
                value, not_req = parser.get_field(
                    field_name=expression,
                    args=None,
                    kwargs=arguments
                )
            except KeyError:
                raise InvalidArgumentReference(
                    "Referenced argument {!r} does not exist, please make sure that the "
                    "correct spelling is used or declare the argument".format(expression)
                )

        # format the value if formatting was specified
        if format_spec:
            value = parser.format_field(value, format_spec)

        # convert the value if a conversion spec was specified
        if conv_spec:
            value = parser.convert_field(value, conv_spec)

        return value

    @staticmethod
    def _execute_function(name, parameters, arguments):
        """
        Executes the function and returns the value for the evaluation

        :param name: The name of the function to be executed
        :param parameters: The parameters as a comma separated list
        :param arguments: The list of arguments that is being used for the build process

        :return: The result of executing the function

        :type name: str
        :type parameters: str
        :type arguments: dict

        :rtype: str

        :raises InvalidFunctionReference: Raised if the given name of the function is not known the
            the build tool
        """

        # confirm if the function exists
        if name not in Functions:
            raise InvalidFunctionReference(
                "Referenced function {!r} is not valid, please make sure that the "
                "correct spelling is used".format(name)
            )

        # parse the parameters and evaluate any arguments or functions
        parameter_list = ConfigurationParser.parse(parameters, arguments).split(",")

        try:

            # run the function
            return Functions[name](*parameter_list)

        except TypeError as ex:
            raise FunctionExecutionError(
                "Execution of function {!r} failed due to error: {!s}".format(name, ex)
            )

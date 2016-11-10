import re

from string import Formatter
from exception import \
    InvalidVariableReference, \
    InvalidFunctionReference, \
    FunctionExecutionError


# the list of functions that can be used in the configuration
FUNCTIONS = {
    "lower": lambda value: str(value).lower(),
    "upper": lambda value: str(value).upper(),
    "capitalise": lambda value: str(value).title()
}


class ConfigurationParser():

    def __init__(self):
        self._parser = Formatter()

    @staticmethod
    def parse(configuration, properties=None):
        """
        Parses the given configuration to evaluate all the found variables and functions. All the
        found variables will be replaced with the value of that variable. All functions will be
        evaluated and the result to the evaluation will be used to replace the referenced function

        :param configuration: The configuration that is to be parsed
        :param properties: The list of known properties for the build

        :return: The parsed configuration with all the variables and functions evaluated

        :type configuration: str
        :type properties: dict

        :rtype: str or list or dict

        :raises ValueError: Raised if the configuration is not specified
        :raises InvalidVariableReference: Raised if any of the variables specified in the config is
            not one of the defined variables for the build
        :raises InvalidFunctionReference: Raised if any of the functions specified in the config is
            not one of the built-in functions in the tool
        :raises FunctionExecutionError: Raised if any of the functions specified ends in an error
            while it is being executed
        """
        if not configuration:
            raise ValueError("Configuration must be specified and cannot be None")

        parser = Formatter()
        properties = properties or {}
        parsed_configuration = []

        # start formatting the configuration. For the scope of the first version of the parser the
        # format
        for literal_text, expression, format_spec, conv_spec in parser.parse(configuration):

            # no need to do anything to the literal text, copy as is
            if literal_text:
                parsed_configuration.append(literal_text)

            # if any expression is specified try to evaluate it
            if expression:
                # append to the resulting configuration to be concatenated at the end
                parsed_configuration.append(
                    ConfigurationParser._evaluate_expression(
                        parser, expression, properties, format_spec, conv_spec
                    )
                )

        # concatenate the parsed configuration and return, all done
        return parsed_configuration[0] \
            if len(parsed_configuration) == 1 else "".join(parsed_configuration)

    @staticmethod
    def _evaluate_expression(parser, expression, properties, format_spec=None, conv_spec=None):
        """
        Evaluates the expression that was given. The expression can be either an argument or a
        function. The expression is evaluated and the value of which returned.

        :param expression: The expression that is to be evaluated
        :param properties: The list of properties that is being used for the build
        :param format_spec: The format spec that should be used on the result of the evaluated
            expression. Optional
        :param conv_spec: The conversion spec that should be used on the result of the evaluated
            expression. Optional

        :return: The result of the expression

        :type expression: str
        :type properties: dict
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
                properties=properties
            )

        else:

            try:

                # parse the variable
                value, not_req = parser.get_field(
                    field_name=expression,
                    args=None,
                    kwargs=properties
                )

            except KeyError:
                raise InvalidVariableReference(
                    "Referenced variable {!r} does not exist".format(expression),
                    expression
                )

        # format the value if formatting was specified
        if format_spec:
            value = parser.format_field(value, format_spec)

        # convert the value if a conversion spec was specified
        if conv_spec:
            value = parser.convert_field(value, conv_spec)

        return value

    @staticmethod
    def _execute_function(name, parameters, properties):
        """
        Executes the function and returns the value for the evaluation

        :param name: The name of the function to be executed
        :param parameters: The parameters as a comma separated list
        :param properties: The list of properties that is being used for the build

        :return: The result of executing the function

        :type name: str
        :type parameters: str
        :type properties: dict

        :rtype: str

        :raises InvalidFunctionReference: Raised if the given name of the function is not known the
            the build tool
        """

        # confirm if the function exists
        if name not in FUNCTIONS:
            raise InvalidFunctionReference(
                "Referenced function {!r} is not valid".format(name),
                name
            )

        # parse the parameters and evaluate any arguments or functions
        parameter_list = ConfigurationParser.parse(parameters, properties).split(",")

        try:
            # run the function
            return FUNCTIONS[name](*parameter_list)
        except Exception as ex:
            raise FunctionExecutionError(
                "Execution of function {!r} failed".format(name),
                name,
                ex
            )

import copy

import yaml
from docker_build.constants import BUILD_CONTEXT_DST_PATH
from docker_build.configuration.encoder import decode_argument_value
from docker_build.configuration.exception import \
    InvalidMainConfigurations, \
    InvalidBuildConfigurations, \
    MissingArgument, \
    InvalidArgumentValue, \
    InvalidArgumentMapping, \
    InvalidVariableReference, \
    InvalidFunctionReference, \
    FunctionExecutionError
from docker_build.configuration.parser import ConfigurationParser, FUNCTIONS
from yaml.parser import ParserError


class MainConfig(object):
    """
    The main configurations for a Docker build
    """

    def __init__(self, config=None):
        self._config = MainConfig._parse(config) if config else None
        self._arguments = self._read_arguments()

    @property
    def arguments(self):
        """
        The list of arguments that have been loaded from the configurations

        :rtype: dict
        """
        return self._arguments

    @staticmethod
    def _parse(config):

        try:
            return yaml.load(config)
        except ParserError as ex:
            raise InvalidMainConfigurations(
                "Main configuration is invalid, parsing failed with error {!r} at {!r}".format(
                    ex.problem,
                    str(ex.problem_mark)
                )
            )

    def _read_arguments(self):
        """
        Reads the arguments from the build tool configurations. These are common configurations that
        are used across all builds

        :return: The list of arguments that have been found in the configurations
        :rtype: dict
        """
        arguments = {}

        if self._config and "ARGS" in self._config:

            try:

                # read all the arguments
                for name, attributes in self._config["ARGS"].items():
                    try:

                        value = attributes["VALUE"]
                        is_encrypted = "ENCRYPTED" in attributes and attributes["ENCRYPTED"]
                        arguments[name] = \
                            decode_argument_value(name, value) if is_encrypted else value

                    except KeyError as ex:
                        raise InvalidMainConfigurations(
                            "Argument {!r} is not properly configured, attribute {!s} is missing"
                            .format(name, ex)
                        )

            except Exception as ex:
                raise InvalidMainConfigurations(
                    "Main configuration contains invalid argument declaration, parsing of "
                    "configurations failed with error - {!s}".format(ex)
                )

        return arguments


class BuildConfig(object):
    """
    The build config containing instructions of a particular build that is to be performed

    :param config: The configuration of a build as loaded from the source
    :param build_arguments: The list of arguments as specified for the build

    :type config: str
    :type build_arguments: dict
    """

    def __init__(self, config, build_arguments=None):

        if not config:
            raise ValueError("Configuration must be specified and cannot be None")

        # parse the build file and build a list of all possible variables
        parsed_config = BuildConfig._parse(config)
        self._variables = BuildConfig._load_variables(parsed_config, build_arguments or {})

        # evaluate all the variables defined in the build config
        BuildConfig._evaluate_variables(parsed_config, self._variables)
        self._config = parsed_config

    @property
    def config(self):
        return self._config

    @property
    def variables(self):
        return self._variables

    @staticmethod
    def _parse(config):

        try:
            return yaml.load(config)
        except ParserError as ex:
            raise InvalidBuildConfigurations(
                "Build configuration is invalid, parsing failed with error {!r} at {!r}".format(
                    ex.problem,
                    str(ex.problem_mark)
                )
            )

    @staticmethod
    def _load_variables(config, build_arguments):

        # the list of variables that are loaded from the list of arguments for the build
        variables = copy.deepcopy(build_arguments)

        if "ARGS" in config:

            try:

                # read all the arguments
                for name, attributes in config["ARGS"].items():

                    # if an argument is set as required confirm that the value for the argument is
                    # known. if on the other hand the argument is optional confirm that a default
                    # was given
                    if "REQUIRED" in attributes and attributes["REQUIRED"]:
                        if name not in variables:
                            raise MissingArgument(
                                "Build argument {!r} is required but no value was passed in for "
                                "the argument".format(name)
                            )
                    else:
                        if "DEFAULT" not in attributes:
                            raise MissingArgument(
                                "Build argument {!r} is required but no default value is specified"
                                .format(name)
                            )

                    # populate the default for the argument if it was not passed
                    if "DEFAULT" in attributes and name not in variables:
                        variables[name] = attributes["DEFAULT"]

                    # confirm that the right value was given for the argument
                    if "CHOICES" in attributes and name in variables:
                        if variables[name] not in attributes["CHOICES"]:
                            raise InvalidArgumentValue(
                                "Value {value!r} for build argument {name!r} is invalid, supported "
                                "values are {choices!r}".format(
                                    value=variables[name],
                                    name=name,
                                    choices=attributes["CHOICES"]
                                )
                            )

                    # confirm if there are any other variables to be loaded
                    if "MAPPINGS" in attributes:

                        for index, mapping in enumerate(attributes["MAPPINGS"]):

                            if "NAME" not in mapping:
                                raise InvalidArgumentMapping(
                                    "Mapping [{mapping_index}] for build argument {argument_name!r}"
                                    " is invalid, mapping should contain NAME attribute".format(
                                        mapping_index=index,
                                        argument_name=name
                                    )
                                )

                            mapping_name = mapping["NAME"]

                            if "VALUES" not in mapping:
                                raise InvalidArgumentMapping(
                                    "Mapping {mapping_name!r} for build argument {argument_name!r} "
                                    "is invalid, mapping should contain VALUES attribute".format(
                                        mapping_name=mapping_name,
                                        argument_name=name
                                    )
                                )

                            argument_value = variables[name]
                            mapping_values = mapping["VALUES"]
                            mapping_default = mapping["DEFAULT"] if "DEFAULT" in mapping else None

                            if argument_value not in mapping_values and mapping_default is None:
                                raise InvalidArgumentMapping(
                                    "Mapping {mapping_name!r} for argument {argument_name!r} does "
                                    "not contain mapping for value {value!r} and no default value "
                                    "specified either".format(
                                        mapping_name=mapping_name,
                                        argument_name=name,
                                        value=argument_value
                                    )
                                )

                            # add the new variable to the list of build arguments
                            variables[mapping_name] = mapping_values[argument_value] \
                                if argument_value in mapping_values else mapping_default

            except Exception as ex:
                raise InvalidBuildConfigurations(
                    "Build configurations contains invalid argument declaration, parsing of "
                    "details failed with error - {!s}".format(
                        ex
                    )
                )

        # inject the build context path (path inside the container) that can be used for
        # reference during the build process
        variables["BUILD_CONTEXT_PATH"] = BUILD_CONTEXT_DST_PATH

        return variables

    @staticmethod
    def _evaluate_variables(config_section, variables, parent_key=None):
        """
        Evaluates the variables defined in the build configuration section that is being evaluated

        :param config_section: The part of the configuration that is being evaluated
        :param variables: The list of variables that are known for the build
        :param parent_key: The key to the parent attribute

        :type config_section: dict or list
        :type variables: dict
        :type parent_key: str or None

        :raises InvalidBuildConfigurations: If any of the configurations contains any error
        """

        # iterate through the attributes of the build config section that is being processed. The
        # build config can either be a dictionary or a list so the iteration can be going through
        # either the key of the dictionary or the item itself in the list.
        for index, key_or_item in enumerate(config_section):

            # if the config section that is being evaluated is the arguments themselves skip them
            # there is no need to evaluate that section
            if key_or_item == "ARGS" and not parent_key:
                continue

            key_or_index = index if isinstance(config_section, list) else key_or_item
            current_config_section = config_section[key_or_index]
            # creates a key in the format of level1.level2
            current_parent_key = "{}{}{}{}".format(
                parent_key if parent_key else "",
                "" if not parent_key else "." if isinstance(config_section, dict) else "[",
                key_or_item if isinstance(config_section, dict) else index + 1,
                "" if not parent_key or isinstance(config_section, dict) else "]"
            )

            if isinstance(current_config_section, dict) or isinstance(current_config_section, list):

                # if the current configuration section being evaluated has more attributes evaluate
                # its attributes too.
                BuildConfig._evaluate_variables(
                    current_config_section, variables, current_parent_key
                )

            else:

                try:

                    # parse the details of the attribute
                    if current_config_section:
                        parsed_item = ConfigurationParser.parse(current_config_section, variables)
                        config_section[key_or_index] = parsed_item

                except InvalidVariableReference as ex:
                    raise InvalidBuildConfigurations(
                        "Build configuration is invalid. Attribute {attribute_name!r} contains a "
                        "reference to variable {variable_name!r} that is not defined. Variable has "
                        "to be one of {all_variables_names}".format(
                            attribute_name=current_parent_key,
                            variable_name=ex.variable_name,
                            all_variables_names=variables.keys()
                        )
                    )

                except InvalidFunctionReference as ex:
                    raise InvalidBuildConfigurations(
                        "Build configuration is invalid. Attribute {attribute_name!r} contains a "
                        "reference to a function {function_name!r} that is not known. Function has "
                        "to be one of {all_function_names}".format(
                            attribute_name=current_parent_key,
                            function_name=ex.function_name,
                            all_function_names=FUNCTIONS.keys()
                        )
                    )

                except FunctionExecutionError as ex:
                    raise InvalidBuildConfigurations(
                        "Build configuration is invalid. Attribute {attribute_name!r} contains a "
                        "reference to function {function_name!r} that failed with error: {error!r}"
                        .format(
                            attribute_name=current_parent_key,
                            function_name=ex.function_name,
                            error=ex.cause
                        )
                    )

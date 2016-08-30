import copy

import yaml
from docker_build.constants import BUILD_CONTEXT_DST_PATH
from docker_build.configuration.encoder import decode_argument_value
from docker_build.configuration.exception import \
    InvalidMainConfigurations, \
    InvalidBuildConfigurations, \
    MissingArgument, \
    InvalidArgumentValue
from docker_build.configuration.parser import ConfigurationParser
from yaml.parser import ParserError


class MainConfig(object):
    """
    The main configurations for a Docker build
    """

    def __init__(self, config=None):
        self._config = config

        self._parsed_config = self._parse() if config else None
        self._arguments = self._read_arguments()

    @property
    def arguments(self):
        """
        The list of arguments that have been loaded from the configurations

        :rtype: dict
        """
        return self._arguments

    def _parse(self):

        try:

            return yaml.load(self._config)

        except ParserError as ex:
            raise InvalidMainConfigurations(
                "Main configurations are invalid. Configurations parsing failed with "
                "error {!r} at {!r}"
                .format(
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
                for name, attributes in self._parsed_config["ARGS"].items():
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
                    "Main configurations contains invalid argument declaration, parsing of "
                    "configurations failed with error - {!s}".format(ex)
                )

        return arguments


class BuildConfig(object):
    """
    The build config containing instructions of a particular build that is to be performed

    :param build_details: The details of a build as loaded from the source
    :param build_arguments: The list of arguments as specified for the build

    :type build_details: str
    :type build_arguments: dict
    """

    def __init__(self, build_details, build_arguments=None):

        if not build_details:
            raise ValueError("Build details must be specified and cannot be None")

        self._build_details = build_details

        # parse the build file and read the arguments
        self._parsed_build_details = self._parse()
        self._build_arguments = self._read_arguments(build_arguments or {})

        # reload the build file populating the build arguments
        self._parsed_build_details = self._parse()

    @property
    def build_details(self):
        return self._parsed_build_details

    def _parse(self):

        build_details = copy.copy(self._build_details)

        try:

            if hasattr(self, "_build_arguments") and self._build_arguments:
                build_details = ConfigurationParser.parse(build_details, self._build_arguments)

            return yaml.load(build_details)

        except KeyError as ex:
            raise InvalidBuildConfigurations(
                "Build configurations are invalid. Argument {!r} is not defined".format(
                    ex.message
                )
            )

        except ParserError as ex:
            raise InvalidBuildConfigurations(
                "Build configurations are invalid. Details failed with error {!r} at {!r}".format(
                    ex.problem,
                    str(ex.problem_mark)
                )
            )

    def _read_arguments(self, build_arguments):

        # the list of arguments that are loaded from the config and from the passed in arguments
        # during the build
        arguments = copy.deepcopy(build_arguments)

        if "ARGS" in self._parsed_build_details:

            try:

                # read all the arguments
                for name, attributes in self._parsed_build_details["ARGS"].items():

                    # if an argument is set as required confirm that the value for the argument is
                    # known. if on the other hand the argument is optional confirm that a default
                    # was given
                    if "REQUIRED" in attributes and attributes["REQUIRED"]:
                        if name not in arguments:
                            raise MissingArgument(
                                "Build argument {!r} is not optional but no value was passed in "
                                "for the argument".format(name)
                            )
                    else:
                        if "DEFAULT" not in attributes:
                            raise MissingArgument(
                                "Build argument {!r} is optional but no default value is specified"
                                .format(name)
                            )

                    # populate the default for the argument if it was not passed
                    if "DEFAULT" in attributes and name not in arguments:
                        arguments[name] = attributes["DEFAULT"]

                    # confirm that the right value was given for the argument
                    if "CHOICES" in attributes and name in arguments:
                        if arguments[name] not in attributes["CHOICES"]:
                            raise InvalidArgumentValue(
                                "Value {value!r} for build argument {name!r} is invalid, supported "
                                "values are {choices!r}".format(
                                    value=arguments[name],
                                    name=name,
                                    choices=attributes["CHOICES"]
                                )
                            )

            except Exception as ex:
                raise InvalidBuildConfigurations(
                    "Build configurations contains invalid argument declaration, parsing of "
                    "details failed with error - {!s}".format(
                        ex
                    )
                )

        # inject the build context path (path inside the container) that can be used for
        # reference during the build process
        arguments["BUILD_CONTEXT_PATH"] = BUILD_CONTEXT_DST_PATH

        return arguments

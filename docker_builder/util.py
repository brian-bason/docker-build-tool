"""
Utility functions and classes that can be used across the Docker builder module
"""

import types
import argparse


def convert_to_list(value):
    """
    Converts the given value into a list. If the value is a dictionary the key and value of the
    dictionary will be parsed into a string with the format key=value. Any other type will be
    converted to its string representation and returned as a list

    :param value: The value that is to be converted

    :return: A list for the given value
    """
    if isinstance(value, types.DictType):
        return [
            "{key}={value}".format(key=k, value=v)
            for k, v in value.items()
        ]
    elif isinstance(value, types.ListType):
        return value
    else:
        return [str(value)]


class PutAction(argparse.Action):
    """
    An Arg Parser action class to put given tuple values into a dictionary. The first item of the
    tuple will be used as the key of the dictionary item being added while the second item will be
    used as the value
    """
    def __call__(self, parser, namespace, values, option_string=None):

        if not isinstance(values, tuple):
            raise argparse.ArgumentParser(
                "Value {} must be of type tuple for {}. Make sure that the type being used to parse"
                "the argument returns a tuple".format(
                    values,
                    self.__class__.__name__
                )
            )

        if len(values) != 2:
            raise argparse.ArgumentParser(
                "Value passed to {} must contain 2 values. Found {} instead".format(
                    self.__class__.__name__,
                    len(values)
                )
            )

        attr = getattr(namespace, self.dest) or {}
        attr[values[0]] = values[1]
        setattr(namespace, self.dest, attr)


def parse_key_value_option(option):
    """
    :param option: The option from the command line that is being parsed

    :return: A tuple containing the name and value of the parsed argument

    :type option: str
    :rtype tuple:
    """
    argument_parts = option.split("=")

    if len(argument_parts) != 2:
        raise argparse.ArgumentTypeError(
            "Option {!r} is not valid, option should be in the format NAME=VALUE".format(
                option
            )
        )

    return argument_parts[0], argument_parts[1]

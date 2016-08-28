import base64

from docker_build.configuration.exception import \
    InvalidArgumentValue


def decode_argument_value(name, value):
    """
    Decodes the value of an argument. The value is assumed to be Base64 encoded

    :param name: The name of the argument that is being decoded
    :param value: The encoded value of the argument. It is assumed to be Base64 encoded

    :return: The decoded value of the argument

    :raises ValueError: If either the name or value arguments are not passed
    :raises InvalidDockerBuildArgumentValue: If the value for the argument is invalid

    :type name: str
    :type value: str

    :rtype: str
    """
    if not name:
        raise ValueError("Argument name must be specified and cannot be None")

    if not value:
        raise ValueError("Argument value must be specified and cannot be None")

    try:

        # base64 decode the value of the argument
        # try to encode the argument value after decoding to make sure that the value is
        # valid
        return unicode(base64.b64decode(value), "utf8")

    except TypeError:
        raise InvalidArgumentValue(
            "Argument {!r} is invalid, argument value is not base64 encoded "
            "but argument is marked as obfuscated".format(name)
        )

    except UnicodeDecodeError:
        raise InvalidArgumentValue(
            "Argument {!r} is invalid, argument value is not a valid base64 string. "
            "Please make sure that the string was properly encoded".format(name)
        )

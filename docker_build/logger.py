import logging


class ConsoleLogger():
    """
    Prints the given log messages to a simulated console. What this means is that the messages are
    logged without any dates or other log information.

    :param header: A string that will be printed at the start of the console logs. If specified this
                   will also trigger the insertion of a footer message. (OPTIONAL)

    :type header: str
    """
    _header_line_character = "*"
    _header_line_marker = _header_line_character * 26

    def __init__(self, header=None):
        self._header = header
        self._log = logging.getLogger("container_console")

    def __enter__(self):
        if self._header:
            self._log.info(
                "{line_marker} {header} {line_marker}".format(
                    line_marker=self._header_line_marker,
                    header=self._header
                )
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._header:
            self._log.info(
                "{line_marker}{header}{line_marker}".format(
                    line_marker=self._header_line_marker,
                    header=self._header_line_character * (len(self._header) + 2)
                )
            )

    def log(self, message):
        """
        Logs the message to the simulated console

        :param message: The messages that is to be printed

        :type message: str
        """
        self._log.info(message)

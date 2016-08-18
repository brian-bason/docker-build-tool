import logging


class ConsoleLogger():
    """
    Prints the given log messages to a simulated console. What this means is that the messages are
    logged without any dates or other log information.

    :param is_enabled: Determines if the logger is enabled and if messages should be printed to
                       console
    :param header: A string that will be printed at the start of the console logs. If specified this
                   will also trigger the insertion of a footer message. (OPTIONAL)

    :type is_enabled: bool
    :type header: str
    """
    _header_line_character = "*"
    _header_line_marker = _header_line_character * 26

    def __init__(self, is_enabled=True, header=None):
        self._is_enabled = is_enabled
        self._header = header
        self._log = logging.getLogger("container_console")
        self._buffer = None

    def __enter__(self):
        if self._is_enabled and self._header:
            self._log.info(
                "{line_marker} {header} {line_marker}".format(
                    line_marker=self._header_line_marker,
                    header=self._header
                )
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._is_enabled:
            # print whatever is left in the buffer
            if self._buffer:
                self._log.info(self._buffer)

            # print the footer if a header was specified
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
        if self._is_enabled:

            is_last_message_incomplete = message[-1:] != "\n"

            # split the stream into individual lines, removing any empty lines
            log_lines = (
                self._buffer if self._buffer else "" +
                message if is_last_message_incomplete else message[:-1]
            ).split("\n")

            # if the last log entry is not complete keep it in the buffer for the next iteration
            # of the log print
            if is_last_message_incomplete:
                self._buffer = log_lines[-1]
                del log_lines[-1]
            else:
                self._buffer = None

            for log_line in log_lines:
                self._log.info(log_line)

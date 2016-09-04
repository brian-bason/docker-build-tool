import os

from docker_build.exception import DockerBuildIOError


class FileNotFound(DockerBuildIOError):
    """
    Raised if any of the files required by the the Docker Build tool is not found
    """
    pass


class FileLoader(object):
    """
    Loads the content of a file

    :param path: The path of the file that is to be loaded

    :type path: str

    :raises FileNotFound: If no file is found for the given path
    """
    def __init__(self, path):

        if not path:
            raise ValueError("File path must be specified and cannot be None")

        self._path = os.path.expanduser(path)
        self._content = None

    @property
    def content(self):
        return self._content

    def exists(self):
        return os.path.exists(self._path)

    def load(self):
        """
        Loads the file in memory, to be processed

        :return: The parser itself
        :raises FileNotFound: If the file is not found in the given path

        :rtype: FileLoader
        """
        # load the build file
        self._content = self._read()
        return self

    def _read(self):
        """
        Reads the file and loads it into the memory for parsing

        :return: The content of the build file

        :rtype: str
        """
        # determine if the file exists
        if not self.exists():
            raise FileNotFound(
                "File not found at {!r}, please make sure that the right "
                "path was specified".format(self._path)
            )

        with open(self._path) as build_file:
            return build_file.read()

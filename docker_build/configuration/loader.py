import os

from docker_build.utils.loader import FileLoader

# the default path for the main configuration file
MAIN_CONFIG_FILE_PATH = "~/.docker/build-config.yml"


class MainConfigFileLoader(FileLoader):

    def __init__(self, path=None):
        super(MainConfigFileLoader, self).__init__(
            path=MAIN_CONFIG_FILE_PATH if not path else path
        )

    def load(self):

        # if the main configuration is to be loaded from the default path and no file exists it
        # means that the user did not set any main configurations which is perfectly valid. In that
        # case no main configurations should be loaded.
        if self._path == os.path.expanduser(MAIN_CONFIG_FILE_PATH) and not self.exists():
            return

        return FileLoader.load(self)

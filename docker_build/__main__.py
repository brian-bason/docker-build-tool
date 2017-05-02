"""
Build tool to create Docker images. This is another implementation of the builder different than the
one provided by the official repository. This tool is intended to give the user more flexibility for
the creation of an image as opposed to what is being provided by the build command provided in
docker
"""
import argparse
import logging
import sys
import os
import time

from os import environ
from docker.errors import \
    APIError, \
    DockerException
from docker_build import __version__
from docker_build.exception import \
    DockerBuildException, \
    DockerBuildIOError
from docker_build.configuration.exception import \
    InvalidBuildConfigurations
from docker_build.configuration.loader import FileLoader, MainConfigFileLoader
from docker_build.configuration.model import BuildConfig, MainConfig
from docker_build.constants import BUILD_CONTEXT_DST_PATH
from docker_build.utils.argparser import \
    PutAction, \
    parse_key_value_option
from docker_build.daemon import DockerAPI
from requests.exceptions import \
    RequestException, \
    ConnectionError

# list of environment variables accepted by the build tool
CONNECTION_TIMEOUT = "DOCKER_CONNECTION_TIMEOUT"
IGNORE_CACHE = "DOCKER_BUILD_IGNORE_CACHE"


# the logger for the docker build tool
log = logging.getLogger("docker_build")


def _copy_build_context(docker_api, container, step_config):
    """
    Copies the build context to the running container. The build context can be either one or many
    paths that can be copied into the container
    """

    files_copied = False

    if "BUILDCONTEXT" in step_config:

        log.info("Copying building context to the container")
        files_copied = True

        if isinstance(step_config["BUILDCONTEXT"], str):

            docker_api.copy(
                container,
                step_config["BUILDCONTEXT"],
                os.path.join(BUILD_CONTEXT_DST_PATH, "")
            )

        elif isinstance(step_config["BUILDCONTEXT"], list):

            for copy_details in step_config["BUILDCONTEXT"]:

                dst = ""

                if "DST" in copy_details:
                    dst = "." + copy_details["DST"] if copy_details["DST"].startswith("/") \
                          else copy_details["DST"]

                dst = os.path.join(BUILD_CONTEXT_DST_PATH, dst)

                if not os.path.normpath(dst).startswith(BUILD_CONTEXT_DST_PATH):
                    raise InvalidBuildConfigurations(
                        "Invalid Build Context 'DST' property {!r}, destination path must be "
                        "within the Build Context folder".format(
                            copy_details["DST"]
                        )
                    )

                docker_api.copy(container, copy_details["SRC"], dst)

        else:

            raise InvalidBuildConfigurations(
                "BUILDCONTEXT is invalid, context must be either a String or a List of SRC and DST "
                "objects"
            )

    return files_copied


def _build(
        docker_api, variables, build_config, step_config, from_image, should_ignore_cache,
        should_remove_container):
    """
    Builds the image for the given step

    :param docker_api: The api interface that is to be used to connect to the docker daemon
    :param variables: The list of variables that are known for the build
    :param build_config: The configurations of the entire build
    :param step_config: The configurations of the step being build with this build process
    :param from_image: The identifier or tag of the image to be used as the base for the image being
        created
    :param should_ignore_cache: Determines if the local cache should be ignored when checking if the
        base image exists
    :param should_remove_container: Indicates if the container should be removed on success or
        failure build

    :returns: The identifier of the image that was created

    :type variables: dict
    :type build_config: dict
    :type step_config: dict
    :type from_image: str
    :type should_remove_container: bool
    
    :rtype: str
    """
    container = None

    try:

        # determine which build step is being executed in the build process
        is_first_build_step = step_config == build_config["STEPS"][0]
        is_last_build_step = step_config == build_config["STEPS"][-1]

        # create the container that will be used to run the details for the image
        log.info("Starting new container from {!r}".format(from_image))
        container = docker_api.create_container(
            from_image,
            volumes=step_config.get("VOLUMES", []),
            should_ignore_cache=is_first_build_step and should_ignore_cache
        )

        # determine if there is a build context specified
        build_context_populated = _copy_build_context(docker_api, container, step_config)

        # copy over any files that are required if any specified
        if "COPY" in step_config:
            log.info("Copying folders or files to container")
            for copy_details in step_config["COPY"]:
                docker_api.copy(
                    container,
                    copy_details["SRC"],
                    copy_details["DST"]
                )

        # execute the commands to make the necessary changes
        if "RUN" in step_config:
            log.info("Making necessary changes to the container")
            docker_api.run_command(
                container,
                step_config["RUN"],
                variables=variables,
                show_logs=True
            )

        # clean up the build context if one was created
        if build_context_populated:
            log.info("Cleaning up container from build context")
            docker_api.run_command(
                container,
                "rm -rf {dst}".format(dst=BUILD_CONTEXT_DST_PATH)
            )

        # commit the change done to the container
        log.info("Creating image with container changes")

        # get the configs of the image that was used as the base image
        image = docker_api.get_image(from_image)
        image_configs = image.attrs["Config"]

        # build the configuration that will be set for the image being created
        configs = step_config.get("CONFIG", {})

        # if the command and entry point are not being over written by a specific configuration of
        # the new image being created set the command and / or entry point of the from image. This
        # is being done as the container which was created from (the base images) is overwriting the
        # command and entry point to force the start of shell in the container
        if "CMD" not in configs:
            configs["CMD"] = image_configs["Cmd"] or []

        if "ENTRYPOINT" not in configs:
            configs["ENTRYPOINT"] = image_configs["Entrypoint"]

        image_id = docker_api.commit_image(
            container,
            author=build_config["MAINTAINER"] if "MAINTAINER" in build_config else None,
            configs=configs,
            tag=build_config["TAG"] if is_last_build_step and "TAG" in build_config else None
        )

        log.info("Successfully created image {!r}".format(image_id))

        # return the identifier of the image that was created from this build step
        return image_id

    finally:

        # if a container was created remove it to clean up
        if container and should_remove_container:
            log.info("Removing created container")
            docker_api.remove_container(container)
            log.info("Successfully removed container")


def main(argv=None):
    """
    Main function for invoking the Docker Build tool
    """
    # Parse argument list
    parser = argparse.ArgumentParser(
        description="Build tool for creating Docker images"
    )
    parser.add_argument(
        "-a", "--arg",
        dest="build_args",
        type=parse_key_value_option,
        action=PutAction,
        metavar="NAME=VALUE",
        default={},
        help="Passes the value of an argument that is defined in the build file. The arguments "
             "option can be defined multiple times for each argument that is to be populated with "
             "a value. Passes arguments are expected to be Name/Value pairs separated with an "
             "equals sign"
    )
    parser.add_argument(
        "-b", "--build-config-file",
        dest="build_config_file_path",
        type=str,
        default="./docker-build.yml",
        help="The path to the build configuration file that will be used during the build process. "
             "By default the tool will look for the build configuration file in the current "
             "working directory unless overwritten with the use of this option"
    )
    parser.add_argument(
        "-m", "--main-config-file",
        dest="main_config_file_path",
        type=str,
        help="The path to the main configuration file that will be used during the build process. "
             "By default the tool will look for the main configuration file in the users home "
             "directory under the .docker folder. The default behaviour can be overwritten with "
             "the use of this option"
    )
    parser.add_argument(
        "-t", "--tag",
        dest="tag",
        type=str,
        help="If specified the tag value defined in the build file will be overwritten. The tag "
             "is used to commit the final image that is generated by the build tool. Either the "
             "TAG command or the tag option must be specified"
    )
    parser.add_argument(
        "--connection-timeout",
        dest="connection_timeout",
        type=int,
        default=int(environ.get(CONNECTION_TIMEOUT, 60)),
        help="The maximum amount of seconds to wait before the connection to the docker daemon "
             "times out. This option can also be set with the use of the environment variable {}"
             .format(CONNECTION_TIMEOUT)
    )
    parser.add_argument(
        "--ignore-cache",
        dest="ignore_cache",
        action="store_true",
        default=True if environ.get(IGNORE_CACHE, "0") == "1" else False,
        help="Determines if the local cache of docker images should be ignored when checking for "
             "the base image that is required by the build. If the option is turned on the remote "
             "repository will always be checked for an updated copy of the image even if it exists "
             "in the local cache. This option can also be set with the use of the environment "
             "variable {}"
             .format(IGNORE_CACHE)
    )
    parser.add_argument(
        "--keep",
        dest="keep_containers",
        action="store_true",
        help="Keeps the intermediate containers after a build. The default behaviour is to remove "
             "all created containers but sometimes it is useful to leave them for debugging "
             "purposes"
    )
    parser.add_argument(
        "--verbose",
        dest="verbose",
        action="store_true",
        help="Prints more logs during the build process to give more context of what is happening"
             "in during a build of an Docker image"
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version="docker-build-tool version {}".format(__version__),
        help="Prints the program's version number and exits"
    )

    try:

        # start the timer to find out at the end how long the build took
        start_time = time.time()

        # parse the command line arguments passed to the tool
        command_line_args = parser.parse_args(argv)

        # determine if lower level logging should be enabled
        if command_line_args.verbose:
            log.setLevel(logging.DEBUG)

        # load the configuration file
        config_file = MainConfigFileLoader(command_line_args.main_config_file_path).load()
        main_config = MainConfig(config_file.content if config_file else None)

        # load all the build arguments for the build process
        build_args = dict(
            main_config.arguments.items() + command_line_args.build_args.items()
        )

        # load the build file
        build_config = BuildConfig(
            FileLoader(command_line_args.build_config_file_path).load().content,
            build_args
        )

        # determine from which image to start
        if "FROM" not in build_config.config:
            raise InvalidBuildConfigurations(
                "FROM is not optional please confirm the build file"
            )

        from_image = build_config.config["FROM"]

        # if the tag command line argument was specified update the tag that is set in the build
        # file
        if command_line_args.tag:
            build_config.config["TAG"] = command_line_args.tag

        # change the working directory to the path where the build file is located before commencing
        # the build. This will make sure that all the paths in the build file are relative to the
        # build file itself
        os.chdir(os.path.dirname(command_line_args.build_config_file_path) or ".")

        # create the client to the API
        docker_api = DockerAPI(connection_timeout=command_line_args.connection_timeout)

        # go through the steps to create the necessary images
        for step_config in build_config.config["STEPS"]:
            from_image = _build(
                docker_api,
                build_config.variables,
                build_config.config,
                step_config,
                from_image,
                command_line_args.ignore_cache,
                not command_line_args.keep_containers
            )

        total_build_time = int(time.time() - start_time)
        log.info("Build finished in {} min/s {} sec/s".format(
            int(total_build_time / 60),
            total_build_time % 60
        ))

    except KeyboardInterrupt:
        log.info("Docker Build shutdown by user")
        return 130

    except ConnectionError:
        log.error("Cannot connect to the Docker daemon. Is the docker daemon running on this host?")
        return 1

    except APIError as ex:
        log.error("Build failed due to error : {}".format(ex.explanation))
        return 1

    except (
            RequestException, DockerException, DockerBuildException, DockerBuildIOError
    ) as ex:
        log.error("Build failed due to error : {}".format(ex))
        return 1

    except Exception as ex:
        log.exception("Unexpected error during build due to error : {}".format(ex))
        return 1


if __name__ == '__main__':
    sys.exit(main())

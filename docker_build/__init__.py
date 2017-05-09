import logging
import os

from logging import StreamHandler, Formatter
from docker.errors import \
    APIError, \
    DockerException
from docker_build.configuration.exception import \
    InvalidBuildConfigurations
from docker_build.configuration.loader import FileLoader, MainConfigFileLoader
from docker_build.configuration.model import BuildConfig, MainConfig
from docker_build.constants import BUILD_CONTEXT_DST_PATH
from docker_build.daemon import DockerAPI
from docker_build.daemon.exception import \
    DockerDaemonConnectionException, \
    DockerDaemonRequestException
from requests.exceptions import \
    RequestException, \
    ConnectionError
from docker_build.daemon import \
    DEFAULT_DOCKER_CONNECTION_TIMEOUT, \
    DEFAULT_DOCKER_IGNORE_CACHE


__author__ = "Brian Bason"
__version__ = "0.13.0"

# list of application defaults
DEFAULT_KEEP_CONTAINERS = False

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


def _build_step(
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
        log.info("Creating image from container changes")

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


def build(build_config_file_path, build_arguments=None, **kwargs):
    """
    Builds the docker image from the given build configuration path. The function returns the image
    identifier and tag used for the created image
    
    :param build_config_file_path: The path to the configuration file that is to be used for the
        build
    :param build_arguments: The list of arguments that should be used for the build
    :param kwargs: A list of key value pairs defining additional optional parameters for the build.
        These include
        - config_file_path: The path to the main configurations that should be loaded for the build.
                            By default the configuration file is searched for in the docker folder
                            in the user directory
        - tag: The tag that should be used for the created image. This parameter can be used to
            overwrite the one set in the build configuration
        - connection_timeout: The maximum amount of seconds to wait for a response from the Docker
            daemon before giving up
        - ignore_cache: Determines if the local repository should be ignored when checking for the
            base image being used for the build
        - keep_containers: Determines if the containers created for the build should be kept or
            removed after the build
            
    :return: A tuple containing the image identifier and used tag for the created image
    
    :type build_config_file_path: str
    :type build_arguments: dict
    
    :rtype: tuple
    
    :raises docker_build.exception.DockerBuildIOError: Raised if any IO errors have been encountered
        during the build process. Such IO errors could be from connection issues to the Docker
        daemon that is to be invoked for the build, to not managing to locate the given build file
        in the specified path
    :raises docker_build.exception.DockerBuildException: Raised if any operations to the docker 
        daemon fail to be processed due to some error in the request
    """
    try:

        config_file_path = kwargs.get("config_file_path")
        tag = kwargs.get("tag")
        connection_timeout = \
            kwargs.get("connection_timeout", DEFAULT_DOCKER_CONNECTION_TIMEOUT)
        ignore_cache = kwargs.get("ignore_cache", DEFAULT_DOCKER_IGNORE_CACHE)
        keep_containers = kwargs.get("keep_containers", DEFAULT_KEEP_CONTAINERS)

        # load the configuration file
        config_file = MainConfigFileLoader(config_file_path).load()
        main_config = MainConfig(config_file.content if config_file else None)

        # load all the build arguments for the build process
        build_args = dict(
            main_config.arguments.items() + (build_arguments.items() if build_arguments else [])
        )

        # load the build file
        build_config = BuildConfig(
            FileLoader(build_config_file_path).load().content,
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
        if tag:
            build_config.config["TAG"] = tag

        # change the working directory to the path where the build file is located before commencing
        # the build. This will make sure that all the paths in the build file are relative to the
        # build file itself
        os.chdir(os.path.dirname(build_config_file_path) or ".")

        # create the client to the API
        docker_api = DockerAPI(connection_timeout=connection_timeout)

        # go through the steps to create the necessary images
        for step_config in build_config.config["STEPS"]:
            from_image = _build_step(
                docker_api,
                build_config.variables,
                build_config.config,
                step_config,
                from_image,
                ignore_cache,
                not keep_containers
            )

        # return the identifier and tag of the generated image
        return from_image, build_config.config["TAG"]

    except ConnectionError:
        raise DockerDaemonConnectionException(
            "Cannot connect to the Docker daemon. Is the docker daemon running on this host?"
        )

    except (APIError, DockerException, RequestException) as ex:
        raise DockerDaemonRequestException(
            "Build process failed due to error '{}'".format(
                ex.explanation if isinstance(ex, APIError) else ex
            )
        )


def initialise_logging():
    # create the default handler
    default_handler = StreamHandler()
    default_handler.setFormatter(
        fmt=Formatter(
            fmt="%(message)s"
        )
    )

    # create the handler for the container console
    container_console_handler = StreamHandler()
    container_console_handler.setFormatter(
        fmt=Formatter(
            fmt="%(message)s",
        )
    )

    # set the root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(default_handler)
    root_logger.setLevel(logging.WARN)

    # set the logger for the builder
    docker_build_logger = logging.getLogger("docker_build")
    docker_build_logger.setLevel(logging.INFO)

    # set the logger for the container console output
    container_console_logger = logging.getLogger("container_console")
    container_console_logger.setLevel(logging.INFO)
    container_console_logger.addHandler(container_console_handler)
    container_console_logger.propagate = 0

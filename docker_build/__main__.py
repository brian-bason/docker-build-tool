"""
Build tool to create Docker images. This is another implementation of the builder different than the
one provided by the official repository. This tool is intended to give the user more flexibility for
the creation of an image as opposed to what is being provided by the build command provided in
docker
"""
from __future__ import print_function

import argparse
import json
import logging
import io
import tarfile
import sys
import docker
import types
import os
import time

from docker import errors
from docker_build import __version__
from docker_build.exception import \
    DockerBuildException, \
    DockerBuildIOError, \
    DockerImageNotFound, \
    SourcePathNotFound, \
    InvalidDockerBuildOptionValue, \
    CommandExecutionError
from docker_build.configuration.exception import \
    InvalidBuildConfigurations
from docker_build.configuration.loader import FileLoader, MainConfigFileLoader
from docker_build.configuration.model import BuildConfig, MainConfig
from docker_build.constants import BUILD_CONTEXT_DST_PATH
from docker_build.daemon.catalog import Configuration
from docker_build.utils.argparser import \
    PutAction, \
    parse_key_value_option
from docker_build.utils.logger import ConsoleLogger
from requests.exceptions import RequestException


# the logger for the docker build tool
log = logging.getLogger("docker_build")


def _parse_config(configs, parsed_configs, configuration_option):
    """
    Validates the given configuration and if required converts the configuration from the format
    supported by the Docker Build tool to the one understood by Docker Daemon.
    """
    if configuration_option.name in configs:

        # get the value of the passed in configuration option
        value = configs[configuration_option.name]

        # validate the configuration value
        configuration_option.validate_value(value)

        # convert the value to the one supported by Docker Daemon
        parsed_configs[configuration_option.docker_command] = configuration_option.convert_value(
            value
        )


def _inspect_image(docker_client, image):
    """
    Inspect the details of the image returning back the full details of that image
    """
    details = None

    try:
        details = docker_client.inspect_image(image)
    except errors.NotFound:
        pass

    return details


def _inspect_container(docker_client, container):
    """
    Inspect the details of the container returning back the full details of that container
    """
    details = None

    try:
        details = docker_client.inspect_container(container)
    except errors.NotFound:
        pass

    return details


def _pull_image(docker_client, image_name):
    """
    Pulls the Docker Image from the remote Docker Registry
    """
    status_log = None
    refresh_count = 1
    repository, tag = _get_docker_image_name_parts(image_name)
    params = {
        "repository": repository,
        "tag": tag,
        "stream": True
    }

    for output in docker_client.pull(**params):
        details = json.loads(output)

        if "status" in details:
            if not status_log:
                log.info(details["status"])
            else:
                print("#" * refresh_count, end="\r")
                refresh_count = refresh_count + 1 if refresh_count <= 50 else 1

            status_log = details["status"]

        if "error" in details:
            raise DockerImageNotFound(details["error"])

    print("", end="\r")
    log.info(status_log)


def _create_container(docker_client, image):
    """
    Create a container that will be used to execute the commands and create the new required image.
    The image will be created and started.
    """

    # the list of parameters that will be passed to the docker command
    params = {
        "tty": True,
        "detach": True,
        "command": "/bin/sh",
        "image": image
    }

    # if the image that the container is being started from has an entry point overwrite it to clear
    # the entry point
    details = _inspect_image(docker_client, image)
    if details and details["Config"]["Entrypoint"]:
        params["entrypoint"] = []

    def create_container_with_auto_pull(remote_download_tried=False):
        # create the container that will be used to run the details for the image
        try:
            return docker_client.create_container(**params)
        except errors.NotFound:
            if not remote_download_tried:
                log.info("Image {!r} not found locally, trying remote registry".format(image))
                _pull_image(docker_client, image)
                return create_container_with_auto_pull(True)
            else:
                raise DockerImageNotFound("Image {!r} could not be found".format(image))

    # create the container
    container = create_container_with_auto_pull()

    if "Warnings" in container and container["Warnings"]:
        log.warn("Created container contains warnings {!r}".format(container["Warnings"]))

    container_id = container["Id"]

    # start the container
    docker_client.start(container=container_id)

    return container_id


def _copy(docker_client, container_id, source, destination):
    """
    Copies a file or directory from a given local path to the container being used for the build
    """

    log.debug("Copying content from {!r} to container path {!r}".format(source, destination))

    # confirm that the given path is valid
    if not os.path.exists(source):
        raise SourcePathNotFound(
            "Source path {!r} is invalid, specified path could not be found".format(source)
        )

    # determine the source and destination type
    is_src_dir = os.path.isdir(source)
    is_dst_dir = destination[-1:] == "/"

    # confirm that the right combination of source to destination is specified
    # the only invalid option is if the source is a directory and the destination is a file
    if is_src_dir and not is_dst_dir:
        raise InvalidDockerBuildOptionValue(
            "Invalid copy destination {!r}, path must be a folder since source {!r} ia a folder"
            .format(destination, source)
        )

    # determine the destination directory according to the determined destination type
    dst_folder = destination if is_dst_dir else os.path.dirname(destination)
    # determine the archive name according to the source and destination
    archive_name = os.path.basename(source) if is_dst_dir else os.path.basename(destination)

    # the in memory archive that will be used to copy the content over to the container
    archive = io.BytesIO()

    # create a tar file with all the contents of the given path
    with tarfile.open(fileobj=archive, mode='w') as tar:
        tar.add(
            name=source,
            arcname=archive_name
        )

    # create the destination folder in the container if it doesn't exist
    _run_command(
        docker_client,
        container_id,
        "mkdir -p {path}".format(path=dst_folder)
    )

    # copy over the content to the container
    docker_client.put_archive(
        container=container_id,
        path=dst_folder,
        data=archive.getvalue()
    )


def _run_command(docker_client, container_id, command, args=None, show_logs=False):
    """
    Runs the given command in the container
    """

    def execute_instructions(instruction_list, variable_list, logger):
        """
        Executes all the given instructions against the container
        """

        # execute the instruction
        execute = docker_client.exec_create(
            container=container_id,
            cmd=[
                "/bin/sh",
                "-c",
                "; ".join(["set -e"] + variable_list + instruction_list)
            ],
            user="root"
        )

        stream = docker_client.exec_start(
            exec_id=execute["Id"],
            stream=True
        )

        # display whatever is being printed to the stdout of the container
        for log_stream in stream:
            logger.log(log_stream)

        # confirm that the command finished with no error
        exit_code = docker_client.exec_inspect(execute["Id"])["ExitCode"]

        if exit_code:
            raise CommandExecutionError(
                "RUN command with instruction/s {instruction!r} failed with exit code [{exit_code}]"
                .format(
                    instruction=instruction_list[0]
                    if len(instruction_list[0]) <= 30 and len(instruction_list) == 1
                    else "{}...".format(instruction_list[0][:30]),
                    exit_code=exit_code
                )
            )

    # the list of variables that will be used during the execution of each command
    environment_variables = [
        "export {name}={value}".format(name=name, value=args[name])
        for name in args or {}
    ]

    # the list of instructions to execute against the container
    instructions = command if isinstance(command, types.ListType) else [command]

    with ConsoleLogger(show_logs, "Start of Container Logs") as console_log:
        execute_instructions(instructions, environment_variables, console_log)


def _commit_image(docker_client, container_id, author=None, configs=None, tag=None):
    """
    Commits the made changes in the container into an image.
    """

    # the list of parameters that will be passed to the docker command
    params = {
        "container": container_id,
        "conf": {}
    }

    # add the tag that should be used for the image to be created if any
    if tag:
        params["repository"], params["tag"] = _get_docker_image_name_parts(tag)

    # populate all other optional parameters
    if author:
        params["author"] = author

    # add all the specified build options
    if configs:
        for index, configuration_option in enumerate(Configuration):
            _parse_config(configs, params["conf"], configuration_option)

    # commit the changes
    image = docker_client.commit(**params)
    image_id = image["Id"]

    return str(image_id[7:19])


def _remove_container(docker_client, container_id):
    """
    Removes the container
    """
    # determine if the container is paused first, if it is first un-pause it before trying to remove
    # the container
    if _inspect_container(docker_client, container_id)["State"]["Paused"]:
        docker_client.unpause(container=container_id)

    # remove the container
    docker_client.remove_container(container=container_id, force=True)


def _copy_build_context(docker_client, container_id, step_config):
    """
    Copies the build context to the running container. The build context can be either one or many
    paths that can be copied into the container
    """

    files_copied = False

    if "BUILDCONTEXT" in step_config:

        log.info("Copying building context to the container")
        files_copied = True

        if isinstance(step_config["BUILDCONTEXT"], str):

            _copy(
                docker_client,
                container_id,
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

                _copy(docker_client, container_id, copy_details["SRC"], dst)

        else:

            raise InvalidBuildConfigurations(
                "BUILDCONTEXT is invalid, context must be either a String or a List of SRC and DST "
                "objects"
            )

    return files_copied


def _build(docker_client, args, build_config, step_config, from_image, should_remove_container):
    """
    Builds the image for the given step

    :param docker_client: The Docker Client that is being used to send commands to the Docker Daemon
    :param args: The list of args that are known for the build
    :param build_config: The configurations of the entire build
    :param step_config: The configurations of the step being build with this build process
    :param from_image: The identifier or tag of the image to be used as the base for the image being
                       created
    :param should_remove_container: Indicates if the container should be removed on success or
                                    failure build

    :returns: The identifier of the image that was created

    :type docker_client: docker.Client
    :type args: dict
    :type build_config: dict
    :type step_config: dict
    :type from_image: str
    :type should_remove_container: bool
    :rtype: str
    """
    container_id = None

    try:

        # create the container that will be used to run the details for the image
        log.info("Starting new container from {!r}".format(from_image))
        container_id = _create_container(docker_client, from_image)

        # determine if there is a build context specified
        build_context_populated = _copy_build_context(docker_client, container_id, step_config)

        # copy over any files that are required if any specified
        if "COPY" in step_config:
            log.info("Copying folders or files to container")
            for copy_details in step_config["COPY"]:
                _copy(
                    docker_client,
                    container_id,
                    copy_details["SRC"],
                    copy_details["DST"]
                )

        # execute the commands to make the necessary changes
        if "RUN" in step_config:
            log.info("Making necessary changes to the container")
            _run_command(
                docker_client,
                container_id,
                step_config["RUN"],
                args=args,
                show_logs=True
            )

        # clean up the build context if one was created
        if build_context_populated:
            log.info("Cleaning up container from build context")
            _run_command(
                docker_client,
                container_id,
                "rm -rf {dst}".format(dst=BUILD_CONTEXT_DST_PATH)
            )

        # commit the change done to the container
        log.info("Creating image with container changes")

        # determine if it is the last build step in the process
        is_last_build_step = step_config == build_config["STEPS"][-1]

        # get the configs of the image that was used as the base image
        image_configs = _inspect_image(docker_client, from_image)["Config"]

        # build the configuration that will be set for the image being created
        configs = step_config["CONFIG"] if "CONFIG" in step_config else {}

        # if the command and entry point are not being over written by a specific configuration of
        # the new image being created set the command and / or entry point of the from image. This
        # is being done as the container which was created from (the base images) is overwriting the
        # command and entry point to force the start of shell in the container
        if "CMD" not in configs:
            configs["CMD"] = image_configs["Cmd"] or []

        if "ENTRYPOINT" not in configs:
            configs["ENTRYPOINT"] = image_configs["Entrypoint"]

        image_id = _commit_image(
            docker_client,
            container_id,
            author=build_config["MAINTAINER"] if "MAINTAINER" in build_config else None,
            configs=configs,
            tag=build_config["TAG"] if is_last_build_step and "TAG" in build_config else None
        )

        log.info("Successfully created image {!r}".format(image_id))

        # return the identifier of the image that was created from this build step
        return image_id

    finally:

        # if a container was created remove it to clean up
        if container_id and should_remove_container:
            log.info("Cleaning up container")
            _remove_container(docker_client, container_id)


def _get_docker_image_name_parts(image_name):
    """
    Gets the parts of the image name. The name is split into two parts, the repository and the tag
    """
    image_name_parts = image_name.split(":")
    return (
        image_name_parts[0],
        image_name_parts[1] if len(image_name_parts) > 1 else "latest"
    )


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
        config_file_loader = MainConfigFileLoader(command_line_args.main_config_file_path)
        main_config = MainConfig(config_file_loader.load().content)

        # load all the build arguments for the build process
        build_args = dict(
            main_config.arguments.items() + command_line_args.build_args.items()
        )

        # load the build file
        build_config = BuildConfig(
            FileLoader(command_line_args.build_config_file_path).load().content,
            build_args
        )

        docker_client = docker.from_env(assert_hostname=False)

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
        os.chdir(os.path.dirname(command_line_args.build_config_file_path))

        # go through the steps to create the necessary images
        for step_config in build_config.config["STEPS"]:
            from_image = _build(
                docker_client,
                build_args,
                build_config.config,
                step_config,
                from_image,
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

    except RequestException:
        log.error("Cannot connect to the Docker daemon. Is the docker daemon running on this host?")
        return 1

    except (DockerBuildException, DockerBuildIOError) as ex:
        log.error("Build failed due to error : {}".format(ex))
        return 1

    except Exception as ex:
        log.exception("Unexpected error during build due to error : {}".format(ex))
        return 1


if __name__ == '__main__':
    sys.exit(main())

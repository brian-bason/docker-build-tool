"""
Build tool to create Docker images. This is another implementation of the builder different than the
one provided by the official repository. This tool is intended to give the user more flexibility to
the creation of the images as opposed to what is being provided by the build command provided in
docker
"""
from __future__ import print_function

import argparse
import docker
import yaml
import logging
import types
import os
import io
import tarfile
import base64
import copy


from docker_builder.catalog import Configuration
from docker_builder.exception import \
    DockerBuilderException, \
    DockerBuilderConfigFileNotFound, \
    InvalidDockerBuilderConfigFile, \
    DockerBuilderFileNotFound, \
    InvalidDockerBuilderFile, \
    InvalidDockerBuildOptionValue, \
    MissingDockerBuilderArgument, \
    CommandExecutionError
from docker_builder.util import \
    PutAction, \
    parse_key_value_option
from yaml.parser import ParserError


# the path to the build context on the container. This determines where the specified build context
# folder on the build machine will be copied on the container.
BUILD_CONTEXT_DST_PATH = "/tmp/build-context"

# the default path for the configuration file
CONFIG_FILE_PATH = "~/.docker/builder-config.yml"

# the logger for the docker builder tool
log = logging.getLogger("docker_builder")


def _parse_config(configs, parsed_configs, configuration_option):
    """
    Validates the given configuration and if required converts the configuration from the format
    supported by the Docker Builder tool to the one understood by Docker Daemon.
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
    Inspect the details of the image returning back the full details of the given image
    """

    return docker_client.inspect_image(image)


def _create_container(docker_client, image):
    """
    Create a container that will be used to execute the commands and create the new required image.
    The image will be created and started.
    """

    # the list of parameters that will be passed to the docker command
    params = {
        "tty": True,
        "detach": True,
        "entrypoint": "bash",
        "image": image
    }

    # create the container that will be used to run the details for the image
    container = docker_client.create_container(**params)

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
        raise IOError("Invalid source path, path {!s} could not be found".format(source))

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


def _run_command(docker_client, container_id, command, args={}, show_logs=False):
    """
    Runs the given command in the container
    """
    # the command will be executed using shell binary. Eventually this will be changed to pass it in
    # as a builder option
    cmd = [
        "/bin/sh",
        "-c",
        ""
    ]

    # insert all the build arguments as environment variables for the command being executed
    for name, value in args.items():
        cmd[2] += "export {name}={value} && ".format(name=name, value=value)

    # keep track of how much of the command is actually the list of arguments being passed as
    # environment variables. This is required if an error is raised during the execution of the
    # command
    args_len = len(cmd[2])

    # insert the command that is to be executed after the list of variables
    if isinstance(command, types.ListType):
        cmd[2] += " ".join(command)
    else:
        cmd[2] += command

    # execute the command in the container
    execute = docker_client.exec_create(
        container=container_id,
        cmd=cmd,
        user="root"
    )

    stream = docker_client.exec_start(
        exec_id=execute["Id"],
        stream=True
    )

    # print the start of the log to keep a clear indication of the start of the container logs
    if show_logs:
        print(
            "************************** Start of Container Logs **************************\n"
        )

    # display whatever is being printed to the stdout of the container
    last_log_entry = ""
    for log_stream in stream:
        if show_logs:
            print(log_stream, end="")
            last_log_entry = log_stream

    # print the end of logs line
    if show_logs:
        print(
            "\n{}*****************************************************************************"
            .format(
                "" if last_log_entry[-1:] == "\n" else "\n"
            )
        )

    # confirm that the command finished with no error
    exit_code = docker_client.exec_inspect(execute["Id"])["ExitCode"]

    if exit_code:
        raise CommandExecutionError(
            "Command {!r} failed with exit code [{}]".format(
                cmd[2][args_len:] if len(cmd[2]) - args_len < 30 else
                "{}...".format(cmd[2][args_len:args_len + 30]),
                exit_code
            )
        )


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
        tag_parts = tag.split(":")
        params["repository"] = tag_parts[0]
        if len(tag_parts) > 1:
            params["tag"] = tag_parts[1]

    # populate all other optional parameters
    if author:
        params["author"] = author

    # add all the specified build options
    if configs:
        for configuration_option in Configuration:
            _parse_config(configs, params["conf"], configuration_option)

    # commit the changes
    image = docker_client.commit(**params)
    image_id = image["Id"]

    return str(image_id[7:19])


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
                    raise InvalidDockerBuilderFile(
                        "Invalid Build Context 'DST' property {!r}, destination path must be "
                        "within the Build Context folder".format(
                            copy_details["DST"]
                        )
                    )

                _copy(docker_client, container_id, copy_details["SRC"], dst)

        else:

            raise InvalidDockerBuilderConfigFile(
                "BUILDCONTEXT is invalid, context must be either a String or a List of SRC and DST "
                "objects"
            )

    return files_copied


def _build(docker_client, args, build_config, step_config, from_image):
    """
    Builds the image for the given step

    :param docker_client: The Docker Client that is being used to send commands to the Docker Daemon
    :param args: The list of args that are known for the build
    :param build_config: The configurations of the entire build
    :param step_config: The configurations of the step being build with this build process
    :param from_image: The identifier or tag of the image to be used as the base for the image being
                       created

    :returns: The identifier of the image that was created

    :type docker_client: docker.Client
    :type args: dict
    :type build_config: dict
    :type step_config: dict
    :type from_image: str
    :rtype: str
    """
    container_id = None

    try:

        # create the container that will be used to run the details for the image
        log.info("Starting new container from {!r}".format(from_image))
        container_id = _create_container(docker_client, from_image)

        # determine if there is a build context specified
        build_context_populated = _copy_build_context(docker_client, container_id, step_config)

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

        # commit the change done to the container
        log.info("Creating image with container changes")

        # determine if it is the last build step in the process
        is_last_build_step = step_config == build_config["STEPS"][-1]

        # get the entry point of the image that was used as the base image
        entry_point = _inspect_image(docker_client, from_image)["Config"]["Entrypoint"]

        # build the configuration that will be set for the image being created
        configs = step_config["CONFIG"] if "CONFIG" in step_config else {}

        # if the entry point is not being over written by a specific configuration of the new image
        # being created set it to the entry point of the from image. This is being done as the
        # container which was created from the base images is overwriting the entry point to force
        # the start of bash in the container
        if "ENTRYPOINT" not in configs:
            configs["ENTRYPOINT"] = entry_point

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
        if container_id:
            log.info("Cleaning up container")
            docker_client.remove_container(container=container_id, force=True)


def _parse_arguments(loaded_args, args):

    for arg in loaded_args:

        name, options = arg.popitem()

        # if an argument is set as not optional confirm that the value for the argument is known.
        # if on the other hand the argument is optional confirm that a default was given
        if "OPTIONAL" in options and not options["OPTIONAL"]:
            if name not in args:
                raise MissingDockerBuilderArgument(
                    "Build argument {!r} is not optional but no value was passed in for the "
                    "arguments".format(
                        name
                    )
                )
        else:
            if "DEFAULT" not in options:
                raise MissingDockerBuilderArgument(
                    "Build argument {!r} is optional but no default value is specified".format(
                        name
                    )
                )

        # populate the default for the argument if it was not passed
        if "DEFAULT" in options and name not in args:
            if "OBFUSCATED" in options and options["OBFUSCATED"]:
                args[name] = base64.b64decode(options["DEFAULT"])
            else:
                args[name] = options["DEFAULT"]


def _load_arguments(line_args, build_configs, common_configs):

    # load the list of arguments that are required for the build
    # first load the command line arguments (first priority)
    # second the arguments in the build file (second priority, load additional args)
    # last the arguments in the config file (last priority, load remaining args)
    args = copy.deepcopy(line_args)

    if "ARGS" in build_configs:
        _parse_arguments(build_configs["ARGS"], args)

    if "ARGS" in common_configs:
        _parse_arguments(common_configs["ARGS"], args)

    # inject the build context path (path inside the container) that can be used for reference
    # during the build process
    args["BUILD_CONTEXT_PATH"] = BUILD_CONTEXT_DST_PATH

    return args


def _parse_config_file(config_file_path):

    # expend the path
    expanded_path = os.path.expanduser(config_file_path)
    file_exists = os.path.exists(expanded_path)
    config_file = {}

    # determine if the config file exists, only raise an error if the given config is not the
    # default one
    if not file_exists and config_file_path != CONFIG_FILE_PATH:
        raise DockerBuilderConfigFileNotFound(
            "Docker Builder configuration file not found at {!r}, please make sure that the right "
            "path was specified".format(
                config_file_path
            )
        )

    if file_exists:
        try:
            config_file = yaml.load(open(expanded_path))
        except ParserError as ex:
            raise InvalidDockerBuilderConfigFile(
                "Docker Builder configuration file is invalid. File failed with error {!r} at {!r}"
                .format(
                    ex.problem,
                    str(ex.problem_mark)
                )
            )

    return config_file


def _parse_build_file(build_file_path, args=None):

    # expend the path
    expanded_path = os.path.expanduser(build_file_path)

    # determine if the build file exists
    if not os.path.exists(expanded_path):
        raise DockerBuilderFileNotFound(
            "Docker Builder build file not found at {!r}, please make sure that the right "
            "path was specified".format(
                build_file_path
            )
        )

    try:

        build_file = open(expanded_path).read()

        if args:
            build_file = build_file.format(**args)

        return yaml.load(build_file)

    except KeyError as ex:
        raise InvalidDockerBuilderFile(
            "Docker Builder build file is invalid. Argument {!r} is not defined".format(ex.message)
        )
    except ParserError as ex:
        raise InvalidDockerBuilderFile(
            "Docker Builder build file is invalid. File failed with error {!r} at {!r}".format(
                ex.problem,
                str(ex.problem_mark)
            )
        )


def main(argv=None):
    """
    Main function for invoking the Docker Builder tool
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
        help="List of build arguments",
        default={}
    )
    parser.add_argument(
        "-f", "--build-file",
        dest="build_file_path",
        type=str,
        default="./docker-builder.yml"
    )
    parser.add_argument(
        "-c", "--config-file",
        dest="config_file_path",
        type=str,
        default=CONFIG_FILE_PATH
    )
    parser.add_argument(
        "-t", "--tag",
        dest="tag",
        type=str
    )

    try:

        # parse the command line arguments passed to the tool
        command_line_args = parser.parse_args(argv)

        # load the common configuration file
        common_configs = _parse_config_file(command_line_args.config_file_path)

        # load the build configuration file
        build_configs = _parse_build_file(
            args={},
            build_file_path=command_line_args.build_file_path
        )

        # load the list of arguments from all known sources
        build_args = _load_arguments(
            line_args=command_line_args.build_args,
            build_configs=build_configs,
            common_configs=common_configs
        )

        # reload the build configs replacing all of the specified arguments with actual values
        build_configs = _parse_build_file(
            args=build_args,
            build_file_path=command_line_args.build_file_path
        )

        docker_client = docker.from_env(assert_hostname=False)

        # determine from which image to start
        if "FROM" not in build_configs:
            raise InvalidDockerBuilderFile("FROM is not optional please confirm the build file")

        from_image = build_configs["FROM"]

        # if the tag command line argument was specified update the tag that is set in the build
        # file
        if command_line_args.tag:
            build_configs["TAG"] = command_line_args.tag

        # go through the steps to create the necessary images
        for step_config in build_configs["STEPS"]:
            from_image = _build(
                docker_client,
                build_args,
                build_configs,
                step_config,
                from_image
            )

    except DockerBuilderException as ex:
        log.error("Build failed due to error : {}".format(ex))

    except Exception as ex:
        log.exception("Unexpected error during build due to error : {}".format(ex))


if __name__ == '__main__':
    main()

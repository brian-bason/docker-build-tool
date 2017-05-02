"""
Groups together the functionality that is required to communicate with the Docker daemon that the
build tool will use to perform the build. The package contains the commands that can be sent to the
daemon through the rest APIs and also other functionality required for such communication.
"""
from __future__ import print_function

import docker
import json
import io
import tarfile
import types
import os
import logging

from sys import stdout
from docker.errors import \
    APIError, \
    DockerException, \
    ImageNotFound
from docker_build.exception import \
    DockerImageNotFound, \
    SourcePathNotFound, \
    InvalidDockerBuildOptionValue, \
    CommandExecutionError
from docker_build.daemon.catalog import Configuration
from docker_build.utils.logger import ConsoleLogger


class DockerAPI(object):
    """
    Help methods for the Docker API
    
    :param connection_timeout: The maximum number of seconds that should be set on the API 
        connection before giving up if no response from the daemon is received
        
    :type connection_timeout: int
    """

    def __init__(self, connection_timeout=60):

        if connection_timeout < 1:
            raise ValueError("Connection timeout must be a greater than zero")

        self._log = logging.getLogger(__name__)
        self._client = docker.from_env(
            assert_hostname=False, version="auto", timeout=connection_timeout
        )

    @staticmethod
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
            parsed_configs[configuration_option.docker_command] = \
                configuration_option.convert_value(value)

    @staticmethod
    def _get_docker_image_name_parts(name):
        """
        Gets the parts of the image name. The name is split into two parts, the repository and the
        tag
        
        :param name: The full name of the image
        :return: The repository and tag for the given image name
        
        :type name: str
        :rtype: tuple[str, str]
        """
        image_name_parts = name.split(":")
        return (
            image_name_parts[0],
            image_name_parts[1] if len(image_name_parts) > 1 else "latest"
        )

    def _image_exists(self, name):
        """
        Determines if an image exists in the local cache
        
        :param name: The full name of the image
        
        :return: True if the image is found in the local cache false otherwise
        
        :type name: str
        
        :rtype: bool
        """
        try:
            self.get_image(name)
            return True
        except ImageNotFound:
            return False

    def get_image(self, name):
        """
        Gets the Docker Image from the local Docker Registry
        
        :param name: The full name of the image
        :return: The image for the given image name
        
        :type name: str
        :rtype: docker.images.Image
        """
        return self._client.images.get(name)

    def pull_image(self, name):
        """
        Pulls the Docker Image from the remote Docker Registry
        
        :param name: The full name of the image
        
        :type name: str
        """
        progress_details = {}
        download_complete = False
        repository, tag = self._get_docker_image_name_parts(name)
        params = {
            "repository": repository,
            "tag": tag,
            "stream": True
        }

        # pull the image using the lower level APIs so that we can keep track
        for output in self._client.images.client.api.pull(**params):
            log_entries = output.split("\n")

            for log_entry in log_entries:

                if log_entry != "":
                    detail = json.loads(log_entry)

                    # confirm that the image has been found
                    if "error" in detail:
                        raise DockerImageNotFound(detail["error"])

                    if "id" in detail:

                        if not detail["id"] in progress_details:
                            progress_details[detail["id"]] = {
                                "status": detail["status"],
                                "current": detail.get("progressDetail", {}).get("current", 0),
                                "total": detail.get("progressDetail", {}).get("total", 0),
                                "is_image": "progressDetail" in detail
                            }

                        else:
                            progress_detail = progress_details[detail["id"]]
                            progress_detail["status"] = detail["status"]
                            progress_detail["is_image"] = \
                                True if progress_detail["is_image"] else "progressDetail" in detail

                            if "total" in detail.get("progressDetail", {}):
                                progress_detail["current"] = detail["progressDetail"]["current"]
                                progress_detail["total"] = detail["progressDetail"]["total"]

                        # build the log output
                        current = 0
                        total = 0
                        completed_images = 0
                        total_images = 0

                        for image_id in progress_details:
                            progress_detail = progress_details[image_id]
                            current += progress_detail["current"]
                            total += progress_detail["total"]
                            completed_images += progress_detail["is_image"] and \
                                progress_detail["current"] == progress_detail["total"]
                            total_images += progress_detail["is_image"]

                        percent_complete = 0 \
                            if total == 0 else int((float(current)/float(total)) * 100)

                        # print the log message by first clearing the old message and then printing
                        # the new message. This is done to make sure that extra characters from the
                        # old log message are removed before printing the new one
                        stdout.write("\r{}".format(" " * 100))
                        stdout.write(
                            "\rDownloaded {} of {} images, image download/extract {}% complete"
                            .format(
                                completed_images,
                                total_images,
                                percent_complete
                            )
                        )
                        stdout.flush()

                    else:
                        if not download_complete:
                            download_complete = True
                            print()
                        self._log.info(detail["status"])

        # return the pulled image
        return self.get_image(name)

    def create_container(self, image_name, volumes=None, should_ignore_cache=False):
        """
        Create a container that will be used to execute the commands and create the new required
        image. The image will be created and started.
        
        :param image_name: The full name of the image that is to be used to create the container
        :param volumes: The volumes that are to be mounted for the container
        :param should_ignore_cache: Determines if the local cache should be ignored when checking if
            the base image exists
        
        :return: The container that was created
        
        :type image_name: str
        :type volumes: list[str]
        :type should_ignore_cache: bool
        
        :rtype: docker.containers.Container
        """

        # the list of parameters that will be passed to the docker command
        params = {
            "tty": True,
            "detach": True,
            "command": "/bin/sh",
            "image": image_name,
            "volumes": volumes
        }

        # determine if the image needs to be pulled from the remote repository
        if not self.get_image(image_name) or should_ignore_cache:

            self._log.info(
                "{}, trying to pull image from remote registry".format(
                    "Requested to ignore local cache" if should_ignore_cache else
                    "Image {!r} not found locally".format(image_name)
                )
            )

            try:
                image = self.pull_image(image_name)
            except ImageNotFound:
                raise DockerImageNotFound("Image {!r} could not be found".format(image_name))

        else:
            image = self.get_image(image_name)

        # if the image that the container is being started from has an entry point overwrite it to
        # clear the entry point
        if image.attrs.get("Config", {}).get("Entrypoint"):
            params["entrypoint"] = []

        # create the container
        container = self._client.containers.create(**params)

        # confirm what this should be mapped to
        if "Warnings" in container.attrs and container.attrs["Warnings"]:
            self._log.warn("Created container contains warnings {!r}".format(container["Warnings"]))

        # start the container
        container.start()

        return container

    def copy(self, container, source, destination):
        """
        Copies a file or directory from a given local path to the container being used for the build
        
        :param container: The container to which the files or directory is to be copied to
        :param source: The source directory or file that is to be copied
        :param destination: The directory or file path to which the files are to be copied to. The 
            destination path is relative to the container
            
        :type container: docker.containers.Container
        :type source: str
        :type destination: str
        """

        self._log.debug("Copying content from {!r} to container path {!r}".format(
            source, destination
        ))

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
        self.run_command(
            container,
            "mkdir -p {path}".format(path=dst_folder)
        )

        # copy over the content to the container
        container.put_archive(
            path=dst_folder,
            data=archive.getvalue()
        )

    def run_command(self, container, command, variables=None, show_logs=False):
        """
        Runs the given command in the container
        
        :param container: The container where the command is to be executed
        :param command: The command that is to be executed
        :param variables: The variables that are to be set as environment variables when executing
            the command
        :param show_logs: True if the logs from the container stdout should be printed to the
            console False otherwise
            
        :type container: docker.containers.Container
        :type command: str
        :type variables: dict
        :type show_logs: bool
        """

        def execute_instructions(instruction_list, variable_list, logger):
            """
            Executes all the given instructions against the container
            """

            # execute the instruction
            # run this through the low level API as more control is required to determine what the
            # output of executing the command was
            execute = container.client.api.exec_create(
                container=container.id,
                cmd=[
                    "/bin/sh",
                    "-c",
                    "; ".join(["set -e"] + variable_list + instruction_list)
                ],
                user="root",
                tty=True
            )

            stream = container.client.api.exec_start(
                exec_id=execute["Id"],
                stream=True
            )

            # display whatever is being printed to the stdout of the container
            for log_stream in stream:
                logger.log(log_stream)

            # confirm that the command finished with no error
            exit_code = container.client.api.exec_inspect(execute["Id"])["ExitCode"]

            if exit_code:
                raise CommandExecutionError(
                    "RUN command with instruction/s {instruction!r} failed with exit code ["
                    "{exit_code}]"
                    .format(
                        instruction=instruction_list[0]
                        if len(instruction_list[0]) <= 30 and len(instruction_list) == 1
                        else "{}...".format(instruction_list[0][:30]),
                        exit_code=exit_code
                    )
                )

        # the list of variables that will be used during the execution of each command
        environment_variables = []

        for name in variables or {}:
            # can only convert strings and numbers for the time being. Dictionaries and Lists will
            # be ignored
            if isinstance(variables[name], dict) or isinstance(variables[name], list):
                self._log.info(
                    "Variable {!r} will be ignored as it cannot be translated to a linux "
                    "environment variable".format(name)
                )

            else:
                environment_variables.append(
                    "export {name}=\"{value}\"".format(name=name, value=variables[name])
                )

        # the list of instructions to execute against the container
        instructions = command if isinstance(command, types.ListType) else [command]

        with ConsoleLogger(show_logs, "Start of Container Logs") as console_log:
            execute_instructions(instructions, environment_variables, console_log)

    def commit_image(self, container, author=None, configs=None, tag=None):
        """
        Commits the made changes in the container into an image.
        
        :param container: The container which is to be used to create the image
        :param author: The name of the user that is to be set as the author of the image
        :param configs: The list of configurations that are to be used to set the details of the
            image. The configurations are given as key value pairs
        :param tag: The name that is to be used to tag the created image
        
        :return: The short identifier of the created image
            
        :type container: docker.containers.Container
        :type author: str
        :type configs: dict
        :type tag: str
        
        :rtype: str
        """

        # the list of parameters that will be passed to the docker command
        params = {
            "conf": {}
        }

        # add the tag that should be used for the image to be created if any
        if tag:
            params["repository"], params["tag"] = self._get_docker_image_name_parts(tag)

        # populate all other optional parameters
        if author:
            params["author"] = author

        # add all the specified build options
        if configs:
            for index, configuration_option in enumerate(Configuration):
                self._parse_config(configs, params["conf"], configuration_option)

        # commit the changes
        image = container.commit(**params)

        return str(image.id[7:19])

    @staticmethod
    def remove_container(container):
        """
        Removes the container
        
        :param container: The container that is to be removed
        
        :type container: docker.containers.Container
        """

        # determine if the container is paused first, if it is first un-pause it before trying to
        # remove the container
        if container.status == "paused":
            container.unpause()

        # remove the container
        container.remove(force=True)

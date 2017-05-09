# Introduction #

Build tool for creating Docker images. This is a massive improvement over the default Docker build 
tool. This gives the user control of where the line is cut for creating an image and will combine 
different commands together before creating the image. This solves a number of problems one of which
is the fact that with the default Docker build tool the secrets are stored in the created images.
This tool aims to give the control back to the user to determine when and what gets stored into the
image and therefore into the development and/or production environments.

# Using the tool as a Library

The docker build tool can be used as a library by importing the docker_build module and calling the
build method. This interface is provided so that you can integrate with your build tool
programmatically without having to go through the command line. The interface replies back with the
image identifier and tag that was used for the generated image.

Following is a code snippet to illustrate how to use the interface

```$python

import docker_build

image_id, tag = docker_build.build("/path/to/docker-build.yml", { "ARGUMENT1": "VALUE1" })

```
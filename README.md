# Introduction #

Build tool for creating Docker images. This is a massive improvement over the default Docker build 
tool. This gives the user control of where the line is cut to create an image and will combine 
different commands together before creating an image. This solves a number of problems one of which
is the fact that with the default Docker build tool the secrets are stored in the created images.
This tool aims to give the control back to the user to determine when and what gets stored into the
image and therefore into the development and production environments.
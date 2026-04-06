cmake_minimum_required(VERSION 3.15)

project(tikworks LANGUAGES CXX)

# Paths
if(NOT DEFINED MAYA_DEVKIT_ROOT)
  set(MAYA_DEVKIT_ROOT "${CMAKE_SOURCE_DIR}/../maya_devkit/${MAYA_VERSION}/devkitBase")
endif()

# Plugin Subdirectories
# BEGIN PLUGIN SUBDIRECTORIES
# Add new plugins via: make add-plugin PLUGIN_NAME=myPlugin
# END PLUGIN SUBDIRECTORIES

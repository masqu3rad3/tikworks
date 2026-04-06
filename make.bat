@echo off
setlocal enabledelayedexpansion

if "%1"=="" goto help

if "%1"=="help" goto help
if "%1"=="docs" goto docs
if "%1"=="show-doc" goto showdoc

if "%1"=="tests" goto tests
if "%1"=="tests-unit" goto tests_unit
if "%1"=="tests-integration" goto tests_integration

if "%1"=="tests-cov" goto tests_cov
if "%1"=="tests-cov-unit" goto tests_cov_unit
if "%1"=="tests-cov-integration" goto tests_cov_integration

if "%1"=="cmake-build" goto cmake_build
if "%1"=="cmake-release" goto cmake_release

if "%1"=="build" goto build
if "%1"=="dev" goto dev
if "%1"=="release" goto release
if "%1"=="add-plugin" goto add_plugin

echo Unknown command: %1
echo Run: make help
exit /b 1

:help
echo.
echo Available commands:
echo   cmake-build ^<VERSION^>       Configure and build Debug via CMake
echo   cmake-release ^<VERSION^>     Configure and build Release via CMake
echo   build ^<VERSION^>             Build using package script
echo   dev [VERSION]              Dev build ^& deploy (all versions if no VERSION)
echo   release                       Release build via CMake
echo   add-plugin ^<NAME^>           Add a new C++ plugin to the project
echo   docs                          Build documentation
echo   show-doc                      Open documentation in browser
echo   tests                         Run all tests
echo   tests-unit                    Run unit tests
echo   tests-integration             Run integration tests
echo   tests-cov                     Run all tests with coverage
echo   tests-cov-unit                Run unit tests with coverage
echo   tests-cov-integration         Run integration tests with coverage
exit /b 0

:docs
cd docs
call make html
exit /b 0

:showdoc
start docs\build\html\index.html
exit /b 0

:tests
call make.bat tests-unit
call make.bat tests-integration
exit /b 0

:tests_unit
set PYTHONPATH=%CD%\src\python;%PYTHONPATH%
mayapy tests\unit\invoke.py
exit /b 0

:tests_integration
set PYTHONPATH=%CD%\src\python;%PYTHONPATH%
mayapy tests\integration\invoke.py
exit /b 0

:tests_cov
mayapy -m coverage erase
call make.bat tests-cov-unit
call make.bat tests-cov-integration
mayapy -m coverage report
exit /b 0

:tests_cov_unit
set PYTHONPATH=%CD%\src\python;%PYTHONPATH%
mayapy -m coverage run tests\unit\invoke.py
exit /b 0

:tests_cov_integration
set PYTHONPATH=%CD%\src\python;%PYTHONPATH%
mayapy -m coverage run tests\integration\invoke.py
exit /b 0

:cmake_build
if "%2"=="" goto missing_version
cmake -B build -DCMAKE_BUILD_TYPE=Debug -DMAYA_VERSION=%2
cmake --build build --config Debug
exit /b 0

:cmake_release
if "%2"=="" goto missing_version
cmake -B build -DCMAKE_BUILD_TYPE=Release -DMAYA_VERSION=%2
cmake --build build --config Release
exit /b 0

:build
if "%2"=="" goto missing_version
python package\package.py --build %2
exit /b 0

:dev
if "%2"=="" (
    python package\package.py --dev
) else (
    python package\package.py --dev %2
)
exit /b 0

:release
python package\package.py --release
exit /b 0

:add_plugin
if "%2"=="" goto missing_plugin_name
python package\package.py --add-plugin %2
exit /b 0

:missing_version
echo.
echo ERROR: VERSION is required.
echo Usage:
echo   make.bat build 2026
echo   make.bat dev 2026
echo   make.bat cmake-build 2026
exit /b 1

:missing_plugin_name
echo.
echo ERROR: Plugin name is required.
echo Usage:
echo   make.bat add-plugin myPlugin
exit /b 1

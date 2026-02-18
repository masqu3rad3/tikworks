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

echo Unknown command: %1
echo Run: make help
exit /b 1

:help
echo.
echo Available commands:
echo   docs
echo   show-doc
echo   tests
echo   tests-unit
echo   tests-integration
echo   tests-cov
echo   tests-cov-unit
echo   tests-cov-integration
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
set PYTHONPATH=%CD%\src;%PYTHONPATH%
mayapy tests\unit\invoke.py
exit /b 0

:tests_integration
set PYTHONPATH=%CD%\src;%PYTHONPATH%
mayapy tests\integration\invoke.py
exit /b 0

:tests_cov
mayapy -m coverage erase
call make.bat tests-cov-unit
call make.bat tests-cov-integration
mayapy -m coverage report
exit /b 0

:tests_cov_unit
set PYTHONPATH=%CD%\src;%PYTHONPATH%
mayapy -m coverage run tests\unit\invoke.py
exit /b 0

:tests_cov_integration
set PYTHONPATH=%CD%\src;%PYTHONPATH%
mayapy -m coverage run tests\integration\invoke.py
exit /b 0

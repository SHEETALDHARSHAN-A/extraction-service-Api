@echo off
setlocal enabledelayedexpansion

REM Load env files without clobbering variables already defined by caller.
REM Priority: .env.local > .env > workspace .env
if exist ".env.local" (
    for /f "usebackq tokens=1,* delims==" %%a in (".env.local") do (
        set "line=%%a"
        if not "!line!"=="" if not "!line:~0,1!"=="#" (
            if not defined %%a set "%%a=%%b"
        )
    )
)

if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        set "line=%%a"
        if not "!line!"=="" if not "!line:~0,1!"=="#" (
            if not defined %%a set "%%a=%%b"
        )
    )
) else (
    if exist "..\..\.env" (
        for /f "usebackq tokens=1,* delims==" %%a in ("..\..\.env") do (
            set "line=%%a"
            if not "!line!"=="" if not "!line:~0,1!"=="#" (
                if not defined %%a set "%%a=%%b"
            )
        )
    )
)

%*

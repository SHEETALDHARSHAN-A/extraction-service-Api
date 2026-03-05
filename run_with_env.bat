@echo off
setlocal enabledelayedexpansion

if not exist ".env" (
    if exist "..\..\.env" (
        for /f "usebackq tokens=1,* delims==" %%a in ("..\..\.env") do (
            set "line=%%a"
            if not "!line:~0,1!"=="#" (
                set "%%a=%%b"
            )
        )
    )
) else (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        set "line=%%a"
        if not "!line:~0,1!"=="#" (
            set "%%a=%%b"
        )
    )
)

%*

@echo off
REM Quick launcher for standalone GLM-OCR test (Windows)

echo ================================================================================
echo GLM-OCR Standalone Test (No Docker)
echo ================================================================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

echo Python found: 
python --version
echo.

REM Check if test file exists
if not exist "test_invoice_local.png" (
    echo WARNING: test_invoice_local.png not found
    echo Looking for alternative test files...
    dir /b testfiles\*.pdf 2>nul | findstr /r ".*" >nul
    if errorlevel 1 (
        echo ERROR: No test files found
        pause
        exit /b 1
    )
    echo Found test files in testfiles\ directory
    echo.
)

echo Choose test mode:
echo   1. Comprehensive test suite (recommended)
echo   2. Single document extraction
echo   3. Custom prompt test
echo   4. All formats test
echo.

set /p choice="Enter choice (1-4): "

if "%choice%"=="1" goto comprehensive
if "%choice%"=="2" goto single
if "%choice%"=="3" goto custom
if "%choice%"=="4" goto formats

:comprehensive
echo.
echo Running comprehensive test suite...
echo This will test all features and output formats
echo.
python test_standalone_api.py --test
goto end

:single
echo.
set /p input="Enter image path (default: test_invoice_local.png): "
if "%input%"=="" set input=test_invoice_local.png

set /p output="Enter output file (default: result.json): "
if "%output%"=="" set output=result.json

echo.
echo Extracting %input% to %output%...
python test_standalone_api.py --input "%input%" --format json --coordinates --output "%output%"
echo.
echo Result saved to: %output%
type "%output%"
goto end

:custom
echo.
set /p input="Enter image path (default: test_invoice_local.png): "
if "%input%"=="" set input=test_invoice_local.png

set /p prompt="Enter custom prompt: "
if "%prompt%"=="" set prompt=Extract all invoice details as JSON

echo.
echo Processing with custom prompt...
python test_standalone_api.py --input "%input%" --prompt "%prompt%" --output custom_result.json
echo.
echo Result saved to: custom_result.json
type custom_result.json
goto end

:formats
echo.
set /p input="Enter image path (default: test_invoice_local.png): "
if "%input%"=="" set input=test_invoice_local.png

echo.
echo Testing all formats...
echo.

echo [1/6] Text format...
python test_standalone_api.py -i "%input%" -f text -o text_result.json

echo [2/6] JSON format...
python test_standalone_api.py -i "%input%" -f json --coordinates -o json_result.json

echo [3/6] Markdown format...
python test_standalone_api.py -i "%input%" -f markdown -o markdown_result.json

echo [4/6] Table format...
python test_standalone_api.py -i "%input%" -f table -o table_result.json

echo [5/6] Key-Value format...
python test_standalone_api.py -i "%input%" -f key_value -o kv_result.json

echo [6/6] Structured format...
python test_standalone_api.py -i "%input%" -f structured --coordinates -o structured_result.json

echo.
echo All results saved:
dir /b *_result.json

:end
echo.
echo ================================================================================
echo Test complete!
echo ================================================================================
echo.
echo To check GPU usage, run: nvidia-smi
echo.
pause

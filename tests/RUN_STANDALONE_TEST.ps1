# Quick launcher for standalone GLM-OCR test (PowerShell)

Write-Host "================================================================================" -ForegroundColor Yellow
Write-Host "GLM-OCR Standalone Test (No Docker)" -ForegroundColor Yellow
Write-Host "================================================================================" -ForegroundColor Yellow
Write-Host ""

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Python not found. Please install Python 3.10+" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Check test file
if (-not (Test-Path "test_invoice_local.png")) {
    Write-Host "WARNING: test_invoice_local.png not found" -ForegroundColor Yellow
    Write-Host "Looking for alternative test files..."
    
    $testFiles = Get-ChildItem testfiles\*.pdf -ErrorAction SilentlyContinue
    if ($testFiles.Count -eq 0) {
        Write-Host "ERROR: No test files found" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "Found test files in testfiles\ directory" -ForegroundColor Green
    Write-Host ""
}

# Menu
Write-Host "Choose test mode:"
Write-Host "  1. Comprehensive test suite (recommended)"
Write-Host "  2. Single document extraction"
Write-Host "  3. Custom prompt test"
Write-Host "  4. All formats test"
Write-Host ""

$choice = Read-Host "Enter choice (1-4)"

switch ($choice) {
    "1" {
        Write-Host ""
        Write-Host "Running comprehensive test suite..." -ForegroundColor Cyan
        Write-Host "This will test all features and output formats"
        Write-Host ""
        
        python test_standalone_api.py --test
    }
    
    "2" {
        Write-Host ""
        $input = Read-Host "Enter image path (default: test_invoice_local.png)"
        if ([string]::IsNullOrWhiteSpace($input)) {
            $input = "test_invoice_local.png"
        }
        
        $output = Read-Host "Enter output file (default: result.json)"
        if ([string]::IsNullOrWhiteSpace($output)) {
            $output = "result.json"
        }
        
        Write-Host ""
        Write-Host "Extracting $input to $output..." -ForegroundColor Cyan
        
        python test_standalone_api.py --input $input --format json --coordinates --output $output
        
        Write-Host ""
        Write-Host "Result saved to: $output" -ForegroundColor Green
        
        if (Test-Path $output) {
            Get-Content $output | ConvertFrom-Json | ConvertTo-Json -Depth 10
        }
    }
    
    "3" {
        Write-Host ""
        $input = Read-Host "Enter image path (default: test_invoice_local.png)"
        if ([string]::IsNullOrWhiteSpace($input)) {
            $input = "test_invoice_local.png"
        }
        
        $prompt = Read-Host "Enter custom prompt"
        if ([string]::IsNullOrWhiteSpace($prompt)) {
            $prompt = "Extract all invoice details as JSON"
        }
        
        Write-Host ""
        Write-Host "Processing with custom prompt..." -ForegroundColor Cyan
        
        python test_standalone_api.py --input $input --prompt $prompt --output custom_result.json
        
        Write-Host ""
        Write-Host "Result saved to: custom_result.json" -ForegroundColor Green
        
        if (Test-Path custom_result.json) {
            Get-Content custom_result.json | ConvertFrom-Json | ConvertTo-Json -Depth 10
        }
    }
    
    "4" {
        Write-Host ""
        $input = Read-Host "Enter image path (default: test_invoice_local.png)"
        if ([string]::IsNullOrWhiteSpace($input)) {
            $input = "test_invoice_local.png"
        }
        
        Write-Host ""
        Write-Host "Testing all formats..." -ForegroundColor Cyan
        Write-Host ""
        
        $formats = @(
            @{name="text"; file="text_result.json"},
            @{name="json"; file="json_result.json"; extra="--coordinates"},
            @{name="markdown"; file="markdown_result.json"},
            @{name="table"; file="table_result.json"},
            @{name="key_value"; file="kv_result.json"},
            @{name="structured"; file="structured_result.json"; extra="--coordinates"}
        )
        
        $i = 1
        foreach ($fmt in $formats) {
            Write-Host "[$i/6] $($fmt.name) format..." -ForegroundColor Yellow
            
            $cmd = "python test_standalone_api.py -i `"$input`" -f $($fmt.name) -o $($fmt.file)"
            if ($fmt.extra) {
                $cmd += " $($fmt.extra)"
            }
            
            Invoke-Expression $cmd
            $i++
        }
        
        Write-Host ""
        Write-Host "All results saved:" -ForegroundColor Green
        Get-ChildItem *_result.json | Select-Object Name
    }
    
    default {
        Write-Host "Invalid choice" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "================================================================================" -ForegroundColor Yellow
Write-Host "Test complete!" -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "To check GPU usage, run: nvidia-smi"
Write-Host ""

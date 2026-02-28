#!/usr/bin/env pwsh
<#
.SYNOPSIS
    End-to-end Docker test for the GLM-OCR Triton backend (mock mode).

.DESCRIPTION
    1. Builds and starts Triton in mock mode (no GPU required)
    2. Waits for the health endpoint to be ready
    3. Runs a series of inference tests covering every output format
    4. Validates the new GLM-OCR schema: pages[], elements[], bbox_2d
    5. Tests precision_mode and extract_fields options
    6. Prints a colour-coded pass/fail summary, then stops the container

.EXAMPLE
    .\scripts\run_docker_test.ps1
    .\scripts\run_docker_test.ps1 -KeepRunning   # don't stop after tests
#>

param(
    [switch]$KeepRunning,
    [string]$TritonURL = "http://localhost:18000"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ─── helpers ──────────────────────────────────────────────────────────────────
$pass  = 0
$fail  = 0
$tests = [System.Collections.Generic.List[hashtable]]::new()

function Write-Header($msg) {
    Write-Host "`n$('─'*70)" -ForegroundColor Cyan
    Write-Host "  $msg" -ForegroundColor Cyan
    Write-Host "$('─'*70)" -ForegroundColor Cyan
}

function Assert-True($name, [scriptblock]$condition, $detail = "") {
    $ok = & $condition
    if ($ok) {
        $script:pass++
        Write-Host "  ✅  PASS  $name" -ForegroundColor Green
    } else {
        $script:fail++
        Write-Host "  ❌  FAIL  $name$(if($detail){" — $detail"})" -ForegroundColor Red
    }
    $script:tests.Add(@{ Name=$name; Pass=[bool]$ok; Detail=$detail })
}

function Invoke-Triton($imagePath, $outputFormat, $options = @{}, $precisionMode = "") {
    $inputs = @(
        @{ name="images";  shape=@(1,1); datatype="BYTES"; data=@($imagePath) }
        @{ name="prompt";  shape=@(1,1); datatype="BYTES"; data=@("Text Recognition:") }
        @{ name="options"; shape=@(1,1); datatype="BYTES"
           data=@(($options + @{ output_format=$outputFormat } | ConvertTo-Json -Compress)) }
    )
    if ($precisionMode) {
        $inputs += @{ name="precision_mode"; shape=@(1,1); datatype="BYTES"; data=@($precisionMode) }
    }
    $body = @{ inputs=$inputs } | ConvertTo-Json -Depth 10 -Compress
    $r = Invoke-RestMethod "$TritonURL/v2/models/glm_ocr/infer" `
            -Method POST -ContentType "application/json" -Body $body
    # Triton wraps output in outputs[].data[]
    $raw = ($r.outputs | Where-Object { $_.name -eq "generated_text" }).data[0]
    return ($raw | ConvertFrom-Json)
}

# ────────────────────────────────────────────────────────────────────────────
# STEP 1 – Build & Start
# ────────────────────────────────────────────────────────────────────────────
Write-Header "Step 1 · Building and starting Triton (mock mode)"

$composeArgs = @(
    "-f", "docker/docker-compose.yml",
    "-f", "docker/docker-compose.test.yml"
)

Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    Write-Host "  docker compose build triton …" -ForegroundColor Yellow
    docker compose @composeArgs build triton
    if ($LASTEXITCODE -ne 0) { throw "docker compose build failed" }

    Write-Host "  docker compose up -d triton …" -ForegroundColor Yellow
    docker compose @composeArgs up -d triton
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

    # ────────────────────────────────────────────────────────────────────────
    # STEP 2 – Wait for health
    # ────────────────────────────────────────────────────────────────────────
    Write-Header "Step 2 · Waiting for Triton health endpoint"
    $deadline = (Get-Date).AddSeconds(120)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $h = Invoke-RestMethod "$TritonURL/v2/health/ready" -TimeoutSec 3
            $ready = $true
            break
        } catch { Start-Sleep 3 ; Write-Host "    … waiting" -ForegroundColor DarkGray }
    }
    if (-not $ready) { throw "Triton did not become healthy within 120 s" }
    Write-Host "  Triton is ready ✅" -ForegroundColor Green

    # ────────────────────────────────────────────────────────────────────────
    # STEP 3 – Model metadata
    # ────────────────────────────────────────────────────────────────────────
    Write-Header "Step 3 · Model metadata"
    $meta = Invoke-RestMethod "$TritonURL/v2/models/glm_ocr"
    Write-Host "  Model: $($meta.name)   platform: $($meta.platform)" -ForegroundColor Gray
    Assert-True "model name is glm_ocr"     { $meta.name -eq "glm_ocr" }
    Assert-True "has generated_text output" { ($meta.outputs | Where-Object { $_.name -eq "generated_text" }).Count -eq 1 }
    Assert-True "has confidence output"     { ($meta.outputs | Where-Object { $_.name -eq "confidence"     }).Count -eq 1 }

    # Fake image path — mock mode doesn't read the file
    $img = "/tmp/idep/test_invoice.png"

    # ────────────────────────────────────────────────────────────────────────
    # STEP 4 – Text extraction with coordinates
    # ────────────────────────────────────────────────────────────────────────
    Write-Header "Step 4 · Text extraction (include_coordinates=true)"
    $r = Invoke-Triton $img "text" @{ include_coordinates=$true }

    Assert-True "top-level 'pages' key present"              { $r.PSObject.Properties.Name -contains "pages" }
    Assert-True "pages is non-empty array"                   { $r.pages.Count -gt 0 }
    Assert-True "page[0] has 'elements' array"               { $r.pages[0].PSObject.Properties.Name -contains "elements" }
    Assert-True "first element has 'bbox_2d' (4 ints)"       {
        $el = $r.pages[0].elements[0]
        $el.PSObject.Properties.Name -contains "bbox_2d" -and $el.bbox_2d.Count -eq 4
    }
    Assert-True "bbox_2d uses [x1,y1,x2,y2] (x2>x1)"        {
        $b = $r.pages[0].elements[0].bbox_2d
        $b[2] -gt $b[0]
    }
    Assert-True "first element has 'label' field"            { $r.pages[0].elements[0].PSObject.Properties.Name -contains "label"   }
    Assert-True "first element has 'content' field"          { $r.pages[0].elements[0].PSObject.Properties.Name -contains "content" }
    Assert-True "model name is zai-org/GLM-OCR"              { $r.model -eq "zai-org/GLM-OCR" }
    Assert-True "confidence is between 0 and 1"              { $r.confidence -ge 0 -and $r.confidence -le 1 }

    Write-Host "`n  Sample element:" -ForegroundColor DarkGray
    $r.pages[0].elements[0] | ConvertTo-Json -Depth 3 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }

    # ────────────────────────────────────────────────────────────────────────
    # STEP 5 – Markdown output
    # ────────────────────────────────────────────────────────────────────────
    Write-Header "Step 5 · Markdown output format"
    $r = Invoke-Triton $img "markdown"
    Assert-True "markdown key present in result"    { $r.PSObject.Properties.Name -contains "markdown" }
    Assert-True "markdown is non-empty string"      { $r.markdown.Length -gt 10 }
    Assert-True "markdown contains heading (#)"     { $r.markdown -match "#" }

    # ────────────────────────────────────────────────────────────────────────
    # STEP 6 – Table recognition
    # ────────────────────────────────────────────────────────────────────────
    Write-Header "Step 6 · Table recognition"
    $r = Invoke-Triton $img "table" @{ include_coordinates=$true }
    $tableEls = $r.pages[0].elements | Where-Object { $_.label -eq "table" }
    Assert-True "at least one 'table' element returned" { $tableEls.Count -gt 0 }
    Assert-True "table element has bbox_2d"             { $tableEls[0].PSObject.Properties.Name -contains "bbox_2d" }

    # ────────────────────────────────────────────────────────────────────────
    # STEP 7 – Precision mode = high
    # ────────────────────────────────────────────────────────────────────────
    Write-Header "Step 7 · Precision mode = high (word-level bbox enrichment)"
    $r = Invoke-Triton $img "text" @{ include_coordinates=$true; include_word_confidence=$true } "high"
    Assert-True "precision field is 'high' in result"  { $r.precision -eq "high" }
    $elWithWords = $r.pages[0].elements | Where-Object { $_.PSObject.Properties.Name -contains "words" }
    Assert-True "at least one element has 'words' sub-array" { $elWithWords.Count -gt 0 }
    Assert-True "each word has bbox_2d" {
        $w = $elWithWords[0].words[0]
        $w.PSObject.Properties.Name -contains "bbox_2d"
    }

    # ────────────────────────────────────────────────────────────────────────
    # STEP 8 – extract_fields (selective field query)
    # ────────────────────────────────────────────────────────────────────────
    Write-Header "Step 8 · extract_fields filter (date, amount)"
    $r = Invoke-Triton $img "text" @{ include_coordinates=$true; extract_fields=@("date","amount") }
    # The backend echoes the requested list as  result.extract_fields  and puts
    # matched key→value pairs into  result.fields  with bbox_2d on each element.
    Assert-True "response contains 'extract_fields' (requested list)" {
        $r.PSObject.Properties.Name -contains "extract_fields"
    }
    Assert-True "extract_fields echo contains 'date'" {
        $r.extract_fields -contains "date"
    }
    Assert-True "extract_fields echo contains 'amount'" {
        $r.extract_fields -contains "amount"
    }
    # pages[] still comes back — only elements matching the requested fields are kept
    Assert-True "pages array is still present after field filter" {
        $r.PSObject.Properties.Name -contains "pages" -and $r.pages.Count -gt 0
    }

    # ────────────────────────────────────────────────────────────────────────
    # STEP 9 – Usage / token counts
    # ────────────────────────────────────────────────────────────────────────
    Write-Header "Step 9 · Usage metadata"
    $r = Invoke-Triton $img "text"
    Assert-True "usage.prompt_tokens present"     { $r.usage.PSObject.Properties.Name -contains "prompt_tokens"     }
    Assert-True "usage.completion_tokens present" { $r.usage.PSObject.Properties.Name -contains "completion_tokens" }

} finally {
    # ────────────────────────────────────────────────────────────────────────
    # STEP 10 – Teardown
    # ────────────────────────────────────────────────────────────────────────
    if (-not $KeepRunning) {
        Write-Header "Step 10 · Stopping containers"
        docker compose @composeArgs down --remove-orphans
    } else {
        Write-Host "`n  -KeepRunning set — containers left up at $TritonURL" -ForegroundColor Yellow
    }

    Pop-Location

    # ────────────────────────────────────────────────────────────────────────
    # Summary
    # ────────────────────────────────────────────────────────────────────────
    Write-Header "Test Summary"
    foreach ($t in $tests) {
        $icon  = if ($t.Pass) { "✅" } else { "❌" }
        $color = if ($t.Pass) { "Green" } else { "Red" }
        Write-Host ("  {0}  {1}" -f $icon, $t.Name) -ForegroundColor $color
    }
    $total = $pass + $fail
    Write-Host "`n  Passed $pass / $total" -ForegroundColor (if ($fail -eq 0) { "Green" } else { "Yellow" })

    if ($fail -gt 0) {
        Write-Host "  $fail test(s) FAILED" -ForegroundColor Red
        exit 1
    } else {
        Write-Host "  All tests passed 🎉" -ForegroundColor Green
        exit 0
    }
}

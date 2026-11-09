$files = @(
    "deployment\install_autostart.ps1",
    "deployment\manage_service.ps1",
    "setup.ps1",
    "run.ps1",
    "scripts\sync_public_data.ps1"
)

$hasErrors = $false

foreach ($file in $files) {
    if (-not (Test-Path $file)) {
        Write-Host "File not found: $file" -ForegroundColor Red
        continue
    }

    $fullPath = (Resolve-Path $file).Path
    $errors = $null
    $tokens = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($fullPath, [ref]$tokens, [ref]$errors)

    if ($errors -and $errors.Count -gt 0) {
        $hasErrors = $true
        Write-Host "FAIL: $file has $($errors.Count) error(s):" -ForegroundColor Red
        foreach ($err in $errors) {
            Write-Host "  Line $($err.Extent.StartLineNumber): $($err.Message)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "PASS: $file (0 errors)" -ForegroundColor Green
    }
}

if ($hasErrors) {
    exit 1
} else {
    exit 0
}

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$executable = Join-Path $projectRoot 'build\lab4.exe'
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw "Executable not found. Build it first with the command in README.md: $executable"
}

$outputDirectory = Join-Path $env:TEMP ("lr4-smoke-" + [guid]::NewGuid().ToString('N'))
try {
    & $executable `
        --mode standard `
        --min-readers 3 `
        --max-readers 3 `
        --trials 3 `
        --base-operations 3 `
        --read-work-us 0 `
        --reader-think-us 0 `
        --write-work-us 0 `
        --jitter-us 0 `
        --reader-phase-ms 0 `
        --output-dir $outputDirectory

    if ($LASTEXITCODE -ne 0) {
        throw "Program exited with code $LASTEXITCODE"
    }

    $csvPath = Join-Path $outputDirectory 'standard.csv'
    $rows = @(Import-Csv -LiteralPath $csvPath)
    if ($rows.Count -ne 3) {
        throw "Expected three trial rows; got $($rows.Count)"
    }
    foreach ($row in $rows) {
        if ([int]$row.successful_reads -ne 9 -or [int]$row.successful_writes -ne 6) {
            throw "Unexpected operation counts in trial $($row.trial)"
        }
        if ([int]$row.timeouts -ne 0 -or [int]$row.invariant_violations -ne 0) {
            throw "Timeout or invariant violation in trial $($row.trial)"
        }
    }

    $timeoutDirectory = Join-Path $outputDirectory 'timeout'
    & $executable `
        --mode standard `
        --min-readers 3 `
        --max-readers 3 `
        --trials 3 `
        --base-operations 3 `
        --read-work-us 50000 `
        --reader-think-us 0 `
        --write-work-us 0 `
        --jitter-us 0 `
        --reader-phase-ms 0 `
        --wait-timeout-ms 1 `
        --max-runtime-ms 1 `
        --output-dir $timeoutDirectory

    $timeoutExitCode = $LASTEXITCODE
    if ($timeoutExitCode -eq 0) {
        throw 'Expected the short maximum-runtime test to report a timeout.'
    }
    $timeoutRows = @(Import-Csv -LiteralPath (Join-Path $timeoutDirectory 'standard.csv'))
    if (($timeoutRows | Where-Object { [int]$_.timeouts -eq 0 }).Count -ne 0) {
        throw 'The timeout test did not record a timeout in every trial.'
    }
    if (($timeoutRows | Where-Object { [int]$_.invariant_violations -ne 0 }).Count -ne 0) {
        throw 'The timeout test introduced an invariant violation.'
    }

    Write-Output 'PASS: normal and bounded-timeout trials behaved as expected.'
} finally {
    $resolvedOutput = [IO.Path]::GetFullPath($outputDirectory)
    $resolvedTemp = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
    if (-not $resolvedOutput.StartsWith($resolvedTemp, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing cleanup outside the temporary directory'
    }
    if (Test-Path -LiteralPath $resolvedOutput) {
        Remove-Item -LiteralPath $outputDirectory -Recurse -Force
    }
}

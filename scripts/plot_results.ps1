param(
    [Parameter(Mandatory = $true)]
    [string] $InputCsv,
    [Parameter(Mandatory = $true)]
    [string] $OutputPrefix
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $InputCsv -PathType Leaf)) {
    throw "CSV file not found: $InputCsv"
}

$rows = @(Import-Csv -LiteralPath $InputCsv)
if ($rows.Count -eq 0) {
    throw "CSV file contains no experiment rows: $InputCsv"
}

$culture = [System.Globalization.CultureInfo]::InvariantCulture

function Get-ChartPoints {
    param(
        [object[]] $Rows,
        [string] $Property
    )

    $groups = $Rows | Group-Object { [int]$_.reader_count } | Sort-Object { [int]$_.Name }
    foreach ($group in $groups) {
        $values = @($group.Group | ForEach-Object {
            [double]::Parse($_.$Property, [System.Globalization.CultureInfo]::InvariantCulture)
        })
        $average = ($values | Measure-Object -Average).Average
        [pscustomobject]@{
            Readers = [int]$group.Name
            Value = [double]$average
        }
    }
}

function Write-LineChart {
    param(
        [object[]] $Points,
        [string] $Title,
        [string] $YAxisLabel,
        [string] $OutputPath,
        [string] $Color
    )

    $width = 960
    $height = 540
    $left = 100
    $right = 900
    $top = 72
    $bottom = 440
    $plotWidth = $right - $left
    $plotHeight = $bottom - $top
    $maxValue = [double](($Points | Measure-Object -Property Value -Maximum).Maximum)
    if ($maxValue -le 0) {
        $maxValue = 1
    }
    $maxValue *= 1.10
    $minReaders = [int](($Points | Measure-Object -Property Readers -Minimum).Minimum)
    $maxReaders = [int](($Points | Measure-Object -Property Readers -Maximum).Maximum)

    $builder = [System.Text.StringBuilder]::new()
    [void]$builder.AppendLine("<svg xmlns='http://www.w3.org/2000/svg' width='$width' height='$height' viewBox='0 0 $width $height'>")
    [void]$builder.AppendLine("<rect width='100%' height='100%' fill='white'/>")
    [void]$builder.AppendLine("<text x='$($width / 2)' y='34' text-anchor='middle' font-family='Arial' font-size='20'>$Title</text>")

    for ($tick = 0; $tick -le 5; $tick++) {
        $value = $maxValue * $tick / 5
        $y = $bottom - $plotHeight * $tick / 5
        $label = $value.ToString('0.###', $culture)
        [void]$builder.AppendLine("<line x1='$left' y1='$y' x2='$right' y2='$y' stroke='#dddddd'/>")
        [void]$builder.AppendLine("<text x='$($left - 12)' y='$($y + 5)' text-anchor='end' font-family='Arial' font-size='12'>$label</text>")
    }

    [void]$builder.AppendLine("<line x1='$left' y1='$top' x2='$left' y2='$bottom' stroke='black'/>")
    [void]$builder.AppendLine("<line x1='$left' y1='$bottom' x2='$right' y2='$bottom' stroke='black'/>")

    $coordinates = [System.Collections.Generic.List[string]]::new()
    foreach ($point in $Points) {
        if ($maxReaders -eq $minReaders) {
            $x = $left + $plotWidth / 2
        } else {
            $x = $left + $plotWidth * ($point.Readers - $minReaders) / ($maxReaders - $minReaders)
        }
        $y = $bottom - $plotHeight * $point.Value / $maxValue
        $coordinates.Add("$($x.ToString('0.##', $culture)),$($y.ToString('0.##', $culture))")
        [void]$builder.AppendLine("<circle cx='$($x.ToString('0.##', $culture))' cy='$($y.ToString('0.##', $culture))' r='5' fill='$Color'/>")
        [void]$builder.AppendLine("<text x='$($x.ToString('0.##', $culture))' y='$($bottom + 24)' text-anchor='middle' font-family='Arial' font-size='13'>$($point.Readers)</text>")
    }

    [void]$builder.AppendLine("<polyline points='$($coordinates -join ' ')' fill='none' stroke='$Color' stroke-width='3'/>")
    [void]$builder.AppendLine("<text x='$($width / 2)' y='510' text-anchor='middle' font-family='Arial' font-size='14'>Number of readers</text>")
    [void]$builder.AppendLine("<text x='24' y='$($height / 2)' text-anchor='middle' transform='rotate(-90 24 $($height / 2))' font-family='Arial' font-size='14'>$YAxisLabel</text>")
    [void]$builder.AppendLine('</svg>')

    $parent = Split-Path -Parent $OutputPath
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    [System.IO.File]::WriteAllText($OutputPath, $builder.ToString(), [System.Text.Encoding]::ASCII)
}

$elapsedPoints = @(Get-ChartPoints -Rows $rows -Property 'elapsed_ms')
$waitPoints = @(Get-ChartPoints -Rows $rows -Property 'average_writer_wait_ms')
Write-LineChart -Points $elapsedPoints -Title 'Average trial duration by reader count' `
    -YAxisLabel 'Duration (ms)' -OutputPath "${OutputPrefix}_elapsed.svg" -Color '#2563eb'
Write-LineChart -Points $waitPoints -Title 'Average writer wait by reader count' `
    -YAxisLabel 'Writer wait (ms)' -OutputPath "${OutputPrefix}_writer_wait.svg" -Color '#dc2626'

Write-Output "Created $OutputPrefix`_elapsed.svg"
Write-Output "Created $OutputPrefix`_writer_wait.svg"

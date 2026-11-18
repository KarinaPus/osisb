param([string]$DocumentPath, [string]$PdfPath)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($PdfPath))) | Out-Null
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$document = $null
try {
    $document = $word.Documents.Open([IO.Path]::GetFullPath($DocumentPath), $false, $false)
    $document.Repaginate()
    $document.Fields.Update() | Out-Null
    $document.Save()
    $document.ExportAsFixedFormat([IO.Path]::GetFullPath($PdfPath), 17)
    Write-Output ('Pages: ' + $document.ComputeStatistics(2))
} finally {
    if ($document) { $document.Close(0) }
    $word.Quit()
}

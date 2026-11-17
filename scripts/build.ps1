$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force (Join-Path $root 'build') | Out-Null
& g++ -std=c++20 -O2 -Wall -Wextra -pedantic (Join-Path $root 'src\main.cpp') -o (Join-Path $root 'build\lab4.exe')
if ($LASTEXITCODE -ne 0) { throw 'C++ build failed' }

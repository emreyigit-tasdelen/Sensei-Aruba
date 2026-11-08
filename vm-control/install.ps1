# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Emre Yiğit Taşdelen
# One-time setup: desktop shortcuts "AI Başlat" / "AI Uyut". No scheduled task: the model unloads itself
# inside the server (Ollama keep-alive), so nothing runs in the background on this PC.
$dir  = $PSScriptRoot
$pwsh = (Get-Command pwsh).Source

$desktop = [Environment]::GetFolderPath("Desktop")
$shell = New-Object -ComObject WScript.Shell
foreach ($s in @(@{Name = "AI Başlat"; File = "ai-start.ps1"; Style = 1}, @{Name = "AI Uyut"; File = "ai-sleep.ps1"; Style = 7})) {
    $lnk = $shell.CreateShortcut((Join-Path $desktop "$($s.Name).lnk"))
    $lnk.TargetPath = $pwsh
    $lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$dir\$($s.File)`""
    $lnk.WorkingDirectory = $dir
    $lnk.WindowStyle = $s.Style
    $lnk.IconLocation = "C:\Program Files (x86)\VMware\VMware Workstation\vmware.exe,0"
    $lnk.Save()
}
Get-ChildItem $desktop -Filter "AI *.lnk" | ForEach-Object Name

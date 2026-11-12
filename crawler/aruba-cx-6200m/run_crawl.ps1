# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Emre Yiğit Taşdelen
# Usage: pwsh run_crawl.ps1 "<root>" "<skip>"   (the password is asked once and never written to disk)
# If the crawler crashes it resumes from the state file after 30 s.
param($Root = "", $Skip = "")
$env:ARUBA_USER = "admin"
# password is asked once and kept only in this process (never stored in a file)
$sec = Read-Host "Device password" -AsSecureString
$env:ARUBA_PASS = [System.Net.NetworkCredential]::new("", $sec).Password
$tag = if ($Root) { $Root -replace '\W+','_' } else { "all" }
while ($true) {
    python "$PSScriptRoot\aruba_crawl.py" --root $Root --skip $Skip
    if (Select-String -Path "$PSScriptRoot\aruba_cli_tree_$tag.md" -Pattern "_Completed._" -Quiet) { break }
    Start-Sleep 30
}

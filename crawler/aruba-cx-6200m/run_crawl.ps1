# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Emre Yiğit Taşdelen
# Kullanim: pwsh run_crawl.ps1 "<root>" "<skip>"   (sifre bir kez sorulur, diske yazilmaz)
# Cokerse 30 sn sonra state'ten devam eder.
param($Root = "", $Skip = "")
$env:ARUBA_USER = "admin"
# password is asked once and kept only in this process (never stored in a file)
$sec = Read-Host "Cihaz sifresi" -AsSecureString
$env:ARUBA_PASS = [System.Net.NetworkCredential]::new("", $sec).Password
$tag = if ($Root) { $Root -replace '\W+','_' } else { "all" }
while ($true) {
    python "$PSScriptRoot\aruba_crawl.py" --root $Root --skip $Skip
    if (Select-String -Path "$PSScriptRoot\aruba_cli_tree_$tag.md" -Pattern "_Tamamlandi._" -Quiet) { break }
    Start-Sleep 30
}

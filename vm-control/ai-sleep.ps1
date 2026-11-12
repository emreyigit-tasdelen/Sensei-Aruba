# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Emre Yiğit Taşdelen
# "AI Uyut": suspends the AI VM immediately (RAM is written to disk and released).
. "$PSScriptRoot\ai-common.ps1"

if (Test-VmRunning) {
    & $VmRun -T ws suspend $Vmx soft
    Write-Log "suspended (manual)"
}

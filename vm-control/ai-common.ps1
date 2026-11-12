# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Emre Yiğit Taşdelen
# Shared settings for the AI VM control scripts.
$VmRun   = "C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe"
$Vmx     = "C:\VMs\Sensei-Aruba\Sensei-Aruba.vmx"
$Dir     = $PSScriptRoot
$Log     = Join-Path $Dir "ai-vm.log"

function Write-Log($msg) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $msg" | Add-Content $Log
    if ((Get-Item $Log).Length -gt 1MB) { Get-Content $Log -Tail 500 | Set-Content $Log }
}

function Test-VmRunning { (& $VmRun list) -contains $Vmx }

# The guest IP is asked from VMware (VMware Tools), never hard-coded; it follows DHCP changes.
function Get-VmIp {
    $ip = (& $VmRun getGuestIPAddress $Vmx -wait 2>$null) -join ""
    if ($ip -match '^\d+\.\d+\.\d+\.\d+$') { $ip } else { $null }
}

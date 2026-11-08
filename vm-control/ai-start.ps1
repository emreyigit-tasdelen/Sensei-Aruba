# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Emre Yiğit Taşdelen
# "AI Başlat": starts or resumes the AI VM, waits for the web UI, opens the browser.
. "$PSScriptRoot\ai-common.ps1"

if (-not (Test-VmRunning)) {
    Write-Host "AI sunucusu uyandiriliyor..."
    $p = Start-Process $VmRun -ArgumentList "-T ws start `"$Vmx`" nogui" -WindowStyle Hidden -PassThru
    $p.WaitForExit(120000) | Out-Null   # vmrun can block on resume; don't hang the shortcut
    Write-Log "start/resume requested (running=$(Test-VmRunning))"
}
Write-Host "Web arayuzu bekleniyor..."
$ip = $null
for ($i = 0; $i -lt 24; $i++) {   # wait for SSH (boot or resume)
    $ip = Get-VmIp
    if ($ip) {
        $out = (& ssh -o BatchMode=yes -o ConnectTimeout=10 -o "HostName=$ip" aruba-bot "sudo -n sh /opt/aruba-bot/wake.sh" 2>$null) -join " "
        if ($out) { break }
    }
    Start-Sleep 5
}
Write-Log "wake: $out"
if ($out -match "https 200") {
    Start-Process "https://$ip"
} else {
    Write-Host "Web arayuzu acilamadi: $out (log: $Log)"
    Read-Host "Kapatmak icin Enter"
}

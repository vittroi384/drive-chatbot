# Drive Chatbot - 개발 환경 검증 스크립트 (v2)
# 사용법: PowerShell에서 .\verify-env.ps1 실행

$ErrorActionPreference = "Continue"

$tools = @(
    @{ Name = "Python";    Cmd = "python --version" },
    @{ Name = "pip";       Cmd = "pip --version" },
    @{ Name = "VS Code";   Cmd = "code --version" },
    @{ Name = "gcloud";    Cmd = "gcloud --version" },
    @{ Name = "Git";       Cmd = "git --version" },
    @{ Name = "Terraform"; Cmd = "terraform --version" }
    # @{ Name = "Docker";    Cmd = "docker --version" }   # Docker 패키징 시 활성화
)

Write-Host "`n========================================" -ForegroundColor Yellow
Write-Host "  Drive Chatbot - Dev Environment Check" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow
Write-Host "Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`n"

$failures = @()
foreach ($t in $tools) {
    Write-Host "[$($t.Name)]" -ForegroundColor Cyan
    try {
        # stderr를 stdout으로 합치고, 결과가 있으면 성공으로 판정 (exit code 무시)
        $output = & cmd /c "$($t.Cmd) 2>&1" | Select-Object -First 3
        if ($output -and $output.Count -gt 0 -and $output[0] -ne "") {
            $output | ForEach-Object { Write-Host "  $_" -ForegroundColor Green }
        } else {
            Write-Host "  NO OUTPUT" -ForegroundColor Red
            $failures += $t.Name
        }
    } catch {
        Write-Host "  NOT FOUND: $($_.Exception.Message)" -ForegroundColor Red
        $failures += $t.Name
    }
    Write-Host ""
}

# PowerShell 정책 확인
Write-Host "[PowerShell ExecutionPolicy]" -ForegroundColor Cyan
$policy = Get-ExecutionPolicy -Scope CurrentUser
if ($policy -eq "RemoteSigned" -or $policy -eq "Unrestricted") {
    Write-Host "  CurrentUser: $policy (OK)" -ForegroundColor Green
} else {
    Write-Host "  CurrentUser: $policy (venv 활성화 막힐 수 있음)" -ForegroundColor Yellow
    $failures += "ExecutionPolicy"
}
Write-Host ""

# gcloud 현재 설정 확인
Write-Host "[gcloud Active Configuration]" -ForegroundColor Cyan
try {
    $gcloudProject = gcloud config get-value project 2>$null
    $gcloudAccount = gcloud config get-value account 2>$null
    Write-Host "  Account: $gcloudAccount" -ForegroundColor Green
    Write-Host "  Project: $gcloudProject" -ForegroundColor Green
} catch {
    Write-Host "  gcloud 설정 확인 실패" -ForegroundColor Red
}
Write-Host ""

# GitHub SSH 연결 확인
Write-Host "[GitHub SSH]" -ForegroundColor Cyan
$sshOutput = ssh -T -o "StrictHostKeyChecking=no" -o "ConnectTimeout=5" git@github.com 2>&1
if ($sshOutput -match "successfully authenticated") {
    Write-Host "  $sshOutput" -ForegroundColor Green
} else {
    Write-Host "  $sshOutput" -ForegroundColor Yellow
}
Write-Host ""

# 작업 디렉토리 확인
Write-Host "[Work Directories]" -ForegroundColor Cyan
@("C:\dev\drive-chatbot", "C:\dev\secrets") | ForEach-Object {
    if (Test-Path $_) {
        Write-Host "  EXISTS: $_" -ForegroundColor Green
    } else {
        Write-Host "  MISSING: $_" -ForegroundColor Red
        $failures += $_
    }
}
Write-Host ""

# 최종 결과
Write-Host "========================================" -ForegroundColor Yellow
if ($failures.Count -eq 0) {
    Write-Host "  [PASS] 모든 항목 정상" -ForegroundColor Green
} else {
    Write-Host "  [WARN] 점검 필요: $($failures -join ', ')" -ForegroundColor Red
}
Write-Host "========================================`n" -ForegroundColor Yellow

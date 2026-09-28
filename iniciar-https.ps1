# Inicia el servidor IPV en HTTPS para la red local (Windows).
# La CA/certificado son solo para desarrollo y red privada; no son certificados públicos.
[CmdletBinding()]
param(
    [switch]$ConfigureNetworkOnly,
    [switch]$Status,       # Muestra el estado del servidor y de la base de datos
    [switch]$Backup,       # Crea una copia de seguridad consistente (API de backup de SQLite)
    [switch]$HealthCheck,  # Devuelve el estado de salud en JSON
    [switch]$AuditLog,     # Muestra los últimos eventos de auditoría
    [switch]$InitSecurity, # Crea .env con un secreto JWT fuerte y el usuario administrador
    [switch]$ShowPin,      # Muestra la huella SHA-256 de la CA local para fijarla en Android
    [switch]$EncryptDb     # Cifra la base de datos con SQLCipher (AES-256) y guarda la clave en .env
)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'iniciar-https.ps1 debe ejecutarse en Windows con PowerShell.' }

$ServerAlias = 'sqlserver'

function Test-IsAdministrator {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [System.Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Configure-LocalNetwork {
    $hostsPath = Join-Path $env:SystemRoot 'System32\drivers\etc\hosts'
    if (Test-Path $hostsPath) {
        $pattern = '^\s*(?!#)\S+\s+.*\b' + [regex]::Escape($ServerAlias) + '\b'
        $hasAlias = Select-String -Path $hostsPath -Pattern $pattern -Quiet
        if (-not $hasAlias) {
            Add-Content -Path $hostsPath -Value "`r`n127.0.0.1`t$ServerAlias # IPV Fichas y Costos local" -Encoding ASCII
            try { & ipconfig.exe /flushdns | Out-Null } catch { }
        }
    }
    $ruleName = 'IPV Fichas y Costos HTTPS 8443 (red local)'
    if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule `
            -DisplayName $ruleName `
            -Direction Inbound `
            -Action Allow `
            -Protocol TCP `
            -LocalPort 8443 `
            -RemoteAddress LocalSubnet `
            -Profile Private, Domain | Out-Null
    }
}

if ($ConfigureNetworkOnly) {
    if (-not (Test-IsAdministrator)) { throw 'La configuración de red requiere permisos de administrador.' }
    Configure-LocalNetwork
    Write-Host "Alias $ServerAlias y regla del firewall configurados para la red local." -ForegroundColor Green
    exit 0
}

# Eleva solo los cambios de hosts/firewall; el servidor Python seguirá con los permisos del usuario.
$adminCommand = $Status -or $Backup -or $HealthCheck -or $AuditLog -or $InitSecurity -or $ShowPin
if (-not $adminCommand -and -not (Test-IsAdministrator)) {
    try {
        $powershellExe = if ($PSVersionTable.PSEdition -eq 'Core') { Join-Path $PSHOME 'pwsh.exe' } else { Join-Path $PSHOME 'powershell.exe' }
        $quotedScript = '"' + $PSCommandPath + '"'
        $networkArgs = "-NoProfile -ExecutionPolicy Bypass -File $quotedScript -ConfigureNetworkOnly"
        Start-Process -FilePath $powershellExe -Verb RunAs -ArgumentList $networkArgs | Out-Null
    } catch {
        Write-Warning 'No se pudo configurar automáticamente hosts/firewall. El servidor podrá funcionar localmente; revisa el acceso de la LAN.'
    }
}
try {
    if (Get-NetConnectionProfile -ErrorAction SilentlyContinue | Where-Object { $_.NetworkCategory -eq 'Public' }) {
        Write-Warning 'Hay una conexión marcada como Pública. Para probar desde otros dispositivos, usa una red confiable y perfil Privado; no habilites acceso en Wi-Fi público.'
    }
} catch { }

function Join-ByteArrays {
    param([System.Collections.Generic.List[byte[]]]$Parts)
    $result = [System.Collections.Generic.List[byte]]::new()
    foreach ($part in $Parts) {
        if ($null -ne $part -and $part.Length -gt 0) { $result.AddRange([byte[]]$part) }
    }
    return ,([byte[]]$result.ToArray())
}

function ConvertTo-DerLength {
    param([int]$Length)
    if ($Length -lt 128) { return ,([byte[]]@([byte]$Length)) }
    $octets = [System.Collections.Generic.List[byte]]::new()
    $remaining = $Length
    while ($remaining -gt 0) {
        $octets.Insert(0, [byte]($remaining -band 0xFF))
        $remaining = [int][Math]::Floor($remaining / 256)
    }
    $result = [System.Collections.Generic.List[byte]]::new()
    $result.Add([byte](0x80 -bor $octets.Count))
    $result.AddRange($octets)
    return ,([byte[]]$result.ToArray())
}

function ConvertTo-DerInteger {
    param([byte[]]$Value)
    if ($null -eq $Value -or $Value.Length -eq 0) { throw 'La clave RSA contiene un parámetro vacío.' }
    $offset = 0
    while ($offset -lt ($Value.Length - 1) -and $Value[$offset] -eq 0) { $offset++ }
    $data = New-Object byte[] ($Value.Length - $offset)
    [Array]::Copy($Value, $offset, $data, 0, $data.Length)
    if (($data[0] -band 0x80) -ne 0) {
        $positive = New-Object byte[] ($data.Length + 1)
        $positive[0] = 0
        [Array]::Copy($data, 0, $positive, 1, $data.Length)
        $data = $positive
    }
    $parts = [System.Collections.Generic.List[byte[]]]::new()
    $parts.Add([byte[]]@(0x02))
    $parts.Add((ConvertTo-DerLength $data.Length))
    $parts.Add([byte[]]$data)
    return Join-ByteArrays $parts
}

function ConvertTo-DerSequence {
    param([System.Collections.Generic.List[byte[]]]$Parts)
    $body = Join-ByteArrays $Parts
    $sequence = [System.Collections.Generic.List[byte[]]]::new()
    $sequence.Add([byte[]]@(0x30))
    $sequence.Add((ConvertTo-DerLength $body.Length))
    $sequence.Add($body)
    return Join-ByteArrays $sequence
}

function ConvertTo-Pem {
    param([string]$Label, [byte[]]$Bytes)
    $base64 = [Convert]::ToBase64String($Bytes)
    $lines = [System.Collections.Generic.List[string]]::new()
    for ($i = 0; $i -lt $base64.Length; $i += 64) {
        $length = [Math]::Min(64, $base64.Length - $i)
        $lines.Add($base64.Substring($i, $length))
    }
    return "-----BEGIN $Label-----`n$($lines -join "`n")`n-----END $Label-----`n"
}

function Export-RsaPrivateKeyPem {
    param([System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate)
    $rsa = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($Certificate)
    if ($null -eq $rsa) { throw 'No se pudo leer la clave privada RSA del certificado.' }
    try {
        $parameters = $rsa.ExportParameters($true)
        $parts = [System.Collections.Generic.List[byte[]]]::new()
        # PKCS#1 RSAPrivateKey: version, n, e, d, p, q, dp, dq e inverseQ.
        $parts.Add([byte[]]@(0x02, 0x01, 0x00))
        foreach ($name in @('Modulus', 'Exponent', 'D', 'P', 'Q', 'DP', 'DQ', 'InverseQ')) {
            $parts.Add((ConvertTo-DerInteger ([byte[]]$parameters.$name)))
        }
        $der = ConvertTo-DerSequence $parts
        return ConvertTo-Pem 'RSA PRIVATE KEY' $der
    } finally {
        $rsa.Dispose()
    }
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# ==========================================================================
#  Configuración (.env) y comandos de administración
# ==========================================================================
$envFile = Join-Path $repoRoot '.env'
function Import-DotEnv {
    if (-not (Test-Path $envFile)) { return }
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$' -and $Matches[2] -ne '') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim('"'), 'Process')
        }
    }
}

function Get-PythonCommand {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) { return @($py.Source) }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return @($py.Source, '-3') }
    throw 'No se encontró Python. Instala Python 3.10+ y vuelve a ejecutar este script.'
}

function Invoke-Py([string]$Code) {
    Import-DotEnv  # carga IPV_DB_KEY y demás variables necesarias para abrir la BD
    $cmd = Get-PythonCommand
    $env:IPV_DB_PATH = Join-Path $repoRoot 'data\ipv.db'
    Push-Location $repoRoot
    try { & $cmd[0] @($cmd | Select-Object -Skip 1) -c $Code } finally { Pop-Location }
}

function Initialize-Security {
    if (Test-Path $envFile) { Write-Host '.env ya existe; no se sobrescribe.' -ForegroundColor Yellow; return }
    $bytes = New-Object byte[] 48
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $secret = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    $email = Read-Host 'Correo del administrador'
    $pwd = Read-Host 'Contraseña del administrador (mín. 10, mayúsculas, números y símbolos)' -AsSecureString
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($pwd))
    $template = Get-Content (Join-Path $repoRoot '.env.example') -Raw
    $template = $template -replace '(?m)^IPV_JWT_SECRET=.*$', "IPV_JWT_SECRET=$secret"
    $template = $template -replace '(?m)^IPV_ADMIN_EMAIL=.*$', "IPV_ADMIN_EMAIL=$email"
    $template = $template -replace '(?m)^IPV_ADMIN_PASSWORD=.*$', "IPV_ADMIN_PASSWORD=$plain"
    Set-Content -Path $envFile -Value $template -Encoding UTF8
    try { & icacls.exe $envFile /inheritance:r /grant:r "$((whoami).Trim()):(M)" | Out-Null } catch { }
    Write-Host '✓ .env creado con secreto JWT de 384 bits (permisos restringidos al usuario actual).' -ForegroundColor Green
    Write-Host '  Tras el primer inicio puede borrar IPV_ADMIN_PASSWORD del archivo .env.' -ForegroundColor Yellow
}

function Protect-Database {
    Import-DotEnv
    if ((Test-ServerHealth).Status -eq 'OK') { throw 'Detenga el servidor antes de cifrar la base de datos.' }
    $cmd = Get-PythonCommand
    & $cmd[0] @($cmd | Select-Object -Skip 1) -c 'import sqlcipher3' 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Instalando el motor SQLCipher (sqlcipher3-wheels)…' -ForegroundColor Cyan
        & $cmd[0] @($cmd | Select-Object -Skip 1) -m pip install --user sqlcipher3-wheels
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo instalar sqlcipher3-wheels.' }
    }
    if (-not $env:IPV_DB_KEY) {
        if (-not (Test-Path $envFile)) { throw 'Primero ejecute -InitSecurity para crear .env.' }
        $bytes = New-Object byte[] 32
        [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        $key = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
        $content = Get-Content $envFile -Raw
        if ($content -match '(?m)^IPV_DB_KEY=') { $content = $content -replace '(?m)^IPV_DB_KEY=.*$', "IPV_DB_KEY=$key" }
        else { $content = $content.TrimEnd() + "`r`nIPV_DB_KEY=$key`r`n" }
        Set-Content -Path $envFile -Value $content -Encoding UTF8
        $env:IPV_DB_KEY = $key
        Write-Host '✓ Clave de cifrado de 256 bits generada y guardada en .env' -ForegroundColor Green
    }
    $env:IPV_DB_PATH = Join-Path $repoRoot 'data\ipv.db'
    Push-Location $repoRoot
    try { & $cmd[0] @($cmd | Select-Object -Skip 1) dbcrypt.py encrypt } finally { Pop-Location }
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n⚠ IMPORTANTE: guarde una copia de IPV_DB_KEY (archivo .env) fuera de este equipo." -ForegroundColor Yellow
        Write-Host '  Sin esa clave la base de datos y sus copias de seguridad NO se pueden recuperar.' -ForegroundColor Yellow
    }
}

function Test-ServerHealth {
    param([string]$Url = 'https://localhost:8443')
    try {
        # La CA local está en el almacén de confianza del usuario: no hace falta omitir la validación TLS.
        $data = Invoke-RestMethod -Uri "$Url/api/health" -TimeoutSec 5
        return [ordered]@{ Status = 'OK'; Version = $data.version; Database = $data.database; TLS = $data.tls; Auth = $data.auth_required }
    } catch {
        return [ordered]@{ Status = 'ERROR'; Message = $_.Exception.Message }
    }
}

function Show-ServerStatus {
    Write-Host "`n═══════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host '  IPV · Fichas y Costos — Estado del servidor' -ForegroundColor Cyan
    Write-Host "═══════════════════════════════════════════════════`n" -ForegroundColor Cyan
    $h = Test-ServerHealth
    if ($h.Status -eq 'OK') {
        Write-Host "  ✓ Operativo · v$($h.Version) · $($h.Database) · TLS: $($h.TLS) · Token API: $($h.Auth)" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Sin respuesta: $($h.Message)" -ForegroundColor Red
    }
    $db = Join-Path $repoRoot 'data\ipv.db'
    if (Test-Path $db) { Write-Host ("  📁 Base de datos: {0:N1} KB" -f ((Get-Item $db).Length / 1KB)) -ForegroundColor Yellow }
    $bk = Join-Path $repoRoot 'data\backups'
    if (Test-Path $bk) { Write-Host "  💾 Copias de seguridad: $((Get-ChildItem $bk -Filter *.db).Count)" -ForegroundColor Yellow }
    Write-Host "  🔐 JWT: $(if (Test-Path $envFile) { 'configurado (.env)' } else { 'no configurado — ejecute -InitSecurity' })" -ForegroundColor Yellow
    if (Test-Path $db) {
        $fs = [System.IO.File]::Open($db, 'Open', 'Read', 'ReadWrite')  # el servidor puede tenerla abierta
        try { $head = New-Object byte[] 15; [void]$fs.Read($head, 0, 15) } finally { $fs.Dispose() }
        $plain = [System.Text.Encoding]::ASCII.GetString($head) -eq 'SQLite format 3'
        if ($plain) { Write-Host '  🔓 Base de datos SIN cifrar — ejecute -EncryptDb' -ForegroundColor Red }
        else { Write-Host '  🔒 Base de datos cifrada (SQLCipher AES-256)' -ForegroundColor Green }
    }
    Write-Host ''
}

if ($InitSecurity) { Initialize-Security; exit 0 }
if ($EncryptDb) { Protect-Database; exit $LASTEXITCODE }
if ($ShowPin) {
    $ca = Join-Path $repoRoot 'certs\ipv-local-root-ca.cer'
    if (-not (Test-Path $ca)) { throw 'Aún no existe la CA local. Inicie el servidor una vez para generarla.' }
    $cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($ca)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $hex = ($sha.ComputeHash($cert.RawData) | ForEach-Object { $_.ToString('X2') }) -join ''
    Write-Host "`nHuella SHA-256 de la CA local (Android → Configuración → Seguridad):" -ForegroundColor Cyan
    Write-Host "  $hex" -ForegroundColor Green
    Write-Host "  $(($hex -split '(.{2})' | Where-Object { $_ }) -join ':')" -ForegroundColor DarkGray
    Write-Host "  Válida hasta: $($cert.NotAfter)`n" -ForegroundColor Yellow
    exit 0
}
if ($Status) { Show-ServerStatus; exit 0 }
if ($HealthCheck) { Test-ServerHealth | ConvertTo-Json; exit 0 }
if ($Backup) {
    Invoke-Py 'import server; i = server.auto_backup(); print("Copia creada:", i["filename"], i["size"], "bytes") if i else print("No se pudo crear la copia.")'
    exit 0
}
if ($AuditLog) {
    Invoke-Py 'import dbcrypt, server; c = dbcrypt.connect(server.DB_PATH); [print(*r, sep="  |  ") for r in c.execute("SELECT timestamp, action, client, user_email, details FROM audit_log ORDER BY id DESC LIMIT 40")]'
    exit 0
}
Import-DotEnv
$certDir = Join-Path $repoRoot 'certs'
$dataDir = Join-Path $repoRoot 'data'
New-Item -ItemType Directory -Path $certDir -Force | Out-Null
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null

$rootSubject = 'CN=IPV Fichas Local Development CA'
$root = Get-ChildItem Cert:\CurrentUser\My | Where-Object {
    $_.Subject -eq $rootSubject -and $_.HasPrivateKey -and $_.NotAfter -gt (Get-Date)
} | Sort-Object NotAfter -Descending | Select-Object -First 1
if ($null -eq $root) {
    Write-Host 'Creando autoridad certificadora local de desarrollo…' -ForegroundColor Cyan
    $root = New-SelfSignedCertificate `
        -Type Custom `
        -Subject $rootSubject `
        -KeyAlgorithm RSA `
        -KeyLength 3072 `
        -HashAlgorithm SHA256 `
        -KeyUsage KeyCertSign,CrlSign,DigitalSignature `
        -KeyExportPolicy Exportable `
        -NotAfter (Get-Date).AddYears(8) `
        -CertStoreLocation 'Cert:\CurrentUser\My' `
        -TextExtension @('2.5.29.19={critical}{text}ca=TRUE&pathlength=1')
}

$rootCerPath = Join-Path $certDir 'ipv-local-root-ca.cer'
[System.IO.File]::WriteAllBytes($rootCerPath, $root.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert))
$trustedRoot = Get-ChildItem Cert:\CurrentUser\Root | Where-Object { $_.Thumbprint -eq $root.Thumbprint } | Select-Object -First 1
if ($null -eq $trustedRoot) { Import-Certificate -FilePath $rootCerPath -CertStoreLocation 'Cert:\CurrentUser\Root' | Out-Null }

$lanIps = @()
try {
    $lanIps = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notmatch '^(127|169\.254)\.' } |
        Select-Object -ExpandProperty IPAddress -Unique)
} catch {
    Write-Warning 'No se pudieron enumerar las direcciones de red; el certificado aún incluirá los nombres locales y del emulador.'
}

$sanEntries = [System.Collections.Generic.List[string]]::new()
$sanEntries.Add("DNS=$ServerAlias")
$sanEntries.Add('DNS=localhost')
if ($env:COMPUTERNAME) { $sanEntries.Add("DNS=$($env:COMPUTERNAME)") }
$ips = @('127.0.0.1', '10.0.2.2') + $lanIps
foreach ($ip in ($ips | Select-Object -Unique)) { $sanEntries.Add("IPAddress=$ip") }
$sanExtension = '2.5.29.17={text}' + ($sanEntries -join '&')

Write-Host "Creando certificado HTTPS para $ServerAlias y las direcciones locales…" -ForegroundColor Cyan
$leaf = New-SelfSignedCertificate `
    -Type Custom `
    -Subject "CN=$ServerAlias" `
    -Signer $root `
    -KeyAlgorithm RSA `
    -KeyLength 2048 `
    -HashAlgorithm SHA256 `
    -KeyUsage DigitalSignature,KeyEncipherment `
    -KeyExportPolicy Exportable `
    -NotAfter (Get-Date).AddYears(2) `
    -CertStoreLocation 'Cert:\CurrentUser\My' `
    -TextExtension @(
        '2.5.29.19={critical}{text}ca=FALSE',
        '2.5.29.37={text}1.3.6.1.5.5.7.3.1',
        $sanExtension
    )

$leafPemPath = Join-Path $certDir 'ipv-server-cert.pem'
$keyPemPath = Join-Path $certDir 'ipv-server-key.pem'
$certificatePem = (ConvertTo-Pem 'CERTIFICATE' $leaf.RawData) + (ConvertTo-Pem 'CERTIFICATE' $root.RawData)
[System.IO.File]::WriteAllText($leafPemPath, $certificatePem, [System.Text.Encoding]::ASCII)
[System.IO.File]::WriteAllText($keyPemPath, (Export-RsaPrivateKeyPem $leaf), [System.Text.Encoding]::ASCII)
try {
    $currentUser = (whoami).Trim()
    & icacls.exe $keyPemPath /inheritance:r /grant:r "${currentUser}:(M)" | Out-Null
} catch {
    Write-Warning 'No se pudo restringir automáticamente la clave PEM; protege certs\ipv-server-key.pem.'
}

# Borra certificados de servidor anteriores firmados por esta misma CA; conserva el actual.
Get-ChildItem Cert:\CurrentUser\My | Where-Object {
    $_.Thumbprint -ne $leaf.Thumbprint -and $_.Subject -eq "CN=$ServerAlias" -and $_.Issuer -eq $root.Subject
} | Remove-Item -ErrorAction SilentlyContinue

$python = Get-Command python -ErrorAction SilentlyContinue
$pythonArgs = @()
if ($null -eq $python) {
    $python = Get-Command py -ErrorAction SilentlyContinue
    if ($null -eq $python) { throw 'No se encontró Python. Instala Python 3.10+ y vuelve a ejecutar este script.' }
    $pythonArgs += '-3'
}

$env:IPV_HOST = '0.0.0.0'
$env:PORT = '8443'
$env:IPV_DB_PATH = Join-Path $dataDir 'ipv.db'
$env:IPV_TLS_CERT = $leafPemPath
$env:IPV_TLS_KEY = $keyPemPath
$env:PYTHONUNBUFFERED = '1'

Write-Host ''
Write-Host 'Servidor HTTPS listo en la red local.' -ForegroundColor Green
Write-Host "En esta PC:       https://${ServerAlias}:8443"
Write-Host 'También:          https://localhost:8443'
foreach ($ip in ($lanIps | Select-Object -Unique)) { Write-Host "Desde la red:     https://${ip}:8443" }
Write-Host ''
Write-Host "CA pública para instalar en móviles/otras PCs: $rootCerPath" -ForegroundColor Yellow
Write-Host 'La clave privada certs\ipv-server-key.pem no debe copiarse ni compartirse.' -ForegroundColor Yellow
Write-Host 'Instala la CA pública en cada cliente y no publiques el puerto en Internet.' -ForegroundColor Yellow
Write-Host 'Detén el servidor con Ctrl+C.'
Write-Host ''

Set-Location $repoRoot
$pythonArgs += (Join-Path $repoRoot 'server.py')
& $python.Source @pythonArgs

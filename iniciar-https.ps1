# Inicia el servidor IPV en HTTPS para la red local (Windows).
# La CA/certificado son solo para desarrollo y red privada; no son certificados públicos.
[CmdletBinding()]
param([switch]$ConfigureNetworkOnly)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'iniciar-https.ps1 debe ejecutarse en Windows con PowerShell.' }

function Test-IsAdministrator {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [System.Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Configure-LocalNetwork {
    $hostsPath = Join-Path $env:SystemRoot 'System32\drivers\etc\hosts'
    if (Test-Path $hostsPath) {
        $hasAlias = Select-String -Path $hostsPath -Pattern '^\s*(?!#)\S+\s+.*\bsqlserver\b' -Quiet
        if (-not $hasAlias) {
            Add-Content -Path $hostsPath -Value "`r`n127.0.0.1`t sqlserver # IPV Fichas y Costos local" -Encoding ASCII
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
    Write-Host 'Alias sqlserver y regla del firewall configurados para la red local.' -ForegroundColor Green
    exit 0
}

# Eleva solo los cambios de hosts/firewall; el servidor Python seguirá con los permisos del usuario.
if (-not (Test-IsAdministrator)) {
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
$sanEntries.Add('DNS=sqlserver')
$sanEntries.Add('DNS=localhost')
if ($env:COMPUTERNAME) { $sanEntries.Add("DNS=$($env:COMPUTERNAME)") }
$ips = @('127.0.0.1', '10.0.2.2') + $lanIps
foreach ($ip in ($ips | Select-Object -Unique)) { $sanEntries.Add("IPAddress=$ip") }
$sanExtension = '2.5.29.17={text}' + ($sanEntries -join '&')

Write-Host 'Creando certificado HTTPS para sqlserver y las direcciones locales…' -ForegroundColor Cyan
$leaf = New-SelfSignedCertificate `
    -Type Custom `
    -Subject 'CN=sqlserver' `
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
    $_.Thumbprint -ne $leaf.Thumbprint -and $_.Subject -eq 'CN=sqlserver' -and $_.Issuer -eq $root.Subject
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
Write-Host 'En esta PC:       https://sqlserver:8443'
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

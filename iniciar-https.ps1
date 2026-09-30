# ==========================================================================
#  IPV · Fichas y Costos — Acceso seguro por HTTPS (Windows)
#  Autor: Ing. Yosvany Hernández Quintero
#
#  Crea una autoridad certificadora local, emite el certificado del servidor
#  y arranca el servidor cifrado para la red local.
#
#  La CA y el certificado son para red privada (LAN); no son certificados
#  públicos y no deben publicarse en Internet.
#
#  Ayuda completa:  .\iniciar-https.ps1 -Help
# ==========================================================================
[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8443,              # Puerto HTTPS
    [ValidateRange(0, 65535)]
    [int]$RedirectPort = 8080,      # Puerto HTTP que redirige a HTTPS (0 o -NoRedirect para desactivar)
    [switch]$NoRedirect,            # No levantar la redirección HTTP → HTTPS
    [switch]$Tls13Only,             # Exigir TLS 1.3 (clientes modernos); por defecto TLS 1.2+
    [switch]$Renew,                 # Forzar certificados nuevos (CA y servidor)
    [switch]$Open,                  # Abrir el navegador al arrancar
    [switch]$Check,                 # Diagnóstico completo del acceso seguro
    [switch]$Stop,                  # Detener el servidor que escucha en el puerto
    [switch]$ConfigureNetworkOnly,  # Uso interno: solo hosts + firewall (elevado)
    [switch]$Status,                # Estado del servidor y de la base de datos
    [switch]$Backup,                # Copia de seguridad consistente (API de backup de SQLite)
    [switch]$HealthCheck,           # Estado de salud en JSON
    [switch]$AuditLog,              # Últimos eventos de auditoría
    [switch]$InitSecurity,          # Crea .env con secreto JWT fuerte y usuario administrador
    [switch]$ShowPin,               # Huella SHA-256 de la CA local (para fijarla en Android)
    [string]$ExportCa = '',         # Copia la CA a una carpeta (USB, red…) para instalarla en otros equipos
    [switch]$EncryptDb,             # Cifra la base de datos con SQLCipher (AES-256)
    [switch]$Help                   # Muestra todos los comandos
)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'iniciar-https.ps1 debe ejecutarse en Windows con PowerShell.' }

$ServerAlias = 'sqlserver'
$RootSubject = 'CN=IPV Fichas Local Development CA'
$RenewDays = 30   # se renueva el certificado cuando le quedan menos días que esto

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$certDir = Join-Path $repoRoot 'certs'
$dataDir = Join-Path $repoRoot 'data'
$envFile = Join-Path $repoRoot '.env'
$rootCerPath = Join-Path $certDir 'ipv-local-root-ca.cer'
$leafPemPath = Join-Path $certDir 'ipv-server-cert.pem'
$keyPemPath = Join-Path $certDir 'ipv-server-key.pem'
if ($NoRedirect) { $RedirectPort = 0 }

# ==========================================================================
#  Salida con estilo
# ==========================================================================
function Write-Titulo { param([string]$Text)
    Write-Host ''
    Write-Host "═══ $Text " -ForegroundColor Cyan
}
function Write-Exito { param([string]$Text) Write-Host "  ✓ $Text" -ForegroundColor Green }
function Write-Aviso { param([string]$Text) Write-Host "  ⚠ $Text" -ForegroundColor Yellow }
function Write-Fallo { param([string]$Text) Write-Host "  ✗ $Text" -ForegroundColor Red }
function Write-Detalle { param([string]$Text) Write-Host "    $Text" -ForegroundColor DarkGray }

function Show-Help {
    $texto = @'
IPV · Fichas y Costos — iniciar-https.ps1

USO HABITUAL
  .\iniciar-https.ps1                    Arranca el servidor HTTPS (crea/renueva certificados si hace falta)
  .\iniciar-https.ps1 -Open              Igual, y abre el navegador
  .\iniciar-https.ps1 -Check             Diagnóstico completo; código 0=correcto, 2=avisos, 1=problemas
  .\iniciar-https.ps1 -Status            Estado del servidor y de la base de datos
  .\iniciar-https.ps1 -Stop              Detiene solo un proceso IPV verificable de este repositorio

PRIMERA INSTALACIÓN
  .\iniciar-https.ps1 -InitSecurity      Crea .env con secreto JWT de 384 bits y el usuario administrador
  .\iniciar-https.ps1                    Primer arranque: crea la CA local y el certificado del servidor
  .\iniciar-https.ps1 -EncryptDb         Cifra la base de datos (SQLCipher AES-256) con el servidor detenido

CERTIFICADOS Y CLIENTES
  .\iniciar-https.ps1 -Renew             Fuerza certificados nuevos (CA + servidor) y limpia los antiguos
  .\iniciar-https.ps1 -ShowPin           Huella SHA-256 de la CA (para fijarla en el móvil)
  .\iniciar-https.ps1 -ExportCa 'E:\'    Copia la CA a un USB o carpeta de red para instalarla en otros equipos

MANTENIMIENTO
  .\iniciar-https.ps1 -Backup            Copia de seguridad; devuelve código distinto de cero si falla o falla la réplica
  .\iniciar-https.ps1 -HealthCheck       Salud del servidor en JSON (0=OK, 1=sin respuesta)
  .\iniciar-https.ps1 -AuditLog          Últimos 40 eventos de auditoría

OPCIONES
  -Port 8443           Puerto HTTPS (por defecto 8443)
  -RedirectPort 8080   Puerto HTTP que reenvía a HTTPS (0 para desactivarlo)
  -NoRedirect          No levantar la redirección HTTP → HTTPS
  -Tls13Only           Exigir TLS 1.3 (solo clientes modernos)
  -Open                Abrir el navegador al arrancar

Seleccione una sola operación de mantenimiento por ejecución. Los puertos deben estar
entre 1 y 65535 y el puerto de redirección debe ser distinto del HTTPS.

Guía paso a paso: docs\acceso-seguro-https.md
'@
    Write-Host $texto
}

if ($Help) { Show-Help; exit 0 }

# Las opciones operativas son excluyentes para impedir que, por ejemplo, -Stop
# o -Backup parezcan ejecutados cuando el script solo terminó mostrando -Status.
$selectedModes = @(
    [bool]$Check, [bool]$Stop, [bool]$ConfigureNetworkOnly, [bool]$Status,
    [bool]$Backup, [bool]$HealthCheck, [bool]$AuditLog, [bool]$InitSecurity,
    [bool]$ShowPin, [bool]$EncryptDb, [bool](-not [string]::IsNullOrWhiteSpace($ExportCa))
) | Where-Object { $_ }
if ($selectedModes.Count -gt 1) {
    throw 'Seleccione una sola operación: -Check, -Stop, -Status, -Backup, -HealthCheck, -AuditLog, -InitSecurity, -ShowPin, -ExportCa o -EncryptDb.'
}
if ($RedirectPort -ne 0 -and $RedirectPort -eq $Port) {
    throw 'El puerto HTTP de redirección debe ser distinto del puerto HTTPS.'
}
# ==========================================================================
#  Red local: alias en hosts y regla de firewall
# ==========================================================================
function Test-IsAdministrator {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [System.Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-LanIPv4 {
    try {
        return @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -notmatch '^(127|169\.254)\.' } |
            Select-Object -ExpandProperty IPAddress -Unique)
    } catch {
        Write-Aviso 'No se pudieron enumerar las direcciones de red; el certificado incluirá solo los nombres locales.'
        return @()
    }
}

function Get-FirewallRuleName { param([int]$TcpPort) return "IPV Fichas y Costos HTTPS $TcpPort (red local)" }

function Test-LocalNetworkConfigured {
    param([int]$HttpsPort = 8443, [int]$HttpPort = 0)
    $hostsPath = Join-Path $env:SystemRoot 'System32\drivers\etc\hosts'
    $hostPattern = '^\s*(?!#)\S+\s+.*\b' + [regex]::Escape($ServerAlias) + '\b'
    $hostLines = if (Test-Path $hostsPath) { @(Select-String -Path $hostsPath -Pattern $hostPattern -ErrorAction SilentlyContinue) } else { @() }
    $hostReady = $hostLines.Count -gt 0
    if ($hostReady -and -not ($hostLines | Where-Object { $_.Line -match ('^\s*127\.0\.0\.1\s+' + [regex]::Escape($ServerAlias) + '(?:\s|$)') })) {
        Write-Aviso "El alias $ServerAlias ya está definido, pero apunta a otra dirección; no se cambiará sin intervención manual."
    }
    foreach ($tcpPort in @($HttpsPort, $HttpPort)) {
        if ($tcpPort -le 0) { continue }
        $rule = Get-NetFirewallRule -DisplayName (Get-FirewallRuleName $tcpPort) -ErrorAction SilentlyContinue
        if (-not $rule -or $rule.Enabled -ne 'True') { return $false }
    }
    return $hostReady
}

function Set-LocalNetwork {
    param([int]$HttpsPort = 8443, [int]$HttpPort = 0)
    $hostsPath = Join-Path $env:SystemRoot 'System32\drivers\etc\hosts'
    if (Test-Path $hostsPath) {
        $pattern = '^\s*(?!#)\S+\s+.*\b' + [regex]::Escape($ServerAlias) + '\b'
        $aliasLines = @(Select-String -Path $hostsPath -Pattern $pattern -ErrorAction SilentlyContinue)
        $expectedPattern = '^\s*127\.0\.0\.1\s+' + [regex]::Escape($ServerAlias) + '(?:\s|$)'
        if (-not ($aliasLines | Where-Object { $_.Line -match $expectedPattern })) {
            if ($aliasLines.Count -gt 0) {
                Write-Aviso "El alias $ServerAlias ya apunta a otra dirección en hosts; no se cambiará automáticamente. Revise $hostsPath."
            } else {
                Add-Content -Path $hostsPath -Value "`r`n127.0.0.1`t$ServerAlias # IPV Fichas y Costos local" -Encoding ASCII
                try { & ipconfig.exe /flushdns | Out-Null } catch { }
            }
        }
    }
    foreach ($tcpPort in @($HttpsPort, $HttpPort)) {
        if ($tcpPort -le 0) { continue }
        $ruleName = Get-FirewallRuleName $tcpPort
        if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
            New-NetFirewallRule `
                -DisplayName $ruleName `
                -Direction Inbound `
                -Action Allow `
                -Protocol TCP `
                -LocalPort $tcpPort `
                -RemoteAddress LocalSubnet `
                -Profile Private, Domain | Out-Null
        }
    }
}

# ==========================================================================
#  Exportación de certificados a PEM (DER a mano: sin dependencias externas)
# ==========================================================================
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
    $parameters = $null
    $parts = $null
    $der = $null
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
        if ($null -ne $parameters) {
            foreach ($name in @('Modulus', 'Exponent', 'D', 'P', 'Q', 'DP', 'DQ', 'InverseQ')) {
                if ($null -ne $parameters.$name) { [Array]::Clear($parameters.$name, 0, $parameters.$name.Length) }
            }
        }
        if ($null -ne $parts) { foreach ($part in $parts) { if ($part.Length -gt 0) { [Array]::Clear($part, 0, $part.Length) } } }
        if ($null -ne $der) { [Array]::Clear($der, 0, $der.Length) }
        $rsa.Dispose()
    }
}

# ==========================================================================
#  Certificados: crear, reutilizar y publicar
# ==========================================================================
function Get-SanEntries {
    $entries = [System.Collections.Generic.List[string]]::new()
    $entries.Add("DNS=$ServerAlias")
    $entries.Add('DNS=localhost')
    if ($env:COMPUTERNAME) { $entries.Add("DNS=$($env:COMPUTERNAME)") }
    $ips = @('127.0.0.1', '10.0.2.2') + (Get-LanIPv4)   # 10.0.2.2 = el PC visto desde el emulador de Android
    foreach ($ip in ($ips | Select-Object -Unique)) { $entries.Add("IPAddress=$ip") }
    return $entries
}

function Get-LocalCa {
    return Get-ChildItem Cert:\CurrentUser\My | Where-Object {
        $_.Subject -eq $RootSubject -and $_.HasPrivateKey -and $_.NotAfter -gt (Get-Date)
    } | Sort-Object NotAfter -Descending | Select-Object -First 1
}

function Get-ServerCert {
    return Get-ChildItem Cert:\CurrentUser\My | Where-Object {
        $_.Subject -eq "CN=$ServerAlias" -and $_.Issuer -eq $RootSubject -and $_.HasPrivateKey
    } | Sort-Object NotAfter -Descending | Select-Object -First 1
}

function Get-CertSanText {
    param([System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate)
    if ($null -eq $Certificate) { return '' }
    $texts = @()
    foreach ($ext in $Certificate.Extensions) {
        if ($ext.Oid.Value -eq '2.5.29.17') { $texts += $ext.Format($true) }
    }
    return ($texts -join "`n")
}

function Test-CertCoversNames {
    # Comprueba que el certificado ya cubre todos los nombres/IPs actuales del equipo.
    param([System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate,
          [System.Collections.Generic.List[string]]$Entries)
    $sanText = Get-CertSanText $Certificate
    if ([string]::IsNullOrWhiteSpace($sanText)) { return $false }
    foreach ($entry in $Entries) {
        $parts = $entry -split '=', 2
        if ($parts.Count -ne 2) { return $false }
        $value = [regex]::Escape($parts[1])
        if ($parts[0] -eq 'IPAddress') { $pattern = "(?<![0-9.])$value(?![0-9.])" }
        else { $pattern = "(?<![A-Za-z0-9.-])$value(?![A-Za-z0-9.-])" }
        if ($sanText -notmatch $pattern) { return $false }
    }
    return $true
}

function New-LocalCa {
    Write-Host 'Creando autoridad certificadora local…' -ForegroundColor Cyan
    return New-SelfSignedCertificate `
        -Type Custom `
        -Subject $RootSubject `
        -KeyAlgorithm RSA `
        -KeyLength 3072 `
        -HashAlgorithm SHA256 `
        -KeyUsage KeyCertSign, CrlSign, DigitalSignature `
        -KeyExportPolicy Exportable `
        -NotAfter (Get-Date).AddYears(8) `
        -CertStoreLocation 'Cert:\CurrentUser\My' `
        -TextExtension @('2.5.29.19={critical}{text}ca=TRUE&pathlength=1')
}

function New-ServerCert {
    param([System.Security.Cryptography.X509Certificates.X509Certificate2]$Ca,
          [System.Collections.Generic.List[string]]$Entries)
    Write-Host "Emitiendo certificado HTTPS para $ServerAlias y las direcciones locales…" -ForegroundColor Cyan
    $sanExtension = '2.5.29.17={text}' + ($Entries -join '&')
    return New-SelfSignedCertificate `
        -Type Custom `
        -Subject "CN=$ServerAlias" `
        -Signer $Ca `
        -KeyAlgorithm RSA `
        -KeyLength 2048 `
        -HashAlgorithm SHA256 `
        -KeyUsage DigitalSignature, KeyEncipherment `
        -KeyExportPolicy Exportable `
        -NotAfter (Get-Date).AddYears(2) `
        -CertStoreLocation 'Cert:\CurrentUser\My' `
        -TextExtension @(
            '2.5.29.19={critical}{text}ca=FALSE',
            '2.5.29.37={text}1.3.6.1.5.5.7.3.1',
            $sanExtension
        )
}

function Set-PrivateFilePermissions {
    param([string]$Path)
    $sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $grant = '*{0}:(M)' -f $sid
    & icacls.exe $Path /inheritance:r /grant:r $grant | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "No se pudieron restringir los permisos del archivo secreto '$Path'." }
}

function Export-ServerPem {
    param([System.Security.Cryptography.X509Certificates.X509Certificate2]$Leaf,
          [System.Security.Cryptography.X509Certificates.X509Certificate2]$Ca)
    $nonce = [guid]::NewGuid().ToString('N')
    $certTemp = "$leafPemPath.$nonce.tmp"
    $keyTemp = "$keyPemPath.$nonce.tmp"
    try {
        $certificatePem = (ConvertTo-Pem 'CERTIFICATE' $Leaf.RawData) + (ConvertTo-Pem 'CERTIFICATE' $Ca.RawData)
        [System.IO.File]::WriteAllText($certTemp, $certificatePem, [System.Text.Encoding]::ASCII)
        $privatePem = Export-RsaPrivateKeyPem $Leaf
        [System.IO.File]::WriteAllText($keyTemp, $privatePem, [System.Text.Encoding]::ASCII)
        $privatePem = $null
        Set-PrivateFilePermissions -Path $keyTemp
        Move-Item -LiteralPath $certTemp -Destination $leafPemPath -Force -ErrorAction Stop
        Move-Item -LiteralPath $keyTemp -Destination $keyPemPath -Force -ErrorAction Stop
    } catch {
        # Si solo uno de los dos archivos pudo publicarse, elimine el par para
        # forzar una regeneración segura en el siguiente inicio.
        Remove-Item -LiteralPath $leafPemPath, $keyPemPath -Force -ErrorAction SilentlyContinue
        throw
    } finally {
        foreach ($temp in @($certTemp, $keyTemp)) {
            if (Test-Path $temp) { Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue }
        }
    }
}

function Get-CaPin {
    if (-not (Test-Path $rootCerPath)) { return '' }
    $cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($rootCerPath)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    return (($sha.ComputeHash($cert.RawData) | ForEach-Object { $_.ToString('X2') }) -join '')
}

function Export-CaFile {
    param([string]$Destination)
    if (-not (Test-Path $rootCerPath)) { throw 'Aún no existe la CA local. Arranque el servidor una vez para generarla.' }
    if (-not (Test-Path $Destination)) { New-Item -ItemType Directory -Path $Destination -Force | Out-Null }
    $target = Join-Path $Destination 'ipv-local-root-ca.cer'
    Copy-Item -Path $rootCerPath -Destination $target -Force
    $readme = Join-Path $Destination 'COMO-INSTALAR-LA-CA.txt'
    $pin = Get-CaPin
    $texto = @"
IPV · Fichas y Costos — Certificado de la autoridad local
=========================================================

Archivo: ipv-local-root-ca.cer
Huella SHA-256: $pin

WINDOWS (otra PC de la red)
  1. Doble clic en ipv-local-root-ca.cer → Instalar certificado.
  2. Ubicación: Usuario actual → Colocar todos los certificados en el siguiente almacén.
  3. Examinar → Entidades de certificación raíz de confianza → Aceptar → Siguiente → Finalizar.
  4. Abrir https://${ServerAlias}:$Port (o https://IP-DEL-SERVIDOR:$Port).
     Si el nombre $ServerAlias no resuelve, use la IP del servidor.

ANDROID (teléfono o tableta)
  1. Copie este archivo al teléfono (cable, correo o USB).
  2. Ajustes → Seguridad → Cifrado y credenciales → Instalar un certificado → Certificado de CA.
  3. Seleccione ipv-local-root-ca.cer y acepte el aviso.
  4. En la app IPV escriba la dirección https://IP-DEL-SERVIDOR:$Port

Este certificado solo sirve para la red local. Nunca publique el servidor en Internet
ni comparta el archivo certs\ipv-server-key.pem.
"@
    Set-Content -Path $readme -Value $texto -Encoding UTF8
    Write-Exito "CA copiada en $target"
    Write-Exito "Instrucciones en $readme"
}

# ==========================================================================
#  Configuración (.env), Python y base de datos
# ==========================================================================
function Get-ProcessEnvironmentSnapshot {
    $snapshot = @{}
    foreach ($entry in Get-ChildItem Env:) { $snapshot[$entry.Name] = $entry.Value }
    return $snapshot
}

function Restore-ProcessEnvironment {
    param([hashtable]$Snapshot)
    foreach ($entry in @(Get-ChildItem Env:)) {
        if (-not $Snapshot.ContainsKey($entry.Name)) {
            [Environment]::SetEnvironmentVariable($entry.Name, $null, 'Process')
        }
    }
    foreach ($name in $Snapshot.Keys) {
        [Environment]::SetEnvironmentVariable($name, [string]$Snapshot[$name], 'Process')
    }
}

function Import-DotEnv {
    if (-not (Test-Path $envFile)) { return }
    foreach ($line in Get-Content -Path $envFile -ErrorAction Stop) {
        $line = ([string]$line).Trim().TrimStart([char]0xFEFF)
        if (-not $line -or $line.StartsWith('#')) { continue }
        if ($line -notmatch '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') { continue }
        $name = $Matches[1]
        $value = $Matches[2]
        if ($value.Length -ge 2 -and (($value[0] -eq '"' -and $value[$value.Length - 1] -eq '"') -or
                                      ($value[0] -eq "'" -and $value[$value.Length - 1] -eq "'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        # Asignar también valores vacíos evita reutilizar inadvertidamente un secreto heredado.
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
}

function Test-PythonExecutable {
    # Sondea un intérprete con 'python -V' usando System.Diagnostics.Process.
    # No usa el operador & ni $LASTEXITCODE porque, al lanzar el script con
    # 'powershell -File', esas construcciones pueden fallar silenciosamente
    # con la ruta del .venv y descartar intérpretes válidos.
    param([string]$Exe, [string[]]$BaseArgs)
    if ([string]::IsNullOrWhiteSpace($Exe)) { return $null }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Exe
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $argParts = @()
    foreach ($a in @($BaseArgs)) {
        if ($null -eq $a) { continue }
        $s = [string]$a
        if ($s -match '[\s"]') { $argParts += '"' + ($s -replace '"', '\"') + '"' }
        else { $argParts += $s }
    }
    $argParts += '-V'
    $psi.Arguments = ($argParts -join ' ')
    $proc = $null
    try {
        $proc = [System.Diagnostics.Process]::Start($psi)
        $stdout = $proc.StandardOutput.ReadToEnd()
        $stderr = $proc.StandardError.ReadToEnd()
        if (-not $proc.WaitForExit(10000)) {
            try { $proc.Kill() } catch { }
            return $null
        }
        if ($proc.ExitCode -ne 0) { return $null }
        $text = ($stdout + "`n" + $stderr)
        if ($text -match 'Python\s+(\d+)\.(\d+)\.(\d+)') {
            return [pscustomobject]@{
                Version = "$($Matches[1]).$($Matches[2]).$($Matches[3])"
                Major   = [int]$Matches[1]
                Minor   = [int]$Matches[2]
            }
        }
        return $null
    } catch {
        return $null
    } finally {
        if ($null -ne $proc) { $proc.Dispose() }
    }
}

function Get-PythonCommand {
    # Devuelve un [string[]] donde el primer elemento es el ejecutable y los
    # siguientes son argumentos base (por ejemplo, 'py -3'). La verificación
    # se hace con Test-PythonExecutable (Process), no con '& $exe ...'.
    $candidates = [System.Collections.Generic.List[string[]]]::new()

    $venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venvPython) { $candidates.Add([string[]]@($venvPython)) }

    $launcher = Get-Command 'py' -ErrorAction SilentlyContinue -CommandType Application | Select-Object -First 1
    if ($launcher -and $launcher.Source) { $candidates.Add([string[]]@([string]$launcher.Source, '-3')) }

    foreach ($name in @('python', 'python3')) {
        $found = Get-Command $name -ErrorAction SilentlyContinue -CommandType Application | Select-Object -First 1
        if ($found -and $found.Source) { $candidates.Add([string[]]@([string]$found.Source)) }
    }

    foreach ($candidate in $candidates) {
        if ($null -eq $candidate -or $candidate.Length -eq 0) { continue }
        $exe = [string]$candidate[0]
        if ([string]::IsNullOrWhiteSpace($exe)) { continue }
        $baseArgs = @()
        if ($candidate.Length -gt 1) { $baseArgs = [string[]]$candidate[1..($candidate.Length - 1)] }
        $info = Test-PythonExecutable -Exe $exe -BaseArgs $baseArgs
        if ($null -eq $info) { continue }
        if ($info.Major -gt 3 -or ($info.Major -eq 3 -and $info.Minor -ge 10)) { return ,$candidate }
    }
    throw "No se encontró una instalación funcional de Python 3.10 o superior. Verifique '$venvPython' o instale Python y asegúrese de que 'python' esté en el PATH."
}

function Get-PythonVersion {
    try {
        $cmd = Get-PythonCommand
        $exe = [string]$cmd[0]
        $baseArgs = @()
        if ($cmd.Length -gt 1) { $baseArgs = [string[]]$cmd[1..($cmd.Length - 1)] }
        $info = Test-PythonExecutable -Exe $exe -BaseArgs $baseArgs
        if ($info) { return $info.Version }
        return ''
    } catch { return '' }
}

function Invoke-Py([string]$Code) {
    $snapshot = Get-ProcessEnvironmentSnapshot
    try {
        Import-DotEnv  # carga secretos solo mientras vive el proceso Python
        $cmd = Get-PythonCommand
        $exe = [string]$cmd[0]
        $baseArgs = @()
        if ($cmd.Length -gt 1) { $baseArgs = [string[]]$cmd[1..($cmd.Length - 1)] }
        $env:IPV_DB_PATH = Join-Path $repoRoot 'data\ipv.db'
        Push-Location $repoRoot
        try { & $exe @baseArgs '-c' $Code } finally { Pop-Location }
    } finally {
        Restore-ProcessEnvironment $snapshot
    }
}

function Initialize-Security {
    if (Test-Path $envFile) { Write-Aviso '.env ya existe; no se sobrescribe.'; return }
    $templatePath = Join-Path $repoRoot '.env.example'
    if (-not (Test-Path $templatePath)) { throw "No se encontró la plantilla '$templatePath'." }

    $bytes = New-Object byte[] 48
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $secret = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    [Array]::Clear($bytes, 0, $bytes.Length)

    $usuario = (Read-Host 'Usuario del administrador [admin]').Trim()
    if ([string]::IsNullOrWhiteSpace($usuario)) { $usuario = 'admin' }
    if ($usuario -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{2,39}$') {
        throw 'El usuario debe tener de 3 a 40 caracteres: letras, números, punto, guion o guion bajo.'
    }
    $email = (Read-Host 'Correo de contacto del administrador (opcional, Enter para omitir)').Trim()
    if ($email) {
        try {
            $mail = [System.Net.Mail.MailAddress]::new($email)
            if ($mail.Address -ne $email) { throw 'Formato no válido.' }
        } catch { throw 'El correo de contacto no es válido; déjelo vacío si no desea indicarlo.' }
    }

    $securePassword = Read-Host 'Contraseña del administrador (mín. 10; minúscula, mayúscula, número y símbolo)' -AsSecureString
    $passwordPtr = [IntPtr]::Zero
    $plain = $null
    try {
        $passwordPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPtr)
        if ($plain.Length -lt 10 -or -not ($plain -cmatch '[a-z]') -or -not ($plain -cmatch '[A-Z]') -or
            -not ($plain -match '\d') -or -not ($plain -match '[^A-Za-z0-9]') -or $plain -match '[\r\n\x00-\x1f\x7f]') {
            throw 'La contraseña debe tener al menos 10 caracteres, minúscula, mayúscula, número y símbolo; no use saltos de línea ni controles.'
        }

        $template = Get-Content -Path $templatePath -Raw -ErrorAction Stop
        $template = [regex]::Replace($template, '(?m)^IPV_JWT_SECRET=.*$', [System.Text.RegularExpressions.MatchEvaluator]{ param($m) "IPV_JWT_SECRET=$secret" })
        $template = [regex]::Replace($template, '(?m)^IPV_ADMIN_USER=.*$', [System.Text.RegularExpressions.MatchEvaluator]{ param($m) "IPV_ADMIN_USER=$usuario" })
        $template = [regex]::Replace($template, '(?m)^IPV_ADMIN_EMAIL=.*$', [System.Text.RegularExpressions.MatchEvaluator]{ param($m) "IPV_ADMIN_EMAIL=$email" })
        # MatchEvaluator evita que caracteres como $, # o comillas en la contraseña
        # sean tratados como referencias de reemplazo de una expresión regular.
        $template = [regex]::Replace($template, '(?m)^IPV_ADMIN_PASSWORD=.*$', [System.Text.RegularExpressions.MatchEvaluator]{ param($m) "IPV_ADMIN_PASSWORD=$plain" })
        $tempEnv = "$envFile.$([guid]::NewGuid().ToString('N')).tmp"
        try {
            Set-Content -Path $tempEnv -Value $template -Encoding UTF8 -ErrorAction Stop
            $sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
            $grant = '*{0}:(M)' -f $sid
            & icacls.exe $tempEnv /inheritance:r /grant:r $grant | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'No se pudieron restringir los permisos del archivo de credenciales.' }
            Move-Item -LiteralPath $tempEnv -Destination $envFile -ErrorAction Stop
        } finally {
            if (Test-Path $tempEnv) { Remove-Item -LiteralPath $tempEnv -Force -ErrorAction SilentlyContinue }
        }
        Write-Exito ".env creado con secreto JWT de 384 bits y permisos restringidos al usuario actual. Usuario administrador: $usuario"
        Write-Aviso 'Tras verificar el primer inicio de sesión, elimine IPV_ADMIN_PASSWORD de .env y conserve la contraseña en un gestor seguro.'
    } finally {
        if ($passwordPtr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPtr) }
        $plain = $null
        if ($null -ne $securePassword) { $securePassword.Dispose() }
    }
}

function Protect-Database {
    $snapshot = Get-ProcessEnvironmentSnapshot
    try {
        Import-DotEnv
        $dbPath = Join-Path $dataDir 'ipv.db'
        if (-not (Test-Path $dbPath)) { throw "No existe la base de datos '$dbPath'; inicie IPV antes de cifrarla." }
        $ipvProcesses = @(Get-RunningIpvServerProcess)
        if ($ipvProcesses.Count -gt 0) {
            throw "IPV ya está ejecutándose (PID $($ipvProcesses[0].ProcessId)); detenga ese proceso y vuelva a intentarlo."
        }
        $owner = Get-PortOwner $Port
        if ($null -ne $owner) {
            throw "El puerto HTTPS $Port está atendido por $($owner.ProcessName) (PID $($owner.Id)); deténgalo y vuelva a intentarlo."
        }
        if ((Test-ServerHealth).Status -eq 'OK') {
            throw 'Detenga el servidor antes de cifrar la base de datos (..\iniciar-https.ps1 -Stop).'
        }
        if (-not (Test-Path $envFile)) { throw 'Primero ejecute -InitSecurity para crear .env y proteger las credenciales.' }
        $cmd = Get-PythonCommand
        $exe = [string]$cmd[0]
        $baseArgs = @()
        if ($cmd.Length -gt 1) { $baseArgs = [string[]]$cmd[1..($cmd.Length - 1)] }
        & $exe @baseArgs '-c' 'import sqlcipher3' 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'Instalando el motor SQLCipher (sqlcipher3-wheels) para el Python seleccionado…' -ForegroundColor Cyan
            & $exe @baseArgs '-m' 'pip' 'install' 'sqlcipher3-wheels'
            if ($LASTEXITCODE -ne 0) { throw 'No se pudo instalar sqlcipher3-wheels en el Python seleccionado.' }
            & $exe @baseArgs '-c' 'import sqlcipher3' 2>$null
            if ($LASTEXITCODE -ne 0) { throw 'SQLCipher se instaló, pero no se puede importar con este Python.' }
        }
        if (-not $env:IPV_DB_KEY) {
            $bytes = New-Object byte[] 32
            $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
            try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
            $key = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
            [Array]::Clear($bytes, 0, $bytes.Length)
            $content = Get-Content $envFile -Raw
            if ($content -match '(?m)^\s*IPV_DB_KEY\s*=') {
                $content = [regex]::Replace($content, '(?m)^\s*IPV_DB_KEY\s*=.*$', "IPV_DB_KEY=$key")
            } else {
                $content = $content.TrimEnd() + "`r`nIPV_DB_KEY=$key`r`n"
            }
            $tempEnv = "$envFile.$([guid]::NewGuid().ToString('N')).tmp"
            try {
                Set-Content -Path $tempEnv -Value $content -Encoding UTF8 -ErrorAction Stop
                Set-PrivateFilePermissions -Path $tempEnv
                Move-Item -LiteralPath $tempEnv -Destination $envFile -Force -ErrorAction Stop
            } finally {
                if (Test-Path $tempEnv) { Remove-Item -LiteralPath $tempEnv -Force -ErrorAction SilentlyContinue }
            }
            $env:IPV_DB_KEY = $key
            Write-Exito 'Clave de cifrado de 256 bits generada y guardada en .env'
        }
        $env:IPV_DB_PATH = $dbPath
        Push-Location $repoRoot
        try { & $exe @baseArgs 'dbcrypt.py' 'encrypt' } finally { Pop-Location }
        if ($LASTEXITCODE -ne 0) { throw 'Falló el cifrado. Revise el mensaje anterior y no borre la copia en claro.' }
        Write-Aviso 'IMPORTANTE: guarde una copia de IPV_DB_KEY (archivo .env) fuera de este equipo.'
        Write-Detalle 'Sin esa clave la base de datos y sus copias de seguridad NO se pueden recuperar.'
    } finally {
        Restore-ProcessEnvironment $snapshot
    }
}

function Test-DatabaseEncrypted {
    $db = Join-Path $dataDir 'ipv.db'
    if (-not (Test-Path $db)) { return $null }
    $fs = [System.IO.File]::Open($db, 'Open', 'Read', 'ReadWrite')  # el servidor puede tenerla abierta
    try { $head = New-Object byte[] 15; [void]$fs.Read($head, 0, 15) } finally { $fs.Dispose() }
    return ([System.Text.Encoding]::ASCII.GetString($head) -ne 'SQLite format 3')
}

# ==========================================================================
#  Estado, diagnóstico y parada
# ==========================================================================
function Test-ServerHealth {
    param([string]$Url = "https://localhost:$Port")
    try {
        # La CA local está en el almacén de confianza del usuario: no hace falta omitir la validación TLS.
        $data = Invoke-RestMethod -Uri "$Url/api/health" -TimeoutSec 5
        return [ordered]@{
            Status = 'OK'; Version = $data.version; Database = $data.database; TLS = $data.tls
            Auth = $data.auth_required; CertDays = $data.tls_days_left; CertExpires = $data.tls_expires_at
            MinVersion = $data.tls_min_version
        }
    } catch {
        return [ordered]@{ Status = 'ERROR'; Message = $_.Exception.Message }
    }
}

function Get-PortOwner {
    param([int]$TcpPort)
    if ($TcpPort -le 0) { return $null }
    try {
        $conn = Get-NetTCPConnection -LocalPort $TcpPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -eq $conn) { return $null }
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($conn.OwningProcess)" -ErrorAction SilentlyContinue
        $name = if ($proc) { [System.IO.Path]::GetFileNameWithoutExtension($proc.Name) } else {
            (Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue).ProcessName
        }
        if (-not $name) { return $null }
        $commandLine = if ($proc) { [string]$proc.CommandLine } else { '' }
        return [pscustomobject]@{
            ProcessName = [string]$name
            Id = [int]$conn.OwningProcess
            CommandLine = $commandLine
        }
    } catch { return $null }
}

function Get-RunningIpvServerProcess {
    $expectedServer = [IO.Path]::GetFullPath((Join-Path $repoRoot 'server.py'))
    try {
        return @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
            -not [string]::IsNullOrWhiteSpace($_.CommandLine) -and
            $_.CommandLine.IndexOf($expectedServer, [StringComparison]::OrdinalIgnoreCase) -ge 0
        } | Select-Object ProcessId, Name, CommandLine)
    } catch {
        throw "No se pudo verificar si IPV está ejecutándose; operación cancelada por seguridad: $($_.Exception.Message)"
    }
}

function Test-TlsHandshake {
    param([string]$TargetHost = 'localhost', [int]$TcpPort = 8443)
    $result = [ordered]@{ Ok = $false; Protocol = ''; Cipher = ''; Subject = ''; Expires = $null; Error = '' }
    $client = $null
    $stream = $null
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $async = $client.BeginConnect($TargetHost, $TcpPort, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(3000)) { throw "sin respuesta en ${TargetHost}:${TcpPort}" }
        $client.EndConnect($async)
        $stream = New-Object System.Net.Security.SslStream($client.GetStream(), $false)
        $stream.AuthenticateAsClient($TargetHost)   # validación completa: CA, nombre y vigencia
        $cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]$stream.RemoteCertificate
        $result.Ok = $true
        $result.Protocol = $stream.SslProtocol.ToString()
        $result.Cipher = "$($stream.CipherAlgorithm) de $($stream.CipherStrength) bits"
        $result.Subject = $cert.Subject
        $result.Expires = $cert.NotAfter
    } catch {
        $result.Error = $_.Exception.Message
    } finally {
        if ($null -ne $stream) { $stream.Dispose() }
        if ($null -ne $client) { $client.Dispose() }
    }
    return $result
}

function Show-ServerStatus {
    Write-Host ''
    Write-Host '═══════════════════════════════════════════════════' -ForegroundColor Cyan
    Write-Host '  IPV · Fichas y Costos — Estado del servidor' -ForegroundColor Cyan
    Write-Host '═══════════════════════════════════════════════════' -ForegroundColor Cyan
    $h = Test-ServerHealth
    if ($h.Status -eq 'OK') {
        Write-Exito "Operativo · v$($h.Version) · $($h.Database) · TLS: $($h.TLS) · Token API: $($h.Auth)"
        if ($null -ne $h.CertDays) { Write-Detalle "Certificado válido $($h.CertDays) día(s) más (hasta $($h.CertExpires))" }
    } else {
        Write-Fallo "Sin respuesta en https://localhost:$Port · $($h.Message)"
    }
    $db = Join-Path $dataDir 'ipv.db'
    if (Test-Path $db) { Write-Detalle ("Base de datos: {0:N1} KB" -f ((Get-Item $db).Length / 1KB)) }
    $bk = Join-Path $dataDir 'backups'
    if (Test-Path $bk) { Write-Detalle "Copias de seguridad: $((Get-ChildItem $bk -Filter *.db).Count)" }
    if (Test-Path $envFile) { Write-Detalle 'JWT: configurado (.env)' } else { Write-Aviso 'JWT no configurado — ejecute -InitSecurity' }
    $encrypted = Test-DatabaseEncrypted
    if ($encrypted -eq $false) { Write-Fallo 'Base de datos SIN cifrar — ejecute -EncryptDb' }
    elseif ($encrypted -eq $true) { Write-Detalle 'Cabecera no SQLite en claro: compatible con SQLCipher; el cifrado e integridad no se verifican aquí.' }
    Write-Host ''
}

function Invoke-Diagnostics {
    $problems = 0
    $warnings = 0
    $script:DiagnosticsExitCode = 0
    Write-Host ''
    Write-Host '═══════════════════════════════════════════════════' -ForegroundColor Cyan
    Write-Host '  Diagnóstico del acceso seguro (HTTPS)' -ForegroundColor Cyan
    Write-Host '═══════════════════════════════════════════════════' -ForegroundColor Cyan

    Write-Titulo 'Requisitos'
    $pyVersion = Get-PythonVersion
    if ($pyVersion) {
        $parts = $pyVersion.Split('.')
        if ([int]$parts[0] -gt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 10)) { Write-Exito "Python $pyVersion" }
        else { Write-Aviso "Python $pyVersion — se recomienda 3.10 o superior"; $warnings++ }
    } else { Write-Fallo 'Python no encontrado en el PATH'; $problems++ }
    Write-Exito "PowerShell $($PSVersionTable.PSVersion)"

    Write-Titulo 'Certificados'
    $ca = Get-LocalCa
    if ($null -eq $ca) { Write-Fallo 'No existe la CA local — arranque el servidor una vez'; $problems++ }
    else {
        Write-Exito "CA local válida hasta $($ca.NotAfter.ToString('yyyy-MM-dd'))"
        $trusted = Get-ChildItem Cert:\CurrentUser\Root | Where-Object { $_.Thumbprint -eq $ca.Thumbprint }
        if ($trusted) { Write-Exito 'CA instalada en «Entidades de certificación raíz de confianza» de este usuario' }
        else { Write-Aviso 'La CA no está en el almacén de confianza — el navegador avisará'; $warnings++ }
    }
    $leaf = Get-ServerCert
    if ($null -eq $leaf) { Write-Fallo 'No existe el certificado del servidor — arranque el servidor una vez'; $problems++ }
    else {
        $days = [int]([Math]::Floor(($leaf.NotAfter - (Get-Date)).TotalDays))
        if ($days -lt 0) { Write-Fallo "El certificado del servidor caducó hace $([Math]::Abs($days)) día(s) — use -Renew"; $problems++ }
        elseif ($days -le $RenewDays) { Write-Aviso "El certificado caduca en $days día(s) — use -Renew"; $warnings++ }
        else { Write-Exito "Certificado del servidor válido $days día(s) más" }
        $entries = Get-SanEntries
        if (Test-CertCoversNames $leaf $entries) { Write-Exito 'El certificado cubre todos los nombres e IP actuales' }
        else { Write-Aviso 'Cambió alguna IP de este equipo: renueve con -Renew para incluirla'; $warnings++ }
        Write-Detalle (Get-CertSanText $leaf).Trim()
    }
    foreach ($file in @($rootCerPath, $leafPemPath, $keyPemPath)) {
        if (Test-Path $file) { Write-Exito "Archivo presente: $(Split-Path $file -Leaf)" }
        else { Write-Aviso "Falta $(Split-Path $file -Leaf) — se regenera al arrancar"; $warnings++ }
    }

    Write-Titulo 'Red local'
    $hostsPath = Join-Path $env:SystemRoot 'System32\drivers\etc\hosts'
    $pattern = '^\s*(?!#)\S+\s+.*\b' + [regex]::Escape($ServerAlias) + '\b'
    if (Select-String -Path $hostsPath -Pattern $pattern -Quiet) { Write-Exito "Alias $ServerAlias definido en hosts" }
    else { Write-Aviso "Falta el alias $ServerAlias en hosts — use la IP o ejecute el script como administrador"; $warnings++ }
    foreach ($tcpPort in @($Port, $RedirectPort)) {
        if ($tcpPort -le 0) { continue }
        $rule = Get-NetFirewallRule -DisplayName (Get-FirewallRuleName $tcpPort) -ErrorAction SilentlyContinue
        if ($rule) { Write-Exito "Regla de firewall para el puerto $tcpPort" }
        else { Write-Aviso "Sin regla de firewall para el puerto $tcpPort (solo afecta al acceso desde otros equipos)"; $warnings++ }
    }
    try {
        $publicas = Get-NetConnectionProfile -ErrorAction SilentlyContinue | Where-Object { $_.NetworkCategory -eq 'Public' }
        if ($publicas) { Write-Aviso 'Hay una red marcada como Pública: use una red privada de confianza'; $warnings++ }
        else { Write-Exito 'Todas las redes activas son privadas o de dominio' }
    } catch { }
    foreach ($ip in (Get-LanIPv4)) { Write-Detalle "Dirección de acceso: https://${ip}:$Port" }

    Write-Titulo 'Servidor y TLS'
    $owner = Get-PortOwner $Port
    if ($null -eq $owner) {
        Write-Aviso "Nadie escucha en el puerto $Port — arranque con .\iniciar-https.ps1"; $warnings++
    } else {
        Write-Exito "Puerto $Port atendido por $($owner.ProcessName) (PID $($owner.Id))"
        $tls = Test-TlsHandshake -TargetHost $ServerAlias -TcpPort $Port
        if (-not $tls.Ok) { $tls = Test-TlsHandshake -TargetHost 'localhost' -TcpPort $Port }
        if ($tls.Ok) {
            Write-Exito "Handshake correcto · $($tls.Protocol) · $($tls.Cipher)"
            Write-Detalle "Certificado: $($tls.Subject) — válido hasta $($tls.Expires)"
            if ($tls.Protocol -notmatch 'Tls12|Tls13') { Write-Aviso 'Protocolo antiguo negociado'; $warnings++ }
        } else {
            Write-Fallo "El cliente no pudo validar el TLS: $($tls.Error)"; $problems++
        }
        $health = Test-ServerHealth
        if ($health.Status -eq 'OK') {
            Write-Exito "API viva · v$($health.Version) · TLS mínimo $($health.MinVersion)"
        } else {
            Write-Fallo "La API no respondió: $($health.Message)"; $problems++
        }
        try {
            $healthResponse = Invoke-WebRequest -Uri "https://localhost:$Port/api/health" -Method Get -TimeoutSec 5 -UseBasicParsing
            if ($healthResponse.StatusCode -ne 200) { throw "HTTP $($healthResponse.StatusCode)" }
            $hsts = $healthResponse.Headers['Strict-Transport-Security']
            if ($hsts) { Write-Exito "HSTS activo: $hsts" }
            else { Write-Aviso 'La API respondió, pero no envió HSTS.'; $warnings++ }
        } catch {
            Write-Aviso "No se pudo comprobar HSTS: $($_.Exception.Message)"; $warnings++
        }
        if ($RedirectPort -gt 0) {
            $redir = Get-PortOwner $RedirectPort
            if ($redir) { Write-Exito "Redirección HTTP → HTTPS activa en el puerto $RedirectPort" }
            else { Write-Detalle "Redirección HTTP no activa (puerto $RedirectPort libre)" }
        }
    }

    Write-Titulo 'Datos y credenciales'
    if (Test-Path $envFile) {
        Write-Exito '.env presente'
        $envText = Get-Content $envFile -Raw
        if ($envText -match '(?m)^IPV_JWT_SECRET=.+$') { Write-Exito 'Secreto JWT configurado (inicio de sesión obligatorio)' }
        else { Write-Aviso 'Sin IPV_JWT_SECRET: el servidor funciona en modo abierto'; $warnings++ }
        if ($envText -match '(?m)^IPV_ADMIN_PASSWORD=.+$') { Write-Aviso 'IPV_ADMIN_PASSWORD sigue en .env: bórrelo tras el primer inicio'; $warnings++ }
    } else { Write-Aviso 'Sin .env — ejecute -InitSecurity'; $warnings++ }
    $encrypted = Test-DatabaseEncrypted
    if ($encrypted -eq $true) { Write-Detalle 'Cabecera no SQLite en claro: compatible con SQLCipher; el cifrado e integridad no se verifican aquí.' }
    elseif ($encrypted -eq $false) { Write-Aviso 'Base de datos sin cifrar — ejecute -EncryptDb'; $warnings++ }
    else { Write-Detalle 'Todavía no hay base de datos (se crea al primer arranque)' }
    $bk = Join-Path $dataDir 'backups'
    if (Test-Path $bk) {
        $ultima = Get-ChildItem $bk -Filter *.db | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($ultima) { Write-Exito "Última copia de seguridad: $($ultima.Name) ($($ultima.LastWriteTime))" }
    } else { Write-Aviso 'Todavía no hay copias de seguridad — ejecute -Backup'; $warnings++ }

    Write-Host ''
    if ($problems -gt 0) {
        Write-Host "  Resultado: $problems problema(s) y $warnings aviso(s)." -ForegroundColor Red
        $script:DiagnosticsExitCode = 1
    } elseif ($warnings -gt 0) {
        Write-Host "  Resultado: todo funciona, con $warnings aviso(s)." -ForegroundColor Yellow
        $script:DiagnosticsExitCode = 2
    } else {
        Write-Host '  Resultado: acceso seguro correcto. Nada que corregir.' -ForegroundColor Green
        $script:DiagnosticsExitCode = 0
    }
    Write-Host ''
}

function Stop-IpvServer {
    $stopped = $false
    foreach ($tcpPort in @($Port, $RedirectPort)) {
        if ($tcpPort -le 0) { continue }
        $owner = Get-PortOwner $tcpPort
        if ($null -eq $owner) { continue }
        $expectedServer = [IO.Path]::GetFullPath((Join-Path $repoRoot 'server.py'))
        $isIpvProcess = $owner.ProcessName -match '^(python|pythonw|py)$' -and
            -not [string]::IsNullOrWhiteSpace($owner.CommandLine) -and
            $owner.CommandLine.IndexOf($expectedServer, [StringComparison]::OrdinalIgnoreCase) -ge 0
        if (-not $isIpvProcess) {
            Write-Aviso "El puerto $tcpPort lo usa $($owner.ProcessName) (PID $($owner.Id)); no coincide de forma verificable con este IPV y no se terminará."
            continue
        }
        try {
            Stop-Process -Id $owner.Id -ErrorAction Stop
            $process = Get-Process -Id $owner.Id -ErrorAction SilentlyContinue
            if ($process) {
                Start-Sleep -Milliseconds 500
                Stop-Process -Id $owner.Id -Force -ErrorAction Stop
            }
            Write-Exito "Servidor IPV detenido (PID $($owner.Id), puerto $tcpPort)."
            $stopped = $true
        } catch {
            Write-Aviso "No se pudo detener PID $($owner.Id): $($_.Exception.Message)"
        }
    }
    if (-not $stopped) { Write-Detalle 'No había ningún servidor IPV escuchando.' }
}

# ==========================================================================
#  Comandos que no arrancan el servidor
# ==========================================================================
if ($ConfigureNetworkOnly) {
    if (-not (Test-IsAdministrator)) { throw 'La configuración de red requiere permisos de administrador.' }
    Set-LocalNetwork -HttpsPort $Port -HttpPort $RedirectPort
    Write-Exito "Alias $ServerAlias y reglas del firewall configurados para la red local."
    exit 0
}
if ($InitSecurity) { Initialize-Security; exit 0 }
if ($EncryptDb) { Protect-Database; exit $LASTEXITCODE }
if ($Stop) { Stop-IpvServer; exit 0 }
if ($Check) { Invoke-Diagnostics; exit $script:DiagnosticsExitCode }
if ($ExportCa) { Export-CaFile -Destination $ExportCa; exit 0 }
if ($ShowPin) {
    $pin = Get-CaPin
    if (-not $pin) { throw 'Aún no existe la CA local. Arranque el servidor una vez para generarla.' }
    $cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($rootCerPath)
    Write-Host ''
    Write-Host 'Huella SHA-256 de la CA local (Android → Configuración → Seguridad):' -ForegroundColor Cyan
    Write-Host "  $pin" -ForegroundColor Green
    Write-Host "  $(($pin -split '(.{2})' | Where-Object { $_ }) -join ':')" -ForegroundColor DarkGray
    Write-Host "  Válida hasta: $($cert.NotAfter)" -ForegroundColor Yellow
    Write-Host ''
    exit 0
}
if ($Status) { Show-ServerStatus; exit 0 }
if ($HealthCheck) {
    $health = Test-ServerHealth
    $health | ConvertTo-Json -Depth 4
    if ($health.Status -ne 'OK') { exit 1 }
    exit 0
}
if ($Backup) {
    $backupCode = @'
import json, sys, server
info = server.auto_backup()
if not info or info.get("error") or not info.get("success", True):
    print(json.dumps({"ok": False, "error": (info or {}).get("error", "no se creó la copia")}, ensure_ascii=False))
    sys.exit(1)
failures = [item for item in info.get("offsite", []) if not item.get("ok")]
print(json.dumps({"ok": not failures, "archivo": info.get("filename"), "bytes": info.get("size"),
                  "replicas": info.get("offsite", []), "fallos_replica": failures}, ensure_ascii=False))
sys.exit(2 if failures else 0)
'@
    Invoke-Py $backupCode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    exit 0
}
if ($AuditLog) {
    Invoke-Py 'import dbcrypt, server; c = dbcrypt.connect(server.DB_PATH); [print(*r, sep="  |  ") for r in c.execute("SELECT timestamp, action, client, user_email, details FROM audit_log ORDER BY id DESC LIMIT 40")]'
    exit 0
}

# ==========================================================================
#  Arranque del servidor HTTPS
# ==========================================================================
# Eleva solo los cambios de hosts/firewall; el servidor Python sigue con los permisos del usuario.
if (-not (Test-IsAdministrator) -and -not (Test-LocalNetworkConfigured -HttpsPort $Port -HttpPort $RedirectPort)) {
    try {
        $powershellExe = if ($PSVersionTable.PSEdition -eq 'Core') { Join-Path $PSHOME 'pwsh.exe' } else { Join-Path $PSHOME 'powershell.exe' }
        $quotedScript = '"' + $PSCommandPath + '"'
        $networkArgs = "-NoProfile -ExecutionPolicy Bypass -File $quotedScript -ConfigureNetworkOnly -Port $Port -RedirectPort $RedirectPort"
        $networkSetup = Start-Process -FilePath $powershellExe -Verb RunAs -ArgumentList $networkArgs -Wait -PassThru
        if ($networkSetup.ExitCode -ne 0) { throw "La configuración elevada de red terminó con código $($networkSetup.ExitCode)." }
    } catch {
        Write-Aviso "No se pudo configurar hosts/firewall: $($_.Exception.Message). El servidor funcionará localmente; revise el acceso desde la LAN."
    }
} elseif (-not (Test-IsAdministrator)) {
    Write-Detalle 'Alias y reglas de firewall ya están configurados; se evita solicitar UAC.'
}
try {
    if (Get-NetConnectionProfile -ErrorAction SilentlyContinue | Where-Object { $_.NetworkCategory -eq 'Public' }) {
        Write-Aviso 'Hay una conexión marcada como Pública. Use una red privada de confianza; no habilite el acceso en Wi-Fi público.'
    }
} catch { }

$runningServer = @(Get-RunningIpvServerProcess)
if ($runningServer.Count -gt 0) {
    throw "IPV ya está ejecutándose desde este repositorio (PID $($runningServer[0].ProcessId)). Use -Stop o revise manualmente el proceso antes de iniciar otra instancia."
}
$owner = Get-PortOwner $Port
if ($null -ne $owner) {
    throw "El puerto $Port ya está en uso por $($owner.ProcessName) (PID $($owner.Id)). Use .\iniciar-https.ps1 -Stop o elija otro puerto con -Port."
}

New-Item -ItemType Directory -Path $certDir -Force | Out-Null
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null

# --- Autoridad certificadora local -----------------------------------------
$root = Get-LocalCa
if ($Renew -and $null -ne $root) {
    Write-Aviso 'Renovación forzada: se emitirán una CA y un certificado nuevos (reinstale la CA en los clientes).'
    $root = $null
}
if ($null -eq $root) { $root = New-LocalCa }

[System.IO.File]::WriteAllBytes($rootCerPath, $root.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert))
$trustedRoot = Get-ChildItem Cert:\CurrentUser\Root | Where-Object { $_.Thumbprint -eq $root.Thumbprint } | Select-Object -First 1
if ($null -eq $trustedRoot) { Import-Certificate -FilePath $rootCerPath -CertStoreLocation 'Cert:\CurrentUser\Root' | Out-Null }
if ($Renew) {
    # Retira las CA anteriores para que no queden certificados de confianza huérfanos.
    Get-ChildItem Cert:\CurrentUser\My, Cert:\CurrentUser\Root | Where-Object {
        $_.Subject -eq $RootSubject -and $_.Thumbprint -ne $root.Thumbprint
    } | Remove-Item -ErrorAction SilentlyContinue
}

# --- Certificado del servidor (se reutiliza mientras siga siendo válido) ----
$sanEntries = Get-SanEntries
$leaf = Get-ServerCert
$reason = ''
if ($Renew) { $reason = 'renovación solicitada' }
elseif ($null -eq $leaf) { $reason = 'todavía no existe' }
elseif ($leaf.Issuer -ne $root.Subject) { $reason = 'lo firmó otra CA' }
elseif ($leaf.NotAfter -lt (Get-Date).AddDays($RenewDays)) { $reason = 'caduca pronto' }
elseif (-not (Test-CertCoversNames $leaf $sanEntries)) { $reason = 'cambió alguna dirección IP del equipo' }
elseif (-not (Test-Path $leafPemPath) -or -not (Test-Path $keyPemPath)) { $reason = 'faltan los archivos PEM' }

if ($reason) {
    Write-Detalle "Certificado del servidor: $reason."
    $leaf = New-ServerCert -Ca $root -Entries $sanEntries
    Export-ServerPem -Leaf $leaf -Ca $root
    # Borra certificados de servidor anteriores firmados por esta misma CA; conserva el actual.
    Get-ChildItem Cert:\CurrentUser\My | Where-Object {
        $_.Thumbprint -ne $leaf.Thumbprint -and $_.Subject -eq "CN=$ServerAlias" -and $_.Issuer -eq $root.Subject
    } | Remove-Item -ErrorAction SilentlyContinue
} else {
    $diasRestantes = [int]([Math]::Floor(($leaf.NotAfter - (Get-Date)).TotalDays))
    Write-Detalle "Certificado del servidor reutilizado ($diasRestantes día(s) de validez)."
}

# --- Variables de entorno del servidor -------------------------------------
$pythonCommand = Get-PythonCommand
$pythonExe = [string]$pythonCommand[0]
$pythonArgs = @()
if ($pythonCommand.Length -gt 1) { $pythonArgs = [string[]]$pythonCommand[1..($pythonCommand.Length - 1)] }
$serverEnvSnapshot = Get-ProcessEnvironmentSnapshot
try {
Import-DotEnv  # secretos disponibles para el proceso servidor y restaurados al salir
$env:IPV_HOST = '0.0.0.0'
$env:PORT = "$Port"
$env:IPV_DB_PATH = Join-Path $dataDir 'ipv.db'
$env:IPV_TLS_CERT = $leafPemPath
$env:IPV_TLS_KEY = $keyPemPath
$tlsMinimo = '1.2'
if ($Tls13Only) { $tlsMinimo = '1.3' }
$env:IPV_TLS_MIN = $tlsMinimo
$env:IPV_REQUIRE_TLS = '1'
$env:IPV_HTTP_REDIRECT_PORT = "$RedirectPort"
$env:PYTHONUNBUFFERED = '1'

# --- Panel de acceso --------------------------------------------------------
$lanIps = Get-LanIPv4
$pin = Get-CaPin
Write-Host ''
Write-Host '═══════════════════════════════════════════════════' -ForegroundColor Green
Write-Host '  Servidor HTTPS listo para la red local' -ForegroundColor Green
Write-Host '═══════════════════════════════════════════════════' -ForegroundColor Green
Write-Host "  En esta PC:      https://${ServerAlias}:$Port"
Write-Host "  También:         https://localhost:$Port"
foreach ($ip in ($lanIps | Select-Object -Unique)) { Write-Host "  Desde la red:    https://${ip}:$Port" }
if ($RedirectPort -gt 0) { Write-Host "  HTTP (redirige): http://${ServerAlias}:$RedirectPort → HTTPS" -ForegroundColor DarkGray }
Write-Host "  TLS mínimo:      $tlsMinimo" -ForegroundColor DarkGray
Write-Host ''
Write-Host "  CA para instalar en móviles u otras PC: $rootCerPath" -ForegroundColor Yellow
if ($pin) { Write-Host "  Huella SHA-256 de la CA: $pin" -ForegroundColor DarkGray }
Write-Host '  La clave privada certs\ipv-server-key.pem no debe copiarse ni compartirse.' -ForegroundColor Yellow
Write-Host '  No publique este puerto en Internet. Detenga el servidor con Ctrl+C.' -ForegroundColor Yellow
# El servidor exige JWT: sin él se cierra al instante (no existe el «modo abierto»).
if ([string]::IsNullOrWhiteSpace($env:IPV_JWT_SECRET)) {
    Write-Fallo 'Falta IPV_JWT_SECRET: el servidor se negará a arrancar.'
    Write-Detalle 'Sin JWT no hay inicio de sesión, ni Roles de Usuarios, ni Licencia.'
    Write-Detalle 'Cree la configuración con:  .\iniciar-https.ps1 -InitSecurity'
    if (-not (Test-Path $envFile)) { Write-Detalle "(no se encontró el archivo $envFile)" }
    else { Write-Detalle 'El archivo .env existe pero no define IPV_JWT_SECRET (o está vacío).' }
}
elseif ([string]::IsNullOrWhiteSpace($env:IPV_ADMIN_USER) -or [string]::IsNullOrWhiteSpace($env:IPV_ADMIN_PASSWORD)) {
    Write-Detalle 'IPV_ADMIN_USER / IPV_ADMIN_PASSWORD no definidos: correcto si el administrador ya existe.'
    Write-Detalle 'Si es la primera instalación, créelo con:  .\iniciar-https.ps1 -InitSecurity'
}
$encrypted = Test-DatabaseEncrypted
if ($encrypted -eq $false) { Write-Aviso 'La base de datos no está cifrada: ejecute -EncryptDb con el servidor detenido.' }
Write-Host ''

if ($Open) {
    try { Start-Process "https://${ServerAlias}:$Port" | Out-Null } catch { Start-Process "https://localhost:$Port" | Out-Null }
}

Set-Location $repoRoot
$pythonArgs += (Join-Path $repoRoot 'server.py')
& $pythonExe @pythonArgs
} finally {
    Restore-ProcessEnvironment $serverEnvSnapshot
}
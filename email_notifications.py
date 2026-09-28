"""
IPV Fichas y Costos - Email Notification System
Async email notifications for critical events
"""
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from threading import Thread
from datetime import datetime
import os

class EmailNotifier:
    def __init__(self):
        self.smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        self.smtp_user = os.environ.get('SMTP_USER', '')
        self.smtp_password = os.environ.get('SMTP_PASSWORD', '')
        self.from_email = os.environ.get('FROM_EMAIL', self.smtp_user)
        self.from_name = os.environ.get('FROM_NAME', 'IPV Fichas y Costos')
        self.enabled = bool(self.smtp_user and self.smtp_password)
    
    def send_async(self, to_email, subject, html_body, text_body=None, attachments=None):
        """Send email asynchronously"""
        if not self.enabled:
            print(f"⚠ Email not configured. Would send to {to_email}: {subject}")
            return False
        
        thread = Thread(
            target=self._send_email,
            args=(to_email, subject, html_body, text_body, attachments),
            daemon=True
        )
        thread.start()
        return True
    
    def _send_email(self, to_email, subject, html_body, text_body=None, attachments=None):
        """Send email synchronously"""
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email
            
            # Add text version
            if text_body:
                msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
            
            # Add HTML version
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))
            
            # Add attachments
            if attachments:
                for filename, content in attachments:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(content)
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename="{filename}"'
                    )
                    msg.attach(part)
            
            # Send email
            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            print(f"✓ Email sent to {to_email}: {subject}")
            return True
            
        except Exception as e:
            print(f"✗ Email failed to {to_email}: {e}")
            return False

# Global email notifier instance
email_notifier = EmailNotifier()

# Email templates
class EmailTemplates:
    @staticmethod
    def _base_template(content):
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f6f8f5; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; }}
                .header {{ background: linear-gradient(135deg, #183b34 0%, #2a7057 100%); padding: 30px; text-align: center; }}
                .header h1 {{ color: #d7e78d; margin: 0; font-size: 28px; }}
                .header p {{ color: #b0c6b9; margin: 5px 0 0; font-size: 14px; }}
                .content {{ padding: 30px; }}
                .content h2 {{ color: #1a2723; margin-top: 0; }}
                .content p {{ color: #495950; line-height: 1.6; }}
                .button {{ display: inline-block; padding: 12px 24px; background: #183b34; color: white; text-decoration: none; border-radius: 8px; font-weight: 600; }}
                .footer {{ padding: 20px 30px; background: #f6f8f5; text-align: center; color: #7d8983; font-size: 12px; }}
                .stat {{ background: #f6f8f5; padding: 15px; border-radius: 8px; margin: 10px 0; }}
                .stat-value {{ font-size: 24px; font-weight: 700; color: #183b34; }}
                .stat-label {{ font-size: 12px; color: #7d8983; }}
                .alert {{ padding: 15px; border-radius: 8px; margin: 10px 0; }}
                .alert-success {{ background: #e8f5e9; border-left: 4px solid #10b981; }}
                .alert-warning {{ background: #fff3e0; border-left: 4px solid #f59e0b; }}
                .alert-danger {{ background: #ffebee; border-left: 4px solid #ef4444; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>IPV · Fichas y Costos</h1>
                    <p>Sistema de Gestión de Costos</p>
                </div>
                <div class="content">
                    {content}
                </div>
                <div class="footer">
                    <p>© {datetime.now().year} IPV Fichas y Costos · Ing. Yosvany Hernández Quintero</p>
                    <p>Este es un mensaje automático, por favor no responder.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    @staticmethod
    def ficha_approved(ficha_data, approver_name):
        content = f"""
        <h2>✓ Ficha de Costo Aprobada</h2>
        <p>La ficha de costo ha sido aprobada exitosamente.</p>
        
        <div class="stat">
            <div class="stat-value">{ficha_data.get('product_name', 'N/A')}</div>
            <div class="stat-label">Producto</div>
        </div>
        
        <div class="stat">
            <div class="stat-value">v{ficha_data.get('version', '1')}</div>
            <div class="stat-label">Versión</div>
        </div>
        
        <div class="stat">
            <div class="stat-value">{ficha_data.get('total_cost', '0.00')} CUP</div>
            <div class="stat-label">Costo Total</div>
        </div>
        
        <div class="alert alert-success">
            <strong>Aprobada por:</strong> {approver_name}<br>
            <strong>Fecha:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}
        </div>
        
        <p>La ficha ya está disponible para generar controles de IPV.</p>
        """
        return EmailTemplates._base_template(content)
    
    @staticmethod
    def control_validated(control_data, validator_name):
        content = f"""
        <h2>✓ Control de IPV Validado</h2>
        <p>El control de IPV ha sido validado exitosamente.</p>
        
        <div class="stat">
            <div class="stat-value">{control_data.get('code', 'N/A')}</div>
            <div class="stat-label">Código de Control</div>
        </div>
        
        <div class="stat">
            <div class="stat-value">{control_data.get('product_name', 'N/A')}</div>
            <div class="stat-label">Producto</div>
        </div>
        
        <div class="stat">
            <div class="stat-value">{control_data.get('period', 'N/A')}</div>
            <div class="stat-label">Período</div>
        </div>
        
        <div class="alert alert-success">
            <strong>Validado por:</strong> {validator_name}<br>
            <strong>Total verificado:</strong> {control_data.get('checked_total', '0.00')} CUP
        </div>
        """
        return EmailTemplates._base_template(content)
    
    @staticmethod
    def control_with_differences(control_data, validator_name, differences):
        diff_html = "".join([f"<li>{d}</li>" for d in differences])
        content = f"""
        <h2>⚠ Control con Diferencias</h2>
        <p>El control de IPV ha sido revisado y se encontraron diferencias.</p>
        
        <div class="stat">
            <div class="stat-value">{control_data.get('code', 'N/A')}</div>
            <div class="stat-label">Código de Control</div>
        </div>
        
        <div class="alert alert-warning">
            <strong>Diferencias encontradas:</strong>
            <ul>{diff_html}</ul>
        </div>
        
        <p>Por favor revise el control y tome las acciones necesarias.</p>
        """
        return EmailTemplates._base_template(content)
    
    @staticmethod
    def backup_completed(backup_data):
        content = f"""
        <h2>💾 Backup Completado</h2>
        <p>Se ha completado exitosamente el backup de la base de datos.</p>
        
        <div class="stat">
            <div class="stat-value">{backup_data.get('filename', 'N/A')}</div>
            <div class="stat-label">Archivo</div>
        </div>
        
        <div class="stat">
            <div class="stat-value">{backup_data.get('size_mb', '0')} MB</div>
            <div class="stat-label">Tamaño</div>
        </div>
        
        <div class="alert alert-success">
            <strong>Fecha:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}<br>
            <strong>Ubicación:</strong> {backup_data.get('path', 'N/A')}
        </div>
        """
        return EmailTemplates._base_template(content)
    
    @staticmethod
    def weekly_report(stats):
        content = f"""
        <h2>📊 Reporte Semanal</h2>
        <p>Resumen de actividad de la última semana.</p>
        
        <div class="stat">
            <div class="stat-value">{stats.get('new_products', 0)}</div>
            <div class="stat-label">Nuevos Productos</div>
        </div>
        
        <div class="stat">
            <div class="stat-value">{stats.get('new_fichas', 0)}</div>
            <div class="stat-label">Nuevas Fichas</div>
        </div>
        
        <div class="stat">
            <div class="stat-value">{stats.get('approved_fichas', 0)}</div>
            <div class="stat-label">Fichas Aprobadas</div>
        </div>
        
        <div class="stat">
            <div class="stat-value">{stats.get('validated_controls', 0)}</div>
            <div class="stat-label">Controles Validados</div>
        </div>
        """
        return EmailTemplates._base_template(content)

# Convenience functions
def notify_ficha_approved(ficha_data, approver_name, recipient_email):
    html = EmailTemplates.ficha_approved(ficha_data, approver_name)
    subject = f"✓ Ficha Aprobada: {ficha_data.get('product_name', 'N/A')}"
    return email_notifier.send_async(recipient_email, subject, html)

def notify_control_validated(control_data, validator_name, recipient_email):
    html = EmailTemplates.control_validated(control_data, validator_name)
    subject = f"✓ Control Validado: {control_data.get('code', 'N/A')}"
    return email_notifier.send_async(recipient_email, subject, html)

def notify_control_differences(control_data, validator_name, differences, recipient_email):
    html = EmailTemplates.control_with_differences(control_data, validator_name, differences)
    subject = f"⚠ Control con Diferencias: {control_data.get('code', 'N/A')}"
    return email_notifier.send_async(recipient_email, subject, html)

def notify_backup_completed(backup_data, recipient_email):
    html = EmailTemplates.backup_completed(backup_data)
    subject = "💾 Backup Completado - IPV Fichas y Costos"
    return email_notifier.send_async(recipient_email, subject, html)

def notify_weekly_report(stats, recipient_email):
    html = EmailTemplates.weekly_report(stats)
    subject = "📊 Reporte Semanal - IPV Fichas y Costos"
    return email_notifier.send_async(recipient_email, subject, html)


def notify_new_login(recipient_email, user_email, ip, device, when):
    """Alerta de seguridad: inicio de sesión desde una IP no vista antes."""
    from html import escape
    content = f"""
        <h2 style="color:#dc2626">🔐 Nuevo inicio de sesión detectado</h2>
        <p>Se ha iniciado sesión en la cuenta <b>{escape(user_email)}</b> desde una dirección IP no utilizada antes.</p>
        <table style="border-collapse:collapse">
          <tr><td style="padding:4px 12px 4px 0"><b>IP</b></td><td>{escape(ip)}</td></tr>
          <tr><td style="padding:4px 12px 4px 0"><b>Dispositivo</b></td><td>{escape(device)}</td></tr>
          <tr><td style="padding:4px 12px 4px 0"><b>Fecha (UTC)</b></td><td>{escape(when)}</td></tr>
        </table>
        <p>Si fue usted, no tiene que hacer nada. Si <b>no</b> reconoce este acceso, entre al sistema,
        cambie su contraseña y cierre las demás sesiones en «Seguridad de la cuenta → Dispositivos».</p>
    """
    html = EmailTemplates._base_template(content)
    text = (f"Nuevo inicio de sesión en {user_email}\nIP: {ip}\nDispositivo: {device}\nFecha (UTC): {when}\n"
            "Si no reconoce este acceso, cambie su contraseña y cierre las demás sesiones.")
    return email_notifier.send_async(recipient_email, "🔐 Alerta de seguridad: nuevo inicio de sesión", html, text)


def notify_failed_logins(recipient_email, user_email, ip, attempts, locked, when):
    """Alerta: intentos fallidos repetidos o cuenta bloqueada."""
    from html import escape
    title = "🔒 Cuenta bloqueada temporalmente" if locked else "⚠ Intentos de acceso fallidos"
    detail = ("La cuenta quedó <b>bloqueada 15 minutos</b> por seguridad." if locked
              else "Si continúan los fallos, la cuenta se bloqueará temporalmente.")
    content = f"""
        <h2 style="color:#dc2626">{title}</h2>
        <p>Se registraron <b>{int(attempts)}</b> intentos fallidos seguidos de inicio de sesión en la cuenta
        <b>{escape(user_email)}</b>. {detail}</p>
        <table style="border-collapse:collapse">
          <tr><td style="padding:4px 12px 4px 0"><b>Última IP</b></td><td>{escape(ip)}</td></tr>
          <tr><td style="padding:4px 12px 4px 0"><b>Fecha (UTC)</b></td><td>{escape(when)}</td></tr>
        </table>
        <p>Si no fue usted, alguien podría estar intentando adivinar su contraseña: cámbiela por una larga
        y única y active la verificación en dos pasos.</p>
    """
    text = (f"{int(attempts)} intentos fallidos en {user_email} desde {ip} ({when} UTC)."
            + (" Cuenta bloqueada 15 minutos." if locked else ""))
    return email_notifier.send_async(recipient_email, f"{title} - IPV Fichas y Costos",
                                     EmailTemplates._base_template(content), text)


def notify_suspicious_ip(recipient_email, ip, failures, accounts, when):
    """Alerta al administrador: posible rociado de contraseñas desde una IP."""
    from html import escape
    content = f"""
        <h2 style="color:#dc2626">🚨 Posible ataque de contraseñas</h2>
        <p>La IP <b>{escape(ip)}</b> acumuló <b>{int(failures)}</b> inicios de sesión fallidos contra
        <b>{int(accounts)}</b> cuentas distintas en 15 minutos ({escape(when)} UTC).</p>
        <p>Recomendación: revise la auditoría y, si la IP no es de confianza, restrinja el acceso con
        <code>IPV_IP_ALLOWLIST</code> o en el cortafuegos.</p>
    """
    text = f"IP {ip}: {int(failures)} fallos contra {int(accounts)} cuentas en 15 min ({when} UTC)."
    return email_notifier.send_async(recipient_email, "🚨 Posible ataque de contraseñas - IPV Fichas y Costos",
                                     EmailTemplates._base_template(content), text)

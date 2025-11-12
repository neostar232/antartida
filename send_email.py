
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

SMTP_PASS = 'jjkc ozol vzhe xiue'
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_USER = 'neostar.notifications@gmail.com'
# Información del correo
FROM_NAME = 'Antarpply - by Neostar'
FROM_EMAIL = 'neostar.notifications@gmail.com'
SUBJECT = "Did you forget your password?"
HTML_PATH = os.path.join(os.path.dirname(__file__), "templates", "email_psw.html")

def send_mail(name,email,psw):
    try:
        print("Intentando enviar correo de login...")
        # Lee el contenido del archivo HTML
        with open(HTML_PATH, "r", encoding="utf-8") as archivo:
            html_template = archivo.read()
        
        # Reemplaza las variables en el HTML
        cuerpo_html = html_template.replace("[name]", name)
        cuerpo_html = cuerpo_html.replace("[email]", email)
        cuerpo_html = cuerpo_html.replace("[password]", psw)
        #cuerpo_html = cuerpo_html.replace("https://americanaddictioncenters.org/how-long-drugs-system", url_sistema)

        # Configura el mensaje multipart
        msg = MIMEMultipart("alternative")
        msg["Subject"] = SUBJECT
        msg["From"] = FROM_EMAIL
        msg["To"] = email
        
        # Adjunta el contenido HTML al mensaje
        part_html = MIMEText(cuerpo_html, "html")
        msg.attach(part_html)

        # Conéctate al servidor SMTP y envía el correo
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as servidor:
            servidor.login(FROM_EMAIL, SMTP_PASS)
            servidor.sendmail(FROM_EMAIL, email, msg.as_string())

        print(f"Correo de credenciales enviado con éxito a {email}!")
    
    except FileNotFoundError:
        print("Error: El archivo html no se encuentra.")
    except Exception as e:
        print(f"Hubo un error al enviar el correo: {e}")

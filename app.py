from flask import Flask, render_template, request, redirect, url_for, flash, session
from twilio.rest import Client
import os
from flask_sqlalchemy import SQLAlchemy
import json
from datetime import datetime, timedelta
from twilio.base.exceptions import TwilioRestException
from dotenv import load_dotenv
load_dotenv() 

app = Flask(__name__)
app.secret_key = "your_secret_key"  # Cambia esto por una clave segura

# Configuración de Twilio
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID') # Reemplaza con tu SID de Twilio
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')    # Reemplaza con tu token de Twilio
VERIFY_SERVICE_SID = os.getenv('VERIFICATION_SID') # Reemplaza con tu Service SID de Twilio
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


# Configuración de SQLite
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)



# Modelo de la base de datos
class User(db.Model):
    identificacion = db.Column(db.String(20), unique=True, nullable=False, primary_key=True)
    nombres = db.Column(db.String(100), nullable=False)
    apellidos = db.Column(db.String(100), nullable=False)
    departamento = db.Column(db.String(50), nullable=True)
    municipio = db.Column(db.String(50), nullable=True)
    correo = db.Column(db.String(100), unique=True, nullable=True)
    numero_celular = db.Column(db.String(15), nullable=True) # Por ahora se asume que el número de celular no es unique
    confirma_asistencia = db.Column(db.Boolean, default=False)
    ultimo_otp_generado = db.Column(db.DateTime, nullable=True)
    verificado = db.Column(db.Boolean, default=False)
    

@app.route("/")
def home():
    if "user" in session:
        user = User.query.filter_by(identificacion=session["user"]).first()
        if user.verificado:
            user_confirmed = user.confirma_asistencia if user else False
            return render_template("home.html", user=user, user_confirmed=user_confirmed)
        else:
            flash("Debes verificar tu identidad para continuar.")
            return redirect(url_for("verify"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("home"))
    
    if request.method == "POST":
        identificacion = request.form["identificacion"]
        verification_method = request.form["verification_method"]  # Obtener el método de verificación seleccionado
        
        user = User.query.filter_by(identificacion=identificacion).first()
       
        
        # Verificar si el usuario existe
        if user:
            
            if user.confirma_asistencia:
                flash("Ya has confirmado tu asistencia.")
                return redirect(url_for("login"))
            
            # Comprobar si ha pasado una hora desde el último OTP
            if user.ultimo_otp_generado:
                tiempo_limite = user.ultimo_otp_generado + timedelta(hours=1)
                if datetime.now() < tiempo_limite:
                    tiempo_restante = (tiempo_limite - datetime.now()).seconds // 60
                    flash(f"Debes esperar {tiempo_restante} minutos antes de generar otro código.")
                    return redirect(url_for("login"))
            
            
            
            # Seleccionar el método de verificación
            if verification_method == "sms":
                
                try: 
                    phone = request.form["phone"]
                    
                    client.verify.v2.services(VERIFY_SERVICE_SID).verifications.create(
                        to='+57'+str(phone), channel="sms"
                    )
            
                    user.numero_celular = phone
                    user.ultimo_otp_generado = datetime.now()
                    user.verificado = False    
                    db.session.add(user)
                    db.session.commit()
                    
                except Exception as e:
                    flash("Ha ocurrido un error al enviar el código de verificación por SMS.")
                    print(e)
                    return redirect(url_for("login"))
                    
            elif verification_method == "email":
                
                try:
                    email = request.form["email"]
                    client.verify.v2.services(VERIFY_SERVICE_SID).verifications.create(
                    to=email, channel="email"
                    )
                    user.correo = email
                    user.ultimo_otp_generado = datetime.now()
                    user.verificado = False
                    db.session.add(user)
                    db.session.commit()
                except Exception as e:
                    flash("Ha ocurrido un error al enviar el código de verificación por email.")
                    return redirect(url_for("login"))
                    
                
                
            elif verification_method == "whatsapp":
                # WhatsApp
                sandbox_number = "whatsapp:+14155238886"
                client.messages.create(
                    body="¡Hola! Este es un mensaje de prueba desde Flask y Twilio.",
                    from_="whatsapp:+14155238886",  # Número de WhatsApp proporcionado por Twilio Sandbox
                    to='whatsapp:+573223907764'
                )
                

            session["user"] = identificacion  # Guarda la identificación en sesión para identificar al usuario
            session["verification_method"] = verification_method  # Guardar el método de verificación
            return redirect(url_for("verify"))
        else:
            flash("Identificación no encontrada.")
            return redirect(url_for("login"))

    return render_template("login.html")



@app.route("/verify", methods=["GET", "POST"])
def verify():
    if "user" not in session:
        return redirect(url_for("login"))
    
    if request.method == "POST":
        code = request.form["code"]
        user = User.query.filter_by(identificacion=session["user"]).first()
        verification_method = session["verification_method"]

        if verification_method == "sms" or verification_method == "whatsapp":
            to = '+57' + user.numero_celular
        elif verification_method == "email":
            to = user.correo
            
        try:
            # Verificar el código enviado por el usuario
            verification_check = client.verify.services(VERIFY_SERVICE_SID).verification_checks.create(
            to=to, code=code
        )

            if verification_check.status == "approved":
                user.verificado = True
                db.session.add(user)
                db.session.commit()
                return redirect(url_for("home"))
            else:
                flash("Código inválido. Inténtalo de nuevo.")
                return redirect(url_for("verify"))
        
        except TwilioRestException as e:
            flash(f"Error de verificación")
            return redirect(url_for("verify"))

    return render_template("verify.html")

@app.route("/confirmar_asistencia", methods=["POST"])
def confirmar_asistencia():
    if "user" not in session:
        flash("Debes iniciar sesión para confirmar tu asistencia.")
        return redirect(url_for("login"))
    
    # Obtener el usuario de la base de datos
    user = User.query.filter_by(identificacion=session["user"]).first()
    
   
    if user:
        user.confirma_asistencia = True  # Actualizar la confirmación de asistencia
        db.session.commit()  # Guardar cambios en la base de datos
        flash("Asistencia confirmada exitosamente.")
    else:
        flash("Usuario no encontrado.")

    return redirect(url_for("home"))

@app.route("/admin")
def admin():
    user_admin= os.getenv("ADMIN")
    password_admin= os.getenv("PASSWORD_ADMIN")
    if request.method == "POST":
        user = request.form["user"]
        password = request.form["password"]
        if user == user_admin and password == password_admin:
            return redirect(url_for("lista_usuarios"))
        else:
            flash("Usuario o contraseña incorrectos.")
            return redirect(url_for("admin"))
    return render_template("admin.html")
    
    

@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Sesión cerrada exitosamente.")
    return redirect(url_for("login"))

# Función para cargar los usuarios desde un archivo JSON
def load_users_from_json(file_path):
    # Abrir y leer el archivo JSON
    with open(file_path, 'r', encoding='utf-8') as file:
        users_data = json.load(file)
    
    # Verificar si ya hay usuarios en la base de datos
    if User.query.count() == 0:  # Si no hay usuarios en la base de datos
        # Iterar a través de la lista de usuarios en el archivo JSON
        for user_data in users_data:
            # Crear un nuevo objeto User para cada entrada en el JSON
            user = User(
                identificacion=str(user_data['CEDULA']),  # Suponiendo que 'CEDULA' es el número de identificación
                nombres=user_data['NOMBRES'],
                apellidos=user_data['APELLIDOS'],
                departamento=user_data['DEPARTAMENTO'],
                municipio=user_data['MUNICIPIO'],
                correo=user_data['CORREO'],
                numero_celular=user_data['CELULAR'],
                confirma_asistencia=False  # Por defecto, el usuario no ha confirmado asistencia
            )
            
            # Agregar el usuario a la sesión
            db.session.add(user)

        # Confirmar la transacción para guardar los cambios en la base de datos
        db.session.commit()

if __name__ == "__main__":
    
    # Crear las tablas (si no existen) antes de iniciar el servidor
    with app.app_context():
        db.create_all()
        load_users_from_json('fixture/user.json')
        
    
    # Iniciar la aplicación Flask
    port = int(os.getenv("PORT", 8080))
    
    # Iniciar la app Flask en el puerto correcto
    app.run(host="0.0.0.0", port=port)
from flask import Flask, render_template_string, request, redirect, url_for, session, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy 
from functools import wraps
import json
import os
import io
import qrcode
from datetime import datetime, timedelta

try:
    from pywebpush import webpush, WebPushException
except ImportError:
    webpush = None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_id' not in session:
            flash("Por favor inicia sesión para continuar.", "warning")
            return redirect(url_for('inicio'))
        return f(*args, **kwargs)
    return decorated_function

class CurrentUserProxy:
    @property
    def id(self):
        return session.get('usuario_id')
    @property
    def nombre(self):
        if 'usuario_id' in session:
            user = Usuario.query.get(session['usuario_id'])
            return user.nombre if user else ""
        return ""

current_user = CurrentUserProxy()

app = Flask(__name__)
app.secret_key = "clave_secreta_para_sesiones_estudiantiles"

database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///cadena_v3.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
from sqlalchemy import text

# -------------------------------------------------------------------
# MODELOS DE BASE DE DATOS
# -------------------------------------------------------------------
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    correo = db.Column(db.String(100), unique=True, nullable=False)
    institucion = db.Column(db.String(100), nullable=False)
    contacto = db.Column(db.String(100), nullable=False)
    carnet = db.Column(db.String(7), unique=True, nullable=False)

class Publicacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False)  # 'necesidad' o 'apoyo'
    titulo = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    materia_area = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(20), default ='activa') 
    fecha_creacion = db.Column(db.DateTime, default=datetime.now)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    usuario = db.relationship('Usuario', backref='publicaciones')

class SolicitudContacto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    publicacion_id = db.Column(db.Integer, db.ForeignKey('publicacion.id'), nullable=False)
    solicitante_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    estado = db.Column(db.String(20), default='pendiente')  # 'pendiente', 'en contacto', 'finalizado'

    publicacion = db.relationship('Publicacion', backref='solicitudes')
    solicitante = db.relationship('Usuario', backref='solicitudes_hechas')
    with app.app_context():
        db.create_all()

class Notificacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    mensaje = db.Column(db.String(255), nullable=False)
    tipo = db.Column(db.String(50), default='info')
    leida = db.Column(db.Boolean, default=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

    usuario = db.relationship('Usuario', backref=db.backref('notificaciones', lazy=True))

# Modelo nuevo para almacenar las suscripciones push de cada dispositivo
class PushSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    endpoint = db.Column(db.Text, nullable=False, unique=True)
    p256dh = db.Column(db.String(255), nullable=False)
    auth = db.Column(db.String(255), nullable=False)

def enviar_push_externa(usuario_id, titulo, mensaje):
    if not webpush:
        return
    suscripciones = PushSubscription.query.filter_by(usuario_id=usuario_id).all()
    vapid_private_key = os.environ.get('VAPID_PRIVATE_KEY')
    vapid_email = os.environ.get('VAPID_EMAIL', 'mailto:admin@cadenadefavores.edu')
    
    if not vapid_private_key:
        return  # Si no hay llaves VAPID configuradas, omite el envío push nativo sin romper la app

    for sub in suscripciones:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth}
                },
                data=json.dumps({"title": titulo, "body": mensaje}),
                vapid_private_key=vapid_private_key,
                vapid_claims={"sub": vapid_email}
            )
        except Exception as ex:
            print(f"Error enviando push externa: {ex}")

def registrar_notificacion(usuario_id, mensaje, tipo='info'):
    try:
        nueva_notif = Notificacion(usuario_id=usuario_id, mensaje=mensaje, tipo=tipo)
        db.session.add(nueva_notif)
        db.session.commit()
        
        # Dispara la notificación push externa hacia el dispositivo (incluso con app cerrada)
        enviar_push_externa(usuario_id, "Cadena de Favores Estudiantiles", mensaje)
    except Exception as e:
        db.session.rollback()
        print(f"Error registrando notificación: {e}")

# -------------------------------------------------------------------
# PLANTILLAS HTML EMBEBIDAS
# -------------------------------------------------------------------
BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cadena de Favores Estudiantiles</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#4f46e5">
    <script>
     // Pega aquí tu llave pública (publicKey) generada en VapidKeys.com
const publicVapidKey = "BJvnANoeOraT2AfAKE4rO2pLHrabAwTeA7C5QhrOV1gH6Ghg1u8mo0MwJdS2lrQ73uq6eWAV1UEOJc1kktFNwcw";

function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/\-/g, '+').replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

document.addEventListener('DOMContentLoaded', () => {
    const btnPush = document.getElementById('btn-activar-push');
    if (btnPush) {
        btnPush.addEventListener('click', async () => {
            if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
                alert("Tu navegador no soporta notificaciones push.");
                return;
            }

            try {
                const reg = await navigator.serviceWorker.register('/sw.js');
                const permission = await Notification.requestPermission();
                
                if (permission !== 'granted') {
                    alert("El permiso de notificaciones fue denegado.");
                    return;
                }

                const subscription = await reg.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: urlBase64ToUint8Array(publicVapidKey)
                });

                const response = await fetch('/api/save-subscription', {
                    method: 'POST',
                    body: JSON.stringify(subscription),
                    headers: { 'Content-Type': 'application/json' }
                });

                if (response.ok) {
                    alert("¡Notificaciones activadas y guardadas correctamente!");
                } else {
                    alert("Error al guardar la suscripción en el servidor.");
                }
            } catch (error) {
                console.error('Error:', error);
                alert("Error al activar: " + error.message);
            }
        });
    }
});
    </script>
</head>
<body class="bg-slate-900 min-h-screen text-gray-800 relative font-sans">
    <div class="fixed inset-0 bg-gradient-to-br from-slate-900 via-indigo-950 to-purple-950 -z-10"></div>
    <div class="fixed top-0 left-1/4 w-96 h-96 bg-indigo-600/10 rounded-full blur-3xl pointer-events-none -z-10"></div>

    <nav class="bg-slate-900/80 backdrop-blur-md border-b border-white/10 text-white p-4 sticky top-0 z-50">
        <div class="max-w-6xl mx-auto flex justify-between items-center">
            <a href="{{ url_for('muro') }}" class="text-xl font-bold flex items-center gap-2 hover:opacity-90 transition-opacity">
                <span>🤝</span> Cadena de Favores Estudiantiles
            </a>
            
            <div class="flex items-center gap-4 text-sm font-medium">
                <a href="{{ url_for('muro') }}" class="hover:text-indigo-300 transition-colors">Muro</a>
                <a href="{{ url_for('nueva_publicacion') }}" class="bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-lg transition-all shadow-md">
                    + Publicar
                </a>
                
                {% if 'usuario_id' in session %}
                    <div class="flex items-center gap-2 pl-3 border-l border-white/20">
                        <span class="text-xs text-indigo-200">Hola, <strong>{{ session.get('usuario_nombre', 'Estudiante') }}</strong></span>
                        <a href="{{ url_for('logout') }}" class="bg-red-500/20 hover:bg-red-500/40 text-red-200 text-xs px-2.5 py-1 rounded-md border border-red-500/30 transition-all">
                            Cerrar Sesión
                        </a>
                    </div>
                {% endif %}
            </div>
        </div>
    </nav>

    <div class="max-w-6xl mx-auto px-6 pt-6">
        <div class="bg-gradient-to-r from-indigo-900/60 via-purple-900/60 to-slate-900/60 border border-indigo-500/30 backdrop-blur-md rounded-2xl p-4 text-white shadow-lg flex flex-col md:flex-row items-center justify-between gap-4">
            <div class="flex items-center gap-3">
                <span class="text-3xl">💡</span>
                <div>
                    <h3 class="font-bold text-indigo-200 text-sm md:text-base">¡El conocimiento compartido se multiplica!</h3>
                    <p class="text-xs text-gray-300">Un pequeño apoyo hoy en el muro puede ser el impulso profesional que tu compañero necesita.</p>
                </div>
            </div>
        </div>
    </div>

    <main class="max-w-6xl mx-auto p-6 relative">
"""

REGISTRO_TEMPLATE = BASE_TEMPLATE + """
<div class="max-w-md mx-auto my-8 bg-white p-8 rounded-2xl shadow-xl border border-gray-100 transform transition-all hover:shadow-2xl">
    <div class="text-center mb-6">
        <div class="w-16 h-16 bg-gradient-to-tr from-indigo-500 to-purple-600 text-white rounded-full flex items-center justify-center mx-auto mb-3 shadow-lg">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
            </svg>
        </div>
        <h2 class="text-3xl font-extrabold text-gray-800 tracking-tight">Acceso Estudiantil</h2>
    </div>

    <form method="POST" action="{{ url_for('registro') }}" class="space-y-4">
        <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-gray-600 mb-1">Nombre completo</label>
            <input type="text" name="nombre" required placeholder="Ej. Gabriela Sofía" 
                class="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none">
        </div>
        <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-gray-600 mb-1">Correo institucional</label>
            <input type="email" name="correo" required placeholder="estudiante@universidad.edu" 
                class="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none">
        </div>
        <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-gray-600 mb-1">Institución / Facultad</label>
            <input type="text" name="institucion" required placeholder="Ej. Facultad de Ingeniería" 
                class="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none">
        </div>
        <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-gray-600 mb-1">Contacto / Teléfono</label>
            <input type="text" name="contacto" required placeholder="+502 5555-5555" 
                class="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none">
        </div>
        <div class="mb-4">
            <label class="block text-sm font-medium text-gray-700">Número de Carnet</label>
            <input type="text" name="carnet" required maxlength="7" pattern="[0-9]{7}" title="Debe tener 7 dígitos"
                   class="w-full border p-2 rounded mt-1" placeholder="Ej. 2023123">
        </div>
        <button type="submit" 
            class="w-full mt-2 bg-gradient-to-r from-indigo-600 to-purple-600 text-white py-3 px-4 rounded-xl font-bold shadow-md hover:opacity-90 transition-all flex items-center justify-center gap-2">
            <span>Iniciar Cadena de Favores</span>
        </button>
    </form>
</div>
</main></body></html>
""" 

COMPROMISO_TEMPLATE = BASE_TEMPLATE + """
<div id="pantallaCompromiso" onclick="window.location.href='{{ url_for('muro') }}';" class="fixed inset-0 bg-slate-900 z-50 flex items-center justify-center p-4 cursor-pointer select-none">
    <div class="bg-slate-800 border border-slate-700 max-w-lg w-full rounded-2xl p-6 sm:p-8 shadow-2xl text-center">
        <div class="text-4xl mb-3">🤝</div>
        <h2 class="text-2xl font-extrabold text-indigo-300 mb-4">Mi compromiso es conmigo.</h2>
        <div class="space-y-4 text-slate-300 text-sm sm:text-base leading-relaxed text-justify mb-6">
        <p>
        Al recibir apoyo, me comprometo conmigo mismo a seguir esta cadena y ayudar a alguien más cuando esté dentro de mis posibilidades.
        </p>
         <p>
       Lo hago porque quiero ser consecuente con la solidaridad que hoy recibo. Puedo compartir lo que sé, dedicar un poco de mi tiempo u ofrecer una mano cuando alguien la necesite.
         </p>
        <p class="text-center font-bold text-amber-300 text-base sm:text-lg pt-2">
           💛 Hoy recibo. Mañana puedo ser yo quien ayude.
         </p>
        </div>
            
        <!-- Indicador / Casilla -->
        <div class="inline-flex items-center gap-3 bg-slate-900/60 px-4 py-3 rounded-xl border border-slate-700/80 mb-4">
        <input type="checkbox" checked class="w-5 h-5 accent-indigo-500 rounded cursor-pointer pointer-events-none">
        <span class="text-xs sm:text-sm text-slate-200 font-medium">
          Asumo este compromiso personal de pagar el favor hacia adelante.
          </span>
         </div>
            
         <!-- Instrucción de Avance -->
         <p class="text-xs text-indigo-400 font-semibold animate-pulse mt-2">
          ✨ Haz clic en cualquier parte de la pantalla para avanzar al muro
        </p>
     </div>
 </div>
"""

MURO_TEMPLATE = BASE_TEMPLATE + """
<div class="flex flex-col sm:flex-row justify-between items-center gap-4 mb-6 bg-white p-4 rounded-xl shadow-md">
    <div>
        <h2 class="text-2xl font-bold text-gray-800">Muro de Necesidades y Apoyos</h2>
    </div>
    <div class="flex items-center gap-2">
        <!-- Botón de Instalación Informativo (Modal) -->
        <button id="btn-instalar" onclick="abrirModalInstalacion()" class="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg font-semibold shadow transition-all text-sm">
            📱 Instalar App
        </button>

        <!-- Ventana Modal Informativa -->
        <div id="modal-instalacion" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
            <div class="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl relative">
                <h3 class="text-xl font-bold text-gray-800 mb-4">📱 Instala nuestra Red de Apoyo</h3>
                
                <div class="space-y-4 text-sm text-gray-600">
                    <div class="bg-indigo-50 p-3 rounded-lg">
                        <p class="font-bold text-indigo-900 mb-1">🤖 Para Android (Google Chrome):</p>
                        <ol class="list-decimal list-inside space-y-1 text-indigo-800">
                            <li>Toca los tres puntos (<span class="font-bold">⋮</span>) arriba a la derecha.</li>
                            <li>Selecciona <span class="font-bold">"Instalar aplicación"</span> o <span class="font-bold">"Añadir a pantalla principal"</span>.</li>
                            <li>Confirma la instalación.</li>
                        </ol>
                    </div>

                    <div class="bg-gray-50 p-3 rounded-lg">
                        <p class="font-bold text-gray-900 mb-1">🍎 Para iPhone / iPad (Safari):</p>
                        <ol class="list-decimal list-inside space-y-1 text-gray-700">
                            <li>Toca el botón de <span class="font-bold">Compartir</span> (cuadrado con flecha <span class="font-bold">⬆️</span>) abajo en Safari.</li>
                            <li>Desplázate y selecciona <span class="font-bold">"Añadir a pantalla de inicio"</span>.</li>
                            <li>Pulsa en <span class="font-bold">"Añadir"</span> arriba a la derecha.</li>
                        </ol>
                    </div>
                </div>

                <div class="mt-6 text-right">
                    <button onclick="cerrarModalInstalacion()" class="bg-gray-800 hover:bg-gray-900 text-white px-4 py-2 rounded-lg text-sm font-semibold transition">
                        Entendido
                    </button>
                </div>
            </div>
        </div>

        <a href="{{ url_for('nueva_publicacion') }}" class="bg-green-600 text-white px-4 py-2 rounded shadow hover:bg-green-700 font-semibold text-sm">+ Publicar</a>
    </div>
</div>

<style>
  @media (display-mode: standalone) {
    #btn-instalar {
      display: none !important;
    }
  }
</style>

<div class="grid md:grid-cols-2 gap-4">
    {% for pub in publicaciones %}
    <div class="bg-white p-5 rounded-lg shadow border-l-4 {% if pub.tipo == 'necesidad' %}border-amber-500{% else %}border-emerald-500{% endif %}">
        <div class="flex justify-between items-start">
            <span class="text-xs font-bold uppercase px-2 py-1 rounded {% if pub.tipo == 'necesidad' %}bg-amber-100 text-amber-800{% else %}bg-emerald-100 text-emerald-800{% endif %}">
                {{ pub.tipo }}
            </span>
            <span class="text-xs text-gray-500">{{ pub.materia_area }}</span>
        </div>
        <h3 class="text-lg font-bold mt-2">{{ pub.titulo }}</h3>
        <p class="text-gray-600 text-sm mt-1">{{ pub.descripcion }}</p>
        
        <div class="mt-4 pt-3 border-t text-xs text-gray-500 flex justify-between items-center">
            <span>Publicado de forma confidencial</span>
            {% if pub.usuario_id != session['usuario_id'] %}
                <form action="{{ url_for('solicitar_contacto', id=pub.id) }}" method="POST">
                    <button class="bg-indigo-600 text-white px-3 py-1 rounded hover:bg-indigo-700">Solicitar Contacto</button>
                </form>
            {% else %}
                <span class="italic font-semibold text-indigo-600">Tu publicación</span>
            {% endif %}
        </div>
    </div>
    {% else %}
        <p class="text-gray-500 col-span-2 text-center py-8">No hay publicaciones todavía. ¡Sé el primero en publicar!</p>
    {% endfor %}
</div>

<!-- Botón Mis Solicitudes con Badge de Notificaciones dinámico y sonoro -->
<div class="relative inline-block my-4">
    <a href="/mis-solicitudes" class="inline-flex items-center px-4 py-2 bg-indigo-600 text-white rounded-lg shadow hover:bg-indigo-700 transition font-semibold text-sm">
        📬 Mis Solicitudes
    </a>
    <span id="badge-contador" class="hidden absolute -top-2 -right-2 bg-red-600 text-white text-xs font-bold px-2 py-0.5 rounded-full shadow">
        0
    </span>
</div>

<!-- Elemento de audio para las alertas -->
<audio id="tono-notificacion" src="https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3" preload="auto"></audio>

<!-- Botón en tu HTML (sin onclick inline) -->
<button id="btn-activar-push" class="px-4 py-2 bg-indigo-600 text-white rounded-lg shadow font-medium my-2">
    🔔 Activar Notificaciones Push
</button>

<script>
document.addEventListener('DOMContentLoaded', () => {
    const btnPush = document.getElementById('btn-activar-push');
    if (btnPush) {
        btnPush.addEventListener('click', async () => {
            console.log("Botón presionado, iniciando registro...");

            if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
                alert("Tu navegador no soporta notificaciones push.");
                return;
            }

            try {
                // 1. Registrar el Service Worker
                const reg = await navigator.serviceWorker.register('/sw.js');
                console.log('Service Worker registrado:', reg);

                // 2. Pedir permiso formalmente
                const permission = await Notification.requestPermission();
                console.log('Permiso obtenido:', permission);

                if (permission !== 'granted') {
                    alert("El permiso de notificaciones fue denegado.");
                    return;
                }

                // Tu llave pública VAPID
                const publicVapidKey = 'B3vnAlosOraT2AfAKE4r02pLHrabAwA7CSQhrOV1gHGhgIu0MoWJds21rQ73uq6eWAV1UEOJc1kktFNwcW';

                // 3. Suscribir el dispositivo
                const subscription = await reg.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: urlBase64ToUint8Array(publicVapidKey)
                });
                console.log('Suscripción push creada con éxito.');

                // 4. Enviar los datos al servidor Flask
                const response = await fetch('/api/save-subscription', {
                    method: 'POST',
                    body: JSON.stringify(subscription),
                    headers: { 'Content-Type': 'application/json' }
                });

                if (response.ok) {
                    alert("¡Notificaciones activadas y guardadas correctamente!");
                } else {
                    alert("Hubo un error al guardar la suscripción en el servidor.");
                }

            } catch (error) {
                console.error('Error detallado:', error);
                alert("Error al activar: " + error.message);
            }
        });
    }
});

function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/\-/g, '+').replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}
</script>
"""

NUEVA_PUB_TEMPLATE = BASE_TEMPLATE + """
<div class="max-w-lg mx-auto bg-white p-6 rounded-lg shadow">
    <h2 class="text-xl font-bold text-gray-800 mb-4">Nueva Publicación</h2>
    <form method="POST" class="space-y-4">
        <div>
            <label class="block text-sm font-medium">¿Qué deseas hacer?</label>
            <select name="tipo" class="w-full border p-2 rounded mt-1">
                <option value="necesidad">Pedir Apoyo (Necesito ayuda)</option>
                <option value="apoyo">Ofrecer Apoyo (Puedo ayudar)</option>
            </select>
        </div>
        <div>
            <label class="block text-sm font-medium">Materia o Área de Conocimiento:</label>
            <input type="text" name="materia_area" placeholder="Ej. Cálculo I, Programación" required class="w-full border p-2 rounded mt-1">
        </div>
        <div>
            <label class="block text-sm font-medium">Título breve:</label>
            <input type="text" name="titulo" placeholder="Ej. Ayuda con derivadas" required class="w-full border p-2 rounded mt-1">
        </div>
        <div>
            <label class="block text-sm font-medium">Descripción detallada:</label>
            <textarea name="descripcion" rows="4" required class="w-full border p-2 rounded mt-1"></textarea>
        </div>
        <button type="submit" class="w-full bg-indigo-600 text-white p-2 rounded font-bold hover:bg-indigo-700">Publicar</button>
    </form>
</div>
"""

SOLICITUDES_TEMPLATE = BASE_TEMPLATE + """
<h2 class="text-2xl font-bold text-white mb-6">Centro de Comunicación Confidencial</h2>
<div class="space-y-6">
  <div class="bg-white p-5 rounded-lg shadow">
    <h3 class="text-lg font-bold mb-3 border-b pb-2">Solicitudes Recibidas</h3>
    {% if recibidas %}
      {% for sol in recibidas %}
        <div class="p-3 border-b last:border-0 flex justify-between items-center">
          <div>
            <p class="font-medium text-sm">Publicación: <strong>{{ sol.publicacion.titulo }}</strong></p>
            <p class="text-xs text-gray-600">Solicitante: <strong>{{ sol.solicitante.nombre }}</strong></p>
            <p class="text-xs text-gray-500 mt-1">Estado: <span class="font-bold text-amber-600">{{ sol.estado }}</span></p>
          </div>
          <div>
             {% if sol.estado == 'pendiente' %}
              <!-- El dueño AUTORIZA enviar sus datos de contacto -->
              <form action="/aceptar-solicitud/{{ sol.id }}" method="POST">
                <button type="submit" class="text-xs bg-green-600 text-white px-3 py-1.5 rounded font-bold hover:bg-green-700">
                  Autorizar y Compartir Datos
                </button>
              </form>

              {% elif sol.estado == 'aceptado' %}
    <!-- En este punto el dueño ya aceptó y se comparten los datos de ambos de inmediato -->
    <div class="mt-2 p-3 bg-green-50 border border-green-200 rounded text-xs">
        <p class="font-bold text-green-800">✅ ¡Datos de Contacto Compartidos!</p>
        <p class="mt-1"><strong>Dueño de la publicación:</strong> {{ sol.publicacion.usuario.nombre }} — 📞 Teléfono: {{ sol.publicacion.usuario.contacto }}</p>
        <p><strong>Persona interesada (Solicitante):</strong> {{ sol.solicitante.nombre }} — 📞 Teléfono: {{ sol.solicitante.contacto }}</p>
        <p class="text-gray-600 mt-1 italic">Ambos ya pueden comunicarse para coordinar el apoyo.</p>
    </div>
              
            {% elif sol.estado == 'brindado' %}
              <form action="/validar-apoyo/{{ sol.id }}" method="POST">
                <button type="submit" class="text-xs bg-blue-600 text-white px-3 py-1.5 rounded font-bold">Validar Apoyo</button>
              </form>
            {% else %}
              <span class="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded">Completado</span>
            {% endif %}
          </div>
        </div>
      {% endfor %}
    {% else %}
      <p class="text-sm text-gray-500">No tienes solicitudes pendientes.</p>
    {% endif %}
  </div>

  <div class="bg-white p-5 rounded-lg shadow">
    <h3 class="text-lg font-bold mb-3 border-b pb-2">Solicitudes Enviadas</h3>
    {% if enviadas %}
      {% for sol in enviadas %}
        <div class="p-3 border-b last:border-0">
          <p class="font-medium text-sm">Publicación: <strong>{{ sol.publicacion.titulo }}</strong></p>
          <p class="text-xs text-gray-500 mt-1">Estado: <span class="font-bold">{{ sol.estado }}</span></p>
          {% if sol.estado == 'aceptado' %}
            <div class="mt-2 p-3 bg-green-50 rounded border border-green-200 text-xs">
              <p class="text-green-800 font-bold mb-1">✅ Contacto Autorizado: {{ sol.publicacion.usuario.contacto }}</p>
              <form action="/marcar-brindado/{{ sol.id }}" method="POST" class="mt-2">
                <button type="submit" class="text-xs bg-blue-600 text-white px-3 py-1 rounded">Marcar como Apoyo Brindado</button>
              </form>
            </div>
          {% endif %}
        </div>
      {% endfor %}
    {% else %}
      <p class="text-sm text-gray-500">No has enviado solicitudes.</p>
    {% endif %}
  </div>
</div>
"""

QR_TEMPLATE = BASE_TEMPLATE + """
<div class="text-center bg-white p-8 rounded-lg shadow max-w-md mx-auto">
    <h2 class="text-xl font-bold mb-2">Escanea este Código QR</h2>
    <img src="{{ url_for('imagen_qr') }}" alt="Código QR" class="mx-auto border p-2 rounded">
</div>
"""

# -------------------------------------------------------------------
# RUTAS DE LA APLICACIÓN
# -------------------------------------------------------------------
@app.route('/')
def inicio():
    if 'usuario_id' in session:
        return redirect(url_for('muro'))
    return render_template_string(REGISTRO_TEMPLATE)

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if 'usuario_id' in session:
        return redirect(url_for('muro'))
        
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        correo = request.form.get('correo', '').strip()
        institucion = request.form.get('institucion', '').strip()
        contacto = request.form.get('contacto', '').strip()
        carnet = request.form.get('carnet', '').strip()

        if not carnet.isdigit() or len(carnet) != 7:
            flash('El carnet debe tener exactamente 7 dígitos.', 'error')
            return redirect(url_for('inicio'))

        carnet_existente = Usuario.query.filter_by(carnet=carnet).first()
        if carnet_existente:
            session['usuario_id'] = carnet_existente.id
            session['usuario_nombre'] = carnet_existente.nombre
            return redirect(url_for('compromiso'))

        nuevo_usuario = Usuario(nombre=nombre, correo=correo, institucion=institucion, contacto=contacto, carnet=carnet)
        db.session.add(nuevo_usuario)
        db.session.commit()

        session['usuario_id'] = nuevo_usuario.id
        session['usuario_nombre'] = nuevo_usuario.nombre
        return redirect(url_for('compromiso'))

    return render_template_string(REGISTRO_TEMPLATE)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('inicio'))

@app.route('/compromiso')
def compromiso():
    if 'usuario_id' not in session:
        return redirect(url_for('inicio'))
    return render_template_string(COMPROMISO_TEMPLATE)

@app.route('/api/save-subscription', methods=['POST'])
def save_subscription():
    if 'usuario_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401
    
    sub_data = request.get_json()
    if not sub_data or not sub_data.get('endpoint'):
        return jsonify({'error': 'Datos de suscripción inválidos'}), 400
        
    usuario_id = session['usuario_id']
    endpoint = sub_data.get('endpoint')
    keys = sub_data.get('keys', {})
    
    # Comprobar si ya existe la suscripción para este endpoint
    existente = PushSubscription.query.filter_by(endpoint=endpoint).first()
    
    if not existente:
        nueva_sub = PushSubscription(
            usuario_id=usuario_id,
            endpoint=endpoint,
            p256dh=keys.get('p256dh'),
            auth=keys.get('auth')
        )
        db.session.add(nueva_sub)
        db.session.commit()
    
    return jsonify({'success': True}), 200                                 
@app.route('/muro')
def muro():
    if 'usuario_id' not in session:
        return redirect(url_for('registro'))
    
    limite_tiempo = datetime.now() - timedelta(days=3)
    try:
        vencidas = Publicacion.query.filter(Publicacion.fecha_creacion < limite_tiempo, Publicacion.estado != 'completada').all()
        for pub in vencidas:
            db.session.delete(pub)
        db.session.commit()
    except Exception:
        db.session.rollback()

    publicaciones = Publicacion.query.filter(Publicacion.estado != 'completada').order_by(Publicacion.fecha_creacion.desc()).all()
    return render_template_string(MURO_TEMPLATE, publicaciones=publicaciones, usuario_id=session['usuario_id'])
    
@app.route('/nueva-publicacion', methods=['GET', 'POST'])
def nueva_publicacion():
    if 'usuario_id' not in session:
        return redirect(url_for('registro'))
    if request.method == 'POST':
        pub = Publicacion(
            tipo=request.form['tipo'],
            materia_area=request.form['materia_area'],
            titulo=request.form['titulo'],
            descripcion=request.form['descripcion'],
            usuario_id=session['usuario_id']
        )
        db.session.add(pub)
        db.session.commit()
        return redirect(url_for('muro'))
    return render_template_string(NUEVA_PUB_TEMPLATE)

@app.route('/solicitar_contacto/<int:id>', methods=['POST'])
@login_required
def solicitar_contacto(id):
    publicacion = Publicacion.query.get_or_404(id)
    usuario_actual_id = session.get('usuario_id')
    
    if publicacion.usuario_id == usuario_actual_id:
        flash("No puedes solicitar contacto a tu propia publicación.", "warning")
        return redirect(url_for('muro'))

    existente = SolicitudContacto.query.filter_by(publicacion_id=id, solicitante_id=usuario_actual_id).first()
    if not existente:
        nueva_solicitud = SolicitudContacto(publicacion_id=id, solicitante_id=usuario_actual_id, estado='pendiente')
        db.session.add(nueva_solicitud)
        publicacion.estado = 'en_proceso'

        usuario_actual = Usuario.query.get(usuario_actual_id)
        nombre_usuario = usuario_actual.nombre if usuario_actual else "Un estudiante"

        registrar_notificacion(publicacion.usuario_id, f"¡{nombre_usuario} quiere contactarte para: '{publicacion.titulo}'!", tipo='contacto')
        db.session.commit()
        flash("¡Solicitud enviada con éxito!", "success")
    return redirect(url_for('muro'))

@app.route('/api/verificar-nuevas-solicitudes', methods=['GET'])
@login_required
def verificar_nuevas_solicitudes():
    usuario_id = session.get('usuario_id')
    notificaciones = Notificacion.query.filter_by(usuario_id=usuario_id, leida=False).all()
    cambios_externos = [n for n in notificaciones if n.tipo in ['contacto', 'actualizacion', 'proceso', 'cierre']]
    return jsonify({
        'cantidad': len(notificaciones),
        'tiene_cambio_externo': len(cambios_externos) > 0,
        'mensajes': [n.mensaje for n in notificaciones]
    })

@app.route('/aceptar-solicitud/<int:sol_id>', methods=['POST'])
def aceptar_solicitud(sol_id):
    if 'usuario_id' not in session:
        return redirect(url_for('inicio'))
    solicitud = SolicitudContacto.query.get_or_404(sol_id)
    if solicitud.publicacion.usuario_id != session['usuario_id']:
        return redirect(url_for('mis_solicitudes'))

    solicitud.estado = 'aceptado'
    registrar_notificacion(solicitud.solicitante_id, f"¡{solicitud.publicacion.usuario.nombre} aceptó tu solicitud para '{solicitud.publicacion.titulo}'!", tipo='actualizacion')
    db.session.commit()
    return redirect(url_for('mis_solicitudes'))

@app.route('/marcar-brindado/<int:sol_id>', methods=['POST'])
def marcar_brindado(sol_id):
    if 'usuario_id' not in session:
        return redirect(url_for('registro'))
    solicitud = SolicitudContacto.query.get_or_404(sol_id)
    if solicitud.solicitante_id == session['usuario_id']:
        solicitud.estado = 'brindado'
        registrar_notificacion(solicitud.publicacion.usuario_id, f"El apoyo en '{solicitud.publicacion.titulo}' fue marcado como brindado.", tipo='actualizacion')
        db.session.commit()
    return redirect(url_for('mis_solicitudes'))

@app.route('/validar-apoyo/<int:sol_id>', methods=['POST'])
def validar_apoyo(sol_id):
    if 'usuario_id' not in session:
        return redirect(url_for('registro'))
    solicitud = SolicitudContacto.query.get_or_404(sol_id)
    if solicitud.publicacion.usuario_id == session['usuario_id']:
        solicitud.estado = 'completado'
        solicitud.publicacion.estado = 'completada'
        registrar_notificacion(solicitud.solicitante_id, f"Se ha validado y cerrado la solicitud para '{solicitud.publicacion.titulo}'.", tipo='cierre')
        db.session.commit()
    return redirect(url_for('mis_solicitudes'))

@app.route('/mis-solicitudes')
def mis_solicitudes():
    if 'usuario_id' not in session:
        return redirect(url_for('registro'))
    usuario_id = session['usuario_id']
    Notificacion.query.filter_by(usuario_id=usuario_id, leida=False).update({'leida': True})
    db.session.commit()

    recibidas = SolicitudContacto.query.join(Publicacion).filter(Publicacion.usuario_id == usuario_id, SolicitudContacto.estado != 'completado').all()
    enviadas = SolicitudContacto.query.filter(SolicitudContacto.solicitante_id == usuario_id, SolicitudContacto.estado != 'completado').all()
    return render_template_string(SOLICITUDES_TEMPLATE, recibidas=recibidas, enviadas=enviadas)

@app.route('/qr')
def generar_qr():
    return render_template_string(QR_TEMPLATE)

@app.route('/imagen-qr')
def imagen_qr():
    img = qrcode.make(request.host_url + "registro")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png")

@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "Cadena de Favores Estudiantiles",
        "short_name": "Favores",
        "start_url": "/muro",
        "display": "standalone",
        "background_color": "#0f172a",
        "theme_color": "#4f46e5",
        "icons": [
            {"src": "https://cdn-icons-png.flaticon.com/512/3076/3076129.png", "sizes": "192x192", "type": "image/png"},
            {"src": "https://cdn-icons-png.flaticon.com/512/3076/3076129.png", "sizes": "512x512", "type": "image/png"}
        ]
    })

# Service Worker actualizado para interceptar eventos push nativos
@app.route('/sw.js')
def service_worker():
    sw_code = """
    self.addEventListener('install', (e) => {
        self.skipWaiting();
    });
    self.addEventListener('activate', (e) => {
        e.waitUntil(clients.claim());
    });
    
    // Escucha eventos push del sistema cuando la app está cerrada
    self.addEventListener('push', function(event) {
        let data = { title: "Cadena de Favores", body: "Tienes una nueva actualización." };
        if (event.data) {
            try {
                data = event.data.json();
            } catch (e) {
                data.body = event.data.text();
            }
        }
        const options = {
            body: data.body,
            icon: 'https://cdn-icons-png.flaticon.com/512/3076/3076129.png',
            vibrate: [200, 100, 200]
        };
        event.waitUntil(
            self.registration.showNotification(data.title, options)
        );
    });

    self.addEventListener('notificationclick', function(event) {
        event.notification.close();
        event.waitUntil(
            clients.openWindow('/mis-solicitudes')
        );
    });

    self.addEventListener('fetch', (e) => {
        e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    });
    """
    return sw_code, 200, {'Content-Type': 'application/javascript'}

with app.app_context():
    db.create_all()

if __name__ == '_main_':
    app.run(debug=True)
@app.route('/api/ver-suscripciones')
def ver_suscripciones():
    try:
        total = PushSubscription.query.count()
        return f"Total de celulares suscritos en la base de datos: {total}"
    except Exception as e:
        return f"Error al consultar la base de datos: {e}"
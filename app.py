from flask import Flask, render_template_string, request, redirect, url_for, session,flash,jsonify,send_file
from flask_sqlalchemy import SQLAlchemy 
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError
import qrcode
import io
import os

app = Flask(__name__)
app.secret_key = "clave_secreta_para_sesiones_estudiantiles"
import os

database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///cadena_v3.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
from sqlalchemy import text

with app.app_context():
    db.create_all()
    try:
        db.session.execute(text('ALTER TABLE usuario ADD COLUMN carnet VARCHAR(7);'))
        db.session.commit()
    except Exception:
        db.session.rollback()
    try:
        db.session.execute(text('ALTER TABLE publicacion ADD COLUMN fecha_creacion TIMESTAMP;'))
        db.session.commit()
    except Exception:
        db.session.rollback()
# -------------------------------------------------------------------
# MODELOS DE BASE DE DATOS
# -------------------------------------------------------------------
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    correo = db.Column(db.String(100), unique=True, nullable=False)
    institucion = db.Column(db.String(100), nullable=False)
    contacto = db.Column(db.String(100), nullable=False)  # Teléfono / Telegram / Alias
    carnet = db.Column(db.String(7), unique=True, nullable=False) # línea para el carnet de 7 dígitos
# ----------------------------------------------------

class Publicacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False)  # 'necesidad' o 'apoyo'
    titulo = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    materia_area = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(20), default ='activa')# 'activa', 'en_proceso', 'completada' 
    fecha_creacion = db.Column(db.DateTime, default=datetime.now)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    usuario = db.relationship('Usuario', backref='publicaciones')
class SolicitudContacto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    publicacion_id = db.Column(db.Integer, db.ForeignKey('publicacion.id'), nullable=False)
    solicitante_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    estado = db.Column(db.String(20), default='pendiente')  # 'pendiente', 'aceptado', 'rechazado'

    publicacion = db.relationship('Publicacion', backref='solicitudes')
    solicitante = db.relationship('Usuario', backref='solicitudes_hechas')
    with app.app_context():
        db.create_all()
# -------------------------------------------------------------------
# PLANTILLAS HTML EMBEBIDAS (Para ejecutar todo en un solo archivo)
# -------------------------------------------------------------------
BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cadena de Favores Estudiantiles</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Enlace al Manifest y Service Worker -->
        <link rel="manifest" href="/manifest.json">
        <meta name="theme-color" content="#4f46e5">
        <script>
          if ('serviceWorker' in navigator) {
            window.addEventListener('load', function() {
              navigator.serviceWorker.register('/sw.js');
            });
          }
        </script>
</head>
<body class="bg-slate-900 min-h-screen text-gray-800 relative font-sans">

    <!-- Fondo dinámico con brillo sutil -->
    <div class="fixed inset-0 bg-gradient-to-br from-slate-900 via-indigo-950 to-purple-950 -z-10"></div>
    <div class="fixed top-0 left-1/4 w-96 h-96 bg-indigo-600/10 rounded-full blur-3xl pointer-events-none -z-10"></div>

    <!-- Barra de Navegación -->
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
                    <!-- Botón de Perfil / Cerrar Sesión -->
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

    <!-- Banner Motivacional Superior (Integrado sin tapar el muro) -->
    <div class="max-w-6xl mx-auto px-6 pt-6">
        <div class="bg-gradient-to-r from-indigo-900/60 via-purple-900/60 to-slate-900/60 border border-indigo-500/30 backdrop-blur-md rounded-2xl p-4 text-white shadow-lg flex flex-col md:flex-row items-center justify-between gap-4">
            <div class="flex items-center gap-3">
                <span class="text-3xl">💡</span>
                <div>
                    <h3 class="font-bold text-indigo-200 text-sm md:text-base">¡El conocimiento compartido se multiplica!</h3>
                    <p class="text-xs text-gray-300">Un pequeño apoyo hoy en el muro puede ser el impulso profesional que tu compañero necesita.</p>
                </div>
            </div>
            <div class="hidden sm:flex items-center gap-2 bg-white/10 px-3 py-1.5 rounded-xl border border-white/10 text-xs text-indigo-200 whitespace-nowrap">
                <span>🌟</span> Comunidad Colaborativa
            </div>
        </div>
    </div>

    <!-- Contenido Principal -->
    <main class="max-w-6xl mx-auto p-6 relative">

    <!-- Enlace para Android y navegadores PWA -->
<link rel="manifest" href="/manifest.json">

<!-- Soporte para iPhone (iOS) -->
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Favores">
<link rel="apple-touch-icon" href="https://cdn-icons-png.flaticon.com/512/3516/3516134.png">

<!-- Registro del Service Worker -->
<script>
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js')
        .then((reg) => console.log('Service Worker listo:', reg.scope))
        .catch((err) => console.log('Error en Service Worker:', err));
    });
  }
</script>
    """
REGISTRO_TEMPLATE = BASE_TEMPLATE + """
<div class="max-w-md mx-auto my-8 bg-white p-8 rounded-2xl shadow-xl border border-gray-100 transform transition-all hover:shadow-2xl">
    <!-- Encabezado con Icono y Mensaje Inspiracional -->
    <div class="text-center mb-6">
        <div class="w-16 h-16 bg-gradient-to-tr from-indigo-500 to-purple-600 text-white rounded-full flex items-center justify-center mx-auto mb-3 shadow-lg transform hover:scale-105 transition-all">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
            </svg>
        </div>
        <h2 class="text-3xl font-extrabold text-gray-800 tracking-tight">Acceso Estudiantil</h2>
        
        <!-- Banner Motivacional Principal -->
        <div class="mt-3 p-3 bg-indigo-50 border border-indigo-100 rounded-xl text-left flex items-start gap-3">
            <span class="text-xl">🤝</span>
            <p class="text-xs text-indigo-900 leading-relaxed font-medium">
                <strong class="block text-indigo-700 font-bold mb-0.5">¡Tu conocimiento puede transformar a alguien más!</strong>
                Únete a la red de colaboración. Hoy compartes una duda o un talento, mañana impulsas el éxito de un compañero.
            </p>
        </div>
    </div>

    <!-- Formulario estilizado con llamadas de apoyo -->
    <form method="POST" action="{{ url_for('registro') }}" class="space-y-4">
        <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-gray-600 mb-1">Nombre completo</label>
            <input type="text" name="nombre" required placeholder="Ej. gabriela sofia" 
                class="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:bg-white focus:outline-none transition-all">
        </div>

        <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-gray-600 mb-1">Correo institucional</label>
            <input type="email" name="correo" required placeholder="estudiante@universidad.edu" 
                class="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:bg-white focus:outline-none transition-all">
        </div>

        <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-gray-600 mb-1">Institución / Facultad</label>
            <input type="text" name="institucion" required placeholder="Ej. Facultad de Ingeniería" 
                class="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:bg-white focus:outline-none transition-all">
        </div>

        <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-gray-600 mb-1">Contacto / Teléfono</label>
            <input type="text" name="contacto" required placeholder="+502 5555-5555" 
                class="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:bg-white focus:outline-none transition-all">
        </div>
<div class="mb-4">
    <label class="block text-sm font-medium text-gray-700">Número de Carnet </label>
    <input type="text" name="carnet" required 
           maxlength="9" 
           minlength="1" 
           pattern="[0-9]{7}" 
           title="El carnet es erroneo"
           class="w-full border p-2 rounded mt-1" 
           placeholder="Ej. 202312374">
</div>
        <!-- Botón con Llamado a la Acción (CTA) Motivacional -->
        <button type="submit" 
            class="w-full mt-2 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-white py-3 px-4 rounded-xl font-bold shadow-md hover:shadow-lg transition-all duration-200 flex items-center justify-center gap-2">
            <span>Iniciar Cadena de Favores</span>
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
        </button>
    </form>
    </main></body></html>.

    <!-- Pie del formulario c """ 

MURO_TEMPLATE = BASE_TEMPLATE + """
<div class="flex justify-between items-center mb-6">
    <h2 class="text-2xl font-bold text-white">Muro de Necesidades y Apoyos</h2>
    <a href="{{ url_for('nueva_publicacion') }}" class="bg-green-600 text-white px-4 py-2 rounded shadow hover:bg-green-700">+ Publicar</a>
</div>

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
                <form action="{{ url_for('solicitar_contacto', pub_id=pub.id) }}" method="POST">
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

<!-- HTML de tu botón corregido -->
<a href="/mis-solicitudes" class="relative inline-flex items-center px-4 py-2 bg-indigo-600 text-white rounded-lg shadow hover:bg-indigo-700 transition">
    Mis Solicitudes
    
    <!-- Badge numérico con clases completas -->
    <span id="badge-contador" class="hidden absolute -top-2 -right-2 bg-red-600 text-white text-xs font-bold px-2 py-0.5 rounded-full shadow">
        0
    </span>
</a>

<!-- Elemento de audio con un tono claro y corto -->
<audio id="tono-notificacion" src="https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3" preload="auto"></audio>

<script>
// Variable para recordar la cantidad anterior
let cantidadAnterior = 0;
let primerCarga = true;

function actualizarContadorNotificaciones() {
    fetch('/api/verificar-nuevas-solicitudes')
        .then(response => response.json())
        .then(data => {
            const badge = document.getElementById('badge-contador');
            const tono = document.getElementById('tono-notificacion');
            const cantidadNueva = data.cantidad || 0;

            if (badge) {
                if (cantidadNueva > 0) {
                    badge.textContent = cantidadNueva;
                    badge.classList.remove('hidden');
                } else {
                    badge.classList.add('hidden');
                }
            }

            // Si llegaron NUEVAS solicitudes (la cantidad aumentó)
            if (cantidadNueva > cantidadAnterior && !primerCarga) {
                if (tono) {
                    tono.play().catch(error => {
                        // Los navegadores bloquean el sonido si el usuario no ha interactuado aún con la página
                        console.log("El navegador bloqueó la reproducción automática del audio:", error);
                    });
                }
            }

            // Actualizamos el estado
            cantidadAnterior = cantidadNueva;
            primerCarga = false;
        })
        .catch(error => console.error('Error al obtener notificaciones:', error));
}

// Consultar cada 10 segundos
setInterval(actualizarContadorNotificaciones, 10000);

// Consultar al cargar la página
document.addEventListener('DOMContentLoaded', actualizarContadorNotificaciones);
</script>

<!-- Botón de Instalación Personalizado -->
<button id="btn-instalar" class="hidden items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-xl font-medium shadow-lg transition-all">
    📱 Instalar Aplicación
</button>

<script>
let deferredPrompt;
const btnInstalar = document.getElementById('btn-instalar');

window.addEventListener('beforeinstallprompt', (e) => {
    // Previene que Chrome muestre el banner automático predeterminado
    e.preventDefault();
    deferredPrompt = e;
    // Muestra tu botón personalizado
    if (btnInstalar) {
        btnInstalar.classList.remove('hidden');
        btnInstalar.classList.add('flex');
    }
});

if (btnInstalar) {
    btnInstalar.addEventListener('click', async () => {
        if (deferredPrompt) {
            deferredPrompt.prompt();
            const { outcome } = await deferredPrompt.userChoice;
            if (outcome === 'accepted') {
                console.log('Usuario aceptó instalar la PWA');
            }
            deferredPrompt = null;
            btnInstalar.classList.add('hidden');
        }
    });
}
<!-- Modal de Compromiso Personal -->
<div id="modalCompromiso" class="fixed inset-0 bg-slate-900/95 backdrop-blur-md z-50 flex items-center justify-center p-4 cursor-pointer select-none">
    <div class="bg-slate-800 border border-slate-700 max-w-lg w-full rounded-2xl p-6 sm:p-8 shadow-2xl text-center transform transition-all duration-300 scale-100">
        
        <!-- Encabezado Motivacional -->
        <div class="text-4xl mb-3">🤝</div>
        <h2 class="text-2xl font-extrabold text-indigo-300 mb-4">
            Mi compromiso es conmigo.
        </h2>

        <!-- Cuerpo del Mensaje -->
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
            <input type="checkbox" id="chkCompromiso" class="w-5 h-5 accent-indigo-500 rounded cursor-pointer" checked onclick="event.stopPropagation();">
            <label for="chkCompromiso" class="text-xs sm:text-sm text-slate-200 font-medium cursor-pointer">
                Asumo este compromiso personal de pagar el favor hacia adelante.
            </label>
        </div>

        <!-- Instrucción de Avance -->
        <p class="text-xs text-indigo-400 font-semibold animate-pulse mt-2">
            ✨ Haz clic en cualquier parte de la pantalla para avanzar al muro
        </p>
    </div>
</div>

<script>
  document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('modalCompromiso');
    if (!modal) return;
    
    // Si ya vio el compromiso en esta sesión, se oculta inmediatamente
    if (sessionStorage.getItem('compromisoMostrado') === 'true') {
      modal.style.display = 'none';
    } else {
      // Al hacer clic en cualquier parte de la pantalla, avanza al muro
      modal.addEventListener('click', function() {
        modal.classList.add('opacity-0', 'transition-opacity', 'duration-300');
        setTimeout(function() {
          modal.style.display = 'none';
        }, 300);
        sessionStorage.setItem('compromisoMostrado', 'true');
      });
    }
  });
</script>
"""
NUEVA_PUB_TEMPLATE = BASE_TEMPLATE + """
<div class="max-w-lg mx-auto bg-white p-6 rounded-lg shadow">
    <h2 class="text-xl font-bold text-white mb-4">Nueva Publicación</h2>
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
            <input type="text" name="materia_area" placeholder="Ej. Cálculo I, Programación, Tutoría de Física" required class="w-full border p-2 rounded mt-1">
        </div>
        <div>
            <label class="block text-sm font-medium">Título breve:</label>
            <input type="text" name="titulo" placeholder="Ej. Ayuda con ejercicios de derivadas" required class="w-full border p-2 rounded mt-1">
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

  <!-- 1. SOLICITUDES RECIBIDAS (Para el dueño de la publicación) -->
  <div class="bg-white p-5 rounded-lg shadow">
    <h3 class="text-lg font-bold mb-3 border-b pb-2">Solicitudes Recibidas (Gente que quiere conectar contigo)</h3>
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
              <!-- El dueño VALIDA que recibió el apoyo y cierra la publicación -->
              <form action="/validar-apoyo/{{ sol.id }}" method="POST">
                <button type="submit" class="text-xs bg-blue-600 text-white px-3 py-1.5 rounded font-bold hover:bg-blue-700">
                  Validar Apoyo Recibido
                </button>
              </form>
            {% elif sol.estado == 'aceptado' %}
              <span class="text-xs bg-yellow-100 text-yellow-800 px-2 py-1 rounded">Esperando que el solicitante marque apoyo</span>
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

  <!-- 2. SOLICITUDES ENVIADAS (Para quien solicitó la ayuda) -->
  <div class="bg-white p-5 rounded-lg shadow">
    <h3 class="text-lg font-bold mb-3 border-b pb-2">Solicitudes Enviadas por ti</h3>
    {% if enviadas %}
      {% for sol in enviadas %}
        <div class="p-3 border-b last:border-0">
          <p class="font-medium text-sm">Publicación: <strong>{{ sol.publicacion.titulo }}</strong></p>
          <p class="text-xs text-gray-500 mt-1">Estado: <span class="font-bold">{{ sol.estado }}</span></p>

          {% if sol.estado == 'aceptado' %}
            <!-- Se REVELAN los datos de contacto únicamente cuando el dueño autorizó -->
            <div class="mt-2 p-3 bg-green-50 rounded border border-green-200">
              <p class="text-xs text-green-800 font-bold mb-1">✅ ¡Contacto Autorizado!</p>
              <p class="text-xs text-gray-700"><strong>Nombre:</strong> {{ sol.publicacion.usuario.nombre }}</p>
              <p class="text-xs text-gray-700"><strong>Contacto:</strong> {{ sol.publicacion.usuario.contacto }}</p>
              
              <form action="/marcar-brindado/{{ sol.id }}" method="POST" class="mt-2">
                <button type="submit" class="text-xs bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700">
                  Marcar como Apoyo Brindado
                </button>
              </form>
            </div>
          {% endif %}
        </div>
      {% endfor %}
    {% else %}
      <p class="text-sm text-gray-500">No has enviado ninguna solicitud aún.</p>
    {% endif %}
  </div>

</div>
<script>
async function chequearNuevasSolicitudes() {
    try {
        const respuesta = await fetch('/api/verificar-nuevas-solicitudes');
        if (!respuesta.ok) return;

        const data = await respuesta.json();
        const badge = document.getElementById('badge-notif');

        if (data.tiene_nuevas) {
            // Muestra el punto rojo si hay solicitudes nuevas
            badge.classList.remove('d-none');
        } else {
            // Oculta el punto rojo si no hay nada pendiente
            badge.classList.add('d-none');
        }
    } catch (error) {
        console.error('Error al verificar solicitudes:', error);
    }
}

// ⏱️ Revisa automáticamente cada 6 segundos en segundo plano
setInterval(chequearNuevasSolicitudes, 6000);

// Ejecutar una vez al cargar la página
chequearNuevasSolicitudes();
</script>
</body>
</html>
"""

QR_TEMPLATE = BASE_TEMPLATE + """
<div class="text-center bg-white p-8 rounded-lg shadow max-w-md mx-auto">
    <h2 class="text-xl font-bold mb-2">Escanea este Código QR</h2>
    <p class="text-sm text-gray-600 mb-4">Los estudiantes pueden usar la cámara de su teléfono para ingresar a la plataforma.</p>
    <img src="{{ url_for('imagen_qr') }}" alt="Código QR" class="mx-auto border p-2 rounded">
    <p class="text-xs text-gray-400 mt-4">Enlace directo de prueba: <a href="{{ url_for('registro') }}" class="text-indigo-600 underline">Ingresar como estudiante</a></p>
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
    # Si el usuario accede mediante el envío del formulario (POST)
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        correo = request.form.get('correo', '').strip()
        institucion = request.form.get('institucion', '').strip()
        contacto = request.form.get('contacto', '').strip()
        carnet = request.form.get('carnet', '').strip()

        # Validación estricta: debe ser exactamente de 7 dígitos numéricos
        if not carnet.isdigit() or len(carnet) != 7:
            flash(
                'El número de carnet debe contener exactamente 7 dígitos numéricos.',
                'error',
            )
            return redirect(url_for('inicio'))

        # Verificar si el carnet ya está registrado
    carnet_existente = Usuario.query.filter_by(carnet=carnet).first()
    
    if carnet_existente:
        # Validación de seguridad: Comparamos si el correo ingresado coincide con el del dueño del carnet
        if carnet_existente.correo.strip().lower() != correo.strip().lower():
            flash('Este número de carnet ya pertenece a otro usuario y los datos no coinciden.', 'error')
            return redirect(url_for('inicio')) # O la ruta donde manejas el formulario
        
        # Si el carnet y el correo coinciden, es el dueño legítimo ingresando de nuevo
        session['usuario_id'] = carnet_existente.id
        session['usuario_nombre'] = carnet_existente.nombre
        return redirect(url_for('muro'))

        # Si es un usuario completamente nuevo, lo creamos y guardamos
        nuevo_usuario = Usuario(
            nombre=nombre,
            correo=correo,
            institucion=institucion,
            contacto=contacto,
            carnet=carnet
        )
        db.session.add(nuevo_usuario)
        db.session.commit()

        session['usuario_id'] = nuevo_usuario.id
        return redirect(url_for('muro'))

    # Si se intenta entrar por GET
    return redirect(url_for('inicio'))
   
@app.route('/muro')
def muro():
    if 'usuario_id' not in session:
        return redirect(url_for('registro'))
    
    # 1. Eliminar publicaciones de más de 3 días que no han sido completadas
    limite_tiempo = datetime.now() - timedelta(days=3)
    try:
        vencidas = Publicacion.query.filter(
            Publicacion.fecha_creacion < limite_tiempo,
            Publicacion.estado != 'completada'
        ).all()
        
        for pub in vencidas:
            db.session.delete(pub)
            
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print("Error al eliminar publicaciones vencidas:", e)

    # 2. Consultar las publicaciones activas
    publicaciones = Publicacion.query.filter(Publicacion.estado != 'completada').order_by(Publicacion.fecha_creacion.desc()).all()
    
    return render_template_string(MURO_TEMPLATE, publicaciones=publicaciones, usuario_id=session['usuario_id'])
    
@app.route('/nueva-publicacion', methods=['GET', 'POST'])
def nueva_publicacion():
    if 'usuario_id' not in session:
        return redirect(url_for('registro'))
    if request.method == 'POST':
        tipo = request.form['tipo']
        materia_area = request.form['materia_area']
        titulo = request.form['titulo']
        descripcion = request.form['descripcion']

        pub = Publicacion(
            tipo=tipo,
            materia_area=materia_area,
            titulo=titulo,
            descripcion=descripcion,
            usuario_id=session['usuario_id']
        )
        db.session.add(pub)
        db.session.commit()
        return redirect(url_for('muro'))

    return render_template_string(NUEVA_PUB_TEMPLATE)

# --- 1. RUTA PARA SOLICITAR CONTACTO ---
@app.route('/solicitar-contacto/<int:pub_id>', methods=['POST'])
def solicitar_contacto(pub_id):
    if 'usuario_id' not in session:
        return redirect(url_for('registro'))
        
    usuario_actual_id = session['usuario_id']
    publicacion = Publicacion.query.get_or_404(pub_id)
    
    # Evitar que el dueño de la publicación se solicite contacto a sí mismo
    if publicacion.usuario_id != usuario_actual_id:
        existe = SolicitudContacto.query.filter_by(
            publicacion_id=pub_id, 
            solicitante_id=usuario_actual_id
        ).first()
        
        if not existe:
            nueva_solicitud = SolicitudContacto(
                publicacion_id=pub_id,
                solicitante_id=usuario_actual_id,
                estado='pendiente'
            )
            db.session.add(nueva_solicitud)
            db.session.commit()
    return redirect(url_for('mis_solicitudes'))

@app.route('/api/verificar-nuevas-solicitudes')
def verificar_nuevas_solicitudes():
    if 'usuario_id' not in session:
        return {'cantidad': 0}
    
    usuario_actual_id = session['usuario_id']
    
    # Cuenta cuántas solicitudes pendientes tienen las publicaciones de este usuario
    # (Ajusta esta consulta según cómo tengas relacionadas tus tablas en SQLAlchemy)
    cantidad = SolicitudContacto.query.join(Publicacion).filter(
        Publicacion.usuario_id == usuario_actual_id,
        SolicitudContacto.estado == 'pendiente'
    ).count()
    
    return {'cantidad': cantidad}

# --- 2. RUTA PARA QUE EL DUEÑO AUTORICE Y COMPARTA SUS DATOS ---
@app.route('/aceptar-solicitud/<int:sol_id>', methods=['POST'])
def aceptar_solicitud(sol_id):
  if 'usuario_id' not in session:
    return redirect(url_for('inicio'))

  solicitud = SolicitudContacto.query.get_or_404(sol_id)

  # Verificar que el usuario actual sea el dueño de la publicación
  if solicitud.publicacion.usuario_id != session['usuario_id']:
    flash('No tienes permiso para aceptar esta solicitud.', 'error')
    return redirect(url_for('mis_solicitudes'))

  # Cambiar el estado a aceptado para habilitar la vista de contactos
  solicitud.estado = 'aceptado'
  db.session.commit()

  flash('¡Solicitud aceptada! Ahora ambos pueden ver sus datos de contacto.', 'success')
  return redirect(url_for('mis_solicitudes'))


# --- 3. RUTA PARA QUE EL SOLICITANTE MARQUE COMO BRINDADO ---
@app.route('/marcar-brindado/<int:sol_id>', methods=['POST'])
def marcar_brindado(sol_id):
    if 'usuario_id' not in session:
        return redirect(url_for('registro'))
        
    solicitud = SolicitudContacto.query.get_or_404(sol_id)
    
    # Solo el solicitante puede marcar que el favor ya le fue brindado
    if solicitud.solicitante_id == session['usuario_id']:
        solicitud.estado = 'brindado'
        db.session.commit()
        
    return redirect(url_for('mis_solicitudes'))


# --- 4. RUTA PARA QUE EL DUEÑO VALIDE EL APOYO Y CIERRE LA PUBLICACIÓN ---
@app.route('/validar-apoyo/<int:sol_id>', methods=['POST'])
def validar_apoyo(sol_id):
    if 'usuario_id' not in session:
        return redirect(url_for('registro'))
        
    solicitud = SolicitudContacto.query.get_or_404(sol_id)
    
    # Solo el dueño valida el apoyo recibido y finaliza la publicación
    if solicitud.publicacion.usuario_id == session['usuario_id']:
        solicitud.estado = 'completado'
        solicitud.publicacion.estado = 'completada'  # Se oculta del muro principal
        db.session.commit()
        
    return redirect(url_for('mis_solicitudes'))

 # --- 5. RUTA PARA MOSTRAR LA VISTA DE MIS SOLICITUDES ---
@app.route('/mis-solicitudes')
def mis_solicitudes():
    if 'usuario_id' not in session:
        return redirect(url_for('registro'))
        
    usuario_id = session['usuario_id']
    
    # Solicitudes que me han hecho a mí
    recibidas = SolicitudContacto.query.join(Publicacion).filter(
        Publicacion.usuario_id == usuario_id,
        SolicitudContacto.estado != 'completado'
    ).all()
    
    # Solicitudes que yo he realizado a otros
    enviadas = SolicitudContacto.query.filter(
        SolicitudContacto.solicitante_id == usuario_id,
        SolicitudContacto.estado != 'completado'
    ).all()
    
    return render_template_string(
        SOLICITUDES_TEMPLATE, 
        recibidas=recibidas, 
        enviadas=enviadas
    )

@app.route('/qr')
def generar_qr():
    return render_template_string(QR_TEMPLATE)

@app.route('/imagen-qr')
def imagen_qr():
    # URL de acceso a la aplicación
    url = request.host_url + "registro"
    img = qrcode.make(url)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('registro'))
# INICIALIZACIÓN DE TABLAS (Se ejecuta en Render/WSGI)
# -----------------------------------------------------------------------------
with app.app_context():
    db.create_all()
from flask import jsonify

@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "Cadena de Favores Estudiantiles",
        "short_name": "Cadena de Favores",
        "start_url": "/muro",
        "display": "standalone",
        "background_color": "#0f172a",
        "theme_color": "#4f46e5",
        "icons": [
            {
                "src": "https://cdn-icons-png.flaticon.com/512/3076/3076129.png",
                "sizes": "192x192",
                "type": "image/png"
            },
            {
                "src": "https://cdn-icons-png.flaticon.com/512/3076/3076129.png",
                "sizes": "512x512",
                "type": "image/png"
            }
        ]
    })

@app.route('/sw.js')
def service_worker():
    sw_code = """
    self.addEventListener('install', (e) => {
        self.skipWaiting();
    });
    self.addEventListener('activate', (e) => {
        e.waitUntil(clients.claim());
    });
    self.addEventListener('fetch', (e) => {
        e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    });
    """
    return sw_code, 200, {'Content-Type': 'application/javascript'}
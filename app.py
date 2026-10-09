from flask import Flask, render_template_string, request, redirect, url_for, session, send_file
from flask_sqlalchemy import SQLAlchemy
import qrcode
import io
import os

app = Flask(__name__)
app.secret_key = "clave_secreta_para_sesiones_estudiantiles"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cadena_v3.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
# -------------------------------------------------------------------
# MODELOS DE BASE DE DATOS
# -------------------------------------------------------------------
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    correo = db.Column(db.String(100), unique=True, nullable=False)
    institucion = db.Column(db.String(100), nullable=False)
    contacto = db.Column(db.String(100), nullable=False)  # Teléfono / Telegram / Alias
# ----------------------------------------------------

class Publicacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False)  # 'necesidad' o 'apoyo'
    titulo = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    materia_area = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(20), default ='activa')# 'activa', 'en_proceso', 'completada' 
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
            <input type="text" name="nombre" required placeholder="Ej. Ana García" 
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

        <!-- Botón con Llamado a la Acción (CTA) Motivacional -->
        <button type="submit" 
            class="w-full mt-2 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-white py-3 px-4 rounded-xl font-bold shadow-md hover:shadow-lg transition-all duration-200 flex items-center justify-center gap-2">
            <span>Iniciar Cadena de Favores</span>
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
        </button>
    </form>

    <!-- Pie del formulario c """ 

MURO_TEMPLATE = BASE_TEMPLATE + """
<div class="flex justify-between items-center mb-6">
    <h2 class="text-2xl font-bold">Muro de Necesidades y Apoyos</h2>
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
"""

NUEVA_PUB_TEMPLATE = BASE_TEMPLATE + """
<div class="max-w-lg mx-auto bg-white p-6 rounded-lg shadow">
    <h2 class="text-xl font-bold mb-4">Nueva Publicación</h2>
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
<h2 class="text-2xl font-bold mb-6">Centro de Comunicación Confidencial</h2>

<div class="space-y-6">
    <!-- Solicitudes Recibidas -->
    <div class="bg-white p-5 rounded-lg shadow">
        <h3 class="text-lg font-bold mb-3 border-b pb-2">Solicitudes Recibidas (Gente que quiere conectar contigo)</h3>
        {% if recibidas %}
            {% for sol in recibidas %}
            <div class="flex justify-between items-center p-3 border-b last:border-0">
                <div>
                    <p class="font-medium text-sm">Alguien quiere ayudarte o recibir tu ayuda en: <strong>{{ sol.publicacion.titulo }}</strong></p>
                    {% if sol.estado == 'aceptado' %}
                        <p class="text-xs text-green-700 bg-green-50 p-2 rounded mt-2">
                            ✅ <strong>Contacto de {{ sol.solicitante.nombre }}:</strong> {{ sol.solicitante.contacto }} (Correo: {{ sol.solicitante.correo }})
                        </p>
                    {% endif %}
                </div>
                <div>
                    {% if sol.estado == 'pendiente' %}
                        <a href="{{ url_for('responder_solicitud', sol_id=sol.id, accion='aceptar') }}" class="bg-green-600 text-white px-3 py-1 rounded text-xs mr-2">Aceptar y Compartir Datos</a>
                        <a href="{{ url_for('responder_solicitud', sol_id=sol.id, accion='rechazar') }}" class="bg-gray-400 text-white px-3 py-1 rounded text-xs">Rechazar</a>
                   {% elif sol.estado == 'aceptado' %}
        <form action="{{ url_for('marcar_brindado', sol_id=sol.id) }}" method="POST" class="inline">
            <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold py-1 px-3 rounded shadow">
                Marcar Apoyo Brindado
            </button>
        </form>

    {% elif sol.estado == 'brindado' %}
        {% if session['usuario_id'] == sol.publicacion.usuario_id %}
            <form action="{{ url_for('validar_apoyo', sol_id=sol.id) }}" method="POST" class="inline">
                <button type="submit" class="bg-green-600 hover:bg-green-700 text-white text-xs font-bold py-1 px-3 rounded shadow">
                    ✓ Validar Apoyo Recibido
                </button>
            </form>
        {% else %}
            <span class="text-xs font-bold text-blue-500 bg-blue-50 px-2 py-1 rounded border border-blue-200">
                ⏳ Esperando confirmación
            </span>
        {% endif %}

    {% elif sol.estado == 'completado' %}
        <span class="text-xs font-bold text-green-600 bg-green-50 px-2 py-1 rounded border border-green-200">
            ✓ Favor Completado y Validado
        </span>
        {% else %}
   <span class="text-xs font-bold uppercase text-gray-500">{{ sol.estado }}</span>
{% endif %}
    </div>

    <!-- Solicitudes Enviadas -->
    <div class="bg-white p-5 rounded-lg shadow">
        <h3 class="text-lg font-bold mb-3 border-b pb-2">Solicitudes Enviadas por ti</h3>
        {% if enviadas %}
            {% for sol in enviadas %}
            <div class="p-3 border-b last:border-0">
                <p class="font-medium text-sm">Publicación: <strong>{{ sol.publicacion.titulo }}</strong></p>
                <p class="text-xs text-gray-500 mt-1">Estado: <span class="font-bold">{{ sol.estado }}</span></p>
                {% if sol.estado == 'aceptado' %}
                    <p class="text-xs text-green-700 bg-green-50 p-2 rounded mt-2">
                        ✅ <strong>Contacto del dueño de la publicación ({{ sol.publicacion.usuario.nombre }}):</strong> {{ sol.publicacion.usuario.contacto }}
                    </p>
                {% endif %}
            </div>
            {% endfor %}
        {% else %}
            <p class="text-sm text-gray-500">No has enviado ninguna solicitud aún.</p>
        {% endif %}
    </div>
</div>
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
    if request.method == 'POST':
        nombre = request.form['nombre']
        correo = request.form['correo']
        institucion = request.form['institucion']
        contacto = request.form['contacto']

        usuario = Usuario.query.filter_by(correo=correo).first()
        if not usuario:
            usuario = Usuario(nombre=nombre, correo=correo, institucion=institucion, contacto=contacto)
            db.session.add(usuario)
            db.session.commit()

        session['usuario_id'] = usuario.id
        session['usuario_nombre'] = usuario.nombre
        return redirect(url_for('muro'))

    return render_template_string(REGISTRO_TEMPLATE)

@app.route('/muro')
def muro():
    if 'usuario_id' not in session:
        return redirect(url_for('registro'))
    publicaciones = Publicacion.query.order_by(Publicacion.id.desc()).all()
    return render_template_string(MURO_TEMPLATE, publicaciones=publicaciones)

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

@app.route('/solicitar-contacto/<int:pub_id>', methods=['POST'])
def solicitar_contacto(pub_id):
    db.create_all()
    if 'usuario_id' not in session:
        return redirect(url_for('registro'))
    
    existe = SolicitudContacto.query.filter_by(publicacion_id=pub_id, solicitante_id=session['usuario_id']).first()
    if not existe:
        solicitud = SolicitudContacto(publicacion_id=pub_id, solicitante_id=session['usuario_id'])
        db.session.add(solicitud)
        db.session.commit()
    return redirect(url_for('mis_solicitudes'))

@app.route('/marcar-brindado/<int:sol_id>', methods=['POST'])
def marcar_brindado(sol_id):
    solicitud = SolicitudContacto.query.get_or_404(sol_id)
    if 'usuario_id' in session:
        solicitud.estado = 'brindado'
        db.session.commit()
    return redirect(url_for('mis_solicitudes'))

@app.route('/validar-apoyo/<int:sol_id>', methods=['POST'])
def validar_apoyo(sol_id):
    solicitud = SolicitudContacto.query.get_or_404(sol_id)
    if 'usuario_id' in session:
        solicitud.estado = 'completado'
        solicitud.publicacion.estado = 'completada'
        db.session.commit()
    return redirect(url_for('mis_solicitudes'))
@app.route('/mis-solicitudes')
def mis_solicitudes():
    if 'usuario_id' not in session:
        return redirect(url_for('registro'))
    
    usuario_id = session['usuario_id']
    
    # Solicitudes sobre mis publicaciones
    recibidas = SolicitudContacto.query.join(Publicacion).filter(Publicacion.usuario_id == usuario_id).all()
    # Solicitudes que yo envié
    enviadas = SolicitudContacto.query.filter_by(solicitante_id=usuario_id).all()

    return render_template_string(SOLICITUDES_TEMPLATE, recibidas=recibidas, enviadas=enviadas)

@app.route('/responder-solicitud/<int:sol_id>/<accion>')
def responder_solicitud(sol_id, accion):
    if 'usuario_id' not in session:
        return redirect(url_for('registro'))
    
    sol = SolicitudContacto.query.get_or_404(sol_id)
    if sol.publicacion.usuario_id == session['usuario_id']:
        if accion == 'aceptar':
            sol.estado = 'aceptado'
        elif accion == 'rechazar':
            sol.estado = 'rechazado'
        db.session.commit()
    return redirect(url_for('mis_solicitudes'))

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

# -------------------------------------------------------------------
# INICIALIZACIÓN
# -------------------------------------------------------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
import os
import logging
import sqlite3
import requests
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# --- 1. CONFIGURACIÓN Y VARIABLES DE ENTORNO ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_URL = os.getenv("DB_URL") 

# Configuración de Archivos
NOMBRE_DB_LOCAL = "datos_seguros.db"
NOMBRE_TABLA = "maestra"      

# --- ⚠️ CONFIGURACIÓN DE COLUMNAS (¡EDITA ESTO!) ---
# Pon aquí el nombre EXACTO del encabezado en tu Excel para cada tipo de búsqueda
COL_ID_PRINCIPAL = "id"       # Para la búsqueda directa por número
COL_APELLIDO     = "APELLIDO" # Columna donde buscar apellidos
COL_NOMBRE       = "NOMBRE"   # Columna donde buscar nombres
COL_DOMICILIO    = "DIRECCION" # Columna donde buscar domicilios

# --- SERVIDOR WEB (KEEP-ALIVE) ---
app = Flask('')

@app.route('/')
def home():
    return "🤖 Bot activo y escuchando."

def run():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- 2. GESTIÓN DE BASE DE DATOS ---
def descargar_db():
    if not DB_URL:
        logging.error("❌ ERROR: No encontré la variable DB_URL.")
        return False
    logging.info("⏳ Descargando base de datos...")
    try:
        r = requests.get(DB_URL, allow_redirects=True)
        if r.status_code == 200:
            with open(NOMBRE_DB_LOCAL, 'wb') as f:
                f.write(r.content)
            logging.info("✅ Base de datos descargada.")
            return True
        else:
            logging.error(f"❌ Error descarga: {r.status_code}")
            return False
    except Exception as e:
        logging.error(f"❌ Excepción: {e}")
        return False

def ejecutar_busqueda(columna, valor):
    """
    Busca coincidencias parciales (LIKE %valor%) y devuelve hasta 5 resultados.
    """
    if not os.path.exists(NOMBRE_DB_LOCAL):
        return "⚠️ La base de datos se está descargando, intenta en unos segundos."

    try:
        conn = sqlite3.connect(NOMBRE_DB_LOCAL)
        cursor = conn.cursor()
        
        # SQL: LIKE %valor% permite encontrar texto en cualquier parte de la celda
        # COLLATE NOCASE hace que no importen mayúsculas/minúsculas
        query = f"SELECT * FROM {NOMBRE_TABLA} WHERE {columna} LIKE ? COLLATE NOCASE LIMIT 5"
        
        cursor.execute(query, (f"%{valor}%",))
        filas = cursor.fetchall()
        
        # Nombres de columnas para el formato
        headers = [d[0] for d in cursor.description]
        conn.close()
        
        if not filas:
            return f"❌ No encontré coincidencias para: *{valor}* en la columna *{columna}*."

        # Construir respuesta con múltiples resultados
        mensaje_final = f"🔎 **Encontré {len(filas)} coincidencias:**\n"
        
        for fila in filas:
            mensaje_final += "\n➖➖➖➖➖➖➖➖➖➖\n"
            for i in range(len(headers)):
                # Filtramos columnas vacías para que no ocupe espacio visual
                dato = str(fila[i])
                if dato and dato.lower() != 'nan' and dato.lower() != 'none':
                    mensaje_final += f"🔹 *{headers[i]}:* {dato}\n"
                    
        return mensaje_final

    except Exception as e:
        return f"⚠️ Error interno de búsqueda: {e}"

# --- 3. MANEJADORES DE COMANDOS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 **¡Bot Financiero Activo!**\n\n"
        "Comandos disponibles:\n"
        "🆔 Envíame un ID/Código directo para buscar.\n"
        "👤 /apellido [texto] -> Busca por apellido\n"
        "📝 /nombre [texto] -> Busca por nombre\n"
        "🏠 /domicilio [texto] -> Busca por dirección\n"
        "🔄 /actualizar -> Recarga la base de datos"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

# Función genérica para manejar los comandos de búsqueda
async def manejar_comando_busqueda(update: Update, context: ContextTypes.DEFAULT_TYPE, columna_db):
    if not context.args:
        await update.message.reply_text("⚠️ Debes escribir algo para buscar. Ej: /apellido Perez")
        return
    
    # Unimos todo lo que escribió el usuario (ej: "De la Cruz")
    busqueda = " ".join(context.args)
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    respuesta = ejecutar_busqueda(columna_db, busqueda)
    
    # Telegram corta mensajes muy largos (4096 caracteres), enviamos con cuidado
    if len(respuesta) > 4000:
        respuesta = respuesta[:4000] + "\n\n⚠️ (Mensaje cortado por límite de longitud)..."
        
    await update.message.reply_text(respuesta, parse_mode='Markdown')

# Wrappers para cada comando específico
async def cmd_apellido(update, context):
    await manejar_comando_busqueda(update, context, COL_APELLIDO)

async def cmd_nombre(update, context):
    await manejar_comando_busqueda(update, context, COL_NOMBRE)

async def cmd_domicilio(update, context):
    await manejar_comando_busqueda(update, context, COL_DOMICILIO)

async def buscar_general(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Si el usuario escribe texto suelto, busca por ID/Código Principal"""
    texto = update.message.text
    # Reutilizamos la lógica pero buscando coincidencia exacta o parcial en la ID
    # Aquí puedes decidir si quieres LIKE o exacto (=). Dejo LIKE para flexibilidad.
    respuesta = ejecutar_busqueda(COL_ID_PRINCIPAL, texto)
    await update.message.reply_text(respuesta, parse_mode='Markdown')

async def reload_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if descargar_db():
        await update.message.reply_text("✅ Base de datos actualizada.")
    else:
        await update.message.reply_text("❌ Error al actualizar.")

# --- 4. ARRANQUE ---
if __name__ == '__main__':
    keep_alive()

    # Intento de descarga inicial
    if not descargar_db():
        print("⚠️ Iniciando sin DB...")

    if not TOKEN:
        print("❌ ERROR: Falta TELEGRAM_TOKEN")
        exit()

    app_bot = ApplicationBuilder().token(TOKEN).build()
    
    # Registramos los comandos
    app_bot.add_handler(CommandHandler('start', start))
    app_bot.add_handler(CommandHandler('actualizar', reload_db))
    
    # Nuevos comandos de búsqueda
    app_bot.add_handler(CommandHandler('apellido', cmd_apellido))
    app_bot.add_handler(CommandHandler('nombre', cmd_nombre))
    app_bot.add_handler(CommandHandler('domicilio', cmd_domicilio))
    
    # Mensaje normal (busca por ID)
    app_bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), buscar_general))
    
    print("🤖 Bot con búsqueda avanzada corriendo...")
    app_bot.run_polling()
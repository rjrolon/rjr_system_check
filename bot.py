import os
import logging
import sqlite3
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# --- 1. CONFIGURACIÓN INICIAL ---
# Estas variables las tomará de la configuración de Render (Environment Variables)
TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_URL = os.getenv("DB_URL") 

# Configuración interna (esto sí puedes editarlo aquí si cambia)
NOMBRE_DB_LOCAL = "datos_descargados.db"
NOMBRE_TABLA = "maestra"      # Debe coincidir con lo que pusiste en el convertidor
COLUMNA_LLAVE = "CODIGO"      # La columna que usará para buscar (ej. DNI, SKU)

# Logging (para ver errores en la consola de Render)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- 2. FUNCIÓN: DESCARGAR BASE DE DATOS ---
def descargar_db():
    """Descarga la base de datos segura desde Google Drive al iniciar."""
    if not DB_URL:
        logging.error("❌ ERROR: No encontré la variable DB_URL.")
        return False
        
    logging.info("⏳ Iniciando descarga de la base de datos...")
    try:
        r = requests.get(DB_URL, allow_redirects=True)
        if r.status_code == 200:
            with open(NOMBRE_DB_LOCAL, 'wb') as f:
                f.write(r.content)
            logging.info("✅ Base de datos descargada correctamente.")
            return True
        else:
            logging.error(f"❌ Error al descargar DB. Status: {r.status_code}")
            return False
    except Exception as e:
        logging.error(f"❌ Excepción al descargar: {e}")
        return False

# --- 3. LÓGICA DE BÚSQUEDA ---
def buscar_en_sql(busqueda):
    """Busca el dato en el archivo SQLite local."""
    if not os.path.exists(NOMBRE_DB_LOCAL):
        return "⚠️ Error: La base de datos no está cargada."

    try:
        conn = sqlite3.connect(NOMBRE_DB_LOCAL)
        cursor = conn.cursor()
        
        # Consulta segura para evitar hackeos SQL
        query = f"SELECT * FROM {NOMBRE_TABLA} WHERE {COLUMNA_LLAVE} = ?"
        cursor.execute(query, (busqueda,))
        
        fila = cursor.fetchone() # Trae solo el primer resultado
        
        # Obtenemos los nombres de las columnas para que el mensaje quede bonito
        nombres_columnas = [description[0] for description in cursor.description]
        
        conn.close()
        
        if fila:
            # Armamos el mensaje de respuesta
            mensaje = "🔎 **Resultado Encontrado:**\n\n"
            for i in range(len(nombres_columnas)):
                # Formato: Negrita la columna: valor
                mensaje += f"🔹 *{nombres_columnas[i]}:* {fila[i]}\n"
            return mensaje
        else:
            return "❌ No encontré ningún registro con ese dato."

    except Exception as e:
        return f"⚠️ Error interno: {e}"

# --- 4. COMANDOS DEL BOT ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hola 👋. Envíame el código/DNI para buscar en la base de datos.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_usuario = update.message.text.strip() # Limpiamos espacios
    
    # Le avisamos al usuario que estamos buscando (útil si tarda un poco)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    
    # Buscamos y respondemos
    respuesta = buscar_en_sql(texto_usuario)
    await update.message.reply_text(respuesta, parse_mode='Markdown')

async def reload_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando secreto /actualizar para recargar la DB sin apagar el bot"""
    if descargar_db():
        await update.message.reply_text("✅ Base de datos actualizada con éxito.")
    else:
        await update.message.reply_text("❌ Falló la actualización.")

# --- 5. EJECUCIÓN PRINCIPAL ---
if __name__ == '__main__':
    # 1. Descargar DB al arrancar
    if not descargar_db():
        print("⚠️ ADVERTENCIA: Iniciando sin base de datos (se intentará descargar luego).")

    # 2. Configurar Bot
    if not TOKEN:
        print("❌ ERROR CRÍTICO: No hay TOKEN configurado.")
        exit()

    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('actualizar', reload_db)) # Comando extra
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("🤖 Bot corriendo...")
    application.run_polling()

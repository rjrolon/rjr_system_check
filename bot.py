import os
import logging
import sqlite3
import requests
import math
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters

# --- 1. CONFIGURACIÓN Y VARIABLES ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_URL = os.getenv("DB_URL") 

NOMBRE_DB_LOCAL = "datos_seguros.db"
NOMBRE_TABLA = "maestra"      

# ⚠️ CONFIGURACIÓN DE COLUMNAS (MANTÉN TUS NOMBRES AQUÍ)
COL_ID_PRINCIPAL = "id"       
COL_APELLIDO     = "APELLIDO" 
COL_NOMBRE       = "NOMBRE"   
COL_DOMICILIO    = "domicilio"

RESULTADOS_POR_PAGINA = 5  # Cantidad de filas a mostrar por vez

# --- SERVIDOR WEB (KEEP-ALIVE) ---
app = Flask('')

@app.route('/')
def home():
    return "🤖 Bot activo con paginación."

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

# --- 2. GESTIÓN BASE DE DATOS ---
def descargar_db():
    if not DB_URL:
        logging.error("❌ Falta DB_URL")
        return False
    try:
        r = requests.get(DB_URL, allow_redirects=True)
        if r.status_code == 200:
            with open(NOMBRE_DB_LOCAL, 'wb') as f:
                f.write(r.content)
            logging.info("✅ DB Descargada.")
            return True
        return False
    except Exception as e:
        logging.error(f"❌ Error descarga: {e}")
        return False

# --- 3. MOTOR DE BÚSQUEDA CON PAGINACIÓN ---
def obtener_datos_paginados(columna, valor, pagina=0):
    """
    Devuelve: (texto_resultado, tiene_mas_paginas)
    Calculando el total de páginas (Ej: 1/5).
    """
    if not os.path.exists(NOMBRE_DB_LOCAL):
        return "⚠️ La base de datos se está descargando...", False

    try:
        conn = sqlite3.connect(NOMBRE_DB_LOCAL)
        cursor = conn.cursor()
        
        # --- PASO 1: Contar cuántos resultados existen en TOTAL ---
        query_count = f"SELECT COUNT(*) FROM {NOMBRE_TABLA} WHERE {columna} LIKE ? COLLATE NOCASE"
        cursor.execute(query_count, (f"%{valor}%",))
        total_filas = cursor.fetchone()[0]
        
        if total_filas == 0:
            conn.close()
            return f"❌ No encontré coincidencias para '{valor}' en {columna}.", False

        # Calculamos cuántas páginas salen (redondeando hacia arriba)
        total_paginas = math.ceil(total_filas / RESULTADOS_POR_PAGINA)
        
        # --- PASO 2: Traer solo los datos de la página actual ---
        offset = pagina * RESULTADOS_POR_PAGINA
        
        query_data = f"""
            SELECT * FROM {NOMBRE_TABLA} 
            WHERE {columna} LIKE ? COLLATE NOCASE 
            LIMIT {RESULTADOS_POR_PAGINA} OFFSET {offset}
        """
        
        cursor.execute(query_data, (f"%{valor}%",))
        filas = cursor.fetchall()
        headers = [d[0] for d in cursor.description]
        conn.close()

        # --- PASO 3: Construir el mensaje con el contador "Pág X/Total" ---
        mensaje = f"🔎 **Resultados para '{valor}'** (Pág {pagina + 1}/{total_paginas}):\n"
        
        for fila in filas:
            mensaje += "\n➖➖➖➖➖\n"
            for i in range(len(headers)):
                dato = str(fila[i])
                if dato and dato.lower() not in ['nan', 'none', '']:
                    mensaje += f"🔹 *{headers[i]}:* {dato}\n"
        
        # Determinar si hay más páginas para activar el botón "Siguiente"
        tiene_mas = (pagina + 1) < total_paginas
        
        return mensaje, tiene_mas

    except Exception as e:
        return f"⚠️ Error interno: {e}", False

# --- 4. MANEJO DE BOTONES ---
def crear_teclado(columna, valor, pagina, tiene_mas):
    botones = []
    
    # Botón Anterior (solo si no es la página 0)
    if pagina > 0:
        botones.append(InlineKeyboardButton("⬅️ Ant.", callback_data=f"{columna}|{valor}|{pagina-1}"))
    
    # Botón Siguiente (solo si hay más resultados)
    if tiene_mas:
        botones.append(InlineKeyboardButton("Sig. ➡️", callback_data=f"{columna}|{valor}|{pagina+1}"))
    
    if not botones:
        return None
        
    return InlineKeyboardMarkup([botones])

async def responder_busqueda(update, context, columna, valor, pagina=0, es_edicion=False):
    # 1. Buscamos en SQL
    texto, tiene_mas = obtener_datos_paginados(columna, valor, pagina)
    
    # 2. Creamos los botones
    teclado = crear_teclado(columna, valor, pagina, tiene_mas)
    
    # 3. Enviamos o Editamos el mensaje
    if es_edicion:
        # Si viene de un clic en botón, editamos el mensaje existente
        try:
            await update.callback_query.edit_message_text(text=texto, parse_mode='Markdown', reply_markup=teclado)
        except Exception:
            pass # A veces da error si el mensaje es idéntico, lo ignoramos
    else:
        # Mensaje nuevo
        await update.message.reply_text(texto, parse_mode='Markdown', reply_markup=teclado)

# --- 5. HANDLERS (COMANDOS) ---

async def manejar_comando(update, context, columna_db):
    if not context.args:
        await update.message.reply_text("⚠️ Escribe algo para buscar.")
        return
    busqueda = " ".join(context.args)
    await responder_busqueda(update, context, columna_db, busqueda, pagina=0)

async def cmd_apellido(update, context): await manejar_comando(update, context, COL_APELLIDO)
async def cmd_nombre(update, context): await manejar_comando(update, context, COL_NOMBRE)
async def cmd_domicilio(update, context): await manejar_comando(update, context, COL_DOMICILIO)

async def buscar_general(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    await responder_busqueda(update, context, COL_ID_PRINCIPAL, texto, pagina=0)

async def boton_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los clics en los botones Anterior/Siguiente"""
    query = update.callback_query
    await query.answer() # Avisar a Telegram que recibimos el clic
    
    # Recuperamos los datos del botón: "COLUMNA|VALOR|PAGINA"
    datos = query.data.split('|')
    columna = datos[0]
    valor = datos[1]
    pagina = int(datos[2])
    
    await responder_busqueda(update, context, columna, valor, pagina, es_edicion=True)

async def start(update, context):
    await update.message.reply_text("👋 Bot Activo.\nUsa /apellido, /nombre, /domicilio o envía un ID.")

async def reload_db(update, context):
    if descargar_db(): await update.message.reply_text("✅ Actualizado.")
    else: await update.message.reply_text("❌ Error.")

# --- 6. ARRANQUE ---
if __name__ == '__main__':
    keep_alive()
    if not descargar_db(): print("⚠️ Sin DB inicial")
    
    app_bot = ApplicationBuilder().token(TOKEN).build()
    
    app_bot.add_handler(CommandHandler('start', start))
    app_bot.add_handler(CommandHandler('actualizar', reload_db))
    app_bot.add_handler(CommandHandler('apellido', cmd_apellido))
    app_bot.add_handler(CommandHandler('nombre', cmd_nombre))
    app_bot.add_handler(CommandHandler('domicilio', cmd_domicilio))
    
    # Handler para los botones
    app_bot.add_handler(CallbackQueryHandler(boton_callback))
    
    app_bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), buscar_general))
    
    print("🤖 Bot con Paginación LISTO")
    app_bot.run_polling()
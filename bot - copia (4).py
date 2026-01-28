import os
import math
import logging
import sqlite3
import requests
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters

# --- 1. CONFIGURACIÓN Y VARIABLES ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_URL = os.getenv("DB_URL") 

NOMBRE_DB_LOCAL = "datos_seguros.db"
NOMBRE_TABLA = "maestra"      

# ⚠️ CONFIGURACIÓN DE COLUMNAS (REVISA EN TU EXCEL)
COL_ID_PRINCIPAL = "id"       
COL_APELLIDO     = "APELLIDO" 
COL_NOMBRE       = "NOMBRE"   
COL_DOMICILIO    = "domicilio"
COL_SEXO         = "SEXO"     
COL_CLASE        = "CLASE"    

RESULTADOS_POR_PAGINA = 5 

# --- SERVIDOR WEB (KEEP-ALIVE) ---
app = Flask('')

@app.route('/')
def home():
    return "🤖 Bot activo v4."

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

# --- 3. MOTORES DE BÚSQUEDA ---

# A. Búsqueda Simple (Una sola columna)
def obtener_datos_paginados(columna, valor, pagina=0):
    if not os.path.exists(NOMBRE_DB_LOCAL): return "⚠️ Cargando DB...", False
    try:
        conn = sqlite3.connect(NOMBRE_DB_LOCAL)
        cursor = conn.cursor()
        
        q_count = f"SELECT COUNT(*) FROM {NOMBRE_TABLA} WHERE {columna} LIKE ? COLLATE NOCASE"
        cursor.execute(q_count, (f"%{valor}%",))
        total = cursor.fetchone()[0]
        
        if total == 0:
            conn.close()
            return f"❌ Nada en {columna} para '{valor}'.", False
        
        paginas_tot = math.ceil(total / RESULTADOS_POR_PAGINA)
        offset = pagina * RESULTADOS_POR_PAGINA
        
        q_data = f"SELECT * FROM {NOMBRE_TABLA} WHERE {columna} LIKE ? COLLATE NOCASE LIMIT {RESULTADOS_POR_PAGINA} OFFSET {offset}"
        cursor.execute(q_data, (f"%{valor}%",))
        filas = cursor.fetchall()
        headers = [d[0] for d in cursor.description]
        conn.close()

        mensaje = f"🔎 **'{valor}'** (Pág {pagina + 1}/{paginas_tot}):\n"
        for fila in filas:
            mensaje += "\n➖➖➖➖➖\n"
            for i in range(len(headers)):
                d = str(fila[i])
                if d and d.lower() not in ['nan', 'none', '']:
                    mensaje += f"🔹 *{headers[i]}:* {d}\n"
        
        return mensaje, (pagina + 1) < paginas_tot
    except Exception as e:
        return f"⚠️ Error: {e}", False

# B. Búsqueda Finder (Sexo + Clase + Domicilio)
def obtener_datos_combinados(sexo, clase, domicilio, pagina=0):
    if not os.path.exists(NOMBRE_DB_LOCAL): return "⚠️ Cargando DB...", False
    try:
        conn = sqlite3.connect(NOMBRE_DB_LOCAL)
        cursor = conn.cursor()
        
        # AQUI ESTÁ EL CAMBIO: Agregamos COLLATE NOCASE a todo para que 'f'='F'
        condicion = f"{COL_SEXO} = ? COLLATE NOCASE AND {COL_CLASE} = ? COLLATE NOCASE AND {COL_DOMICILIO} LIKE ? COLLATE NOCASE"
        params = (sexo, clase, f"%{domicilio}%")

        cursor.execute(f"SELECT COUNT(*) FROM {NOMBRE_TABLA} WHERE {condicion}", params)
        total = cursor.fetchone()[0]
        
        if total == 0:
            conn.close()
            return f"❌ Sin resultados Finder.", False
            
        paginas_tot = math.ceil(total / RESULTADOS_POR_PAGINA)
        offset = pagina * RESULTADOS_POR_PAGINA
        
        q_data = f"SELECT * FROM {NOMBRE_TABLA} WHERE {condicion} LIMIT {RESULTADOS_POR_PAGINA} OFFSET {offset}"
        cursor.execute(q_data, params)
        filas = cursor.fetchall()
        headers = [d[0] for d in cursor.description]
        conn.close()

        mensaje = f"🎯 **Finder** (Pág {pagina + 1}/{paginas_tot}):\n"
        for fila in filas:
            mensaje += "\n➖➖➖➖➖\n"
            for i in range(len(headers)):
                d = str(fila[i])
                if d and d.lower() not in ['nan', 'none', '']:
                    mensaje += f"🔹 *{headers[i]}:* {d}\n"
        
        return mensaje, (pagina + 1) < paginas_tot
    except Exception as e:
        return f"⚠️ Error Finder: {e}", False

# C. NUEVO: Búsqueda Persona (Apellido + Nombre)
def obtener_datos_persona(apellido, nombre, pagina=0):
    if not os.path.exists(NOMBRE_DB_LOCAL): return "⚠️ Cargando DB...", False
    try:
        conn = sqlite3.connect(NOMBRE_DB_LOCAL)
        cursor = conn.cursor()
        
        # Buscamos coincidencias parciales en AMBOS campos
        condicion = f"{COL_APELLIDO} LIKE ? COLLATE NOCASE AND {COL_NOMBRE} LIKE ? COLLATE NOCASE"
        params = (f"%{apellido}%", f"%{nombre}%")

        cursor.execute(f"SELECT COUNT(*) FROM {NOMBRE_TABLA} WHERE {condicion}", params)
        total = cursor.fetchone()[0]
        
        if total == 0:
            conn.close()
            return f"❌ Nadie con Apellido '{apellido}' y Nombre '{nombre}'.", False
            
        paginas_tot = math.ceil(total / RESULTADOS_POR_PAGINA)
        offset = pagina * RESULTADOS_POR_PAGINA
        
        q_data = f"SELECT * FROM {NOMBRE_TABLA} WHERE {condicion} LIMIT {RESULTADOS_POR_PAGINA} OFFSET {offset}"
        cursor.execute(q_data, params)
        filas = cursor.fetchall()
        headers = [d[0] for d in cursor.description]
        conn.close()

        mensaje = f"👤 **{apellido}, {nombre}** (Pág {pagina + 1}/{paginas_tot}):\n"
        for fila in filas:
            mensaje += "\n➖➖➖➖➖\n"
            for i in range(len(headers)):
                d = str(fila[i])
                if d and d.lower() not in ['nan', 'none', '']:
                    mensaje += f"🔹 *{headers[i]}:* {d}\n"
        
        return mensaje, (pagina + 1) < paginas_tot
    except Exception as e:
        return f"⚠️ Error Persona: {e}", False

# --- 4. MANEJO DE COMANDOS Y BOTONES ---

def crear_teclado(prefix, datos, pagina, tiene_mas):
    botones = []
    data_str = "|".join(map(str, datos))
    if pagina > 0:
        botones.append(InlineKeyboardButton("⬅️ Ant.", callback_data=f"{prefix}|{data_str}|{pagina-1}"))
    if tiene_mas:
        botones.append(InlineKeyboardButton("Sig. ➡️", callback_data=f"{prefix}|{data_str}|{pagina+1}"))
    return InlineKeyboardMarkup([botones]) if botones else None

async def responder_busqueda(update, columna, valor, pagina=0, es_edicion=False):
    texto, tiene_mas = obtener_datos_paginados(columna, valor, pagina)
    teclado = crear_teclado('simple', [columna, valor], pagina, tiene_mas)
    await enviar_respuesta(update, texto, teclado, es_edicion)

async def responder_finder(update, sexo, clase, domicilio, pagina=0, es_edicion=False):
    texto, tiene_mas = obtener_datos_combinados(sexo, clase, domicilio, pagina)
    teclado = crear_teclado('finder', [sexo, clase, domicilio], pagina, tiene_mas)
    await enviar_respuesta(update, texto, teclado, es_edicion)

async def responder_persona(update, apellido, nombre, pagina=0, es_edicion=False):
    texto, tiene_mas = obtener_datos_persona(apellido, nombre, pagina)
    teclado = crear_teclado('persona', [apellido, nombre], pagina, tiene_mas)
    await enviar_respuesta(update, texto, teclado, es_edicion)

async def enviar_respuesta(update, texto, teclado, es_edicion):
    if es_edicion:
        try: await update.callback_query.edit_message_text(texto, parse_mode='Markdown', reply_markup=teclado)
        except: pass
    else:
        await update.message.reply_text(texto, parse_mode='Markdown', reply_markup=teclado)

# --- HANDLERS ---

async def cmd_persona(update, context):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("⚠️ Uso: `/persona [Apellido] [Nombre]`\nEj: `/persona Gomez Juan`", parse_mode='Markdown')
        return
    # Asumimos que la primera palabra es el Apellido y el resto el Nombre
    apellido = args[0]
    nombre = " ".join(args[1:]) 
    await responder_persona(update, apellido, nombre, 0)

async def cmd_finder(update, context):
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("⚠️ Uso: `/finder [Sexo] [Clase] [Domicilio]`", parse_mode='Markdown')
        return
    sexo = args[0] # Al tener COLLATE NOCASE en SQL, ya no importa si es 'f' o 'F'
    clase = args[1]
    domicilio = " ".join(args[2:])
    await responder_finder(update, sexo, clase, domicilio, 0)

async def manejar_comando_simple(update, context, columna_db):
    if not context.args:
        await update.message.reply_text("⚠️ Escribe algo para buscar.")
        return
    busqueda = " ".join(context.args)
    await responder_busqueda(update, columna_db, busqueda, 0)

async def cmd_apellido(u, c): await manejar_comando_simple(u, c, COL_APELLIDO)
async def cmd_nombre(u, c): await manejar_comando_simple(u, c, COL_NOMBRE)
async def cmd_domicilio(u, c): await manejar_comando_simple(u, c, COL_DOMICILIO)

async def buscar_general(update, context):
    await responder_busqueda(update, COL_ID_PRINCIPAL, update.message.text, 0)

async def boton_callback(update, context):
    query = update.callback_query
    await query.answer()
    datos = query.data.split('|')
    tipo = datos[0]
    
    if tipo == 'simple':
        await responder_busqueda(update, datos[1], datos[2], int(datos[3]), True)
    elif tipo == 'finder':
        await responder_finder(update, datos[1], datos[2], datos[3], int(datos[4]), True)
    elif tipo == 'persona':
        # persona|apellido|nombre|pagina
        await responder_persona(update, datos[1], datos[2], int(datos[3]), True)

async def start(update, context):
    msg = (
        "👋 **Bot Activo**\n\n"
        "🔎 /apellido [val]\n"
        "🔎 /nombre [val]\n"
        "👤 /persona [Apellido] [Nombre]\n"
        "🎯 /finder [S] [Clase] [Dom]\n"
        "🏠 /domicilio [val]"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def reload_db(update, context):
    if descargar_db(): await update.message.reply_text("✅ Actualizado.")
    else: await update.message.reply_text("❌ Error.")

# --- ARRANQUE ---
if __name__ == '__main__':
    keep_alive()
    if not descargar_db(): print("⚠️ Sin DB inicial")
    
    app_bot = ApplicationBuilder().token(TOKEN).build()
    
    app_bot.add_handler(CommandHandler('start', start))
    app_bot.add_handler(CommandHandler('actualizar', reload_db))
    app_bot.add_handler(CommandHandler('apellido', cmd_apellido))
    app_bot.add_handler(CommandHandler('nombre', cmd_nombre))
    app_bot.add_handler(CommandHandler('domicilio', cmd_domicilio))
    app_bot.add_handler(CommandHandler('finder', cmd_finder))
    app_bot.add_handler(CommandHandler('persona', cmd_persona)) # <--- COMANDO NUEVO
    
    app_bot.add_handler(CallbackQueryHandler(boton_callback))
    app_bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), buscar_general))
    
    print("🤖 Bot v4 LISTO")
    app_bot.run_polling()
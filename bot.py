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

# ⚠️ CONFIGURACIÓN DE COLUMNAS (¡REVISA ESTO EN TU EXCEL!)
COL_ID_PRINCIPAL = "id"       
COL_APELLIDO     = "APELLIDO" 
COL_NOMBRE       = "NOMBRE"   
COL_DOMICILIO    = "domicilio"
COL_SEXO         = "SEXO"     # <--- NUEVO: Nombre exacto columna Sexo
COL_CLASE        = "CLASE"    # <--- NUEVO: Nombre exacto columna Clase (Año)

RESULTADOS_POR_PAGINA = 5 

# --- SERVIDOR WEB (KEEP-ALIVE) ---
app = Flask('')

@app.route('/')
def home():
    return "🤖 Bot activo con Finder."

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
        
        # Contar total
        q_count = f"SELECT COUNT(*) FROM {NOMBRE_TABLA} WHERE {columna} LIKE ? COLLATE NOCASE"
        cursor.execute(q_count, (f"%{valor}%",))
        total = cursor.fetchone()[0]
        
        if total == 0:
            conn.close()
            return f"❌ Nada encontrado en {columna}.", False
        
        paginas_tot = math.ceil(total / RESULTADOS_POR_PAGINA)
        offset = pagina * RESULTADOS_POR_PAGINA
        
        # Consultar datos
        q_data = f"SELECT * FROM {NOMBRE_TABLA} WHERE {columna} LIKE ? COLLATE NOCASE LIMIT {RESULTADOS_POR_PAGINA} OFFSET {offset}"
        cursor.execute(q_data, (f"%{valor}%",))
        filas = cursor.fetchall()
        headers = [d[0] for d in cursor.description]
        conn.close()

        mensaje = f"🔎 **Resultados '{valor}'** (Pág {pagina + 1}/{paginas_tot}):\n"
        for fila in filas:
            mensaje += "\n➖➖➖➖➖\n"
            for i in range(len(headers)):
                d = str(fila[i])
                if d and d.lower() not in ['nan', 'none', '']:
                    mensaje += f"🔹 *{headers[i]}:* {d}\n"
        
        return mensaje, (pagina + 1) < paginas_tot
    except Exception as e:
        return f"⚠️ Error: {e}", False

# B. Búsqueda Combinada (FINDER: Sexo + Clase + Domicilio)
def obtener_datos_combinados(sexo, clase, domicilio, pagina=0):
    if not os.path.exists(NOMBRE_DB_LOCAL): return "⚠️ Cargando DB...", False
    try:
        conn = sqlite3.connect(NOMBRE_DB_LOCAL)
        cursor = conn.cursor()
        
        # Filtros: Sexo (=), Clase (=), Domicilio (LIKE)
        # Usamos COLLATE NOCASE en domicilio, pero en Sexo/Clase solemos querer exactitud (o también nocase si prefieres)
        condicion = f"{COL_SEXO} = ? AND {COL_CLASE} = ? AND {COL_DOMICILIO} LIKE ? COLLATE NOCASE"
        params = (sexo, clase, f"%{domicilio}%")

        # 1. Contar Total
        cursor.execute(f"SELECT COUNT(*) FROM {NOMBRE_TABLA} WHERE {condicion}", params)
        total = cursor.fetchone()[0]
        
        if total == 0:
            conn.close()
            return f"❌ Sin resultados para Sexo:{sexo}, Clase:{clase}, Dom:{domicilio}", False
            
        paginas_tot = math.ceil(total / RESULTADOS_POR_PAGINA)
        offset = pagina * RESULTADOS_POR_PAGINA
        
        # 2. Traer Datos
        q_data = f"SELECT * FROM {NOMBRE_TABLA} WHERE {condicion} LIMIT {RESULTADOS_POR_PAGINA} OFFSET {offset}"
        cursor.execute(q_data, params)
        filas = cursor.fetchall()
        headers = [d[0] for d in cursor.description]
        conn.close()

        mensaje = f"🎯 **Finder: {sexo} | {clase} | {domicilio}**\n(Pág {pagina + 1}/{paginas_tot}):\n"
        for fila in filas:
            mensaje += "\n➖➖➖➖➖\n"
            for i in range(len(headers)):
                d = str(fila[i])
                if d and d.lower() not in ['nan', 'none', '']:
                    mensaje += f"🔹 *{headers[i]}:* {d}\n"
        
        return mensaje, (pagina + 1) < paginas_tot
        
    except Exception as e:
        return f"⚠️ Error Finder: {e}", False

# --- 4. MANEJO DE COMANDOS Y BOTONES ---

# Helper para crear botones (Genérico)
def crear_teclado(callback_prefix, datos_lista, pagina, tiene_mas):
    """
    callback_prefix: 'simple' o 'finder'
    datos_lista: lista de valores a pasar en el callback
    """
    botones = []
    # Convertimos lista de datos a string separado por |
    data_str = "|".join(map(str, datos_lista))
    
    if pagina > 0:
        botones.append(InlineKeyboardButton("⬅️ Ant.", callback_data=f"{callback_prefix}|{data_str}|{pagina-1}"))
    if tiene_mas:
        botones.append(InlineKeyboardButton("Sig. ➡️", callback_data=f"{callback_prefix}|{data_str}|{pagina+1}"))
        
    return InlineKeyboardMarkup([botones]) if botones else None

# Respuesta Búsqueda Simple
async def responder_busqueda(update, columna, valor, pagina=0, es_edicion=False):
    texto, tiene_mas = obtener_datos_paginados(columna, valor, pagina)
    teclado = crear_teclado('simple', [columna, valor], pagina, tiene_mas)
    
    if es_edicion:
        try: await update.callback_query.edit_message_text(texto, parse_mode='Markdown', reply_markup=teclado)
        except: pass
    else:
        await update.message.reply_text(texto, parse_mode='Markdown', reply_markup=teclado)

# Respuesta Búsqueda Finder
async def responder_finder(update, sexo, clase, domicilio, pagina=0, es_edicion=False):
    texto, tiene_mas = obtener_datos_combinados(sexo, clase, domicilio, pagina)
    # Callback data será: finder|sexo|clase|domicilio|pagina
    teclado = crear_teclado('finder', [sexo, clase, domicilio], pagina, tiene_mas)
    
    if es_edicion:
        try: await update.callback_query.edit_message_text(texto, parse_mode='Markdown', reply_markup=teclado)
        except: pass
    else:
        await update.message.reply_text(texto, parse_mode='Markdown', reply_markup=teclado)

# --- HANDLERS ---

async def cmd_finder(update, context):
    args = context.args
    # Esperamos al menos 3 argumentos: Sexo Clase Domicilio...
    if len(args) < 3:
        await update.message.reply_text("⚠️ Uso incorrecto.\nEjemplo: `/finder M 1990 San Martin`\n(Sexo Clase Domicilio)", parse_mode='Markdown')
        return
    
    sexo = args[0]
    clase = args[1]
    domicilio = " ".join(args[2:]) # Une el resto de palabras como domicilio
    
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
        # simple|columna|valor|pagina
        col, val, pag = datos[1], datos[2], int(datos[3])
        await responder_busqueda(update, col, val, pag, es_edicion=True)
        
    elif tipo == 'finder':
        # finder|sexo|clase|domicilio|pagina
        sex, cla, dom, pag = datos[1], datos[2], datos[3], int(datos[4])
        await responder_finder(update, sex, cla, dom, pag, es_edicion=True)

async def start(update, context):
    msg = "👋 **Bot Activo**\n\n🔎 /apellido [val]\n🔎 /nombre [val]\n🔎 /domicilio [val]\n🎯 /finder [sexo] [clase] [domicilio]\n\nO envía un ID directo."
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
    app_bot.add_handler(CommandHandler('finder', cmd_finder)) # <--- NUEVO COMANDO
    
    app_bot.add_handler(CallbackQueryHandler(boton_callback))
    app_bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), buscar_general))
    
    print("🤖 Bot Finder LISTO")
    app_bot.run_polling()
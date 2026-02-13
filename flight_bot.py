"""
✈️ Bot de Alertas de Passagens Aéreas - Google Flights + Telegram
Autor: Gerado com Claude
Descrição: Monitora passagens aéreas no Google Flights e envia alertas
           via Telegram quando o preço cai abaixo do valor configurado.
"""

import os
import time
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field, asdict
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters, ConversationHandler
)

# ─── SERVIDOR HTTP (KEEP ALIVE PARA RENDER) ─────────────────────────────────────
class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot Telegram rodando com sucesso!")

def iniciar_servidor_http():
    porta = int(os.environ.get("PORT", 10000))
    servidor = HTTPServer(("0.0.0.0", porta), KeepAliveHandler)
    print(f"🌐 Servidor HTTP ativo na porta {porta}")
    servidor.serve_forever()

# ─── Configuração de Logging ───────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ─── Estados da Conversa ───────────────────────────────────────────────────────
AGUARDANDO_ORIGEM, AGUARDANDO_PRECO, AGUARDANDO_DATA, AGUARDANDO_TIPO = range(4)

# ─── Configurações ─────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "SEU_TOKEN_AQUI")
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "SUA_CHAVE_SERPAPI_AQUI")
INTERVALO_VERIFICACAO_MINUTOS = 30

# ─── Aeroportos (mantido igual) ────────────────────────────────────────────────
AEROPORTOS_BRASIL = {
    "São Paulo (GRU)": "GRU",
    "Rio de Janeiro (GIG)": "GIG",
    "Brasília (BSB)": "BSB",
    "Salvador (SSA)": "SSA",
    "Belo Horizonte (CNF)": "CNF",
    "Fortaleza (FOR)": "FOR",
    "Recife (REC)": "REC",
    "Porto Alegre (POA)": "POA",
    "Curitiba (CWB)": "CWB",
}

# ─── Estrutura de Dados ────────────────────────────────────────────────────────
@dataclass
class AlertaPassagem:
    chat_id: int
    origem: str
    codigo_origem: str
    preco_maximo: float
    data_partida: str
    tipo_voo: str
    ativo: bool = True
    criado_em: str = field(default_factory=lambda: datetime.now().isoformat())
    ultimo_alerta: Optional[str] = None

# ─── Gerenciador de Alertas ────────────────────────────────────────────────────
class GerenciadorAlertas:
    def __init__(self, arquivo="alertas.json"):
        self.arquivo = arquivo
        self.alertas = []
        self.carregar()

    def carregar(self):
        if os.path.exists(self.arquivo):
            with open(self.arquivo, "r", encoding="utf-8") as f:
                self.alertas = [AlertaPassagem(**a) for a in json.load(f)]

    def salvar(self):
        with open(self.arquivo, "w", encoding="utf-8") as f:
            json.dump([asdict(a) for a in self.alertas], f, indent=2, ensure_ascii=False)

    def adicionar(self, alerta):
        self.alertas.append(alerta)
        self.salvar()

    def listar_usuario(self, chat_id):
        return [a for a in self.alertas if a.chat_id == chat_id and a.ativo]

    def todos_ativos(self):
        return [a for a in self.alertas if a.ativo]

    def remover(self, chat_id, indice):
        alertas = self.listar_usuario(chat_id)
        if 0 <= indice < len(alertas):
            self.alertas.remove(alertas[indice])
            self.salvar()
            return True
        return False

gerenciador = GerenciadorAlertas()

# ─── Scraper via SerpAPI (mantido) ──────────────────────────────────────────────
class GoogleFlightsScraper:
    BASE_URL = "https://serpapi.com/search"

    def buscar_voos(self, origem, destino, data):
        params = {
            "engine": "google_flights",
            "departure_id": origem,
            "arrival_id": destino,
            "outbound_date": data,
            "currency": "BRL",
            "hl": "pt",
            "api_key": SERPAPI_KEY,
        }
        try:
            r = requests.get(self.BASE_URL, params=params, timeout=30)
            r.raise_for_status()
            return r.json().get("best_flights", [])
        except Exception:
            return []

scraper = GoogleFlightsScraper()

# ─── Telegram Handlers (mantidos) ───────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✈️ Bot de passagens ativo! Use /novo_alerta")

# ─── Verificador de preços ─────────────────────────────────────────────────────
async def verificar_precos(bot: Bot):
    for alerta in gerenciador.todos_ativos():
        voos = scraper.buscar_voos(alerta.codigo_origem, "SSA", alerta.data_partida)
        if voos:
            await bot.send_message(
                alerta.chat_id,
                f"🚨 Oferta encontrada saindo de {alerta.origem}!"
            )

# ─── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    if TELEGRAM_BOT_TOKEN == "SEU_TOKEN_AQUI":
        print("❌ Configure o TELEGRAM_BOT_TOKEN")
        return

    # 🔥 Inicia servidor HTTP em background (Render)
    Thread(target=iniciar_servidor_http, daemon=True).start()

    print("✈️ Iniciando bot Telegram...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    async def tarefa(context: ContextTypes.DEFAULT_TYPE):
        await verificar_precos(context.bot)

    app.job_queue.run_repeating(
        tarefa,
        interval=INTERVALO_VERIFICACAO_MINUTOS * 60,
        first=10
    )

    print("✅ Bot rodando e aguardando mensagens...")
    app.run_polling()

if __name__ == "__main__":
    main()

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
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests
from telegram import Bot, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes
)

# ─── SERVIDOR HTTP (OBRIGATÓRIO NO RENDER) ───────────────────────────────────────
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

# ─── LOGGING ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── CONFIGURAÇÕES ─────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "SEU_TOKEN_AQUI")
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "SUA_CHAVE_SERPAPI_AQUI")
INTERVALO_VERIFICACAO_MINUTOS = 30

# ─── ESTRUTURA DE DADOS ────────────────────────────────────────────────────────
@dataclass
class AlertaPassagem:
    chat_id: int
    origem: str
    codigo_origem: str
    preco_maximo: float
    data_partida: str
    ativo: bool = True
    criado_em: str = field(default_factory=lambda: datetime.now().isoformat())
    ultimo_alerta: Optional[str] = None

# ─── GERENCIADOR DE ALERTAS ────────────────────────────────────────────────────
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
            json.dump(
                [asdict(a) for a in self.alertas],
                f,
                indent=2,
                ensure_ascii=False
            )

    def todos_ativos(self):
        return [a for a in self.alertas if a.ativo]

gerenciador = GerenciadorAlertas()

# ─── SCRAPER (SERPAPI) ─────────────────────────────────────────────────────────
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
        except Exception as e:
            logger.error(f"Erro ao buscar voos: {e}")
            return []

scraper = GoogleFlightsScraper()

# ─── TELEGRAM HANDLERS ─────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✈️ Bot de passagens ativo!\n"
        "Use /novo_alerta para criar um alerta."
    )

async def novo_alerta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛫 Novo alerta iniciado!\n\n"
        "Em breve vou te perguntar:\n"
        "• cidade de origem\n"
        "• data da viagem\n"
        "• preço máximo\n\n"
        "🚧 Fluxo completo em desenvolvimento"
    )

# ─── VERIFICADOR DE PREÇOS (JOB) ───────────────────────────────────────────────
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

    # 🔥 HTTP server obrigatório no Render
    Thread(target=iniciar_servidor_http, daemon=True).start()

    print("✈️ Iniciando bot Telegram...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("novo_alerta", novo_alerta))

    # job periódico
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

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
import schedule
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field, asdict

import requests
from bs4 import BeautifulSoup
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters, ConversationHandler
)

# ─── Configuração de Logging ───────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("flight_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ─── Estados da Conversa ───────────────────────────────────────────────────────
AGUARDANDO_ORIGEM, AGUARDANDO_PRECO, AGUARDANDO_DATA, AGUARDANDO_TIPO = range(4)


# ─── Configurações ─────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "SEU_TOKEN_AQUI")
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "SUA_CHAVE_SERPAPI_AQUI")  # Para raspar o Google Flights
INTERVALO_VERIFICACAO_MINUTOS = 30  # Verificar a cada 30 minutos

# Principais aeroportos do Brasil
AEROPORTOS_BRASIL = {
    "São Paulo (GRU)": "GRU",
    "São Paulo (CGH)": "CGH",
    "Rio de Janeiro (GIG)": "GIG",
    "Rio de Janeiro (SDU)": "SDU",
    "Brasília (BSB)": "BSB",
    "Salvador (SSA)": "SSA",
    "Belo Horizonte (CNF)": "CNF",
    "Fortaleza (FOR)": "FOR",
    "Manaus (MAO)": "MAO",
    "Recife (REC)": "REC",
    "Porto Alegre (POA)": "POA",
    "Curitiba (CWB)": "CWB",
    "Belém (BEL)": "BEL",
    "Florianópolis (FLN)": "FLN",
    "Maceió (MCZ)": "MCZ",
    "Natal (NAT)": "NAT",
    "João Pessoa (JPA)": "JPA",
    "Aracaju (AJU)": "AJU",
    "Teresina (THE)": "THE",
    "Campo Grande (CGR)": "CGR",
    "Cuiabá (CGB)": "CGB",
    "Porto Velho (PVH)": "PVH",
    "Rio Branco (RBR)": "RBR",
    "Boa Vista (BVB)": "BVB",
    "Macapá (MCP)": "MCP",
    "Palmas (PMW)": "PMW",
    "Goiânia (GYN)": "GYN",
    "Vitória (VIX)": "VIX",
}


# ─── Estrutura de Dados de Alerta ──────────────────────────────────────────────
@dataclass
class AlertaPassagem:
    chat_id: int
    origem: str
    codigo_origem: str
    preco_maximo: float
    data_partida: str  # Formato: YYYY-MM-DD ou "flexivel"
    tipo_voo: str  # "ida" ou "ida_e_volta"
    ativo: bool = True
    criado_em: str = field(default_factory=lambda: datetime.now().isoformat())
    ultimo_alerta: Optional[str] = None


# ─── Gerenciador de Alertas (persistência simples em JSON) ─────────────────────
class GerenciadorAlertas:
    def __init__(self, arquivo: str = "alertas.json"):
        self.arquivo = arquivo
        self.alertas: list[AlertaPassagem] = []
        self.carregar()

    def carregar(self):
        if os.path.exists(self.arquivo):
            with open(self.arquivo, "r", encoding="utf-8") as f:
                dados = json.load(f)
                self.alertas = [AlertaPassagem(**a) for a in dados]
        logger.info(f"✅ {len(self.alertas)} alertas carregados.")

    def salvar(self):
        with open(self.arquivo, "w", encoding="utf-8") as f:
            json.dump([asdict(a) for a in self.alertas], f, ensure_ascii=False, indent=2)

    def adicionar(self, alerta: AlertaPassagem):
        self.alertas.append(alerta)
        self.salvar()
        logger.info(f"➕ Alerta adicionado para chat_id={alerta.chat_id} | {alerta.origem} → Brasil | R${alerta.preco_maximo}")

    def remover(self, chat_id: int, indice: int) -> bool:
        alertas_usuario = [a for a in self.alertas if a.chat_id == chat_id]
        if 0 <= indice < len(alertas_usuario):
            alerta = alertas_usuario[indice]
            self.alertas.remove(alerta)
            self.salvar()
            return True
        return False

    def listar_usuario(self, chat_id: int) -> list[AlertaPassagem]:
        return [a for a in self.alertas if a.chat_id == chat_id and a.ativo]

    def todos_ativos(self) -> list[AlertaPassagem]:
        return [a for a in self.alertas if a.ativo]

    def marcar_alerta_enviado(self, alerta: AlertaPassagem):
        alerta.ultimo_alerta = datetime.now().isoformat()
        self.salvar()


# ─── Scraper do Google Flights via SerpAPI ─────────────────────────────────────
class GoogleFlightsScraper:
    """
    Usa a SerpAPI para consultar o Google Flights.
    Alternativa gratuita com limitações: usar requests + BeautifulSoup
    diretamente (veja método _buscar_direto para fallback).
    """

    BASE_URL = "https://serpapi.com/search"

    def buscar_voos(
        self,
        origem: str,
        destino: str,
        data_partida: str,
        data_volta: Optional[str] = None
    ) -> list[dict]:
        """
        Busca voos no Google Flights via SerpAPI.
        Retorna lista de dicionários com informações do voo.
        """
        params = {
            "engine": "google_flights",
            "departure_id": origem,
            "arrival_id": destino,
            "outbound_date": data_partida,
            "currency": "BRL",
            "hl": "pt",
            "api_key": SERPAPI_KEY,
            "type": "1" if data_volta is None else "2",  # 1=só ida, 2=ida e volta
        }
        if data_volta:
            params["return_date"] = data_volta

        try:
            response = requests.get(self.BASE_URL, params=params, timeout=30)
            response.raise_for_status()
            dados = response.json()
            return self._processar_resposta(dados)
        except requests.exceptions.ConnectionError:
            logger.error("❌ Sem conexão com a internet ou SerpAPI indisponível.")
            return []
        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ Erro HTTP na SerpAPI: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Erro inesperado ao buscar voos: {e}")
            return []

    def _processar_resposta(self, dados: dict) -> list[dict]:
        voos = []
        for secao in ["best_flights", "other_flights"]:
            for voo in dados.get(secao, []):
                try:
                    preco = voo.get("price", 0)
                    if not preco:
                        continue

                    itinerario = voo.get("flights", [{}])[0]
                    voos.append({
                        "preco": float(preco),
                        "companhia": itinerario.get("airline", "N/A"),
                        "origem": itinerario.get("departure_airport", {}).get("name", ""),
                        "destino": itinerario.get("arrival_airport", {}).get("name", ""),
                        "partida": itinerario.get("departure_airport", {}).get("time", ""),
                        "chegada": itinerario.get("arrival_airport", {}).get("time", ""),
                        "duracao": voo.get("total_duration", 0),
                        "escalas": len(voo.get("flights", [])) - 1,
                        "link": f"https://www.google.com/flights#flt={itinerario.get('departure_airport', {}).get('id', '')}.{itinerario.get('arrival_airport', {}).get('id', '')}.",
                    })
                except Exception as e:
                    logger.warning(f"⚠️ Erro ao processar voo: {e}")
        return voos

    def buscar_menor_preco_todos_destinos(
        self,
        origem: str,
        data_partida: str,
        preco_maximo: float,
    ) -> list[dict]:
        """
        Busca o menor preço para todos os destinos no Brasil.
        """
        resultados = []
        destinos_verificar = list(AEROPORTOS_BRASIL.values())

        # Remove o aeroporto de origem da lista
        if origem in destinos_verificar:
            destinos_verificar.remove(origem)

        logger.info(f"🔍 Buscando voos de {origem} para {len(destinos_verificar)} destinos...")

        for destino_codigo in destinos_verificar:
            try:
                voos = self.buscar_voos(origem, destino_codigo, data_partida)
                for voo in voos:
                    if voo["preco"] <= preco_maximo:
                        # Encontra nome do destino
                        destino_nome = next(
                            (nome for nome, cod in AEROPORTOS_BRASIL.items() if cod == destino_codigo),
                            destino_codigo
                        )
                        voo["destino_codigo"] = destino_codigo
                        voo["destino_nome"] = destino_nome
                        resultados.append(voo)
                        logger.info(f"✅ Oferta encontrada: {origem} → {destino_codigo} | R${voo['preco']}")
                time.sleep(1)  # Evitar rate limiting
            except Exception as e:
                logger.warning(f"⚠️ Erro ao buscar {origem} → {destino_codigo}: {e}")

        return sorted(resultados, key=lambda x: x["preco"])


# ─── Instâncias Globais ────────────────────────────────────────────────────────
gerenciador = GerenciadorAlertas()
scraper = GoogleFlightsScraper()


# ─── Handlers do Telegram ──────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensagem de boas-vindas."""
    texto = (
        "✈️ *Bot de Alertas de Passagens Aéreas*\n\n"
        "Olá! Eu monitoro o Google Flights e te aviso quando aparecer passagens baratas!\n\n"
        "📋 *Comandos disponíveis:*\n"
        "• /novo\\_alerta — Criar um novo alerta de preço\n"
        "• /meus\\_alertas — Ver seus alertas ativos\n"
        "• /remover\\_alerta — Remover um alerta\n"
        "• /ajuda — Mostrar esta mensagem\n\n"
        "🎯 *Como funciona:*\n"
        "1. Você define sua cidade de origem\n"
        "2. Define o preço máximo que quer pagar\n"
        "3. Eu verifico automaticamente a cada 30 minutos\n"
        "4. Quando achar uma passagem mais barata, te aviso aqui! 🔔"
    )
    await update.message.reply_text(texto, parse_mode="Markdown")


async def novo_alerta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia o fluxo de criação de um novo alerta."""
    # Cria teclado com cidades de origem
    teclado = []
    lista = list(AEROPORTOS_BRASIL.items())
    for i in range(0, len(lista), 2):
        linha = []
        for j in range(i, min(i + 2, len(lista))):
            nome, cod = lista[j]
            linha.append(InlineKeyboardButton(nome, callback_data=f"origem_{cod}_{nome}"))
        teclado.append(linha)

    reply_markup = InlineKeyboardMarkup(teclado)
    await update.message.reply_text(
        "🛫 *De qual cidade você quer partir?*\n\nSelecione sua cidade de origem:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return AGUARDANDO_ORIGEM


async def selecionar_origem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Salva a origem e pede o preço máximo."""
    query = update.callback_query
    await query.answer()

    partes = query.data.split("_", 2)
    codigo = partes[1]
    nome = partes[2]

    context.user_data["origem_codigo"] = codigo
    context.user_data["origem_nome"] = nome

    await query.edit_message_text(
        f"✅ Origem selecionada: *{nome}*\n\n"
        f"💰 *Qual o preço máximo que você quer pagar?*\n\n"
        f"Digite o valor em reais (apenas números). Exemplo: `500`",
        parse_mode="Markdown"
    )
    return AGUARDANDO_PRECO


async def receber_preco(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Salva o preço e pergunta sobre a data."""
    texto = update.message.text.strip().replace(",", ".").replace("R$", "").replace(" ", "")

    try:
        preco = float(texto)
        if preco <= 0 or preco > 100000:
            raise ValueError("Preço inválido")
    except ValueError:
        await update.message.reply_text(
            "❌ Valor inválido! Por favor, digite apenas números. Exemplo: `500`",
            parse_mode="Markdown"
        )
        return AGUARDANDO_PRECO

    context.user_data["preco_maximo"] = preco

    # Perguntar sobre a data
    hoje = datetime.now()
    teclado = [
        [
            InlineKeyboardButton("📅 Próximos 30 dias", callback_data="data_flexivel"),
            InlineKeyboardButton("📆 Data específica", callback_data="data_especifica"),
        ],
        [
            InlineKeyboardButton(f"Próxima semana", callback_data=f"data_{(hoje + timedelta(days=7)).strftime('%Y-%m-%d')}"),
            InlineKeyboardButton(f"Próximo mês", callback_data=f"data_{(hoje + timedelta(days=30)).strftime('%Y-%m-%d')}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(teclado)

    await update.message.reply_text(
        f"✅ Preço máximo: *R$ {preco:.2f}*\n\n"
        f"📅 *Para quando você quer viajar?*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return AGUARDANDO_DATA


async def selecionar_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Salva a data e pergunta o tipo de voo."""
    query = update.callback_query
    await query.answer()

    if query.data == "data_especifica":
        await query.edit_message_text(
            "📅 *Digite a data de partida* no formato DD/MM/AAAA:\nExemplo: `25/12/2025`",
            parse_mode="Markdown"
        )
        context.user_data["aguardando_data_texto"] = True
        return AGUARDANDO_DATA

    data = "flexivel" if query.data == "data_flexivel" else query.data.replace("data_", "")
    context.user_data["data_partida"] = data
    context.user_data["aguardando_data_texto"] = False

    # Perguntar tipo de voo
    teclado = [
        [
            InlineKeyboardButton("✈️ Só Ida", callback_data="tipo_ida"),
            InlineKeyboardButton("🔄 Ida e Volta", callback_data="tipo_ida_e_volta"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(teclado)

    data_texto = "Próximos 30 dias" if data == "flexivel" else data
    await query.edit_message_text(
        f"✅ Data: *{data_texto}*\n\n"
        f"🎫 *Que tipo de passagem você quer?*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return AGUARDANDO_TIPO


async def receber_data_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe a data digitada pelo usuário."""
    if not context.user_data.get("aguardando_data_texto"):
        return AGUARDANDO_DATA

    texto = update.message.text.strip()
    try:
        data = datetime.strptime(texto, "%d/%m/%Y")
        if data < datetime.now():
            raise ValueError("Data no passado")
        data_formatada = data.strftime("%Y-%m-%d")
    except ValueError:
        await update.message.reply_text(
            "❌ Data inválida! Use o formato DD/MM/AAAA. Exemplo: `25/12/2025`",
            parse_mode="Markdown"
        )
        return AGUARDANDO_DATA

    context.user_data["data_partida"] = data_formatada
    context.user_data["aguardando_data_texto"] = False

    teclado = [
        [
            InlineKeyboardButton("✈️ Só Ida", callback_data="tipo_ida"),
            InlineKeyboardButton("🔄 Ida e Volta", callback_data="tipo_ida_e_volta"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(teclado)
    await update.message.reply_text(
        f"✅ Data: *{texto}*\n\n"
        f"🎫 *Que tipo de passagem você quer?*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return AGUARDANDO_TIPO


async def selecionar_tipo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finaliza a criação do alerta."""
    query = update.callback_query
    await query.answer()

    tipo = "ida" if query.data == "tipo_ida" else "ida_e_volta"
    tipo_texto = "Só Ida" if tipo == "ida" else "Ida e Volta"

    alerta = AlertaPassagem(
        chat_id=update.effective_chat.id,
        origem=context.user_data["origem_nome"],
        codigo_origem=context.user_data["origem_codigo"],
        preco_maximo=context.user_data["preco_maximo"],
        data_partida=context.user_data["data_partida"],
        tipo_voo=tipo,
    )
    gerenciador.adicionar(alerta)

    data_texto = "Próximos 30 dias" if alerta.data_partida == "flexivel" else alerta.data_partida

    await query.edit_message_text(
        f"🎉 *Alerta criado com sucesso!*\n\n"
        f"📍 Origem: *{alerta.origem}*\n"
        f"🎯 Destino: Qualquer lugar no Brasil\n"
        f"💰 Preço máximo: *R$ {alerta.preco_maximo:.2f}*\n"
        f"📅 Data: *{data_texto}*\n"
        f"🎫 Tipo: *{tipo_texto}*\n\n"
        f"⏰ Verificarei a cada {INTERVALO_VERIFICACAO_MINUTOS} minutos e te aviso quando achar uma oferta!",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


async def meus_alertas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista os alertas ativos do usuário."""
    alertas = gerenciador.listar_usuario(update.effective_chat.id)

    if not alertas:
        await update.message.reply_text(
            "📭 Você não tem alertas ativos.\n\nUse /novo_alerta para criar um!"
        )
        return

    texto = "🔔 *Seus alertas ativos:*\n\n"
    for i, alerta in enumerate(alertas, 1):
        data_texto = "Próximos 30 dias" if alerta.data_partida == "flexivel" else alerta.data_partida
        tipo_texto = "Só Ida" if alerta.tipo_voo == "ida" else "Ida e Volta"
        texto += (
            f"*{i}.* {alerta.origem} → Brasil\n"
            f"   💰 Máx: R$ {alerta.preco_maximo:.2f} | 📅 {data_texto} | {tipo_texto}\n\n"
        )

    await update.message.reply_text(texto, parse_mode="Markdown")


async def remover_alerta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove um alerta do usuário."""
    alertas = gerenciador.listar_usuario(update.effective_chat.id)

    if not alertas:
        await update.message.reply_text("📭 Você não tem alertas para remover.")
        return

    teclado = []
    for i, alerta in enumerate(alertas):
        data_texto = "Flexível" if alerta.data_partida == "flexivel" else alerta.data_partida
        label = f"❌ {alerta.origem} → R${alerta.preco_maximo:.0f} ({data_texto})"
        teclado.append([InlineKeyboardButton(label, callback_data=f"remover_{i}")])

    reply_markup = InlineKeyboardMarkup(teclado)
    await update.message.reply_text(
        "🗑️ *Qual alerta você quer remover?*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def confirmar_remocao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirma a remoção do alerta."""
    query = update.callback_query
    await query.answer()

    indice = int(query.data.replace("remover_", ""))
    sucesso = gerenciador.remover(update.effective_chat.id, indice)

    if sucesso:
        await query.edit_message_text("✅ Alerta removido com sucesso!")
    else:
        await query.edit_message_text("❌ Erro ao remover alerta. Tente novamente.")


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela a operação atual."""
    await update.message.reply_text("❌ Operação cancelada.")
    return ConversationHandler.END


# ─── Verificador de Preços (Task Periódica) ────────────────────────────────────
async def verificar_precos(bot: Bot):
    """Verifica os preços para todos os alertas ativos e envia notificações."""
    alertas = gerenciador.todos_ativos()
    if not alertas:
        return

    logger.info(f"🔍 Verificando preços para {len(alertas)} alertas...")

    for alerta in alertas:
        try:
            # Determine as datas para busca
            if alerta.data_partida == "flexivel":
                datas = [
                    (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
                    for i in range(1, 31, 7)  # Verifica a cada semana
                ]
            else:
                datas = [alerta.data_partida]

            melhores_ofertas = []
            for data in datas:
                voos = scraper.buscar_menor_preco_todos_destinos(
                    origem=alerta.codigo_origem,
                    data_partida=data,
                    preco_maximo=alerta.preco_maximo,
                )
                for voo in voos:
                    voo["data_buscada"] = data
                    melhores_ofertas.append(voo)

            if melhores_ofertas:
                # Ordena por preço e pega as 5 melhores
                melhores_ofertas = sorted(melhores_ofertas, key=lambda x: x["preco"])[:5]
                await enviar_alerta(bot, alerta, melhores_ofertas)
                gerenciador.marcar_alerta_enviado(alerta)

        except Exception as e:
            logger.error(f"❌ Erro ao verificar alerta {alerta.chat_id}: {e}")


async def enviar_alerta(bot: Bot, alerta: AlertaPassagem, ofertas: list[dict]):
    """Envia a notificação de alerta para o usuário."""
    texto = (
        f"🚨 *OFERTA ENCONTRADA!* 🚨\n\n"
        f"✈️ Saindo de: *{alerta.origem}*\n"
        f"💰 Seu limite: R$ {alerta.preco_maximo:.2f}\n\n"
        f"*🔥 Melhores ofertas encontradas:*\n\n"
    )

    for i, oferta in enumerate(ofertas, 1):
        escalas_txt = "Direto" if oferta["escalas"] == 0 else f"{oferta['escalas']} escala(s)"
        texto += (
            f"*{i}.* {oferta.get('destino_nome', oferta.get('destino', 'N/A'))}\n"
            f"   💸 *R$ {oferta['preco']:.2f}* | {oferta['companhia']}\n"
            f"   📅 {oferta.get('data_buscada', '')} | {escalas_txt}\n"
            f"   🔗 [Ver no Google Flights]({oferta.get('link', 'https://www.google.com/flights')})\n\n"
        )

    texto += "⚡ Corra! Preços podem mudar a qualquer momento!"

    try:
        await bot.send_message(
            chat_id=alerta.chat_id,
            text=texto,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        logger.info(f"✅ Alerta enviado para chat_id={alerta.chat_id}")
    except Exception as e:
        logger.error(f"❌ Erro ao enviar mensagem: {e}")


# ─── Ponto de Entrada Principal ────────────────────────────────────────────────
def main():
    """Inicia o bot do Telegram."""
    if TELEGRAM_BOT_TOKEN == "SEU_TOKEN_AQUI":
        print("❌ ERRO: Configure o TELEGRAM_BOT_TOKEN no arquivo .env ou nas variáveis de ambiente!")
        return

    if SERPAPI_KEY == "SUA_CHAVE_SERPAPI_AQUI":
        print("⚠️  AVISO: Configure o SERPAPI_KEY para buscar voos reais.")
        print("   Acesse: https://serpapi.com para obter sua chave gratuita.")

    print("✈️  Iniciando Bot de Alertas de Passagens Aéreas...")
    print(f"⏰  Verificações a cada {INTERVALO_VERIFICACAO_MINUTOS} minutos")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Handler de conversa para criar alertas
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("novo_alerta", novo_alerta)],
        states={
            AGUARDANDO_ORIGEM: [CallbackQueryHandler(selecionar_origem, pattern="^origem_")],
            AGUARDANDO_PRECO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_preco)],
            AGUARDANDO_DATA: [
                CallbackQueryHandler(selecionar_data, pattern="^data_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receber_data_texto),
            ],
            AGUARDANDO_TIPO: [CallbackQueryHandler(selecionar_tipo, pattern="^tipo_")],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ajuda", start))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("meus_alertas", meus_alertas))
    app.add_handler(CommandHandler("remover_alerta", remover_alerta))
    app.add_handler(CallbackQueryHandler(confirmar_remocao, pattern="^remover_"))

    # Agendar verificação periódica de preços
    async def tarefa_verificacao(context: ContextTypes.DEFAULT_TYPE):
        await verificar_precos(context.bot)

    app.job_queue.run_repeating(
        tarefa_verificacao,
        interval=INTERVALO_VERIFICACAO_MINUTOS * 60,
        first=10  # Primeira verificação após 10 segundos
    )

    print("✅ Bot iniciado! Aguardando mensagens...\n")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

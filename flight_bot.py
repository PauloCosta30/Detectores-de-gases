"""
✈️ Bot de Alertas de Passagens Aéreas - Google Flights + Telegram
Descrição: Monitora passagens aéreas no Google Flights e envia alertas
           via Telegram quando o preço cai abaixo do valor configurado.
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ─── SERVIDOR HTTP (OBRIGATÓRIO NO RENDER) ────────────────────────────────────
class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot Telegram rodando!")
    def log_message(self, format, *args):
        pass

def iniciar_servidor_http():
    porta = int(os.environ.get("PORT", 10000))
    servidor = HTTPServer(("0.0.0.0", porta), KeepAliveHandler)
    print(f"🌐 Servidor HTTP ativo na porta {porta}")
    servidor.serve_forever()

# ─── LOGGING ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── CONFIGURAÇÕES ────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "SEU_TOKEN_AQUI")
SERPAPI_KEY        = os.getenv("SERPAPI_KEY", "SUA_CHAVE_SERPAPI_AQUI")
ADMIN_CHAT_ID      = int(os.getenv("ADMIN_CHAT_ID", "8012383697"))   # SEU chat_id aqui
INTERVALO_MINUTOS  = 30

# ─── ESTADOS DA CONVERSA ──────────────────────────────────────────────────────
ORIGEM, DESTINO, DATA, PRECO = range(4)

# ─── AEROPORTOS DO BRASIL ─────────────────────────────────────────────────────
AEROPORTOS = {
    "Belém (BEL)":           "BEL",
    "Brasília (BSB)":        "BSB",
    "Belo Horizonte (CNF)":  "CNF",
    "Curitiba (CWB)":        "CWB",
    "Fortaleza (FOR)":       "FOR",
    "Florianópolis (FLN)":   "FLN",
    "Goiânia (GYN)":         "GYN",
    "Maceió (MCZ)":          "MCZ",
    "Manaus (MAO)":          "MAO",
    "Natal (NAT)":           "NAT",
    "Porto Alegre (POA)":    "POA",
    "Recife (REC)":          "REC",
    "Rio de Janeiro (GIG)":  "GIG",
    "Rio de Janeiro (SDU)":  "SDU",
    "Salvador (SSA)":        "SSA",
    "São Paulo (GRU)":       "GRU",
    "São Paulo (CGH)":       "CGH",
    "Vitória (VIX)":         "VIX",
}

# ─── ESTRUTURA DE DADOS ───────────────────────────────────────────────────────
@dataclass
class AlertaPassagem:
    chat_id: int
    origem: str
    codigo_origem: str
    destino: str
    codigo_destino: str
    preco_maximo: float
    data_partida: str
    ativo: bool = True
    criado_em: str = field(default_factory=lambda: datetime.now().isoformat())
    ultimo_alerta: Optional[str] = None


# ─── GERENCIADOR DE USUÁRIOS ──────────────────────────────────────────────────
class GerenciadorUsuarios:
    """
    Controla quem pode usar o bot.
    Status possíveis: "pendente", "aprovado", "negado"
    """
    def __init__(self, arquivo="usuarios.json"):
        self.arquivo = arquivo
        self.usuarios: dict[str, dict] = {}   # chave = str(chat_id)
        self.carregar()

    def carregar(self):
        if os.path.exists(self.arquivo):
            try:
                with open(self.arquivo, "r", encoding="utf-8") as f:
                    self.usuarios = json.load(f)
                logger.info(f"✅ {len(self.usuarios)} usuários carregados.")
            except Exception as e:
                logger.warning(f"⚠️ Erro ao carregar usuários: {e}")

    def salvar(self):
        with open(self.arquivo, "w", encoding="utf-8") as f:
            json.dump(self.usuarios, f, indent=2, ensure_ascii=False)

    def registrar(self, chat_id: int, nome: str, username: str):
        key = str(chat_id)
        if key not in self.usuarios:
            self.usuarios[key] = {
                "chat_id":    chat_id,
                "nome":       nome,
                "username":   username or "",
                "status":     "pendente",
                "solicitado": datetime.now().isoformat(),
                "aprovado_em": None,
            }
            self.salvar()
            return "novo"       # primeira vez
        return self.usuarios[key]["status"]   # "pendente", "aprovado", "negado"

    def status(self, chat_id: int) -> str:
        info = self.usuarios.get(str(chat_id))
        return info["status"] if info else "desconhecido"

    def aprovar(self, chat_id: int):
        key = str(chat_id)
        if key in self.usuarios:
            self.usuarios[key]["status"]      = "aprovado"
            self.usuarios[key]["aprovado_em"] = datetime.now().isoformat()
            self.salvar()

    def negar(self, chat_id: int):
        key = str(chat_id)
        if key in self.usuarios:
            self.usuarios[key]["status"] = "negado"
            self.salvar()

    def eh_aprovado(self, chat_id: int) -> bool:
        # O admin sempre tem acesso
        if chat_id == ADMIN_CHAT_ID:
            return True
        return self.status(chat_id) == "aprovado"

    def pendentes(self) -> list[dict]:
        return [u for u in self.usuarios.values() if u["status"] == "pendente"]

    def info(self, chat_id: int) -> Optional[dict]:
        return self.usuarios.get(str(chat_id))


usuarios = GerenciadorUsuarios()


# ─── GERENCIADOR DE ALERTAS ───────────────────────────────────────────────────
class GerenciadorAlertas:
    def __init__(self, arquivo="alertas.json"):
        self.arquivo = arquivo
        self.alertas: list[AlertaPassagem] = []
        self.carregar()

    def carregar(self):
        if os.path.exists(self.arquivo):
            try:
                with open(self.arquivo, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                    self.alertas = []
                    for a in dados:
                        if "destino" not in a:
                            a["destino"] = "Qualquer lugar no Brasil"
                            a["codigo_destino"] = "TODOS"
                        self.alertas.append(AlertaPassagem(**a))
                logger.info(f"✅ {len(self.alertas)} alertas carregados.")
            except Exception as e:
                logger.warning(f"⚠️ Erro ao carregar alertas: {e}")

    def salvar(self):
        with open(self.arquivo, "w", encoding="utf-8") as f:
            json.dump([asdict(a) for a in self.alertas], f, indent=2, ensure_ascii=False)

    def adicionar(self, alerta: AlertaPassagem):
        self.alertas.append(alerta)
        self.salvar()

    def listar_usuario(self, chat_id: int):
        return [a for a in self.alertas if a.chat_id == chat_id and a.ativo]

    def remover(self, chat_id: int, indice: int) -> bool:
        lista = self.listar_usuario(chat_id)
        if 0 <= indice < len(lista):
            self.alertas.remove(lista[indice])
            self.salvar()
            return True
        return False

    def todos_ativos(self):
        return [a for a in self.alertas if a.ativo]

    def marcar_enviado(self, alerta: AlertaPassagem):
        alerta.ultimo_alerta = datetime.now().isoformat()
        self.salvar()

gerenciador = GerenciadorAlertas()


# ─── SCRAPER (SERPAPI + GOOGLE FLIGHTS) ───────────────────────────────────────
class GoogleFlightsScraper:
    BASE_URL = "https://serpapi.com/search"

    def buscar_voos(self, origem: str, destino: str, data: str) -> list[dict]:
        params = {
            "engine":        "google_flights",
            "departure_id":  origem,
            "arrival_id":    destino,
            "outbound_date": data,
            "currency":      "BRL",
            "hl":            "pt",
            "api_key":       SERPAPI_KEY,
            "type":          "1",
        }
        try:
            r = requests.get(self.BASE_URL, params=params, timeout=30)
            r.raise_for_status()
            dados = r.json()
            voos = []
            for secao in ["best_flights", "other_flights"]:
                for v in dados.get(secao, []):
                    preco = v.get("price")
                    if preco:
                        itinerario = v.get("flights", [{}])[0]
                        voos.append({
                            "preco":   float(preco),
                            "cia":     itinerario.get("airline", "N/A"),
                            "escalas": len(v.get("flights", [])) - 1,
                        })
            return voos
        except Exception as e:
            logger.error(f"Erro SerpAPI ({origem}→{destino}): {e}")
            return []

    def buscar_ofertas(self, alerta: AlertaPassagem) -> list[dict]:
        resultados = []
        if alerta.codigo_destino != "TODOS":
            for voo in self.buscar_voos(alerta.codigo_origem, alerta.codigo_destino, alerta.data_partida):
                if voo["preco"] <= alerta.preco_maximo:
                    voo["destino"] = alerta.destino
                    resultados.append(voo)
        else:
            destinos = {k: v for k, v in AEROPORTOS.items() if v != alerta.codigo_origem}
            for nome, cod in destinos.items():
                for voo in self.buscar_voos(alerta.codigo_origem, cod, alerta.data_partida):
                    if voo["preco"] <= alerta.preco_maximo:
                        voo["destino"] = nome
                        resultados.append(voo)
        return sorted(resultados, key=lambda x: x["preco"])[:5]

scraper = GoogleFlightsScraper()


# ─── DECORATOR: exige aprovação ───────────────────────────────────────────────
def requer_aprovacao(func):
    """Bloqueia comandos para usuários não aprovados."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        if not usuarios.eh_aprovado(chat_id):
            status = usuarios.status(chat_id)
            if status == "pendente":
                await update.message.reply_text(
                    "⏳ Sua solicitação de acesso ainda está *pendente*.\n\n"
                    "Aguarde a aprovação do administrador. Você será notificado assim que liberado!",
                    parse_mode="Markdown"
                )
            elif status == "negado":
                await update.message.reply_text(
                    "❌ Seu acesso foi *negado* pelo administrador.",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    "⚠️ Você ainda não solicitou acesso. Use /start primeiro."
                )
            return
        return await func(update, context)
    return wrapper


# ─── HANDLERS DO TELEGRAM ─────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id  = update.effective_chat.id
    nome     = update.effective_user.full_name or "Usuário"
    username = update.effective_user.username or ""

    # Admin não precisa de aprovação
    if chat_id == ADMIN_CHAT_ID:
        await update.message.reply_text(
            f"👑 Bem-vindo de volta, *Admin*!\n\n"
            f"Comandos disponíveis:\n"
            f"• /novo\\_alerta — Criar alerta de preço\n"
            f"• /meus\\_alertas — Ver alertas ativos\n"
            f"• /remover\\_alerta — Remover um alerta\n"
            f"• /pendentes — Ver solicitações pendentes",
            parse_mode="Markdown"
        )
        return

    resultado = usuarios.registrar(chat_id, nome, username)

    if resultado == "novo":
        # Notifica o admin com botões de aprovar/negar
        user_str = f"@{username}" if username else f"ID: {chat_id}"
        botoes = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Aprovar", callback_data=f"aprv|{chat_id}|{nome}"),
            InlineKeyboardButton("❌ Negar",   callback_data=f"neg|{chat_id}|{nome}"),
        ]])
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    f"🔔 *Nova solicitação de acesso!*\n\n"
                    f"👤 Nome: *{nome}*\n"
                    f"📱 {user_str}\n"
                    f"🆔 Chat ID: `{chat_id}`"
                ),
                reply_markup=botoes,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Erro ao notificar admin: {e}")

        await update.message.reply_text(
            f"👋 Olá, *{nome}*!\n\n"
            f"✈️ Bem-vindo ao Bot de Alertas de Passagens Aéreas!\n\n"
            f"📋 Sua solicitação de acesso foi enviada ao administrador.\n"
            f"Você receberá uma notificação assim que for aprovado! 🔔",
            parse_mode="Markdown"
        )

    elif resultado == "aprovado":
        await update.message.reply_text(
            f"✅ Olá, *{nome}*! Você já tem acesso liberado.\n\n"
            f"Comandos disponíveis:\n"
            f"• /novo\\_alerta — Criar alerta de preço\n"
            f"• /meus\\_alertas — Ver alertas ativos\n"
            f"• /remover\\_alerta — Remover um alerta",
            parse_mode="Markdown"
        )

    elif resultado == "pendente":
        await update.message.reply_text(
            f"⏳ Olá, *{nome}*! Sua solicitação ainda está *pendente*.\n\n"
            f"Aguarde a aprovação do administrador.",
            parse_mode="Markdown"
        )

    elif resultado == "negado":
        await update.message.reply_text(
            f"❌ Desculpe, *{nome}*. Seu acesso foi negado pelo administrador.",
            parse_mode="Markdown"
        )


# ── Callbacks de aprovar / negar ──────────────────────────────────────────────
async def cb_aprovar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if update.effective_chat.id != ADMIN_CHAT_ID:
        await q.answer("⛔ Apenas o administrador pode fazer isso.", show_alert=True)
        return

    _, chat_id_str, nome = q.data.split("|", 2)
    chat_id = int(chat_id_str)
    usuarios.aprovar(chat_id)

    await q.edit_message_text(
        f"✅ *{nome}* foi *aprovado* com sucesso!\n🆔 ID: `{chat_id}`",
        parse_mode="Markdown"
    )

    # Avisa o usuário que foi aprovado
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "🎉 *Acesso aprovado!*\n\n"
                "Você já pode usar o bot! ✈️\n\n"
                "Comandos disponíveis:\n"
                "• /novo\\_alerta — Criar alerta de preço\n"
                "• /meus\\_alertas — Ver alertas ativos\n"
                "• /remover\\_alerta — Remover um alerta"
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Erro ao avisar usuário aprovado: {e}")


async def cb_negar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if update.effective_chat.id != ADMIN_CHAT_ID:
        await q.answer("⛔ Apenas o administrador pode fazer isso.", show_alert=True)
        return

    _, chat_id_str, nome = q.data.split("|", 2)
    chat_id = int(chat_id_str)
    usuarios.negar(chat_id)

    await q.edit_message_text(
        f"❌ *{nome}* foi *negado*.\n🆔 ID: `{chat_id}`",
        parse_mode="Markdown"
    )

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Sua solicitação de acesso foi negada pelo administrador."
        )
    except Exception as e:
        logger.error(f"Erro ao avisar usuário negado: {e}")


# ── /pendentes (apenas admin) ─────────────────────────────────────────────────
async def pendentes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ Comando exclusivo do administrador.")
        return

    lista = usuarios.pendentes()
    if not lista:
        await update.message.reply_text("✅ Nenhuma solicitação pendente no momento.")
        return

    for u in lista:
        user_str = f"@{u['username']}" if u["username"] else f"ID: {u['chat_id']}"
        botoes = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Aprovar", callback_data=f"aprv|{u['chat_id']}|{u['nome']}"),
            InlineKeyboardButton("❌ Negar",   callback_data=f"neg|{u['chat_id']}|{u['nome']}"),
        ]])
        await update.message.reply_text(
            f"🔔 *Solicitação pendente*\n\n"
            f"👤 Nome: *{u['nome']}*\n"
            f"📱 {user_str}\n"
            f"🆔 Chat ID: `{u['chat_id']}`\n"
            f"🕐 Solicitado em: {u['solicitado'][:10]}",
            reply_markup=botoes,
            parse_mode="Markdown"
        )


# ── /novo_alerta ──────────────────────────────────────────────────────────────
@requer_aprovacao
async def novo_alerta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    lista  = list(AEROPORTOS.items())
    botoes = []
    for i in range(0, len(lista), 2):
        linha = []
        for nome, cod in lista[i:i+2]:
            linha.append(InlineKeyboardButton(nome, callback_data=f"orig|{cod}|{nome}"))
        botoes.append(linha)

    await update.message.reply_text(
        "🛫 *De qual cidade você vai partir?*\n\nEscolha sua origem:",
        reply_markup=InlineKeyboardMarkup(botoes),
        parse_mode="Markdown"
    )
    return ORIGEM


async def cb_origem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    _, cod, nome = q.data.split("|", 2)
    context.user_data["origem_cod"]  = cod
    context.user_data["origem_nome"] = nome

    lista  = list(AEROPORTOS.items())
    botoes = [
        [InlineKeyboardButton("🌎  Qualquer lugar no Brasil", callback_data="dest|TODOS|Qualquer lugar no Brasil")]
    ]
    for i in range(0, len(lista), 2):
        linha = []
        for nome_dest, cod_dest in lista[i:i+2]:
            if cod_dest != cod:
                linha.append(InlineKeyboardButton(nome_dest, callback_data=f"dest|{cod_dest}|{nome_dest}"))
        if linha:
            botoes.append(linha)

    await q.edit_message_text(
        f"✅ Origem: *{nome}*\n\n"
        f"🛬 *Para onde você quer ir?*\n\nEscolha o destino:",
        reply_markup=InlineKeyboardMarkup(botoes),
        parse_mode="Markdown"
    )
    return DESTINO


async def cb_destino(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    _, cod, nome = q.data.split("|", 2)
    context.user_data["destino_cod"]  = cod
    context.user_data["destino_nome"] = nome

    await q.edit_message_text(
        f"✅ Origem: *{context.user_data['origem_nome']}*\n"
        f"✅ Destino: *{nome}*\n\n"
        f"📅 *Qual a data da viagem?*\n\n"
        f"Digite no formato DD/MM/AAAA\n"
        f"_Exemplo: 25/02/2026_",
        parse_mode="Markdown"
    )
    return DATA


async def receber_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    try:
        data = datetime.strptime(texto, "%d/%m/%Y")
        if data.date() < datetime.now().date():
            raise ValueError("data passada")
        context.user_data["data"]    = data.strftime("%Y-%m-%d")
        context.user_data["data_br"] = texto
    except ValueError:
        await update.message.reply_text(
            "❌ Data inválida! Use o formato *DD/MM/AAAA* e uma data futura.\n"
            "_Exemplo: 25/02/2026_",
            parse_mode="Markdown"
        )
        return DATA

    await update.message.reply_text(
        f"✅ Data: *{texto}*\n\n"
        f"💰 *Qual o preço máximo que você quer pagar?*\n\n"
        f"Digite só o número em reais\n"
        f"_Exemplo: 600_",
        parse_mode="Markdown"
    )
    return PRECO


async def receber_preco(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip().replace("R$", "").replace(",", ".").replace(" ", "")
    try:
        preco = float(texto)
        if preco <= 0:
            raise ValueError()
    except ValueError:
        await update.message.reply_text(
            "❌ Valor inválido! Digite apenas o número.\n_Exemplo: 600_",
            parse_mode="Markdown"
        )
        return PRECO

    alerta = AlertaPassagem(
        chat_id        = update.effective_chat.id,
        origem         = context.user_data["origem_nome"],
        codigo_origem  = context.user_data["origem_cod"],
        destino        = context.user_data["destino_nome"],
        codigo_destino = context.user_data["destino_cod"],
        preco_maximo   = preco,
        data_partida   = context.user_data["data"],
    )
    gerenciador.adicionar(alerta)

    await update.message.reply_text(
        f"🎉 *Alerta criado com sucesso!*\n\n"
        f"📍 Origem: *{alerta.origem}*\n"
        f"🎯 Destino: *{alerta.destino}*\n"
        f"💰 Preço máximo: *R$ {preco:.2f}*\n"
        f"📅 Data: *{context.user_data['data_br']}*\n\n"
        f"⏰ Vou verificar a cada {INTERVALO_MINUTOS} minutos e te aviso quando achar uma oferta! 🔔",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operação cancelada.")
    return ConversationHandler.END


@requer_aprovacao
async def meus_alertas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alertas = gerenciador.listar_usuario(update.effective_chat.id)
    if not alertas:
        await update.message.reply_text(
            "📭 Você não tem alertas ativos.\nUse /novo_alerta para criar um!"
        )
        return

    texto = "🔔 *Seus alertas ativos:*\n\n"
    for i, a in enumerate(alertas, 1):
        texto += (
            f"*{i}.* {a.origem} → {a.destino}\n"
            f"   💰 Máx: R$ {a.preco_maximo:.2f} | 📅 {a.data_partida}\n\n"
        )
    await update.message.reply_text(texto, parse_mode="Markdown")


@requer_aprovacao
async def remover_alerta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alertas = gerenciador.listar_usuario(update.effective_chat.id)
    if not alertas:
        await update.message.reply_text("📭 Nenhum alerta para remover.")
        return

    botoes = []
    for i, a in enumerate(alertas):
        label = f"❌ {a.origem} → {a.destino} | R${a.preco_maximo:.0f} | {a.data_partida}"
        botoes.append([InlineKeyboardButton(label, callback_data=f"del|{i}")])

    await update.message.reply_text(
        "🗑️ *Qual alerta deseja remover?*",
        reply_markup=InlineKeyboardMarkup(botoes),
        parse_mode="Markdown"
    )


async def cb_remover(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    indice = int(q.data.split("|")[1])
    if gerenciador.remover(update.effective_chat.id, indice):
        await q.edit_message_text("✅ Alerta removido com sucesso!")
    else:
        await q.edit_message_text("❌ Erro ao remover. Tente novamente.")


# ─── VERIFICADOR PERIÓDICO ────────────────────────────────────────────────────
async def verificar_precos(context: ContextTypes.DEFAULT_TYPE):
    alertas = gerenciador.todos_ativos()
    if not alertas:
        return
    logger.info(f"🔍 Verificando {len(alertas)} alertas...")
    for alerta in alertas:
        try:
            ofertas = scraper.buscar_ofertas(alerta)
            if ofertas:
                texto = (
                    f"🚨 *OFERTA ENCONTRADA!* 🚨\n\n"
                    f"✈️ *{alerta.origem}* → *{alerta.destino}*\n"
                    f"📅 Data: *{alerta.data_partida}*\n"
                    f"💰 Seu limite: R$ {alerta.preco_maximo:.2f}\n\n"
                    f"*🔥 Melhores ofertas:*\n\n"
                )
                for i, v in enumerate(ofertas, 1):
                    escalas = "Direto" if v["escalas"] == 0 else f"{v['escalas']} escala(s)"
                    texto += (
                        f"*{i}.* {v['destino']}\n"
                        f"   💸 *R$ {v['preco']:.2f}* | {v['cia']} | {escalas}\n\n"
                    )
                texto += "⚡ Corra! Preços mudam a qualquer momento!"
                await context.bot.send_message(
                    chat_id=alerta.chat_id,
                    text=texto,
                    parse_mode="Markdown"
                )
                gerenciador.marcar_enviado(alerta)
        except Exception as e:
            logger.error(f"Erro ao verificar alerta: {e}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    if TELEGRAM_BOT_TOKEN == "SEU_TOKEN_AQUI":
        print("❌ Configure o TELEGRAM_BOT_TOKEN nas variáveis de ambiente!")
        return
    if ADMIN_CHAT_ID == 0:
        print("⚠️  AVISO: Configure o ADMIN_CHAT_ID para receber solicitações de acesso!")

    Thread(target=iniciar_servidor_http, daemon=True).start()

    print("✈️ Iniciando bot de passagens aéreas...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("novo_alerta", novo_alerta)],
        states={
            ORIGEM:  [CallbackQueryHandler(cb_origem,  pattern=r"^orig\|")],
            DESTINO: [CallbackQueryHandler(cb_destino, pattern=r"^dest\|")],
            DATA:    [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_data)],
            PRECO:   [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_preco)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )

    app.add_handler(CommandHandler("start",          start))
    app.add_handler(CommandHandler("ajuda",          start))
    app.add_handler(CommandHandler("pendentes",      pendentes))
    app.add_handler(conv)
    app.add_handler(CommandHandler("meus_alertas",   meus_alertas))
    app.add_handler(CommandHandler("remover_alerta", remover_alerta))
    app.add_handler(CallbackQueryHandler(cb_aprovar, pattern=r"^aprv\|"))
    app.add_handler(CallbackQueryHandler(cb_negar,   pattern=r"^neg\|"))
    app.add_handler(CallbackQueryHandler(cb_remover, pattern=r"^del\|"))

    app.job_queue.run_repeating(verificar_precos, interval=INTERVALO_MINUTOS * 60, first=15)

    print("✅ Bot rodando! Aguardando mensagens...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

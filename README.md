# ✈️ Bot de Alertas de Passagens Aéreas

Bot para Telegram que monitora o Google Flights e envia notificações quando passagens aéreas ficam abaixo de um valor definido por você.

---

## 📋 Pré-requisitos

- Python 3.10 ou superior
- Conta no Telegram
- Conta na SerpAPI (plano gratuito disponível)

---

## 🚀 Configuração Passo a Passo

### 1. Criar o Bot no Telegram

1. Abra o Telegram e procure por **@BotFather**
2. Envie o comando `/newbot`
3. Escolha um nome para o bot (ex: `Alertas de Voos`)
4. Escolha um username (ex: `meus_voos_bot`)
5. Copie o **token** gerado (parece assim: `123456789:ABCdefGhIJKlmNoPQRstuVWXyz`)

### 2. Obter a Chave da SerpAPI

1. Acesse **https://serpapi.com** e crie uma conta gratuita
2. No painel, copie sua **API Key**
3. O plano gratuito oferece **100 buscas/mês** — suficiente para testes

> 💡 **Alternativa paga:** A SerpAPI tem planos pagos para uso intensivo.
> Para buscas ilimitadas, você pode assinar o plano deles.

### 3. Instalar as Dependências

```bash
# Clone ou baixe os arquivos
cd flight_alert_bot

# Instale as dependências
pip install -r requirements.txt
```

### 4. Configurar as Variáveis de Ambiente

```bash
# Copie o arquivo de exemplo
cp .env.example .env

# Edite o arquivo .env com seu editor favorito
nano .env
```

Preencha com seus dados:
```
TELEGRAM_BOT_TOKEN=123456789:SeuTokenAqui
SERPAPI_KEY=SuaChaveAqui
```

### 5. Executar o Bot

```bash
python flight_bot.py
```

---

## 🤖 Como Usar o Bot

Após iniciar o bot, abra o Telegram e busque pelo nome do seu bot.

| Comando | Descrição |
|---|---|
| `/start` | Exibe a mensagem de boas-vindas |
| `/novo_alerta` | Cria um novo alerta de preço |
| `/meus_alertas` | Lista seus alertas ativos |
| `/remover_alerta` | Remove um alerta |
| `/cancelar` | Cancela a operação atual |

### Exemplo de uso:

1. `/novo_alerta`
2. Selecione sua cidade de origem (ex: São Paulo - GRU)
3. Digite o preço máximo (ex: `500`)
4. Escolha a data ou período
5. Escolha tipo: **Só Ida** ou **Ida e Volta**
6. ✅ Pronto! O bot vai monitorar e te avisar quando achar uma oferta.

---

## ⚙️ Personalização

No arquivo `flight_bot.py`, você pode ajustar:

```python
# Altere o intervalo de verificação (em minutos)
INTERVALO_VERIFICACAO_MINUTOS = 30  # Padrão: 30 minutos
```

---

## 🏗️ Arquitetura do Projeto

```
flight_alert_bot/
├── flight_bot.py      # Código principal do bot
├── requirements.txt   # Dependências Python
├── .env.example       # Template de configuração
├── .env               # Suas configurações (não commitar!)
├── alertas.json       # Banco de dados local dos alertas (gerado automaticamente)
└── flight_bot.log     # Logs de execução (gerado automaticamente)
```

---

## 🔧 Executar em Produção (Linux/VPS)

Para rodar continuamente em um servidor, use o `systemd` ou `screen`:

```bash
# Com screen (mais simples)
screen -S flightbot
python flight_bot.py
# Pressione Ctrl+A, depois D para desanexar

# Para reabrir depois:
screen -r flightbot
```

Ou crie um serviço systemd em `/etc/systemd/system/flightbot.service`:

```ini
[Unit]
Description=Flight Alert Bot
After=network.target

[Service]
User=seuusuario
WorkingDirectory=/caminho/para/flight_alert_bot
ExecStart=/usr/bin/python3 flight_bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## ❓ Problemas Comuns

**Bot não responde:**
- Verifique se o token está correto no `.env`
- Certifique-se que o bot está rodando

**Nenhuma passagem encontrada:**
- Verifique se sua chave SerpAPI está válida
- Confirme que você não atingiu o limite de buscas do plano gratuito

**Erro de importação:**
- Execute novamente: `pip install -r requirements.txt`

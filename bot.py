import os
import io
import re
import sqlite3
import datetime

import discord
from discord import app_commands
from discord.ext import commands


# =========================================================
# BANCO DE DADOS
# =========================================================

db = sqlite3.connect("honradinho.db")

cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS ticket_config (
    guild_id INTEGER PRIMARY KEY,
    staff_role_id INTEGER,
    logs_channel_id INTEGER,
    category_id INTEGER
)
""")

db.commit()


def criar_config_servidor(guild_id: int):
    cursor.execute(
        """
        INSERT OR IGNORE INTO ticket_config (guild_id)
        VALUES (?)
        """,
        (guild_id,)
    )
    db.commit()


def pegar_config(guild_id: int):
    criar_config_servidor(guild_id)

    cursor.execute(
        """
        SELECT staff_role_id, logs_channel_id, category_id
        FROM ticket_config
        WHERE guild_id = ?
        """,
        (guild_id,)
    )

    return cursor.fetchone()


def definir_staff(guild_id: int, role_id: int):
    criar_config_servidor(guild_id)

    cursor.execute(
        """
        UPDATE ticket_config
        SET staff_role_id = ?
        WHERE guild_id = ?
        """,
        (role_id, guild_id)
    )

    db.commit()


def definir_logs(guild_id: int, channel_id: int):
    criar_config_servidor(guild_id)

    cursor.execute(
        """
        UPDATE ticket_config
        SET logs_channel_id = ?
        WHERE guild_id = ?
        """,
        (channel_id, guild_id)
    )

    db.commit()


def definir_categoria(guild_id: int, category_id: int):
    criar_config_servidor(guild_id)

    cursor.execute(
        """
        UPDATE ticket_config
        SET category_id = ?
        WHERE guild_id = ?
        """,
        (category_id, guild_id)
    )

    db.commit()


# =========================================================
# INTENTS
# =========================================================

intents = discord.Intents.default()

intents.members = True
intents.message_content = True


# =========================================================
# BOT
# =========================================================

class HonraDinho(commands.Bot):

    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents
        )

    async def setup_hook(self):

        # Views persistentes
        self.add_view(TicketPanelView())
        self.add_view(TicketActionsView())

        # Adiciona grupo de configuração
        self.tree.add_command(ticket_config)

        comandos = await self.tree.sync()

        print(
            f"{len(comandos)} comandos sincronizados."
        )


bot = HonraDinho()


# =========================================================
# EVENTO ONLINE
# =========================================================

@bot.event
async def on_ready():

    print("=" * 45)
    print(f"BOT ONLINE: {bot.user}")
    print(f"ID: {bot.user.id}")
    print("=" * 45)

    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game(
            name="/ajuda | HonraDinho"
        )
    )


# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def nome_seguro(texto: str):

    texto = texto.lower()

    texto = re.sub(
        r"[^a-z0-9-]",
        "-",
        texto
    )

    texto = re.sub(
        r"-+",
        "-",
        texto
    )

    texto = texto.strip("-")

    return texto[:40]


def extrair_dado_topic(topic: str | None, chave: str):

    if not topic:
        return None

    for parte in topic.split("|"):

        parte = parte.strip()

        if parte.startswith(chave + ":"):

            return parte.split(
                ":",
                1
            )[1].strip()

    return None


def ticket_do_usuario(
    guild: discord.Guild,
    user_id: int
):

    for canal in guild.text_channels:

        valor = extrair_dado_topic(
            canal.topic,
            "ticket_user"
        )

        if valor == str(user_id):
            return canal

    return None


def usuario_e_staff_ticket(
    canal: discord.TextChannel
):

    usuario = extrair_dado_topic(
        canal.topic,
        "ticket_user"
    )

    staff = extrair_dado_topic(
        canal.topic,
        "staff"
    )

    categoria = extrair_dado_topic(
        canal.topic,
        "tipo"
    )

    try:
        usuario = int(usuario) if usuario else None
    except ValueError:
        usuario = None

    try:
        staff = int(staff) if staff else None
    except ValueError:
        staff = None

    return usuario, staff, categoria


def alterar_staff_topic(
    canal: discord.TextChannel,
    staff_id: int
):

    partes = []

    if canal.topic:

        for parte in canal.topic.split("|"):

            parte = parte.strip()

            if not parte.startswith("staff:"):
                partes.append(parte)

    partes.append(
        f"staff:{staff_id}"
    )

    return " | ".join(partes)


async def gerar_transcript(
    canal: discord.TextChannel
):

    linhas = []

    linhas.append(
        "HONRADINHO - TRANSCRIPT DE TICKET"
    )

    linhas.append(
        "=" * 50
    )

    linhas.append(
        f"Servidor: {canal.guild.name}"
    )

    linhas.append(
        f"Canal: #{canal.name}"
    )

    linhas.append(
        f"ID do canal: {canal.id}"
    )

    linhas.append(
        "=" * 50
    )

    linhas.append("")

    async for mensagem in canal.history(
        limit=None,
        oldest_first=True
    ):

        horario = mensagem.created_at.strftime(
            "%d/%m/%Y %H:%M:%S UTC"
        )

        autor = (
            f"{mensagem.author} "
            f"({mensagem.author.id})"
        )

        conteudo = mensagem.content or ""

        linhas.append(
            f"[{horario}] {autor}: {conteudo}"
        )

        for anexo in mensagem.attachments:

            linhas.append(
                f"    [ANEXO] {anexo.url}"
            )

        for embed in mensagem.embeds:

            if embed.title:

                linhas.append(
                    f"    [EMBED] {embed.title}"
                )

            if embed.description:

                linhas.append(
                    f"    {embed.description}"
                )

    texto = "\n".join(linhas)

    arquivo = io.BytesIO(
        texto.encode("utf-8")
    )

    arquivo.seek(0)

    return arquivo


async def enviar_log(
    guild: discord.Guild,
    embed: discord.Embed,
    arquivo=None,
    nome_arquivo=None
):

    config = pegar_config(
        guild.id
    )

    logs_id = config[1]

    if not logs_id:
        return

    canal = guild.get_channel(
        logs_id
    )

    if not isinstance(
        canal,
        discord.TextChannel
    ):
        return

    try:

        if arquivo:

            await canal.send(
                embed=embed,
                file=discord.File(
                    arquivo,
                    filename=nome_arquivo
                )
            )

        else:

            await canal.send(
                embed=embed
            )

    except discord.HTTPException:
        pass


# =========================================================
# CRIAR TICKET
# =========================================================

async def criar_ticket(
    interaction: discord.Interaction,
    tipo: str,
    emoji: str
):

    guild = interaction.guild

    if guild is None:

        await interaction.response.send_message(
            "❌ Este recurso funciona apenas em servidores.",
            ephemeral=True
        )
        return

    existente = ticket_do_usuario(
        guild,
        interaction.user.id
    )

    if existente:

        await interaction.response.send_message(
            (
                "⚠️ Você já possui um ticket aberto:\n"
                f"{existente.mention}"
            ),
            ephemeral=True
        )
        return

    config = pegar_config(
        guild.id
    )

    staff_id = config[0]
    categoria_id = config[2]

    if not staff_id:

        await interaction.response.send_message(
            (
                "❌ O sistema ainda não possui um cargo "
                "de Staff configurado."
            ),
            ephemeral=True
        )
        return

    staff_role = guild.get_role(
        staff_id
    )

    if not staff_role:

        await interaction.response.send_message(
            "❌ O cargo da Staff configurado não existe mais.",
            ephemeral=True
        )
        return

    categoria = None

    if categoria_id:

        canal_categoria = guild.get_channel(
            categoria_id
        )

        if isinstance(
            canal_categoria,
            discord.CategoryChannel
        ):
            categoria = canal_categoria

    if categoria is None:

        try:

            categoria = await guild.create_category(
                "TICKETS",
                reason="Categoria criada pelo HonraDinho"
            )

            definir_categoria(
                guild.id,
                categoria.id
            )

        except discord.Forbidden:

            await interaction.response.send_message(
                (
                    "❌ Não consegui criar a categoria. "
                    "Verifique minha permissão "
                    "**Gerenciar Canais**."
                ),
                ephemeral=True
            )
            return

    await interaction.response.defer(
        ephemeral=True
    )

    bot_member = guild.me

    overwrites = {

        guild.default_role:
            discord.PermissionOverwrite(
                view_channel=False
            ),

        interaction.user:
            discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            ),

        staff_role:
            discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )
    }

    if bot_member:

        overwrites[bot_member] = (
            discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True
            )
        )

    usuario = nome_seguro(
        interaction.user.name
    )

    if not usuario:

        usuario = str(
            interaction.user.id
        )

    tipo_nome = nome_seguro(
        tipo
    )

    nome = (
        f"{tipo_nome}-{usuario}"
    )

    topic = (
        f"ticket_user:{interaction.user.id} | "
        f"tipo:{tipo} | "
        f"staff:0"
    )

    try:

        canal = await guild.create_text_channel(
            name=nome,
            category=categoria,
            overwrites=overwrites,
            topic=topic,
            reason=(
                f"Ticket {tipo} aberto por "
                f"{interaction.user}"
            )
        )

    except discord.Forbidden:

        await interaction.followup.send(
            (
                "❌ Não tenho permissão para "
                "criar canais."
            ),
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title=f"{emoji} Ticket de {tipo}",
        description=(
            f"Olá {interaction.user.mention}!\n\n"
            "Seu ticket foi aberto com sucesso.\n"
            "Explique detalhadamente o motivo "
            "do atendimento.\n\n"
            f"{staff_role.mention}, um novo "
            "ticket está aguardando atendimento."
        ),
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow()
    )

    embed.add_field(
        name="👤 Usuário",
        value=interaction.user.mention,
        inline=True
    )

    embed.add_field(
        name="📂 Categoria",
        value=tipo,
        inline=True
    )

    embed.add_field(
        name="🛡️ Atendimento",
        value="Aguardando Staff",
        inline=False
    )

    embed.set_footer(
        text="HonraDinho • Tickets V2"
    )

    await canal.send(
        content=(
            f"{interaction.user.mention} "
            f"{staff_role.mention}"
        ),
        embed=embed,
        view=TicketActionsView(),
        allowed_mentions=discord.AllowedMentions(
            users=True,
            roles=True
        )
    )

    await interaction.followup.send(
        (
            "✅ Ticket criado com sucesso!\n"
            f"➡️ {canal.mention}"
        ),
        ephemeral=True
    )

    log = discord.Embed(
        title="🎫 Ticket aberto",
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow()
    )

    log.add_field(
        name="Usuário",
        value=(
            f"{interaction.user.mention}\n"
            f"`{interaction.user.id}`"
        )
    )

    log.add_field(
        name="Categoria",
        value=tipo
    )

    log.add_field(
        name="Canal",
        value=canal.mention
    )

    await enviar_log(
        guild,
        log
    )


# =========================================================
# SELECT DE CATEGORIA
# =========================================================

class TicketSelect(discord.ui.Select):

    def __init__(self):

        options = [

            discord.SelectOption(
                label="Suporte",
                description="Precisa de ajuda da equipe?",
                emoji="🆘",
                value="Suporte"
            ),

            discord.SelectOption(
                label="Denúncia",
                description="Denuncie membros ou problemas.",
                emoji="🚨",
                value="Denúncia"
            ),

            discord.SelectOption(
                label="Compra",
                description="Assuntos relacionados a compras.",
                emoji="🛒",
                value="Compra"
            ),

            discord.SelectOption(
                label="Parceria",
                description="Propostas e parcerias.",
                emoji="🤝",
                value="Parceria"
            )
        ]

        super().__init__(
            placeholder="Selecione o motivo do ticket...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="honradinho:ticket_select"
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        tipo = self.values[0]

        emojis = {
            "Suporte": "🆘",
            "Denúncia": "🚨",
            "Compra": "🛒",
            "Parceria": "🤝"
        }

        await criar_ticket(
            interaction,
            tipo,
            emojis.get(
                tipo,
                "🎫"
            )
        )


# =========================================================
# PAINEL PERSISTENTE
# =========================================================

class TicketPanelView(discord.ui.View):

    def __init__(self):

        super().__init__(
            timeout=None
        )

        self.add_item(
            TicketSelect()
        )


# =========================================================
# BOTÕES DO TICKET
# =========================================================

class TicketActionsView(discord.ui.View):

    def __init__(self):

        super().__init__(
            timeout=None
        )

    # -----------------------------------------------------
    # ASSUMIR
    # -----------------------------------------------------

    @discord.ui.button(
        label="Assumir",
        emoji="🙋",
        style=discord.ButtonStyle.success,
        custom_id="honradinho:ticket_claim"
    )
    async def assumir(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not interaction.guild:

            await interaction.response.send_message(
                "❌ Este botão só funciona em servidores.",
                ephemeral=True
            )
            return

        canal = interaction.channel

        if not isinstance(
            canal,
            discord.TextChannel
        ):

            return

        usuario_id, staff_atual, tipo = (
            usuario_e_staff_ticket(
                canal
            )
        )

        if not usuario_id:

            await interaction.response.send_message(
                "❌ Este canal não é um ticket válido.",
                ephemeral=True
            )
            return

        config = pegar_config(
            interaction.guild.id
        )

        staff_role_id = config[0]

        staff_role = (
            interaction.guild.get_role(
                staff_role_id
            )
            if staff_role_id
            else None
        )

        membro = interaction.user

        autorizado = (
            membro.guild_permissions.manage_channels
        )

        if (
            staff_role
            and staff_role in membro.roles
        ):
            autorizado = True

        if not autorizado:

            await interaction.response.send_message(
                (
                    "❌ Apenas membros da Staff "
                    "podem assumir tickets."
                ),
                ephemeral=True
            )
            return

        if staff_atual and staff_atual != 0:

            membro_atual = (
                interaction.guild.get_member(
                    staff_atual
                )
            )

            nome = (
                membro_atual.mention
                if membro_atual
                else f"`{staff_atual}`"
            )

            await interaction.response.send_message(
                (
                    "⚠️ Este ticket já foi "
                    f"assumido por {nome}."
                ),
                ephemeral=True
            )
            return

        novo_topic = alterar_staff_topic(
            canal,
            interaction.user.id
        )

        await canal.edit(
            topic=novo_topic,
            reason="Ticket assumido"
        )

        embed = discord.Embed(
            description=(
                f"🙋 **Ticket assumido por "
                f"{interaction.user.mention}**"
            ),
            color=discord.Color.green()
        )

        await interaction.response.send_message(
            embed=embed
        )

        log = discord.Embed(
            title="🙋 Ticket assumido",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )

        log.add_field(
            name="Staff",
            value=interaction.user.mention
        )

        log.add_field(
            name="Ticket",
            value=canal.mention
        )

        await enviar_log(
            interaction.guild,
            log
        )

    # -----------------------------------------------------
    # TRANSCRIPT
    # -----------------------------------------------------

    @discord.ui.button(
        label="Transcript",
        emoji="📄",
        style=discord.ButtonStyle.secondary,
        custom_id="honradinho:ticket_transcript"
    )
    async def transcript(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        canal = interaction.channel

        if not isinstance(
            canal,
            discord.TextChannel
        ):

            return

        usuario_id = extrair_dado_topic(
            canal.topic,
            "ticket_user"
        )

        if not usuario_id:

            await interaction.response.send_message(
                "❌ Este canal não é um ticket.",
                ephemeral=True
            )
            return

        await interaction.response.defer(
            ephemeral=True
        )

        arquivo = await gerar_transcript(
            canal
        )

        await interaction.followup.send(
            "📄 Transcript gerado:",
            file=discord.File(
                arquivo,
                filename=f"{canal.name}.txt"
            ),
            ephemeral=True
        )

    # -----------------------------------------------------
    # FECHAR
    # -----------------------------------------------------

    @discord.ui.button(
        label="Fechar",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="honradinho:ticket_close"
    )
    async def fechar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        guild = interaction.guild

        canal = interaction.channel

        if (
            guild is None
            or not isinstance(
                canal,
                discord.TextChannel
            )
        ):
            return

        usuario_id, staff_id, tipo = (
            usuario_e_staff_ticket(
                canal
            )
        )

        if not usuario_id:

            await interaction.response.send_message(
                "❌ Este canal não é um ticket.",
                ephemeral=True
            )
            return

        config = pegar_config(
            guild.id
        )

        staff_role = (
            guild.get_role(
                config[0]
            )
            if config[0]
            else None
        )

        pode_fechar = False

        if interaction.user.id == usuario_id:
            pode_fechar = True

        if (
            staff_role
            and staff_role in interaction.user.roles
        ):
            pode_fechar = True

        if interaction.user.guild_permissions.manage_channels:
            pode_fechar = True

        if not pode_fechar:

            await interaction.response.send_message(
                (
                    "❌ Você não possui permissão "
                    "para fechar este ticket."
                ),
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "🔒 Salvando transcript e fechando ticket..."
        )

        arquivo = await gerar_transcript(
            canal
        )

        # Precisamos copiar os bytes antes
        # de enviar em locais diferentes.
        dados = arquivo.getvalue()

        transcript_logs = io.BytesIO(
            dados
        )

        usuario = guild.get_member(
            usuario_id
        )

        staff = (
            guild.get_member(
                staff_id
            )
            if staff_id
            else None
        )

        log = discord.Embed(
            title="🔒 Ticket fechado",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )

        log.add_field(
            name="👤 Usuário",
            value=(
                usuario.mention
                if usuario
                else f"`{usuario_id}`"
            ),
            inline=True
        )

        log.add_field(
            name="📂 Categoria",
            value=tipo or "Desconhecida",
            inline=True
        )

        log.add_field(
            name="🙋 Atendido por",
            value=(
                staff.mention
                if staff
                else "Não assumido"
            ),
            inline=True
        )

        log.add_field(
            name="🔒 Fechado por",
            value=interaction.user.mention,
            inline=False
        )

        await enviar_log(
            guild,
            log,
            arquivo=transcript_logs,
            nome_arquivo=f"{canal.name}.txt"
        )

        # Tenta enviar transcript por DM
        if usuario:

            try:

                transcript_dm = io.BytesIO(
                    dados
                )

                dm_embed = discord.Embed(
                    title="🎫 Seu ticket foi fechado",
                    description=(
                        f"Servidor: **{guild.name}**\n"
                        f"Categoria: **{tipo}**\n\n"
                        "O transcript do atendimento "
                        "está anexado."
                    ),
                    color=discord.Color.blurple()
                )

                await usuario.send(
                    embed=dm_embed,
                    file=discord.File(
                        transcript_dm,
                        filename=f"{canal.name}.txt"
                    )
                )

            except (
                discord.Forbidden,
                discord.HTTPException
            ):
                pass

        await discord.utils.sleep_until(
            discord.utils.utcnow()
            + datetime.timedelta(
                seconds=3
            )
        )

        try:

            await canal.delete(
                reason=(
                    f"Ticket fechado por "
                    f"{interaction.user}"
                )
            )

        except discord.Forbidden:

            pass


# =========================================================
# /TICKET
# =========================================================

@bot.tree.command(
    name="ticket",
    description="Envia o painel de tickets."
)
@app_commands.checks.has_permissions(
    manage_channels=True
)
async def ticket(
    interaction: discord.Interaction
):

    if not interaction.guild:

        await interaction.response.send_message(
            "❌ Este comando só funciona em servidores.",
            ephemeral=True
        )
        return

    config = pegar_config(
        interaction.guild.id
    )

    if not config[0]:

        await interaction.response.send_message(
            (
                "❌ Configure primeiro o cargo "
                "da Staff usando:\n"
                "`/ticket-config staff`"
            ),
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="🎫 Central de Atendimento",
        description=(
            "Bem-vindo à central de atendimento "
            "do **HonraDinho**.\n\n"
            "Selecione abaixo o motivo do seu ticket."
        ),
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="🆘 Suporte",
        value="Ajuda e dúvidas.",
        inline=True
    )

    embed.add_field(
        name="🚨 Denúncia",
        value="Denúncias e problemas.",
        inline=True
    )

    embed.add_field(
        name="🛒 Compra",
        value="Assuntos comerciais.",
        inline=True
    )

    embed.add_field(
        name="🤝 Parceria",
        value="Parcerias e propostas.",
        inline=True
    )

    embed.set_footer(
        text="HonraDinho • Tickets V2"
    )

    await interaction.response.send_message(
        embed=embed,
        view=TicketPanelView()
    )


# =========================================================
# /TICKET-CONFIG
# =========================================================

ticket_config = app_commands.Group(
    name="ticket-config",
    description="Configura o sistema de tickets."
)


@ticket_config.command(
    name="staff",
    description="Define o cargo da equipe de atendimento."
)
@app_commands.describe(
    cargo="Cargo responsável pelos tickets."
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def ticket_config_staff(
    interaction: discord.Interaction,
    cargo: discord.Role
):

    if not interaction.guild:
        return

    definir_staff(
        interaction.guild.id,
        cargo.id
    )

    await interaction.response.send_message(
        (
            "✅ Cargo da Staff configurado:\n"
            f"{cargo.mention}"
        ),
        ephemeral=True
    )


@ticket_config.command(
    name="logs",
    description="Define o canal de logs dos tickets."
)
@app_commands.describe(
    canal="Canal que receberá os logs."
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def ticket_config_logs(
    interaction: discord.Interaction,
    canal: discord.TextChannel
):

    if not interaction.guild:
        return

    definir_logs(
        interaction.guild.id,
        canal.id
    )

    await interaction.response.send_message(
        (
            "✅ Canal de logs configurado:\n"
            f"{canal.mention}"
        ),
        ephemeral=True
    )


@ticket_config.command(
    name="categoria",
    description="Define a categoria onde os tickets serão criados."
)
@app_commands.describe(
    categoria="Categoria destinada aos tickets."
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def ticket_config_categoria(
    interaction: discord.Interaction,
    categoria: discord.CategoryChannel
):

    if not interaction.guild:
        return

    definir_categoria(
        interaction.guild.id,
        categoria.id
    )

    await interaction.response.send_message(
        (
            "✅ Categoria dos tickets configurada:\n"
            f"**{categoria.name}**"
        ),
        ephemeral=True
    )


# =========================================================
# /PING
# =========================================================

@bot.tree.command(
    name="ping",
    description="Mostra a latência do HonraDinho."
)
async def ping(
    interaction: discord.Interaction
):

    latencia = round(
        bot.latency * 1000
    )

    embed = discord.Embed(
        title="🏓 Pong!",
        description=(
            f"Latência: **{latencia}ms**"
        ),
        color=discord.Color.blurple()
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# /AJUDA
# =========================================================

@bot.tree.command(
    name="ajuda",
    description="Mostra os comandos disponíveis."
)
async def ajuda(
    interaction: discord.Interaction
):

    embed = discord.Embed(
        title="🤖 HonraDinho — Ajuda",
        description=(
            "Veja os comandos disponíveis abaixo."
        ),
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="📊 Informações",
        value=(
            "`/ping`\n"
            "`/server`\n"
            "`/userinfo`\n"
            "`/avatar`"
        ),
        inline=True
    )

    embed.add_field(
        name="🛡️ Moderação",
        value=(
            "`/clear`\n"
            "`/kick`\n"
            "`/ban`"
        ),
        inline=True
    )

    embed.add_field(
        name="🎫 Tickets",
        value=(
            "`/ticket`\n"
            "`/ticket-config staff`\n"
            "`/ticket-config logs`\n"
            "`/ticket-config categoria`"
        ),
        inline=False
    )

    embed.set_footer(
        text="HonraDinho • Seu servidor, suas regras."
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# /SERVER
# =========================================================

@bot.tree.command(
    name="server",
    description="Mostra informações do servidor."
)
async def server(
    interaction: discord.Interaction
):

    guild = interaction.guild

    if guild is None:

        await interaction.response.send_message(
            "❌ Use este comando em um servidor.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title=f"📊 {guild.name}",
        color=discord.Color.blurple()
    )

    if guild.icon:

        embed.set_thumbnail(
            url=guild.icon.url
        )

    embed.add_field(
        name="👑 Dono",
        value=(
            guild.owner.mention
            if guild.owner
            else "Desconhecido"
        )
    )

    embed.add_field(
        name="👥 Membros",
        value=str(guild.member_count)
    )

    embed.add_field(
        name="💬 Canais",
        value=str(len(guild.channels))
    )

    embed.add_field(
        name="🎭 Cargos",
        value=str(len(guild.roles))
    )

    embed.add_field(
        name="🆔 ID",
        value=str(guild.id)
    )

    embed.add_field(
        name="📅 Criado",
        value=discord.utils.format_dt(
            guild.created_at,
            style="D"
        )
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# /USERINFO
# =========================================================

@bot.tree.command(
    name="userinfo",
    description="Mostra informações de um membro."
)
@app_commands.describe(
    membro="Membro que deseja consultar."
)
async def userinfo(
    interaction: discord.Interaction,
    membro: discord.Member | None = None
):

    membro = membro or interaction.user

    embed = discord.Embed(
        title=f"👤 {membro}",
        color=discord.Color.blurple()
    )

    embed.set_thumbnail(
        url=membro.display_avatar.url
    )

    embed.add_field(
        name="Nome",
        value=membro.name
    )

    embed.add_field(
        name="ID",
        value=str(membro.id)
    )

    embed.add_field(
        name="Conta criada",
        value=discord.utils.format_dt(
            membro.created_at,
            style="D"
        ),
        inline=False
    )

    if membro.joined_at:

        embed.add_field(
            name="Entrou no servidor",
            value=discord.utils.format_dt(
                membro.joined_at,
                style="D"
            ),
            inline=False
        )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# /AVATAR
# =========================================================

@bot.tree.command(
    name="avatar",
    description="Mostra o avatar de um usuário."
)
@app_commands.describe(
    membro="Usuário que deseja consultar."
)
async def avatar(
    interaction: discord.Interaction,
    membro: discord.Member | None = None
):

    membro = membro or interaction.user

    embed = discord.Embed(
        title=(
            f"🖼️ Avatar de "
            f"{membro.display_name}"
        ),
        color=discord.Color.blurple()
    )

    embed.set_image(
        url=membro.display_avatar.url
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# /CLEAR
# =========================================================

@bot.tree.command(
    name="clear",
    description="Apaga mensagens do canal."
)
@app_commands.describe(
    quantidade="Quantidade entre 1 e 100."
)
@app_commands.checks.has_permissions(
    manage_messages=True
)
async def clear(
    interaction: discord.Interaction,
    quantidade: app_commands.Range[int, 1, 100]
):

    canal = interaction.channel

    if not isinstance(
        canal,
        (
            discord.TextChannel,
            discord.Thread
        )
    ):

        await interaction.response.send_message(
            "❌ Este comando não funciona aqui.",
            ephemeral=True
        )
        return

    await interaction.response.defer(
        ephemeral=True
    )

    mensagens = await canal.purge(
        limit=quantidade
    )

    await interaction.followup.send(
        (
            f"🧹 **{len(mensagens)} mensagens** "
            "apagadas."
        ),
        ephemeral=True
    )


# =========================================================
# /KICK
# =========================================================

@bot.tree.command(
    name="kick",
    description="Expulsa um membro."
)
@app_commands.describe(
    membro="Membro que será expulso.",
    motivo="Motivo."
)
@app_commands.checks.has_permissions(
    kick_members=True
)
async def kick(
    interaction: discord.Interaction,
    membro: discord.Member,
    motivo: str = "Não informado."
):

    if interaction.guild is None:
        return

    if membro == interaction.user:

        await interaction.response.send_message(
            "❌ Você não pode expulsar a si mesmo.",
            ephemeral=True
        )
        return

    if membro == interaction.guild.owner:

        await interaction.response.send_message(
            "❌ O dono não pode ser expulso.",
            ephemeral=True
        )
        return

    try:

        await membro.kick(
            reason=motivo
        )

        embed = discord.Embed(
            title="👢 Membro expulso",
            color=discord.Color.orange()
        )

        embed.add_field(
            name="Usuário",
            value=str(membro)
        )

        embed.add_field(
            name="Moderador",
            value=interaction.user.mention
        )

        embed.add_field(
            name="Motivo",
            value=motivo,
            inline=False
        )

        await interaction.response.send_message(
            embed=embed
        )

    except discord.Forbidden:

        await interaction.response.send_message(
            "❌ Não tenho permissão para expulsá-lo.",
            ephemeral=True
        )


# =========================================================
# /BAN
# =========================================================

@bot.tree.command(
    name="ban",
    description="Bane um membro."
)
@app_commands.describe(
    membro="Membro que será banido.",
    motivo="Motivo."
)
@app_commands.checks.has_permissions(
    ban_members=True
)
async def ban(
    interaction: discord.Interaction,
    membro: discord.Member,
    motivo: str = "Não informado."
):

    if interaction.guild is None:
        return

    if membro == interaction.user:

        await interaction.response.send_message(
            "❌ Você não pode banir a si mesmo.",
            ephemeral=True
        )
        return

    if membro == interaction.guild.owner:

        await interaction.response.send_message(
            "❌ O dono não pode ser banido.",
            ephemeral=True
        )
        return

    try:

        await membro.ban(
            reason=motivo
        )

        embed = discord.Embed(
            title="🔨 Membro banido",
            color=discord.Color.red()
        )

        embed.add_field(
            name="Usuário",
            value=str(membro)
        )

        embed.add_field(
            name="Moderador",
            value=interaction.user.mention
        )

        embed.add_field(
            name="Motivo",
            value=motivo,
            inline=False
        )

        await interaction.response.send_message(
            embed=embed
        )

    except discord.Forbidden:

        await interaction.response.send_message(
            "❌ Não tenho permissão para bani-lo.",
            ephemeral=True
        )


# =========================================================
# ERRO GLOBAL DE COMANDOS
# =========================================================

@bot.tree.error
async def erro_comando(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):

    if isinstance(
        error,
        app_commands.MissingPermissions
    ):

        mensagem = (
            "❌ Você não possui as permissões "
            "necessárias para usar este comando."
        )

    else:

        print(
            f"Erro em comando: {error}"
        )

        mensagem = (
            "❌ Ocorreu um erro ao executar "
            "este comando."
        )

    try:

        if interaction.response.is_done():

            await interaction.followup.send(
                mensagem,
                ephemeral=True
            )

        else:

            await interaction.response.send_message(
                mensagem,
                ephemeral=True
            )

    except discord.HTTPException:
        pass


# =========================================================
# TOKEN
# =========================================================

TOKEN = os.getenv(
    "DISCORD_TOKEN"
)

if not TOKEN:

    raise RuntimeError(
        "A variável DISCORD_TOKEN não foi configurada."
    )


bot.run(
    TOKEN
)

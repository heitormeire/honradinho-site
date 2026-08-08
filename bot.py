import os
import re
import discord
from discord import app_commands
from discord.ext import commands


# =========================================================
# CONFIGURAÇÃO
# =========================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True


class HonraDinho(commands.Bot):

    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents
        )

    async def setup_hook(self):

        # Mantém os botões funcionando
        # mesmo depois de reiniciar o bot.
        self.add_view(TicketView())
        self.add_view(FecharTicketView())

        comandos = await self.tree.sync()

        print(
            f"{len(comandos)} comandos sincronizados com o Discord."
        )


bot = HonraDinho()


# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def nome_seguro(texto: str) -> str:

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

    return texto.strip("-")


def encontrar_ticket_usuario(
    guild: discord.Guild,
    usuario_id: int
):

    marcador = f"ticket_user:{usuario_id}"

    for canal in guild.text_channels:

        if canal.topic and marcador in canal.topic:
            return canal

    return None


async def encontrar_ou_criar_categoria(
    guild: discord.Guild
):

    categoria = discord.utils.get(
        guild.categories,
        name="TICKETS"
    )

    if categoria:
        return categoria

    try:

        categoria = await guild.create_category(
            "TICKETS",
            reason="Sistema de tickets do HonraDinho"
        )

        return categoria

    except discord.Forbidden:

        return None


# =========================================================
# BOT ONLINE
# =========================================================

@bot.event
async def on_ready():

    print("===================================")
    print(f"BOT ONLINE: {bot.user}")
    print(f"ID: {bot.user.id}")
    print("===================================")

    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game(
            name="/ajuda | HonraDinho"
        )
    )


# =========================================================
# SISTEMA DE TICKETS
# =========================================================

class FecharTicketView(discord.ui.View):

    def __init__(self):
        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="Fechar Ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="honradinho:fechar_ticket"
    )
    async def fechar_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not interaction.guild:

            await interaction.response.send_message(
                "❌ Este botão só funciona dentro de um servidor.",
                ephemeral=True
            )

            return

        canal = interaction.channel

        if not isinstance(
            canal,
            discord.TextChannel
        ):

            await interaction.response.send_message(
                "❌ Este não é um canal de ticket.",
                ephemeral=True
            )

            return

        if not canal.topic or "ticket_user:" not in canal.topic:

            await interaction.response.send_message(
                "❌ Este canal não foi identificado como um ticket.",
                ephemeral=True
            )

            return

        usuario_id = None

        try:

            parte = canal.topic.split(
                "ticket_user:"
            )[1]

            usuario_id = int(
                parte.split()[0]
            )

        except (IndexError, ValueError):

            pass

        pode_fechar = False

        if interaction.user.guild_permissions.manage_channels:

            pode_fechar = True

        if usuario_id == interaction.user.id:

            pode_fechar = True

        if not pode_fechar:

            await interaction.response.send_message(
                "❌ Apenas o dono do ticket ou um moderador pode fechá-lo.",
                ephemeral=True
            )

            return

        await interaction.response.send_message(
            "🔒 Fechando ticket...",
            ephemeral=True
        )

        try:

            await canal.delete(
                reason=(
                    f"Ticket fechado por "
                    f"{interaction.user}"
                )
            )

        except discord.Forbidden:

            try:

                await interaction.followup.send(
                    "❌ Não tenho permissão para excluir este canal.",
                    ephemeral=True
                )

            except discord.HTTPException:

                pass


class TicketView(discord.ui.View):

    def __init__(self):
        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="Abrir Ticket",
        emoji="🎫",
        style=discord.ButtonStyle.primary,
        custom_id="honradinho:abrir_ticket"
    )
    async def abrir_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        guild = interaction.guild

        if guild is None:

            await interaction.response.send_message(
                "❌ Tickets só podem ser abertos dentro de servidores.",
                ephemeral=True
            )

            return

        ticket_existente = encontrar_ticket_usuario(
            guild,
            interaction.user.id
        )

        if ticket_existente:

            await interaction.response.send_message(
                (
                    "⚠️ Você já possui um ticket aberto:\n"
                    f"{ticket_existente.mention}"
                ),
                ephemeral=True
            )

            return

        await interaction.response.defer(
            ephemeral=True
        )

        categoria = await encontrar_ou_criar_categoria(
            guild
        )

        if categoria is None:

            await interaction.followup.send(
                (
                    "❌ Não consegui criar a categoria de tickets.\n"
                    "Verifique se o bot possui a permissão "
                    "**Gerenciar Canais**."
                ),
                ephemeral=True
            )

            return

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
                )
        }

        if bot_member:

            overwrites[bot_member] = (
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                    manage_messages=True,
                    read_message_history=True
                )
            )

        nome_usuario = nome_seguro(
            interaction.user.name
        )

        if not nome_usuario:
            nome_usuario = str(
                interaction.user.id
            )

        nome_canal = (
            f"ticket-{nome_usuario}"
        )

        try:

            canal = await guild.create_text_channel(
                name=nome_canal,
                category=categoria,
                overwrites=overwrites,
                topic=(
                    f"ticket_user:{interaction.user.id} "
                    f"| Ticket criado pelo HonraDinho"
                ),
                reason=(
                    f"Ticket aberto por "
                    f"{interaction.user}"
                )
            )

        except discord.Forbidden:

            await interaction.followup.send(
                (
                    "❌ Não tenho permissão para criar "
                    "o canal do ticket."
                ),
                ephemeral=True
            )

            return

        embed = discord.Embed(
            title="🎫 Ticket aberto",
            description=(
                f"Olá {interaction.user.mention}!\n\n"
                "Seu atendimento foi iniciado.\n"
                "Explique abaixo o motivo do contato "
                "e aguarde a equipe responsável.\n\n"
                "Quando o atendimento terminar, "
                "use o botão **Fechar Ticket**."
            ),
            color=discord.Color.blurple()
        )

        embed.add_field(
            name="👤 Criado por",
            value=interaction.user.mention,
            inline=True
        )

        embed.add_field(
            name="🆔 Usuário",
            value=str(interaction.user.id),
            inline=True
        )

        embed.set_footer(
            text="HonraDinho • Sistema de Tickets"
        )

        await canal.send(
            content=interaction.user.mention,
            embed=embed,
            view=FecharTicketView()
        )

        await interaction.followup.send(
            (
                "✅ Seu ticket foi criado com sucesso!\n"
                f"🎫 {canal.mention}"
            ),
            ephemeral=True
        )


# =========================================================
# /TICKET
# =========================================================

@bot.tree.command(
    name="ticket",
    description="Envia o painel para abertura de tickets."
)
@app_commands.checks.has_permissions(
    manage_channels=True
)
async def ticket(
    interaction: discord.Interaction
):

    if interaction.guild is None:

        await interaction.response.send_message(
            "❌ Este comando só funciona dentro de servidores.",
            ephemeral=True
        )

        return

    embed = discord.Embed(
        title="🎫 Central de Atendimento",
        description=(
            "Precisa falar com nossa equipe?\n\n"
            "Clique no botão abaixo para criar "
            "um canal privado de atendimento."
        ),
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="🔐 Privacidade",
        value=(
            "Seu ticket será visível somente "
            "para você e para a equipe autorizada."
        ),
        inline=False
    )

    embed.add_field(
        name="⚠️ Atenção",
        value=(
            "Evite abrir vários tickets para "
            "o mesmo assunto."
        ),
        inline=False
    )

    embed.set_footer(
        text="HonraDinho • Sistema de Tickets"
    )

    await interaction.response.send_message(
        embed=embed,
        view=TicketView()
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
            f"Minha latência é **{latencia}ms**."
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
    description="Mostra os comandos do HonraDinho."
)
async def ajuda(
    interaction: discord.Interaction
):

    embed = discord.Embed(
        title="🤖 HonraDinho — Central de Ajuda",
        description=(
            "Veja abaixo os comandos disponíveis."
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
        value="`/ticket`",
        inline=True
    )

    embed.set_footer(
        text="HonraDinho • Seu servidor, do seu jeito."
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# /SERVER
# =========================================================

@bot.tree.command(
    name="server",
    description="Mostra informações sobre o servidor."
)
async def server(
    interaction: discord.Interaction
):

    guild = interaction.guild

    if guild is None:

        await interaction.response.send_message(
            "❌ Este comando só funciona dentro de servidores.",
            ephemeral=True
        )

        return

    dono = guild.owner

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
            dono.mention
            if dono
            else "Desconhecido"
        ),
        inline=True
    )

    embed.add_field(
        name="👥 Membros",
        value=str(
            guild.member_count
        ),
        inline=True
    )

    embed.add_field(
        name="💬 Canais",
        value=str(
            len(guild.channels)
        ),
        inline=True
    )

    embed.add_field(
        name="🎭 Cargos",
        value=str(
            len(guild.roles)
        ),
        inline=True
    )

    embed.add_field(
        name="🆔 ID",
        value=str(
            guild.id
        ),
        inline=True
    )

    embed.add_field(
        name="📅 Criado em",
        value=discord.utils.format_dt(
            guild.created_at,
            style="D"
        ),
        inline=True
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# /USERINFO
# =========================================================

@bot.tree.command(
    name="userinfo",
    description="Mostra informações sobre um membro."
)
@app_commands.describe(
    membro="Escolha o membro."
)
async def userinfo(
    interaction: discord.Interaction,
    membro: discord.Member | None = None
):

    membro = (
        membro
        or interaction.user
    )

    embed = discord.Embed(
        title=f"👤 {membro}",
        color=discord.Color.blurple()
    )

    embed.set_thumbnail(
        url=membro.display_avatar.url
    )

    embed.add_field(
        name="Nome",
        value=membro.name,
        inline=True
    )

    embed.add_field(
        name="ID",
        value=str(
            membro.id
        ),
        inline=True
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
    membro="Escolha o usuário."
)
async def avatar(
    interaction: discord.Interaction,
    membro: discord.Member | None = None
):

    membro = (
        membro
        or interaction.user
    )

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
    quantidade="Quantidade de mensagens para apagar."
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
            "❌ Este comando não pode ser usado aqui.",
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
            "foram apagadas."
        ),
        ephemeral=True
    )


# =========================================================
# /KICK
# =========================================================

@bot.tree.command(
    name="kick",
    description="Expulsa um membro do servidor."
)
@app_commands.describe(
    membro="Membro que será expulso.",
    motivo="Motivo da expulsão."
)
@app_commands.checks.has_permissions(
    kick_members=True
)
async def kick(
    interaction: discord.Interaction,
    membro: discord.Member,
    motivo: str = "Nenhum motivo informado."
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
            "❌ O dono do servidor não pode ser expulso.",
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
            value=str(membro),
            inline=False
        )

        embed.add_field(
            name="Moderador",
            value=interaction.user.mention,
            inline=False
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
            "❌ Não tenho permissão para expulsar esse membro.",
            ephemeral=True
        )


# =========================================================
# /BAN
# =========================================================

@bot.tree.command(
    name="ban",
    description="Bane um membro do servidor."
)
@app_commands.describe(
    membro="Membro que será banido.",
    motivo="Motivo do banimento."
)
@app_commands.checks.has_permissions(
    ban_members=True
)
async def ban(
    interaction: discord.Interaction,
    membro: discord.Member,
    motivo: str = "Nenhum motivo informado."
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
            "❌ O dono do servidor não pode ser banido.",
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
            value=str(membro),
            inline=False
        )

        embed.add_field(
            name="Moderador",
            value=interaction.user.mention,
            inline=False
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
            "❌ Não tenho permissão para banir esse membro.",
            ephemeral=True
        )


# =========================================================
# ERROS DE PERMISSÃO
# =========================================================

async def enviar_erro(
    interaction: discord.Interaction,
    error
):

    if isinstance(
        error,
        app_commands.MissingPermissions
    ):

        mensagem = (
            "❌ Você não possui permissão "
            "para usar este comando."
        )

    else:

        mensagem = (
            "❌ Ocorreu um erro ao executar o comando."
        )

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


@clear.error
async def clear_error(
    interaction: discord.Interaction,
    error
):
    await enviar_erro(
        interaction,
        error
    )


@kick.error
async def kick_error(
    interaction: discord.Interaction,
    error
):
    await enviar_erro(
        interaction,
        error
    )


@ban.error
async def ban_error(
    interaction: discord.Interaction,
    error
):
    await enviar_erro(
        interaction,
        error
    )


@ticket.error
async def ticket_error(
    interaction: discord.Interaction,
    error
):
    await enviar_erro(
        interaction,
        error
    )


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

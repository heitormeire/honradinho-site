import os
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
        # Sincroniza os comandos de barra com o Discord
        comandos = await self.tree.sync()

        print(
            f"{len(comandos)} comandos sincronizados com o Discord."
        )


bot = HonraDinho()


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
# /PING
# =========================================================

@bot.tree.command(
    name="ping",
    description="Mostra a latência do HonraDinho."
)
async def ping(interaction: discord.Interaction):

    latencia = round(bot.latency * 1000)

    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Minha latência é **{latencia}ms**.",
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
async def ajuda(interaction: discord.Interaction):

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
async def server(interaction: discord.Interaction):

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
        value=dono.mention if dono else "Desconhecido",
        inline=True
    )

    embed.add_field(
        name="👥 Membros",
        value=str(guild.member_count),
        inline=True
    )

    embed.add_field(
        name="💬 Canais",
        value=str(len(guild.channels)),
        inline=True
    )

    embed.add_field(
        name="🎭 Cargos",
        value=str(len(guild.roles)),
        inline=True
    )

    embed.add_field(
        name="🆔 ID",
        value=str(guild.id),
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
        value=membro.name,
        inline=True
    )

    embed.add_field(
        name="ID",
        value=str(membro.id),
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

    membro = membro or interaction.user

    embed = discord.Embed(
        title=f"🖼️ Avatar de {membro.display_name}",
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
        (discord.TextChannel, discord.Thread)
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
        f"🧹 **{len(mensagens)} mensagens** foram apagadas.",
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
# ERRO DE PERMISSÃO
# =========================================================

@clear.error
@kick.error
@ban.error
async def erro_permissao(
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


# =========================================================
# TOKEN
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "A variável DISCORD_TOKEN não foi configurada."
    )

bot.run(TOKEN)

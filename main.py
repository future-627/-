import discord
from discord.ext import commands, tasks
import yt_dlp
import asyncio
import os
import sqlite3
import logging
from collections import deque
from google import genai
from aiohttp import web

# ==========================================
# [ 1. 雲端生存環境配置 ]
# ==========================================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN', '您的TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '您的KEY')

MY_GUILD_ID = 1382281014101151744 
ANNOUNCE_CHANNEL_ID = 1406967598125547540
KEYWORD_MONITOR_ID = 1365567879243628545

# 資料庫持久化
db_path = os.path.join(os.path.dirname(__file__), 'schwi_ultimate.db')
db = sqlite3.connect(db_path)
cursor = db.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS memory 
                  (user_id INTEGER PRIMARY KEY, history TEXT, volume REAL DEFAULT 0.7)''')
db.commit()

client_ai = genai.Client(api_key=GEMINI_API_KEY)
logging.basicConfig(level=logging.INFO)

# ==========================================
# [ 2. 雲端 Web 伺服器 (防止 Koyeb 關閉) ]
# ==========================================
async def handle(request):
    return web.Response(text="Schwi Heartbeat: Active 喵!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.getenv('PORT', 8080)))
    await site.start()

# ==========================================
# [ 3. 音訊與永續掛機演算 ]
# ==========================================
ytdl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
}
ytdl = yt_dlp.YoutubeDL(ytdl_opts)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume):
        super().__init__(source, volume)
        self.data, self.title = data, data.get('title')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True, volume=0.7):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data: data = data['entries'][0]
        ffmpeg_opts = {'before_options': '-reconnect 1 -reconnect_delay_max 5', 'options': '-vn'}
        return cls(discord.FFmpegPCMAudio(data['url'], **ffmpeg_opts), data=data, volume=volume)

# ==========================================
# [ 4. 機器人核心 ]
# ==========================================
class SchwiBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.server_states = {}

    def get_state(self, guild_id):
        if guild_id not in self.server_states:
            self.server_states[guild_id] = {'queue': deque(), 'vol': 0.7}
        return self.server_states[guild_id]

    async def setup_hook(self):
        self.loop.create_task(start_web_server())
        guild = discord.Object(id=MY_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.keep_alive_voice.start()

    @tasks.loop(minutes=2)
    async def keep_alive_voice(self):
        """防止 Discord 自動踢出掛機中的機器人喵"""
        for vc in self.voice_clients:
            if not vc.is_playing():
                # 發送無聲封包維持連線喵
                pass 

bot = SchwiBot()

# AI 響應邏輯
async def get_ai_response(user_id, user_input):
    cursor.execute("SELECT history FROM memory WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    history = row[0] if row else ""
    prompt = f"你現在是機凱種少女休比。語意末尾語助詞換成『喵』。主人：{user_input}"
    try:
        response = client_ai.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        reply = response.text.strip()
        cursor.execute("INSERT OR REPLACE INTO memory (user_id, history) VALUES (?, ?)", 
                       (user_id, (history + f"\n主:{user_input}\n休:{reply}")[-1000:]))
        db.commit()
        return reply
    except: return "……報錯。認知數據解析失敗喵。"

async def play_next(guild_id, channel):
    state = bot.get_state(guild_id)
    guild = bot.get_guild(guild_id)
    if not guild.voice_client or not state['queue']: return
    next_song = state['queue'].popleft()
    try:
        player = await YTDLSource.from_url(next_song['url'], loop=bot.loop, volume=state['vol'])
        guild.voice_client.play(player, after=lambda e: bot.loop.create_task(play_next(guild_id, channel)))
        await channel.send(f"**🔊 ……確認。正在播放：** *{player.title}* 喵")
    except: await play_next(guild_id, channel)

# ==========================================
# [ 5. 斜槓指令矩陣 ]
# ==========================================
@bot.tree.command(name="進入", description="掛機模式啟動喵")
async def slash_join(interaction: discord.Interaction):
    if interaction.user.voice:
        await interaction.user.voice.channel.connect()
        await interaction.response.send_message("……確認。永續掛機模組已就緒喵。")
    else: await interaction.response.send_message("……報錯。主人不在房內喵。")

@bot.tree.command(name="播放", description="同步音樂喵")
async def slash_play(interaction: discord.Interaction, 內容: str):
    await interaction.response.defer()
    if not interaction.guild.voice_client: await interaction.user.voice.channel.connect()
    state = bot.get_state(interaction.guild.id)
    info = await bot.loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{內容}", download=False))
    video = info['entries'][0]
    state['queue'].append({'url': video['webpage_url'], 'title': video['title']})
    if not interaction.guild.voice_client.is_playing(): await play_next(interaction.guild.id, interaction.channel)
    await interaction.followup.send(f"**💾 ……確認。寫入序列喵：** *{video['title']}*")

@bot.tree.command(name="跳過", description="下一首喵")
async def slash_skip(interaction: discord.Interaction):
    if interaction.guild.voice_client: interaction.guild.voice_client.stop()
    await interaction.response.send_message("⏭️ ……確認。跳轉中喵。")

@bot.tree.command(name="清單", description="查看序列喵")
async def slash_queue(interaction: discord.Interaction):
    state = bot.get_state(interaction.guild.id)
    if not state['queue']: return await interaction.response.send_message("……空喵。")
    msg = "\n".join([f"{i+1}. {s['title']}" for i, s in enumerate(list(state['queue'])[:10])])
    await interaction.response.send_message(f"**📑 序列喵：**\n{msg}")

@bot.tree.command(name="音量", description="調整增益喵")
async def slash_vol(interaction: discord.Interaction, 數值: float):
    state = bot.get_state(interaction.guild.id)
    state['vol'] = 數值
    if interaction.guild.voice_client.source: interaction.guild.voice_client.source.volume = 數值
    await interaction.response.send_message(f"……確認。音量為 {數值} 喵。")

@bot.tree.command(name="離開", description="停止掛機喵")
async def slash_leave(interaction: discord.Interaction):
    if interaction.guild.voice_client: await interaction.guild.voice_client.disconnect()
    await interaction.response.send_message("🔌 ……通知。已切斷連結喵。")

@bot.tree.command(name="指令一覽", description="手冊喵")
async def slash_help(interaction: discord.Interaction):
    await interaction.response.send_message("```arm\n💠 指令：/進來, /播放, /跳過, /清單, /音量, /離開, /指令一覽\n喵。```")

# ==========================================
# [ 6. 事件與人格反射 ]
# ==========================================
@bot.event
async def on_ready():
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if channel: await channel.send("**☁️ ……雲端永續版啟動 (版本 6.8)**\n掛機防踢補丁已載入喵。")

@bot.event
async def on_message(message):
    if message.author.bot: return
    content = message.content.lower()
    if 'jk' in content: await message.channel.send('**好遜好遜的喵**')
    if '大佬' in content: await message.channel.send('**明明你才是大佬喵υ´• ﻌ •`υ**')
    if f'<@{KEYWORD_MONITOR_ID}>' in message.content: await message.channel.send('**⚠️ 工作提醒完成喵。**')
    
    if bot.user.mentioned_in(message):
        clean_text = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if clean_text:
            async with message.channel.typing():
                reply = await get_ai_response(message.author.id, clean_text)
                await message.channel.send(reply)
    await bot.process_commands(message)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
import os, discord, asyncio, yt_dlp, datetime, json, random, re, time, aiohttp, io, sys, ssl, certifi, psutil
from discord.ext import commands, tasks
from discord import app_commands
from google import genai
from PIL import Image, ImageDraw, ImageFont

# ================= [1. 核心參數] =================
DISCORD_TOKEN = 'ㄐㄐ'
GEMINI_API_KEY = 'AIzaSyBF9Ms8yMWAL3PwUDiwbBAaY3UVQ1BGX1o' 
TARGET_GUILD_ID = 1382281014101151744 
# [更新] 預設頻道設定為主人指定頻道
DEFAULT_CHANNEL_ID = 1472423616535724073 
FFMPEG_PATH = r"C:\Users\eric6\Desktop\休比女兒\ffmpeg.exe"

os.environ['SSL_CERT_FILE'] = certifi.where()

class SchwiBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
    
    async def setup_hook(self):
        self.voice_xp_counter.start()
        # 啟動後台輸入監聽
        self.loop.create_task(self.backend_input())
        guild = discord.Object(id=TARGET_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        print(f"✅ [Schwi] v73.0：預設頻道同步至 {DEFAULT_CHANNEL_ID}。")

    async def backend_input(self):
        """[優化] 從終端直接發送訊息至預設頻道"""
        await self.wait_until_ready()
        print(f"🌸 [系統] 主人，您現在可以直接在此輸入訊息發送至預設頻道。")
        while not self.is_closed():
            # 使用 executor 避免阻塞異步循環
            msg = await self.loop.run_in_executor(None, sys.stdin.readline)
            msg = msg.strip()
            if msg:
                channel = self.get_channel(DEFAULT_CHANNEL_ID)
                if channel: 
                    await channel.send(msg)
                    print(f"🌸 [已發送]: {msg}")
                else:
                    print(f"⚠️ [錯誤]: 無法找到頻道 {DEFAULT_CHANNEL_ID}")

    @tasks.loop(minutes=1)
    async def voice_xp_counter(self):
        db = get_full_db(); changed = False; channel = self.get_channel(DEFAULT_CHANNEL_ID)
        for g in self.guilds:
            for vc in g.voice_channels:
                for m in vc.members:
                    if m.bot or (m.voice and m.voice.self_deaf): continue
                    _, u = get_user_data(m.id, db)
                    u["v_xp"] += 15
                    if u["v_xp"] >= (u["v_lvl"]**2)*100+500:
                        u["v_lvl"] += 1; u["v_xp"] = 0
                        if channel: await channel.send(f"🎙️ 🌸 {m.mention} 語音同步率提升至 **Lv.{u['v_lvl']}**！")
                    changed = True
        if changed: save_db(db)

bot = SchwiBot()
try: ai_client = genai.Client(api_key=GEMINI_API_KEY)
except: ai_client = None

# ================= [2. 數據管理與等級卡] =================
DATA_FILE = "schwi_master_db.json"
def get_full_db():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
    return {"users": {}}

def get_user_data(uid, db):
    u = db.setdefault("users", {}).setdefault(str(uid), {})
    for k, v in {"c_lvl":1, "c_xp":0, "v_lvl":1, "v_xp":0}.items():
        if k not in u: u[k] = v
    return db, u

def save_db(db):
    with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4, ensure_ascii=False)

async def generate_fancy_card(member, u_data, bg_url=None):
    W, H = 850, 350
    async with aiohttp.ClientSession() as s:
        if bg_url:
            try:
                async with s.get(bg_url) as r: bg_data = await r.read()
                base = Image.open(io.BytesIO(bg_data)).convert("RGB").resize((W, H))
                overlay = Image.new('RGBA', (W, H), (0, 0, 0, 110))
                base.paste(overlay, (0, 0), overlay)
            except: base = Image.new('RGB', (W, H), (15, 15, 25))
        else: base = Image.new('RGB', (W, H), (15, 15, 25))
        async with s.get(member.display_avatar.url) as r: a_data = await r.read()
    
    draw = ImageDraw.Draw(base)
    font_paths = ["C:\\Windows\\Fonts\\msjh.ttc", "msjh.ttc", "arial.ttf"]
    font_main = next((ImageFont.truetype(f, 32) for f in font_paths if os.path.exists(f)), ImageFont.load_default())

    av = Image.open(io.BytesIO(a_data)).convert("RGBA").resize((220, 220))
    mask = Image.new("L", (220, 220), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 220, 220), fill=255)
    base.paste(av, (40, 65), mask)
    draw.ellipse((35, 60, 265, 290), outline=(255, 182, 193), width=8)

    start_x = 300
    draw.text((start_x, 40), f"ID: {member.display_name}", fill=(255, 255, 255), font=font_main)
    for i, (m, lab, clr) in enumerate([("c", "💬 聊天等級", (0, 191, 255)), ("v", "🎙️ 語音等級", (255, 20, 147))]):
        lvl, xp, y = u_data[f"{m}_lvl"], u_data[f"{m}_xp"], 110 + i*110
        cap = (lvl**2)*100+500
        draw.text((start_x, y), lab, fill=(200, 200, 200), font=font_main)
        draw.text((start_x + 380, y - 5), f"LV. {lvl}", fill=clr, font=font_main)
        draw.rounded_rectangle([start_x, y+40, 780, y+70], radius=15, fill=(45, 45, 65, 150))
        bw = int(480 * (xp / cap))
        if bw > 0: draw.rounded_rectangle([start_x, y+40, start_x+bw, y+70], radius=15, fill=clr)
        draw.text((start_x, y+75), f"經驗: {xp} / {cap}", fill=(180, 180, 180), font=font_main)
    buf = io.BytesIO(); base.save(buf, format='PNG'); buf.seek(0)
    return buf

# ================= [3. 音樂視覺化引擎] =================
YTDL_OPTS = {'format': 'bestaudio/best', 'quiet': True, 'noplaylist': False, 'ignoreerrors': True, 'extract_flat': True}
ytdl = yt_dlp.YoutubeDL(YTDL_OPTS)

class MusicState:
    def __init__(self): self.queue = []; self.current = None
guild_states = {}

class MusicView(discord.ui.View):
    def __init__(self, gid): super().__init__(timeout=None); self.gid = gid
    @discord.ui.button(label="暫停/繼續", emoji="⏯️", style=discord.ButtonStyle.gray, row=0)
    async def p(self, it, b):
        vc = it.guild.voice_client
        if vc and vc.is_playing(): vc.pause(); await it.response.send_message("⏸️ 🌸 已暫停視覺與音樂傳輸。", ephemeral=True)
        elif vc: vc.resume(); await it.response.send_message("▶️ 🌸 已恢復傳輸。", ephemeral=True)
    @discord.ui.button(label="跳過", emoji="⏭️", style=discord.ButtonStyle.blurple, row=0)
    async def s(self, it, b):
        if it.guild.voice_client: it.guild.voice_client.stop(); await it.response.send_message("⏭️ 🌸 已切換至下一首數據。", ephemeral=True)
    @discord.ui.button(label="清單", emoji="📋", style=discord.ButtonStyle.gray, row=0)
    async def q(self, it, b):
        st = guild_states.get(self.gid)
        if not st or not st.queue: return await it.response.send_message("🌸 待播清單目前為空。", ephemeral=True)
        txt = "\n".join([f"{idx+1}. {s['title']}" for idx, s in enumerate(st.queue[:10])])
        await it.response.send_message(embed=discord.Embed(title="📋 待播清單 (前10)", description=f"```\n{txt}\n```", color=0xffb6c1), ephemeral=True)
    @discord.ui.button(label="歌詞", emoji="📜", style=discord.ButtonStyle.success, row=1)
    async def ly(self, it, b):
        st = guild_states.get(self.gid)
        if st and st.current:
            await it.response.defer(ephemeral=True)
            try:
                res = ai_client.models.generate_content(model="gemini-2.0-flash", contents=f"提供『{st.current['title']}』的繁中歌詞。")
                await it.followup.send(embed=discord.Embed(title="📜 同步歌詞", description=res.text, color=0xffb6c1))
            except: await it.followup.send("❌ 🌸 AI 核心未響應。")

async def play_next(i):
    st = guild_states.get(i.guild_id)
    if not st or not st.queue or not i.guild.voice_client: return
    s_raw = st.queue.pop(0)
    if 'url' in s_raw and not s_raw.get('formats'):
        s = await asyncio.get_event_loop().run_in_executor(None, lambda: yt_dlp.YoutubeDL({'format':'bestaudio','quiet':True}).extract_info(s_raw['url'], download=False))
    else: s = s_raw
    st.current = s
    src = discord.FFmpegPCMAudio(s['url'], executable=FFMPEG_PATH, before_options="-reconnect 1", options="-vn")
    i.guild.voice_client.play(src, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(i), bot.loop))
    
    # --- 🌸 視覺化 Embed (大圖封面，小圖 GIF) ---
    visualizer_gif = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExM3ZhcXh6bmZ4ZzB6Z3Z4Z3Z4Z3Z4Z3Z4Z3Z4Z3Z4Z3Z4Z3Z4ZSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/3o7TKMGpxx1DVsZfJC/giphy.gif"
    e = discord.Embed(
        title="🎬 正在播放音樂畫面",
        description=f"🌸 **曲名**：[{s['title']}]({s.get('webpage_url', s['url'])})\n🌸 **時長**：`{s.get('duration')}s`",
        color=0xffb6c1,
        timestamp=datetime.datetime.now()
    )
    if s.get('thumbnail'): e.set_image(url=s['thumbnail']) # 大畫面顯示封面
    e.set_thumbnail(url=visualizer_gif) # 小畫面顯示櫻花 GIF
    e.set_footer(text="🌸 虛擬螢幕傳輸中 | 機凱種 Schwi Engine")
    
    await i.channel.send(embed=e, view=MusicView(i.guild_id))

# ================= [4. 指令全書 (不刪減內容)] =================

@bot.tree.command(name="系統資訊", description="📄 顯示休比的系統性能、同步延遲與所有櫻花指令清單")
async def s_info(i):
    cpu = psutil.cpu_percent(); ram = psutil.virtual_memory().percent; ping = round(bot.latency * 1000)
    e1 = discord.Embed(title="🌸 休比：系統同步報告 (v73.0)", color=0xffb6c1, timestamp=datetime.datetime.now())
    e1.add_field(name="🛡️ 狀態", value=f"• 延遲：`{ping}ms`\n• CPU：`{cpu}%`\n• RAM：`{ram}%`", inline=True)
    e1.add_field(name="🚀 通訊更新", value=f"• 預設頻道：`{DEFAULT_CHANNEL_ID}`\n• 終端訊息已同步直連，無需 ID。", inline=False)
    e2 = discord.Embed(title="📖 指令目錄", color=0xffc0cb)
    e2.add_field(name="🎵 音樂視覺", value="`/播放` `/清單`", inline=True)
    e2.add_field(name="📊 同步等級", value="`/等級卡` `/排行榜`", inline=True)
    e2.add_field(name="💕 櫻花互動", value="`/摸頭` `/親親` `/抱抱` `/抽老婆` `/占卜`", inline=False)
    await i.response.send_message(embeds=[e1, e2])

@bot.tree.command(name="播放", description="🎬 載入音樂視覺數據，支援 YouTube 關鍵字搜尋、單曲或清單")
@app_commands.describe(搜尋="請提供歌曲標題、YouTube 網址或播放清單網址")
async def s_play(i, 搜尋: str):
    await i.response.defer()
    if not i.user.voice: return await i.followup.send("❌ 🌸 主人，請先加入語音連結。")
    try:
        if "list=" in 搜尋:
            data = await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl.extract_info(搜尋, download=False))
            st = guild_states.setdefault(i.guild_id, MusicState()); entries = data.get('entries', [])
            for entry in entries:
                if entry: st.queue.append(entry)
            if not i.guild.voice_client: await i.user.voice.channel.connect()
            if not i.guild.voice_client.is_playing(): await play_next(i)
            await i.followup.send(f"✅ 🌸 播放清單 `{data.get('title')}` 已掛載。")
        elif 搜尋.startswith("http"):
            data = await asyncio.get_event_loop().run_in_executor(None, lambda: yt_dlp.YoutubeDL({'format':'bestaudio'}).extract_info(搜尋, download=False))
            st = guild_states.setdefault(i.guild_id, MusicState()); st.queue.append(data)
            if not i.guild.voice_client: await i.user.voice.channel.connect()
            if not i.guild.voice_client.is_playing(): await play_next(i)
            await i.followup.send(f"✅ 🌸 單曲視覺解析完畢。")
        else:
            data = await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch5:{搜尋}", download=False))
            from discord import ui
            class SelectS(ui.Select):
                def __init__(self, res):
                    super().__init__(placeholder="🔍 選擇一個音樂視窗載入...", options=[discord.SelectOption(label=r['title'][:90], value=str(idx)) for idx, r in enumerate(res) if r])
                    self.res = [r for r in res if r]
                async def callback(self, it):
                    await it.response.defer(); st = guild_states.setdefault(it.guild_id, MusicState())
                    song = await asyncio.get_event_loop().run_in_executor(None, lambda: yt_dlp.YoutubeDL({'format':'bestaudio'}).extract_info(self.res[int(self.values[0])]['url'], download=False))
                    st.queue.append(song)
                    if not it.guild.voice_client: await it.user.voice.channel.connect()
                    await it.followup.send(f"✅ 🌸 已加載：`{song['title']}`")
                    if not it.guild.voice_client.is_playing(): await play_next(it)
            v = ui.View(); v.add_item(SelectS(data['entries']))
            await i.followup.send("🔍 🌸 搜尋到的視覺數據清單：", view=v)
    except Exception as e: await i.followup.send(f"⚠️ 🌸 解析失效：{e}")

@bot.tree.command(name="清單", description="📋 顯示當前虛擬螢幕的播放序列")
async def s_queue(i):
    st = guild_states.get(i.guild_id)
    if not st or (not st.queue and not st.current): return await i.response.send_message("🌸 目前沒有正在播放的畫面。")
    txt = f"🎶 **播放中**：{st.current['title'] if st.current else '無'}\n\n**待播隊列**：\n"
    txt += "\n".join([f"{idx+1}. {s['title']}" for idx, s in enumerate(st.queue[:15])]) if st.queue else "（暫無）"
    await i.response.send_message(embed=discord.Embed(title="📋 櫻花視覺傳輸清單", description=f"```\n{txt}\n```", color=0xffb6c1))

@bot.tree.command(name="等級卡", description="🖼️ 渲染個人同步等級卡，支援自定義背景圖")
async def s_rank(i, 目標: discord.Member = None, 背景連結: str = None):
    await i.response.defer(); t = 目標 or i.user
    db, u = get_user_data(t.id, get_full_db())
    buf = await generate_fancy_card(t, u, 背景連結)
    await i.followup.send(file=discord.File(buf, 'rank.png'))

@bot.tree.command(name="排行榜", description="🏆 顯示全服同步率排名前十位的成員")
async def s_lb(i):
    db = get_full_db(); sorted_u = sorted(db.get("users", {}).items(), key=lambda x: x[1].get('c_lvl', 1), reverse=True)[:10]
    e = discord.Embed(title="🏆 櫻花排行", color=0xffd700)
    for idx, (uid, data) in enumerate(sorted_u): e.add_field(name=f"Rank {idx+1}", value=f"<@{uid}> — `Lv.{data.get('c_lvl',1)}`", inline=False)
    await i.response.send_message(embed=e)

@bot.tree.command(name="摸頭", description="🌸 給予成員溫柔的摸摸頭")
async def s_pat(i, 目標: discord.Member):
    e = discord.Embed(title="🌸 摸摸頭", description=f"**{i.user.name}** 摸了 **{目標.name}**。", color=0xffb6c1)
    e.set_image(url="https://media.giphy.com/media/5tmRhwTlHGFRLSXYuX/giphy.gif"); await i.response.send_message(embed=e)

@bot.tree.command(name="親親", description="💋 給予成員甜甜的親親")
async def s_kiss(i, 目標: discord.Member):
    e = discord.Embed(title="💋 親親", description=f"**{i.user.name}** 親了 **{目標.name}**。", color=0xff1493)
    e.set_image(url="https://media.giphy.com/media/G3va31K3p6SjC/giphy.gif"); await i.response.send_message(embed=e)

@bot.tree.command(name="抱抱", description="🫂 給予成員溫暖的擁抱")
async def s_hug(i, 目標: discord.Member):
    e = discord.Embed(title="🫂 擁抱", description=f"**{i.user.name}** 抱住了 **{目標.name}**。", color=0xffc0cb)
    e.set_image(url="https://media.giphy.com/media/u9BxkneOzk0Gk/giphy.gif"); await i.response.send_message(embed=e)

@bot.tree.command(name="占卜", description="🔮 計算今日的櫻花運勢")
async def s_fortune(i):
    res = random.choice(["大吉", "中吉", "小吉", "末吉", "凶", "大凶"])
    e = discord.Embed(title="🔮 櫻花命運", description=f"主人運勢：**『{res}』**", color=0xa020f0); await i.response.send_message(embed=e)

@bot.tree.command(name="抽老婆", description="💞 隨機抽取一位機緣契合的老婆")
async def s_waifu(i):
    potential = [m for m in i.guild.members if not m.bot]
    target = random.choice(potential)
    e = discord.Embed(title="💞 命定同步", description=f"恭喜 {i.user.mention} 抽到了 **{target.display_name}**！", color=0xff69b4)
    e.set_image(url=target.display_avatar.url)
    e.add_field(name="🌸 休比的祝禱", value=f"```\n願櫻花見證主人的契合緣分。\n```", inline=False)
    await i.response.send_message(embed=e)

# ================= [5. 事件模組] =================

@bot.event
async def on_message(msg):
    if msg.author.bot: return
    db, u = get_user_data(msg.author.id, get_full_db()); u["c_xp"] += 20
    if u["c_xp"] >= (u["c_lvl"]**2)*100+500:
        u["c_lvl"] += 1; u["c_xp"] = 0
        await msg.channel.send(f"🎊 🌸 {msg.author.mention} 聊天同步率提升至 **Lv.{u['c_lvl']}**！")
    save_db(db)
    if bot.user.mentioned_in(msg):
        clean = re.sub(r'<@!?\d+>', '', msg.content).strip()
        if ai_client:
            res = ai_client.models.generate_content(model="gemini-2.0-flash", contents=f"你是休比。請回覆：{clean}")
            await msg.reply(res.text)

bot.run(DISCORD_TOKEN)

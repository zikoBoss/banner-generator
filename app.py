import io
import os
import asyncio
import httpx
from fastapi import FastAPI, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageDraw, ImageFont
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CONFIG ---
API_KEY = "ziko"  # المفتاح السري
INFO_API_URL = "http://203.57.85.58:2035/player-info"
ITEM_API_URL = "https://mafu-icon-api.onrender.com/icon?key=MAFU&item_id="
FONT_FILE = "NotoSans-Bold.ttf"

client = httpx.AsyncClient(
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=10.0,
    follow_redirects=True
)

process_pool = ThreadPoolExecutor(max_workers=4)

# --- UTILS ---

def load_unicode_font(size):
    try:
        font_path = os.path.join(os.path.dirname(__file__), FONT_FILE)
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
        return ImageFont.load_default()
    except:
        return ImageFont.load_default()

async def fetch_image_bytes(item_id):
    if not item_id or str(item_id) == "0" or item_id is None:
        return None
    item_id = str(item_id)
    url = f"{ITEM_API_URL}{item_id}"
    try:
        resp = await client.get(url)
        if resp.status_code == 200:
            return resp.content
    except:
        return None
    return None

def bytes_to_image(img_bytes):
    if img_bytes:
        return Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    return Image.new('RGBA', (100, 100), (0, 0, 0, 0))

def process_banner_image(data, avatar_bytes, banner_bytes, pin_bytes):
    avatar_img = bytes_to_image(avatar_bytes)
    banner_img = bytes_to_image(banner_bytes)
    pin_img = bytes_to_image(pin_bytes)

    level = str(data.get("AccountLevel", "0"))
    name = data.get("AccountName", "Unknown")
    guild = data.get("GuildName", "")

    TARGET_HEIGHT = 400
    avatar_img = avatar_img.resize((TARGET_HEIGHT, TARGET_HEIGHT), Image.LANCZOS)

    b_w, b_h = banner_img.size
    if b_w > 50 and b_h > 50:
        banner_img = banner_img.rotate(3, resample=Image.BICUBIC, expand=True)
        b_w, b_h = banner_img.size
        crop_top, crop_bottom, crop_sides = 0.23, 0.32, 0.17
        left, top = b_w * crop_sides, b_h * crop_top
        right, bottom = b_w * (1 - crop_sides), b_h * (1 - crop_bottom)
        banner_img = banner_img.crop((left, top, right, bottom))

    b_w, b_h = banner_img.size
    if b_h > 0:
        new_banner_w = int(TARGET_HEIGHT * (b_w / b_h) * 2.0)
        banner_img = banner_img.resize((new_banner_w, TARGET_HEIGHT), Image.LANCZOS)
    else:
        banner_img = Image.new("RGBA", (800, 400), (50, 50, 50))
        new_banner_w = 400

    final_w = TARGET_HEIGHT + new_banner_w
    final_h = TARGET_HEIGHT
    combined = Image.new("RGBA", (final_w, final_h), (0, 0, 0, 0))
    combined.paste(avatar_img, (0, 0))
    combined.paste(banner_img, (TARGET_HEIGHT, 0))

    draw = ImageDraw.Draw(combined)
    font_large = load_unicode_font(125)
    font_small = load_unicode_font(95)
    font_level = load_unicode_font(50)

    text_x = TARGET_HEIGHT + 40
    text_y = 40

    stroke_col, text_col = "black", "white"
    def draw_text_with_stroke(x, y, text, font, size):
        for dx in range(-size, size + 1):
            for dy in range(-size, size + 1):
                draw.text((x + dx, y + dy), text, font=font, fill=stroke_col)
        draw.text((x, y), text, font=font, fill=text_col)

    draw_text_with_stroke(text_x + 25, text_y, name, font_large, 4)
    draw_text_with_stroke(text_x + 25, text_y + 200, guild, font_small, 3)

    if pin_img and pin_img.size != (100, 100):
        pin_size = 130
        pin_img = pin_img.resize((pin_size, pin_size), Image.LANCZOS)
        combined.paste(pin_img, (0, TARGET_HEIGHT - pin_size), pin_img)

    level_txt = f"Lvl.{level}"
    try:
        bbox = draw.textbbox((0, 0), level_txt, font=font_level)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except:
        text_w, text_h = len(level_txt) * 20, 40

    px, py = 25, 16
    box_x = final_w - (text_w + px * 2)
    box_y = final_h - (text_h + py * 2)

    draw.rectangle([box_x, box_y, final_w, final_h], fill="black")
    draw.text((box_x + px, box_y + py - 6), level_txt, font=font_level, fill="white")

    img_io = io.BytesIO()
    combined.save(img_io, 'PNG')
    img_io.seek(0)
    return img_io

# --- ROUTES ---

@app.get("/")
async def home():
    return {
        "message": "⚡ Banner API with API Key",
        "usage": "/profile?key=ziko&uid=YOUR_UID",
        "note": "You must provide valid key 'ziko'"
    }

@app.get("/profile")
async def get_banner(uid: str, key: str):
    # التحقق من المفتاح
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")

    if not uid:
        raise HTTPException(status_code=400, detail="UID required")

    try:
        resp = await client.get(f"{INFO_API_URL}?uid={uid}&key=@yashapis")
        resp.raise_for_status()
        data = resp.json()

        basic_info = data.get("basicInfo", {})
        clan_info = data.get("clanBasicInfo", {})

        avatar_id = basic_info.get("headPic")
        banner_id = basic_info.get("bannerId")
        pin_id = basic_info.get("title")

        avatar_task = fetch_image_bytes(avatar_id)
        banner_task = fetch_image_bytes(banner_id)
        pin_task = fetch_image_bytes(pin_id) if (pin_id and str(pin_id) != "0") else asyncio.sleep(0)

        results = await asyncio.gather(avatar_task, banner_task, pin_task)
        avatar_bytes, banner_bytes, pin_bytes = results[0], results[1], results[2]
        if pin_bytes is None: pin_bytes = b''

        loop = asyncio.get_event_loop()
        banner_data = {
            "AccountLevel": basic_info.get("level") or 0,
            "AccountName": basic_info.get("nickname") or "Unknown",
            "GuildName": clan_info.get("clanName") or ""
        }

        img_io = await loop.run_in_executor(
            process_pool,
            process_banner_image,
            banner_data, avatar_bytes, banner_bytes, pin_bytes
        )

        return Response(
            content=img_io.getvalue(),
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=300"}
        )

    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Info API request failed: {e}")
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- SHUTDOWN ---
@app.on_event("shutdown")
async def shutdown_event():
    await client.aclose()
    process_pool.shutdown()

# --- RUN SERVER ---
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)

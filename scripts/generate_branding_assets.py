"""
Script reproduzível para geração de assets gráficos de branding do ClipMaker.io:
- frontend/favicon-32x32.png (32x32)
- frontend/apple-touch-icon.png (180x180)
- frontend/assets/og-image.png (1200x630 para Open Graph / Twitter Cards)
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
ASSETS_DIR = FRONTEND_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# Cores oficiais da Direção A (Studio Engine)
BG_DARK = (9, 10, 13)       # #090A0D
SURFACE_CARD = (17, 19, 24) # #111318
BORDER_COLOR = (38, 42, 54) # #262A36
BADGE_BG = (13, 21, 32)     # #0D1520
BADGE_RIM = (75, 110, 150)  # #4B6E96
LIME_ACCENT = (0, 240, 118) # #00F076
LIME_BRIGHT = (118, 255, 180)# #76FFB4
MINT_PLAY = (167, 243, 208) # #A7F3D0
TEXT_WHITE = (245, 246, 248)# #F5F6F8
SILVER_BRACKET = (241, 245, 249) # #F1F5F9
TEXT_MUTED = (142, 150, 166)# #8E96A6

def draw_symbol(draw, x, y, size):
    """Desenha o símbolo Studio Engine fiel ao app badge com alto contraste e visibilidade."""
    # Caixa base squircle
    rad = int(size * 0.22)
    bw = max(1, int(size * 0.035))
    draw.rounded_rectangle([x, y, x + size, y + size], radius=rad, fill=BADGE_BG, outline=BADGE_RIM, width=bw)
    
    # Top specular shine
    if size >= 32:
        top_y = y + max(1, int(size * 0.04))
        draw.line([(x + int(size * 0.25), top_y), (x + int(size * 0.75), top_y)], fill=(255, 255, 255, 200), width=max(1, int(size * 0.02)))
        
    # Colchetes de corte (viewfinder) em branco-prata de alto contraste
    bracket_pad = int(size * 0.22)
    bracket_len = int(size * 0.14)
    bracket_w = max(2, int(size * 0.065))
    
    # Top-left
    draw.line([(x + bracket_pad, y + bracket_pad + bracket_len), (x + bracket_pad, y + bracket_pad), (x + bracket_pad + bracket_len, y + bracket_pad)], fill=SILVER_BRACKET, width=bracket_w)
    # Top-right
    draw.line([(x + size - bracket_pad - bracket_len, y + bracket_pad), (x + size - bracket_pad, y + bracket_pad), (x + size - bracket_pad, y + bracket_pad + bracket_len)], fill=SILVER_BRACKET, width=bracket_w)
    # Bottom-left
    draw.line([(x + bracket_pad, y + size - bracket_pad - bracket_len), (x + bracket_pad, y + size - bracket_pad), (x + bracket_pad + bracket_len, y + size - bracket_pad)], fill=SILVER_BRACKET, width=bracket_w)
    # Bottom-right
    draw.line([(x + size - bracket_pad - bracket_len, y + size - bracket_pad), (x + size - bracket_pad, y + size - bracket_pad), (x + size - bracket_pad, y + size - bracket_pad - bracket_len)], fill=SILVER_BRACKET, width=bracket_w)
    
    # Quadro vertical 9:16 central (verde neon vibrante)
    qw = int(size * 0.31)
    qh = int(size * 0.63)
    qx = x + (size - qw) // 2
    qy = y + (size - qh) // 2
    frame_w = max(2, int(size * 0.065))
    draw.rounded_rectangle([qx, qy, qx + qw, qy + qh], radius=int(size * 0.10), fill=(0, 24, 11, 100), outline=LIME_ACCENT, width=frame_w)
    
    # Play centralizado em mint vibrante
    pw = int(size * 0.12)
    px = x + size // 2 - int(pw * 0.35)
    py = y + size // 2
    draw.polygon([(px, py - pw), (px + int(pw * 1.3), py), (px, py + pw)], fill=MINT_PLAY)


def generate_favicons():
    # 1. Favicon 32x32
    img32 = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d32 = ImageDraw.Draw(img32)
    draw_symbol(d32, 0, 0, 32)
    img32.save(FRONTEND_DIR / "favicon-32x32.png", "PNG")
    print(f"[OK] Favicon 32x32 gerado: {FRONTEND_DIR / 'favicon-32x32.png'}")

    # 2. Apple Touch Icon 180x180
    img180 = Image.new("RGBA", (180, 180), BG_DARK)
    d180 = ImageDraw.Draw(img180)
    draw_symbol(d180, 15, 15, 150)
    img180.save(FRONTEND_DIR / "apple-touch-icon.png", "PNG")
    print(f"[OK] Apple Touch Icon 180x180 gerado: {FRONTEND_DIR / 'apple-touch-icon.png'}")

def generate_og_image():
    # 1200 x 630 px
    w, h = 1200, 630
    img = Image.new("RGB", (w, h), BG_DARK)
    d = ImageDraw.Draw(img)

    # Grid sutil no fundo
    grid_size = 40
    for x in range(0, w, grid_size):
        d.line([(x, 0), (x, h)], fill=(17, 19, 24), width=1)
    for y in range(0, h, grid_size):
        d.line([(0, y), (w, y)], fill=(17, 19, 24), width=1)

    # Brilho sutil radial verde no canto superior esquerdo
    # Moldura externa elegante
    d.rounded_rectangle([40, 40, w - 40, h - 40], radius=24, outline=BORDER_COLOR, width=2)

    # Símbolo maior
    sym_size = 140
    draw_symbol(d, 80, 80, sym_size)

    # Tipografia e títulos com fallback seguro para fontes do sistema
    try:
        font_title = ImageFont.truetype("arialbd.ttf", 52)
        font_sub = ImageFont.truetype("arial.ttf", 26)
        font_badge = ImageFont.truetype("arialbd.ttf", 20)
        font_logo = ImageFont.truetype("arialbd.ttf", 36)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_badge = ImageFont.load_default()
        font_logo = ImageFont.load_default()

    # Logo Text
    d.text((250, 110), "ClipMaker", font=font_logo, fill=TEXT_WHITE)
    d.text((250 + 195, 110), ".io", font=font_logo, fill=LIME_ACCENT)

    # Badge de categoria
    d.rounded_rectangle([80, 260, 360, 298], radius=8, fill=(0, 240, 118, 30), outline=LIME_ACCENT, width=1)
    d.text((95, 268), "CORTES VIRAIS COM IA", font=font_badge, fill=LIME_ACCENT)

    # Headline
    d.text((80, 320), "De um vídeo longo para cortes que viralizam.", font=font_title, fill=TEXT_WHITE)
    d.text((80, 395), "Transcreva, detecte momentos chave, recorte em 9:16 e adicione legendas dinâmicas.", font=font_sub, fill=TEXT_MUTED)

    # Métricas / Features no rodapé
    features = [
        "Transcritor Whisper",
        "Detecção com Gemini",
        "Render FFmpeg Passe Único",
        "Zero Marca D'água"
    ]
    fx = 80
    for feat in features:
        d.rounded_rectangle([fx, 500, fx + 240, 545], radius=10, fill=SURFACE_CARD, outline=BORDER_COLOR, width=1)
        d.text((fx + 18, 514), f"•  {feat}", font=font_badge, fill=TEXT_WHITE)
        fx += 260

    out_path = ASSETS_DIR / "og-image.png"
    img.save(out_path, "PNG", optimize=True)
    print(f"[OK] OG Image 1200x630 gerada: {out_path}")

if __name__ == "__main__":
    generate_favicons()
    generate_og_image()
    print("[SUCESSO] Todos os assets de branding gerados com sucesso!")

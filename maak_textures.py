"""
Maakt onze eigen pixel-plaatjes (textures) voor de Minecraft-achtige blokken.
Draai dit één keer:   python maak_textures.py
De plaatjes komen in de map  assets/textures/  te staan.

We tekenen eerst op een raster van 32x32 (lekker veel detail) en maken het
plaatje daarna SCHERP groter naar 128x128 (zonder wazige rand). Zo krijg je
grote, mooie blokken die er toch chunky uitzien, net als Minecraft.

Dit zijn ONZE EIGEN plaatjes die LIJKEN op Minecraft-blokken.
De echte Minecraft-plaatjes zijn van Mojang en mogen we niet kopiëren.
"""
import os
import random
from PIL import Image
from mc_blokken import TEXTUUR_DEFS

S = 32     # op zoveel pixels tekenen we (meer detail dan de oude 16)
GROOT = 128  # zo groot wordt het plaatje uiteindelijk opgeslagen


def _grens(waarde):
    """Houd een kleurwaarde tussen 0 en 255."""
    return max(0, min(255, int(waarde)))


def _schaduw(kleur, delta):
    """Maakt een kleur iets lichter (delta > 0) of donkerder (delta < 0)."""
    return (_grens(kleur[0] + delta), _grens(kleur[1] + delta), _grens(kleur[2] + delta))


def zet(px, x, y, kleur):
    """Zet één pixel op kleur (als hij op het plaatje ligt)."""
    if 0 <= x < S and 0 <= y < S:
        px[x, y] = (kleur[0], kleur[1], kleur[2], 255)


def blok(px, x0, y0, w, h, kleur):
    """Vult een rechthoekje met een kleur."""
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            zet(px, x, y, kleur)


# ---------- De verschillende plaatjes-stijlen (op 32x32) ----------

def speckle(px, rng, c1, var=15, **_):
    """Spikkels: overal de hoofdkleur met kleine licht/donker verschillen."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-var, var)))


def gras(px, rng, c1, c2, **_):
    """Gras: twee tinten groen door elkaar, met sprietjes."""
    for y in range(S):
        for x in range(S):
            basis = c1 if rng.random() > 0.5 else c2
            zet(px, x, y, _schaduw(basis, rng.randint(-12, 12)))
    for _ in range(24):                 # kleine sprietjes bovenop
        x = rng.randint(0, S - 1)
        y = rng.randint(0, S - 4)
        zet(px, x, y, _schaduw(c2, 25))
        zet(px, x, y + 1, _schaduw(c2, 15))


def leaves(px, rng, c1, c2, **_):
    """Bladeren: groen met donkere gaatjes."""
    for y in range(S):
        for x in range(S):
            basis = c1 if rng.random() > 0.35 else c2
            zet(px, x, y, _schaduw(basis, rng.randint(-18, 18)))


def planks(px, rng, c1, c2, **_):
    """Planken: liggende plankjes met naden en houtnerf."""
    for y in range(S):
        rij = _schaduw(c1, rng.randint(-8, 8))
        for x in range(S):
            zet(px, x, y, _schaduw(rij, rng.randint(-7, 7)))
    for y in range(0, S, 8):            # naad tussen de planken
        for x in range(S):
            zet(px, x, y, c2)
    for _ in range(8):                  # korte verticale nerf-streepjes
        x = rng.randint(1, S - 2)
        y = rng.randint(0, S - 3)
        for k in range(rng.randint(2, 5)):
            zet(px, x, y + k, _schaduw(c1, -18))


def bark(px, rng, c1, c2, **_):
    """Boomschors: staande strepen en donkere streepjes."""
    for x in range(S):
        kolom = _schaduw(c1, rng.randint(-10, 10))
        for y in range(S):
            zet(px, x, y, _schaduw(kolom, rng.randint(-7, 7)))
    for x in range(0, S, 8):            # donkere schors-lijnen
        for y in range(S):
            zet(px, x, y, _schaduw(c2, rng.randint(-6, 6)))
    for _ in range(12):                 # kleine donkere streepjes (bv berk)
        x = rng.randint(0, S - 1)
        y = rng.randint(0, S - 3)
        blok(px, x, y, 1, 2, c2)


def brick(px, rng, c1, c2, **_):
    """Baksteen: rijen stenen met specie ertussen."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-12, 12)))
    for y in range(0, S, 8):            # liggende specie-lijnen
        for x in range(S):
            zet(px, x, y, c2)
    for i, y0 in enumerate(range(0, S, 8)):   # staande specie, om en om verschoven
        off = 0 if i % 2 == 0 else 8
        for x in range(off, S, 16):
            for y in range(y0, min(S, y0 + 8)):
                zet(px, x, y, c2)


def cobble(px, rng, c1, c2, **_):
    """Rommelsteen: losse keien op donkere specie."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, c2)          # donkere achtergrond (specie)
    for _ in range(13):                # keien erover
        w = rng.randint(8, 14)
        h = rng.randint(8, 14)
        x0 = rng.randint(0, S - w)
        y0 = rng.randint(0, S - h)
        kei = _schaduw(c1, rng.randint(-18, 22))
        for y in range(y0 + 1, y0 + h - 1):
            for x in range(x0 + 1, x0 + w - 1):
                zet(px, x, y, _schaduw(kei, rng.randint(-12, 12)))


def ore(px, rng, c1, c2, **_):
    """Erts: gewone steen met een paar gekleurde korrels."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-16, 16)))
    for _ in range(6):                 # klontjes erts
        cx = rng.randint(3, S - 4)
        cy = rng.randint(3, S - 4)
        for y in range(cy - 2, cy + 3):
            for x in range(cx - 2, cx + 3):
                if (x - cx) ** 2 + (y - cy) ** 2 <= 6 and rng.random() > 0.2:
                    zet(px, x, y, _schaduw(c2, rng.randint(-20, 20)))


def gem(px, rng, c1, c2, **_):
    """Mineraal-blok: gladde kleur met glinstervlakjes en een rand."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-10, 10)))
    for _ in range(5):                 # glinstervlakjes
        s = rng.randint(4, 8)
        x0 = rng.randint(0, S - s)
        y0 = rng.randint(0, S - s)
        for y in range(y0, y0 + s):
            for x in range(x0, x0 + s):
                zet(px, x, y, _schaduw(c2, rng.randint(-8, 8)))
    for i in range(S):                 # donkere rand (2 pixels dik)
        for d in (0, 1):
            zet(px, i, d, _schaduw(c1, -25))
            zet(px, i, S - 1 - d, _schaduw(c1, -25))
            zet(px, d, i, _schaduw(c1, -25))
            zet(px, S - 1 - d, i, _schaduw(c1, -25))


def solid(px, rng, c1, var=8, **_):
    """Metaal-blok: bijna effen met een glans-lijn."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-var, var)))
    for i in range(S):                 # diagonale glans (2 pixels dik)
        zet(px, i, i, _schaduw(c1, 45))
        zet(px, i, min(S - 1, i + 1), _schaduw(c1, 30))


def wool(px, rng, c1, **_):
    """Wol: zachte, pluizige effen kleur."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-14, 14)))


def sandstone(px, rng, c1, c2, **_):
    """Zandsteen: zand met een lijn boven en onder."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-8, 8)))
    for x in range(S):
        blok(px, x, 2, 1, 2, c2)
        blok(px, x, S - 4, 1, 2, c2)


def dots(px, rng, c1, c2, **_):
    """Paddenstoel: gekleurd met witte stippen."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-8, 8)))
    for _ in range(6):
        cx = rng.randint(4, S - 5)
        cy = rng.randint(4, S - 5)
        r = rng.randint(2, 4)
        for y in range(cy - r, cy + r + 1):
            for x in range(cx - r, cx + r + 1):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r + 1:
                    zet(px, x, y, c2)


def stripes(px, rng, c1, c2, **_):
    """Meloen: staande strepen in twee groentinten."""
    for x in range(S):
        kleur = c1 if (x // 4) % 2 == 0 else c2
        for y in range(S):
            zet(px, x, y, _schaduw(kleur, rng.randint(-10, 10)))


def hay(px, rng, c1, c2, **_):
    """Hooibaal: liggende strootjes."""
    for y in range(S):
        kleur = c1 if (y // 4) % 2 == 0 else c2
        for x in range(S):
            zet(px, x, y, _schaduw(kleur, rng.randint(-12, 12)))
    for x in range(0, S, 14):
        for y in range(S):
            zet(px, x, y, _schaduw(c2, -12))


def pumpkin(px, rng, c1, c2, **_):
    """Pompoen: oranje met staande ribbels."""
    for x in range(S):
        kleur = c1 if (x % 8) >= 1 else c2
        for y in range(S):
            zet(px, x, y, _schaduw(kleur, rng.randint(-10, 10)))


def lava(px, rng, c1, c2, **_):
    """Lava: donkere gloed met felle blobjes."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-20, 10)))
    for _ in range(8):
        cx = rng.randint(2, S - 3)
        cy = rng.randint(2, S - 3)
        r = rng.randint(2, 4)
        for y in range(cy - r, cy + r + 1):
            for x in range(cx - r, cx + r + 1):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    zet(px, x, y, _schaduw(c2, rng.randint(-15, 15)))


def ice(px, rng, c1, c2, **_):
    """IJs: lichtblauw met barstjes."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-8, 8)))
    for _ in range(6):
        x = rng.randint(0, S - 1)
        y = rng.randint(0, S - 1)
        for _stap in range(rng.randint(6, 12)):
            zet(px, x, y, c2)
            x += rng.choice([-1, 0, 1])
            y += rng.choice([0, 1])


def glow(px, rng, c1, c2, **_):
    """Glowsteen: warme kleur met lichtpuntjes."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-10, 10)))
    for _ in range(14):
        cx = rng.randint(1, S - 2)
        cy = rng.randint(1, S - 2)
        blok(px, cx, cy, 2, 2, c2)


def tnt(px, rng, c1, c2, **_):
    """TNT: rood met een witte band in het midden."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-10, 10)))
    for y in range(12, 20):            # witte band
        for x in range(S):
            zet(px, x, y, c2)
    for x in range(4, S, 6):           # streepjes (lijkt op letters)
        blok(px, x, 14, 2, 4, _schaduw(c1, -30))


def sponge(px, rng, c1, c2, **_):
    """Spons: geel met donkere gaatjes."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-12, 12)))
    for _ in range(22):
        blok(px, rng.randint(1, S - 3), rng.randint(1, S - 3), 2, 2, c2)


def bookshelf(px, rng, c1, c2, **_):
    """Boekenkast: hout met gekleurde boeken in het midden."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-8, 8)))
    boek_kleuren = [(180, 50, 50), (50, 90, 180), (60, 160, 70),
                    (200, 180, 60), (150, 60, 160)]
    x = 1
    while x < S - 1:                    # staande boeken naast elkaar
        breedte = rng.randint(1, 3)
        if rng.random() < 0.85:
            kleur = rng.choice(boek_kleuren)
            for xx in range(x, min(S - 1, x + breedte)):
                for y in range(8, S - 8):
                    zet(px, xx, y, _schaduw(kleur, rng.randint(-15, 15)))
        x += breedte + 1
    for x in range(S):                  # plank-lijnen boven en onder de boeken
        blok(px, x, 6, 1, 2, c2)
        blok(px, x, S - 8, 1, 2, c2)


# Welke functie hoort bij welke stijl?
STIJLEN = {
    'speckle': speckle, 'gras': gras, 'leaves': leaves, 'planks': planks,
    'bark': bark, 'brick': brick, 'cobble': cobble, 'ore': ore, 'gem': gem,
    'solid': solid, 'wool': wool, 'sandstone': sandstone, 'dots': dots,
    'stripes': stripes, 'hay': hay, 'pumpkin': pumpkin, 'lava': lava,
    'ice': ice, 'glow': glow, 'tnt': tnt, 'sponge': sponge, 'bookshelf': bookshelf,
}


def maak_alle_textures():
    """Maakt alle plaatjes en zet ze (128x128) in de map assets/textures."""
    map_pad = os.path.join('assets', 'textures')
    os.makedirs(map_pad, exist_ok=True)

    for d in TEXTUUR_DEFS:
        naam = d['naam']
        functie = STIJLEN[d['stijl']]
        # Elk plaatje krijgt altijd hetzelfde 'toeval' (op basis van de naam),
        # zodat het elke keer precies hetzelfde plaatje wordt.
        rng = random.Random(naam)
        img = Image.new('RGBA', (S, S), (0, 0, 0, 255))
        px = img.load()
        functie(px, rng, **{k: v for k, v in d.items()
                            if k not in ('naam', 'stijl')})
        # SCHERP groter maken naar 128x128 (NEAREST = geen wazige rand).
        groot = img.resize((GROOT, GROOT), Image.NEAREST)
        groot.save(os.path.join(map_pad, naam + '.png'))

    print(f"Klaar! {len(TEXTUUR_DEFS)} plaatjes gemaakt "
          f"(getekend op {S}x{S}, opgeslagen als {GROOT}x{GROOT}) in {map_pad}")


if __name__ == '__main__':
    maak_alle_textures()

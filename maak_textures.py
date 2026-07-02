"""
Maakt onze eigen pixel-plaatjes (textures) voor de Minecraft-achtige blokken.
Draai dit één keer:   python maak_textures.py
De plaatjes komen in de map  assets/textures/  te staan.

Elk plaatje is 16x16 pixels, net als de echte Minecraft-blokken.
"""
import os
import random
from PIL import Image
from mc_blokken import TEXTUUR_DEFS

S = 16   # het plaatje is 16 bij 16 pixels


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


# ---------- De verschillende plaatjes-stijlen ----------

def speckle(px, rng, c1, var=15, **_):
    """Spikkels: overal de hoofdkleur met kleine licht/donker verschillen."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-var, var)))


def gras(px, rng, c1, c2, **_):
    """Gras: twee tinten groen door elkaar."""
    for y in range(S):
        for x in range(S):
            basis = c1 if rng.random() > 0.5 else c2
            zet(px, x, y, _schaduw(basis, rng.randint(-12, 12)))


def leaves(px, rng, c1, c2, **_):
    """Bladeren: groen met donkere gaatjes."""
    for y in range(S):
        for x in range(S):
            basis = c1 if rng.random() > 0.35 else c2
            zet(px, x, y, _schaduw(basis, rng.randint(-15, 15)))


def planks(px, rng, c1, c2, **_):
    """Planken: liggende plankjes met naden ertussen."""
    for y in range(S):
        rij = _schaduw(c1, rng.randint(-8, 8))
        for x in range(S):
            zet(px, x, y, _schaduw(rij, rng.randint(-6, 6)))
    for y in range(0, S, 4):            # naad tussen de planken
        for x in range(S):
            zet(px, x, y, c2)
    for _ in range(3):                  # een paar korte verticale naadjes
        x = rng.randint(1, S - 2)
        y = rng.randint(0, S - 1)
        zet(px, x, y, c2)


def bark(px, rng, c1, c2, **_):
    """Boomschors: staande strepen."""
    for x in range(S):
        kolom = _schaduw(c1, rng.randint(-10, 10))
        for y in range(S):
            zet(px, x, y, _schaduw(kolom, rng.randint(-6, 6)))
    for x in range(0, S, 4):            # donkere schors-lijnen
        for y in range(S):
            zet(px, x, y, _schaduw(c2, rng.randint(-5, 5)))
    for _ in range(6):                  # kleine donkere streepjes (bv berk)
        x = rng.randint(0, S - 1)
        y = rng.randint(0, S - 2)
        zet(px, x, y, c2)
        zet(px, x, y + 1, c2)


def brick(px, rng, c1, c2, **_):
    """Baksteen: rijen stenen met specie ertussen."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-12, 12)))
    for y in range(0, S, 4):            # liggende specie-lijnen
        for x in range(S):
            zet(px, x, y, c2)
    for i, y0 in enumerate(range(0, S, 4)):   # staande specie, om en om verschoven
        off = 0 if i % 2 == 0 else 4
        for x in range(off, S, 8):
            for y in range(y0, min(S, y0 + 4)):
                zet(px, x, y, c2)


def cobble(px, rng, c1, c2, **_):
    """Rommelsteen: losse keien op donkere specie."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, c2)          # donkere achtergrond (specie)
    for _ in range(9):                 # keien erover
        w = rng.randint(4, 7)
        h = rng.randint(4, 7)
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
    for _ in range(4):                 # klontjes erts
        cx = rng.randint(2, S - 3)
        cy = rng.randint(2, S - 3)
        for y in range(cy - 1, cy + 2):
            for x in range(cx - 1, cx + 2):
                if rng.random() > 0.25:
                    zet(px, x, y, _schaduw(c2, rng.randint(-20, 20)))


def gem(px, rng, c1, c2, **_):
    """Mineraal-blok: gladde kleur met glinsterende vlakjes en een rand."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-10, 10)))
    for _ in range(4):                 # glinstervlakjes
        s = rng.randint(2, 4)
        x0 = rng.randint(0, S - s)
        y0 = rng.randint(0, S - s)
        for y in range(y0, y0 + s):
            for x in range(x0, x0 + s):
                zet(px, x, y, _schaduw(c2, rng.randint(-8, 8)))
    for i in range(S):                 # donkere rand
        zet(px, i, 0, _schaduw(c1, -25))
        zet(px, i, S - 1, _schaduw(c1, -25))
        zet(px, 0, i, _schaduw(c1, -25))
        zet(px, S - 1, i, _schaduw(c1, -25))


def solid(px, rng, c1, var=8, **_):
    """Metaal-blok: bijna effen met een glans-lijn."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-var, var)))
    for i in range(S):                 # diagonale glans
        zet(px, i, i, _schaduw(c1, 40))


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
        zet(px, x, 1, c2)
        zet(px, x, S - 2, c2)


def dots(px, rng, c1, c2, **_):
    """Paddenstoel: gekleurd met witte stippen."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-8, 8)))
    for _ in range(5):
        cx = rng.randint(2, S - 3)
        cy = rng.randint(2, S - 3)
        r = rng.randint(1, 2)
        for y in range(cy - r, cy + r + 1):
            for x in range(cx - r, cx + r + 1):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r + 1:
                    zet(px, x, y, c2)


def stripes(px, rng, c1, c2, **_):
    """Meloen: staande strepen in twee groentinten."""
    for x in range(S):
        kleur = c1 if (x // 2) % 2 == 0 else c2
        for y in range(S):
            zet(px, x, y, _schaduw(kleur, rng.randint(-10, 10)))


def hay(px, rng, c1, c2, **_):
    """Hooibaal: liggende strootjes."""
    for y in range(S):
        kleur = c1 if (y // 2) % 2 == 0 else c2
        for x in range(S):
            zet(px, x, y, _schaduw(kleur, rng.randint(-12, 12)))
    for x in range(0, S, 7):
        for y in range(S):
            zet(px, x, y, _schaduw(c2, -10))


def pumpkin(px, rng, c1, c2, **_):
    """Pompoen: oranje met staande ribbels."""
    for x in range(S):
        kleur = c1 if (x % 4) != 0 else c2
        for y in range(S):
            zet(px, x, y, _schaduw(kleur, rng.randint(-10, 10)))


def lava(px, rng, c1, c2, **_):
    """Lava: donkere gloed met felle blobjes."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-20, 10)))
    for _ in range(6):
        cx = rng.randint(1, S - 2)
        cy = rng.randint(1, S - 2)
        r = rng.randint(1, 2)
        for y in range(cy - r, cy + r + 1):
            for x in range(cx - r, cx + r + 1):
                zet(px, x, y, _schaduw(c2, rng.randint(-15, 15)))


def ice(px, rng, c1, c2, **_):
    """IJs: lichtblauw met barstjes."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-8, 8)))
    for _ in range(4):
        x = rng.randint(0, S - 1)
        y = rng.randint(0, S - 1)
        for _stap in range(rng.randint(3, 6)):
            zet(px, x, y, c2)
            x += rng.choice([-1, 0, 1])
            y += rng.choice([0, 1])


def glow(px, rng, c1, c2, **_):
    """Glowsteen: warme kleur met lichtpuntjes."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-10, 10)))
    for _ in range(7):
        zet(px, rng.randint(1, S - 2), rng.randint(1, S - 2), c2)


def tnt(px, rng, c1, c2, **_):
    """TNT: rood met een witte band in het midden."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-10, 10)))
    for y in range(6, 10):             # witte band
        for x in range(S):
            zet(px, x, y, c2)
    for x in range(2, S, 3):           # streepjes (lijkt op letters)
        zet(px, x, 7, _schaduw(c1, -30))
        zet(px, x, 8, _schaduw(c1, -30))


def sponge(px, rng, c1, c2, **_):
    """Spons: geel met donkere gaatjes."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-12, 12)))
    for _ in range(11):
        zet(px, rng.randint(1, S - 2), rng.randint(1, S - 2), c2)


def bookshelf(px, rng, c1, c2, **_):
    """Boekenkast: hout met gekleurde boeken in het midden."""
    for y in range(S):
        for x in range(S):
            zet(px, x, y, _schaduw(c1, rng.randint(-8, 8)))
    boek_kleuren = [(180, 50, 50), (50, 90, 180), (60, 160, 70),
                    (200, 180, 60), (150, 60, 160)]
    for x in range(1, S - 1):          # staande boeken
        if rng.random() < 0.8:
            kleur = rng.choice(boek_kleuren)
            for y in range(4, S - 4):
                zet(px, x, y, _schaduw(kleur, rng.randint(-15, 15)))
    for x in range(S):                 # plank-lijnen
        zet(px, x, 3, c2)
        zet(px, x, S - 4, c2)


# Welke functie hoort bij welke stijl?
STIJLEN = {
    'speckle': speckle, 'gras': gras, 'leaves': leaves, 'planks': planks,
    'bark': bark, 'brick': brick, 'cobble': cobble, 'ore': ore, 'gem': gem,
    'solid': solid, 'wool': wool, 'sandstone': sandstone, 'dots': dots,
    'stripes': stripes, 'hay': hay, 'pumpkin': pumpkin, 'lava': lava,
    'ice': ice, 'glow': glow, 'tnt': tnt, 'sponge': sponge, 'bookshelf': bookshelf,
}


def maak_alle_textures():
    """Maakt alle plaatjes en zet ze in de map assets/textures."""
    map_pad = os.path.join('assets', 'textures')
    os.makedirs(map_pad, exist_ok=True)

    for d in TEXTUUR_DEFS:
        naam = d['naam']
        stijl = d['stijl']
        functie = STIJLEN[stijl]
        # Elk plaatje krijgt altijd hetzelfde 'toeval' (op basis van de naam),
        # zodat het elke keer precies hetzelfde plaatje wordt.
        rng = random.Random(naam)
        img = Image.new('RGBA', (S, S), (0, 0, 0, 255))
        px = img.load()
        # De losse gegevens (c1, c2, var) doorgeven aan de teken-functie.
        functie(px, rng, **{k: v for k, v in d.items()
                            if k not in ('naam', 'stijl')})
        img.save(os.path.join(map_pad, naam + '.png'))

    print(f"Klaar! {len(TEXTUUR_DEFS)} plaatjes gemaakt in {map_pad}")


if __name__ == '__main__':
    maak_alle_textures()

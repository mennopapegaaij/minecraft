from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
from perlin_noise import PerlinNoise
import random
import math

app = Ursina()

# --- Instellingen ---
WERELD_GROOTTE = 30   # De wereld is 30 x 30 blokken groot
WERELD_DIEPTE  = 6    # Hoe diep de grond gaat

# Willekeurig zaad: elke keer een andere wereld!
WERELD_ZAAD = random.randint(1, 9999)
print(f"Wereld zaad: {WERELD_ZAAD}  (bewaar dit getal voor dezelfde wereld)")

# Drie lagen ruis: grote bergen + middelgrote heuvels + kleine details
ruis_groot  = PerlinNoise(octaves=3,  seed=WERELD_ZAAD)
ruis_midden = PerlinNoise(octaves=6,  seed=WERELD_ZAAD + 1)
ruis_klein  = PerlinNoise(octaves=12, seed=WERELD_ZAAD + 2)

# --- Kleuren van de blokken ---
KLEUREN = {
    'gras':   color.rgb(106, 170, 60),
    'aarde':  color.rgb(134, 96, 67),
    'steen':  color.rgb(128, 128, 128),
    'hout':   color.rgb(101, 67, 33),
    'blad':   color.rgb(34, 120, 34),
    'zand':   color.rgb(210, 190, 140),
    'sneeuw': color.rgb(230, 230, 250),
}

# Lijst van alle blokken in de wereld
blokken = []

# Welk blok de speler in de hand heeft
huidig_blok = 'gras'


class Blok(Button):
    """Een enkel blok in de wereld."""

    def __init__(self, positie, blok_type='gras'):
        kleur = KLEUREN.get(blok_type, color.white)
        super().__init__(
            parent=scene,
            position=positie,
            model='cube',
            origin_y=0.5,       # Positie is de ONDERKANT van het blok
            texture='white_cube',
            color=kleur,
            highlight_color=color.lime,
        )
        self.blok_type = blok_type
        blokken.append(self)

    def input(self, toets):
        if self.hovered:
            if toets == 'left mouse down':
                # Blok afbreken
                blokken.remove(self)
                destroy(self)
            if toets == 'right mouse down':
                # Blok plaatsen naast dit blok
                Blok(positie=self.position + mouse.normal, blok_type=huidig_blok)


def hoogte_op(x, z):
    """Berekent de grondhoogte op (x, z) met Perlin ruis — zo krijg je echte bergen."""
    # Schaal de positie zodat de wereld er mooi uitziet
    nx = x / WERELD_GROOTTE
    nz = z / WERELD_GROOTTE
    # Combineer drie lagen voor een natuurlijk landschap
    h = (ruis_groot([nx, nz])  * 14 +   # Grote bergen
         ruis_midden([nx, nz]) *  5 +   # Middelgrote heuvels
         ruis_klein([nx, nz])  *  1.5)  # Kleine golfjes
    # Verschuif naar basisgrond 10 (hoogte is altijd positief)
    return int(h + 10)


def bepaal_blok_type(y, grond_hoogte):
    """Geeft het juiste bloktype terug op basis van hoogte."""
    if y == grond_hoogte:
        if y <= 5:
            return 'zand'    # Laag land bij water = zand
        elif y >= 18:
            return 'sneeuw'  # Hoge bergtoppen = sneeuw
        else:
            return 'gras'
    elif y >= grond_hoogte - 3:
        return 'aarde'
    else:
        return 'steen'


def is_grot(x, y, z, grond_hoogte):
    """Bepaalt of er op deze plek een grot is."""
    # Grotten beginnen pas 4 lagen onder de grond
    if y >= grond_hoogte - 3:
        return False
    # Wiskundige golven maken holtes in de steen
    golfwaarde = (
        math.sin(x * 0.5 + WERELD_ZAAD * 0.01) * math.cos(z * 0.5) +
        math.sin(y * 0.8 + x * 0.3) +
        math.cos(y * 0.4 + z * 0.3)
    )
    return golfwaarde > 1.4


def plaats_boom(x, grond_hoogte, z):
    """Plaatst een boom op de gegeven plek."""
    stam_hoogte = random.randint(3, 5)
    # Stam
    for y in range(1, stam_hoogte + 1):
        Blok(positie=(x, grond_hoogte + y, z), blok_type='hout')
    # Bladeren als een ronde bol bovenop de stam
    top = grond_hoogte + stam_hoogte
    for bx in range(-2, 3):
        for by in range(0, 4):
            for bz in range(-2, 3):
                afstand = abs(bx) + abs(bz) + abs(by) * 0.7
                if afstand <= 2.5:
                    if not (bx == 0 and bz == 0 and by < 2):
                        Blok(positie=(x + bx, top + by, z + bz), blok_type='blad')


SPAWN_X = WERELD_GROOTTE // 2
SPAWN_Z = WERELD_GROOTTE // 2


def maak_wereld():
    """Maakt de hele 3D wereld: bergen, grotten en bomen."""
    for x in range(WERELD_GROOTTE):
        for z in range(WERELD_GROOTTE):
            grond_hoogte = hoogte_op(x, z)

            # Bovenste laag (gras, zand of sneeuw afhankelijk van hoogte)
            blok_type = bepaal_blok_type(grond_hoogte, grond_hoogte)
            Blok(positie=(x, grond_hoogte, z), blok_type=blok_type)

            # Lagen eronder (aarde en steen, met grotten)
            for y in range(grond_hoogte - 1, grond_hoogte - WERELD_DIEPTE, -1):
                if is_grot(x, y, z, grond_hoogte):
                    continue  # Hier is een grot, geen blok plaatsen
                Blok(positie=(x, y, z), blok_type=bepaal_blok_type(y, grond_hoogte))

            # Kleine kans op een boom (alleen op gras, niet te steil, niet op de startplek)
            is_startplek = (x == SPAWN_X and z == SPAWN_Z)
            if not is_startplek and blok_type == 'gras' and random.random() < 0.05:
                hoogte_links  = hoogte_op(max(0, x - 1), z)
                hoogte_rechts = hoogte_op(min(WERELD_GROOTTE - 1, x + 1), z)
                if abs(grond_hoogte - hoogte_links) <= 1 and abs(grond_hoogte - hoogte_rechts) <= 1:
                    plaats_boom(x, grond_hoogte, z)


# --- Maak de wereld aan ---
print("Wereld wordt aangemaakt, even wachten...")
maak_wereld()
print("Klaar!")

# --- Zet de speler bovenop de grond in het midden ---
speler = FirstPersonController()
grond = hoogte_op(SPAWN_X, SPAWN_Z)
# Spawn EXACT op het grondblok — de FirstPersonController detecteert grond
# pas als afstand <= height+0.1 (dus max 0.1 boven het blok)
speler.position = (SPAWN_X, grond, SPAWN_Z)

# --- Lucht ---
Sky()

# --- Uitleg op het scherm ---
Text(
    text="[1] Gras  [2] Aarde  [3] Steen  [4] Hout  [5] Blad  [6] Zand  [7] Sneeuw\n"
         "Linker muis = afbreken   Rechter muis = plaatsen\n"
         "WASD = lopen   Spatie = springen   Escape = stoppen",
    position=(-0.85, 0.47),
    scale=1.1,
    background=True,
)


def input(toets):
    global huidig_blok

    # Kies welk blok je in de hand hebt met de cijfertoetsen
    if toets == '1': huidig_blok = 'gras';   print("Je hebt nu: GRAS")
    if toets == '2': huidig_blok = 'aarde';  print("Je hebt nu: AARDE")
    if toets == '3': huidig_blok = 'steen';  print("Je hebt nu: STEEN")
    if toets == '4': huidig_blok = 'hout';   print("Je hebt nu: HOUT")
    if toets == '5': huidig_blok = 'blad';   print("Je hebt nu: BLAD")
    if toets == '6': huidig_blok = 'zand';   print("Je hebt nu: ZAND")
    if toets == '7': huidig_blok = 'sneeuw'; print("Je hebt nu: SNEEUW")
    if toets == 'escape':
        quit()


app.run()

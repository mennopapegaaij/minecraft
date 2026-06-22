from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import random
import math

app = Ursina()

# --- Instellingen ---
WERELD_GROOTTE = 30   # De wereld is 30 x 30 blokken groot
WERELD_DIEPTE = 10    # Hoe diep de grond gaat

# --- Kleuren van de blokken ---
KLEUREN = {
    'gras': color.rgb(106, 170, 60),
    'aarde': color.rgb(134, 96, 67),
    'steen': color.rgb(128, 128, 128),
    'hout':  color.rgb(101, 67, 33),
    'blad':  color.rgb(34, 120, 34),
}

# Lijst van alle blokken
blokken = []

# Welk blok de speler in de hand heeft
huidig_blok = 'gras'


class Blok(Button):
    """Een blok in de wereld."""

    def __init__(self, positie, blok_type='gras'):
        kleur = KLEUREN.get(blok_type, color.white)
        super().__init__(
            parent=scene,
            position=positie,
            model='cube',
            origin_y=0.5,
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
    """Berekent hoe hoog het land is op positie x, z — zo maken we bergen."""
    # Meerdere golven door elkaar = natuurlijk landschap met bergen
    h = 5                                       # Basisgrond
    h += math.sin(x * 0.25) * 4                # Grote bergen
    h += math.cos(z * 0.2) * 4                 # Bergen in andere richting
    h += math.sin(x * 0.1 + z * 0.1) * 6      # Nog grotere bergen
    h += math.sin(x * 0.6) * 1.5              # Kleine heuveltjes
    h += math.cos(z * 0.7 + x * 0.3) * 1.5   # Nog meer kleine heuveltjes
    return int(h)


def is_grot(x, y, z, grond_hoogte):
    """Bepaalt of er op deze plek een grot zit."""
    # Grotten zijn alleen diep onder de grond
    if y >= grond_hoogte - 4:
        return False
    # Wiskundige golven maken holtes (grotten) in de steen
    golfwaarde = (
        math.sin(x * 0.6) * math.cos(z * 0.6) +
        math.sin(y * 0.9 + x * 0.4) +
        math.cos(y * 0.5 + z * 0.4)
    )
    return golfwaarde > 1.3  # Hoge waarde = grot


def plaats_boom(x, grond_hoogte, z):
    """Plaatst een boom op de gegeven plek."""
    stam_hoogte = random.randint(3, 5)

    # Teken de stam
    for y in range(1, stam_hoogte + 1):
        Blok(positie=(x, grond_hoogte + y, z), blok_type='hout')

    # Teken de bladeren als een bol bovenop de stam
    top = grond_hoogte + stam_hoogte
    for bx in range(-2, 3):
        for by in range(0, 4):
            for bz in range(-2, 3):
                # Maak een ronde wolk van bladeren
                afstand = abs(bx) + abs(bz) + abs(by) * 0.7
                if afstand <= 2.5:
                    # Zorg dat bladeren niet de stam overlappen
                    if not (bx == 0 and bz == 0 and by < 2):
                        Blok(positie=(x + bx, top + by, z + bz), blok_type='blad')


def maak_wereld():
    """Maakt de hele 3D wereld: bergen, grotten en bomen."""
    for x in range(WERELD_GROOTTE):
        for z in range(WERELD_GROOTTE):
            grond_hoogte = hoogte_op(x, z)

            # Bovenste laag = gras
            Blok(positie=(x, grond_hoogte, z), blok_type='gras')

            # Lagen eronder
            for y in range(grond_hoogte - 1, grond_hoogte - WERELD_DIEPTE, -1):
                # Controleer of hier een grot is — zo ja, geen blok plaatsen
                if is_grot(x, y, z, grond_hoogte):
                    continue

                if y >= grond_hoogte - 3:
                    Blok(positie=(x, y, z), blok_type='aarde')
                else:
                    Blok(positie=(x, y, z), blok_type='steen')

            # Kleine kans op een boom (alleen op vlakke plekken)
            if random.random() < 0.06:
                # Controleer of het niet te steil is voor een boom
                hoogte_links = hoogte_op(max(0, x - 1), z)
                hoogte_rechts = hoogte_op(min(WERELD_GROOTTE - 1, x + 1), z)
                if abs(grond_hoogte - hoogte_links) <= 1 and abs(grond_hoogte - hoogte_rechts) <= 1:
                    plaats_boom(x, grond_hoogte, z)


# --- Maak de wereld ---
print("Wereld wordt aangemaakt, even wachten...")
maak_wereld()
print("Klaar!")

# --- Speler ---
speler = FirstPersonController()
# Zet de speler in het midden bovenop de wereld
midden = WERELD_GROOTTE // 2
speler.position = (midden, hoogte_op(midden, midden) + 5, midden)

# --- Lucht ---
Sky()

# --- Uitleg op het scherm ---
Text(
    text="[1] Gras  [2] Aarde  [3] Steen  [4] Hout  [5] Blad\n"
         "Linker muis = afbreken   Rechter muis = plaatsen\n"
         "WASD = lopen   Spatie = springen",
    position=(-0.85, 0.47),
    scale=1.1,
    background=True,
)


def input(toets):
    global huidig_blok

    # Kies welk blok je in de hand hebt
    if toets == '1':
        huidig_blok = 'gras'
        print("Je hebt nu: GRAS")
    if toets == '2':
        huidig_blok = 'aarde'
        print("Je hebt nu: AARDE")
    if toets == '3':
        huidig_blok = 'steen'
        print("Je hebt nu: STEEN")
    if toets == '4':
        huidig_blok = 'hout'
        print("Je hebt nu: HOUT")
    if toets == '5':
        huidig_blok = 'blad'
        print("Je hebt nu: BLAD")

    if toets == 'escape':
        quit()


app.run()

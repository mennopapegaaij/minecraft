from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import random

app = Ursina()

# --- Instellingen ---
WERELD_GROOTTE = 20   # De wereld is 20 x 20 blokken groot
WERELD_DIEPTE = 5     # Hoe veel lagen de grond heeft

# --- Kleuren van de blokken ---
KLEUR_GRAS = color.rgb(106, 170, 60)
KLEUR_AARDE = color.rgb(134, 96, 67)
KLEUR_STEEN = color.rgb(128, 128, 128)

# Lijst van alle blokken in de wereld
blokken = []

# Welk type blok de speler in de hand heeft
huidig_blok = 'gras'


class Blok(Button):
    """Een blok in de wereld. Je kunt erop klikken om het af te breken of er naast te plaatsen."""

    def __init__(self, positie, blok_type='gras'):
        # Kies de kleur op basis van het type blok
        if blok_type == 'gras':
            kleur = KLEUR_GRAS
        elif blok_type == 'aarde':
            kleur = KLEUR_AARDE
        else:
            kleur = KLEUR_STEEN

        super().__init__(
            parent=scene,
            position=positie,
            model='cube',           # Een kubus (blok)
            origin_y=0.5,
            texture='white_cube',   # Witte textuur met randen
            color=kleur,
            highlight_color=color.lime,  # Wordt groen als je erop kijkt
        )
        self.blok_type = blok_type
        blokken.append(self)

    def input(self, toets):
        if self.hovered:  # Als de muis over dit blok gaat
            if toets == 'left mouse down':
                # Linker muisknop: blok afbreken
                blokken.remove(self)
                destroy(self)

            if toets == 'right mouse down':
                # Rechter muisknop: nieuw blok plaatsen naast dit blok
                nieuw_blok = Blok(
                    positie=self.position + mouse.normal,
                    blok_type=huidig_blok
                )


def maak_wereld():
    """Maakt de 3D wereld met blokken."""
    for x in range(WERELD_GROOTTE):
        for z in range(WERELD_GROOTTE):
            # Kies een willekeurige hoogte voor het landschap
            hoogte = random.randint(0, 3)

            # Bovenste laag = gras
            Blok(positie=(x, hoogte, z), blok_type='gras')

            # Lagen aarde daaronder
            for y in range(hoogte - 1, hoogte - WERELD_DIEPTE, -1):
                if y > hoogte - 3:
                    Blok(positie=(x, y, z), blok_type='aarde')
                else:
                    Blok(positie=(x, y, z), blok_type='steen')


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

    # Druk op Escape om af te sluiten
    if toets == 'escape':
        quit()


# --- Maak de wereld ---
maak_wereld()

# --- De speler ---
speler = FirstPersonController()
speler.position = (WERELD_GROOTTE // 2, 6, WERELD_GROOTTE // 2)  # Zet de speler bovenop de wereld

# --- Lucht kleur ---
sky = Sky()

# --- Uitleg op het scherm ---
uitleg = Text(
    text="[1] Gras  [2] Aarde  [3] Steen\nLinks klikken = afbreken  Rechts klikken = plaatsen",
    position=(-0.85, 0.45),
    scale=1.2,
    background=True,
)

app.run()

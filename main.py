import pygame
import random

# --- Instellingen ---
SCHERM_BREEDTE = 800
SCHERM_HOOGTE = 600
BLOK_GROOTTE = 40  # Hoe groot elk blok is in pixels

# --- Kleuren van de blokken ---
KLEUR_LUCHT = (135, 206, 235)   # Lichtblauw
KLEUR_GRAS = (106, 170, 60)     # Groen
KLEUR_AARDE = (134, 96, 67)     # Bruin
KLEUR_STEEN = (128, 128, 128)   # Grijs
KLEUR_BEDROCK = (50, 50, 50)    # Donkergrijs
KLEUR_RAND = (0, 0, 0)          # Zwart (randen van blokken)

# --- Soorten blokken (als nummers) ---
LUCHT = 0
GRAS = 1
AARDE = 2
STEEN = 3
BEDROCK = 4

# --- Hoe groot de wereld is ---
WERELD_BREEDTE = 100   # 100 blokken breed
WERELD_HOOGTE = 50     # 50 blokken hoog


def maak_wereld():
    """Maakt een nieuwe wereld met blokken."""
    # Begin met een lege wereld (alles is lucht)
    wereld = [[LUCHT for _ in range(WERELD_BREEDTE)] for _ in range(WERELD_HOOGTE)]

    for x in range(WERELD_BREEDTE):
        # Kies een willekeurige hoogte voor het landschap
        grond_hoogte = random.randint(20, 28)

        for y in range(WERELD_HOOGTE):
            if y == grond_hoogte:
                wereld[y][x] = GRAS       # Bovenste laag = gras
            elif y < grond_hoogte + 4:
                wereld[y][x] = AARDE      # Daarna 4 lagen aarde
            elif y < WERELD_HOOGTE - 1:
                wereld[y][x] = STEEN      # De rest is steen
            else:
                wereld[y][x] = BEDROCK    # Onderste laag = bedrock

    return wereld


def teken_wereld(scherm, wereld, camera_x, camera_y):
    """Tekent alle zichtbare blokken op het scherm."""
    # Hoeveel blokken passen er op het scherm?
    blokken_x = SCHERM_BREEDTE // BLOK_GROOTTE + 2
    blokken_y = SCHERM_HOOGTE // BLOK_GROOTTE + 2

    # Begin bij het eerste zichtbare blok
    start_x = camera_x // BLOK_GROOTTE
    start_y = camera_y // BLOK_GROOTTE

    for y in range(start_y, min(start_y + blokken_y, WERELD_HOOGTE)):
        for x in range(start_x, min(start_x + blokken_x, WERELD_BREEDTE)):
            blok = wereld[y][x]

            # Kies de juiste kleur
            if blok == LUCHT:
                continue  # Lucht hoeven we niet te tekenen
            elif blok == GRAS:
                kleur = KLEUR_GRAS
            elif blok == AARDE:
                kleur = KLEUR_AARDE
            elif blok == STEEN:
                kleur = KLEUR_STEEN
            elif blok == BEDROCK:
                kleur = KLEUR_BEDROCK

            # Bereken waar op het scherm dit blok staat
            scherm_x = x * BLOK_GROOTTE - camera_x
            scherm_y = y * BLOK_GROOTTE - camera_y

            # Teken het blok
            pygame.draw.rect(scherm, kleur, (scherm_x, scherm_y, BLOK_GROOTTE, BLOK_GROOTTE))
            # Teken een randje eromheen
            pygame.draw.rect(scherm, KLEUR_RAND, (scherm_x, scherm_y, BLOK_GROOTTE, BLOK_GROOTTE), 1)


def main():
    pygame.init()
    scherm = pygame.display.set_mode((SCHERM_BREEDTE, SCHERM_HOOGTE))
    pygame.display.set_caption("Mijn Minecraft!")
    klok = pygame.time.Clock()

    # Maak de wereld aan
    wereld = maak_wereld()

    # Camera positie (hoeveel pixels zijn we al naar rechts/beneden)
    camera_x = 0
    camera_y = 0
    CAMERA_SNELHEID = 10

    # Spel-lus
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return

        # Beweeg de camera met de pijltjestoetsen
        toetsen = pygame.key.get_pressed()
        if toetsen[pygame.K_LEFT]:
            camera_x -= CAMERA_SNELHEID
        if toetsen[pygame.K_RIGHT]:
            camera_x += CAMERA_SNELHEID
        if toetsen[pygame.K_UP]:
            camera_y -= CAMERA_SNELHEID
        if toetsen[pygame.K_DOWN]:
            camera_y += CAMERA_SNELHEID

        # Zorg dat de camera niet buiten de wereld gaat
        camera_x = max(0, min(camera_x, WERELD_BREEDTE * BLOK_GROOTTE - SCHERM_BREEDTE))
        camera_y = max(0, min(camera_y, WERELD_HOOGTE * BLOK_GROOTTE - SCHERM_HOOGTE))

        # Teken alles
        scherm.fill(KLEUR_LUCHT)  # Lucht achtergrond
        teken_wereld(scherm, wereld, camera_x, camera_y)

        pygame.display.flip()
        klok.tick(60)  # 60 frames per seconde


main()

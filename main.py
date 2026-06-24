from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
from perlin_noise import PerlinNoise
import random
import math
import collections

app = Ursina()

# --- Instellingen ---
CHUNK_GROOTTE  = 8    # Een stukje wereld is 8x8 blokken groot
RENDER_AFSTAND = 2    # Hoeveel stukjes rondom de speler worden geladen (2 = 5x5 stukjes)
WERELD_DIEPTE  = 4    # Hoe diep de grond gaat
BLOKKEN_FRAME  = 40   # Blokken per frame aanmaken (hogere waarde = sneller maar meer haperingen)

# Willekeurig zaad: elke keer een andere wereld!
WERELD_ZAAD = random.randint(1, 9999)
print(f"Wereld zaad: {WERELD_ZAAD}")

# Drie lagen ruis voor een natuurlijk landschap
ruis_groot  = PerlinNoise(octaves=3,  seed=WERELD_ZAAD)
ruis_midden = PerlinNoise(octaves=6,  seed=WERELD_ZAAD + 1)
ruis_klein  = PerlinNoise(octaves=12, seed=WERELD_ZAAD + 2)

# --- Kleuren van de blokken (waarden van 0 tot 1!) ---
KLEUREN = {
    'gras':   color.rgb(106/255, 170/255,  60/255),
    'aarde':  color.rgb(134/255,  96/255,  67/255),
    'steen':  color.rgb(128/255, 128/255, 128/255),
    'hout':   color.rgb(101/255,  67/255,  33/255),
    'blad':   color.rgb( 34/255, 120/255,  34/255),
    'zand':   color.rgb(210/255, 190/255, 140/255),
    'sneeuw': color.rgb(230/255, 230/255, 250/255),
}

# Welk blok de speler in de hand heeft
huidig_blok = 'gras'

# Bijhouden welke stukjes wereld geladen zijn
geladen_chunks  = {}                    # (cx, cz) -> verzameling van blokken
laad_wachtrij   = collections.deque()   # Blokken die nog aangemaakt moeten worden
vorige_chunk    = None                  # Was de speler in dit chunk in de vorige frame?


def chunk_van_pos(x, z):
    """Berekent in welk stukje wereld een positie ligt."""
    return (math.floor(x / CHUNK_GROOTTE), math.floor(z / CHUNK_GROOTTE))


class Blok(Button):
    """Een enkel blok in de wereld."""

    def __init__(self, positie, blok_type='gras', chunk_sleutel=None):
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
        self.blok_type    = blok_type
        self.chunk_sleutel = chunk_sleutel  # In welk stukje wereld zit dit blok?

    def input(self, toets):
        if self.hovered:
            if toets == 'left mouse down':
                # Blok afbreken
                if self.chunk_sleutel in geladen_chunks:
                    geladen_chunks[self.chunk_sleutel].discard(self)
                destroy(self)

            if toets == 'right mouse down':
                # Blok plaatsen naast dit blok
                nieuwe_pos   = self.position + mouse.normal
                nieuwe_chunk = chunk_van_pos(nieuwe_pos.x, nieuwe_pos.z)
                nieuw = Blok(positie=nieuwe_pos, blok_type=huidig_blok, chunk_sleutel=nieuwe_chunk)
                if nieuwe_chunk in geladen_chunks:
                    geladen_chunks[nieuwe_chunk].add(nieuw)


def hoogte_op(x, z):
    """Berekent de grondhoogte op positie (x, z) met Perlin ruis."""
    nx = x * 0.04
    nz = z * 0.04
    h = (ruis_groot([nx, nz])  * 14 +
         ruis_midden([nx, nz]) *  5 +
         ruis_klein([nx, nz])  *  1.5)
    return int(h + 10)


def bepaal_blok_type(y, grond_hoogte):
    """Geeft het juiste bloktype terug op basis van de hoogte."""
    if y == grond_hoogte:
        if y <= 5:   return 'zand'
        if y >= 18:  return 'sneeuw'
        return 'gras'
    if y >= grond_hoogte - 3:
        return 'aarde'
    return 'steen'


def is_grot(x, y, z, grond_hoogte):
    """Bepaalt of er op deze plek een grot is."""
    if y >= grond_hoogte - 3:
        return False
    golfwaarde = (
        math.sin(x * 0.5 + WERELD_ZAAD * 0.01) * math.cos(z * 0.5) +
        math.sin(y * 0.8 + x * 0.3) +
        math.cos(y * 0.4 + z * 0.3)
    )
    return golfwaarde > 1.4


def voeg_boom_toe(x, grond, z, sleutel, rng):
    """Voegt een boom toe aan de laadwachtrij."""
    stam_h = rng.randint(3, 5)
    for y in range(1, stam_h + 1):
        laad_wachtrij.append(((x, grond + y, z), 'hout', sleutel))
    top = grond + stam_h
    for bx in range(-2, 3):
        for by in range(0, 4):
            for bz in range(-2, 3):
                if abs(bx) + abs(bz) + abs(by) * 0.7 <= 2.5:
                    if not (bx == 0 and bz == 0 and by < 2):
                        laad_wachtrij.append(((x + bx, top + by, z + bz), 'blad', sleutel))


def laad_chunk(cx, cz):
    """Voegt alle blokken van een stukje wereld toe aan de laadwachtrij."""
    if (cx, cz) in geladen_chunks:
        return  # Dit stukje is al (aan het) laden

    geladen_chunks[(cx, cz)] = set()
    sleutel = (cx, cz)
    # Vaste willekeur per chunk, zodat bomen altijd op dezelfde plek staan
    rng = random.Random(WERELD_ZAAD + cx * 73856093 + cz * 19349663)

    for x in range(cx * CHUNK_GROOTTE, (cx + 1) * CHUNK_GROOTTE):
        for z in range(cz * CHUNK_GROOTTE, (cz + 1) * CHUNK_GROOTTE):
            grond_hoogte = hoogte_op(x, z)
            blok_type    = bepaal_blok_type(grond_hoogte, grond_hoogte)

            # Bovenste laag
            laad_wachtrij.append(((x, grond_hoogte, z), blok_type, sleutel))

            # Lagen eronder
            for y in range(grond_hoogte - 1, grond_hoogte - WERELD_DIEPTE, -1):
                if not is_grot(x, y, z, grond_hoogte):
                    laad_wachtrij.append(((x, y, z), bepaal_blok_type(y, grond_hoogte), sleutel))

            # Soms een boom (niet op de startpositie)
            is_startplek = (cx == 0 and cz == 0 and x == 0 and z == 0)
            if not is_startplek and blok_type == 'gras' and rng.random() < 0.05:
                if abs(grond_hoogte - hoogte_op(x - 1, z)) <= 1:
                    if abs(grond_hoogte - hoogte_op(x + 1, z)) <= 1:
                        voeg_boom_toe(x, grond_hoogte, z, sleutel, rng)


def verwijder_chunk(cx, cz):
    """Verwijdert alle blokken van een stukje wereld."""
    if (cx, cz) not in geladen_chunks:
        return
    for blok in geladen_chunks.pop((cx, cz)):
        destroy(blok)


# --- Startpositie ---
SPAWN_X = 0
SPAWN_Z = 0
spawn_grond  = hoogte_op(SPAWN_X, SPAWN_Z)
start_chunk  = chunk_van_pos(SPAWN_X, SPAWN_Z)

# Laad de oppervlakte van het startchunk DIRECT, zodat de speler niet valt
geladen_chunks[start_chunk] = set()
start_rng = random.Random(WERELD_ZAAD + start_chunk[0] * 73856093 + start_chunk[1] * 19349663)

for sx in range(start_chunk[0] * CHUNK_GROOTTE, (start_chunk[0] + 1) * CHUNK_GROOTTE):
    for sz in range(start_chunk[1] * CHUNK_GROOTTE, (start_chunk[1] + 1) * CHUNK_GROOTTE):
        gh = hoogte_op(sx, sz)
        bt = bepaal_blok_type(gh, gh)
        b  = Blok(positie=(sx, gh, sz), blok_type=bt, chunk_sleutel=start_chunk)
        geladen_chunks[start_chunk].add(b)
        # Stel de ondergrond in de wachtrij
        for y in range(gh - 1, gh - WERELD_DIEPTE, -1):
            if not is_grot(sx, y, sz, gh):
                laad_wachtrij.append(((sx, y, sz), bepaal_blok_type(y, gh), start_chunk))
        # Bomen (niet op startplek)
        if not (sx == SPAWN_X and sz == SPAWN_Z) and bt == 'gras' and start_rng.random() < 0.05:
            if abs(gh - hoogte_op(sx - 1, sz)) <= 1 and abs(gh - hoogte_op(sx + 1, sz)) <= 1:
                voeg_boom_toe(sx, gh, sz, start_chunk, start_rng)

# Stel omliggende chunks in de wachtrij
for dcx in range(-RENDER_AFSTAND, RENDER_AFSTAND + 1):
    for dcz in range(-RENDER_AFSTAND, RENDER_AFSTAND + 1):
        chunk = (start_chunk[0] + dcx, start_chunk[1] + dcz)
        if chunk != start_chunk:
            laad_chunk(*chunk)

# --- Speler ---
speler = FirstPersonController()
speler.position = (SPAWN_X, spawn_grond, SPAWN_Z)

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


def update():
    """Wordt elke frame aangeroepen: laad blokken en beheer chunks."""
    global vorige_chunk

    # Maak een paar blokken aan uit de laadwachtrij
    for _ in range(BLOKKEN_FRAME):
        if not laad_wachtrij:
            break
        positie, blok_type, sleutel = laad_wachtrij.popleft()
        if sleutel not in geladen_chunks:
            continue  # Dit stukje is al verwijderd, sla over
        blok = Blok(positie=positie, blok_type=blok_type, chunk_sleutel=sleutel)
        geladen_chunks[sleutel].add(blok)

    # Controleer of de speler van stukje wereld is veranderd
    speler_chunk = chunk_van_pos(speler.x, speler.z)
    if speler_chunk == vorige_chunk:
        return  # Speler is nog in hetzelfde stukje, niets te doen
    vorige_chunk = speler_chunk
    cx, cz = speler_chunk

    # Laad nieuwe stukjes rondom de speler
    for dcx in range(-RENDER_AFSTAND, RENDER_AFSTAND + 1):
        for dcz in range(-RENDER_AFSTAND, RENDER_AFSTAND + 1):
            chunk = (cx + dcx, cz + dcz)
            if chunk not in geladen_chunks:
                laad_chunk(*chunk)

    # Verwijder stukjes die te ver weg zijn
    for chunk in list(geladen_chunks.keys()):
        if abs(chunk[0] - cx) > RENDER_AFSTAND + 1 or abs(chunk[1] - cz) > RENDER_AFSTAND + 1:
            verwijder_chunk(*chunk)


def input(toets):
    global huidig_blok
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

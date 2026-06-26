from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
from perlin_noise import PerlinNoise
import random
import math
import collections

app = Ursina()

# --- Instellingen ---
CHUNK_GROOTTE    = 8    # Een stukje wereld is 8x8 blokken groot
RENDER_AFSTAND   = 3    # Hoeveel stukjes rondom de speler je ziet (3 = 7x7 stukjes)
                        # Dankzij het Minecraft-trucje mag dit nu veel groter zijn!
WERELD_DIEPTE    = 4    # Hoe diep de grond gaat
DOEL_FPS         = 50   # Hoe snel we het spel willen laten draaien (beeldjes per seconde)

# Het spel mag niet sneller gaan dan DOEL_FPS (een soort maximumsnelheid).
from panda3d.core import ClockObject
spel_klok = ClockObject.getGlobalClock()
spel_klok.setMode(ClockObject.MLimited)
spel_klok.setFrameRate(DOEL_FPS)
# Belangrijk: nooit een grotere tijdstap nemen dan 1/30 seconde. Bij een korte
# hapering valt de speler anders in één keer zo ver dat hij DWARS DOOR de grond
# schiet. Met deze grens blijven de stapjes klein en blijf je netjes staan.
spel_klok.setMaxDt(1 / 30)

# Willekeurig zaad: elke keer een andere wereld!
WERELD_ZAAD = random.randint(1, 9999)
print(f"Wereld zaad: {WERELD_ZAAD}")

# Drie lagen ruis voor een natuurlijk landschap
ruis_groot  = PerlinNoise(octaves=3,  seed=WERELD_ZAAD)
ruis_midden = PerlinNoise(octaves=6,  seed=WERELD_ZAAD + 1)
ruis_klein  = PerlinNoise(octaves=12, seed=WERELD_ZAAD + 2)

# --- Kleuren van de blokken (waarden van 0 tot 1!) ---
KLEUREN = {
    'gras':     color.rgb(106/255, 170/255,  60/255),
    'aarde':    color.rgb(134/255,  96/255,  67/255),
    'steen':    color.rgb(128/255, 128/255, 128/255),
    'hout':     color.rgb(101/255,  67/255,  33/255),
    'planken':  color.rgb(160/255, 120/255,  70/255),
    'blad':     color.rgb( 34/255, 120/255,  34/255),
    'zand':     color.rgb(210/255, 190/255, 140/255),
    'sneeuw':   color.rgb(235/255, 235/255, 250/255),
    'baksteen': color.rgb(150/255,  60/255,  50/255),
    'glas':     color.rgba(200/255, 230/255, 255/255, 0.4),
    'goud':     color.rgb(250/255, 215/255,  60/255),
    'diamant':  color.rgb(110/255, 230/255, 230/255),
    'ijzer':    color.rgb(200/255, 200/255, 205/255),
    'smaragd':  color.rgb( 40/255, 200/255, 100/255),
    'robijn':   color.rgb(220/255,  40/255,  60/255),
    'kool':     color.rgb( 45/255,  45/255,  45/255),
    'lava':     color.rgb(240/255, 100/255,  20/255),
    'pompoen':  color.rgb(230/255, 140/255,  30/255),
    'mos':      color.rgb( 60/255, 110/255,  40/255),
    'paars':    color.rgb(140/255,  60/255, 200/255),
    'roze':     color.rgb(240/255, 140/255, 200/255),
    'water':    color.rgba(45/255, 110/255, 200/255, 0.6),
}

# De blokken die je kunt vasthouden en plaatsen (met muiswiel of cijfertoetsen)
BLOK_KEUZES = ['gras', 'aarde', 'steen', 'zand', 'hout', 'planken', 'blad',
               'baksteen', 'glas', 'sneeuw', 'goud', 'diamant', 'ijzer',
               'smaragd', 'robijn', 'kool', 'lava', 'pompoen', 'mos',
               'paars', 'roze']

WATER_NIVEAU = 6          # Tot welke hoogte staat er water in de lage plekken
blok_index   = 0          # Welk blok uit de lijst je vasthoudt
huidig_blok  = BLOK_KEUZES[blok_index]

# --- Het geheugen van de wereld ---
# 'wereld' is het grote telefoonboek: op welke plek (x, y, z) staat welk soort blok?
# Dit zijn alleen getallen, geen 3D-modellen. Heel licht voor de computer.
wereld          = {}                    # (x, y, z) -> bloktype, bv 'gras'
chunk_blokken   = {}                    # (cx, cz) -> dict met de blokken van dat stukje
chunk_modellen  = {}                    # (cx, cz) -> lijst met de samengeplakte 3D-modellen
bouw_wachtrij   = collections.deque()   # stukjes die nog een 3D-model moeten krijgen
weggehaald      = set()                 # plekken waar de speler een blok heeft weggesloopt
vorige_chunk    = None


def chunk_van_pos(x, z):
    """Berekent in welk stukje wereld een positie ligt."""
    return (math.floor(x / CHUNK_GROOTTE), math.floor(z / CHUNK_GROOTTE))


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


# Staan er grotten (holtes) diep onder de grond?
# Even uit gezet: grotten maken gaten waar je in valt en dan zie je void.
# Met grotten UIT is de wereld lekker solide, zodat je oneindig diep kunt graven.
# Wil je ze later terug? Zet GROTTEN_AAN op True (we maken ze dan eerst netter).
GROTTEN_AAN = False


def is_grot(x, y, z, grond_hoogte):
    """Bepaalt of er op deze plek een grot is."""
    if not GROTTEN_AAN:
        return False
    if y >= grond_hoogte - 3:
        return False
    golfwaarde = (
        math.sin(x * 0.5 + WERELD_ZAAD * 0.01) * math.cos(z * 0.5) +
        math.sin(y * 0.8 + x * 0.3) +
        math.cos(y * 0.4 + z * 0.3)
    )
    return golfwaarde > 1.4


# De 6 buren van een blok: rechts, links, boven, onder, voor, achter
BUREN = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]


def blok_zichtbaar(x, y, z):
    """Een blok hoef je alleen te tekenen als minstens één buur leeg is.
    Blokken die helemaal binnenin de berg zitten, zie je toch niet."""
    for dx, dy, dz in BUREN:
        if (x + dx, y + dy, z + dz) not in wereld:
            return True
    return False


def is_gevuld_wiskundig(x, y, z):
    """Volgens de WISKUNDIGE wereld: hoort hier vaste grond te zitten?
    Dit geldt oneindig diep naar beneden (behalve in grotten en in de lucht)."""
    grond = hoogte_op(x, z)
    if y > grond:
        return False                          # boven de grond = lucht
    return not is_grot(x, y, z, grond)         # in een grot = leeg, anders gevuld


def onthul_buren(pos):
    """Maakt de buur-blokken aan die door het graven zichtbaar worden.
    Zo zie je geen leegte (void) als je naar beneden graaft: de wereld
    'groeit' steeds een laagje dieper precies waar jij graaft. Oneindig diep!"""
    for dx, dy, dz in BUREN:
        buur = (pos[0] + dx, pos[1] + dy, pos[2] + dz)
        # Niet terugzetten: blokken die de speler zelf heeft weggesloopt
        if buur in weggehaald:
            continue
        if buur not in wereld and is_gevuld_wiskundig(*buur):
            grond = hoogte_op(buur[0], buur[2])
            t = bepaal_blok_type(buur[1], grond)
            wereld[buur] = t
            cx, cz = chunk_van_pos(buur[0], buur[2])
            chunk_blokken.setdefault((cx, cz), {})[buur] = t


def voeg_boom_toe(blokken, x, grond, z, rng):
    """Zet een boom in de blokken-lijst van een stukje wereld."""
    stam_h = rng.randint(3, 5)
    for y in range(1, stam_h + 1):
        blokken[(x, grond + y, z)] = 'hout'
    top = grond + stam_h
    for bx in range(-2, 3):
        for by in range(0, 4):
            for bz in range(-2, 3):
                if abs(bx) + abs(bz) + abs(by) * 0.7 <= 2.5:
                    if not (bx == 0 and bz == 0 and by < 2):
                        blokken[(x + bx, top + by, z + bz)] = 'blad'


def genereer_chunk_data(cx, cz):
    """Bedenkt welke blokken er in een stukje wereld staan (alleen getallen,
    nog geen 3D-modellen). Slaat ze op in het telefoonboek."""
    if (cx, cz) in chunk_blokken:
        return  # Dit stukje is al bedacht

    blokken = {}
    rng = random.Random(WERELD_ZAAD + cx * 73856093 + cz * 19349663)

    for lx in range(CHUNK_GROOTTE):
        for lz in range(CHUNK_GROOTTE):
            x = cx * CHUNK_GROOTTE + lx
            z = cz * CHUNK_GROOTTE + lz
            grond = hoogte_op(x, z)

            # De grond en de lagen eronder
            for y in range(grond, grond - WERELD_DIEPTE, -1):
                if not is_grot(x, y, z, grond):
                    blokken[(x, y, z)] = bepaal_blok_type(y, grond)

            # Water in de lage plekken
            if grond < WATER_NIVEAU:
                for y in range(grond + 1, WATER_NIVEAU + 1):
                    blokken[(x, y, z)] = 'water'

            # Soms een boom. We houden 2 blokken afstand van de rand,
            # zodat de bladeren netjes binnen dit stukje wereld blijven.
            if 2 <= lx <= CHUNK_GROOTTE - 3 and 2 <= lz <= CHUNK_GROOTTE - 3:
                if blokken.get((x, grond, z)) == 'gras' and rng.random() < 0.05:
                    voeg_boom_toe(blokken, x, grond, z, rng)

    chunk_blokken[(cx, cz)] = blokken
    # Zet alle blokken ook in het grote telefoonboek
    for pos, t in blokken.items():
        wereld[pos] = t


def bouw_chunk_model(cx, cz):
    """HET MINECRAFT-TRUCJE: plak alle zichtbare blokken van dit stukje wereld
    samen tot één groot model per kleur. Daardoor hoeft de computer nog maar
    een paar modellen te tekenen in plaats van duizenden losse blokken."""
    # Zorg dat de buur-stukjes ook bedacht zijn, anders kloppen de randen niet
    for ncx, ncz in [(cx, cz), (cx + 1, cz), (cx - 1, cz), (cx, cz + 1), (cx, cz - 1)]:
        genereer_chunk_data(ncx, ncz)

    verwijder_chunk_model(cx, cz)  # eventueel oud model weghalen

    # Verzamel de zichtbare blokken, gesorteerd per bloktype (per kleur)
    per_type = collections.defaultdict(list)
    for pos, t in chunk_blokken.get((cx, cz), {}).items():
        if blok_zichtbaar(*pos):
            per_type[t].append(pos)

    modellen = []
    for t, posities in per_type.items():
        ouder = Entity()
        # Maak tijdelijk voor elk blok een kubus...
        for (x, y, z) in posities:
            Entity(parent=ouder, model='cube', position=(x, y, z))
        # ...en plak ze daarna samen tot één model. De losse kubussen
        # worden dan automatisch opgeruimd (auto_destroy).
        ouder.combine(auto_destroy=True)
        ouder.texture = 'white_cube'
        ouder.color   = KLEUREN.get(t, color.white)
        if t != 'water':
            ouder.collider = 'mesh'   # zodat je het kunt aanklikken en erop staan
        modellen.append(ouder)

    chunk_modellen[(cx, cz)] = modellen


def verwijder_chunk_model(cx, cz):
    """Haalt de 3D-modellen van een stukje wereld weg (de blokken-getallen
    blijven bewaard zolang we ze nog nodig hebben)."""
    for model in chunk_modellen.pop((cx, cz), []):
        destroy(model)


def vergeet_chunk(cx, cz):
    """Gooit een stukje wereld helemaal weg: het model én de getallen."""
    verwijder_chunk_model(cx, cz)
    blokken = chunk_blokken.pop((cx, cz), {})
    for pos in blokken:
        wereld.pop(pos, None)


# --- Blokken breken en plaatsen (met een 'straal' vanuit je ogen) ---
def herbouw_rond(pos):
    """Bouwt het stukje wereld van een blok opnieuw, plus de buur-stukjes
    (want aan de rand kan de zichtbaarheid van buren veranderen)."""
    chunks_te_doen = set()
    for dx, dy, dz in [(0, 0, 0)] + BUREN:
        chunks_te_doen.add(chunk_van_pos(pos[0] + dx, pos[2] + dz))
    for (cx, cz) in chunks_te_doen:
        if (cx, cz) in chunk_modellen:
            bouw_chunk_model(cx, cz)


def breek_blok():
    """Breekt het blok af waar je naar kijkt."""
    if mouse.world_point is None or mouse.world_normal is None:
        return
    # Het blok zit net BINNEN het oppervlak waar je straal op landt
    punt = mouse.world_point - mouse.world_normal * 0.5
    pos  = (round(punt.x), round(punt.y), round(punt.z))
    if pos in wereld:
        wereld.pop(pos, None)
        cx, cz = chunk_van_pos(pos[0], pos[2])
        chunk_blokken.get((cx, cz), {}).pop(pos, None)
        weggehaald.add(pos)        # onthoud dat dit blok weg is (komt niet terug)
        onthul_buren(pos)          # maak de blokken eronder/ernaast aan (geen void)
        geluid_afbreken.play()
        herbouw_rond(pos)


def plaats_blok():
    """Plaatst een nieuw blok tegen het blok waar je naar kijkt."""
    if mouse.world_point is None or mouse.world_normal is None:
        return
    # Het nieuwe blok komt net BUITEN het oppervlak (aan de kant waar je staat)
    punt = mouse.world_point + mouse.world_normal * 0.5
    pos  = (round(punt.x), round(punt.y), round(punt.z))
    if pos in wereld:
        return  # Hier staat al een blok
    wereld[pos] = huidig_blok
    cx, cz = chunk_van_pos(pos[0], pos[2])
    chunk_blokken.setdefault((cx, cz), {})[pos] = huidig_blok
    weggehaald.discard(pos)    # hier staat weer een blok, dus niet meer 'weg'
    geluid_plaatsen.play()
    herbouw_rond(pos)


# --- Geluiden ---
geluid_plaatsen = Audio('plop',  autoplay=False)   # plop bij plaatsen
geluid_afbreken = Audio('boink', autoplay=False)   # boink bij afbreken


class Varken(Entity):
    """Een varken dat vrolijk over de wereld rondloopt."""

    def __init__(self, positie):
        super().__init__(parent=scene, position=positie)
        roze       = color.rgb(1.0,  0.7,  0.75)
        donkerroze = color.rgb(0.9,  0.5,  0.55)
        Entity(parent=self, model='cube', color=roze, scale=(0.9, 0.7, 1.3))            # lichaam
        Entity(parent=self, model='cube', color=donkerroze,
               position=(0, 0, 0.7), scale=(0.4, 0.4, 0.2))                             # snuit
        for px in (-0.3, 0.3):                                                          # 4 pootjes
            for pz in (-0.45, 0.45):
                Entity(parent=self, model='cube', color=donkerroze,
                       position=(px, -0.45, pz), scale=(0.2, 0.5, 0.2))
        self.richting   = random.uniform(0, 360)
        self.loop_timer = 0

    def update(self):
        self.loop_timer -= time.dt
        if self.loop_timer <= 0:
            self.richting   = random.uniform(0, 360)
            self.loop_timer = random.uniform(1, 3)
        self.rotation_y = self.richting
        self.position  += self.forward * time.dt * 1.5
        self.y = hoogte_op(self.x, self.z) + 1.2   # netjes op de grond blijven


# --- Startpositie ---
SPAWN_X = 0
SPAWN_Z = 0
spawn_grond  = hoogte_op(SPAWN_X, SPAWN_Z)
start_chunk  = chunk_van_pos(SPAWN_X, SPAWN_Z)

# Bouw de stukjes rondom de startplek meteen (zodat de speler niet valt)
for dcx in range(-1, 2):
    for dcz in range(-1, 2):
        bouw_chunk_model(start_chunk[0] + dcx, start_chunk[1] + dcz)

# Zet de overige stukjes binnen kijk-afstand in de bouw-wachtrij
for dcx in range(-RENDER_AFSTAND, RENDER_AFSTAND + 1):
    for dcz in range(-RENDER_AFSTAND, RENDER_AFSTAND + 1):
        chunk = (start_chunk[0] + dcx, start_chunk[1] + dcz)
        if chunk not in chunk_modellen:
            bouw_wachtrij.append(chunk)

# --- Speler ---
speler = FirstPersonController(height=2)
speler.position = (SPAWN_X, spawn_grond + 2, SPAWN_Z)

# --- Dieren ---
dieren = []
for _ in range(5):
    dx = SPAWN_X + random.randint(-6, 6)
    dz = SPAWN_Z + random.randint(-6, 6)
    dieren.append(Varken((dx, hoogte_op(dx, dz) + 1.2, dz)))

# --- Dag en nacht ---
lucht = Sky(color=color.rgb(0.5, 0.7, 1.0))
zon   = DirectionalLight()
zon.rotation = (45, -45, 0)
dag_tijd   = 0.0
DAG_LENGTE = 60.0

window.fps_counter.enabled = True

# --- Uitleg op het scherm ---
Text(
    text="Linker muis = afbreken   Rechter muis = plaatsen   Muiswiel = ander blok\n"
         "WASD = lopen   Spatie = springen   Escape = stoppen   F3 = meet-schermpje",
    position=(-0.85, 0.47),
    scale=1.1,
    background=True,
)

# --- Blok-kiezer onderaan: laat zien welk blok je vasthoudt ---
blok_tekst = Text(text="", position=(-0.15, -0.42), scale=1.3, background=True)


def kies_blok(index):
    """Kiest een blok uit de lijst en laat de naam onderaan zien."""
    global blok_index, huidig_blok
    blok_index  = index % len(BLOK_KEUZES)   # blijf netjes binnen de lijst
    huidig_blok = BLOK_KEUZES[blok_index]
    blok_tekst.text = f"Blok: {huidig_blok.upper()}  ({blok_index + 1}/{len(BLOK_KEUZES)})"
    k = KLEUREN.get(huidig_blok, color.white)
    blok_tekst.color = color.rgb(k.r, k.g, k.b)   # zelfde kleur, maar altijd goed zichtbaar


kies_blok(0)   # begin met het eerste blok


# --- Inventaris (open en sluit met de toets 'i') ---
# Een scherm met alle blokken als vakjes. Klik op een vakje om dat blok te kiezen.
inventaris = Entity(parent=camera.ui, enabled=False)
# Donkere achtergrond zodat de vakjes goed opvallen
Entity(parent=inventaris, model='quad', color=color.rgba(0, 0, 0, 0.75),
       scale=(1.8, 1.0), z=1)
Text(parent=inventaris, text="Kies een blok (klik erop)   -   'i' om te sluiten",
     position=(0, 0.4), origin=(0, 0), scale=1.3)


def verberg_inventaris():
    """Sluit de inventaris en vergrendel de muis weer voor het rondkijken."""
    inventaris.enabled = False
    mouse.locked  = True
    mouse.visible = False


def toon_inventaris():
    """Open de inventaris en maak de muis vrij zodat je kunt klikken."""
    inventaris.enabled = True
    mouse.locked  = False
    mouse.visible = True


def kies_uit_inventaris(index):
    """Wordt aangeroepen als je op een blok-vakje klikt."""
    kies_blok(index)
    verberg_inventaris()


# Maak voor elk blok een gekleurd vakje in een net rooster (7 op een rij)
KOLOMMEN = 7
for i, naam in enumerate(BLOK_KEUZES):
    rij = i // KOLOMMEN
    kol = i % KOLOMMEN
    vx  = (kol - (KOLOMMEN - 1) / 2) * 0.2
    vy  = 0.2 - rij * 0.22
    kleur = KLEUREN[naam]
    vakje = Button(parent=inventaris, model='quad', scale=0.16, position=(vx, vy),
                   color=color.rgb(kleur.r, kleur.g, kleur.b))
    vakje.on_click = Func(kies_uit_inventaris, i)   # klik = dit blok kiezen
    Text(parent=inventaris, text=naam, position=(vx, vy - 0.1),
         origin=(0, 0), scale=0.7)


# --- Meet-schermpje (linksonder) ---
debug_tekst = Text(text="", position=(-0.85, -0.30), scale=1.1, background=True)
gemiddelde_fps = 50.0
debug_timer    = 0.0


def update():
    """Wordt elke frame aangeroepen: dag/nacht, bouwen en stukjes beheren."""
    global vorige_chunk, gemiddelde_fps, debug_timer, dag_tijd

    # --- Dag en nacht laten verlopen ---
    dag_tijd += time.dt
    fractie = (dag_tijd % DAG_LENGTE) / DAG_LENGTE
    zon.rotation = (fractie * 360, -45, 0)
    hoogte = math.sin(fractie * 2 * math.pi)
    helder = max(0.1, (hoogte + 1) / 2)
    lucht.color = color.rgb(0.5 * helder, 0.7 * helder, 1.0 * helder)

    # --- Plafond-check: niet van onderen in een blok springen ---
    # Tijdens het springen schuift de speler recht omhoog. De besturing kijkt
    # zelf NIET of er een blok boven je hoofd zit, dus dan schiet je er dwars
    # in. Daarom schieten we hier een straaltje recht omhoog vanaf je hoofd.
    # Zit er vlak boven je een blok? Dan stoppen we de sprong meteen.
    sprong = getattr(speler, 'y_animator', None)
    if sprong is not None and not speler.grounded:
        boven = raycast(speler.world_position + Vec3(0, speler.height - 0.1, 0),
                        Vec3(0, 1, 0), distance=0.3, ignore=[speler])
        if boven.hit:
            speler.y_animator.pause()   # stop het omhoog-springen meteen

    # --- Reddingslijn: alleen als je ECHT in de leegte valt ---
    # We schieten een straal recht naar beneden. Is er grond onder je? Top, dan
    # doen we niks (zo kun je zo diep graven als je wilt). Is er niets onder je
    # (je valt de leegte in)? Dan zetten we je weer veilig bovenop de grond.
    grond_hier = hoogte_op(speler.x, speler.z)
    if speler.y < grond_hier - 3:
        val_straal = raycast(speler.world_position, Vec3(0, -1, 0),
                             distance=80, ignore=[speler])
        if not val_straal.hit:
            speler.position = (speler.x, grond_hier + 2, speler.z)

    # --- FPS meten ---
    if time.dt > 0:
        gemiddelde_fps = gemiddelde_fps * 0.95 + (1 / time.dt) * 0.05

    # --- Per frame één stukje wereld samenplakken (spreidt het werk) ---
    if bouw_wachtrij:
        cx, cz = bouw_wachtrij.popleft()
        if (cx, cz) not in chunk_modellen:
            bouw_chunk_model(cx, cz)

    # --- Meet-schermpje bijwerken ---
    if debug_tekst.enabled:
        debug_timer += time.dt
        if debug_timer >= 0.25:
            debug_timer = 0.0
            speler_chunk = chunk_van_pos(speler.x, speler.z)
            debug_tekst.text = (
                f"FPS: {round(gemiddelde_fps)}\n"
                f"Stukjes wereld: {len(chunk_modellen)}\n"
                f"Blokken in geheugen: {len(wereld)}\n"
                f"Bouw-wachtrij: {len(bouw_wachtrij)}\n"
                f"Chunk: {speler_chunk}"
            )

    # --- Stukjes laden en lossen als de speler beweegt ---
    speler_chunk = chunk_van_pos(speler.x, speler.z)
    if speler_chunk == vorige_chunk:
        return
    vorige_chunk = speler_chunk
    cx, cz = speler_chunk

    # Nieuwe stukjes binnen kijk-afstand in de bouw-wachtrij zetten
    for dcx in range(-RENDER_AFSTAND, RENDER_AFSTAND + 1):
        for dcz in range(-RENDER_AFSTAND, RENDER_AFSTAND + 1):
            chunk = (cx + dcx, cz + dcz)
            if chunk not in chunk_modellen and chunk not in bouw_wachtrij:
                bouw_wachtrij.append(chunk)

    # Stukjes die te ver weg zijn helemaal vergeten
    for chunk in list(chunk_modellen.keys()):
        if abs(chunk[0] - cx) > RENDER_AFSTAND or abs(chunk[1] - cz) > RENDER_AFSTAND:
            vergeet_chunk(*chunk)


def input(toets):
    # De inventaris openen of sluiten
    if toets == 'i':
        verberg_inventaris() if inventaris.enabled else toon_inventaris()
        return

    # Als de inventaris open is, niet breken/plaatsen (je klikt dan op vakjes)
    if not inventaris.enabled:
        if toets == 'left mouse down':  breek_blok()
        if toets == 'right mouse down': plaats_blok()

    # Met het muiswiel door alle blokken bladeren
    if toets == 'scroll up':   kies_blok(blok_index + 1)
    if toets == 'scroll down': kies_blok(blok_index - 1)

    # De cijfertoetsen 1 t/m 9 en 0 kiezen snel de eerste tien blokken
    if len(toets) == 1 and toets in '1234567890':
        nummer = 9 if toets == '0' else int(toets) - 1   # '1'->0, ..., '0'->9
        if nummer < len(BLOK_KEUZES):
            kies_blok(nummer)

    if toets == 'f3':
        debug_tekst.enabled        = not debug_tekst.enabled
        window.fps_counter.enabled = debug_tekst.enabled
    if toets == 'escape':
        quit()


app.run()

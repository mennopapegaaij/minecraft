from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
from ursina.prefabs.input_field import InputField   # het typ-vakje (zoekbalk)
from ursina.shader import Shader                     # om onze eigen licht-shader te maken
import mc_blokken                                    # gegevens van de Minecraft-blokken
from perlin_noise import PerlinNoise
import random
import math
import collections
import json
import os
import sys
import subprocess
import shutil

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


# ======================================================================
#  VERLICHTING (zoals in het echte Minecraft: licht in de blokken bakken)
# ======================================================================
# We gebruiken GEEN echte lampen. Onze eigen shader doet twee dingen:
#  1) VLAK-SHADING: uit de richting (normaal) van een vlak berekent hij hoe
#     fel dat vlak is -- bovenkant helder, zijkanten donkerder, onderkant het
#     donkerst. Precies zoals Minecraft.
#  2) BLOKLICHT: elk blok krijgt een kleur (ingebakken als vertex-kleur) die
#     vertelt hoeveel licht het krijgt (grotten worden donker).
# Met de 'daglicht'-knop dimmen we 's nachts alles in één keer.

blok_shader = Shader(name='blok_shader', language=Shader.GLSL,
vertex='''#version 130
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
in vec3 p3d_Normal;
in vec4 p3d_Color;
out vec2 uvs;
out vec3 world_normal;
out vec4 vertex_color;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    uvs = p3d_MultiTexCoord0;
    world_normal = normalize(mat3(p3d_ModelMatrix) * p3d_Normal);  // welke kant wijst dit vlak op?
    vertex_color = p3d_Color;      // de ingebakken licht-kleur van dit blok
}
''',
fragment='''#version 140
uniform sampler2D p3d_Texture0;
uniform vec4 p3d_ColorScale;
uniform float daglicht;            // 1 = dag, klein = nacht
in vec2 uvs;
in vec3 world_normal;
in vec4 vertex_color;
out vec4 fragColor;
void main() {
    // Vlak-shading: hoe fel is dit vlak op basis van zijn richting?
    vec3 n = normalize(world_normal);
    float fb;
    if (abs(n.y) >= abs(n.x) && abs(n.y) >= abs(n.z))
        fb = n.y > 0.0 ? 1.0 : 0.45;   // boven fel, onder donkerst
    else if (abs(n.z) >= abs(n.x))
        fb = 0.80;                     // voor/achter
    else
        fb = 0.60;                     // links/rechts
    vec4 c = texture(p3d_Texture0, uvs) * p3d_ColorScale * vertex_color;
    c.rgb *= fb * daglicht;            // vlak-shading en nacht-dimming
    fragColor = c;
}
''',
default_input={'daglicht': 1.0},
)

MIN_LICHT = 0.10    # hoe donker de allerdonkerste plekken worden (niet pikzwart)
MAX_LICHT = 15      # hoogste lichtniveau (net als Minecraft: 0 t/m 15)


def licht_factor(niveau):
    """Zet een lichtniveau (0..15) om in een helderheid (MIN_LICHT..1.0)."""
    return MIN_LICHT + (1 - MIN_LICHT) * (niveau / MAX_LICHT)


# --- Opslaan / verder spelen (meerdere werelden met een eigen naam) ---
# Elke wereld is een eigen bestandje in de map 'werelden/'. In zo'n bestand
# staat het zaad + alles wat de speler heeft veranderd (gesloopte en geplaatste
# blokken, rugzak, plek, tijd, enz.). In 'huidige_wereld.txt' onthouden we welke
# wereld je nu speelt.
WERELDEN_MAP        = 'werelden'
HUIDIGE_WERELD_PAD  = 'huidige_wereld.txt'


def _wereld_bestand(naam):
    """Het opslag-bestand dat bij een wereldnaam hoort."""
    return os.path.join(WERELDEN_MAP, naam + '.json')


def _bestaande_werelden():
    """Alle wereldnamen die al zijn opgeslagen (op alfabet)."""
    if not os.path.isdir(WERELDEN_MAP):
        return []
    return sorted(f[:-5] for f in os.listdir(WERELDEN_MAP) if f.endswith('.json'))


def _huidige_wereld_naam():
    """Welke wereld speel je nu? (staat in huidige_wereld.txt, anders 'wereld1')."""
    if os.path.exists(HUIDIGE_WERELD_PAD):
        try:
            naam = open(HUIDIGE_WERELD_PAD, encoding='utf-8').read().strip()
            if naam:
                return naam
        except Exception:
            pass
    return 'wereld1'


# Zorg dat de werelden-map bestaat. Oude enkel-bestand-opslag netjes verhuizen.
os.makedirs(WERELDEN_MAP, exist_ok=True)
if os.path.exists('wereld_opslag.json') and not os.path.exists(_wereld_bestand('wereld1')):
    try:
        shutil.move('wereld_opslag.json', _wereld_bestand('wereld1'))
    except Exception:
        pass

HUIDIGE_WERELD = _huidige_wereld_naam()
OPSLAG_PAD     = _wereld_bestand(HUIDIGE_WERELD)


def _lees_opslag():
    """Leest de huidige wereld in (of None als hij nieuw is / het bestand stuk is)."""
    if not os.path.exists(OPSLAG_PAD):
        return None
    try:
        with open(OPSLAG_PAD, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


OPGESLAGEN = _lees_opslag()

# Het zaad bepaalt hoe de wereld eruitziet. Verder spelen? Dan het opgeslagen
# zaad gebruiken. Anders een nieuw willekeurig zaad (elke keer een andere wereld).
if OPGESLAGEN:
    WERELD_ZAAD = OPGESLAGEN['zaad']
    print(f"Wereld '{HUIDIGE_WERELD}' geladen (zaad {WERELD_ZAAD})")
else:
    WERELD_ZAAD = random.randint(1, 9999)
    print(f"Nieuwe wereld '{HUIDIGE_WERELD}' (zaad {WERELD_ZAAD})")

# CREATIEF: in deze stand heb je oneindig blokken, kun je vliegen, komen er
# geen monsters en breekt alles meteen. Deze stand hoort bij de wereld zelf.
CREATIEF = bool(OPGESLAGEN and OPGESLAGEN.get('creatief'))
if CREATIEF:
    print("Creatieve modus AAN")

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
    'kool':     color.rgb( 45/255,  45/255,  45/255),
    'lava':     color.rgb(240/255, 100/255,  20/255),
    'pompoen':  color.rgb(230/255, 140/255,  30/255),
    'mos':      color.rgb( 60/255, 110/255,  40/255),
    # Natuur-blokken die je in de wereld kunt vinden
    'klei':        color.rgb(160/255, 165/255, 175/255),
    'zandsteen':   color.rgb(220/255, 205/255, 160/255),
    'paddenstoel': color.rgb(200/255,  50/255,  50/255),
    'water':    color.rgba(45/255, 110/255, 200/255, 0.6),
}

# De blokken die je kunt vasthouden en plaatsen (met muiswiel of cijfertoetsen)
BLOK_KEUZES = ['gras', 'aarde', 'steen', 'zand', 'hout', 'planken', 'blad',
               'baksteen', 'glas', 'sneeuw', 'goud', 'diamant', 'ijzer',
               'smaragd', 'kool', 'lava', 'pompoen', 'mos',
               'klei', 'zandsteen', 'paddenstoel']

WATER_NIVEAU = 6          # Tot welke hoogte staat er water in de lage plekken

# --- Rugzak: hoeveel je van elk blok of zelfgemaakt ding hebt ---
# Je begint met NIETS. Ga eerst blokken slopen om spullen te verzamelen!
rugzak = {}

# Het blok of ding dat je nu vasthoudt om te plaatsen (None = niks)
vastgehouden = None

# De eigen vololgorde van je hotbar (kun je zelf wisselen met de pijltjestoetsen).
hotbar_volgorde = []

# Voor dubbel-spatie om te gaan vliegen (creatief): telt af na een spatie-tik.
spatie_timer = 0.0

# Hoe sterk is je pikhouweel? 0 = nog geen, 1 = stenen, 2 = ijzeren,
# 3 = gouden, 4 = smaragden. Hoe hoger, hoe meer je kunt hakken.
pikhouweel_niveau = 0

# Welke pikhouweel hoort bij welk niveau (om netjes op het scherm te laten zien).
PIKHOUWEEL_NAAM = {
    1: 'stenen pikhouweel',
    2: 'ijzeren pikhouweel',
    3: 'gouden pikhouweel',
    4: 'smaragden pikhouweel',
}

# De harde ertsen, met het MINIMALE pikhouweel-niveau dat je nodig hebt.
# Net als in het echte Minecraft: een sterkere pikhouweel kan meer hakken!
# (Steen en kool staan er NIET bij: die mag je met je hand, anders kun je
#  nooit je eerste pikhouweel maken.)
ERTS_NIVEAU = {
    'ijzer':   1,   # nodig: stenen pikhouweel (of sterker)
    'goud':    2,   # nodig: ijzeren pikhouweel (of sterker)
    'smaragd': 3,   # nodig: gouden pikhouweel (of sterker)
    'diamant': 4,   # nodig: smaragden pikhouweel
}

# --- Het geheugen van de wereld ---
# 'wereld' is het grote telefoonboek: op welke plek (x, y, z) staat welk soort blok?
# Dit zijn alleen getallen, geen 3D-modellen. Heel licht voor de computer.
wereld          = {}                    # (x, y, z) -> bloktype, bv 'gras'
chunk_blokken   = {}                    # (cx, cz) -> dict met de blokken van dat stukje
chunk_modellen  = {}                    # (cx, cz) -> lijst met de samengeplakte 3D-modellen
bouw_wachtrij   = collections.deque()   # stukjes die nog een 3D-model moeten krijgen
weggehaald      = set()                 # plekken waar de speler een blok heeft weggesloopt
vorige_chunk    = None

# Om te kunnen OPSLAAN onthouden we per stukje wat de speler heeft veranderd:
# welke blokken zijn weggehaald, en welke zijn erbij gekomen (geplaatst of
# opgegraven). Zo kunnen we de wereld later precies zo terugbouwen.
extra_blokken = {}                              # (x,y,z) -> bloktype (erbij gekomen)
weg_index     = collections.defaultdict(set)    # (cx,cz) -> set met weggehaalde plekken
extra_index   = collections.defaultdict(dict)   # (cx,cz) -> {plek: bloktype}


def markeer_weg(pos):
    """Onthoud dat hier een blok is weggehaald (voor opslaan + hergeneratie)."""
    c = chunk_van_pos(pos[0], pos[2])
    weggehaald.add(pos)
    weg_index[c].add(pos)
    extra_blokken.pop(pos, None)
    extra_index[c].pop(pos, None)


def markeer_extra(pos, bloktype):
    """Onthoud dat hier een blok is bijgekomen (geplaatst of opgegraven)."""
    c = chunk_van_pos(pos[0], pos[2])
    extra_blokken[pos] = bloktype
    extra_index[c][pos] = bloktype
    weggehaald.discard(pos)
    weg_index[c].discard(pos)


def chunk_van_pos(x, z):
    """Berekent in welk stukje wereld een positie ligt."""
    return (math.floor(x / CHUNK_GROOTTE), math.floor(z / CHUNK_GROOTTE))


# Is er een opgeslagen wereld? Zet de wijzigingen dan alvast klaar, zodat de
# stukjes meteen goed (met jouw gebouwde/gesloopte dingen) gegenereerd worden.
if OPGESLAGEN:
    for _p in OPGESLAGEN.get('weg', []):
        markeer_weg((_p[0], _p[1], _p[2]))
    for _e in OPGESLAGEN.get('extra', []):
        markeer_extra((_e[0], _e[1], _e[2]), _e[3])


def hoogte_op(x, z):
    """Berekent de grondhoogte op positie (x, z) met Perlin ruis."""
    nx = x * 0.04
    nz = z * 0.04
    h = (ruis_groot([nx, nz])  * 14 +
         ruis_midden([nx, nz]) *  5 +
         ruis_klein([nx, nz])  *  1.5)
    return int(h + 10)


def steen_of_erts(x, y, z):
    """Diep in de steen zit soms een erts in plaats van gewone steen.
    Hoe dieper je graaft, hoe zeldzamer (en mooier) het erts kan zijn!"""
    # Een eigen willekeurig getal per plekje, altijd hetzelfde voor die plek
    rng = random.Random((x * 73856093) ^ (y * 19349663) ^ (z * 83492791) ^ WERELD_ZAAD)
    r = rng.random()
    if y <= -2 and r < 0.012:  return 'diamant'   # heel diep en heel zeldzaam
    if y <=  2 and r < 0.034:  return 'smaragd'
    if y <=  4 and r < 0.054:  return 'goud'
    if y <= 12 and r < 0.090:  return 'ijzer'
    if y <= 10 and r < 0.125:  return 'redstone_erts'   # redstone: redelijk diep
    if            r < 0.155:   return 'kool'       # kool kom je overal tegen
    return 'steen'


def bepaal_blok_type(x, y, z, grond_hoogte):
    """Geeft het juiste bloktype terug op basis van de plek en de hoogte."""
    if y == grond_hoogte:
        if y <= 5:   return 'zand'
        if y >= 18:  return 'sneeuw'
        return 'gras'
    if grond_hoogte <= 6 and y >= grond_hoogte - 2:
        return 'zandsteen'        # vlak onder het strand zit zandsteen
    if y >= grond_hoogte - 3:
        return 'aarde'
    return steen_of_erts(x, y, z)  # diep in de grond: steen of soms erts


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

# Deze blokken houden het licht NIET tegen (licht schijnt er dwars doorheen).
# Alle andere blokken wel. Zo wordt het donker onder de grond, maar niet onder
# een raampje van glas.
LICHT_DOORLATEND = {'glas', 'water'}


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
            t = bepaal_blok_type(buur[0], buur[1], buur[2], grond)
            wereld[buur] = t
            cx, cz = chunk_van_pos(buur[0], buur[2])
            chunk_blokken.setdefault((cx, cz), {})[buur] = t
            markeer_extra(buur, t)     # onthouden voor opslaan/hergeneratie


def voeg_boom_toe(blokken, x, grond, z, rng, stam='hout', blad='blad', soort='rond'):
    """Zet een boom in de blokken-lijst van een stukje wereld.
    'stam' en 'blad' bepalen de blokken; 'soort' bepaalt de vorm:
    'den' = hoog en puntig, 'acacia' = platte brede kruin,
    'jungle' = extra hoog, anders een gewone ronde kruin."""
    if soort == 'den':
        # Dennenboom: hoge stam met een puntige, gelaagde kruin.
        stam_h = rng.randint(5, 7)
        for y in range(1, stam_h + 1):
            blokken[(x, grond + y, z)] = stam
        top = grond + stam_h
        blokken[(x, top + 1, z)] = blad                    # het puntje bovenop
        for i, straal in enumerate((1, 1, 2, 2)):          # ringen, breder naar onder
            yy = top - i
            for bx in range(-straal, straal + 1):
                for bz in range(-straal, straal + 1):
                    if abs(bx) + abs(bz) <= straal and not (bx == 0 and bz == 0):
                        blokken[(x + bx, yy, z + bz)] = blad
        return

    if soort == 'acacia':
        # Acaciaboom: stam met een platte, brede parasol-kruin.
        stam_h = rng.randint(3, 5)
        for y in range(1, stam_h + 1):
            blokken[(x, grond + y, z)] = stam
        top = grond + stam_h
        for by, straal in ((0, 2), (1, 1)):                # onderlaag breed, bovenlaag klein
            for bx in range(-straal, straal + 1):
                for bz in range(-straal, straal + 1):
                    if not (bx == 0 and bz == 0 and by == 0):
                        blokken[(x + bx, top + by, z + bz)] = blad
        return

    # Ronde boom (eik, berk, kers, jungle, mangrove): rechte stam + bolvormige kruin.
    if soort == 'jungle':
        stam_h = rng.randint(6, 9)                          # jungle is extra hoog
    elif soort == 'berk':
        stam_h = rng.randint(4, 6)
    else:
        stam_h = rng.randint(3, 5)
    for y in range(1, stam_h + 1):
        blokken[(x, grond + y, z)] = stam
    top = grond + stam_h
    for bx in range(-2, 3):
        for by in range(0, 4):
            for bz in range(-2, 3):
                if abs(bx) + abs(bz) + abs(by) * 0.7 <= 2.5:
                    if not (bx == 0 and bz == 0 and by < 2):
                        blokken[(x + bx, top + by, z + bz)] = blad


# ============================================================================
#  HET DORP 🏘️  — een paar huisjes waar de villagers wonen
# ============================================================================
# Het dorp hoort BIJ de wereld, net als de bomen. We bedenken het één keer aan
# het begin uit het wereld-zaad. Daarna zetten we het in de stukjes wereld die
# eroverheen liggen. Zo staat het dorp na opnieuw opstarten weer precies op
# dezelfde plek, en hoeven we er niets extra's voor op te slaan.

DORP_PER_CHUNK = {}     # (cx, cz) -> (blokken om te ZETTEN, plekken om LEEG te maken)
DORP_DEUREN    = []     # alle voordeuren van alle dorpjes: (positie, richting)
DORPEN         = []     # alle dorpjes van deze wereld (zie _bedenk_dorp)

HUIS_HALF = 3           # een huisje is 7x7 blokken (3 aan elke kant van het midden)
DORP_HALF = 13          # het hele dorpsplein is 27x27 blokken

# Elk dorpje krijgt een eigen naam, zodat je ze uit elkaar kunt houden.
DORP_NAMEN = ['Eikendorp', 'Zonneveld', 'Steenbrug', 'Molenwijk',
              'Bosdal', 'Verweghuizen', 'Zandhoven', 'Beekdorp']

# Hoe ver staan de VERRE dorpjes van je startplek? (van ... tot ... blokken)
# Het eerste dorpje staat altijd lekker dichtbij, deze moet je gaan ZOEKEN.
DORP_AFSTANDEN = [(70, 110), (115, 160), (165, 210)]


def _eerste_dorp_plek():
    """Zoekt de plek voor het dorpje vlak bij je startplek.
    Dit is precies dezelfde manier van zoeken als toen er nog maar één dorp
    was. Zo blijft het dorp in een wereld die je AL had gewoon op zijn eigen
    plek staan, ook nu er dorpjes bij gekomen zijn."""
    rng = random.Random(WERELD_ZAAD + 4242)
    beste, beste_verschil = None, None
    for _ in range(40):
        vx = rng.randint(-45, 45)
        vz = rng.randint(-45, 45)
        if abs(vx) < 18 and abs(vz) < 18:
            continue                        # niet bovenop je startplek bouwen
        hoogtes = [hoogte_op(vx + dx, vz + dz)
                   for dx in (-12, 0, 12) for dz in (-12, 0, 12)]
        if min(hoogtes) <= WATER_NIVEAU + 1:
            continue                        # te laag: daar staat water
        verschil = max(hoogtes) - min(hoogtes)
        if beste is None or verschil < beste_verschil:
            beste, beste_verschil = (vx, vz), verschil
    return beste or (26, 26)


def _dorp_plek(rng, van, tot, al_gekozen):
    """Zoekt een mooie VLAKKE plek voor een dorpje: tussen 'van' en 'tot' blokken
    van de startplek, niet in het water en niet bovenop een ander dorpje.
    We proberen een heleboel plekjes en kiezen de allervlakste."""
    beste, beste_verschil = None, None
    for _ in range(80):
        hoek = rng.uniform(0, 2 * math.pi)          # een willekeurige richting
        afst = rng.uniform(van, tot)                # en een willekeurige afstand
        vx = int(math.cos(hoek) * afst)
        vz = int(math.sin(hoek) * afst)
        # Niet bovenop een dorpje dat er al staat
        if any(abs(vx - ox) < 2 * DORP_HALF + 12 and abs(vz - oz) < 2 * DORP_HALF + 12
               for ox, oz in al_gekozen):
            continue
        # Hoe vlak is het hier? We meten de hoogte op 9 plekjes.
        hoogtes = [hoogte_op(vx + dx, vz + dz)
                   for dx in (-12, 0, 12) for dz in (-12, 0, 12)]
        if min(hoogtes) <= WATER_NIVEAU + 1:
            continue                        # te laag: daar staat water
        verschil = max(hoogtes) - min(hoogtes)
        if beste is None or verschil < beste_verschil:
            beste, beste_verschil = (vx, vz), verschil
    return beste


def _bouw_huisje(blokken, leeg, dorp, hx, hz, vloer, muur, deur_kant):
    """Bouwt één huisje van 7x7: vloer, muren, dak, ramen en een deur-opening."""
    for x in range(hx - HUIS_HALF, hx + HUIS_HALF + 1):
        for z in range(hz - HUIS_HALF, hz + HUIS_HALF + 1):
            aan_de_rand = (x in (hx - HUIS_HALF, hx + HUIS_HALF) or
                           z in (hz - HUIS_HALF, hz + HUIS_HALF))
            blokken[(x, vloer, z)] = 'planken'            # de houten vloer
            for y in range(vloer + 1, vloer + 4):          # 3 blokken hoog
                if aan_de_rand:
                    blokken[(x, y, z)] = muur              # de muren
                else:
                    leeg.add((x, y, z))                    # binnen is het leeg
            blokken[(x, vloer + 4, z)] = 'hout'            # het dak
    # Ramen: midden in elke muur een glazen blok, zodat het gezellig is
    for rx, rz in ((hx, hz - HUIS_HALF), (hx, hz + HUIS_HALF),
                   (hx - HUIS_HALF, hz), (hx + HUIS_HALF, hz)):
        blokken[(rx, vloer + 2, rz)] = 'glas'
    # De deur: een gat van 2 blokken hoog in de muur aan de kant van het plein
    dx = hx + deur_kant[0] * HUIS_HALF
    dz = hz + deur_kant[1] * HUIS_HALF
    for y in (vloer + 1, vloer + 2):
        blokken.pop((dx, y, dz), None)     # de muur hier weghalen...
        leeg.add((dx, y, dz))              # ...en de plek echt leeg maken
    # Een deur die opendraait. Zit hij in een muur die van links naar rechts
    # loopt? Dan richting 0, anders een kwartslag gedraaid (90).
    richting = 0 if deur_kant[1] != 0 else 90
    DORP_DEUREN.append(((dx, vloer + 1, dz), richting))
    dorp['huizen'].append((hx, vloer + 1, hz))


def _bedenk_dorp(naam, vx, vz):
    """Bedenkt één dorpje: een vlak grasveld, vier huisjes, paadjes en een put.
    Geeft een 'dorp' terug: een kaartje met de naam, het midden, het vlakke
    plein en waar de huisjes staan."""
    vloer = hoogte_op(vx, vz)
    dorp = {
        'naam':   naam,
        'midden': (vx, vloer + 1, vz),
        'vlak':   (vx - DORP_HALF, vx + DORP_HALF,
                   vz - DORP_HALF, vz + DORP_HALF, vloer),
        'huizen': [],
    }
    blokken, leeg = {}, set()

    # 1) Het land vlak maken: een grasveld op één hoogte, heuvels en bomen weg.
    for x in range(vx - DORP_HALF, vx + DORP_HALF + 1):
        for z in range(vz - DORP_HALF, vz + DORP_HALF + 1):
            grond = hoogte_op(x, z)
            blokken[(x, vloer, z)] = 'gras'
            for y in range(vloer - 3, vloer):               # eronder gewoon aarde
                blokken[(x, y, z)] = 'aarde'
            # Alles wat er BOVENUIT steekt weghalen (heuvels en bomen)
            for y in range(vloer + 1, max(grond, vloer) + 9):
                leeg.add((x, y, z))

    # 2) Vier huisjes op de hoeken van het plein. Elk huisje heeft zijn eigen
    #    muur-materiaal, zodat het dorp er vrolijk uitziet.
    MUREN = ['planken', 'baksteen', 'zandsteen', 'planken']
    HOEKEN = ((-8, -8), (8, -8), (-8, 8), (8, 8))
    for i, (hx, hz) in enumerate(HOEKEN):
        kant = (0, 1) if hz < 0 else (0, -1)     # de deur kijkt naar het plein
        _bouw_huisje(blokken, leeg, dorp, vx + hx, vz + hz, vloer, MUREN[i], kant)

    # 3) Paadjes van zandsteen: een kruis midden over het plein
    for d in range(-DORP_HALF, DORP_HALF + 1):
        blokken[(vx + d, vloer, vz)] = 'zandsteen'
        blokken[(vx, vloer, vz + d)] = 'zandsteen'

    # 4) Een putje midden op het plein (met echt water erin)
    for x in range(vx - 1, vx + 2):
        for z in range(vz - 1, vz + 2):
            if x == vx and z == vz:
                blokken[(vx, vloer, vz)] = 'water'          # het water
            else:
                blokken[(x, vloer + 1, z)] = 'steen'        # de rand eromheen

    # 5) Alles netjes per stukje wereld sorteren, zodat we het later snel
    #    kunnen opzoeken als zo'n stukje gemaakt wordt.
    for pos, t in blokken.items():
        c = chunk_van_pos(pos[0], pos[2])
        DORP_PER_CHUNK.setdefault(c, ({}, set()))[0][pos] = t
    for pos in leeg:
        c = chunk_van_pos(pos[0], pos[2])
        DORP_PER_CHUNK.setdefault(c, ({}, set()))[1].add(pos)
    return dorp


def _bedenk_dorpen():
    """Bedenkt ALLE dorpjes van deze wereld. Het eerste staat lekker dichtbij,
    de andere verder weg zodat je ze kunt gaan zoeken. Ze horen bij het
    wereld-zaad, dus in dezelfde wereld staan ze altijd op dezelfde plek."""
    namen = list(DORP_NAMEN)
    random.Random(WERELD_ZAAD + 777).shuffle(namen)   # elke wereld andere namen
    # 1) Het dorpje dicht bij je startplek (staat er in oude werelden al).
    dichtbij = _eerste_dorp_plek()
    gekozen = [dichtbij]
    DORPEN.append(_bedenk_dorp(namen[0], *dichtbij))
    # 2) En daarna de verre dorpjes om te ontdekken.
    rng = random.Random(WERELD_ZAAD + 4243)
    for i, (van, tot) in enumerate(DORP_AFSTANDEN, start=1):
        plek = _dorp_plek(rng, van, tot, gekozen)
        if plek is None:
            continue                          # hier was geen vlakke plek: jammer
        gekozen.append(plek)
        DORPEN.append(_bedenk_dorp(namen[i % len(namen)], *plek))


def dichtstbijzijnde_dorp(x, z):
    """Welk dorpje is hier het dichtstbij, en hoe ver is het nog lopen?
    Geeft (dorp, afstand) terug, of (None, 0) als er geen dorpjes zijn."""
    beste, kortste = None, None
    for dorp in DORPEN:
        dx = dorp['midden'][0] - x
        dz = dorp['midden'][2] - z
        afst = math.sqrt(dx * dx + dz * dz)
        if kortste is None or afst < kortste:
            beste, kortste = dorp, afst
    return beste, (kortste or 0)


def zet_dorp_in_chunk(blokken, cx, cz):
    """Zet het stukje dorp dat in dit stukje wereld ligt erin.
    Eerst leegmaken (heuvels, bomen, de binnenkant van de huisjes),
    daarna de blokken van het dorp neerzetten."""
    deel = DORP_PER_CHUNK.get((cx, cz))
    if not deel:
        return
    dorp_blokken, dorp_leeg = deel
    for pos in dorp_leeg:
        blokken.pop(pos, None)
    for pos, t in dorp_blokken.items():
        blokken[pos] = t


def grond_onder(x, z):
    """Hoe hoog ligt de grond hier? Op een dorpsplein is dat de vlakke vloer,
    overal anders het gewone landschap. Dieren, villagers en golems gebruiken
    dit om netjes op de grond te blijven staan."""
    for dorp in DORPEN:
        x0, x1, z0, z1, vloer = dorp['vlak']
        if x0 <= x <= x1 and z0 <= z <= z1:
            return vloer
    return hoogte_op(x, z)


# De dorpjes meteen bedenken, VOORDAT de eerste stukjes wereld gemaakt worden.
_bedenk_dorpen()


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
                    blokken[(x, y, z)] = bepaal_blok_type(x, y, z, grond)

            # Klei op de bodem van meertjes (bij het water)
            if grond <= WATER_NIVEAU and rng.random() < 0.5:
                blokken[(x, grond, z)] = 'klei'

            # Water in de lage plekken
            if grond < WATER_NIVEAU:
                for y in range(grond + 1, WATER_NIVEAU + 1):
                    blokken[(x, y, z)] = 'water'

            # Op het gras: soms een boom, of een paddenstoel.
            if blokken.get((x, grond, z)) == 'gras':
                in_het_midden = 2 <= lx <= CHUNK_GROOTTE - 3 and 2 <= lz <= CHUNK_GROOTTE - 3
                if in_het_midden and rng.random() < 0.06:
                    # Kies een van de 8 boomsoorten. Eik komt het vaakst voor.
                    # Elk lijstje is: (naam, stam-blok, blad-blok, vorm).
                    BOOMSOORTEN = [
                        ('hout',             'blad',              'rond'),    # eik
                        ('mc_berk_stam',     'mc_berk_blad',      'berk'),
                        ('mc_den_stam',      'mc_den_blad',       'den'),
                        ('mc_kers_stam',     'mc_kers_blad',      'kers'),
                        ('mc_jungle_stam',   'mc_jungle_blad',    'jungle'),
                        ('mc_acacia_stam',   'mc_acacia_blad',    'acacia'),
                        ('mc_donkereik_stam','mc_donkereik_blad', 'rond'),
                        ('mc_mangrove_stam', 'mc_mangrove_blad',  'rond'),
                    ]
                    gewichten = [6, 3, 3, 2, 2, 2, 2, 2]
                    stam, blad, vorm = rng.choices(BOOMSOORTEN, weights=gewichten)[0]
                    voeg_boom_toe(blokken, x, grond, z, rng, stam, blad, vorm)
                elif rng.random() < 0.04:
                    blokken[(x, grond + 1, z)] = 'paddenstoel'  # klein paddenstoeltje

    # Ligt er een stukje DORP in dit stukje wereld? Dan die huisjes erin zetten.
    zet_dorp_in_chunk(blokken, cx, cz)

    # De wijzigingen van de speler toepassen: eerst de erbij gekomen blokken
    # (geplaatst of opgegraven), daarna de weggehaalde weer verwijderen.
    c = (cx, cz)
    for pos, t in extra_index.get(c, {}).items():
        blokken[pos] = t
    for pos in weg_index.get(c, ()):
        blokken.pop(pos, None)

    chunk_blokken[(cx, cz)] = blokken
    # Zet alle blokken ook in het grote telefoonboek (en houd redstone-blokken bij)
    for pos, t in blokken.items():
        wereld[pos] = t
        if t in DRAAD_TYPES or t in LAMP_TYPES or t == 'redstone_blok':
            registreer_redstone_blok(pos, t, True)


LICHT_MARGE = 6      # hoeveel blokken buiten de chunk we meenemen (licht van buren)
LICHT_HOOGTE = 48    # niet dieper dan dit rekenen (anders te traag bij diepe schachten)


def bereken_chunk_licht(cx, cz):
    """Reken uit hoeveel licht elk zichtbaar blok van deze chunk krijgt.
    Werkt zoals in het echte Minecraft: licht begint bij niveau 15 in de open
    lucht en stroomt de holtes in, elke stap 1 minder. Zo wordt een grot of
    tunnel steeds donkerder naarmate je dieper gaat -- in alle richtingen.
    Geeft terug: {(x, y, z): niveau 0..15} voor de zichtbare blokken."""
    x0, z0 = cx * CHUNK_GROOTTE, cz * CHUNK_GROOTTE
    xmin, xmax = x0 - LICHT_MARGE, x0 + CHUNK_GROOTTE - 1 + LICHT_MARGE
    zmin, zmax = z0 - LICHT_MARGE, z0 + CHUNK_GROOTTE - 1 + LICHT_MARGE

    # 1. Verzamel alle blokken in dit gebied (deze chunk + de buurchunks).
    vaste = {}
    for gcx in range(cx - 1, cx + 2):
        for gcz in range(cz - 1, cz + 2):
            genereer_chunk_data(gcx, gcz)
            for pos, t in chunk_blokken.get((gcx, gcz), {}).items():
                if xmin <= pos[0] <= xmax and zmin <= pos[2] <= zmax:
                    vaste[pos] = t

    if not vaste:
        return {}

    def laat_licht_door(pos):
        """Kan licht door deze plek? (lege lucht, of glas/water)"""
        t = vaste.get(pos)
        return t is None or t in LICHT_DOORLATEND

    # 2. Bepaal het hoogste 'dichte' blok per kolom (daarboven schijnt de zon).
    ys = [pos[1] for pos in vaste]
    ytop = max(ys) + 2
    ybot = max(min(ys) - 2, ytop - LICHT_HOOGTE)
    kolom_top = {}
    for (x, y, z), t in vaste.items():
        if t not in LICHT_DOORLATEND and y > kolom_top.get((x, z), -10 ** 9):
            kolom_top[(x, z)] = y

    # 3. Seed: alle lucht-cellen bóven het kolom-dak krijgen vol zonlicht (15).
    licht = {}
    rij = collections.deque()
    for x in range(xmin, xmax + 1):
        for z in range(zmin, zmax + 1):
            dak = kolom_top.get((x, z), ybot - 1)
            for y in range(dak + 1, ytop + 1):
                pos = (x, y, z)
                if laat_licht_door(pos):
                    licht[pos] = MAX_LICHT
                    rij.append(pos)

    # 4. Flood-fill: het licht stroomt naar de buren, elke stap 1 minder.
    while rij:
        x, y, z = rij.popleft()
        niveau = licht[(x, y, z)]
        if niveau <= 1:
            continue
        for dx, dy, dz in BUREN:
            buur = (x + dx, y + dy, z + dz)
            if not (xmin <= buur[0] <= xmax and ybot <= buur[1] <= ytop
                    and zmin <= buur[2] <= zmax):
                continue
            if laat_licht_door(buur) and licht.get(buur, 0) < niveau - 1:
                licht[buur] = niveau - 1
                rij.append(buur)

    # 5. Elk zichtbaar blok krijgt het felste licht van zijn 6 buur-lucht-cellen.
    resultaat = {}
    for pos, t in chunk_blokken.get((cx, cz), {}).items():
        if not blok_zichtbaar(*pos):
            continue
        best = 0
        for dx, dy, dz in BUREN:
            buur = (pos[0] + dx, pos[1] + dy, pos[2] + dz)
            n = licht.get(buur, 0)
            if n > best:
                best = n
        resultaat[pos] = best
    return resultaat


def bouw_chunk_model(cx, cz):
    """HET MINECRAFT-TRUCJE: plak alle zichtbare blokken van dit stukje wereld
    samen tot één groot model per kleur. Daardoor hoeft de computer nog maar
    een paar modellen te tekenen in plaats van duizenden losse blokken."""
    # Zorg dat de buur-stukjes ook bedacht zijn, anders kloppen de randen niet
    for ncx, ncz in [(cx, cz), (cx + 1, cz), (cx - 1, cz), (cx, cz + 1), (cx, cz - 1)]:
        genereer_chunk_data(ncx, ncz)

    verwijder_chunk_model(cx, cz)  # eventueel oud model weghalen

    blokken_hier = chunk_blokken.get((cx, cz), {})

    # Reken uit hoeveel licht elk zichtbaar blok krijgt (grotten worden donker).
    licht = bereken_chunk_licht(cx, cz)

    # Verzamel de zichtbare blokken, gesorteerd per bloktype (per texture).
    per_type = collections.defaultdict(list)
    for pos, t in blokken_hier.items():
        if blok_zichtbaar(*pos):
            per_type[t].append(pos)

    modellen = []
    for t, posities in per_type.items():
        # Heeft dit blok een echt plaatje (texture)? Dan is de basiskleur wit,
        # zodat het plaatje z'n eigen kleuren houdt. Anders het gekleurde blok.
        tex = BLOK_TEXTUUR.get(t)
        basiskleur = color.white if tex else KLEUREN.get(t, color.white)

        ouder = Entity()
        # Maak tijdelijk voor elk blok een kubus. De KLEUR van het blokje =
        # basiskleur x bloklicht. Bij het samenplakken wordt die kleur ingebakken
        # als vertex-kleur; de vlak-shading doet de shader zelf via de normaal.
        for pos in posities:
            factor = licht_factor(licht.get(pos, 0))
            Entity(parent=ouder, model='cube', position=pos,
                   color=color.rgba(basiskleur.r * factor,
                                    basiskleur.g * factor,
                                    basiskleur.b * factor,
                                    basiskleur.a))
        # ...en plak ze daarna samen tot één model (losse kubussen ruimt hij op).
        # include_normals=True is nodig zodat de shader de vlak-richting kent!
        ouder.combine(auto_destroy=True, include_normals=True)
        ouder.shader  = blok_shader        # doet vlak-shading + leest bloklicht uit
        ouder.texture = blok_texture(tex) if tex else 'white_cube'
        ouder.color   = color.white        # niet nog eens tinten (kleur zit al in mesh)
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
    for pos, t in blokken.items():
        wereld.pop(pos, None)
        if t in DRAAD_TYPES or t in LAMP_TYPES or t == 'redstone_blok':
            registreer_redstone_blok(pos, t, False)


# --- Zelfgemaakte dingen (specials) ---
# Deze hebben een eigen vorm en zijn LOSSE 3D-modellen (niet samengeplakt in
# een stukje wereld). We onthouden ze apart in 'speciaal'. Plaatsen kost 1 uit
# je rugzak; weer afbreken geeft het ding terug in je rugzak.
speciaal = {}   # plek (x,y,z) -> record met info over het ding dat daar staat

# Mooie namen om op het scherm te laten zien
ITEM_NAMEN = {
    'maaktafel': 'Maak-tafel',
    'slab': 'Halve blok', 'valluik': 'Valluik', 'trap': 'Traptrede',
    'hek': 'Hek', 'deur': 'Deur',
    'hefboom': 'Hefboom (schakelaar)',
    'piston': 'Piston', 'kleverige_piston': 'Kleverige piston',
    'ijzergolem': 'IJzergolem', 'boot': 'Boot',
    'stenen_pikhouweel': 'Stenen pikhouweel',
    'ijzeren_pikhouweel': 'IJzeren pikhouweel',
    'gouden_pikhouweel': 'Gouden pikhouweel',
    'smaragden_pikhouweel': 'Smaragden pikhouweel',
}

# De recepten: wat kost het, en hoeveel krijg je ervan?
# 'is_blok' = True betekent: het is een gewoon blok (geen ding met eigen vorm).
RECEPTEN = {
    # De maak-tafel zelf: dit is het ENIGE dat je met je handen kunt maken.
    'maaktafel':  {'kosten': {'hout': 4},             'maakt': 1, 'plaatsbaar': True},
    'slab':       {'kosten': {'steen': 3},            'maakt': 6, 'plaatsbaar': True},
    'valluik':    {'kosten': {'hout': 4},             'maakt': 3, 'plaatsbaar': True},
    'trap':       {'kosten': {'steen': 6},            'maakt': 4, 'plaatsbaar': True},
    'hek':        {'kosten': {'hout': 4},             'maakt': 4, 'plaatsbaar': True},
    'deur':       {'kosten': {'hout': 6},             'maakt': 1, 'plaatsbaar': True},
    # Redstone-machines (bij een maak-tafel):
    'hefboom':          {'kosten': {'steen': 1, 'hout': 1},                'maakt': 1, 'plaatsbaar': True},
    'piston':           {'kosten': {'hout': 3, 'steen': 4, 'ijzer': 1},    'maakt': 1, 'plaatsbaar': True},
    'kleverige_piston': {'kosten': {'hout': 3, 'steen': 4, 'ijzer': 1, 'blad': 1}, 'maakt': 1, 'plaatsbaar': True},
    # Een ijzergolem bouwen (4 ijzer + een pompoen als hoofd), net als in het
    # echte Minecraft. Zet hem neer met de G-toets: hij beschermt je!
    'ijzergolem': {'kosten': {'ijzer': 4, 'pompoen': 1}, 'maakt': 1, 'plaatsbaar': False},
    # Een bootje om snel over het water te varen. Zet hem neer met de N-toets.
    'boot':       {'kosten': {'hout': 5},                'maakt': 1, 'plaatsbaar': False},
    # De pikhouweel-ketting: elke pikhouweel kan een mooier erts hakken.
    # 'niveau' = hoe sterk hij is (zie ERTS_NIVEAU hierboven).
    'stenen_pikhouweel':    {'kosten': {'steen': 3,   'hout': 2}, 'maakt': 1, 'plaatsbaar': False, 'niveau': 1},
    'ijzeren_pikhouweel':   {'kosten': {'ijzer': 3,   'hout': 2}, 'maakt': 1, 'plaatsbaar': False, 'niveau': 2},
    'gouden_pikhouweel':    {'kosten': {'goud': 3,    'hout': 2}, 'maakt': 1, 'plaatsbaar': False, 'niveau': 3},
    'smaragden_pikhouweel': {'kosten': {'smaragd': 3, 'hout': 2}, 'maakt': 1, 'plaatsbaar': False, 'niveau': 4},
}

# 'maaktafel' mag je met je HANDEN maken (zonder tafel). De rest niet.
RECEPTEN['maaktafel']['hand'] = True


# ============================================================================
#  MINECRAFT-BLOKKEN met echte plaatjes (textures) 🧱
#  De plaatjes staan in assets/textures/ (gemaakt met maak_textures.py).
# ============================================================================

# BLOK_TEXTUUR onthoudt per bloktype welk plaatje het gebruikt.
BLOK_TEXTUUR = {}
BLOK_TEXTUUR.update(mc_blokken.BESTAANDE_TEXTUREN)   # bestaande blokken krijgen een plaatje

# De reservekleur per plaatje (voor als een plaatje niet geladen kan worden)
_basiskleur = {d['naam']: d['c1'] for d in mc_blokken.TEXTUUR_DEFS}

# De nieuwe Minecraft-blokken toevoegen aan het spel
for _b in mc_blokken.NIEUWE_BLOKKEN:
    _key = _b['key']
    BLOK_TEXTUUR[_key] = _key                        # plaatje heet net zo als het blok
    ITEM_NAMEN[_key]   = _b['naam']
    _rgb = _basiskleur.get(_key, (150, 150, 150))
    KLEUREN[_key]      = color.rgb(_rgb[0] / 255, _rgb[1] / 255, _rgb[2] / 255)
    BLOK_KEUZES.append(_key)                          # je kunt het vasthouden en plaatsen
    RECEPTEN[_key] = {'kosten': _b['kosten'], 'maakt': 4,
                      'plaatsbaar': True, 'is_blok': True, 'hand': False}

# De natuur-blokken (stammen en bladeren van bomen). Deze haal je uit bomen,
# dus ze krijgen GEEN recept, maar je kunt ze wel vasthouden en plaatsen.
for _b in mc_blokken.NATUUR_BLOKKEN:
    _key = _b['key']
    BLOK_TEXTUUR[_key] = _key
    ITEM_NAMEN[_key]   = _b['naam']
    _rgb = _basiskleur.get(_key, (150, 150, 150))
    KLEUREN[_key]      = color.rgb(_rgb[0] / 255, _rgb[1] / 255, _rgb[2] / 255)
    BLOK_KEUZES.append(_key)


# ============================================================================
#  REDSTONE-BLOKKEN 🔴⚡ (het elektrische spul)
# ============================================================================
# Welk bloktype gebruikt welk plaatje. De '..._aan' blokken zijn de 'aan'-stand
# (die maakt het spel zelf; die kun je niet vasthouden of maken).
_RS_TEXTUUR = {
    'redstone_erts':        'mc_redstone_erts',
    'redstone_blok':        'mc_redstone_blok',
    'redstone_lamp':        'mc_redstone_lamp',
    'redstone_lamp_aan':    'mc_redstone_lamp_aan',
    'redstone_draad':       'mc_redstone_draad',
    'redstone_draad_aan':   'mc_redstone_draad_aan',
}
_RS_NAAM = {
    'redstone_erts':      'Redstone-erts',
    'redstone_blok':      'Redstoneblok',
    'redstone_lamp':      'Redstonelamp',
    'redstone_lamp_aan':  'Redstonelamp (aan)',
    'redstone_draad':     'Redstone-draad',
    'redstone_draad_aan': 'Redstone-draad (aan)',
}
for _key, _tex in _RS_TEXTUUR.items():
    BLOK_TEXTUUR[_key] = _tex
    ITEM_NAMEN[_key]   = _RS_NAAM[_key]
    _rgb = _basiskleur.get(_tex, (150, 150, 150))
    KLEUREN[_key]      = color.rgb(_rgb[0] / 255, _rgb[1] / 255, _rgb[2] / 255)

# Deze redstone-blokken kun je vasthouden en plaatsen (de '..._aan' niet).
for _key in ('redstone_erts', 'redstone_blok', 'redstone_lamp', 'redstone_draad'):
    BLOK_KEUZES.append(_key)

# Recepten om redstone-dingen te maken (redstone_erts haal je uit de grond).
RECEPTEN['redstone_blok']  = {'kosten': {'redstone_erts': 4}, 'maakt': 1,
                              'plaatsbaar': True, 'is_blok': True, 'hand': False}
RECEPTEN['redstone_lamp']  = {'kosten': {'redstone_erts': 1, 'glas': 1}, 'maakt': 1,
                              'plaatsbaar': True, 'is_blok': True, 'hand': False}
RECEPTEN['redstone_draad'] = {'kosten': {'redstone_erts': 1}, 'maakt': 4,
                              'plaatsbaar': True, 'is_blok': True, 'hand': False}

# De '..._aan' blokken horen bij hun 'uit'-versie (om terug te geven bij slopen).
REDSTONE_BASIS = {
    'redstone_lamp_aan':  'redstone_lamp',
    'redstone_draad_aan': 'redstone_draad',
}
DRAAD_TYPES = {'redstone_draad', 'redstone_draad_aan'}
LAMP_TYPES  = {'redstone_lamp', 'redstone_lamp_aan'}


# We onthouden geladen plaatjes, zodat we ze maar één keer hoeven te laden.
_textuur_geheugen = {}


def blok_texture(naam):
    """Laadt een plaatje en zorgt voor SCHERPE pixels (geen wazige rand)."""
    if naam not in _textuur_geheugen:
        t = load_texture(naam)
        if t is not None:
            try:
                t.filtering = None      # 'nearest': mooie blokkerige pixels
            except Exception:
                pass
        _textuur_geheugen[naam] = t
    return _textuur_geheugen[naam]


def maak_speciaal_model(naam, pos, richting=0, uit=False):
    """Bouwt het 3D-model van een zelfgemaakt ding op plek pos.
    Geeft twee dingen terug: het model om weg te gooien bij afbreken, en
    het deel waar je op klikt (bij een deur is dat het paneel).
    'uit' = staat de piston uitgeschoven?"""
    x, y, z = pos
    hout  = KLEUREN['planken']   # houtkleur voor de houten dingen
    steen = KLEUREN['steen']

    if naam == 'hefboom':         # een schakelaar: een plaatje met een stokje
        ouder = Entity(position=pos, collider='box')
        Entity(parent=ouder, model='cube', texture='white_cube', color=steen,
               position=(0, -0.4, 0), scale=(0.5, 0.2, 0.5))          # het plaatje
        stick = Entity(parent=ouder, model='cube', texture='white_cube',
                       color=color.rgb(0.55, 0.32, 0.16), position=(0, -0.15, 0),
                       scale=(0.14, 0.7, 0.14), origin_y=-0.5, rotation_x=28)
        ouder.stick = stick       # het stokje kunnen we omzetten (aan/uit)
        return ouder, ouder

    if naam in ('piston', 'kleverige_piston'):
        kleverig = (naam == 'kleverige_piston')
        kop = color.rgb(0.45, 0.75, 0.35) if kleverig else color.rgb(0.78, 0.68, 0.5)
        ouder = Entity(position=pos, rotation_y=richting)
        Entity(parent=ouder, model='cube', color=steen, position=(0, 0, 0))   # het lijf
        Entity(parent=ouder, model='cube', color=kop,                          # de voorkant
               position=(0, 0, 0.45), scale=(0.9, 0.9, 0.12))
        if uit:                    # uitgeschoven: een arm met een kopje eraan
            Entity(parent=ouder, model='cube', color=steen,
                   position=(0, 0, 1.0), scale=(0.3, 0.3, 1.0))
            Entity(parent=ouder, model='cube', color=kop,
                   position=(0, 0, 1.45), scale=(0.9, 0.9, 0.12))
        ouder.combine(auto_destroy=True)
        ouder.texture = 'white_cube'
        ouder.collider = 'mesh'
        return ouder, ouder

    if naam == 'slab':            # een halve blok: ligt op de bodem van het vakje
        ent = Entity(model='cube', texture='white_cube', color=steen,
                     position=(x, y - 0.25, z), scale=(1, 0.5, 1), collider='box')
        return ent, ent

    if naam == 'valluik':         # een dun luikje op de vloer
        ent = Entity(model='cube', texture='white_cube', color=hout,
                     position=(x, y - 0.43, z), scale=(1, 0.15, 1), collider='box')
        return ent, ent

    if naam == 'hek':             # een paaltje met een dwarsbalkje erop
        ouder = Entity(position=pos)
        Entity(parent=ouder, model='cube', position=(0, 0,   0), scale=(0.2, 1,   0.2))
        Entity(parent=ouder, model='cube', position=(0, 0.2, 0), scale=(1,   0.15, 0.15))
        ouder.combine(auto_destroy=True)
        ouder.texture = 'white_cube'; ouder.color = hout; ouder.collider = 'box'
        return ouder, ouder

    if naam == 'trap':            # traptrede: onderste helft + achterste blokje erop
        ouder = Entity(position=pos, rotation_y=richting)
        Entity(parent=ouder, model='cube', position=(0, -0.25,  0),    scale=(1, 0.5, 1))
        Entity(parent=ouder, model='cube', position=(0,  0.25, -0.25), scale=(1, 0.5, 0.5))
        ouder.combine(auto_destroy=True)
        ouder.texture = 'white_cube'; ouder.color = steen; ouder.collider = 'mesh'
        return ouder, ouder

    if naam == 'deur':            # een deur van 2 blokken hoog die opendraait
        scharnier = Entity(position=(x - 0.5, y + 0.5, z), rotation_y=richting)
        paneel = Entity(parent=scharnier, model='cube', texture='white_cube',
                        color=hout, position=(0.45, 0, 0),
                        scale=(0.9, 1.95, 0.18), collider='box')
        return scharnier, paneel

    if naam == 'maaktafel':       # een houten blok met een grijs werkblad erop
        ouder = Entity(model='cube', texture='white_cube', color=hout,
                       position=pos, collider='box')
        Entity(parent=ouder, model='cube', texture='white_cube', color=steen,
               position=(0, 0.44, 0), scale=(0.9, 0.12, 0.9))
        return ouder, ouder

    return None, None


def plaats_speciaal(naam, pos, richting):
    """Zet een zelfgemaakt ding neer (als er plek is). Geeft True als het lukte."""
    cellen = [pos]
    if naam == 'deur':            # een deur is 2 blokken hoog
        cellen.append((pos[0], pos[1] + 1, pos[2]))
    # Alle vakjes die het ding nodig heeft, moeten leeg zijn
    for c in cellen:
        if c in wereld or c in speciaal:
            return False
    model, klik = maak_speciaal_model(naam, pos, richting)
    record = {'naam': naam, 'model': model, 'cellen': cellen,
              'open': False, 'richting': richting, 'aan': False, 'uit': False}
    klik.record = record          # zo weten we later: hier klikte je op dit ding
    for c in cellen:
        speciaal[c] = record
    return True


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


def sloop_speciaal():
    """Sloopt een zelfgemaakt ding (deur, slab, hek...) waar je op klikt en
    stopt het terug in je rugzak. Geeft True als er zoiets gesloopt is."""
    geklikt = mouse.hovered_entity
    if geklikt is not None and hasattr(geklikt, 'record'):
        record = geklikt.record
        rugzak[record['naam']] = rugzak.get(record['naam'], 0) + 1
        destroy(record['model'])
        for c in record['cellen']:
            speciaal.pop(c, None)
        geluid_afbreken.play()
        werk_hud_bij()
        if record['naam'] in ('hefboom', 'piston', 'kleverige_piston'):
            werk_redstone_bij()          # stroom opnieuw uitrekenen
        return True
    return False


def doel_hak_blok():
    """Welk gewoon wereld-blok kijk je op dit moment aan? (None = geen)."""
    if mouse.world_point is None or mouse.world_normal is None:
        return None
    geklikt = mouse.hovered_entity
    # Niet hakken op dieren/monsters of op zelfgemaakte dingen (deur/hek...)
    if geklikt is None or isinstance(geklikt, Levend) or hasattr(geklikt, 'record'):
        return None
    punt = mouse.world_point - mouse.world_normal * 0.5
    pos  = (round(punt.x), round(punt.y), round(punt.z))
    return pos if pos in wereld else None


def voltooi_breken(pos):
    """Haalt het blok echt weg (na genoeg hakken) en stopt het in je rugzak."""
    if pos not in wereld:
        return
    t = wereld.pop(pos)
    cx, cz = chunk_van_pos(pos[0], pos[2])
    chunk_blokken.get((cx, cz), {}).pop(pos, None)
    markeer_weg(pos)           # onthoud dat dit blok weg is (ook voor opslaan)
    # Was het een redstone-blok? Uit de lijst halen (straks stroom herberekenen).
    was_redstone = t in DRAAD_TYPES or t in LAMP_TYPES or t == 'redstone_blok'
    if was_redstone:
        registreer_redstone_blok(pos, t, False)
    onthul_buren(pos)          # maak de blokken eronder/ernaast aan (geen void)
    # In je rugzak stoppen (water pak je niet op). Een aan-blok geeft z'n gewone versie.
    if t != 'water':
        gekregen = REDSTONE_BASIS.get(t, t)
        rugzak[gekregen] = rugzak.get(gekregen, 0) + 1
        werk_hud_bij()
    # Soms vind je een appel als je bladeren sloopt!
    if t in BLAD_TYPES and not CREATIEF and random.random() < 0.18:
        rugzak['appel'] = rugzak.get('appel', 0) + 1
        werk_appel_hud()
        toon_melding("Je vond een appel! Druk op E om te eten.")
    # Sneeuw slopen geeft sneeuwballen (om te gooien).
    if t == 'sneeuw':
        rugzak['sneeuwbal'] = rugzak.get('sneeuwbal', 0) + 2
        werk_appel_hud()
    # Lag er een sneeuwlaagje op deze plek? Dan schep je er een sneeuwbal uit.
    if (pos[0], pos[2]) in sneeuw_lagen:
        _laag = sneeuw_lagen.pop((pos[0], pos[2]), None)
        if _laag:
            destroy(_laag)
        rugzak['sneeuwbal'] = rugzak.get('sneeuwbal', 0) + 1
        werk_appel_hud()
    geluid_afbreken.play()
    herbouw_rond(pos)
    if was_redstone:
        werk_redstone_bij()


def plaats_blok():
    """Plaatst het blok/ding dat je vasthoudt. Dit kost 1 uit je rugzak!"""
    if mouse.world_point is None or mouse.world_normal is None:
        return
    naam = vastgehouden
    if naam is None:
        return
    if not CREATIEF and rugzak.get(naam, 0) <= 0:   # in creatief heb je oneindig
        toon_melding("Je hebt dit niet (meer)! Sloop eerst wat blokken.")
        return

    # Wijs je naar een DIER terwijl je VOER vasthoudt? Dan voer je het dier
    # (er komt een baby-dier bij) in plaats van een blok te plaatsen.
    doel = mouse.hovered_entity
    if isinstance(doel, Dier) and naam in VOER:
        if (doel.world_position - speler.world_position).length() < 6:
            voer_dier(doel)
        return

    # De nieuwe plek komt net BUITEN het oppervlak (aan de kant waar je staat)
    punt = mouse.world_point + mouse.world_normal * 0.5
    pos  = (round(punt.x), round(punt.y), round(punt.z))

    # Houd je een zelfgemaakt ding vast (deur, slab, hek...)? Dan dat neerzetten.
    if is_item(naam):
        richting = round(speler.rotation_y / 90) * 90   # naar de kant waar je kijkt
        if plaats_speciaal(naam, pos, richting):
            if not CREATIEF:
                rugzak[naam] -= 1
            geluid_plaatsen.play()
            werk_hud_bij()
            if naam in ('hefboom', 'piston', 'kleverige_piston'):
                werk_redstone_bij()
        return

    # Anders: een gewoon blok plaatsen
    if pos in wereld or pos in speciaal:
        return  # Hier staat al iets
    wereld[pos] = naam
    cx, cz = chunk_van_pos(pos[0], pos[2])
    chunk_blokken.setdefault((cx, cz), {})[pos] = naam
    markeer_extra(pos, naam)   # onthoud dat je hier een blok plaatste (ook voor opslaan)
    if naam in DRAAD_TYPES or naam in LAMP_TYPES or naam == 'redstone_blok':
        registreer_redstone_blok(pos, naam, True)
        werk_redstone_bij()
    if not CREATIEF:
        rugzak[naam] -= 1      # het blok gaat uit je rugzak (in creatief: oneindig)
    geluid_plaatsen.play()
    werk_hud_bij()
    herbouw_rond(pos)


# ======================================================================
#  REDSTONE-MOTOR ⚡ (stroom door draden, lampen aan, pistons duwen)
# ======================================================================
redstone_draad_cellen = set()   # alle plekken met redstone-draad
redstone_lamp_cellen  = set()   # alle plekken met een redstonelamp
redstone_blok_cellen  = set()   # alle plekken met een redstoneblok (stroombron)
redstone_moet_update  = False   # moeten we de stroom opnieuw uitrekenen?


def registreer_redstone_blok(pos, bloktype, erbij):
    """Houd de redstone-lijsten bij als er een blok bij komt of weg gaat."""
    global redstone_moet_update
    if bloktype in DRAAD_TYPES:
        lijst = redstone_draad_cellen
    elif bloktype in LAMP_TYPES:
        lijst = redstone_lamp_cellen
    elif bloktype == 'redstone_blok':
        lijst = redstone_blok_cellen
    else:
        return
    lijst.add(pos) if erbij else lijst.discard(pos)
    redstone_moet_update = True


def _zet_bloktype(pos, nieuw):
    """Verandert stil het bloktype op een plek (bv draad -> draad_aan)."""
    cx, cz = chunk_van_pos(pos[0], pos[2])
    wereld[pos] = nieuw
    chunk_blokken.setdefault((cx, cz), {})[pos] = nieuw
    extra_blokken[pos] = nieuw
    extra_index[(cx, cz)][pos] = nieuw


def _unieke_specials():
    """Alle zelfgemaakte dingen, elk maar één keer (deuren hebben 2 cellen)."""
    gezien, uit = set(), []
    for rec in speciaal.values():
        if id(rec) not in gezien:
            gezien.add(id(rec))
            uit.append(rec)
    return uit


def _voor_vector(richting):
    """De richting (x, y, z) waar een piston naartoe wijst."""
    r = math.radians(richting)
    return (round(math.sin(r)), 0, round(math.cos(r)))


def _verplaats_blok(van, naar, te_herbouwen):
    """Verplaatst een gewoon blok van 'van' naar 'naar' (voor een piston)."""
    t = wereld.pop(van)
    cxv, czv = chunk_van_pos(van[0], van[2])
    chunk_blokken.get((cxv, czv), {}).pop(van, None)
    markeer_weg(van)
    registreer_redstone_blok(van, t, False)
    wereld[naar] = t
    cxn, czn = chunk_van_pos(naar[0], naar[2])
    chunk_blokken.setdefault((cxn, czn), {})[naar] = t
    markeer_extra(naar, t)
    registreer_redstone_blok(naar, t, True)
    te_herbouwen.add((cxv, czv))
    te_herbouwen.add((cxn, czn))


def _herteken_piston(rec):
    """Tekent een piston opnieuw (in- of uitgeschoven)."""
    destroy(rec['model'])
    model, klik = maak_speciaal_model(rec['naam'], rec['cellen'][0],
                                      rec['richting'], uit=rec['uit'])
    klik.record = rec
    rec['model'] = model


def _piston_uit(rec, te_herbouwen):
    """Schuift een piston uit en duwt het blok ervoor één plek weg."""
    pos = rec['cellen'][0]
    vx, vy, vz = _voor_vector(rec['richting'])
    front  = (pos[0] + vx, pos[1] + vy, pos[2] + vz)
    front2 = (front[0] + vx, front[1] + vy, front[2] + vz)
    if front in speciaal:
        return                          # er staat een ander ding voor
    geduwd = False
    if front in wereld:
        if front2 not in wereld and front2 not in speciaal:
            _verplaats_blok(front, front2, te_herbouwen)
            geduwd = True
        else:
            return                      # blok voor de piston kan nergens heen
    rec['uit'] = True
    rec['geduwd'] = geduwd
    if front not in rec['cellen']:
        rec['cellen'].append(front)
    speciaal[front] = rec               # armcel bezet houden
    _herteken_piston(rec)
    te_herbouwen.add(chunk_van_pos(pos[0], pos[2]))


def _piston_in(rec, te_herbouwen):
    """Schuift een piston in; een kleverige piston trekt het blok weer terug."""
    pos = rec['cellen'][0]
    vx, vy, vz = _voor_vector(rec['richting'])
    front  = (pos[0] + vx, pos[1] + vy, pos[2] + vz)
    front2 = (front[0] + vx, front[1] + vy, front[2] + vz)
    if (rec['naam'] == 'kleverige_piston' and rec.get('geduwd')
            and front2 in wereld and front not in wereld):
        _verplaats_blok(front2, front, te_herbouwen)
    rec['uit'] = False
    rec['geduwd'] = False
    if front in rec['cellen'] and front != pos:
        rec['cellen'].remove(front)
    if speciaal.get(front) is rec:
        del speciaal[front]
    _herteken_piston(rec)
    te_herbouwen.add(chunk_van_pos(pos[0], pos[2]))


def werk_redstone_bij():
    """Rekent de hele redstone opnieuw uit: welke draden staan aan, welke lampen
    branden en welke pistons schuiven uit. Aanroepen als er iets verandert."""
    global redstone_moet_update
    redstone_moet_update = False

    # 1. Stroombronnen: redstoneblokken + hefbomen die AAN staan.
    bron_cellen = set(redstone_blok_cellen)
    for rec in _unieke_specials():
        if rec['naam'] == 'hefboom' and rec.get('aan'):
            bron_cellen.add(rec['cellen'][0])

    # 2. Stroom door de draden laten stromen (elke stap 1 minder, tot 0).
    power = {}
    rij = collections.deque()
    for d in redstone_draad_cellen:
        if any((d[0] + bx, d[1] + by, d[2] + bz) in bron_cellen for bx, by, bz in BUREN):
            power[d] = 15
            rij.append(d)
    while rij:
        d = rij.popleft()
        p = power[d]
        if p <= 1:
            continue
        for bx, by, bz in BUREN:
            n = (d[0] + bx, d[1] + by, d[2] + bz)
            if n in redstone_draad_cellen and power.get(n, 0) < p - 1:
                power[n] = p - 1
                rij.append(n)
    aan_draad = set(power)

    def krijgt_stroom(p):
        for bx, by, bz in BUREN:
            n = (p[0] + bx, p[1] + by, p[2] + bz)
            if n in bron_cellen or n in aan_draad:
                return True
        return False

    te_herbouwen = set()

    # 3. Draden aan/uit (kleur) zetten.
    for d in redstone_draad_cellen:
        gewenst = 'redstone_draad_aan' if d in aan_draad else 'redstone_draad'
        if wereld.get(d) != gewenst:
            _zet_bloktype(d, gewenst)
            te_herbouwen.add(chunk_van_pos(d[0], d[2]))

    # 4. Lampen aan/uit zetten.
    for l in redstone_lamp_cellen:
        gewenst = 'redstone_lamp_aan' if krijgt_stroom(l) else 'redstone_lamp'
        if wereld.get(l) != gewenst:
            _zet_bloktype(l, gewenst)
            te_herbouwen.add(chunk_van_pos(l[0], l[2]))

    # 5. Pistons in-/uitschuiven.
    for rec in _unieke_specials():
        if rec['naam'] in ('piston', 'kleverige_piston'):
            aan = krijgt_stroom(rec['cellen'][0])
            if aan and not rec['uit']:
                _piston_uit(rec, te_herbouwen)
            elif not aan and rec['uit']:
                _piston_in(rec, te_herbouwen)

    # 6. De veranderde stukjes opnieuw tekenen.
    for c in te_herbouwen:
        if c in chunk_modellen:
            bouw_chunk_model(*c)


def sla_op(stil=False):
    """Slaat de wereld op in een bestandje, zodat je later verder kunt spelen.
    stil=True = geen melding op het scherm (voor automatisch opslaan)."""
    # De zelfgemaakte dingen (deuren, hekken, hefbomen...) verzamelen, elk 1x.
    unieke = {}
    for rec in speciaal.values():
        unieke[tuple(rec['cellen'][0])] = rec
    spec = [{'naam': r['naam'], 'pos': list(p), 'richting': r['richting'],
             'aan': r.get('aan', False)}
            for p, r in unieke.items()]

    data = {
        'zaad': WERELD_ZAAD,
        'creatief': CREATIEF,
        'weg':   [list(p) for p in weggehaald],
        'extra': [[p[0], p[1], p[2], t] for p, t in extra_blokken.items()],
        'speciaal': spec,
        'rugzak': rugzak,
        'pikhouweel': pikhouweel_niveau,
        'honger': honger,
        'hotbar': hotbar_volgorde,
        'speler': [speler.x, speler.y, speler.z, speler.rotation_y, camera.rotation_x],
        'dag_tijd': dag_tijd,
        # De bootjes die je gemaakt hebt en de golems die JIJ hebt neergezet.
        # (De golems van de dorpjes komen vanzelf terug, die slaan we niet op.)
        'boten':  [[b.x, b.y, b.z] for b in boten],
        'golems': [[g.x, g.y, g.z] for g in golems if g.eigen],
    }
    try:
        with open(OPSLAG_PAD, 'w') as f:
            json.dump(data, f)
        if not stil:
            toon_melding("Wereld opgeslagen! Je kunt gerust stoppen.")
    except Exception:
        if not stil:
            toon_melding("Oeps, opslaan lukte niet.")


# --- Geluiden ---
geluid_plaatsen = Audio('plop',  autoplay=False)   # plop bij plaatsen
geluid_afbreken = Audio('boink', autoplay=False)   # boink bij afbreken
geluid_wissel   = Audio('plop',  autoplay=False, volume=0.4)  # zacht tikje bij wisselen van blok


class Levend(Entity):
    """De basis voor alle dieren en monsters. Ze blijven op de grond staan
    en je kunt ze slaan (ze hebben levens en gaan dood bij 0)."""

    def __init__(self, positie, levens, lijst):
        super().__init__(parent=scene, position=positie)
        self.levens     = levens
        self.lijst      = lijst       # de lijst waar dit wezen in staat
        self.snelheid   = 1.5
        self.richting   = random.uniform(0, 360)
        self.loop_timer = 0
        self.delen      = []          # de zichtbare blokjes (om rood te flitsen)
        # Een onzichtbare 'box' eromheen, zodat je het kunt aanklikken en slaan
        self.collider   = BoxCollider(self, center=Vec3(0, 0.3, 0),
                                      size=Vec3(1, 1.8, 1.4))

    def maak_deel(self, **kw):
        """Maakt een blokje (lichaamsdeel) en onthoudt het voor de rode flits."""
        deel = Entity(parent=self, model='cube', **kw)
        self.delen.append(deel)
        return deel

    def raak(self, schade=1):
        """Wordt aangeroepen als je het wezen slaat."""
        self.levens -= schade
        for deel in self.delen:
            deel.blink(color.red, duration=0.2)   # even rood knipperen: au!
        if self.levens <= 0:
            self.ga_dood()

    def ga_dood(self):
        if self in self.lijst:
            self.lijst.remove(self)
        destroy(self)

    def op_de_grond(self, hoogte):
        """Houd het wezen netjes op de grond (ook op het vlakke dorpsplein)."""
        self.y = grond_onder(self.x, self.z) + hoogte

    def loop_vooruit(self, achteruit=False):
        """Zet een stapje vooruit (of achteruit), maar NIET door muren heen.
        We voelen eerst met een straaltje: zit er vlak voor zijn neus een blok?
        Dan blijft hij staan."""
        voor = self.forward * (-1 if achteruit else 1)
        muur = raycast(self.world_position, voor, distance=0.6,
                       ignore=[self] + alle_wezens())
        if not muur.hit:
            self.position += voor * time.dt * self.snelheid


def alle_wezens():
    """Alle dieren, villagers, golems en monsters bij elkaar. Handig om
    straaltjes (raycasts) ze te laten NEGEREN: we willen alleen echte blokken
    voelen."""
    return monsters + dieren + villagers + golems


# Wezens die VER van de speler vandaan zijn hoeven niets te doen: je ziet ze
# toch niet. Dat scheelt een hoop rekenwerk nu er meerdere dorpjes zijn.
SLAAP_AFSTAND = 60


def slaapt(wezen):
    """Staat dit wezen zo ver weg dat het even niets hoeft te doen?"""
    return (wezen.world_position - speler.world_position).length() > SLAAP_AFSTAND


class Dier(Levend):
    """Een vreedzaam dier dat rustig rondloopt. Je kunt het slaan of voeren."""

    def __init__(self, positie):
        super().__init__(positie, levens=2, lijst=dieren)
        self.groeit = False       # groeit dit dier nog van baby naar groot?

    def word_baby(self):
        """Maak dit een klein baby-dier dat langzaam groter wordt."""
        self.scale = 0.5
        self.groeit = True

    def update(self):
        self.loop_timer -= time.dt
        if self.loop_timer <= 0:                     # af en toe een nieuwe kant op
            self.richting   = random.uniform(0, 360)
            self.loop_timer = random.uniform(1, 3)
        self.rotation_y = self.richting
        self.position  += self.forward * time.dt * self.snelheid
        # Hoogte boven de grond: een baby zit lager (want hij is kleiner).
        self.op_de_grond(1.2 * self.scale_x)
        # Een baby groeit langzaam naar z'n volle grootte.
        if self.groeit:
            nieuw = min(1.0, self.scale_x + time.dt * 0.04)
            self.scale = nieuw
            if nieuw >= 1.0:
                self.groeit = False


class Varken(Dier):
    """Een roze varken."""

    def __init__(self, positie):
        super().__init__(positie)
        roze       = color.rgb(1.0, 0.7, 0.75)
        donkerroze = color.rgb(0.9, 0.5, 0.55)
        self.maak_deel(color=roze, scale=(0.9, 0.7, 1.3))                       # lichaam
        self.maak_deel(color=donkerroze, position=(0, 0, 0.7), scale=(0.4, 0.4, 0.2))  # snuit
        for px in (-0.3, 0.3):
            for pz in (-0.45, 0.45):
                self.maak_deel(color=donkerroze, position=(px, -0.45, pz),
                               scale=(0.2, 0.5, 0.2))                           # pootjes


class Koe(Dier):
    """Een zwart-witte koe."""

    def __init__(self, positie):
        super().__init__(positie)
        wit    = color.rgb(0.95, 0.95, 0.95)
        zwart  = color.rgb(0.15, 0.15, 0.15)
        self.maak_deel(color=wit, scale=(1.0, 0.9, 1.5))                        # lichaam
        self.maak_deel(color=zwart, position=(0.3, 0.2, 0.3), scale=(0.4, 0.4, 0.4))  # vlek
        self.maak_deel(color=wit, position=(0, 0.2, 0.85), scale=(0.5, 0.5, 0.4))     # kop
        for px in (-0.35, 0.35):
            for pz in (-0.55, 0.55):
                self.maak_deel(color=wit, position=(px, -0.6, pz),
                               scale=(0.22, 0.6, 0.22))                         # pootjes


class Schaap(Dier):
    """Een wollig schaap."""

    def __init__(self, positie):
        super().__init__(positie)
        wol  = color.rgb(0.95, 0.95, 0.9)
        kop  = color.rgb(0.2, 0.2, 0.2)
        self.maak_deel(color=wol, scale=(0.9, 0.9, 1.2))                        # wollig lijf
        self.maak_deel(color=kop, position=(0, 0.1, 0.7), scale=(0.4, 0.4, 0.4))  # kop
        for px in (-0.3, 0.3):
            for pz in (-0.4, 0.4):
                self.maak_deel(color=kop, position=(px, -0.6, pz),
                               scale=(0.18, 0.6, 0.18))                         # pootjes


class Kip(Dier):
    """Een klein wit kippetje."""

    def __init__(self, positie):
        super().__init__(positie)
        self.snelheid = 1.9
        wit  = color.rgb(0.97, 0.97, 0.95)
        geel = color.rgb(0.95, 0.8, 0.2)
        rood = color.rgb(0.85, 0.2, 0.2)
        self.maak_deel(color=wit,  scale=(0.45, 0.45, 0.65))                    # lijfje
        self.maak_deel(color=wit,  position=(0, 0.35, 0.3), scale=(0.32, 0.35, 0.3))  # kop
        self.maak_deel(color=rood, position=(0, 0.58, 0.3), scale=(0.14, 0.14, 0.1))  # kam
        self.maak_deel(color=geel, position=(0, 0.35, 0.48), scale=(0.12, 0.1, 0.18)) # snavel
        for px in (-0.12, 0.12):
            self.maak_deel(color=geel, position=(px, -0.35, 0), scale=(0.07, 0.4, 0.07))  # pootjes


class Konijn(Dier):
    """Een snel bruin konijntje met lange oren."""

    def __init__(self, positie):
        super().__init__(positie)
        self.snelheid = 2.3
        bruin  = color.rgb(0.72, 0.56, 0.42)
        licht  = color.rgb(0.85, 0.72, 0.6)
        self.maak_deel(color=bruin, scale=(0.4, 0.4, 0.6))                       # lijfje
        self.maak_deel(color=bruin, position=(0, 0.25, 0.3), scale=(0.32, 0.32, 0.3))  # kop
        for ox in (-0.09, 0.09):
            self.maak_deel(color=licht, position=(ox, 0.55, 0.28), scale=(0.1, 0.4, 0.1))  # oren
        for px in (-0.13, 0.13):
            self.maak_deel(color=bruin, position=(px, -0.28, -0.05), scale=(0.12, 0.3, 0.16))  # pootjes


# --- Wat de villagers met je willen RUILEN ---
# Elk beroep heeft zijn eigen ruiltjes: (wat je GEEFT, wat je KRIJGT).
# Smaragd is het geld van het dorp, net als in het echte Minecraft!
HANDEL = {
    'Boer': [
        ({'appel': 6},    {'smaragd': 1}),
        ({'smaragd': 1},  {'appel': 4}),
        ({'smaragd': 2},  {'pompoen': 3}),
    ],
    'Houthakker': [
        ({'hout': 10},    {'smaragd': 1}),
        ({'smaragd': 1},  {'planken': 8}),
        ({'smaragd': 2},  {'deur': 1}),
    ],
    'Mijnwerker': [
        ({'steen': 15},   {'smaragd': 1}),
        ({'kool': 8},     {'smaragd': 1}),
        ({'smaragd': 3},  {'ijzer': 2}),
        ({'smaragd': 6},  {'diamant': 1}),
    ],
    'Smid': [
        ({'ijzer': 3},    {'smaragd': 1}),
        ({'smaragd': 4},  {'goud': 2}),
        ({'smaragd': 5},  {'ijzeren_pikhouweel': 1}),
    ],
}

# De kleur van het schort dat bij elk beroep hoort (zo herken je ze!)
BEROEP_KLEUR = {
    'Boer':       color.rgb(0.85, 0.75, 0.25),   # geel als stro
    'Houthakker': color.rgb(0.55, 0.35, 0.18),   # bruin als hout
    'Mijnwerker': color.rgb(0.45, 0.45, 0.5),    # grijs als steen
    'Smid':       color.rgb(0.2,  0.25, 0.3),    # donker als ijzer
}


class Villager(Levend):
    """Een villager (dorpeling): een vriendelijk mensje uit het dorp.
    Klik erop met de linkermuis en je kunt met hem RUILEN.
    's Nachts loopt hij naar huis, en voor monsters rent hij hard weg!"""

    def __init__(self, positie, beroep, thuis):
        super().__init__(positie, levens=6, lijst=villagers)
        self.beroep   = beroep
        self.thuis    = Vec3(*thuis)      # bij welk huisje hoort hij?
        self.snelheid = 1.1
        huid    = color.rgb(0.78, 0.62, 0.48)
        mantel  = color.rgb(0.45, 0.3, 0.2)
        schort  = BEROEP_KLEUR[beroep]
        donker  = color.rgb(0.15, 0.12, 0.1)
        self.maak_deel(color=mantel, position=(0, 0.15, 0),  scale=(0.55, 1.2, 0.35))  # mantel
        self.maak_deel(color=schort, position=(0, 0.35, 0),  scale=(0.58, 0.4, 0.38))  # schort
        self.maak_deel(color=mantel, position=(0, 0.15, 0.2), scale=(0.62, 0.22, 0.18))  # armen
        self.maak_deel(color=huid,   position=(0, 1.05, 0),  scale=(0.5, 0.55, 0.45))  # kop
        # De beroemde GROTE neus van een villager
        self.maak_deel(color=color.rgb(0.7, 0.54, 0.4), position=(0, 1.0, 0.28),
                       scale=(0.16, 0.3, 0.2))
        for ex in (-0.15, 0.15):                                                       # ogen
            self.maak_deel(color=color.rgb(0.2, 0.25, 0.5), position=(ex, 1.18, 0.23),
                           scale=(0.1, 0.12, 0.06))
        self.maak_deel(color=donker, position=(0, 1.3, 0.23), scale=(0.45, 0.07, 0.05))  # wenkbrauw
        for px in (-0.13, 0.13):                                                       # benen
            self.maak_deel(color=donker, position=(px, -0.6, 0), scale=(0.18, 0.6, 0.2))

    def dichtstbijzijnde_monster(self):
        """Loopt er een monster vlakbij? Geef dan het dichtstbijzijnde terug."""
        dichtste, kortste = None, 9
        for m in monsters:
            d = (m.world_position - self.world_position).length()
            if d < kortste:
                dichtste, kortste = m, d
        return dichtste

    def update(self):
        if slaapt(self):
            return                  # hij woont in een dorp ver weg: even niks doen
        bang_voor = self.dichtstbijzijnde_monster()
        if bang_voor is not None:
            # Help, een monster! Wegrennen, precies de andere kant op.
            weg = self.world_position - bang_voor.world_position
            self.look_at(self.world_position + Vec3(weg.x, 0, weg.z))
            self.snelheid = 2.6                      # rennen gaat sneller
            self.loop_vooruit()
        elif het_is_nacht:
            # 's Nachts wil hij lekker naar huis.
            self.snelheid = 1.4
            naar_huis = Vec3(self.thuis.x - self.x, 0, self.thuis.z - self.z)
            if naar_huis.length() > 1.0:
                self.look_at(Vec3(self.thuis.x, self.y, self.thuis.z))
                self.loop_vooruit()
        else:
            # Overdag rustig rondwandelen, maar wel in de buurt van zijn huisje.
            self.snelheid = 1.1
            self.loop_timer -= time.dt
            if self.loop_timer <= 0:
                self.loop_timer = random.uniform(1.5, 4)
                ver_van_huis = Vec3(self.thuis.x - self.x, 0, self.thuis.z - self.z)
                if ver_van_huis.length() > 10:
                    self.look_at(Vec3(self.thuis.x, self.y, self.thuis.z))
                    self.richting = self.rotation_y      # weer richting huis
                else:
                    self.richting = random.uniform(0, 360)
            self.rotation_y = self.richting
            self.loop_vooruit()
        self.op_de_grond(1.15)


GOLEM_HOOGTE = 1.35    # zo hoog zit het midden van een golem boven de grond


class IJzerGolem(Levend):
    """Een grote sterke ijzergolem. Hij bewaakt het dorp: ziet hij een monster,
    dan stampt hij erheen en mept hij het met één klap ver weg. Jou en de
    villagers doet hij niets — die beschermt hij juist!"""

    def __init__(self, positie, thuis):
        super().__init__(positie, levens=30, lijst=golems)   # heel veel levens
        self.thuis        = Vec3(*thuis)     # welk dorp bewaakt hij?
        self.snelheid     = 1.5
        self.sla_cooldown = 0
        self.eigen        = False            # heeft de speler hem zelf gemaakt?
        ijzer  = color.rgb(0.82, 0.81, 0.78)   # licht ijzergrijs
        donker = color.rgb(0.62, 0.61, 0.58)   # donkerder grijs
        rank   = color.rgb(0.35, 0.6, 0.25)    # groene ranken op zijn buik
        neus   = color.rgb(0.72, 0.6, 0.5)
        self.maak_deel(color=ijzer,  position=(0, 0.5, 0),    scale=(1.0, 1.4, 0.6))   # lijf
        self.maak_deel(color=rank,   position=(0, 0.35, 0.32), scale=(0.5, 0.7, 0.06)) # ranken
        self.maak_deel(color=ijzer,  position=(0, 1.55, 0),   scale=(0.55, 0.6, 0.5))  # kop
        self.maak_deel(color=neus,   position=(0, 1.45, 0.28), scale=(0.16, 0.5, 0.16))# lange neus
        for ex in (-0.16, 0.16):                                                       # ogen
            self.maak_deel(color=color.rgb(0.5, 0.15, 0.15),
                           position=(ex, 1.72, 0.24), scale=(0.12, 0.1, 0.06))
        for ax in (-0.72, 0.72):                                                       # dikke armen
            self.maak_deel(color=donker, position=(ax, 0.35, 0), scale=(0.35, 1.8, 0.35))
        for px in (-0.28, 0.28):                                                       # stevige benen
            self.maak_deel(color=donker, position=(px, -0.75, 0), scale=(0.4, 1.1, 0.45))
        # Hij is groter dan een dier, dus ook een grotere klik-box
        self.collider = BoxCollider(self, center=Vec3(0, 0.6, 0),
                                    size=Vec3(1.4, 2.8, 1.2))

    def zoek_monster(self):
        """Zoekt het dichtstbijzijnde monster binnen 16 blokken."""
        dichtste, kortste = None, 16
        for m in monsters:
            d = (m.world_position - self.world_position).length()
            if d < kortste:
                dichtste, kortste = m, d
        return dichtste

    def mep(self, monster):
        """BENG! Een klap van een golem doet heel veel pijn en slaat het
        monster een flink stuk weg."""
        weg = monster.world_position - self.world_position
        plat = Vec3(weg.x, 0, weg.z)
        if plat.length() > 0.01:
            monster.position += plat.normalized() * 2.5     # ver weggeslagen
        monster.raak(5)
        geluid_afbreken.play()

    def update(self):
        if slaapt(self):
            return                       # veel te ver weg: even niks doen
        self.sla_cooldown -= time.dt
        doel = self.zoek_monster()
        if doel is not None:
            # Een monster! Erop af en meppen.
            self.look_at(Vec3(doel.x, self.y, doel.z))
            afstand = Vec3(doel.x - self.x, 0, doel.z - self.z).length()
            if afstand > 2.0:
                self.snelheid = 2.1      # rennen
                self.loop_vooruit()
            elif self.sla_cooldown <= 0:
                self.sla_cooldown = 1.2  # even bijkomen na een klap
                self.mep(doel)
        elif self.eigen and Vec3(speler.x - self.x, 0, speler.z - self.z).length() > 4:
            # Een golem die JIJ gemaakt hebt loopt als een maatje met je mee,
            # zodat hij altijd in de buurt is als er een monster komt.
            self.snelheid = 2.0
            self.look_at(Vec3(speler.x, self.y, speler.z))
            self.loop_vooruit()
        else:
            # Geen monsters: rustig een rondje lopen door zijn dorp.
            self.snelheid = 1.0
            self.loop_timer -= time.dt
            if self.loop_timer <= 0:
                self.loop_timer = random.uniform(2, 5)
                ver_van_huis = Vec3(self.thuis.x - self.x, 0, self.thuis.z - self.z)
                if ver_van_huis.length() > 12:
                    self.look_at(Vec3(self.thuis.x, self.y, self.thuis.z))
                    self.richting = self.rotation_y     # weer terug naar het dorp
                else:
                    self.richting = random.uniform(0, 360)
            self.rotation_y = self.richting
            self.loop_vooruit()
        self.op_de_grond(GOLEM_HOOGTE)


class Monster(Levend):
    """Een boos monster dat naar je toe loopt en je aanvalt. Sla het terug!
    Dit is ook de BASIS voor het skelet en de creeper: die erven het lopen,
    het kijken naar de speler en het 'vrij_zicht' van dit monster."""

    def __init__(self, positie):
        super().__init__(positie, levens=3, lijst=monsters)
        self.snelheid    = 1.9
        self.sla_cooldown = 0
        self.maak_lijf()          # elk soort monster ziet er anders uit

    def maak_lijf(self):
        """Bouwt het groene zombie-lijf. Skelet en creeper maken hun eigen lijf."""
        groen  = color.rgb(0.2, 0.5, 0.2)
        donker = color.rgb(0.1, 0.3, 0.1)
        self.maak_deel(color=groen,  position=(0, 0.1, 0),  scale=(0.8, 1.2, 0.5))   # lijf
        self.maak_deel(color=donker, position=(0, 0.95, 0), scale=(0.6, 0.6, 0.6))   # kop
        for ex in (-0.13, 0.13):                                                     # rode ogen
            self.maak_deel(color=color.red, position=(ex, 1.0, 0.28),
                           scale=(0.12, 0.12, 0.1))
        for px in (-0.22, 0.22):
            self.maak_deel(color=donker, position=(px, -0.6, 0), scale=(0.25, 0.7, 0.3))  # benen

    def update(self):
        # Reken uit welke kant de speler op is (alleen plat, niet omhoog/omlaag)
        naar = speler.world_position - self.world_position
        plat = Vec3(naar.x, 0, naar.z)
        afstand = plat.length()
        if afstand > 0.1:
            self.look_at(Vec3(speler.x, self.y, speler.z))   # kijk naar de speler
            if afstand > 1.3:                                # loop ernaartoe
                self.loop_vooruit()
        self.op_de_grond(1.0)
        # Het monster mag je ALLEEN slaan als het ECHT naast je staat:
        #  1) vlakbij op de plattegrond (naast je, niet ver weg),
        #  2) ongeveer op dezelfde hoogte (niet boven of onder je),
        #  3) met vrij zicht (geen blok ertussen).
        self.sla_cooldown -= time.dt
        if (self.sla_cooldown <= 0 and afstand < 1.7
                and abs(naar.y) < 1.6 and self.vrij_zicht()):
            self.sla_cooldown = 1.0
            doe_schade(1)

    def vrij_zicht(self):
        """Kan het monster je echt zien, of zit er een BLOK tussen?
        We schieten een onzichtbaar straaltje van het monster naar jou.
        Andere monsters en dieren tellen NIET mee (die negeren we), alleen
        echte blokken. Raakt het straaltje een blok? Dan is het zicht geblokkeerd."""
        oog  = self.world_position + Vec3(0, 1, 0)     # ongeveer het hoofd
        doel = speler.world_position + Vec3(0, 1, 0)    # ongeveer jouw lijf
        naar = doel - oog
        afst = naar.length()
        if afst < 0.01:
            return True
        straal = raycast(oog, naar.normalized(), distance=afst,
                         ignore=[self] + alle_wezens())
        return not straal.hit                           # niks geraakt = vrij zicht


class Skelet(Monster):
    """Een skelet houdt AFSTAND en schiet pijlen op je. Kom dichtbij, want
    van dichtbij loopt hij juist bij je weg!"""

    def __init__(self, positie):
        super().__init__(positie)
        self.snelheid    = 1.6
        self.schiet_timer = random.uniform(1.0, 2.0)   # hoe lang tot de volgende pijl

    def maak_lijf(self):
        bot    = color.rgb(0.9, 0.9, 0.85)      # botwit
        zwart  = color.rgb(0.05, 0.05, 0.05)
        hout   = color.rgb(0.45, 0.3, 0.15)
        self.maak_deel(color=bot,   position=(0, 0.1, 0),   scale=(0.45, 1.2, 0.3))  # smal lijf
        self.maak_deel(color=bot,   position=(0, 0.95, 0),  scale=(0.55, 0.55, 0.55))  # kop
        for ex in (-0.13, 0.13):                                                     # oogkassen
            self.maak_deel(color=zwart, position=(ex, 1.0, 0.26), scale=(0.14, 0.14, 0.08))
        for ax in (-0.35, 0.35):                                                     # dunne armen
            self.maak_deel(color=bot, position=(ax, 0.3, 0.25), scale=(0.15, 0.15, 0.8))
        self.maak_deel(color=hout, position=(0, 0.3, 0.6), scale=(0.08, 0.8, 0.08))  # de boog
        for px in (-0.14, 0.14):                                                     # dunne benen
            self.maak_deel(color=bot, position=(px, -0.6, 0), scale=(0.16, 0.7, 0.16))

    def update(self):
        naar = speler.world_position - self.world_position
        plat = Vec3(naar.x, 0, naar.z)
        afstand = plat.length()
        if afstand > 0.1:
            self.look_at(Vec3(speler.x, self.y, speler.z))   # kijk naar de speler
            # Een skelet wil je op AFSTAND houden: te ver weg? Kom dichterbij.
            # Te dichtbij? Loop juist achteruit. Daartussenin blijft hij staan.
            if afstand > 9:
                self.loop_vooruit()
            elif afstand < 5:
                self.loop_vooruit(achteruit=True)
        self.op_de_grond(1.0)
        # Af en toe een pijl schieten, maar alleen als hij je echt kan zien.
        self.schiet_timer -= time.dt
        if self.schiet_timer <= 0 and afstand < 14 and self.vrij_zicht():
            self.schiet_timer = random.uniform(1.8, 2.6)
            self.schiet_pijl()

    def schiet_pijl(self):
        """Schiet een pijl richting de speler."""
        start = self.world_position + Vec3(0, 1.0, 0)        # vanaf zijn hoofd
        doel  = speler.world_position + Vec3(0, 1.0, 0)      # naar jouw lijf
        richting = (doel - start).normalized()
        pijl = Entity(model='cube', color=color.rgb(0.5, 0.35, 0.2),
                      scale=(0.07, 0.07, 0.7), position=start)
        pijl.look_at(doel)                                    # met de punt vooruit
        pijl.snelheid = richting * 18 + Vec3(0, 1.5, 0)       # een beetje omhoog mikken
        pijl.leeftijd = 0.0
        pijlen_vliegend.append(pijl)


class Creeper(Monster):
    """Een creeper rent naar je toe, gaat SISSEN en ontploft dan met een
    grote knal: een gat in de wereld en flink wat schade. Ren op tijd weg!"""

    LONT_TIJD = 1.5      # hoeveel seconden hij sist voordat hij knalt
    KNAL_STRAAL = 3      # hoe groot het gat wordt (in blokken)

    def __init__(self, positie):
        super().__init__(positie)
        self.snelheid = 2.2
        self.lont     = None       # None = nog niet aan het sissen
        # De eigen kleuren onthouden, zodat we tijdens het sissen kunnen
        # knipperen en daarna weer netjes terug kunnen kleuren.
        self.kleuren  = [deel.color for deel in self.delen]

    def maak_lijf(self):
        groen  = color.rgb(0.35, 0.65, 0.3)
        donker = color.rgb(0.2, 0.45, 0.2)
        zwart  = color.rgb(0.05, 0.1, 0.05)
        self.maak_deel(color=groen, position=(0, 0.25, 0),  scale=(0.6, 1.1, 0.4))   # hoog lijf
        self.maak_deel(color=groen, position=(0, 1.05, 0),  scale=(0.65, 0.65, 0.5)) # vierkante kop
        # Het bekende creeper-gezicht: twee ogen en een mond
        for ex in (-0.16, 0.16):
            self.maak_deel(color=zwart, position=(ex, 1.15, 0.26), scale=(0.18, 0.18, 0.06))
        self.maak_deel(color=zwart, position=(0, 0.95, 0.26), scale=(0.18, 0.28, 0.06))
        for ex in (-0.14, 0.14):
            self.maak_deel(color=zwart, position=(ex, 0.87, 0.26), scale=(0.1, 0.12, 0.06))
        # Vier korte pootjes en GEEN armen (net als in het echte spel)
        for px in (-0.18, 0.18):
            for pz in (-0.15, 0.15):
                self.maak_deel(color=donker, position=(px, -0.5, pz), scale=(0.22, 0.45, 0.2))

    def update(self):
        naar = speler.world_position - self.world_position
        plat = Vec3(naar.x, 0, naar.z)
        afstand = plat.length()
        if afstand > 0.1:
            self.look_at(Vec3(speler.x, self.y, speler.z))
        self.op_de_grond(0.75)

        if self.lont is None:
            # Nog niet aan het sissen: gewoon achter de speler aan rennen.
            if afstand > 1.3:
                self.loop_vooruit()
            # Dichtbij genoeg én hij ziet je? Dan begint de lont te branden!
            if afstand < 2.5 and abs(naar.y) < 2.5 and self.vrij_zicht():
                self.start_sissen()
        else:
            # De lont brandt: hij staat stil, knippert wit en telt af.
            self.lont -= time.dt
            self.knipper(int(self.lont * 8) % 2 == 0)
            if afstand > 4.5:
                self.stop_sissen()        # je bent ontsnapt, hij kalmeert weer
            elif self.lont <= 0:
                self.ontplof()

    def knipper(self, wit):
        """Zet alle lichaamsdelen wit (wit=True) of weer in hun eigen kleur."""
        for deel, kleur in zip(self.delen, self.kleuren):
            deel.color = color.white if wit else kleur

    def start_sissen(self):
        """Ssssss... de creeper zwelt op en gaat knipperen."""
        self.lont = Creeper.LONT_TIJD
        self.animate_scale(1.3, duration=Creeper.LONT_TIJD)
        geluid_wissel.play()

    def stop_sissen(self):
        """Je bent weggerend: de creeper wordt weer rustig."""
        self.lont = None
        self.animate_scale(1.0, duration=0.3)
        self.knipper(False)               # weer zijn eigen kleur

    def ontplof(self):
        """BOEM! Schade voor alles in de buurt en een gat in de wereld."""
        midden = self.world_position
        # 1) Schade voor de speler: hoe dichterbij, hoe meer het pijn doet.
        afstand = (speler.world_position - midden).length()
        if afstand < 5:
            doe_schade(max(1, 6 - int(afstand)))
        # 2) Andere dieren, villagers en monsters in de buurt krijgen er ook van langs.
        for wezen in alle_wezens():
            if wezen is not self and (wezen.world_position - midden).length() < 4:
                wezen.raak(3)
        # 3) Een gat in de blokken
        blaas_blokken_weg(midden, Creeper.KNAL_STRAAL)
        # 4) Een mooie knal om naar te kijken
        knal_effect(midden)
        toon_melding("BOEM! Een creeper is ontploft! 💥")
        self.ga_dood()


def knal_effect(midden):
    """Een oranje bol die groeit en verdwijnt, plus rondvliegende steenbrokjes."""
    bol = Entity(model='sphere', color=color.rgb(1.0, 0.6, 0.1), position=midden,
                 scale=0.5, alpha=0.8)
    bol.animate_scale(6, duration=0.35)
    bol.animate('alpha', 0, duration=0.35)
    destroy(bol, delay=0.4)
    for _ in range(12):
        brok = Entity(model='cube', color=color.rgb(0.4, 0.4, 0.4), scale=0.2,
                      position=midden)
        brok.animate_position(midden + Vec3(random.uniform(-3, 3),
                                            random.uniform(0, 3),
                                            random.uniform(-3, 3)), duration=0.5)
        brok.animate_scale(0, duration=0.5)
        destroy(brok, delay=0.55)
    geluid_afbreken.play()


def blaas_blokken_weg(midden, straal):
    """Haalt alle blokken binnen een bol weg (het gat van een creeper).
    Je krijgt deze blokken NIET in je rugzak: ze zijn kapot!"""
    mx, my, mz = round(midden.x), round(midden.y), round(midden.z)
    weg_gehaald = []
    redstone_veranderd = False
    for dx in range(-straal, straal + 1):
        for dy in range(-straal, straal + 1):
            for dz in range(-straal, straal + 1):
                # Alleen binnen de BOL (anders wordt het een vierkant gat)
                if dx * dx + dy * dy + dz * dz > straal * straal:
                    continue
                pos = (mx + dx, my + dy, mz + dz)
                t = wereld.get(pos)
                if t is None or t in ('water', 'lava'):
                    continue                     # water en lava laten we staan
                # Het blok echt weghalen (net als in voltooi_breken, maar
                # zonder dat je het in je rugzak krijgt).
                wereld.pop(pos)
                cx, cz = chunk_van_pos(pos[0], pos[2])
                chunk_blokken.get((cx, cz), {}).pop(pos, None)
                markeer_weg(pos)                 # onthouden, ook voor het opslaan
                if t in DRAAD_TYPES or t in LAMP_TYPES or t == 'redstone_blok':
                    registreer_redstone_blok(pos, t, False)
                    redstone_veranderd = True
                # Lag hier een sneeuwlaagje? Dat waait ook weg.
                laag = sneeuw_lagen.pop((pos[0], pos[2]), None)
                if laag:
                    destroy(laag)
                weg_gehaald.append(pos)
    if not weg_gehaald:
        return
    # Onder het gat de wereld weer aanvullen, zodat je geen leegte ziet.
    for pos in weg_gehaald:
        onthul_buren(pos)
    # Alle stukjes wereld die geraakt zijn ÉÉN keer opnieuw bouwen.
    # (Per blok herbouwen zou veel te traag zijn!)
    chunks = set()
    for pos in weg_gehaald:
        for dx, dz in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            chunks.add(chunk_van_pos(pos[0] + dx, pos[2] + dz))
    for chunk in chunks:
        if chunk in chunk_modellen:
            bouw_chunk_model(*chunk)
    if redstone_veranderd:
        werk_redstone_bij()


def linker_klik():
    """Linkermuis indrukken: RUIL met een villager, sla een dier/monster, of
    sloop meteen een zelfgemaakt ding. Gewone blokken hak je door de muis
    INGEDRUKT te houden (dat regelt werk_hakken_bij elke frame)."""
    doel = mouse.hovered_entity
    # Klik je op een villager? Dan ga je RUILEN in plaats van slaan.
    if isinstance(doel, Villager):
        if (doel.world_position - speler.world_position).length() < 5:
            toon_ruil_scherm(doel)
        else:
            toon_melding("Loop even wat dichter naar de villager toe om te ruilen.")
        return
    # Een ijzergolem sla je natuurlijk niet: die is aan JOUW kant!
    if isinstance(doel, IJzerGolem):
        toon_melding("De ijzergolem is je vriend. Hij past op je! 🤖")
        return
    if isinstance(doel, Levend):
        if (doel.world_position - speler.world_position).length() < 5:
            doel.raak(1)
        return
    sloop_speciaal()


# ======================================================================
#  HAKKEN (zoals Minecraft: muis ingedrukt houden, barsten, en het duurt even)
# ======================================================================
STANDAARD_HAK_TIJD = 0.75    # standaard duurt hakken zo lang (seconden)
HAK_TIJDEN = {               # sommige blokken zijn zachter of harder
    'blad': 0.2, 'paddenstoel': 0.2, 'sneeuw': 0.25, 'glas': 0.35,
    'mc_berk_blad': 0.2, 'mc_den_blad': 0.2, 'mc_kers_blad': 0.2,
    'mc_jungle_blad': 0.2, 'mc_acacia_blad': 0.2, 'mc_donkereik_blad': 0.2,
    'mc_mangrove_blad': 0.2,
    'zand': 0.4, 'gras': 0.5, 'aarde': 0.5, 'klei': 0.5, 'mos': 0.5,
    'pompoen': 0.7, 'planken': 0.8, 'hout': 0.9,
    'mc_berk_stam': 0.9, 'mc_den_stam': 0.9, 'mc_kers_stam': 0.9,
    'mc_jungle_stam': 0.9, 'mc_acacia_stam': 0.9, 'mc_donkereik_stam': 0.9,
    'mc_mangrove_stam': 0.9,
    'zandsteen': 1.0, 'steen': 1.2, 'baksteen': 1.3, 'lava': 1.5,
    'kool': 1.6, 'ijzer': 2.2, 'goud': 2.4, 'diamant': 2.8, 'smaragd': 2.8,
}
BARST_AANTAL = 5             # zoveel barst-plaatjes hebben we (barst_0 t/m barst_4)


def bereken_hak_duur(bloktype):
    """Hoe lang duurt het om dit bloktype te hakken? Met een pikhouweel sneller."""
    if CREATIEF:
        return 0.05          # in creatief breekt alles bijna meteen
    duur = HAK_TIJDEN.get(bloktype, STANDAARD_HAK_TIJD)
    if pikhouweel_niveau > 0:
        duur *= 0.6          # met pikhouweel gaat hakken lekker vlot
    return duur


# De barst-plaatjes vooraf laden (scherpe pixels). barst_0 = klein beetje barst,
# barst_4 = bijna kapot.
BARST_TEXTUREN = [blok_texture(f'barst_{i}') for i in range(BARST_AANTAL)]

# Het doorzichtige kubusje met barsten dat we OVER het blok leggen dat je hakt.
# Iets groter (1.03) zodat het net vóór het blok zweeft (geen flikker).
barst_overlay = Entity(model='cube', scale=1.03, enabled=False, color=color.white)
barst_overlay.texture = BARST_TEXTUREN[0]

hak_pos       = None     # welk blok hak je nu? (None = niks)
hak_verstreken = 0.0     # hoe lang hak je er al op?
hak_doel_duur  = 0.0     # hoe lang moet het totaal duren? (None = te hard)
hak_fase       = -1      # welk barst-plaatje ligt er nu (om niet elke frame te wisselen)


def stop_hakken():
    """Stop met hakken en haal de barsten weg."""
    global hak_pos, hak_verstreken, hak_doel_duur, hak_fase
    hak_pos = None
    hak_verstreken = 0.0
    hak_doel_duur = 0.0
    hak_fase = -1
    barst_overlay.enabled = False


def werk_hakken_bij():
    """Elke frame: houd je de linkermuis ingedrukt op een blok? Dan hak je eraan.
    Er groeien barsten, en na genoeg tijd breekt het blok."""
    global hak_pos, hak_verstreken, hak_doel_duur, hak_fase

    # Alleen hakken als de linkermuis ingedrukt is en het menu dicht is
    bezig = held_keys['left mouse'] and not maaktafel.enabled and not ruil_scherm.enabled
    doel = doel_hak_blok() if bezig else None

    if doel is None:                     # niks (meer) om te hakken
        if hak_pos is not None:
            stop_hakken()
        return

    if doel != hak_pos:                  # een NIEUW blok: opnieuw beginnen
        hak_pos = doel
        hak_verstreken = 0.0
        hak_fase = -1
        nodig = ERTS_NIVEAU.get(wereld.get(doel), 0)
        if nodig > pikhouweel_niveau and not CREATIEF:   # te hard voor je pikhouweel
            toon_melding(f"Te hard! Hiervoor heb je een {PIKHOUWEEL_NAAM[nodig]} nodig.")
            hak_doel_duur = None
        else:
            hak_doel_duur = bereken_hak_duur(wereld[doel])

    if hak_doel_duur is None:            # te hard: geen barsten, niets breken
        barst_overlay.enabled = False
        return

    # Doorhakken: tijd optellen en de barsten laten groeien
    hak_verstreken += time.dt
    fase = int(hak_verstreken / hak_doel_duur * BARST_AANTAL)
    fase = max(0, min(BARST_AANTAL - 1, fase))
    barst_overlay.enabled = True
    barst_overlay.position = hak_pos
    if fase != hak_fase:                 # alleen wisselen als de fase verandert
        hak_fase = fase
        barst_overlay.texture = BARST_TEXTUREN[fase]

    if hak_verstreken >= hak_doel_duur:  # klaar: het blok breekt!
        voltooi_breken(hak_pos)
        stop_hakken()


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
speler = FirstPersonController(height=1.5)   # ooghoogte: anderhalf blok
speler.jump_height = 1.1                      # net genoeg om op 1 blok hoog te springen
speler.position = (SPAWN_X, spawn_grond + 2, SPAWN_Z)

# Vliegen (alleen in creatief). We onthouden de gewone zwaartekracht.
STANDAARD_GRAVITY = speler.gravity
STANDAARD_SPEED   = speler.speed      # hoe snel je normaal loopt
vliegt = False


def zet_vliegen(aan):
    """Zet vliegen aan of uit (alleen in de creatieve modus)."""
    global vliegt
    vliegt = aan
    speler.gravity = 0 if aan else STANDAARD_GRAVITY
    toon_melding("Vliegen AAN (spatie = omhoog, shift = omlaag)" if aan
                 else "Vliegen uit")

# --- Dieren (vreedzaam: varkens, koeien, schapen, kippen en konijnen) ---
dieren = []
DIER_SOORTEN = [Varken, Koe, Schaap, Kip, Konijn]
for _ in range(12):
    dx = SPAWN_X + random.randint(-18, 18)
    dz = SPAWN_Z + random.randint(-18, 18)
    soort = random.choice(DIER_SOORTEN)        # kies willekeurig een diersoort
    dieren.append(soort((dx, hoogte_op(dx, dz) + 1.2, dz)))


# --- Villagers: de mensjes die in het dorp wonen ---
# Bij elk huisje hoort één villager met zijn eigen beroep. Ze staan bij hun
# voordeur te wachten tot jij komt ruilen.
villagers   = []
golems      = []              # de ijzergolems die de dorpjes bewaken
huidig_dorp = None            # in welk dorpje sta je nu? (voor het 'welkom'-berichtje)
BEROEPEN    = ['Boer', 'Houthakker', 'Mijnwerker', 'Smid']
for _dorp in DORPEN:
    for _i, _huis in enumerate(_dorp['huizen']):
        _beroep = BEROEPEN[_i % len(BEROEPEN)]
        _hx, _hy, _hz = _huis
        # Hij begint net buiten zijn huisje, op het plein.
        _sx = _hx + random.uniform(-1, 1)
        _sz = _hz + (HUIS_HALF + 2) * (1 if _hz < _dorp['midden'][2] else -1)
        villagers.append(Villager((_sx, grond_onder(_sx, _sz) + 1.15, _sz),
                                  _beroep, (_hx, _hy, _hz)))
    # In elk dorpje staat één ijzergolem op wacht, vlak bij de put.
    _gx, _gy, _gz = _dorp['midden']
    golems.append(IJzerGolem((_gx + 3, grond_onder(_gx + 3, _gz) + GOLEM_HOOGTE, _gz + 3),
                             (_gx, _gy, _gz)))

# De voordeuren van de huisjes neerzetten (deuren die echt open kunnen!).
# Alleen bij een NIEUWE wereld: in een opgeslagen wereld komen de deuren uit
# het opslagbestand, want misschien heb je er zelf een weggehaald.
if not OPGESLAGEN:
    for _pos, _richting in DORP_DEUREN:
        plaats_speciaal('deur', _pos, _richting)


# Waarmee kun je dieren voeren? (bladeren, paddenstoelen, groente)
VOER = {'blad', 'mc_berk_blad', 'mc_den_blad', 'mc_kers_blad', 'mc_jungle_blad',
        'mc_acacia_blad', 'mc_donkereik_blad', 'mc_mangrove_blad',
        'paddenstoel', 'pompoen', 'mc_meloen', 'mc_hooibaal'}

# Alle soorten bladeren (daar vind je soms een appel in).
BLAD_TYPES = {'blad', 'mc_berk_blad', 'mc_den_blad', 'mc_kers_blad', 'mc_jungle_blad',
              'mc_acacia_blad', 'mc_donkereik_blad', 'mc_mangrove_blad'}

# De appel: die kun je opeten om je honger te stillen (niet plaatsen).
ITEM_NAMEN['appel'] = 'Appel'
KLEUREN['appel']    = color.rgb(0.85, 0.2, 0.2)

# De sneeuwbal: die kun je gooien (krijg je door sneeuw te slopen).
ITEM_NAMEN['sneeuwbal'] = 'Sneeuwbal'
KLEUREN['sneeuwbal']    = color.rgb(0.95, 0.97, 1.0)


def toon_hartjes(pos):
    """Laat een paar zwevende hartjes boven een dier zien (het is blij!)."""
    for _ in range(4):
        h = Entity(model='cube', color=color.rgb(1, 0.3, 0.45), scale=0.16,
                   position=pos + Vec3(random.uniform(-0.3, 0.3), 1,
                                       random.uniform(-0.3, 0.3)))
        h.animate_position(h.position + Vec3(0, 0.9, 0), duration=0.8)
        destroy(h, delay=0.9)


def voer_dier(dier):
    """Voer een dier: er komt een baby-dier bij en het dier is blij (hartjes)."""
    if not CREATIEF:
        rugzak[vastgehouden] -= 1
        werk_hud_bij()
    baby = type(dier)((dier.x, dier.y, dier.z + 0.6))   # zelfde soort dier
    baby.word_baby()
    dieren.append(baby)
    toon_hartjes(dier.world_position)
    geluid_plaatsen.play()

# --- Monsters (gevaarlijk: ze komen alleen 's NACHTS en vallen aan) ---
# We beginnen overdag, dus de lijst is nog leeg. 's Nachts komen ze vanzelf.
monsters = []
MAX_MONSTERS = 6          # zoveel monsters mogen er 's nachts tegelijk zijn

# --- Dag en nacht + verlichting ---
lucht = Sky(color=color.rgb(0.5, 0.7, 1.0))

# De verlichting van de blokken zit al ingebakken (zie blok_shader / LICHT_KUBUS).
# Overdag staat de 'daglicht'-knop op 1, 's nachts dimmen we die naar MAANLICHT.
MAANLICHT = 0.14          # hoeveel licht er 's nachts nog is (maanlicht, niet pikzwart)

dag_tijd   = 0.0
DAG_LENGTE = 600.0        # een hele dag+nacht duurt 10 minuten: 5 min dag + 5 min nacht
het_is_nacht = False      # is het nu nacht? (dan komen de monsters!)

# --- Weer: af en toe regen of sneeuw die rond de speler valt ---
WEER_DEELTJES = 90
weer_deeltjes = []
for _i in range(WEER_DEELTJES):
    weer_deeltjes.append(Entity(model='cube', scale=0.06, color=color.white,
                                enabled=False))
weer       = 'helder'                       # 'helder', 'regen' of 'sneeuw'
weer_timer = random.uniform(25, 45)         # hoe lang duurt dit weer nog?
sneeuw_leg_timer = 0.0                       # om af en toe sneeuw op de grond te leggen

# Sneeuw op de grond = losse dunne witte laagjes (aparte entities, geen chunk-herbouw).
sneeuw_lagen    = {}                          # (x, z) -> het witte laagje-entity
sneeuw_volgorde = collections.deque()        # om de oudste weg te halen als het te veel wordt
MAX_SNEEUW_LAGEN = 260
smelt_timer     = 0.0                         # om sneeuw langzaam te laten smelten
sneeuwballen_vliegend = []                    # sneeuwballen die nu door de lucht vliegen
pijlen_vliegend       = []                    # pijlen van skeletten die nu vliegen


def _nieuwe_deeltjes_plek(d, hoog=False):
    """Zet een regen/sneeuw-deeltje op een willekeurige plek rond de speler."""
    d.position = (speler.x + random.uniform(-13, 13),
                  speler.y + (random.uniform(4, 11) if hoog else random.uniform(2, 11)),
                  speler.z + random.uniform(-13, 13))


def zet_weer(nieuw):
    """Verander het weer (helder, regen of sneeuw) en stel de deeltjes in."""
    global weer
    weer = nieuw
    if weer == 'helder':
        for d in weer_deeltjes:
            d.enabled = False
        return
    for d in weer_deeltjes:
        d.enabled = True
        _nieuwe_deeltjes_plek(d)
        if weer == 'regen':
            d.scale = (0.04, 0.4, 0.04)          # dunne blauwe streepjes
            d.color = color.rgb(0.5, 0.6, 0.95)
        else:                                     # sneeuw
            d.scale = 0.1                         # witte vlokjes
            d.color = color.rgb(0.95, 0.97, 1.0)
    toon_melding("Het begint te regenen! 🌧️" if weer == 'regen'
                 else "Het begint te sneeuwen! ❄️")


def leg_sneeuw_neer():
    """Legt tijdens sneeuw dunne witte laagjes op de grond rond de speler.
    Dit zijn losse entities (geen chunk-herbouw), dus het blijft snel."""
    for _ in range(4):
        x = round(speler.x) + random.randint(-13, 13)
        z = round(speler.z) + random.randint(-13, 13)
        if (x, z) in sneeuw_lagen:
            continue                      # hier ligt al sneeuw
        g = hoogte_op(x, z)
        grond = (x, g, z)
        boven = (x, g + 1, z)
        if grond not in wereld or boven in wereld:
            continue                      # geen open grond om op te liggen
        t = wereld[grond]
        if t in ('water', 'sneeuw', 'lava') or t in BLAD_TYPES:
            continue                      # niet op water, sneeuw, lava of bladeren
        # Een dun wit laagje bovenop het grondblok.
        laag = Entity(model='cube', color=color.rgb(0.95, 0.97, 1.0),
                      position=(x, g + 0.55, z), scale=(1, 0.12, 1))
        sneeuw_lagen[(x, z)] = laag
        sneeuw_volgorde.append((x, z))
        # Te veel sneeuw? Haal de oudste laagjes weg (blijft licht voor de computer).
        while len(sneeuw_volgorde) > MAX_SNEEUW_LAGEN:
            oud = sneeuw_volgorde.popleft()
            weg = sneeuw_lagen.pop(oud, None)
            if weg:
                destroy(weg)


window.fps_counter.enabled = True

# Een regel met alle dorpjes en waar ze staan (2 per regel, anders wordt het te lang)
_dorp_regels = []
for _i in range(0, len(DORPEN), 2):
    _dorp_regels.append("   ".join(
        f"{_d['naam']} (x={_d['midden'][0]}, z={_d['midden'][2]})"
        for _d in DORPEN[_i:_i + 2]))
DORP_UITLEG = "Dorpjes: " + "\n         ".join(_dorp_regels)

# --- Uitleg op het scherm ---
Text(
    text="Linker muis INGEDRUKT houden = hakken (barsten!)   Rechter muis = plaatsen   Muiswiel = ander blok\n"
         "Pas op: 's NACHTS komen er monsters! Skeletten schieten pijlen, creepers ONTPLOFFEN (ren weg!).\n"
         "Er zijn DORPJES met villagers: klik erop met de linkermuis om te RUILEN (smaragd = het geld).\n"
         "C = maak-tafel (maak er eerst een en ga ernaast staan!)   F = deur / hefboom aan-uit\n"
         "G = ijzergolem neerzetten (4 ijzer + 1 pompoen)   N = boot te water / in- en uitstappen\n"
         "WASD = lopen   1-9/muiswiel = kies blok   Pijltjes = blok verschuiven   Dubbel-spatie = vliegen (creatief)\n"
         "O = opslaan   M = werelden (andere/nieuwe wereld)   Escape = opslaan & stoppen\n"
         + DORP_UITLEG + "   (druk F3 om te zien waar jij bent)",
    position=(-0.85, 0.47),
    scale=1.1,
    background=True,
)

# In de creatieve modus een duidelijke melding bovenaan (aan/uit met de modus).
creatief_banner = Text(text="CREATIEF   (V = vliegen  •  C = blokken gratis pakken)",
                       position=(0, 0.38), origin=(0, 0), scale=1.1, color=color.cyan,
                       background=True, enabled=CREATIEF)

# --- Rugzak-overzicht LINKSONDER: wat heb je, en wat houd je vast? ---
# Een pijltje '>' staat bij het blok/ding dat je nu vasthoudt om te plaatsen.
rugzak_hud = Text(text="", position=(-0.87, -0.02), origin=(-0.5, 0.5),
                  scale=0.9, background=True)

# Een pikhouweel-melding rechtsonder (gaat aan zodra je er een hebt gemaakt)
pikhouweel_hud = Text(text="", position=(0.40, -0.42), scale=1.0,
                      background=True, enabled=False)


def werk_pikhouweel_hud():
    """Laat rechtsonder zien welke pikhouweel je nu hebt."""
    if pikhouweel_niveau == 0:
        pikhouweel_hud.enabled = False
    else:
        pikhouweel_hud.enabled = True
        naam = PIKHOUWEEL_NAAM[pikhouweel_niveau].capitalize()
        pikhouweel_hud.text = f"{naam} (2x blokken!)"

# Een melding in het midden (bv. "Te weinig materiaal!"). Verdwijnt vanzelf.
melding = Text(text="", position=(0, -0.28), origin=(0, 0), scale=1.3,
               background=True, enabled=False)


def verberg_melding():
    melding.enabled = False


def toon_melding(tekst):
    """Laat 1,5 seconde een melding in beeld zien."""
    melding.text = tekst
    melding.enabled = True
    invoke(verberg_melding, delay=1.5)


def is_item(naam):
    """Is dit een zelfgemaakt ding met een eigen vorm (deur, slab...)?
    Gekleurde blokken tellen NIET mee: dat zijn gewone blokken."""
    return naam in RECEPTEN and not RECEPTEN[naam].get('is_blok')


def beschikbaar():
    """Alle dingen die je in je rugzak hebt om te plaatsen, in JOUW hotbar-volgorde.
    Een blok dat je NIEUW oppakt komt vanzelf achteraan (op het eerste vrije plekje)."""
    # Alle plaatsbare dingen (gewone/natuur-blokken + maakbare deuren/slabs/...).
    basis = list(BLOK_KEUZES) + [n for n in RECEPTEN if RECEPTEN[n]['plaatsbaar']]
    # Zet blokken die je NU hebt maar nog niet in je volgorde staan er achteraan bij.
    for n in basis:
        if rugzak.get(n, 0) > 0 and n not in hotbar_volgorde:
            hotbar_volgorde.append(n)
    return [n for n in hotbar_volgorde if rugzak.get(n, 0) > 0]


def verplaats_in_hotbar(richting):
    """Schuift het blok dat je vasthoudt een plekje op in de hotbar
    (richting -1 = naar links, +1 = naar rechts)."""
    spullen = beschikbaar()
    if vastgehouden not in spullen:
        return
    i = spullen.index(vastgehouden)
    j = i + richting
    if 0 <= j < len(spullen):
        # Verwissel deze twee blokken van plek in je eigen volgorde.
        a, b = spullen[i], spullen[j]
        ia, ib = hotbar_volgorde.index(a), hotbar_volgorde.index(b)
        hotbar_volgorde[ia], hotbar_volgorde[ib] = hotbar_volgorde[ib], hotbar_volgorde[ia]
        werk_hud_bij()


def werk_hud_bij():
    """Laat linksonder je rugzak zien, met een pijltje bij wat je vasthoudt."""
    global vastgehouden
    spullen = beschikbaar()
    # Zorg dat je altijd iets geldigs vasthoudt (bv. nadat een blok op is)
    if vastgehouden not in spullen:
        vastgehouden = spullen[0] if spullen else None
    regels = ["RUGZAK:"]
    for n in spullen:
        naam = ITEM_NAMEN.get(n, n)
        pijl = ">" if n == vastgehouden else "  "
        aantal = "oneindig" if CREATIEF else rugzak[n]
        regels.append(f"{pijl} {naam}: {aantal}")
    if len(regels) == 1:
        regels.append("  (leeg - ga blokken slopen!)")
    rugzak_hud.text = "\n".join(regels)
    werk_hotbar_bij()          # ook de balk onderin bijwerken


# --- HOTBAR: een rij vakjes onderin, zoals in Minecraft ---
HOTBAR_SLOTS  = 9
_HB_Y         = -0.44          # hoogte van de balk (onderin)
_HB_STAP      = 0.095         # ruimte tussen de vakjes
hotbar_start  = 0             # welk item staat links in de balk (voor scrollen)
hotbar_bg     = []            # de donkere vakjes
hotbar_icon   = []            # het plaatje van het blok
hotbar_getal  = []            # hoeveel je ervan hebt
for _i in range(HOTBAR_SLOTS):
    _x = (_i - (HOTBAR_SLOTS - 1) / 2) * _HB_STAP
    hotbar_bg.append(Entity(parent=camera.ui, model='quad', z=1,
                            color=color.rgba(0, 0, 0, 0.55), scale=0.085, position=(_x, _HB_Y)))
    hotbar_icon.append(Entity(parent=camera.ui, model='quad', z=0,
                              color=color.white, scale=0.072, position=(_x, _HB_Y)))
    hotbar_getal.append(Text(parent=camera.ui, text="", scale=0.7,
                             position=(_x + 0.035, _HB_Y - 0.028), origin=(0.5, 0)))
    Text(parent=camera.ui, text=str((_i + 1) % 10), scale=0.6, color=color.yellow,
         position=(_x - 0.038, _HB_Y + 0.032))          # het cijfer van de toets
# Wit kadertje rond het gekozen vakje.
hotbar_kader = Entity(parent=camera.ui, model='quad', z=1.5,
                      color=color.white, scale=0.098, position=(0, _HB_Y), enabled=False)


def werk_hotbar_bij():
    """Vult de balk onderin met je blokken en zet het kadertje bij het gekozen blok."""
    global hotbar_start
    spullen = beschikbaar()

    # Zorg dat het vastgehouden blok in de balk zichtbaar blijft (venster van 9).
    if vastgehouden in spullen:
        idx = spullen.index(vastgehouden)
        if idx < hotbar_start:
            hotbar_start = idx
        elif idx >= hotbar_start + HOTBAR_SLOTS:
            hotbar_start = idx - HOTBAR_SLOTS + 1
    hotbar_start = max(0, min(hotbar_start, max(0, len(spullen) - HOTBAR_SLOTS)))
    zicht = spullen[hotbar_start:hotbar_start + HOTBAR_SLOTS]

    for i in range(HOTBAR_SLOTS):
        if i < len(zicht):
            naam = zicht[i]
            tex = BLOK_TEXTUUR.get(naam)
            if tex:                              # blok met een echt plaatje
                hotbar_icon[i].texture = blok_texture(tex)
                hotbar_icon[i].color   = color.white
            else:                                # deur/hek/... : een kleurtje
                hotbar_icon[i].texture = None
                hotbar_icon[i].color   = KLEUREN.get(naam, color.gray)
            hotbar_icon[i].enabled = True
            hotbar_getal[i].text = "" if CREATIEF else str(rugzak.get(naam, 0))
        else:
            hotbar_icon[i].enabled = False
            hotbar_getal[i].text = ""

    # Het witte kadertje op de plek van het gekozen blok.
    if vastgehouden in zicht:
        j = zicht.index(vastgehouden)
        hotbar_kader.enabled = True
        hotbar_kader.x = (j - (HOTBAR_SLOTS - 1) / 2) * _HB_STAP
    else:
        hotbar_kader.enabled = False


def kies_vast(naam):
    """Houd dit blok/ding vast om te plaatsen (met een zacht tikje bij wisselen)."""
    global vastgehouden
    if naam is not None and naam != vastgehouden:
        geluid_wissel.play()
    vastgehouden = naam
    werk_hud_bij()


def blader(stap):
    """Blader met het muiswiel naar het volgende/vorige ding dat je hebt."""
    spullen = beschikbaar()
    if not spullen:
        return
    i = spullen.index(vastgehouden) if vastgehouden in spullen else 0
    kies_vast(spullen[(i + stap) % len(spullen)])


werk_hud_bij()   # laat meteen je begin-rugzak zien


# --- Hartjes: jouw levens, bovenaan in beeld ---
MAX_HP    = 10
speler_hp = MAX_HP
hartjes   = []
for i in range(MAX_HP):
    # Een klein rood vierkantje per hartje, op een rijtje bovenaan
    hart = Entity(parent=camera.ui, model='quad', color=color.red,
                  scale=0.035, position=(-0.2 + i * 0.045, 0.43), rotation_z=45)
    hartjes.append(hart)


def werk_hartjes_bij():
    """Kleurt de hartjes: rood als je het nog hebt, grijs als het op is."""
    for i, hart in enumerate(hartjes):
        hart.color = color.red if i < speler_hp else color.rgb(0.25, 0.25, 0.25)


def doe_schade(n):
    """Haalt n hartjes van je af. Bij 0 hartjes begin je opnieuw."""
    global speler_hp
    if CREATIEF:
        return                # in creatief kun je geen schade krijgen
    speler_hp = max(0, speler_hp - n)
    werk_hartjes_bij()
    if speler_hp <= 0:
        respawn()


def respawn():
    """Zet je weer veilig op de startplek met volle hartjes."""
    global speler_hp, honger
    toon_melding("Au! Je bent verslagen! Je begint opnieuw bovenaan.")
    speler.position = (SPAWN_X, hoogte_op(SPAWN_X, SPAWN_Z) + 2, SPAWN_Z)
    speler_hp = MAX_HP
    honger    = MAX_HONGER
    werk_hartjes_bij()
    werk_honger_bij()


# --- Honger: hoeveel je nog kunt eten. Loopt langzaam leeg; eet appels! ---
MAX_HONGER   = 10
honger       = MAX_HONGER
honger_timer = 0.0
honger_pijn_timer = 0.0
honger_iconen = []
for i in range(MAX_HONGER):
    # Een oranje vierkantje per honger-punt, op een rijtje onder de hartjes.
    ico = Entity(parent=camera.ui, model='quad', color=color.rgb(0.9, 0.55, 0.15),
                 scale=0.03, position=(-0.2 + i * 0.045, 0.385))
    honger_iconen.append(ico)

appel_hud = Text(text="", position=(0.55, 0.40), scale=1.0, background=True)


def werk_honger_bij():
    """Kleurt de honger-blokjes: oranje als je nog vol zit, grijs als je honger krijgt."""
    for i, ico in enumerate(honger_iconen):
        ico.color = color.rgb(0.9, 0.55, 0.15) if i < honger else color.rgb(0.3, 0.25, 0.2)


def werk_appel_hud():
    """Laat rechtsboven zien hoeveel appels, sneeuwballen, golems en boten je
    hebt. Dit zijn dingen die je niet plaatst maar met een TOETS gebruikt."""
    delen = []
    for naam, tekst in (('appel',      "Appels: {} (E = eten)"),
                        ('sneeuwbal',  "Sneeuwballen: {} (B = gooien)"),
                        ('ijzergolem', "Golems: {} (G = neerzetten)"),
                        ('boot',       "Boten: {} (N = te water)")):
        aantal = rugzak.get(naam, 0)
        if aantal > 0:
            delen.append(tekst.format(aantal))
    appel_hud.text = "     ".join(delen)


def _sneeuwbal_poef(pos):
    """Een klein wit poef-effect als een sneeuwbal ergens tegenaan komt."""
    for _ in range(5):
        p = Entity(model='cube', color=color.rgb(0.95, 0.97, 1.0), scale=0.12,
                   position=pos + Vec3(random.uniform(-0.2, 0.2), random.uniform(-0.2, 0.2),
                                       random.uniform(-0.2, 0.2)))
        p.animate_scale(0, duration=0.4)
        destroy(p, delay=0.45)


def gooi_sneeuwbal():
    """Gooi een sneeuwbal in de richting waar je kijkt."""
    if rugzak.get('sneeuwbal', 0) <= 0:
        toon_melding("Je hebt geen sneeuwballen. Sloop sneeuw om ze te maken!")
        return
    rugzak['sneeuwbal'] -= 1
    werk_appel_hud()
    bal = Entity(model='sphere', color=color.rgb(0.97, 0.98, 1.0), scale=0.3,
                 position=camera.world_position + camera.forward * 0.8)
    bal.snelheid = camera.forward * 24 + Vec3(0, 2.5, 0)   # vooruit + beetje omhoog
    bal.leeftijd = 0.0
    sneeuwballen_vliegend.append(bal)
    geluid_plaatsen.play()


def eet_appel():
    """Eet een appel om je honger te stillen."""
    global honger
    if CREATIEF:
        return
    if rugzak.get('appel', 0) <= 0:
        toon_melding("Je hebt geen appels. Sloop bladeren om er te vinden!")
        return
    if honger >= MAX_HONGER:
        toon_melding("Je zit al helemaal vol!")
        return
    rugzak['appel'] -= 1
    honger = min(MAX_HONGER, honger + 4)
    werk_honger_bij()
    werk_appel_hud()
    geluid_plaatsen.play()
    toon_melding("Mmm, lekker! Een appel gegeten.")


def zet_golem_neer():
    """De G-toets: zet een zelfgemaakte ijzergolem voor je neer.
    Hij loopt daarna rond en beschermt jou tegen de monsters."""
    if rugzak.get('ijzergolem', 0) <= 0:
        toon_melding("Je hebt geen ijzergolem. Maak er een van 4 ijzer + 1 pompoen!")
        return
    rugzak['ijzergolem'] -= 1
    werk_appel_hud()
    werk_hud_bij()
    plek = speler.world_position + speler.forward * 2.5
    golem = IJzerGolem((plek.x, grond_onder(plek.x, plek.z) + GOLEM_HOOGTE, plek.z),
                       (plek.x, 0, plek.z))
    golem.eigen = True                 # deze heb JIJ gemaakt (die slaan we op)
    golems.append(golem)
    geluid_plaatsen.play()
    toon_melding("Een ijzergolem! Hij past op jou en op het dorp. 🤖")


# ======================================================================
#  DE BOOT ⛵ — snel over het water varen
# ======================================================================
# Een boot maak je van 5 hout. Met de N-toets zet je hem op het water, stap je
# in en stap je er weer uit. Terwijl je vaart ga je bijna twee keer zo snel!
boten   = []          # alle bootjes die in de wereld liggen
in_boot = None        # in welke boot zit je nu? (None = je loopt gewoon)
BOOT_SNELHEID = 9     # hoe snel je vaart (lopen is 5)


def maak_boot(pos):
    """Bouwt een houten bootje: een bodem, twee zijkanten, twee uiteinden
    en een bankje om op te zitten."""
    hout   = color.rgb(0.55, 0.38, 0.2)
    donker = color.rgb(0.42, 0.28, 0.14)
    boot = Entity(position=pos)
    Entity(parent=boot, model='cube', color=hout, scale=(1.4, 0.2, 2.4))       # bodem
    for zijkant in (-0.7, 0.7):                                                 # zijkanten
        Entity(parent=boot, model='cube', color=donker,
               position=(zijkant, 0.22, 0), scale=(0.16, 0.45, 2.4))
    for uiteinde in (-1.2, 1.2):                                                # voor en achter
        Entity(parent=boot, model='cube', color=donker,
               position=(0, 0.22, uiteinde), scale=(1.4, 0.45, 0.16))
    Entity(parent=boot, model='cube', color=hout,
           position=(0, 0.25, 0), scale=(1.0, 0.12, 0.5))                       # bankje
    boten.append(boot)
    return boot


def is_water(x, z):
    """Staat er hier water? (De grond ligt dan lager dan het waterniveau.)
    We kijken naar het BLOK waar je op staat, dus we ronden eerst af. Anders
    kijk je net tussen twee blokken in en denkt de boot dat hij op het land
    ligt terwijl hij gewoon op het water dobbert."""
    return hoogte_op(round(x), round(z)) < WATER_NIVEAU


def stap_in_boot(boot):
    """Instappen: je zit in de boot en vaart lekker snel."""
    global in_boot
    in_boot = boot
    speler.gravity = 0                     # je zinkt niet, je drijft
    speler.speed   = BOOT_SNELHEID
    speler.position = (boot.x, WATER_NIVEAU + 1.1, boot.z)
    toon_melding("Je vaart! WASD = sturen, N = uitstappen. ⛵")


def stap_uit_boot(tekst="Je stapt uit de boot."):
    """Uitstappen: je loopt weer gewoon (en de boot blijft liggen)."""
    global in_boot
    if in_boot is None:
        return
    in_boot = None
    speler.gravity = 0 if vliegt else STANDAARD_GRAVITY
    speler.speed   = STANDAARD_SPEED
    speler.y = max(speler.y, grond_onder(speler.x, speler.z) + 1.5)
    toon_melding(tekst)


def boot_toets():
    """De N-toets doet drie dingen, net welke past:
    zit je in een boot? -> uitstappen.  Ligt er een boot vlakbij? -> instappen.
    Anders: een boot uit je rugzak op het water zetten."""
    if in_boot is not None:
        stap_uit_boot()
        return
    # Ligt er een boot vlakbij? Dan stap je in. We kijken alleen naar de afstand
    # op de plattegrond, want als je in het water ligt te spartelen zit je lager.
    for boot in boten:
        naar = boot.world_position - speler.world_position
        if Vec3(naar.x, 0, naar.z).length() < 4:
            stap_in_boot(boot)
            return
    if rugzak.get('boot', 0) <= 0:
        toon_melding("Je hebt geen boot. Maak er een van 5 hout bij de maak-tafel!")
        return
    # Een boot moet op het WATER liggen, dus kijken we net voor je neus.
    plek = speler.world_position + speler.forward * 2.5
    if not is_water(plek.x, plek.z):
        toon_melding("Een boot hoort op het WATER. Ga aan de waterkant staan!")
        return
    rugzak['boot'] -= 1
    werk_appel_hud()
    werk_hud_bij()
    maak_boot(Vec3(plek.x, WATER_NIVEAU + 0.6, plek.z))
    geluid_plaatsen.play()
    toon_melding("Boot te water! Druk op N om in te stappen. ⛵")


# --- Maak-tafel (open met 'c', sluit met Escape of de Sluiten-knop) ---
# Hier maak je nieuwe dingen. Omdat er honderden blokken zijn, gebruiken we
# een ZOEKBALK (typ een naam) en PAGINA'S (blader met < Vorige / Volgende >).
maaktafel = Entity(parent=camera.ui, enabled=False)
Entity(parent=maaktafel, model='quad', color=color.rgba(0, 0, 0, 0.88),
       scale=(1.85, 1.0), z=1)
maaktafel_titel = Text(parent=maaktafel, text="", position=(0, 0.45),
                       origin=(0, 0), scale=1.0)

# Staat de geopende maak-tafel in de 'volledige' stand (bij een echte tafel)?
# Met je handen kun je namelijk ALLEEN een maak-tafel maken.
menu_bij_tafel = False

# De zoekbalk: klik erin en typ om blokken te zoeken (bv 'groen' of '42').
Text(parent=maaktafel, text="Zoek:", position=(-0.62, 0.37), origin=(-0.5, 0), scale=1.0)
zoekveld = InputField(parent=maaktafel, position=(-0.30, 0.37), scale=(0.55, 0.05))

# Linksonder: wat je in je rugzak hebt (het materiaal om mee te maken)
materiaal_tekst = Text(parent=maaktafel, text="", position=(-0.90, 0.22),
                       origin=(-0.5, 0.5), scale=0.8)

# 18 knop-'vakjes' (2 kolommen van 9). Ze worden steeds opnieuw gevuld met de
# blokken van de pagina die je nu bekijkt. Zo heb je er maar 18 nodig!
KNOPPEN_PER_PAGINA = 18
recept_slots = []
for i in range(KNOPPEN_PER_PAGINA):
    kol = i // 9
    rij = i % 9
    kx = -0.02 + kol * 0.45
    ky = 0.30 - rij * 0.072
    knop = Button(parent=maaktafel, text="-", scale=(0.42, 0.066),
                  position=(kx, ky), color=color.azure)
    knop.text_entity.scale *= 0.55
    recept_slots.append(knop)

# De pagina-knoppen en de teller onderaan
huidige_pagina = 0       # welke pagina kijk je nu?
gefilterd      = []      # de namen die nu (na zoeken/stand) in het menu passen
vorige_zoek    = ""      # om te merken dat je iets nieuws hebt getypt

pagina_tekst = Text(parent=maaktafel, text="", position=(0, -0.37),
                    origin=(0, 0), scale=0.9)
vorige_knop   = Button(parent=maaktafel, text="< Vorige",   scale=(0.22, 0.06),
                       position=(-0.28, -0.44), color=color.orange)
volgende_knop = Button(parent=maaktafel, text="Volgende >", scale=(0.22, 0.06),
                       position=(0.28, -0.44), color=color.orange)
sluit_knop    = Button(parent=maaktafel, text="Sluiten (Esc)", scale=(0.22, 0.06),
                       position=(0.70, -0.44), color=color.red)


# ALLE houtsoorten (stammen én planken). Als een recept 'hout' vraagt, mag je
# betalen met ELKE houtsoort. Zo kun je een maak-tafel, pikhouweel, deur enz.
# van eik, berk, den, kers, jungle, acacia, donkere eik of mangrove maken.
HOUT_SOORTEN = [
    'hout', 'planken',
    'mc_berk_stam',      'mc_berk_planken',
    'mc_den_stam',       'mc_den_planken',
    'mc_kers_stam',      'mc_kers_planken',
    'mc_jungle_stam',    'mc_jungle_planken',
    'mc_acacia_stam',    'mc_acacia_planken',
    'mc_donkereik_stam', 'mc_donkereik_planken',
    'mc_mangrove_stam',  'mc_mangrove_planken',
]


def totaal_hout():
    """Hoeveel hout heb je in totaal (alle soorten bij elkaar opgeteld)?"""
    return sum(rugzak.get(h, 0) for h in HOUT_SOORTEN)


def betaal_hout(aantal):
    """Haalt 'aantal' hout uit de rugzak, van welke houtsoort dan ook."""
    for h in HOUT_SOORTEN:
        if aantal <= 0:
            break
        pak = min(rugzak.get(h, 0), aantal)
        if pak > 0:
            rugzak[h] -= pak
            aantal   -= pak


def kan_betalen(naam):
    """Heb je genoeg materiaal voor dit recept? ('hout' = elke houtsoort telt mee.)"""
    for m, n in RECEPTEN[naam]['kosten'].items():
        genoeg = totaal_hout() if m == 'hout' else rugzak.get(m, 0)
        if genoeg < n:
            return False
    return True


def alle_plaatsbare():
    """Alle dingen die je kunt plaatsen (blokken + deuren/hekken/...), elk 1x."""
    volgorde = list(BLOK_KEUZES) + [n for n in RECEPTEN if RECEPTEN[n]['plaatsbaar']]
    gezien, uniek = set(), []
    for n in volgorde:
        if n not in gezien:
            gezien.add(n)
            uniek.append(n)
    return uniek


def filter_recepten():
    """Maakt de lijst met blokken die nu in het menu passen én bij de zoekbalk.
    In creatief zie je ALLE blokken (om zomaar te pakken)."""
    global gefilterd
    zoek = zoekveld.text.lower().strip()
    # In creatief: alle plaatsbare blokken. Anders: de recepten van de huidige stand.
    bron = alle_plaatsbare() if CREATIEF else list(RECEPTEN)
    namen = []
    for naam in bron:
        if not CREATIEF and not menu_bij_tafel and not RECEPTEN[naam].get('hand'):
            continue          # zonder tafel zie je alleen hand-dingen
        toon = ITEM_NAMEN.get(naam, naam).lower()
        if zoek and zoek not in toon:
            continue
        namen.append(naam)
    gefilterd = namen


def aantal_paginas():
    """Hoeveel pagina's zijn er nodig voor alle gevonden blokken?"""
    return max(1, (len(gefilterd) + KNOPPEN_PER_PAGINA - 1) // KNOPPEN_PER_PAGINA)


def toon_pagina():
    """Vult de 18 vakjes met de blokken van de huidige pagina."""
    global huidige_pagina
    huidige_pagina = max(0, min(huidige_pagina, aantal_paginas() - 1))
    start = huidige_pagina * KNOPPEN_PER_PAGINA
    deel  = gefilterd[start:start + KNOPPEN_PER_PAGINA]
    for i, knop in enumerate(recept_slots):
        if i < len(deel):
            naam = deel[i]
            if CREATIEF:                 # in creatief: gewoon de naam, gratis pakken
                knop.text  = ITEM_NAMEN.get(naam, naam)
                knop.color = color.lime
            else:
                kosten = "  ".join(
                    f"{n}x {'hout (elke soort)' if m == 'hout' else m}"
                    for m, n in RECEPTEN[naam]['kosten'].items())
                knop.text  = f"{ITEM_NAMEN.get(naam, naam)}\n{kosten}"
                knop.color = color.lime if kan_betalen(naam) else color.gray
            knop.on_click = Func(craft, naam)
            knop.enabled  = True
        else:
            knop.enabled = False        # leeg vakje: verbergen
    pagina_tekst.text = (f"Pagina {huidige_pagina + 1} / {aantal_paginas()}"
                         f"     ({len(gefilterd)} blokken gevonden)")
    # En links je rugzak-materiaal laten zien (hout = alle houtsoorten samen)
    mats = ['hout', 'steen', 'kool', 'ijzer', 'goud', 'smaragd', 'diamant', 'klei']
    materiaal_tekst.text = "Je rugzak:\n" + "\n".join(
        f"{'hout (alle)' if m == 'hout' else m}: "
        f"{totaal_hout() if m == 'hout' else rugzak.get(m, 0)}" for m in mats)


def werk_maaktafel_bij():
    """Filtert opnieuw en laat de juiste pagina zien."""
    filter_recepten()
    toon_pagina()


def volgende_pagina():
    global huidige_pagina
    huidige_pagina += 1
    toon_pagina()


def vorige_pagina():
    global huidige_pagina
    huidige_pagina -= 1
    toon_pagina()


volgende_knop.on_click = volgende_pagina
vorige_knop.on_click   = vorige_pagina


def craft(naam):
    """Maakt een ding als je genoeg materiaal hebt (in creatief: gewoon pakken)."""
    global pikhouweel_niveau
    if CREATIEF:
        # In creatief pak je het blok gratis en houd je het meteen vast.
        rugzak[naam] = 999
        kies_vast(naam)
        werk_maaktafel_bij()
        return
    # Niet bij een tafel? Dan kun je alleen 'hand'-dingen maken.
    if not menu_bij_tafel and not RECEPTEN[naam].get('hand'):
        toon_melding("Hiervoor moet je bij een maak-tafel staan!")
        return
    r = RECEPTEN[naam]
    if not kan_betalen(naam):
        # Niet genoeg materiaal: maar als je er al een hebt, pak je hem vast
        if r['plaatsbaar'] and rugzak.get(naam, 0) > 0:
            kies_vast(naam)
        else:
            toon_melding("Te weinig materiaal!")
        return
    # Materiaal afrekenen ('hout' mag van elke houtsoort betaald worden)
    for m, n in r['kosten'].items():
        if m == 'hout':
            betaal_hout(n)
        else:
            rugzak[m] -= n
    if 'niveau' in r:
        # Een pikhouweel: je pikhouweel-niveau gaat omhoog (sterkste telt).
        pikhouweel_niveau = max(pikhouweel_niveau, r['niveau'])
        werk_pikhouweel_hud()
    else:
        # Een gewoon maakbaar ding gaat in je rugzak.
        rugzak[naam] = rugzak.get(naam, 0) + r['maakt']
        if r['plaatsbaar']:
            kies_vast(naam)         # meteen vastpakken om te plaatsen
    geluid_plaatsen.play()
    werk_maaktafel_bij()
    werk_hud_bij()
    werk_appel_hud()      # ook golems/boten/appels rechtsboven bijwerken


def bij_maaktafel():
    """Staat de speler vlakbij een geplaatste maak-tafel?"""
    for rec in speciaal.values():
        if rec['naam'] == 'maaktafel':
            if (rec['model'].world_position - speler.world_position).length() < 4:
                return True
    return False


def toon_maaktafel():
    """Opent de maak-tafel en maakt de muis vrij om te klikken.
    Bij een echte tafel kun je alles maken; met je handen alleen een tafel."""
    global menu_bij_tafel, huidige_pagina, vorige_zoek
    menu_bij_tafel = bij_maaktafel()
    maaktafel.enabled = True
    mouse.locked  = False
    mouse.visible = True
    zoekveld.text = ""           # zoekbalk leegmaken
    vorige_zoek   = ""
    huidige_pagina = 0           # weer op de eerste pagina beginnen
    if CREATIEF:
        maaktafel_titel.text = "CREATIEF   -   klik op een blok om het te pakken (gratis!)   -   zoek in de balk"
    elif menu_bij_tafel:
        maaktafel_titel.text = "MAAK-TAFEL   -   klik om te maken   -   typ in de zoekbalk om te zoeken"
    else:
        maaktafel_titel.text = ("MET JE HANDEN   -   nu kun je hand-blokken en een maak-tafel maken.\n"
                                "Plaats een maak-tafel en ga ernaast staan voor ALLE blokken!")
    werk_maaktafel_bij()


def verberg_maaktafel():
    """Sluit de maak-tafel en vergrendelt de muis weer."""
    maaktafel.enabled = False
    mouse.locked  = True
    mouse.visible = False


sluit_knop.on_click = verberg_maaktafel


# ======================================================================
#  RUILEN MET EEN VILLAGER 🤝
# ======================================================================
# Klik met de linkermuis op een villager en dit schermpje gaat open.
# Je ziet dan wat hij wil ruilen: geef iets, krijg iets terug.
ruil_scherm = Entity(parent=camera.ui, enabled=False)
Entity(parent=ruil_scherm, model='quad', color=color.rgba(0, 0, 0, 0.9),
       scale=(1.2, 0.9), z=1)
ruil_titel = Text(parent=ruil_scherm, text="", position=(0, 0.36),
                  origin=(0, 0), scale=1.3)
ruil_rugzak_tekst = Text(parent=ruil_scherm, text="", position=(-0.55, 0.22),
                         origin=(-0.5, 0.5), scale=0.8)

MAX_RUILEN = 4                 # zoveel ruiltjes kan een villager hebben
ruil_knoppen = []
for _i in range(MAX_RUILEN):
    _knop = Button(parent=ruil_scherm, text="-", scale=(0.62, 0.09),
                   position=(0.13, 0.20 - _i * 0.11), color=color.azure)
    _knop.text_entity.scale *= 0.7
    ruil_knoppen.append(_knop)

ruil_sluit_knop = Button(parent=ruil_scherm, text="Sluiten (Esc)", scale=(0.25, 0.07),
                         position=(0, -0.35), color=color.red)
ruil_villager = None           # met wie ben je nu aan het ruilen?


def _spullen_tekst(spullen):
    """Maakt van {'hout': 10} de tekst '10x hout (elke soort)'."""
    delen = []
    for naam, aantal in spullen.items():
        toon = ITEM_NAMEN.get(naam, naam)
        if naam == 'hout':
            toon = 'hout (elke soort)'
        delen.append(f"{aantal}x {toon}")
    return " + ".join(delen)


def kan_ruilen(kosten):
    """Heb je genoeg in je rugzak voor dit ruiltje?
    Voor 'hout' telt elke houtsoort mee (net als bij de maak-tafel)."""
    for naam, aantal in kosten.items():
        heb = totaal_hout() if naam == 'hout' else rugzak.get(naam, 0)
        if heb < aantal:
            return False
    return True


def ruil(index):
    """Doe het ruiltje waar je op klikt: betalen en je beloning krijgen."""
    if ruil_villager is None:
        return
    kosten, krijgt = HANDEL[ruil_villager.beroep][index]
    if CREATIEF:
        toon_melding("In de creatieve modus heb je alles al gratis!")
        return
    if not kan_ruilen(kosten):
        toon_melding("Je hebt niet genoeg om dit te ruilen!")
        return
    # Betalen ('hout' mag van elke houtsoort)
    for naam, aantal in kosten.items():
        if naam == 'hout':
            betaal_hout(aantal)
        else:
            rugzak[naam] -= aantal
    # En je beloning erbij
    for naam, aantal in krijgt.items():
        rugzak[naam] = rugzak.get(naam, 0) + aantal
    geluid_plaatsen.play()
    toon_hartjes(ruil_villager.world_position)      # de villager is blij!
    toon_melding("Geruild! Je kreeg " + _spullen_tekst(krijgt))
    werk_ruil_bij()
    werk_hud_bij()
    werk_appel_hud()


def werk_ruil_bij():
    """Vult de knoppen met de ruiltjes van deze villager en kleurt ze:
    groen = dit kun je betalen, grijs = daar heb je nog te weinig voor."""
    if ruil_villager is None:
        return
    ruiltjes = HANDEL[ruil_villager.beroep]
    for i, knop in enumerate(ruil_knoppen):
        if i < len(ruiltjes):
            kosten, krijgt = ruiltjes[i]
            knop.text = (f"GEEF  {_spullen_tekst(kosten)}\n"
                         f"KRIJG  {_spullen_tekst(krijgt)}")
            knop.color    = color.lime if kan_ruilen(kosten) else color.gray
            knop.on_click = Func(ruil, i)
            knop.enabled  = True
        else:
            knop.enabled = False
    # Links laten zien wat je bij je hebt om mee te betalen
    spullen = ['smaragd', 'hout', 'steen', 'kool', 'ijzer', 'goud', 'diamant', 'appel']
    ruil_rugzak_tekst.text = "Je rugzak:\n" + "\n".join(
        f"{'hout (alle)' if s == 'hout' else s}: "
        f"{totaal_hout() if s == 'hout' else rugzak.get(s, 0)}" for s in spullen)


def toon_ruil_scherm(villager):
    """Opent het ruil-schermpje van deze villager."""
    global ruil_villager
    ruil_villager = villager
    ruil_scherm.enabled = True
    mouse.locked  = False
    mouse.visible = True
    ruil_titel.text = f"{villager.beroep.upper()}   -   klik op een ruiltje om te ruilen"
    werk_ruil_bij()


def verberg_ruil_scherm():
    """Sluit het ruil-schermpje en vergrendelt de muis weer."""
    global ruil_villager
    ruil_villager = None
    ruil_scherm.enabled = False
    mouse.locked  = True
    mouse.visible = False


ruil_sluit_knop.on_click = verberg_ruil_scherm


# ======================================================================
#  WERELDEN-MENU: meerdere werelden opslaan en een nieuwe wereld beginnen
# ======================================================================
werelden_menu = Entity(parent=camera.ui, enabled=False)
Entity(parent=werelden_menu, model='quad', color=color.rgba(0, 0, 0, 0.92),
       scale=(1.5, 1.0), z=1)
Text(parent=werelden_menu, text="WERELDEN", position=(0, 0.43), origin=(0, 0), scale=1.6)
werelden_huidig_tekst = Text(parent=werelden_menu, text="", position=(0, 0.35),
                             origin=(0, 0), scale=0.9)
Text(parent=werelden_menu, text="Klik op een wereld om daar verder te spelen:",
     position=(0, 0.27), origin=(0, 0), scale=0.8)

# Tien knop-vakjes voor de opgeslagen werelden (2 kolommen van 5).
WERELD_KNOPPEN = 10
wereld_slots = []
for i in range(WERELD_KNOPPEN):
    _kol = i // 5
    _rij = i % 5
    _knop = Button(parent=werelden_menu, text="-", scale=(0.32, 0.075),
                   position=(-0.30 + _kol * 0.36, 0.10 - _rij * 0.086),
                   color=color.azure)
    _knop.text_entity.scale *= 0.7
    wereld_slots.append(_knop)

Text(parent=werelden_menu, text="Nieuwe wereld - typ een naam:",
     position=(-0.46, -0.30), origin=(-0.5, 0), scale=0.8)
wereld_naamveld = InputField(parent=werelden_menu, position=(0.06, -0.30),
                             scale=(0.42, 0.05))
# Twee knoppen: een gewone (overleven) of een creatieve wereld.
overleven_knop = Button(parent=werelden_menu, text="Nieuw: Overleven",
                        scale=(0.36, 0.07), position=(-0.2, -0.41), color=color.lime)
overleven_knop.text_entity.scale *= 0.7
creatief_knop = Button(parent=werelden_menu, text="Nieuw: Creatief",
                       scale=(0.36, 0.07), position=(0.2, -0.41), color=color.cyan)
creatief_knop.text_entity.scale *= 0.7
# Knop om DEZE wereld tussen creatief en overleven te wisselen.
modus_knop = Button(parent=werelden_menu, text="Wissel modus",
                    scale=(0.55, 0.055), position=(0, 0.21), color=color.orange)
modus_knop.text_entity.scale *= 0.7
werelden_sluit = Button(parent=werelden_menu, text="X", scale=(0.05, 0.05),
                        position=(0.71, 0.45), color=color.red)


def _herstart_naar(naam):
    """Slaat de huidige wereld op, onthoudt de nieuwe wereld en start opnieuw op."""
    sla_op(stil=True)
    try:
        with open(HUIDIGE_WERELD_PAD, 'w', encoding='utf-8') as f:
            f.write(naam)
    except Exception:
        pass
    # Start het spel opnieuw (die leest dan de gekozen wereld) en sluit dit venster.
    subprocess.Popen([sys.executable] + sys.argv)
    application.quit()


def ga_naar_wereld(naam):
    """Ga naar een bestaande wereld (of blijf, als je er al bent)."""
    if naam == HUIDIGE_WERELD:
        verberg_werelden_menu()
        return
    _herstart_naar(naam)


def _werk_modus_knop():
    """Zet de juiste tekst op de wissel-knop (afhankelijk van de huidige modus)."""
    modus_knop.text = ("Zet deze wereld op OVERLEVEN" if CREATIEF
                       else "Zet deze wereld op CREATIEF")


def wissel_modus():
    """Wisselt DEZE wereld tussen creatief en overleven (zonder opnieuw op te starten)."""
    global CREATIEF
    CREATIEF = not CREATIEF
    if not CREATIEF and vliegt:
        zet_vliegen(False)                 # in overleven kun je niet vliegen
    creatief_banner.enabled = CREATIEF
    _werk_modus_knop()
    werk_hud_bij()
    sla_op(stil=True)                      # de nieuwe modus meteen bewaren
    toon_melding("Creatieve modus AAN! (V = vliegen, C = blokken pakken)" if CREATIEF
                 else "Overleven-modus AAN!")


def maak_nieuwe_wereld(creatief=False):
    """Begin een gloednieuwe wereld met de getypte naam (altijd een vrije naam).
    creatief=True maakt er een creatieve wereld van."""
    naam = ''.join(c for c in wereld_naamveld.text if c.isalnum() or c in ' _-').strip()
    if not naam:
        naam = 'wereld'
    basis, n = naam, 1
    while os.path.exists(_wereld_bestand(naam)):   # nooit een bestaande overschrijven
        n += 1
        naam = f"{basis}{n}"
    if creatief:
        # Meteen een leeg wereld-bestand maken met de creatief-vlag erin.
        try:
            with open(_wereld_bestand(naam), 'w', encoding='utf-8') as f:
                json.dump({'zaad': random.randint(1, 9999), 'creatief': True}, f)
        except Exception:
            pass
    _herstart_naar(naam)


def _wereld_is_creatief(naam):
    """Kijkt in het wereld-bestand of het een creatieve wereld is."""
    try:
        with open(_wereld_bestand(naam), encoding='utf-8') as f:
            return bool(json.load(f).get('creatief'))
    except Exception:
        return False


def vul_werelden_lijst():
    """Zet de knoppen goed: één knop per opgeslagen wereld."""
    werelden_huidig_tekst.text = f"Je speelt nu in: {HUIDIGE_WERELD}"
    namen = _bestaande_werelden()
    for i, knop in enumerate(wereld_slots):
        if i < len(namen):
            naam = namen[i]
            merk = "* " if _wereld_is_creatief(naam) else ""   # * = creatief
            knop.text     = ("> " if naam == HUIDIGE_WERELD else "") + merk + naam
            knop.color    = color.gold if naam == HUIDIGE_WERELD else color.azure
            knop.on_click = Func(ga_naar_wereld, naam)
            knop.enabled  = True
        else:
            knop.enabled = False


def toon_werelden_menu():
    """Opent het werelden-menu en maakt de muis vrij."""
    werelden_menu.enabled = True
    mouse.locked  = False
    mouse.visible = True
    wereld_naamveld.text = ""
    _werk_modus_knop()
    vul_werelden_lijst()


def verberg_werelden_menu():
    """Sluit het werelden-menu en vergrendelt de muis weer."""
    werelden_menu.enabled = False
    mouse.locked  = True
    mouse.visible = False


werelden_sluit.on_click = verberg_werelden_menu
overleven_knop.on_click = Func(maak_nieuwe_wereld, False)
creatief_knop.on_click  = Func(maak_nieuwe_wereld, True)
modus_knop.on_click     = wissel_modus


def toggle_deur():
    """Doet de deur open/dicht, of zet een hefboom aan/uit (met de F-toets)."""
    ent = mouse.hovered_entity
    if ent is None or not hasattr(ent, 'record'):
        return
    rec = ent.record
    if rec['naam'] == 'deur':
        rec['open'] = not rec['open']
        doel = rec['richting'] + (90 if rec['open'] else 0)
        rec['model'].animate('rotation_y', doel, duration=0.2)
    elif rec['naam'] == 'hefboom':
        rec['aan'] = not rec['aan']       # schakelaar omzetten
        stick = getattr(rec['model'], 'stick', None)
        if stick is not None:
            stick.animate('rotation_x', -28 if rec['aan'] else 28, duration=0.15)
        werk_redstone_bij()               # stroom aan/uit!


# --- Meet-schermpje (linksonder) ---
debug_tekst = Text(text="", position=(-0.85, -0.30), scale=1.1, background=True)
gemiddelde_fps = 50.0
debug_timer    = 0.0
monster_timer  = 0.0      # om af en toe een nieuw monster te laten verschijnen
autosave_timer = 0.0      # om af en toe automatisch op te slaan


# --- Verder spelen: alle opgeslagen spullen, plek en tijd terugzetten ---
if OPGESLAGEN:
    rugzak.clear()
    rugzak.update(OPGESLAGEN.get('rugzak', {}))
    hotbar_volgorde[:] = OPGESLAGEN.get('hotbar', [])   # jouw eigen hotbar-volgorde
    honger = OPGESLAGEN.get('honger', MAX_HONGER)
    pikhouweel_niveau = OPGESLAGEN.get('pikhouweel', 0)
    dag_tijd = OPGESLAGEN.get('dag_tijd', 0.0)
    _sp = OPGESLAGEN.get('speler')
    if _sp:
        speler.position   = (_sp[0], _sp[1], _sp[2])
        speler.rotation_y = _sp[3]
        camera.rotation_x = _sp[4]
    # De zelfgemaakte dingen (deuren, hekken, slabs...) terugzetten
    for _s in OPGESLAGEN.get('speciaal', []):
        plaats_speciaal(_s['naam'], tuple(_s['pos']), _s['richting'])
        if _s.get('aan'):                    # een hefboom die aan stond
            _rec = speciaal.get(tuple(_s['pos']))
            if _rec:
                _rec['aan'] = True
                _stick = getattr(_rec['model'], 'stick', None)
                if _stick is not None:
                    _stick.rotation_x = -28
    # De bootjes terugzetten waar je ze had laten liggen
    for _b in OPGESLAGEN.get('boten', []):
        maak_boot(Vec3(_b[0], _b[1], _b[2]))
    # En de golems die JIJ zelf had neergezet
    for _g in OPGESLAGEN.get('golems', []):
        _golem = IJzerGolem((_g[0], _g[1], _g[2]), (_g[0], 0, _g[2]))
        _golem.eigen = True
        golems.append(_golem)
    # De stukjes rondom de speler meteen bouwen zodat hij niet in de leegte valt
    _pc = chunk_van_pos(speler.x, speler.z)
    for _dcx in range(-1, 2):
        for _dcz in range(-1, 2):
            bouw_chunk_model(_pc[0] + _dcx, _pc[1] + _dcz)
    werk_hud_bij()
    werk_pikhouweel_hud()
    werk_honger_bij()
    werk_appel_hud()
    werk_redstone_bij()                      # redstone opnieuw uitrekenen na laden


def update():
    """Wordt elke frame aangeroepen: dag/nacht, bouwen en stukjes beheren."""
    global vorige_chunk, gemiddelde_fps, debug_timer, dag_tijd, monster_timer
    global het_is_nacht, vorige_zoek, huidige_pagina, autosave_timer

    # --- Zoekbalk: typ je iets nieuws? Dan meteen opnieuw zoeken (pagina 1) ---
    if maaktafel.enabled and zoekveld.text != vorige_zoek:
        vorige_zoek = zoekveld.text
        huidige_pagina = 0
        werk_maaktafel_bij()

    # --- Af en toe automatisch opslaan (zodat je niks kwijtraakt) ---
    autosave_timer += time.dt
    if autosave_timer > 90:
        autosave_timer = 0.0
        sla_op(stil=True)

    # --- Hakken: linkermuis ingedrukt houden op een blok laat barsten groeien ---
    werk_hakken_bij()

    # --- Redstone opnieuw uitrekenen als er iets veranderd is (bv nieuw stukje) ---
    if redstone_moet_update:
        werk_redstone_bij()

    # --- Dubbel-spatie-timer laten aftellen ---
    global spatie_timer
    if spatie_timer > 0:
        spatie_timer = max(0.0, spatie_timer - time.dt)


    # --- Weer: af en toe regen of sneeuw, en de deeltjes laten vallen ---
    global weer, weer_timer, sneeuw_leg_timer
    weer_timer -= time.dt
    if weer_timer <= 0:
        if weer == 'helder':
            # Koud (hoog) gebied? Dan sneeuw, anders regen.
            koud = hoogte_op(speler.x, speler.z) >= 16
            zet_weer('sneeuw' if koud else 'regen')
            weer_timer = random.uniform(15, 30)
        else:
            zet_weer('helder')
            toon_melding("Het weer klaart op. ☀️")
            weer_timer = random.uniform(30, 60)
    if weer != 'helder':
        val = (16 if weer == 'regen' else 3.5) * time.dt
        for d in weer_deeltjes:
            d.y -= val
            if weer == 'sneeuw':
                d.x += math.sin(d.y * 3) * 0.5 * time.dt   # sneeuw dwarrelt
            # te laag of te ver weg? terug naar bovenaan rond de speler
            if (d.y < speler.y - 9 or abs(d.x - speler.x) > 15
                    or abs(d.z - speler.z) > 15):
                _nieuwe_deeltjes_plek(d, hoog=True)
    # Tijdens sneeuw blijft er sneeuw op de grond liggen (losse laagjes, snel).
    if weer == 'sneeuw':
        sneeuw_leg_timer += time.dt
        if sneeuw_leg_timer > 0.4:
            sneeuw_leg_timer = 0.0
            leg_sneeuw_neer()

    # Is het weer helder? Dan smelt de sneeuw op de grond langzaam weg.
    global smelt_timer
    if weer == 'helder' and sneeuw_lagen:
        smelt_timer += time.dt
        if smelt_timer > 0.25:
            smelt_timer = 0.0
            for _ in range(4):
                if not sneeuw_volgorde:
                    break
                oud = sneeuw_volgorde.popleft()
                _e = sneeuw_lagen.pop(oud, None)
                if _e:
                    destroy(_e)

    # --- Vliegende sneeuwballen laten vliegen (met zwaartekracht) ---
    for bal in list(sneeuwballen_vliegend):
        bal.snelheid += Vec3(0, -12, 0) * time.dt     # zwaartekracht
        bal.position += bal.snelheid * time.dt
        bal.leeftijd += time.dt
        geraakt = False
        # Raakt de sneeuwbal een dier, villager of monster? Geef een tikje.
        for wezen in alle_wezens():
            if (wezen.world_position - bal.world_position).length() < 1.1:
                if isinstance(wezen, Monster):
                    wezen.raak(1)
                geraakt = True
                break
        # Op de grond gevallen of te lang onderweg? Dan poef.
        if geraakt or bal.leeftijd > 3 or bal.y < grond_onder(bal.x, bal.z) + 0.2:
            _sneeuwbal_poef(bal.world_position)
            sneeuwballen_vliegend.remove(bal)
            destroy(bal)

    # --- Pijlen van skeletten laten vliegen (net als de sneeuwballen) ---
    for pijl in list(pijlen_vliegend):
        pijl.snelheid += Vec3(0, -9, 0) * time.dt     # zwaartekracht (pijlen zakken)
        pijl.position += pijl.snelheid * time.dt
        pijl.leeftijd += time.dt
        # Raakt de pijl JOU? Dan gaat er een hartje af.
        raak_speler = (speler.world_position + Vec3(0, 1, 0)
                       - pijl.world_position).length() < 1.1
        if raak_speler:
            doe_schade(1)
            toon_melding("Au! Een pijl van een skelet! 🏹")
        # Geraakt, op de grond gevallen of te lang onderweg? Dan is hij op.
        if (raak_speler or pijl.leeftijd > 5
                or pijl.y < grond_onder(pijl.x, pijl.z) + 0.1):
            pijlen_vliegend.remove(pijl)
            destroy(pijl)

    # --- Honger: loopt langzaam leeg. Is hij op, dan doet het pijn (eet appels!) ---
    global honger, honger_timer, honger_pijn_timer
    if not CREATIEF:
        honger_timer += time.dt
        if honger_timer > 12 and honger > 0:      # elke 12 sec 1 honger eraf
            honger_timer = 0.0
            honger -= 1
            werk_honger_bij()
        if honger <= 0:
            honger_pijn_timer += time.dt
            if honger_pijn_timer > 4:              # honger doet af en toe pijn
                honger_pijn_timer = 0.0
                toon_melding("Je hebt honger! Eet een appel (E).")
                doe_schade(1)

    # --- Varen: de boot blijft netjes onder je op het water ---
    if in_boot is not None:
        in_boot.position   = Vec3(speler.x, WATER_NIVEAU + 0.6, speler.z)
        in_boot.rotation_y = speler.rotation_y        # de boot draait met je mee
        speler.y = WATER_NIVEAU + 1.1                 # je blijft mooi drijven
        if not is_water(speler.x, speler.z):
            stap_uit_boot("De boot loopt vast op het land. Je stapt eruit!")

    # --- Kom je een dorpje binnen? Dan zeggen we welkom ---
    global huidig_dorp
    _dorp, _afst = dichtstbijzijnde_dorp(speler.x, speler.z)
    if _dorp is not None and _afst < DORP_HALF:
        if huidig_dorp is not _dorp:
            huidig_dorp = _dorp
            toon_melding(f"Welkom in {_dorp['naam']}! 🏘️")
    elif _afst > DORP_HALF + 6:
        huidig_dorp = None            # je bent het dorp weer uit gelopen

    # --- Vliegen (creatief): met spatie omhoog en shift omlaag ---
    if vliegt:
        if held_keys['space']:
            speler.y += 7 * time.dt
        if held_keys['left shift'] or held_keys['control']:
            speler.y -= 7 * time.dt

    # --- 's Nachts af en toe een nieuw monster laten verschijnen (niet te dichtbij) ---
    # In creatief komen er GEEN monsters.
    monster_timer += time.dt
    if not CREATIEF and het_is_nacht and monster_timer > 5 and len(monsters) < MAX_MONSTERS:
        monster_timer = 0.0
        hoek = random.uniform(0, 2 * math.pi)
        afst = random.uniform(18, 28)
        mx = speler.x + math.cos(hoek) * afst
        mz = speler.z + math.sin(hoek) * afst
        # Welk monster wordt het? Het gewone monster komt het vaakst,
        # daarna af en toe een skelet of een creeper.
        soort = random.choice([Monster, Monster, Skelet, Creeper])
        monsters.append(soort((mx, hoogte_op(mx, mz) + 1.0, mz)))

    # --- Dag en nacht laten verlopen ---
    dag_tijd += time.dt
    fractie = (dag_tijd % DAG_LENGTE) / DAG_LENGTE
    hoogte = math.sin(fractie * 2 * math.pi)
    helder = max(0.1, (hoogte + 1) / 2)
    lucht.color = color.rgb(0.5 * helder, 0.7 * helder, 1.0 * helder)

    # Ook de blokken mee laten dimmen: overdag vol daglicht, 's nachts alleen
    # een beetje maanlicht (MAANLICHT) zodat het donker is maar niet pikzwart.
    # We draaien aan de 'daglicht'-knop van elk chunk-model (onze eigen shader).
    daglicht = max(MAANLICHT, helder)
    for modellen in chunk_modellen.values():
        for model in modellen:
            model.set_shader_input('daglicht', daglicht)

    # Is het nacht? (de zon staat onder de horizon). Wordt het net dag?
    # Dan verbranden alle monsters in de zon en is het weer veilig!
    was_nacht = het_is_nacht
    het_is_nacht = hoogte < -0.05
    if was_nacht and not het_is_nacht and monsters:
        for m in list(monsters):
            m.ga_dood()
        toon_melding("De zon komt op! De monsters verbranden in het licht.")

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
    if not vliegt and speler.y < grond_hier - 3:
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
            bij_dorp, bij_afst = dichtstbijzijnde_dorp(speler.x, speler.z)
            dorp_regel = ("geen dorpjes" if bij_dorp is None else
                          f"{bij_dorp['naam']} op x={bij_dorp['midden'][0]}, "
                          f"z={bij_dorp['midden'][2]} ({round(bij_afst)} blokken)")
            debug_tekst.text = (
                f"FPS: {round(gemiddelde_fps)}\n"
                f"Stukjes wereld: {len(chunk_modellen)}\n"
                f"Blokken in geheugen: {len(wereld)}\n"
                f"Bouw-wachtrij: {len(bouw_wachtrij)}\n"
                f"Chunk: {speler_chunk}\n"
                f"Jij staat op: x={round(speler.x)}, z={round(speler.z)}\n"
                f"Dichtstbijzijnde dorp: {dorp_regel}"
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
    # Escape: een open menu sluiten, anders opslaan en stoppen.
    if toets == 'escape':
        if maaktafel.enabled:
            verberg_maaktafel()
        elif ruil_scherm.enabled:
            verberg_ruil_scherm()
        elif werelden_menu.enabled:
            verberg_werelden_menu()
        else:
            sla_op(stil=True)   # automatisch opslaan zodat je niks kwijtraakt
            quit()
        return

    # Is er een menu OPEN? Dan doen we verder niets met toetsen, zodat je rustig
    # in een typvakje kunt typen zonder dat er per ongeluk iets anders gebeurt.
    if maaktafel.enabled or werelden_menu.enabled or ruil_scherm.enabled:
        return

    # 'c' opent de maak-tafel
    if toets == 'c':
        toon_maaktafel()
        return

    # 'm' opent het werelden-menu (opslaan / andere of nieuwe wereld)
    if toets == 'm':
        toon_werelden_menu()
        return

    # 'o' slaat de wereld op (met een melding op het scherm)
    if toets == 'o':
        sla_op()
        return

    # 'v' zet vliegen aan/uit (alleen in de creatieve modus)
    if toets == 'v' and CREATIEF:
        zet_vliegen(not vliegt)
        return

    # 'e' eet een appel (om je honger te stillen)
    if toets == 'e':
        eet_appel()
        return

    # 'b' gooit een sneeuwbal
    if toets == 'b':
        gooi_sneeuwbal()
        return

    # 'g' zet een zelfgemaakte ijzergolem neer
    if toets == 'g':
        zet_golem_neer()
        return

    # 'n' = boot: neerzetten, instappen of uitstappen
    if toets == 'n':
        boot_toets()
        return

    # DUBBEL op spatie tikken = vliegen aan/uit (net als Minecraft, creatief).
    if toets == 'space':
        global spatie_timer
        if CREATIEF and spatie_timer > 0:
            zet_vliegen(not vliegt)
            spatie_timer = 0.0
        else:
            spatie_timer = 0.3        # 0,3 sec om nog een keer te tikken

    # Pijltjes links/rechts: het vastgehouden blok in de hotbar verschuiven
    if toets == 'left arrow':  verplaats_in_hotbar(-1)
    if toets == 'right arrow': verplaats_in_hotbar(1)

    # Breken / plaatsen / deur
    if toets == 'left mouse down':  linker_klik()
    if toets == 'right mouse down': plaats_blok()
    if toets == 'f':                toggle_deur()

    # Met het muiswiel door de blokken die je HEBT bladeren
    if toets == 'scroll up':   blader(1)
    if toets == 'scroll down': blader(-1)

    # De cijfertoetsen 1 t/m 9 kiezen het vakje in de hotbar (0 = het 10e).
    if len(toets) == 1 and toets in '1234567890':
        nummer = 9 if toets == '0' else int(toets) - 1   # '1'->0, ..., '0'->9
        spullen = beschikbaar()
        keuze = hotbar_start + nummer                    # het zichtbare vakje in de balk
        if keuze < len(spullen):
            kies_vast(spullen[keuze])

    if toets == 'f3':
        debug_tekst.enabled        = not debug_tekst.enabled
        window.fps_counter.enabled = debug_tekst.enabled


app.run()

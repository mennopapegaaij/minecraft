from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
from ursina.prefabs.input_field import InputField   # het typ-vakje (zoekbalk)
import mc_blokken                                    # gegevens van de Minecraft-blokken
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
    # Natuur-blokken die je in de wereld kunt vinden
    'klei':        color.rgb(160/255, 165/255, 175/255),
    'zandsteen':   color.rgb(220/255, 205/255, 160/255),
    'paddenstoel': color.rgb(200/255,  50/255,  50/255),
    'water':    color.rgba(45/255, 110/255, 200/255, 0.6),
}

# De blokken die je kunt vasthouden en plaatsen (met muiswiel of cijfertoetsen)
BLOK_KEUZES = ['gras', 'aarde', 'steen', 'zand', 'hout', 'planken', 'blad',
               'baksteen', 'glas', 'sneeuw', 'goud', 'diamant', 'ijzer',
               'smaragd', 'robijn', 'kool', 'lava', 'pompoen', 'mos',
               'klei', 'zandsteen', 'paddenstoel']

WATER_NIVEAU = 6          # Tot welke hoogte staat er water in de lage plekken

# --- Rugzak: hoeveel je van elk blok of zelfgemaakt ding hebt ---
# Je begint met NIETS. Ga eerst blokken slopen om spullen te verzamelen!
rugzak = {}

# Het blok of ding dat je nu vasthoudt om te plaatsen (None = niks)
vastgehouden = None

# Hoe sterk is je pikhouweel? 0 = nog geen, 1 = stenen, 2 = ijzeren,
# 3 = gouden, 4 = smaragden, 5 = robijnen. Hoe hoger, hoe meer je kunt hakken.
pikhouweel_niveau = 0

# Welke pikhouweel hoort bij welk niveau (om netjes op het scherm te laten zien).
PIKHOUWEEL_NAAM = {
    1: 'stenen pikhouweel',
    2: 'ijzeren pikhouweel',
    3: 'gouden pikhouweel',
    4: 'smaragden pikhouweel',
    5: 'robijnen pikhouweel',
}

# De harde ertsen, met het MINIMALE pikhouweel-niveau dat je nodig hebt.
# Net als in het echte Minecraft: een sterkere pikhouweel kan meer hakken!
# (Steen en kool staan er NIET bij: die mag je met je hand, anders kun je
#  nooit je eerste pikhouweel maken.)
ERTS_NIVEAU = {
    'ijzer':   1,   # nodig: stenen pikhouweel (of sterker)
    'goud':    2,   # nodig: ijzeren pikhouweel (of sterker)
    'smaragd': 3,   # nodig: gouden pikhouweel (of sterker)
    'robijn':  4,   # nodig: smaragden pikhouweel (of sterker)
    'diamant': 5,   # nodig: robijnen pikhouweel
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


def steen_of_erts(x, y, z):
    """Diep in de steen zit soms een erts in plaats van gewone steen.
    Hoe dieper je graaft, hoe zeldzamer (en mooier) het erts kan zijn!"""
    # Een eigen willekeurig getal per plekje, altijd hetzelfde voor die plek
    rng = random.Random((x * 73856093) ^ (y * 19349663) ^ (z * 83492791) ^ WERELD_ZAAD)
    r = rng.random()
    if y <= -2 and r < 0.012:  return 'diamant'   # heel diep en heel zeldzaam
    if y <=  0 and r < 0.022:  return 'robijn'
    if y <=  2 and r < 0.034:  return 'smaragd'
    if y <=  4 and r < 0.054:  return 'goud'
    if y <= 12 and r < 0.090:  return 'ijzer'
    if            r < 0.140:   return 'kool'       # kool kom je overal tegen
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
                if in_het_midden and rng.random() < 0.05:
                    voeg_boom_toe(blokken, x, grond, z, rng)   # bladeren binnen het stukje
                elif rng.random() < 0.04:
                    blokken[(x, grond + 1, z)] = 'paddenstoel'  # klein paddenstoeltje

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
        # Heeft dit blok een echt plaatje (texture)? Dan dat gebruiken (kleur wit,
        # zodat het plaatje z'n eigen kleuren houdt). Anders het oude gekleurde blok.
        tex = BLOK_TEXTUUR.get(t)
        if tex:
            ouder.texture = blok_texture(tex)
            ouder.color   = color.white
        else:
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
    'stenen_pikhouweel': 'Stenen pikhouweel',
    'ijzeren_pikhouweel': 'IJzeren pikhouweel',
    'gouden_pikhouweel': 'Gouden pikhouweel',
    'smaragden_pikhouweel': 'Smaragden pikhouweel',
    'robijnen_pikhouweel': 'Robijnen pikhouweel',
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
    # De pikhouweel-ketting: elke pikhouweel kan een mooier erts hakken.
    # 'niveau' = hoe sterk hij is (zie ERTS_NIVEAU hierboven).
    'stenen_pikhouweel':    {'kosten': {'steen': 3,   'hout': 2}, 'maakt': 1, 'plaatsbaar': False, 'niveau': 1},
    'ijzeren_pikhouweel':   {'kosten': {'ijzer': 3,   'hout': 2}, 'maakt': 1, 'plaatsbaar': False, 'niveau': 2},
    'gouden_pikhouweel':    {'kosten': {'goud': 3,    'hout': 2}, 'maakt': 1, 'plaatsbaar': False, 'niveau': 3},
    'smaragden_pikhouweel': {'kosten': {'smaragd': 3, 'hout': 2}, 'maakt': 1, 'plaatsbaar': False, 'niveau': 4},
    'robijnen_pikhouweel':  {'kosten': {'robijn': 3,  'hout': 2}, 'maakt': 1, 'plaatsbaar': False, 'niveau': 5},
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


def maak_speciaal_model(naam, pos, richting=0):
    """Bouwt het 3D-model van een zelfgemaakt ding op plek pos.
    Geeft twee dingen terug: het model om weg te gooien bij afbreken, en
    het deel waar je op klikt (bij een deur is dat het paneel)."""
    x, y, z = pos
    hout  = KLEUREN['planken']   # houtkleur voor de houten dingen
    steen = KLEUREN['steen']

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
              'open': False, 'richting': richting}
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


def breek_blok():
    """Breekt het blok af waar je naar kijkt en stopt het in je rugzak."""
    if mouse.world_point is None or mouse.world_normal is None:
        return

    # Klik je op een zelfgemaakt ding (deur, slab, hek...)? Haal dat dan weg
    # en stop het terug in je rugzak.
    geklikt = mouse.hovered_entity
    if geklikt is not None and hasattr(geklikt, 'record'):
        record = geklikt.record
        rugzak[record['naam']] = rugzak.get(record['naam'], 0) + 1
        destroy(record['model'])
        for c in record['cellen']:
            speciaal.pop(c, None)
        geluid_afbreken.play()
        werk_hud_bij()
        return

    # Anders: een gewoon blok afbreken. Het blok zit net BINNEN het oppervlak.
    punt = mouse.world_point - mouse.world_normal * 0.5
    pos  = (round(punt.x), round(punt.y), round(punt.z))
    if pos in wereld:
        # Mooie ertsen zijn keihard: je pikhouweel moet sterk genoeg zijn!
        nodig = ERTS_NIVEAU.get(wereld[pos], 0)
        if nodig > pikhouweel_niveau:
            toon_melding(f"Te hard! Hiervoor heb je een {PIKHOUWEEL_NAAM[nodig]} nodig.")
            return
        t = wereld.pop(pos)
        cx, cz = chunk_van_pos(pos[0], pos[2])
        chunk_blokken.get((cx, cz), {}).pop(pos, None)
        weggehaald.add(pos)        # onthoud dat dit blok weg is (komt niet terug)
        onthul_buren(pos)          # maak de blokken eronder/ernaast aan (geen void)
        # In je rugzak stoppen (water pak je niet op). Met pikhouweel krijg je 2!
        if t != 'water':
            aantal = 2 if pikhouweel_niveau > 0 else 1
            rugzak[t] = rugzak.get(t, 0) + aantal
            werk_hud_bij()
        geluid_afbreken.play()
        herbouw_rond(pos)


def plaats_blok():
    """Plaatst het blok/ding dat je vasthoudt. Dit kost 1 uit je rugzak!"""
    if mouse.world_point is None or mouse.world_normal is None:
        return
    naam = vastgehouden
    if naam is None or rugzak.get(naam, 0) <= 0:
        toon_melding("Je hebt dit niet (meer)! Sloop eerst wat blokken.")
        return

    # De nieuwe plek komt net BUITEN het oppervlak (aan de kant waar je staat)
    punt = mouse.world_point + mouse.world_normal * 0.5
    pos  = (round(punt.x), round(punt.y), round(punt.z))

    # Houd je een zelfgemaakt ding vast (deur, slab, hek...)? Dan dat neerzetten.
    if is_item(naam):
        richting = round(speler.rotation_y / 90) * 90   # naar de kant waar je kijkt
        if plaats_speciaal(naam, pos, richting):
            rugzak[naam] -= 1
            geluid_plaatsen.play()
            werk_hud_bij()
        return

    # Anders: een gewoon blok plaatsen
    if pos in wereld or pos in speciaal:
        return  # Hier staat al iets
    wereld[pos] = naam
    cx, cz = chunk_van_pos(pos[0], pos[2])
    chunk_blokken.setdefault((cx, cz), {})[pos] = naam
    weggehaald.discard(pos)    # hier staat weer een blok, dus niet meer 'weg'
    rugzak[naam] -= 1          # het blok gaat uit je rugzak
    geluid_plaatsen.play()
    werk_hud_bij()
    herbouw_rond(pos)


# --- Geluiden ---
geluid_plaatsen = Audio('plop',  autoplay=False)   # plop bij plaatsen
geluid_afbreken = Audio('boink', autoplay=False)   # boink bij afbreken


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
        """Houd het wezen netjes op de grond."""
        self.y = hoogte_op(self.x, self.z) + hoogte


class Dier(Levend):
    """Een vreedzaam dier dat rustig rondloopt. Je kunt het slaan."""

    def __init__(self, positie):
        super().__init__(positie, levens=2, lijst=dieren)

    def update(self):
        self.loop_timer -= time.dt
        if self.loop_timer <= 0:                     # af en toe een nieuwe kant op
            self.richting   = random.uniform(0, 360)
            self.loop_timer = random.uniform(1, 3)
        self.rotation_y = self.richting
        self.position  += self.forward * time.dt * self.snelheid
        self.op_de_grond(1.2)


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


class Monster(Levend):
    """Een boos monster dat naar je toe loopt en je aanvalt. Sla het terug!"""

    def __init__(self, positie):
        super().__init__(positie, levens=3, lijst=monsters)
        self.snelheid    = 1.9
        self.sla_cooldown = 0
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
            if afstand > 1.3:                                # loop ernaartoe...
                # ...maar NIET door muren! We voelen eerst met een straaltje
                # vooruit. Zit er vlak voor zijn neus een blok? Dan blijft hij staan.
                voor = self.forward
                muur = raycast(self.world_position, voor, distance=0.6,
                               ignore=[self] + monsters + dieren)
                if not muur.hit:
                    self.position += voor * time.dt * self.snelheid
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
                         ignore=[self] + monsters + dieren)
        return not straal.hit                           # niks geraakt = vrij zicht


def linker_klik():
    """Linkermuis: sla een dier/monster waar je naar kijkt, anders sloop een blok."""
    doel = mouse.hovered_entity
    if isinstance(doel, Levend):
        if (doel.world_position - speler.world_position).length() < 5:
            doel.raak(1)
        return
    breek_blok()


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

# --- Dieren (vreedzaam: varkens, koeien en schapen) ---
dieren = []
DIER_SOORTEN = [Varken, Koe, Schaap]
for _ in range(10):
    dx = SPAWN_X + random.randint(-15, 15)
    dz = SPAWN_Z + random.randint(-15, 15)
    soort = random.choice(DIER_SOORTEN)        # kies willekeurig een diersoort
    dieren.append(soort((dx, hoogte_op(dx, dz) + 1.2, dz)))

# --- Monsters (gevaarlijk: ze komen alleen 's NACHTS en vallen aan) ---
# We beginnen overdag, dus de lijst is nog leeg. 's Nachts komen ze vanzelf.
monsters = []
MAX_MONSTERS = 6          # zoveel monsters mogen er 's nachts tegelijk zijn

# --- Dag en nacht ---
lucht = Sky(color=color.rgb(0.5, 0.7, 1.0))
zon   = DirectionalLight()
zon.rotation = (45, -45, 0)
dag_tijd   = 0.0
DAG_LENGTE = 60.0
het_is_nacht = False      # is het nu nacht? (dan komen de monsters!)

window.fps_counter.enabled = True

# --- Uitleg op het scherm ---
Text(
    text="Linker muis = slopen / slaan   Rechter muis = plaatsen   Muiswiel = ander blok\n"
         "Pas op: 's NACHTS komen er monsters! Sla ze met de linkermuis. Hartjes = je levens.\n"
         "C = maak-tafel (maak er eerst een en ga ernaast staan!)   F = deur open/dicht\n"
         "WASD = lopen   Spatie = springen   Escape = stoppen   F3 = meet-schermpje",
    position=(-0.85, 0.47),
    scale=1.1,
    background=True,
)

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
    """Alle dingen die je in je rugzak hebt om te plaatsen, in een nette
    vaste volgorde. (De pikhouweel zit er niet bij, die plaats je niet.)"""
    # Gewone/natuur-blokken (BLOK_KEUZES) + alles wat je kunt maken en plaatsen
    # (gekleurde blokken, deuren, slabs...). Dubbele namen halen we eruit.
    volgorde = list(BLOK_KEUZES) + [n for n in RECEPTEN if RECEPTEN[n]['plaatsbaar']]
    gezien = set()
    uniek = []
    for n in volgorde:
        if n not in gezien:
            gezien.add(n)
            uniek.append(n)
    return [n for n in uniek if rugzak.get(n, 0) > 0]


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
        regels.append(f"{pijl} {naam}: {rugzak[n]}")
    if len(regels) == 1:
        regels.append("  (leeg - ga blokken slopen!)")
    rugzak_hud.text = "\n".join(regels)


def kies_vast(naam):
    """Houd dit blok/ding vast om te plaatsen."""
    global vastgehouden
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
    speler_hp = max(0, speler_hp - n)
    werk_hartjes_bij()
    if speler_hp <= 0:
        respawn()


def respawn():
    """Zet je weer veilig op de startplek met volle hartjes."""
    global speler_hp
    toon_melding("Au! Je bent verslagen! Je begint opnieuw bovenaan.")
    speler.position = (SPAWN_X, hoogte_op(SPAWN_X, SPAWN_Z) + 2, SPAWN_Z)
    speler_hp = MAX_HP
    werk_hartjes_bij()


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


def kan_betalen(naam):
    """Heb je genoeg materiaal voor dit recept?"""
    return all(rugzak.get(m, 0) >= n for m, n in RECEPTEN[naam]['kosten'].items())


def filter_recepten():
    """Maakt de lijst met blokken die nu in het menu passen: ze moeten bij de
    huidige stand horen (hand of tafel) én bij wat je in de zoekbalk typte."""
    global gefilterd
    zoek = zoekveld.text.lower().strip()
    namen = []
    for naam in RECEPTEN:
        # Niet bij een tafel? Dan zie je alleen de dingen die je met de hand mag.
        if not menu_bij_tafel and not RECEPTEN[naam].get('hand'):
            continue
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
            kosten = "  ".join(f"{n}x {m}" for m, n in RECEPTEN[naam]['kosten'].items())
            knop.text     = f"{ITEM_NAMEN.get(naam, naam)}\n{kosten}"
            knop.color    = color.lime if kan_betalen(naam) else color.gray
            knop.on_click = Func(craft, naam)
            knop.enabled  = True
        else:
            knop.enabled = False        # leeg vakje: verbergen
    pagina_tekst.text = (f"Pagina {huidige_pagina + 1} / {aantal_paginas()}"
                         f"     ({len(gefilterd)} blokken gevonden)")
    # En links je rugzak-materiaal laten zien
    mats = ['hout', 'steen', 'kool', 'ijzer', 'goud', 'smaragd', 'robijn', 'diamant']
    materiaal_tekst.text = "Je rugzak:\n" + "\n".join(
        f"{m}: {rugzak.get(m, 0)}" for m in mats)


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
    """Maakt een ding als je genoeg materiaal hebt."""
    global pikhouweel_niveau
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
    # Materiaal afrekenen
    for m, n in r['kosten'].items():
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
    if menu_bij_tafel:
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


def toggle_deur():
    """Doet de deur waar je naar kijkt open of dicht."""
    ent = mouse.hovered_entity
    if ent is not None and hasattr(ent, 'record') and ent.record['naam'] == 'deur':
        rec = ent.record
        rec['open'] = not rec['open']
        doel = rec['richting'] + (90 if rec['open'] else 0)
        rec['model'].animate('rotation_y', doel, duration=0.2)


# --- Meet-schermpje (linksonder) ---
debug_tekst = Text(text="", position=(-0.85, -0.30), scale=1.1, background=True)
gemiddelde_fps = 50.0
debug_timer    = 0.0
monster_timer  = 0.0      # om af en toe een nieuw monster te laten verschijnen


def update():
    """Wordt elke frame aangeroepen: dag/nacht, bouwen en stukjes beheren."""
    global vorige_chunk, gemiddelde_fps, debug_timer, dag_tijd, monster_timer
    global het_is_nacht, vorige_zoek, huidige_pagina

    # --- Zoekbalk: typ je iets nieuws? Dan meteen opnieuw zoeken (pagina 1) ---
    if maaktafel.enabled and zoekveld.text != vorige_zoek:
        vorige_zoek = zoekveld.text
        huidige_pagina = 0
        werk_maaktafel_bij()

    # --- 's Nachts af en toe een nieuw monster laten verschijnen (niet te dichtbij) ---
    monster_timer += time.dt
    if het_is_nacht and monster_timer > 5 and len(monsters) < MAX_MONSTERS:
        monster_timer = 0.0
        hoek = random.uniform(0, 2 * math.pi)
        afst = random.uniform(18, 28)
        mx = speler.x + math.cos(hoek) * afst
        mz = speler.z + math.sin(hoek) * afst
        monsters.append(Monster((mx, hoogte_op(mx, mz) + 1.0, mz)))

    # --- Dag en nacht laten verlopen ---
    dag_tijd += time.dt
    fractie = (dag_tijd % DAG_LENGTE) / DAG_LENGTE
    zon.rotation = (fractie * 360, -45, 0)
    hoogte = math.sin(fractie * 2 * math.pi)
    helder = max(0.1, (hoogte + 1) / 2)
    lucht.color = color.rgb(0.5 * helder, 0.7 * helder, 1.0 * helder)

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
    # Escape: het menu sluiten als het open is, anders het spel stoppen.
    if toets == 'escape':
        if maaktafel.enabled:
            verberg_maaktafel()
        else:
            quit()
        return

    # Als de maak-tafel OPEN is, doen we verder niets met toetsen. Zo kun je
    # rustig in de zoekbalk typen (ook letters als 'c' en cijfers) zonder dat
    # er per ongeluk iets anders gebeurt.
    if maaktafel.enabled:
        return

    # 'c' opent de maak-tafel
    if toets == 'c':
        toon_maaktafel()
        return

    # Breken / plaatsen / deur
    if toets == 'left mouse down':  linker_klik()
    if toets == 'right mouse down': plaats_blok()
    if toets == 'f':                toggle_deur()

    # Met het muiswiel door de blokken die je HEBT bladeren
    if toets == 'scroll up':   blader(1)
    if toets == 'scroll down': blader(-1)

    # De cijfertoetsen 1 t/m 9 en 0 kiezen snel uit wat je in je rugzak hebt
    if len(toets) == 1 and toets in '1234567890':
        nummer = 9 if toets == '0' else int(toets) - 1   # '1'->0, ..., '0'->9
        spullen = beschikbaar()
        if nummer < len(spullen):
            kies_vast(spullen[nummer])

    if toets == 'f3':
        debug_tekst.enabled        = not debug_tekst.enabled
        window.fps_counter.enabled = debug_tekst.enabled


app.run()

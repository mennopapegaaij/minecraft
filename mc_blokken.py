"""
Hier staan de gegevens van alle Minecraft-achtige blokken op één plek.
Twee bestanden gebruiken dit:
 - maak_textures.py  -> maakt de pixel-plaatjes (textures)
 - main.py           -> zet de blokken in het spel

BELANGRIJK: dit zijn ONZE EIGEN plaatjes die LIJKEN op Minecraft-blokken.
De echte Minecraft-plaatjes zijn van Mojang en mogen we niet kopiëren.

Elke textuur heeft:
 - naam:  de bestandsnaam (zonder .png)
 - stijl: hoe het plaatje eruitziet (speckle = spikkels, brick = baksteen, ...)
 - c1:    de hoofdkleur (rood, groen, blauw van 0 t/m 255)
 - c2:    een tweede kleur (voor spikkels, lijnen, ertskorrels, enz.)
"""

# ---- Alle textuur-plaatjes die we maken ----
TEXTUUR_DEFS = [
    # --- Steen-familie ---
    {'naam': 'mc_steen',           'stijl': 'speckle',  'c1': (128, 128, 128), 'var': 18},
    {'naam': 'mc_cobblestone',     'stijl': 'cobble',   'c1': (120, 120, 120), 'c2': (75, 75, 75)},
    {'naam': 'mc_mossige_cobble',  'stijl': 'cobble',   'c1': (110, 120, 95),  'c2': (65, 80, 55)},
    {'naam': 'mc_grondsteen',      'stijl': 'speckle',  'c1': (70, 70, 75),    'var': 30},
    {'naam': 'mc_grind',           'stijl': 'speckle',  'c1': (120, 110, 105), 'var': 28},
    {'naam': 'mc_zandsteen',       'stijl': 'sandstone','c1': (224, 208, 160), 'c2': (200, 182, 135)},
    {'naam': 'mc_stenen_baksteen', 'stijl': 'brick',    'c1': (122, 122, 122), 'c2': (88, 88, 88)},
    {'naam': 'mc_kwarts',          'stijl': 'solid',    'c1': (235, 232, 225), 'var': 6},
    {'naam': 'mc_obsidiaan',       'stijl': 'speckle',  'c1': (40, 30, 55),    'var': 14},
    {'naam': 'mc_netherrack',      'stijl': 'speckle',  'c1': (110, 45, 45),   'var': 22},
    {'naam': 'mc_netherbaksteen',  'stijl': 'brick',    'c1': (60, 30, 35),    'c2': (35, 18, 20)},
    {'naam': 'mc_glowstone',       'stijl': 'glow',     'c1': (225, 190, 85),  'c2': (255, 245, 170)},
    {'naam': 'mc_ijs',             'stijl': 'ice',      'c1': (160, 200, 235), 'c2': (120, 170, 220)},

    # --- Ertsen (steen met gekleurde korrels) ---
    {'naam': 'mc_kool_erts',       'stijl': 'ore', 'c1': (128, 128, 128), 'c2': (40, 40, 40)},
    {'naam': 'mc_ijzer_erts',      'stijl': 'ore', 'c1': (128, 128, 128), 'c2': (205, 160, 120)},
    {'naam': 'mc_goud_erts',       'stijl': 'ore', 'c1': (128, 128, 128), 'c2': (240, 210, 70)},
    {'naam': 'mc_diamant_erts',    'stijl': 'ore', 'c1': (128, 128, 128), 'c2': (110, 230, 230)},
    {'naam': 'mc_smaragd_erts',    'stijl': 'ore', 'c1': (128, 128, 128), 'c2': (40, 200, 100)},
    {'naam': 'mc_lapis_erts',      'stijl': 'ore', 'c1': (128, 128, 128), 'c2': (40, 70, 200)},
    {'naam': 'mc_redstone_erts',   'stijl': 'ore', 'c1': (128, 128, 128), 'c2': (230, 30, 30)},

    # --- Grond ---
    {'naam': 'mc_aarde',   'stijl': 'speckle', 'c1': (134, 96, 67), 'var': 18},
    {'naam': 'mc_gras',    'stijl': 'gras',    'c1': (95, 155, 65), 'c2': (120, 175, 80)},
    {'naam': 'mc_zand',    'stijl': 'speckle', 'c1': (220, 205, 150), 'var': 12},
    {'naam': 'mc_klei',    'stijl': 'speckle', 'c1': (160, 165, 175), 'var': 10},
    {'naam': 'mc_sneeuw',  'stijl': 'speckle', 'c1': (238, 240, 250), 'var': 6},
    {'naam': 'mc_mos_steen','stijl': 'speckle','c1': (90, 120, 80),  'var': 22},

    # --- Hout ---
    {'naam': 'mc_eik_stam',      'stijl': 'bark',   'c1': (120, 90, 55),  'c2': (90, 65, 40)},
    {'naam': 'mc_eik_planken',   'stijl': 'planks', 'c1': (165, 130, 80), 'c2': (135, 100, 60)},
    {'naam': 'mc_berk_stam',     'stijl': 'bark',   'c1': (220, 215, 205),'c2': (60, 60, 55)},
    {'naam': 'mc_berk_planken',  'stijl': 'planks', 'c1': (210, 195, 150),'c2': (180, 165, 120)},
    {'naam': 'mc_den_stam',      'stijl': 'bark',   'c1': (85, 60, 40),   'c2': (55, 38, 25)},
    {'naam': 'mc_den_planken',   'stijl': 'planks', 'c1': (110, 80, 55),  'c2': (85, 60, 40)},
    {'naam': 'mc_blad',          'stijl': 'leaves', 'c1': (45, 120, 45),  'c2': (30, 90, 30)},
    {'naam': 'mc_boekenkast',    'stijl': 'bookshelf','c1': (165, 130, 80),'c2': (110, 80, 50)},

    # --- Baksteen en gemaakte blokken ---
    {'naam': 'mc_baksteen', 'stijl': 'brick',  'c1': (150, 60, 50), 'c2': (110, 45, 38)},
    {'naam': 'mc_tnt',      'stijl': 'tnt',    'c1': (200, 45, 40), 'c2': (235, 235, 235)},
    {'naam': 'mc_spons',    'stijl': 'sponge', 'c1': (220, 215, 90),'c2': (170, 165, 60)},

    # --- Mineraal-blokken (van erts gemaakt) ---
    {'naam': 'mc_diamant_blok', 'stijl': 'gem',   'c1': (110, 230, 230),'c2': (175, 245, 245)},
    {'naam': 'mc_goud_blok',    'stijl': 'solid', 'c1': (240, 210, 70), 'var': 10},
    {'naam': 'mc_ijzer_blok',   'stijl': 'solid', 'c1': (215, 215, 220),'var': 10},
    {'naam': 'mc_smaragd_blok', 'stijl': 'gem',   'c1': (40, 200, 100), 'c2': (95, 225, 145)},
    {'naam': 'mc_kool_blok',    'stijl': 'speckle','c1': (35, 35, 38),  'var': 8},
    {'naam': 'mc_lapis_blok',   'stijl': 'speckle','c1': (40, 70, 200), 'var': 18},

    # --- Planten en eten ---
    {'naam': 'mc_pompoen',          'stijl': 'pumpkin', 'c1': (225, 135, 30),'c2': (180, 100, 20)},
    {'naam': 'mc_meloen',           'stijl': 'stripes', 'c1': (60, 140, 50), 'c2': (120, 180, 70)},
    {'naam': 'mc_hooibaal',         'stijl': 'hay',     'c1': (210, 180, 70),'c2': (180, 150, 55)},
    {'naam': 'mc_paddenstoel_rood', 'stijl': 'dots',    'c1': (200, 50, 50), 'c2': (240, 240, 240)},
    {'naam': 'mc_lava',             'stijl': 'lava',    'c1': (180, 55, 15), 'c2': (255, 180, 40)},

    # --- Wol (zacht en effen) ---
    {'naam': 'mc_wol_wit',   'stijl': 'wool', 'c1': (235, 235, 235)},
    {'naam': 'mc_wol_rood',  'stijl': 'wool', 'c1': (190, 60, 55)},
    {'naam': 'mc_wol_blauw', 'stijl': 'wool', 'c1': (60, 90, 190)},
    {'naam': 'mc_wol_groen', 'stijl': 'wool', 'c1': (80, 160, 70)},
    {'naam': 'mc_wol_geel',  'stijl': 'wool', 'c1': (220, 200, 70)},
]


# ---- Bestaande spel-blokken die nu een echt plaatje krijgen ----
# (bloktype in het spel  ->  welk plaatje het gebruikt)
BESTAANDE_TEXTUREN = {
    'gras': 'mc_gras', 'aarde': 'mc_aarde', 'steen': 'mc_steen', 'zand': 'mc_zand',
    'hout': 'mc_eik_stam', 'planken': 'mc_eik_planken', 'blad': 'mc_blad',
    'baksteen': 'mc_baksteen', 'sneeuw': 'mc_sneeuw', 'klei': 'mc_klei',
    'zandsteen': 'mc_zandsteen', 'mos': 'mc_mos_steen',
    'paddenstoel': 'mc_paddenstoel_rood', 'pompoen': 'mc_pompoen', 'lava': 'mc_lava',
    'goud': 'mc_goud_erts', 'diamant': 'mc_diamant_erts', 'ijzer': 'mc_ijzer_erts',
    'smaragd': 'mc_smaragd_erts', 'kool': 'mc_kool_erts',
}


# ---- Nieuwe blokken die je in de maak-tafel kunt maken (key == plaatje-naam) ----
NIEUWE_BLOKKEN = [
    {'key': 'mc_cobblestone',     'naam': 'Rommelsteen',        'kosten': {'steen': 1}},
    {'key': 'mc_mossige_cobble',  'naam': 'Mossige rommelsteen','kosten': {'steen': 2}},
    {'key': 'mc_grondsteen',      'naam': 'Grondsteen',         'kosten': {'steen': 3}},
    {'key': 'mc_grind',           'naam': 'Grind',              'kosten': {'zand': 1}},
    {'key': 'mc_lapis_erts',      'naam': 'Lapiserts',          'kosten': {'steen': 2}},
    {'key': 'mc_redstone_erts',   'naam': 'Redstone-erts',      'kosten': {'steen': 2}},
    {'key': 'mc_ijs',             'naam': 'IJs',                'kosten': {'sneeuw': 2}},
    {'key': 'mc_berk_stam',       'naam': 'Berkenstam',         'kosten': {'hout': 2}},
    {'key': 'mc_berk_planken',    'naam': 'Berken planken',     'kosten': {'hout': 1}},
    {'key': 'mc_den_stam',        'naam': 'Dennenstam',         'kosten': {'hout': 2}},
    {'key': 'mc_den_planken',     'naam': 'Dennen planken',     'kosten': {'hout': 1}},
    {'key': 'mc_boekenkast',      'naam': 'Boekenkast',         'kosten': {'hout': 3}},
    {'key': 'mc_stenen_baksteen', 'naam': 'Stenen baksteen',    'kosten': {'steen': 2}},
    {'key': 'mc_netherbaksteen',  'naam': 'Netherbaksteen',     'kosten': {'steen': 2}},
    {'key': 'mc_kwarts',          'naam': 'Kwartsblok',         'kosten': {'steen': 2}},
    {'key': 'mc_obsidiaan',       'naam': 'Obsidiaan',          'kosten': {'steen': 3}},
    {'key': 'mc_glowstone',       'naam': 'Glowsteen',          'kosten': {'zand': 2}},
    {'key': 'mc_netherrack',      'naam': 'Netherrack',         'kosten': {'steen': 1}},
    {'key': 'mc_tnt',             'naam': 'TNT',                'kosten': {'zand': 2, 'kool': 1}},
    {'key': 'mc_diamant_blok',    'naam': 'Diamantblok',        'kosten': {'diamant': 4}},
    {'key': 'mc_goud_blok',       'naam': 'Goudblok',           'kosten': {'goud': 4}},
    {'key': 'mc_ijzer_blok',      'naam': 'IJzerblok',          'kosten': {'ijzer': 4}},
    {'key': 'mc_smaragd_blok',    'naam': 'Smaragdblok',        'kosten': {'smaragd': 4}},
    {'key': 'mc_kool_blok',       'naam': 'Kolenblok',          'kosten': {'kool': 4}},
    {'key': 'mc_lapis_blok',      'naam': 'Lapisblok',          'kosten': {'steen': 4}},
    {'key': 'mc_meloen',          'naam': 'Meloen',             'kosten': {'blad': 2}},
    {'key': 'mc_hooibaal',        'naam': 'Hooibaal',           'kosten': {'blad': 2}},
    {'key': 'mc_spons',           'naam': 'Spons',              'kosten': {'zand': 2}},
    {'key': 'mc_wol_wit',         'naam': 'Witte wol',          'kosten': {'blad': 1}},
    {'key': 'mc_wol_rood',        'naam': 'Rode wol',           'kosten': {'blad': 1}},
    {'key': 'mc_wol_blauw',       'naam': 'Blauwe wol',         'kosten': {'blad': 1}},
    {'key': 'mc_wol_groen',       'naam': 'Groene wol',         'kosten': {'blad': 1}},
    {'key': 'mc_wol_geel',        'naam': 'Gele wol',           'kosten': {'blad': 1}},
]

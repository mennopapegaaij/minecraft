"""
Maakt twee korte geluidjes voor het spel: een 'plop' en een 'boink'.
Je hoeft dit maar één keer te draaien: python maak_geluiden.py
De geluiden komen dan in de map 'assets' te staan.
"""
import wave      # hiermee kun je geluidsbestanden (.wav) maken
import struct    # hiermee zetten we getallen om in bytes
import math      # voor de sinus-golf (dat is de toon)
import os        # om de map 'assets' te maken

# Hoeveel 'metingen' per seconde het geluid heeft (standaard voor geluid)
SAMPLES_PER_SEC = 44100


def maak_geluid(bestandsnaam, frequentie, duur):
    """Maakt een kort piepje dat langzaam zachter wordt (een 'plopje')."""
    os.makedirs('assets', exist_ok=True)   # zorg dat de map 'assets' bestaat
    pad = os.path.join('assets', bestandsnaam)

    aantal = int(SAMPLES_PER_SEC * duur)   # hoeveel metingen we nodig hebben
    bestand = wave.open(pad, 'w')
    bestand.setnchannels(1)    # 1 = mono (één kanaal)
    bestand.setsampwidth(2)    # 2 bytes per meting
    bestand.setframerate(SAMPLES_PER_SEC)

    for i in range(aantal):
        tijd = i / SAMPLES_PER_SEC
        # De golf wordt steeds zachter (decay), zodat het als een 'plop' klinkt
        zachter = max(0.0, 1.0 - i / aantal)
        waarde  = math.sin(2 * math.pi * frequentie * tijd) * zachter
        # Zet de waarde (-1 tot 1) om in een heel getal en schrijf het weg
        bestand.writeframes(struct.pack('<h', int(waarde * 32000)))

    bestand.close()
    print(f"Gemaakt: {pad}")


# Een hoge, vrolijke 'plop' (om een blok te plaatsen)
maak_geluid('plop.wav', frequentie=700, duur=0.08)
# Een lage 'boink' (om een blok af te breken)
maak_geluid('boink.wav', frequentie=250, duur=0.12)

print("Klaar! De geluiden staan nu in de map 'assets'.")

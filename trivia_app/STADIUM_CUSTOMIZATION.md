# Stadion v6 a vzhled POINTS

Aktualni scena pouziva geometrii a trasu z dodaneho `stadion_penalty_v6.html`.
Original v Downloads zustal beze zmeny. Jeho demo ovladani ani pravidlo
"stred = save" se neprebiraji. Hra nadale pouziva serverove vysledky a sest zon.

## Kde upravovat

| Soubor | Co ovlada |
|---|---|
| `static/stadium_config.js` | `V6_WORLD`: barvy, travnik, tunel, mic, obleceni; `STADIUM`: herni kamera, casy a cile kopu |
| `static/stadium_v6_world.js` | Geometrie v6, spojity ram brany, sit, stiny, modely, rozplynuti tribun |
| `static/stadium_scene.js` | Trasa kamery, PvP pohled, ramovani, strela a chyceni mice |
| `static/points_theme.css` | ON THE DOT.: tmava stadionova paleta UI, koralove akce a limetkove vybrane stavy |
| `static/community.css` | Verejna navigace, menu, leaderboard, historie a profilovy panel |
| `static/stadium.css` | Rozlozeni 3D stadionu a panelu otazek |
| `static/stadium_intro.js` | Nacitani, reduced motion, Skip, nastup UI, uvolneni rendereru |
| `static/penalty_shots.js` | Nahodny plan kopu stejny pro oba PvP klienty |

## Barvy a geometrie

Barvy v `V6_WORLD.colors` jsou `0xRRGGBB`. Napriklad `shirt: 0xef8464`
je koralovy dres, `pitch: 0x244b3d` travnik a `bright: 0xe6eee4` cary.
CSS pouziva stejny styl: `--bg`, `--surface`, `--accent`, `--coral`,
`--text`, `--muted`, `--border` v `points_theme.css`.

- `pitchMarkings.width`: skutecna sirka malovanych pasu v metrech (0.22).
- `pitchMarkings.centreSpotRadius`: polomer plneho stredoveho puntiku.
- `penalty.ballRadius`: polomer mice; 0.17 m pro citelnost.
- `tunnel`: sirka, vyska a delka cisteho nepruhledneho tunelu.
  `lightSpacing`, `lightWidth`, `lightDepth` meni stropni svetla;
  `edgeWidth` meni tloustku zvyraznenych hran sten (v metrech).
- `focus.duration`: rozplynuti tribun po prijezdu, vychozi 1.65 sekundy.
- `duration`: samotny prijezd, vychozi 8.4 sekundy.
- `maxPixelRatio`: ostrost canvasu vs. vykon na telefonu.

Tloustka tyci je parametr `radius` pri volani `continuousFrame` v
`buildGoal()`: predni ram 0.06 m, zadni 0.021 m. Jde o POLOMER.
Sit ma `nZ=30, nY=10, nX=9`; zvetseni znamena hustejsi sit.
Tribuny jsou plne, nepruhledne a maji uzavreny predni/zadni plast i boky u tunelu.
`outlineOnly: false` a zapis do depth bufferu zakryvaji zadni konstrukci.
Tenke predni obrysy zustavaji citelne diky polygon offsetu plochy.
Pri rozpousteni zustava depth test i shader stejny. Plast se kresli pred obrysy
(`renderOrder=-2`, cary `-1`); materialy maji blending zapnuty od zacatku,
ale pri focus=0 je plast zcela nepruhledny. Neprepinat `transparent` nebo
`depthWrite` uvnitr animace: zpusobuje to kompilaci a zmenu viditelnych hran.
`fadingMaterial()` pouziva pro plochy, cary i tunel stejnou masku shora dolu.
Hodnota 12 m je horni vyska masky, 0.6 je sirka mekke hrany; celkove tempo
ovlada `STADIUM.focusMs`. Skupina se skryje az pri focus=1.
Malovane cary hriste jsou
trojuhelnikove pasy, nikoliv nefunkcni WebGL `linewidth`.

Mic ma skutecnych 12 pentagonu a 20 hexagonu, hladky povrch a zapustene svy.
Brankar ma dres, rukavice, boty, oblicej a cislo. Protihrac v PvP pouziva
stejny model s cislem 10. Stiny i cisla vznikaji lokalne na malem canvasu.

## Trasa a herni cas

X = delka hriste, Y = vyska, Z = sirka. Brana je na X=52.5, puntik na X=41.5.
Kamera jede tunelem rovne do Z=12, projede mekkou kvintickou zatackou a
dobrzdi za micem. PvP brankar pokracuje kolem puntiku do brany a otoci se.

Po dojezdu se rozplynou tribuny a vzdaleny stadion, nikoliv brana nebo hrac.
`#stadium-framing` v CSS vymezuje prostor mimo otazky; renderer do nej
automaticky ramuje branu a mic. Na mobilu je panel dole, na desktopu vpravo.

Panel se odhaluje gradientni maskou a vyjizdi o 36 px vzhuru SOUCASNE s fade
stadionu. `--stadium-reveal` dostava primo jeho hodnotu 0..1 ze stejneho RAF,
ne z nezavisleho CSS timeru. Behem nastupu je panel inertni. Skip/reduced motion
nastavi oboji rovnou na 1. Sirka desktopoveho panelu je `min(560px,44vw)`,
mobilni vyska 56dvh; velikosti a maska jsou v `stadium.css`.

Solo intro probiha v `READY`, pred spustenim casu otazky. PvP intro je pred
odeslanim `ready`; countdown zacne az po obou hracich. Obnoveni stranky
uprostred otazky nespousti dalsi intro a neposouva deadline.
Pri dalsich PvP kolech se kamera musi zastavit nejpozdeji pri otevreni otazky.

## Sest zon a vysledky

Plan vybira leva/stred/prava, vzdy nizka nebo vysoka strela.
`STADIUM.shot.postInset` a `crossbarInset` jsou rezervy od tyci a brevna;
`catchX` je poloha dlani pred brankovou carou.

- `goal`: brankar skoci na opacnou stranu, u strely na stred do rohu.
- `save`: dlane miri presne na mic; mic po chyceni zustava mezi rukavicemi.
- `miss`: strela mine branu.
- `replay`: bez zavadejici animace strely.

`stadium_motion.js` pocita paraboly a tlumene odrazy analyticky, nezavisle na
FPS. `STADIUM.shot.gravity` je 9.81 m/s2, `flightSeconds` urcuje dobu letu k
brane a `bounce` ztratu rychlosti pri odrazu. `shotDuration` zahrnuje i doskok.
Brankar po vysoku klesne na travnik; pri save zustava mic ve stredu rukavic
a ruce se skladaji k hrudi. Vysoky gol po kontaktu se siti spadne a odskoci.
Reduced motion zobrazi az klidovou polohu, nikoli mic visici v sibenici.

Fade shader zacina menit alpha hned pri prvnim nenulovem `focus`, bez
pocatecni prodlevy. Stejny snimek meni masku HTML panelu. Oba prechody
zacnou az po dojezdu kamery; skip oba soucasne dokonci.

Identifikator kola seeduje pouze vizualni losovani. Oba PvP hraci vidi stejny
prostorovy kop, kazdy ze sve kamery. Opakovane zpravy
nelosuji novy smer. Vizualizace nikdy neurcuje spravnost odpovedi, skore nebo XP.

## UI a vysvetleni

Vysledek odpovedi a vysvetleni zustavaji viditelne. Texty o zdroji, autorovi
a databazovem overeni se v hernim feedbacku ani souhrnu nezobrazuji.
Zdrojova metadata a validace v databazi/Studio zustaly beze zmeny.
Odstraneny jsou take dekorativni podnadpisy a opakovane "Daily quiz complete".
Dulezite chybove stavy, casovac a informace o neukladanem trial XP zustavaji.
Po End shootout se posledni otazka skryje a fokus prejde na souhrn. Pocet
spravnych odpovedi ma jmenovatel cely kviz, ne jen odehrane otazky. Level a
zbyvajici XP jsou ze serverove transakce, ktera zapisuje odmeny; trial nema
ulozeny postup. Detail odpovedi je sbalitelny.

## Pristupnost a zavislosti

`Skip intro` nebo Escape preskoci pohyb. Systemovy reduced motion a prepinac
Animations ho potlaci. 2D pohled, SVG hriste i oba prepinace jsou odstranene.
Pri chybe WebGL se zobrazi upozorneni; otazky zustanou ovladatelne, ale zadny
nahradni 2D renderer se nespusti. Mimo animaci nebezi nekonecny RAF.
Pri zavreni sceny se uvolni geometrie, materialy, textury a listenery.

Pouziva se puvodni lokalni Three.js 0.180.0 vcetne MIT licence. Knihovna r140
vlozena v dodanem HTML se nekopiruje; shadery byly prizpusobeny r180.
Zadne CDN, externi modely nebo externi textury nejsou potreba.

## Overeni

```sh
node --test tests/*.cjs
.venv/bin/python -m unittest tests.test_penalty_engine tests.test_stadium_assets
NODE_PATH=<cesta-k-playwright-a-pngjs> node src/verify_stadium.cjs
NODE_PATH=<cesta-k-playwright-a-pngjs> node src/verify_points_theme.cjs
```

Browser test potrebuje server na portu 8002 a Chrome. Vytvori izolovane
anonymni solo/PvP hry a na konci je ukonci. Kontroluje pohyb, v6 modely,
nepruhledne tribuny, synchronni gradientni nastup panelu, deadline, chyby WebGL
a vsech sest zon goal/save. Kontroluje i landscape a uzky mobil.
Screenshoty a pixelove kontroly desktopu/mobilu jsou v
`data/private/stadium-ui-check`. Node testy kontroluji i 1000 losovanych kol.

Izolovana pixelova kontrola fade bez databaze:
spust `.venv/bin/python -m tests.community_preview`, otevri
`http://127.0.0.1:8013/stadium-fade` a stiskni `Check gradient`.
Test vykresli skutecne materialy car/plaste samostatne i dohromady v sedmi
fazich a zmeri alpha pixely. `pass: true` znamena postupny ubytek az na nulu.
`tests/test_stadium_fade.cjs` navic hlida stabilni shader/depth stav a predcasne
skryti skupiny tesne pred koncem.

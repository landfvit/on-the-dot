# Pixel-art scena penalty

Hra zobrazuje souvisly travnik s carami vapna, bilou branu, mic a dve pixelove
postavy. Stadion, tribuny, tunel, svetla, blur a prelety kamery se nevytvareji.
Nazvy souboru a exportu zustaly kompatibilni s hernim mostem a Retry 3D.

## Kde upravovat

| Soubor | Co ovlada |
|---|---|
| `static/stadium_config.js` | Barvy, velikosti postav, brany a travniku, pevny zaber, casovani |
| `static/stadium_v6_world.js` | Hriste, ridka sit, pixelove vzory hracu a presne ukotveni dlani |
| `static/stadium_scene.js` | Ramovani, pohyb mice a brankare, vykreslovani a uvolneni GPU |
| `static/stadium_inline.css` | Velikost nahledu a stabilni rozmery otazek a odpovedi |
| `static/stadium_intro.js` | Nacteni, Ready, Retry, vypnuti animaci a prechod do vysledku |
| `static/penalty_shots.js` | Losovani sesti cilovych zon; stejny plan pro oba hrace duelu |
| `static/kit_pixels.js` | Vlastni pixelove vzory dresu, kratasy, stulpny a cisla |
| `../tools/player_kit_designs.json` | Overene barvy a vzory klubovych sad s odkazy na predlohy |
| `static/player_kit.js` a `static/player_kit.css` | Vyber vlastniho dresu a cisla v profilu |

## Barvy a rozmery

Hodnoty barev v `V6_WORLD.colors` maji format `0xRRGGBB`.

- `pitch: 0x88b04b`: zelena travniku z palety.
- `goal` a `markings`: bila brana, sit a cary v obou rezimech.
- `strikerShirt` (modra) a `shirt` (fialova), jejich `Light`/`Shade` varianty: mistni a souperuv dres.
- `skin`, `hair`, `shorts`, `outline`: paleta pixelovych postav, stejna v obou tematech.
- `structure.postRadius`: polovina sirky prednich tyci (0.07 m).
- `structure.goalOutline`: cerny obrys tyci (0.025 m navic).
- `structure.netOpacity`: pruhlednost ridke bile site (0.80).
- `pitchMarkings.width`: zakladni sirka bilych car (0.15 m).
- `ground`: vyska travniku a presah za branou; travnik pokracuje mimo nahled.
- `area`: rozmery velkeho/maleho vapna a radius oblouku; sirka je stylizovana pro kratky nahled.
- `penalty.ballRadius`: stylizovany polomer mice (0.28 m) pro citelne chyceni.

Sit ma deset sloupcu a ctyri rady. `prepareFrame()` drzi cary alespon na
1.4 logickeho pixelu a bile jadro tyci na 2.2 px, aby nebyly prerusovane.
Postavy jsou sestavene z malych ASCII vzoru prevedenych na `DataTexture`:
tecka znamena pruhlednost, ostatni znaky barvy z palety. Hlava, telo a koncetiny
jsou samostatne `Sprite` objekty s `NearestFilter`, bez mipmap. Velikosti dilu
jsou u volani `part()` a `limb()` ve funkci `player()`.
Rukavice jsou artikulovane, aby chyceny mic presne sledoval ruce.
Mic pouziva vlastni vzor 16x16 pixelu s cernymi panely, jemnymi sedymi
svy a ctyrmi otocenimi. Pri chyceni se rotace zastavi. Poloha mice
stale pouziva 3D fyziku; minimum 7 logickych pixelu zachovava citelnost v brane.

`world.setRole()` prohodi dresy: pri kopani nosi mistni dres strelec,
pri chytani brankar. Bez vybraneho klubu zustava modra/fialova vychozi paleta.
Stejna lokalni logika plati v Solu, Daily i na obou zarizenich Duelu.
Rukavice a anatomie se nemeni. Prepinani role nevytvari nove textury.

## Klubove dresy

Dresy se kresli z vlastnich pixelovych vzoru, nikoli ze stazenych obrazku
Wikipedie. `kit_pixels.js` umi pruhy, obruce, diagonalu, kostky a dalsi vzory.
Predni a zadni strana maji 18x20 pixelu. Cisla 1-99 maji kontrastni obrys.
Jde o stylizaci barev a strihu; sponzori a klubove znaky nejsou kopirovany.

Zdrojovy soubor `tools/player_kit_designs.json` obsahuje 35 klubu a 75 sad;
30 dalsich kombinaci klub/sada zatim ceka na overeni predlohy. Kazda sada
je `[typ, vzor, dres, kontrast, rukav, lem, kratasy, stulpny]`.
Sezona je 2026/27 pro soucasne PL kluby, 2025/26 pro drivejsi kluby.
Po uprave spust `node tools/build_player_kits.mjs`; tento offline prikaz
vygeneruje verejny `static/player-kits/catalog.json` bez stahovani obrazku.
Pri pridani noveho ID priprav i novou migraci registru `game_kits`.

Profil vybira pouze sady sveho klubu. API i slozeny databazovy cizi klic
hlidaji vlastnictvi. Zmena klubu vymaze vybranou sadu a pouzije novy domaci
dres; cislo zustane. Duel uklada verejny snapshot obou dresu pri vstupu,
aby uprava profilu neprebarvila rozehranou hru. Stare mistnosti a hoste
zustavaji kompatibilni s vychozimi dresy.

Pred nasazenim na dalsi databazi aplikuj `053_player_kits`:
`.venv/bin/python -m tools.migrate_account_settings --render --migration 053_player_kits`.
Lokalni migrace je aplikovana, produkcni nasazeni neni soucasti teto upravy.

## Kamera a animace

X = delka hriste, Y = vyska, Z = sirka. Brana je na X=52.5,
penaltovy puntik na X=41.5. `STADIUM.camera` ma pole
`offset` (pozice kamery) a `lookAt` (cil pohledu), obe relativne k puntiku.
Kamera je primo za kopajicim; zaber zustava stejny pri obou rolich.
Vychozi `offset=[-14,3.5,1.35]`, `lookAt=[6,.9,1.35]`.
Nizsi vyska s tesnejsim ramovanim zvetsuje branu oproti puvodnimu nadhledu.
Stejne Z kamery a cile zachovava vodorovne cary hriste rovnobezne s UI.
`framingPadding` nechava bezpecny okraj kolem postav a vsech sesti cilovych zon.
Kamera ramuje akci, ne vsechny rohy hriste; travnik a cary zustavaji souvisle.

Zaber se zobrazi okamzite (`introMs=0`, `roleChangeMs=0`). Role se pozna
podle prohozeneho dresu. Retry i reduced motion obnovi stejne barvy a zaber.
Konec hry pouziva kratke 180ms prolnuti; odchazejici canvas zustava
ve stejnem obdelniku, aby pri zobrazeni vysledku neposkocil.

`runUpMs=280` a `shotMs=1500` sdileji rychlost `betweenShotSpeed=1.3`.
Po animaci zbyva `resultHoldMs=350` ms. Celkem jde priblizne o 1.72 s.
Zmena rychlosti nemeni gravitaci ani presnost zasahu.

`stadium_motion.js` pocita paraboly a tlumene odrazy nezavisle na FPS.
Brankar musi dopadnout zpatky na travnik; pri save zustava mic mezi rukavicemi.
Po doskoku vstane a podrzi mic u hrudi; rotace mice se pri chyceni zastavi.
Vysoky gol po kontaktu se siti spadne a odskoci.

Plan urcuje leva/stred/prava a nizka/vysoka strela. Vysledek dodava server:
`goal`, `save`, `miss` nebo `replay`. Animace nikdy nerozhoduje o skore,
XP, spravnosti odpovedi ani casovem limitu. V Duelu zustavaji reakce zvuku
vzdy z pohledu mistniho hrace.

## Vykon a pristupnost

Scena pouziva jeden render pruchod, bez svetel, postprocessingu, render
targetu nebo externich textur. Mimo animaci nebezi nekonecny RAF.
`pixelArt.maxWidth=480` a `maxHeight=270` urcuji pixelovou mrizku.
Renderer pouziva nejvyse DPR 1, bez multisamplingu. CSS zvetsuje canvas
pomoci `image-rendering: pixelated`; textury maji nearest filtering.
Citelnost zajistuje blizsi kamera a podrzeni mice, nikoli hladky retina render.
Textury postav se sdileji a pri zavreni sceny se uvolni spolu s GPU zdroji.

Vypnuti animaci nebo systemovy reduced motion zobrazi klidovy vysledek.
Chyba WebGL nesmi zamknout Ready/Next ani menit herni stav.
Retry vytvari novy renderer a muze znovu nacist celou zavislostni vetev.
Pri uvolneni sceny se zlikviduji geometrie, materialy, renderer a listenery.

## Overeni

Vychozi localhost je `http://127.0.0.1:8009`; browser testy lze presmerovat
promennou `MOBILE_TEST_URL`. Pouzivaji mockovane herni API nebo pouze
renderer, takze nezapisuji pokusy do databaze.

- `test_stadium_motion.cjs`, `test_stadium_fade.cjs`: fyzika, geometrie a pixelove textury.
- `test_stadium_compact_browser.cjs`: sest zon, pevna kamera, dresy, citelnost mice a prolinani.
- `test_stadium_players_browser.cjs`: light/dark sprity, doskok a presne chyceni.
- `test_stadium_inline_browser.cjs`: mobil/desktop, stabilni tlacitka a prechod do vysledku.
- `test_stadium_recovery_browser.cjs`: importy, WebGL chyby a obnova bez hernich zapisu.
- `test_daily_ready_browser.cjs`, `test_friend_decision_browser.cjs`: Daily a obe role duelu.
- `test_player_kits_browser.cjs`: mobil/desktop profil, 99 cisel, vlastni klub,
  ulozeni a obnoveni, pevna kamera, rovnobeznost car a opakovane zmeny textur.
- `test_player_kits.py`: katalog a izolovane databazove testy vlastnictvi,
  zmeny klubu, blokace, smazani uctu a snapshotu dresu v duelu.

Browser skripty potrebuji Playwright a sharp; `TEST_BROWSER=webkit` voli WebKit.
Pro Chromium lze v inline testu pouzit `TEST_GPU=native`.

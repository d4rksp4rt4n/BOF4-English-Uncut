# Breath of Fire IV – English Uncut & fixes (GOG PC)

A patcher for the English GOG release of *Breath of Fire IV* that restores content cut from the Western
release and fixes several problems of the PC port. It comes as a small Windows installer with a GUI. Every
option can be switched on or off, and "Restore original files" undoes everything.

| Option | What it does |
|---|---|
| Restore cut scenes | Ryu/Ursula at the checkpoint, Ursula on Zig's ship, Emperor Soniel's attack on Fou-Lu and the Saldine Island bath scene, with English text |
| Unlock the Dengeki Store | The Japan-only store, with its original English (US PlayStation) text and the graphics the English port dropped |
| Stutter fix | The per-frame screen clear runs on the GPU instead of forcing a GPU readback in GOG's ddraw wrapper (random hitches) |
| PlayStation reverb | The PC music is dry MP3 recordings; this adds the PS1 sound chip's reverb back at runtime, using the PS1 game's own setting |
| Correct music loops | Songs loop from their real loop point instead of replaying the intro, and without the click/gap the PC player makes at every restart |
| Scias learns Identify | Restores the cut Identify ability at level 3, with element icons for the weakness/resistance list as in the PS1 hack |
| Better Descriptions | Naro's descriptions of hidden item, equipment and master effects |

## For players

1. You need the English GOG version of Breath of Fire IV. The installer checks every file and refuses
   to change anything that isn't the original English GOG data.
2. Download `BOF4_Uncut_EN.exe` from this repository's **Releases** page, put it next to `BOF4.exe`
   and run it. Tick the options you want and press **Apply**.
3. Originals are kept in `BOF4_Uncut_EN_backup`. Run the installer again any time to change options or
   to restore the original files.

Notes:
- **Saves past Saldine:** a save made in the unmodded game after the party reached the Saldine Island
  creek will freeze when it enters the creek with "Restore cut scenes" on, because the bath scene still
  counts as unseen. Use an earlier save, or play that save without that option.
- **Windows warnings:** the installer is unsigned, edits `BOF4.exe` and adds a DLL, so Windows SmartScreen
  or antivirus software may warn about it. The full source is here; you can build it yourself.
- **Music tuning:** optional `BOF4_reverb.ini` next to `BOF4.exe`:
  ```ini
  [reverb]
  wet=100   ; reverb level in % of the PS1's (0 = off)
  ```

## Status – testing wanted

This is a young project tested on one machine. Reports are very welcome. Open an issue with what you
did, where you were in the game, and, if possible, a save file.

| Area | Status |
|---|---|
| Restored scenes | All four tested in game: the checkpoint, Ursula on Zig's ship, Soniel vs. Fou-Lu and the Saldine bath scene |
| Dengeki Store | Tested in game: shop and lottery work, with English text and the clerk's portrait. The signs on the building and in the shop stay Japanese: they are painted into the textures, and the store never had an English release |
| Stutter fix, reverb | Tested over long play sessions |
| Music loops | Many songs checked by ear and sample-exact in game; not every song in every area has been heard. Report any song whose loop sounds off (jump, gap, replayed intro), with the area |
| Scias learns Identify | Tested in game: HP, Exp, treasure, info, and the element icons with their weak/normal/strong colours |
| **Steam version** | **Not supported.** The installer only accepts the English GOG files and refuses anything else, so it won't damage a Steam install. The Steam exe is protected differently and has not been examined. Help from Steam owners is welcome |

## Building from source

Requirements (Windows):
- Python 3 with `numpy` and `Pillow`
- Visual Studio Build Tools with the C++ x86 compiler (for `bof4_reverb.dll`)
- the .NET Framework 4 C# compiler that ships with Windows (for the installer)

Inputs (never committed; set the paths in `config.py` or with environment variables):

| Setting | Default | What |
|---|---|---|
| `BOF4_GAME` | parent of this folder | the game folder |
| `BOF4_CLEAN_EXE` | `backup\BOF4.exe` | an untouched GOG `BOF4.exe` |
| `BOF4_CLEAN_DAT` | `<game>\DAT_backup` | untouched English GOG `DAT` files |
| `BOF4_DESC_ZIP` | `<game>\Breath of Fire IV - Better Descriptions-*.zip` | Naro's PC release |

Build:
```bat
reverb\build.bat
py build_mod.py
```
`build_mod.py` writes `mod\BOF4_Uncut_EN.exe`. The installer embeds only the differences from the original
files, plus SHA-256 checks, for every combination of options.

The loop analysis in `loops\` (only needed to regenerate `reverb\loops_table.h`) also needs `ffmpeg`
(`FFMPEG`) and the extracted US PS1 disc (`BOF4_PS1_BGM`). Run it as `analyze.py`, then `measure.py`,
`final.py` and `make_table.py`.

`derive_scenes.py` (only needed to re-check the scene redirects) also needs the clean US PS1 disc image
(`BOF4_PS1_US_BIN`, Track 1 `.bin`) and navarchos' Uncensored hack applied and extracted
(`BOF4_PS1_HACK_WORLD`, its `BIN\WORLD` folder).

## Repository layout

| Path | Contents |
|---|---|
| `build_mod.py` | builds the installer (variants, diffs, art, C# compile) |
| `patch_uncut_en.py` | the game patches: exe code caves, restored text, Dengeki Store, Identify. Its command line is an older local patcher |
| `identify_icons.py` | the Identify screen's element icons (font glyphs, labels); run it for a preview image |
| `derive_scenes.py` | derives the scene redirects from the US PS1 disc and the Uncensored hack |
| `installer.cs` | the GUI installer (WinForms) |
| `reverb\` | `bof4_reverb.dll`: PS1 SPU reverb (`bof4_reverb.c`) and loop engine (`loops.c`, `loops_table.h`) |
| `loops\` | analysis that derives loop points from the PS1 sequences and the PC recordings |
| `lzhuf.py` | codec for the PC DAT files' compressed chunks |
| `art\` | installer artwork (see credits) |
| `mod\README.txt` | the readme shipped with releases |

## How it works (short)

- **Restored scenes:** the US release cut three scenes in the event scripts (early script ends and
  skips). `derive_scenes.py` diffs the US PS1 disc against navarchos' Uncensored hack and maps the
  changes onto the script data in `BOF4.exe`; a hook on the script interpreter (code caves in unused
  `.text` padding) then runs the hack's script code at those points. The Saldine bath setup the US build
  dropped is re-added as x86 code. The restored English lines are appended to the areas' text tables.
- **Dengeki Store:** two event flags held every frame, the US PS1 English text, and the two chunks the
  English port dropped (from the Japanese GOG release).
- **Identify:** Scias' level-3 entry gets the ability back. Its Data panel draws the 12 element names one
  Japanese character (12 px) apart, so the English names overlap. As in navarchos' PS1 hack they become
  icons: 12 glyphs added to the game's text font (`INIT.DAT`), drawn from the PS1 element icons, so the
  panel's red/grey/blue resistance colours tint them like letters. The labels in the battle text
  (`AB000_00`, `BTLEND`) become those characters, and the HP separator, which shared the unknown-item
  "?", becomes "/" (the hack's v1.1 fix). An unseen item's "?" marks are drawn 8 px apart instead of
  12, so long names stay inside the Treasure panel.
- **Music:** the PC version streams MP3s. A stub in the exe loads `bof4_reverb.dll`, which wraps the MP3
  decoder:
  - **Loops:** it jumps from each recording's loop end to its loop start, sample-exact, skipping the final
    frame that the game's decoder garbles.
  - **Reverb:** it runs the PS1 reverb ("Studio Medium", depth 64/127, as the PS1 sound driver sets it) on
    the decoded music.

## Credits

- Restored scene scripts and text: **navarchos** – [Breath of Fire IV Uncensored (PS1)](https://www.romhacking.net/hacks/7192/)
- Identify (level-up entry, element icon idea and the Wind/Holy/Mind icon shapes): **navarchos** – Breath of Fire IV: Working Identify Ability Hack (PS1)
- Better Descriptions: **Naro** – [Better Descriptions](https://www.romhacking.net/hacks/9575/)
- PS1 reverb algorithm: [psx-spx](https://psx-spx.consoledev.net/soundprocessingunitspu/) (nocash)
- Installer art (SteamGridDB): background by **Ar,,**, logo by **Llisandur**, icon by **Rebochan**
- Dengeki Store graphics: the Japanese GOG release of Breath of Fire IV

*Breath of Fire IV* is © Capcom. This is an unofficial fan project, not affiliated with Capcom or GOG.

## License

See [LICENSE](LICENSE). In short: personal use, modification and GitHub forks are fine. **Re-uploading or
redistributing it anywhere else, including Nexus Mods, is not allowed without permission.** Link to this
repository instead. Third-party material stays with its owners.

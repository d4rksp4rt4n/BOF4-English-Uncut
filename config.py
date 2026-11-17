# Local paths for the build and analysis tools. Defaults assume this folder sits inside the game folder
# (e.g. "...\Breath of Fire IV\_uncut_en"); override any of them with environment variables.
import glob, os, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("BOF4_GAME", os.path.dirname(HERE))                       # the game folder
CLEAN_DAT = os.environ.get("BOF4_CLEAN_DAT", os.path.join(GAME, "DAT_backup"))   # untouched English GOG DAT files
CLEAN_EXE = os.environ.get("BOF4_CLEAN_EXE", os.path.join(HERE, "backup", "BOF4.exe"))   # untouched GOG BOF4.exe
PS1_BGM = os.environ.get("BOF4_PS1_BGM", os.path.join(GAME, "PS1", "BIN", "BGM"))        # PS1 disc's BIN\BGM folder
PS1_US_BIN = os.environ.get("BOF4_PS1_US_BIN", os.path.join(GAME, "Breath of Fire IV (USA) (Track 1).bin"))  # clean US disc
PS1_HACK_WORLD = os.environ.get("BOF4_PS1_HACK_WORLD", os.path.join(GAME, "PS1", "BIN", "WORLD"))  # Uncensored hack, extracted
DESC_ZIP =os.environ.get("BOF4_DESC_ZIP") or next(iter(sorted(glob.glob(
    os.path.join(GAME, "Breath of Fire IV - Better Descriptions-*.zip")))), "")  # Naro's PC release (Nexus)
FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"         # only the loop analysis needs it

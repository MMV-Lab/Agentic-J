"""
MIST_WORKFLOW_TILE_STITCHING.py
Microscopy Image Stitching Tool — Batch Stitching Workflow

PURPOSE:
    Runs MIST headless via the standalone JAR to stitch a grid
    of microscopy tiles into a single mosaic .tif.

USAGE:
    Edit the PARAMETERS block below, then run:
        python MIST_WORKFLOW_TILE_STITCHING.py

REQUIREMENTS:
    - Python 3.6+
    - Java 8+ (64-bit) accessible on PATH (test with: java -version)
    - MIST standalone JAR built from source:
        git clone https://github.com/usnistgov/MIST.git
        cd MIST && mvn package
        JAR = MIST/target/MIST_-{version}-jar-with-dependencies.jar
    - FFTW library (recommended for speed):
        Linux/macOS: sudo apt install libfftw3-dev  OR  brew install fftw
        Windows: libfftw3f.dll is bundled in Fiji.app/lib/fftw/

NOTES:
    - MIST has NO IJ.run() scripting API — the standalone JAR is the
      only supported headless execution pathway.
    - All tiles must be grayscale and the same pixel dimensions.
    - Tiles must be in a single flat directory (no subdirectories).
"""

import subprocess
import sys
import os
import time
from pathlib import Path

# ============================================================
# PARAMETERS — edit these for your dataset
# ============================================================

# Path to MIST standalone JAR
MIST_JAR = "/path/to/MIST_-2.1-jar-with-dependencies.jar"

# --- Input ---
IMAGE_DIR = "/data/experiment01/tiles"

# Filename pattern using MIST tokens
# Row-Column examples:
#   "img_r{rr}_c{cc}.tif"      (2-digit row/col)
#   "Tile_r{rrr}_c{ccc}.tiff"  (3-digit row/col)
# Sequential examples:
#   "img_pos{ppp}.tif"          (3-digit sequential)
FILENAME_PATTERN      = "img_r{rrr}_c{ccc}.tif"
FILENAME_PATTERN_TYPE = "ROWCOL"   # "ROWCOL" or "SEQUENTIAL"

GRID_WIDTH  = 5    # number of columns (tiles per row)
GRID_HEIGHT = 5    # number of rows (tiles per column)
GRID_ORIGIN = "UL" # "UL", "UR", "LL", "LR"

# --- Row-Column mode parameters ---
START_ROW = 1   # smallest row index in filenames (usually 0 or 1)
START_COL = 1   # smallest col index in filenames (usually 0 or 1)

# --- Sequential mode parameters (uncomment if using SEQUENTIAL) ---
# NUMBERING_PATTERN = "HORIZONTALCOMBING"  # HORIZONTALCONTINUOUS, VERTICALCOMBING, VERTICALCONTINUOUS
# START_TILE = 1

# --- Output ---
OUTPUT_DIR      = "/data/experiment01/output"
OUT_FILE_PREFIX = ""         # prefix for output filenames; empty = no prefix
BLENDING_MODE   = "OVERLAY"  # "OVERLAY", "LINEAR", "AVERAGE"
OUTPUT_FULL_IMAGE = "true"

# --- FFT Engine ---
PROGRAM_TYPE  = "FFTW"          # "AUTO", "JAVA", or "FFTW"
FFTW_LIB_FILE = "libfftw3.so"   # Linux; Windows: libfftw3f.dll; macOS: libfftw3.dylib
FFTW_LIB_NAME = "libfftw3"      # Windows: libfftw3f
FFTW_LIB_PATH = "/usr/local/lib" # Windows: C:/Fiji.app/lib/fftw

# --- Advanced (None = let MIST estimate automatically) ---
HORIZONTAL_OVERLAP     = None  # e.g. 15 (percent)
VERTICAL_OVERLAP       = None  # e.g. 15 (percent)
OVERLAP_UNCERTAINTY    = 5     # percent tolerance (default 5; increase for sparse images)
NUM_FFT_PEAKS          = 2     # 1-10 (default 2; try 3-5 for repetitive samples)
TRANSLATION_REFINEMENT = "SINGLE_HILL_CLIMB"  # MULTI_POINT_HILL_CLIMB, EXHAUSTIVE
LOG_LEVEL              = "HELPFUL"  # NONE, MANDATORY, HELPFUL, INFO, VERBOSE

# ============================================================
# VALIDATION
# ============================================================

def validate():
    errors = []
    if not Path(MIST_JAR).is_file():
        errors.append(f"MIST JAR not found: {MIST_JAR}\n    Build with: cd MIST && mvn package")
    if not Path(IMAGE_DIR).is_dir():
        errors.append(f"Image directory not found: {IMAGE_DIR}")
    if GRID_WIDTH < 1 or GRID_HEIGHT < 1:
        errors.append("GRID_WIDTH and GRID_HEIGHT must be >= 1")
    if FILENAME_PATTERN_TYPE not in ("ROWCOL", "SEQUENTIAL"):
        errors.append("FILENAME_PATTERN_TYPE must be 'ROWCOL' or 'SEQUENTIAL'")
    if GRID_ORIGIN not in ("UL", "UR", "LL", "LR"):
        errors.append("GRID_ORIGIN must be one of: UL, UR, LL, LR")
    if errors:
        print("ERROR — parameter validation failed:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

# ============================================================
# BUILD COMMAND
# ============================================================

def build_command():
    cmd = ["java", "-jar", MIST_JAR]

    cmd += ["--filenamePattern",     FILENAME_PATTERN]
    cmd += ["--filenamePatternType", FILENAME_PATTERN_TYPE]
    cmd += ["--gridHeight",          str(GRID_HEIGHT)]
    cmd += ["--gridWidth",           str(GRID_WIDTH)]
    cmd += ["--gridOrigin",          GRID_ORIGIN]
    cmd += ["--imageDir",            IMAGE_DIR]
    cmd += ["--outputPath",          OUTPUT_DIR]
    cmd += ["--programType",         PROGRAM_TYPE]

    if FILENAME_PATTERN_TYPE == "ROWCOL":
        cmd += ["--startRow", str(START_ROW)]
        cmd += ["--startCol", str(START_COL)]
    elif FILENAME_PATTERN_TYPE == "SEQUENTIAL":
        cmd += ["--numberingPattern", NUMBERING_PATTERN]
        cmd += ["--startTile",        str(START_TILE)]

    if PROGRAM_TYPE == "FFTW":
        cmd += ["--fftwLibraryFilename", FFTW_LIB_FILE]
        cmd += ["--fftwLibraryName",     FFTW_LIB_NAME]
        cmd += ["--fftwLibraryPath",     FFTW_LIB_PATH]

    if OUT_FILE_PREFIX:
        cmd += ["--outFilePrefix", OUT_FILE_PREFIX]
    cmd += ["--blendingMode",     BLENDING_MODE]
    cmd += ["--outputFullImage",  OUTPUT_FULL_IMAGE]
    cmd += ["--displayStitching", "false"]

    if HORIZONTAL_OVERLAP is not None:
        cmd += ["--horizontalOverlap", str(HORIZONTAL_OVERLAP)]
    if VERTICAL_OVERLAP is not None:
        cmd += ["--verticalOverlap", str(VERTICAL_OVERLAP)]
    cmd += ["--overlapUncertainty",         str(OVERLAP_UNCERTAINTY)]
    cmd += ["--numFFTPeaks",                str(NUM_FFT_PEAKS)]
    cmd += ["--translationRefinementMethod", TRANSLATION_REFINEMENT]
    cmd += ["--logLevel",                   LOG_LEVEL]

    return cmd

# ============================================================
# EXECUTE
# ============================================================

def main():
    print("=" * 50)
    print("MIST Tile Stitching Workflow")
    print("=" * 50)

    validate()

    tile_count = len(list(Path(IMAGE_DIR).iterdir()))
    expected   = GRID_WIDTH * GRID_HEIGHT
    print(f"Image directory : {IMAGE_DIR}")
    print(f"Files found     : {tile_count}")
    print(f"Grid            : {GRID_WIDTH} cols x {GRID_HEIGHT} rows = {expected} expected tiles")
    if tile_count < expected:
        print(f"WARNING: fewer files ({tile_count}) than expected ({expected}). "
              "Missing tiles are OK if remaining tiles form a connected graph.")

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {OUTPUT_DIR}")
    print()

    cmd = build_command()
    print("Command:")
    print("  " + " \\\n    ".join(cmd))
    print()
    print("Running MIST...")

    start  = time.time()
    result = subprocess.run(cmd, text=True)
    elapsed = time.time() - start

    print()
    print("=" * 50)
    if result.returncode == 0:
        print(f"MIST completed successfully in {elapsed:.1f} seconds")
        print()
        print(f"Output files in: {OUTPUT_DIR}")
        for f in sorted(Path(OUTPUT_DIR).iterdir()):
            size_kb = f.stat().st_size // 1024
            print(f"  {size_kb:>8} KB  {f.name}")
        print()
        print("Next steps:")
        print(f"  - Open mosaic in Fiji : {OUTPUT_DIR}/{OUT_FILE_PREFIX}stitched-0.tif")
        print(f"  - Check quality stats : {OUTPUT_DIR}/{OUT_FILE_PREFIX}statistics.txt")
        print("  - To re-blend without re-stitching: use 'Assemble from metadata'")
        print("    in MIST GUI, pointing to global-positions-0.txt")
    else:
        print(f"MIST FAILED (exit code {result.returncode}) after {elapsed:.1f} seconds")
        print()
        print("Troubleshooting:")
        print(f"  1. Check log : {OUTPUT_DIR}/{OUT_FILE_PREFIX}log.txt")
        print("  2. Verify FILENAME_PATTERN exactly matches your filenames")
        print("     (case-sensitive on Linux; count digits: {rr}=2-digit, {rrr}=3-digit)")
        print("  3. Verify GRID_WIDTH x GRID_HEIGHT matches your tile count")
        print("  4. If FFTW fails, set PROGRAM_TYPE = 'JAVA'")
        print("  5. For low-content tiles, set HORIZONTAL_OVERLAP and VERTICAL_OVERLAP")
        print("     explicitly (percent from your acquisition software settings)")
        sys.exit(result.returncode)
    print("=" * 50)


if __name__ == "__main__":
    main()

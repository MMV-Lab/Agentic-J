#!/usr/bin/env python3
"""
ImageJ Plugin Community Usage Ranker
=====================================
Ranks ImageJ/Fiji plugins by their mention frequency on forum.image.sc
(the official ImageJ community forum, powered by Discourse).

Optionally also fetches GitHub stars for plugins that have a known repo.

Requirements:
    pip install requests tqdm

HOW TO GET YOUR SESSION COOKIE (free, ~3 minutes):
    1. Log in to https://forum.image.sc in your browser
    2. Open DevTools:  F12  (or right-click → Inspect)
    3. Go to the  Network  tab, then search for anything on the forum
    4. Click any request to forum.image.sc, scroll to  Request Headers
    5. Find the  Cookie  header — copy its entire value (long string)
    6. Paste it into FORUM_COOKIE below

    TIP (Chrome shortcut):
    - Go to Application tab → Cookies → https://forum.image.sc
    - Copy the value of the "_t" cookie — that is usually enough on its own

Output:
    - plugin_rankings.csv   : Full ranked results
    - top50_plugins.csv     : Top 50 only
"""

import requests
import time
import csv
import sys
from tqdm import tqdm

# ─────────────────────────────────────────────
# CONFIGURATION  ← fill these in!
# ─────────────────────────────────────────────

FORUM_BASE = "https://forum.image.sc"
# Paste the value of the "_t" cookie from forum.image.sc here.
# (See instructions in the docstring above.)
FORUM_COOKIE = "scAb6se2qP8Q0bsjSczpuz3Q7i6rk0lueKweDbjRpHROKZK9NWYFiUHaaCu5n67NnLq7tnfCRGXpEFmyvhVmB%2FLK6ePsp3QLvDDVTWvuPNC7sGIwqdFwWm8UpBj5vNgv8UjEGbDwvRkwpFF5Tpvc%2BEpYpgvihjfes5%2BN9iGQfeYuCXJW3T%2Byc8lpM35al4QvnnMDRqy9yMWmVpLCRKdMh%2F2cX7Tkle2iYpAXEeJMZaUubTsUwhYbSdxDM5ndk2FvAA1XawF5sUPZ85%2B%2FLcqQorTdhmUDa0RMtmBgKA%3D%3D--cPdKcmGlJXNvnNKb--wbeWhPbmUcxJ%2FYX98AU%2Fjg%3D%3D"   # ← paste cookie value here

# Delay between forum requests (be polite to the server)
REQUEST_DELAY = 2.5

# Optional: GitHub personal access token for higher rate limits
# Get one at: https://github.com/settings/tokens  (no scopes needed)
GITHUB_TOKEN = None

# ─────────────────────────────────────────────
# YOUR 289 PLUGINS
# ─────────────────────────────────────────────

PLUGINS = [
    # ── Core / Well-known ─────────────────────────────────────────────────
    ("StarDist",                            "stardist/stardist"),
    ("MorphoLibJ",                          "ijpb/MorphoLibJ"),
    ("CLIJ2",                               "clij/clij2"),
    ("BioVoxxel Toolbox",                   "biovoxxel/biovoxxel-toolbox"),
    ("BigStitcher",                         "PreibischLab/BigStitcher"),
    ("BoneJ",                               "bonej-org/bonej"),
    ("Bio-Formats",                         "ome/bioformats"),
    ("Labkit",                              "juglab/labkit-ui"),
    ("LimeSeg",                             "NicoKiaru/LimeSeg"),
    ("SNT",                                 "morphonets/SNT"),
    ("FeatureJ",                            None),
    ("CSBDeep",                             "CSBDeep/CSBDeep_fiji"),
    ("N2V",                                 "juglab/N2V_fiji"),
    ("TurboReg",                            None),
    ("StackReg",                            None),
    ("bUnwarpJ",                            "fiji/bUnwarpJ"),
    ("ClearVolume",                         "ClearVolume/clearvolume"),
    ("SciView",                             "scenerygraphics/sciview"),
    ("OMERO Insight",                       "ome/omero-insight"),
    ("N5 Viewer",                           "saalfeldlab/n5-viewer"),
    ("Rolling Ball Background Subtraction", None),
    ("Auto Local Threshold",                None),
    ("Auto Threshold",                      None),
    ("OrientationJ",                        None),
    ("Shape Filter",                        None),
    ("Measure Stack",                       None),
    ("CLIJ Assistant",                      "clij/assistant"),
    ("Colocalization Threshold",            None),
    ("CellCounter",                         None),
    ("Watershed Irregular Features",        None),
    ("Manual Tracking",                     None),
    ("IJ-OpenCV",                           "joheras/IJ-OpenCV"),
    ("Results to Excel",                    "antinos/Results_to_Excel"),
    ("Sholl Analysis",                      "morphonets/SNT"),
    ("CLAHE",                               None),
    ("Classic Watershed",                   "fiji/fiji"),
    ("Distance Transform Watershed",        "ijpb/MorphoLibJ"),
    ("FilamentDetector",                    "hadim/FilamentDetector"),
    ("FLIMJ",                               "flimlib/flimj-ui"),
    ("Kappa",                               "fiji/Kappa"),
    ("MaMuT",                               "trackmate-sc/MaMuT"),
    ("MoBIE",                               "mobie/mobie-viewer-fiji"),
    ("Multi-Template Matching",             "multi-template-matching/MultiTemplateMatching-Fiji"),
    ("NeuronJ",                             None),
    ("Time Stamper",                        None),
    ("TransformJ",                          None),
    ("DiameterJ",                           None),
    ("SIMcheck",                            "MicronOxford/SIMcheck"),
    ("TAPAS",                               "mcib3d/tapas-core"),
    ("Marker-controlled Watershed",         "ijpb/MorphoLibJ"),
    ("Interactive Marker-controlled Watershed", "ijpb/MorphoLibJ"),
    ("RATS",                                None),
    ("CiliaQ",                              "hansenjn/CiliaQ"),
    ("SpermQ",                              "hansenjn/SpermQ"),
    ("CARE",                                "CSBDeep/CSBDeep_fiji"),
    ("DenoiSeg",                            "juglab/DenoiSeg_fiji"),
    ("ilastik",                             "ilastik/ilastik4ij"),
    ("DeepImageJ",                          "deepimagej/deepimagej-plugin"),
    ("SAMJ",                                "segment-anything-models-java/SAMJ-IJ"),
    ("Mastodon",                            "mastodon-sc/mastodon"),
    ("JIPipe",                              "applied-systems-biology/JIPipe"),
    ("GDSC SMLM2",                          "aherbert/gdsc-smlm"),
    ("NanoJ-SRRF",                          "HenriquesLab/NanoJ-SRRF"),
    ("NanoJ-Core",                          "HenriquesLab/NanoJ-Core"),
    ("NanoJ-SQUIRREL",                      "HenriquesLab/NanoJ-SQUIRREL"),
    ("Mastodon-DeepLineage",                "mastodon-sc/mastodon-deep-lineage"),
    ("TrackMate-StarDist",                  "trackmate-sc/TrackMate-StarDist"),
    ("TrackMate-Cellpose",                  "trackmate-sc/TrackMate-Cellpose"),
    ("TrackMate-Weka",                      "trackmate-sc/TrackMate-Weka"),
    ("TrackMate-Ilastik",                   "trackmate-sc/TrackMate-Ilastik"),
    ("TrackMate-MorphoLibJ",                "trackmate-sc/TrackMate-MorphoLibJ"),
    ("TrackMate-ExTrack",                   "trackmate-sc/TrackMate-ExTrack"),
    ("TrackMate-YOLO",                      "trackmate-sc/TrackMate-YOLO"),
    ("TrackMate-Spotiflow",                 "trackmate-sc/TrackMate-Spotiflow"),
    ("TrackMate-Lacss",                     "jiyuuchc/lacss"),
    ("TrackMate-Trackastra",                "trackmate-sc/TrackMate-Trackastra"),
    ("TrackMate-Helper",                    "trackmate-sc/TrackMate-CTCRunner"),
    ("TrackMate-GEFF",                      "trackmate-sc/TrackMate-Geff"),
    ("TrackMate-InTRACKtive",               "trackmate-sc/TrackMate-InTRACKtive"),
    ("TrackMate-Kymograph",                 None),
    ("TrackMate-Oneat",                     "trackmate-sc/TrackMate-Oneat"),
    ("TrackMate-Pairing",                   None),
    ("TrackMateCSVImporter",                "trackmate-sc/TrackMate-CSVImporter"),
    ("ELEPHANT",                            "elephant-track/elephant-client"),
    ("ElastixWrapper",                      "embl-cba/elastix-wrapper"),
    ("MOSAIC ToolSuite",                    None),
    ("Colocalization by Cross Correlation", "SnowySpider/Colocalization_by_Cross_Correlation"),
    ("GDSC",                                "aherbert/gdsc"),
    ("clijx-assistant",                     "clij/clijx-assistant"),
    ("apoc",                                "haesleinhuepf/apoc"),
    ("BaSiC",                               "marrlab/BaSiC"),
    ("ModularImageAnalysis (MIA)",          "mianalysis/mia"),
    ("Tissue Analyzer",                     None),
    ("PTBIOP",                              "BIOP/ijp-kheops"),
    ("Zeiss Quick Start Reader",            None),
    ("MIST",                                "usnistgov/MIST"),
    ("NucleusJ",                            "PouletAxel/NucleusJ_"),
    ("MiToBo",                              "mitobo-hub/mitobo"),
    ("BigDataProcessor",                    "bigdataprocessor/bigDataProcessor2"),
    ("Morphology (Landini)",                None),
    ("CMTK Registration",                   None),
    ("Mastodon-Tomancak",                   "mastodon-sc/mastodon-tomancak"),
    ("BACMMAN",                             "jeanollion/bacmman"),
    ("Mars",                                "duderstadt-lab/mars-fx"),
    ("ImagingFCS",                          None),
    ("Ultrack",                             "royerlab/ultrack"),
    ("Multi-Template-Matching",             "multi-template-matching/MultiTemplateMatching-Fiji"),
    ("3D ImageJ Suite",                     None),
    ("3Dscript",                            "bene51/3Dscript"),
    ("4d-Tools",                            None),
    ("ActogramJ",                           None),
    ("AdipoQ",                              "hansenjn/AdipoQ"),
    ("ALPACA",                              None),
    ("AMPT",                                None),
    ("AngioTool",                           "jbendtsen/AngioTool-Batch"),
    ("Animove",                             None),
    ("Archipelago",                         None),
    ("AxoNet",                              None),
    ("BACMMAN-DL",                          "jeanollion/bacmman"),
    ("BACMMAN-DL-GPU",                      "jeanollion/bacmman"),
    ("BAR",                                 "tferr/Scripts"),
    ("Batch Tools",                         None),
    ("BD-CellView",                         None),
    ("BigVolumeBrowser",                    None),
    ("BigVolumeViewer Demo",                None),
    ("Biomat",                              None),
    ("BioVoxxel 3D Box",                    "biovoxxel/bv3dbox"),
    ("BioVoxxel Figure Tools",              "biovoxxel/biovoxxel-figure-tools"),
    ("Blind Analysis Tools",                None),
    ("BTrack",                              "kapoorlab/BTrack"),
    ("CALM",                                None),
    ("CAMDU",                               None),
    ("CATS",                                None),
    ("CellTrackingChallenge",               None),
    ("CIP",                                 None),
    ("CircleSkinner",                       None),
    ("clijx-assistant-extensions",          "clij/clijx-assistant-imagej"),
    ("clijx-deconvolution",                 "clij/clij2-fft"),
    ("CMCI-EMBL",                           None),
    ("CMP-BIA tools",                       None),
    ("ColonyArea",                          None),
    ("ColorBlindLUTs",                      None),
    ("Colour Deconvolution2",               "fiji/Colour_Deconvolution"),
    ("Cookbook",                            None),
    ("CSIM Laboratory",                     None),
    ("DeepClas4Bio-plugins",                None),
    ("Dendrite Dynamics Tracker",           None),
    ("DHM Utilities",                       None),
    ("DHPSFU",                              None),
    ("DiversePathsJ",                       None),
    ("DNA FISH",                            None),
    ("Dorsal Horn Mapping",                 None),
    ("Draw 3D ROI",                         None),
    ("EasyFiji",                            None),
    ("EM Tool",                             None),
    ("EpiGraph",                            "ComplexOrganizationOfLivingMatter/Epigraph"),
    ("EVAnalyzer",                          "joda01/evanalyzer"),
    ("Excel Functions",                     None),
    ("EZFig",                               None),
    ("FAST",                                None),
    ("FAST-HIPPOS",                         None),
    ("Fast4DReg",                           "guijacquemet/Fast4DReg"),
    ("FFMPEG",                              None),
    ("FFmpegVideoImportExport",             None),
    ("FibrilJ",                             None),
    ("FiloQuant",                           "CellMigrationLab/FiloQuant"),
    ("Foci Analyzer",                       None),
    ("FOCUST",                              None),
    ("FPBioimage",                          "fpbioimage/FPBioimageHelper-FIJI"),
    ("FracLac Suite",                       None),
    ("FRAP-Tools",                          None),
    ("FreQ",                                None),
    ("FunImageJ",                           "funimage/funimage"),
    ("Fuzzy logic and artificial neural networks image processing toolbox for ImageJ", None),
    ("Fuzzy Set",                           None),
    ("Gamma_LUT_Toggle",                    None),
    ("Gut Analysis Toolbox",                "pr4deepr/GutAnalysisToolbox"),
    ("HDF5",                                "scifio/scifio-hdf5"),
    ("HPC-Datastore",                       None),
    ("HPC-ParallelTools",                   None),
    ("IamMM",                               None),
    ("IJ-Plugins",                          "ij-plugins/ijp-toolkit"),
    ("IJMMD",                               None),
    ("Image Viewer",                        None),
    ("ImageJ Latex",                        None),
    ("ImageJ-ITK",                          "imagej/imagej-itk"),
    ("ImageJ-MATLAB",                       "imagej/imagej-matlab"),
    ("IMCF Uni Basel",                      "imcf/imcf-fiji-scripts"),
    ("ImgLib2-Imaris-Bridge",               None),
    ("IMOD-ZOLA",                           None),
    ("Intensity Profile tools",             None),
    ("IsletJ",                              None),
    ("JavaCVInstaller",                     None),
    ("JOGL Canvas Deep Color / 3D",         None),
    ("KTZ-LUTs",                            None),
    ("Lab-utility-plugins",                 "Macklin-Lab/imagej-microscopy-scripts"),
    ("Leiden University",                   None),
    ("Lineage-Mapper",                      "usnistgov/Lineage-Mapper"),
    ("Live-Kymographer",                    None),
    ("LLTT",                                None),
    ("LMCF-IMG",                            None),
    ("Local Z Projector",                   None),
    ("LSM-W2",                              None),
    ("LUMoS",                               None),
    ("LysoQuant",                           None),
    ("Mars-Latest",                         "duderstadt-lab/mars-fx"),
    ("Maskflow",                            None),
    ("Masks from ROIs",                     None),
    ("Mastodon-Benchmark",                  None),
    ("Mcat",                                None),
    ("MiC mask comparator",                 None),
    ("MIC-MAQ",                             None),
    ("Micro-Magellan",                      "micro-manager/micro-manager"),
    ("Microglia-Morphometry",               None),
    ("Mighty Data, Inc.",                   None),
    ("MoMA",                                "fjug/MoMA"),
    ("MotiQ",                               "hansenjn/MotiQ"),
    ("MS-ECS-2D",                           None),
    ("MTrack",                              None),
    ("Multifrac",                           None),
    ("MultiStackReg",                       None),
    ("NanoJ-VirusMapper",                   "HenriquesLab/NanoJ-Core"),
    ("NeuroCyto LUTs",                      None),
    ("NoiSee",                              "imcf/noisee"),
    ("Nscale-segmentation",                 None),
    ("OpenMIMS",                            "BWHCNI/OpenMIMS"),
    ("OPTIMISME",                           None),
    ("Oxford Oncology",                     None),
    ("ParticleSizer",                       "thorstenwagner/ij-particlesizer"),
    ("Pendent Drop",                        None),
    ("PET-CT",                              None),
    ("PHANTAST",                            None),
    ("PhotoBend",                           None),
    ("PhotonImaging",                       None),
    ("PillarTracker",                       None),
    ("PixFRET",                             None),
    ("PlateViewer",                         None),
    ("PQCT",                                None),
    ("Puncta Process",                      None),
    ("Qualitative Annotations",             None),
    ("QuickFigures",                        "grishkam/QuickFigures"),
    ("QuimP",                               "CellDynamics/QuimP"),
    ("Radial Symmetry",                     "PreibischLab/RadialSymmetryLocalization"),
    ("RadialIntensityProfile",              None),
    ("ReadPlate",                           None),
    ("ROI 1-click Tools",                   "LauLauThom/Fiji-RoiClickTools"),
    ("ROI-group Table",                     None),
    ("RT-Multiview-Deconvolution",          None),
    ("Sceptical Physiologist",              None),
    ("ScientiFig",                          None),
    ("Scijava Jupyter Kernel",              "scijava/scijava-jupyter-kernel"),
    ("SciJava Ops",                         "scijava/scijava"),
    ("sciview",                             "scenerygraphics/sciview"),
    ("SimonKlein",                          None),
    ("SiMView",                             None),
    ("SIMworks",                            None),
    ("Slide Set",                           None),
    ("SlideBook",                           None),
    ("SLIM Curve",                          "flimlib/slim-curve"),
    ("SLIM-Notts",                          None),
    ("Spindle3D",                           None),
    ("Stereoscopic 3D Projection",          None),
    ("Stowers",                             None),
    ("Tango",                               None),
    ("TEM suite",                           None),
    ("TensorFlow",                          "tensorflow/tensorflow"),
    ("Timebar",                             None),
    ("Tr2d",                                "fjug/tr2d"),
    ("TraJClassifier",                      "thorstenwagner/ij-trajectory-classifier"),
    ("TreeJ",                               None),
    ("TWOMBLI",                             "wershofe/TWOMBLI"),
    ("U-Net Segmentation",                  None),
    ("UCB Vision Sciences",                 None),
    ("Vale lab plugins",                    None),
    ("VCell Simulation Results Viewer",     None),
    ("VerciniAnalysisJ",                    None),
    ("VersiLab plugins",                    None),
    ("Virtual-Orientation-Tools-VOTj",      None),
    ("Visualization Toolset",               None),
    ("Void Whizzard",                       None),
    ("Volumetric Tissue Exploration and Analysis", None),
    ("WhiskerTracking",                     None),
    ("WormBox",                             None),
    ("WormSizer",                           None),
    ("XitoSBML",                            "spatialsimulator/XitoSBML"),
    ("Xlib",                                None),
    ("ZedMate Suite",                       None),
    ("Zellige",                             None),
    ("ZFBONE",                              None),
    ("Zoom-in-movie",                       None),
    ("TrackMate",                           "trackmate-sc/TrackMate"),
]

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def parse_plugin(entry):
    """Normalize plugin entry to (name, github_repo_or_None)."""
    if isinstance(entry, tuple):
        return entry[0], entry[1] if len(entry) > 1 else None
    return entry, None


def make_session() -> requests.Session:
    """Create a requests session that mimics a real browser login."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://forum.image.sc/",
        "X-Requested-With": "XMLHttpRequest",
    })
    # Inject the _t session cookie from your browser
    session.cookies.set("_t", FORUM_COOKIE, domain="forum.image.sc")
    return session


def forum_mention_count(plugin_name: str, session: requests.Session, retries: int = 3) -> dict:
    """
    Search forum.image.sc for a plugin name and return hit counts.
    Authenticated via the browser session cookie to avoid 403 errors.
    """
    url = f"{FORUM_BASE}/search.json"
    params = {"q": f'"{plugin_name}"', "page": 1}
    for attempt in range(retries):
        try:
            r = session.get(url, params=params, timeout=20)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 60))
                print(f"\n  [rate limit] Waiting {wait}s before retrying '{plugin_name}'...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            data = r.json()
            grouped     = data.get("grouped_search_result", {})
            topic_count = grouped.get("topic_count", len(data.get("topics", [])))
            post_count  = grouped.get("post_count",  len(data.get("posts",  [])))
            return {"forum_topics": topic_count, "forum_posts": post_count}
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
            else:
                print(f"\n  [!] Forum error for '{plugin_name}': {e}")
    return {"forum_topics": 0, "forum_posts": 0}


def github_stars(repo: str) -> int:
    """
    Fetch GitHub star count by scraping github.com directly.
    Avoids api.github.com which returns 403 without a token.
    """
    import re
    if not repo:
        return 0
    url = "https://github.com/" + repo
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 404:
            print("  [!] GitHub 404 for: " + repo)
            return 0
        r.raise_for_status()
        # Star count is in a span with id="repo-stars-counter-star" and title="NNN"
        m = re.search(r'id="repo-stars-counter-star"[^>]*title="([0-9,]+)"', r.text)
        if not m:
            m = re.search(r'title="([0-9,]+)"[^>]*id="repo-stars-counter-star"', r.text)
        if m:
            return int(m.group(1).replace(",", ""))
        return 0
    except Exception as e:
        print("  [!] GitHub error for " + repo + ": " + str(e))
        return 0


def compute_score(row: dict) -> float:
    """
    Composite score combining forum activity and GitHub stars.
      forum_topics : 3 pts each  (topics are stronger signal)
      forum_posts  : 1 pt each
      github_stars : 0.5 pts each (GitHub != usage, just interest)
    """
    return (row["forum_topics"] * 3 +
            row["forum_posts"]  * 1 +
            row["github_stars"] * 0.5)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    if FORUM_COOKIE == "YOUR_SESSION_COOKIE_HERE":
        print("\n❌  ERROR: Please set FORUM_COOKIE at the top of the script.")
        print("   See the docstring for instructions on getting your session cookie.\n")
        sys.exit(1)

    session = make_session()

    print(f"\n{'='*55}")
    print("  ImageJ Plugin Community Usage Ranker")
    print(f"  Scanning {len(PLUGINS)} plugins ...")
    print(f"{'='*55}\n")

    results = []

    for entry in tqdm(PLUGINS, unit="plugin"):
        name, repo = parse_plugin(entry)

        forum = forum_mention_count(name, session)
        time.sleep(REQUEST_DELAY)

        stars = 0
        if repo:
            stars = github_stars(repo)
            time.sleep(0.5)

        row = {
            "plugin":       name,
            "github_repo":  repo or "",
            "forum_topics": forum["forum_topics"],
            "forum_posts":  forum["forum_posts"],
            "github_stars": stars,
        }
        row["score"] = compute_score(row)
        results.append(row)

    results.sort(key=lambda x: x["score"], reverse=True)
    for i, row in enumerate(results, 1):
        row["rank"] = i

    fieldnames = ["rank", "plugin", "score", "forum_topics",
                  "forum_posts", "github_stars", "github_repo"]

    with open("plugin_rankings.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    top50 = results[:50]
    with open("top50_plugins.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(top50)

    print(f"\n{chr(9472)*70}")
    print(f"  {'Rank':<5} {'Plugin':<35} {'Topics':>7} {'Posts':>7} {'Stars':>7}")
    print(f"{chr(9472)*70}")
    for row in top50:
        print(f"  {row['rank']:<5} {row['plugin']:<35} "
              f"{row['forum_topics']:>7} {row['forum_posts']:>7} "
              f"{row['github_stars']:>7}")
    print(f"{chr(9472)*70}")
    print(f"\n✓ Full results  → plugin_rankings.csv")
    print(f"✓ Top 50        → top50_plugins.csv\n")


if __name__ == "__main__":
    main()
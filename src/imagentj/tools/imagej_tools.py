import json
from langchain.tools import tool
from imagentj.imagej_context import get_ij
from .metadata_tools import extract_file_metadata


@tool
def ask_user(prompt: str) -> str:
    """
    Ask the user a question and return their input.
    Always ask in a way that a biologists without programming experience can understand.
    """
    return input(f"🖐 USER INPUT REQUIRED: {prompt}\n> ")


@tool
def load_image_ij(path: str)  -> object:
    """Load an image from a given path using ImageJ.

    Args:
        path (str): The file path to the image.

    Returns:
        [].
    """

    global image

    ij = get_ij()

    image = ij.io().open(path)
    return "Loaded image from " + path


@tool
def inspect_all_ui_windows():
    """
    Inspected everything visible in the ImageJ UI:
    1. Image Windows (Metadata & Stats)
    2. Results Tables (Row/Column counts)
    3. The Log window and ROI Manager
    """
    ij = get_ij()

    # Correct way to import Java classes in PyImageJ
    from scyjava import jimport
    WindowManager = jimport('ij.WindowManager')
    ResultsTable = jimport('ij.measure.ResultsTable')
    RoiManager = jimport('ij.plugin.frame.RoiManager')
    Frame = jimport('java.awt.Frame')

    all_inspections = {
        "images": [],
        "tables_and_text": []
    }

    # --- 1. Inspect Image Windows ---
    image_ids = WindowManager.getIDList()
    if image_ids:
        for img_id in image_ids:
            imp = WindowManager.getImage(img_id)
            try:
                # Convert ImagePlus to Dataset for stats
                dataset = ij.py.to_dataset(imp)

                min_val = ij.op().stats().min(dataset).getRealDouble()
                max_val = ij.op().stats().max(dataset).getRealDouble()

                all_inspections["images"].append({
                    "title": imp.getTitle(),
                    "dimensions": f"{imp.getWidth()}x{imp.getHeight()}x{imp.getNSlices()}",
                    "stats": {"min": min_val, "max": max_val},
                    "bit_depth": imp.getBitDepth()
                })
            except Exception as e:
                all_inspections["images"].append({"title": imp.getTitle(), "error": str(e)})

    # --- 2. Inspect Non-Image Windows ---
    all_frames = Frame.getFrames()
    for frame in all_frames:
        if frame.isVisible():
            title = frame.getTitle()

            if title == "Results":
                rt = ResultsTable.getResultsTable()
                all_inspections["tables_and_text"].append({
                    "type": "Results Table",
                    "rows": rt.size(),
                    "columns": rt.getLastColumn() + 1
                })
            elif title == "ROI Manager":
                rm = RoiManager.getInstance()
                all_inspections["tables_and_text"].append({
                    "type": "ROI Manager",
                    "roi_count": rm.getCount() if rm else 0
                })
            elif title == "Log":
                all_inspections["tables_and_text"].append({
                    "type": "Log Window",
                    "status": "Visible"
                })

    return str(all_inspections)


@tool
def extract_image_metadata(path: str) -> str:
    """Extract calibration, pixel intensity statistics, and suggested
    threshold/filter parameters from an image file.

    Returns a JSON string with pixel scale, intensity stats, recommended
    threshold values, filter sizes, and noise estimates.  Does NOT require
    an active ImageJ dataset — reads the file directly.

    Args:
        path: Absolute file path to the image.
    """

    result = extract_file_metadata(path)
    return json.dumps(result, indent=2, default=str)

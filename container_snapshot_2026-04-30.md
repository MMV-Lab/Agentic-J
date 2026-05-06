# Container Snapshot — 2026-04-30

## System / runtime

| Component | Version / detail |
|-----------|-----------------|
| **Java** | OpenJDK 21.0.10-internal (conda-forge build, mixed mode) |
| **JAVA\_HOME** | `/opt/conda/envs/local_imagent_J` |
| **ImageJ 1.x** | 1.54p (2025-02-18) |
| **Fiji / imagej2** | 2.17.1-SNAPSHOT (fiji jar), imagej2 2.16.0 |
| **Groovy** | 4.0.23 (in Fiji jars) |
| **conda** | 26.1.1 |
| **CUDA** | None (CPU-only container) |
| **Xvfb** | 2:21.1.16 |
| **x11vnc** | 0.9.17 |
| **noVNC** | 1.6.0 |
| **websockify** | 0.12.0 |
| **fluxbox** | 1.3.7 |
| **Mesa / OpenGL** | 25.0.7 |
| **wget** | 1.25.0 |
| **curl** | 8.14.1 |

## Python environments


### Main conda env (`local_imagent_J`) — Python 3.13.13

| Package | Version |
|---------|---------|
| accelerate | 1.13.0 |
| aiofiles | 24.1.0 |
| aiohappyeyeballs | 2.6.1 |
| aiohttp | 3.13.5 |
| aiohttp-retry | 2.9.1 |
| aiosignal | 1.4.0 |
| aiosqlite | 0.22.1 |
| annotated-types | 0.7.0 |
| anthropic | 0.97.0 |
| antlr4-python3-runtime | 4.9.3 |
| anyio | 4.12.1 |
| attrs | 26.1.0 |
| beautifulsoup4 | 4.14.3 |
| certifi | 2026.2.25 |
| cffi | 2.0.0 |
| charset-normalizer | 3.4.4 |
| cjdk | 0.5.0 |
| click | 8.3.3 |
| colorlog | 6.10.1 |
| contourpy | 1.3.3 |
| cryptography | 47.0.0 |
| cuda-toolkit | 13.0.2 |
| cycler | 0.12.1 |
| dataclasses-json | 0.6.7 |
| ddgs | 9.14.1 |
| deepagents | 0.5.3 |
| docling | 2.91.0 |
| docling-core | 2.74.1 |
| docling-ibm-models | 3.13.2 |
| docling-parse | 5.10.1 |
| environs | 14.6.0 |
| fastembed | 0.8.0 |
| filelock | 3.29.0 |
| fonttools | 4.62.1 |
| frozenlist | 1.7.0 |
| fsspec | 2026.3.0 |
| google-genai | 1.73.1 |
| grpcio | 1.80.0 |
| httpx | 0.28.1 |
| huggingface_hub | 1.12.0 |
| imagecodecs | 2026.3.6 |
| imagentj | 0.1.0 |
| imglyb | 2.1.0 |
| ipykernel | 7.2.0 |
| ipython | 9.13.0 |
| jpype1 | 1.6.0 |
| langchain | 1.2.15 |
| langchain-anthropic | 1.4.1 |
| langchain-community | 0.4.1 |
| langchain-core | 1.2.16 |
| langchain-docling | 2.0.0 |
| langchain-google-genai | 4.2.2 |
| langchain-openai | 1.2.1 |
| langchain-qdrant | 1.1.0 |
| langchain-text-splitters | 1.1.2 |
| langgraph | 1.1.10 |
| langgraph-checkpoint | 4.0.0 |
| langgraph-checkpoint-sqlite | 3.0.3 |
| langgraph-prebuilt | 1.0.12 |
| langgraph-sdk | 0.3.13 |
| langsmith | 0.7.7 |
| matplotlib | 3.10.9 |
| mpmath | 1.3.0 |
| networkx | 3.6.1 |
| numpy | 2.4.3 |
| nvidia-cudnn-cu13 | 9.19.0.56 |
| openai | 2.32.0 |
| opencv-python | 4.13.0.92 |
| openpyxl | 3.1.5 |
| packaging | 26.0 |
| pandas | 3.0.2 |
| pillow | 12.2.0 |
| pip | 26.0.1 |
| protobuf | 6.33.6 |
| psutil | 7.2.2 |
| pydantic | 2.12.5 |
| pydicom | 3.0.2 |
| pyimagej | 1.7.0 |
| PyMuPDF | 1.27.2.3 |
| pymupdf4llm | 0.1.9 |
| PySide6 | 6.11.0 |
| python-dateutil | 2.9.0.post0 |
| PyYAML | 6.0.3 |
| qdrant-client | 1.17.1 |
| rank-bm25 | 0.2.2 |
| readlif | 0.6.6 |
| regex | 2026.4.4 |
| requests | 2.32.5 |
| rich | 15.0.0 |
| safetensors | 0.7.0 |
| scipy | 1.17.1 |
| scyjava | 1.12.1 |
| seaborn | 0.13.2 |
| setuptools | 81.0.0 |
| shapely | 2.1.2 |
| six | 1.17.0 |
| SQLAlchemy | 2.0.49 |
| statsmodels | 0.14.6 |
| tifffile | 2026.4.11 |
| tiktoken | 0.12.0 |
| tokenizers | 0.22.2 |
| torch | 2.11.0 |
| torchvision | 0.26.0 |
| tqdm | 4.67.3 |
| transformers | 5.6.2 |
| urllib3 | 2.6.3 |
| xarray | 2026.4.0 |
| zstandard | 0.25.0 |

### conda env `stardist` — Python 3.11.15

| Package | Version |
|---------|---------|
| stardist | 0.9.2 |
| csbdeep | 0.8.2 |
| tensorflow-cpu | 2.15.1 |
| tensorflow-estimator | 2.15.0 |
| keras | 2.15.0 |
| numpy | 1.26.4 |
| scipy | 1.17.1 |
| scikit-image | 0.26.0 |
| tifffile | 2026.3.3 |
| matplotlib | 3.10.9 |
| pillow | 12.2.0 |
| ImageIO | 2.37.3 |
| h5py | 3.16.0 |
| numba | 0.65.1 |
| llvmlite | 0.47.0 |
| tensorboard | 2.15.2 |
| protobuf | 4.25.9 |
| grpcio | 1.80.0 |
| langchain-core | 1.2.16 |
| langgraph-checkpoint-sqlite | 3.0.3 |
| pydantic | 2.12.5 |
| requests | 2.32.5 |
| tqdm | 4.67.3 |

---

### conda env `cellpose4` — Python 3.11.15

| Package | Version |
|---------|---------|
| cellpose | 4.1.1 |
| segment-anything | 1.0 |
| torch | 2.11.0+cpu |
| torchvision | 0.26.0+cpu |
| numpy | 2.4.3 |
| scipy | 1.17.1 |
| scikit-image | (via imagecodecs) |
| imagecodecs | 2026.3.6 |
| tifffile | 2026.3.3 |
| pillow | 12.1.1 |
| opencv-python-headless | 4.13.0.92 |
| fastremap | 1.18.0 |
| fill_voids | 2.1.1 |
| roifile | 2026.2.10 |
| natsort | 8.4.0 |
| PyQt6 | 6.11.0 |
| pyqtgraph | 0.14.0 |
| superqt | 0.8.1 |
| langchain-core | 1.2.16 |
| langgraph-checkpoint-sqlite | 3.0.3 |
| pydantic | 2.12.5 |
| sympy | 1.14.0 |
| networkx | 3.6.1 |
| tqdm | 4.67.3 |

---

### conda env `cellpose` — Python 3.10.20

| Package | Version |
|---------|---------|
| cellpose | 3.1.1.2 |
| omnipose | 1.1.4 |
| torch | 2.11.0+cpu |
| torchvision | 0.26.0+cpu |
| numpy | 2.0.2 |
| scipy | 1.15.3 |
| scikit-image | 0.25.2 |
| scikit-learn | 1.7.2 |
| imagecodecs | 2025.3.30 |
| tifffile | 2023.2.28 |
| pillow | 12.1.1 |
| opencv-python-headless | 4.13.0.92 |
| fastremap | 1.18.0 |
| fill_voids | 2.1.1 |
| roifile | 2025.12.12 |
| natsort | 8.4.0 |
| numba | 0.65.1 |
| llvmlite | 0.47.0 |
| dask | 2026.3.0 |
| dask-image | 2025.11.0 |
| aicsimageio | 4.14.0 |
| ome-zarr | 0.11.1 |
| zarr | 2.15.0 |
| mahotas | 1.4.18 |
| networkit | 11.2.1 |
| pandas | 2.3.3 |
| matplotlib | 3.10.9 |
| PyQt6 | 6.11.0 |
| pyqtgraph | 0.14.0 |
| superqt | 0.8.1 |
| langchain-core | 1.2.16 |
| langgraph-checkpoint-sqlite | 3.0.3 |
| pydantic | 2.12.5 |
| ipython | 8.39.0 |
| tqdm | 4.67.3 |

### Appose / DeepImageJ env — Python 3.10 (`~/.local/lib/python3.10`)

| Package | Version |
|---------|---------|
| ImageIO | 2.37.3 |
| PIMS | 0.7 |
| aicsimageio | 4.14.0 |
| aiobotocore | 2.5.4 |
| aiohttp | 3.13.5 |
| aioitertools | 0.13.0 |
| aiosignal | 1.4.0 |
| asciitree | 0.3.3 |
| async-timeout | 5.0.1 |
| attrs | 26.1.0 |
| botocore | 1.31.17 |
| click | 8.3.3 |
| cloudpickle | 3.1.2 |
| cmap | 0.7.2 |
| colour-science | 0.4.6 |
| contourpy | 1.3.2 |
| cycler | 0.12.1 |
| dask | 2026.3.0 |
| dask-image | 2025.11.0 |
| dbscan | 1.0.0 |
| decorator | 5.2.1 |
| edt | 3.1.1 |
| exceptiongroup | 1.3.1 |
| fasteners | 0.20 |
| fonttools | 4.62.1 |
| frozenlist | 1.8.0 |
| fsspec | 2023.6.0 |
| ipython | 8.39.0 |
| ipywidgets | 8.1.8 |
| joblib | 1.5.3 |
| lazy-loader | 0.5 |
| lxml | 4.9.4 |
| mahotas | 1.4.18 |
| matplotlib | 3.10.9 |
| mgen | 1.2.1 |
| ncolor | 1.5.3 |
| networkit | 11.2.1 |
| numcodecs | 0.13.1 |
| numexpr | 2.14.1 |
| ome-types | 0.6.3 |
| ome-zarr | 0.11.1 |
| omnipose | 1.1.4 |
| pandas | 2.3.3 |
| partd | 1.4.2 |
| pyarrow | 24.0.0 |
| pydantic-extra-types | 2.11.1 |
| pyinstrument | 5.1.2 |
| pyparsing | 3.3.2 |
| python-dateutil | 2.9.0.post0 |
| pytorch-ranger | 0.1.1 |
| s3fs | 2023.6.0 |
| scikit-image | 0.25.2 |
| scikit-learn | 1.7.2 |
| six | 1.17.0 |
| tabulate | 0.10.0 |
| threadpoolctl | 3.6.0 |
| tifffile | 2023.2.28 |
| toolz | 1.1.0 |
| torch-optimizer | 0.3.0 |
| torchvf | 0.1.4 |
| traitlets | 5.14.3 |
| xarray | 2025.6.1 |
| xmlschema | 4.3.1 |
| xsdata | 26.2 |
| yarl | 1.23.0 |
| zarr | 2.15.0 |

---

## Fiji plugins (`/opt/Fiji.app/plugins/`)

| JAR | Version |
|-----|---------|
| 3D_Blob_Segmentation | 4.0.0 |
| 3D_Objects_Counter | 2.0.1 |
| 3D_Viewer | 5.0.1 |
| AnalyzeSkeleton | 3.4.2 |
| Anisotropic_Diffusion_2D | 2.0.1 |
| Archipelago_Plugins | 0.5.4 |
| Arrow_ | 2.0.2 |
| Auto_Local_Threshold | 1.11.0 |
| Auto_Threshold | 1.18.0 |
| BalloonSegmentation_ | 3.0.1 |
| Big_Stitcher | 2.6.1 |
| Biovoxxel_Plugins | 2.6.3 |
| Cell_Counter | 3.0.0 |
| Colocalisation_Analysis | 3.1.0 |
| Colour_Deconvolution | 3.0.3 |
| CorrectBleach_ | 2.1.0 |
| DeepImageJ | 3.1.0-SNAPSHOT |
| Descriptor_based_registration | 2.1.8 |
| Directionality_ | 2.3.0 |
| Extended_Depth_Field | 2.0.1 |
| Fiji_Plugins | 3.2.0 |
| FlowJ_ | 2.0.1 |
| Graph_Cut | 1.0.2 |
| HDF5_Vibez | 1.1.1 |
| IO_ | 4.3.0 |
| LSM_Reader | 4.1.2 |
| LocalThickness_ | 5.0.0 |
| Manual_Tracking | 2.1.1 |
| MorphoLibJ_ | 1.6.5 |
| OrientationJ_ | 2.0.7 |
| RATS_ | 2.0.2 |
| SNT | 5.0.8-SNAPSHOT |
| Siox_Segmentation | 1.0.5 |
| Skeletonize3D_ | 2.1.1 |
| StackReg_ | 2.0.1 |
| StarDist_ | 0.3.0-scijava / 0.3.0 |
| Statistical_Region_Merging | 2.0.1 |
| Stitching_ | 3.1.9 |
| ToAST_ | 25.0.2 |
| TrackMate | 8.1.6 |
| TrackMate-Cellpose | 1.0.1 |
| TrackMate-Ilastik | 2.0.0 |
| TrackMate-MorphoLibJ | 2.0.0 |
| TrackMate-StarDist | 2.0.0 |
| Trainable_Segmentation (Weka) | 4.0.0 |
| TrakEM2_ | 2.0.0 |
| TurboReg_ | 2.0.1 |
| UnwarpJ_ | 2.0.0 |
| VIB_ | 4.0.0 |
| bigwarp_fiji | 9.3.1 |
| bio-formats_plugins | 8.5.0 |
| bonej-legacy-plugins_ | 7.1.10 |
| bUnwarpJ_ | 2.6.13 |
| bv3dbox | 1.25.1 |
| clij_ | 1.9.0.1 |
| clij2_ | 2.5.3.5 |
| clij2-assistant_ | 2.5.1.6 |
| clijx_ | 0.32.2.0 |
| ij_ridge_detect | 1.4.1 |
| mcib3d_plugins | 4.1.7b |
| mpicbg_ | 1.6.0 |
| multiview_reconstruction | 8.1.2 |
| n5-viewer_fiji | 6.1.2 |
| register_virtual_stack_slices | 3.0.8 |

---

## Key Fiji jars (`/opt/Fiji.app/jars/`)

| JAR | Version |
|-----|---------|
| appose | 0.11.0 |
| bio-formats (formats-api/bsd/gpl) | 8.5.0 |
| csbdeep | 0.6.0 |
| dl-modelrunner | 0.6.2-SNAPSHOT |
| fiji | 2.17.1-SNAPSHOT |
| groovy + modules | 4.0.23 |
| ij (ImageJ 1.x) | 1.54p |
| imagej | 2.16.0 |
| imagej-common | 2.1.1 |
| imagej-legacy | 2.0.3 |
| imagej-modelzoo | 0.9.10 |
| imagej-ops | 2.2.0 |
| imagej-updater | 2.0.3 |
| imglib2 | 7.1.5 |
| imglib2-appose | 0.5.0-ctr |
| javafx (all modules) | 23.0.2 |
| jogl-all | 2.6.0 |
| jython-slim | 2.7.4 |
| labkit-ui | 0.4.0 |
| n5 | 3.5.1 |
| nashorn-core | 15.6 |
| ome-xml | 6.5.3 |
| opencv | 4.9.0-1.5.10 |
| protobuf-java | 3.6.1 |
| scijava-common | 2.100.0 |
| scifio | 0.49.0 |
| scifio-ome-xml | 0.17.1 |
| simpleitk | 2.1.0.dev54 |
| slf4j-api | 2.0.17 |
| slf4j-nop | 2.0.17 |
| sqlite-jdbc | 3.49.1.0 |
| torch (libtensorflow) | 1.12.0 |
| weka-dev | 3.9.6 |

---

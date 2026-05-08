# Container Snapshot — 2026-04-30

## Cellpose aliases

Cellpose-SAM and individual model names are not separate packages — they
ship inside the `cellpose` Python package. Common phrasings ("cellpose sam",
"cellpose-sam", "cellpose 4", "cyto3", …) are embedded in the rows below so
substring search finds them.

| Alias | Where it lives | Notes |
|-------|----------------|-------|
| Cellpose-SAM / cpsam / cellpose sam / cellpose-sam / cellpose 4 SAM | env `cellpose4` (cellpose 4.1.1) | Cellpose 4 ships SAM-based models out of the box. |
| Cellpose 4 / cellpose v4 / cellpose4 | env `cellpose4` (Python 3.11, cellpose 4.1.1) | Use this env for SAM and any v4 model. |
| Cellpose 3 | env `cellpose` (Python 3.10, cellpose 3.1.1.2) | Includes Omnipose. |
| Cellpose models: cyto / cyto2 / cyto3 / nuclei / livecell / tissuenet | bundled with the cellpose package (envs `cellpose` and `cellpose4`) | Weights download to `~/.cellpose` on first use. |
| Omnipose | env `cellpose` (omnipose 1.1.4, with cellpose 3) | Not present in the `cellpose4` env. |

---

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

Generated from `pip list --format=freeze | sed 's/ @ .*//'` on 2026-04-30.

| Package | Version |
|---------|---------|
| accelerate | 1.13.0 |
| aiofiles | 24.1.0 |
| aiohappyeyeballs | 2.6.1 |
| aiohttp | 3.13.5 |
| aiohttp-retry | 2.9.1 |
| aiosignal | 1.4.0 |
| aiosqlite | 0.22.1 |
| annotated-doc | 0.0.4 |
| annotated-types | 0.7.0 |
| anthropic | 0.97.0 |
| antlr4-python3-runtime | 4.9.3 |
| anyio | 4.12.1 |
| asttokens | 3.0.1 |
| async-timeout | 4.0.3 |
| attrs | 26.1.0 |
| backports.zstd | 1.3.0 |
| beautifulsoup4 | 4.14.3 |
| bracex | 2.6 |
| Brotli | 1.2.0 |
| certifi | 2026.2.25 |
| cffi | 2.0.0 |
| charset-normalizer | 3.4.4 |
| cjdk | 0.5.0 |
| click | 8.3.3 |
| colorlog | 6.10.1 |
| comm | 0.2.3 |
| contourpy | 1.3.3 |
| cryptography | 47.0.0 |
| cuda-bindings | 13.2.0 |
| cuda-pathfinder | 1.5.4 |
| cuda-toolkit | 13.0.2 |
| cycler | 0.12.1 |
| dataclasses-json | 0.6.7 |
| daytona | 0.169.0 |
| daytona_api_client | 0.169.0 |
| daytona_api_client_async | 0.169.0 |
| daytona_toolbox_api_client | 0.169.0 |
| daytona_toolbox_api_client_async | 0.169.0 |
| ddgs | 9.14.1 |
| debugpy | 1.8.20 |
| decorator | 5.2.1 |
| deepagents | 0.5.3 |
| defusedxml | 0.7.1 |
| Deprecated | 1.3.1 |
| dill | 0.4.1 |
| distro | 1.9.0 |
| docling | 2.91.0 |
| docling-core | 2.74.1 |
| docling-ibm-models | 3.13.2 |
| docling-parse | 5.10.1 |
| docstring_parser | 0.18.0 |
| environs | 14.6.0 |
| et_xmlfile | 2.0.0 |
| exceptiongroup | 1.3.1 |
| executing | 2.2.1 |
| fake-useragent | 2.2.0 |
| Faker | 40.15.0 |
| fastembed | 0.8.0 |
| filelock | 3.29.0 |
| filetype | 1.2.0 |
| flatbuffers | 25.12.19 |
| fonttools | 4.62.1 |
| frozenlist | 1.7.0 |
| fsspec | 2026.3.0 |
| git-filter-repo | 2.47.0 |
| gitdb | 4.0.12 |
| GitPython | 3.1.48 |
| google-auth | 2.49.2 |
| google-genai | 1.73.1 |
| googleapis-common-protos | 1.74.0 |
| greenlet | 3.5.0 |
| grpcio | 1.80.0 |
| h11 | 0.16.0 |
| h2 | 4.3.0 |
| hf-xet | 1.4.3 |
| hpack | 4.1.0 |
| httpcore | 1.0.9 |
| httpx | 0.28.1 |
| httpx-sse | 0.4.3 |
| huggingface_hub | 1.12.0 |
| hyperframe | 6.1.0 |
| idna | 3.11 |
| imagecodecs | 2026.3.6 |
| imagentj | 0.1.0 |
| imglyb | 2.1.0 |
| importlib_metadata | 8.7.1 |
| ipykernel | 7.2.0 |
| ipython | 9.13.0 |
| ipython_pygments_lexers | 1.1.1 |
| jedi | 0.19.2 |
| jgo | 1.0.6 |
| Jinja2 | 3.1.6 |
| jiter | 0.14.0 |
| jpype1 | 1.6.0 |
| jsonlines | 4.0.0 |
| jsonpatch | 1.33 |
| jsonpointer | 3.0.0 |
| jsonref | 1.1.0 |
| jsonschema | 4.26.0 |
| jsonschema-specifications | 2025.9.1 |
| jupyter_client | 8.8.0 |
| jupyter_core | 5.9.1 |
| kiwisolver | 1.5.0 |
| labeling | 0.1.14 |
| langchain | 1.2.15 |
| langchain-anthropic | 1.4.1 |
| langchain-classic | 1.0.4 |
| langchain-community | 0.4.1 |
| langchain-core | - |
| langchain-docling | 2.0.0 |
| langchain-google-genai | 4.2.2 |
| langchain-openai | 1.2.1 |
| langchain-protocol | 0.0.12 |
| langchain-pymupdf4llm | 0.5.0 |
| langchain-qdrant | 1.1.0 |
| langchain-text-splitters | 1.1.2 |
| langgraph | 1.1.10 |
| langgraph-checkpoint | 4.0.0 |
| langgraph-checkpoint-sqlite | 3.0.3 |
| langgraph-prebuilt | 1.0.12 |
| langgraph-sdk | 0.3.13 |
| langsmith | 0.7.7 |
| lark | 1.3.1 |
| latex2mathml | 3.81.0 |
| loguru | 0.7.3 |
| lxml | 6.1.0 |
| markdown-it-py | 4.0.0 |
| marko | 2.2.2 |
| MarkupSafe | 3.0.3 |
| marshmallow | 3.26.2 |
| matplotlib | 3.10.9 |
| matplotlib-inline | 0.2.1 |
| mdurl | 0.1.2 |
| mistune | 3.2.0 |
| mmh3 | 5.2.1 |
| mpire | 2.10.2 |
| mpmath | 1.3.0 |
| multidict | 6.7.1 |
| multipart | 1.3.1 |
| multiprocess | 0.70.19 |
| munkres | 1.1.4 |
| mypy_extensions | 1.1.0 |
| mysql-connector-python | 9.6.0 |
| nest_asyncio | 1.6.0 |
| networkx | 3.6.1 |
| numpy | 2.4.3 |
| nvidia-cublas | 13.1.0.3 |
| nvidia-cuda-cupti | 13.0.85 |
| nvidia-cuda-nvrtc | 13.0.88 |
| nvidia-cuda-runtime | 13.0.96 |
| nvidia-cudnn-cu13 | 9.19.0.56 |
| nvidia-cufft | 12.0.0.61 |
| nvidia-cufile | 1.15.1.6 |
| nvidia-curand | 10.4.0.35 |
| nvidia-cusolver | 12.0.4.66 |
| nvidia-cusparse | 12.6.3.3 |
| nvidia-cusparselt-cu13 | 0.8.0 |
| nvidia-nccl-cu13 | 2.28.9 |
| nvidia-nvjitlink | 13.0.88 |
| nvidia-nvshmem-cu13 | 3.4.5 |
| nvidia-nvtx | 13.0.85 |
| obstore | 0.8.2 |
| omegaconf | 2.3.0 |
| onnxruntime | 1.25.1 |
| openai | 2.32.0 |
| opencv-python | 4.13.0.92 |
| openpyxl | 3.1.5 |
| opentelemetry-api | 1.41.1 |
| opentelemetry-exporter-otlp-proto-common | 1.41.1 |
| opentelemetry-exporter-otlp-proto-http | 1.41.1 |
| opentelemetry-instrumentation | 0.62b1 |
| opentelemetry-instrumentation-aiohttp-client | 0.62b1 |
| opentelemetry-proto | 1.41.1 |
| opentelemetry-sdk | 1.41.1 |
| opentelemetry-semantic-conventions | 0.62b1 |
| opentelemetry-util-http | 0.62b1 |
| orjson | 3.11.7 |
| ormsgpack | 1.12.2 |
| packaging | 26.0 |
| pandas | 3.0.2 |
| parso | 0.8.6 |
| patsy | 1.0.2 |
| pexpect | 4.9.0 |
| pillow | 12.2.0 |
| pip | 26.0.1 |
| platformdirs | 4.9.6 |
| pluggy | 1.6.0 |
| polyfactory | 3.3.0 |
| portalocker | 3.2.0 |
| primp | 1.2.3 |
| progressbar2 | 4.5.0 |
| prometheus_client | 0.25.0 |
| prompt_toolkit | 3.0.52 |
| propcache | 0.3.1 |
| protobuf | 6.33.6 |
| psutil | 7.2.2 |
| ptyprocess | 0.7.0 |
| pure_eval | 0.2.3 |
| py_rust_stemmers | 0.1.5 |
| pyasn1 | 0.6.3 |
| pyasn1_modules | 0.4.2 |
| pyclipper | 1.4.0 |
| pycparser | 2.22 |
| pydantic | 2.12.5 |
| pydantic_core | 2.41.5 |
| pydantic-settings | 2.14.0 |
| pydicom | 3.0.2 |
| Pygments | 2.20.0 |
| pyimagej | 1.7.0 |
| pylatexenc | 2.10 |
| PyMuPDF | 1.27.2.3 |
| pymupdf4llm | 0.1.9 |
| pyparsing | 3.3.2 |
| pypdfium2 | 5.7.1 |
| PySide6 | 6.11.0 |
| PySocks | 1.7.1 |
| python-dateutil | 2.9.0.post0 |
| python-docx | 1.2.0 |
| python-dotenv | 1.2.2 |
| python-json-logger | 4.1.0 |
| python-multipart | 0.0.27 |
| python-pptx | 1.0.2 |
| python-utils | 3.9.1 |
| PyYAML | 6.0.3 |
| pyzmq | 27.1.0 |
| qdrant-client | 1.17.1 |
| rank-bm25 | 0.2.2 |
| rapidocr | 3.8.1 |
| readlif | 0.6.6 |
| referencing | 0.37.0 |
| regex | 2026.4.4 |
| requests | 2.32.5 |
| requests-toolbelt | 1.0.0 |
| rich | 15.0.0 |
| rpds-py | 0.30.0 |
| rtree | 1.4.1 |
| safetensors | 0.7.0 |
| scipy | 1.17.1 |
| scyjava | 1.12.1 |
| seaborn | 0.13.2 |
| semchunk | 3.2.5 |
| Send2Trash | 2.1.0 |
| setuptools | 81.0.0 |
| shapely | 2.1.2 |
| shellingham | 1.5.4 |
| shiboken6 | 6.11.0 |
| six | 1.17.0 |
| smmap | 5.0.3 |
| sniffio | 1.3.1 |
| socksio | 1.0.0 |
| soupsieve | 2.8.3 |
| SQLAlchemy | 2.0.49 |
| sqlite-vec | 0.1.6 |
| stack_data | 0.6.3 |
| statsmodels | 0.14.6 |
| sympy | 1.14.0 |
| tabulate | 0.10.0 |
| tavily | 1.1.0 |
| tenacity | 9.1.4 |
| tifffile | 2026.4.11 |
| tiktoken | 0.12.0 |
| tinycss2 | 1.5.1 |
| tokenizers | 0.22.2 |
| toml | 0.10.2 |
| torch | 2.11.0 |
| torchvision | 0.26.0 |
| tornado | 6.5.5 |
| tqdm | 4.67.3 |
| traitlets | 5.14.3 |
| transformers | 5.6.2 |
| tree-sitter | 0.25.2 |
| tree-sitter-c | 0.24.2 |
| tree-sitter-javascript | 0.25.0 |
| tree-sitter-python | 0.25.0 |
| tree-sitter-typescript | 0.23.2 |
| triton | 3.6.0 |
| typer | 0.21.2 |
| typing_extensions | 4.15.0 |
| typing-inspect | 0.9.0 |
| typing-inspection | 0.4.2 |
| urllib3 | 2.6.3 |
| uuid_utils | 0.14.1 |
| wcmatch | 10.1 |
| wcwidth | 0.6.0 |
| webencodings | 0.5.1 |
| websocket-client | 1.9.0 |
| websockets | 15.0.1 |
| wrapt | 2.1.2 |
| xarray | 2026.4.0 |
| xlsxwriter | 3.2.9 |
| xxhash | 3.6.0 |
| yarl | 1.23.0 |
| zipp | 3.23.1 |
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

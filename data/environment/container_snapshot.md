# Container Snapshot — 2026-11-24

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
| Cellpose models: cyto / cyto2 / cyto3 / nuclei / livecell / tissuenet | bundled with the cellpose package (envs `cellpose` and `cellpose4`) | Weights are baked into the image (`~/.cellpose/models`); no download needed. |
| Omnipose | env `cellpose` (omnipose 1.1.4, with cellpose 3) | Not present in the `cellpose4` env. |
| Cellpose 3D / cellpose z-stack / 3D cell segmentation / 3D nuclei segmentation / volumetric segmentation / do_3D / cellpose anisotropy | env `cellpose4` (cpsam), skill `python/cellpose` → `WORKFLOW_CPSAM_3D_SEGMENTATION.py` | Copy the workflow; do not hand-write. Needs the voxel size (fails fast if the file is uncalibrated — ask the user, never guess). Gotchas it handles: `do_3D` capital D; `z_axis` mandatory; `anisotropy` needs `resample=False` or objects split/merge in z; `flow_threshold` ignored in 3D; 2D-sized `min_size`. Plane-by-plane segmentation or `stitch_threshold` is not a substitute. The `cellpose4` env has no scikit-image/pandas. |
| Cellpose (BIOP) Fiji plugin / direct cellpose / cellpose segmentation in Fiji / Cellpose command / CellposeSAM command | Fiji jar `ijl-utilities-wrappers` 0.12.1 (BIOP wrapper); shells to env `cellpose` (cyto3/nuclei) or env `cellpose4` (cpsam) | Direct single-image Cellpose segmentation in Fiji, NO TrackMate. Returns the label image in-process. See the `cellpose_documentation` skill. Use for still images; TrackMate-Cellpose is only for tracking over time. |

---

## System / runtime

| Component | Version / detail |
|-----------|-----------------|
| **Java** | OpenJDK 21.0.10-internal (conda-forge build, mixed mode) |
| **JAVA\_HOME** | `/opt/conda/envs/local_imagent_J/lib/jvm` |
| **ImageJ 1.x** | 1.54p (2025-02-18) |
| **Fiji / imagej2** | 2.18.1-SNAPSHOT (fiji jar), imagej2 2.18.0 |
| **Groovy** | 4.0.28 (in Fiji jars) |
| **conda** | 26.7.1 |
| **CUDA** | None in the CPU image; the GPU image ships CUDA 12.6 builds of torch (`cu126`) and TensorFlow |
| **Xvfb** | 2:21.1.16 |
| **x11vnc** | 0.9.17 |
| **noVNC** | 1.6.0 |
| **websockify** | 0.12.0 |
| **fluxbox** | 1.3.7 |
| **Mesa / OpenGL** | 25.0.7 |
| **wget** | 1.25.0 |
| **curl** | 8.14.1 |

## Interactive pixel classification (Labkit)

| Alias | Where it lives | Notes |
|-------|----------------|-------|
| Labkit / labkit pixel classifier / trainable segmentation / random forest pixel classification / segment fluorescent marker or stain | Fiji plugin (`Plugins > Labkit`), jars `labkit-ui`, `labkit-pixel-classification` | Pixel classifier trained from a few user-marked examples (strokes or ROIs). Offer it whenever objects are defined by a fluorescent marker or stain, especially with noisy channels, textured background or an uncertain threshold. 2D and 3D. See the `labkit_documentation` skill. |

## Python environments


### Main conda env (`local_imagent_J`) — Python 3.13.18

Generated from `pip list` on 2026-11-24 (CPU image). Versions are pinned in `constraints/`.

| Package | Version |
|---------|---------|
| accelerate | 1.16.0 |
| aiofiles | 25.1.0 |
| aiohappyeyeballs | 2.7.1 |
| aiohttp | 3.14.5 |
| aiohttp-retry | 2.9.1 |
| aiosignal | 1.4.0 |
| aiosqlite | 0.22.1 |
| annotated-doc | 0.0.7 |
| annotated-types | 0.8.0 |
| anthropic | 2.11.0 |
| antlr4-python3-runtime | 4.13.2 |
| anyio | 4.16.0 |
| asttokens | 3.0.2 |
| attrs | 26.1.0 |
| Authlib | 1.9.10 |
| beartype | 0.23.1 |
| beautifulsoup4 | 4.15.0 |
| big-fish | 0.6.2 |
| bioio | 3.7.1 |
| bioio-base | 3.6.0 |
| bioio-ome-tiff | 1.5.0 |
| bioio-tifffile | 1.3.1 |
| bracex | 3.2.3 |
| burner-redis | 0.1.7 |
| cachetools | 8.0.2 |
| centrosome | 1.3.4 |
| certifi | 2026.10.23 |
| cffi | 2.1.1 |
| charset-normalizer | 3.5.2 |
| cjdk | 0.5.0 |
| click | 8.5.1 |
| cloudpickle | 3.1.3 |
| colorlog | 6.12.0 |
| comm | 0.2.3 |
| contourpy | 1.4.0 |
| cp_measure | 0.4.1.dev82+g881cb7085 |
| cronsim | 2.8 |
| cryptography | 50.0.2 |
| cuda-bindings | 13.5.0 |
| cuda-pathfinder | 1.9.1 |
| cuda-toolkit | 13.2.2 |
| cycler | 0.12.1 |
| cyclopts | 5.5.2 |
| dask | 2026.8.0 |
| dataclasses-json | 0.6.7 |
| daytona | 2.1.0 |
| ddgs | 9.16.1 |
| debugpy | 1.8.22 |
| deepagents | 0.7.41 |
| defusedxml | 0.7.1 |
| Deprecated | 3.0.1 |
| deprecation | 2.1.0 |
| dill | 0.4.1 |
| diskcache | 5.6.3 |
| distributed | 2026.8.0 |
| distro | 1.9.0 |
| dnspython | 2.9.2 |
| doclang | 0.9.1 |
| docling | 2.151.1 |
| docling-core | 2.107.1 |
| docling-ibm-models | 4.0.4 |
| docling-parse | 7.27.0 |
| docling-slim | 2.151.1 |
| docstring_parser | 0.18.0 |
| donfig | 0.8.1.post1 |
| elementpath | 5.1.4 |
| email-validator | 2.4.0 |
| environs | 14.6.0 |
| et_xmlfile | 2.0.0 |
| exceptiongroup | 1.3.2 |
| executing | 2.3.0 |
| fake-useragent | 2.2.0 |
| Faker | 40.54.0 |
| fakeredis | 2.34.1 |
| fastembed | 0.9.1 |
| fastmcp | 2.14.7 |
| filelock | 4.2.12 |
| filetype | 1.2.0 |
| flatbuffers | 25.12.19 |
| flexcache | 0.3 |
| flexparser | 0.4 |
| fonttools | 4.68.0 |
| formulaic | 1.2.2 |
| frozenlist | 1.8.0 |
| fsspec | 2026.9.0 |
| git-filter-repo | 2.47.0 |
| gitdb | 4.0.12 |
| GitPython | 3.2.1 |
| google-auth | 2.62.2 |
| google-crc32c | 1.9.0 |
| google-genai | 3.6.1 |
| grpcio | 1.85.3 |
| h11 | 0.16.0 |
| h2 | 4.4.1 |
| hf-xet | 1.8.0 |
| hpack | 4.2.0 |
| httpcore | 1.0.9 |
| httpcore2 | 2.16.2 |
| httpx | 0.28.1 |
| httpx-sse | 0.4.3 |
| httpx2 | 2.16.2 |
| huggingface_hub | 1.33.0 |
| hyperframe | 6.1.0 |
| idna | 3.20 |
| imagecodecs | 2026.11.11 |
| ImageIO | 2.38.2 |
| imglyb | 2.1.0 |
| interface_meta | 1.3.0 |
| ipykernel | 7.4.0 |
| ipython | 9.18.1 |
| ipython_pygments_lexers | 1.1.1 |
| jaraco.classes | 3.4.0 |
| jaraco.context | 6.1.2 |
| jaraco.functools | 4.6.0 |
| jedi | 0.20.1 |
| jeepney | 0.9.0 |
| jgo | 1.0.6 |
| Jinja2 | 3.1.6 |
| jiter | 0.19.0 |
| joblib | 1.6.0 |
| joserfc | 1.8.0 |
| jpype1 | 1.6.0 |
| jsonlines | 4.0.0 |
| jsonpatch | 1.48 |
| jsonpointer | 3.12 |
| jsonref | 1.1.0 |
| jsonschema | 4.26.0 |
| jsonschema-path | 0.5.0 |
| jsonschema-specifications | 2025.9.1 |
| jupyter_client | 8.10.0 |
| jupyter_core | 5.9.1 |
| kerchunk | 0.2.10 |
| keyring | 25.7.0 |
| kiwisolver | 1.5.1 |
| labeling | 0.1.14 |
| langchain | 1.5.2 |
| langchain-anthropic | 1.7.12 |
| langchain-classic | 1.0.8 |
| langchain-community | 0.4.2 |
| langchain-core | 1.8.4 |
| langchain-docling | 3.0.0 |
| langchain-google-genai | 4.5.2 |
| langchain-openai | 1.8.5 |
| langchain-protocol | 0.0.22 |
| langchain-pymupdf4llm | 1.28.0 |
| langchain-qdrant | 1.1.0 |
| langchain-text-splitters | 1.1.3 |
| langcodes | 3.5.1 |
| langgraph | 1.2.24 |
| langgraph-checkpoint | 4.3.2 |
| langgraph-checkpoint-sqlite | 3.1.3 |
| langgraph-prebuilt | 1.1.3 |
| langgraph-sdk | 0.4.14 |
| langsmith | 0.15.0 |
| lark | 1.3.1 |
| latex2mathml | 3.81.1 |
| lazy-loader | 0.6 |
| locket | 1.0.0 |
| loguru | 0.7.3 |
| lupa | 2.8 |
| lxml | 6.1.3 |
| mahotas | 1.4.19 |
| mail-parser | 4.11.0 |
| markdown-it-py | 4.3.0 |
| marko | 2.2.5 |
| MarkupSafe | 3.0.4 |
| marshmallow | 3.26.2 |
| matplotlib | 3.11.2 |
| matplotlib-inline | 0.2.2 |
| mcp | 1.30.0 |
| mdurl | 0.1.2 |
| mistune | 3.4.0 |
| mizani | 0.14.6 |
| mmh3 | 5.3.1 |
| more-itertools | 11.2.1 |
| mpire | 2.10.2 |
| mpmath | 1.3.0 |
| mrc | 0.4.0 |
| msgpack | 1.2.4 |
| msgspec | 0.22.0 |
| multidict | 7.2.1 |
| multipart | 2.0.1 |
| multiprocess | 0.70.19 |
| munkres | 1.1.4 |
| mypy_extensions | 1.2.0 |
| mysql-connector-python | 26.10.0 |
| narwhals | 2.29.0 |
| nest-asyncio2 | 1.7.4 |
| nest_asyncio | 1.6.0 |
| networkx | 3.7 |
| numcodecs | 0.17.1 |
| numpy | 2.5.5 |
| nvidia-cublas | 13.4.1.3 |
| nvidia-cuda-cccl | 13.3.5.0.6 |
| nvidia-cuda-cupti | 13.2.86 |
| nvidia-cuda-nvrtc | 13.2.86 |
| nvidia-cuda-runtime | 13.2.86 |
| nvidia-cudnn-cu13 | 9.26.0.51 |
| nvidia-cufft | 12.2.0.57 |
| nvidia-cufile | 1.17.1.22 |
| nvidia-cusolver | 12.2.0.11 |
| nvidia-cusparse | 12.7.10.12 |
| nvidia-cusparselt-cu13 | 0.8.1 |
| nvidia-nccl-cu13 | 2.30.7 |
| nvidia-nvjitlink | 13.5.37 |
| nvidia-nvshmem-cu13 | 3.7.2 |
| nvidia-nvtx | 13.2.86 |
| obstore | 0.12.1 |
| olefile | 0.47 |
| ome-types | 0.7.0 |
| omegaconf | 2.4.0 |
| onnxruntime | 1.32.0 |
| openai | 3.57.0 |
| openapi-pydantic | 0.6.0 |
| opencv-python | 5.1.0.95 |
| opencv-python-headless | 5.1.0.95 |
| openpyxl | 3.1.5 |
| opentelemetry-api | 1.45.2 |
| orjson | 3.13.0 |
| ormsgpack | 1.13.0 |
| packaging | 26.3 |
| pandas | 3.1.1 |
| parso | 0.8.7 |
| partd | 1.4.2 |
| pathable | 0.6.0 |
| pathvalidate | 3.3.1 |
| patsy | 1.0.3 |
| pexpect | 4.9.0 |
| pillow | 11.3.0 |
| Pint | 0.26.2 |
| pip | 26.2.2 |
| platformdirs | 4.14.7 |
| plotnine | 0.15.9 |
| pluggy | 1.7.0 |
| polyfactory | 3.5.0 |
| portalocker | 4.4.2 |
| primp | 2.0.1 |
| progressbar2 | 4.7.1 |
| prometheus_client | 0.26.0 |
| prompt_toolkit | 3.0.53 |
| propcache | 0.5.4 |
| protobuf | 7.36.2 |
| psutil | 7.2.2 |
| ptyprocess | 0.7.0 |
| pure_eval | 0.2.4 |
| py-key-value-aio | 0.3.0 |
| py-key-value-shared | 0.3.0 |
| py_rust_stemmers | 0.1.8 |
| pyasn1 | 0.6.5 |
| pyasn1_modules | 0.4.2 |
| pyclipper | 1.4.0 |
| pycparser | 3.12 |
| pydantic | 2.14.4 |
| pydantic-extra-types | 2.11.1 |
| pydantic-settings | 2.16.3 |
| pydantic_core | 2.50.5 |
| pydicom | 3.0.2 |
| pydocket | 0.29.1 |
| Pygments | 2.21.0 |
| pyimagej | 1.7.0 |
| PyJWT | 2.15.1 |
| pylatexenc | 2.11 |
| pymupdf | 1.28.0 |
| pymupdf-layout | 1.28.0 |
| pymupdf4llm | 1.28.0 |
| pyparsing | 3.3.3 |
| pypdfium2 | 5.15.2 |
| pyperclip | 1.11.0 |
| PySide6 | 6.12.0 |
| python-dateutil | 4.0.0 |
| python-docx | 1.2.0 |
| python-dotenv | 1.2.4 |
| python-json-logger | 4.2.0 |
| python-multipart | 0.0.34 |
| python-oxmsg | 0.0.2 |
| python-pptx | 1.0.2 |
| python-utils | 4.2.2 |
| PyYAML | 6.0.3 |
| pyzmq | 27.3.0 |
| qdrant-client | 1.20.0 |
| rank-bm25 | 0.2.2 |
| rapidocr | 3.10.0 |
| readlif | 0.6.6 |
| redis | 8.1.0 |
| referencing | 0.37.0 |
| regex | 2026.11.19 |
| requests | 2.34.2 |
| requests-toolbelt | 1.0.0 |
| rich | 15.0.0 |
| rich-rst | 2.2.0 |
| rpds-py | 2026.9.1 |
| rtree | 1.4.1 |
| safetensors | 0.8.0 |
| scikit-image | 0.26.0 |
| scikit-learn | 1.9.1 |
| scikit-misc | 0.0.0 |
| scipy | 1.18.1 |
| scyjava | 1.12.1 |
| seaborn | 0.13.2 |
| SecretStorage | 3.5.0 |
| semchunk | 3.2.5 |
| semver | 3.1.2 |
| Send2Trash | 2.2.0 |
| setuptools | 84.2.1 |
| shapely | 2.2.0 |
| shellingham | 1.5.4 |
| shiboken6 | 6.12.0 |
| six | 1.17.0 |
| smmap | 5.0.3 |
| sniffio | 1.3.1 |
| socksio | 1.0.0 |
| sortedcontainers | 2.4.0 |
| soupsieve | 4.1.2 |
| SQLAlchemy | 2.1.9 |
| sqlite-vec | 0.1.9 |
| sse-starlette | 3.7.0 |
| stack_data | 0.6.3 |
| starlette | 1.10.0 |
| statsmodels | 0.15.0 |
| sympy | 1.14.0 |
| tabulate | 0.10.0 |
| tavily | 1.1.0 |
| tblib | 3.2.2 |
| tenacity | 9.1.4 |
| threadpoolctl | 3.8.0 |
| tifffile | 2026.11.16 |
| tiktoken | 0.14.0 |
| tinycss2 | 1.5.1 |
| tokenizers | 0.23.3 |
| toml | 0.10.2 |
| toolz | 1.2.0 |
| torch | 2.15.0 |
| torchvision | 0.29.2 |
| tornado | 6.6.1 |
| tqdm | 4.70.1 |
| traitlets | 5.16.1 |
| transformers | 5.23.0 |
| tree-sitter | 0.26.1 |
| tree-sitter-c | 0.24.2 |
| tree-sitter-javascript | 0.25.0 |
| tree-sitter-python | 0.25.0 |
| tree-sitter-typescript | 0.23.2 |
| triton | 3.9.0 |
| truststore | 0.10.5 |
| typer | 0.27.3 |
| typing-inspect | 0.9.0 |
| typing-inspection | 0.4.5 |
| typing_extensions | 4.16.0 |
| tzdata | 2026.6 |
| ujson | 6.1.0 |
| uncalled-for | 0.6.2 |
| urllib3 | 2.8.0 |
| uuid_utils | 0.17.0 |
| uvicorn | 0.54.0 |
| wcmatch | 12.0.3 |
| wcwidth | 0.9.4 |
| webencodings | 0.6.1 |
| websocket-client | 1.9.2 |
| websockets | 17.4 |
| wrapt | 2.5.2 |
| xarray | 2026.9.0 |
| xlsxwriter | 3.3.3 |
| xmlschema | 4.3.2 |
| xsdata | 26.10 |
| xxhash | 3.7.0 |
| yarl | 1.25.1 |
| zarr | 3.4.2 |
| zict | 3.0.0 |
| zstandard | 0.25.0 |

### conda env `stardist` — Python 3.11.18

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
| matplotlib | 3.11.2 |
| pillow | 13.0.0 |
| ImageIO | 2.38.2 |
| h5py | 3.16.0 |
| numba | 0.68.1 |
| llvmlite | 0.50.0 |
| tensorboard | 2.15.2 |
| protobuf | 4.25.9 |
| grpcio | 1.85.3 |
| langchain-core | 1.2.16 |
| langgraph-checkpoint-sqlite | 3.0.3 |
| pydantic | 2.12.5 |
| requests | 2.34.2 |
| tqdm | 4.70.1 |

---

### conda env `cellpose4` — Python 3.11.18

| Package | Version |
|---------|---------|
| cellpose | 4.1.1 |
| segment-anything | 1.0 |
| torch | 2.11.0+cpu |
| torchvision | 0.26.0+cpu |
| numpy | 2.4.6 |
| scipy | 1.17.1 |
| imagecodecs | 2026.3.6 |
| tifffile | 2026.3.3 |
| pillow | 13.0.0 |
| opencv-python-headless | 5.1.0.95 |
| fastremap | 1.21.0 |
| fill_voids | 2.1.2 |
| roifile | 2026.2.10 |
| natsort | 8.4.0 |
| PyQt6 | 6.12.1 |
| pyqtgraph | 0.14.0 |
| superqt | 0.9.2 |
| langchain-core | 1.2.16 |
| langgraph-checkpoint-sqlite | 3.0.3 |
| pydantic | 2.12.5 |
| sympy | 1.14.0 |
| networkx | 3.6.1 |
| tqdm | 4.70.1 |

---

### conda env `cellpose` — Python 3.10.22

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
| tifffile | 2025.5.10 |
| pillow | 12.3.0 |
| opencv-python-headless | 5.1.0.95 |
| fastremap | 1.21.0 |
| fill_voids | 2.1.2 |
| roifile | 2025.12.12 |
| natsort | 8.4.0 |
| numba | 0.68.1 |
| llvmlite | 0.50.0 |
| dask | 2026.11.0 |
| dask-image | 2026.5.0 |
| aicsimageio | 4.14.0 |
| ome-zarr | 0.11.1 |
| zarr | 2.15.0 |
| mahotas | 1.4.19 |
| networkit | 11.3 |
| pandas | 2.3.3 |
| matplotlib | 3.10.9 |
| PyQt6 | 6.12.1 |
| pyqtgraph | 0.14.0 |
| superqt | 0.8.2 |
| langchain-core | 1.2.16 |
| langgraph-checkpoint-sqlite | 3.0.3 |
| pydantic | 2.12.5 |
| ipython | 8.39.0 |
| tqdm | 4.70.1 |

### conda env `napari-mcp` — Python 3.11.18 (micro_sam + in-container napari MCP viewer)

Versions re-checked 2026-11-24 and listed as they IMPORT (several packages are installed
twice in this env, by pip and by conda; the conda copy is the one that loads). Baked
micro_sam checkpoints, each with its AIS decoder, no download needed: `vit_t_lm`,
`vit_t_em_organelles`, `vit_b_lm`. Hosts
`micro_sam` ("Segment Anything for Microscopy") for both the interactive napari viewer
(backend `napari`, driven via `mcp__napari_mcp__*`) and the headless batch route
(`# imagentj-env: napari-mcp`). On the GPU build, torch/torchvision are swapped to the
cu126 CUDA wheels so micro_sam uses the A100 (`cuda_build 12.6`, verified).

| Package | Version |
|---------|---------|
| micro_sam | 1.8.2 |
| torch | 2.10.0 (CPU image) / 2.11.0+cu126 (GPU image) |
| torchvision | 0.26.0 (CPU image) / 0.26.0+cu126 (GPU image) |
| torch_em | 0.10.11 |
| python-elf | 0.9.3 |
| segment-anything-py | 1.0 |
| mobile_sam | 1.0 |
| timm | 1.0.31 |
| huggingface_hub | 2.4.0 |
| napari | 0.6.6 |
| napari-mcp | 0.1.0 |
| napari-console | 0.1.5 |
| napari-plugin-engine | 0.2.1 |
| napari-plugin-manager | 0.1.12 |
| napari-svg | 0.2.1 |
| napari-metadata | 0.5.0 |
| magicgui | 0.10.2 |
| superqt | 0.9.2 |
| QtPy | 2.4.3 |
| PyQt6 | 6.12.0 |
| vispy | 0.15.2 |
| fastmcp | 2.14.7 |
| mcp | 1.30.0 |
| numpy | 2.4.6 |
| scipy | 1.17.1 |
| scikit-image | 0.26.0 |
| scikit-learn | 1.9.1 |
| tifffile | 2024.12.12 |
| ImageIO | 2.38.2 |
| pillow | 12.0.0 (CPU image) / 13.0.0 (GPU image) |
| zarr | 3.1.5 |
| pandas | 3.0.6 |
| xarray | 2026.9.0 |
| pooch | 1.9.0 |


### conda env `brainglobe` — Python 3.12.16 (whole-brain registration and atlases)

Selected with `# imagentj-env: brainglobe` from python_data_analyst. Holds the BrainGlobe
stack for atlas-based work — registering a sample brain to a reference atlas and querying
anatomical regions. Versions captured 2026-11-24. Do NOT use this env for anything the main
env can do; it exists for the atlas tooling only.

| Package | Version |
|---------|---------|
| brainglobe-atlasapi | 3.1.0 |
| brainglobe-utils | 0.11.3 |
| brainglobe-space | 1.0.4 |
| brainglobe-segmentation | 1.3.4 |
| brainreg | 1.0.17 |
| napari | 0.10.0 |
| numpy | 2.4.6 |
| scipy | 1.18.1 |
| scikit-image | 0.26.0 |
| tifffile | 2026.11.16 |
| pandas | 3.1.1 |
| dask | 2026.11.0 |

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
| Big_Stitcher | 3.0.8 |
| Biovoxxel_Plugins | 2.6.3 |
| Cell_Counter | 3.0.0 |
| Colocalisation_Analysis | 3.1.0 |
| Colour_Deconvolution | 3.0.3 |
| CorrectBleach_ | 2.1.0 |
| DeepImageJ | 3.2.1-SNAPSHOT |
| Descriptor_based_registration | 3.0.3 |
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
| SNT | 5.0.25 |
| Siox_Segmentation | 1.0.5 |
| Skeletonize3D_ | 2.1.1 |
| StackReg_ | 2.0.1 |
| StarDist_ | 0.3.0-scijava / 0.3.0 |
| Statistical_Region_Merging | 2.0.1 |
| Stitching_ | 3.1.10 |
| ToAST_ | 25.0.2 |
| TrackMate | 8.1.6 |
| TrackMate-Cellpose | 1.0.1 |
| TrackMate-MorphoLibJ | 2.0.0 |
| TrackMate-StarDist | 2.0.0 |
| Trainable_Segmentation (Weka) | 4.0.0 |
| TrakEM2_ | 2.0.0 |
| TurboReg_ | 2.0.1 |
| UnwarpJ_ | 2.0.0 |
| VIB_ | 4.0.0 |
| bigwarp_fiji | 9.4.0 |
| bio-formats_plugins | 8.5.0 |
| bonej-legacy-plugins_ | 7.2.2 |
| bUnwarpJ_ | 2.6.13 |
| bv3dbox | 1.25.1 |
| clij_ | 1.9.0.1 |
| clij2_ | 2.5.3.5 |
| clij2-assistant_ | 2.5.1.6 |
| clijx_ | 0.32.2.0 |
| ij_ridge_detect | 1.4.1 |
| mcib3d_plugins | 4.1.8 |
| mpicbg_ | 1.6.6 |
| multiview_reconstruction | 9.0.11 |
| n5-viewer_fiji | 6.2.0 |
| register_virtual_stack_slices | 3.0.8 |

---

## Key Fiji jars (`/opt/Fiji.app/jars/`)

| JAR | Version |
|-----|---------|
| appose | 0.12.0 |
| bio-formats (formats-api/bsd/gpl) | 8.5.0 |
| csbdeep | 0.6.0 |
| dl-modelrunner | 0.6.4 |
| fiji | 2.18.1-SNAPSHOT |
| groovy + modules | 4.0.28 |
| ij (ImageJ 1.x) | 1.54p |
| ijl-utilities-wrappers (BIOP Cellpose/CellposeSAM direct wrapper) | 0.12.1 |
| imagej | 2.18.0 |
| imagej-common | 2.1.2 |
| imagej-legacy | 3.0.0 |
| imagej-modelzoo | 0.9.10 |
| imagej-ops | 2.2.0 |
| imagej-updater | 2.0.3 |
| imglib2 | 8.0.0 |
| imglib2-appose | 0.5.0-ctr |
| javafx (all modules) | 23.0.2 |
| jogl-all | 2.6.0 |
| jython-slim | 2.7.4 |
| labkit-ui | 0.4.0 |
| n5 | 4.0.1 |
| nashorn-core | 15.6 |
| ome-xml | 6.5.3 |
| opencv | 4.9.0-1.5.10 |
| protobuf-java | 4.32.0 |
| scijava-common | 2.101.0 |
| scifio | 0.49.2 |
| scifio-ome-xml | 0.17.1 |
| simpleitk | 2.1.0.dev54 |
| slf4j-api | 2.0.17 |
| slf4j-nop | 2.0.16 |
| sqlite-jdbc | 3.49.1.0 |
| torch (libtensorflow) | 1.12.0 |
| weka-dev | 3.9.6 |

---

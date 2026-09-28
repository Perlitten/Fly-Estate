# Fly Estate

A personal apartment fly for Limassol. Photos, budget and location become inputs to a model built on real FlyWire connections. Rate listings and choose between pairs; the application learns your preferences and shows its responses on a map and in a 3D brain.

Spiking dynamics, dopamine learning and upcoming work: **[roadmap](docs/ROADMAP.md)**.

## Getting started

Requires Node.js 22+, pnpm 11 and Python 3.11+. On a computer with Codex installed, setup can also locate its bundled Python.

```sh
pnpm install --frozen-lockfile
pnpm setup
pnpm dev
```

Open **http://127.0.0.1:5176**. The Python API runs on `127.0.0.1:8000`. Both servers listen on localhost only. No API key is required.

The first setup downloads approximately 2 GB of public data and model weights, prepares the graph and imports the catalogue. Internet access and several GB of free space are required. Subsequent runs reuse cached files and skip apartments already imported. `pnpm setup --no-seed` prepares the brain without importing apartments. Set `FLY_PYTHON` to choose the Python used to create the environment.

`pnpm build` builds the frontend and checks TypeScript. To preview the production build, start the API separately (`.venv/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port 8000`), then run `pnpm preview`. On Windows, Python is located at `.venv/Scripts/python.exe`.

## Available features

- **Fly brain:** 139,248 annotated neurons in 3D. Rotate, zoom, highlight groups and select a neuron to inspect it. The API returns 16 steps of computed activity for each apartment. View the response to the whole gallery or to an individual photo.
- **Interest map:** OpenStreetMap, price markers, grouped apartments at shared coordinates, a preferred area and a draggable center. The fly marker shows the model’s interest in the selected apartment.
- **Learning:** “Would visit”, “Maybe” and “Not for me”, with an option to remove a rating. A new rating replaces the previous one.
- **Apartment duels:** choose A, B or a tie. Each pair is stored once, regardless of its order.
- **Rules:** target budget, hard price limit, bedroom count, covered parking and excluded areas. Listings are filtered before computation and learning.
- **Pure Fly:** photos become an 8×8 RGB grid projected onto selected visual inputs.
- **Cyborg Fly:** local CLIP extracts signals of spaciousness, light, interior design, a large balcony and shelter. Preferences are then computed through the FlyWire graph.
- **Every photo:** each available image passes through the encoder and 16 neural steps. MBON/CX outputs are averaged after computation; the input photos are not averaged first. The interface shows processed and expected photo counts. Unavailable photos are not replaced with invented images.
- **Space and balconies:** floor area, balcony/loggia presence, stated balcony size and shelter provide positive input signals. Cyborg Fly also estimates large balcony and shelter signals from photos. Balcony area is never inferred in square meters from an image: it stays unknown if the source does not state it.
- **Import:** JSON-LD, JSON, HTML/text, supported listing URLs and manual entry with uploaded photos. A bookmark button copies listing data from pages rendered with JavaScript.

Defaults from the original brief: €1,800 target budget, €2,800 hard limit, at least one bedroom, covered parking required and Ypsonas excluded. These are editable initial settings.

Classification starts after at least five ratings/comparisons with both positive and negative examples, or five pairwise comparisons. Until then, the interface says the fly is still learning. A fresh installation contains no fabricated personal ratings.

## Model architecture

```text
Every photo → RGB / CLIP ──┐
Price, space, balcony → ALPN├→ FlyWire graph → MBON + CX per photo
Location and distance → CX┘                         ↓
                                      average across all photos
                                                   ↓
                              your ratings → learned readout → interest
```

`scripts/prepare_brain.py` aggregates real synaptic connections by neuron pair, removes self-connections and excludes pairs with fewer than five synapses. The current prepared graph contains **2,700,429** directed connections and **34,152,544** synapses on those connections. Weights are positive and normalized by incoming weight.

`server/brain.py` implements simple rate dynamics: 16 leak-and-`tanh` steps, followed by the activity of 96 MBONs and pooling across 229 CX types. Only these outputs enter a regularized logistic readout trained on ratings and pair differences. Price and photo features are not passed directly to the final classifier. The same neural computation supplies the frames of the 3D visualization.

Each image is computed independently using the same apartment metadata. Batch size limits memory use, not the total number of processed photos. The gallery visualization averages absolute activities across images before normalizing each frame. Positive space and balcony inputs are artificial preferences requested by the user; the learned readout still depends on their ratings.

### Scientific boundaries

**Anatomical positions, identifiers, types and connection topology are real.** Dynamics, sensory adapters and the apartment readout are our experimental model. They are not measured activity from a living fly or a validated emulation of its decisions.

- RGB-to-neuron mapping is a deterministic artificial adapter, not reconstructed retinotopy. Pretrained FlyVis is not connected.
- ALPNs are not “price neurons”. Numeric features are projected onto them artificially. CX receives an artificial direction and distance signal.
- Excitatory/inhibitory signs, delays, biophysics and receptor specificity are not reconstructed in the application engine. A neurotransmitter label is not treated as a proven synaptic sign.
- A separate MBON/CX readout is trained. Biological dopamine-dependent KC→MBON plasticity is not yet integrated. The DAN group in 3D is an anatomical group.
- CLIP signals are photo–text similarities, not verified housing properties or calibrated probabilities. The final score is not a probability that you will like an apartment in real life.
- Points represent annotated neuron locations, not neurite morphologies. Lines display a subset of real connections. The complete prepared graph is used for computation.
- Brightness shows activity magnitude using `sqrt(abs(a)/max(abs(a)))`, normalized separately in each frame. Brightness cannot be compared between frames as an absolute firing rate.
- The fly marker’s movement on the map visualizes a result. It does not simulate a motor system or a real travel route.

## Sources and versions

- Connections: [FlyWire public release 783, Zenodo 10676866](https://zenodo.org/records/10676866), `proofread_connections_783.feather`. The download script verifies the published MD5. Metadata and the CC BY 4.0 license are recorded in `data/provenance.json`.
- Annotations: [flyconnectome/flywire_annotations, v3.1.0](https://github.com/flyconnectome/flywire_annotations/tree/v3.1.0), `Supplemental_file1_neuron_annotations.tsv`. Coordinates are converted to physical scale according to [fafbseg documentation: 4×4×40 nm](https://natverse.org/fafbseg/reference/flywire_voxdims.html).
- Vision: the [official openai/clip-vit-base-patch32 model](https://huggingface.co/openai/clip-vit-base-patch32), pinned to `3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268`. All available images are processed locally in batches of four, without truncating galleries.
- Catalogue: public cards from [RentSpot Cyprus](https://www.rentspotcy.com/rentals). `data/listings.json` contains links, short fields and image URLs captured on September 28, 2026. Full descriptions and contact details are excluded. Photos are downloaded from public URLs during import and are not stored in Git.
- Geography: OpenStreetMap/Nominatim, ODbL. Sources and accuracy are recorded in `data/areas.json`. Most markers are approximate area locations, not exact addresses. Distances are straight-line distances. Listing availability and prices may change; check the original source.

The [annotation citation guidelines](https://github.com/flyconnectome/flywire_annotations#how-to-cite) require citing **Berg et al. (2025)**, **Schlegel et al. (2024)**, **Matsliah et al. (2024)** and **Dorkenwald et al. (2024)** when using annotation versions ≥3.0. Full references are available in the upstream repository. Fly Estate is not an official FlyWire product.

## Storage and import

SQLite at `data/state.sqlite` stores local listings, rules and ratings. `data/photos` stores photos. These files, downloaded models and large raw datasets are excluded from Git.

Export downloads JSON containing listings, settings and ratings. Paste it into import to restore settings and ratings for successfully imported apartments. Images are downloaded again from their original URLs; manually uploaded photos must be added again. This export is not a complete image backup.

Direct URLs are accepted only from RentSpot, Fox, Bazaraki and INDEX. Supporting a URL does not guarantee that its source will return data without a browser. Bazaraki presented a Cloudflare check during development, so direct collection from it is unavailable. Use an open page with the bookmark button, JSON/HTML or the manual form for such sources.

The server restricts sources to supported sites and public HTTPS addresses, checks redirects and enforces size limits. The application is intended for one person running it locally. Public deployment requires authentication, separate user storage and resource limits.

Each import accepts up to 100 listings and up to 100 images per listing. Larger galleries are rejected with an explicit error rather than truncated. Unavailable photos are reported as warnings.

## Project structure

```text
src/                     React, 3D brain, map, cards and import
server/                  FastAPI, graph, CLIP, SQLite and import
scripts/                 reproducible preparation and startup
data/listings.json       public fields of the initial catalogue
data/areas.json          approximate area coordinates
data/provenance.json     versions, sources and checksums
.github/workflows/       frontend build and Python syntax checks
```

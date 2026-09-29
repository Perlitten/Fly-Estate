# Fly Estate

A personal apartment fly for Limassol. Photos, budget and location become inputs to a model built on real FlyWire connections. Rate listings and choose between pairs; the application learns your preferences and shows its responses on a map and in a 3D brain.

Spiking dynamics, dopamine learning and upcoming work: **[roadmap](docs/ROADMAP.md)**.

Voice, colour, type, motion and media rules: **[brand kit](docs/BRAND_KIT.md)** (live version at `/brand.html` in `pnpm dev`).

Completed research: **[R1 measurements and results](reports/lif-baseline.md)** and **[research setup](research/README.md)**. The 3D brain offers the rate overview and actual per-photo LIF spikes from the worker. The main apartment verdict still uses the rate readout; spiking results have their own experimental readout (see [spiking engine](#spiking-engine-and-worker)).

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

## Working from another computer

Install Git, Node.js 22+, pnpm 11 and Python 3.11+, then clone the repository:

```sh
git clone https://github.com/Perlitten/Fly-Estate.git
cd Fly-Estate
pnpm install --frozen-lockfile
pnpm setup
pnpm dev
```

`main` contains the code, English interface and documentation, public catalogue, roadmap and measured research results. Setup downloads datasets, models and available source photos on the new computer; those large caches are regenerated locally.

To carry your personal preferences over, click **Export** on the old computer and transfer the JSON file privately. On the new computer, open **Import**, paste the JSON and start import. A version 1 backup supports up to 1,000 listings and restores settings, ratings and pairwise choices for successfully imported apartments. Photos and encoder outputs are rebuilt, so importing can take several minutes. Manually uploaded photos must be added again. Personal state is stored locally and is excluded from this public repository.

To continue development, create a branch with `git switch -c codex/your-change`. Run `git pull --ff-only` on `main` before starting new work.

## Available features

- **Fly brain:** 139,248 annotated neurons in 3D. Rotate, zoom, highlight groups and select a neuron to inspect it. **Rate overview** shows 16 computed steps for a gallery or photo. **Analyze in 3D** follows the worker through every photo, showing actual LIF spikes on the 8,991 simulated neurons while the remaining anatomy stays dim. **Replay analysis** plays the saved photos in order; pause, scrub or select a photo to inspect it.
- **Interest map:** OpenStreetMap, price markers, grouped apartments at shared coordinates, a preferred area and a draggable center. The fly marker shows the model’s interest in the selected apartment.
- **Portfolio:** search by area or apartment name, filter by your review status and sort by interest, price or distance. Open an apartment through its cover or **Inspect in brain**. Returning to the portfolio keeps the search and review filter.
- **Apartment inspection:** previous/next apartment and photo controls, a prominent start/replay action, an optional photo gallery and expandable neural/sensory details. The agent’s rate-model view is labelled separately from recorded spiking responses. On a phone, jump between the apartment and connectome; starting or replaying analysis brings the brain into view.
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

`server/brain.py` implements simple rate dynamics: 16 leak-and-`tanh` steps, followed by the activity of 96 MBONs and pooling across 229 CX types. Only these outputs enter a regularized logistic readout trained on ratings and pair differences. Price and photo features are not passed directly to the final classifier. The same neural computation supplies the **Rate overview** frames. **Spiking analysis** instead displays recordings from the LIF worker described below.

Each image is computed independently using the same apartment metadata. Batch size limits memory use, not the total number of processed photos. The gallery visualization averages absolute activities across images before normalizing each frame. Positive space and balcony inputs are artificial preferences requested by the user; the learned readout still depends on their ratings.

### Scientific boundaries

**Anatomical positions, identifiers, types and connection topology are real.** Dynamics, sensory adapters and the apartment readout are our experimental model. They are not measured activity from a living fly or a validated emulation of its decisions.

- RGB-to-neuron mapping is a deterministic artificial adapter, not reconstructed retinotopy. Pretrained FlyVis is not connected.
- ALPNs are not “price neurons”. Numeric features are projected onto them artificially. CX receives an artificial direction and distance signal.
- The rate engine does not reconstruct excitatory/inhibitory signs, delays, biophysics or receptor specificity. The LIF worker uses the explicit assumptions and structural edits documented in R1.
- The main verdict trains a separate MBON/CX readout. The LIF engine supports the R1 dopamine-gated KC→MBON depression rule; analyzing photos does not apply reinforcement or change weights. Taste-history and before/after learning visualization remain planned.
- CLIP signals are photo–text similarities, not verified housing properties or calibrated probabilities. The final score is not a probability that you will like an apartment in real life.
- Points represent annotated neuron locations, not neurite morphologies. Lines display a subset of real connections. The complete prepared graph is used for computation.
- **Rate overview** brightness uses `sqrt(abs(a)/max(abs(a)))`, normalized separately in each frame, so it is not an absolute firing rate. **Spiking analysis** uses actual counts in 25 ms bins and a fixed square-root scale, clipped at 20 spikes per bin. Frames interpolate for display; the underlying count bins stay lossless. The timeline shows simulation time, and replay runs four times slower than the recorded episode.
- The fly marker’s movement on the map visualizes a result. It does not simulate a motor system or a real travel route.

## Spiking engine and worker

`server/engine/` contains the R2 engine: the `SimulationEngine` interface and `OlfactoryMBEngine`, a NumPy LIF implementation of the edited 8,991-neuron olfactory→mushroom-body subgraph from R1 (Shiu v783 weights, 0.1 ms step, 1.8 ms delay, 2.2 ms refractory period, dopamine-gated KC→MBON depression). It does not require Brian2. An exact-drive check against the pinned Brian2 kernel produced identical spikes; the [parity replay](reports/results/engine_parity.json) of the R1 conditioning protocol matches R1 within its stated tolerances. An episode takes about 0.75 s including the 150 ms washout.

Prepare the subgraph once, after `pnpm setup`:

```sh
.venv/bin/python -m research.bootstrap        # pinned upstream data, ~200 MB, verified by SHA256
.venv/bin/python -m server.engine.subgraph    # writes data/engine/olfactory_mb_v783.npz
```

`pnpm dev` then starts one engine worker next to the API (`python -m server.worker`; `--once` processes the queue and exits). Only one worker can hold the lease in `data/engine/engine.sqlite`; a second worker exits with code 3. The HTTP server only enqueues and reads, so the interface stays responsive during computation.

In the brain sidebar, **Analyze in 3D** queues every photo and follows the running photo. The worker publishes completed spike bins every 100 ms of simulated time; the interface polls progress and maps those counts by FlyWire root ID. Only the prepared subgraph receives activity. Saved recordings expose the checkpoint, photo coverage and simulation time. Cached results without a recording are recomputed with the same deterministic seed to add it. Once every photo has a current recording, **Replay analysis** reuses the cache and plays the gallery in order. **Stop** finishes the current photo before stopping the job. Selecting a photo leaves automatic following and opens that photo’s recording; stale recordings are labelled as earlier weights or brief.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/engine` | engine, subgraph, worker heartbeat, current checkpoint and queue counts |
| `POST /api/simulations` `{listing_id}` | queue every photo of a listing; repeated requests return the active job |
| `GET /api/simulations[?listing_id=]`, `GET /api/simulations/{id}` | job status and per-photo progress |
| `POST /api/simulations/{id}/cancel` | cancel a queued job, or stop a running one before its next photo |
| `GET /api/engine/activity/{listing_id}` | latest activity per photo; `stale` marks results produced with older weights |
| `GET /api/engine/gallery/{listing_id}` | current photo readiness, recording keys and live progress under the active brief |
| `GET /api/engine/replay/{cache_key}` | saved spike bins projected by neuron ID onto the anatomical view |
| `GET /api/engine/live/{job_id}?photo={position}` | completed bins of the currently running photo, or `available: false` between photos |

Jobs, items and activity are stored in SQLite (WAL). After a crash or restart, the worker requeues interrupted jobs and keeps finished photos. Results are cached by photo SHA256, stimulus, codec settings, engine version and weight fingerprint. Checkpoints are written atomically to `data/engine/checkpoints/<sha256>.npz` and contain plastic weights, network state, seed, parameters, root-ID checksum, RNG state and episode history; restoring validates all of them.

The photo stimulus (`photo-orn-v0`) is a provisional, artificial mapping of brightness and ten CLIP signals onto the first eleven ORN channels. It is not an odor and not a model of vision; R3 replaces it.

Tests use a synthetic circuit and, when the prepared subgraph exists, the real one:

```sh
.venv/bin/python -m unittest discover -s tests -t . -v
```

## Sources and versions

- Connections: [FlyWire public release 783, Zenodo 10676866](https://zenodo.org/records/10676866), `proofread_connections_783.feather`. The download script verifies the published MD5. Metadata and the CC BY 4.0 license are recorded in `data/provenance.json`.
- Annotations: [flyconnectome/flywire_annotations, v3.1.0](https://github.com/flyconnectome/flywire_annotations/tree/v3.1.0), `Supplemental_file1_neuron_annotations.tsv`. Coordinates are converted to physical scale according to [fafbseg documentation: 4×4×40 nm](https://natverse.org/fafbseg/reference/flywire_voxdims.html).
- Vision: the [official openai/clip-vit-base-patch32 model](https://huggingface.co/openai/clip-vit-base-patch32), pinned to `3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268`. All available images are processed locally in batches of four, without truncating galleries.
- Catalogue: public cards from [RentSpot Cyprus](https://www.rentspotcy.com/rentals). `data/listings.json` contains links, short fields and image URLs captured on September 28, 2026. Full descriptions and contact details are excluded. Photos are downloaded from public URLs during import and are not stored in Git.
- Geography: OpenStreetMap/Nominatim, ODbL. Sources and accuracy are recorded in `data/areas.json`. Most markers are approximate area locations, not exact addresses. Distances are straight-line distances. Listing availability and prices may change; check the original source.

The [annotation citation guidelines](https://github.com/flyconnectome/flywire_annotations#how-to-cite) require citing **Berg et al. (2025)**, **Schlegel et al. (2024)**, **Matsliah et al. (2024)** and **Dorkenwald et al. (2024)** when using annotation versions ≥3.0. Full references are available in the upstream repository. Fly Estate is not an official FlyWire product.

## Storage and import

SQLite at `data/state.sqlite` stores local listings, rules and ratings. `data/photos` stores photos. These files, downloaded models and large raw datasets are excluded from Git.

Export downloads portable JSON containing listings, settings, ratings and pairwise choices. It excludes local photo paths and encoder tensors. Paste it into import to restore settings and ratings for successfully imported apartments. Images are downloaded again from their original URLs; manually uploaded photos must be added again. This export is not a complete image backup.

Direct URLs are accepted only from RentSpot, Fox, Bazaraki and INDEX. Supporting a URL does not guarantee that its source will return data without a browser; for such pages, use an open page with the bookmark button, JSON/HTML or the manual form. Bazaraki adverts are read directly by the connector below.

### Bazaraki connector

`server/bazaraki.py` reads the Limassol apartment rentals on [Bazaraki](https://www.bazaraki.com) the way a visitor's browser would, and the area map's "Search Bazaraki" panel drives it.

- **robots.txt.** It requests only pages that robots.txt allows: public search pages (`/real-estate-to-rent/apartments-flats/lemesos-district-limassol/`), the public map page (`/map/...`) and advert pages (`/adv/<id>_<slug>/`). It never calls `/api` and never uses `attrs_*` filters, both of which are disallowed. The brief's ceiling goes in `price_max`; bedrooms are checked locally.
- **Pace.** Requests are sequential, with a 0.8 s pause between them, and carry the tool's User-Agent. A market snapshot is cached for 15 minutes per brief, so reopening the map does not read the site again.
- **Data.** Pages are Next.js; the connector decodes the React flight payload (`self.__next_f.push`) instead of scraping markup. Search pages give price, bedrooms, size, area, date and the first photo. An advert page gives the stated features, the description, every photo and the advert's own coordinates, flagged when Bazaraki marks them approximate. The seller's name and profile are not kept.
- **Locations.** Exact points come from the map page, which lists about 100 adverts, or from the advert page on import. Offers that Bazaraki places automatically, and the rest, sit at their area centre from `data/areas.json`; offers from unknown areas stay off the map. The map draws exact points as dots and area centres as dashed rings with a count.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/sources/bazaraki[?pages=N]` | market snapshot under the brief: offers, counts, which are already on file and which fall in excluded areas |
| `POST /api/sources/bazaraki/sync` `{limit, pages}` | import up to `limit` new offers that fit the brief; returns the import job and how many remain |
| `POST /api/import` `{urls}` | import particular adverts, for example one offer from the map |
| `GET /api/jobs`, `GET /api/jobs/{id}` | running and recent import jobs, and one job's progress |

The server restricts sources to supported sites and public HTTPS addresses, checks redirects and enforces size limits. The application is intended for one person running it locally. Public deployment requires authentication, separate user storage and resource limits.

Each ordinary import accepts up to 100 listings; a version 1 backup accepts up to 1,000. The pasted content limit is 4 million characters. Each listing accepts up to 100 images. Larger galleries are rejected with an explicit error rather than truncated. Unavailable photos are reported as warnings.

## Project structure

```text
src/                     React, 3D brain, map, cards and import
server/                  FastAPI, graph, CLIP, SQLite and import
server/engine/           LIF engine interface, subgraph and photo stimuli
server/worker.py         single engine worker, durable queue and checkpoints
tests/                   engine, queue and worker tests (unittest)
scripts/                 reproducible preparation and startup
data/listings.json       public fields of the initial catalogue
data/areas.json          approximate area coordinates
data/provenance.json     versions, sources and checksums
research/                pinned LIF reproduction and separate dependency lock
reports/                 measured results, resource profile and figures
docs/ROADMAP.md          stages, acceptance criteria and GitHub tasks
docs/BRAND_KIT.md        brand rules; src/tokens.css holds the values
.github/workflows/       frontend build and Python syntax checks
```

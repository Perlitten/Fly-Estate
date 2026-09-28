import {
  Component,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Canvas, type ThreeEvent } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import {
  Activity,
  Pause,
  Play,
  RotateCcw,
  Scan,
  ArrowRight,
  Info,
} from "lucide-react";
import type { Data, Listing } from "./types";
import { api, count, money } from "./api";
import Fly from "./Fly";
import { RatingButtons, decisions } from "./ApartmentCard";

const groups = [
  ["All neurons", "#a3bcc0"],
  ["Vision", "#43d9ea"],
  ["Kenyon cells", "#c39aff"],
  ["Navigation · CX", "#f7bf75"],
  ["Output · MBON", "#d5fc87"],
  ["Input · ALPN", "#82aaff"],
  ["Dopamine · DAN", "#f592ac"],
] as const;
type Geometry = {
  positions: Float32Array;
  groups: Float32Array;
  lines: Float32Array;
  n: number;
};
class SceneBoundary extends Component<
  { children: ReactNode },
  { error: boolean }
> {
  state = { error: false };
  static getDerivedStateFromError() {
    return { error: true };
  }
  render() {
    return this.state.error ? (
      <div className="scene-message">
        3D is unavailable in this browser. Open the project in Chrome with
        WebGL.
      </div>
    ) : (
      this.props.children
    );
  }
}
function Cloud({
  geometry,
  frame,
  group,
  onNeuron,
}: {
  geometry: Geometry;
  frame: Uint8Array | undefined;
  group: number;
  onNeuron: (i: number) => void;
}) {
  const geo = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute(
      "position",
      new THREE.BufferAttribute(geometry.positions, 3),
    );
    g.setAttribute("kind", new THREE.BufferAttribute(geometry.groups, 1));
    g.setAttribute(
      "activation",
      new THREE.BufferAttribute(new Uint8Array(geometry.n), 1, true),
    );
    return g;
  }, [geometry]);
  const lineGeo = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(geometry.lines, 3));
    return g;
  }, [geometry]);
  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        uniforms: { focus: { value: 0 } },
        vertexShader: `
 attribute float kind; attribute float activation; varying vec3 tint; varying float power; varying float visible;
 uniform float focus;
 void main(){
 vec3 c=vec3(.22,.43,.45);
 if(kind>0.5&&kind<1.5)c=vec3(.20,.85,.92);
 if(kind>1.5&&kind<2.5)c=vec3(.67,.42,1.);
 if(kind>2.5&&kind<3.5)c=vec3(1.,.66,.32);
 if(kind>3.5&&kind<4.5)c=vec3(.75,1.,.4);
 if(kind>4.5&&kind<5.5)c=vec3(.4,.63,1.);
 if(kind>5.5)c=vec3(1.,.35,.54);
 float selected=focus<0.5||abs(kind-focus)<.1?1.:.08;
 tint=c;power=(.09+activation*.91)*selected;visible=kind<0.?0.:1.;
 vec4 p=modelViewMatrix*vec4(position,1.);gl_Position=projectionMatrix*p;
 gl_PointSize=clamp((1.8+activation*6.)*4.5/-p.z,1.,12.);
 }`,
        fragmentShader: `
 varying vec3 tint;varying float power;varying float visible;
 void main(){float d=length(gl_PointCoord-.5)*2.;if(d>1.||visible<.5)discard;
 float glow=pow(1.-d,1.6);gl_FragColor=vec4(tint,power*glow);}
 `,
      }),
    [],
  );
  useEffect(() => {
    material.uniforms.focus.value = group;
  }, [group, material]);
  useEffect(() => {
    const a = geo.getAttribute("activation") as THREE.BufferAttribute;
    (a.array as Uint8Array).fill(0);
    if (frame) (a.array as Uint8Array).set(frame);
    a.needsUpdate = true;
  }, [frame, geo]);
  useEffect(
    () => () => {
      geo.dispose();
      lineGeo.dispose();
      material.dispose();
    },
    [geo, lineGeo, material],
  );
  return (
    <>
      <points
        geometry={geo}
        material={material}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          if (e.index !== undefined) onNeuron(e.index);
        }}
      />
      <lineSegments geometry={lineGeo}>
        <lineBasicMaterial
          color="#6ac4c5"
          transparent
          opacity={0.045}
          depthWrite={false}
        />
      </lineSegments>
    </>
  );
}
export default function BrainView({
  data,
  selected,
  onSelect,
  onRate,
  busy,
}: {
  data: Data;
  selected: Listing | undefined;
  onSelect: (id: string) => void;
  onRate: (id: string, v: number | null) => void;
  busy: boolean;
}) {
  const [geometry, setGeometry] = useState<Geometry>(),
    [frames, setFrames] = useState<Uint8Array>(),
    [step, setStep] = useState(0),
    [playing, setPlaying] = useState(true),
    [group, setGroup] = useState(0),
    [loading, setLoading] = useState(false),
    [error, setError] = useState(""),
    [neuron, setNeuron] = useState<{
      id: string;
      type: string;
      group: string;
      incoming: number;
      outgoing: number;
    }>(),
    [reset, setReset] = useState(0);
  const selectionSequence = useRef(0);
  const [photoSelection, setPhotoSelection] = useState({ id: "", index: -1 });
  const photoIndex =
    photoSelection.id === selected?.id &&
    photoSelection.index < (selected?.vision?.per_photo?.length || 0)
      ? photoSelection.index
      : -1;
  const photoSignal =
    photoIndex >= 0
      ? selected?.vision?.per_photo?.[photoIndex]
      : selected?.vision;
  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    Promise.all(
      ["/api/brain/geometry", "/api/brain/lines"].map(async (u) => {
        const r = await fetch(u, { signal: controller.signal });
        if (!r.ok) throw Error("Could not load neurons");
        return r.arrayBuffer();
      }),
    )
      .then(([p, l]) => {
        if (!alive) return;
        const raw = new Float32Array(p),
          n = raw.length / 4,
          pos = new Float32Array(n * 3),
          kinds = new Float32Array(n),
          edges = new Uint32Array(l),
          segments = new Float32Array(edges.length * 3);
        for (let i = 0; i < n; i++) {
          pos.set(raw.subarray(i * 4, i * 4 + 3), i * 3);
          kinds[i] = raw[i * 4 + 3];
        }
        for (let i = 0; i < edges.length; i++)
          segments.set(pos.subarray(edges[i] * 3, edges[i] * 3 + 3), i * 3);
        setGeometry({ positions: pos, groups: kinds, lines: segments, n });
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => {
      alive = false;
      controller.abort();
    };
  }, []);
  const settingsKey = JSON.stringify(data.settings);
  useEffect(() => {
    setStep(0);
    setFrames(undefined);
    setNeuron(undefined);
    setError("");
    if (!selected?.vision || selected.filter_reasons.length) return;
    const c = new AbortController();
    setLoading(true);
    fetch(
      "/api/brain/activity/" +
        selected.id +
        (photoIndex >= 0 ? "?photo=" + photoIndex : ""),
      { signal: c.signal },
    )
      .then(async (r) => {
        if (!r.ok) {
          const x = await r.json();
          throw Error(x.detail || "Computation failed");
        }
        return new Uint8Array(await r.arrayBuffer());
      })
      .then((f) => {
        setFrames(f);
        setLoading(false);
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => c.abort();
  }, [selected?.id, selected?.updated_at, settingsKey, photoIndex]);
  useEffect(() => {
    if (!playing || !frames) return;
    const t = setInterval(() => setStep((s) => (s + 1) % 16), 420);
    return () => clearInterval(t);
  }, [playing, frames]);
  const frame = useMemo(
    () =>
      geometry && frames
        ? frames.subarray(step * geometry.n, (step + 1) * geometry.n)
        : undefined,
    [geometry, frames, step],
  );
  const inspect = async (i: number) => {
    const seq = ++selectionSequence.current;
    try {
      const result = await api<{
        id: string;
        type: string;
        group: string;
        incoming: number;
        outgoing: number;
      }>("/api/brain/neuron/" + i);
      if (seq === selectionSequence.current) setNeuron(result);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const l = selected,
    eligible = data.listings.filter(
      (x) => !x.filter_reasons.length && x.vision,
    );
  const attributes = photoSignal?.attributes || {};
  const signals = [
    ["Natural light", attributes.natural_light],
    ["Spaciousness", attributes.spacious],
    ["Modern interior", attributes.modern],
    ["Visual clutter", attributes.clutter],
    ["Large balcony / loggia", attributes.large_balcony],
    ["Balcony shelter", attributes.sheltered_balcony],
  ] as const;
  return (
    <div className="brain-layout">
      <section className="brain-stage">
        <div className="stage-top">
          <div>
            <span className="eyebrow">LIVE CONNECTOME / v783</span>
            <h2>
              Watch it think<span className="mint">.</span>
            </h2>
          </div>
          <span className="simulation-badge">
            <span className="live-dot" />
            Computed activity
          </span>
        </div>
        <div className="brain-canvas" aria-label="Interactive 3D fly brain">
          <SceneBoundary>
            {geometry ? (
              <Canvas
                key={reset}
                dpr={[1, 1.5]}
                camera={{ position: [0, 0.1, 5.5], fov: 42 }}
                gl={{ antialias: false }}
                raycaster={{
                  params: {
                    Points: { threshold: 0.018 },
                    Line: { threshold: 0.01 },
                    Mesh: {},
                    LOD: {},
                    Sprite: {},
                  },
                }}
              >
                <Cloud
                  geometry={geometry}
                  frame={frame}
                  group={group}
                  onNeuron={inspect}
                />
                <OrbitControls
                  enablePan={false}
                  minDistance={2}
                  maxDistance={10}
                  autoRotate={playing}
                  autoRotateSpeed={0.35}
                />
              </Canvas>
            ) : (
              <div className="scene-message">
                {error || "Loading 139,248 neurons…"}
              </div>
            )}
          </SceneBoundary>
        </div>
        <div className="brain-corner">
          <span>01 — DROSOPHILA MELANOGASTER</span>
          <small>Rotate · zoom · select a neuron</small>
        </div>
        <button
          className="scene-reset"
          title="Reset camera"
          aria-label="Reset camera"
          onClick={() => setReset((v) => v + 1)}
        >
          <Scan size={18} />
        </button>
        {neuron && (
          <div className="neuron-inspector">
            <button
              onClick={() => setNeuron(undefined)}
              aria-label="Close neuron details"
            >
              ×
            </button>
            <span className="eyebrow">SELECTED NEURON</span>
            <strong>{neuron.type}</strong>
            <small>{neuron.group}</small>
            <code>{neuron.id}</code>
            <p>
              {count(neuron.incoming)} incoming · {count(neuron.outgoing)}{" "}
              outgoing connections
            </p>
          </div>
        )}
        <div className="brain-groups">
          {groups.map(([label, color], i) => (
            <button
              key={label}
              className={group === i ? "active" : ""}
              onClick={() => setGroup(i)}
            >
              <i style={{ background: color }} />
              {label}
            </button>
          ))}
        </div>
        <div className="timeline">
          <button
            disabled={!frames}
            onClick={() => setPlaying(!playing)}
            aria-label={playing ? "Pause activity" : "Play activity"}
          >
            {playing ? <Pause size={17} /> : <Play size={17} />}
          </button>
          <button
            disabled={!frames}
            onClick={() => {
              setStep(0);
              setPlaying(false);
            }}
            aria-label="Restart activity"
          >
            <RotateCcw size={16} />
          </button>
          <div>
            <div className="timeline-label">
              <b>
                {loading
                  ? "Propagating signals…"
                  : frames
                    ? "Signal travels through the brain"
                    : l?.filter_reasons.length
                      ? "Apartment excluded by filters"
                      : "Select an apartment with photos"}
              </b>
              <span>STEP {String(step + 1).padStart(2, "0")} / 16</span>
            </div>
            <input
              aria-label="Neural activity step"
              type="range"
              min="0"
              max="15"
              value={step}
              disabled={!frames}
              onChange={(e) => {
                setPlaying(false);
                setStep(+e.target.value);
              }}
            />
          </div>
          <Activity size={20} />
        </div>
        <div className="brain-source">
          <Info size={14} />
          <span>
            Real FlyWire positions and connections. Points are neuron locations;
            lines show a subset of connections. Brightness is our model’s
            activity, normalized within each step.
          </span>
          <a
            href="https://zenodo.org/records/10676866"
            target="_blank"
            rel="noreferrer"
          >
            Source ↗
          </a>
        </div>
        {error && geometry && <p className="inline-error">{error}</p>}
      </section>
      <aside className="brain-sidebar">
        <div className="side-heading">
          <span className="eyebrow">STIMULUS → RESPONSE</span>
          <h3>An apartment through fly eyes</h3>
        </div>
        <label className="select-label">
          Current listing
          <select
            value={l?.id || ""}
            onChange={(e) => onSelect(e.target.value)}
          >
            <option value="" disabled>
              Select an apartment
            </option>
            {eligible.map((x) => (
              <option key={x.id} value={x.id}>
                {money(x.price)} · {x.area} · {x.bedrooms} bed
              </option>
            ))}
          </select>
        </label>
        {l ? (
          <>
            <div className="stimulus-photo">
              {l.photos[Math.max(photoIndex, 0)] ? (
                <img src={l.photos[Math.max(photoIndex, 0)]} alt={l.title} />
              ) : (
                <div className="no-photo">Photo needed</div>
              )}
              <span>
                {money(l.price)} <small>/ month</small>
              </span>
            </div>
            <div className="photo-brain-controls">
              <button
                className={photoIndex === -1 ? "active" : ""}
                onClick={() => setPhotoSelection({ id: l.id, index: -1 })}
              >
                All {l.vision?.photos_analyzed || 0} photos
              </button>
              <button
                className={photoIndex >= 0 ? "active" : ""}
                aria-pressed={photoIndex >= 0}
                disabled={!l.vision?.per_photo?.length}
                onClick={() =>
                  setPhotoSelection({
                    id: l.id,
                    index: (Math.max(photoIndex, -1) + 1) % l.photos.length,
                  })
                }
              >
                {photoIndex < 0
                  ? "One at a time →"
                  : `Photo ${photoIndex + 1} / ${l.photos.length} →`}
              </button>
            </div>
            <p className="photo-coverage">
              Processed {l.vision?.photos_analyzed || 0} of{" "}
              {Math.max(l.photo_urls.length, l.photos.length)} photos
              {l.import_warnings.length > 0
                ? " · some photos unavailable"
                : " · every photo passed through the brain"}
            </p>
            <p className="stimulus-address">
              {l.bedrooms} bedrooms · {l.size} m² · {l.area}
            </p>
            <div className="signal-heading">
              <span>01</span>
              <b>
                {data.settings.mode === "cyborg"
                  ? "Image signals"
                  : "Light → retina"}
              </b>
              <small>
                {data.settings.mode === "cyborg" ? "CLIP" : "8 × 8 RGB"}
              </small>
            </div>
            {data.settings.mode === "cyborg" ? (
              <div className="signal-bars">
                {signals.map(([name, val]) => (
                  <div key={name}>
                    <span>{name}</span>
                    <div>
                      <i
                        style={{
                          width: `${Math.max(0, Math.min(1, val || 0)) * 100}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
                <small>Photo–text similarity · unverified properties</small>
              </div>
            ) : (
              <div className="retina-grid">
                {(photoSignal?.retina || [])
                  .filter((_, i) => i % 3 === 0)
                  .map((_, i) => (
                    <i
                      key={i}
                      style={{
                        background: `rgb(${photoSignal!.retina
                          .slice(i * 3, i * 3 + 3)
                          .map((x) => Math.round(x * 255))
                          .join(",")})`,
                      }}
                    />
                  ))}
              </div>
            )}
            <div className="space-signals">
              <div>
                <span>Room to fly</span>
                <b>+ {l.size} m²</b>
              </div>
              <div>
                <span>Balcony / loggia</span>
                <b>{l.balcony ? "+ available" : "Unconfirmed"}</b>
              </div>
              {l.balcony && (
                <small>
                  {l.balcony_size
                    ? "Stated area: " + l.balcony_size + " m²"
                    : "Area unspecified"}
                  {l.balcony_covered ? " · shelter available" : ""}
                </small>
              )}
            </div>
            <div className="sensory-factors">
              <div>
                <span>02</span>
                <b>Price</b>
                <small>{money(data.settings.budget)} target</small>
                <strong
                  className={l.price > data.settings.budget ? "price-over" : ""}
                >
                  {l.price > data.settings.budget ? "+" : ""}
                  {Math.round((l.price / data.settings.budget - 1) * 100)}%
                </strong>
              </div>
              <div>
                <span>03</span>
                <b>Location</b>
                <small>Straight-line distance from your preferred point</small>
                <strong>
                  {l.prediction.distance !== null
                    ? "≈ " + l.prediction.distance + " km"
                    : "Not set"}
                </strong>
              </div>
            </div>
            <div className={`fly-reaction ${l.prediction.decision}`}>
              <Fly />
              <div>
                <span className="eyebrow">MBON + CX OUTPUT</span>
                <strong>
                  {l.filter_reasons.length
                    ? "Excluded by filters"
                    : decisions[l.prediction.decision]}
                </strong>
                <small>
                  {data.training.ready && !l.filter_reasons.length
                    ? Math.round(l.prediction.probability * 100) +
                      "% · estimated similarity to your choices"
                    : "Rate apartments to teach it your preferences"}
                </small>
              </div>
            </div>
            {!l.filter_reasons.length && l.vision && (
              <RatingButtons listing={l} onRate={onRate} busy={busy} />
            )}
          </>
        ) : (
          <div className="empty-stimulus">
            <Fly />
            <h3>Your first apartment stimulus</h3>
            <p>
              Add listings with photos. Your fly will see the interior and send
              signals through its connections.
            </p>
            <ArrowRight size={24} />
          </div>
        )}
      </aside>
    </div>
  );
}

import {
  Component,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
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
import { token } from "./tokens";
import Fly from "./Fly";
import SpikingPanel from "./SpikingPanel";
import { Decrypt } from "./effects";
import { RatingButtons, decisions } from "./ApartmentCard";
import "./brain.css";

/*
 * Neuron groups. Index = the `kind` code from /api/brain/geometry (0 = every
 * other neuron). Colours are one categorical data scale (BRAND_KIT: data
 * palette exception); the chip dots and the shader read the same values.
 * "Other" is ~85 % of the brain, so it is the neutral night token at low power.
 */
const groups = [
  ["All neurons", "token:night-muted"],
  ["Vision", "#43d9ea"],
  ["Kenyon cells", "#c39aff"],
  ["Navigation · CX", "#f7bf75"],
  ["Output · MBON", "token:lime"],
  ["Input · ALPN", "#82aaff"],
  ["Dopamine · DAN", "#f592ac"],
] as const;
const resolveColour = (c: string) =>
  c.startsWith("token:") ? token(c.slice(6)) || "#8da39b" : c;
/* sRGB components as written by gl_FragColor (ShaderMaterial skips colour-space conversion). */
function rgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? [...h].map((x) => x + x).join("") : h;
  const v = parseInt(full.slice(0, 6), 16);
  return [((v >> 16) & 255) / 255, ((v >> 8) & 255) / 255, (v & 255) / 255];
}
/* Draw order: the bulk first, rare groups last so they stay on top. */
const DRAW_ORDER = [0, 1, 3, 2, 5, 6, 4];

/*
 * The 16 recorded frames are the 16 reservoir steps in server/brain.py. Inputs
 * (photo drive, listing facts on ALPN, location on CX) are clamped from step 1;
 * Kenyon cells light up at step 2, MBON/DAN from step 3, and by step 6 the
 * network only converges. Measured on a real listing: KC 0 → .32 → .39, MBON
 * .02 → .14 → .27, then < 3 % change per step.
 */
const FRAMES = 16;
const PLAY_SECONDS = 6;
/* Playhead u ∈ [0, 1] (time) → fractional frame f ∈ [-1, 15]; -1 is dark.
 * A monotone cubic through these knots gives each early stage about a second,
 * eases in from dark and eases out into the settled frame. */
const KNOT_U = [0, 0.08, 0.22, 0.36, 0.52, 1],
  KNOT_F = [-1, 0, 1, 2, 4.5, FRAMES - 1];
const KNOT_M = KNOT_U.map((_, k) => {
  const d = (i: number) =>
    (KNOT_F[i + 1] - KNOT_F[i]) / (KNOT_U[i + 1] - KNOT_U[i]);
  if (k === 0) return 0;
  if (k === KNOT_U.length - 1) return d(k - 1) * 0.3;
  const h0 = KNOT_U[k] - KNOT_U[k - 1],
    h1 = KNOT_U[k + 1] - KNOT_U[k],
    w0 = 2 * h1 + h0,
    w1 = h1 + 2 * h0;
  return (w0 + w1) / (w0 / d(k - 1) + w1 / d(k));
});
function frameAt(u: number) {
  let k = 0;
  while (k < KNOT_U.length - 2 && u > KNOT_U[k + 1]) k++;
  const h = KNOT_U[k + 1] - KNOT_U[k],
    t = Math.min(1, Math.max(0, (u - KNOT_U[k]) / h)),
    t2 = t * t,
    t3 = t2 * t;
  return (
    (2 * t3 - 3 * t2 + 1) * KNOT_F[k] +
    (t3 - 2 * t2 + t) * h * KNOT_M[k] +
    (-2 * t3 + 3 * t2) * KNOT_F[k + 1] +
    (t3 - t2) * h * KNOT_M[k + 1]
  );
}
const stages = [
  { until: 0.5, pure: "Photo reaches the eyes", cyborg: "Photo signals enter" },
  { until: 1.5, pure: "Kenyon cells pick it up" },
  { until: 4.5, pure: "Output neurons respond · MBON, DAN" },
  { until: 14.5, pure: "Activity settles" },
  { until: Infinity, pure: "Settled response · MBON + CX output" },
] as const;
const stageAt = (f: number) => stages.findIndex((s) => f < s.until);
type Playhead = { u: number; playing: boolean };

type Geometry = {
  positions: Float32Array;
  groups: Float32Array;
  lines: Float32Array;
  order: Uint32Array;
  n: number;
};
type ShellMesh = { positions: Float32Array; index: Uint16Array | Uint32Array };
/* public/data/brain-shell.bin, written by scripts/build_brain_shell.py. */
function parseShell(buf: ArrayBuffer): ShellMesh {
  const view = new DataView(buf);
  const magic = String.fromCharCode(...new Uint8Array(buf, 0, 4));
  if (magic !== "FBS1") throw Error("Unknown shell format");
  const v = view.getUint32(4, true),
    t = view.getUint32(8, true),
    width = view.getUint32(12, true),
    q = new Uint16Array(buf, 40, v * 3),
    positions = new Float32Array(v * 3);
  for (let a = 0; a < 3; a++) {
    const o = view.getFloat32(16 + a * 4, true),
      s = view.getFloat32(28 + a * 4, true);
    for (let i = a; i < v * 3; i += 3) positions[i] = o + q[i] * s;
  }
  let offset = 40 + v * 6;
  offset += (4 - (offset % 4)) % 4;
  const index =
    width === 2
      ? new Uint16Array(buf, offset, t * 3)
      : new Uint32Array(buf, offset, t * 3);
  return { positions, index };
}
function Shell({ mesh }: { mesh: ShellMesh }) {
  const geo = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(mesh.positions, 3));
    g.setIndex(new THREE.BufferAttribute(mesh.index, 1));
    g.computeVertexNormals();
    return g;
  }, [mesh]);
  const [back, front] = useMemo(() => {
    const core = rgb(token("night-line") || "#36544c"),
      rim = rgb(token("night-muted") || "#8da39b"),
      edge = rgb(token("leaf") || "#9dbb74");
    const make = (side: THREE.Side, a0: number, a1: number) =>
      new THREE.ShaderMaterial({
        transparent: true,
        depthWrite: false,
        side,
        uniforms: {
          core: { value: new THREE.Vector3(...core) },
          rim: { value: new THREE.Vector3(...rim) },
          edge: { value: new THREE.Vector3(...edge) },
          alpha: { value: new THREE.Vector2(a0, a1) },
        },
        vertexShader: `
 varying vec3 vNormal; varying vec3 vView;
 void main(){vec4 p=modelViewMatrix*vec4(position,1.);vNormal=normalMatrix*normal;vView=-p.xyz;gl_Position=projectionMatrix*p;}`,
        fragmentShader: `
 uniform vec3 core; uniform vec3 rim; uniform vec3 edge; uniform vec2 alpha;
 varying vec3 vNormal; varying vec3 vView;
 void main(){
 float facing=abs(dot(normalize(vNormal),normalize(vView)));
 float f=pow(1.-facing,2.4);
 vec3 c=mix(core,rim,smoothstep(0.,.7,f));c=mix(c,edge,smoothstep(.55,1.,f)*.35);
 gl_FragColor=vec4(c,mix(alpha.x,alpha.y,f));}`,
      });
    return [make(THREE.BackSide, 0.05, 0.1), make(THREE.FrontSide, 0.04, 0.34)];
  }, []);
  useEffect(
    () => () => {
      geo.dispose();
      back.dispose();
      front.dispose();
    },
    [geo, back, front],
  );
  return (
    <>
      <mesh geometry={geo} material={back} renderOrder={0} raycast={noRaycast} />
      <mesh geometry={geo} material={front} renderOrder={1} raycast={noRaycast} />
    </>
  );
}
const noRaycast = () => null;
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
  frames,
  head,
  group,
  palette,
  onTick,
  onNeuron,
}: {
  geometry: Geometry;
  frames: Uint8Array | undefined;
  head: RefObject<Playhead>;
  group: number;
  palette: Float32Array;
  onTick: (u: number, ended: boolean) => void;
  onNeuron: (i: number) => void;
}) {
  const dpr = useThree((s) => s.viewport.dpr);
  const geo = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute(
      "position",
      new THREE.BufferAttribute(geometry.positions, 3),
    );
    g.setAttribute("kind", new THREE.BufferAttribute(geometry.groups, 1));
    // Two frames on the GPU; the shader blends them, so playback uploads only on step changes.
    for (const name of ["actA", "actB"])
      g.setAttribute(
        name,
        new THREE.BufferAttribute(new Uint8Array(geometry.n), 1, true),
      );
    g.setIndex(new THREE.BufferAttribute(geometry.order, 1));
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
        // Normal blending: dense regions converge to the group colour instead of white.
        uniforms: {
          focus: { value: 0 },
          blend: { value: 0 },
          scale: { value: 4.5 },
          palette: { value: palette },
        },
        vertexShader: `
 attribute float kind; attribute float actA; attribute float actB;
 uniform float focus; uniform float blend; uniform float scale; uniform vec3 palette[7];
 varying vec3 tint; varying float power;
 void main(){
 if(kind<0.){gl_Position=vec4(2.,2.,2.,1.);gl_PointSize=0.;power=0.;return;}
 int k=int(kind+.5);
 float act=mix(actA,actB,blend);
 bool other=k==0; bool rare=k>=4;
 tint=palette[k];
 float base=other?.06:rare?.55:.14;
 float gain=other?.28:rare?.45:.66;
 float selected=focus<.5||abs(kind-focus)<.1?1.:.05;
 power=min(1.,base+act*gain)*selected;
 float size=(other?1.3:rare?4.2:1.9)+act*(other?2.:rare?3.:4.);
 vec4 p=modelViewMatrix*vec4(position,1.);gl_Position=projectionMatrix*p;
 gl_PointSize=clamp(size*scale/-p.z,1.,16.);
 }`,
        fragmentShader: `
 varying vec3 tint;varying float power;
 void main(){float d=length(gl_PointCoord-.5)*2.;if(d>1.)discard;
 gl_FragColor=vec4(tint,power*(1.-smoothstep(.35,1.,d)));}
 `,
      }),
    [palette],
  );
  useEffect(() => {
    material.uniforms.focus.value = group;
  }, [group, material]);
  useEffect(() => {
    material.uniforms.scale.value = 4.5 * dpr;
  }, [dpr, material]);
  // Which frame pair is on the GPU; -2 forces a reload after new frames arrive.
  const loaded = useRef(-2);
  const zeros = useMemo(() => new Uint8Array(geometry.n), [geometry]);
  useEffect(() => {
    loaded.current = -2;
  }, [frames, geo]);
  useFrame((_, delta) => {
    const h = head.current;
    if (!h) return;
    if (h.playing && frames) {
      h.u = Math.min(1, h.u + delta / PLAY_SECONDS);
      if (h.u >= 1) h.playing = false;
      onTick(h.u, !h.playing);
    }
    const f = frames ? frameAt(h.u) : -1;
    const s = Math.min(FRAMES - 2, Math.floor(f));
    if (s !== loaded.current) {
      const a = geo.getAttribute("actA") as THREE.BufferAttribute,
        b = geo.getAttribute("actB") as THREE.BufferAttribute,
        n = geometry.n;
      const frame = (i: number) =>
        frames && i >= 0 ? frames.subarray(i * n, (i + 1) * n) : zeros;
      (a.array as Uint8Array).set(frame(s));
      (b.array as Uint8Array).set(frame(s + 1));
      a.needsUpdate = b.needsUpdate = true;
      loaded.current = s;
    }
    material.uniforms.blend.value = Math.min(1, Math.max(0, f - s));
  });
  useEffect(
    () => () => {
      geo.dispose();
      lineGeo.dispose();
      material.dispose();
    },
    [geo, lineGeo, material],
  );
  const lineColour = useMemo(() => token("night-muted") || "#8da39b", []);
  return (
    <>
      <lineSegments geometry={lineGeo} renderOrder={2} raycast={noRaycast}>
        <lineBasicMaterial
          color={lineColour}
          transparent
          opacity={0.04}
          depthWrite={false}
        />
      </lineSegments>
      <points
        geometry={geo}
        material={material}
        renderOrder={3}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          if (e.index !== undefined) onNeuron(e.index);
        }}
      />
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
    [shell, setShell] = useState<ShellMesh>(),
    [showShell, setShowShell] = useState(true),
    [playing, setPlaying] = useState(false),
    [stage, setStage] = useState(stages.length - 1),
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
  // Playback lives in a ref and is advanced inside the render loop; React only
  // hears about stage changes and the end, the slider is moved through its ref.
  const head = useRef<Playhead>({ u: 1, playing: false }),
    slider = useRef<HTMLInputElement>(null),
    stageRef = useRef(stage);
  const reducedMotion = useMemo(
    () => matchMedia("(prefers-reduced-motion: reduce)").matches,
    [],
  );
  const colours = useMemo(() => groups.map(([, c]) => resolveColour(c)), []);
  const palette = useMemo(
    () => new Float32Array(colours.flatMap((c) => rgb(c))),
    [colours],
  );
  const sync = (u: number) => {
    if (slider.current) slider.current.value = String(Math.round(u * 1000));
    const s = stageAt(frameAt(u));
    if (s !== stageRef.current) {
      stageRef.current = s;
      setStage(s);
    }
  };
  const onTick = (u: number, ended: boolean) => {
    sync(u);
    if (ended) setPlaying(false);
  };
  const play = (from?: number) => {
    const h = head.current;
    if (from !== undefined || h.u >= 1) h.u = from ?? 0;
    h.playing = true;
    sync(h.u);
    setPlaying(true);
  };
  const pause = () => {
    head.current.playing = false;
    setPlaying(false);
  };
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
        const order = new Uint32Array(n);
        let k = 0;
        for (const code of [-1, ...DRAW_ORDER])
          for (let i = 0; i < n; i++) if (kinds[i] === code) order[k++] = i;
        setGeometry({ positions: pos, groups: kinds, lines: segments, order, n });
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    fetch("/data/brain-shell.bin", { signal: controller.signal })
      .then((r) => {
        if (!r.ok) throw Error("No brain shell");
        return r.arrayBuffer();
      })
      .then((b) => alive && setShell(parseShell(b)))
      // The envelope is decoration around real data; without it the cloud still works.
      .catch(() => undefined);
    return () => {
      alive = false;
      controller.abort();
    };
  }, []);
  const settingsKey = JSON.stringify(data.settings);
  useEffect(() => {
    pause();
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
        // Play once per listing or photo and stop on the settled response.
        if (reducedMotion) {
          head.current.u = 1;
          sync(1);
        } else play(0);
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => c.abort();
  }, [selected?.id, selected?.updated_at, settingsKey, photoIndex]);
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
  const stageInfo = stages[stage];
  const stageName =
    "cyborg" in stageInfo && data.settings.mode === "cyborg"
      ? stageInfo.cyborg
      : stageInfo.pure;
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
              Working on your file<span className="mint">.</span>
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
                {shell && showShell && <Shell mesh={shell} />}
                <Cloud
                  geometry={geometry}
                  frames={frames}
                  head={head}
                  group={group}
                  palette={palette}
                  onTick={onTick}
                  onNeuron={inspect}
                />
                <OrbitControls
                  enablePan={false}
                  minDistance={2}
                  maxDistance={10}
                  autoRotate={playing && !reducedMotion}
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
          {groups.map(([label], i) => (
            <button
              key={label}
              className={group === i ? "active" : ""}
              aria-pressed={group === i}
              onClick={() => setGroup(i)}
            >
              <i style={{ background: colours[i] }} />
              {label}
            </button>
          ))}
          <button
            className={"shell-toggle" + (showShell && shell ? " active" : "")}
            aria-pressed={showShell && !!shell}
            disabled={!shell}
            title="Brain outline built from the neuron positions"
            onClick={() => setShowShell((v) => !v)}
          >
            <i />
            Shell
          </button>
        </div>
        <div className="timeline">
          <button
            disabled={!frames}
            onClick={() => (playing ? pause() : play())}
            aria-label={playing ? "Pause replay" : "Play replay"}
          >
            {playing ? <Pause size={17} /> : <Play size={17} />}
          </button>
          <button
            disabled={!frames}
            onClick={() => play(0)}
            aria-label="Replay from the start"
            title="Replay from the start"
          >
            <RotateCcw size={16} />
          </button>
          <div>
            <div className="timeline-label">
              <b aria-live="polite">
                {loading
                  ? "Propagating signals…"
                  : frames
                    ? stageName
                    : l?.filter_reasons.length
                      ? "Apartment excluded by filters"
                      : "Select an apartment with photos"}
              </b>
              {frames && !loading && (
                <span>
                  {stage + 1} / {stages.length}
                </span>
              )}
            </div>
            <input
              ref={slider}
              aria-label="Replay position"
              aria-valuetext={frames ? stageName : undefined}
              type="range"
              min="0"
              max="1000"
              step="1"
              defaultValue="1000"
              disabled={!frames}
              onInput={(e) => {
                pause();
                head.current.u = +e.currentTarget.value / 1000;
                sync(head.current.u);
              }}
            />
            <p className="timeline-note">
              {photoIndex >= 0
                ? `Replay how photo ${photoIndex + 1} spreads through the brain.`
                : "Replay how this listing’s photos spread through the brain."}{" "}
              Drag to inspect any moment.
            </p>
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
          <h3>The listing, as your agent sees it</h3>
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
                <span>Floor area</span>
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
            {l.vision?.per_photo?.length ? (
              <SpikingPanel
                listing={l}
                settingsKey={settingsKey}
                photoIndex={photoIndex}
                onPhoto={(index) => setPhotoSelection({ id: l.id, index })}
              />
            ) : null}
            <div className={`fly-reaction ${l.prediction.decision}`}>
              <Fly />
              <div>
                <span className="eyebrow">VERDICT · MBON + CX OUTPUT</span>
                <strong>
                  <Decrypt
                    text={
                      l.filter_reasons.length
                        ? "Excluded by filters"
                        : decisions[l.prediction.decision]
                    }
                  />
                </strong>
                <small>
                  {data.training.ready && !l.filter_reasons.length
                    ? Math.round(l.prediction.probability * 100) +
                      "% · estimated similarity to your choices"
                    : "Rate a few listings to brief your agent"}
                </small>
              </div>
            </div>
            {!l.filter_reasons.length && l.vision && (
              <RatingButtons listing={l} onRate={onRate} busy={busy} />
            )}
          </>
        ) : (
          <div className="empty-stimulus">
            <h3>No listing on file yet</h3>
            <p>
              Add listings with photos. Your agent will inspect the interior and
              pass the signals through its connections.
            </p>
            <ArrowRight size={24} />
          </div>
        )}
      </aside>
    </div>
  );
}

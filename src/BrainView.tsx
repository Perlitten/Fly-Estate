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
  ["Все нейроны", "#a3bcc0"],
  ["Зрение", "#43d9ea"],
  ["Kenyon cells", "#c39aff"],
  ["Навигация · CX", "#f7bf75"],
  ["Выход · MBON", "#d5fc87"],
  ["Вход · ALPN", "#82aaff"],
  ["Дофамин · DAN", "#f592ac"],
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
        3D недоступен в этом браузере. Открой проект в Chrome с включённым
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
        if (!r.ok) throw Error("Не удалось загрузить нейроны");
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
          throw Error(x.detail || "Ошибка расчёта");
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
    ["Естественный свет", attributes.natural_light],
    ["Простор", attributes.spacious],
    ["Современный интерьер", attributes.modern],
    ["Визуальный шум", attributes.clutter],
    ["Большой балкон / лоджия", attributes.large_balcony],
    ["Укрытие на балконе", attributes.sheltered_balcony],
  ] as const;
  return (
    <div className="brain-layout">
      <section className="brain-stage">
        <div className="stage-top">
          <div>
            <span className="eyebrow">LIVE CONNECTOME / v783</span>
            <h2>
              Посмотри, как она думает<span className="mint">.</span>
            </h2>
          </div>
          <span className="simulation-badge">
            <span className="live-dot" />
            Расчётная активность
          </span>
        </div>
        <div className="brain-canvas" aria-label="Интерактивный 3D-мозг мухи">
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
                {error || "Загружаю 139 248 нейронов…"}
              </div>
            )}
          </SceneBoundary>
        </div>
        <div className="brain-corner">
          <span>01 — DROSOPHILA MELANOGASTER</span>
          <small>Вращай · приближай · нажми на нейрон</small>
        </div>
        <button
          className="scene-reset"
          title="Сбросить камеру"
          aria-label="Сбросить камеру"
          onClick={() => setReset((v) => v + 1)}
        >
          <Scan size={18} />
        </button>
        {neuron && (
          <div className="neuron-inspector">
            <button
              onClick={() => setNeuron(undefined)}
              aria-label="Закрыть нейрон"
            >
              ×
            </button>
            <span className="eyebrow">ВЫБРАННЫЙ НЕЙРОН</span>
            <strong>{neuron.type}</strong>
            <small>{neuron.group}</small>
            <code>{neuron.id}</code>
            <p>
              {count(neuron.incoming)} входящих · {count(neuron.outgoing)}{" "}
              исходящих связей
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
            aria-label={
              playing ? "Приостановить активность" : "Воспроизвести активность"
            }
          >
            {playing ? <Pause size={17} /> : <Play size={17} />}
          </button>
          <button
            disabled={!frames}
            onClick={() => {
              setStep(0);
              setPlaying(false);
            }}
            aria-label="В начало расчёта"
          >
            <RotateCcw size={16} />
          </button>
          <div>
            <div className="timeline-label">
              <b>
                {loading
                  ? "Распространяю сигналы…"
                  : frames
                    ? "Сигнал проходит по мозгу"
                    : l?.filter_reasons.length
                      ? "Квартира исключена фильтрами"
                      : "Выбери квартиру с фото"}
              </b>
              <span>ШАГ {String(step + 1).padStart(2, "0")} / 16</span>
            </div>
            <input
              aria-label="Шаг нейронной активности"
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
            Реальные координаты и связи FlyWire. Точки — позиции нейронов, линии
            — часть связей. Яркость — активность нашей модели, нормированная
            внутри каждого шага.
          </span>
          <a
            href="https://zenodo.org/records/10676866"
            target="_blank"
            rel="noreferrer"
          >
            Источник ↗
          </a>
        </div>
        {error && geometry && <p className="inline-error">{error}</p>}
      </section>
      <aside className="brain-sidebar">
        <div className="side-heading">
          <span className="eyebrow">СТИМУЛ → РЕАКЦИЯ</span>
          <h3>Квартира глазами мухи</h3>
        </div>
        <label className="select-label">
          Текущее объявление
          <select
            value={l?.id || ""}
            onChange={(e) => onSelect(e.target.value)}
          >
            <option value="" disabled>
              Выбери квартиру
            </option>
            {eligible.map((x) => (
              <option key={x.id} value={x.id}>
                {money(x.price)} · {x.area} · {x.bedrooms} сп.
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
                <div className="no-photo">Нужно фото</div>
              )}
              <span>
                {money(l.price)} <small>/ мес.</small>
              </span>
            </div>
            <div className="photo-brain-controls">
              <button
                className={photoIndex === -1 ? "active" : ""}
                onClick={() => setPhotoSelection({ id: l.id, index: -1 })}
              >
                Все {l.vision?.photos_analyzed || 0} фото
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
                  ? "По одному →"
                  : `Фото ${photoIndex + 1} / ${l.photos.length} →`}
              </button>
            </div>
            <p className="photo-coverage">
              Обработано {l.vision?.photos_analyzed || 0} из{" "}
              {Math.max(l.photo_urls.length, l.photos.length)} фото
              {l.import_warnings.length > 0
                ? " · часть фото недоступна"
                : " · каждый снимок прошёл через мозг"}
            </p>
            <p className="stimulus-address">
              {l.bedrooms} спальни · {l.size} м² · {l.area}
            </p>
            <div className="signal-heading">
              <span>01</span>
              <b>
                {data.settings.mode === "cyborg"
                  ? "Сигналы изображения"
                  : "Свет → сетчатка"}
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
                <small>
                  Сходство фото с описанием · не проверенные свойства
                </small>
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
                <span>Простор для полётов</span>
                <b>+ {l.size} м²</b>
              </div>
              <div>
                <span>Балкон / лоджия</span>
                <b>{l.balcony ? "+ есть" : "Не подтверждён"}</b>
              </div>
              {l.balcony && (
                <small>
                  {l.balcony_size
                    ? "Указанная площадь: " + l.balcony_size + " м²"
                    : "Площадь не указана"}
                  {l.balcony_covered ? " · есть укрытие" : ""}
                </small>
              )}
            </div>
            <div className="sensory-factors">
              <div>
                <span>02</span>
                <b>Цена</b>
                <small>{money(data.settings.budget)} ориентир</small>
                <strong
                  className={l.price > data.settings.budget ? "price-over" : ""}
                >
                  {l.price > data.settings.budget ? "+" : ""}
                  {Math.round((l.price / data.settings.budget - 1) * 100)}%
                </strong>
              </div>
              <div>
                <span>03</span>
                <b>Расположение</b>
                <small>От идеальной точки, по прямой</small>
                <strong>
                  {l.prediction.distance !== null
                    ? "≈ " + l.prediction.distance + " км"
                    : "Не задано"}
                </strong>
              </div>
            </div>
            <div className={`fly-reaction ${l.prediction.decision}`}>
              <Fly />
              <div>
                <span className="eyebrow">ВЫХОД MBON + CX</span>
                <strong>
                  {l.filter_reasons.length
                    ? "Исключена фильтрами"
                    : decisions[l.prediction.decision]}
                </strong>
                <small>
                  {data.training.ready && !l.filter_reasons.length
                    ? Math.round(l.prediction.probability * 100) +
                      "% · оценка сходства с твоими выборами"
                    : "Дай ей свои оценки, чтобы обучить предпочтения"}
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
            <h3>Первый квартирный стимул</h3>
            <p>
              Добавь объявления с фотографиями. Муха увидит интерьер и запустит
              сигналы по своим связям.
            </p>
            <ArrowRight size={24} />
          </div>
        )}
      </aside>
    </div>
  );
}

import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  X,
  Upload,
  Link,
  FileText,
  Plus,
  Check,
  LoaderCircle,
  Download,
  MapPin,
  Search,
  ChevronDown,
} from "lucide-react";
import { api } from "./api";
import type { Data, Settings, Job } from "./types";

function areaNames(data: Data) {
  return Array.from(
    new Set([
      ...Object.keys(data.areas),
      ...data.listings
        .filter((listing) => (listing.city || "").toLowerCase() === "limassol")
        .map((listing) => listing.area),
      ...data.settings.excluded,
    ]),
  )
    .filter((name) => name.trim() && name !== "Area unspecified")
    .sort((a, b) => a.localeCompare(b, "en"));
}

function ExcludedAreas({
  options,
  value,
  onChange,
}: {
  options: string[];
  value: string[];
  onChange: (areas: string[]) => void;
}) {
  const [query, setQuery] = useState("");
  const visible = options.filter((area) =>
    area.toLowerCase().includes(query.trim().toLowerCase()),
  );
  return (
    <fieldset className="excluded-areas">
      <legend>Areas to avoid</legend>
      <div className="area-selection" aria-label="Selected excluded areas">
        {value.length ? (
          value.map((area) => (
            <button
              key={area}
              type="button"
              className="area-chip"
              aria-label={`Include ${area} again`}
              onClick={() => onChange(value.filter((item) => item !== area))}
            >
              {area} <X size={13} />
            </button>
          ))
        ) : (
          <span>No areas excluded</span>
        )}
      </div>
      <details className="area-picker">
        <summary>
          Choose areas <ChevronDown size={16} />
        </summary>
        <label className="area-search">
          <Search size={16} aria-hidden="true" />
          <input
            type="search"
            aria-label="Find an area to exclude"
            placeholder="Find an area…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <div className="area-options">
          {visible.map((area) => (
            <label key={area} className="checkbox-label">
              <input
                type="checkbox"
                checked={value.includes(area)}
                disabled={!value.includes(area) && value.length >= 30}
                onChange={(event) =>
                  onChange(
                    event.target.checked
                      ? [...value, area]
                      : value.filter((item) => item !== area),
                  )
                }
              />
              {area}
            </label>
          ))}
          {!visible.length && <p>No matching areas.</p>}
        </div>
      </details>
    </fieldset>
  );
}

export function Modal({
  title,
  children,
  onClose,
  className = "",
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      className={`modal ${className}`}
      aria-labelledby={titleId}
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal-header">
        <h2 id={titleId}>{title}</h2>
        <button aria-label="Close dialog" onClick={onClose}>
          <X size={21} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function SettingsDialog({
  data,
  onSave,
  onClose,
}: {
  data: Data;
  onSave: (s: Settings) => Promise<void>;
  onClose: () => void;
}) {
  const [s, setS] = useState(data.settings),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [customRadius, setCustomRadius] = useState(false);
  const areas = areaNames(data);
  // Source names can share a centre. Group them so the selected label stays
  // stable when the same coordinates are stored under two different names.
  const areaCentres = new Map<string, { name: string; labels: string[] }>();
  for (const [name, area] of Object.entries(data.areas)) {
    const key = area.coords.join(",");
    const centre = areaCentres.get(key);
    if (centre) centre.labels.push(name);
    else areaCentres.set(key, { name, labels: [name] });
  }
  const areaOptions = Array.from(areaCentres.values()).sort((a, b) =>
    a.name.localeCompare(b.name, "en"),
  );
  const preferredArea =
    Object.entries(data.areas).find(([, area]) =>
      area.coords.every(
        (coordinate, index) => Math.abs(coordinate - s.ideal[index]) < 0.000001,
      ),
    )?.[0] || "";
  const radii = Array.from(new Set([1, 3, 5, 10, 20, 30, s.radius])).sort(
    (a, b) => a - b,
  );
  const change = <K extends keyof Settings>(key: K, value: Settings[K]) =>
    setS((x) => ({ ...x, [key]: value }));
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await onSave(s);
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="Client brief" className="brief-modal" onClose={onClose}>
      <form onSubmit={submit} className="settings-form">
        <div className="brief-body">
          <p className="muted">
            Where should your agent look, and what must an apartment have?
          </p>
          <fieldset className="brief-section">
            <legend>
              <MapPin size={16} /> Location
            </legend>
            <div className="form-grid">
              <label>
                City
                <select
                  defaultValue="Limassol"
                  aria-describedby="city-coverage"
                >
                  <option value="Limassol">Limassol</option>
                </select>
              </label>
              <label>
                Preferred area
                <select
                  value={preferredArea}
                  onChange={(event) => {
                    const area = data.areas[event.target.value];
                    change(
                      "ideal",
                      area ? [...area.coords] : [...data.settings.ideal],
                    );
                  }}
                >
                  <option value="">Custom point on map</option>
                  {areaOptions.map((area) => (
                    <option key={area.name} value={area.name}>
                      {area.labels.join(" / ")}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <p className="field-note" id="city-coverage">
              Search currently covers Limassol district. Pick an area centre or
              keep your custom point on the map.
            </p>
            <label>
              Preferred radius
              <select
                value={customRadius ? "custom" : s.radius}
                onChange={(event) => {
                  setCustomRadius(event.target.value === "custom");
                  if (event.target.value !== "custom")
                    change("radius", +event.target.value);
                }}
              >
                {radii.map((radius) => (
                  <option key={radius} value={radius}>
                    Within {radius} km
                  </option>
                ))}
                <option value="custom">Custom distance…</option>
              </select>
            </label>
            {customRadius && (
              <label>
                Distance, km
                <input
                  required
                  type="number"
                  min="0.1"
                  max="30"
                  step="0.1"
                  value={s.radius}
                  onChange={(event) => change("radius", +event.target.value)}
                />
              </label>
            )}
            <ExcludedAreas
              options={areas}
              value={s.excluded}
              onChange={(areas) => change("excluded", areas)}
            />
          </fieldset>
          <fieldset className="brief-section">
            <legend>Budget & essentials</legend>
            <div className="form-grid">
              <label>
                Target budget, €
                <input
                  required
                  type="number"
                  min="100"
                  max="20000"
                  value={s.budget}
                  onChange={(e) => change("budget", +e.target.value)}
                />
              </label>
              <label>
                Hard limit, €
                <input
                  required
                  type="number"
                  min={s.budget}
                  max="100000"
                  value={s.ceiling}
                  onChange={(e) => change("ceiling", +e.target.value)}
                />
              </label>
              <label>
                Minimum bedrooms
                <select
                  value={s.min_bedrooms}
                  onChange={(e) => change("min_bedrooms", +e.target.value)}
                >
                  {Array.from(new Set([0, 1, 2, 3, 4, 5, s.min_bedrooms]))
                    .sort((a, b) => a - b)
                    .map((x) => (
                      <option key={x} value={x}>
                        {x === 0 ? "Studio or more" : `${x}+ bedrooms`}
                      </option>
                    ))}
                </select>
              </label>
            </div>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={s.covered_parking}
                onChange={(e) => change("covered_parking", e.target.checked)}
              />
              <span>
                <b>Covered parking required</b>
                <small>
                  Uncovered and unspecified parking are excluded too
                </small>
              </span>
            </label>
          </fieldset>
          <p className="muted">
            Only “Save brief” applies your changes. Your brief is saved on this
            computer.
          </p>
          {error && (
            <p className="inline-error" role="alert">
              {error}
            </p>
          )}
        </div>
        <div className="brief-actions">
          <button className="primary" disabled={busy}>
            <Check size={17} />
            Save brief
          </button>
          <a className="backup-link" href="/api/export" download>
            <Download size={16} />
            Download my listings and ratings
          </a>
          <a className="backup-link" href="/api/session/export" download>
            <Download size={16} />
            Download full session · photos and brain memory
          </a>
          <details className="learning-method">
            <summary>Restore a full session on another computer</summary>
            <p>
              Use the matching model code, stop Fly Estate, place the ZIP in the
              project folder, then run{" "}
              <code>
                .venv/bin/python -m server.session restore
                fly-estate-session.zip
              </code>
              . Start the project again. The archive restores photos, choices,
              exact checkpoints and recorded results; the previous local session
              is kept in .cache/session-restores.
            </p>
          </details>
        </div>
      </form>
    </Modal>
  );
}
const bookmarklet =
  "javascript:(()=>{const scripts=[...document.querySelectorAll('script[type=\"application/ld+json\"]')].map(x=>{try{return JSON.parse(x.textContent)}catch{return null}}).filter(Boolean);const content=scripts.length?JSON.stringify(scripts):document.documentElement.outerHTML;const text=JSON.stringify({url:location.href,content});navigator.clipboard.writeText(text).then(()=>alert('Listing copied. Paste it into Fly Estate → JSON / HTML.')).catch(()=>prompt('Copy this listing:',text))})()";
export function ImportDialog({
  data,
  onDone,
  onClose,
}: {
  data: Data;
  onDone: () => Promise<void>;
  onClose: () => void;
}) {
  const [tab, setTab] = useState("url"),
    [url, setUrl] = useState(""),
    [content, setContent] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [job, setJob] = useState<Job>(),
    [files, setFiles] = useState<File[]>([]),
    [otherArea, setOtherArea] = useState(false),
    [manual, setManual] = useState({
      title: "",
      price: 1800,
      bedrooms: 2,
      size: 90,
      area: "Agios Athanasios",
      parking: "unknown",
      city: "Limassol",
      furnished: false,
      balcony: false,
      balcony_size: "",
      balcony_covered: false,
    });
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined),
    alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    const resume = sessionStorage.getItem("fly-estate-job");
    if (resume) {
      setBusy(true);
      timer.current = setTimeout(() => poll(resume), 0);
    }
    return () => {
      alive.current = false;
      clearTimeout(timer.current);
    };
  }, []);
  const poll = async (id: string) => {
    try {
      const j = await api<Job>("/api/jobs/" + id);
      if (!alive.current) return;
      setJob(j);
      if (j.status === "running") {
        timer.current = setTimeout(() => poll(id), 1500);
      } else {
        sessionStorage.removeItem("fly-estate-job");
        setBusy(false);
        if (j.status === "error") setError(j.error || "Import failed");
        await onDone();
      }
    } catch (e) {
      if (alive.current) {
        setBusy(false);
        setError((e as Error).message);
      }
    }
  };
  const start = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setJob(undefined);
    setBusy(true);
    try {
      let payload: Record<string, unknown> = {};
      if (tab === "url") payload = { url };
      else if (tab === "content") {
        let parsed;
        try {
          parsed = JSON.parse(content);
        } catch {
          /* HTML or plain text */
        }
        payload = parsed && parsed.content ? parsed : { content };
      } else {
        const uploads = await Promise.all(
          files.map(
            (f) =>
              new Promise<string>((resolve, reject) => {
                const r = new FileReader();
                r.onload = () => resolve(String(r.result));
                r.onerror = reject;
                r.readAsDataURL(f);
              }),
          ),
        );
        payload = {
          listing: {
            ...manual,
            url,
            balcony_size: manual.balcony_size
              ? Number(manual.balcony_size)
              : null,
          },
          uploads,
        };
      }
      const r = await api<{ job: string }>("/api/import", "POST", payload);
      sessionStorage.setItem("fly-estate-job", r.job);
      await poll(r.job);
    } catch (e) {
      setBusy(false);
      setError((e as Error).message);
    }
  };
  return (
    <Modal title="Add listings" onClose={onClose}>
      <div className="dialog-tabs">
        {[
          ["url", "Link", Link],
          ["content", "JSON / HTML", FileText],
          ["manual", "Manual", Plus],
        ].map(([key, label, Icon]) => (
          <button
            key={String(key)}
            disabled={busy}
            className={tab === key ? "active" : ""}
            onClick={() => setTab(String(key))}
          >
            {typeof Icon !== "string" && <Icon size={16} />} {String(label)}
          </button>
        ))}
      </div>
      <form onSubmit={start} className="import-form">
        {tab === "url" ? (
          <>
            <label>
              Listing URL
              <input
                required
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.bazaraki.com/adv/…"
              />
            </label>
            <p className="muted">
              Bazaraki adverts import directly. “Search Bazaraki” on the area
              map finds them for you. RentSpot, Fox and INDEX pages also work;
              for pages that need a browser check, use JSON / HTML.
            </p>
          </>
        ) : tab === "content" ? (
          <>
            <label>
              Listing data
              <textarea
                required
                aria-label="Listing data"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Paste JSON, JSON-LD, page HTML or listing text"
                rows={8}
              />
            </label>
            <details>
              <summary>How to import a listing from your browser</summary>
              <p>
                Drag the button to your bookmarks bar. Open a listing, click the
                bookmark and paste the result above. It copies data from the
                current page.
              </p>
              <a
                className="bookmarklet"
                href="#"
                ref={(el) => {
                  if (el) el.setAttribute("href", bookmarklet);
                }}
                onClick={(e) => e.preventDefault()}
              >
                To Fly Estate
              </a>
              <small>
                If the site prevents saving the bookmark, copy the page HTML or
                fill in a listing manually.
              </small>
            </details>
          </>
        ) : (
          <>
            <label>
              Title
              <input
                required
                value={manual.title}
                onChange={(e) =>
                  setManual((x) => ({ ...x, title: e.target.value }))
                }
              />
            </label>
            <div className="form-grid">
              <label>
                Monthly rent, €
                <input
                  required
                  type="number"
                  min="100"
                  max="100000"
                  value={manual.price}
                  onChange={(e) =>
                    setManual((x) => ({ ...x, price: +e.target.value }))
                  }
                />
              </label>
              <label>
                Floor area, m²
                <input
                  type="number"
                  min="10"
                  max="5000"
                  value={manual.size}
                  onChange={(e) =>
                    setManual((x) => ({ ...x, size: +e.target.value }))
                  }
                />
              </label>
              <label>
                Bedrooms
                <input
                  type="number"
                  min="0"
                  max="20"
                  value={manual.bedrooms}
                  onChange={(e) =>
                    setManual((x) => ({ ...x, bedrooms: +e.target.value }))
                  }
                />
              </label>
              <label>
                Parking
                <select
                  value={manual.parking}
                  onChange={(e) =>
                    setManual((x) => ({ ...x, parking: e.target.value }))
                  }
                >
                  <option value="unknown">Unspecified</option>
                  <option value="covered">Covered</option>
                  <option value="uncovered">Uncovered</option>
                  <option value="none">None</option>
                </select>
              </label>
            </div>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={manual.balcony}
                onChange={(e) =>
                  setManual((x) => ({ ...x, balcony: e.target.checked }))
                }
              />
              Balcony or loggia
            </label>
            {manual.balcony && (
              <>
                <label>
                  Balcony area, m² (if stated)
                  <input
                    type="number"
                    min="0.1"
                    max="499"
                    step="0.1"
                    value={manual.balcony_size}
                    onChange={(e) =>
                      setManual((x) => ({ ...x, balcony_size: e.target.value }))
                    }
                  />
                </label>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={manual.balcony_covered}
                    onChange={(e) =>
                      setManual((x) => ({
                        ...x,
                        balcony_covered: e.target.checked,
                      }))
                    }
                  />
                  Covered balcony / enclosed loggia
                </label>
              </>
            )}
            <div className="form-grid">
              <label>
                City
                <select
                  value={manual.city}
                  onChange={(event) =>
                    setManual((x) => ({ ...x, city: event.target.value }))
                  }
                >
                  <option value="Limassol">Limassol</option>
                </select>
              </label>
              <label>
                Area
                <select
                  required
                  value={otherArea ? "__other" : manual.area}
                  onChange={(event) => {
                    setOtherArea(event.target.value === "__other");
                    setManual((x) => ({
                      ...x,
                      area:
                        event.target.value === "__other"
                          ? ""
                          : event.target.value,
                    }));
                  }}
                >
                  <option value="" disabled>
                    Select an area
                  </option>
                  {areaNames(data).map((area) => (
                    <option key={area} value={area}>
                      {area}
                    </option>
                  ))}
                  <option value="__other">Other area…</option>
                </select>
              </label>
            </div>
            {otherArea && (
              <label>
                Area name
                <input
                  required
                  value={manual.area}
                  onChange={(event) =>
                    setManual((x) => ({ ...x, area: event.target.value }))
                  }
                  placeholder="Area as shown in the listing"
                />
              </label>
            )}
            <label>
              Source URL (optional)
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </label>
            <label className="upload-zone">
              <Upload size={22} />
              <b>
                {files.length
                  ? `${files.length} photos selected`
                  : "Add photos"}
              </b>
              <small>
                All photos · up to 100 JPG, PNG or WebP · up to 8 MB each
              </small>
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                multiple
                onChange={(e) => {
                  const f = Array.from(e.target.files || []);
                  if (
                    f.length > 100 ||
                    f.some((x) => x.size > 8 * 1024 * 1024)
                  ) {
                    setError("Up to 100 photos, each up to 8 MB.");
                    return;
                  }
                  setFiles(f);
                }}
              />
            </label>
          </>
        )}
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
        {job && (
          <div className="import-progress">
            <b>{job.phase}</b>
            <span>
              {job.done} / {job.total} · imported {job.imported}
            </span>
            <progress max={job.total || 1} value={job.done} />
            {[...job.errors, ...job.warnings].map((x, i) => (
              <small key={i}>{x}</small>
            ))}
            {job.status === "done" && (
              <p className="success">
                Listings added. Close this dialog and brief your agent.
              </p>
            )}
          </div>
        )}
        <button className="primary" disabled={busy}>
          {busy ? (
            <LoaderCircle className="spin" size={17} />
          ) : (
            <Upload size={17} />
          )}{" "}
          {busy ? "Processing photos…" : "Add listings"}
        </button>
      </form>
    </Modal>
  );
}

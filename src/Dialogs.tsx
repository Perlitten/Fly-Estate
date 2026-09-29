import {
  useEffect,
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
} from "lucide-react";
import { api } from "./api";
import type { Data, Settings, Job } from "./types";

export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      className="modal"
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal-header">
        <h2>{title}</h2>
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
    [excluded, setExcluded] = useState(s.excluded.join(", ")),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const change = (key: keyof Settings, value: unknown) =>
    setS((x) => ({ ...x, [key]: value }));
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await onSave({
        ...s,
        excluded: excluded
          .split(",")
          .map((x) => x.trim())
          .filter(Boolean),
      });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="Client brief" onClose={onClose}>
      <form onSubmit={submit} className="settings-form">
        <p className="muted">
          Budget shapes the response. Hard limits exclude listings before
          computation.
        </p>
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
              {[0, 1, 2, 3, 4, 5].map((x) => (
                <option key={x} value={x}>
                  {x === 0 ? "Studio" : x}
                </option>
              ))}
            </select>
          </label>
          <label>
            Preferred area radius, km
            <input
              type="number"
              min="0.1"
              max="30"
              step="0.1"
              value={s.radius}
              onChange={(e) => change("radius", +e.target.value)}
            />
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
            <small>Uncovered and unspecified parking are excluded too</small>
          </span>
        </label>
        <label>
          Excluded areas, separated by commas
          <input
            value={excluded}
            onChange={(e) => setExcluded(e.target.value)}
            placeholder="For example: Ypsonas"
          />
        </label>
        <p className="muted">
          You can drag your preferred point on the map. These settings are saved
          on this computer only.
        </p>
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
        <button className="primary" disabled={busy}>
          <Check size={17} />
          Save brief
        </button>
        <a className="backup-link" href="/api/export" download>
          <Download size={16} />
          Download my listings and ratings
        </a>
      </form>
    </Modal>
  );
}
const bookmarklet =
  "javascript:(()=>{const scripts=[...document.querySelectorAll('script[type=\"application/ld+json\"]')].map(x=>{try{return JSON.parse(x.textContent)}catch{return null}}).filter(Boolean);const content=scripts.length?JSON.stringify(scripts):document.documentElement.outerHTML;const text=JSON.stringify({url:location.href,content});navigator.clipboard.writeText(text).then(()=>alert('Listing copied. Paste it into Fly Estate → JSON / HTML.')).catch(()=>prompt('Copy this listing:',text))})()";
export function ImportDialog({
  onDone,
  onClose,
}: {
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
            <label>
              Area
              <input
                required
                value={manual.area}
                onChange={(e) =>
                  setManual((x) => ({ ...x, area: e.target.value }))
                }
              />
            </label>
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

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUpRight, RotateCw, Search } from "lucide-react";
import type { Job, Market, Settings } from "./types";
import { api, count, money } from "./api";
import "./market.css";

/** The same key ImportDialog uses, so a reload resumes whichever import is running. */
const JOB_KEY = "fly-estate-job";
/** Refresh the file after this many new listings, so markers appear while the agent reads. */
const REFRESH_EVERY = 3;

type HttpError = Error & { status?: number };
export type MarketStatus =
  | "idle"
  | "loading"
  | "ready"
  | "error"
  | "blocked"
  | "unavailable";
export type AgentSearch = {
  market?: Market;
  status: MarketStatus;
  error: string;
  job?: Job;
  /** Advert being added from the map popup; empty for a search. */
  jobUrl: string;
  starting: boolean;
  notice: string;
  failed?: { url: string; message: string };
  fetchMarket: (quiet?: boolean, force?: boolean) => Promise<void>;
  search: () => Promise<void>;
  add: (url: string) => Promise<void>;
};

const read = <T,>(path: string, method = "GET", body?: unknown) =>
  api<T>(path, method, body);
const statusOf = (e: unknown) => (e as HttpError).status;

/**
 * Market snapshot and the agent's import job. Lives in App, so the sidebar
 * panel and the map layer share one poller. `open` fetches the market lazily
 * the first time the map is shown.
 */
export function useAgentSearch(
  open: boolean,
  onListings: () => Promise<void>,
  onInspect?: (id: string) => void,
): AgentSearch {
  const [market, setMarket] = useState<Market>(),
    [status, setStatus] = useState<MarketStatus>("idle"),
    [error, setError] = useState(""),
    [job, setJob] = useState<Job>(),
    [jobUrl, setJobUrl] = useState(""),
    [starting, setStarting] = useState(false),
    [notice, setNotice] = useState(""),
    [failed, setFailed] = useState<{ url: string; message: string }>();
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined),
    tracking = useRef(""),
    generation = useRef(0),
    refreshed = useRef(0),
    sawRunning = useRef(false),
    remaining = useRef(0),
    marketSeq = useRef(0),
    hasMarket = useRef(false),
    listings = useRef(onListings),
    inspect = useRef(onInspect),
    opening = useRef(false);
  listings.current = onListings;
  inspect.current = onInspect;

  const fetchMarket = useCallback(async (quiet = false, force = false) => {
    const seq = ++marketSeq.current;
    if (!quiet || !hasMarket.current) setStatus("loading");
    try {
      const m = await read<Market>(
        "/api/sources/bazaraki" + (force ? "?force=true" : ""),
      );
      if (seq !== marketSeq.current) return;
      hasMarket.current = true;
      setMarket(m);
      setError("");
      setStatus("ready");
    } catch (e) {
      if (seq !== marketSeq.current) return;
      if (statusOf(e) === 404) setStatus("unavailable");
      else if (quiet && hasMarket.current) setStatus("ready");
      else {
        setError((e as Error).message);
        setStatus(statusOf(e) === 503 ? "blocked" : "error");
      }
    }
  }, []);

  const finish = useCallback(
    async (j: Job) => {
      tracking.current = "";
      if (sessionStorage.getItem(JOB_KEY) === j.id)
        sessionStorage.removeItem(JOB_KEY);
      await listings.current().catch(() => {});
      if (opening.current && j.listing_ids?.[0])
        inspect.current?.(j.listing_ids[0]);
      opening.current = false;
      if (sawRunning.current) {
        const missed = j.errors.length
          ? ` ${j.errors.length} could not be read.`
          : "";
        const more = remaining.current
          ? ` ${remaining.current} more wait for the next search.`
          : "";
        setNotice(
          j.status === "error"
            ? j.error || "The import did not complete."
            : j.total === 1
              ? j.imported
                ? "Added to your file."
                : "This advert could not be read."
              : `Added ${j.imported} of ${j.total} to your file.${missed}${more}`,
        );
      }
      remaining.current = 0;
      if (hasMarket.current) await fetchMarket(true);
    },
    [fetchMarket],
  );

  const poll = useCallback(
    async (id: string, gen: number) => {
      const current = () =>
        tracking.current === id && generation.current === gen;
      if (!current()) return;
      try {
        const j = await read<Job>("/api/jobs/" + id);
        if (!current()) return;
        setJob(j);
        if (j.status === "running") {
          sawRunning.current = true;
          if (j.imported - refreshed.current >= REFRESH_EVERY) {
            refreshed.current = j.imported;
            listings.current().catch(() => {});
          }
          timer.current = setTimeout(() => poll(id, gen), 1500);
        } else await finish(j);
      } catch (e) {
        if (!current()) return;
        if (statusOf(e) === 404) {
          // The server restarted and forgot the job.
          tracking.current = "";
          sessionStorage.removeItem(JOB_KEY);
          setJob(undefined);
        } else timer.current = setTimeout(() => poll(id, gen), 4000);
      }
    },
    [finish],
  );

  const track = useCallback(
    (id: string, url = "", fresh = false) => {
      clearTimeout(timer.current);
      tracking.current = id;
      refreshed.current = 0;
      sawRunning.current = fresh;
      opening.current = fresh && !!url;
      sessionStorage.setItem(JOB_KEY, id);
      setJobUrl(url);
      setNotice("");
      setFailed(undefined);
      poll(id, ++generation.current);
    },
    [poll],
  );

  /** A job started elsewhere (sync from another tab, the import dialog). */
  const discover = useCallback(async () => {
    try {
      const r = await read<{ running: Job[] }>("/api/jobs");
      const running = r.running[0];
      if (running && !tracking.current) track(running.id);
      return !!running;
    } catch {
      return false; // Older server without GET /api/jobs.
    }
  }, [track]);

  useEffect(() => {
    const saved = sessionStorage.getItem(JOB_KEY);
    if (saved) track(saved);
    else discover();
    return () => {
      clearTimeout(timer.current);
      tracking.current = "";
      generation.current++;
    };
  }, [track, discover]);

  useEffect(() => {
    if (open && status === "idle") fetchMarket();
  }, [open, status, fetchMarket]);

  const search = async () => {
    setNotice("");
    setStarting(true);
    try {
      await fetchMarket(false, true);
    } finally {
      setStarting(false);
    }
  };

  const add = async (url: string) => {
    setFailed(undefined);
    try {
      const r = await read<{ job: string }>("/api/import", "POST", {
        urls: [url],
      });
      remaining.current = 0;
      track(r.job, url, true);
    } catch (e) {
      setFailed({
        url,
        message:
          statusOf(e) === 409
            ? "Wait for the current import to finish."
            : (e as Error).message,
      });
    }
  };

  return {
    market,
    status,
    error,
    job,
    jobUrl,
    starting,
    notice,
    failed,
    fetchMarket,
    search,
    add,
  };
}

export const searchUrl = (ceiling: number) =>
  `https://www.bazaraki.com/real-estate-to-rent/apartments-flats/lemesos-district-limassol/?price_max=${Math.round(ceiling)}`;

export function JobProgress({ job, label }: { job: Job; label?: string }) {
  const total = job.total || 0;
  const share = total ? Math.min(1, job.done / total) : 0;
  return (
    <div className="market-progress" role="status">
      <span>
        {label ??
          (total
            ? `Reading ${Math.min(job.done + 1, total)} of ${total}`
            : "Starting")}
        {job.phase ? ` · ${job.phase}` : ""}
      </span>
      <div className={"market-bar" + (total ? "" : " indeterminate")}>
        <i
          style={total ? { width: `${Math.max(4, share * 100)}%` } : undefined}
        />
      </div>
    </div>
  );
}

export default function MarketPanel({
  agent,
  settings,
}: {
  agent: AgentSearch;
  settings: Settings;
}) {
  const { market, status, job, notice } = agent;
  const running = job?.status === "running";
  const fresh = market?.new ?? 0;
  // Counted over the new offers themselves: the map page also marks auto-placed
  // adverts, so the server's exact_coords total overstates what is pinned.
  const newOffers = (market?.offers || []).filter(
      (o) => !o.listing_id && !o.excluded_area,
    ),
    exact = newOffers.filter(
      (o) => o.coords && o.coord_kind === "source",
    ).length,
    centred = newOffers.filter(
      (o) => o.coords && o.coord_kind !== "source",
    ).length;
  const terms = `under ${money(settings.ceiling)} with ${settings.min_bedrooms}+ bedrooms`;
  return (
    <section
      className="market-panel"
      aria-label="Bazaraki live market"
      aria-busy={status === "loading" || running || agent.starting}
    >
      <span className="eyebrow">BAZARAKI · LIVE MARKET</span>
      {status === "ready" && market ? (
        <>
          <p className="market-lead">
            <b>{count(fresh)}</b> new {fresh === 1 ? "offer" : "offers"} {terms}
          </p>
          <small className="market-meta">
            On the map: {count(exact)} exact, {count(centred)} at area centres ·{" "}
            {count(market.scanned)} of {count(market.listed ?? market.scanned)}{" "}
            scanned
          </small>
        </>
      ) : status === "unavailable" ? (
        <p className="market-lead">
          The live market needs a server restart.
          <small className="market-meta">
            Restart the API to let your agent read Bazaraki.
          </small>
        </p>
      ) : status === "error" || status === "blocked" ? (
        <div className="market-lead">
          <p>
            {status === "blocked"
              ? "Bazaraki blocked or limited this request."
              : "Bazaraki could not be read."}
          </p>
          <small className="market-meta">{agent.error}</small>
          <button
            className="text-button market-retry"
            onClick={() => agent.fetchMarket()}
          >
            <RotateCw size={14} />
            Try again
          </button>
        </div>
      ) : (
        <div className="market-lead">
          <p>Your agent is reading Bazaraki {terms}.</p>
          <small className="market-meta">
            The first read takes about 12 seconds.
          </small>
          <div className="market-bar indeterminate">
            <i />
          </div>
        </div>
      )}
      {running ? (
        <JobProgress job={job} />
      ) : (
        <button
          className="primary market-search"
          disabled={
            agent.starting || status === "loading" || status === "unavailable"
          }
          onClick={() => agent.search()}
        >
          <Search size={16} />
          {agent.starting ? "Reading the map…" : "Refresh Bazaraki map"}
        </button>
      )}
      {agent.starting && (
        <div className="market-bar indeterminate">
          <i />
        </div>
      )}
      {notice && !running && <p className="market-notice">{notice}</p>}
      <p className="market-meta">
        Browse prices and locations here. A gallery is downloaded only when you
        choose an apartment to analyze.
      </p>
      <a
        className="market-link"
        href={searchUrl(settings.ceiling).replace(".com/", ".com/map/")}
        target="_blank"
        rel="noopener"
      >
        Open the map on Bazaraki
        <ArrowUpRight size={13} />
      </a>
      <a
        className="market-link"
        href={market?.search || searchUrl(settings.ceiling)}
        target="_blank"
        rel="noopener"
      >
        Open the search on Bazaraki
        <ArrowUpRight size={13} />
      </a>
    </section>
  );
}

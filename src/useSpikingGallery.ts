import { useEffect, useState } from "react";
import type { Gallery, Listing } from "./types";

/** One polling subscription shared by the controls and the 3D playback. */
export function useSpikingGallery(
  listing: Listing | undefined,
  settingsKey: string,
) {
  const [gallery, setGallery] = useState<Gallery>(),
    [error, setError] = useState(""),
    [revision, setRevision] = useState(0);
  const id = listing?.id,
    updated = listing?.updated_at;
  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      let interval = 4000;
      try {
        const response = await fetch("/api/engine/gallery/" + id, {
          signal: controller.signal,
        });
        const result = await response.json();
        if (!response.ok)
          throw Error(result.detail || "Could not read the simulation");
        if (controller.signal.aborted) return;
        setGallery(result);
        setError("");
        if (["queued", "running"].includes(result.job?.status)) interval = 300;
      } catch (e) {
        if (controller.signal.aborted) return;
        setError((e as Error).message);
      }
      timer = setTimeout(poll, interval);
    };
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [id, updated, settingsKey, revision]);
  const params = JSON.parse(settingsKey);
  const current =
    gallery &&
    gallery.listing_id === id &&
    gallery.mode === params.mode &&
    gallery.params?.brief?.ceiling === params.ceiling &&
    gallery.params?.brief?.radius === params.radius &&
    JSON.stringify(gallery.params?.brief?.ideal) ===
      JSON.stringify(params.ideal)
      ? gallery
      : undefined;
  return { gallery: current, error, refresh: () => setRevision((x) => x + 1) };
}

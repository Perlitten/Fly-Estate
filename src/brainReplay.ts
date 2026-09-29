import type { SpikingReplay } from "./types";

export type ReplayFrames = {
  frames: Uint8Array;
  scope: Uint8Array;
  info: SpikingReplay;
};

/** Map the engine's explicitly identified neurons; the rest stays dark. */
export function decodeReplay(
  info: SpikingReplay,
  neurons: number,
): ReplayFrames {
  const values = Uint8Array.from(atob(info.values), (x) => x.charCodeAt(0));
  if (values.length !== info.bins * info.indices.length || info.bins < 1)
    throw Error("The recorded spike frames are incomplete");
  const frames = new Uint8Array(info.bins * neurons),
    scope = new Uint8Array(neurons);
  info.indices.forEach((index, local) => {
    if (index < 0) return;
    if (index >= neurons)
      throw Error("Replay neuron is outside the anatomical view");
    scope[index] = 255;
    for (let frame = 0; frame < info.bins; frame++)
      frames[frame * neurons + index] =
        values[frame * info.indices.length + local];
  });
  return { frames, scope, info };
}

export async function api<T = Record<string, unknown>>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(
    path,
    body === undefined
      ? { method }
      : {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const result = await response.json();
  if (!response.ok) {
    let detail =
      result.detail || result.error || "Could not complete the action";
    if (Array.isArray(detail)) detail = detail.map((x) => x.msg).join("; ");
    throw Object.assign(new Error(detail), { status: response.status });
  }
  return result;
}
export const money = (v: number) =>
  new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(v);
export const count = (v: number) => new Intl.NumberFormat("en-GB").format(v);

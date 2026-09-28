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
      result.detail || result.error || "Не удалось выполнить действие";
    if (Array.isArray(detail)) detail = detail.map((x) => x.msg).join("; ");
    throw new Error(detail);
  }
  return result;
}
export const money = (v: number) =>
  new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(v);
export const count = (v: number) => new Intl.NumberFormat("ru-RU").format(v);

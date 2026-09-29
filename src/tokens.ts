/** Значение CSS-токена из tokens.css для библиотек, которым нужен готовый цвет (Leaflet, three.js). */
export function token(name: string): string {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(`--${name}`)
    .trim();
}

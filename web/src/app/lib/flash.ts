export function flashSuccessButton(target?: EventTarget | null) {
  if (typeof document === "undefined") return;
  const candidate = target instanceof HTMLElement ? target : document.activeElement;
  if (!(candidate instanceof HTMLButtonElement)) return;
  candidate.classList.add("btn-success-flash");
  window.setTimeout(() => {
    candidate.classList.remove("btn-success-flash");
  }, 900);
}

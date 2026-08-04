import { useEffect, type RefObject } from "react";

/** Surfaces we float above the page ourselves have to survive a modal dialog.
 *
 *  Radix's modal Dialog sets `pointer-events: none` on <body> and re-enables
 *  them only inside its own content. Our select panel, confirm dialog and
 *  command palette are siblings of that content rather than descendants, so
 *  without this class they inherit the none and go completely dead the moment
 *  they are opened from inside a modal — the reason select options could not
 *  be picked in the expense claim form.
 *
 *  `pointer-events` is inherited but not binding: setting it back to auto on
 *  the layer restores hit testing for that subtree only.
 */
export const FLOATING_LAYER = "pointer-events-auto";

/** Stops a click on our layer from closing the dialog underneath it.
 *
 *  Radix decides "this was outside the dialog" from a pointerdown listener on
 *  document. Our layers really are outside the dialog in the DOM, so every
 *  click on one would read as a dismissal. Swallowing pointerdown at the layer
 *  keeps it from ever reaching that listener.
 *
 *  Deliberately pointerdown only. Swallowing mousedown here would also stop
 *  React's own delegated listener (which sits on the portal container, not on
 *  the layer) from ever running, and the option handlers would stop firing —
 *  trading one dead dropdown for another.
 */
export function useLayerDismissGuard(
  ref: RefObject<HTMLElement | null>,
  active: boolean,
): void {
  useEffect(() => {
    const node = active ? ref.current : null;
    if (!node) return;
    const swallow = (event: Event) => event.stopPropagation();
    node.addEventListener("pointerdown", swallow);
    return () => node.removeEventListener("pointerdown", swallow);
  }, [ref, active]);
}

import { useEffect, useRef, useState } from "react";

/** Smooth letter-by-letter reveal, decoupled from bursty network chunks.
 *
 * SSE deltas land in multi-word bursts; rendering them directly makes text
 * jump. Instead the full target accumulates and this hook drains it with a
 * requestAnimationFrame loop whose speed scales with the backlog — instant
 * catch-up when far behind, silky character flow at the tail. When `active`
 * turns false (stream finished/aborted) it snaps to the full text.
 */
export function useTypewriter(target: string, active: boolean): string {
  const [shown, setShown] = useState(active ? "" : target);
  const shownLen = useRef(active ? 0 : target.length);
  const raf = useRef<number>(0);

  useEffect(() => {
    if (!active) {
      shownLen.current = target.length;
      setShown(target);
      return;
    }
    // target got shorter → a new message started reusing the hook
    if (shownLen.current > target.length) {
      shownLen.current = 0;
    }
    const tick = () => {
      const backlog = target.length - shownLen.current;
      if (backlog > 0) {
        // 2 chars/frame minimum (~120 cps) up to big jumps when far behind
        const step = Math.max(2, Math.ceil(backlog / 24));
        shownLen.current = Math.min(target.length, shownLen.current + step);
        setShown(target.slice(0, shownLen.current));
      }
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [target, active]);

  return shown;
}

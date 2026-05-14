"use client";

import { useEffect, useRef, useState } from "react";
import type { Locale, TerminalContent } from "../../../types/site";

export function BootTerminal({ terminal, locale, fast = false, onDone }: { terminal: TerminalContent; locale: Locale; fast?: boolean; onDone: () => void }) {
  const [completeLines, setCompleteLines] = useState<string[]>([]);
  const [activeLine, setActiveLine] = useState("");
  const [progress, setProgress] = useState(0);
  const [online, setOnline] = useState(false);
  const [closing, setClosing] = useState(false);
  const doneRef = useRef(false);
  const onDoneRef = useRef(onDone);

  useEffect(() => {
    onDoneRef.current = onDone;
  }, [onDone]);

  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const durations = [800, 650, 900, 800, 900, 1000, 900, 1000, 400];
    const pauses = [200, 180, 200, 200, 200, 200, 200, 300, 1000];
    const speed = fast ? 0.35 : 1;
    const wait = (duration: number) => new Promise((resolve) => window.setTimeout(resolve, duration));
    const finish = async () => {
      if (doneRef.current) return;
      doneRef.current = true;
      setOnline(true);
      setProgress(100);
      if (fast) {
        onDoneRef.current();
        return;
      }
      await wait(fast ? 220 : 1000);
      if (cancelled) return;
      setClosing(true);
      await wait(800);
      if (!cancelled) onDoneRef.current();
    };
    const run = async () => {
      const lines = terminal.lines;
      const totalChars = lines.reduce((sum, line) => sum + line.length, 0);
      let typedChars = 0;
      for (let lineIndex = 0; lineIndex < lines.length; lineIndex += 1) {
        const line = lines[lineIndex];
        const charDelay = Math.max(8, ((durations[lineIndex] ?? 650) * speed) / Math.max(line.length, 1));
        for (let charIndex = 1; charIndex <= line.length; charIndex += 1) {
          if (cancelled || doneRef.current) return;
          setActiveLine(line.slice(0, charIndex));
          typedChars += 1;
          setProgress(Math.min(98, (typedChars / totalChars) * 100));
          await wait(charDelay);
        }
        if (cancelled || doneRef.current) return;
        setCompleteLines((current) => [...current, line]);
        setActiveLine("");
        await wait((pauses[lineIndex] ?? 180) * speed);
      }
      await finish();
    };
    run();
    return () => { cancelled = true; };
  }, [terminal, fast]);

  const skip = () => {
    if (doneRef.current) return;
    doneRef.current = true;
    setProgress(100);
    setClosing(true);
    window.setTimeout(() => onDoneRef.current(), 450);
  };

  return (
    <div className={`boot-overlay ${closing ? "boot-closing" : ""}`} dir={locale === "ar" ? "rtl" : "ltr"}>
      <div className={`terminal-window ${closing ? "terminal-closing" : ""}`}>
        <div className="terminal-topbar">
          <div className="terminal-dots" aria-hidden="true"><span /><span /><span /></div>
          <span>{terminal.label}</span>
        </div>
        <div className="terminal-body">
          <div className="terminal-lines">
            {completeLines.map((line, index) => <p className={index === terminal.lines.length - 1 ? "terminal-ready" : ""} key={`${line}-${index}`}><span>{line}</span></p>)}
            {activeLine && <p><span>{activeLine}</span><b className="terminal-cursor">▋</b></p>}
          </div>
          {online && <div className="terminal-online"><i /><span>{terminal.online}</span></div>}
          <div className="terminal-progress"><span style={{ width: `${progress}%` }} /></div>
        </div>
      </div>
      <button type="button" className="terminal-skip" onClick={skip}>{terminal.skip}</button>
    </div>
  );
}

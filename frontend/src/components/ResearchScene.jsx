import { useRef, useState } from 'react';

export default function ResearchScene() {
  const scene = useRef(null);
  const [paused, setPaused] = useState(false);
  function reset() { scene.current.style.setProperty('--tilt', '0deg'); }
  function move(event) {
    if (paused || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const box = event.currentTarget.getBoundingClientRect();
    scene.current.style.setProperty('--tilt', `${((event.clientX - box.left) / box.width - .5) * 16}deg`);
  }
  return <div className={`research-scene ${paused ? 'is-paused' : ''}`} onPointerMove={move} onPointerLeave={reset}>
    <div className="scene-label">A NEW DIMENSION TO YOUR RESEARCH <span>↗</span></div>
    <div className="knowledge-sculpture" ref={scene} aria-hidden="true">
      {[['draft', '01', 'THE IDEA', 'Every breakthrough starts with a question.'], ['insight', '02', 'THE INSIGHT', 'Find the connections that move you forward.'], ['impact', '03', 'THE IMPACT', 'Make your next chapter count.']].map(([name, n, title, text]) => <div className={`sculpture-block block-${name}`} key={name}><div className="block-face front"><span className="block-number">{n}</span><div className="block-glyph">{n === '01' ? '✳' : n === '02' ? '⌁' : '↗'}</div><strong>{title}</strong><p>{text}</p><div className="block-lines" /></div><div className="block-face side" /><div className="block-face top" /></div>)}
    </div>
    <div className="scene-bottom"><span>FROM FIRST DRAFT TO WHAT’S NEXT.</span><button type="button" className="motion-toggle" aria-pressed={paused} onClick={() => { reset(); setPaused(!paused); }}>{paused ? 'Enable motion' : 'Pause motion'}</button></div>
  </div>;
}

"use client";

import { memo, useEffect, useRef, useCallback, useState } from "react";

interface MaskCanvasProps {
  inputImageSrc: string;
  maskSrc: string;
  labels: { color: [number, number, number]; name: string }[];
  hiddenClasses: Set<number>;
  ignoreIndex?: number;
  opacity: number;
  zoom?: number;
  onHover?: (classIndex: number | null, x: number, y: number) => void;
  className?: string;
}

function MaskCanvas({ inputImageSrc, maskSrc, labels, hiddenClasses,
  ignoreIndex = 255, opacity, zoom = 1, onHover, className = "" }: MaskCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const baseRef = useRef<HTMLCanvasElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const [loaded, setLoaded] = useState<{ key: string; image: HTMLImageElement;
    indices: Uint8Array; width: number; height: number } | null>(null);
  const [error, setError] = useState<{key: string; message: string} | null>(null);
  const key = `${inputImageSrc}\n${maskSrc}`;
  const current = loaded?.key === key ? loaded : null;

  useEffect(() => {
    let cancelled = false;
    for (const canvas of [baseRef.current, overlayRef.current]) {
      canvas?.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
    }
    const load = (src: string) => new Promise<HTMLImageElement>((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error(`Could not load image or mask: ${src}`));
      image.src = src;
    });
    Promise.all([load(inputImageSrc), load(maskSrc)]).then(([image, mask]) => {
      if (cancelled) return;
      if (image.width !== mask.width || image.height !== mask.height) {
        throw new Error(`Dimension mismatch: input ${image.width}x${image.height}, mask ${mask.width}x${mask.height}`);
      }
      const canvas = document.createElement("canvas");
      canvas.width = mask.width; canvas.height = mask.height;
      const ctx = canvas.getContext("2d", {willReadFrequently: true});
      if (!ctx) throw new Error("Browser could not create a mask canvas");
      ctx.drawImage(mask, 0, 0);
      const rgba = ctx.getImageData(0, 0, mask.width, mask.height).data;
      const indices = new Uint8Array(mask.width * mask.height);
      for (let i = 0; i < indices.length; i++) indices[i] = rgba[i * 4];
      setLoaded({key, image, indices, width: mask.width, height: mask.height});
    }).catch((e) => {
      if (!cancelled) setError({key, message: String(e.message || e)});
    });
    return () => { cancelled = true; };
  }, [inputImageSrc, maskSrc, key]);

  useEffect(() => {
    if (!current) return;
    const base = baseRef.current; const canvas = overlayRef.current;
    if (!base || !canvas) return;
    base.width = canvas.width = current.width;
    base.height = canvas.height = current.height;
    base.getContext("2d")?.drawImage(current.image, 0, 0);
    const ctx = canvas.getContext("2d"); if (!ctx) return;
    const pixels = ctx.createImageData(current.width, current.height);
    for (let i = 0; i < current.indices.length; i++) {
      const id = current.indices[i];
      if (id === ignoreIndex || id >= labels.length || hiddenClasses.has(id)) continue;
      const color = labels[id].color;
      pixels.data[i * 4] = color[0];
      pixels.data[i * 4 + 1] = color[1];
      pixels.data[i * 4 + 2] = color[2];
      pixels.data[i * 4 + 3] = 255;
    }
    ctx.putImageData(pixels, 0, 0);
  }, [current, labels, hiddenClasses, ignoreIndex]);

  const hover = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    if (!current || !containerRef.current || !onHover) return;
    const rect = containerRef.current.getBoundingClientRect();
    const scale = Math.min(rect.width / current.width, rect.height / current.height);
    const x = (event.clientX - rect.left - (rect.width - current.width * scale) / 2) / scale;
    const y = (event.clientY - rect.top - (rect.height - current.height * scale) / 2) / scale;
    const id = x >= 0 && y >= 0 && x < current.width && y < current.height
      ? current.indices[Math.floor(y) * current.width + Math.floor(x)] : ignoreIndex;
    onHover(id === ignoreIndex || id >= labels.length ? null : id, event.clientX, event.clientY);
  }, [current, ignoreIndex, labels.length, onHover]);

  return <div className="canvas-scroll"><div style={{width: `${zoom * 100}%`, height: `${zoom * 100}%`}} ref={containerRef} className={`canvas-stage relative overflow-hidden ${className}`}
    onMouseMove={hover} onMouseLeave={() => onHover?.(null, 0, 0)}>
    <canvas ref={baseRef} className="absolute inset-0 w-full h-full object-contain" />
    <canvas ref={overlayRef} className="absolute inset-0 w-full h-full object-contain" style={{opacity}} />
    {error?.key === key && <div role="alert" className="absolute inset-x-4 bottom-4 bg-black/90 p-3 text-sm text-red-200">{error.message}</div>}
  </div></div>;
}

export default memo(MaskCanvas);

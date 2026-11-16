import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';
import { iconOf } from '../utils/labels';
import Photo from './Photo';

// Every photo sits in a fixed 4:3 frame and is shown whole (object-fit: contain), so nothing is cropped
// and the page does not jump while pictures load. width/height match that frame.

const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

function Lightbox({ images, index, title, onChange, onClose }) {
  const [actualSize, setActualSize] = useState(false);
  const closeRef = useRef(null);
  const touchStart = useRef(null);
  const many = images.length > 1;
  const step = useCallback((by) => onChange((index + by + images.length) % images.length), [index, images.length, onChange]);

  useEffect(() => {
    const opener = document.activeElement;
    closeRef.current?.focus();
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = '';
      opener?.focus?.();
    };
  }, []);

  useEffect(() => {
    const onKey = (event) => {
      if (event.key === 'Escape') onClose();
      if (many && event.key === 'ArrowLeft') step(-1);
      if (many && event.key === 'ArrowRight') step(1);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [many, step, onClose]);

  // A one-finger swipe changes photo; two fingers (pinch) are left to the browser's own zoom.
  const onTouchStart = (event) => {
    touchStart.current = event.touches.length === 1 ? event.touches[0].clientX : null;
  };
  const onTouchEnd = (event) => {
    if (touchStart.current == null || actualSize || !many) return;
    const dx = event.changedTouches[0].clientX - touchStart.current;
    touchStart.current = null;
    if (Math.abs(dx) > 60) step(dx < 0 ? 1 : -1);
  };

  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label={`Photos of ${title}`} onClick={onClose}>
      <button ref={closeRef} type="button" className="lightbox-close" aria-label="Close" onClick={onClose}>
        <X aria-hidden="true" />
      </button>
      {many && <span className="lightbox-count" aria-hidden="true">{index + 1}/{images.length}</span>}
      {many && (
        <button type="button" className="lightbox-nav prev" aria-label="Previous photo" onClick={(e) => { e.stopPropagation(); step(-1); }}>
          <ChevronLeft aria-hidden="true" />
        </button>
      )}
      <div className={`lightbox-stage${actualSize ? ' actual' : ''}`} onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}>
        <img
          src={images[index].image_url}
          alt={`${title}, photo ${index + 1} of ${images.length}`}
          onClick={(e) => {
            e.stopPropagation();
            setActualSize((value) => !value);
          }}
        />
      </div>
      {many && (
        <button type="button" className="lightbox-nav next" aria-label="Next photo" onClick={(e) => { e.stopPropagation(); step(1); }}>
          <ChevronRight aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

export default function Gallery({ images = [], title, category }) {
  const [index, setIndexState] = useState(0);
  const [zoomed, setZoomed] = useState(false);
  const track = useRef(null);
  // Held in a ref as well, so keys pressed in quick succession each start from the latest photo.
  const current = useRef(0);
  const setIndex = useCallback((value) => {
    current.current = value;
    setIndexState(value);
  }, []);
  const frame = useRef(0);
  const count = images.length;

  // The swipe position decides which photo is current, so dots, counter and thumbnails follow a finger swipe.
  const onScroll = () => {
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      const el = track.current;
      if (el && el.clientWidth) setIndex(Math.round(el.scrollLeft / el.clientWidth));
    });
  };
  useEffect(() => () => cancelAnimationFrame(frame.current), []);

  const go = useCallback(
    (to) => {
      const next = Math.min(Math.max(to, 0), count - 1);
      const el = track.current;
      if (el) el.scrollTo({ left: next * el.clientWidth, behavior: reducedMotion() ? 'auto' : 'smooth' });
      setIndex(next);
    },
    [count, setIndex]
  );

  // After the full-screen viewer closes, bring the strip to the photo that was last shown there.
  const closeViewer = () => {
    setZoomed(false);
    requestAnimationFrame(() => {
      const el = track.current;
      if (el) el.scrollTo({ left: index * el.clientWidth, behavior: 'auto' });
    });
  };

  if (!count) {
    return (
      <div className="photo-frame photo-empty gallery" role="img" aria-label="No photo added">
        <span aria-hidden="true">{iconOf(category)}</span>
        <small>No photo added</small>
      </div>
    );
  }

  const onKeyDown = (event) => {
    if (event.key === 'ArrowLeft') { event.preventDefault(); go(current.current - 1); }
    if (event.key === 'ArrowRight') { event.preventDefault(); go(current.current + 1); }
    if (event.key === 'Home') { event.preventDefault(); go(0); }
    if (event.key === 'End') { event.preventDefault(); go(count - 1); }
  };

  return (
    <div className="gallery">
      <div className="gallery-stage">
        <div
          ref={track}
          className="gallery-track"
          role="group"
          aria-roledescription="carousel"
          aria-label={`Photos of ${title}`}
          tabIndex={count > 1 ? 0 : undefined}
          onScroll={onScroll}
          onKeyDown={onKeyDown}
        >
          {images.map((image, i) => (
            <div className="gallery-slide" key={image.id} role="group" aria-roledescription="slide" aria-label={`${i + 1} of ${count}`}>
              <button type="button" className="photo-frame photo-zoomable" aria-label="Enlarge photo" onClick={() => setZoomed(true)}>
                <Photo
                  category={category}
                  src={image.image_url}
                  alt={i === 0 ? title : `${title}, photo ${i + 1}`}
                  width="800"
                  height="600"
                  loading={i === 0 ? 'eager' : 'lazy'}
                  decoding="async"
                  draggable="false"
                />
              </button>
            </div>
          ))}
        </div>
        {count > 1 && (
          <>
            <span className="gallery-count" aria-hidden="true">{index + 1}/{count}</span>
            <button type="button" className="gallery-arrow prev" aria-label="Previous photo" disabled={index === 0} onClick={() => go(index - 1)}>
              <ChevronLeft aria-hidden="true" />
            </button>
            <button type="button" className="gallery-arrow next" aria-label="Next photo" disabled={index === count - 1} onClick={() => go(index + 1)}>
              <ChevronRight aria-hidden="true" />
            </button>
          </>
        )}
      </div>

      {count > 1 && (
        <>
          <div className="gallery-dots">
            {images.map((image, i) => (
              <button
                key={image.id}
                type="button"
                aria-label={`Show photo ${i + 1} of ${count}`}
                aria-current={i === index ? 'true' : undefined}
                className={i === index ? 'active' : ''}
                onClick={() => go(i)}
              />
            ))}
          </div>
          <ul className="gallery-thumbs">
            {images.map((image, i) => (
              <li key={image.id}>
                <button
                  type="button"
                  className={i === index ? 'active' : ''}
                  aria-label={`Show photo ${i + 1} of ${count}`}
                  aria-current={i === index ? 'true' : undefined}
                  onClick={() => go(i)}
                >
                  <Photo src={image.image_url} alt="" category={category} width="96" height="72" loading="lazy" decoding="async" />
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      {zoomed && <Lightbox images={images} index={index} title={title} onChange={setIndex} onClose={closeViewer} />}
    </div>
  );
}

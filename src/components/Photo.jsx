import { useEffect, useState } from 'react';
import { iconOf } from '../utils/labels';

/**
 * A listing photo that cannot show a broken-image icon. If the picture fails to load, a neutral placeholder
 * with the category's icon takes its place; it is never presented as the real photo.
 */
export default function Photo({ src, alt, category, ...imgProps }) {
  const [failed, setFailed] = useState(false);

  // A different picture in the same spot gets a fresh try.
  useEffect(() => setFailed(false), [src]);

  if (failed) {
    return (
      <span className="photo-fallback" role="img" aria-label={alt ? `${alt} (photo unavailable)` : 'Photo unavailable'}>
        {iconOf(category)}
      </span>
    );
  }

  return <img src={src} alt={alt} onError={() => setFailed(true)} {...imgProps} />;
}

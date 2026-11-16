import { Component, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { failureCopy } from '../utils/messages';

/**
 * One short line and one action, in place, next to whatever failed. `error` is a failed result from `safe()`;
 * `context` picks the wording (see utils/messages.js). Admins also get a small copyable reference for the log.
 */
export function InlineError({ error, context = 'generic', onRetry, text, action, compact = false }) {
  const { user } = useAuth();
  const [copied, setCopied] = useState(false);
  // Explicit text/action win; otherwise the wording comes from the failure (or from the context alone, for a render crash).
  const copy = text !== undefined ? { text, action, ref: null } : failureCopy(error, context);

  const copyRef = async () => {
    try {
      await navigator.clipboard.writeText(copy.ref);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Nothing to do: the reference is on screen to be read out.
    }
  };

  return (
    <p className={`inline-error${compact ? ' compact' : ''}`} role="alert">
      <span>{copy.text}</span>
      {copy.action && onRetry && (
        <button type="button" className="link-button" onClick={onRetry}>
          {copy.action}
        </button>
      )}
      {user?.is_admin && copy.ref && (
        <button type="button" className="error-ref" onClick={copyRef} title="Copy reference for the server log">
          {copied ? 'Copied' : `Ref ${copy.ref}`}
        </button>
      )}
    </p>
  );
}

/**
 * Keeps one block of a page from taking the whole page down. If anything inside throws while rendering, only
 * this block shows the small message; the rest of the page carries on. "Retry" tries the block again.
 */
export class SectionBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error, info) {
    console.error(`Section "${this.props.name ?? 'unnamed'}" failed to render:`, error, info?.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return <InlineError context={this.props.context ?? 'generic'} compact={this.props.compact} onRetry={() => this.setState({ failed: false })} />;
  }
}

// Grey rows that hold the shape of a list while it loads.
export function SkeletonList({ rows = 3 }) {
  return (
    <div className="skeleton-list" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div className="skeleton-row" key={i}>
          <span />
          <span />
        </div>
      ))}
    </div>
  );
}

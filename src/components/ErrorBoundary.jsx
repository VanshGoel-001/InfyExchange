import { Component } from 'react';
import { Header } from './Layout';

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('Unhandled Application Render Error:', error, errorInfo);
  }

  handleReload = () => {
    this.setState({ hasError: false, error: null });
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <>
          <Header />
          <main className="wide" style={{ textAlign: 'center', padding: '60px 20px' }}>
            <div className="panel" style={{ maxWidth: '600px', margin: '0 auto', padding: '30px' }}>
              <span style={{ fontSize: '48px', display: 'block', marginBottom: '16px' }}>⚠️</span>
              <h2>Something went wrong</h2>
              <p style={{ color: '#566276', margin: '14px 0 24px', lineHeight: 1.5 }}>
                An unexpected UI rendering error occurred. The application state has been preserved safely.
              </p>
              {this.state.error?.message && (
                <pre
                  style={{
                    background: '#f8fafc',
                    color: '#c3283e',
                    padding: '12px',
                    borderRadius: '6px',
                    textAlign: 'left',
                    overflowX: 'auto',
                    fontSize: '12px',
                    marginBottom: '20px',
                  }}
                >
                  {this.state.error.message}
                </pre>
              )}
              <button className="primary" onClick={this.handleReload}>
                ⌁ Reload Application
              </button>
            </div>
          </main>
        </>
      );
    }

    return this.props.children;
  }
}

export function SkeletonCard() {
  return (
    <div
      className="product"
      style={{
        border: '1px solid #edf0f4',
        borderRadius: '9px',
        overflow: 'hidden',
        background: '#fff',
        opacity: 0.7,
      }}
    >
      <div
        style={{
          height: '155px',
          background: 'linear-gradient(90deg, #f0f2f5 25%, #e6e8eb 50%, #f0f2f5 75%)',
          backgroundSize: '200% 100%',
          animation: 'skeleton-pulse 1.5s infinite',
        }}
      />
      <div style={{ padding: '12px', display: 'grid', gap: '8px' }}>
        <div style={{ height: '18px', width: '70%', background: '#e6e8eb', borderRadius: '4px' }} />
        <div style={{ height: '14px', width: '40%', background: '#edf0f4', borderRadius: '4px' }} />
        <div style={{ height: '16px', width: '50%', background: '#e6e8eb', borderRadius: '4px' }} />
      </div>
    </div>
  );
}

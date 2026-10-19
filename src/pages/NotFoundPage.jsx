import { Link } from 'react-router-dom';
import { Header } from '../components/Layout';
import { Banner } from '../components/Ui';

export default function NotFoundPage() {
  return (
    <>
      <Header />
      <main className="wide" style={{ textAlign: 'center', padding: '60px 20px' }}>
        <Banner
          title="404 — Page Not Found"
          subtitle="The page you are looking for does not exist or has been relocated."
        />
        <div style={{ marginTop: '30px' }}>
          <p style={{ color: '#566276', fontSize: '16px', marginBottom: '20px' }}>
            Looking for something specific on InfyExchange? Explore active listings or search community needs.
          </p>
          <div style={{ display: 'inline-flex', gap: '12px' }}>
            <Link className="primary" to="/listings">
              Browse Listings
            </Link>
            <Link className="outline" to="/needs">
              Explore Needs
            </Link>
            <Link className="outline" to="/">
              Back to Home
            </Link>
          </div>
        </div>
      </main>
    </>
  );
}

import { Link } from 'react-router-dom';
import { Header } from '../components/Layout';
import { Banner } from '../components/Ui';

export default function NotFoundPage() {
  return (
    <>
      <Header />
      <main className="wide" style={{ textAlign: 'center', padding: '60px 20px' }}>
        <Banner
          title="Page not found"
          subtitle="That page does not exist, or the link is out of date."
        />
        <div style={{ marginTop: '30px' }}>
          <p style={{ color: '#566276', fontSize: '16px', marginBottom: '20px' }}>
            Looking for something? Browse what other trainees are sharing, or see what they are asking for.
          </p>
          <div style={{ display: 'inline-flex', gap: '12px', flexWrap: 'wrap', justifyContent: 'center' }}>
            <Link className="primary" to="/listings">
              Browse items
            </Link>
            <Link className="outline" to="/needs">
              See requests
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

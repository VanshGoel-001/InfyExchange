import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import * as I from "lucide-react";
import { useAuth } from "../context/AuthContext";
import logoSvg from "../assets/InfyExchange-logo-v2.svg";
import { ROLES, formatDate, initials, labelOf } from "../utils/labels";
export function Logo() {
  return (
    <Link to="/" className="logo">
      <img
        src={logoSvg}
        alt="InfyExchange"
        style={{ width: "48px", height: "48px", objectFit: "contain" }}
      />
      <span>
        <b>
          <em>Infy</em>Exchange
        </b>
        <small>Buy · Rent · Lend · Give · Within Our Community</small>
      </span>
    </Link>
  );
}
export function Header() {
  const nav = useNavigate(),
    { user, logout } = useAuth(),
    [mobileOpen, setMobileOpen] = useState(false),
    [accountOpen, setAccountOpen] = useState(false);
  const closeMobile = () => setMobileOpen(false);
  const leave = () => {
    logout();
    nav("/");
    setAccountOpen(false);
    closeMobile();
  };
  return (
    <header>
      <Logo />
      <button
        className="menu-toggle"
        aria-label="Toggle menu"
        aria-expanded={mobileOpen}
        onClick={() => setMobileOpen((x) => !x)}
      >
        {mobileOpen ? <I.X /> : <I.Menu />}
      </button>
      <nav className={mobileOpen ? "open" : ""}>
        <NavLink onClick={closeMobile} to="/">
          Home
        </NavLink>
        <NavLink onClick={closeMobile} to="/listings">
          Listings
        </NavLink>
        <NavLink onClick={closeMobile} to="/needs">
          Needs
        </NavLink>
      </nav>
      {!user ? (
        <div className={"nav-actions " + (mobileOpen ? "open" : "")}>
          <Link className="outline" onClick={closeMobile} to="/login">
            Login
          </Link>
          <Link className="primary" onClick={closeMobile} to="/register">
            Register
          </Link>
        </div>
      ) : (
        <div
          className={
            "nav-actions account-actions " + (mobileOpen ? "open" : "")
          }
        >
          {user.profile_complete && (
            <details className="post-menu">
              <summary className="primary">
                <I.Plus /> Post
              </summary>
              <div className="post-menu-list">
                <Link to="/listings/new" onClick={closeMobile}>
                  <I.Package /> Post an item
                  <small>Sell, rent, lend or give away</small>
                </Link>
                <Link to="/needs/new" onClick={closeMobile}>
                  <I.Megaphone /> Post a request
                  <small>Ask for something you need</small>
                </Link>
              </div>
            </details>
          )}
          <div className="account-menu">
            <button
              className="account-trigger"
              aria-expanded={accountOpen}
              onClick={() => setAccountOpen((x) => !x)}
            >
              <span className="avatar">{initials(user.name)}</span>
              <b>{user.name}</b>
              <I.ChevronDown />
            </button>
            {accountOpen && (
              <div className="account-dropdown">
                <Link to="/profile" onClick={() => setAccountOpen(false)}>
                  <I.UserRound /> Profile
                </Link>
                <Link to="/my-listings" onClick={() => setAccountOpen(false)}>
                  <I.ClipboardList /> My items
                </Link>
                <Link to="/my-needs" onClick={() => setAccountOpen(false)}>
                  <I.Megaphone /> My requests
                </Link>
                <Link to="/activity" onClick={() => setAccountOpen(false)}>
                  <I.MessageSquare /> Enquiries
                </Link>
                {user.is_admin && (
                  <Link
                    to="/admin"
                    onClick={() => setAccountOpen(false)}
                    style={{ color: "#0874ee", fontWeight: 600 }}
                  >
                    <I.ShieldCheck /> Admin
                  </Link>
                )}
                <button onClick={leave}>
                  <I.LogOut /> Logout
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
export function Footer() {
  return (
    <footer>
      <Logo />
      <p>
        A community platform for Infosys Mysore trainees to buy, rent, borrow
        and give away sports gear within campus.
      </p>
      <div>
        <b>Quick Links</b>
        <Link to="/">Home</Link>
        <Link to="/listings">Listings</Link>
        <Link to="/needs">Needs</Link>
      </div>
      <span>© 2026 InfyExchange. All rights reserved.</span>
    </footer>
  );
}
export function Sidebar() {
  const { user, logout } = useAuth(),
    nav = useNavigate();
  const navLinks = [
    [I.Home, "Home", "/"],
    [I.UserRound, "My profile", "/profile"],
    [I.ClipboardList, "My items", "/my-listings"],
    [I.Megaphone, "My requests", "/my-needs"],
    [I.MessageSquare, "Enquiries", "/activity"],
  ];
  if (user?.is_admin) navLinks.push([I.ShieldCheck, "Admin", "/admin"]);
  return (
    <aside className="side">
      <div className="profile-pic">{initials(user?.name)}</div>
      <b>{user?.name}</b>
      <small>
        {labelOf(ROLES, user?.role)}
        {user?.is_admin ? " · Admin" : ""}
        {user?.joining_date ? ` · Joined ${formatDate(user.joining_date)}` : ""}
      </small>
      {navLinks.map(([X, n, to]) => (
        <NavLink to={to} key={n}>
          <X />
          {n}
        </NavLink>
      ))}
      <button
        className="logout"
        onClick={() => {
          logout();
          nav("/");
        }}
      >
        <I.LogOut />
        Logout
      </button>
    </aside>
  );
}
export function AppShell({ children }) {
  return (
    <>
      <Header />
      <div className="app-layout">
        <Sidebar />
        <main className="dashboard">{children}</main>
      </div>
    </>
  );
}

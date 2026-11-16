import { useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import * as I from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useMediaQuery } from "../hooks/useMediaQuery";
import NotificationBell from "./NotificationBell";
import { SectionBoundary } from "./Section";
import { Toast } from "./Ui";
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
        <small className="tagline-full">Buy · Rent · Lend · Give · Within Our Community</small>
        <small className="tagline-short">Buy · Rent · Lend · Give</small>
      </span>
    </Link>
  );
}

const PHONE = "(max-width: 760px)";

// Phones get one slide-in panel under the header; larger screens keep the inline nav and account dropdown.
export function Header() {
  const nav = useNavigate(),
    { pathname } = useLocation(),
    { user, logout } = useAuth(),
    phone = useMediaQuery(PHONE),
    [menuOpen, setMenuOpen] = useState(false),
    [postOpen, setPostOpen] = useState(false),
    [accountOpen, setAccountOpen] = useState(false);

  const leave = () => {
    logout();
    nav("/");
    setAccountOpen(false);
    setMenuOpen(false);
  };

  // Navigating anywhere, or growing the window past phone size, closes the panel.
  useEffect(() => {
    setMenuOpen(false);
    setPostOpen(false);
  }, [pathname, phone]);

  // While the panel is open the page behind it must not scroll; Escape closes it.
  useEffect(() => {
    if (!menuOpen) return undefined;
    const onKey = (event) => event.key === "Escape" && setMenuOpen(false);
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [menuOpen]);

  if (phone) {
    return (
      <>
        <Toast />
        <header>
          <Logo />
          <div className="header-tools">
            {user && <SectionBoundary name="notifications" context="notifications" compact><NotificationBell /></SectionBoundary>}
            <button
              className="menu-toggle"
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              aria-expanded={menuOpen}
              aria-controls="phone-menu"
              onClick={() => setMenuOpen((open) => !open)}
            >
              {menuOpen ? <I.X /> : <I.Menu />}
            </button>
          </div>
        </header>
        {menuOpen && <div className="drawer-backdrop" onClick={() => setMenuOpen(false)} aria-hidden="true" />}
        <aside id="phone-menu" className={`drawer${menuOpen ? " open" : ""}`} aria-label="Menu" hidden={!menuOpen}>
          <nav className="drawer-links" aria-label="Main">
            <NavLink to="/" end><I.Home aria-hidden="true" /> Home</NavLink>
            <NavLink to="/listings" end><I.Package aria-hidden="true" /> Listings</NavLink>
            <NavLink to="/needs" end><I.Megaphone aria-hidden="true" /> Needs</NavLink>
          </nav>
          <hr />
          {user ? (
            <>
              <div className="drawer-user">
                <span className="avatar">{initials(user.name)}</span>
                <b>{user.name}</b>
              </div>
              {user.profile_complete && (
                <div className="drawer-post">
                  <button type="button" className="primary" aria-expanded={postOpen} onClick={() => setPostOpen((open) => !open)}>
                    <I.Plus aria-hidden="true" /> Post
                  </button>
                  {postOpen && (
                    <div className="drawer-links">
                      <Link to="/listings/new"><I.Package aria-hidden="true" /> Post a listing</Link>
                      <Link to="/needs/new"><I.Megaphone aria-hidden="true" /> Post a need</Link>
                    </div>
                  )}
                </div>
              )}
              <nav className="drawer-links" aria-label="Account">
                <NavLink to="/profile"><I.UserRound aria-hidden="true" /> Profile</NavLink>
                <NavLink to="/my-listings"><I.ClipboardList aria-hidden="true" /> My listings</NavLink>
                <NavLink to="/my-needs"><I.Megaphone aria-hidden="true" /> My needs</NavLink>
                <NavLink to="/activity"><I.MessageSquare aria-hidden="true" /> Enquiries</NavLink>
                {user.is_admin && <NavLink to="/admin"><I.ShieldCheck aria-hidden="true" /> Admin</NavLink>}
              </nav>
              <hr className="push" />
              <button type="button" className="drawer-logout" onClick={leave}>
                <I.LogOut aria-hidden="true" /> Logout
              </button>
            </>
          ) : (
            <div className="drawer-auth">
              <Link className="outline" to="/login">Login</Link>
              <Link className="primary" to="/register">Register</Link>
            </div>
          )}
        </aside>
      </>
    );
  }

  return (
    <>
      <Toast />
      <header>
        <Logo />
        <nav>
          <NavLink to="/">Home</NavLink>
          <NavLink to="/listings">Listings</NavLink>
          <NavLink to="/needs">Needs</NavLink>
        </nav>
        {!user ? (
          <div className="nav-actions">
            <Link className="outline" to="/login">Login</Link>
            <Link className="primary" to="/register">Register</Link>
          </div>
        ) : (
          <div className="nav-actions account-actions">
            {user.profile_complete && (
              <details className="post-menu">
                <summary className="primary">
                  <I.Plus /> Post
                </summary>
                <div className="post-menu-list">
                  <Link to="/listings/new">
                    <I.Package /> Post a listing
                    <small>Sell, rent, lend or give away</small>
                  </Link>
                  <Link to="/needs/new">
                    <I.Megaphone /> Post a need
                    <small>Ask for something you need</small>
                  </Link>
                </div>
              </details>
            )}
            <SectionBoundary name="notifications" context="notifications" compact><NotificationBell /></SectionBoundary>
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
                    <I.ClipboardList /> My listings
                  </Link>
                  <Link to="/my-needs" onClick={() => setAccountOpen(false)}>
                    <I.Megaphone /> My needs
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
    </>
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
    [I.ClipboardList, "My listings", "/my-listings"],
    [I.Megaphone, "My needs", "/my-needs"],
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

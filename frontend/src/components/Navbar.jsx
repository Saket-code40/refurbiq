const LINKS = [
  { href: "#home", label: "Home" },
  { href: "#how-it-works", label: "How it works" },
  { href: "#live-demo", label: "Live demo" },
  { href: "#results", label: "Results" },
  { href: "#methodology", label: "Methodology" },
];

export default function Navbar() {
  return (
    <header className="sticky top-0 z-50 shadow-card">
      <nav className="bg-navy text-white" aria-label="Main navigation">
        <div className="max-w-6xl mx-auto px-4 min-h-16 flex flex-wrap items-center justify-between gap-x-6 gap-y-1 py-2">
          <a
            href="#home"
            className="font-serif text-2xl font-bold tracking-wide rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
          >
            RefurbIQ
          </a>
          <ul className="flex flex-wrap items-center gap-x-5 gap-y-1">
            {LINKS.map((link) => (
              <li key={link.href}>
                <a
                  href={link.href}
                  className="text-sm font-medium text-white/90 hover:text-white rounded px-1 py-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
                >
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </nav>
      {/* Persistent provenance badge — always visible. */}
      <div
        className="bg-crimson text-white text-center text-xs sm:text-sm font-medium py-1.5 px-4"
        role="note"
      >
        Synthetic demonstration corpus — not verified marketplace data
      </div>
    </header>
  );
}
export default function Footer() {
  return (
    <footer className="bg-navy text-white">
      <div className="max-w-6xl mx-auto px-4 py-10 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm">
        <p className="font-serif text-lg font-bold">RefurbIQ</p>
        <p className="text-white/70 text-center">
          Aspect-based sentiment analysis of refurbished electronics —
          synthetic demonstration corpus, not verified marketplace data.
        </p>
        <a
          href="https://github.com/Saket-code40/refurbiq"
          target="_blank"
          rel="noreferrer"
          className="text-white/90 underline underline-offset-2 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
        >
          GitHub
        </a>
      </div>
    </footer>
  );
}
import { RecordPage } from "./record/RecordPage";

/** Lab Home (SPEC 13.1). Device check, Sessions and Results arrive with M2.1, M2.8 and M4.4. */
function Home() {
  return (
    <main>
      <h1>PulseLens Lab</h1>
      <p>Experiments site: record labelled sessions on any phone or laptop.</p>
      <nav className="home-nav">
        <a className="button primary" href="/record">
          Record
        </a>
      </nav>
    </main>
  );
}

export function App({ path = location.pathname }: { path?: string }) {
  return path.replace(/\/+$/, "") === "/record" ? <RecordPage /> : <Home />;
}

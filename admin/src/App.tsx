const apiUrl = import.meta.env.VITE_API_URL;

export default function App() {
  return (
    <main style={{ padding: "2rem", fontFamily: "sans-serif" }}>
      <h1>Kina Admin</h1>
      <p>API endpoint: {apiUrl}</p>
    </main>
  );
}

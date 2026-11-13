import Link from "next/link";
import { SiteFrame } from "@/components/site/SiteChrome";
import { SITE } from "@/domain/site";

const MODES = [
  { name: "Simple", text: "One model of your choice answers quickly, with the thinking level, answer length and tools you pick." },
  { name: "Thinker", text: "Two to five models answer on their own or debate, then one combines the best of them." },
  { name: "Planner", text: "Writes a plan you approve, runs the steps in order, checks the results and builds the final file." },
];

const FEATURES = [
  { name: "Cost you can see", text: "Every question has a budget cap and a live meter. You see tokens and dollars for each call." },
  { name: "Your documents", text: "Attach PDFs, scans, images and Office files. Tables and charts are read, and answers cite pages." },
  { name: "Memory you control", text: "Long-term facts and checked summaries keep long chats usable. See, edit or delete anything it remembers." },
  { name: "Finished files", text: "Get a PDF, Markdown, web page or code file that passed an automatic final check." },
  { name: "Private by design", text: "Each account's chats, files and memory are separate. Delete a chat or your whole account at any time." },
  { name: "Choose your models", text: "Pick from the full OpenRouter catalogue, with capabilities and prices shown before you send." },
];

export default function Home() {
  return (
    <SiteFrame>
      <section className="hero" aria-labelledby="hero-title">
        <h1 id="hero-title">One assistant. Three ways to think.</h1>
        <p>{SITE.name} answers quickly, debates with a team of agents, or plans and builds a finished document, with the cost and the reasoning in plain sight.</p>
        <div className="row">
          <Link className="btn primary" href="/signup">Get started</Link>
          <Link className="btn" href="/login">Sign in</Link>
        </div>
      </section>

      <section className="section" aria-labelledby="modes-title">
        <h2 id="modes-title">Pick how much thinking a question deserves</h2>
        <p>Switch modes in one click. Everything else (budget, files, memory, history) works the same way in all of them.</p>
        <div className="grid">
          {MODES.map((m) => (
            <div className="card" key={m.name}><h3>{m.name}</h3><p>{m.text}</p></div>
          ))}
        </div>
      </section>

      <section className="section" aria-labelledby="features-title">
        <h2 id="features-title">Built for work you want to trust</h2>
        <div className="grid">
          {FEATURES.map((f) => (
            <div className="card" key={f.name}><h3>{f.name}</h3><p>{f.text}</p></div>
          ))}
        </div>
      </section>

      <section className="section" aria-labelledby="how-title">
        <h2 id="how-title">How it works</h2>
        <ol className="steps">
          <li><span><strong>Create an account.</strong> Each account gets a monthly usage allowance, so there are no surprise bills.</span></li>
          <li><span><strong>Ask or attach.</strong> Type a question, add documents, and and pick Simple, Thinker or Planner.</span></li>
          <li><span><strong>Watch it work.</strong> Steps, tools and costs stream in as the answer is built and checked.</span></li>
          <li><span><strong>Keep what you need.</strong> Download chats and files, or delete them whenever you like.</span></li>
        </ol>
      </section>
    </SiteFrame>
  );
}

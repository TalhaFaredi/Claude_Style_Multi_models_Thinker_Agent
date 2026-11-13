import Link from "next/link";
import { SiteFrame } from "@/components/site/SiteChrome";

export default function NotFound() {
  return (
    <SiteFrame>
      <h1 className="page-title">Page not found</h1>
      <p className="page-lead">That page does not exist or has moved.</p>
      <div className="row"><Link className="btn primary" href="/">Go to the home page</Link><Link className="btn" href="/app">Open the app</Link></div>
    </SiteFrame>
  );
}

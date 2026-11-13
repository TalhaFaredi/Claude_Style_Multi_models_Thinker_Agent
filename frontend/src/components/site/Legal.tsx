import { SITE } from "@/domain/site";

/** Shown until NEXT_PUBLIC_LEGAL_REVIEWED=1: these pages are a starting template, not legal advice. */
export function TemplateNotice() {
  if (SITE.legalReviewed) return null;
  return (
    <div className="alert notice" role="note" style={{ margin: "20px 0" }}>
      <strong>Template text.</strong> This page is a starting point written for how this software works. It is not legal advice. The operator of this site must review it
      with a qualified lawyer, fill in the details and then set <code>NEXT_PUBLIC_LEGAL_REVIEWED=1</code> to remove this notice.
    </div>
  );
}

export function Operator() {
  return <>{SITE.operator || `the operator of ${SITE.name}`}</>;
}

export function ContactLine() {
  return SITE.contact ? <a href={`mailto:${SITE.contact}`}>{SITE.contact}</a> : <em>the contact address published by the operator</em>;
}

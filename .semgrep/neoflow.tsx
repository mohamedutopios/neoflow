import DOMPurify from "dompurify";

export function Detail({ d }: { d: { description: string } }) {
  // ruleid: neoflow-dangerously-set-inner-html
  const brut = <div className="description" dangerouslySetInnerHTML={{ __html: d.description }} />;
  // ok: neoflow-dangerously-set-inner-html
  const assaini = <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(d.description) }} />;
  // ok: neoflow-dangerously-set-inner-html
  const texte = <p className="description">{d.description}</p>;
  return <div>{brut}{assaini}{texte}</div>;
}

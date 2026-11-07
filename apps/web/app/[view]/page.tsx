import { notFound } from "next/navigation";
import { Suspense } from "react";
import Workspace, { type View } from "../workspace";

export default async function Page({ params }: { params: Promise<{ view: string }> }) {
  const { view } = await params;
  if (!["overview", "risk", "cohorts", "status"].includes(view)) notFound();
  return (
    <Suspense fallback={<p role="status">Loading workspace…</p>}>
      <Workspace view={view as View} />
    </Suspense>
  );
}

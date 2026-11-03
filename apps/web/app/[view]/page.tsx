import { notFound } from "next/navigation";
import Workspace, { type View } from "../workspace";

export default async function Page({ params }: { params: Promise<{ view: string }> }) {
  const { view } = await params;
  if (!["risk", "cohorts", "status"].includes(view)) notFound();
  return <Workspace view={view as View} />;
}

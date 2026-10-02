"use client";

import Link from "next/link";
import {usePathname} from "next/navigation";

export default function TrainingChrome({children}:{children:React.ReactNode}) {
  const pathname=usePathname();
  const isTrainingHome=pathname==="/training"||pathname==="/";
  return <>
    {isTrainingHome&&<header className="topbar"><Link href="/training" className="brand"><span className="brandMark">派</span><span>12345派单训练</span></Link><span className="tag">业务能力训练</span></header>}
    <main className={`shell${isTrainingHome?"":" trainingShell"}`}>{children}</main>
  </>;
}

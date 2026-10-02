"use client";
import Link from "next/link";
import {useCallback, useEffect, useState} from "react";
import {api, PracticeProgress} from "@/lib/api";

type Level = {level:number; state:"locked"|"passed"|"unlocked"; best_score:number; latest_score:number; attempt_count:number};

export default function DashboardPage() {
  const [levels,setLevels]=useState<Level[]>();
  const [practice,setPractice]=useState<PracticeProgress>();
  const [error,setError]=useState("");
  const load=useCallback(()=>{setError("");Promise.all([api<Level[]>("/levels"),api<PracticeProgress>("/practice/progress")]).then(([l,p])=>{setLevels(l);setPractice(p)}).catch(()=>setError("暂时无法获取训练进度，请稍后重试。"));},[]);
  useEffect(()=>{load()},[load]);
  const passed=levels?.filter(x=>x.state==="passed").length;
  const highest=levels?.filter(x=>x.state!=="locked").at(-1)?.level;
  return <>
    <section className="hero"><p className="eyebrow">DISPATCH TRAINING</p><h1>练判断，懂职责，派得准</h1><p>通过真实业务场景，训练热线工单承办部门判断能力。</p></section>
    {error&&<div className="inlineNotice"><span>{error}</span><button onClick={load}>重试</button></div>}
    <section className="modeGrid" aria-busy={!levels||!practice}>
      <article className="modeCard"><div className="modeIcon">关</div><div><p className="eyebrow">CHALLENGE</p><h2>闯关模式</h2><p>10个固定关卡，每关10题，60分通关并永久解锁下一关。</p></div><div className="progressSummary"><span>已通过 <b>{passed ?? "—"} / 10</b></span><span>最高解锁 <b>Level {highest ?? "—"}</b></span></div><Link className="primary" href="/training/challenge">进入闯关</Link></article>
      <article className="modeCard"><div className="modeIcon pale">练</div><div><p className="eyebrow">PRACTICE</p><h2>自由练习</h2><p>每轮随机10题，未做题优先；完成全部题目后进入下一循环。</p></div><div className="progressSummary"><span>Cycle {practice?.cycle ?? "—"}</span><span>已完成 <b>{practice?.completed_count ?? "—"} / {practice?.total_count ?? "—"}</b></span><span>剩余 <b>{practice?.remaining_count ?? "—"}</b></span></div><Link className="secondary" href="/training/practice">开始自由练习</Link></article>
    </section>
  </>;
}

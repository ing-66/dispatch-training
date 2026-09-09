"use client";
import Link from "next/link";
import {useEffect, useState} from "react";
import {api} from "@/lib/api";

type Dashboard = {highest_unlocked_level: number; practice: {completed_sessions: number; answered: number; accuracy: number}};
export default function DashboardPage() {
  const [data, setData] = useState<Dashboard>();
  useEffect(() => { api<Dashboard>("/training/dashboard").then(setData).catch(() => undefined); }, []);
  return <>
    <section className="hero"><p className="eyebrow">DISPATCH TRAINING</p><h1>练判断，懂职责，派得准</h1><p>通过真实业务场景，训练热线工单承办部门判断能力。</p></section>
    <section className="modeGrid">
      <article className="modeCard"><div className="modeIcon">关</div><div><p className="eyebrow">CHALLENGE</p><h2>闯关模式</h2><p>10个固定关卡，每关10题，60分通关并永久解锁下一关。</p></div><div className="metric"><strong>{data?.highest_unlocked_level ?? "—"}</strong><span>/ 10 当前进度</span></div><Link className="primary" href="/training/challenge">继续闯关</Link></article>
      <article className="modeCard"><div className="modeIcon pale">练</div><div><p className="eyebrow">PRACTICE</p><h2>自由练习</h2><p>每轮随机10题，未做题优先；完成全部题目后进入下一循环。</p></div><div className="metric"><strong>{data?.practice.answered ?? "—"}</strong><span>累计作答 · 正确率 {data?.practice.accuracy ?? 0}%</span></div><Link className="secondary" href="/training/practice">开始练习</Link></article>
    </section>
  </>;
}

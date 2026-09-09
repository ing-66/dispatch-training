"use client";
import Link from "next/link";
import {useEffect, useState} from "react";
import {api} from "@/lib/api";

type Level = {level:number; state:"locked"|"passed"|"unlocked"; best_score:number; latest_score:number; attempt_count:number};
export default function ChallengePage() {
  const [levels, setLevels] = useState<Level[]>([]);
  useEffect(() => { api<Level[]>("/levels").then(setLevels); }, []);
  return <><div className="pageHead"><div><p className="eyebrow">CHALLENGE MAP</p><h1>闯关模式</h1><p>固定题目可反复训练；通过后不会因重试低分而失去进度。</p></div><Link className="textLink" href="/training">返回首页</Link></div>
  <div className="levels">{levels.map(item => <article key={item.level} className={`levelCard ${item.state}`}><div className="levelNo">{String(item.level).padStart(2,"0")}</div><div><h2>第 {item.level} 关</h2><p>{item.state === "locked" ? "尚未解锁" : item.state === "passed" ? `已通过 · 最高 ${item.best_score} 分` : item.attempt_count ? `最近 ${item.latest_score} 分` : "等待挑战"}</p></div>{item.state === "locked" ? <span className="lock">锁定</span> : <Link className="smallButton" href={`/training/challenge/${item.level}`}>{item.state === "passed" ? "再次挑战" : "开始挑战"}</Link>}</article>)}</div></>;
}

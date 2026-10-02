"use client";
import Link from "next/link";
import {use, useCallback, useEffect, useState} from "react";
import {api, PracticeProgress} from "@/lib/api";
type Result={mode:"challenge"|"practice";level?:number;score:number;correct_count:number;incorrect_count:number;passed_this_attempt:boolean;is_passed:boolean};
export default function ResultPage({params}:{params:Promise<{attempt:string}>}){
  const {attempt}=use(params);const [r,setR]=useState<Result>();const [practice,setPractice]=useState<PracticeProgress>();const [error,setError]=useState("");
  const load=useCallback(()=>{setError("");api<Result>(`/attempts/${attempt}`).then(async result=>{setR(result);if(result.mode==="practice")setPractice(await api<PracticeProgress>("/practice/progress"));}).catch(()=>setError("暂时无法获取本轮成绩，请稍后重试。"));},[attempt]);
  useEffect(()=>{load()},[load]);
  if(error)return <div className="notice"><h2>成绩加载失败</h2><p>{error}</p><div className="noticeActions"><button onClick={load}>重试</button><Link className="secondary" href="/training">返回训练首页</Link></div></div>;
  if(!r)return <div className="loading">正在汇总成绩…</div>;
  const permanentAfterLow=r.mode==="challenge"&&!r.passed_this_attempt&&r.is_passed;
  return <article className="resultCard"><p className="eyebrow">SESSION RESULT</p><h1>{r.mode==="challenge"?`第 ${r.level} 关完成`:"本轮练习完成"}</h1><div className="score">{r.score}<span>/ 100</span></div><div className="resultStats"><span>答对 <b>{r.correct_count}</b> 题</span><span>答错 <b>{r.incorrect_count}</b> 题</span><span>正确率 <b>{r.score}%</b></span></div>
  {r.mode==="challenge"&&<><h2 className={r.passed_this_attempt?"pass":"fail"}>{r.passed_this_attempt?"通关":"本次未通关"}</h2>{r.passed_this_attempt&&r.level!<10&&<p className="resultNote">下一关已解锁</p>}{permanentAfterLow&&<p className="resultNote">该关此前已通过，永久通关状态保持不变。</p>}</>}
  {r.mode==="practice"&&practice&&<div className="cycleResult"><b>Cycle {practice.cycle}</b><span>已完成 {practice.completed_count} / {practice.total_count}</span><span>剩余 {practice.remaining_count}</span></div>}
  <div className="resultActions">{r.mode==="challenge"?<><Link className="secondary" href="/training/challenge">返回关卡</Link><Link className="secondary" href={`/training/challenge/${r.level}`}>重新挑战</Link>{r.is_passed&&r.level!<10&&<Link className="primary" href={`/training/challenge/${r.level!+1}`}>继续下一关</Link>}</>:<><Link className="secondary" href="/training">返回训练首页</Link><Link className="primary" href="/training/practice">再练10题</Link></>}</div></article>;
}

"use client";
import {useEffect, useState} from "react";
import {useRouter} from "next/navigation";
import {api, Attempt, Feedback} from "@/lib/api";

export default function Quiz({mode, level}:{mode:"challenge"|"practice"; level?:number}) {
  const router = useRouter(); const [attempt,setAttempt]=useState<Attempt>(); const [index,setIndex]=useState(0);
  const [selections,setSelections]=useState<Record<string,string>>({}); const [feedbacks,setFeedbacks]=useState<Record<string,Feedback>>({}); const [error,setError]=useState("");
  const [busy,setBusy]=useState(false); const [reload,setReload]=useState(0);
  useEffect(() => { setError("");setAttempt(undefined);setIndex(0);setSelections({});setFeedbacks({});api<Attempt>(mode === "challenge" ? `/levels/${level}/start` : "/practice/start", {method:"POST"}).then(setAttempt).catch(()=>setError("暂时无法开始训练，请稍后重试。")); }, [mode,level,reload]);
  if (error) return <div className="notice"><h2>暂时无法开始</h2><p>{error}</p><div className="noticeActions"><button onClick={()=>setReload(x=>x+1)}>重试</button><button onClick={()=>router.push("/training")}>返回训练首页</button></div></div>;
  if (!attempt) return <div className="loading">正在准备题目…</div>;
  const question=attempt.questions[index];
  const selected=selections[question.id]??""; const feedback=feedbacks[question.id];
  async function submit(){if(!selected||busy||feedback)return;setBusy(true);setError("");try{const result=await api<Feedback>(`/attempts/${attempt!.attempt_id}/answer`,{method:"POST",body:JSON.stringify({question_id:question.id,selected_department_id:selected})});setFeedbacks(current=>({...current,[question.id]:result}));}catch{setError("答案提交失败，请检查网络后重试。");}finally{setBusy(false);}}
  async function next(){if(busy||!feedback)return;if(index<attempt!.questions.length-1){setIndex(index+1);setError("");return;}setBusy(true);try{await api(`/attempts/${attempt!.attempt_id}/complete`,{method:"POST"});router.push(`/training/result/${attempt!.attempt_id}`);}catch{setError("成绩提交失败，请稍后重试。");setBusy(false);}}
  function previous(){if(index>0&&!busy){setIndex(index-1);setError("");}}
  const optionClass=(departmentId:string)=>{if(!feedback)return selected===departmentId?"selected":"";if(departmentId===feedback.correct_department.department_id)return"correct";if(departmentId===selected&&!feedback.is_correct)return"incorrect";return"muted";};
  return <div className="quizWrap"><div className="quizMeta"><div><p className="eyebrow">{mode === "challenge" ? `LEVEL ${level}` : `PRACTICE · CYCLE ${attempt.practice_cycle}`}</p><h1>{mode === "challenge" ? `第 ${level} 关` : "自由练习"}</h1></div><strong>{index+1} <span>/ {attempt.questions.length}</span></strong></div><div className="progress"><i style={{width:`${(index+1)/attempt.questions.length*100}%`}} /></div>
  <article className="questionCard"><div className="questionStage"><button className="questionArrow questionArrowLeft" aria-label="上一题" title="上一题" disabled={index===0||busy} onClick={previous}>‹</button><button className="questionArrow questionArrowRight" aria-label="下一题" title="下一题" disabled={!feedback||busy} onClick={next}>›</button><p className="questionLabel">工单内容</p>
  <p className="questionOrigin">{question.case_origin === "baiyun_original" ? "白云区历史案例" : question.case_origin === "cross_district_transfer" ? "广州其他区同类案例" : question.case_origin === "citywide_same_target" ? "广州市级统一事项" : question.case_origin === "public_service_same_target" ? "城市公共服务事项" : "训练案例"}</p>
  <h2>{question.case_content}</h2><p className="questionPrompt">该工单应该派发至哪个部门？</p><div className="options">{question.options.map((o,i)=><button disabled={!!feedback||busy} onClick={()=>setSelections(current=>({...current,[question.id]:o.department_id}))} className={optionClass(o.department_id)} key={o.department_id}><span>{String.fromCharCode(65+i)}</span>{o.name}</button>)}</div>{!feedback&&<button className="primary submit" disabled={!selected||busy} onClick={submit}>{busy?"正在提交…":"确认答案"}</button>}
  {error&&<p className="formError">{error}</p>}</div>
  {feedback&&<div className={`feedback ${feedback.is_correct?"right":"wrong"}`}><h3>{feedback.is_correct?"回答正确":"回答错误"}</h3>{!feedback.is_correct&&<p>你的答案：{feedback.selected_department}</p>}<p><b>正确答案：</b>{feedback.correct_department.name}</p><div><b>为什么派给这个部门？</b><p>{feedback.explanation}</p></div><div className="evidence"><b>职责依据</b>{feedback.reference_basis_detail?.title&&<p><strong>{feedback.reference_basis_detail.title}</strong>{feedback.reference_basis_detail.source?` · ${feedback.reference_basis_detail.source}`:""}</p>}<p>{feedback.reference_basis_detail?.excerpt||feedback.reference_basis}</p>{feedback.reference_basis_detail?.reason&&<p>{feedback.reference_basis_detail.reason}</p>}{feedback.reference_basis_detail?.locator&&<small>{feedback.reference_basis_detail.locator}</small>}</div></div>}
  </article></div>;
}

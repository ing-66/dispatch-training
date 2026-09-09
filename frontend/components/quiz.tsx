"use client";
import {useEffect, useState} from "react";
import {useRouter} from "next/navigation";
import {api, Attempt, Feedback} from "@/lib/api";

export default function Quiz({mode, level}:{mode:"challenge"|"practice"; level?:number}) {
  const router = useRouter(); const [attempt,setAttempt]=useState<Attempt>(); const [index,setIndex]=useState(0);
  const [selected,setSelected]=useState(""); const [feedback,setFeedback]=useState<Feedback>(); const [error,setError]=useState("");
  useEffect(() => { api<Attempt>(mode === "challenge" ? `/levels/${level}/start` : "/practice/start", {method:"POST"}).then(setAttempt).catch(e=>setError(e.message)); }, [mode,level]);
  if (error) return <div className="notice"><h2>暂时无法开始</h2><p>{error}</p><button onClick={()=>router.back()}>返回</button></div>;
  if (!attempt) return <div className="loading">正在准备题目…</div>;
  const question=attempt.questions[index];
  async function submit(){ if(!selected)return; const result=await api<Feedback>(`/attempts/${attempt!.attempt_id}/answer`,{method:"POST",body:JSON.stringify({question_id:question.id,selected_department_id:selected})});setFeedback(result); }
  async function next(){ if(index < attempt!.questions.length-1){setIndex(index+1);setSelected("");setFeedback(undefined);return;} await api(`/attempts/${attempt!.attempt_id}/complete`,{method:"POST"});router.push(`/training/result/${attempt!.attempt_id}`); }
  return <div className="quizWrap"><div className="quizMeta"><div><p className="eyebrow">{mode === "challenge" ? `LEVEL ${level}` : `PRACTICE · CYCLE ${attempt.practice_cycle}`}</p><h1>{mode === "challenge" ? `第 ${level} 关` : "自由练习"}</h1></div><strong>{index+1} <span>/ {attempt.questions.length}</span></strong></div><div className="progress"><i style={{width:`${(index+1)/attempt.questions.length*100}%`}} /></div>
  <article className="questionCard"><p className="questionLabel">工单内容</p>
  <p className="questionOrigin">{question.case_origin === "baiyun_original" ? "白云区历史案例" : question.case_origin === "cross_district_transfer" ? "广州其他区同类案例 · 映射至白云职责" : question.case_origin === "citywide_same_target" ? "广州市级统一承办事项" : question.case_origin === "public_service_same_target" ? "城市级公共服务事项" : ""}</p>
  <h2>{question.case_content}</h2><p className="questionPrompt">该工单应该派发至哪个部门？</p><div className="options">{question.options.map((o,i)=><button disabled={!!feedback} onClick={()=>setSelected(o.department_id)} className={selected===o.department_id?"selected":""} key={o.department_id}><span>{String.fromCharCode(65+i)}</span>{o.name}</button>)}</div>{!feedback&&<button className="primary submit" disabled={!selected} onClick={submit}>确认答案</button>}
  {feedback&&<div className={`feedback ${feedback.is_correct?"right":"wrong"}`}><h3>{feedback.is_correct?"回答正确":"回答错误"}</h3>{!feedback.is_correct&&<p>你的答案：{feedback.selected_department}</p>}<p><b>正确答案：</b>{feedback.correct_department.name}</p><div><b>为什么派给这个部门？</b><p>{feedback.explanation}</p></div><div><b>参考依据</b><p>{feedback.reference_basis}</p></div><button className="primary submit" onClick={next}>{index===attempt.questions.length-1?"查看成绩":"下一题"}</button></div>}</article></div>;
}
